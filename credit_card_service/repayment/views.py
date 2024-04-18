from datetime import timedelta
import json

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.core.exceptions import ObjectDoesNotExist

from user.models import User, Loan
from repayment.models import Payment, Transaction
from .serializers import PaymentSerializer
from repayment.tasks import update_next_emis


class MakePaymentView(APIView):
    def handle_exception(self, exc):
        if isinstance(exc, (KeyError, ValueError, ObjectDoesNotExist)):
            return Response(data=str(exc), status=status.HTTP_400_BAD_REQUEST)
        return super().handle_exception(exc)

    def validate_data(self, data):
        return data['loan_id'], round(data['amount'])

    def get_total_due_and_days(self, loan_id, loan_disbursement_date):
        all_payments = Payment.objects.filter(loan=loan_id)
        total_due = 0
        i = 0

        for payment in all_payments:
            if payment.status == 'NOT_DUE':
                break
            if payment.status in ('PARTIALLY_COMPLETED', 'DUE'):
                total_due += payment.emi_amount - payment.total_paid if payment.status == 'PARTIALLY_COMPLETED' else payment.emi_amount
            i += 1
        
        if i == 0:
            raise ValueError("No Payments Due")
        duration = all_payments[i-1].due_date - loan_disbursement_date - timedelta(days=15) if i == 1 else all_payments[i-1].due_date - all_payments[i-2].due_date
        return total_due, duration.days
    
    def pay_amount(self, amount, loan_id, min_due):
        loan = Loan.objects.get(loan_id=loan_id)
        if round(round(loan.principal_balance * 0.97) + min_due) < amount:
            raise ValueError("Amount greater than principal balance and interest")
        
        transaction = Transaction(loan=loan, amount=amount)
        transaction.save()
        
        try:
            current_due = Payment.objects.get(loan=loan_id, status="DUE")
            current_due.total_paid += min_due
            loan.principal_balance -= (loan.principal_balance * 0.03)
            current_due.status = "PARTIALLY_COMPLETED"
            current_due.save()
            amount -= min_due
        except ObjectDoesNotExist:
            pass

        if amount == 0:
            return

        if loan.principal_balance == amount or loan.principal_balance == 0:
            loan.principal_balance = 0
            loan.staus = "REPAID"
        else:
            loan.principal_balance -= amount 

        loan.save()

        previous_dues = Payment.objects.filter(loan=loan_id, status="PARTIALLY_COMPLETED")

        for previous_due in previous_dues:
            if amount == 0:
                break
            pending = previous_due.emi_amount - previous_due.total_paid
            if  pending <= amount:
                previous_due.total_paid = previous_due.emi_amount
                previous_due.status = "COMPLETED"
                amount -= pending
            else:
                previous_due.total_paid += amount
                amount = 0
            previous_due.save()

    def get_min_due(self, loan, days):
        return round((loan.principal_balance * 0.03) + round(loan.principal_balance * days * loan.interest_rate / 365 / 100, 3), 3)

    def post(self, request):
        data = json.loads(request.body)
        loan_id, amount = self.validate_data(data)

        loan = Loan.objects.get(loan_id=loan_id)

        if loan.loan_status == "STOPPED":
            raise ValueError("Loan has been stopped as min due is not paid for the previous month")
        
        if loan.loan_status == "REPAID":
            raise ValueError("Loan has been repaid completely")

        total_due, duration_days = self.get_total_due_and_days(loan_id, loan.disbursement_date)

        if total_due == 0:
            raise ValueError("All Payments Already Completed")

        min_due = round(self.get_min_due(loan, duration_days))

        due_payments = Payment.objects.filter(loan=loan_id, status="DUE")

        if amount < min_due and len(due_payments) != 0:
            raise ValueError("Minimum Due to be paid is ", min_due)
        
        self.pay_amount(amount, loan_id, min_due)

        if amount > total_due:
            update_next_emis.delay(loan_id)

        return Response(status=status.HTTP_200_OK)
        

class StatementView(APIView):
    def handle_exception(self, exc):
        if isinstance(exc, (ObjectDoesNotExist, ValueError)):
            return Response(data=str(exc), status=status.HTTP_400_BAD_REQUEST)
        return super().handle_exception(exc)

    def get(self, request):
        loan_id = request.GET.get('loan_id')
        if not loan_id:
            raise ValueError("Loan Id is required")
        payments = Payment.objects.filter(loan=loan_id)

        account_statement = []

        for payment in PaymentSerializer(payments, many=True).data:
            account_statement.append({
                "payment_id": payment['payment_id'],
                "loan_id": payment['loan'],
                "emi_amount": payment['emi_amount'],
                "total_paid": payment['total_paid'],
                "status": payment['status'],
                "due_date": payment['due_date'],
            })
        
        return Response(data=account_statement, status=status.HTTP_200_OK)
