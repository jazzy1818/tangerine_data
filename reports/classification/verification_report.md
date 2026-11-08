# Classification verification — 2026-11-08

The original request was rechecked against README.md, both team plans, the eight-module taxonomy,
the actual CSVs, current provider contracts, and the existing app. The implementation remains
limited to data discovery, feature engineering, scenario inputs, and plan-module classification.
Model quality comparison and action/financial-plan execution remain outside this work.

## Defects corrected during the audit

| Finding | Correction and regression coverage |
|---|---|
| Future household percentage shocks could yield identical classifier inputs despite different underlying bill amounts | Added signed normalized cash-flow deltas to each quantifiable effect, retaining start/duration; paired-profile regression proves the cases differ |
| Identical one-off expenses were accepted twice when evidence labels differed | Duplicate financial identity ignores provenance; a duplicate CAD 3000 charge is rejected |
| Unspecified duration was conflated with ongoing effects | Added explicit `ongoing`; unknown recurring duration retains a clarification question; conflicting duration/ongoing inputs are rejected |
| Malformed provider model metadata could crash fallback | Metadata is validated before assignment; invalid responses use an explicit local fallback |
| Retry usage omitted earlier billed responses and missing metrics appeared as zero | Sum known usage across attempts; preserve nulls; record completeness and separate Gemini visible/thought/total tokens |
| Gemini's SDK OpenAPI schema path emitted unsupported `additional_properties` | Use `response_json_schema`; inspect the real SDK's serialized HTTP body in regression tests |
| Large array bounds caused a live Gemini HTTP 400 schema-complexity failure | Keep a compact API schema and enforce array/string limits locally; both a minimal schema probe and the full classifier now pass live |
| The old Gemini default is restricted for new projects | Use configurable `gemini-3.5-flash-lite` for this classifier; preserve the original advisor's configuration |
| Unusual scenarios required hand-written JSON | Added a guided editor covering all 13 effect types, combined effects, dates/durations, evidence, unknowns, and recovery/no-shock states |
| Invalid guided phase changes could throw an exception | Show an editable validation error and retain remove controls |
| Negative-day checks accepted impossible calendar counts | Validate against the actual month, including leap-year February |
| Engine adapter could mix supplied baselines with unrelated derived ratios | Validate raw baseline consistency and active loan values |
| Discovery assumed optional columns and nonzero total spending | Explicit valid-data denominators, null undefined cash share, and clearing of stale matched-account exports |

## Automated and data verification

Command: `/tmp/tangerine-classification-venv/bin/python -m pytest tests -q`

Result: **159 passed in 18.59 seconds**. Automated tests are offline and mock external services.
They include independent baseline formula checks for all 4,500 accounts, provider failure paths,
privacy boundaries, the actual Google SDK wire serialization, local output constraints, guided
editor state changes, and a full `app.py` render/classification with mocked market feeds.
Compilation and `git diff --check` also passed.

`python -m plan_classification discover` regenerated the reports. An independent CSV calculation
confirmed the same findings:

- 714 / 3,309 positive-typical-surplus accounts have under six months of runway at 55% inflow.
- 2,952 / 3,264 eligible positive-surplus accounts have at least three deficit months in the recent year.
- 242 / 655 eligible negative-balance months recover by month-end.
- Genuine cash withdrawals are 76.3735% of total all-history outflow.

Windows, filters, missingness, and denominators are documented in discovery_report.md.
Canonical example/schema files were refreshed to schema 1.1. No model ranking was performed.

## Live provider verification

Gemini was tested through the complete `select_plan(..., backend="gemini")` path using a wholly
invented profile: I=4000, S=3200, H=1200, insurance=100, B=4000, no loan, and 12 constant monthly
observations. The synthetic shock was 55% inflow for six months. Only the canonical derived case
was transmitted; no actual bank customer record was used.

Final result:

- Actual backend/model: `gemini` / `gemini-3.5-flash-lite`.
- API calls: 1; invalid outputs: 0; fallback: false.
- Schema-valid selection: M1.
- Reported input/output/total tokens: 786 / 82 / 868.
- Thought tokens were not reported; they remain null and usage_complete=false.
- Observed elapsed time: about 1.41 seconds for this single integration check, not a latency benchmark.

Earlier synthetic diagnostics identified the two schema errors described above. They were fixed
before the final successful call. The normal application never prints raw provider errors or keys.

Jev's request and response contract, retry logic, probabilities, and fallback are covered offline.
**Live Jev verification is still pending:** no OpenRouter key is configured in this environment.
This is an explicit verification limit, not a claim that the live Jev service was tested.

## Scope preservation

`git diff --exit-code` confirmed no changes to engine.py, daily_simulation.py, gemini_advisor.py,
etf_service.py, shock_playbook.json, data/, or the existing outputs/. The existing app only imports
and renders the optional classification panel; its financial calculations and action engine
continue independently. No credentials were committed. The source CSVs were never overwritten.
