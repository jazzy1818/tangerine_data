# Tangerine Mission Control — Agent Implementation Plan

**Project:** Sheridan Datathon 2026 — Tangerine / Resilience Rewired  
**Audience:** Coding / research agent and team developers  
**Status:** Execution brief, ready to start  
**Priority:** Data discovery → structured customer features → **JEFF classifier vs Gemini API** → independent financial simulation → comparative validation → live demonstration  
**Constraint:** Use **only the Tangerine competition datasets** for customer data. Do **not** import or analyze NASA datasets. NASA is a conceptual inspiration for *fault detection, safe mode, and mission replanning*, not a data source.

---

## 0. Mission and exact expected behavior

Build a reliable, explainable financial-resilience engine for this live judging workflow:

1. A judge enters an **`account_id`** selected from the Tangerine dataset.
2. A judge provides a previously unknown **financial twist/shock** (possibly in natural language). It may be negative, positive, temporary, permanent, or multiple events at once.
3. The system retrieves the customer's financial profile and engineered features, translates the event into structured **financial effects**, calculates the organizer-standard financial metrics and shock-adjusted runway, and identifies financial constraints.
4. The system **compares two plan-selection methods**: (a) the team's **JEFF classifier**, and (b) the **Gemini API**. Both receive the **same canonical information** and propose one lead financial module plus optional supporting modules and a brief rationale.
5. A **deterministic finance engine** validates the selected modules, sizes actions using equations and confirmed constraints, and simulates finances with and without the proposed response.
6. The interface shows the financial impact, selected **goal plan + backup/recovery plan**, **official runway**, conditional post-action projection, cost/tradeoffs, and any **unresolved funding gap**. No fictitious savings, insurance benefits, assets, or credit approvals.
7. Evaluate JEFF vs Gemini under the **same accounts, same twists, same financial solver, same measurement rules**; choose the method that yields the most useful **valid** plans, not the most persuasive prose.

**Product thesis:** "A NASA-inspired financial fault-management system that responds to externally specified shocks, enters an appropriate financial safe mode, and replans around the customer's actual resources." **Do not claim the model predicts job losses, accidents, deaths, or other shock probabilities.** The judge supplies the event.

**What we're optimizing for:** Protect essential financial commitments; reduce the chance or duration of a projected cash shortfall; improve **runway where it is meaningful**; minimize intervention costs and unreasonable burden; communicate remaining risk honestly. **Never maximize runway by assuming unlimited spending cuts, fake funds, or future income.**

**Five-minute live evaluation:** Discovery 35%; Data Use 25%; Communication 25%; Impact 15%. Expect 1-minute pitch, 3-minute live random customer + twist, 1-minute questions.

---

## 1. Inputs and repository inventory (start here)

**Before implementing:** inspect the available repository, data files, documentation, and dependencies. Reuse existing code rather than blindly replacing it. Determine whether the actual Tangerine `data/*.csv` files are present. The organizer README describes them, but they **were not present in the files previously shared with this agent brief**. If absent, build against a documented synthetic profile and the official schemas; do not invent findings or state that real-account tests passed.

Read in this order:

- `README.md` — **official Tangerine challenge definition**; source of truth for judge-facing metrics.
- `Tangerine_Universal_Financial_Planning_Blueprint.pdf` or `.docx` (if available) — 8-module financial philosophy.
- `Tangerine_Final_Financial_Plan.md` (if available) — calculation details, guardrails and worked examples; **note:** this is an earlier 7-module design. **The latest 8-module taxonomy below controls**.
- `Tangerine_Universal_Shock_Tester_v0_1.zip` or extracted `tangerine_universal_tester/` — an existing deterministic prototype, tests, and scenario matrix. Inspect before extending.
- `Pasted text(1).txt` (optional) — prior discovery hypotheses; **reported empirical counts are unverified** until reproduced.

Expected Tangerine data when available: `monthly_summary.csv`, `transactions.csv`, `loans.csv`, `accounts.csv`, `standing_orders.csv`, `dispositions.csv`, `clients.csv`, `cards.csv`, `districts.csv`. Key joins use `account_id` and supplied ID relationship tables. Do not import NASA CSVs.

**Clarify without blocking:** “JEFF classifier” is the team's chosen name, but no model/library definition was supplied here. Treat it as a pluggable backend called `jeff`. Find the existing JEFF implementation in the repository or team documentation; record its exact approach, inputs, training needs, and limitations. **Do not invent an algorithm named JEFF.** If it is not implemented, prepare its interface and start with a transparent rule-based baseline, clearly labelled **not JEFF**.

---

## 2. Phase A — Reliable data discovery and feature engineering (FIRST PRIORITY)

### A1. Implement the organizer's official customer profile exactly

For any `account_id`, calculate from `monthly_summary.csv`:

| Symbol | Definition | Exact requirement |
|---|---|---|
| `I` | Typical monthly money in | Median of account's `money_in` |
| `S` | Typical monthly spending | Median of `money_out` |
| `F` | Fixed costs | Median of monthly **sum** `household_bills + insurance + loan_payments` |
| `H` | Household bills | Median of `household_bills` |
| `B` | Historical buffer proxy | Mean of `avg_daily_balance` over **last six** month-ordered rows for the account |
| `P` | Active loan payment | `loans.monthly_payment` **only** if loan is still running at end of 2025; otherwise `0` |

Use the organizer's official runway function, separate from time-varying simulations:

```python
buffer_left = B - one_off_costs
gap = spending_after_shock - income_after_shock
if buffer_left <= 0:
    official_runway = 0
elif gap <= 0:
    official_runway = "no shortfall (120+)"
else:
    official_runway = min(buffer_left / gap, 120)
# Round numeric runway to 1 decimal for display.
```

- The README example: job loss with EI at 55% -> `income_after_shock = 0.55 * I` **for the challenge scenario**, not a claim of actual eligibility; household bills up 15% -> `spending_after_shock = S + 0.15 * H`; furnace repair costing typical monthly spending -> `one_off_costs = S`.
- **Do not add `F`, `H`, or `P` to `S` again**; those costs are already represented in `money_out`. Add only shock *increments*.
- `I` is **money in**, not a proven employment salary. `B` is an **historical mean**, not a verified current account balance. Show these distinctions.
- `transactions.csv` rows within the same day are not strictly time-ordered; do not infer an intraday ordering from their row sequence.
- Active loans, available history, absent rows, missing/null fields, zero incomes, negative balances, and sparse records need explicit handling.

### A2. Discover useful patterns from the **actual Tangerine data**

Do **not** start with ML. Use descriptive statistics and account-level exploratory analysis. Prioritize meaningful insights that could change the financial decision:

| Feature (trailing 12 months when available) | How to calculate | Potential planning decision |
|---|---|---|
| Typical surplus | `I - S` | Initial capacity benchmark, **not** fixed contribution proof |
| Realized monthly surplus | `money_in_t - money_out_t` | Detect whether an apparently affordable plan is actually sustainable |
| Share of deficit months | `% of months with money_out > money_in` | Fixed vs flexible savings; caution on recurring commitments |
| Income/inflow volatility | E.g. std/median or IQR, with zero-denominator handling | Cash-flow instability; liquidity caution |
| Minimum balance and negative-balance days | `min_balance`, `days_below_zero` | Hidden liquidity shortfalls despite positive monthly figures |
| Historical buffer coverage | `B / S` if `S > 0` | Emergency reserve strength |
| Fixed-cost burden | `F / I` if `I > 0` | Degree of likely budget inflexibility |
| Debt-payment burden | `P / I` if `I > 0` | Debt Defense overlay |
| Balance trajectory | Observed change in balances over window | Deteriorating or improving reserves |
| Recurring payment / inflow timing | Transaction dates; only where inferable | Cash-flow scheduling recommendations |
| Data-quality flags | Months observed, missing columns, stale or incomplete information | Confidence; safe fallback |

**Discovery experiments to run and report with reproducible denominators:**

1. Accounts with positive typical surplus but insufficient official runway under an organizer-stated 55% income scenario.
2. Accounts with positive typical surplus but frequent real deficit months; identify whether fixed monthly savings would have been sustainable.
3. Months with at least one negative balance day that nevertheless finish with nonnegative month-end balance.
4. Accounts with similar typical inflows and buffers but different low-balance histories — investigate whether volatility/timing adds information beyond averages.
5. Optional: relationship between fixed-payment burden, low-balance days and vulnerability. Control for inflow and buffer levels where practical.

**Important:** The prior research note mentioned counts (714/3,309; 1,986/2,902; 612/1,326). Treat these as hypotheses to **reproduce or correct**, not established facts. Document filters, periods, missingness, and exact denominator for each finding. Do not generalize from the anonymized source bank accounts to all Canadian households.

**Outputs of Phase A:** `data_audit.md`, `account_features.csv` (one row per account, documented formulas), `discovery_report.md` (3–5 findings with charts and caveats), `feature_dictionary.md`, and a tested function `get_customer_profile(account_id)`.

**Acceptance:** Every sampled `account_id` reproducibly computes the organizer's definitions; discovered patterns refer to real, inspected Tangerine data; no hidden dependence on future transactions in a historical experiment.

---

## 3. Phase B — Universal shock translator (unknown twist handling)

A shock is supplied externally, so **model financial effects, not event probabilities**. Implement a typed, validated event schema supporting multiple simultaneous or sequential effects, such as:

```json
{
  "shock_id": "combined_01",
  "description": "Lost job, EI at 55% for six months, bills up 15%, repair $1500",
  "effects": [
    {"type":"income_multiplier", "value":0.55, "start_month":1, "duration_months":6, "evidence":"judge_specified"},
    {"type":"household_bills_percent", "value":15, "start_month":1, "duration_months":6, "evidence":"judge_specified"},
    {"type":"one_off_cost", "value":1500, "start_month":0, "evidence":"judge_specified"}
  ],
  "assumptions": ["No automatic re-employment assumed after month 6"]
}
```

Support at least: `income_multiplier`, `income_delta`, `expense_delta`, `expense_percent`, `household_bills_percent`, `household_bills_delta`, `debt_payment_delta`, `one_off_cost`, `one_off_receipt`, `liquidity_hold`, `investment_return`, and `unspecified_event`. Use a normalized monetary-effect schema and implement overlap, sign, and duration constraints. Do **not** apply two incompatible overlapping multipliers or debit the same one-time expense twice.

**Free-text challenge:** A judge may phrase a shock in unexpected terms. Provide either (a) a validated natural-language translator to the structured schema or (b) a fast guided form allowing an operator to translate arbitrary twists manually. Gemini may be tested as a translator **separately** from its plan-selection performance. Invalid or ambiguous shocks should produce `needs_details` + an editable assumption field, **not invented financial effects**. Keep the ability to edit magnitude, duration, timing and combined events during the demo.

**Outputs:** `shock_schema.json`, `parse_shock.py` or equivalent, `shock_validation_tests.py`, and an auditable source-of-each-number field.

---

## 4. Phase C — Financial planning library and solver (shared by both selectors)

Use the latest **8-module response library**. One lead module plus zero or more supporting modules may be activated. Modules are **actions/financial response families**, not risk predictions or demographic labels.

| ID | Module | Trigger/problem |
|---|---|---|
| `M1` | Income Continuity | Lost, delayed, or changed recurring inflows |
| `M2` | Cost Rebalancing | Recurring increases/decreases in living costs |
| `M3` | Emergency Liquidity | One-time expenses / immediate liquidity pressure |
| `M4` | Debt & Obligation Defense | Loan payment changes or threatened essential obligations |
| `M5` | Multi-Shock Stabilization | Several interacting shocks; orchestrates other modules, no duplicated charges |
| `M6` | Reserve Restoration | Rebuild an accessible cash cushion after a shock |
| `M7` | Cash-Flow Timing & Access | Delayed payments, frozen funds, date mismatches |
| `M8` | Surplus & Windfall Allocation | Raises, bonuses, inheritances, positive surpluses |

**Important compatibility note:** The older markdown financial plan used 7 `P1..P7` modules, while the newer shock-tester README defines these 8 `M1..M8` modules. **Standardize on the table above everywhere**, and implement a documented crosswalk if reusing legacy code.

### C1. Both plan outputs are generated **after** account ID + twist are entered

- **Goal plan:** A realistic resilience target, such as rebuilding or establishing a cash reserve, with affordable contribution strategy and optional timeline. If recurring contributions are unsupported, say so.
- **Backup plan:** An immediate response to the given shock: primary financial problem, candidate interventions, exact calculated target, feasible confirmed actions, runway/projection impact, and unresolved funding gap.

### C2. Shared deterministic financial calculations

- Compute the official first-period runway **exactly** as specified in Phase A.
- Separately simulate a month-by-month cash path over the stated horizon, with time-varying income/benefits, expenses, one-time transfers, verified commitments, and action costs.
- Preserve non-cash invested assets separately from accessible cash; a stock loss must not silently reduce checking cash and an investment gain must not count as cash without a sale/settlement assumption.
- When the post-shock monthly gap is zero or negative, official runway is *no shortfall*; do not pretend that maximizing a capped 120-month display is meaningful. Optimize reserve adequacy, shortfall prevention, and feasible recovery instead.
- Represent interventions with IDs, `amount_cad`, timing, user-confirmed bounds, `evidence`, status (`verified`, `conditional`, `calculated_target`, `not_feasible`), cost, trade-off, and revised cash-path effect.
- Before optimizing, **protect essential obligations**. Then consider verified liquidity/benefits, realistically adjustable spending, timing changes, and approved payment relief. Credit and policy payouts cannot be assumed.
- If no feasible set of actions covers the selected horizon, report the shortfall amount and first period of shortage, not a fabricated recovery.
- NASA-inspired **Financial Safe Mode** (`NORMAL`, `PROTECTION`, `EMERGENCY`) is determined by transparent financial conditions, *not* the selector's unverified confidence score.

**Illustrative formula for constant deficit**, with available buffer after immediate one-off costs `B_left`, target `T` months and no additional costs:

```text
monthly_gap = max(0, S_after - I_after)
required_monthly_improvement = max(0, monthly_gap - max(0, B_left)/T)
```

This is a **required target**, not proof that the customer can cut that much spending. Dynamic shocks require the period-by-period solver, not this shortcut.

**Outputs:** shared `finance_engine` APIs `official_metrics()`, `simulate_cash_path()`, `score_candidate_plan()`, `size_actions()`, `make_goal_plan()`, `make_backup_plan()`, and `determine_safe_mode()` with unit tests.

---

## 5. Phase D — Two competing plan-selection backends

Both candidates receive the **exact same** canonical `CustomerFeatures + ShockEffects + FinancialConstraints` object; both return the same `PlanSelection` JSON structure, e.g.:

```json
{
  "lead_module": "M1",
  "support_modules": ["M2", "M5"],
  "reason_codes": ["income_drop", "recurring_cost_increase", "compound_shock"],
  "needs_clarification": [],
  "rationale": "Income and household costs changed together."
}
```

Selector outputs are **proposals**, never the authority on dollar calculations. **The finance engine** sizes actions, checks constraints, rejects invalid proposals, and computes consequences. If a backend outputs invalid modules, unsupported assumptions, or nothing, use a deterministic rule-based fallback and record the failure. Keep the fallback's results distinct from model wins.

### D1. Approach 1 — JEFF classifier

- Locate and document what the team means by **JEFF classifier**; do not assume a named off-the-shelf package.
- Implement `select_plan_jeff(customer_features, shock_effects, constraints) -> PlanSelection`.
- Determine whether it is an existing trained model, a custom classifier, or rule system; log implementation/version and training data requirements.
- **Critical issue:** Tangerine has no ground-truth labels for “best financial module.” Do not train supervised JEFF directly as though such labels exist. If labels are created by financial rules or synthetic optimizer results, label them `synthetic/pseudo-labels` and evaluate both agreement with that teacher and independently measured financial outcomes.
- If the real classifier is not available, implement only the adapter and a clearly named `rule_baseline`, then proceed with the rest of the product.

### D2. Approach 2 — Gemini API

- Implement `select_plan_gemini(customer_features, shock_effects, constraints) -> PlanSelection` using the official Gemini API/SDK and **structured JSON output**.
- Give Gemini the module descriptions, allowed enum values, case facts, explicit restrictions, and the **minimum necessary** derived customer features. Validate every returned field; retry once or fail closed to the rule baseline.
- Use a low-variance setup and log model version, prompt version, calls, elapsed time, invalid outputs, and cost where measurable. Never place API keys in code or logs; use environment variables.
- Do not send raw transaction histories, names, full customer records, or other unnecessary private details; an anonymized feature vector and scenario are sufficient. Check competition policy and API data-handling terms before remote calls.
- **Gemini must not invent cash amounts, insurance coverage, employment status, or benefits;** it selects modules and explains the known facts. All arithmetic is deterministic.
- Official API reference: https://ai.google.dev/gemini-api/docs/structured-output (check the current SDK syntax rather than copying outdated code snippets).

### D3. Shared integration

Implement an adapter/factory:

```python
select_plan(profile, shock, constraints, backend="jeff" | "gemini" | "rules")
```

Use one `PlanSelection` validator, one financial engine, and one output renderer. Switching the backend should not change the official baseline profile/runway for the same account and shock.

**Outputs:** selector interfaces and adapters, versions/config files, a rule baseline, trace logs, and paired backend outputs.

---

## 6. Phase E — Fair JEFF vs Gemini evaluation (DO NOT CHOOSE BY VIBES)

Build a fixed **evaluation suite** of accounts and twists. Include all three organizer examples, rare/unfamiliar events, positive shocks, no financial impact, missing dollar values, unusual account histories, and combined/overlapping effects. Test the same cases through `jeff`, `gemini`, and a transparent rule-based baseline.

**Evaluation cases:**

- Negative income, delayed income, partial EI, full unemployment, and an explicitly specified post-benefit phase.
- Bills/rent inflation, loan-payment changes, one-off emergency costs, a windfall and a salary increase.
- Divorce or accident **with specified financial effects**; the same life event **without amounts** must produce `needs_details`.
- Account access temporarily frozen; investment return shock to separately supplied holdings; no-effect event.
- Multi-shock stacking, opposite effects, inconsistent/contradictory event fields, repeated identical inputs, nonpositive buffer, no active loan, zero inflow, high historical volatility, short account history.

**Metrics** (store *per case* for each backend):

| Metric | Interpretation |
|---|---|
| Schema validity | Was output parseable and within module enums? |
| Financial safety violations | Any invented funds, unsupported actions, double counting, negative essential spending? **Must be zero** after validation. |
| Fit to shock | Does the lead/overlay selection address observed effects? Independent expert/rule rubric. |
| Feasible projection | Did solver produce a valid action plan or an honest unresolved gap? |
| Improvement | Conditional cash shortfall reduction, time to first shortfall, reserve remaining, costs/assumptions; compare against no-action baseline. |
| Consistency | Same input repeated; sensitivity to reasonable perturbations. |
| Generalization | Handling of held-out scenarios not used to tune prompts/classifier. |
| Latency and reliability | P50/P95 response time, error/fallback frequency, offline usability. |
| Explainability | Can a judge understand *why* the action was proposed? |

Use a simple, published decision rule: **first disqualify unsafe/invalid recommendations**, then compare financial feasibility/fit; only then use latency, clarity, and cost as tie-breakers. Don't select Gemini solely because the prose sounds polished, or JEFF solely because its category accuracy looks high. If neither consistently beats the rule baseline, **use the rule baseline** for judging and report the finding honestly.

**Evaluation discipline:**

- Keep a **held-out** scenario/account set untouched while tuning prompts or classifier parameters.
- If testing sustainability over historical time, use earlier months to generate features, later months to assess outcomes; do not use later transactions as inputs to earlier predictions. `monthly_summary` is based on transactions, so avoid redundant leakage.
- A plan label supplied by rules is not independent proof that the rule-based plan is financially optimal.
- Run identical deterministic financial checks for both selectors. Mark savings cuts as hypothetical/confirmed, not automatic.
- Synthetic scenario tests establish consistency under assumptions, **not** actual future impact on customers. Do not claim causal success from simulated recommendations.

**Outputs:** `evaluation_cases.jsonl`, `selection_comparison.csv`, `comparison_report.md` (winner **and reasons**, or fallback choice), and tests against failures.

---

## 7. Phase F — Demo and submission integration

**Judge screen minimum:**

1. Account ID input and editable twist field; form controls for shock magnitude, duration and combined events.
2. Customer summary: `I, S, F, H, B, P`, reserve coverage and 2–3 informative discovered features.
3. Official-style pre-shock / post-shock runway (clear labels), cash-path projection and financial safe mode.
4. Goal plan and shock-specific backup plan: lead module, overlays, amount/timing, conditional vs verified actions.
5. No-action vs with-action projection; visible remaining gap and first shortage period.
6. A concise explanation of **why** the selected strategy matches this customer; assumptions and uncertainty.
7. Backend toggle for internal comparison; **hide confusing experimental controls during the actual judging flow**.

**Suggested pitch:** "NASA-inspired fault management for personal finance: the shock is provided, our system diagnoses the impact, protects essential financial functions and replans with quantified, feasible interventions. Our data discovery reveals when normal monthly averages conceal risk." Use the last claim only if supported by a reproducible Tangerine analysis.

**Required competition submission artifacts:** 2–3 minute demo video, code repository/ZIP, short write-up and biggest validated finding, and citations/links to all external data sources actually used. Allow the judges' random account/twist to run live without hand-editing code.

---

## 8. Proposed repository / work product layout

Adapt to whatever project structure already exists; do not rewrite everything unnecessarily.

```text
README.md
requirements.txt
.env.example                  # only variable names; no secrets
config/
  modules.json
  selector_config.json
  shock_schema.json
src/
  data_loader.py
  official_metrics.py
  discovery.py
  feature_engineering.py
  shock_parser.py
  financial_engine.py
  plan_modules.py
  selectors/
    interface.py
    rules.py
    jeff.py
    gemini.py
  evaluate.py
  app.py
reports/
  data_audit.md
  feature_dictionary.md
  discovery_report.md
  comparison_report.md
  selection_comparison.csv
  evaluation_cases.jsonl
tests/
  test_official_metrics.py
  test_shocks.py
  test_finance_engine.py
  test_selectors.py
  test_judge_scenarios.py
```

---

## 9. Execution order, stop conditions and acceptance gates

**P0 — Make the judge calculation indisputably correct (mandatory).**

- Verify original data availability; inspect and join sources.
- Write reproducible `get_customer_profile(account_id)` and unit tests against independently calculated reference examples.
- Implement the official runway and three example twists with correct money-in/spending handling.
- Reuse/fix the prior shock-tester code as appropriate.
- **Gate:** 100% pass on organizer formula tests; random valid IDs don't crash; missing data is explicit.

**P1 — Discover findings and build explainable features (mandatory).**

- Reproduce or correct preliminary findings; make one real-data insight suitable for the 1-minute pitch.
- Build one canonical feature vector with provenance, date windows and missingness flags.
- **Gate:** documented denominators and no fabricated statistics; features are demonstrably useful to a plan decision.

**P2 — Normalize arbitrary judge twists and connect finance solver (mandatory).**

- Handle compound effects, event timing, ambiguous input and unknown events; output `needs_details` as appropriate.
- Ensure consistent goal + backup outputs for all 8 modules; support insufficient-funds outcomes.
- **Gate:** correct responses to judge examples and adverse synthetic tests; no double counting and no unfounded claims.

**P3 — Compare JEFF, Gemini and rules on the same data (mandatory to answer team's model choice).**

- Finish adapters and safe fallback; record paired outputs on held-out cases.
- **Gate:** zero unchecked financial-safety violations, validated schemas, reproducible comparison; justified winner or explicit baseline fallback.

**P4 — Deliver stable live demo (mandatory).**

- Random accounts, editable shock controls, explanation, runway, revised trajectory and gap.
- **Gate:** successful dry run of 5-minute judging workflow; no API key exposure; offline fallback if Gemini fails.

**P5 — Optional enhancements (only after P0–P4):** richer daily liquidity analysis, optimization across verified interventions, natural-language explanation polish, ensemble approach, NASA-themed visuals, insurance/investment *scenario lab with disclosed assumptions*.

---

## 10. First task for the coding agent (execute immediately)

**Do not spend the first work session training a classifier or designing a UI.**

1. Inventory the repository; report the Tangerine files actually present, JEFF status, Gemini credentials/config status, existing tester compatibility and missing prerequisites.
2. Implement and test the official `get_customer_profile(account_id)` calculation and its runway function. If the original CSVs are unavailable, implement readers from the documented schema and write accurate synthetic fixture tests; **do not invent dataset findings**.
3. Run the preliminary discovery checks once real data exists, producing a short reproducible report with exact denominators.
4. Build canonical data structures for `CustomerFeatures`, `ShockEffects`, `FinancialConstraints`, `PlanSelection`, `FinancialPlanResult`; save JSON sample payloads.
5. Return a status update with **files created/modified, tests run, actual findings, blockers, and the next smallest implementation step**.

**Never silently claim a finished feature or tested result without executable evidence.** Prefer a working minimal vertical slice over a sprawling, unfinished model training pipeline.

---

## 11. Non-negotiable policy and methodological guardrails

- **Only Tangerine banking datasets** for real customer data; **no NASA raw data**. The NASA analogy is fault management / safe mode / replanning.
- Don't use protected personal attributes (e.g., gender/age) or region as shortcuts for restricting essential financial support; avoid inferring sensitive traits from accounts.
- Don't transmit identifiable/raw customer transactions to Gemini; use derived anonymized aggregates and respect event rules and API data-handling constraints.
- No probabilities of shock occurrence unless sourced and explicitly justified; a supplied shock has an assumed occurrence, not an estimated probability.
- Do not hallucinate discretionary categories from unlabeled cash withdrawals.
- Keep official historical-buffer runway distinct from current cash availability and the time-varying trajectory.
- No fabricated insurance payout, investment return, credit approval, salary, benefit, or spending-cut feasibility.
- Cash moved from checking to savings is a reallocation, not new wealth. Do not double-count loans, one-time costs, or internal transfers.
- Never let a selector bypass financial constraints. Fallback to deterministic rules if an API or model fails.
- Explicitly report uncertainty and unresolved gaps. Never promise that hypothetical advice will prevent actual future financial hardship.
- Treat this as an educational competition prototype, **not** regulated individualized financial advice or a bank's deployed underwriting tool.

## References supplied with project

- Organizer's *Tangerine / Resilience Rewired* `README.md` (requirements and official financial formulas).
- Team's finalized universal financial blueprint and prior financial-plan markdown (use latest module mapping in this document).
- Existing v0.1 universal shock tester and validation report, if present.
- Gemini structured output documentation: https://ai.google.dev/gemini-api/docs/structured-output
