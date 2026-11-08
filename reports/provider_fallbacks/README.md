# Provider fallback evidence — Phase 3

This handoff verifies the existing adapters, accepted financial plan and actual
Streamlit labels offline. All provider responses are mocked at the HTTP/client
boundary. No live request was made. A successful mocked response demonstrates
integration behavior, not provider availability, agreement, or model accuracy.

Start: clean `main` at `48806bd`. Work is on `provider-fallback-evidence`.
Existing fallback/SDK/privacy tests were reused. The additions close the gaps in
inspectable case results, the UI failure matrix, and independent explanation tests.

Result on this branch: **498 tests and 9 subtests passed**, including the 52 new
checks. The export contains **65 verified rows** across classification, classifier
UI, explanation and explanation UI. Export consistency checks confirmed one
effective lead/ledger fingerprint per normalized reference case, unique rows,
matching source hashes and explicit live **Not run** records. `git diff --check`
passed. No live provider availability or model-quality claim follows from this.

## Reproduce

```bash
# Install the repo's declared dependencies in the active virtual environment.
python -m pip install -r requirements.txt -r requirements-classification-dev.txt

# Focused offline evidence (52 tests, 65 recorded result rows).
.venv/bin/python -m pytest tests/test_provider_fallback_evidence.py tests/test_provider_fallback_ui.py -q --provider-evidence-dir=reports/provider_fallbacks

# Full regression suite and the same evidence export.
.venv/bin/python -m pytest tests -q --provider-evidence-dir=reports/provider_fallbacks
```

Tests isolate the project `.env` reference and inherited provider settings without
reading/editing operator credentials. New cases also block unmocked HTTP sends.
The test guard supports both `httpx` and the SDK's `httpx2` transport namespace.

Read [offline_results.csv](offline_results.csv) for one row per case and backend
within each route. [manifest.json](manifest.json) records overall success/failure,
runtime versions, source-file hashes and each live route's **Not run** status.
Case hashes identify the exact canonical normalized input. Ledger hashes include
the no-action path, applied path, goal decision, applied pauses and recovery.
Neither export contains an account ID, exact financial amount, note, transaction,
credential, rejected free text or provider exception body.

`provider_lead_proposal` is the controlled mock's lead when one was supplied.
It stays blank for local runs, missing credentials and unparseable/unavailable
responses. `selected_lead` is the validated adapter result, including local
fallbacks; `effective_lead` is the finance engine's final module or `BANK_REVIEW`.
An `override_reason` is separate from `fallback_reason`: a valid remote proposal
may still fail financial eligibility. `api_calls` counts adapter attempts against
the mocked boundary, including retries; it does not imply a live/billed request.
`parse_outcome` records accepted/rejected validation or that no response could
be parsed. No latency, cost, or live model-quality results are claimed.

## Seven synthetic reference cases

These expectations come from code-reviewed synthetic fixtures and simple cash
equations, not human finance signoff. Each uses the same normalized input across
local rules and the two mocked providers. Mock lead proposals are predetermined;
these rows must not be presented as a head-to-head model comparison.

| Case | Independent check / expected handling |
|---|---|
| Steady | Start 7,200; six 600 surpluses; no shortfall or evidenced crisis action. |
| Income | Start 3,000; monthly deficit 750; first shortfall Month 5, six-month gap 1,500. |
| Compound | Start 3,000 less immediate 1,500; monthly deficit 810 before supported pauses. Six evidenced 300 pauses reduce the gap from 3,360 to 1,560; first shortfall Month 3 after action. |
| Late receipt | Start 1,000; monthly deficit 600; 2,000 arrives in Month 3. First shortfall remains Month 2; the full six-month gap is 600. A surplus proposal is overridden. |
| Payment timing | A seven-day delay identifies timing review, but lacks dated payment events. Monthly cash stays a partial reference; no daily-solvency benefit is invented. Existing daily-replay tests cover identified bill movements separately. |
| Unknown | No magnitude/evidence is supplied. Hold for review; full funding need is not established and a reserve-restoration proposal cannot establish recovery. |
| Recovery | A separate supplied checkpoint establishes cash 3,000, spending 2,400, covered obligations, stable inflows and a supported 300 contribution: reserve gap 4,200 / 300 = 14 months. The historical monthly reference remains partial; the checkpoint is not silently applied to that ledger. |

The fault matrix covers missing credentials, timeouts, provider failure, malformed
output, unsupported modules/reasons, valid structured output and a valid but
financially ineligible proposal. UI tests verify requested/actual labels, fallback
warnings, passive reruns and same-account scenario changes. A full-app test checks
that an accepted provider label survives a financial override while the chart's
cash path stays identical.

Explanation tests supply an accepted plan with an evidenced transfer schedule.
Valid output selects approved fact IDs only. Extra amounts, extra actions,
promises, claims embedded in IDs, malformed responses, timeouts and missing
credentials preserve every accepted local card and the ledger. The actual result
card explicitly labels this as optional emphasis and reports requested and actual
sources separately. Unrelated edits reuse only a matching session result;
changed financial facts revert to local output without another remote call.

## Live smoke tests — Not run

Jev classification, Gemini classification, Gemini explanation and the daily
advisor are **Not run live** for this phase: separate live-test authorization was
not provided. No conclusion about current provider availability follows from
these mocked results. Prior historical verification is not a live observation
of this build.

For the operator's smallest classification smoke test later:

1. Obtain authorization for the named provider and a bounded smoke case. Put the
   corresponding key/model in the approved local `.env` settings; keep credentials
   out of chat, Git, logs and screenshots. `.env` takes precedence over the shell;
   an empty `.env` key disables an inherited key. Use models enabled for the project.
2. Run this single synthetic normalized case once for **one authorized backend**.
   Adapters retain their existing maximum of two attempts; a fallback is not live
   provider success. Do not run a batch comparison until that smoke succeeds.

```bash
# After authorization only: choose jev OR gemini, one invocation per smoke case.
SMOKE_BACKEND=jev .venv/bin/python - <<'PY'
import json
import os
from pathlib import Path
from plan_classification import select_plan
from plan_classification.schemas import ClassificationCase
case = ClassificationCase.model_validate_json(
    Path('reports/provider_fallbacks/smoke_case.json').read_text())
result = select_plan(case, backend=os.environ['SMOKE_BACKEND'])
print(json.dumps({
    'case_hash': result.input_hash, 'requested_backend': result.requested_backend,
    'actual_backend': result.actual_backend, 'fallback_reason': result.fallback_reason,
    'selected_lead': result.selection.lead_module, 'api_calls': result.api_calls,
}))
PY
```

Explanation and daily-advisor testing require separate authorization and their
own explicit buttons described in [the reliability audit](../../PROVIDER_RELIABILITY.md).
A successful classifier smoke does not verify either route. For any later six-to-eight
case comparison, have the finance teammate review expected handling first. Keep
the cash solver and normalized cases identical, record fallback and financial
override separately, and report observed agreement/differences rather than accuracy.
