# Finance review handoff

**Finance approval is pending.** The scenario approvals in this package are hypothetical. Please review the ordering and evidence for each recommendation before signing off.

1. Open `finance_acceptance_cases.csv` and enter a verdict and notes in the two blank reviewer columns.
2. Match the case ID to `rendered_reviews.txt` for the actual website rendering and `finance_acceptance_details.json` for the request, source commit, evidence and checkpoint ledgers.
3. Compare the first shortage and its phase, the amount needed at that point, and the largest shortage over the full horizon. For a paid/paused item, trace its amount and fee to the ledger on the correct date. For blocked or conditional items, check that the same event did not book relief in the supported path.
4. For Case A, verify the CAD 3,360 / CAD 1,560 comparison and separate CAD 260 target. For Case C, verify whether the timing/cost trade-off is explained clearly enough to support a discussion. For missing amounts, check that the model separates known cash from the unestablished full requirement.

## Three decisions for finance

1. **Costed bridges.** Is delaying an imminent shortage worth an explicitly quantified increase in later funding need? What maximum cost, approval and repayment protection should permit proposing the bridge?
2. **Approval and protected payments.** What proof is sufficient for an included outflow, effective date, fees and approval? Can the team define the actual schedule and treatment for a permitted instalment or bill-date move before those become executable candidates?
3. **Reserve and savings policy.** Does the three-month illustrative target remain appropriate for the demo, and what evidence and review window should allow flexible set-asides after obligations and the cash cushion are protected?

## Sampling and known limits

The exporter chooses distinct account histories by sorted account ID within each cohort, with an explicit shortest-recent-history selection. It does not choose based on favorable post-action results. Published account features are used only to choose the sample. The engine loads the original monthly summary, loan and access tables for the calculations. The 21 examples use hypothetical shocks, balances, approvals and recovery facts where supplied. They cover stable surplus, structural deficits, thin and negative balances, zero typical inflow/spending/bills, active loans, shared access, no recent history, income reduction, repair, compound shocks, late receipts, deferral, holds, missing inputs, recovery and windfall. No account has exactly zero historical B in this snapshot. A separate case supplies a hypothetical opening cash of zero while preserving the original B. No account has fewer than six total monthly rows. The real short-history example has no observations in the latest reference window.

The continuation adds `20-withheld-identity`: an anonymous expense and a separately identified deferral whose baseline inclusion is unconfirmed. The expense posts, but neither loan relief nor catch-up posts, and the deferral remains blocked. `21-access-review` shows an upcoming Month 2 hold with nonnegative modeled cash; it still requires an access review at Month 2 start. The original 19 no-action and supported-action ledgers remain identical to the prior package. There are now 33 decision rows, 588 paired checkpoints and 21 text captures.

The handoff keeps the standalone and cumulative pause trials rather than searching every possible subset. It retains conditional or manual review for standalone loan renegotiation, arbitrary instalments and verified bill-date execution. Generic asset returns and product suitability do not create accessible cash. The conditional daily bill replay is a separately based historical comparison. A historical snapshot can demonstrate the plan and its limits but cannot establish current authorizations or eligibility.

The previously reproduced baseline audit found 5 of 4,500 accounts with a positive fixed long-term amount and zero with a positive fixed reserve earmark. Of the 4,495 without a fixed amount, 4,490 had a recent month where spending exceeded inflows. The flexible-savings review remains evidence-gated and separate. The figures describe this dataset and policy, not the number of people who could save.

## Reproduce and demo offline

1. Activate the project's Python environment and start the website with `bash run.sh`. Choose **Standard rules-based** under Preferences. The finance export uses the local rules directly.
2. Select the account shown for **12-compound** in the review sheet. Enter its structured effects and supplied schedule from the JSON. Prepare the review and open **Recommended Financial Actions**.
3. Read the first shortage, explain why the recorded transfers count as modeled relief, then point to the residual and compare both cash paths. Open candidate evidence and the detailed ledger.
4. Use **13-late-receipt** to show a receipt after the first shortage. Use **15-unknown** to show that an unpriced event keeps full funding open.
5. Rebuild the handoff at the code commit with `python -B -m finance_policy_integration.export_cases --out /tmp/tangerine-finance-review`. Node is used only to render text from the existing review component. The website itself uses its normal launcher.

See [OFFLINE_DEMO.md](OFFLINE_DEMO.md) for the walkthrough and exact saved requests. The verbatim supplied policy is [FINANCIAL_DECISION_POLICY_v1_1.md](FINANCIAL_DECISION_POLICY_v1_1.md). The current combined code commit is `4950dc2`, merging main `b65be04` into this feature branch after preserving the evidence follow-up in `d1788af`. The detailed export's source manifest identifies the actual code hashes. [MAIN_SYNC.md](MAIN_SYNC.md) records the merge and 570-test validation. No changes have been pushed or merged into main, and the blank reviewer verdicts do not constitute sign-off.
