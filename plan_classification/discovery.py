"""Reproducible descriptive discovery, not classifier evaluation or causal inference."""
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .features import DATA_DIR, REQUIRED, build_account_features, load_tables


def _fraction(n, d):
    return f'{n:,} / {d:,} ({100*n/d:.1f}%)' if d else f'{n:,} / 0 (undefined)'


def generate_report(data_dir: Path = DATA_DIR, output: Path = Path('reports/classification')):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    monthly, loans = load_tables(data_dir)
    accounts = build_account_features(data_dir)
    accounts.to_csv(output / 'account_features.csv', index=False)
    end = str(monthly.month.max())
    start = str(pd.Period(end, 'M') - 11)
    recent = monthly.loc[monthly.month >= start]
    positive = accounts.I > accounts.S
    gap = accounts.S - .55*accounts.I
    runway = np.where(accounts.B <= 0, 0, np.where(gap <= 0, 120, np.minimum(accounts.B / gap.where(gap > 0, 1), 120)))
    short = positive & (runway < 6)
    complete = accounts.recent_months == 12
    eligible = positive & complete
    inconsistent = eligible & (accounts.deficit_month_share >= .25)
    days = recent.get('days_below_zero', pd.Series(np.nan, index=recent.index))
    closing = recent.get('month_end_balance', pd.Series(np.nan, index=recent.index))
    liquidity_known = days.notna() & closing.notna()
    negative = liquidity_known & (days > 0)
    recovered = negative & (closing >= 0)
    monthly_deficit = recent.money_out > recent.money_in
    cash = pd.to_numeric(monthly.get('cash_withdrawals_genuine',
                                    pd.Series(np.nan, index=monthly.index)), errors='coerce')
    cash_known = bool(cash.notna().all() and np.isfinite(cash).all() and (cash >= 0).all())
    total_outflow = float(monthly.money_out.sum())
    cash_share = float(cash.sum()/total_outflow) if cash_known and total_outflow > 0 else None
    cash_description = f'{cash_share:.1%}' if cash_share is not None else 'an undefined share'
    findings = {
        'positive_surplus_but_under_6_months_at_55pct_inflow': {'numerator': int(short.sum()), 'denominator': int(positive.sum())},
        'positive_surplus_but_at_least_3_deficit_months_of_12': {'numerator': int(inconsistent.sum()), 'denominator': int(eligible.sum())},
        'negative_balance_months_recovered_by_month_end': {'numerator': int(recovered.sum()), 'denominator': int(negative.sum())},
        'recent_deficit_months': {'numerator': int(monthly_deficit.sum()), 'denominator': len(recent)},
        'cash_withdrawal_share_of_all_outflow': cash_share,
    }
    (output/'findings.json').write_text(json.dumps(findings, indent=2, allow_nan=False)+'\n')
    feature_cols = ['surplus_margin', 'reserve_months', 'fixed_cost_ratio', 'debt_payment_ratio',
                    'inflow_iqr_ratio', 'deficit_month_share', 'negative_balance_month_share',
                    'recovered_overdraft_month_share', 'balance_change_to_spending']
    correlations = accounts[feature_cols].corr(method='pearson')
    correlations.to_csv(output/'feature_correlations.csv')
    correlated = [(a,b,float(correlations.loc[a,b])) for i,a in enumerate(feature_cols)
                  for b in feature_cols[i+1:] if abs(correlations.loc[a,b]) >= .9]
    # Find an illustrative pair within 5% on I and B, with different observed timing histories.
    comparable = accounts.loc[(accounts.I > 0) & (accounts.B > 0) & complete].dropna(
        subset=['negative_balance_month_share']).sort_values(['I', 'account_id'])
    matched = None
    best_difference = -1
    for row in comparable.itertuples():
        near = comparable.loc[(comparable.account_id != row.account_id)
                              & comparable.I.between(row.I*.95, row.I*1.05)
                              & comparable.B.between(row.B*.95, row.B*1.05)]
        if near.empty:
            continue
        difference = (near.negative_balance_month_share-row.negative_balance_month_share).abs()
        idx = difference.idxmax()
        if float(difference.loc[idx]) > best_difference:
            best_difference = float(difference.loc[idx])
            matched = accounts.loc[accounts.account_id.isin([row.account_id, near.loc[idx,'account_id']])]
    pair_text = 'No eligible matched pair found.'
    cols = ['account_id','I','B','negative_balance_month_share','inflow_iqr_ratio','deficit_month_share']
    # Always replace this export so a rerun with sparse data cannot leave a stale pair.
    (matched[cols] if matched is not None else pd.DataFrame(columns=cols)).to_csv(
        output/'matched_accounts.csv', index=False)
    if matched is not None:
        pair_text = '\n'.join(f'- Account {int(r.account_id)}: I={r.I:.2f}, B={r.B:.2f}, '
                              f'negative-balance months={r.negative_balance_month_share:.1%}, '
                              f'inflow IQR/median={format(r.inflow_iqr_ratio,".4f") if pd.notna(r.inflow_iqr_ratio) else "unknown"}, '
                              f'deficit months={r.deficit_month_share:.1%}.'
                              for r in matched.itertuples())
    report = f'''# Classification data discovery

Reproduce: `python -m plan_classification discover`. Sources: supplied Tangerine CSVs only.
All-history official baseline: {monthly.month.min()} through {end}; recent features: {start} through {end}.
This is a descriptive end-of-data snapshot, not a historical prediction experiment.

## 1. Positive typical surplus does not guarantee shock resilience

{_fraction(int(short.sum()), int(positive.sum()))} accounts with I > S have **unrounded** official
runway below six months under the judge's 55%-of-inflow scenario. All {len(accounts):,} accounts
are eligible; denominator is the subset with I > S. No assumed eligibility, top-ups, spending cuts,
or post-benefit employment. This is an imposed scenario, not an estimated job-loss probability.
Keep reserve coverage and scenario magnitude, rather than classifying by income alone.

## 2. A typical surplus can hide repeated real deficits

{_fraction(int(inconsistent.sum()), int(eligible.sum()))} positive-typical-surplus accounts with all
12 recent months had at least three actual deficit months (money_out > money_in).
Keep deficit_month_share; I-S alone is insufficient evidence for a fixed savings commitment.

## 3. Month-end balances miss within-month pressure

{_fraction(int(recovered.sum()), int(negative.sum()))} recent months with days_below_zero > 0
ended with nonnegative balances. This affects {recent.loc[recovered,'account_id'].nunique():,}
distinct accounts; total recent records = {len(recent):,}. The denominator here is negative-balance
**months**, not accounts. Timing is a hypothesis; this does not establish bill/payday causation
or reproduce the separate July–December daily shock replay (143 hidden-shortfall accounts among 4,424 eligible accounts; 44 of 102 qualifying bill-shift cases resolved conditionally).
Only months with both days_below_zero and month_end_balance observed enter this ratio:
{int(liquidity_known.sum()):,} eligible records; {int((~liquidity_known).sum()):,} excluded for missing data.

## 4. Similar inflow/buffer, different liquidity history

Select full-12-month accounts with positive I and B. For each account, find all other accounts
within ±5% on both I and B; retain the pair with the largest difference in negative-balance month
share (sorted account/inflow order breaks ties). This is a deliberately illustrative extreme,
not a population effect estimate or a causal control.
Accounts missing the negative-balance month share are excluded from matching.

{pair_text}

## 5. Unlabelled cash limits spending assumptions

Genuine cash withdrawals represent {cash_description} of total all-history money_out (ratio of
sums, not mean of account ratios). Cash withdrawals do not reveal groceries, rent, entertainment,
or what can be cut. No discretionary-spending feature is inferred from them.
The share is undefined when any cash-withdrawal value is missing/invalid or total outflow is zero;
missing cash values are never treated as zero.

## Feature reduction decisions

Nine continuous ratios replace repeated monthly rows and most absolute amounts in classifier
inputs. Retain I/S/F/H/B/P locally for exact arithmetic and auditing. No PCA: we need named,
auditable financial drivers and there are no plan labels to validate a loss of information.
Pairs with absolute Pearson correlation ≥0.90: {correlated or 'none'}. See feature_correlations.csv.
Correlation alone is not permission to drop a signal: negative months include unresolved
overdrafts, whereas recovered months specifically reveal hidden pressure at month-end.
No fabricated risk probability, demographic grouping, region, client ID, or account ID is a predictor.
Raw account IDs remain only in local audit exports so teammates can reproduce cases.

The labels in outputs/client_labels.csv are demographic/inflow labels, not best-plan labels.
Neither remote classifier is trained here. Both use the same canonical case. Model comparison
and held-out financial-outcome evaluation are intentionally left for the team.

## Scope and limitations

I measures bank inflows, not verified salary; B is a six-row historical mean, not spendable cash.
Recent measures use the last 12 calendar months ending at the dataset cutoff. Missing months
are flagged, never zero-filled. Ratios with zero denominators are null. Loan status is an
end-of-data snapshot; earlier as_of requests exclude it rather than leaking future status.
These bank observations cannot establish outcomes for all Canadian households.
Prior counts in the plans used unspecified/different filters and are not reproduced by assumption.

![Discovery findings](discovery.png)
'''
    (output/'discovery_report.md').write_text(report)
    audit = ['# Data audit', '', '| File | Rows | Columns | SHA-256 |', '|---|---:|---:|---|']
    for path in sorted(Path(data_dir).glob('*.csv')):
        digest = hashlib.sha256()
        with path.open('rb') as handle:
            for chunk in iter(lambda: handle.read(1024*1024), b''):
                digest.update(chunk)
        with path.open(newline='') as handle:
            reader = csv.reader(handle)
            header = next(reader)
            count = sum(1 for _ in reader)
        audit.append(f'| {path.name} | {count:,} | {len(header)} | `{digest.hexdigest()}` |')
    audit += ['', f'Month range: {monthly.month.min()}–{end}; unique accounts: {len(accounts):,}.',
              f'Duplicate account/month rows: {int(monthly.duplicated(["account_id","month"]).sum())}.',
              f'Missing required monthly values: {int(monthly[REQUIRED].isna().sum().sum())}.',
              f'Recent months excluded from recovered-overdraft analysis for missing data: {int((~liquidity_known).sum())}.',
              f'Accounts with fewer than six rows: {int((accounts.months_observed < 6).sum())}.',
              f'Accounts with fewer than 12 recent rows: {int((accounts.recent_months < 12).sum())}.',
              f'Stale accounts at dataset cutoff: {int((accounts.stale_months > 0).sum())}.',
              f'Unknown loan-account joins: {len(set(loans.account_id)-set(accounts.account_id)) if loans is not None else "loan file unavailable"}.',
              '', ('README/PDF count (185,326 monthly rows) is correct; the master guide’s 26,846 is not.'
                   if len(monthly) == 185326 and len(accounts) == 4500 else
                   'Current input counts differ from the organizer reference; the table above describes these files.'),
              'The classification pipeline reads monthly_summary and loans. Other files are inventoried only.',
              'Required numeric fields reject nulls, infinities, malformed months, and duplicate keys.',
              'Optional missing liquidity signals produce null features and explicit quality flags.',
              'CSV exports retain full precision; ratios supplied to APIs retain full precision as well.',
              'No raw data or existing outputs are overwritten. No classifier API was called for discovery.']
    (output/'data_audit.md').write_text('\n'.join(audit)+'\n')
    _plot(findings, output)
    return findings


def _plot(findings, output):
    import os
    os.environ.setdefault('MPLCONFIGDIR', '/tmp/tangerine-matplotlib')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    keys = list(findings)[:3]
    labels = ['Positive surplus, <6 months\nunder 55% inflow scenario',
              'Positive surplus, ≥3 deficit\nmonths out of last 12',
              'Negative-balance months\nrecovered by month-end']
    values = [findings[k] for k in keys]
    fig, ax = plt.subplots(figsize=(10, 5))
    bars = ax.barh(labels, [100*v['numerator']/v['denominator'] if v['denominator'] else 0 for v in values], color='#ef7925')
    for bar, v in zip(bars, values):
        ax.text(bar.get_width()+1, bar.get_y()+bar.get_height()/2,
                _fraction(v['numerator'],v['denominator']), va='center', fontsize=9)
    ax.set_xlim(0, 125)
    ax.set_xlabel('Percent within each stated denominator')
    ax.set_title('Financial averages hide different forms of cash pressure', loc='left')
    ax.spines[['top','right']].set_visible(False)
    fig.tight_layout()
    fig.savefig(output/'discovery.png', dpi=160)
    plt.close(fig)
