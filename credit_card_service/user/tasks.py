import pandas as pd
from celery import shared_task

TRANSACTIONS_CSV_PATH = './user/transactions.csv'

def read_transactions_csv():
    return pd.read_csv(TRANSACTIONS_CSV_PATH)

def calculate_credit_score(aadhar_id):
    df = read_transactions_csv()
    cur_df = df.loc[df['aadhar_id'] == aadhar_id]

    if cur_df.empty: # User not found
        return -1

    total_credit = cur_df['credit'].sum()
    total_debit = cur_df['debit'].sum()

    account_balance = total_credit - total_debit

    if account_balance >= 1000000:
        return 900
    if account_balance <= 10000:
        return 300

    credit_score = 300 + (account_balance - 10000) // 1500

    return credit_score

@shared_task()
def update_credit_score(aadhar_id):
    credit_score = calculate_credit_score(aadhar_id)
    from .models import User
    user = User.objects.get(aadhar_number=aadhar_id)
    user.credit_score = credit_score
    user.save()
