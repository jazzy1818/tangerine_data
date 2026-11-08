# Finance presentation branch synchronized with main

Branch: `feat/finance-decision-policy`.

- Fetched main: `b65be040e9270ca12c44edb3edfa850497fba809` (`final`).
- Preserved finance follow-up: `d1788afbb1711f0236e419c2df8bc3a026f789d4`.
- Merge/code commit: `4950dc20f02f8b36e768bdb9b67431b1544fa2ee`.

The merge is **main into the feature branch**. Main was fetched and inspected without checking it out, resetting it or writing to it. No push or merge into remote main was performed. Both histories are retained by a merge commit, and the previous uncommitted finance edits were committed before the merge. A recovery patch and archive were also saved outside the checkout.

## Combined functionality

All 18 incoming paths from main are present. Thirteen paths match main exactly; five shared files combine both feature sets. Conflicts in `web_app/service.py`, `static/app.js`, `static/scenario.js` and `static/reviews.js` were resolved explicitly.

- Keep main's account selection, plain-text shock reader, visible defaults, basic shock editor, main/backup overview, options table and optional detailed explanations.
- Keep the finance branch's account-bound savings evidence, guarded contribution review, collision-safe event identities, conditional daily comparison, detailed financial actions, trade-offs and review dates.
- Build both `plans.action_plan` and `plans.crisis_plan.finance_plan` from the same validated crisis ledgers. The main overview's funding amount agrees with the finance plan; the finance review deadline takes precedence when available.
- Unpriced effects retain an incomplete projection. The merged overview labels its first-shortfall facts as known components instead of asserting cash is safe.
- The exporter builds the same two action views as the website and captures the combined renderer. The 21 no-action/supported-action ledger pairs are unchanged from the pre-merge finance package.

## Verification

Run from the repository root with `.venv` active:

```bash
python -m pytest -q --junitxml=/tmp/tangerine-main-sync-full.xml
python -m pytest -q tests/test_main_sync.py tests/test_action_plan.py tests/test_shock_text.py tests/test_website_savings.py tests/test_finance_policy_followup.py
python -m finance_policy_integration.export_cases --out /tmp/tangerine-main-sync-final-review
node --check web_app/static/app.js
node --check web_app/static/scenario.js
node --check web_app/static/reviews.js
python -m pip check
git merge-base --is-ancestor origin/main HEAD
```

- Full suite: **570 tests passed + 9 subtests passed**, 152.93 seconds, **0 failures/errors/skips**.
- Focused combined-flow checks: **58 passed**, 4.29 seconds. New integration coverage checks offline interpretation through a saved review, unpriced expenses, agreement of funding in both action views, and coexistence of text entry with the savings-evidence form.
- JavaScript syntax and dependency consistency passed. Source whitespace passed; intentional Markdown hard-break spaces in main's verbatim policy document were preserved.
- The restarted website served the merged assets and passed offline description-to-saved-review requests for a compound shock and an unpriced repair. Both action views were present with matching funding results and zero remote provider calls.
- Refreshed review package: **21 accounts, 33 decision rows, 588 paired checkpoints**, and 21 exact UI text captures. Source hashes match the clean merge/code commit; finance verdicts remain blank and approval remains **PENDING**.

For presenting, activate `.venv`, run `bash run.sh`, select an account and use **Generate main & backup plans**. The new text reader works offline when no Gemini key is configured; the rules classifier requires no provider credentials. See [OFFLINE_DEMO.md](OFFLINE_DEMO.md) for the finance cases.
