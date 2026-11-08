# Tangerine Mission Control — Finance-Owned Decision Policy v1.1 — With Codex Integration Handoff

**Status:** Proposed finance policy for team review; not yet approved or regression-tested as a complete policy.  
**Owner:** Finance teammate. **Audience:** Engineering, release owner, judge-facing bank analysts.  
**Date:** 2026-11-08. **Coverage:** All 4,500 accounts; arbitrary typed shocks supported by the project schema.  
**Not:** A customer-executed banking instruction, personalized regulated investment advice, a guarantee of solvency, or a probabilistic forecast of job loss.

## 0. Decision statement

**Given an account, an externally supplied scenario, and a modeling horizon, output an ordered, defensible financial response:**

1. Diagnose the change and its first financial consequence.
2. Identify the earliest urgent cash/obligation risk.
3. Generate **eligible candidate financial actions** from M1–M8.
4. Gate each action by evidence, timing, consent/authority, direct costs, and available liquidity.
5. Recalculate all cash checkpoints for each supported action and defensible combinations.
6. Select a defensible response, make its trade-offs explicit, and state the **unresolved funding requirement** when one remains.
7. Specify the next event/date that requires reassessment.

**Non-negotiable:** A module label is not an actionable recommendation. A mathematically required savings or spending target is not proof that the customer can implement it. Never turn missing approval into approved cash relief.

## 1. Three distinct outputs; do not blend them

| Output | Inputs and basis | Intended meaning |
|---|---|---|
| **Official organizer runway** | Full-history medians I/S/H; last-six-month historical B; prescribed shock | Standardized judging metric, not a personalized lifespan forecast |
| **Modeled shock cash ledger** | Historical proxy or separately specified opening cash; quantified dated shock effects | First negative checkpoint, maximum deficit, six-month need, access timing |
| **Financial action plan** | Cash ledger plus eligible, evidenced action candidates and constraints | Prioritized recommendation with amounts, dates, limitations and remaining gap |

Never compare cash results from different opening-cash bases as though they were causally comparable. `B` is a historical average balance, **not verified current spendable funds**. Income data are bank inflows, **not necessarily wages**. A single account does not establish complete household wealth or financial obligations.

## 2. Evidence framework — required on every proposed action

Each fact/action carries a provenance code:

- **OBSERVED:** Recorded in supplied bank files; note observation dates. Example: an outflow was recorded. This does *not* establish current availability or adjustability.
- **DERIVED:** Deterministic computation from OBSERVED, with named formula/window.
- **JUDGE_SPECIFIED:** External hypothetical scenario input; valid for scenario arithmetic, not evidence of a real-life event.
- **BANK_CONFIRMED:** Explicit authorized action terms actually provided to the tool, including dates, approvals, fees and baseline treatment. For synthetic tests, label confirmation as *hypothetical within test*.
- **ASSUMED_FOR_COMPARISON:** Conditional assumption; must not be posted to the primary supported-action result.
- **UNKNOWN_OR_CONFLICTING:** Missing/ambiguous information; no guessed impact or full funding claim.

**Action status:**

| Status | What bank analyst may say | What numerical result may include |
|---|---|---|
| `SUPPORTED_MODELED` | “Under the supplied authorized terms, this action reduces the modeled funding need by $X.” | Cash change in the **supported action** ledger |
| `CONDITIONAL_ONLY` | “If X is approved and costs Y, this scenario would change cash by Z.” | **Separate scenario comparison only**; never silently in supported ledger |
| `TARGET_ONLY` | “The scenario requires an additional $X by Month N or $Y/month.” | **No cash change** until a source is verified |
| `BLOCKED_OR_UNKNOWN` | “Cannot quantify/execute this action from the available evidence.” | **No credited relief**; if unknown affects projected cash, full funding need is null |
| `MAINTAIN` | “No safe changes are justified; preserve the current viable plan and review.” | Original ledger unchanged |

Even `SUPPORTED_MODELED` does **not** mean the bank executed a transfer, altered a loan contract or made a trade.

## 3. Core calculation rules (finance owns meaning; code owns arithmetic)

For a fully specified model, including **all** relevant dates within horizon:

- `cash[0_start] = opening_accessible_cash` (provided/current verified cash if available; else historical proxy clearly labeled).
- Post immediate expenses/holds at Month 0; show start/end checkpoints if code provides both.
- For each month `t`, post **start-of-month** costs, receipts, loan repayments, approved fees, and hold releases **before** the monthly recurring net flow.
- Post the full month’s recurring income, spending and supported recurring action cash changes at **month-end**.
- `first_shortfall = first chronological checkpoint with accessible_cash < 0`; exactly $0 is covered at that checkpoint.
- `first_shortfall_need = abs(cash[first_shortfall])`.
- `funding_need_horizon = max(0, -min(accessible_cash for all checkpoints))` **only when the path is complete**.
- `action_funding_improvement = funding_need_no_action - funding_need_with_action` on matched openings/scenarios/horizons.
- `remaining_need` is the **with-action funding need**, not merely the prior need minus an untested nominal saving.
- Track **total cash** separately from **accessible cash** during holds. A hold release isn't income.
- A transfer from a checking account to another accessible savings account may change *account-specific observed cash* without creating household net wealth. Do not claim newly earned funds.
- Unknown-priced effects, unknown duration that can materially affect the horizon, unverified debt terms, or unconfirmed future income can make the **complete** need unknown. Display known-components-only values separately.
- Never double count loans, bills, fees or insurance already included in `S`. `F` is a presentation breakdown, not an additional line added to `S`.
- Scheduled repayments beyond the comparison horizon remain **visible obligations**, not forgiven liabilities. A six-month result does not prove a decision has no later downside.
- For organizer presets, preserve README formula *separately*: `buffer_left=B-one_off`, `gap=S_after-I_after`; buffer<=0 -> 0; positive buffer and gap<=0 -> `no shortfall (120+)`; else round `min(120,buffer_left/gap)` to 1 decimal at end.

### Timing dominance rule

A later action cannot prevent an earlier shortage. An action is **timely for a particular shortfall** only if its cash effect becomes accessible **at or before that negative checkpoint**. If it starts later, label the early shortage unresolved even if six-month ending cash improves.

### Action interaction rule

Cash effects must be composable once only: if a $300 scheduled transfer is already counted as spending, a supported pause releases exactly that payment, not an additional saving contribution; if a repayment includes a $50 fee, post it once. Recalculate the entire path from original inputs for any combination; do not add individually estimated improvements unless their interactions have been replayed.

## 4. Policy priorities — by financial urgency, not module number

1. **Immediate access/solvency:** Prevent the earliest negative checkpoint or quantify the cash required to cover it; identify protected essential obligations.
2. **Obligation defense:** Avoid missing required loan, rent/utility and insurance-related payments **where actually identified**. If obligations cannot all be covered, show the uncovered amount; do not assume new credit eligibility.
3. **Recurring financial stabilization:** Address structural negative net flow; temporary delays alone are not permanent solutions.
4. **Cheaper, evidenced interventions:** Prefer options that improve the cash path without creating larger unreported fees, later catch-up obligations or new high-risk exposure.
5. **Reserve restoration:** Once obligations and stable resources support it, rebuild an accessible reserve with a defensible contribution.
6. **Non-urgent goals:** Consider additional debt repayment, goal-based savings, and investment *readiness* only after liquidity and actual objectives are appropriately established.

Priority exceptions are explicit: an imminent contractual payment, a verified expensive obligation, and a known dated receipt can alter sequencing. Never automatically force a zero-cost savings plan ahead of genuinely urgent debt.

### Selecting among candidate sets

Evaluate `no_action`, each eligible action, and reasonable, non-conflicting combinations. **Do not optimize a dollar score before respecting hard constraints.** Reject action sets that rely on unapproved terms, double-count cash, violate timing, or hide downstream obligations.

For valid sets, show the trade-off across these dimensions (in order of explanation, not as an unreviewed weighted algorithm):

- Does it resolve or delay the **earliest** shortage? What amount is still needed at that point?
- What is the **lowest accessible cash** and full-horizon funding need?
- Does it protect required obligations and a justified minimum accessible-cash floor?
- What are the **fees, repayment dates, interest/costs (if supplied), and post-horizon obligations**?
- Does it sacrifice longer-term goals or decrease flexibility?

A temporary deferral may improve Month 1 while worsening the final need; it may be shown as a **conditional emergency bridge with a cost**, never as a net saving. If no action passes the gates, output a prioritized **bank review / funding target**, not a fake accepted action.

## 5. Module-by-module financial decision rules

### M1 — Income Continuity

**Activate:** Documented/judge-specified reduction, loss or delay of recurring income. An event name with unknown amount is a diagnosis flag, not a numeric flow.

**Finance decision:**

1. Calculate income in each affected month **only** from known event parameters. Bank inflows are not verified wages; an EI multiplier is an organizer scenario assumption.
2. Measure first shortage and ongoing gap; protect immediate obligations.
3. Suspend **new, proposed** non-essential allocation commitments that would worsen the modeled cash path (cash credit $0 if they were never in spending).
4. Evaluate actual, evidenced scheduled transfers that are included in spending and are permitted to pause (M5/M2 if shared). Recompute cash and note delayed goal.
5. Quantify remaining cash gap or required recurring improvement as **TARGET_ONLY**. Recommend examining verified alternatives (new income, documented benefits, actual adjustable expenses), but never invent their amounts.
6. At benefit expiration, if replacement income is unverified, mark subsequent projection incomplete and specify review of next income event.

**Never:** Assume full wages return automatically after six months; apply loan relief without terms; misinterpret `money_in` as salary.

### M2 — Cost Rebalancing

**Activate:** Higher/lower recurring spending, category bill shocks, or demonstrable structural deficit.

**Finance decision:**

1. Apply specified increments to baseline `S`, e.g., `S_after=S+0.15*H`. H=0 => zero *modeled identified bill increment*, not proof no actual household bills exist.
2. Categorize costs as **evidenced mandatory**, **confirmed adjustable**, or **unclassified**. Unlabelled cash withdrawals are never auto-classified as discretionary.
3. For a positive recurring deficit, calculate required improvement for the relevant horizon, respecting immediate checkpoints.
4. Only an identified reduction with amount, start/end dates, permissions if needed, and no double counting can enter `SUPPORTED_MODELED`.
5. Show unfilled residual if the verified cuts do not cover the gap. If costs fall instead, preserve positive surplus; don't automatically invest it.

**Never:** Suggest cutting rent, loan payments, insurance or household necessities as though contractual reduction were freely available; sum F atop S.

### M3 — Emergency Liquidity

**Activate:** Unexpected one-off expense or an immediate / first-period funding shortage.

**Finance decision:**

1. Post the expense at its **actual specified checkpoint**; a Month 0 repair reduces opening cash first.
2. Compare cost against **accessible** cash; distinguish historical B from currently liquid funds.
3. Quantify immediate shortfall separately from six-month minimum cash need.
4. First evaluate existing accessible funds and confirmed permitted payment scheduling; only **approved** instalments, repayments and fees can replace the original dated cost.
5. Review unsupported sources (insurance, external accounts, credit) as **unverified bank-review items**, not funded solutions.

**Never:** Invent insurance payouts, new loans, external savings, payment plans, or say a later receipt covers a prior shortage.

### M4 — Debt & Obligation Defense

**Activate:** Loan payment pressure, an identified debt-payment shock, or an obligation threatened by cash shortages.

**Finance decision:**

1. Determine payment from historical obligations *in modeled spending* and/or explicit scenario terms. A loan snapshot P alone does not prove a particular amount is already present in S.
2. Do not add P to S again. Confirm any candidate reduction is bounded by the **actual included payment**.
3. For deferral: record **each** month of relief, date and amount of catch-up, **all** fees/interest supplied, and any outstanding principal after horizon.
4. Evaluate **earliest shortage relief and total-horizon cost together**. Show if it merely shifts the problem to another checkpoint.
5. If included payment/approval/repayment terms are missing, block cash posting of both relief **and** linked repayment; display conditional comparison only if explicitly labeled and complete.

**Never:** Say deferred debt is forgiven or refinanced when no agreement establishes it; assume access to new borrowing.

### M5 — Multi-Shock Stabilization

**Activate:** Two or more material simultaneous/adjoining adverse effects, or interaction of income loss, costs, debt and one-offs.

**Finance decision:**

1. Build a **single unified dated ledger**, not one separate bank balance per module.
2. Rank first shortage/essential obligations before long-term goals.
3. Merge M1–M4/M7 action candidates; deduplicate overlapping cash effects; model fees and delays once.
4. Compare no action, individually eligible actions, and defensible combinations. Do **not** assume individual funding improvements add linearly.
5. Output a **time-ordered response**, not merely a list of modules. Display residual gap and first unresolved checkpoint.

**Never:** Claim a combined fix without recalculating the full path or double-counting bill increases/outflow pauses.

### M6 — Reserve Restoration

**Activate:** A separately evidenced/stipulated stable recovery checkpoint after pressure, or insufficient reserves under normal conditions when financially supportable.

**Finance decision:**

1. At a **new checkpoint**, establish current/provided accessible cash, committed upcoming costs, obligations covered, cash-flow stability, and available supported contribution.
2. Use initial competition policy target `reserve_target=3 * representative_monthly_spending` unless a documented different policy/goal is supplied. This is an illustrative starting target, **not a universal necessity**. FCAC discusses 3–6 months of regular expenses as a general guideline.
3. `usable_cash = available_cash - earmarked_near_term_cash` (without flooring a negative value to zero); `reserve_gap = max(0, reserve_target - usable_cash)` when the cash evidence is complete. Negative usable cash blocks automatic rebuilding.
4. If **confirmed sustainable monthly contribution `c>0`**, `months_to_target=ceil(reserve_gap/c)` (ignoring interest), capped by verified monthly surplus if known.
5. If `c=0` or unknown, leave ETA **unknown/open**; still show target and gap.
6. Avoid immediate investment recommendations based solely on reserve reaching target; reassess normal goal and investment suitability separately.

**Never:** Assume the customer automatically recovered income when a temporary benefit ends; treat moving existing money between accounts as earnings.

### M7 — Cash-Flow Timing & Access

**Activate:** Shortfall caused or aggravated by dated cash timing, delayed receipt, temporary liquidity hold, or a candidate bill-date shift.

**Finance decision:**

1. Diagnose **which checkpoint** fails, and whether the money arrives afterward.
2. Model confirmed dates and same-month bill shifts only with identified bill, date window, actual effective date, fees and approval. A historical seven-day move is a **conditional replay**, not evidence billers agreed.
3. Compare first negative day/checkpoint, deepest deficit and month-end total. Show where a shift solves a within-month shortage but **doesn't** solve negative monthly net flow.
4. A liquidity hold reduces accessible cash; release increases accessibility, not income.
5. Keep **daily replay** distinct from median-based monthly ledger unless the opening basis and measurement horizon are deliberately made comparable.

**Never:** Assume a future deposit retroactively pays an earlier bill, or confuse a timing solution with permanent budget improvement.

### M8 — Surplus & Windfall Allocation

**Activate:** Quantified one-off receipt, stable new recurring income or documented surplus after protecting obligations/reserves.

**Finance decision:**

1. Post one-off receipts **once** at actual timing; don't multiply by six and call them ongoing salary.
2. Check liquidity shortfalls, obligations, reserves, verified near-term goals and expensive debt **where APR/terms known**.
3. Protect required funds and pending expenses; compute **uncommitted** amount without assuming all B is spendable.
4. For near-term or unknown horizon, recommend liquid goal allocation / bank review, not a security.
5. Initiate investment **readiness review** only if cash conditions pass and appropriate investment objective, timeline, risk and other suitability data are available. Do not select a specific ETF/trade from these CSVs.
6. A positive windfall with unresolved financing needs may properly be assigned first to covering a quantified cash deficit.

**Never:** Recommend investing immediately after an unexplained deposit; invent returns, tax status, debt APR or risk tolerance.

## 6. Normal-life Goal Plan (before/alongside the shock)

The **normal goal is a separate pathway**. Triggers are financial conditions, not invented external events. It is assessed from the account's supported historical features **before** applying the selected shock, then stress-checked after the shock.

| Condition | Primary goal | Action decision |
|---|---|---|
| Repeated deficits / negative cash checkpoints | Cash-flow stabilization | Diagnose deficit and first pressure point; avoid fixed new commitments |
| Low observed reserves and supported positive cash generation | Emergency reserve | Set a policy-backed target and a contribution **only if supported** |
| Loan/obligation stress | Obligation protection | Preserve required amounts; review debt cost if terms known |
| Irregular, but sometimes positive, monthly cash | Flexible reserve accumulation *review* | Consider conditional surplus-based contribution **only** when dated accessible cash exceeds protected obligations/floor; don't impose a fixed schedule |
| Consistent surplus with reserves and verified goals | Goal-based saving | Size contribution without dipping below cash floor or binding payments |
| Long-term objectives with verified suitability data | Investment readiness review | Assess suitable options; do **not** automatically buy ETFs |
| No justified opportunity | Maintain & monitor | Provide a legitimate positive explanation for not changing allocations |
| Insufficient/contradictory facts | Bank-side evidence review | Continue known calculations, label uncertain quantities; no customer form in judge demo |

**Important current implementation finding:** In a historical-data-only test, **5 of 4,500** accounts received a positive *fixed* monthly allocation. That is **not proof** 4,495 customers cannot save. Finance/engineering should audit which blockers dominate, and ensure alternate *nonfixed* advice (stabilize, reserve liquidity, flexible review, maintain) is useful and not disguised as an automatic money transfer. Never loosen controls merely to increase a recommendation count.

## 7. Required action proposal object (conceptual contract)

For **each** candidate/selected action, produce:

```json
{
  "action_id": "existing-transfer-pause-01",
  "module_ids": ["M1", "M5"],
  "title": "Pause a confirmed existing monthly transfer",
  "purpose": "Retain cash during six-month income shock",
  "status": "SUPPORTED_MODELED",
  "evidence": ["JUDGE_SPECIFIED synthetic approval; already included in S; fee=0"],
  "amount_cad": 300.00,
  "starts_at": "Month 1 end",
  "ends_at": "Month 6 end",
  "required_permission": "Verified pause terms (hypothetical in this test)",
  "cash_treatment": "Release included monthly outflow once; never create wealth",
  "effect_on_first_shortfall": "Month 2 end to Month 3 end",
  "effect_on_horizon_need_cad": -1800.00,
  "downsides": ["Delays original savings goal", "Depends on six permitted pauses"],
  "outstanding_need_after_cad": 1560.00,
  "review_checkpoint": "Before Month 3 end",
  "not_executed": true
}
```

A `TARGET_ONLY` action uses **null/unknown impact**, not an invented reduction. Each action must have a specific ID, dates, evidence, model status and scenario hash; selected actions in the UI must match actual modeled ledger inputs. A classifier or LLM cannot inject arbitrary amount, fee or product fields.

### Required plan-level output

1. Account/profile basis and evidence labels.
2. Scenario summary and diagnosed first shortage (if complete).
3. Normal goal **before** the shock and whether the goal should be held, reduced or revisited.
4. Top **1–3 prioritized actions** with `SUPPORTED_MODELED` / `CONDITIONAL_ONLY` / `TARGET_ONLY` clearly distinguished.
5. Side-by-side no-action vs **same-shock with supported actions**, including lowest cash, first shortage, six-month need and fees/repayments.
6. Amount still unfunded and the **earliest review deadline**; if incomplete, display `FULL FUNDING NEED NOT ESTABLISHED` rather than a numeric claim.
7. What bank-side data/approval is required; never interrupt judge demo with a mandatory customer questionnaire.
8. Next checkpoint or trigger for reassessment; include post-horizon obligations.

## 8. Worked finance acceptance examples

### A — Compound shock; transfer distinction

Inputs: opening $3,000; immediate repair $1,500; original monthly income $3,000; spending $2,400 including H=$400; income falls to 55%; H rises 15%, all for six months. No-action cash after repair $1,500; new inflow $1,650; spending $2,460; monthly deficit $810.

| Comparison | First shortage | Six-month extra starting cash need | Interpretation |
|---|---|---:|---|
| No action | Month 2 end, $120 | $3,360 | Quantified problem |
| Cancel a **future proposed** $300 transfer not in S | Month 2 end, $120 | $3,360 | Frees **$0**; may be sensible to avoid a new commitment |
| Pause **confirmed existing** $300/month outflow in S, fee $0 | Month 3 end, $30 | $1,560 | Retains $1,800 **in modeled account cash**; original goal may be delayed |

After the existing pause, a further **$260 per month from Month 1** would mathematically close the remaining six-month gap *if actually available*. This is a **TARGET_ONLY**, not a suggested fictional cut. A new action beginning later must be re-simulated and may fail to cover an earlier shortage.

### B — Late receipt; liquidity before the receipt

Opening $1,000; income $1,800, spending $2,400 monthly; **confirmed** $2,000 receipt at Month 3 start. Month-end cash: $400, -$200, $1,200, $600, $0, -$600. First shortage: $200 at Month 2 end **before receipt**; full six-month need: $600. The receipt doesn't cure the missed checkpoint.

### C — Debt deferral increases long-run need

Opening $300; income $2,200, spending $2,400 including $300 loan payment. Original path: first shortage Month 2 end, $100; six-month need $900. With approved Months 1–2 $300 relief, plus **$650 catch-up** Month 4 start: first shortage Month 4 **start**, $350; six-month need **$950**. It is temporary liquidity relief at an extra $50 cost. If inclusion evidence is absent, the intervention is blocked and funding conclusion of altered action path remains unknown.

### D — Supported recovery, no arbitrary investment

Stable checkpoint: accessible cash $3,000, monthly essential spending $2,400, obligations covered, supported contribution $300/month. Initial target `3 × 2400 = $7,200`, gap $4,200, timeline `ceil(4200/300)=14 months`; if no contribution is established, timeline remains open. No claim customer has invested.

### E — Missing income amount

If judge enters “Income changes” with no amount, direction or duration, display observed profile and *known-only* diagnostic with **complete affected funding need null**. Do not silently substitute 0% loss or a false zero deficit. Bank analyst sees missing scenario components for review.

## 9. Critical edge cases and mandatory behavior

| Case | Mandatory result |
|---|---|
| `I=0` | No fictitious wage-loss dollars; assess existing spending and cash honestly |
| `S=0` | No undefined reserve ratios / divide-by-zero; spending-based shock may be 0 by organizer rule |
| `H=0` | 15% × H = 0 for official shock; no inference the household has no bills elsewhere |
| `B<=0` | Official runway = 0; cash ledger separately shows current/proxy basis |
| `gap<=0` and `B_left>0` | Official `no shortfall (120+)`; do not imply infinite real-world safety |
| Exactly $0 cash checkpoint | Not a negative shortage |
| Very large / negative inputs | Reject invalid effect rather than produce impossible cash flows |
| Loan active but P not observed within S | Don't claim a payment decrease without inclusion evidence |
| Only future proposed transfer | Pause cash effect = **$0** |
| Existing transfer included but approval/fees unknown | Conditional only or blocked, no cash credited |
| Bill date adjustment with next-month date | Not automatically eligible for the same-month historical comparison |
| Temporary relief with post-horizon catch-up | Show later liability and prevent claim that cost was eliminated |
| Future receipt after first deficit | Earlier deficit must remain in timeline |
| Income or expense effect with unknown amount | Incomplete future funding; don't fabricate numeric gap |
| Shared account / external finances unknown | Do not claim customer/household total wealth or income |
| High cash balance + one-off windfall | Do not prescribe ETFs without goal/suitability information |
| Combined repeated effect ID | Reject conflict or avoid duplicate debit depending on semantics |
| Multiple independent one-off charges | Post each *genuinely distinct* charge once |
| Reserve is needed during emergency | Allow modeled emergency drawdown; don't apply reserve floor as a fictitious prohibition on spending essential cash |
| Customer account switches in UI | Clear/bind action evidence, transfer approvals and recovery snapshot to new account |
| Monthly scenario vs separate daily replay | Don't claim daily solvency from month-end data; keep bases explicit |

## 10. Version 1 engineering acceptance criteria

**P0 — financial correctness (must pass):**

- No action may change the supported ledger without a corresponding original financial event, permitted dates, amount, and appropriate evidence.
- All displayed CAD changes reconcile to original scenario and candidate entries; fees/repayments counted once.
- First shortage uses earliest **negative checkpoint**, including Month 0 and month start; six-month need uses **minimum** checkpoint, not final balance.
- No-action and supported-action paths share identical original scenario and opening cash basis.
- No complete funding claim for unpriced material effect; known-component estimate clearly separated.
- For synthetic cases A–E, preserve the expected outcomes in §8 (and 112-point independent audit where applicable).
- No hardcoded customer IDs; all available accounts use the same policy gates.
- Classifier (local/Jev/Gemini) suggests modules only; finance rules validate effects, and selected text is generated from validated numbers.

**P1 — actionable outputs (should pass before demo):**

- Show ordered diagnosis, at most three principal actions, and action status, dates, money impact, review flags and residual funding need.
- Show reason **why** each candidate was included, excluded or left conditional.
- Show post-horizon catch-up obligations and timing tradeoffs.
- Give legitimate `NO_SUPPORTABLE_ACTION`, `MAINTAIN`, and `REVIEW_REQUIRED` plans rather than generic or fabricated advice.
- When fixed saving contribution = 0, propose a meaningful *nonfixed finance objective* where evidence justifies it, with no false cash projection.

**P2 — optional improvements if time remains:**

- A structured candidate action library beyond existing transfer pauses, using proper bank review approvals for expense reductions or installment schedules.
- Better prioritization for multiple feasible interventions and a dedicated bank analyst decision audit trail.
- Adaptive stress scenarios to reveal shortcomings; don't label invented data as observed bank outcomes.

### Required QA handoff for the finance teammate

For each review case, engineering exports: `account_id`, `scenario_hash`, `source_commit`, `opening_cash_basis`, `lead_module`, `candidate_action_ids`, `accepted_action_ids`, `conditional_action_ids`, `excluded_action_ids_and_reasons`, every month/phase/cash ledger row, `first_shortfall`, `first_shortfall_gap`, `horizon_need`, `action_fees_and_future_obligations`, `remaining_gap`, `completeness`, and bank-review evidence flags. The finance teammate independently checks recommendation **reasoning**, not just arithmetic.

## 11. Explicit policy questions for team approval

1. **Target:** Keep initial three-month reserve target tied to representative spending (`S`) for demo, with explicit policy disclaimer? *Proposed: yes.*
2. **Action status:** Must bank approval be required before an action alters the supported path? *Proposed: yes; judge-provided fictional approvals are synthetic evidence only.*
3. **Shortage ordering:** Prioritize earliest shortage/essential obligation even where total six-month funding need worsens slightly? *Proposed: show as a conditional, costed emergency bridge with explicit tradeoff; do not automatically declare it optimal.*
4. **Missing amounts:** Prefer a specific calculable funding target and review flag over a fictional savings/credit source? *Proposed: yes.*
5. **Investments:** Should the model buy/recommend particular ETFs based on transaction history alone? *Proposed: no; only readiness and conditional suitability review.*
6. **Goal saving:** When a fixed allocation is unsafe, allow condition-based *flexible savings review* without inventing a monthly deposit? *Proposed: yes.*

## Source and compatibility notes

- Competition's organizer formulas and definitions: project `README.md` in `jazzy1818/tangerine_data` repository.
- Existing implementation checked at 2026-11-08: `CRISIS_RESPONSE.md`, `crisis_response.py`, `tailored_advice.py`, `shock_playbook.json`, `investment_triggers.py`, `INVESTMENT_TRIGGERS.md`. Much of cash accounting and some supported action logic already exists; **the policy above does not claim every candidate action type is automatically executable today**.
- FCAC general emergency fund framework: https://www.canada.ca/en/financial-consumer-agency/services/savings-investments/setting-up-emergency-funds.html
- CIRO client objectives, risk capacity, time horizon and suitability context: https://www.ciro.ca/office-investor/investing-basics/selecting-advisor
- The 3-month illustrative reserve target, priority ordering and action-status framework in this file are **our proposed project policy**, not regulatory requirements or truths proven by the CSV dataset.

**Approval status: DRAFT — finance teammate to approve constraints and priority exceptions; engineering to implement/test; finance to sign off on actual output.**


---

# Appendix A — Engineering / Codex integration handoff

The following is the copy-ready team integration brief; preserve the finance-policy clauses above as the source of truth.

# Codex handoff — Integrate the finance-owned Financial Decision Policy

**Project:** Tangerine Mission Control / Sheridan Datathon 2026  
**Assigned to:** Engineering / Codex  
**Finance policy owner:** Finance teammate (human review required)  
**Task status:** Implementation request, **not** approval to alter financial policy  
**Primary reference:** `Tangerine_Financial_Decision_Policy_v1.md` (or the appended identical policy in the v1.1 handoff edition).  
**Important:** This is a **bank analyst decision-support** tool; it does not contact customers, execute transfers, buy securities, arrange credit or approve loan changes.

## Copy-ready task for Codex

You are working in the existing `tangerine_data` project. Implement the **finance-owned decision policy** in `Tangerine_Financial_Decision_Policy_v1.md`, preserving organizer scoring logic, tested cash arithmetic, safe existing behaviours and the current application. The end product must turn a selected account ID and a judge-entered shock into a **specific, ordered, financially defensible action plan** with clear evidence limits. **Do not stop at assigning M1–M8 labels.**

### Phase 0 — Inspect and audit before changing code

1. Record branch, exact Git commit, `git status`, current tests, and available data. Work on a separate feature branch/worktree; preserve uncommitted changes, avoid unrelated edits, and **do not push/merge/submit** without explicit team approval.
2. Read the attached policy in full, then inspect the actual current versions of `README.md`, `CRISIS_RESPONSE.md`, `engine.py`, `crisis_response.py`, `scenario_execution.py`, `tailored_advice.py`, `pause_decisions.py`, `recovery_plan.py`, `investment_triggers.py`, `goal_validation.py`, `backup_comparison.py` (if present), `shock_playbook.json`, `app.py`, and tests. **Do not assume names or signatures if they changed.**
3. Create `finance_policy_integration/POLICY_IMPLEMENTATION_MATRIX.md`: map each actionable rule in policy §§2–10 to **already implemented / partially implemented / missing / blocked by unavailable evidence** and note the exact function and test. Distinguish a classification output, an arithmetic funding target, an actual supported action, and a conditional bank-review suggestion.
4. Prefer extending existing validated financial paths. Do not build a competing cash calculator or modify the organizer's I/S/F/H/B/P and official runway definitions.

### Phase 1 — Define a deterministic action-plan contract

For every valid selected account and scenario, return a structured **finance plan** after the deterministic finance engine validates the scenario. Reuse existing schema/output fields where sensible, or add a small versioned schema. It should contain:

- `account_id` (local display/export only), `scenario_hash`, `source_commit`, `horizon_months`, and `opening_cash_basis` (`historical_proxy` vs supplied/verified).
- `financial_diagnosis`: the imposed shock, relevant baseline, recurring gap, one-offs, timing, first negative **month and phase**, first shortage amount, lowest accessible cash checkpoint, no-action horizon funding need, and complete/partial status.
- `lead_module`, `support_modules`, and **why** they apply. Keep M1–M8 as the project taxonomy; they are not the recommendations themselves.
- `prioritized_actions`: **at most three primary actions** in the bank analyst summary. For each: stable ID, plain-English instruction, rationale and targeted problem, `status`, necessary evidence, start/effective date, amount/frequency, source of cash movement, fees, repayment/catch-up dates, post-horizon obligations, affected scenario events, financial effect on matched checkpoints, and any risks/trade-offs.
- `candidate_action_decisions`: **all evaluated candidates**, including excluded ones and exact reason. Do not hide why a plausible intervention was rejected.
- `no_action` and `supported_action` cash paths from the **same scenario/opening basis**, plus first-shortage comparison, minimum cash, funding need, and residual gap. Leave full need null when materially incomplete.
- `required_target_only` (e.g., additional cash now or recurring improvement needed) **separate from actionable savings**; do not credit it to the applied ledger.
- `bank_review_flags`, `next_review_checkpoint`, and `model_limitations` for unconfirmed terms, insufficient facts, unaffordable contributions, unverified current liquidity or future conditions.
- `normal_goal_impact`: preserve/resize/pause only if the existing goal is genuinely affordable; distinguish a **proposed future transfer** from an included, approved existing outflow.

`status` must distinguish at least: `SUPPORTED_MODELED`, `CONDITIONAL_ONLY`, `TARGET_ONLY`, `BLOCKED_OR_UNKNOWN`, and `MAINTAIN`. A supported modeled action means *the supplied scenario evidence supports including its cash effect*, **not** that the bank performed it. Add a review flag where a scenario approval is hypothetical.

### Phase 2 — Implement finance-owned action selection and timing

Use the financial policy's priorities, rather than choosing whichever module produces attractive prose:

1. Protect the **earliest negative accessible-cash checkpoint**, including Month 0 and month-start. Exactly $0 is *not* a shortage.
2. Preserve identified essential obligations and required debt service; never pretend undocumented cash withdrawals are discretionary or cancellable.
3. For structural deficits, calculate the required improvement, but present it as `TARGET_ONLY` until a specific fundable action is evidenced.
4. For verified existing transfers already in baseline spending, with known approval/date/fee and no double-counting, use existing guarded pause logic. A new **proposed transfer not in spending frees $0** in the no-action cash path.
5. For a loan deferral, include **both** reduced payments and exact dated catch-up/fees, and show total future liability. Block/mark incomplete if baseline inclusion or repayment terms are missing. Do not imply debt forgiveness.
6. For dated bills/receipts and liquidity holds, evaluate **when** cash becomes accessible. A later action cannot cure an earlier shortage. Preserve the separate basis and approval caveats of any conditional daily-replay bill shift; do not silently mix it into the monthly supported path.
7. For specific expense reductions or split-payment arrangements, model the cash benefit **only when the underlying expense/approval, amount, fee and effective schedule are supplied and supported by existing engine semantics**. Otherwise show a conditional suggestion and verification requirement, with $0 credited.
8. For simultaneous shocks (M5), replay combined actions **once from the original scenario**. Prevent duplicate fees, payouts, pauses, bill increases and debt adjustments; evaluate interaction and future commitments. M5 orchestrates, rather than creates separate cash.
9. For recovery (M6), require a **separately supplied stable checkpoint** and supported contribution. Reserve target/gap can be calculated without a contribution; the timeline stays unknown when contribution or stability isn't established.
10. For surplus/windfall (M8), recognize a one-time receipt as one-time. Do not assume recurring income or recommend an ETF, TFSA contribution, trades or products without relevant suitability, objective, horizon and consent evidence.
11. If **no supported intervention** exists, return an honest and useful plan: state the first problem, quantified shortfall if complete, priority of obligations, `NO_SUPPORTABLE_ACTION`/review outcome, and **what specific bank-side evidence could change the decision**. No forced recommendations.

**Action prioritization:** hard financial/evidence constraints first; then earliest-shortfall relief; then remaining horizon funding gap and essential payment protection; then fees, repayment timing, future liabilities, liquidity floor and delayed long-term goals. If priorities conflict, show the trade-off. Do **not** claim an optimized plan without actually evaluating the feasible candidate combinations.

### Phase 3 — Integrate the output into the actual demo

- Place a compact **“Recommended Financial Actions”** section in the bank analyst Backup Plan view **above or beside** the existing two-path cash chart, with up to three numbered action cards and a visible *remaining funding gap*.
- Each action card must show: what, why, when, amount, supported/conditional/target status, expected improvement, and required review. A bank analyst must distinguish a financially demonstrated benefit from a hypothetical possibility at a glance.
- Keep the existing complete ledgers and reviewer flags available. If the two cash paths overlap because no feasible action is established, say why in plain English.
- Keep the normal **Goal Plan** and **Allocation Review** separate from the shock response; explicitly show when shock conditions justify pausing/reducing a proposed new contribution or reviewing an existing schedule.
- Gemini/Jev (actual provider name **Jev**, not JEFF) may classify the case or emphasize **approved, validated findings** only. They must not invent prices, cash savings, fees, action approvals or new accounting entries. Preserve local/offline fallback; don't make external API calls on page rerenders. No raw customer records or account IDs to remote providers.
- Use language suitable for an **internal bank analyst**. Missing evidence is a review flag—not a customer-facing pop-up or demo-blocking questionnaire.

### Phase 4 — Prove the finance decisions, not merely that code runs

**Mandatory regression:** preserve all existing tests, official runway formula, dataset-wide metric behaviour and ledger-validation invariants. Test account switches and stale evidence, duplicate action identities, unknown amounts/durations, future receipts and repayments, zero balance, zero I/S/H, negative historical B, active loan status, short histories, shared accounts, unusual windfalls, costs outside horizon and compound shocks. Never hardcode account IDs into decision rules.

**Independent known-case financial anchors:**

| Case | Required result |
|---|---|
| A, six-month compound shock | No action: first shortage Month 2 **End**, full need **$3,360**. Proposed new $300 transfer pause: **$0 benefit**. Verified included/approved $300/month pause: Month 3 **End**, residual full need **$1,560**. Further $260/month only `TARGET_ONLY` unless actually sourced. |
| B, $2,000 at Month 3 **Start** | Month 2 **End** first shortage **$200**, full six-month need **$600**. Later receipt doesn't erase earlier negative cash. |
| C, $300 loan deferral M1–2 with $650 catch-up M4 **Start** | Original: first shortage M2 End, full need **$900**. Deferral: first shortage M4 **Start**, full need **$950**. Without payment-in-spending evidence do not post assumed relief/repayment to supported ledger. |
| D, separately supplied stable recovery snapshot | Reserve target **$7,200**, gap **$4,200**, conditional **14 months** at supported $300/month; unknown contribution → timeline **unknown**. |
| E, unspecified “Income changes” | Show known components; **full affected cash need unknown**, no invented 0%/55% loss. |

**Finance acceptance sampling:** export **15 fully rendered examples** with different **real account histories and hypothetical judge-supplied shocks**. Include: stable surplus, structural deficit, thin buffer, negative/zero B, zero I, zero S, zero H, account with active loan, short history, shared account, income loss, one-off repair, compounded loss+bills, late receipt, deferral with fee/catch-up, liquidity hold, missing-value scenario, recovery and positive windfall. A case may cover more than one category; ensure **every category** is represented even if >15 cases are necessary. Sampling must be documented and not handpicked exclusively from successful cases. If a scenario isn't representable, mark it as **not supported with a reason**, not as passed.

For each reviewed case export: raw input provenance (avoid unnecessary personal data), account ID stored locally, scenario, code commit, module choices, normal goal, action cards with evidence/eligibility, all candidate inclusion/exclusion decisions, complete checkpoint-level no-action and supported-action ledgers, first shortfall month/phase, total fees/future repayments, funding need improvement, remaining gap, accuracy/completeness flags, and an exact screenshot or textual UI capture of what the judge sees. Finance will check both the numbers **and quality of recommendations**.

Provide a machine-readable review sheet with columns: `case_id`, `account_id`, `scenario`, `candidate`, `finance_policy_clause`, `priority`, `evidence_status`, `action_status`, `result_before`, `result_after`, `remaining_gap`, `first_shortfall`, `complete`, `bank_review_flags`, `finance_reviewer_verdict` (blank), and `finance_reviewer_notes` (blank).

### Phase 5 — Hand back to the finance teammate

Produce `finance_policy_integration/` with:

1. `POLICY_IMPLEMENTATION_MATRIX.md` — policy clause → existing/new functions → current status and residual gaps.
2. `ACTION_PLAN_CONTRACT.md` — final output schema, definitions and examples.
3. `FINANCIAL_DECISION_TEST_RESULTS.md` — exact commands, pass/fail counts, skipped tests, source commit and important edge cases.
4. `finance_acceptance_cases.csv` plus detailed structured outputs (`.json` or `.csv`) for the complete reviewed set of 15+ customer/scenario pairs.
5. `FINANCE_REVIEW_NOTES.md` — unresolved policy decisions, conditional actions, risks and instructions to reproduce any case.
6. A short **offline demo script**: select account → enter shock → observe diagnosis → open actions → compare cash paths → explain remaining gap and limitations.

**Required final Codex message:** “Implemented / already existing / deferred” by policy area, files changed, branch and commit, exact automated test results, link/path to the 15+ outputs, and the most important **three outstanding finance review questions**. Leave human finance approval **PENDING**. **Do not claim completion based solely on test counts.**

### Stop conditions and non-goals

- If finance policy conflicts with organizer math, preserve the **official organizer metric** and flag the conflict. Do not silently change its definition.
- If a new action type cannot be modelled with reliable dates/fees/evidence, **do not invent an executable cash effect**. Provide a conditional/manual-review recommendation with no booked benefit instead.
- Do not reclassify raw cash withdrawals as non-essential spending, invent debt APRs, imply verified current balances from historical B, assume EI is real salary replacement, use external APIs for financial arithmetic, buy ETFs, execute transactions, or claim banking approval.
- Do not expand into unnecessary redesigns, replace existing validators, remove functioning Goal/ETF panels, or rewrite unrelated files.
- Do not send bank customer data or source files to external services; keep API keys in approved local configuration.
- Finish with a reviewable code diff and a **finance acceptance package**, not a congratulatory summary.

## Finance owner's acceptance condition

**The finance teammate signs off only after seeing the actual action recommendations for varied accounts and shocks.** Passing calculations proves the arithmetic, not that the chosen advice is financially sensible. The final plan must make the next action, timing, conditional evidence, measured effect and unresolved need understandable to a skeptical bank analyst.
