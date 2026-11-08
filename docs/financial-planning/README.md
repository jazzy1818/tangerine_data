# Eight-module financial plan

This is the team's starting point for the financial-planning material already
stored in this repository. The full blueprint, financial rules and implementation
references are linked below. Module names follow the current code contract.

## Full plan and policy documents

| Document | What to use it for |
|---|---|
| [Universal Financial Planning & Shock-Response Engine — full PDF](../../Tangerine_Universal_Financial_Planning_Blueprint.pdf) | Financial specification, reusable response modules, action primitives, worked cases, validation and evidence requirements. |
| [Bank-facing implementation plan v2](../../Tangerine_Agent_Implementation_Plan_v2_Bank_Facing.md) | Product workflow, structured scenarios, shared financial solver and eight-module implementation brief. |
| [Bank-facing goal trigger engine v2](../../Tangerine_Goal_Trigger_Engine_v2_Bank_Facing.md) | The 26 normal-life goal triggers, eligibility priorities and evidence limits that complement the eight shock-response modules. |
| [Current crisis response and recovery](../../CRISIS_RESPONSE.md) | Implemented cash checkpoints, supported effects, debt deferrals, contribution pauses, unknown inputs, recovery and runtime validation. |
| [Current surplus allocation and investment review](../../INVESTMENT_TRIGGERS.md) | Historical capacity, reserve protection, investment-review restrictions and mandatory safeguards. |
| [Current classification contract](../../CLASSIFICATION.md) | M1–M8 labels, canonical input, local/provider selection and separation of selection from cash arithmetic. |

The PDF is a financial design specification. An action described there is not
automatically implemented or approved: check the current calculation limits in
CRISIS_RESPONSE.md and the execution code before using it in a customer case.
Older briefs' seven-module `P1`–`P7` naming and historical provider descriptions
should not override the current `M1`–`M8` code contract.

## The eight financial response modules

| ID | Canonical name | Financial problem addressed | What the plan must make visible |
|---|---|---|---|
| M1 | Income Continuity | Lost, reduced, delayed or changed recurring inflows. | Supplied income effects, monthly deficit, timing and the funding gap; unknown replacement income remains unknown. |
| M2 | Cost Rebalancing | Changed living costs or an unsustainable recurring budget. | The affected expense component and its change, with existing obligations counted once. |
| M3 | Emergency Liquidity | One-time expenses or immediate liquidity pressure. | Immediate cash impact, accessible funds, first shortage and additional cash required. |
| M4 | Debt & Obligation Defense | Debt-payment changes, arrears or threatened essential obligations. | Payment inclusion evidence, approved relief, fees, repayment obligations and any remaining gap. |
| M5 | Multi-Shock Stabilization | Several interacting financial effects. | One combined ledger, priorities and supporting modules, with no duplicated charges or cash credits. |
| M6 | Reserve Restoration | Rebuilding an accessible cash cushion. | Supplied recovery cash, reserve target/gap, supported contribution and a conditional timeline when the amount is known. |
| M7 | Cash-Flow Timing & Access | Delayed payments, frozen funds or bill/deposit timing mismatches. | When cash is accessible and payments occur; monthly projections and separate historical daily comparisons keep their own bases. |
| M8 | Surplus & Windfall Allocation | Raises, receipts, positive surplus or a windfall. | The supplied amount and timing, protected obligations/reserves and evidence needed before allocation. |

The classifier proposes one lead module and up to two supporting labels. All
supplied financial effects still execute; the label limit never drops a cost,
receipt or repayment from the cash ledger. These modules describe responses,
not probabilities of future shocks or demographic customer labels.

## How a financial plan is produced

1. Load the account and show the organizer's I, S, H, F, B and P definitions.
   Historical buffer B remains a historical proxy, not verified cash today.
2. Express the event as dated changes to income, spending, one-time flows, debt
   or liquidity. Preserve unknown amounts and timing as unknown.
3. Produce the normal goal and the shock-specific backup comparison. Keep the
   official rounded runway separate from the dated cash ledger.
4. Use local rules or a classifier to propose modules. The deterministic finance
   engine validates the proposed response and calculates money independently.
5. Show immediate, month-start and month-end accessible cash, the first negative
   checkpoint and remaining funding need. Label incomplete results as known
   components only rather than making a complete funding claim.
6. Model an intervention only with the required source, baseline inclusion,
   authority, amount, timing and fee/repayment evidence. A proposed investment
   pause supplies no cash already present in the baseline.
7. Evaluate recovery from a separately supplied checkpoint. Liquid reserve
   earmarks remain accessible cash; no investment returns or new wealth appear.
8. Keep implementation checks and human finance sign-off separate. An analyst
   reviews the independent worksheet, observed results and assumptions before
   recording an approval.

## Source code and review evidence

| Reference | Role |
|---|---|
| [plan_classification/schemas.py](../../plan_classification/schemas.py) | Canonical module IDs/names and validated financial effects. |
| [engine.py](../../engine.py) | Organizer metrics, official shocks and financial-plan integration. |
| [scenario_execution.py](../../scenario_execution.py) | Dated CAD execution and cash checkpoints. |
| [crisis_response.py](../../crisis_response.py) | Combined response, guarded interventions and separate recovery. |
| [investment_triggers.py](../../investment_triggers.py) | Normal-goal triggers and surplus-allocation review. |
| [goal_validation.py](../../goal_validation.py) | Mandatory runtime policy and unsupported-output suppression. |
| [Finance review workbook and evidence](../../finance_qa_export/README.md) | Independent-formula comparisons, actual exports and the unsigned human-review handoff. |
| [Employee website guide](../../WEBSITE.md) | How teammates run customer reviews and inspect the results. |

Savings-policy development under review is documented on
[`feat/inclusive-liquid-savings`](https://github.com/jazzy1818/tangerine_data/tree/feat/inclusive-liquid-savings),
including its [before/after audit](https://github.com/jazzy1818/tangerine_data/blob/feat/inclusive-liquid-savings/reports/savings_access/README.md).
Read that branch's status before treating its changes as part of `main`.

## Source status

This index summarizes existing repository documents and the current implementation.
It introduces no new financial formula, eligibility rule or finance approval.

The additional ChatGPT conversation titled **“clarify JB meaning”** has not been
provided to this repository task. Its contents have not been imported or verified.
Once its export or text is supplied, the team can add the original material with
its source identified and reconcile any differences with these implementation
references.
