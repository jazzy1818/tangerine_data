# Financial decision verification

## Continuation verification

Branch `feat/finance-decision-policy`, with a reviewable uncommitted diff based on `372fa21e06327b6855259e5f4485d6213b9de2b1`. Python 3.12.14 and Node v24.22.1 on the cloud machine. The detailed export's `source_manifest` records the actual runtime, renderer, exporter and test hashes; the base commit alone does not identify these edits. **Finance approval is PENDING.**

Commands, from `/workspace/tangerine_data`:

```bash
.venv/bin/python -m pip install -r requirements-classification-dev.txt
.venv/bin/python -m pip check
.venv/bin/python -m pytest -q --junitxml=/tmp/tangerine-policy-followup-full.xml
.venv/bin/python -m pytest -q tests/test_finance_policy_followup.py tests/test_finance_decision_policy.py tests/test_backup_comparison.py tests/test_review_regressions.py
.venv/bin/python -m finance_policy_integration.export_cases --out /tmp/tangerine-policy-followup-final-package
node --check web_app/static/reviews.js
node --check web_app/static/scenario.js
git diff --check
```

- Full suite: **545 passed and 9 subtests passed** in 152.74 seconds. **0 failures, 0 errors, 0 skips.** JUnit records 554 outcomes including subtests and 545 test cases.
- Focused finance/comparison/regression suite: **76 passed** in 15.88 seconds. The 11 new cases also passed independently.
- New regressions cover generated/supplied event-ID collisions, withheld and posted deferral evidence, unpriced-event prompt binding, pending deferral identity, an upcoming hold without a shortage, supplied-approval review flags, escaped website trade-offs, per-action review dates, deferral costs and the Streamlit cards.
- Regenerated package: **21 distinct account histories, 33 decision rows, 588 paired start/end checkpoints and 21 exact website-renderer text captures**. All runtime validations passed; full targets remain null for incomplete projections, target-only action impacts remain null, and reviewer verdict/note columns remain blank.
- The original 19 cases have **identical no-action and supported-action ledgers** to the committed package. The two added cases expose blocked deferral identity binding and a Month 2 access-review deadline.
- Source hashes in the exported manifest matched the actual working-tree files. No credentials or raw bank CSVs are included in that manifest.
- The development requirements now declare `httpx` for the existing FastAPI TestClient checks. It was installed for the passing suite; recording it prevents those API tests from silently skipping on fresh setup. Dependency consistency checks passed.
- JavaScript syntax checks passed. The 112 independent synthetic checkpoint anchors and all 4,500 prescribed organizer-metric checks ran within the full suite.
- HTTP smoke checks against the restarted website passed for `12-compound`, `20-withheld-identity` and `21-access-review`. Each fresh saved review completed, matched its exported supported ledger and recorded zero remote provider calls. Health and the updated `/assets/reviews.js` also passed.

Exact UI text captures are from the actual website component, including collapsed evidence. They are not screenshots or human finance acceptance. Live Gemini/Jev calls, real bank authorization, product suitability and a human browser walkthrough remain outside this offline verification. The three unresolved policy questions are in `FINANCE_REVIEW_NOTES.md`.

## Prior committed verification

The record below belongs to Python runtime test commit `bb5bf5e2ac1217de071fc8683bebbbda670b7680` and export/render source commit `d2ef37c08a539a3ef9d442bfa52a1fb7bb22dde4`. Both are on `feat/finance-decision-policy`; the latter changes display and documentation only. It is retained as historical evidence, not substituted for the continuation results above.

### Commands

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

### Results

- Full Python suite: **534 passed and 9 subtests passed** in 206.96 seconds. No test skips were reported.
- Focused policy, backup-comparison and regression checks: **65 passed**.
- All 112 checkpoints in the independent synthetic finance CSV matched across eight paths, including dated fees and repayments, posted cash, and opening and closing checkpoints.
- All 4,500 account records matched the archived official I/S/F/H/B/P values and an independently calculated combined organizer runway. The new decision plan remains separate from the official metric.
- Offline saved-review API test passed through the actual website server. It verified the applied plan matches the validated ledger and rejected an approval bound to a different account. No live provider call was used.
- Package verification passed for 19 distinct account histories, 30 candidate/decision rows, 532 primary-path checkpoints and 19 text captures from the live website component's renderer. Paired bases match, reviewer fields are blank, and target-only rows contain no calculated action benefit.
- JavaScript syntax and Git whitespace checks passed.

### Worked checks

| Case | Verified result |
| --- | --- |
| A | Month 2 end, CAD 120 at the first shortage and CAD 3,360 over the horizon. Approved included pauses moved the first shortage to Month 3 end, CAD 30, with CAD 1,560 still needed. The additional CAD 260/month was a target. Stopping a proposed contribution released CAD 0. |
| B | CAD 200 short at Month 2 end, before the Month 3 start receipt. Full need remained CAD 600. |
| C | Original need CAD 900. Stipulated deferral moved first shortage to Month 4 start and raised full need to CAD 950. The CAD 650 catch-up includes the CAD 50 premium. The primary path withheld both legs when inclusion or repayment evidence was missing. |
| D | CAD 7,200 target and CAD 4,200 gap at the separate checkpoint. Conditional ETA was 14 months with CAD 300 supported monthly and unknown without a contribution. |
| E | Known-components diagnostic with full need and actionable benefit unestablished. |
| Fee timing | A CAD 50 fee would worsen the earliest shortage from CAD 100 to CAD 150 even while improving horizon need by CAD 250. The candidate was excluded and its trial preserved. |

A live browser walkthrough and live Gemini/Jev calls were outside this offline verification. The UI artifacts are textual captures from the actual renderer. Human review of action suitability, eligibility and prioritization is still required.
