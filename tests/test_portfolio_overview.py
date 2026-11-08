import pandas as pd
import pytest
from portfolio_overview import portfolio_finding


def test_denominator_and_unrounded_six_month_boundary():
    # Account 1: 55% inflow is 550, gap 100, buffer 599 -> under six.
    # Account 2: same gap but buffer 600 -> exactly six, excluded.
    # Account 3: baseline deficit -> outside the positive-surplus denominator.
    # Account 4: positive surplus and no shock deficit -> denominator only.
    frame=pd.DataFrame([dict(account_id=i,month='2025-12',money_in=income,money_out=spend,avg_daily_balance=buffer)
        for i,income,spend,buffer in [(1,1000,650,599),(2,1000,650,600),(3,1000,1100,50),(4,1000,500,1000)]])
    out=portfolio_finding(frame)
    assert out['total_accounts']==4 and out['positive_surplus_accounts']==3
    assert out['under_six_months']==1
    assert 'unrounded' in out['basis']


def test_duplicate_source_rows_are_not_silently_counted():
    f=pd.DataFrame([dict(account_id=1,month='2025-12',money_in=1000,money_out=650,avg_daily_balance=599)]*2)
    with pytest.raises(ValueError,match='duplicate'):portfolio_finding(f)


def test_supplied_portfolio_reproduces_reported_finding():
    import engine
    out=portfolio_finding(engine.load_data()['monthly'])
    assert out['positive_surplus_accounts']==3309 and out['under_six_months']==714
