# Surplus allocation and investment review

`investment_triggers.py` is a deterministic analyst decision module. It is called
by `engine.make_plan()` and appears in the CLI and the dashboard's **Allocation
Review** tab. It requires no API key and never asks the customer questions.
It does not select an ETF, establish suitability, or execute transfers/trades.

## Variable liquid savings versus fixed investment contributions

Failure to support a fixed monthly debit does not mean the customer can never
save. The engine now returns `flexible_reserve_savings` alongside the existing
fixed-allocation outputs. It reviews each completed month's realized surplus and
minimum cash separately. A deficit month has zero saving capacity rather than
disqualifying every positive month.

The per-month historical capacity is the smaller of 75% of positive realized
surplus (the existing configurable allocation fraction), cash above the operating
cushion and all supplied additional commitments, and the remaining reserve gap.
Amounts are rounded down. Money remains accessible; it is never deducted as an
investment debit, credited as new cash, or added to any projection.

An opportunity requires at least six valid consecutive months, protected capacity
in at least half the observed months and the latest month, positive median
realized surplus, and a current historical cash estimate above the protected
floor. Active/unknown shocks, a modeled deficit, deterioration, unquantified
commitments, source loan arrears and verified costly debt keep protective review
first. Fixed costs and loan payments already in outflows are not added again.

This output is **historical conditional review**, not a standing payment or
verified current set-aside. It leaves `current_set_aside` and `months_to_target`
unknown and `fixed_monthly_commitment` false. Confirm accessible cash, authority,
all obligations through the next reliable income, and the sourced reserve goal
before any actual set-aside. No investment suitability requirement is removed.
The runtime guard suppresses tampered amounts, fixed commitments and invented
dates. Both website savings reviews and Allocation Review expose the distinction.

See `reports/savings_access/README.md` for the all-account before/after audit.

## Mandatory rules on every analysis

`goal_validation.py` hardcodes the S01–S40 runtime policy. Every return from
`evaluate_investment_triggers()` invokes `enforce_goal_validations()`, including
short/invalid-history results. `engine.make_plan()`, the dashboard and the CLI all
use this guarded path. There is no validation-disable option and no dependency
on the test files or the CSV being present at runtime.

Rules match derived financial conditions, not account IDs, case IDs or event
keywords. They enforce reserve/debt/known-expense priorities, evidence gates,
contribution limits, exact cash-flow accounting, one-time receipts, unquantified
effects, no unsupported product selection, and no false funding success.
They are regular executable conditions, not Python `assert` statements, so
Python's `-O` optimization cannot remove them.

If an invariant fails, unsupported amounts/actions/projections are suppressed,
the result becomes `DATA_LIMITED_REVIEW`, and a `RUNTIME_VALIDATION_BLOCKED` flag
explains why. Supported observed features remain available. Results include
`runtime_validation` with the policy version, enforcement status, all 40 checks,
and any violations. A check can be applicable/passed, not applicable, or unknown;
unknown evidence never counts as a verified fact. `passed` does not mean every
scenario occurred or every fact was established.

When adding a selector, model or UI route, preserve this mandatory entry point.
Tests prove enforcement but are not what activates it. Fault-injection tests
deliberately corrupt results to verify that runtime policy blocks them.

## Evidence and policy

Default policy uses the latest **12 calendar months**, with at least **6 complete,
consecutive, unique account-month records**. `as_of="2025-06"` excludes later rows;
only completed monthly data should be supplied. Official README medians and runway
remain separate and unchanged. Allocation inputs use trailing-window medians,
not a difference of medians masquerading as a median of actual monthly net flows.

Defaults are illustrative bank policy, configurable through `InvestmentPolicy`:

- Operating cash floor: one month of observed median outflows.
- Reserve target: three months of observed median outflows, including the
  operating floor (the floor is not added again).
- Thin surplus: median realized net flow at or below 5% of median outflows.
- Fixed-cost pressure: above 60% of median inflows; observed loan-payment
  pressure: above 20%. Fixed costs/loans are already in outflows, never added twice.
- Deposit volatility: inflow interquartile range above 50% of median inflows,
  or intermittent/sparse zero-inflow months.
- Material trajectory change: change between earlier/recent-half median net
  flows above 25% of the larger of earlier absolute median net flow and spending.
- An inflow above three times median inflows is unusual, not verified salary,
  inheritance, recurring revenue, or newly created wealth.

These choices require calibration; none is a universal financial rule.

## Sizing

For each observed month, `net[t] = money_in[t] - money_out[t]`.
The initial recurring capacity is 75% of the **lowest** observed monthly net flow
(and therefore no greater than 75% of its lower quartile), floored to cents.
A deficit/zero month cannot establish a positive fixed contribution. Thin or
volatile cash flow, worsening net flows, negative-balance days, insufficient daily
cash cushion, missing timing fields, or invalid history block fixed investment
sizing. Material fixed/debt-payment pressure also gates investment sizing.

With competition data, opening cash is the lower of the last-six-month average
daily balance and latest month-end balance, explicitly a **historical proxy**.
A supplied, sourced available-cash fact can override it. No present-day cash,
external assets, debt-free status, or sole personal control is inferred.

The historical diagnostic subtracts accumulated hypothetical investment transfers
from every month's observed minimum and closing cash. Transfers are conservatively
assumed to occur at the start of each month. This is **in-sample**, not a forecast
or out-of-sample backtest. It is not evidence that a future transfer date is safe.
Reserve earmarks retain liquid cash; they are not cumulatively subtracted from
historical total liquid cash as though they were investments.

Projection cash at month `t` is:

```
opening_cash + explicitly_supplied_additional_one_off_receipt - immediate_costs
+ t * (median_inflows * income_multiplier
       - median_outflows - household_bills * bills_change
       - monthly_allocation)
- additional_known_expenses_due_through_t
```

The maximum contribution is capped by positive monthly net inflow and the cash
floor headroom at **every** checkpoint, including Month 0. Additional known
expenses within the projection are debited once on their due month. Documented
near-term obligations beyond the projection are retained as an extra floor;
they are not also deducted from the projected closing cash. `KnownExpense`
represents an **additional** expense, not something already in observed spending
or the selected shock. The source must distinguish these to avoid duplicate events.

Outputs distinguish:

1. A conditional normal monthly allocation after liquidity/history gates.
2. The revised amount for the judge's selected scenario (possibly zero).
3. The amount preserving the reserve under **every listed** scenario, which can
   be zero even when the normal opportunity is positive.
4. A separate liquid-reserve earmark when reserves are insufficient. It is not
   both an investment transfer and a reserve contribution.

Six-month independent scenarios: baseline; household bills +15%; inflows at 55%;
repair equal to median spending; all three combined; and the selected judge
scenario. The 55% value is a challenge assumption, not verified benefit
eligibility. No investment returns, insurance payouts, new borrowing, expense
cuts, or sale of investments are assumed. Amounts are fixed over each projection;
a reduction/pause starts immediately when that scenario is selected.

Pausing does not resolve an existing deficit automatically. Each scenario shows
no-allocation, continued-allocation, and revised-allocation paths, reserve breaches,
negative-cash dates, and any extra starting cash needed to avoid negative cash.
Monthly paths cannot establish future daily solvency or cover every possible shock.

## Triggers and suitability

The response exposes G01–G26 with `active`, `inactive`, or `unknown` plus reasons.
Unknown is never silently treated as a verified negative. G07's dated bill/deposit
mismatch requires supplied dated transactions, a labeled household bill with a
stable counterparty, one payment per month, and at least three months where that
bill (at least 25% of median spending) precedes the first observed monthly credit.
It stays unknown when that evidence is insufficient. G14's future release of loan
payments stays unknown: source loan completion is not current released cash.
G13, G17, G19/G20 and G23 require additional
explicit facts for costly debt, verified cash, upcoming obligations/horizon, and
completed goals respectively. Other triggers cover cash-flow stability, liquidity,
reserve depletion, obligation burden, unusual inflows and shock-driven pauses.

Possible goals include stabilization, operating-cash protection, income smoothing,
debt-obligation review, known-expense preparation, reserve building, investment
readiness review, and maintaining/reviewing. Missing suitability evidence does not
interrupt supported calculations. No undocumented customer objective is invented.
Without verified available cash, a surplus opportunity remains
`DATA_LIMITED_REVIEW`; its amount is only a conditional capacity estimate. G17
also requires reviewed obligations. With supplied cash but no objective, the
result is `MAINTAIN_AND_REVIEW`, without an investment instruction.

`KnownExpense(None, 2, "Tuition")` preserves an unknown amount; a missing deadline
can likewise be `None`. These trigger expense review without invented amounts.
Investment sizing is blocked and `funding_result_complete` is false. Known
components still calculate, but do not establish full funding.

Optional judge event context is available in the dashboard. Descriptions do not
create money effects. Unquantified events flag `SHOCK_UNDER_SPECIFIED`; explicit
numeric twist effects still calculate. No customer questionnaire is introduced.

The competition data cannot justify a particular security. Even an explicitly
supplied objective, horizon, risk tolerance, loss capacity, holdings review and
obligations review results only in `ANALYST_REVIEW_REQUIRED`, never automatic
product approval. Short horizons protect liquidity. `security_recommendations`
is always empty; `automatic_trade_allowed` is always false.

## Calling the module

```python
import engine
from investment_triggers import (
    AnalystEvidence, InvestmentPolicy, KnownExpense, evaluate_investment_triggers,
)

customer = engine.know_customer(20111)
shock = engine.take_shock(customer, income_multiplier=.55, bills_increase_pct=.15)
result = evaluate_investment_triggers(customer, shock)

# Only when facts are explicitly supplied by an authorized scenario/record:
evidence = AnalystEvidence(
    source="Judge scenario, assessed 2025-12",
    known_expenses=(KnownExpense(6000, 2, "Additional tuition obligation"),),
)
result = evaluate_investment_triggers(
    customer, shock, policy=InvestmentPolicy(reserve_months=6), evidence=evidence,
)
```

The UI requires only the account and twist; additional-evidence support is a
Python interface for authorized scenarios, not a mandatory customer questionnaire.
No suitability data or account history is sent to Gemini by this module.

## Verification

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python engine.py --account 20111 --ei .55 --bills .15 --repair 1000
.venv/bin/python -m streamlit run app.py --server.headless=true
```

The synthetic $3,000 typical/$2,000 weakest surplus example yields a conditional
$1,500 normal allocation when liquidity gates pass. A selected adverse shock can
reduce it, and the amount surviving every listed scenario can be zero. This is
expected behavior, not proof of permanent affordability.

See [GOAL_TRIGGER_VALIDATION_AUDIT.md](GOAL_TRIGGER_VALIDATION_AUDIT.md) for the
40-row acceptance audit, evidence limitations, and four literal CSV exceptions.
