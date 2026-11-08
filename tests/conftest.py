"""Never consume an operator's real provider credentials during automated tests."""
import pytest
from plan_classification import config


def pytest_addoption(parser):
    parser.addoption('--provider-evidence-dir', default=None,
                     help='Write synthetic offline provider evidence CSV/manifest after this run.')


def pytest_configure(config):
    config._provider_evidence = []


@pytest.fixture
def record_provider_evidence(request):
    return request.config._provider_evidence.append


def pytest_sessionfinish(session, exitstatus):
    destination = session.config.getoption('--provider-evidence-dir')
    if not destination:
        return
    import csv
    import hashlib
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    output = Path(destination)
    output.mkdir(parents=True, exist_ok=True)
    rows = sorted(session.config._provider_evidence,
                  key=lambda row: (row['route'], row['case_id'], row['requested_backend']))
    columns = ('case_id', 'normalized_case_hash', 'route', 'expected_handling', 'evidence_mode',
               'requested_backend', 'actual_backend', 'fallback_reason', 'provider_lead_proposal',
               'selected_lead', 'effective_lead', 'override_reason', 'api_calls', 'parse_outcome',
               'ledger_hash', 'result')
    with (output/'offline_results.csv').open('w', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=columns, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    sources = ['plan_classification/backends.py', 'plan_classification/case.py',
        'plan_classification/schemas.py', 'plan_classification/config.py', 'plan_classification/ui.py',
        'provider_controls.py', 'tailored_advice.py', 'app.py', 'crisis_response.py',
        'scenario_execution.py', 'recovery_plan.py', 'pause_decisions.py', 'goal_validation.py',
        'tests/test_crisis_execution.py', 'tests/test_tailored_advice.py',
        'tests/provider_test_support.py', 'tests/conftest.py',
        'tests/test_provider_fallback_evidence.py', 'tests/test_provider_fallback_ui.py']
    import importlib.metadata
    import platform
    from plan_classification import build_case, profile_from_engine
    from plan_classification.case import canonical_json, case_hash
    from provider_test_support import reviewed_examples
    example = reviewed_examples()[1]
    smoke_case = build_case(profile_from_engine(example['customer']), example['scenario'])
    (output/'smoke_case.json').write_text(canonical_json(smoke_case)+'\n')
    manifest = dict(status='passed' if exitstatus == 0 and rows else 'incomplete_or_failed',
        pytest_exit_status=int(exitstatus), rows=len(rows), input_basis='synthetic_only',
        smoke_case_hash=case_hash(smoke_case),
        runtime=dict(python=platform.python_version(), packages={name: importlib.metadata.version(name)
            for name in ('pytest', 'pandas', 'google-genai', 'pydantic', 'streamlit')}),
        live_tests=[dict(route=route, status='Not run', reason='No separate live-test authorization')
            for route in ('jev_classification', 'gemini_classification', 'gemini_explanation', 'gemini_daily')],
        source_sha256={name: hashlib.sha256((root/name).read_bytes()).hexdigest() for name in sources})
    (output/'manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True)+'\n')


@pytest.fixture(autouse=True)
def provider_configuration(tmp_path,monkeypatch):
    # Individual provider tests may install synthetic settings after this fixture.
    # The real project file is neither read nor edited, and subprocess env is local.
    monkeypatch.setattr(config,'ENV_FILE',tmp_path/'unconfigured-provider.env')
    for name in config.SETTING_NAMES:
        monkeypatch.delenv(name,raising=False)
