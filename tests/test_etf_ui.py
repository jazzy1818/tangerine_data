"""Full Streamlit app, with Yahoo completely mocked and engine outputs preserved."""
from copy import deepcopy
from unittest.mock import patch
import pandas as pd
import pytest
from test_crisis_ui import app,metric
from etf_market import get_history,MarketUnavailable


@pytest.fixture(autouse=True)
def no_implicit_market_network():
    get_history.clear()
    with patch('etf_market._download',side_effect=AssertionError('Market request before explicit consent')):
        yield
    get_history.clear()


def sample(values):
    end=pd.Timestamp.now(tz='UTC').tz_localize(None).normalize()
    return pd.DataFrame({'Adj Close':values},index=pd.date_range(end-pd.Timedelta(days=2),end))


def test_initial_load_and_etf_selection_make_no_market_requests(app):
    get_history.clear()
    before={m.label:m.value for m in app.metric}
    with patch('etf_market._download',side_effect=AssertionError('Network must not be used')) as network:
        app.selectbox(key='etf_symbol').select('VEQT.TO').run()
        assert not app.exception
        assert network.call_count==0
        after={m.label:m.value for m in app.metric}
        for key in ['Normal contributed','Shock contributed','Month 6 Closing Balance','Extra Starting Cash Needed']:
            assert before[key]==after[key]
    assert any('Fit review required' in c.value for c in app.caption)


def test_ticker_changes_history_without_changing_contributions(app):
    get_history.clear()
    with patch('etf_market._download',side_effect=lambda symbol,*args:sample([100,110,90] if symbol=='XEQT.TO' else [100,110,120])) as network:
        app.button(key='etf_show_history').click().run()
        assert not app.exception
        assert metric(app,'Historical illustration ending value')=='$900.00'
        before={m.label:m.value for m in app.metric}
        app.selectbox(key='etf_symbol').select('VEQT.TO').run()
        assert network.call_count==1
        app.button(key='etf_show_history').click().run()
        assert metric(app,'Historical illustration ending value')=='$1,200.00'
        after={m.label:m.value for m in app.metric}
        for label in ['Normal contributed','Shock contributed','Month 6 Closing Balance','Extra Starting Cash Needed']:
            assert before[label]==after[label]
        assert network.call_count==2
    get_history.clear()


def test_shock_and_display_controls_reuse_loaded_history(app):
    app.number_input(key='account_selector').set_value(49082).run()
    get_history.clear()
    with patch('etf_market._download',return_value=sample([100,110,90])) as network:
        app.button(key='etf_show_history').click().run()
        assert metric(app,'Shock contributed')!='$0.00'
        normal=metric(app,'Normal contributed')
        app.slider(key='slider_income_mult').set_value(0.).run()
        assert not app.exception
        assert metric(app,'Shock contributed')=='$0.00'
        assert metric(app,'Normal contributed')==normal
        assert metric(app,'Historical illustration ending value')=='$900.00'
        app.selectbox(key='etf_history_months').select(36).run()
        app.select_slider(key='etf_forward_horizon').set_value(3).run()
        app.selectbox(key='etf_market_move').select(-10).run()
        assert not app.exception and network.call_count==1
    get_history.clear()


def test_provider_failure_and_short_history_leave_local_forward_view(app):
    get_history.clear()
    normal=metric(app,'Normal contributed')
    with patch('etf_market._download',side_effect=MarketUnavailable('Synthetic provider outage')):
        app.button(key='etf_show_history').click().run()
        assert not app.exception
        assert any('Synthetic provider outage' in w.value for w in app.warning)
        assert metric(app,'Normal contributed')==normal
    with patch('etf_market._download',return_value=sample([100,110,90])):
        app.button(key='etf_show_history').click().run()
        assert any('Shortened historical window' in w.value for w in app.warning)
    # A failed refresh preserves only the same symbol's successful session data.
    get_history.clear()
    with patch('etf_market._download',side_effect=MarketUnavailable('Synthetic refresh outage')):
        app.button(key='etf_show_history').click().run()
        assert metric(app,'Historical illustration ending value')=='$900.00'
        assert any('last successful session result' in i.value for i in app.info)
    get_history.clear()


def test_synthetic_case_changes_fit_without_changing_real_etfs(app):
    options=tuple(app.selectbox(key='etf_symbol').options)
    before=metric(app,'Normal contributed')
    app.selectbox(key='etf_demo_case').select('Two-year preservation example').run()
    assert not app.exception
    assert tuple(app.selectbox(key='etf_symbol').options)==options
    assert metric(app,'Normal contributed')==before
    assert any('Demo Short-Term Bonds' in m.value and 'Closest fit' in m.value for m in app.markdown)


def test_blocked_plan_still_supports_independent_market_history():
    from streamlit.testing.v1 import AppTest
    panel="""
from etf_ui import render_etf_explorer
render_etf_explorer({'investment_plan':{}},{'runtime_validation':{'status':'blocked'},'scenario':{'horizon_months':6}})
"""
    view=AppTest.from_string(panel).run()
    assert not view.exception
    with patch('etf_market._download',return_value=sample([100,110,90])):
        view.button(key='etf_show_history').click().run()
    assert not view.exception
    assert metric(view,'Historical illustration ending value')=='$900.00'
    assert any('Shock contribution not established' in i.value for i in view.info)
    assert not any(m.label=='Shock contributed' for m in view.metric)
