"""Every remote button is deliberate; cache state belongs to the current session."""
import json
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
import pytest
from streamlit.testing.v1 import AppTest
from plan_classification import config
from plan_classification.request_log import LOG_PATH
from provider_controls import request_identity


@pytest.fixture(autouse=True)
def fake_settings(tmp_path,monkeypatch,provider_configuration):
    file=tmp_path/'.env'
    file.write_text('GEMINI_API_KEY=synthetic-local-key\nOPENROUTER_API_KEY=synthetic-local-openrouter\n')
    monkeypatch.setattr(config,'ENV_FILE',file)
    monkeypatch.setattr('plan_classification.request_log.LOG_PATH',tmp_path/'requests.jsonl')
    return file


def test_app_changes_and_cold_launch_never_call_remote_clients():
    root=Path(__file__).resolve().parents[1]
    with patch('google.genai.Client',side_effect=AssertionError('No explicit provider action')) as client, \
         patch('plan_classification.backends.requests.post',side_effect=AssertionError('No explicit provider action')) as post:
        app=AppTest.from_file(str(root/'app.py'),default_timeout=120).run()
        assert not app.exception
        app.number_input(key='account_selector').set_value(22812).run()
        app.slider(key='slider_income_mult').set_value(.55).run()
        app.text_input(key='judge_event').set_value('PRIVATE-NOTE').run()
        app.selectbox(key='classification_backend').set_value('Gemini').run()
        app.run() # rerun/tab navigation is passive
        assert not app.exception
        assert client.call_count==post.call_count==0


DAILY='''
import streamlit as st
from provider_controls import daily_advisor_control
cash=st.number_input('Cash need',value=1500.,key='cash')
advice=daily_advisor_control(dict(shock_type='compound',days_to_shortfall=5,cash_needed=cash,
    has_bill_to_shift=True,has_one_off=True), account_id=17, normalized_case='synthetic-case',scenario_hash='synthetic-scenario')
st.caption('Actual: '+advice['actual_backend'])
'''


def test_daily_button_is_explicit_cached_model_aware_and_session_local(fake_settings):
    client=__import__('unittest.mock',fromlist=['Mock']).Mock()
    client.models.generate_content.return_value=SimpleNamespace(text='{"primary_action_id":"move_recurring_bill"}')
    with patch('gemini_advisor.genai.Client') as factory:
        factory.return_value.__enter__.return_value=client
        app=AppTest.from_string(DAILY).run()
        assert factory.call_count==0
        app.button(key='daily_advisor_run').click().run()
        assert factory.call_count==1
        app.run()
        assert factory.call_count==1 and any('Actual: gemini' in c.value for c in app.caption)
        # Other sessions never reuse this session's successful result.
        second=AppTest.from_string(DAILY).run()
        assert factory.call_count==1 and any('Actual: local' in c.value for c in second.caption)
        app.number_input(key='cash').set_value(1600.).run()
        assert factory.call_count==1 and any('Actual: local' in c.value for c in app.caption)
        app.button(key='daily_advisor_run').click().run()
        assert factory.call_count==2
        fake_settings.write_text('GEMINI_API_KEY=synthetic-local-key\nGEMINI_ADVISOR_MODEL=gemini-other-model\n')
        app.run()
        assert factory.call_count==2 and any('Actual: local' in c.value for c in app.caption)


def test_cache_identity_changes_with_model_without_containing_key(fake_settings):
    before=request_identity('explanation',{'normalized_case':'synthetic-case','facts':'approved-facts'})
    fake_settings.write_text('GEMINI_API_KEY=synthetic-key\nGEMINI_EXPLANATION_MODEL=gemini-other-model\n')
    after=request_identity('explanation',{'normalized_case':'synthetic-case','facts':'approved-facts'})
    assert before!=after
    assert 'synthetic-key' not in repr(after)


EXPLANATION='''
import streamlit as st
from test_tailored_advice import plan
from provider_controls import explanation_control
p=plan()
account=st.number_input('Account',value=17,key='account')
out=explanation_control(p,account)
st.caption('Actual: '+out['actual_backend'])
'''


def test_explanation_button_cache_and_session_are_separate_from_classifier(fake_settings):
    from unittest.mock import Mock
    client=Mock();client.models.generate_content.return_value=SimpleNamespace(text='{"focus_ids":["gap"]}')
    with patch('google.genai.Client',return_value=client) as factory:
        first=AppTest.from_string(EXPLANATION).run()
        assert not first.exception and factory.call_count==0
        first.button(key='tailored_explain').click().run()
        assert factory.call_count==1 and any('Actual: gemini' in c.value for c in first.caption)
        first.run()
        assert factory.call_count==1
        second=AppTest.from_string(EXPLANATION).run()
        assert factory.call_count==1 and any('Actual: local' in c.value for c in second.caption)
        first.number_input(key='account').set_value(18).run()
        assert factory.call_count==1 and any('Actual: local' in c.value for c in first.caption)
        first.button(key='tailored_explain').click().run()
        assert factory.call_count==2
        fake_settings.write_text('GEMINI_API_KEY=synthetic-local-key\nGEMINI_EXPLANATION_MODEL=gemini-other-model\n')
        first.run()
        assert factory.call_count==2 and any('Actual: local' in c.value for c in first.caption)


def test_classifier_cache_tracks_model_and_override_edits_without_calls(fake_settings):
    from unittest.mock import Mock
    client=Mock()
    client.models.generate_content.return_value=SimpleNamespace(text=json.dumps(dict(
        lead_module='M1',reason_codes=['income_reduction'],rationale='Income reduced.')),
        model_version='gemini-3.5-flash-lite')
    panel='''
import engine
from plan_classification.ui import render_classification
render_classification(engine.know_customer(22812),.55,0.,0.)
'''
    with patch('google.genai.Client',return_value=client) as factory:
        first=AppTest.from_string(panel).run()
        first.selectbox(key='classification_backend').set_value('Gemini').run()
        assert factory.call_count==0
        first.button(key='classification_run').click().run()
        assert factory.call_count==1 and any('M1 — Income Continuity' in m.value for m in first.markdown)
        first.run()
        assert factory.call_count==1
        first.text_input(key='classification_gemini_key').set_value('synthetic-override').run()
        assert factory.call_count==1 and not any('M1 — Income Continuity' in m.value for m in first.markdown)
        first.button(key='classification_run').click().run()
        assert factory.call_count==2
        fake_settings.write_text('GEMINI_API_KEY=synthetic-local-key\nGEMINI_CLASSIFIER_MODEL=gemini-other-model\n')
        first.run()
        assert factory.call_count==2 and not any('M1 — Income Continuity' in m.value for m in first.markdown)
        second=AppTest.from_string(panel).run()
        assert factory.call_count==2 and 'classification_result' not in second.session_state


def test_bad_settings_do_not_block_cold_app_or_explicit_classifier_fallback(fake_settings):
    fake_settings.write_text('GEMINI_API_KEY="synthetic-unclosed\n')
    root=Path(__file__).resolve().parents[1]
    with patch('google.genai.Client',side_effect=AssertionError('Must remain local')) as factory:
        app=AppTest.from_file(str(root/'app.py'),default_timeout=120).run()
        assert not app.exception and factory.call_count==0
        app.selectbox(key='classification_backend').set_value('Gemini').run()
        app.button(key='classification_run').click().run()
        assert not app.exception and factory.call_count==0
        result=app.session_state['classification_result'][1]
        assert result['actual_backend']=='rule_baseline' and result['fallback_reason']=='invalid_provider_settings'


def test_cache_identity_accepts_native_and_numpy_replay_scalars():
    import numpy as np
    assert request_identity('daily',{'bill':True,'days':5,'cash':1500.})==request_identity(
        'daily',{'bill':np.bool_(True),'days':np.int64(5),'cash':np.float64(1500.)})
