"""Independent reproductions of the five pre-demo review findings."""
import pytest
from test_crisis_execution import account, normal_goal
from crisis_response import make_crisis_plan, NormalGoal
from plan_classification import ShockScenario
from scenario_execution import execute_scenario


def transfer(identity,month=1,fee=0.):
    return dict(event_id=identity,month=month,amount=300.,source='Explicit synthetic schedule',
        included_in_baseline=True,pause_approved=True,pause_fee=fee)


def test_reduction_cannot_release_a_nonexistent_loan_payment():
    s=ShockScenario(effects=[dict(type='debt_payment_delta',value=-300.,ongoing=True)])
    with pytest.raises(ValueError,match='loan payment'):
        execute_scenario(account(),s)


def test_healthy_account_keeps_costly_pause_as_option_only():
    p=make_crisis_plan(account(cash=10000),ShockScenario(phase='normal'),normal_goal=normal_goal(),
        existing_transfers=[transfer('optional',fee=50.)])
    assert not p['applied_transfer_ids']
    assert p['applied_plan']==p['revised_goal']
    assert p['supported_pause']['ending_cash'] > p['no_action']['ending_cash']


def test_costly_candidate_cannot_cancel_fee_free_candidate():
    c=account(income=1400,spending=1600,cash=0)
    g=NormalGoal(name='No proposed transfer',monthly_contribution=0,reserve_target=0)
    p=make_crisis_plan(c,ShockScenario(phase='normal'),normal_goal=g,
        existing_transfers=[transfer('free'),transfer('costly',month=1,fee=50.)])
    assert p['applied_transfer_ids']==['free']
    assert p['applied_plan']['first_shortfall_month']==2
    assert p['applied_plan']['additional_cash_needed']==900


def test_unknown_impact_holds_goal_without_confirming_G25():
    g=NormalGoal(name='Proposal',monthly_contribution=300,reserve_target=7200)
    p=make_crisis_plan(account(cash=10000),ShockScenario(effects=[dict(type='unspecified_event')]),normal_goal=g)
    assert p['G25'] is None
    assert p['goal_status']=='REVIEW_REQUIRED'
    assert p['no_action']['full_funding_need'] is None


def loan_account():
    c=account()
    c.update(raw_P=300., P=300., raw_F=700., F=700., has_running_loan=True)
    c['history']['loan_payments']=300.
    return c


def test_specific_loan_floor_protects_household_and_remaining_loan():
    s=ShockScenario(effects=[dict(type='debt_payment_delta',value=-200.,ongoing=True),
                             dict(type='expense_delta',value=-1700.,ongoing=True)])
    assert execute_scenario(loan_account(),s)['schedule'][1]['spending']==500
    s.effects[1].value=-1700.01
    with pytest.raises(ValueError,match='fixed obligations'):execute_scenario(loan_account(),s)


def test_unknown_payment_requires_evidence_and_never_creates_relief():
    c=account();c['raw_P']=c['P']=None
    s=ShockScenario(effects=[dict(type='debt_payment_delta',value=-300.,ongoing=True)])
    p=execute_scenario(c,s)
    assert p['schedule'][1]['spending']==2400 and p['full_funding_need'] is None
    assert not p['funding_result_complete']


def test_supplied_payment_without_inclusion_does_not_free_cash():
    s=ShockScenario(effects=[dict(type='debt_payment_delta',value=-300.,ongoing=True,
        obligation_payment=300.,obligation_source='Explicit judge payment',payment_in_baseline=False)])
    p=execute_scenario(account(),s)
    assert p['schedule'][1]['spending']==2400 and not p['funding_result_complete']


def test_supplied_payment_cannot_erase_unchanged_household_bills():
    s=ShockScenario(effects=[dict(type='debt_payment_delta',value=-300.,ongoing=True,
        obligation_payment=300.,obligation_source='Explicit judge payment',payment_in_baseline=True),
        dict(type='expense_delta',value=-2000.,ongoing=True)])
    with pytest.raises(ValueError,match='fixed obligations'): execute_scenario(account(),s)


def test_deferral_repayment_counts_once_and_does_not_create_wealth():
    from plan_classification import build_case, profile_from_engine
    s=ShockScenario(effects=[dict(type='debt_payment_delta',value=-300.,duration_months=2,
        debt_change_kind='deferral',repayment_month=4,repayment_amount=600.)])
    c=loan_account();p=execute_scenario(c,s)
    assert p['schedule'][1]['spending']==2100 and p['schedule'][3]['spending']==2400
    assert p['schedule'][4]['one_off_cost']==600
    assert p['ending_cash']==6600 and p['funding_result_complete']
    case=build_case(profile_from_engine(c),s)
    assert any(e.type=='one_off_cost' and e.start_month==4 for e in case.effects)


@pytest.mark.parametrize('terms',[{'repayment_unresolved':True},{'repayment_month':8,'repayment_amount':600.}])
def test_unresolved_or_future_repayment_keeps_full_need_open(terms):
    s=ShockScenario(effects=[dict(type='debt_payment_delta',value=-300.,duration_months=2,
        debt_change_kind='deferral',**terms)])
    p=execute_scenario(loan_account(),s)
    assert not p['funding_result_complete'] and p['full_funding_need'] is None
    assert any(e['type']=='deferred_repayment' for e in p['pending_effects'])


def test_deferral_cannot_silently_omit_repayment_or_principal():
    for terms in ({},{'repayment_month':4,'repayment_amount':300.}):
        with pytest.raises(ValueError):
            ShockScenario(effects=[dict(type='debt_payment_delta',value=-300.,duration_months=2,
                debt_change_kind='deferral',**terms)])


def test_pause_selection_is_order_independent_and_explains_exclusions():
    c=account(income=1400,spending=1600,cash=0)
    g=NormalGoal(name='No proposal',monthly_contribution=0,reserve_target=0)
    records=[transfer('costly',fee=50.),transfer('free')]
    a=make_crisis_plan(c,ShockScenario(phase='normal'),normal_goal=g,existing_transfers=records)
    b=make_crisis_plan(c,ShockScenario(phase='normal'),normal_goal=g,existing_transfers=list(reversed(records)))
    assert a['applied_plan']==b['applied_plan']
    assert a['applied_transfer_ids']==['free']
    d={d['event_id']:d for d in a['pause_decisions']}
    assert d['free']['purpose']=='reduces_funding_gap'
    assert d['costly']['reason']=='advances_shortfall_or_worsens_gap'


def test_reserve_floor_is_a_supported_purpose_even_without_shortfall():
    g=NormalGoal(name='Protect reserve',monthly_contribution=0,reserve_target=5000)
    p=make_crisis_plan(account(cash=3000),ShockScenario(phase='normal'),normal_goal=g,
        existing_transfers=[transfer('reserve')])
    assert p['applied_transfer_ids']==['reserve']
    assert p['pause_decisions'][0]['purpose']=='protects_reserve_floor'


def test_known_immediate_shortage_remains_evidenced_before_later_unknown():
    p=make_crisis_plan(account(),ShockScenario(effects=[
        dict(type='one_off_cost',value=4000.,start_month=0),dict(type='unspecified_event',start_month=1)]),normal_goal=normal_goal())
    assert p['G25'] is True and p['G25_state']=='active'
    assert p['no_action']['full_funding_need'] is None


def test_expired_income_uncertainty_is_not_a_new_confirmed_deterioration():
    s=ShockScenario(horizon_months=7,effects=[dict(type='income_multiplier',value=.99,duration_months=6)])
    p=make_crisis_plan(account(cash=20000),s,normal_goal=normal_goal())
    assert p['G25'] is None and p['goal_status']=='REVIEW_REQUIRED'


def test_active_loan_snapshot_does_not_prove_inclusion_in_historical_spending():
    c=account();c.update(raw_P=300.,P=300.,has_running_loan=True)
    s=ShockScenario(effects=[dict(type='debt_payment_delta',value=-300.,ongoing=True)])
    with pytest.raises(ValueError,match='included in baseline spending'):execute_scenario(c,s)


def test_unclassified_payment_inclusion_leaves_relief_conditional():
    c=loan_account();del c['history']
    s=ShockScenario(effects=[dict(type='debt_payment_delta',value=-100.,ongoing=True)])
    p=execute_scenario(c,s)
    assert p['schedule'][1]['spending']==2400
    assert p['full_funding_need'] is None


@pytest.mark.parametrize('phase',['active','recovery'])
def test_unestablished_empty_event_is_not_an_official_preset(phase):
    from scenario_execution import organizer_inputs
    assert organizer_inputs(ShockScenario(phase=phase)) is None


def test_payment_override_cannot_leak_to_another_account():
    from plan_classification import build_case, profile_from_engine
    s=ShockScenario(effects=[dict(type='debt_payment_delta',value=-300.,ongoing=True,
        obligation_payment=300.,obligation_source='Explicit account 18 scenario',
        payment_in_baseline=True,obligation_account_id=18)])
    c=account();p=execute_scenario(c,s)
    assert p['schedule'][1]['spending']==2400 and p['full_funding_need'] is None
    case=build_case(profile_from_engine(c),s)
    assert case.effects[0].cashflow_delta_to_scale is None
    assert any('another account' in m for m in case.missing_details)


def test_other_accounts_deferral_does_not_become_a_classifier_cash_cost():
    from plan_classification import build_case, profile_from_engine
    s=ShockScenario(effects=[dict(type='debt_payment_delta',value=-300.,duration_months=2,
        obligation_payment=300.,obligation_source='Account 18 evidence',payment_in_baseline=True,
        obligation_account_id=18,debt_change_kind='deferral',repayment_month=4,repayment_amount=600.)])
    c=account();p=execute_scenario(c,s)
    assert all(r['one_off_cost']==0 for r in p['schedule'])
    case=build_case(profile_from_engine(c),s)
    assert all(e.cashflow_delta_to_scale is None for e in case.effects)
