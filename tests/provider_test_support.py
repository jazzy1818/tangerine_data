"""Synthetic fixtures and mocked provider boundaries; never load customer data."""
import json
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock, patch

import requests

from plan_classification import ShockScenario
from test_crisis_execution import account, compound, normal_goal
from test_tailored_advice import transfers


def reviewed_examples():
    """Code-reviewed expectations, not human finance signoff or model labels."""
    return [
        dict(case_id='steady', customer=account(cash=7200), scenario=ShockScenario(phase='normal'),
             proposal='M8', expected_first=None, expected_gap=0, complete=True, effective=None,
             expected='Keep the healthy cash path; no evidenced crisis action.'),
        dict(case_id='income', customer=account(), scenario=ShockScenario(effects=[
            dict(type='income_multiplier', value=.55, duration_months=6)]),
             proposal='M1', expected_first=5, expected_gap=1500, complete=True, effective='M1',
             expected='Apply the dated inflow loss; local cash math stays authoritative.'),
        dict(case_id='compound', customer=account(), scenario=compound(),
             options=dict(existing_transfers=transfers()),
             proposal='M5', expected_first=3, expected_gap=1560, complete=True, effective='M5',
             expected='Only the evidenced six scheduled pauses retain cash.'),
        dict(case_id='late_receipt', customer=account(income=1800, cash=1000),
             scenario=ShockScenario(effects=[dict(type='one_off_receipt', value=2000, start_month=3)]),
             proposal='M8', expected_first=2, expected_gap=600, complete=True, effective='M2',
             expected='Keep the earlier shortfall; a later receipt does not establish surplus allocation.'),
        dict(case_id='payment_timing', customer=account(), scenario=ShockScenario(effects=[
            dict(type='payment_delay_days', value=7, duration_months=6)]),
             proposal='M7', expected_first=None, expected_gap=0, complete=False, effective='M7',
             expected='Monthly projection stays partial; a timing label cannot establish daily solvency.'),
        dict(case_id='unknown', customer=account(), scenario=ShockScenario(effects=[
            dict(type='unspecified_event', value=None, evidence='unknown')]),
             proposal='M6', expected_first=None, expected_gap=0, complete=False, effective=None,
             expected='Hold for analyst review; the full funding need and recovery are not established.'),
        dict(case_id='recovery', customer=account(), scenario=ShockScenario(phase='recovery'),
             options=dict(recovery_snapshot=dict(source='Synthetic supplied checkpoint',
                 account_id=17, assessment_month='2026-07', cash_basis='judge_specified',
                 available_cash=3000, monthly_inflow=3000, monthly_spending=2400,
                 stable_cash_flow=True, obligations_covered=True, supported_monthly_contribution=300)),
             proposal='M6', expected_first=None, expected_gap=0, complete=False, effective='M6',
             expected='Rebuild from the separate evidenced checkpoint; the historical monthly path remains a partial reference.'),
    ]


def build_plan(example, selection=None):
    from crisis_response import make_crisis_plan
    return make_crisis_plan(example['customer'], example['scenario'], normal_goal=normal_goal(),
                            selection_result=selection, **example.get('options', {}))


@contextmanager
def classifier_boundary(handling='success', lead='M1'):
    """Patch the real adapters' transport/client factories, not select_plan()."""
    inputs = {'jev': [], 'gemini': []}

    def failure():
        if handling == 'timeout':
            raise requests.Timeout('PRIVATE provider body and synthetic key')
        if handling == 'provider_failure':
            raise RuntimeError('PRIVATE provider failure')

    def gemini_call(**kwargs):
        # Retry correction instructions follow the same canonical JSON object.
        state, _ = json.JSONDecoder().raw_decode(kwargs['contents'])
        inputs['gemini'].append(state)
        failure()
        text = 'invalid JSON' if handling == 'malformed' else json.dumps(dict(
            lead_module='M99' if handling == 'unsupported' else lead,
            reason_codes=['windfall'] if handling == 'unsupported_reason' else state['observed_reasons'],
            rationale='Synthetic structured response.'))
        return SimpleNamespace(text=text, model_version='gemini-mocked')

    def post(url, **kwargs):
        state = kwargs['json']['state']
        inputs['jev'].append(state)
        failure()
        response = Mock(status_code=200)
        if handling == 'malformed':
            response.json.side_effect = ValueError('PRIVATE malformed response')
        else:
            selected = 'M99' if handling == 'unsupported' else lead
            allowed = state['constraints']['allowed_modules']
            answers = {'lead_module': dict(type='choice', choice=selected, confidence=.8,
                probabilities={m: float(m == selected) for m in allowed})}
            answers.update({f'support_{m}': dict(type='noul', noul=.1) for m in allowed})
            response.json.return_value = dict(answers=answers, model='typesafe/jev-1.14')
        return response

    client = Mock()
    client.models.generate_content.side_effect = gemini_call
    with patch('plan_classification.backends.requests.post', side_effect=post) as transport, \
         patch('google.genai.Client', return_value=client) as factory:
        yield SimpleNamespace(inputs=inputs, transport=transport, factory=factory, client=client)


def finance_snapshot(plan):
    """Exclude classifier metadata; keep the effective financial decisions and ledger."""
    return {key: plan[key] for key in ('no_action', 'applied_plan', 'goal_status',
        'goal_contribution_revised', 'applied_transfer_ids', 'existing_transfer_pause_credit', 'recovery')}


def digest(value):
    import hashlib
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()
