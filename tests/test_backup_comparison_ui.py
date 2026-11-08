"""Backup chart and summary must follow the same live app inputs."""
import json
from pathlib import Path
from streamlit.testing.v1 import AppTest
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


def test_exact_compound_example_on_streamlit_screen():
    panel='''
from backup_comparison import render_backup_comparison
from test_backup_comparison import compound_plan
render_backup_comparison(compound_plan(True))
'''
    # Use the real renderer and engine with explicit synthetic case inputs.
    import sys
    tests=str(Path(__file__).resolve().parent)
    if tests not in sys.path:sys.path.insert(0,tests)
    view=AppTest.from_string(panel).run(timeout=30)
    assert not view.exception
    assert metric(view,'First shortfall · without new action')=='Month 2 (end)'
    assert metric(view,'First shortfall · revised plan')=='Month 3 (end)'
    assert metric(view,'Extra cash needed · without new action')=='CAD 3,360.00'
    assert metric(view,'Extra cash needed · revised plan')=='CAD 1,560.00'
