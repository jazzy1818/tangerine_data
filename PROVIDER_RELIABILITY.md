# Provider and demo reliability audit

Work began with a clean tree on branch `work`, commit
`b9c39a45ddfb32f8acc2cd1459c2b6cd12c71943` (Backup Plan cash comparison).
Implementation was developed on `provider-demo-reliability` and subsequently
merged into `main`; integration results are recorded below.
The initial mocked reproductions exposed four failures: automatic daily API use
with an inherited key; malformed-settings exceptions on both remote classifiers;
and explanation settings bypassing the project file. No live provider was called.

## Routes, intent and actual labels

| Route | Explicit action | Models/settings | Actual result |
|---|---|---|---|
| Rules classification | Classify scenario / engine offline fallback | No key/model | `rule_baseline`, zero API calls |
| Jev classification | Classify scenario with Jev selected | `OPENROUTER_API_KEY`, `JEV_MODEL` (default `typesafe/jev-1.14`) | `jev` on valid response; otherwise `rule_baseline` with a fixed fallback code |
| Gemini classification | Classify scenario with Gemini selected | `GEMINI_API_KEY`, `GEMINI_CLASSIFIER_MODEL` (default `gemini-3.5-flash-lite`) | `gemini` on valid response; otherwise `rule_baseline` |
| Gemini explanation emphasis | Use Gemini to emphasize validated findings | `GEMINI_API_KEY`, `GEMINI_EXPLANATION_MODEL` (default `gemini-2.5-flash`) | `gemini` for valid approved IDs; otherwise complete `local` explanation |
| Legacy daily advisor | Ask Gemini to review bill timing | `GEMINI_API_KEY`, `GEMINI_ADVISOR_MODEL` (default `gemini-2.5-flash`) | `gemini` for valid selection/abstention; otherwise `local` advice and fixed fallback reason |

Jev endpoint remains `https://openrouter.ai/api/v1/systemone`. Both Gemini routes
and the classifier use the official Google SDK. No remote provider is called on
cold launch or merely by selecting an account, scenario, note, backend or tab.
The daily advisor's Python API now defaults to `backend='local'`; a key alone no
longer enables live behavior. Explicit `backend='gemini'` is required there.
Classification CLI `--backend jev/gemini` is an explicit provider request.

`requested_backend`, `actual_backend`, fallback metadata and API-call count
identify what actually happened. A requested daily route with no supported bill
candidate returns local advice without an API request. A valid provider abstention
is a provider response, not a fallback. A provider success is not financial approval.

## Configuration and caches

`plan_classification/config.py` remains the shared reader. Explicit nonblank
API arguments take priority over project `.env`, then inherited shell values.
Blank password overrides use configured values; empty `.env` entries override
inherited entries. Unsupported/malformed configuration produces local fallback;
raw settings values never enter error messages. Keys are not exported to the
process environment. The classifier's password fields are scoped to that browser
and classifier, with no implicit forwarding to the other advice routes.

Models are independent per route. The two advice routes retain their original
2.5 default; operators must choose models enabled for their project. Availability
is not assumed or probed automatically. Legacy 2.x temperature settings are omitted
when a newer model is explicitly configured.

Classification identity includes the account, canonical normalized case, chosen
backend, configured model and credential availability. Password edits invalidate
the classifier result. Advice identities include route/model, current normalized
case, local scenario/facts and effective module as applicable. Daily inputs include
the actual replay values; scientific scalar types are normalized deterministically.
No key value is stored in cache identities. Cached provider outputs are per-browser
session state, never a process-wide shared response cache. Account changes clear
advice results; input or model changes use local output until a new explicit call.
No automatic refresh, retry-on-edit or cross-provider fallback is introduced.

ETF fetches and market caches are unchanged and remain public-only, with their
separate explicit history button.

## Financial authority and accepted text

The classifier proposes one lead and up to two supports. The existing typed
schema, case validation and financial eligibility override remain in force.
The Backup Plan explicitly identifies the proposed module/source separately
from the effective engine response. The Python engine owns cash, contribution
limits, evidence, pauses, recovery and every effective financial action.

Free-form provider rationale/questions can contain unsupported claims despite a
valid module. The Gemini adapter therefore accepts its validated modules/reasons
and renders a local evidence template plus canonical missing-detail flags. Raw
provider prose is discarded rather than becoming an analyst recommendation.
Its source is labeled `evidence_template`, not model-authored financial text.

The independent emphasis route sends categories and the effective accepted module,
then accepts at most three unique IDs from the already validated local cards.
Every card and review flag stays visible; Gemini cannot rewrite totals, hide a
remaining gap, create approval, or add an ETF/credit/insurance action. The daily
advisor sends bands and permits only a conditional bill move or abstention. Its
rationale is the local reviewed playbook text; no provider-authored action prose
is displayed. Neither route changes any forecast.

## Outbound privacy and error handling

- Jev and Gemini classifiers receive the same canonical normalized case: ratios,
  relative effects/timing, approved reasons and generated missing-detail flags.
  Account ID, CAD scale, original monetary amounts, demographics, raw notes,
  obligation IDs/source text, and transaction history stay local.
- Explanation requests contain approved card IDs, status categories, accepted
  module, pause/gap booleans and completeness. Full card text and CAD amounts
  never leave the app.
- Daily requests contain a whitelisted shock category, a shortfall timing band,
  a funding-size band and one allowed action ID. Exact money/dates and notes
  remain local.
- Auth keys are used only for provider authentication. Provider exceptions and
  response bodies are never copied into UI, retry prompts, JSONL logs or this
  report. HTTP/error codes are bounded safe values. Invalid metadata or output
  falls back; actual model IDs must have identifier syntax.
- Classification logs keep the existing metadata allowlist: no credential,
  account ID, exact balance, narrative, provider rationale or raw response.
  The existing `jeff` alias still reports the actual Jev name.

No keys, responses, screenshots containing credentials, or fetched customer data
are bundled in this handoff. Automated tests redirect logs to temporary paths
where applicable and isolate real `.env`/inherited provider settings globally.
The operator's real configuration file is not read or edited by tests.

## Offline verification and live boundary

Run:

```bash
.venv/bin/python -m pytest tests/test_provider_reliability.py tests/test_provider_controls.py -q
.venv/bin/python -m pytest tests -q
# With the desired environment active:
bash run.sh
```

Mocked tests cover deliberate calls, missing keys, malformed configuration,
provider exceptions/invalid output, abstention, model/credential precedence,
empty-file overrides, session isolation, model-aware cache invalidation, payload
privacy and unchanged cash paths under provider proposals/overrides. Tests also
exercise actual Google SDK wire serialization and response parsing for the
classifier, explanation and daily-advisor schemas, without network transport.

Live Jev, Gemini classification, explanation and daily selection availability
remain **not verified in this assignment**. Live tests require an operator's
separate authorization and credentials already in approved configuration. No
live requests or credential-based live verification were performed, no head-to-head winner is claimed,
and an offline fallback must never be counted as a successful live response.


## Results for this branch

After merging the latest `main` at `064a173` into this feature branch without
conflicts, the full suite passed **444 tests and 9 subtests** (23 new
provider-specific checks). The existing finance, crisis, chart and ETF
regressions passed unchanged. This sync did not merge the feature into `main`.
`git diff --check` passed. Chromium used an ephemeral wrapper with synthetic
settings and all remote entry points blocked: cold launch, all five tabs,
account/shock/provider/note edits made zero provider attempts. Only the explicit
classifier and emphasis actions reached the blocked test entry points and both
retained complete local fallbacks. No operator configuration was changed and no
real network provider request was made. The wrapper and its temporary log were
not added to the repository.

The branch also adds `tests/conftest.py` to isolate real operator credentials and
`.env` for the entire automated suite. Provider tests explicitly opt into synthetic
settings and mocked transports; the production settings file is never edited.

## Main integration verification

Pulled `main` at `d920e5b`, including the newer Backup Plan smoke checks, and
merged `provider-demo-reliability` at `e6c5663` without conflicts. The combined
code passed **446 tests and 9 subtests** using `.venv/bin/python -m pytest tests -q`.
`git diff --check` passed. Provider testing remained mocked; no live provider
requests or credential-based live verification were performed during integration.
