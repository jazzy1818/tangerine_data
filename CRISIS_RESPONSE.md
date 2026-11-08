# Shared scenario, crisis response and recovery

The classifier and financial planner now consume the same `ShockScenario`.
Changing the guided/custom scenario changes the backup immediately. Clicking
**Classify scenario** requests a provider proposal; it is not required to run
Python financial calculations. Rerunning the page does not apply an effect twice.

## Entry points

```bash
.venv/bin/python -m streamlit run app.py
.venv/bin/python engine.py --account 22812 --scenario examples/classification/combined.json
.venv/bin/python engine.py --account 22812 --scenario examples/classification/windfall.json
.venv/bin/python -m pytest tests -q
```

Structured CLI output is JSON with the first-period reference, frozen normal goal,
and crisis plan. Legacy `--ei`, `--bills` and `--repair` commands remain supported;
they cannot be combined with `--scenario`. On a Mac with x86-only dependencies,
use the matching active interpreter/environment; the reported working
`arch -x86_64 bash run.sh` path is platform-specific and was not tested on Linux.

```python
import engine
from plan_classification import build_case, profile_from_engine, select_plan, ShockScenario

customer = engine.know_customer(22812)
scenario = ShockScenario(effects=[
    {"type": "income_multiplier", "value": .55, "duration_months": 6},
    {"type": "household_bills_percent", "value": 15., "duration_months": 6},
    {"type": "one_off_cost", "value": 1500., "start_month": 0, "effect_id": "repair-1"},
])
case = build_case(profile_from_engine(customer), scenario)
proposal = select_plan(case, backend="rules")
plan = engine.make_plan(customer, scenario=scenario, selection_result=proposal,
                        include_timing_comparison=True)
# A bare PlanSelection is also accepted:
plan = engine.make_plan(customer, scenario=scenario, selection=proposal.selection)
```

A full `SelectionResult` must match the current canonical input hash. A bare
`PlanSelection` is structurally validated against the current case and has no
invented provider metadata. The finance engine independently checks eligible
modules; overrides and rejected/stale proposals are recorded. All effects execute
regardless of the limit of two supporting module labels. Model confidence never
changes cash or establishes an approved intervention.

Case schema 1.2 adds `planning_cash_basis` and optional `build_case(...,
planning_cash=...)` so explicitly supplied opening cash affects both screening
and execution. Historical ratios and official B remain historical. Model payloads
still exclude account IDs, execution effect IDs, narrative and the CAD scale.

## What executes

`scenario_execution.py` uses original CAD amounts with cent-denominated Decimal
arithmetic. CAD inputs and ledger checkpoints are bounded to ±1 trillion to retain cent precision on serialization; extreme amounts are rejected instead of producing infinite balances. It supports income multipliers/deltas, expense deltas/percentages,
household-bill changes, debt-payment deltas, one-off receipts/costs, and temporary
liquidity holds. Recurring effects apply only to their specified periods; scoped
bill/loan changes alter total spending once. Fixed obligations cannot be silently
cut by an unscoped spending reduction.

Month 0 is immediate, including an explicitly immediate hold. A two-month hold starting at Month 0 protects cash through full Months 1–2 and releases it at the start of Month 3. One-offs in a later month occur at its start. Recurring net
flows are month-end checkpoints, with month-start access checks. This is a monthly
model, not proof of intraday or daily solvency. Cash remains negative in earlier
checkpoints even if a later receipt restores it. Exactly zero is nonnegative;
negative one cent is a shortfall. Holds reduce accessible cash, not total cash,
and their release never creates income or wealth.

An explicit `effect_id` identifies an obligation. Identical repeats of that same
identified effect are idempotent; conflicting values/dates/evidence for one ID
are rejected. Distinct identified $900 invoices both count. Unidentified identical
effects remain rejected as ambiguous rather than silently guessed distinct.

No automatic salary restoration follows the end of a temporary income reduction.
The first unestablished income is null; only quantified cash components continue
as a partial diagnostic. Unknown values/durations/evidence and unsupported effects
prevent a complete funding claim. `full_funding_need` is null for partial paths;
`additional_cash_needed` describes only the quantified-component path.

**Supported limits:** a generic `payment_delay_days` has no identified payment
schedule, and `investment_return` has no supplied holding/settlement. Both are
reported as unexecuted/partial; neither silently changes bank cash. Effects beyond
the horizon remain in `pending_effects`. Known future one-off obligations also
protect allocation headroom; future receipts are not cash available today.

The official organizer preset formula is unchanged and uses original unrounded
I/S/H/B. Other scenarios show a labeled first-period component reference.
Planning paths use rounded posted-CAD amounts and apply timing; their exhaustion
checkpoint is not the same concept as official runway.

## Goals, G25 and action accounting

The normal goal is frozen before applying the crisis. `crisis_rules.goal_worsened`
is shared with the goal trigger and runtime validator. It compares the funding
gap, first shortage and contribution headroom. An improving raise does not create
G25 just because an old deficit persists. A pre-existing infeasible proposal is
marked for baseline review instead of attributed to a new shock.

Proposed transfers leave available cash only in the **continue goal** / **revised
goal** comparisons. Pausing a proposal credits $0 to the **no action** path.
Liquid-reserve earmarks stay liquid; they are not debited as investments.

`ExistingGoalTransfer` records require unique event IDs, scheduled months,
amounts, source, baseline inclusion, explicit pause approval, and known fees.
Only qualifying events inside the horizon reduce spending in the separate
`supported_pause` comparison. No standing order is inferred to be a pausable goal.
No negative transfer, duplicate release or cut into known fixed obligations is
accepted. No actual banking instruction is executed.

For I=$3,000, S=$2,400 (including H=$400), B=$3,000, a $1,500 immediate repair,
55% inflow and 15% higher bills for six months:

- Opening after repair: $1,500; recurring gap: $810.
- Month 1: $690; Month 2: -$120; funding need: $3,360.
- Pausing a proposal leaves the no-action need at $3,360.
- Six explicitly supported $300 existing-transfer pauses (zero fees) reduce the
  need to $1,560; the modeled improvement is $1,800, not full resolution.
- The required uniform monthly improvement is $560. It is a **calculated target**,
  not proof that $560 of spending is adjustable. Immediate cash targets are shown
  separately because later monthly improvements cannot fund an earlier shortage.

## M7 comparison

The existing daily replay is used only for compatible six-month scenarios; dated
or unsupported effects are not flattened to old sliders. Before/after daily paths
use identical opening inputs and historical dated flows. The conditional bill move
retains approval/effective-date/no-fee review flags. Its historical opening basis
and daily flows are distinct from monthly-median planning; no improvement is
claimed by subtracting results with different bases. Generic day delays remain
partial until actual target events/dates are supplied.

## Recovery

The optional UI checkpoint accepts explicitly supplied assessment month, cash,
updated spending, obligation coverage, stability, and an optional supported
monthly rebuild bound. Updated inflows are optional: an explicitly supported
contribution can establish a conditional rebuild rate without inventing income.
It is cleared when the selected account changes. Merely
selecting phase `recovery` cannot establish recovery or a new cash balance.

`RecoverySnapshot` source and cash basis (`judge_specified`, `observed`, or
`simulated`) stay visible. A negative balance, ongoing deficit, uncovered
obligations, or unestablished stability keeps stabilization active. Otherwise,
reserve restoration uses the same configured reserve-month policy with updated
spending and protected earmarks. When inflows are supplied, the rate cannot exceed
current surplus, and a known deficit blocks rebuilding even if a contribution is
supplied. When inflows are absent, monthly surplus remains unknown and only an
explicitly supported contribution is used; an inflow-unquantified flag records
that limitation. Stable cash flow and covered obligations must still be supplied;
the displayed cent amount is the amount used for the timeline. Zero/unknown rates
have no ETA. Restored reserves trigger reassessment, never automatic ETF advice.

Example: current spending $2,400, cash $3,000 and a supported $300/month rebuild
bound give a $7,200 target, $4,200 gap and 14-month conditional timeline. This is a
separately supplied checkpoint, not cash magically created after an unfunded
negative crisis projection. Recovery calculations are deterministic; a classifier
M6 proposal is not evidence that recovery occurred.

## Mandatory validation and verification

The original S01-S40 runtime gate still evaluates the normal-goal assessment.
Every crisis path is then reconciled to the original CAD scenario, including
explicit releases/fees, before `enforce_crisis_validations` checks G25, zero
proposal-pause credit, partial funding and M6 evidence. Blocked output cannot leave
a stale valid backup behind. No validator-disable flag or Python asserts control
production enforcement.

Tests cover independent worked answers, the editor/classifier/backup handoff,
windfall reruns, improving deficits, source conflicts, duplicate invoices,
unsupported actions, benefit expiry, holds, unknown recovery, reserve earmarks,
checkpoint boundaries, organizer compatibility, and corrupted ledger rejection.
Jev/Gemini quality and live provider compatibility are not established by offline
mocked tests; no model winner is claimed.

## Personalized action advice

The dashboard accepts explicitly supplied monthly goal-transfer schedules under
**Existing goal transfers — supplied evidence**. An identifier, amount, months,
source, baseline inclusion, approval and known per-payment fee are required for
cash relief. No transaction is inferred to be a savings transfer. A new account
clears the evidence; changing scenarios recalculates it. Duplicate schedules,
fractional-cent transfers and amounts exceeding included nonfixed spending are
rejected. Correct or clear invalid schedules before advice is issued.

`applied_plan` combines the supported revised contribution with approved existing
transfer pauses. The separate `supported_pause` path remains a comparison. Fees
occur at month-start; avoided payments affect month-end. A pause whose fees consume
the benefit is excluded. Each payment is evaluated in deterministic fee/month/ID
order. Useful payments remain selected when another payment would advance a
shortfall or increase required funding. Approval permits modeling; recommendation
also requires reducing the funding gap, delaying a shortfall, or improving a
stated reserve-floor deficit without worsening its maximum. A healthy account
with no such purpose retains the pause only as a comparison. Every payment has an
included/excluded decision with a reason. This is a deterministic selection
policy, not a proof of a globally optimal combination. No banking action occurs.

Mandatory runtime checks reconcile each applied payment, fee and contribution
against supplied records, the original scenario ledger, and every closing cash
difference. `tailored_advice.py` derives account-specific explanations from that
validated result: opening basis, monthly cash flows, event dates, goals, supported
pauses, remaining gaps, conditional bill timing and separately supplied recovery.
A funding target never establishes adjustable spending. Partial paths retain
explicit incomplete-funding language. No product, TFSA transfer, insurance payout,
loan approval or investment suitability is inferred.

Gemini is optional and invoked by an explicit dashboard button. It selects up to
three approved findings to emphasize; it does not author unrestricted financial
prose. The API receives categorical statuses and approved IDs, excluding account
IDs, source descriptions and exact CAD amounts. Unknown IDs, extra fields,
duplicate IDs, invalid JSON, timeouts or missing credentials retain the full local
explanation. Every finding and review flag remains visible. Cached emphasis is
bound to the complete advice fingerprint. This is a constrained explanation layer,
not a live provider benchmark or product recommendation engine.

Independent numerical regression examples include the $3,360/$1,560 compound
case; fee and approval boundaries; the late receipt path
$400, -$200, $1,200, $600, $0, -$600; and a $4,200 reserve gap rebuilt at $300/month
in 14 months. The late-receipt example needs $200 before the receipt and $600 of
extra starting cash across the full six-month horizon. These are synthetic
verification cases, not observed customer facts or independent finance-team signoff.


## Pre-demo review corrections

Loan relief is bounded by the specific existing payment and its inclusion in
baseline spending. The current loan snapshot and the historical monthly spending
component are distinct facts. A zero loan payment cannot be reduced, and a
snapshot alone cannot establish an avoided payment in the modeled spending.
Unknown payment/inclusion leaves relief unapplied and the projection incomplete.
An explicit scenario override requires `obligation_payment`, `obligation_source`
and `payment_in_baseline=true`. The guided editor binds such evidence to the
selected account with local `obligation_account_id`; switching accounts leaves
that override unapplied until matching evidence is supplied and clears unsaved
loan and repayment inputs. Scoped reductions never consume unchanged
household bills or other protected fixed obligations. Classification uses the
same obligation checks; raw payment evidence remains local.

A temporary deferral uses `debt_change_kind="deferral"` plus finite duration,
`repayment_month` and `repayment_amount`, or `repayment_unresolved=true`.
Reductions and repayments must be in whole CAD cents, and repayment must cover
the deferred principal. The relief and repayment share the same evidence decision.
An excluded deferral posts neither side. A dated repayment enters cash once,
including in an assumed comparison where both sides remain conditional. Unknown
repayment or repayment beyond the horizon stays visible when relief was modeled
and prevents a full-funding claim. The classifier receives normalized amounts
from the same posted changes. Example with a known included $300 payment:

```json
{"type":"debt_payment_delta","value":-300.0,"duration_months":2,
 "debt_change_kind":"deferral","repayment_month":4,"repayment_amount":600.0}
```

G25 is tri-state: `true` for evidenced deterioration, `false` when complete paths
show none, and `null`/`G25_state="unknown"` when the impact is unestablished.
`goal_review_required` independently holds contributions for incomplete evidence.
A complete known prefix can still prove an immediate shortage before a later
unknown effect. Unknown income, unknown event effects and missing duration do not
by themselves prove deteriorated allocation capacity.

Only `scope="ORGANIZER_STANDARD"` receives the official runway label and colored
runway badge. Dated scenarios display a neutral Month 1 reference and the actual
monthly projection's first shortfall prominently. Incomplete cash paths label
cash need and closing cash as partial estimates; the full funding need remains
not established. Runtime policy `crisis-lifecycle-v2` enforces the uncertainty,
financial-purpose, per-payment audit and original-CAD reconciliation rules.

## Backup Plan comparison screen

**Goal and Backup Plans → Backup Plan** now puts the analyst summary and a Plotly
cash comparison above the detailed ledgers. Both paths are after the same shock:
`no_action` versus `applied_plan`. The display reads the engine's existing outputs;
it does not call the engine again, change a goal or create cash relief.

Every Month 0 through the chosen horizon has separate start/end points. The chart
uses an ordered checkpoint axis (not days), a CAD 0 line, distinct line styles,
and first-negative annotations. A negative month-start balance remains visible
even if that month's closing balance recovers. Held funds follow the engine's
accessible-cash definition. Lines between checkpoints do not establish daily
solvency. Daily Replay remains a separate historical analysis.

The view validates matching scenario hashes, horizon and opening basis, ordered
checkpoint grids, finite CAD cents, first-shortfall metadata, full/partial funding
status and the funding need implied by minimum cash. Inconsistent or blocked
results produce no comparison. Source results are not mutated.

Above the chart, the screen shows first shortfall and required cash before/after,
then explains the supported pauses, fees and new proposed transfers that account
for the difference. Identical paths explicitly explain why a proposal pause or an
unavailable existing-transfer action adds no cash. A partial projection leaves
full funding needs **Not established** and identifies quantified estimates and
unresolved effects separately. The complete checkpoint ledger, monthly schedule,
comparison table and per-payment inclusion/exclusion decisions remain underneath
in expanders. Existing evidence and review flags remain available.

**Financial Safe Mode** is a read-only presentation of existing engine decisions:
review required, modeled liquidity protection, or no additional restriction
established. It adds no financial policy, account control or automatic transfer.
It does not equate an unrestricted contribution conclusion with suitability.

The opening portfolio card is recomputed from `monthly_summary.csv`: **714 of
3,309 accounts with positive typical monthly surplus** have modeled runway below
six months at 55% inflow, using the unrounded threshold and no additional bill or
repair shock. The denominator excludes zero/negative typical surplus accounts.
I/S are full-history medians; B is the mean of the last up to six monthly average
balances. This is a simulation finding, not observed future customer outcomes.
The one-decimal official runway display is separate: thresholding that rounded
display would produce 699 rather than 714. No organizer formula is changed.

[Manual comparison review sheet](examples/crisis/backup_comparison_review.csv)
contains independently worked synthetic expectations and empty finance-reviewer
fields. Automated tests do not constitute independent finance signoff. Tests
cover the $3,360/$1,560 example, start/end timing, zero and one-cent boundaries,
unknown impacts, proposed debits, identical paths, corrupt/stale comparisons,
account/shock/evidence changes, safe-mode presentation and the portfolio finding.

Verification for this screen: `python -m pytest tests/test_backup_comparison.py
tests/test_backup_comparison_ui.py tests/test_portfolio_overview.py -q` passed all
22 focused checks. The full suite passed **400 tests and 9 subtests**. A Chromium
run exercised the actual app, account changes, a custom income shock and the
monthly comparison. These checks establish the tested behavior, not finance-team
signoff or completeness across every possible future scenario.

## Finance decision policy

Validated crisis results include a local `finance_plan` with the ordered actions,
the matched cash paths and a candidate audit. The website and Streamlit display
the action summary above the comparison. Assumed effects have a separate
conditional path. A loan deferral with missing repayment terms withholds both
legs until the terms are known. See the [finance action contract](finance_policy_integration/ACTION_PLAN_CONTRACT.md)
and [finance review handoff](finance_policy_integration/FINANCE_REVIEW_NOTES.md).
