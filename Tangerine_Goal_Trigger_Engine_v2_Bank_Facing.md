# Tangerine Mission Control — Bank-Facing Goal Trigger Engine v2.0

**Audience:** Internal bank analyst / judge-facing decision-support prototype, **not** a customer-facing questionnaire or an automatic trading tool.

**v2 clarification:** Bank staff enter the account ID and the judge's shock. The engine returns a usable goal and backup recommendation with visible evidence and limitations. Missing facts become **internal data-quality / analyst-review flags**, never questions interrupting the live demonstration.

**Purpose:** Define *when* a normal-life financial goal should be recommended, *which* goals are eligible, *what should be calculated*, and *when the system must abstain*. This is complementary to — not a replacement for — the existing **8 shock-response financial modules**. The judge's account ID and twist are entered before both goal and backup plans are presented.

**Source-of-truth:** Only the Tangerine competition's bank files. No NASA data. NASA's fault-management concept is an inspiration for separating observation, protective conditions, resource allocation, and recovery. These are decision-support rules, not proof of individualized suitability.

## 1. Definitions: four different decisions

1. **Condition trigger:** A reproducible pattern in available bank data (e.g., repeated deficit months), or an additional explicit fact if supplied in the bank record / judge scenario. It does not mean a financial disaster occurred. A personal goal that is not in the supplied dataset must stay **unknown**, not become a customer question.
2. **Priority/eligibility gate:** Whether a goal is reasonable *now*. An investment discussion can be relevant while an investment purchase is not eligible.
3. **Plan selection:** Choose a **primary normal-life goal** and optional supporting goals among the eligible ones. Both Classifier A (algorithm TBD) and Gemini receive exactly the same trigger record and restrictions.
4. **Action sizing:** The deterministic finance engine computes amounts, time horizons, and feasibility; the selectors may not invent contributions or investment returns.

An account may have many active triggers. **The output does not have to recommend investing.** `MAINTAIN`, `DATA_LIMITED_REVIEW`, `STABILIZE_FIRST` and `NO_FEASIBLE_CONTRIBUTION` are valid outputs.

## 2. Data availability and explicit exclusions

### Direct or derived from the supplied files

- `monthly_summary.csv`: `money_in`, `money_out`, `household_bills`, `insurance` (recorded payments, **not** proof of insurance coverage), `loan_payments`, `avg_daily_balance`, `min_balance`, `days_below_zero`, `month_end_balance`.
- `transactions.csv`: cash-flow timing, credits/debits, `purpose` where populated; unlabeled withdrawals are **not** reliable discretionary-spending categories.
- `loans.csv`: end-of-2025 active status and monthly payments; **no verified interest rate or prepayment penalty information**.
- `standing_orders.csv`: standing-payment clues, but **undated** and not proof of a current or amendable agreement.
- `accounts.csv`, `dispositions.csv`: account ID and ownership/authorized users; an account is **not necessarily one individual's entire household wealth**.
- District data: background context at most, not reliable evidence that a particular customer will lose employment or afford an investment.

### Not in the dataset: do not invent

- All external savings, cash accounts, investment holdings, TFSA/RRSP room, debt APRs, insurance payout eligibility, exact salary, essential-vs-discretionary category breakdown, willingness to invest, risk tolerance, investment objective/horizon, dependants, current employment, exact current liquid balance, or actual consent to implement actions.
- Dataset history ends in 2025; do not pretend 2026 real-time finances are observed.

Use a provenance tag for every significant field: `OBSERVED`, `DERIVED`, `BANK_RECORD_VERIFIED` (only if actually supplied), `JUDGE_SPECIFIED`, `ASSUMED`, `NOT_AVAILABLE`. **Do not act as though the bank possesses unprovided client records.**

### Bank-side decision policy (mandatory)

- **Do not request additional data from the customer in the live tool.** Only `account_id` and the judge-specified twist are required user inputs.
- If data is adequate for a reserve or cash-flow plan, generate it automatically from observed / derived values with conditional amounts where needed.
- If a fact needed for precise investment / debt / insurance advice is absent, produce a nonblocking **analyst review flag**, never an inferred fact.
- A label such as **"investment suitability not verified"** means **no ETF/security recommendation can be justified using the supplied CSVs alone**; it does not mean the customer is unsuitable to invest.
- If an external amount has no evidence (e.g. a policy payout), exclude it from the funded base case; show it only as an explicitly labelled *what-if*.

## 3. Registry of normal-life goal triggers

A trigger is **active** when its documented condition holds; some triggers only produce a bank-side review flag rather than a goal recommendation. Names are stable IDs suitable for model inputs. Thresholds below are **policy choices to calibrate**, not facts derived from the competition or universal personal-finance rules.

| ID | Trigger | Signal / condition | Candidate goal or response | Availability / caveat |
|---|---|---|---|---|
| G01 | Sustained negative cash flow | Observed months with net outflow; `I - S < 0` as secondary lens | Budget stabilization, stop unsupported contributions | Derivable; distinguish recurring vs exceptional months |
| G02 | Very thin surplus | Near-zero typical surplus and small margin for error | Maintain liquidity and avoid new commitments | Set materiality threshold relative to spending; configurable |
| G03 | Unreliable surplus | High share of months `money_out > money_in` despite positive medians | Flexible vs fixed savings; protect cash | Derivable from monthly account data |
| G04 | Volatile deposits | Large swings in monthly `money_in` or long deposit gaps | Income smoothing reserve / variable contributions | Deposits are not necessarily salary |
| G05 | Deteriorating trajectory | Falling balance / worsening net flows in recent vs previous windows | Early stabilization review | Need adequate history; do not infer cause |
| G06 | Repeated negative balances | Nonzero `days_below_zero` or consistently low `min_balance` | Liquidity timing, operating cash floor | Derivable; not proof of overdraft fees unless separately observed |
| G07 | Timing mismatch | Dated credits arrive after recurrent large payments | Payment-timing strategy, operating float | Requires cautious transaction analysis and current-date confirmation |
| G08 | Below reserve target | Historical buffer proxy below configurable 3–6 months of chosen spending measure | Emergency-reserve building | B is historical proxy, not confirmed accessible funds |
| G09 | Cannot afford reserve contributions | All feasible monthly contribution policies fail affordability checks | `NO_FEASIBLE_CONTRIBUTION`; address cash flow first | No forced savings amount |
| G10 | Strong reserve but fragile timing | Sufficient average buffer yet frequent low/negative days | Cash availability/timing before investing | Shows why runway alone misses risk |
| G11 | High fixed-payment burden | High verified `F/I` or inability to cover fixed obligations under plausible stress | Review commitment exposure, protective reserve | `F` already included in `S`; do not add it twice |
| G12 | Active loan-payment pressure | Active loan payment material relative to inflows | Debt-budget protection | No APR inferred; cannot assert high-interest debt |
| G13 | Verified costly debt | Verified APR, fees, payment terms exist in an additional authorized record or the scenario; debt payoff economically preferable under constraints | Prioritize verified costly debt, retaining minimum liquidity | **Not established from supplied CSVs**; report payment pressure, not a high-interest claim |
| G14 | Loan nearing completion / payment freed | Verified remaining term and future release of payment | Redirect future surplus to next goal | Must verify timing; end-of-2025 status is not current repayment schedule |
| G15 | Reserve depleted after earlier event | Observed historical buffer proxy or verified accessible balance below target | Replenish emergency buffer | Historical depletion is evidence, not necessarily cause |
| G16 | Positive sustained surplus | Sufficient, repeated net-positive months with no higher-priority blockers | Choose savings/goal allocation | Positive medians alone not proof of investable surplus |
| G17 | Cash exceeds short-term reserve requirement | Verified available balances (if separately supplied) exceed estimated emergency and earmarked needs | Review options for additional capital | Do not equate historical B with unrestricted idle cash |
| G18 | Long-term investment readiness | G16 + plausible liquidity / manageable obligations; verified goal, horizon and risk information needed for investment suitability | Flag **potential investment review**, not ETF/security selection or automatic purchase | Bank records in competition do **not** establish suitability; do not prompt customer during demo |
| G19 | Short-term goal | Explicitly supplied known expense and short time horizon | Protected goal savings / liquidity | Without an explicit bank-record/scenario fact, this trigger is unknown |
| G20 | Major upcoming obligation | Explicitly supplied planned tuition, relocation, repairs, taxes, etc. | Sinking fund / scheduled funding | Requires documented amount and timing in input; otherwise stay inactive |
| G21 | Windfall / unusual high inflow | Exceptional deposit in banking history, or source documented as true windfall in additional supplied data | Mark apparent one-off inflow; avoid unrestricted windfall allocation without evidence | A transfer is not necessarily new income |
| G22 | Meaningful change in normal finances | Sustained new income/spending pattern validated across months | Recalculate goals and contribution capacity | Trend ≠ permanent salary change |
| G23 | Goal completed | Target met in supplied information or explicit scenario | Switch to next eligible goal or maintain | If required evidence is absent, flag review and avoid inferred completion |
| G24 | Insufficient or conflicting bank data | Short history, impossible values, ambiguous ownership or undocumented goal | `DATA_LIMITED_REVIEW` flag + safest supported goal (or maintain) | Do not interrupt with customer questions or claim verified eligibility |
| G25 | Shock makes prior goal temporarily unsafe | Judge event generates deficit / essential shortfall | Pause or revise goal contributions; prioritize backup response | Trigger on event, cross-links goal and shock pathways |
| G26 | No justified change | Stable obligations/reserves, no documented new objective, or available evidence insufficient | `MAINTAIN_AND_REVIEW`, not forced product sales | Legitimate high-quality answer |

**Notes:** G08 3–6 months is a configurable convention, not a hard rule for every person; essential spending is not fully identifiable in this dataset. G18 investment readiness **cannot** be concluded from bank records alone. An observed windfall G21 must not silently become a recurring salary assumption.

## 4. Decision order / conflicts

Evaluate **all** triggers; then choose one prioritized goal and optionally 0–2 overlay goals. This is a **ranking of urgency**, not a set of mutually exclusive hard-coded classes.

1. **Hard gates:** Check account validity, time windows, missing data, negative/invalid amounts, ownership ambiguity, current-balance uncertainty, and essential-expense limitations. Explicitly mark what cannot be concluded.
2. **Urgent protective needs:** G01, G06, G07, G09, G11 and G25. If essential commitments cannot be funded, `STABILIZE_FIRST` or `EMERGENCY_ACTION` precedes growth.
3. **Liquidity sufficiency:** G08, G10, G15. Build or protect accessible reserves; configure an operating-cash floor.
4. **Debt:** G12 protects payment obligations; G13 ranks debt repayment only when borrowing cost/terms are confirmed. Liquidity and expensive debt may both need partial allocation.
5. **Time-bound real goals:** G19 and G20 take precedence over long-term illiquid investment for money needed soon.
6. **Surplus allocation:** G16, G17, G18, G21, G23. If observed cash flow suggests surplus, flag *possible surplus allocation review*. An ETF or other personalized security recommendation remains **not verified** unless sufficient suitability evidence is actually supplied; never place trades automatically.
7. **Maintain / bank review:** G24 and G26. Return a conservative bank-facing plan and a `DATA_LIMITED_REVIEW` flag where necessary. Do not launch a customer questionnaire as part of the judging workflow.

**Priority exception:** Verified imminent essential obligations take precedence over generic reserve/investment heuristics; for fixed nonessential debt with extremely high verified APR, compare explicitly against the value of additional buffer rather than rigidly forcing a single sequence.

## 5. Goal type library: what the normal plan can actually say

| Goal type | Primary target | Plan sizing logic | Minimum constraint |
|---|---|---|---|
| `STABILIZE_CASHFLOW` | Reduce persistent monthly funding gap | Size required improvement from observed net cash flow; compute the improvement needed; label expense flexibility unverified | No imaginary budget cuts; essential costs protected |
| `PROTECT_OPERATING_CASH` | Maintain cash before bills fall due | Target an operating cash floor based on documented/observed upcoming bills | Dated flows needed; may produce conditional recommendation |
| `BUILD_EMERGENCY_RESERVE` | Reach customer-appropriate cash reserve | `max(0, reserve_target - available_liquid_cash_if_verified)`; if unavailable, show judging-proxy estimate with caveat | Contribution feasible in weaker months, not just average month |
| `SMOOTH_IRREGULAR_INCOME` | Reduce contribution failures during lean months | Small fixed or variable surplus-based transfers; cap after bills | No fixed contribution if inconsistent history cannot sustain it |
| `MANAGE_DEBT_OBLIGATIONS` | Meet required payments and avoid expensive deterioration | Use active payment and verified terms for repayment/relief | Do not assume lender approval or debt APR |
| `PREPARE_KNOWN_EXPENSE` | Fund a dated future obligation | `needed = max(0, amount - reserved_cash)`; monthly deposit = needed / months until due | Spending commitment must be documented in the supplied scenario or bank records |
| `REBUILD_AFTER_SHOCK` | Restore depleted accessible liquidity | Compute gap to target and feasible schedule | Never assume shock already recovered |
| `ALLOCATE_SURPLUS` | Choose among reserve, debt, near-term savings, long-term objectives | Compare feasible alternatives based on available verified or explicitly assumed inputs | No guaranteed returns; avoid asset double counting |
| `INVESTMENT_READINESS_REVIEW` | Determine suitability of long-term investment discussion | Check availability of documented objective, time horizon, risk tolerance, holdings and debt terms; if absent flag bank review | Not an ETF recommendation or trade |
| `MAINTAIN_AND_REVIEW` | Keep finances monitored with no forced change | Explain why no immediate action is warranted and what would trigger reassessment | Valid output; avoid fake personalized advice |
| `DATA_LIMITED_REVIEW` | Produce a cautious bank-facing conclusion when consequential facts are absent | Identify missing evidence as a flag, continue with supported calculations, suppress unsupported product advice | No customer questions during demo; no unsupported amount/insurance/investment claims |

## 6. Numerical methods and calibration

### Mandatory competition metrics — unchanged

- `I = median(money_in)` and `S = median(money_out)` over the account's monthly records, per README.
- `F = median(household_bills + insurance + loan_payments)` of the *monthly sums*; `H = median(household_bills)`.
- `B = mean(last six account-month avg_daily_balance)`.
- The official runway equation remains independent from goal scoring and is computed after the judge's shock.

### Additional behavioral features

- `r_t = money_in_t - money_out_t` for observed months; `positive_months_share`, `deficit_months_share`, median `r_t`, and e.g. 25th-percentile `r_t` (with data sufficiency caveats).
- `cashflow_volatility`, `deposit_gaps`, trailing balances, negative-balance days, observed loan-payment pressure.
- Record `history_months`, `history_start/end`, `missingness`, and use a documented trailing window (e.g. 12 rows) distinct from official full-history medians.

### Provisional reserve / contribution policy

- Set a **bank-policy-configurable** reserve objective, e.g. 3–6 months of spending; don't represent `3*S` as the one correct target for every customer.
- Use `B` only as the judging proxy; any actual recommendation based on a present liquid reserve requires confirmation of current available cash and pending obligations.
- Compare contributions (`$0`, small fixed, flexible surplus sweep) across historical months using no future information. A conservative heuristic may cap a proposed monthly contribution at a fraction of the lower-quartile realized surplus, but that is **not evidence of future affordability**.
- Never count a transfer to a savings account as newly created wealth; measure liquidity position and total resources separately.
- A valid result is `$0/month currently feasible`, followed by a plan to repair the deficit.

### Investment gate

`INVESTMENT_READINESS_REVIEW` may be offered when cash flow and liquidity are supportable. An **actual investment recommendation** requires sufficient verified suitability information (objective, horizon, tolerance, capacity for loss, other relevant finances); the challenge CSVs do not supply this. The bank-facing tool may flag *candidate for investment review* based on historical surplus, but should not automatically recommend an ETF or execute a trade. Compare returns as uncertain scenarios; do not invent ROI or claim an ETF is always appropriate. A selection model must never bypass this gate.

## 7. Shared interface to Classifier A (algorithm TBD), Gemini, and rules fallback

Input to each selector:

```json
{
  "account_id": "example_only",
  "feature_window": "trailing_12_months",
  "data_quality": {"history_months": 12, "missing_inputs": []},
  "active_goal_triggers": ["G03", "G08"],
  "documented_customer_goals_if_available": [],
  "shock_effects": {"judge_specified": true, "events": []},
  "constraints": {
    "current_liquid_cash_verified": false,
    "essential_spending_breakdown_available": false,
    "adjustable_expenses_verified": false,
    "investment_risk_profile_verified": false,
    "investment_horizon_verified": false
  },
  "eligible_goal_types": ["BUILD_EMERGENCY_RESERVE", "SMOOTH_IRREGULAR_INCOME", "DATA_LIMITED_REVIEW"]
}
```

The output must include `primary_goal`, `supporting_goals`, `trigger_ids`, `reason`, `data_provenance`, `bank_review_flags`, `proposed_actions`, `conditional_vs_verified`, `abstain_reason`, `next_review_conditions`. For a simultaneous judge shock also include selected backup modules and link any paused goal to G25. **Compute every monetary value in the independent finance engine, not via Classifier A/Gemini.**

Models compete on the **same cases**, same constraints and finance engine. If either suggests unsupported investments, fictional assets/insurance, unauthorized spending cuts, or a non-existent goal, it fails the safety gate and falls back to rules. Synthetic labels are not ground truth.

## 8. Acceptance scenarios / anti-loophole test cases

See companion CSV `Tangerine_Goal_Trigger_Test_Matrix.csv` for machine-readable scenarios. Examples:

- Positive medians but 5 of 12 months in deficit → G03, recommend flexible contributions, not a full-median-surplus fixed transfer.
- Historical average balance is high but latest months are negative → G05/G06, do not assume high present liquid wealth.
- Low reserve and high verified APR debt → cash minimum plus debt trade-off, not single blanket investment recommendation.
- Inheritance appears as one transaction → confirm it is genuinely new unrestricted cash before recommending allocation.
- Long-term long-term investing contemplated but emergency fund insufficient → explain trade-off; investment readiness not forced purchase.
- Customer has adequate reserves and no specific goal → G26 or flag undocumented objective; do not invent ROI recommendation.
- One month of banking history → G24; descriptive metrics only, abstain on confident volatility/seasonality claims.
- Active-loan status ended in 2025 → do not infer current balance or APR; avoid claim of expensive debt.
- Unlabeled withdrawals → do not classify as entertainment/subscriptions.
- Life event has no given financial effect → cannot assign dollars to it; report unquantified effect and expose bank-editable assumptions; no customer-facing prompt.
- Duplicate combined shocks → don't double-count changes or use annual percentage as monthly absolute amount.
- Salary rise amid severe liquidity deficits → stabilization and reserves first, not auto-invest.
- Savings goal complete but short-term expense approaching → switch to `PREPARE_KNOWN_EXPENSE`.
- Scenario or documented bank record states investment horizon under 1 year → avoid risky equities for required near-term money.
- An existing insurance premium in bank data is **not** proof of covered benefits.
- Client only an authorized user, not verified account owner → avoid assumed personal control over all account resources.
- Shock passed alongside goal calculation → generate goal and backup now, never assume months of prior savings have occurred.

## 9. Integration order for the team

1. Code the **trigger engine** as deterministic, testable predicates with provenance and explicit `unknown` states.
2. Verify with observed Tangerine records; do not treat all examples in the test matrix as real findings.
3. Implement goal eligibility/prioritization rules and `$0`/`MAINTAIN`/`DATA_LIMITED_REVIEW` flags without interrupting the demo.
4. Connect Classifier A (algorithm TBD) and Gemini to **the same** input schema and eligible goals; validate their outputs.
5. Connect the independent sizing solver and scenario evaluator, keeping the official shock runway untouched.
6. Compare selectors on safety first, suitability/goal relevance second, clarity and latency third. Preserve rules fallback.
7. Showcase 3 cases in judging: insufficient emergency buffer, healthy surplus but unstable cash-flow timing, and a combined judge shock that temporarily pauses the goal.

**Bank operator presentation:** For every account, return `primary_goal`, `backup_plan_if_shock`, `reason_codes`, `official_runway`, `conditional_projection`, `unresolved_gap`, and `bank_review_flags`. Display a result even when flags are present; never block on a customer response. The goal-plan output can be `MAINTAIN_AND_REVIEW` or a cash-flow stabilization objective when the data supports no more specific goal.

**Definition of done:** No unsupported investment recommendations; no fabricated current assets, debt APR, insurance payout or discretionary cuts; all official metrics match README; all acceptance scenarios pass; all recommendations identify their triggering evidence, assumptions and next review point. This is broad *financial-effect coverage*, not a claim to know every unknowable real-life event.
