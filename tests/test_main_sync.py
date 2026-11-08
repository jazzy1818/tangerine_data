"""The combined branch retains main's entry flow and finance-policy evidence."""
import json
from pathlib import Path
import shutil
import subprocess
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from finance_policy_integration.export_cases import render_reviews
from web_app import service, store
from web_app.server import app


@pytest.mark.parametrize('description,kinds', [
    ('Lost job and bills up 15%', {'income_multiplier', 'household_bills_percent'}),
    ('car broke down', {'one_off_cost'}),
])
def test_offline_description_produces_both_saved_action_views(tmp_path, monkeypatch, description, kinds):
    monkeypatch.setattr(store, 'DB_PATH', tmp_path / 'merged-review.sqlite3')
    monkeypatch.setattr(service, 'append_request', lambda record: None)
    with TestClient(app) as client:
        response = client.post('/api/scenarios/interpret', json={
            'account_id': 22812, 'description': description, 'horizon_months': 6})
        assert response.status_code == 200, response.text
        interpreted = response.json()
        assert interpreted['source'] == 'local'
        assert {effect['type'] for effect in interpreted['scenario']['effects']} == kinds
        identity = str(uuid4())
        response = client.post('/api/runs', json={
            'account_id': 22812, 'scenario': interpreted['scenario'], 'backend': 'rules',
            'request_id': identity, 'review_details': {'shock_defaults': interpreted['assumptions'][:12]}})
        assert response.status_code == 202, response.text
        saved = client.get('/api/runs/' + identity).json()
    assert saved['status'] == 'complete', saved['error']
    result = saved['result']; crisis = result['plans']['crisis_plan']
    assert result['classification']['api_calls'] == 0
    assert crisis['runtime_validation']['status'] == 'passed'
    assert result['plans']['action_plan']['comparison']['supported_actions']['full_funding_need'] == crisis['finance_plan']['remaining_gap_cad']
    assert crisis['finance_plan']['supported_action'] == crisis['applied_plan']
    if shutil.which('node'):
        capture = next(render_reviews([saved]))
        assert 'Main plan' in capture and 'Backup plan' in capture
        assert 'All options considered' in capture
        assert capture.count('Recommended Financial Actions') == 1
        assert capture.index('Recommended Financial Actions') < capture.index('Compare the financial paths')
        assert 'Cash stays above zero' not in capture
        if description == 'car broke down':
            assert crisis['finance_plan']['remaining_gap_cad'] is None
            assert 'First shortfall · Known components' in capture
            assert 'Known amounts only' in capture


@pytest.mark.parametrize('with_shock', [False, True])
def test_description_entry_and_savings_evidence_coexist(with_shock):
    if not shutil.which('node'):
        pytest.skip('Node is required to verify the combined scenario renderer')
    script = """
      import {blankDraft} from './web_app/static/common.js';
      import {scenarioView,basicScenario,savingsReviewApplies} from './web_app/static/scenario.js';
      const draft=blankDraft(22812);
      draft.reviewDetails.purpose='savings';
      draft.scenario={phase:'normal',horizon_months:6,effects:[]};
      if(process.argv[1]==='true')draft.scenario=basicScenario({income:55,bills:0,cost:0,receipt:0,months:6},draft.scenario);
      const html=scenarioView(draft,{account_id:22812,metrics:{I:3000,S:2400,B:3000}},{});
      process.stdout.write(JSON.stringify({html,applies:savingsReviewApplies(draft)}));
    """
    rendered=json.loads(subprocess.check_output(
        ['node','--input-type=module','-e',script,str(with_shock).lower()],
        cwd=Path(__file__).resolve().parents[1], text=True, timeout=10))
    assert 'id="shock-description"' in rendered['html']
    assert 'Generate main &amp; backup plans' in rendered['html']
    assert rendered['applies'] is not with_shock
    assert ('data-savings-field' in rendered['html']) is not with_shock
