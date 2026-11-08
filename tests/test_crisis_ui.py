"""The scenario editor, classifier and backup must describe the same case."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from streamlit.testing.v1 import AppTest

import engine
from plan_classification.schemas import ShockScenario

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture
def app():
    with patch('gemini_advisor.HAVE_GOOGLE_GENAI',False):
        view=AppTest.from_file(str(ROOT/'app.py'),default_timeout=120).run()
        view.number_input(key='account_selector').set_value(22812).run()
        assert not view.exception
        yield view


def metric(app,label):
    return next(m.value for m in app.metric if m.label==label)


def dollars(value):
    return float(value.replace('$','').replace(',',''))


def custom(app,scenario):
    app.radio(key='classification_input_mode').set_value('Custom structured scenario').run()
    app.text_area(key='classification_scenario_json').set_value(json.dumps(scenario)).run()
    assert not app.exception


def backup_cash_chart(app):
    return next((json.loads(chart.proto.spec) for chart in app.tabs[2].get('plotly_chart')
                 if chart.proto.id.endswith('-backup_cash_comparison')), None)


def test_backup_chart_uses_dated_checkpoints_and_posted_events(app):
    customer = engine.know_customer(22812)
    scenario = {'effects': [
        {'type': 'one_off_cost', 'value': round(customer['raw_B'], 2) + 100., 'start_month': 1},
        {'type': 'income_delta', 'value': 1000., 'ongoing': True},
        {'type': 'one_off_receipt', 'value': 200., 'start_month': 3},
        {'type': 'one_off_cost', 'value': 50., 'start_month': 4},
        {'type': 'debt_payment_delta', 'value': -100., 'start_month': 2, 'duration_months': 2,
         'debt_change_kind': 'deferral', 'repayment_month': 4, 'repayment_amount': 225.,
         'obligation_payment': 300., 'obligation_source': 'Synthetic test evidence',
         'payment_in_baseline': True},
    ]}
    custom(app, scenario)
    expected = engine.make_plan(customer, scenario=ShockScenario.model_validate(scenario))['crisis_plan']
    figure = backup_cash_chart(app)
    traces = {trace['name']: trace for trace in figure['data']}
    for label, key, dash in (('Shock only', 'no_action', 'dash'),
                             ('With supported actions', 'applied_plan', 'solid')):
        trace = traces[label]
        checkpoints = expected[key]['checkpoints']
        labels = [row[:2] for row in trace['customdata']]
        assert labels == [[p['month'], p['phase']] for p in checkpoints]
        assert trace['x'] == list(range(len(checkpoints)))
        assert trace['y'] == [p['cash'] for p in checkpoints]
        assert trace['line']['dash'] == dash
        first = labels.index([1, 'start'])
        assert trace['y'][first] == -100.
        assert trace['y'][first + 1] > 0.
        assert trace['marker']['symbol'][first] == 'diamond-open'
        assert 'One-off receipt: CAD 200.00' in trace['customdata'][labels.index([3, 'start'])][2]
        repayment = trace['customdata'][labels.index([4, 'start'])][2]
        assert 'Deferred loan repayment: CAD 225.00' in repayment
        assert 'One-off cost: CAD 50.00' in repayment
    assert figure['layout']['shapes'][0]['y0'] == figure['layout']['shapes'][0]['y1'] == 0
    assert metric(app,'First shortfall · without new action') == 'Month 1 (start)'
    assert metric(app,'Extra cash needed · without new action') == 'CAD 100.00'
    assert sum(c.value == 'Lowest modeled cash: CAD -100.00' for c in app.tabs[2].caption) == 2


def test_windfall_changes_classification_and_backup_once(app):
    before=dollars(metric(app,'Month 6 Closing Balance'))
    custom(app,{'effects':[{'type':'one_off_receipt','value':5000.,'start_month':0}]})
    after=dollars(metric(app,'Month 6 Closing Balance'))
    assert after-before==pytest.approx(5000.)
    app.button(key='classification_run').click().run()
    assert not app.exception
    assert app.session_state['classification_result'][1]['selection']['lead_module']=='M8'
    assert dollars(metric(app,'Month 6 Closing Balance'))==after
    app.run()
    assert dollars(metric(app,'Month 6 Closing Balance'))==after


def test_guided_income_drop_drives_backup_without_classify_click(app):
    app.radio(key='classification_input_mode').set_value('Guided scenario editor').run()
    app.selectbox(key='classification_guided_duration_mode').select('Known duration').run()
    app.number_input(key='classification_guided_duration').set_value(6).run()
    app.button(key='classification_guided_add').click().run()
    assert not app.exception
    expected=engine.simulate_6mo_trajectory(engine.know_customer(22812),income_multiplier=.55)
    assert dollars(metric(app,'Month 6 Closing Balance'))==pytest.approx(expected['month_6_balance'],abs=.05)
    app.button(key='classification_run').click().run()
    assert app.session_state['classification_result'][1]['selection']['lead_module']=='M1'
    assert not app.exception


def test_invalid_or_unknown_scenario_does_not_restore_old_slider_values(app):
    custom(app,{'effects':[{'type':'one_off_receipt','value':5000.,'start_month':0}]})
    receipt_balance=dollars(metric(app,'Month 6 Closing Balance'))
    app.text_area(key='classification_scenario_json').set_value('not json').run()
    assert not app.exception
    assert any('no stale slider scenario' in m.value for m in app.warning)
    assert backup_cash_chart(app) is None
    assert dollars(metric(app,'Month 6 Closing Balance (partial estimate)'))==pytest.approx(receipt_balance-5000.)
    assert any('quantified effects only' in m.value for m in app.warning)
    app.text_area(key='classification_scenario_json').set_value(json.dumps({'effects':[{'type':'income_multiplier','value':None}]})).run()
    assert not app.exception
    assert metric(app,'Month 1 Inflow')=='Not established'
    assert backup_cash_chart(app) is not None
    assert metric(app,'Extra cash needed · without new action') == 'Not established'
    assert metric(app,'Extra cash needed · revised plan') == 'Not established'


def test_recovery_phase_needs_checkpoint_and_then_shows_rebuild(app):
    custom(app,{'phase':'recovery','effects':[]})
    assert any('RECOVERY_UNVERIFIED' in str(m.value) for m in app.markdown)
    app.checkbox(key='recovery_supplied').check().run()
    app.text_input(key='recovery_month').set_value('2026-07')
    app.number_input(key='recovery_cash').set_value(3000.)
    app.number_input(key='recovery_income').set_value(3000.)
    app.number_input(key='recovery_spending').set_value(2400.)
    app.number_input(key='recovery_rate').set_value(300.)
    app.checkbox(key='recovery_stable').check()
    app.checkbox(key='recovery_covered').check().run()
    assert not app.exception
    assert any('14 months' in str(m.value) for m in app.markdown)
    assert any('REBUILDING' in str(m.value) for m in app.markdown)


def test_generic_delay_does_not_silently_show_old_daily_replay(app):
    custom(app,{'effects':[{'type':'payment_delay_days','value':5.,'duration_months':1}]})
    assert not app.exception
    assert any('No old slider scenario is substituted' in m.value for m in app.info)


def test_recovery_supported_without_inflow_then_unknown_rate_has_no_date(app):
    app.checkbox(key='recovery_supplied').check().run()
    app.text_input(key='recovery_month').set_value('2026-11')
    app.number_input(key='recovery_cash').set_value(3000.)
    app.number_input(key='recovery_spending').set_value(2400.)
    app.number_input(key='recovery_rate').set_value(300.)
    app.checkbox(key='recovery_stable').check()
    app.checkbox(key='recovery_covered').check().run()
    assert app.number_input(key='recovery_income').value is None
    assert not app.exception
    assert any('14 months' in str(m.value) for m in app.markdown)
    app.number_input(key='recovery_rate').set_value(None).run()
    assert not app.exception
    assert not any('14 months' in str(m.value) for m in app.markdown)
    assert any('Rebuild date not established' in str(m.value) for m in app.markdown)


def test_account_change_clears_account_specific_recovery(app):
    app.checkbox(key='recovery_supplied').check().run()
    app.number_input(key='recovery_cash').set_value(9000.).run()
    app.number_input(key='account_selector').set_value(20111).run()
    assert not app.exception
    assert not app.checkbox(key='recovery_supplied').value


def test_organizer_preset_switches_from_custom_back_to_controls(app):
    custom(app,{'effects':[{'type':'one_off_receipt','value':5000.,'start_month':0}]})
    next(button for button in app.button if 'Layoff (EI 55%)' in button.label).click().run()
    assert app.radio(key='classification_input_mode').value=='Current shock controls'
    assert not app.exception
