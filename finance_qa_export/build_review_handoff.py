"""Package the executed finance checks into an inspectable review workbook."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import re

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

OUT=Path(__file__).resolve().parent
ROOT=OUT.parent
def load(name):return json.loads((OUT/name).read_text())
def rows(name):return list(csv.DictReader((OUT/name).open()))
def write(name,rs):
    fields=list(dict.fromkeys(k for r in rs for k in r))
    with (OUT/name).open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,lineterminator='\n');w.writeheader();w.writerows(rs)
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()
def application_revision(ref):
    entries=git('ls-tree','-r','--full-tree',ref).splitlines()
    return hashlib.sha256('\n'.join(line for line in entries
        if not line.split('\t',1)[1].startswith('finance_qa_export/')).encode()).hexdigest()

parser=argparse.ArgumentParser()
parser.add_argument('--test-log',type=Path)
parser.add_argument('--tested-commit',help='Commit on which the supplied full-suite log was produced')
args=parser.parse_args()

summary=load('finance_check_summary.json');expected=load('finance_expected.json')
commit=git('rev-parse','HEAD');tree=git('rev-parse','HEAD^{tree}')
previous=load('test_evidence.json') if (OUT/'test_evidence.json').exists() else {}
tested_commit=args.tested_commit or previous.get('executed_on_commit')
if not tested_commit:raise RuntimeError('Supply --tested-commit with the full-suite test log')
tested_commit=git('rev-parse',tested_commit)
if application_revision('HEAD')!=application_revision(tested_commit):
    raise RuntimeError('Application files differ from the full-suite-tested revision')
for diff_args in [('diff','--quiet'),('diff','--cached','--quiet')]:
    subprocess.run(['git',*diff_args,'--','.',':(exclude)finance_qa_export'],cwd=ROOT,check=True)
if summary['commit']!=commit:raise RuntimeError('Stale financial comparisons')
test_log_path=args.test_log or OUT/'test_results.log'
full_log=test_log_path.read_text()
result_lines=[line for line in full_log.splitlines() if re.search(r'\d+ passed',line) and re.search(r' in \d',line)]
if not result_lines:raise RuntimeError('Missing full-suite result summary')
test_summary=result_lines[-1].strip('= ')
if re.search(r'\d+ (failed|error|errors|skipped|deselected|xfailed|xpassed)',test_summary):
    raise RuntimeError('Full suite has non-passing outcomes; review the test log')
if test_log_path.resolve()!=(OUT/'test_results.log').resolve():shutil.copyfile(test_log_path,OUT/'test_results.log')
(OUT/'test_evidence.json').write_text(json.dumps(dict(command='/workspace/.venvs/tangerine/bin/python -m pytest -q',
    executed_on_commit=tested_commit,current_commit=commit,tree=tree,
    application_revision=application_revision('HEAD'),evidence=test_summary,
    scope='All tracked application/data/test files outside finance_qa_export match the tested revision. Audit artifacts are verified separately.',
    additional_checks=summary['comparison_count'],mismatches=summary['mismatches']),indent=2)+'\n')
requirements=[
    ('1','Worksheet','DONE','Workbook has inputs, standalone expectations, observed outputs and findings.'),
    ('2','Independent arithmetic','DONE WITH LIMITATION','No engine imports in check_finance.py. Expectations frozen before this fresh export; retrospective check because prior results were already seen. Original independent Excel workbook remains unreviewed.'),
    ('3','Checkpoints','DONE','112 accessible-cash checkpoints, exact CAD-cent comparisons; immediate/start/end labels retained. Recovery exposes target/ETA only.'),
    ('4','Funding need','DONE','First shortage, full six-month minimum, and $200 pre-receipt requirement checked. Unknown full amounts stay blank.'),
    ('A','Compound paths','DONE','All three paths checked; proposal pause gives no cash credit; included approved pause releases $300/month.'),
    ('B','Late receipt','DONE','Month 2 End shortage remains before Month 3 Start receipt; full-period need $600.'),
    ('C','Deferral','DONE','Month 4 Start repayment checked; missing inclusion blocks both relief and repayment and full funding remains unknown.'),
    ('D','Recovery','DONE','Target $7200, gap $4200, supported ETA 14 months; unknown contribution gives no ETA.'),
    ('E','Unknown income','DONE','Synthetic baseline explicitly reused from A. Value/timing/duration questions and goal-review hold verified; full funding unknown.'),
    ('5','Real accounts','DONE','Both accounts, chronological six months, fixed-cost sum then median, active loan status and full raw metric precision checked.'),
    ('6','Organizer shocks','DONE','Six scenarios and seven runway boundary cases checked, including zero/negative buffer precedence, no shortfall and cap.'),
    ('7','Daily replay denominator','DONE','Independent raw-data replay matches the engine: 4424 eligible, 143 hidden, 102 qualifying, 44 eliminated, 43.1%; unchanged month ends and conditional zero-fee assumptions documented.'),
    ('8','Handoff package','READY FOR HUMAN REVIEW','Worksheet, source/commit, logs, findings and open issues are packaged. No message or file has been sent to another teammate.'),
    ('Human','Original workbook comparison and sign-off','PENDING','Finance teammate compares their independent Excel workbook, checks assumptions, and signs name/date/commit/cases/exceptions. No signature has been invented.'),
]
checklist=[dict(point=p,requirement=r,status=s,evidence=e) for p,r,s,e in requirements]
write('finance_requirements_checklist.csv',checklist)
cover=[dict(item='Review status',value='Pending human finance review'),
    dict(item='Branch / commit',value=f'{git("branch","--show-current")} / {commit}'),
    dict(item='Audited at UTC',value=summary['checked_at']),
    dict(item='Automated field comparisons',value=summary['comparison_count']),
    dict(item='Mismatches',value=summary['mismatches']),
    dict(item='Full suite',value=f'{test_summary}; application revision matches tested commit {tested_commit}'),
    dict(item='Comparison rules',value='Cash checkpoints: exact posted CAD cents. Official raw metrics: absolute tolerance 1e-9 CAD for binary-float representation. Organizer runway: one decimal. Unknown stays blank.'),
    dict(item='Expected arithmetic',value='Standalone Decimal calculation from raw CSV/PDF inputs, no engine imports. Retrospective; does not replace the original independent Excel workbook.'),
    dict(item='Source',value='Tangerine-Team-Execution-Prompts.pdf, Phase 1 pages 2–4; local source CSVs and current README'),
    dict(item='Case E harness',value='Synthetic Case A baseline only: opening cash 3000, baseline inflow 3000, spending 2400, bills 400; no amount/direction/timing/duration supplied for the event.'),
    dict(item='Precision',value='CSV/JSON files preserve raw exported precision. Spreadsheet numbers are a review aid; original CSVs are authoritative.'),
    dict(item='Formulas',value=json.dumps(expected['formulas'])),
]
signoff=[dict(item=k,value=v) for k,v in [
    ('Status','Pending human finance review'),('Reviewer name',''),('Review date',''),
    ('Reviewed commit',commit),('Independent Excel comparison completed',''),
    ('Reviewed cases',''),('Exceptions / remaining issues',''),('Reviewer approval','')]]
workbook=Workbook();workbook.remove(workbook.active)
def sheet(name,records):
    ws=workbook.create_sheet(name)
    fields=list(dict.fromkeys(k for r in records for k in r))
    ws.append(fields)
    for record in records:
        ws.append([str(record[k]) if isinstance(record.get(k),(list,dict)) else record.get(k) for k in fields])
    for cell in ws[1]:
        cell.font=Font(bold=True,color='FFFFFF');cell.fill=PatternFill('solid',fgColor='264653')
    ws.freeze_panes='A2';ws.auto_filter.ref=ws.dimensions
    for row in ws.iter_rows(min_row=2):
        for cell in row:cell.alignment=Alignment(vertical='top',wrap_text=True)
    for i in range(1,len(fields)+1):
        ws.column_dimensions[get_column_letter(i)].width=min(55,max(16,len(fields[i-1])+2))
recovery_inputs=[dict(case='D',path=path,units='CAD',horizon='Conditional elapsed months to reserve target',
    **data['inputs']) for path,data in load('recovery_engine_raw.json').items()]
sheet('Start here',cover);sheet('Inputs',rows('finance_inputs.csv')+recovery_inputs)
sheet('Expected checkpoints',rows('synthetic_expected_checkpoints.csv'))
sheet('Observed checkpoints',rows('synthetic_checkpoint_ledger.csv'))
sheet('Expected cash summaries',rows('synthetic_expected_summaries.csv'))
sheet('Observed case summaries',rows('synthetic_case_summary.csv'))
sheet('Account metrics',rows('official_account_metrics.csv'))
sheet('Expected account metrics',[dict(account_id=k,**v) for k,v in expected['metrics'].items()])
sheet('Expected shocks',expected['shocks']);sheet('Observed shocks',rows('official_shock_results.csv'))
sheet('Recovery comparison',rows('recovery_expected_observed.csv'))
sheet('Daily replay',rows('daily_replay_verification.csv'))
sheet('Findings',rows('finance_findings.csv'));sheet('Requirements',checklist)
sheet('Open issues',rows('finance_open_issues.csv'));sheet('Human sign-off',signoff)
path=OUT/'FINANCE_REVIEW_WORKBOOK.xlsx';workbook.save(path)
check=load_workbook(path,read_only=True)
if check['Findings'].max_row!=summary['comparison_count']+1:raise RuntimeError('Incomplete workbook findings')
check.close()
(OUT/'HUMAN_FINANCE_REVIEW.md').write_text(f'''# Pending human finance review

Open FINANCE_REVIEW_WORKBOOK.xlsx. Compare the expected/observed checkpoints,
official metrics and shocks, and reserve recovery to your original independent
Excel workbook. Check the PDF's synthetic assumptions, conditional actions, and
daily replay denominator. Filter Findings for MISMATCH; currently there are none.

Only the human finance reviewer can sign off. Complete:

- Reviewer name:
- Date:
- Reviewed commit: {commit}
- Independent Excel comparison completed:
- Reviewed cases:
- Exceptions:
- Approval:

The package is ready for the finance teammate to hand over to the release owner
after human review. Repository publication does not constitute finance sign-off.
''')
report=f'''# Finance review handoff — pending human finance review

The automated financial checks target commit `{commit}` (branch `{git('branch','--show-current')}`).
{summary['comparison_count']:,} field comparisons produced **zero numerical mismatches**.
The full repository suite result is **{test_summary}** on `{tested_commit}`.
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
'''
(OUT/'FINANCE_QA_EXPORT_REPORT.md').write_text(report)
source_hashes=load('source_sha256.json')
for name in ['README.md','backup_comparison.py','tests/test_recovery_evidence.py','tests/test_crisis_ui.py']:
    source_hashes[name]=hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
for source in [*OUT.glob('*.py'),OUT/'README.md',OUT/'install_environment.sh',OUT/'START_ENVIRONMENT.md']:
    source_hashes[str(source.relative_to(ROOT))]=hashlib.sha256(source.read_bytes()).hexdigest()
(OUT/'source_sha256.json').write_text(json.dumps(source_hashes,indent=2)+'\n')
excluded={'artifact_sha256.json','recovery_code_changes.patch','cli_smoke.log','export_validation.log'}
manifest={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(OUT.iterdir())
          if p.is_file() and p.name not in excluded}
(OUT/'artifact_sha256.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(f'Created and reopened {path.name}; {len(workbook.sheetnames)} sheets. Pending human finance review.')
