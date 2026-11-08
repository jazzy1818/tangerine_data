# Bank-facing goal checkpoint audit

The original `Tangerine_Goal_Trigger_Test_Matrix_v2_Bank_Facing.csv` is unchanged. Every S01–S40 row has an executable regression test in `tests/test_goal_matrix.py`.

**Always-on runtime enforcement:** `goal_validation.py` now hardcodes every
checkpoint's financial condition and required behavior. The production evaluator
calls it on every return, including insufficient-data returns; the dashboard and
CLI share that path. It never imports tests or reads this audit/the test CSV.
Runtime failures suppress the unsupported recommendation and return a review
result. Each result records all 40 runtime check statuses and the policy version.
Fault-injection tests verify this behavior, including under Python `-O`.

**Evidence boundaries:** production calculations use supplied monthly summaries, transactions, loans and account access records. Current available cash, total external debts/assets, suitability, goals, insurance benefits and future events are not inferred. A historical balance is always a proxy. Policy thresholds and stress tests are labeled assumptions, not bank facts.

**Test boundaries:** the CSV contains qualitative scenarios, not complete numeric test inputs. The tests use explicitly synthetic records to instantiate those descriptions; their numbers are not customer facts or a discovery from the competition data. Extra scenario facts are never populated automatically in the application. A scenario-only check tests how an explicitly supplied fact is handled; it does not establish that fact for any actual account.

**Literal agreement:** 36/40 representative fixtures match both the named primary goal and listed active triggers. Four cases retain stricter evidence gates, listed below. All 40 safety checkpoint tests pass with these exceptions explicit; this is not a claim that all 40 literal CSV expectations passed.

## Evidence exceptions

- **S10:** No loan in one table cannot establish current cash or other debts. DATA_LIMITED_REVIEW is retained rather than inferring sufficient finances for MAINTAIN.
- **S11:** Conflict: G17 requires verified available cash/obligations. With historical proxy only, G17 must be unknown, while G24 is active and primary goal is DATA_LIMITED_REVIEW.
- **S12:** Verified cash does not establish all obligations/earmarks. G17 stays unknown without an obligations review; investment readiness review is allowed, but never a security recommendation.
- **S20:** Goal completion alone supplies neither current cash nor a next objective. ALLOCATE_SURPLUS is conditional in the must_not_do column; missing evidence yields DATA_LIMITED_REVIEW.

## Checkpoint results

| Case | Input availability | Expected primary goal | Actual fixture goal | Literal match | Guard enforced |
|---|---|---|---|---|---|
| S01 | Observable fields; unknowns retained | BUILD_EMERGENCY_RESERVE | BUILD_EMERGENCY_RESERVE | Yes | No immediate ETF purchase; use verified cash or label B proxy |
| S02 | Observable fields; unknowns retained | STABILIZE_CASHFLOW | STABILIZE_CASHFLOW | Yes | No forced positive savings transfer |
| S03 | Observable fields; unknowns retained | SMOOTH_IRREGULAR_INCOME | SMOOTH_IRREGULAR_INCOME | Yes | Avoid fixed transfer equal to median surplus |
| S04 | Observable fields; unknowns retained | PROTECT_OPERATING_CASH | PROTECT_OPERATING_CASH | Yes | Do not assume no short-term risk |
| S05 | Observable fields; unknowns retained | STABILIZE_CASHFLOW | STABILIZE_CASHFLOW | Yes | Do not call trend permanent cause |
| S06 | Observable fields; unknowns retained | PROTECT_OPERATING_CASH | PROTECT_OPERATING_CASH | Yes | Must verify dates and essential bills |
| S07 | Observable fields; unknowns retained | BUILD_EMERGENCY_RESERVE | BUILD_EMERGENCY_RESERVE | Yes | Do not double count fixed costs |
| S08 | Observable fields; unknowns retained | MANAGE_DEBT_OBLIGATIONS | MANAGE_DEBT_OBLIGATIONS | Yes | Do not claim high-interest debt |
| S09 | Explicit scenario/record required | MANAGE_DEBT_OBLIGATIONS | MANAGE_DEBT_OBLIGATIONS | Yes | Compare cash minimum and costly debt; no automatic zero buffer |
| S10 | Observable fields; unknowns retained | MAINTAIN_AND_REVIEW | DATA_LIMITED_REVIEW | Evidence exception | Do not infer debt-free outside bank |
| S11 | Observable fields; unknowns retained | DATA_LIMITED_REVIEW | DATA_LIMITED_REVIEW | Evidence exception | Flag bank review; no automatic investment allocation |
| S12 | Explicit scenario/record required | INVESTMENT_READINESS_REVIEW | INVESTMENT_READINESS_REVIEW | Evidence exception | Flag investment suitability unverified; no specific ETF or trade |
| S13 | Explicit scenario/record required | MAINTAIN_AND_REVIEW | MAINTAIN_AND_REVIEW | Yes | No investment or savings forced |
| S14 | Explicit scenario/record required | PREPARE_KNOWN_EXPENSE | PREPARE_KNOWN_EXPENSE | Yes | No equities assumption for needed short-term money |
| S15 | Explicit scenario/record required | PREPARE_KNOWN_EXPENSE | PREPARE_KNOWN_EXPENSE | Yes | Budget amount and timing customer confirmed |
| S16 | Observable fields; unknowns retained | DATA_LIMITED_REVIEW | DATA_LIMITED_REVIEW | Yes | Flag possible transfer; do not assume new unrestricted money |
| S17 | Explicit scenario/record required | BUILD_EMERGENCY_RESERVE | BUILD_EMERGENCY_RESERVE | Yes | Allocate windfall once, not as recurring salary |
| S18 | Observable fields; unknowns retained | STABILIZE_CASHFLOW | STABILIZE_CASHFLOW | Yes | No immediate invest until sustainable |
| S19 | Explicit scenario/record required | REBUILD_AFTER_SHOCK | REBUILD_AFTER_SHOCK | Yes | Use proxy with visible limitations; flag current cash unavailable |
| S20 | Explicit scenario/record required | ALLOCATE_SURPLUS | DATA_LIMITED_REVIEW | Evidence exception | Only upon documented goals and eligibility; otherwise flag bank review |
| S21 | Observable fields; unknowns retained | DATA_LIMITED_REVIEW | DATA_LIMITED_REVIEW | Yes | Do not assert volatility/seasonality |
| S22 | Observable fields; unknowns retained | STABILIZE_CASHFLOW | STABILIZE_CASHFLOW | Yes | No negative dollar reserve contributions |
| S23 | Observable fields; unknowns retained | DATA_LIMITED_REVIEW | DATA_LIMITED_REVIEW | Yes | Do not infer current payment or APR |
| S24 | Observable fields; unknowns retained | DATA_LIMITED_REVIEW | DATA_LIMITED_REVIEW | Yes | Do not recommend cancel subscriptions by guessed amount |
| S25 | Observable fields; unknowns retained | DATA_LIMITED_REVIEW | DATA_LIMITED_REVIEW | Yes | Do not assume covered policy and payout |
| S26 | Observable fields; unknowns retained | DATA_LIMITED_REVIEW | DATA_LIMITED_REVIEW | Yes | Do not presume full personal control of balance |
| S27 | Explicit scenario/record required | STABILIZE_CASHFLOW | STABILIZE_CASHFLOW | Yes | Suspend optional contributions conditionally; show backup now |
| S28 | Explicit scenario/record required | MAINTAIN_AND_REVIEW | MAINTAIN_AND_REVIEW | Yes | Do not invent injury or costs |
| S29 | Explicit scenario/record required | DATA_LIMITED_REVIEW | DATA_LIMITED_REVIEW | Yes | Flag shock as under-specified, present configurable assumptions; no fabricated amounts |
| S30 | Explicit scenario/record required | ALLOCATE_SURPLUS | ALLOCATE_SURPLUS | Yes | One-time bonus not recurring cashflow |
| S31 | Observable fields; unknowns retained | DATA_LIMITED_REVIEW | DATA_LIMITED_REVIEW | Yes | No unsupported automated cash investment |
| S32 | Explicit scenario/record required | PREPARE_KNOWN_EXPENSE | PREPARE_KNOWN_EXPENSE | Yes | Horizon dominates stock growth hypothesis |
| S33 | Explicit scenario/record required | PREPARE_KNOWN_EXPENSE | PREPARE_KNOWN_EXPENSE | Yes | Protect imminent essential payment, compare debt and buffer |
| S34 | Explicit scenario/record required | STABILIZE_CASHFLOW | STABILIZE_CASHFLOW | Yes | Goal may be paused despite historical completion |
| S35 | Observable fields; unknowns retained | STABILIZE_CASHFLOW | STABILIZE_CASHFLOW | Yes | Review outlier; no assumption ongoing deficit |
| S36 | Observable fields; unknowns retained | SMOOTH_IRREGULAR_INCOME | SMOOTH_IRREGULAR_INCOME | Yes | Overlay debt defense and reserve; do not force single class |
| S37 | Explicit scenario/record required | NO_FEASIBLE_CONTRIBUTION | NO_FEASIBLE_CONTRIBUTION | Yes | Report unresolved gap, not false positive outcome |
| S38 | Explicit scenario/record required | MAINTAIN_AND_REVIEW | MAINTAIN_AND_REVIEW | Yes | Do not recommend risky purchase against documented preference |
| S39 | Observable fields; unknowns retained | BUILD_EMERGENCY_RESERVE | BUILD_EMERGENCY_RESERVE | Yes | Do not double count transferred savings as new wealth |
| S40 | Observable fields; unknowns retained | DATA_LIMITED_REVIEW | DATA_LIMITED_REVIEW | Yes | Do not divide by zero or infer salary from transfers |

## Corrections made

- G05 now checks balance deterioration as well as net-flow deterioration; neither proves a cause or permanent change.
- G07 uses dated, labeled recurring household payments and credits when available. It stays unknown if the dates, counterparties, or recurrence cannot be established. A timing pattern alone does not prove an essential-cost shortfall.
- Current cash uncertainty keeps a surplus opportunity at DATA_LIMITED_REVIEW. G17 requires supplied available cash and reviewed obligations. No documented objective means no forced product or trade.
- Known expense identity can activate G19/G20 even when amount or timing is missing. Unknown values remain None; allocation sizing is blocked and funding completeness is false. Quantified components are still shown, without claiming full affordability.
- Verified imminent obligations precede debt optimization. Reserve and debt protection remain overlays for irregular-income cases.
- A verified prior shock permits REBUILD_AFTER_SHOCK. Historical depletion alone does not establish that a shock occurred.
- A windfall/bonus does not increase recurring income. Missing receipt amounts add no cash. An explicitly supplied additional receipt is counted once at Month 0.
- Source loan completion does not establish a current payment, APR, or newly freed cash. Insurance premiums do not establish benefits. Unlabeled withdrawals do not establish discretionary purchases.
- A free-text event never creates dollar effects. A no-effect event does not create injury/repair costs. An unspecified event displays SHOCK_UNDER_SPECIFIED and retains supported calculations without blocking the demonstration.
- A shock-induced deficit activates G01/G25 distinctly from observed historical deficits. Optional contributions are reduced/paused; an unresolved gap is reported even after pausing. NO_FEASIBLE_CONTRIBUTION means no supported positive optional contribution, not proof that every conceivable intervention was exhausted.
- Sparse zero-inflow months are flagged even when an interquartile statistic alone would miss them.
- Investment selections/trades remain disabled. No external financial facts or data sources were added.

## Verification

Run `.venv/bin/python -m unittest discover -s tests -v`. Named tests `test_S01` through `test_S40` check every row, specific prohibited behaviors, and the evidence exceptions above. Other tests check exact cash-flow accounting, invalid/missing inputs, no look-ahead in monthly sizing, official runway compatibility, and dashboard behavior.

An independent scan of all 4,500 supplied accounts, including dated transaction evidence, completed without calculation or JSON serialization errors. In that scan, G13 (costly debt), G17 (verified excess cash), G23 (completed goals), security recommendations and automatic trades were never inferred. There were 992 accounts with the defined observed G07 timing pattern, 2,226 with no qualifying pattern, and 1,282 with insufficient evidence. These are policy-defined diagnostics, not verified current financial conditions.

No claim is made that all qualitative acceptance scenarios occur in the real dataset, that historical affordability guarantees future affordability, or that passing these tests establishes personalized investment suitability.
