# Eight-module scenario classification

This addition implements your portion of the combined plans: reproducible data discovery,
interpretable customer features, and **Jev via OpenRouter vs Gemini via Google's SDK**. Both
receive one canonical case and return one lead module plus up to two supporting modules.
No winner has been selected and no live quality benchmark has been run.

The plans agree on M1–M8. The existing app implements financial arithmetic, action-level
advice, daily replay, and investing; it did not implement this module classifier. The plans'
“JEFF” spelling refers here to **Jev, TypeSafe's API decision model**, as clarified by the user.
`backend="jeff"` remains an alias for `"jev"` for teammate compatibility. Jev is not a local
trained model, and the local baseline is always reported as `rule_baseline`.

## Approach

Keep the original I/S/F/H/B/P numbers for finance and audit. Derive a compact set of interpretable
ratios and historical stress measures for selection. Preserve distinct sources of stress instead
of inventing one aggregate risk score. Include the actual financial effects of the supplied
scenario: the same person can require M1 under inflow loss and M8 after a windfall.

There are no best-plan labels in this dataset. The existing demographic/client labels are not
training targets. Neither remote model needs training in this repo. Later, compare the two on
expert-reviewed cases and outcomes from your shared financial solver, grouped by account/scenario
to avoid leakage. Keep API failures/fallbacks separate from successful model decisions.

Discovery: [report](reports/classification/discovery_report.md), [data audit](reports/classification/data_audit.md),
[feature formulas](reports/classification/feature_dictionary.md), [all account features](reports/classification/account_features.csv).
The 714/3,309 finding from the implementation brief was reproduced. Other findings use explicitly
specified windows and denominators; they must not be confused with the friend's daily replay.

## Run

Python 3.10+; install normal app dependencies with `python -m pip install -r requirements.txt`.
For discovery charts/tests: `python -m pip install -r requirements-classification-dev.txt`.

```bash
# Local, no API calls
python -m plan_classification profile 22812
python -m plan_classification discover
python -m plan_classification classify 22812 --scenario examples/classification/combined.json

# Inspect exactly the canonical case that either model receives, without calling an API
python -m plan_classification classify 22812 --scenario examples/classification/combined.json --show-input

# Set credentials in the project .env file or environment before these commands
python -m plan_classification classify 22812 --scenario examples/classification/combined.json --backend jev
python -m plan_classification classify 22812 --scenario examples/classification/combined.json --backend gemini

# Save one run for later review
python -m plan_classification classify 22812 --scenario examples/classification/windfall.json --backend jev --output outputs/classification/windfall.json

python -m pytest tests -q

# Start the app: every remote route requires a separate explicit button
python -m streamlit run app.py
```

Copy `.env.example` to `.env` in the repo root and fill in your keys. The classifier reads it
directly, without changing `os.environ`. The classifier and both advice routes share this reader.
Explicit nonblank API arguments / the classifier's password fields take priority, followed by
`.env`, then inherited shell settings. Classifier password overrides stay in that browser's
classifier control; they are not forwarded to the other advice routes.
An empty `.env` value overrides an inherited value too. Never paste keys into code.

| Backend | Environment | Default model | API |
|---|---|---|---|
| Jev | `OPENROUTER_API_KEY`; optional `JEV_MODEL` | `typesafe/jev-1.14` | `https://openrouter.ai/api/v1/systemone` |
| Gemini | `GEMINI_API_KEY`; optional `GEMINI_CLASSIFIER_MODEL` | `gemini-3.5-flash-lite` | Official `google-genai` client |
| Local baseline | None | None | Offline |

Get an OpenRouter key from [OpenRouter settings](https://openrouter.ai/settings/keys).
Get a Gemini key from [Google AI Studio](https://aistudio.google.com/apikey).
The new classifier uses Google's current Flash-Lite model because access to older 2.5 models
is restricted for new projects. The existing advisor retains its original configuration.
Use accounts/models enabled for your team; model names are configurable. Explanation emphasis uses
`GEMINI_EXPLANATION_MODEL`; the daily advisor uses `GEMINI_ADVISOR_MODEL`. Both retain
`gemini-2.5-flash` as their separate legacy default; set an enabled model for your project.
No model availability is inferred from a key. No secrets are printed, logged, or included in errors.

In the existing Streamlit app, open **Take a Shock → Classify this scenario into one of the eight
plan modules**. The panel uses the selected account and shock sliders, a guided effect editor,
or a custom JSON scenario for windfalls, debt changes, delays, holds, recovery, and combinations. Choose the backend and
press **Classify scenario**. Selecting a backend alone never calls it. Results are invalidated
when the account, canonical case, or backend changes. The selected structured scenario also drives the backup through `engine.make_plan()`. Module proposals pass independent financial validation; changing the provider cannot change the cash arithmetic. No financial action is executed. See [CRISIS_RESPONSE.md](CRISIS_RESPONSE.md).

**Classification request logs** in that panel show each run's provider, model, lead module,
latency, API call count, fallback reason, and reported usage. `api_success` means a valid provider
response; `fallback` means the local baseline was used instead. The panel keeps the latest 100
requests in the current browser session and offers a JSONL download. A persistent metadata copy
is appended to `logs/classification.jsonl` (ignored by Git) when the button is clicked. It excludes
keys, account IDs, balances, scenario text, and model rationale. Unknown costs/tokens stay blank.
Gemini's response schema restricts module IDs and reason codes to the current case. Its single
retry includes corrective instructions after invalid output; strict local validation still applies.
The `validation_errors` log field records safe rejection codes (including a failed first attempt
when the retry succeeds), without storing provider text or credentials.
To watch new classification records in a terminal after the first request:

```bash
tail -f logs/classification.jsonl
```

All remote UI routes are deliberate and separate:

- **Classify scenario** calls only the selected Jev/Gemini classifier, or offline rules.
- **Use Gemini to emphasize validated findings** requests only approved fact IDs.
- **Ask Gemini to review bill timing** requests a conditional bill-move selection or abstention.

The daily advisor defaults to local rules even with keys configured. Changing accounts, shocks,
notes, ETF controls or tabs never initiates a provider call. Missing/unreadable configuration,
missing keys, SDK failures and provider errors retain useful local results with explicit fallback
labels. ETF history still has its independent **Show ETF history** action and public-only cache.
The former `env -u` launch workaround is unnecessary; keys no longer enable an automatic advisor.
See [provider/demo reliability audit](PROVIDER_RELIABILITY.md) for route traces and checks.

This implementation uses **structured scenario input**. The guided editor lets an operator enter
each effect, amount, timing, duration, and evidence without writing JSON, then add or remove effects.
It does not claim arbitrary free-text parsing: a narrative is retained locally and financial effects
must be entered explicitly. A finite duration or `ongoing: true` states known timing; an omitted
duration with `ongoing: false` stays unknown and requests clarification.
Unknown effects use null and produce nonblocking bank-analyst review flags (the shared field remains `needs_clarification`). Your friend's future translator can
produce the same `ShockScenario` directly; no classifier rewrite is needed.

## Integration contract for teammates

```python
from plan_classification import (
    build_case, get_customer_profile, select_plan,
    FinancialConstraints, ShockScenario,
)

profile = get_customer_profile(22812)
shock = ShockScenario(effects=[
    {"type": "income_multiplier", "value": 0.55, "duration_months": 6},
    {"type": "household_bills_percent", "value": 15, "ongoing": True},
])
case = build_case(profile, shock, FinancialConstraints())
result = select_plan(case, backend="jev")  # or "gemini" or "rules"
proposal = result.selection.model_dump()
# The shared financial solver sizes and validates the proposal:
import engine
customer = engine.know_customer(22812)
plan = engine.make_plan(customer, scenario=shock, selection=proposal)
```

Use `profile_from_engine(customer)` and `scenario_from_engine(...)` to adapt objects from the
current app. `bills_increase_pct` in the engine uses 0.15; the structured effect uses 15. The adapter
handles that conversion. `get_customer_profile(..., as_of="2025-06")` excludes future rows and
end-of-data loan status. The CSV feature report is local and includes IDs for reproducibility;
`build_case` excludes them from both model payloads.

| ID | Module |
|---|---|
| M1 | Income Continuity |
| M2 | Cost Rebalancing |
| M3 | Emergency Liquidity |
| M4 | Debt & Obligation Defense |
| M5 | Multi-Shock Stabilization |
| M6 | Reserve Restoration |
| M7 | Cash-Flow Timing & Access |
| M8 | Surplus & Windfall Allocation |

Selection output: `lead_module`, `support_modules`, `reason_codes`, `needs_clarification`,
`rationale`. The enclosing result records requested/actual backend, fallback reason, schema/input
hash, implementation/prompt/model version, latency, call count, invalid outputs, token usage,
available provider cost, and Jev's returned confidence/probabilities. Token/cost metadata sums
known usage across attempts; `usage_complete` distinguishes complete from partial accounting.
Gemini's visible output tokens and thinking tokens are reported separately. Raw provider responses and
credentials are not logged. Identical `input_hash` values let you pair later model runs.

Jev gets a Choice question for the lead and independent Noul questions for module usefulness.
The application excludes the lead from supporting modules and keeps up to two scores ≥0.5.
That support threshold is an explicit, **untuned** starting point, not a validated threshold.
Jev does not generate rationale text: its rationale is a labeled application evidence summary
of the observed signals, not a claim to expose Jev's reasoning. Model confidence is not the
probability that a customer will recover or that an intervention is financially feasible.

Gemini uses `response_json_schema` with a compact provider schema: field types and allowed enum
values are sent, together with the small two-support-module bound. Larger array and string bounds remain enforced locally. This avoids the SDK's
incompatible OpenAPI field serialization and the provider's constrained-decoding complexity limit.
Gemini returns validated structured JSON. After validation, its module and reason codes are
accepted as a proposal; raw rationale and extra questions are not accepted as financial prose.
The application supplies an evidence template (`rationale_source=evidence_template`) and retains
canonical missing-details flags. The finance engine still owns the effective module and cash. Its default model uses supported provider sampling
settings; a configured legacy Gemini 2.x model uses temperature 0. Neither backend may emit unknown
module IDs, disallowed modules, duplicate modules, or unsupported reason codes. Missing input
questions are preserved even if the model omits them. API calls have bounded timeouts and at most
two application attempts. Missing credentials, network/provider errors, or invalid results use
the explicitly identified local baseline. No cross-provider fallback silently changes the contest.
A structurally valid selection still needs the shared finance engine's substantive validation.

## Original package integration and checks (historical)

The following records the initial classification package. Current provider changes and
verification are in [PROVIDER_RELIABILITY.md](PROVIDER_RELIABILITY.md).

The new `plan_classification/` package owns features, normalized case data, adapters, CLI, discovery,
and the optional UI panel. Existing `engine.py`, `daily_simulation.py`, `gemini_advisor.py`,
`etf_service.py`, `shock_playbook.json`, raw CSVs, and prior outputs are unchanged.
`app.py` only adds the optional panel; `requirements.txt` explicitly declares its HTTP dependency.

Offline tests cover financial definitions for all 4,500 accounts, time cutoffs, sparse/invalid data,
all eight baseline routes, contradictory effects, future magnitudes, unknown durations, privacy
boundaries, actual SDK request serialization, output validation, retries, explicit fallback,
usage metadata, the guided editor, and full-app integration. Automated tests mock remote services.

Verification after the audit: **159 tests passed**. A separate live Gemini check used only an
invented customer profile and a six-month 55%-inflow scenario. The complete classifier returned
a valid M1 selection in one call, without fallback. This verifies integration, not model quality.
Jev was checked against its official API contract and mocked responses; live Jev verification
remains pending because `OPENROUTER_API_KEY` is not configured. No head-to-head model comparison
or winner selection was performed. See the [verification report](reports/classification/verification_report.md).

The full `app.py` headless regression test uses mocked market feeds and the existing advisor
offline. Dependencies were installed in `/tmp/tangerine-classification-venv`; you can use its
`bin/python` for the commands above in this session, or install in your own environment.

## Provider references checked during implementation

- [OpenRouter Jev integration](https://openrouter.ai/docs/guides/community/jev)
- [OpenRouter System One request/response contract](https://openrouter.ai/docs/guides/community/typesafe-sdk)
- [TypeSafe Choice semantics](https://docs.typesafe.ai/primitives/choice)
- [Google Gen AI SDK structured output](https://googleapis.github.io/python-genai/)
- [Google model availability](https://ai.google.dev/gemini-api/docs/models?hl=en)
- [Google structured-output schema complexity](https://ai.google.dev/gemini-api/docs/structured-output#simplifying-complex-schemas)

The banking dataset remains the only source of customer features. Provider documentation is an
API implementation source, not additional financial data.

## Crisis handoff update

Case schema 1.2 preserves historical features and adds `planning_cash_basis` for
explicit scenario opening cash. `build_case(..., planning_cash=...)` and the finance
executor use the same supplied amount without changing official historical B.
The local optional `effect_id` identifies invoices: exact repeated IDs are
idempotent, conflicting repeats are rejected, and distinct IDs can identify equal
amounts. IDs are excluded from the canonical model case.

The classifier remains a proposal layer. The dated executor, goal handoff, G25
deterioration rule, approved-transfer comparisons and evidence-gated recovery are
documented in [CRISIS_RESPONSE.md](CRISIS_RESPONSE.md). Old verification counts
below describe the earlier classifier audit, not the complete merged suite.


## Demo reliability update

Classifier session identity includes account, canonical case hash, selected backend, effective
configured model and key availability. Editing a classifier password override clears its result.
Model/case/provider changes hide nonmatching saved results without making a replacement call.
Advice caches likewise bind current facts/scenario/accepted module and route-specific model to
the browser session. No provider result uses a process-wide shared cache, and credentials never
enter cache keys or request logs. Repeated reruns reuse only matching session results.

Gemini emphasis and daily selection now use explicit JSON Schema transport, with the actual
Google SDK serializer exercised through mocked transport. Emphasis is limited to up to three
approved card IDs; daily selection permits only the supported bill-move ID or null. Model output
cannot author new approvals or change any cash totals. All mandatory local facts remain visible.
Automated tests isolate both inherited provider settings and the project `.env` reference; no
operator key is read or consumed. Live verification requires separate operator authorization.
