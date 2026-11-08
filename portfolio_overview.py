"""Reproducible portfolio simulation from the supplied monthly CSV only."""
import numpy as np
import pandas as pd


def portfolio_finding(monthly):
    required={'account_id','month','money_in','money_out','avg_daily_balance'}
    if not required.issubset(monthly.columns) or monthly.empty:
        raise ValueError('Portfolio finding requires the supplied monthly account history')
    frame=monthly[list(required)].copy()
    if frame.isna().any().any() or frame.duplicated(['account_id','month']).any():
        raise ValueError('Portfolio history contains missing or duplicate account-month records')
    amounts=frame[['money_in','money_out','avg_daily_balance']].to_numpy(dtype=float)
    if not np.isfinite(amounts).all() or (frame[['money_in','money_out']]<0).any().any():
        raise ValueError('Portfolio history has invalid inflow, spending or balance values')
    frame['month']=pd.to_datetime(frame['month'].astype(str),format='%Y-%m',errors='raise')
    frame=frame.sort_values(['account_id','month'])
    typical=frame.groupby('account_id')[['money_in','money_out']].median()
    typical['buffer']=frame.groupby('account_id').tail(6).groupby('account_id')['avg_daily_balance'].mean()
    positive=typical.loc[typical['money_in']>typical['money_out']].copy()
    gap=positive['money_out']-.55*positive['money_in']
    # Use the unrounded threshold, not the organizer's one-decimal display value.
    short=(positive['buffer']<=0)|((gap>0)&(positive['buffer']<6*gap))
    return {'total_accounts':len(typical),'positive_surplus_accounts':len(positive),
        'under_six_months':int(short.sum()),'inflow_multiplier':.55,
        'source':'monthly_summary.csv','last_month':frame['month'].max().strftime('%Y-%m'),
        'basis':'Full-history median inflows/spending; mean of the last up to six monthly average balances; unrounded runway threshold. No bill increase, repair, credit or relief assumed.'}
