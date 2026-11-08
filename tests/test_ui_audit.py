"""Guided scenario editing and full-app integration, with external services disabled."""
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from plan_classification.ui import EFFECT_INPUTS

PANEL = '''
import engine
from plan_classification.ui import render_classification
render_classification(engine.know_customer(22812), .55, .15, 0)
'''


def guided_app():
    app = AppTest.from_string(PANEL).run(timeout=15)
    app.radio(key='classification_input_mode').set_value('Guided scenario editor').run(timeout=15)
    assert not app.exception
    return app


def test_guided_compound_scenario_and_removal():
    app = guided_app()
    app.selectbox(key='classification_guided_duration_mode').select('Known duration').run(timeout=15)
    app.number_input(key='classification_guided_duration').set_value(6).run(timeout=15)
    app.button(key='classification_guided_add').click().run(timeout=15)
    app.selectbox(key='classification_guided_type').select('household_bills_percent').run(timeout=15)
    app.selectbox(key='classification_guided_duration_mode').select('Ongoing (confirmed)').run(timeout=15)
    app.button(key='classification_guided_add').click().run(timeout=15)
    assert not app.exception
    effects = app.session_state['classification_guided_effects']
    assert len(effects) == 2
    assert effects[0]['duration_months'] == 6
    assert effects[1]['ongoing'] is True
    app.button(key='classification_run').click().run(timeout=15)
    result = app.session_state['classification_result'][1]
    assert result['selection']['lead_module'] == 'M5'
    assert result['selection']['needs_clarification'] == []
    app.button(key='classification_guided_remove_1').click().run(timeout=15)
    assert len(app.session_state['classification_guided_effects']) == 1
    assert not any('M5 — Multi-Shock Stabilization' in el.value for el in app.markdown)
    app.button(key='classification_run').click().run(timeout=15)
    assert app.session_state['classification_result'][1]['selection']['lead_module'] == 'M1'
    app.button(key='classification_guided_clear').click().run(timeout=15)
    assert not app.session_state['classification_guided_effects']
    assert not app.exception


@pytest.mark.parametrize('kind', list(EFFECT_INPUTS))
def test_every_effect_type_can_be_entered_without_json(kind):
    app = guided_app()
    app.selectbox(key='classification_guided_type').select(kind).run(timeout=15)
    app.button(key='classification_guided_add').click().run(timeout=15)
    assert not app.exception and not app.error
    effects = app.session_state['classification_guided_effects']
    assert len(effects) == 1
    assert effects[0]['type'] == kind
    if kind in {'one_off_cost', 'one_off_receipt'}:
        assert effects[0]['start_month'] == 0
        assert effects[0]['duration_months'] is None
        assert effects[0]['ongoing'] is False


def test_guided_unknown_amount_and_duration_preserved():
    app = guided_app()
    app.checkbox(key='classification_guided_value_unknown').check().run(timeout=15)
    app.button(key='classification_guided_add').click().run(timeout=15)
    effect = app.session_state['classification_guided_effects'][0]
    assert effect['value'] is None
    assert effect['duration_months'] is None
    assert effect['ongoing'] is False
    app.button(key='classification_run').click().run(timeout=15)
    assert app.session_state['classification_result'][1]['selection']['needs_clarification']
    assert not app.exception


def test_guided_edits_do_not_call_a_provider(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Editing a scenario must never classify or call a provider.')
    monkeypatch.setattr('plan_classification.ui.select_plan', forbidden)
    app = guided_app()
    app.selectbox(key='classification_backend').select('Jev (OpenRouter)').run(timeout=15)
    app.text_input(key='classification_openrouter_key').set_value('test-only-key').run(timeout=15)
    app.selectbox(key='classification_guided_type').select('one_off_receipt').run(timeout=15)
    app.number_input(key='classification_guided_value_one_off_receipt').set_value(5000).run(timeout=15)
    app.button(key='classification_guided_add').click().run(timeout=15)
    app.number_input(key='classification_guided_horizon').set_value(12).run(timeout=15)
    app.selectbox(key='classification_guided_phase').select('recovery').run(timeout=15)
    assert not app.exception
    assert len(app.session_state['classification_guided_effects']) == 1


def test_guided_duplicate_is_not_added():
    app = guided_app()
    app.button(key='classification_guided_add').click().run(timeout=15)
    app.button(key='classification_guided_add').click().run(timeout=15)
    assert len(app.session_state['classification_guided_effects']) == 1
    assert app.error and not app.exception


def test_guided_edit_hides_previous_result():
    app = guided_app()
    app.selectbox(key='classification_guided_type').select('one_off_receipt').run(timeout=15)
    app.button(key='classification_guided_add').click().run(timeout=15)
    app.button(key='classification_run').click().run(timeout=15)
    assert any('M8 — Surplus & Windfall Allocation' in el.value for el in app.markdown)
    app.number_input(key='classification_guided_value_one_off_receipt').set_value(2000).run(timeout=15)
    assert not any('M8 — Surplus & Windfall Allocation' in el.value for el in app.markdown)
    # An unsaved draft does not silently change the listed scenario.
    assert app.session_state['classification_guided_effects'][0]['value'] == 1000
    assert not app.exception


def test_full_app_classification_offline(monkeypatch):
    import gemini_advisor

    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    monkeypatch.delenv('OPENROUTER_API_KEY', raising=False)
    original_advisor = gemini_advisor.consult_gemini_advisor

    def offline_advisor(*args, **kwargs):
        kwargs['api_key'] = None
        return original_advisor(*args, **kwargs)

    # Classifier requests require Classify scenario. The daily advisor defaults
    # to local rules and requires its own explicit button for a remote request.
    with patch.object(gemini_advisor, 'HAVE_GOOGLE_GENAI', False), \
         patch.object(gemini_advisor, 'consult_gemini_advisor', side_effect=offline_advisor):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py')).run(timeout=30)
        assert not app.exception
        app.button(key='classification_run').click().run(timeout=30)
        assert not app.exception
        assert app.session_state['classification_result'][1]['actual_backend'] == 'rule_baseline'
        assert app.session_state['classification_result'][1]['api_calls'] == 0


def test_guided_scenario_survives_input_mode_switch():
    app = guided_app()
    app.selectbox(key='classification_guided_phase').select('recovery').run(timeout=15)
    app.number_input(key='classification_guided_horizon').set_value(12).run(timeout=15)
    app.text_input(key='classification_guided_note').set_value('Recovery after a repair').run(timeout=15)
    app.selectbox(key='classification_guided_type').select('one_off_receipt').run(timeout=15)
    app.button(key='classification_guided_add').click().run(timeout=15)
    app.radio(key='classification_input_mode').set_value('Current shock controls').run(timeout=15)
    app.radio(key='classification_input_mode').set_value('Guided scenario editor').run(timeout=15)
    assert app.selectbox(key='classification_guided_phase').value == 'recovery'
    assert app.number_input(key='classification_guided_horizon').value == 12
    assert app.text_input(key='classification_guided_note').value == 'Recovery after a repair'
    assert len(app.session_state['classification_guided_effects']) == 1
    assert not app.exception


def test_guided_normal_phase_with_existing_shock_is_editable_error():
    app = guided_app()
    app.selectbox(key='classification_guided_type').select('one_off_cost').run(timeout=15)
    app.button(key='classification_guided_add').click().run(timeout=15)
    app.selectbox(key='classification_guided_phase').select('normal').run(timeout=15)
    assert app.error and not app.exception
    assert len(app.session_state['classification_guided_effects']) == 1
    app.button(key='classification_guided_remove_0').click().run(timeout=15)
    assert not app.error and not app.exception
    assert not app.session_state['classification_guided_effects']
    app.button(key='classification_run').click().run(timeout=15)
    assert not app.exception
    assert app.session_state['classification_result'][1]['actual_backend'] == 'rule_baseline'
