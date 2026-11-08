"""Finance-owned acceptance examples and action-boundary regressions."""
import csv
from decimal import Decimal
from math import isclose
from pathlib import Path
from uuid import uuid4

import pytest

import engine
from crisis_response import make_crisis_plan
from test_crisis_execution import account, compound, normal_goal


def assess(customer, scenario, **options):
    crisis = make_crisis_plan(customer, scenario, normal_goal=options.pop('goal', normal_goal()), **options)
    assert crisis['runtime_validation']['status'] == 'passed', crisis['review_flags']
    return crisis['finance_plan']


def scenario(effect=None, phase='active'):
    return {'phase': phase, 'effects': [effect] if effect else []}


def loan_account():
    customer = account(2200., 2400., 300., 0.)
    customer.update(P=300., raw_P=300., F=300., raw_F=300., has_running_loan=True)
    customer['history']['loan_payments'] = 300.
    return customer


def deferral(**changes):
    return {'type': 'debt_payment_delta', 'effect_id': 'loan-1', 'value': -300.,
            'duration_months': 2, 'evidence': 'user_confirmed', 'debt_change_kind': 'deferral',
            'repayment_month': 4, 'repayment_amount': 650., **changes}


def transfers():
    return [{'event_id': f'payment-{month}', 'month': month, 'amount': 300., 'included_in_baseline': True,
             'pause_approved': True, 'pause_fee': 0., 'source': 'Hypothetical supplied schedule'}
            for month in range(1, 7)]


def test_compound_action_order_and_residual_are_from_supported_cash():
    plan = assess(account(), compound(), opening_cash=3000., existing_transfers=transfers())
    assert plan['status'] == 'SUPPORTED_MODELED'
    assert plan['financial_diagnosis']['first_shortfall'] == {'month': 2, 'phase': 'end', 'cash': -120., 'need_cad': 120.}
    assert plan['comparison']['after']['first_shortfall'] == {'month': 3, 'phase': 'end', 'cash': -30., 'need_cad': 30.}
    assert plan['comparison']['funding_improvement_cad'] == 1800.
    assert plan['remaining_gap_cad'] == 1560.
    assert plan['required_target_only']['uniform_monthly_improvement_cad'] == 260.
    assert [item['status'] for item in plan['prioritized_actions']] == ['SUPPORTED_MODELED', 'TARGET_ONLY', 'CONDITIONAL_ONLY']
    assert plan['normal_goal_impact']['proposal_pause_cash_credit_cad'] == 0.
    assert plan['prioritized_actions'][1]['impact'] is None
    assert len([row for row in plan['candidate_action_decisions'] if 'standalone' in row.get('evaluated_paths', {})]) == 6
    assert plan['no_action']['scenario_hash'] == plan['supported_action']['scenario_hash'] == plan['scenario_hash']
    assert plan['no_action']['opening_cash'] == plan['supported_action']['opening_cash'] == 3000.
    assert plan['finance_approval'] == 'PENDING'


def test_late_receipt_and_late_action_cannot_cover_earlier_shortage():
    late = scenario({'type': 'one_off_receipt', 'value': 2000., 'start_month': 3, 'evidence': 'user_confirmed'})
    plan = assess(account(1800., 2400., 1000.), late, opening_cash=1000.)
    assert plan['financial_diagnosis']['first_shortfall']['need_cad'] == 200.
    assert plan['remaining_gap_cad'] == 600.
    assert plan['next_review_checkpoint']['checkpoint'] == {'month': 2, 'phase': 'end'}
    plan = assess(account(), compound(), existing_transfers=[transfers()[-1]])
    assert plan['prioritized_actions'][0]['status'] == 'TARGET_ONLY'
    action = next(item for item in plan['prioritized_actions'] if item['status'] == 'SUPPORTED_MODELED')
    assert action['impact']['cash_change_at_original_shortfall_cad'] == 0.


def test_deferral_keeps_extra_cost_and_separate_counterfactual():
    plan = assess(loan_account(), scenario(deferral()))
    action = next(item for item in plan['candidate_action_decisions'] if item['action_id'] == 'deferral:loan-1')
    assert action['status'] == 'CONDITIONAL_ONLY'
    assert action['repayment']['extra_over_deferred_principal_cad'] == 50.
    assert action['impact']['before']['first_shortfall']['phase'] == 'end'
    assert action['impact']['before']['full_funding_need_cad'] == 900.
    assert action['impact']['after']['first_shortfall']['phase'] == 'start'
    assert action['impact']['after']['full_funding_need_cad'] == 950.
    assert action['impact']['funding_improvement_cad'] == -50.
    assert plan['comparison']['funding_improvement_cad'] == 0.


def test_unknown_input_never_has_a_full_target_and_later_debt_is_visible():
    unknown = assess(account(), scenario({'type': 'income_delta', 'evidence': 'unknown'}))
    assert unknown['remaining_gap_cad'] is unknown['required_target_only'] is None
    assert unknown['status'] == 'REVIEW_REQUIRED'
    assert unknown['prioritized_actions'][0]['status'] == 'BLOCKED_OR_UNKNOWN'
    late = assess(loan_account(), scenario(deferral(repayment_month=8)))
    assert late['remaining_gap_cad'] is None
    assert late['post_horizon_obligations'][0]['value'] == 650.


def test_assumptions_cannot_change_supported_path():
    result = assess(loan_account(), scenario(deferral(evidence='assumed')))
    assert result['supported_action']['schedule'][1]['spending'] == 2400.
    assert result['supported_action']['schedule'][4]['deferred_repayment'] == 0.
    assert result['conditional_assumption_path']['schedule'][1]['spending'] == 2100.
    assert result['conditional_assumption_path']['schedule'][4]['deferred_repayment'] == 650.
    assert result['comparison']['funding_improvement_cad'] is None


def test_recurring_deficit_is_visible_when_opening_cash_covers_the_horizon():
    plan = assess(account(1800., 2400., 6000.), scenario(phase='normal'))
    assert plan['remaining_gap_cad'] == 0.
    action = plan['prioritized_actions'][0]
    assert (action['action_id'], action['status'], action['amount_cad']) == ('review-recurring-deficit', 'TARGET_ONLY', 600.)
    assert action['impact'] is None


def test_stale_history_prompts_current_evidence_before_a_normal_decision():
    customer = account()
    customer['history']['month'] = customer['history']['month'].str.replace('2025', '2023')
    plan = assess(customer, scenario(phase='normal'))
    assert plan['comparison']['after']['complete'] is True
    assert plan['status'] == 'REVIEW_REQUIRED'
    assert plan['prioritized_actions'][0]['action_id'] == 'review-stale-history'


def test_rules_only_saved_website_review_uses_the_validated_action_plan(tmp_path, monkeypatch):
    pytest.importorskip('httpx')
    pytest.importorskip('fastapi')
    from fastapi.testclient import TestClient
    from web_app import service, store
    from web_app.server import app

    monkeypatch.setattr(store, 'DB_PATH', tmp_path / 'review.sqlite3')
    monkeypatch.setattr(service, 'append_request', lambda record: None)
    identity = str(uuid4())
    data = {'request_id': identity, 'account_id': 22812, 'backend': 'rules',
            'scenario': scenario({'type': 'one_off_cost', 'value': 250., 'start_month': 0})}
    with TestClient(app) as client:
        response = client.post('/api/runs', json=data)
        assert response.status_code == 202, response.text
        stored = client.get(f'/api/runs/{identity}').json()
        assert stored['status'] == 'complete', stored['error']
        result = stored['result']
        crisis = result['plans']['crisis_plan']
        assert crisis['finance_plan']['supported_action'] == crisis['applied_plan']
        assert crisis['finance_plan']['remaining_gap_cad'] == crisis['applied_plan']['full_funding_need']
        assert result['classification']['api_calls'] == 0
        stale = {'event_id': 'saved', 'account_id': 20111, 'month': 1, 'amount': 20., 'source': 'Synthetic',
                 'included_in_baseline': True, 'pause_approved': True, 'pause_fee': 0.}
        wrong = client.post('/api/scenarios/preview', json={
            'account_id': 22812, 'scenario': data['scenario'], 'existing_transfers': [stale]})
        assert wrong.status_code == 422
        assert 'different account' in wrong.json()['detail']


def test_account_binding_and_excluded_pause_reasons():
    record = transfers()[0]
    with pytest.raises(ValueError, match='different account'):
        assess(account(), compound(), existing_transfers=[{**record, 'account_id': 18}])
    plan = assess(account(), compound(), existing_transfers=[{**record, 'pause_fee': None}])
    row = next(item for item in plan['candidate_action_decisions'] if item['action_id'].startswith('pause:'))
    assert row['status'] == 'BLOCKED_OR_UNKNOWN'
    assert 'fee' in row['reason']
    assert plan['comparison']['funding_improvement_cad'] == 0.


@pytest.mark.parametrize('contribution,months', [(300., 14), (None, None)])
def test_recovery_separate_checkpoint(contribution, months):
    checkpoint = {'source': 'Synthetic independent recovery', 'cash_basis': 'judge_specified',
                  'assessment_month': '2026-11', 'available_cash': 3000., 'monthly_spending': 2400.,
                  'stable_cash_flow': True, 'obligations_covered': True,
                  'supported_monthly_contribution': contribution}
    plan = assess(account(), scenario(phase='recovery'), recovery_snapshot=checkpoint)
    recovery = plan['recovery_checkpoint']
    assert (recovery['reserve_target'], recovery['reserve_gap'], recovery['months_to_target']) == (7200., 4200., months)
    assert plan['remaining_gap_cad'] is None


def test_independent_112_checkpoint_anchors():
    a = assess(account(), compound(), opening_cash=3000.)
    a_with_pause = assess(account(), compound(), opening_cash=3000., existing_transfers=transfers())
    b = assess(account(1800., 2400., 1000.), scenario({'type': 'one_off_receipt', 'value': 2000.,
                                                       'start_month': 3, 'evidence': 'user_confirmed'}))
    c = loan_account()
    c_base = assess(c, scenario(phase='normal'))
    c_deferral = assess(c, scenario(deferral()))
    c_blocked = assess(c, scenario(deferral(obligation_payment=300., obligation_source='Synthetic', payment_in_baseline=False)))
    e = assess(account(), scenario({'type': 'income_delta', 'evidence': 'unknown'}))
    paths = {
        ('A', 'No intervention'): a['no_action'],
        ('A', 'Pause future proposed investment'): a['supported_action'],
        ('A', 'Pause approved existing outflow'): a_with_pause['supported_action'],
        ('B', 'Start Month 3 receipt'): b['no_action'],
        ('C', 'Original payments'): c_base['no_action'],
        ('C', 'Approved deferral'): c_deferral['no_action'],
        ('C', 'Deferral without baseline evidence'): c_blocked['no_action'],
        ('E', 'Income changes; synthetic baseline from Case A'): e['no_action'],
    }
    source = Path(__file__).resolve().parents[1] / 'finance_qa_export' / 'synthetic_expected_checkpoints.csv'
    with source.open() as handle:
        expected = list(csv.DictReader(handle))
    assert len(expected) == 112
    for row in expected:
        path = paths[row['case'], row['path']]
        month, phase = int(row['month']), row['engine_phase']
        schedule = path['schedule'][month]
        index = 2 * month + (phase == 'end')
        point = path['checkpoints'][index]
        assert (point['month'], point['phase']) == (month, phase)
        start = phase == 'start'
        values = {'opening_cash': schedule['start_balance'] if start else path['checkpoints'][index - 1]['cash'],
            'one_time_receipt': schedule['one_off_receipt'] if start else 0,
            'one_time_expense': schedule['one_off_cost'] - schedule['deferred_repayment'] if start else 0,
            'income': 0 if start else schedule['income'], 'spending': 0 if start else schedule['spending'],
            'action_cash_effect': 0 if start else schedule['paused_existing_outflow'] - schedule['proposed_contribution'],
            'fees': schedule['action_fees'] if start else 0, 'repayments': schedule['deferred_repayment'] if start else 0,
            'closing_accessible_cash': point['cash']}
        for key, actual in values.items():
            assert (None if actual is None else Decimal(str(actual))) == (Decimal(row[key]) if row[key] else None), (row, key)


def test_organizer_metrics_and_combined_runway_on_all_accounts():
    reference = Path(__file__).resolve().parents[1] / 'reports' / 'classification' / 'account_features.csv'
    with reference.open() as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == len({row['account_id'] for row in rows}) == 4500
    for row in rows:
        account_id = int(row['account_id'])
        customer = engine.know_customer(account_id)
        for field in ('I', 'S', 'F', 'H', 'B', 'P'):
            assert isclose(customer[f'raw_{field}'], float(row[field]), rel_tol=1e-12, abs_tol=1e-8), (account_id, field)
        cash = float(row['B'])
        gap = float(row['S']) + .15 * float(row['H']) - .55 * float(row['I'])
        expected = 0. if cash <= 0 else 'no shortfall (120+)' if gap <= 0 else round(min(120., cash / gap), 1)
        assert engine.take_shock(customer, .55, .15)['runway'] == expected, account_id
