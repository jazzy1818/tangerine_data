"""Independent arithmetic and public-history boundaries using synthetic prices."""
from copy import deepcopy
from datetime import date
from unittest.mock import patch
import pandas as pd
import pytest
from etf_calculations import contribution_paths,forward_values,historical_view,monthly_replay
from etf_market import normalize_history,get_history,MarketUnavailable,SYMBOLS
from etf_demo import demo_fit


def prices(values=(100.,110.,90.),dates=None):
    return pd.DataFrame({'Adj Close':values},index=pd.to_datetime(dates or ['2026-01-01','2026-01-02','2026-01-03']))


def fixture(monthly=(100.,)*6,kind='PROPOSED_TRANSFER',complete=True,status='passed'):
    plans={'investment_plan':{'normal_monthly_allocation':200.,'runtime_validation':{'status':'passed'}}}
    path={'horizon_months':len(monthly),'funding_result_complete':complete,
        'schedule':[{'month':0,'proposed_contribution':0}]+[{'month':i,'proposed_contribution':v,'period_complete':True} for i,v in enumerate(monthly,1)]}
    crisis={'runtime_validation':{'status':status},'funding_result_complete':complete,'applied_plan':path,
        'goal_before_crisis':{'kind':kind},'scenario':{'horizon_months':len(monthly)}}
    return plans,crisis


@pytest.mark.parametrize('months,move,normal,shock',[(6,0,1200,600),(6,-10,1080,540),(3,0,600,300),(3,-10,540,270)])
def test_worked_forward_answers(months,move,normal,shock):
    p,c=fixture();paths=contribution_paths(p,c)
    n=forward_values([paths['normal_monthly']]*6,months,move)
    s=forward_values(paths['shock_monthly'],months,move)
    assert n['ending_value']==normal and s['ending_value']==shock
    if months==6 and move==-10:assert s['market_gain_loss']==-60


def test_dated_zero_month_and_slicing_are_exact_and_read_only():
    p,c=fixture((100,0,50,75,25,0));before=deepcopy((p,c))
    values=contribution_paths(p,c)['shock_monthly']
    assert forward_values(values,3)['contributed']==150
    assert forward_values(values,6)['contributed']==250
    assert (p,c)==before
    with pytest.raises(ValueError):forward_values(values,7)


def test_unknown_zero_reserve_and_blocked_are_distinct():
    p,c=fixture((0,)*6)
    assert contribution_paths(p,c)['shock_monthly']==[0.]*6
    c['goal_before_crisis']['kind']='LIQUID_RESERVE_EARMARK'
    assert 'liquid reserves' in contribution_paths(p,c)['reason']
    c['applied_plan']['funding_result_complete']=False
    assert contribution_paths(p,c)['shock_monthly'] is None
    c['runtime_validation']['status']='blocked';c['applied_plan']=None
    assert contribution_paths(p,c)['shock_monthly'] is None


def test_invalid_path_does_not_turn_into_contributions():
    p,c=fixture((100,)*6,kind='LIQUID_RESERVE_EARMARK')
    with pytest.raises(ValueError):contribution_paths(p,c)
    p,c=fixture();c['applied_plan']['schedule'][2]['month']=1
    with pytest.raises(ValueError):contribution_paths(p,c)


def test_adjusted_history_arithmetic_and_short_window():
    f=normalize_history(prices());view,summary=historical_view(f,6,as_of='2026-01-03')
    assert view['normalized_value'].tolist()==[1000,1100,900]
    assert summary['period_change_pct']==pytest.approx(-10)
    assert summary['ending_value']==900 and summary['shortened']


def test_history_cleaning_dates_nonfinite_and_duplicate_conflicts():
    raw=prices([110.,100.,100.,0.,float('inf'),-4.],['2026-01-02','2026-01-01','2026-01-01','2026-01-03','2026-01-04','2026-01-05'])
    f=normalize_history(raw)
    assert f['adjusted_price'].tolist()==[100,110]
    assert f.attrs=={'discarded_rows':3,'duplicate_dates':1}
    with pytest.raises(MarketUnavailable):normalize_history(prices([100,101],['2026-01-01','2026-01-01']))
    with pytest.raises(MarketUnavailable):normalize_history(pd.DataFrame({'Close':[100,110]}))
    with pytest.raises(MarketUnavailable):normalize_history(pd.DataFrame())


def test_market_fetch_is_curated_bounded_cached_and_explicit():
    get_history.clear()
    with patch('etf_market._download',return_value=prices()) as fetch:
        get_history('XEQT.TO','2025-01-01','2026-02-01')
        get_history('XEQT.TO','2025-01-01','2026-02-01')
        assert fetch.call_count==1
        with pytest.raises(MarketUnavailable):get_history('UNLISTED','2025-01-01','2026-02-01')
        assert fetch.call_count==1
    get_history.clear()


def test_provider_has_explicit_adjustment_timeout_and_no_account_arguments():
    from unittest.mock import Mock
    from types import SimpleNamespace
    ticker=Mock()
    ticker.return_value.history.return_value=prices()
    with patch.dict('sys.modules',{'yfinance':SimpleNamespace(Ticker=ticker)}):
        from etf_market import _download
        _download('XEQT.TO','2025-01-01','2026-02-01')
        args=ticker.return_value.history.call_args.kwargs
        assert args['auto_adjust'] is False and args['timeout']==8
        assert set(args)=={'start','end','interval','auto_adjust','actions','timeout','raise_errors'}


def test_monthly_replay_dates_and_zero_amount_are_explicit():
    f=normalize_history(prices([100,110,120,90],['2026-01-30','2026-03-02','2026-03-30','2026-04-01']))
    r=monthly_replay(f,100)
    assert [t['modeled_purchase_date'] for t in r['trades']]==['2026-01-30','2026-03-02','2026-03-30']
    assert r['total_contributed']==300
    assert r['ending_value']==246.82
    assert r['difference']==-53.18
    assert monthly_replay(f,0)['ending_value']==0


def test_synthetic_fit_and_market_catalog_are_independent():
    before=tuple(SYMBOLS)
    growth,excluded=demo_fit('Seven-year growth example')
    assert growth[0]['name']=='Demo Balanced Mix'
    assert excluded[0]['name']=='Demo Global Equity'
    preservation,_=demo_fit('Two-year preservation example')
    assert preservation[0]['name']=='Demo Short-Term Bonds'
    assert SYMBOLS==before


def test_optional_dependency_failure_has_no_finance_side_effect():
    from etf_market import _download
    with patch.dict('sys.modules',{'yfinance':None}):
        with pytest.raises(MarketUnavailable,match='Optional history dependency missing'):
            _download('XEQT.TO','2025-01-01','2026-02-01')
    assert forward_values([200.]*6,6)['ending_value']==1200
