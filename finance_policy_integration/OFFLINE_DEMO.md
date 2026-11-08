# Offline finance review walkthrough

Use the existing checkout on `feat/finance-decision-policy`. This is an analyst demonstration using real anonymized histories and hypothetical shocks and approvals. **Finance approval is PENDING.** Nothing executes a bank instruction.

## Prepare

From the repository root:

```bash
source .venv/bin/activate
bash run.sh
```

In the website, choose **Standard rules-based** in Assessment preferences. No Gemini/Jev credentials are needed. With no Gemini key configured, the new description reader also runs offline; a configured key can enable assisted interpretation independently of the classifier preference. Use local HTTP checks for `/api/health` and `/api/accounts?limit=1` when diagnosing startup. Retain one worker for the SQLite workspace.

The exact case inputs are `cases[].request` in `finance_acceptance_details.json`. Matching account IDs are in `finance_acceptance_cases.csv`; they are demonstration inputs, never special cases in the policy. For an API demonstration, submit a selected request to `POST /api/runs` with a fresh UUID `request_id` and `backend: "rules"`, then poll `GET /api/runs/{id}` using the same browser-workspace cookie. Request IDs are idempotent, so reuse must not be confused with a fresh test.

## Show the financial decision

1. **12-compound:** Find the customer in the review sheet. Describe the shock or use **Adjust the shock (optional)** to enter the exact income and bills changes, immediate repair, and hypothetical included-payment schedule from the saved request. Select **Generate main & backup plans**. Above the comparison chart, read the original first shortage, first remaining shortage, and full remaining need separately.
2. Open **Recommended Financial Actions**. Show the modeled pause bundle, dates, fees, **Review by**, and **Trade-offs**. Only existing included payments produce relief; holding a future proposal releases zero. The residual target identifies required funds without inventing a source.
3. Open candidate evidence and the monthly schedule. Trace one pause and its fee to the right checkpoint. Compare both paths using the same opening basis. Monthly projections do not prove daily solvency.
4. **13-late-receipt:** Explain the shortage before the later receipt. A later source does not retroactively cover that checkpoint.
5. **08-deferral:** Explain the separate stipulated deferral comparison, catch-up date and extra cost. The trade-off stays visible on the card; this is not a new approved loan action.
6. **15-unknown:** Show that an unpriced material event leaves full need unestablished. Known components continue as a diagnostic. Missing information is an analyst review item.
7. **20-withheld-identity:** Show the expense posting while the deferral stays blocked for missing inclusion evidence. Supplied `effect-1` cannot borrow confirmation from the anonymous expense. Relief and linked catch-up remain absent.
8. **21-access-review:** Show the Month 2 start access review even though cash stays nonnegative. **MAINTAIN** does not mean ignoring an upcoming hold.

## Hand off for review

Match cases to `rendered_reviews.txt` for exact text from the website renderer, or inspect them in the running website. Text captures include collapsed candidate details; they are not screenshots or evidence of completed human review.

Rebuild without overwriting the signed review sheet:

```bash
python -B -m finance_policy_integration.export_cases --out /tmp/tangerine-finance-review
```

Node renders the existing website component for export; no Node build is required for the website. Check `source_manifest` when reviewing uncommitted changes. Record finance verdicts and notes in the two blank CSV columns and resolve the three questions in `FINANCE_REVIEW_NOTES.md`. Software test results do not constitute finance approval.
