# Savings access audit

Status: implemented for review; human finance sign-off remains pending.

The five-account result was reproduced across all **4,500** local accounts on the
`feat/flexible-emergency-savings` baseline, commit
`eb45c8dd6dd4ad26be4dca88dcaa17967b002cdd`.

| Measure | Before | After |
|---|---:|---:|
| Conditional fixed-allocation candidates | 5 | 5 |
| Fixed reserve earmarks | 0 | 0 |
| Variable liquid-reserve savings reviews | No pathway | **307 (6.82%)** |
| Verified current set-aside amounts from historical data alone | 0 | 0 |
| Runtime validation failures across the portfolio | 0 | 0 |

The 307 reserve-gap accounts are separate from the five fixed-allocation
candidates, giving **312 accounts (6.93%) with one of these review paths**.
This does not mean 312 customers qualify for an investment or a bank transfer.

## What was too restrictive

G03 requires every observed month to have positive net cash flow before a fixed
debit can be sized. **4,490 accounts** fail that condition; only 10 meet it before
the remaining constraints reduce fixed candidates to five. This is defensible
for a fixed investment debit but too blunt as the only savings-sizing pathway.

There are occasional deficit months for most accounts, even when other months
have a real surplus. The new `investment_triggers.py` calculation evaluates a
variable liquid-reserve opportunity in those positive months, with no payment
in deficit months. It protects cash using recorded daily minima and the existing
operating cushion, accounts for supplied additional commitments, caps at the
reserve gap, requires capacity in at least half the months and the latest month,
and refuses to turn this diagnostic into today's available money or a target date.

Fixed investment rules were not loosened to achieve a target count. Existing
fixed amounts were compared account by account and remain exactly unchanged.
Known adverse debt evidence continues to take priority. Trigger counts overlap;
they are not independent rejection causes and should not be added together.

## Evidence and reproduction

`baseline_evaluation.csv` records the original output for every account.
`account_comparison.csv` records the new output, protected opportunity counts,
reasons for no review, and unchanged fixed amounts. `summary.json` includes source
checksums, aggregate counts and overlapping trigger/goal distributions.

```bash
python -m pip install -r requirements-web-dev.txt
python audit_savings_access.py --baseline reports/savings_access/baseline_evaluation.csv
python -m pytest -q
```

The audit uses local CSVs and deterministic code, not external providers. Accounts
use their latest available 12 calendar months, subject to the six-month minimum;
this is not evidence that the records are current today. The review is in-sample,
not a forecast or out-of-sample success rate. Historical set-asides are capped
independently per month; their sum is not a claim of accumulated new savings.

The existing website one-time savings feature is included from its feature
branch. Its current evidence contract is separate from this historical review.
The commitment-window and reserve-goal-source enhancements identified in the
finance review remain recommendations for that one-time feature; this change
does not claim those fields are newly verified. Final finance approval is pending.
