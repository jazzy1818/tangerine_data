"""Backup chart and summary must follow the same live app inputs."""
import json
from pathlib import Path
from streamlit.testing.v1 import AppTest
from test_crisis_ui import app,custom,metric
from test_advice_ui import add_schedule


def figure(app):
    # Plotly elements are transported as real JSON specs in the Streamlit runner.
    return next(json.loads(el.proto.spec) for el in app.get('plotly_chart') if 'cash before and after' in el.proto.spec)


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
    assert 'Partial projection' in figure(app)['layout']['title']['text']
    assert any('Full funding need: Not established' in m.value for m in app.warning)


def test_unsupported_pause_and_identical_paths_have_explanation(app):
    custom(app,{'effects':[dict(type='income_multiplier',value=0.,duration_months=6)]})
    add_schedule(app,fee=None)
    assert not app.exception
    fig=figure(app)
    assert fig['data'][0]['y']==fig['data'][1]['y']
    assert any('No existing-transfer pause is applied' in m.value and 'evidence incomplete' in m.value for m in app.markdown)
    assert any('two cash paths are identical' in m.value for m in app.markdown)
    assert any('Full projection ledger' in e.label for e in app.expander)


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
