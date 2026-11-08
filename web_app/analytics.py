"""Read-only website views of the supplied CSVs; no external database required."""
from functools import lru_cache
import json

import numpy as np

import engine


def records(frame):
    # Pandas explicitly serializes missing data as null, never NaN in HTTP JSON.
    return json.loads(frame.to_json(orient='records'))


@lru_cache(maxsize=1)
def account_index():
    tables = engine.load_data()
    monthly = tables['monthly'].sort_values(['account_id', 'month'])
    grouped = monthly.groupby('account_id')
    index = grouped[['money_in', 'money_out', 'household_bills']].median()
    index['buffer'] = monthly.groupby('account_id').tail(6).groupby('account_id').avg_daily_balance.mean()
    index['last_month'] = grouped.month.max()
    index['surplus'] = index.money_in - index.money_out
    index['reserve_months'] = index.buffer / index.money_out.replace(0, np.nan)
    loans = tables['loans'].set_index('account_id')
    index['loan_status'] = loans.status
    index['loan_status'] = index.loan_status.fillna('NONE')
    index['active_loan'] = index.loan_status.isin(['C', 'D'])
    index['loan_in_arrears'] = index.loan_status.eq('D')
    return index.reset_index()


def accounts(query='', filter_by='all', offset=0, limit=30):
    frame = account_index()
    if query:
        frame = frame.loc[frame.account_id.astype(str).str.contains(query, regex=False)]
    if filter_by == 'arrears':
        frame = frame.loc[frame.loan_in_arrears]
    elif filter_by == 'surplus':
        frame = frame.loc[frame.surplus > 0]
    elif filter_by == 'shortfall':
        frame = frame.loc[frame.surplus < 0]
    elif filter_by == 'no_loan':
        frame = frame.loc[~frame.active_loan]
    return {'total': len(frame), 'offset': offset, 'items': records(frame.iloc[offset:offset+limit])}


def discovery():
    # Preserve the earlier internal entry point without duplicating portfolio formulae.
    from .portfolio import discovery as portfolio_discovery
    return portfolio_discovery()
