"""Exercise real Streamlit labels and session invalidation with blocked transports."""
from copy import deepcopy
from unittest.mock import Mock, patch
from types import SimpleNamespace

import pytest
from streamlit.testing.v1 import AppTest

from provider_test_support import reviewed_examples, build_plan, classifier_boundary, digest, finance_snapshot
from test_provider_fallback_evidence import (classification_row, configured_keys, EXPLANATIONS,
                                              prohibit_network)


PANEL = '''
import streamlit as st
from provider_test_support import reviewed_examples
from plan_classification.ui import render_classification
repair = st.number_input('Repair', value=0., key='repair')
st.text_input('Local analyst note', key='local_note')
example = reviewed_examples()[1]
handoff = render_classification(example['customer'], .55, 0., repair)
st.session_state['current_handoff'] = handoff
'''


@pytest.mark.parametrize('backend,choice,handling', [('rules', 'Local baseline', 'success')] + [
    (backend, choice, handling)
    for backend, choice in [('jev', 'Jev (OpenRouter)'), ('gemini', 'Gemini')]
    for handling in ['missing_credentials', 'timeout', 'provider_failure', 'malformed', 'unsupported', 'success']])
def test_classifier_labels_and_case_isolation(backend, choice, handling, monkeypatch, tmp_path, record_provider_evidence):
    if handling != 'missing_credentials':
        configured_keys(monkeypatch)
    monkeypatch.setattr('plan_classification.request_log.LOG_PATH', tmp_path/'classification.jsonl')
    with classifier_boundary(handling) as boundary:
        app = AppTest.from_string(PANEL, default_timeout=30).run()
        app.selectbox(key='classification_backend').select(choice).run()
        assert not app.exception
        assert boundary.transport.call_count == boundary.factory.call_count == 0
        app.button(key='classification_run').click().run()
        result = deepcopy(app.session_state['current_handoff']['selection_result'])
        assert not app.exception and result is not None
        expected_actual = backend if handling == 'success' and backend != 'rules' else 'rule_baseline'
        assert result['requested_backend'] == backend and result['actual_backend'] == expected_actual
        assert any(f'Source: {expected_actual} · requested: {backend}' in c.value for c in app.caption)
        assert any('Module proposal only.' in c.value for c in app.caption)
        if result['fallback_used']:
            assert any(f"{choice} unavailable ({result['fallback_reason']}). Showing the local baseline." == w.value for w in app.warning)
        else:
            assert not any('unavailable (' in w.value for w in app.warning)
        count = (boundary.transport.call_count, boundary.client.models.generate_content.call_count)
        assert result['api_calls'] == sum(count)
        app.run()
        app.text_input(key='local_note').set_value('Changed local note').run()
        assert count == (boundary.transport.call_count, boundary.client.models.generate_content.call_count)
        assert app.session_state['current_handoff']['selection_result'] == result
        # Same account, materially different normalized scenario: no stale answer.
        app.number_input(key='repair').set_value(1000.).run()
        assert app.session_state['current_handoff']['selection_result'] is None
        assert not any(c.value.startswith('Source: ') for c in app.caption)
        assert count == (boundary.transport.call_count, boundary.client.models.generate_content.call_count)
        app.button(key='classification_run').click().run()
        assert app.session_state['current_handoff']['selection_result']['input_hash'] != result['input_hash']
        assert not app.exception
    from plan_classification.schemas import SelectionResult
    parsed = SelectionResult.model_validate(result)
    example = reviewed_examples()[1]
    plan = build_plan(example, result)
    record_provider_evidence({**classification_row('income_ui_'+handling,
        'Show requested and actual routes, label fallback, invalidate changed case without remote calls.',
        parsed, plan, 'M99' if handling == 'unsupported' else 'M1' if handling == 'success' and backend != 'rules' else None,
        build_plan(example)), 'route': 'classification_ui'})


EXPLANATION_PANEL = '''
import streamlit as st
from plan_classification import ShockScenario
from provider_controls import render_explanation
from provider_test_support import reviewed_examples, build_plan
extra = st.number_input('Repair increase', value=0., key='extra')
st.text_input('Local note', key='note')
example = reviewed_examples()[2]
data = example['scenario'].model_dump()
data['effects'][0]['value'] += extra
example['scenario'] = ShockScenario.model_validate(data)
plan = build_plan(example)
st.session_state['accepted_plan'] = plan
st.session_state['displayed_explanation'] = render_explanation(plan, 17)
'''


@pytest.mark.parametrize('handling', EXPLANATIONS)
def test_explanation_card_keeps_all_facts_and_labels_optional(handling, monkeypatch, record_provider_evidence):
    if handling != 'missing_credentials':
        configured_keys(monkeypatch)
    client = Mock()
    client.models.generate_content.return_value = SimpleNamespace(text=EXPLANATIONS[handling])
    if handling == 'failure':
        client.models.generate_content.side_effect = TimeoutError('PRIVATE response')
    with patch('google.genai.Client', return_value=client) as factory:
        app = AppTest.from_string(EXPLANATION_PANEL, default_timeout=30).run()
        plan = deepcopy(app.session_state['accepted_plan'])
        assert factory.call_count == 0
        app.button(key='tailored_explain').click().run()
        assert not app.exception
        result = app.session_state['displayed_explanation']
        assert result['actual_backend'] == ('gemini' if handling == 'valid' else 'local')
        assert result['requested_backend'] == 'gemini'
        assert any('Optional explanation emphasis only.' in c.value for c in app.caption)
        assert any(f"Explanation emphasis: {result['actual_backend']} · requested: gemini" in c.value for c in app.caption)
        if handling != 'valid':
            assert any(f"local fallback: {result['fallback_reason']}" in c.value for c in app.caption)
        shown = [m.value for m in app.markdown] + [m.value for m in app.info]
        assert all(text in shown for text in plan['advice']['cards'].values())
        current = deepcopy(app.session_state['accepted_plan'])
        previous = deepcopy(plan)
        # The normal rerun measures classification latency again; every fact,
        # decision and financial amount must still match exactly.
        current['classification'].pop('elapsed_ms')
        previous['classification'].pop('elapsed_ms')
        assert current == previous
        count = factory.call_count
        app.run()
        app.text_input(key='note').set_value('Local-only note edit').run()
        assert factory.call_count == count
        assert app.session_state['displayed_explanation'] == result
        app.number_input(key='extra').set_value(100.).run()
        assert factory.call_count == count
        updated = app.session_state['displayed_explanation']
        assert updated['actual_backend'] == updated['requested_backend'] == 'local'
        assert updated['fingerprint'] != result['fingerprint']
        assert updated['focus_ids'] == []
    record_provider_evidence(dict(case_id='compound_explanation_ui_'+handling,
        normalized_case_hash=plan['classification_input_hash'], route='explanation_ui',
        expected_handling='Label optional emphasis; display all local facts and invalidate on changed scenario.',
        evidence_mode='mocked', requested_backend=result['requested_backend'], actual_backend=result['actual_backend'],
        fallback_reason=result['fallback_reason'] or '', provider_lead_proposal='', selected_lead='',
        effective_lead=plan['lead_module'], override_reason='', api_calls=result['api_calls'],
        parse_outcome='accepted' if handling == 'valid' else 'not_attempted' if handling in ('failure', 'missing_credentials') else 'rejected',
        ledger_hash=digest(finance_snapshot(plan)), result='passed'))


def test_actual_backup_plan_labels_provider_override_without_changing_cash(monkeypatch, tmp_path):
    from pathlib import Path
    from test_crisis_ui import backup_cash_chart
    configured_keys(monkeypatch)
    monkeypatch.setattr('plan_classification.request_log.LOG_PATH', tmp_path/'classification.jsonl')
    with classifier_boundary(lead='M6') as boundary:
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'), default_timeout=120).run()
        app.slider(key='slider_income_mult').set_value(.55).run()
        before = backup_cash_chart(app)
        app.selectbox(key='classification_backend').select('Gemini').run()
        app.button(key='classification_run').click().run()
        assert not app.exception
        assert boundary.factory.call_count == 1
        assert any('Module proposal: M6 (gemini); effective financial response:' in c.value
                   and 'effective financial response: M6' not in c.value for c in app.caption)
        assert backup_cash_chart(app) == before
