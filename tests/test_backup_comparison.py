"""Independently worked amounts, timing boundaries and view validation."""
from copy import deepcopy
import pytest
from crisis_response import make_crisis_plan,NormalGoal
from plan_classification import ShockScenario
from test_crisis_execution import account,compound,normal_goal
from backup_comparison import build_comparison,comparison_figure


def compound_plan(pauses=False):
    transfers=[dict(event_id=f'pause-{m}',month=m,amount=300.,source='Explicit synthetic judge schedule',
                    included_in_baseline=True,pause_approved=True,pause_fee=0.) for m in range(1,7)] if pauses else []
    return make_crisis_plan(account(),compound(),normal_goal=normal_goal(),existing_transfers=transfers)


def test_worked_compound_summary_chart_and_source_are_consistent():
    plan=compound_plan(True);original=deepcopy(plan);view=build_comparison(plan)
    assert view['before']['first']=={'month':2,'phase':'end','cash':-120.}
    assert view['after']['first']=={'month':3,'phase':'end','cash':-30.}
    assert view['before']['full_need']==3360 and view['after']['full_need']==1560
    assert view['funding_improvement']==1800
    assert 'Month 2 (end) to Month 3 (end)' in view['summary']
    assert any('6 supported transfer pauses' in a for a in view['actions'])
    fig=comparison_figure(view)
    assert len(fig.data)==2
    assert list(fig.data[0].y)==[p['cash'] for p in plan['no_action']['checkpoints']]
    assert list(fig.data[1].y)==[p['cash'] for p in plan['applied_plan']['checkpoints']]
    assert list(fig.data[0].x)==list(range(14))
    assert any(shape.y0==0 and shape.y1==0 for shape in fig.layout.shapes)
    assert len(fig.layout.annotations)==3 # two first-shortage labels and the zero line
    assert plan==original


def test_proposal_pause_adds_no_cash_and_explains_identical_paths():
    view=build_comparison(compound_plan())
    assert view['identical'] and view['after']['full_need']==3360
    assert any('Pausing a proposal adds CAD 0.00' in a for a in view['actions'])
    assert any('No evidenced existing-transfer schedule' in a for a in view['actions'])
    fig=comparison_figure(view)
    assert any('Both paths' in a.text for a in fig.layout.annotations)


def test_month_start_shortage_survives_positive_month_end():
    c=account(income=1000,spending=500,cash=200,bills=100)
    scenario=ShockScenario(effects=[dict(type='one_off_cost',value=600.,start_month=1)])
    p=make_crisis_plan(c,scenario,normal_goal=NormalGoal(name='No new transfer',monthly_contribution=0,reserve_target=0))
    v=build_comparison(p)
    assert v['before']['first']=={'month':1,'phase':'start','cash':-400.}
    assert v['before']['points'][3]['cash']==100
    assert v['before']['full_need']==400
    assert 'Month 1 (start)' in v['summary']


@pytest.mark.parametrize('cost,first,gap',[(3000.,None,0.),(3000.01,{'month':0,'phase':'start','cash':-.01},.01)])
def test_zero_and_immediate_one_cent_boundaries(cost,first,gap):
    p=make_crisis_plan(account(),ShockScenario(effects=[dict(type='one_off_cost',value=cost,start_month=0)]),normal_goal=normal_goal())
    v=build_comparison(p)
    assert v['before']['first']==first and v['before']['full_need']==gap


def test_partial_projection_has_no_full_funding_claim():
    p=make_crisis_plan(account(),ShockScenario(effects=[dict(type='unspecified_event')]),normal_goal=normal_goal())
    v=build_comparison(p)
    assert not v['complete']
    assert v['before']['full_need'] is None and v['after']['full_need'] is None
    assert 'Partial projection' in v['summary'] and 'Not established' in v['summary']
    assert 'Partial projection' in comparison_figure(v).layout.title.text


@pytest.mark.parametrize('corrupt',[
    lambda p:p['applied_plan'].update(scenario_hash='wrong-case'),
    lambda p:p['no_action']['checkpoints'].pop(),
    lambda p:p['applied_plan'].update(first_shortfall_month=1),
    lambda p:p['no_action'].update(additional_cash_needed=0.),
    lambda p:p['applied_plan']['checkpoints'][0].update(cash=float('nan')),
    lambda p:p['no_action']['checkpoints'][0].update(cash=None),
    lambda p:p['runtime_validation'].update(status='blocked'),
])
def test_inconsistent_or_blocked_comparison_is_rejected(corrupt):
    p=compound_plan(True);corrupt(p)
    with pytest.raises(ValueError):build_comparison(p)


def test_positive_new_proposal_does_not_get_described_as_cash_relief():
    c=account(cash=20000)
    p=make_crisis_plan(c,ShockScenario(phase='normal'),normal_goal=normal_goal())
    v=build_comparison(p)
    assert not v['identical'] and v['after']['ending_cash']<v['before']['ending_cash']
    assert v['funding_improvement']==0
    assert any('proposed new transfers' in a and 'leave bill-paying cash' in a for a in v['actions'])


def test_safe_mode_reflects_engine_without_changing_amounts():
    from backup_comparison import safe_mode_status
    p=compound_plan(True);original=deepcopy(p)
    assert safe_mode_status(p,build_comparison(p))[0]=='Modeled liquidity protection'
    assert p==original
    p=make_crisis_plan(account(),ShockScenario(effects=[dict(type='unspecified_event')]),normal_goal=normal_goal())
    assert safe_mode_status(p,build_comparison(p))[0]=='Review required'
    p=make_crisis_plan(account(cash=20000),ShockScenario(phase='normal'),normal_goal=normal_goal())
    assert safe_mode_status(p,build_comparison(p))[0]=='No additional restriction established'
