# Finance review handoff — pending human finance review

The automated financial checks target commit `d920e5b2e41e8b7ab79ece69cd75a796f8e4e8f4` (branch `chore/finance-verification-handoff`).
1,157 field comparisons produced **zero numerical mismatches**.
The full repository suite result is **423 passed, 9 subtests passed in 204.85s (0:03:24)** on `d920e5b2e41e8b7ab79ece69cd75a796f8e4e8f4`.
All tracked files outside the audit folder match that tested application revision;
see test_results.log and test_evidence.json. Audit artifacts are verified separately.
No application code was changed for this audit. No external model/provider was called.
These files form a versioned audit handoff. Repository publication is separate
from the human finance approval below.

## What remains

**Human finance review is pending.** The original independent Excel workbook was
not supplied and has not been compared or signed. Review FINANCE_REVIEW_WORKBOOK.xlsx,
then fill in HUMAN_FINANCE_REVIEW.md (name, date, commit, reviewed cases, exceptions).
The PDF assigns this to the Finance teammate in Phase 1, point 8, page 4. The package
is ready for that teammate's handoff to the release owner. No signature is implied.

The expectations here were computed without application imports, using raw CSVs
and standalone Decimal arithmetic. They were frozen before the fresh observed export.
This is a **retrospective check**: earlier engine outputs had already been seen.
It cannot replace the finance reviewer's original independently prepared workbook.

## Scope and evidence

- Inputs, Expected, Observed and Findings tables are in the workbook and CSVs.
- All 112 cash checkpoints match to posted CAD cents, with first-shortfall month
  and phase and the full six-month minimum checked. Recovery has no cash-checkpoint
  API; its target/gap/ETA is compared directly, without invented ledger rows.
- Organizer metrics I/S/H/F/B/P were independently calculated for 22812 and 20111.
  Both B windows are July–December 2025. F is the median of monthly component sums;
  P uses the end-2025 C/D active-loan snapshot and is not added to S a second time.
- All six organizer shocks match. Raw float comparisons allow at most 1e-9 CAD
  for binary representation; exported raw numbers are unchanged. Final runway is
  compared at one decimal. Seven extra boundary checks cover zero/negative buffer,
  no gap, negative gap, the 120-month cap and fractional runway.
- Case A: no action and pausing a proposal each need $3,360; approved included
  outflow pause needs $1,560. First shortage is Month 2 End / Month 3 End respectively.
  The six-month all-approved `supported_pause` comparison is the requested path;
  the application's separate selective `applied_plan` is preserved in raw JSON.
- Case B: first shortage $200 at Month 2 End, before the Month 3 Start receipt;
  $200 needed before the receipt, $600 needed across six months.
- Case C: original path needs $900, first shortage Month 2 End; approved deferral
  needs $950, first shortage $350 at Month 4 Start. The $650 repayment is now
  separately exported in repayments, so fees/costs cannot double-count it.
  Without inclusion evidence, both deferral legs are blocked and full funding stays unknown.
- Case D: target $7,200, gap $4,200, conditional ETA 14 months at supported $300/month;
  unknown contribution gives no ETA. Stability/covered obligations come from PDF
  page 3, not invented income. Assessment month 2026-11 is a synthetic run label.
- Case E is now synthetic as required by the PDF (the earlier export's real-account
  harness is superseded). It explicitly reuses A's baseline. Value/timing/duration
  questions, REVIEW_REQUIRED goal status, unknown G25 and null full funding are checked.
  Its numerical cash gaps are known components only, not zero actual income.
- Daily replay was recomputed both by the application and an independent standard-
  library implementation over the raw CSVs: 4,424 eligible, 143 hidden shortages,
  102 qualifying bill shifts, 44 eliminated. Denominator is **102**, hence 43.1%.
  The independent account-level evidence is in daily_independent_account_evidence.csv.
  Seven-day moves remain within the month with zero month-end balance change.
  Approval and zero fees are conditional assumptions; end-of-day replay does not
  establish intraday solvency. Its pre-July opening proxy differs from official B.

## Reproduce

From `/workspace/tangerine_data`, using the prepared virtual environment:

```bash
/workspace/.venvs/tangerine/bin/python finance_qa_export/check_finance.py --prepare
/workspace/.venvs/tangerine/bin/python finance_qa_export/verify_recovery_export.py --prepare
/workspace/.venvs/tangerine/bin/python finance_qa_export/generate_exports.py
/workspace/.venvs/tangerine/bin/python finance_qa_export/check_finance.py
/workspace/.venvs/tangerine/bin/python finance_qa_export/verify_recovery_export.py
/workspace/.venvs/tangerine/bin/python finance_qa_export/build_review_handoff.py
```

`check_finance.py` has no engine imports. `generate_exports.py` is the Observed
side and uses the actual application functions with local data. Workbook generation
uses openpyxl (installed locally without changing repository requirements).
For a new application revision, run the full suite and provide its result log and
commit to the builder with `--test-log <path> --tested-commit <SHA>`. Without those
arguments it reuses the retained evidence only if the application revision matches.
The retained full-suite command was:

```bash
/workspace/.venvs/tangerine/bin/python -m pytest -q
```

All raw input/source checksums are recorded in source_sha256.json. Archive checksums
for the delivered files are in artifact_sha256.json. Empty cells indicate unknown
or not applicable values; unknown full funding/ETAs are never replaced by zero.
For the unknown recovery contribution, the engine's zero applied rate represents
no supported allocation, not knowledge of an actual zero contribution.

The earlier cloud configuration-save error remains an unrelated onboarding issue;
it does not block these financial results. No publication is claimed.
