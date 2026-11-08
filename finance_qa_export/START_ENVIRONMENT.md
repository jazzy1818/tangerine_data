Use the existing isolated checkout `/workspace/tangerine_data`; do not create a Git worktree.

Activate with `source /workspace/.venvs/tangerine/bin/activate`, then work from `/workspace/tangerine_data`.
The deterministic finance workflow needs no running services or credentials.
Use local CSVs and existing engine functions. Do not call Gemini, Jev or other providers.
Keep tracked source, tests, requirements and lockfiles unchanged. Do not commit or push.

Validate with `python -m pytest -q tests/test_crisis_execution.py tests/test_runtime_enforcement.py`.
Run `bash run.sh cli --account 22812 --ei 0.55 --bills 0.15` for an offline CLI calculation.
Regenerate the exports with `python finance_qa_export/generate_exports.py`.
Case D uses the recovery change merged into main at `064a1735b3e5cdf25542568953352835964f959d`.
Use `python finance_qa_export/verify_recovery_export.py --prepare` before a fresh
export, then `python finance_qa_export/verify_recovery_export.py` to compare the
standalone Case D calculations. These checks do not replace human finance review.
Recovery regression checks: `python -m pytest -q tests/test_recovery_evidence.py tests/test_crisis_ui.py tests/test_crisis_execution.py tests/test_tailored_advice.py tests/test_runtime_enforcement.py`.

For the complete finance handoff, follow the reproduction commands in
FINANCE_QA_EXPORT_REPORT.md. `check_finance.py --prepare` computes standalone
expectations for the entire finance task before a fresh observed export; the
comparison checks every cash checkpoint, organizer metric/shock, boundary case,
daily replay aggregate and unknown-input guard. Workbook generation requires
openpyxl, included in the local install helper. The current workbook is ready for
comparison to the finance reviewer's original Excel workbook and human sign-off.

The install script reproduces the repository's declared dependency ranges; exact observed
versions are recorded in `installed_dependencies.txt`. The recovery UI was validated
with Streamlit AppTest; external advisor services remain outside this deterministic workflow.

These local instructions are a fallback artifact. The platform draft save returned an error;
neither reusable configuration persistence nor publication has been confirmed.
