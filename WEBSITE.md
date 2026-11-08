# Tangerine Customer Review Workspace

The employee website supports customer conversations, financial assessments, discussion
notes, and follow-up work. Technical diagnostics remain in the backend and request logs. It uses the existing financial engines; no M1–M8
definitions, eligibility rules, investment rules, or official formulae were rewritten.

## Run

Activate your Conda environment. Install once, then start the website yourself:

```bash
python -m pip install -r requirements-web.txt
bash run.sh
```

Open **http://127.0.0.1:8000**. Use the same host consistently: `localhost` and `127.0.0.1`
have different browser cookies and therefore different saved workspaces.

The launcher uses the active Python environment and also supports `python3`. No Node.js,
frontend build, CDN, or Streamlit installation is required for this website.

```bash
bash run.sh --port 8001
bash run.sh cli
bash run.sh streamlit  # Previous interface, with requirements.txt installed
```

This is a local judge/demo application, bound to loopback by default. Its browser-workspace
cookie separates saved records; it is not user authentication. Public hosting needs an
authenticated deployment and a durable shared job/storage setup. Portfolio analytics use
the supplied local CSV files.

## Employee workflow

1. **My reviews:** start a customer review, continue a draft, or open the follow-up diary.
   The getting-started guide explains the three stages of a review and can be hidden.
2. **Find a customer:** search by account number or filter by financial circumstances.
   Review cash flow, commitments, reserves and past payment pressure before assessing changes.
3. **Assess a change:** record the purpose, employee reference, and customer priority.
   Add or edit the actual financial changes, amounts, timing and information basis.
   Income levels are entered as percentages (55 means 55% of usual inflow).
4. Confirm accessible cash and its source. Optional financial forms capture existing savings
   payments, a savings objective, and updated recovery figures. No JSON entry is required.
   Recovery inflow can remain unknown. A rebuild date then requires an explicitly supported
   contribution, confirmed stability and covered obligations; blank inflow is not zero income.
5. **Check the financial impact**, then **Prepare customer review**. The prepared review
   shows the funding gap, first shortfall, suggested focus, savings-goal impact, and
   outstanding information. It identifies a standard assessment when assistance is unavailable.
6. Record discussion notes, a review owner, next steps and follow-up date. Mark progress as
   in progress, awaiting information, ready for discussion, follow-up scheduled, or closed.
7. Download the review summary, print/save a PDF, or export the cash-flow schedule as CSV.
   Compare two saved assessments from **Review history** when discussing alternatives.

The financial comparison stays in the existing review card and uses the shared
`backup_comparison.py` validation and explanations. Charts show month-start and month-end
cash, with the first shortfall marked and posted events available on hover. A month-start
shortage stays visible even when the balance recovers by month-end. Partial projections
show known components and leave the full funding need unestablished.

New assessments save the validated comparison alongside the original plan. Earlier saved
reviews remain readable and unchanged; prepare a revised assessment to obtain the newly
saved comparison explanation. The portfolio income-shock finding also uses the teammate's
shared `portfolio_overview.py` calculation.

**Portfolio insights** is a secondary view with historical observations and conversation
prompts, customer groups and links into individual reviews. Its charts and customer groups
are calculated from the supplied local records.
**Assessment preferences** retains the choice of Jev, Gemini or standard rules
without asking the employee to manage keys or inspect provider diagnostics. A new draft uses
Jev when configured, otherwise Gemini when configured, otherwise standard rules. Existing
saved preferences are retained. No assessment is requested until the employee prepares it.

Review status and checklist completion describe administrative work. They do not approve a
product, execute a payment, verify a cash balance, or change financial calculations. Update
figures and prepare a new assessment to change a cash projection. Financial assessments remain
immutable; discussion notes are stored separately with a version to prevent silent overwrites
between browser windows.

Draft entries and unsaved discussion notes are retained in browser storage. An unfinished
financial form must be saved or discarded before preparing the review. Save discussion notes
before exporting. If another window changes saved notes, the older update is rejected; use
**Discard edits / load saved notes** to reload the latest record after retaining any desired
text. Drafts are retained per customer in this browser, so switching accounts restores each
customer's current draft. Saved assessments remain available independently.

Presets are starting examples and are marked as estimates to confirm. A new custom change
starts with no monetary amount and no confirmed duration. Context notes do not create financial
effects. The payment-pause, debt-deferral and recovery forms retain the existing engine's
requirements for evidence, dates and amounts.

This remains a local workspace. The recorded owner/preparer is an employee-entered reference,
not an authenticated identity or a shared institutional case-management account. Worklist
counts cover the latest 100 saved assessments; all amounts remain conditional on the supplied
facts and recorded data.

## API keys and monitoring

Keep `GEMINI_API_KEY` and `OPENROUTER_API_KEY` in the existing root `.env`. The same
classifier configuration reader is used. The browser receives readiness booleans only,
never credentials. Model overrides still use `GEMINI_CLASSIFIER_MODEL` and `JEV_MODEL`.

The server terminal shows HTTP requests. Classifier request metadata is also appended
to the existing log, including calls, source, fallback, latency and validation codes:

```bash
tail -F logs/classification.jsonl
```

Assessments and separate employee review notes are stored in `logs/website.sqlite3`, already covered by the repository's
`logs/` ignore rule. They include the selected account, scenario, local evidence, financial
result, and request metadata. Browser workspaces expire after 30 days unless renewed;
keep JSON exports for portable handoff. Clearing cookies changes the browser workspace.
The old Streamlit request log is retained, but its requests have no saved website analysis.

A request ID makes submission idempotent: resending the same request does not start another
provider call. Failed or interrupted runs are not automatically resubmitted. An interrupted
provider call may already have incurred usage; review the log before creating another run.
Run one server process/worker against a given website database. Saved results remain usable
without model access, and a provider failure is explicitly labelled as a local fallback.

## Architecture and maintenance

- `web_app/static/`: employee worklist, financial entry forms, review summaries, accessible SVG charts and CSS.
  JavaScript modules use the same-origin HTTP API. Styling can be replaced independently.
- `web_app/server.py`: FastAPI endpoints, input validation, private browser-workspace cookie,
  static asset serving, and background execution after explicit submission.
- `web_app/contracts.py`: HTTP contracts that reuse the repository's Pydantic financial types.
- `web_app/service.py`: adapts `engine`, `plan_classification`, and the existing runtime
  validators. It checks the full financial plan before a paid call, then binds the returned
  classification to the exact canonical input hash. Shared comparison validation runs before
  that call and again against the final plan; financial amounts are not recalculated in JS.
- `web_app/analytics.py`: read-only CSV-derived customer search.
  In-memory data views refresh on server restart, matching the engine's dataset cache.
- `web_app/portfolio.py`: local portfolio groups, historical charts and customer drilldown.
- `web_app/store.py`: SQLite assessment snapshots and versioned staff notes scoped to an opaque browser cookie.

Main endpoints:

| Endpoint | Purpose |
| --- | --- |
| `GET /api/config` | Provider readiness, module descriptions and scenario schema; no keys |
| `GET /api/accounts` | Search/filter/paginate accounts |
| `GET /api/customers/{id}` | Customer metrics, features and monthly history |
| `GET /api/discovery` | Groups, paginated accounts, charts and source; accepts `cohort`, `offset`, `limit`, `refresh` |
| `POST /api/scenarios/preview` | Validate inputs and calculate the local cash path |
| `POST /api/runs` | Save an idempotent request and start its explicit analysis |
| `GET /api/runs` | Latest 100 saved records in this browser workspace |
| `GET /api/runs/{id}` | Poll or reopen an immutable result with separately saved review notes |
| `PATCH /api/runs/{id}/review` | Save staff progress, notes, checklist and follow-up without recalculating or calling a provider |

Interactive API documentation is at `/api/docs`. All money calculations remain server-side.
The website presents full funding as unknown when effects are incomplete, and never treats
monthly checkpoints as proof of daily solvency. The default path includes the existing
normal-goal, crisis, recovery, and allocation validation. Specialized historical daily replay
and ETF exploration remain available in the previous Streamlit interface; the new site does
not turn either into a live trade or an automatic funding action.

## Why move away from Streamlit here?

Streamlit builds interactive data apps from Python. By default, widget interactions rerun
the script ([official execution-model documentation](https://docs.streamlit.io/get-started/fundamentals/main-concepts)).
It was useful for the initial prototype. The previous app accumulated UI state, editor modes,
classification and financial reports in one script. The new site gives editing, submission,
background calculation and saved results distinct boundaries. Streamlit remains useful for
the team's exploratory screens; it is no longer required to serve the judge website.
