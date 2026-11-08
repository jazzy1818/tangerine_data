> **Deferred — inactive archive.** The instructions below describe the earlier implementation.
> Its modules and app connections have been removed from the active website. Do not run these
> commands until the user explicitly resumes Snowflake work and the integration is restored.

# Snowflake portfolio insights

The employee website has a Snowflake integration with two parts:

1. Snowflake SQL computes financial medians, recent monthly patterns and portfolio trends.
   **Portfolio insights** turns those results into customer groups and links to reviews.
2. **Prepare discussion questions** calls the Snowflake Cortex REST API with measured
   aggregate evidence and drafts questions for the employee to review.

The [Sheridan prize listing](https://sheridandatathon2026.devpost.com/) describes **Best Use
of Snowflake API** as adding an AI feature through Snowflake's REST API. Cortex addresses
that description, with SQL supplying its evidence. A demonstrated connection and call are
still needed; adding code alone does not demonstrate live use or guarantee an award.

## Create the account and resources

Use the signup link on the [MLH Snowflake partner page](https://www.mlh.com/partners/snowflake),
which advertises a 120-day student trial. Check the terms shown during signup.

In a Snowflake SQL worksheet, run this setup as an administrator. Replace
`YOUR_SNOWFLAKE_USERNAME` in the final line with your actual user identifier.
Use this dedicated project schema, not a shared bank schema.

```sql
USE ROLE ACCOUNTADMIN;
CREATE WAREHOUSE IF NOT EXISTS TANGERINE_WH
  WAREHOUSE_SIZE = 'XSMALL' AUTO_SUSPEND = 60 AUTO_RESUME = TRUE INITIALLY_SUSPENDED = TRUE;
CREATE DATABASE IF NOT EXISTS TANGERINE_ANALYTICS;
CREATE SCHEMA IF NOT EXISTS TANGERINE_ANALYTICS.PORTFOLIO;
CREATE ROLE IF NOT EXISTS TANGERINE_PORTFOLIO;
GRANT USAGE ON WAREHOUSE TANGERINE_WH TO ROLE TANGERINE_PORTFOLIO;
GRANT USAGE ON DATABASE TANGERINE_ANALYTICS TO ROLE TANGERINE_PORTFOLIO;
GRANT USAGE, CREATE TABLE ON SCHEMA TANGERINE_ANALYTICS.PORTFOLIO TO ROLE TANGERINE_PORTFOLIO;
GRANT DATABASE ROLE SNOWFLAKE.CORTEX_REST_API_USER TO ROLE TANGERINE_PORTFOLIO;
GRANT ROLE TANGERINE_PORTFOLIO TO USER YOUR_SNOWFLAKE_USERNAME;
```

Create a **programmatic access token (PAT)** restricted to `TANGERINE_PORTFOLIO` in
Snowsight under your user's **Programmatic access tokens**. Current navigation is
**Governance & security → Users & roles → your user**; some layouts expose it in the
profile. Choose an appropriate expiry and copy the token directly into `.env`.
Account network/authentication policies may require administrator configuration;
follow the [official PAT setup](https://docs.snowflake.com/en/user-guide/programmatic-access-tokens).

## Add connection details to your existing `.env`

Keep the Gemini and OpenRouter settings. Append this block; do not replace the file.
Use the account identifier from Snowflake's connection details, usually
`organization-account`, without `https://` or `.snowflakecomputing.com`.

```dotenv
PORTFOLIO_SOURCE=snowflake
SNOWFLAKE_ACCOUNT=your_organization-your_account
SNOWFLAKE_USER=your_username
SNOWFLAKE_TOKEN=your_programmatic_access_token
SNOWFLAKE_WAREHOUSE=TANGERINE_WH
SNOWFLAKE_DATABASE=TANGERINE_ANALYTICS
SNOWFLAKE_SCHEMA=PORTFOLIO
SNOWFLAKE_ROLE=TANGERINE_PORTFOLIO
SNOWFLAKE_CORTEX_MODEL=claude-sonnet-4-6
```

The Cortex model must be enabled and available in your account/region. Change
`SNOWFLAKE_CORTEX_MODEL` to an available model supporting structured Chat Completions
if necessary. See [Cortex REST API](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-rest-api).
The app does not change account-wide model policies or enable cross-region inference.
No shell exports, `.bashrc` changes or browser key entry are needed.

## Install, upload and inspect

From the repository root, in your active Conda environment:

```bash
python -m pip install -r requirements-web.txt -r requirements-snowflake.txt
python -m web_app.snowflake_sync sync --dry-run
python -m web_app.snowflake_sync sync
python -m web_app.snowflake_sync status
```

- `sync --dry-run` validates the files and prints counts without network access.
- `sync` loads the supplied 185,326 monthly rows and 682 loan-status rows. It creates and
  reloads only `MONTHLY_HISTORY`, `LOAN_SNAPSHOT`, and `DATASET_SNAPSHOT` in the configured
  schema. **These tables are reserved for this app.** Replacement data and metadata commit
  together; failed inserts roll back to the previous snapshot. Run one sync at a time.
  Table creation precedes the transaction, so a failed first load can leave empty tables;
  running sync again completes setup.
- `status` actually connects and runs the portfolio SQL. It prints observation dates,
  upload time, source hash, row counts, query IDs and duration. It does not call Cortex.

The upload contains only account/month, inflow, spending, average daily balance, closing
balance, negative-balance days and loan status. Transactions, demographics, staff notes,
scenarios and API keys are not uploaded. Cortex receives aggregate evidence without
individual account identifiers. Connection settings stay on the server.

Start or restart the website yourself:

```bash
bash run.sh
```

Open **http://127.0.0.1:8000/#discovery**. Confirm that the source says **Snowflake** and
shows an upload timestamp. Choose a customer group, then **Prepare discussion questions**
to make the explicit Cortex call. Generated text appears beside the measured evidence it
references. Invalid or unavailable responses show an error, not a fabricated AI briefing.

## Useful financial analysis

| Group | Recorded evidence | Conversation purpose |
| --- | --- | --- |
| Repeated monthly shortfalls | At least 3 deficit months in a complete recent 12-month window | Understand how gaps are covered |
| Less than one month of reserves | Historical cash estimate divided by typical spending below 1 | Confirm funds for essential costs |
| Overdrafts hidden by month-end recovery | Negative-balance days followed by nonnegative month-end cash | Explore income and payment timing |
| Limited cover after an income reduction | Positive typical surplus but runway below 6 months at 55% inflow | Discuss resilience to an income interruption |

Typical inflow/spending use all-history medians. Cash uses the last six observed average
daily balances. Recent patterns use the dataset's latest twelve calendar months; incomplete
histories are excluded from the repeated-shortfall group. Zero typical spending gives
undefined reserve coverage. The hypothetical income reduction uses an unrounded runway
threshold. Groups overlap and are conversation prompts, not current affordability findings,
credit scores, default probabilities or lending decisions.

## Demonstrate and monitor

The app terminal logs `portfolio_snowflake` with query IDs/timing and `portfolio_cortex`
with outcome, latency and returned token counts. Credentials, prompts and raw provider
errors are not logged. Failures log a fixed `portfolio_fallback code=...` and the page
clearly says **Local records**.

In Snowflake Query History, filter the query tag `tangerine_portfolio_v1`. The actual
queries are in `web_app/sql/`. Cortex usage is separate: administrators can inspect
`SNOWFLAKE.ACCOUNT_USAGE.CORTEX_REST_API_USAGE_HISTORY` (reporting may lag).

For judges: show the Snowflake source → choose the recovered-overdraft group → prepare
discussion questions → open an account → assess changed circumstances through Jev/Gemini.
Snowflake supplies evidence and discussion preparation; the existing engine calculates plans.

## Refresh, availability and costs

SQL results are cached for five minutes; filters and pagination reuse the snapshot.
**Refresh insights** refreshes results at most once per ten seconds. Failed requests use
an explicit local fallback and a short retry cooldown. The website never runs the uploader.

Successful Cortex briefings are reused for thirty minutes for the same snapshot, group,
model and connection settings. There are no automatic paid retries. A timeout may still
incur usage; a later explicit request may make another call. Briefings are temporary
preparation aids, not saved customer assessments or notes.

The small warehouse auto-suspends. SQL compute and Cortex use credits; check trial usage
in Snowflake. Set `PORTFOLIO_SOURCE=local` to disable cloud access. The connector is optional.
For institutional deployment, separate uploader write privileges from a read-only website
role with Cortex access.

Source hashes prevent using a mismatched warehouse snapshot with local customer records.
After changing CSVs, rerun sync and restart the website to reload the engine's data cache.
Do not edit the warehouse snapshot tables manually.

Local checks used the supplied dataset. Live SQL/Cortex validation still requires your
Snowflake account, resources and PAT and has not been completed yet.
