"""Headless checks for the added panel; never call paid APIs or market feeds."""
from streamlit.testing.v1 import AppTest

PANEL = '''
import streamlit as st
import engine
from plan_classification.ui import render_classification
amount = st.number_input('Repair', value=0.0, key='test_repair')
render_classification(engine.know_customer(22812), .55, .15, amount)
'''


def test_panel_selection_and_stale_result_invalidation():
    app=AppTest.from_string(PANEL).run(timeout=15)
    assert not app.exception
    app.button(key='classification_run').click().run(timeout=15)
    assert not app.exception
    assert app.session_state['classification_result'][1]['selection']['lead_module']=='M5'
    assert any('M5 — Multi-Shock Stabilization' in el.value for el in app.markdown)
    app.number_input(key='test_repair').set_value(100000).run(timeout=15)
    assert not app.exception
    assert not any('M5 — Multi-Shock Stabilization' in el.value for el in app.markdown)
    app.button(key='classification_run').click().run(timeout=15)
    assert app.session_state['classification_result'][1]['selection']['lead_module']=='M3'


def test_panel_missing_key_is_visible_fallback(monkeypatch):
    monkeypatch.delenv('OPENROUTER_API_KEY',raising=False)
    app=AppTest.from_string(PANEL).run(timeout=15)
    app.selectbox(key='classification_backend').select('Jev (OpenRouter)').run(timeout=15)
    app.button(key='classification_run').click().run(timeout=15)
    assert not app.exception
    result=app.session_state['classification_result'][1]
    assert result['fallback_used'] and result['api_calls']==0
    assert any('missing_openrouter_api_key' in w.value for w in app.warning)


def test_panel_custom_invalid_and_unknown_scenarios():
    app=AppTest.from_string(PANEL).run(timeout=15)
    app.radio(key='classification_input_mode').set_value('Custom structured scenario').run(timeout=15)
    app.text_area(key='classification_scenario_json').set_value('not json').run(timeout=15)
    assert app.error and not app.exception
    app.text_area(key='classification_scenario_json').set_value(
        '{"effects":[{"type":"unspecified_event","value":null}]}').run(timeout=15)
    app.button(key='classification_run').click().run(timeout=15)
    assert app.warning and not app.exception
    assert app.session_state['classification_result'][1]['selection']['needs_clarification']
