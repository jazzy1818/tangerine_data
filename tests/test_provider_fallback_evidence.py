"""Inspectable offline evidence, never a live comparison or accuracy benchmark."""
import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from plan_classification import build_case, profile_from_engine, select_plan
from tailored_advice import explain_plan
from provider_test_support import (reviewed_examples, build_plan, classifier_boundary,
                                   finance_snapshot, digest)


@pytest.fixture(autouse=True)
def prohibit_network(monkeypatch):
    import importlib.util
    def deny(*args, **kwargs):
        pytest.fail('Offline verification attempted unmocked network access')
    monkeypatch.setattr('requests.sessions.Session.request', deny)
    for module in ('httpx', 'httpx2'):
        if importlib.util.find_spec(module):
            monkeypatch.setattr(f'{module}.Client.send', deny)


def configured_keys(monkeypatch):
    monkeypatch.setenv('OPENROUTER_API_KEY', 'synthetic-jev-key')
    monkeypatch.setenv('GEMINI_API_KEY', 'synthetic-gemini-key')


def classification_row(case_id, expected, result, plan, proposed, baseline):
    assert plan['runtime_validation']['status'] == 'passed'
    assert finance_snapshot(plan) == finance_snapshot(baseline)
    return dict(case_id=case_id, normalized_case_hash=result.input_hash,
        route='classification', expected_handling=expected, evidence_mode='mocked' if result.requested_backend != 'rules' else 'local',
        requested_backend=result.requested_backend, actual_backend=result.actual_backend,
        fallback_reason=result.fallback_reason or '', provider_lead_proposal=proposed or '',
        selected_lead=result.selection.lead_module, effective_lead=plan['lead_module'] or 'BANK_REVIEW',
        override_reason=plan['selection_status'] if plan['selection_status'] == 'financial_eligibility_override' else '',
        api_calls=result.api_calls,
        parse_outcome='accepted' if result.api_calls and not result.fallback_used else 'rejected' if result.invalid_outputs else 'not_attempted',
        ledger_hash=digest(finance_snapshot(plan)), result='passed')


@pytest.mark.parametrize('example', reviewed_examples(), ids=lambda e: e['case_id'])
def test_same_case_and_finance_across_mocked_backends(example, monkeypatch, record_provider_evidence):
    configured_keys(monkeypatch)
    case = build_case(profile_from_engine(example['customer']), example['scenario'])
    baseline = build_plan(example)
    path = baseline['applied_plan']
    assert path['first_shortfall_month'] == example['expected_first']
    assert path['additional_cash_needed'] == example['expected_gap']
    assert path['funding_result_complete'] is example['complete']
    if example['case_id'] == 'recovery':
        assert baseline['recovery']['months_to_target'] == 14
    with classifier_boundary(lead=example['proposal']) as boundary:
        for backend in ('rules', 'jev', 'gemini'):
            result = select_plan(case, backend)
            assert result.requested_backend == backend and not result.fallback_used
            assert result.actual_backend == ('rule_baseline' if backend == 'rules' else backend)
            plan = build_plan(example, result)
            assert plan['lead_module'] == example['effective']
            row = classification_row(example['case_id'], example['expected'], result, plan,
                                     example['proposal'] if backend != 'rules' else None, baseline)
            record_provider_evidence(row)
        assert boundary.inputs['jev'] == boundary.inputs['gemini'] == [case.model_dump(mode='json')]


@pytest.mark.parametrize('backend', ['jev', 'gemini'])
@pytest.mark.parametrize('handling', ['missing_credentials', 'timeout', 'provider_failure',
                                    'malformed', 'unsupported', 'ineligible', 'success'])
def test_classification_fault_matrix(backend, handling, monkeypatch, record_provider_evidence):
    if handling != 'missing_credentials':
        configured_keys(monkeypatch)
    example = reviewed_examples()[1]
    case = build_case(profile_from_engine(example['customer']), example['scenario'])
    baseline = build_plan(example)
    lead = 'M6' if handling == 'ineligible' else 'M1'
    with classifier_boundary(handling=handling, lead=lead) as boundary:
        result = select_plan(case, backend)
        if handling in ('success', 'ineligible'):
            assert result.actual_backend == backend and not result.fallback_used
            assert result.api_calls == 1
        else:
            assert result.actual_backend == 'rule_baseline' and result.fallback_used
            expected_failures = {
                'missing_credentials': ('missing_openrouter_api_key', 'missing_gemini_api_key'),
                'timeout': ('jev_transport_error', 'gemini_api_error'),
                'provider_failure': ('jev_transport_error', 'gemini_api_error'),
                'malformed': ('invalid_jev_response', 'gemini_invalid_json'),
                'unsupported': ('invalid_jev_response', 'gemini_schema_mismatch'),
            }
            assert result.fallback_reason == expected_failures[handling][backend == 'gemini']
            assert result.api_calls == (0 if handling == 'missing_credentials' else 2)
        if handling == 'missing_credentials':
            assert boundary.factory.call_count == boundary.transport.call_count == 0
        plan = build_plan(example, result)
        assert plan['lead_module'] == 'M1'
        if handling == 'ineligible':
            assert plan['selection_status'] == 'financial_eligibility_override'
            assert plan['classification']['actual_backend'] == backend
        assert 'PRIVATE' not in result.model_dump_json()
        proposal = 'M99' if handling == 'unsupported' else lead if handling in ('success', 'ineligible') else None
        row = classification_row('income_'+handling, 'Local fallback on invalid/unavailable output; validate any accepted module.',
                                 result, plan, proposal, baseline)
        record_provider_evidence(row)


def test_unsupported_reason_is_rejected(monkeypatch, record_provider_evidence):
    configured_keys(monkeypatch)
    example = reviewed_examples()[1]
    case = build_case(profile_from_engine(example['customer']), example['scenario'])
    with classifier_boundary('unsupported_reason'):
        result = select_plan(case, 'gemini')
    assert result.fallback_reason == 'gemini_unsupported_reason_codes'
    plan = build_plan(example, result)
    record_provider_evidence(classification_row('income_unsupported_reason',
        'Reject reasons not established by source facts.', result, plan, 'M1', build_plan(example)))


EXPLANATIONS = {
    'valid': '{"focus_ids":["pause","gap"]}',
    'amount': '{"focus_ids":["gap"],"amount":99999}',
    'action': '{"focus_ids":["pause"],"action":"Take a new loan"}',
    'promise': '{"focus_ids":["gap"],"promise":"Guaranteed recovery"}',
    'embedded_claim': '{"focus_ids":["Invest CAD 99999 with guaranteed returns"]}',
    'malformed': 'invalid JSON',
    'failure': None,
    'missing_credentials': None,
}


@pytest.mark.parametrize('handling', EXPLANATIONS)
def test_explanations_are_independent_of_accepted_finance(handling, record_provider_evidence):
    example = reviewed_examples()[2]
    plan = build_plan(example)
    original = deepcopy(plan)
    client = Mock()
    client.models.generate_content.return_value = SimpleNamespace(text=EXPLANATIONS[handling])
    if handling == 'failure':
        client.models.generate_content.side_effect = TimeoutError('PRIVATE synthetic key')
    # Even missing credentials patches the factory so regressions cannot make real calls.
    with patch('google.genai.Client', return_value=client) as factory:
        result = explain_plan(plan, backend='gemini', **({} if handling == 'missing_credentials' else {'client': client}))
    assert factory.call_count == 0
    assert result['requested_backend'] == 'gemini'
    assert result['actual_backend'] == ('gemini' if handling == 'valid' else 'local')
    assert result['api_calls'] == (0 if handling == 'missing_credentials' else 1)
    assert result['cards'] == original['advice']['cards']
    assert plan == original
    assert 'PRIVATE' not in json.dumps(result) and '99999' not in json.dumps(result)
    if handling == 'valid':
        assert result['fallback_reason'] is None
    else:
        assert result['fallback_reason']
    record_provider_evidence(dict(case_id='compound_explanation_'+handling,
        normalized_case_hash=plan['classification_input_hash'], route='explanation',
        expected_handling='Optional emphasis may select approved facts only; preserve every local fact and the ledger.',
        evidence_mode='mocked', requested_backend=result['requested_backend'], actual_backend=result['actual_backend'],
        fallback_reason=result['fallback_reason'] or '', provider_lead_proposal='', selected_lead='',
        effective_lead=plan['lead_module'], override_reason='', api_calls=result['api_calls'],
        parse_outcome='accepted' if handling == 'valid' else 'not_attempted' if handling in ('failure', 'missing_credentials') else 'rejected',
        ledger_hash=digest(finance_snapshot(plan)), result='passed'))
