# Finance verification handoff

Open **FINANCE_REVIEW_WORKBOOK.xlsx** for Inputs, Expected, Observed, Findings,
the requirements checklist and the unsigned human-review page. The detailed
scope and audited commit are in **FINANCE_QA_EXPORT_REPORT.md**.

The automated arithmetic checks are retrospective and do not replace the
finance teammate's original independent Excel workbook. Status remains
**Pending human finance review** until that teammate signs off.

The CSV and JSON files preserve numerical precision and the actual engine
warnings. Empty values mean unknown or not applicable. The independent daily
replay evidence contains the eligibility and outcome for each account in the
cohort. Approval and zero-fee bill-shift assumptions are conditional.

To reproduce the audit from the repository root:

```bash
bash finance_qa_export/install_environment.sh
source /workspace/.venvs/tangerine/bin/activate
python finance_qa_export/check_finance.py --prepare
python finance_qa_export/verify_recovery_export.py --prepare
python finance_qa_export/generate_exports.py
python finance_qa_export/check_finance.py
python finance_qa_export/verify_recovery_export.py
```

Run `python -m pytest -q` and preserve its exit status and result log when
validating a new application revision. Then run:

```bash
python finance_qa_export/build_review_handoff.py --test-log /path/to/test.log --tested-commit <tested-SHA>
```

The builder verifies that tracked application files outside this audit folder
match the tested commit. Regeneration intentionally updates the audit snapshot;
review and commit those changes separately. No helper calls an external model
or executes a banking action.
