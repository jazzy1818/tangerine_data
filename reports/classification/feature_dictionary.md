# Feature dictionary (schema 1.1)

One row per account; default cutoff is the dataset's maximum month (2025-12), not today's date.
`python -m plan_classification profile ACCOUNT --as-of YYYY-MM` uses no later monthly rows.
Recent means the 12 **calendar** months ending at the cutoff; missing months are not filled.
Zero-denominator ratios are `null` in JSON / empty in CSV, never infinity or a guessed zero.

| Field | Formula / meaning | Why retain it |
|---|---|---|
| `surplus_margin` | (I − S) / I | Normalized typical affordability |
| `reserve_months` | B / S; negative B remains negative | Reserve coverage, distinct from deficit-based runway |
| `fixed_cost_ratio` | F / I | Observed recurring commitment burden, not proof all other spending is adjustable |
| `debt_payment_ratio` | P / I | Active contractual debt burden |
| `inflow_iqr_ratio` | (Q75 − Q25) / median(recent money_in), linear quantiles; at least two rows | Robust inflow variability, not employment risk |
| `deficit_month_share` | Count(recent money_out > money_in) / recent rows | Reliability of the typical surplus |
| `negative_balance_month_share` | Count(recent days_below_zero > 0) / recent rows | Observed liquidity stress |
| `recovered_overdraft_month_share` | Count(recent days_below_zero > 0 AND month_end_balance ≥ 0) / recent rows | Pressure hidden by month-end totals; same denominator as preceding feature |
| `balance_change_to_spending` | (last − first recent month_end_balance) / S; at least two rows | Direction and size of reserve change; not a monthly slope |
| `active_loan` | End-of-data status C or D | Distinguishes no loan from undefined debt ratio at zero income |
| `loan_in_arrears` | End-of-data status D | Observed running-loan distress, not historical default B |
| `months_observed` | All available rows through cutoff | Baseline reliability |
| `recent_months` | Available rows inside recent calendar window | Recent-feature denominator |
| `stale_months` | Cutoff month minus latest observed month | Stale profile detection |
| `quality_flags` | Sparse/missing history, missing optional data, undefined denominators, negative buffer, unavailable historical loan snapshot | Explicit uncertainty |

Nine continuous features plus two loan flags and four quality fields replace the repeated time
series and absolute-dollar dimensions in model input. The measured high correlation (0.912)
between reserve coverage and normalized balance change is recorded, but they retain different
meanings (level versus direction). Keep both until later held-out ablation tests support removal.
This is an interpretable aggregation/reduction, not PCA or a learned feature selection claim.

Local-only audit columns: `account_id`, `as_of`, `last_month`, I/S/F/H/B/P and baseline runway.
I/S/H are all-history medians; F is the median **of monthly sums**; B is the mean of the last six
available average-balance rows. P is the running-loan payment. At a cutoff before the dataset
snapshot, P and both loan flags are unknown because end-of-data status would leak future data.
Source rows with invalid required values/duplicate account-month keys fail validation. Missing
optional liquidity columns/values yield null features and flags rather than partial zero filling.

No age, gender, district, account/client ID, relationship labels, inferred salary, inferred
spending flexibility, or fabricated financial-risk probability is a model feature.

# Scenario representation

`ShockScenario` has `phase` (active/recovery/normal), `horizon_months`, `effects`, and a local-only
`description`. Default phase is active; an empty active scenario requests financial details.
An explicitly normal scenario means no new financial event and rejects nonneutral financial
effects. Recovery is operator-supplied.

| Effect | Input unit / convention |
|---|---|
| `income_multiplier` | 0.55 means 55% of baseline inflow, not a 55% reduction |
| `income_delta`, `expense_delta` | Signed CAD/month, additive against original baselines |
| `expense_percent`, `household_bills_percent` | Percentage points; 15 means +15%, −10 means −10% |
| `household_bills_delta`, `debt_payment_delta` | Signed CAD/month change; never add the existing payment again |
| `one_off_cost`, `one_off_receipt` | Nonnegative CAD; start_month=0 for immediate; no duration |
| `liquidity_hold` | Nonnegative CAD inaccessible during specified months; not a permanent cash loss |
| `payment_delay_days` | Nonnegative number of days; signals timing, does not fabricate a cash amount |
| `investment_return` | Percentage points of unverified invested assets; no cash effect inferred |
| `unspecified_event` | value=null; asks for the actual financial effect |

Recurring/access effects start in month 1 or later; durations are inclusive of start and contain
exactly duration_months periods. `ongoing: true` declares a confirmed ongoing effect and cannot
be combined with a finite duration. Without either a duration or `ongoing: true`, a recurring/access
effect has unknown duration and creates a clarification question; it is not assumed permanent.
All unit conversions preserve values and evidence (`judge_specified`, `user_confirmed`,
`assumed`, `unknown`). Unknown values/evidence and assumed effects retain clarification questions.
Two overlapping effects of the same recurring type are rejected. Duplicate financial effects
remain duplicates when only their evidence labels differ. Overlapping broad expense
percentages and category changes require an explicit net delta; category percent+absolute changes
also require consolidation. An income multiplier and income delta refer to independent changes
against original I. Neutral effects don't create compound-shock signals. Events after the chosen
horizon are excluded from the classifier case. Future in-horizon events retain their timing.

# Canonical case sent identically to Jev and Gemini

`ClassificationCase` contains the derived customer features, normalized financial effects,
phase/horizon, financial constraints, observed reason codes, missing details, and four deterministic
screening values. Currency-valued effects use `cash_scale = max(I, S, 1)`; that CAD scale is never
sent. All relative amounts retain their relationships. Narrative, IDs, dates, exact balances,
raw records, and demographics are omitted. This reduces disclosure; ratios remain financial data.

Each quantifiable effect also carries `cashflow_delta_to_scale`: its signed change to cash flow
divided by the same scale (positive for extra inflow/reduced outflow; negative for lost inflow/extra
outflow). Percentage changes use their actual local baseline before normalization. This preserves
future household-shock magnitude even though household bills are not sent as a separate amount.
Holds, delays, investment changes, and unknown-value/evidence effects have no established direct
cash-flow delta and use null. Duration and `ongoing` status remain attached to each effect.

`first_period_gap_to_scale` = (first-period S* − I*) / cash_scale.
`immediate_buffer_to_scale` = (B − month-0 costs + month-0 receipts) / cash_scale.
`first_period_runway_months` = 0 if the immediate buffer ≤ 0; otherwise buffer/gap for positive
gap, or null for no shortfall. `first_period_no_shortfall` requires positive immediate buffer and
nonpositive gap. These are **screening** measures, not the judge's rounded/capped display and not
a dynamic projection. They omit later one-offs, hold/access restrictions, delay timing, and expiry;
those effects remain explicit in the effect list for selection and the existing finance solver.

Constraints limit allowed modules and state reserve-target and confirmed-obligation/timing facts.
Approval flags are evidence only; a module selection does not approve a cut, loan, or payout.
Observed reason codes are deterministic facts available to both models, not target class labels.
