"""Account-level features. Never modify source CSVs or use demographic labels."""
from functools import lru_cache
import math
from pathlib import Path

import numpy as np
import pandas as pd

from engine import calculate_runway, load_data
from .schemas import Baseline, CustomerFeatures, CustomerProfile

DATA_DIR = Path(__file__).resolve().parents[1] / 'data'
REQUIRED = ['money_in', 'money_out', 'household_bills', 'insurance',
            'loan_payments', 'avg_daily_balance']
OPTIONAL = ['min_balance', 'month_end_balance', 'days_below_zero']


def ratio(numerator: float, denominator: float) -> float | None:
    return float(numerator / denominator) if denominator > 0 else None


def validate_monthly(monthly: pd.DataFrame) -> pd.DataFrame:
    missing = set(['account_id', 'month'] + REQUIRED) - set(monthly.columns)
    if missing:
        raise ValueError(f'Missing monthly columns: {sorted(missing)}')
    frame = monthly.copy()
    if frame.empty:
        raise ValueError('No monthly records available.')
    if frame[['account_id', 'month']].isna().any().any():
        raise ValueError('Missing account_id or month.')
    if not frame['month'].astype(str).str.fullmatch(r'\d{4}-(0[1-9]|1[0-2])').all():
        raise ValueError('month must use YYYY-MM.')
    if frame.duplicated(['account_id', 'month']).any():
        raise ValueError('Duplicate account/month rows would distort the official baseline.')
    for col in REQUIRED + [c for c in OPTIONAL if c in frame]:
        frame[col] = pd.to_numeric(frame[col], errors='raise')
        if col in REQUIRED and frame[col].isna().any():
            raise ValueError(f'Missing required values in {col}; repair the source explicitly.')
        if np.isinf(frame[col].to_numpy(dtype=float)).any():
            raise ValueError(f'Non-finite values in {col}.')
    if (frame[['money_in', 'money_out', 'household_bills', 'insurance', 'loan_payments']] < 0).any().any():
        raise ValueError('Monthly inflows/outflows and categories must be nonnegative.')
    if 'days_below_zero' in frame:
        days = frame['days_below_zero'].dropna()
        calendar_days = pd.PeriodIndex(frame['month'], freq='M').days_in_month[
            frame['days_below_zero'].notna().to_numpy()]
        if (days < 0).any() or (days.to_numpy() > calendar_days).any() or (days % 1 != 0).any():
            raise ValueError('Invalid days_below_zero.')
    return frame.sort_values(['account_id', 'month'])


@lru_cache(maxsize=4)
def _read_tables(path: str, monthly_stamp: int, loans_stamp: int):
    root = Path(path)
    monthly = validate_monthly(pd.read_csv(root / 'monthly_summary.csv'))
    loans_path = root / 'loans.csv'
    loans = pd.read_csv(loans_path) if loans_path.exists() else None
    if loans is not None:
        required = {'account_id', 'status', 'monthly_payment'}
        if not required <= set(loans):
            raise ValueError('loans.csv is missing account_id, status, or monthly_payment.')
        if loans['account_id'].duplicated().any():
            raise ValueError('Expected at most one loan per account.')
        if not loans['status'].isin(['A', 'B', 'C', 'D']).all():
            raise ValueError('Unknown loan status.')
        payments = pd.to_numeric(loans['monthly_payment'], errors='raise')
        if payments.isna().any() or not np.isfinite(payments).all() or (payments < 0).any():
            raise ValueError('Invalid loan monthly_payment.')
    return monthly, loans


def load_tables(data_dir: Path = DATA_DIR):
    root = Path(data_dir).resolve()
    monthly_path, loans_path = root / 'monthly_summary.csv', root / 'loans.csv'
    return _read_tables(str(root), monthly_path.stat().st_mtime_ns,
                        loans_path.stat().st_mtime_ns if loans_path.exists() else 0)


def profile_from_history(account_id: int, history: pd.DataFrame,
                         loan_row=None, *, as_of: str, loan_snapshot_available=True,
                         validated=False) -> CustomerProfile:
    frame = history if validated else validate_monthly(history)
    frame = frame.loc[(frame['account_id'] == account_id) & (frame['month'] <= as_of)].sort_values('month')
    if frame.empty:
        raise ValueError(f'Account {account_id} has no history on or before {as_of}.')
    cutoff = pd.Period(as_of, freq='M')
    window_start = str(cutoff - 11)
    recent = frame.loc[frame['month'] >= window_start]
    flags = []
    if len(frame) < 6:
        flags.append('fewer_than_6_history_months')
    if len(recent) < 12:
        flags.append('fewer_than_12_recent_months')
    first, last = pd.Period(frame.iloc[0]['month'], 'M'), pd.Period(frame.iloc[-1]['month'], 'M')
    if last.ordinal - first.ordinal + 1 != len(frame):
        flags.append('missing_calendar_months')
    stale = cutoff.ordinal - last.ordinal
    if stale:
        flags.append('stale_history')
    I, S = float(frame['money_in'].median()), float(frame['money_out'].median())
    F = float(frame[['household_bills', 'insurance', 'loan_payments']].sum(axis=1).median())
    H = float(frame['household_bills'].median())
    B = float(frame.tail(6)['avg_daily_balance'].mean())
    if I == 0:
        flags.append('zero_typical_inflow')
    if S == 0:
        flags.append('zero_typical_spending')
    if B < 0:
        flags.append('negative_historical_buffer')
    if loan_snapshot_available:
        active = loan_row is not None and str(loan_row['status']).strip() in {'C', 'D'}
        P = float(loan_row['monthly_payment']) if active else 0.0
        arrears = loan_row is not None and str(loan_row['status']).strip() == 'D'
    else:
        P, active, arrears = None, None, None
        flags.append('loan_snapshot_unavailable_at_cutoff')

    def available(columns):
        ok = all(c in recent and recent[c].notna().all() for c in columns)
        if not ok:
            flags.extend(f'missing_{c}' for c in columns if c not in recent or recent[c].isna().any())
        return ok and len(recent) > 0

    deficit = float((recent.money_out > recent.money_in).mean()) if len(recent) else None
    inflow_iqr = None
    if len(recent) >= 2:
        inflow_iqr = ratio(recent.money_in.quantile(.75) - recent.money_in.quantile(.25), recent.money_in.median())
        if inflow_iqr is None:
            flags.append('zero_recent_median_inflow')
    negative = recovered = trend = None
    if available(['days_below_zero']):
        negative = float((recent.days_below_zero > 0).mean())
    if available(['days_below_zero', 'month_end_balance']):
        recovered = float(((recent.days_below_zero > 0) & (recent.month_end_balance >= 0)).mean())
    if available(['month_end_balance']) and len(recent) >= 2:
        trend = ratio(float(recent.iloc[-1].month_end_balance - recent.iloc[0].month_end_balance), S)
    return CustomerProfile(
        account_id=account_id, as_of=str(cutoff), last_month=str(last),
        baseline=Baseline(I=I, S=S, F=F, H=H, B=B, P=P, runway=calculate_runway(B, S-I)),
        features=CustomerFeatures(
            surplus_margin=ratio(I-S, I), reserve_months=ratio(B, S),
            fixed_cost_ratio=ratio(F, I), debt_payment_ratio=ratio(P, I) if P is not None else None,
            inflow_iqr_ratio=inflow_iqr, deficit_month_share=deficit,
            negative_balance_month_share=negative, recovered_overdraft_month_share=recovered,
            balance_change_to_spending=trend, active_loan=active, loan_in_arrears=arrears,
            months_observed=len(frame), recent_months=len(recent), stale_months=stale,
            quality_flags=sorted(set(flags)),
        ),
    )


def get_customer_profile(account_id: int, data_dir: Path = DATA_DIR,
                         as_of: str | None = None) -> CustomerProfile:
    monthly, loans = load_tables(data_dir)
    snapshot = str(monthly.month.max())
    cutoff = str(pd.Period(as_of or snapshot, freq='M'))
    rows = loans.loc[loans.account_id == account_id] if loans is not None else pd.DataFrame()
    return profile_from_history(account_id, monthly.loc[monthly.account_id == account_id],
                                rows.iloc[0] if len(rows) else None, as_of=cutoff,
                                loan_snapshot_available=loans is not None and cutoff >= snapshot,
                                validated=True)


def profile_from_engine(customer: dict) -> CustomerProfile:
    """Read the existing engine's profile without mutating it or its cached history."""
    history = customer['history']
    # Use the engine dataset's cutoff, not this account's last row: stale accounts
    # must have identical recent windows in the app and the discovery/CLI paths.
    cutoff = str(load_data()['monthly']['month'].max())
    profile = profile_from_history(customer['account_id'], history, as_of=cutoff)
    # The history is the source of exact I/S/F/H/B. Reject an inconsistent caller
    # rather than silently pairing one baseline with ratios from another.
    for name in ['I', 'S', 'F', 'H', 'B']:
        supplied = customer.get(f'raw_{name}')
        if supplied is not None and not math.isclose(
            float(supplied), getattr(profile.baseline, name), rel_tol=1e-12, abs_tol=1e-8
        ):
            raise ValueError(f'Engine raw_{name} disagrees with the supplied account history.')
    payment = customer.get('raw_P', customer.get('P'))
    if payment is None:
        raise ValueError('Engine profile is missing its active loan payment.')
    baseline = Baseline.model_validate({**profile.baseline.model_dump(), 'P': payment})
    if bool(customer['has_running_loan']) != (baseline.P > 0):
        raise ValueError('Engine loan flag disagrees with its active loan payment.')
    features = CustomerFeatures.model_validate({**profile.features.model_dump(),
        'debt_payment_ratio': ratio(baseline.P, baseline.I),
        'active_loan': bool(customer['has_running_loan']),
        'loan_in_arrears': 'client in debt' in str(customer.get('loan_status_meaning', '')).lower(),
    })
    return CustomerProfile.model_validate({**profile.model_dump(), 'baseline': baseline, 'features': features})


def build_account_features(data_dir: Path = DATA_DIR, as_of: str | None = None) -> pd.DataFrame:
    monthly, loans = load_tables(data_dir)
    snapshot = str(monthly.month.max())
    cutoff = str(pd.Period(as_of or snapshot, freq='M'))
    loan_rows = {} if loans is None else {int(r.account_id): r for _, r in loans.iterrows()}
    rows = []
    for account_id, group in monthly.loc[monthly.month <= cutoff].groupby('account_id', sort=True):
        p = profile_from_history(int(account_id), group, loan_rows.get(int(account_id)), as_of=cutoff,
                                 loan_snapshot_available=loans is not None and cutoff >= snapshot,
                                 validated=True)
        rows.append({'account_id': p.account_id, 'as_of': p.as_of, 'last_month': p.last_month,
                     **p.baseline.model_dump(), **p.features.model_dump(),
                     'quality_flags': ';'.join(p.features.quality_flags)})
    return pd.DataFrame(rows)
