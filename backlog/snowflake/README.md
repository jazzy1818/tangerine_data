# Snowflake — deferred

The user asked to put Snowflake on the backlog and keep it out of the app until
they explicitly decide to proceed. Do not activate it as part of unrelated work.

The active website uses local portfolio analysis only. It has no Snowflake imports,
configuration reader, uploader, Cortex route, AI briefing controls or cloud setup prompts.
Even an existing `PORTFOLIO_SOURCE=snowflake` setting cannot activate the integration.
Existing secrets in the user's `.env` have not been edited.

Preserved work:

- `warehouse.py.disabled`: connection, credential handling and SQL reads.
- `snowflake_sync.py.disabled`: validated snapshot upload and status command.
- `portfolio_brief.py.disabled`: aggregate-evidence Cortex discussion preparation.
- `sql/`: original warehouse analysis queries.
- `requirements-snowflake.txt`: optional connector dependency, outside active requirements.
- `integration.patch`: reference diff from the local-only app to the previous integration,
  including backend, browser UI and configuration wiring.
- `SETUP.md`: archived setup and demonstration instructions; inactive until restored.

The Python modules have a `.disabled` suffix so they cannot run as application modules.
No cloud account was connected and live SQL/Cortex behavior was not verified.

If the user later resumes this work, review the patch against the then-current app instead
of replacing newer files. Restore only the intended integration, refresh relevant service
documentation, and complete live validation using credentials configured by the user.
