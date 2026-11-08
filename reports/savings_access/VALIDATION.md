# Validation

- Full suite: `python -m pytest -q` — 536 passed, 9 subtests passed; no skips.
- Focused engine/API suite: 91 passed, 9 subtests passed.
- `python -m pip check` — passed.
- Full cohort: all 4,500 accounts evaluated before and after; both original fixed amount fields match for every account; zero runtime blocks.
- Website API smoke: account 20160 normal savings preview exposes a conditional historical review while withholding the one-time amount without current evidence; projection stays unchanged.
- JavaScript card: rendered the conditional explanation and suppressed blocked reviews. Source module syntax checked with Node.
- No external provider calls or actual financial transfers were made.

Install test dependencies using `python -m pip install -r requirements-web-dev.txt`.
Full logs and the account-level comparison accompany this report. Portfolio source
checksums in summary.json identify the evaluated working code, whose base is the
existing one-time savings feature commit eb45c8d. This is implementation validation,
not a human finance sign-off or a forecast of actual customer outcomes.
