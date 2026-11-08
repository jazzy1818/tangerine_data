"""Employee portfolio insights calculated from the supplied local records."""
from datetime import datetime, timezone
from functools import lru_cache
from threading import Lock

import numpy as np
import pandas as pd

import engine
from . import analytics

COHORTS = {
    'recurring_shortfalls': ('Repeated monthly shortfalls',
        'Spending exceeded inflow in at least 3 of the latest 12 months; all 12 months must be present.',
        'Ask how the customer covers shortfall months and whether income or spending has changed.'),
    'thin_reserves': ('Less than one month of reserves',
        'Historical average cash is below one month of typical spending, including negative balances.',
        'Confirm accessible cash today and upcoming essential payments.'),
    'payment_timing': ('Overdrafts hidden by month-end recovery',
        'At least one recent month had negative-balance days but ended with a nonnegative balance.',
        'Review the dates of incoming funds and regular payments with the customer.'),
    'shock_exposure': ('Limited cover after an income reduction',
        'Positive typical surplus, but under six months of runway if inflow falls to 55% of its usual level.',
        'Discuss income continuity and available reserves. This is a hypothetical scenario, not a forecast.'),
}
_lock = Lock()
_cache = None


@lru_cache(maxsize=1)
def local_snapshot():
    monthly = engine.load_data()['monthly']
    facts = analytics.account_index().copy()
    cutoff = pd.Period(str(monthly.month.max()), freq='M')
    recent = monthly.loc[monthly.month >= str(cutoff-11)].copy()
    recent['deficit_months'] = (recent.money_out > recent.money_in).astype(int)
    recent['negative_months'] = (recent.days_below_zero > 0).astype(int)
    recent['eligible_negative_months'] = ((recent.days_below_zero > 0) & recent.month_end_balance.notna()).astype(int)
    recent['recovered_months'] = ((recent.days_below_zero > 0) & (recent.month_end_balance >= 0)).astype(int)
    counts = recent.groupby('account_id').agg(
        recent_months=('month', 'count'), deficit_months=('deficit_months', 'sum'),
        negative_months=('negative_months', 'sum'), eligible_negative_months=('eligible_negative_months', 'sum'),
        recovered_months=('recovered_months', 'sum'))
    facts = facts.join(counts, on='account_id')
    facts[list(counts.columns)] = facts[list(counts.columns)].fillna(0).astype(int)
    trend = recent.groupby('month').agg(accounts=('account_id', 'count'),
        deficit_accounts=('deficit_months', 'sum'), total_inflow=('money_in', 'sum'),
        total_spending=('money_out', 'sum')).reset_index()
    meta = {'period_start': str(monthly.month.min()), 'period_end': str(monthly.month.max()),
            'monthly_observations': len(monthly)}
    return facts, trend, meta


def enrich(facts):
    facts = facts.copy()
    for field in ('money_in', 'money_out', 'buffer'):
        facts[field] = pd.to_numeric(facts[field]).astype(float)
    facts['surplus'] = facts.money_in-facts.money_out
    facts['reserve_months'] = facts.buffer/facts.money_out.replace(0, np.nan)
    facts['active_loan'] = facts.loan_status.isin(['C', 'D'])
    facts['loan_in_arrears'] = facts.loan_status.eq('D')
    gap = facts.money_out-.55*facts.money_in
    facts['shock_exposure'] = (facts.surplus > 0) & ((facts.buffer <= 0) | ((gap > 0) & (facts.buffer/gap.replace(0, np.nan) < 6)))
    return facts


def snapshot(refresh=False):
    global _cache
    with _lock:
        if _cache is None or refresh:
            facts, trend, meta = local_snapshot()
            provenance = {'source': 'local', 'label': 'Local records',
                          'queried_at': datetime.now(timezone.utc).isoformat(),
                          'status': 'Calculated from the supplied monthly financial records.'}
            _cache = (enrich(facts), trend, meta, provenance)
        return _cache


def discovery(cohort='recurring_shortfalls', offset=0, limit=25, refresh=False):
    if cohort not in COHORTS:
        raise ValueError('Choose one of the available portfolio groups.')
    facts, trend, meta, provenance = snapshot(refresh)
    masks = {
        'recurring_shortfalls': (facts.recent_months == 12) & (facts.deficit_months >= 3),
        'thin_reserves': facts.reserve_months < 1,
        'payment_timing': facts.recovered_months > 0,
        'shock_exposure': facts.shock_exposure,
    }
    denominators = {'recurring_shortfalls': int((facts.recent_months == 12).sum()),
                    'thin_reserves': int(facts.reserve_months.notna().sum()),
                    'payment_timing': int((facts.recent_months > 0).sum()),
                    'shock_exposure': int((facts.surplus > 0).sum())}
    eligible = (facts.surplus > 0) & (facts.recent_months == 12)
    coverage = facts.reserve_months.dropna()
    bins = [(-np.inf, 0, 'Below zero'), (0, 1, '0–1 month'), (1, 3, '1–3 months'),
            (3, 6, '3–6 months'), (6, np.inf, '6+ months')]
    selected = facts.loc[masks[cohort]].sort_values(['deficit_months', 'reserve_months', 'account_id'],
                                                   ascending=[False, True, True], na_position='last')
    columns = ['account_id', 'money_in', 'money_out', 'surplus', 'buffer', 'reserve_months',
               'last_month', 'recent_months', 'deficit_months', 'negative_months', 'recovered_months', 'loan_in_arrears']
    return {
        'source': provenance['label'], 'provenance': provenance,
        'period_start': meta['period_start'], 'period_end': meta['period_end'],
        'recent_start': str(pd.Period(meta['period_end'], freq='M')-11),
        'accounts': len(facts), 'monthly_observations': int(meta['monthly_observations']),
        'active_loans': int(facts.active_loan.sum()),
        'findings': [
            {'title': 'A surplus can disappear under a shock', 'numerator': int(facts.shock_exposure.sum()),
             'denominator': int((facts.surplus > 0).sum()),
             'description': 'Positive-surplus accounts with under six months of runway when inflow drops to 55%. This is a hypothetical scenario, not a job-loss probability.'},
            {'title': 'Typical surplus can hide difficult months', 'numerator': int((eligible & masks['recurring_shortfalls']).sum()),
             'denominator': int(eligible.sum()),
             'description': 'Positive-surplus accounts with all 12 recent months that spent more than their inflow in at least three months.'},
            {'title': 'Month-end balances can hide overdrafts', 'numerator': int(facts.recovered_months.sum()),
             'denominator': int(facts.eligible_negative_months.sum()),
             'description': 'Recent negative-balance months that ended with a nonnegative balance. Only months with a recorded closing balance are included; these are months, not customers.'},
        ],
        'cohorts': [{'id': key, 'title': item[0], 'description': item[1], 'prompt': item[2],
                     'count': int(masks[key].sum()), 'denominator': denominators[key]} for key, item in COHORTS.items()],
        'worklist': {'cohort': cohort, 'total': len(selected), 'offset': offset, 'limit': limit,
                     'items': analytics.records(selected.iloc[offset:offset+limit][columns])},
        'reserve_distribution': [{'label': label, 'count': int(((coverage >= low) & (coverage < high)).sum())}
                                 for low, high, label in bins],
        'reserve_undefined': int(facts.reserve_months.isna().sum()),
        'monthly_trend': analytics.records(trend),
        'limitations': ['Bank inflows are not verified salary. All monetary amounts are CAD.',
                       'Cash coverage uses the last six observed average daily balances, not live accessible cash.',
                       'Typical inflow and spending are medians over all available history; patterns use the latest 12 calendar months in the dataset.',
                       'Groups can overlap. These indicators guide conversations; they are not credit scores or lending decisions.',
                       'Historical observations end at the dataset cutoff and may not reflect the customer’s current circumstances.'],
    }
