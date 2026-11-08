from copy import deepcopy
from types import SimpleNamespace
import pytest
from test_crisis_execution import account, compound, normal_goal
from crisis_response import make_crisis_plan
from tailored_advice import explain_plan, validate_advice
from goal_validation import enforce_crisis_validations
from plan_classification import ShockScenario


def transfers(fee=0., approved=True):
    return [dict(event_id=f'saving-{m}',month=m,amount=300.,source='Synthetic judge schedule',
        included_in_baseline=True,pause_approved=approved,pause_fee=fee) for m in range(1,7)]


def plan(**kwargs):
    return make_crisis_plan(account(),compound(),normal_goal=normal_goal(),**kwargs)


def test_personalized_two_people_and_independent_cash_equation():
    a,b=plan(),plan(existing_transfers=transfers())
    assert a['applied_plan']['additional_cash_needed']==3360
    assert b['applied_plan']['additional_cash_needed']==1560
    assert b['applied_plan']['first_shortfall_month']==3
    assert b['applied_plan']['ending_cash']==3000-1500+6*(1650-2460+300)
    assert '1,800.00' in b['advice']['cards']['pause']
    assert 'No existing-transfer pause' in a['advice']['cards']['pause']
    assert a['advice']['fingerprint']!=b['advice']['fingerprint']


@pytest.mark.parametrize('fee,approved',[(None,True),(0.,False),(300.,True),(350.,True)])
def test_unsupported_or_nonbeneficial_pause_never_applied(fee,approved):
    p=plan(existing_transfers=transfers(fee,approved))
    assert not p['applied_transfer_ids']
    assert p['applied_plan']['additional_cash_needed']==3360


def test_upfront_fee_creating_earlier_shortfall_is_not_recommended():
    c=account(cash=0.)
    p=make_crisis_plan(c,ShockScenario(phase='normal'),normal_goal=normal_goal(),existing_transfers=transfers(50.))
    assert p['supported_pause']['first_shortfall_month']==1
    assert p['applied_plan']['first_shortfall_month'] is None
    assert not p['applied_transfer_ids']


def test_tampered_advice_and_action_accounting_blocked():
    p=plan(existing_transfers=transfers())
    bad=deepcopy(p['advice']);bad['cards']['pause']='Obtain a guaranteed relief loan.'
    with pytest.raises(ValueError): validate_advice(bad,p)
    p['applied_plan']['schedule'][1]['end_balance']+=1
    with pytest.raises(ValueError): enforce_crisis_validations(p)


class Client:
    def __init__(self,text):self.models=self;self.text=text
    def generate_content(self,**kwargs):
        self.prompt=kwargs['contents']
        return SimpleNamespace(text=self.text)


@pytest.mark.parametrize('text',['{"focus_ids":["invented_loan"]}',
    '{"focus_ids":["pause"],"recommendation":"Buy an ETF"}',
    '{"focus_ids":["pause","pause"]}', 'invalid'])
def test_invalid_provider_claims_fall_back_without_changing_advice(text):
    p=plan(); c=Client(text); out=explain_plan(p,backend='gemini',client=c)
    assert out['actual_backend']=='local' and out['fallback_reason']
    assert out['cards']==p['advice']['cards']


def test_valid_provider_only_emphasizes_existing_facts():
    p=plan(existing_transfers=transfers());c=Client('{"focus_ids":["pause","gap"]}')
    out=explain_plan(p,backend='gemini',client=c)
    assert out['actual_backend']=='gemini' and out['cards']==p['advice']['cards']
    assert 'Synthetic judge schedule' not in c.prompt and '3360' not in c.prompt


def test_late_windfall_preserves_early_shortfall_and_six_month_gap():
    p=make_crisis_plan(account(income=1800,spending=2400,cash=1000),
        ShockScenario(effects=[dict(type='one_off_receipt',value=2000,start_month=3)]),normal_goal=normal_goal())
    path=p['applied_plan']
    assert [r['end_balance'] for r in path['schedule'][1:]]==[400,-200,1200,600,0,-600]
    assert path['first_shortfall_month']==2 and path['additional_cash_needed']==600
    assert 'Month 3' in p['advice']['cards']['dated_events']


def test_fractional_cent_transfer_rejected():
    t=transfers();t[0]['amount']=.001
    with pytest.raises(ValueError):plan(existing_transfers=t)


def test_normal_and_explicit_income_recovery_advice_use_dated_math():
    from crisis_response import NormalGoal
    goal=NormalGoal(name='No new transfer',monthly_contribution=0,reserve_target=7200)
    normal=make_crisis_plan(account(cash=7200),ShockScenario(phase='normal'),normal_goal=goal)
    assert normal['applied_plan']['ending_cash']==10800 and not normal['G25']
    s=ShockScenario(effects=[dict(type='income_multiplier',value=.5,start_month=2,duration_months=2),
                            dict(type='income_multiplier',value=1.,start_month=4,ongoing=True)])
    p=make_crisis_plan(account(),s,normal_goal=goal)
    assert [r['end_balance'] for r in p['applied_plan']['schedule'][1:]]==[3600,2700,1800,2400,3000,3600]
    assert p['applied_plan']['funding_result_complete']


def test_recovery_explanation_uses_separate_supplied_checkpoint():
    p=plan(recovery_snapshot=dict(source='Synthetic judge checkpoint',assessment_month='2026-07',
        cash_basis='judge_specified',available_cash=3000,monthly_inflow=3000,monthly_spending=2400,
        stable_cash_flow=True,obligations_covered=True,supported_monthly_contribution=300))
    assert p['recovery']['reserve_gap']==4200 and p['recovery']['months_to_target']==14
    assert '14 months' in p['advice']['cards']['recovery']
    assert p['applied_plan']['additional_cash_needed']==3360
