"""Backup chart and summary must follow the same live app inputs."""
import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import engine
from test_crisis_execution import account, compound
from test_crisis_ui import app, backup_cash_chart, custom, metric
from test_advice_ui import add_schedule


def figure(app):
    chart = backup_cash_chart(app)
    assert chart is not None
    ledger = next(frame.value for frame in app.tabs[2].dataframe
                  if 'Without new action (CAD)' in frame.value.columns)
    for trace, column in zip(chart['data'], ['Without new action (CAD)', 'Revised plan (CAD)'], strict=True):
        assert trace['y'] == ledger[column].tolist()
        assert [row[:2] for row in trace['customdata']] == ledger[['Month', 'Phase']].values.tolist()
    return chart


@pytest.fixture
def synthetic_app(monkeypatch):
    real_customer = engine.know_customer

    def start(**inputs):
        customer = account(**inputs)
        customer['account_id'] = 20111
        customer['history'] = customer['history'].assign(account_id=20111)
        customer['baseline_runway'] = engine.calculate_runway(customer['B'], customer['baseline_gap'])

        def lookup(account_id, *args, **kwargs):
            if account_id == 20111:
                return customer
            return real_customer(account_id, *args, **kwargs)

        monkeypatch.setattr(engine, 'know_customer', lookup)
        monkeypatch.setattr('gemini_advisor.HAVE_GOOGLE_GENAI', False)
        view = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py'), default_timeout=120).run()
        assert not view.exception
        assert view.number_input(key='account_selector').value == 20111
        return view

    return start


def test_account_and_shock_changes_update_chart_and_summary_together(app):
    before=figure(app)['data'][0]['y']
    custom(app,{'effects':[dict(type='income_multiplier',value=0.,duration_months=6)]})
    shocked=figure(app)
    assert shocked['data'][0]['y']!=before
    assert 'Month' in metric(app,'First shortfall · without new action')
    add_schedule(app)
    revised=figure(app)
    assert revised['data'][0]['y']==shocked['data'][0]['y']
    assert revised['data'][1]['y']!=revised['data'][0]['y']
    assert any('6 supported transfer pauses' in m.value for m in app.markdown)
    app.number_input(key='account_selector').set_value(20111).run()
    assert not app.exception
    changed=figure(app)
    assert changed['data'][0]['y']!=revised['data'][0]['y']
    assert any('No evidenced existing-transfer schedule' in m.value for m in app.markdown)


def test_unknown_event_is_a_partial_chart_with_open_full_need(app):
    custom(app,{'effects':[dict(type='unspecified_event')]})
    assert not app.exception
    assert metric(app,'Extra cash needed · without new action')=='Not established'
    assert metric(app,'Extra cash needed · revised plan')=='Not established'
    assert figure(app)['layout']['title']['text'] == 'Known components'
    assert all('Known components' in trace['hovertemplate'] for trace in figure(app)['data'])
    assert any('Full funding need: Not established' in m.value for m in app.warning)
    assert any('Enter the cash impact and when it happens' in m.value for m in app.tabs[2].markdown)


def test_unsupported_pause_and_identical_paths_have_explanation(app):
    custom(app,{'effects':[dict(type='income_multiplier',value=0.,duration_months=6)]})
    add_schedule(app,fee=None)
    assert not app.exception
    fig=figure(app)
    assert fig['data'][0]['y']==fig['data'][1]['y']
    assert any('No existing-transfer pause is applied' in m.value for m in app.markdown)
    assert any('Confirm the pause fee, including zero if confirmed' in m.value for m in app.markdown)
    assert any('two cash paths are identical' in m.value for m in app.markdown)
    assert any('Full projection ledger' in e.label for e in app.expander)


def test_chart_updates_for_dated_edit_note_and_preset(app):
    baseline = figure(app)['data'][0]['y']
    receipt = {'type': 'one_off_receipt', 'value': 400., 'start_month': 7}
    custom(app, {'effects': [receipt]})
    assert figure(app)['data'][0]['y'] == baseline
    assert any('Scheduled for Month 7: one off receipt' in c.value for c in app.tabs[2].caption)
    assert metric(app, 'Extra cash needed · without new action') != 'Not established'

    receipt['start_month'] = 1
    app.text_area(key='classification_scenario_json').set_value(json.dumps({'effects': [receipt]})).run()
    dated = figure(app)['data'][0]['y']
    assert dated[2] == baseline[2] + 400.
    assert not any('Scheduled for Month 7' in c.value for c in app.tabs[2].caption)

    app.text_input(key='judge_event').set_value('Income changes').run()
    partial = figure(app)
    assert partial['data'][0]['y'] == dated
    assert partial['layout']['title']['text'] == 'Known components'
    assert metric(app, 'Extra cash needed · without new action') == 'Not established'

    app.text_input(key='judge_event').set_value('')
    next(b for b in app.button if 'Layoff (EI 55%)' in b.label).click().run()
    assert figure(app)['data'][0]['y'] != dated
    assert any('Official Shock Runway' in m.value for m in app.tabs[1].markdown)


def test_exact_compound_example_on_streamlit_screen(synthetic_app):
    view = synthetic_app()
    custom(view, compound().model_dump(mode='json'))
    shock_only = figure(view)['data'][0]['y']
    assert shock_only[1::2] == [1500., 690., -120., -930., -1740., -2550., -3360.]
    assert figure(view)['data'][1]['y'] == shock_only
    schedule = next(frame.value for frame in view.tabs[2].dataframe
                    if 'Money in (CAD)' in frame.value.columns)
    assert schedule.loc[1, 'Money in (CAD)'] == 1650.
    assert schedule.loc[1, 'Money out (CAD)'] == 2460.

    add_schedule(view)
    shock, applied = figure(view)['data']
    assert shock['y'] == shock_only
    assert applied['y'][1::2] == [1500., 990., 480., -30., -540., -1050., -1560.]
    assert metric(view, 'First shortfall · without new action') == 'Month 2 (end)'
    assert metric(view, 'First shortfall · revised plan') == 'Month 3 (end)'
    assert metric(view, 'Extra cash needed · without new action') == 'CAD 3,360.00'
    assert metric(view, 'Extra cash needed · revised plan') == 'CAD 1,560.00'


def test_late_receipt_distinguishes_first_shortfall_and_full_need(synthetic_app):
    view = synthetic_app(income=1800., spending=2400., cash=1000.)
    custom(view, {'effects': [dict(type='one_off_receipt', start_month=3, value=2000.)]})
    shock, applied = figure(view)['data']
    assert shock['y'][3::2] == [400., -200., 1200., 600., 0., -600.]
    assert shock['y'][6] == 1800.
    assert 'One-off receipt: CAD 2,000.00' in shock['customdata'][6][2]
    assert applied['y'] == shock['y']
    assert metric(view, 'First shortfall · without new action') == 'Month 2 (end)'
    assert any(c.value == 'Cash missing at first shortfall: CAD 200.00' for c in view.tabs[2].caption)
    assert metric(view, 'Extra cash needed · without new action') == 'CAD 600.00'


def test_deferral_chart_with_and_without_inclusion_evidence(synthetic_app):
    view = synthetic_app(income=2200., spending=2400., cash=300.)
    deferral = dict(
        type='debt_payment_delta', value=-300., duration_months=2, debt_change_kind='deferral',
        repayment_month=4, repayment_amount=650., obligation_payment=300.,
        obligation_source='Synthetic loan schedule', payment_in_baseline=True,
    )
    custom(view, {'effects': [deferral]})
    shock, applied = figure(view)['data']
    assert shock['y'][3::2] == [400., 500., 300., -550., -750., -950.]
    assert shock['y'][8] == -350.
    assert 'Deferred loan repayment: CAD 650.00' in shock['customdata'][8][2]
    assert applied['y'] == shock['y']
    assert metric(view, 'First shortfall · without new action') == 'Month 4 (start)'
    assert metric(view, 'Extra cash needed · without new action') == 'CAD 950.00'

    deferral['payment_in_baseline'] = False
    view.text_area(key='classification_scenario_json').set_value(json.dumps({'effects': [deferral]})).run()
    partial = figure(view)
    assert partial['layout']['title']['text'] == 'Known components'
    for trace in partial['data']:
        assert trace['y'][3::2] == [100., -100., -300., -500., -700., -900.]
        assert trace['y'][8] == -300.
        assert all('Deferred loan repayment' not in row[2] for row in trace['customdata'])
    assert metric(view, 'Extra cash needed · without new action') == 'Not established'
    assert metric(view, 'Extra cash needed · revised plan') == 'Not established'
    assert any('Known components · extra cash: CAD 900.00' in c.value for c in view.tabs[2].caption)
