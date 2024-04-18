import datetime
import pandas as pd

from celery import shared_task
from django.db.models import Q

from credit_card_service.celery import app
from user.models import User, Loan
from repayment.models import Payment
from repayment.serializers import PaymentSerializer


def get_users_billing_day(day):
    return User.objects.filter(billing_day=int(day))


def update_next_payment_status(loan):
    if Payment.objects.filter(loan=loan.loan_id, status='DUE').exists():
        loan.loan_status = "STOPPED"
        loan.save()
    
    next_payment = Payment.objects.filter(loan=loan.loan_id, status='NOT_DUE').first()
    if next_payment:
        next_payment.status = 'DUE'
        next_payment.save()


def generate_csv(data, filename):
    df = pd.DataFrame(data)
    df.to_csv(filename)


def billing_process(loan, name, date):
    print('Started billing process for', loan, name, date)

    update_next_payment_status(loan)

    billed_payments = Payment.objects.filter(Q(loan=loan.loan_id) & (Q(status="COMPLETED") | Q(status="PARTIALLY_COMPLETED")))
    serialized_billed_payments = PaymentSerializer(billed_payments, many=True).data
    generate_csv(serialized_billed_payments, f'./data/billed_payments_{name}_{date}.csv')

    due_payments = Payment.objects.filter(Q(loan=loan.loan_id) & (Q(status="DUE") | Q(status="NOT_DUE")))
    serialized_due_payments = PaymentSerializer(due_payments, many=True).data
    generate_csv(serialized_due_payments, f'./data/due_payments_{name}_{date}.csv')


@app.task
def billing_queue():
    print('Billing Queue Started')
    now = datetime.datetime.now()
    month_day = now.day
    users = get_users_billing_day(month_day)
    print("Users For Today:", users)

    for user in users:
        name = user.name
        loans = Loan.objects.filter(user=user.user_id)
        print("Loans for:", user.name, loans)
        for loan in loans:
            billing_process(loan, name, f'{now.day}-{now.month}-{now.year}')


@shared_task
def update_next_emis(loan_id):
    loan = Loan.objects.get(loan_id=loan_id)
    print('Current Principal Balance When Extra Payment was done:', loan.principal_balance)
    interest_rate = loan.interest_rate

    current_principal_balance = loan.principal_balance

    payments = Payment.objects.filter(loan=loan_id, status="NOT_DUE")
    today = datetime.datetime.now()
    last_billing_date = datetime.datetime(day=loan.user.billing_day, month=today.month, year=today.year) \
        if today.day > loan.user.billing_day \
        else datetime.datetime(day=loan.user.billing_day, month=today.month - 1 if today.month != 1 else 12, year=today.year if today.month != 1 else today.year - 1)
    
    constant_part_emi = round(current_principal_balance / len(payments))
    print("Constant Part EMI: ", constant_part_emi)

    for payment in payments:
        due_date = datetime.datetime.combine(payment.due_date, datetime.datetime.min.time())
        duration = (due_date - datetime.timedelta(days=15)) - last_billing_date
        days_of_interest = duration.days
        interest_accrued = round(round(interest_rate / 365, 3) * days_of_interest * current_principal_balance / 100) 
        payment.emi_amount = constant_part_emi + interest_accrued
        current_principal_balance -= payment.emi_amount
        payment.save()
