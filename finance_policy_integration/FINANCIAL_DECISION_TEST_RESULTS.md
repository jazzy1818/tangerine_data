# Financial decision verification

Python runtime test commit `bb5bf5e2ac1217de071fc8683bebbbda670b7680`. Export and website-render source commit `d2ef37c08a539a3ef9d442bfa52a1fb7bb22dde4`. Both are on `feat/finance-decision-policy`. The latter commit changes the website display and documentation only. Finance approval is **PENDING**.

## Commands

The local runs used the x86 Python 3.13 interpreter with the existing website and pytest dependencies. Run the equivalent commands from the repository root with the project environment active.

```bash
python -B -m pytest -p no:cacheprovider -q
python -B -m pytest -p no:cacheprovider -q tests/test_finance_decision_policy.py tests/test_backup_comparison.py tests/test_review_regressions.py
python -B -m finance_policy_integration.export_cases
node --check web_app/static/reviews.js
node --check web_app/static/scenario.js
git diff --check
```

Exact Python launcher on the review machine for the test commands:

```bash
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/private/tmp/tangerine-website-deps.b15lDv:/private/tmp/tangerine-backup-tests.pA2gbh/pytest313 arch -x86_64 /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -B -m pytest -p no:cacheprovider -q
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/private/tmp/tangerine-website-deps.b15lDv:/private/tmp/tangerine-backup-tests.pA2gbh/pytest313 arch -x86_64 /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -B -m pytest -p no:cacheprovider -q tests/test_finance_decision_policy.py tests/test_backup_comparison.py tests/test_review_regressions.py
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/private/tmp/tangerine-website-deps.b15lDv arch -x86_64 /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -B -m finance_policy_integration.export_cases
```

## Results

- Full Python suite: **534 passed and 9 subtests passed** in 206.96 seconds. No test skips were reported.
- Focused policy, backup-comparison and regression checks: **65 passed**.
- All 112 checkpoints in the independent synthetic finance CSV matched across eight paths, including dated fees and repayments, posted cash, and opening and closing checkpoints.
- All 4,500 account records matched the archived official I/S/F/H/B/P values and an independently calculated combined organizer runway. The new decision plan remains separate from the official metric.
- Offline saved-review API test passed through the actual website server. It verified the applied plan matches the validated ledger and rejected an approval bound to a different account. No live provider call was used.
- Package verification passed for 19 distinct account histories, 30 candidate/decision rows, 532 primary-path checkpoints and 19 text captures from the live website component's renderer. Paired bases match, reviewer fields are blank, and target-only rows contain no calculated action benefit.
- JavaScript syntax and Git whitespace checks passed.

## Worked checks

| Case | Verified result |
| --- | --- |
| A | Month 2 end, CAD 120 at the first shortage and CAD 3,360 over the horizon. Approved included pauses moved the first shortage to Month 3 end, CAD 30, with CAD 1,560 still needed. The additional CAD 260/month was a target. Stopping a proposed contribution released CAD 0. |
| B | CAD 200 short at Month 2 end, before the Month 3 start receipt. Full need remained CAD 600. |
| C | Original need CAD 900. Stipulated deferral moved first shortage to Month 4 start and raised full need to CAD 950. The CAD 650 catch-up includes the CAD 50 premium. The primary path withheld both legs when inclusion or repayment evidence was missing. |
| D | CAD 7,200 target and CAD 4,200 gap at the separate checkpoint. Conditional ETA was 14 months with CAD 300 supported monthly and unknown without a contribution. |
| E | Known-components diagnostic with full need and actionable benefit unestablished. |
| Fee timing | A CAD 50 fee would worsen the earliest shortage from CAD 100 to CAD 150 even while improving horizon need by CAD 250. The candidate was excluded and its trial preserved. |

A live browser walkthrough and live Gemini/Jev calls were outside this offline verification. The UI artifacts are textual captures from the actual renderer. Human review of action suitability, eligibility and prioritization is still required.
