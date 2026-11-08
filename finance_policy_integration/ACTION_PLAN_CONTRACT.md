# Finance action plan v1.1

`plans.crisis_plan.finance_plan` is a local decision record built after the dated scenario and crisis lifecycle validators pass. Website saved reviews and structured CLI output include it. The website and Streamlit render its prioritized actions above their cash charts. Existing saved website reviews without the field still render. The organizer runway remains a separate result.

## Plan fields

| Field | Meaning |
| --- | --- |
| `policy_version`, `finance_approval`, `source_commit` | Schema/policy version, pending human approval, and the Git commit running the plan. A deployment without Git can supply `TANGERINE_SOURCE_COMMIT`. A missing commit is null. |
| `account_id`, `scenario_hash`, `horizon_months`, `opening_cash_basis` | Local identity, selected scenario fingerprint, modeled months, and historical proxy or supplied scenario cash. A supplied amount does not establish live availability. |
| `financial_diagnosis` | Original scenario, historical baseline and window, event-level evidence, first month's recurring gap when complete, known dated flows, first negative checkpoint and shortage amount, lowest cash checkpoint, and full versus known-components funding. |
| `lead_module`, `support_modules`, `module_rationale` | Finance-eligible response labels and why they apply. The upstream classifier supplies module proposals. |
| `prioritized_actions`, `candidate_action_decisions` | Up to three principal items plus all evaluated pause candidates, replayed deferral comparisons, and applicable review and target items. |
| `no_action`, `supported_action`, `comparison` | Original validated shock-only and applied paths, including every start/end checkpoint, the monthly ledger, and their paired summary. They share the same scenario, opening amount, basis and horizon. |
| `remaining_gap_cad`, `required_target_only` | Full residual when complete. When needed, the target separates upfront cash and a uniform month-end improvement from Month 1. The target cannot itself affect either ledger. |
| `conditional_assumption_path`, `recovery_checkpoint` | Independent references. Assumptions are replayed separately with incomplete status. Recovery uses a separately supplied snapshot and can report a conditional ETA. Daily timing has a separate basis and its own metrics on the candidate and existing timing comparison. |
| `normal_goal_impact`, `post_horizon_obligations` | Normal goal, revised amount, zero relief from pausing a proposal, and the unpaid dated liabilities beyond the chart. The applied legacy plan can include an affordable proposed contribution as an outflow in the modeled comparison. It is identified as a proposal in the ledger. |
| `bank_review_flags`, `next_review_checkpoint`, `model_limitations` | Missing terms, earliest decision checkpoint or separate recovery month, and model limits. A complete historical proxy ledger can coexist with `REVIEW_REQUIRED` when evidence is too stale for a current decision. |

The complete horizon need is `max(0, -minimum_accessible_cash)`. A point with exactly zero is covered at that checkpoint. `comparison.funding_improvement_cad` is before minus after, with positive values improving funding. A null value leaves the full impact unestablished. The known-components fields are separate. Source account inflows are historical and may include transfers. Currency fields are CAD.

## Action fields and statuses

Every action carries a stable `action_id`, parent `scenario_hash`, module IDs, instruction, reason, policy clause, status, disposition, and evidence codes. When applicable it also carries dates, amount and frequency, fee, catch-up terms, affected event IDs, earliest review checkpoint, matched impact, and downsides. `not_executed` is always true. The event-level audit retains approval and baseline inclusion details and candidate trial results.

| Status | Treatment |
| --- | --- |
| `SUPPORTED_MODELED` | An eligible included transfer is paused in the model using supplied dates, fee and authorization. The synthetic approvals in the handoff remain hypothetical. |
| `CONDITIONAL_ONLY` | A separate scenario, daily replay, stipulated loan deferral comparison, or analyst review. It credits no additional benefit to the supported path. |
| `TARGET_ONLY` | Calculated required cash or an identified recurring deficit. Impact is null and funding remains unresolved until a source is supplied and replayed. |
| `BLOCKED_OR_UNKNOWN` | Evidence, feasibility, timing or purpose fails a gate. The decision explains what was withheld and why. |
| `MAINTAIN` | Existing circumstances support monitoring rather than a new action. |

Observed records and derived calculations are distinguished from judge-supplied terms, supplied confirmations, assumptions and unknowns. For the demo, `BANK_CONFIRMED` means a confirmation supplied for the scenario. It is not an independent assertion that a bank performed an action. Transfer approvals are treated as supplied scenario terms and require a bank-side check before acting.

### Candidate selection and timing

For pauses, the existing selector evaluates fee, month and ID order. Eligible candidates get a standalone trial and a cumulative trial, and the existing full eligible-schedule comparison is still available. The final supported bundle is revalidated on the original ledger. A pause that advances or deepens the first shortage, increases the funding need, lacks purpose, or breaches payment evidence is withheld. An action that improves later cash may leave the earlier shortage intact. The principal actions call this out by comparing cash at the original shortage and putting an unresolved earlier need first.

A stipulated loan deferral is part of the original shock. Its separate counterfactual removes only that deferral while keeping the other scenario inputs and opening basis. This comparison explains a costed emergency bridge and never inserts a new loan decision into the supported bundle. When the deferral terms are missing, the primary ledger withholds both the reduction and repayment. A known catch-up beyond the horizon remains visible.

### Example

Synthetic Case A books six included, approved payments of CAD 300 with zero fee. The supported bundle moves the first shortage from Month 2 end to Month 3 end and reduces full need from CAD 3,360 to CAD 1,560. The remaining CAD 260 per month from Month 1 is `TARGET_ONLY`. Separately, a future contribution proposal outside spending frees CAD 0.

Synthetic Case C delays the first shortage from Month 2 end to Month 4 start while increasing full funding need from CAD 900 to CAD 950. The extra CAD 50 is part of the CAD 650 catch-up, not a separately charged fee. It is shown as a conditional bridge trade-off.
