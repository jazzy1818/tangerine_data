from datetime import date, timedelta
from hashlib import sha256
import json
from uuid import uuid4

import pytest

pytest.importorskip('httpx')
pytest.importorskip('fastapi')
from fastapi.testclient import TestClient

from web_app import service, store
from web_app.contracts import RunInput
from web_app.server import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'DB_PATH', tmp_path / 'website.sqlite3')
    monkeypatch.setattr(service, 'append_request', lambda record: None)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def savings_review():
    today = date.today()
    return {
        'account_id': 22812, 'scenario': {'phase': 'normal'}, 'opening_cash': 10000,
        'review_details': {'purpose': 'savings', 'cash_source': 'Synthetic staff-confirmed snapshot'},
        'savings_evidence': {
            'account_id': 22812, 'as_of': today.isoformat(),
            'protect_through': (today + timedelta(days=7)).isoformat(), 'unallocated_cash': '1500.00',
            'unpaid_commitments': '1000.00', 'cash_cushion': '400.00', 'remaining_reserve_goal': '500.00',
        },
    }


def preview(client, payload):
    response = client.post('/api/scenarios/preview', json=payload)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize(('changes', 'status', 'expected'), [
    ({}, 'available', 100),
    ({'remaining_reserve_goal': '60.00'}, 'available', 60),
    ({'unallocated_cash': '1400.01'}, 'available', 0.01),
    ({'unallocated_cash': '1350.00'}, 'no_room', 0),
    ({'unallocated_cash': '0'}, 'no_room', 0),
    ({'remaining_reserve_goal': '0'}, 'goal_met', 0),
    ({'remaining_reserve_goal': '0', 'unallocated_cash': '1350.00'}, 'no_room', 0),
    ({'unpaid_commitments': None}, 'needs_evidence', None),
    ({'account_id': 20111}, 'needs_evidence', None),
    ({'protect_through': (date.today() - timedelta(days=1)).isoformat()}, 'needs_evidence', None),
    ({'as_of': (date.today() - timedelta(days=1)).isoformat()}, 'needs_evidence', None),
])
def test_savings_uses_confirmed_account_snapshot(client, savings_review, changes, status, expected):
    savings_review['savings_evidence'].update(changes)
    result = preview(client, savings_review)['flexible_savings']
    assert result['status'] == status
    assert result['amount'] == expected
    if changes == {'unallocated_cash': '1350.00'}:
        assert result['room_after_commitments_and_cushion'] == -50
    if changes == {'account_id': 20111}:
        assert result['outstanding'] == ['a savings snapshot confirmed for this account']
        assert 'unallocated_cash' not in result


def test_snapshot_does_not_fall_back_to_historical_cash(client, savings_review):
    del savings_review['opening_cash']
    result = preview(client, savings_review)
    assert result['projection']['opening_basis'] == 'HISTORICAL_PROXY'
    assert result['flexible_savings']['amount'] is None
    assert 'the accessible cash balance and its source' in result['flexible_savings']['outstanding']


def test_missing_snapshot_or_cash_source_withholds_amount(client, savings_review):
    savings_review['review_details']['cash_source'] = ' '
    result = preview(client, savings_review)['flexible_savings']
    assert result['amount'] is None
    assert 'the accessible cash balance and its source' in result['outstanding']
    del savings_review['savings_evidence']
    assert 'cleared, unallocated cash' in preview(client, savings_review)['flexible_savings']['outstanding']


def test_conflicting_confirmed_cash_withholds_amount(client, savings_review):
    savings_review['savings_evidence']['unallocated_cash'] = '10000.01'
    result = preview(client, savings_review)['flexible_savings']
    assert result['amount'] is None
    assert 'cash figures that agree with the supplied accessible balance' in result['outstanding']


@pytest.mark.parametrize('changes', [
    {'review_details': {'purpose': 'cash_flow'}},
    {'scenario': {'phase': 'active', 'effects': [{'type': 'one_off_cost', 'value': 250, 'start_month': 0}]}},
    {'scenario': {'phase': 'recovery'}},
    {'normal_goal': {'name': 'Existing savings plan', 'monthly_contribution': 50, 'reserve_target': 500}},
    {'existing_transfers': [{'event_id': 'scheduled', 'month': 1, 'amount': 50,
                             'source': 'Synthetic payment schedule', 'included_in_baseline': True}]},
    {'opening_cash': -1},
])
def test_other_priorities_keep_savings_out_of_the_review(client, savings_review, changes):
    assert 'flexible_savings' not in preview(client, {**savings_review, **changes})


def test_preview_and_saved_review_agree_without_changing_projection(client, savings_review):
    baseline = preview(client, {'account_id': 22812, 'scenario': {'phase': 'normal'}, 'opening_cash': 10000})
    with_savings = preview(client, savings_review)
    result = with_savings.pop('flexible_savings')
    assert with_savings == baseline
    run_id = str(uuid4())
    response = client.post('/api/runs', json={**savings_review, 'request_id': run_id, 'backend': 'rules'})
    assert response.status_code == 202, response.text
    saved = client.get('/api/runs/' + run_id).json()
    assert saved['status'] == 'complete', saved['error']
    assert saved['result']['flexible_savings'] == result
    assert saved['result']['projection'] == baseline['projection']
    assert saved['result']['classification']['api_calls'] == 0


def test_run_without_savings_still_matches_pre_feature_request(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'DB_PATH', tmp_path / 'legacy.sqlite3')
    request = RunInput(request_id=uuid4(), account_id=22812, scenario={'phase': 'normal'})
    old_payload = request.model_dump(mode='json', exclude={'savings_evidence'})
    serialized = json.dumps(old_payload, sort_keys=True, allow_nan=False)
    with store.connection() as db:
        db.execute('INSERT INTO runs (id,session_id,fingerprint,created_at,status,request) VALUES (?,?,?,?,?,?)',
                   (str(request.request_id), 'legacy', sha256(serialized.encode()).hexdigest(),
                    store.now(), 'complete', serialized))
    assert store.reserve('legacy', request) is False
