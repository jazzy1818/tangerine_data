# Investment what-if in Allocation Review

Open **5. Allocation Review → Investment what-if**. This section reads the
existing guarded plan outputs. It never selects a suitable security for an
account, invokes a classifier, executes a trade, or changes cash available for
bills. A Streamlit fragment keeps ETF selection, history ranges and chart controls
independent of the financial calculation. Account/shock changes rebuild the
existing plan normally and pass its updated outputs into the fragment.

## Run

```bash
python -m pip install -r requirements.txt
# Optional: needed only for the explicit public-history request
python -m pip install -r requirements-etf.txt
bash run.sh
```

Activate the intended virtual environment first. The cloud checkout uses
`PATH="$PWD/.venv/bin:$PATH" bash run.sh`. The previously reported Mac workaround
is `arch -x86_64 bash run.sh` when its installed dependencies require x86 Python;
that platform-specific command was not tested here.

The rest of the screen works without Yahoo, API keys, or the optional yfinance
package. The **Show ETF history** button is the only market-fetch trigger. On a
provider failure, the contribution outlook stays available. A successful history
already loaded for that same symbol remains in session memory with its retrieval
and last trading dates disclosed. No replacement/synthetic prices are presented
as market observations. Blocked/incomplete shock capacity remains unknown rather
than being shown as zero; independent market exploration stays available.

## Three distinct sources

- **Fictional profiles:** `etf_demo.py` supplies invented risk/horizon constraints
  and two explicit synthetic cases. Reserve/liquidity coverage is assumed only
  for those examples. Stable goal-priority rules order eligible fictional
  profiles; exclusions have reasons. No account field enters those rules. The
  CAD 2,400 ±10%/0% scenario is a teaching input applied equally to all four
  profiles, not an estimated fund return.
- **Market examples:** `market_data/etf_catalog.json` records XEQT.TO, VEQT.TO and
  ZEQT.TO in one peer group: Canadian-listed globally diversified all-equity
  asset-allocation ETFs with CAD trading units. Issuer product references, names,
  category, catalog date and individual inclusion reasons are included. This is
  **Selected market examples**, with no performance or size ranking. Fund assets
  and comparable one-year returns are unknown, not estimated. The date is a
  catalog metadata date, not a claim that live market metrics were observed.
  Live issuer-page retrieval could not be verified through this cloud proxy.
- **Account contributions:** normal amount comes directly from
  `investment_plan.normal_monthly_allocation`, conditional on passed runtime
  validation. Shock rows come from the complete validated
  `crisis.applied_plan.schedule[].proposed_contribution`. A verified zero remains
  zero; a reserve earmark contributes zero to the ETF illustration. Paused
  existing payments remain crisis cash and are never converted to new ETF
  purchases. Starting invested balance is zero; the cash buffer is excluded.

The source market list is identical for every account, shock and synthetic case.
Existing suitability/review flags remain visible above and below the explorer.

## Financial illustrations

For a supported period, sum the actual selected monthly contribution rows.
The forward chart displays cumulative contributions before market change; the
readout applies a single chosen -10%, 0% or +10% move at the end to the complete
illustrative invested balance. It never compounds that rate monthly or derives
it from historical returns. Both paths use the same move. Supported chart windows
are at most six months and cannot exceed the evaluated crisis path; shorter
custom horizons include their actual length. Selecting Month 3 slices the first
three rows unchanged. Amounts use posted-CAD Decimal arithmetic.

Independent example: normal CAD 200/month and shock CAD 100/month give CAD 1,200
and CAD 600 after six months at 0%. A single 10% end decline gives CAD 1,080 and
CAD 540, with CAD 60 loss on the shock path. Three-month 0% totals are CAD 600 and
CAD 300. Liquid reserves are not treated as invested balances.

## Yahoo history and optional historical replay

`etf_market.py` accepts only curated symbols and public source dates. It requests
daily history through `yfinance.Ticker.history(auto_adjust=False, timeout=8)` and
requires `Adj Close`. No account, balance, scenario, narrative, or credentials
are passed to Yahoo or Gemini. The timeout bounds each library request; the
library can make multiple requests internally. Successful normalized responses
are cached in memory by symbol/start/end for one hour, with a 12-entry limit.
Display controls slice those results without a new request. No price history is
bundled in Git or persisted by this feature.

The normalizer sorts dates, preserves local trading dates when removing time
zones, drops invalid/nonpositive prices, collapses identical duplicate dates and
rejects conflicting duplicates. Missing adjusted prices never fall back silently
to raw closes. The chart rebases the first valid selected price to CAD 1,000.
Prices 100 → 110 → 90 therefore produce 1,000 → 1,100 → 900 and -10% change.
Actual date range, source, currency and final value are shown. Shortened windows
and stale data are disclosed. Yahoo adjusted-price illustrations can differ from
an issuer's NAV-based total returns.

The optional replay uses today's normal monthly amount, including zero, with
monthly dates anchored to the first displayed trading date (month-end clipping).
Each contribution buys synthetic adjusted-price units on the first available
trading date on or after its scheduled date within the selected period. The
readout shows total contributed, ending value and difference. These are not
customer holdings or transactions; personal taxes and trading costs are excluded.

References and data-use scope:

- [yfinance documentation](https://ranaroussi.github.io/yfinance/)
- [Price history API](https://ranaroussi.github.io/yfinance/reference/yfinance.price_history.html)
- [yfinance project and data-use notice](https://github.com/ranaroussi/yfinance)
- [Yahoo terms](https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html)

The library is an unofficial research/educational client and points users to
Yahoo's personal-use data terms. This implementation provides no redistribution
license. Review applicable provider/issuer rights for a public submission or
video; automated tests use synthetic prices exclusively.

## Verification

```bash
.venv/bin/python -m pytest tests/test_etf_explorer.py tests/test_etf_ui.py -q
.venv/bin/python -m pytest tests -q
```

At implementation, **363 tests and 9 subtests passed**, including 20 new ETF
checks. Coverage includes explicit fetch only, curated symbols, adjustment and
timeout settings, synthetic history arithmetic, source cleaning, cache reuse,
three/six-month forward math, dated zero months, unknown/reserve/blocked states,
ticker and shock independence, provider failures and a fixed monthly replay.

Chromium exercised the actual Streamlit app: Allocation Review rendered, fund
selection preserved contribution totals, and a failed live Yahoo request retained
the local outlook with a clear error. This environment's proxy returns HTTP 403
for Yahoo access; live adjusted-price retrieval and issuer-page verification
remain open. Successful-history behavior is verified with mocked synthetic data.


## Files

- `app.py`: Allocation Review hook and independent explorer on blocked plans.
- `etf_ui.py`: Streamlit fragment and Plotly views.
- `etf_calculations.py`: validated contribution readout, end-move arithmetic,
  rebasing and optional historical contribution replay.
- `etf_market.py`: public-only fetch, cleaning and bounded cache.
- `etf_demo.py`: fictional profiles and independent synthetic fit rules.
- `market_data/etf_catalog.json`: dated issuer-reference catalog.
- `requirements-etf.txt`: optional yfinance dependency.
- `tests/test_etf_explorer.py`, `tests/test_etf_ui.py`: synthetic numerical and
  full-dashboard regressions. `README.md` links this guide.
