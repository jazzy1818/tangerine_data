"""Independent hand calculations and end-to-end scenario/backup regressions."""
from copy import deepcopy
from unittest.mock import patch

import pandas as pd
import pytest
from pydantic import ValidationError
from streamlit.testing.v1 import AppTest

import engine
from crisis_response import NormalGoal, ExistingGoalTransfer, make_crisis_plan
from plan_classification import ShockScenario, build_case, profile_from_engine, select_plan
from recovery_plan import make_recovery_plan
from scenario_execution import execute_scenario, enforce_execution


def account(income=3000., spending=2400., cash=3000., bills=400.):
    h = pd.DataFrame({'account_id': 17, 'month': pd.period_range('2025-01', periods=12, freq='M').astype(str),
        'money_in': income, 'money_out': spending, 'household_bills': bills, 'insurance': 0., 'loan_payments': 0.,
        'avg_daily_balance': cash, 'month_end_balance': cash, 'min_balance': cash, 'days_below_zero': 0})
    return {'account_id': 17, 'history': h, 'raw_I': income, 'I': income, 'raw_S': spending, 'S': spending,
        'raw_B': cash, 'B': cash, 'raw_H': bills, 'H': bills, 'raw_F': bills, 'F': bills,
        'raw_P': 0., 'P': 0., 'has_running_loan': False, 'loan_status_meaning': None,
        'demographics': {'relationship': 'Single Owner'}, 'baseline_gap': spending-income}


def compound():
    return ShockScenario(effects=[{'type':'one_off_cost','value':1500.,'start_month':0,'effect_id':'repair'},
        {'type':'income_multiplier','value':.55,'duration_months':6},
        {'type':'household_bills_percent','value':15.,'duration_months':6}])


def normal_goal():
    return NormalGoal(name='Reserve goal', monthly_contribution=300., reserve_target=7200.)


def test_compound_all_effects_executed_and_pause_proposal_adds_no_cash():
    result = make_crisis_plan(account(), compound(), normal_goal=normal_goal())
    p = result['no_action']
    assert result['runtime_validation']['status'] == 'passed'
    assert result['lead_module'] == 'M5'
    assert len(result['support_modules']) <= 2
    assert {'M1','M2','M3','M5'} <= set(result['affected_modules'])
    assert p['schedule'][0]['end_balance'] == 1500
    assert p['schedule'][1]['end_balance'] == 690
    assert p['schedule'][2]['end_balance'] == -120
    assert p['first_shortfall_month'] == 2 and p['additional_cash_needed'] == 3360
    assert result['G25'] and result['goal_status'] == 'PAUSED'
    assert result['proposal_pause_cash_credit'] == 0
    assert result['supported_pause']['additional_cash_needed'] == 3360
    assert result['continue_goal']['additional_cash_needed'] == 5160
    assert result['revised_goal']['additional_cash_needed'] == 3360


def test_verified_existing_transfer_pause_and_fees_count_once():
    transfers = [ExistingGoalTransfer(event_id=f'transfer-{m}', month=m, amount=300., source='Explicit synthetic judge schedule',
                  included_in_baseline=True, pause_approved=True, pause_fee=0.) for m in range(1,7)]
    result = make_crisis_plan(account(), compound(), normal_goal=normal_goal(), existing_transfers=transfers)
    assert result['supported_pause']['first_shortfall_month'] == 3
    assert result['supported_pause']['additional_cash_needed'] == 1560
    assert result['pause_funding_gap_improvement'] == 1800
    assert result['existing_transfer_pause_credit'] == 1800
    transfers[0] = transfers[0].model_copy(update={'pause_fee':100.})
    revised = make_crisis_plan(account(), compound(), normal_goal=normal_goal(), existing_transfers=transfers)
    assert revised['supported_pause']['additional_cash_needed'] == 1660
    with pytest.raises(ValueError, match='Duplicate scheduled'):
        make_crisis_plan(account(), compound(), normal_goal=normal_goal(), existing_transfers=transfers+[transfers[0]])


def test_unsupported_pause_without_inclusion_or_approval_or_fees_gets_no_credit():
    for kwargs in ({'included_in_baseline':False,'pause_approved':True,'pause_fee':0.},
                   {'included_in_baseline':True,'pause_approved':False,'pause_fee':0.},
                   {'included_in_baseline':True,'pause_approved':True}):
        transfer = ExistingGoalTransfer(event_id='one',month=1,amount=300.,source='Synthetic case',**kwargs)
        result=make_crisis_plan(account(),compound(),normal_goal=normal_goal(),existing_transfers=[transfer])
        assert result['existing_transfer_pause_credit'] == 0
        assert result['supported_pause']['additional_cash_needed'] == 3360


def test_improving_existing_deficit_does_not_activate_G25():
    c = account(income=1000.,spending=2000.,cash=3000.)
    s = ShockScenario(effects=[{'type':'income_delta','value':100.,'ongoing':True}])
    r = make_crisis_plan(c,s,normal_goal=NormalGoal(name='Stabilize',monthly_contribution=0.,reserve_target=6000.))
    assert not r['G25'] and r['goal_status']=='NOT_SCHEDULED'
    assert r['no_action']['additional_cash_needed'] == 2400
    # The existing static trigger path and its S27 runtime gate must agree too.
    p = engine.run_pipeline(20111, income_multiplier=1.05)['plan']['investment_plan']
    assert p['runtime_validation']['status']=='passed'
    assert next(t['state'] for t in p['triggers'] if t['id']=='G25') == 'inactive'


def test_same_profile_windfall_changes_backup_by_exactly_5000():
    c=engine.know_customer(22812)
    base=engine.make_plan(c,scenario=ShockScenario(phase='normal'))
    s=ShockScenario(effects=[{'type':'one_off_receipt','value':5000.,'start_month':0}])
    case=build_case(profile_from_engine(c),s)
    selection=select_plan(case,'rules')
    out=engine.make_plan(c,scenario=s,selection_result=selection)
    assert out['crisis_plan']['lead_module']=='M8'
    assert out['crisis_plan']['classification_input_hash']==selection.input_hash
    assert out['backup_plan']['month_6_balance']-base['backup_plan']['month_6_balance']==pytest.approx(5000.)
    assert sum(row['one_off_receipt'] for row in out['backup_plan']['six_month_schedule'])==5000


def test_delayed_cost_and_temporary_expense_expire_correctly():
    s=ShockScenario(effects=[{'type':'one_off_cost','value':900.,'start_month':3},
        {'type':'household_bills_delta','value':100.,'start_month':2,'duration_months':2}])
    p=execute_scenario(account(),s)
    assert [r['spending'] for r in p['schedule'][1:]]==[2400,2500,2500,2400,2400,2400]
    assert p['schedule'][3]['one_off_cost']==900
    assert p['ending_cash']==5500


def test_income_expiry_does_not_automatically_restore_full_salary():
    s=ShockScenario(horizon_months=7,effects=[{'type':'income_multiplier','value':.55,'duration_months':6}])
    p=execute_scenario(account(),s)
    assert p['schedule'][6]['income']==1650
    assert p['schedule'][7]['income'] is None
    assert not p['funding_result_complete'] and p['full_funding_need'] is None
    data=s.model_dump()
    data['effects'].append({'type':'income_multiplier','value':1.,'start_month':7,'ongoing':True})
    explicit=ShockScenario.model_validate(data)
    q=execute_scenario(account(),explicit)
    assert q['schedule'][7]['income']==3000 and q['funding_result_complete']


def test_unknown_effect_known_cost_is_partial_and_no_financial_success_claim():
    s=ShockScenario(effects=[{'type':'unspecified_event','value':None},
                           {'type':'one_off_cost','value':1200.,'start_month':0}])
    p=execute_scenario(account(),s)
    assert p['schedule'][0]['end_balance']==1800
    assert not p['funding_result_complete'] and not p['makes_it_through_horizon']
    assert p['full_funding_need'] is None


@pytest.mark.parametrize('kind', ['income_multiplier','expense_delta','liquidity_hold'])
def test_unknown_duration_not_silently_ongoing(kind):
    value=.55 if kind=='income_multiplier' else 500.
    p=execute_scenario(account(),ShockScenario(effects=[{'type':kind,'value':value}]))
    assert not p['funding_result_complete']
    assert any('duration unknown' in flag for flag in p['unresolved_effects'])


def test_zero_boundary_and_one_cent_shortfall():
    assert execute_scenario(account(income=0.,spending=500.,cash=3000.),ShockScenario(phase='normal'))['additional_cash_needed']==0
    p=execute_scenario(account(income=0.,spending=500.,cash=2999.99),ShockScenario(phase='normal'))
    assert p['additional_cash_needed']==.01 and p['first_shortfall_month']==6
    p=execute_scenario(account(),ShockScenario(effects=[{'type':'one_off_cost','value':3000.01,'start_month':0}]))
    assert p['first_shortfall_month']==0


def test_duplicate_invoice_rejected_distinct_identical_invoices_count_twice():
    cost={'type':'one_off_cost','value':900.,'start_month':0}
    once=ShockScenario(effects=[{**cost,'effect_id':'A'},{**cost,'effect_id':'A'}])
    assert execute_scenario(account(),once)['schedule'][0]['one_off_cost']==900
    with pytest.raises(ValueError):
        ShockScenario(effects=[{**cost,'effect_id':'A'},{**cost,'value':1000.,'effect_id':'A'}])
    p=execute_scenario(account(),ShockScenario(effects=[{**cost,'effect_id':'A'},{**cost,'effect_id':'B'}]))
    assert p['schedule'][0]['one_off_cost']==1800


def test_hold_restricts_access_and_releases_without_creating_money():
    p=execute_scenario(account(),ShockScenario(effects=[{'type':'liquidity_hold','value':2000.,'duration_months':2}]))
    assert p['schedule'][1]['held_cash']==2000
    assert p['schedule'][3]['held_cash']==0
    assert p['schedule'][3]['total_cash']==4800
    assert sum(r['one_off_receipt'] for r in p['schedule'])==0


@pytest.mark.parametrize('kind,value',[('investment_return',25.),('payment_delay_days',5.)])
def test_unsupported_asset_or_generic_delay_does_not_change_cash(kind,value):
    base=execute_scenario(account(),ShockScenario(phase='normal'))
    result=execute_scenario(account(),ShockScenario(effects=[{'type':kind,'value':value,'ongoing':True}]))
    assert result['ending_cash']==base['ending_cash']
    assert not result['funding_result_complete']


def test_beyond_horizon_obligation_remains_visible():
    p=execute_scenario(account(),ShockScenario(effects=[{'type':'one_off_cost','value':900.,'start_month':8}]))
    assert p['ending_cash']==6600
    assert p['pending_effects'][0]['value']==900


def test_corrupted_ledger_is_blocked_at_runtime():
    c,s=account(),compound()
    p=execute_scenario(c,s)
    p['schedule'][1]['end_balance']+=100
    with pytest.raises(ValueError,match='Runtime cash-ledger'):
        enforce_execution(p,c,s)


def test_wrong_account_or_scenario_classifier_result_is_rejected():
    c=account()
    case=build_case(profile_from_engine(c),ShockScenario(phase='normal'))
    wrong=select_plan(case,'rules')
    r=make_crisis_plan(c,compound(),normal_goal=normal_goal(),selection_result=wrong)
    assert r['selection_status']=='rejected_stale_or_invalid_proposal'
    assert r['lead_module']=='M5'


def snapshot(**changes):
    return dict(source='Explicit synthetic judge checkpoint',assessment_month='2026-01',cash_basis='judge_specified',
        available_cash=3000.,monthly_inflow=3000.,monthly_spending=2400.,stable_cash_flow=True,
        obligations_covered=True,supported_monthly_contribution=300.,**changes)


def test_recovery_14_month_example_and_unknown_or_zero_rate():
    p=make_recovery_plan(snapshot())
    assert p['status']=='REBUILDING' and p['lead_module']=='M6'
    assert p['reserve_gap']==4200 and p['months_to_target']==14
    for bound in [None,0.]:
        data=snapshot(); data['supported_monthly_contribution']=bound
        assert make_recovery_plan(data)['months_to_target'] is None
    assert make_recovery_plan()['status']=='RECOVERY_UNVERIFIED'


def test_recovery_deficit_uncovered_obligations_and_restored_reserve():
    for updates in [{'monthly_inflow':2000.},{'available_cash':-1.},{'obligations_covered':False},{'stable_cash_flow':False}]:
        p=make_recovery_plan({**snapshot(),**updates})
        assert p['status']=='ACTIVE_CRISIS' and p['monthly_contribution']==0
        assert p['months_to_target'] is None
    restored=make_recovery_plan({**snapshot(),'available_cash':7200.})
    assert restored['status']=='RESERVE_RESTORED'


def test_phase_label_alone_does_not_establish_recovery():
    p=make_crisis_plan(account(),ShockScenario(phase='recovery'),normal_goal=normal_goal())
    assert p['recovery']['status']=='RECOVERY_UNVERIFIED'
    assert p['lead_module']!='M6'


def test_organizer_formula_unchanged_for_all_three_presets():
    c=engine.know_customer(20111)
    from plan_classification.case import scenario_from_engine
    for inputs in [(.55,0.,0.),(1.,0.,c['raw_S']),(.55,.15,0.)]:
        prior=engine.take_shock(c,*inputs)
        reference=engine.scenario_reference(c,scenario_from_engine(*inputs))
        assert all(reference[key]==value for key,value in prior.items())


def test_liquid_reserve_earmark_stays_liquid():
    p=make_crisis_plan(account(),ShockScenario(phase='normal'),
        normal_goal=NormalGoal(name='Reserve',kind='LIQUID_RESERVE_EARMARK',monthly_contribution=300.,reserve_target=7200.))
    assert p['continue_goal']['ending_cash']==p['no_action']['ending_cash']
    assert p['proposal_pause_cash_credit']==0


def test_engine_does_not_mutate_profile_or_scenario():
    c,s=account(),compound()
    original=c['history'].copy(deep=True); raw=s.model_dump()
    engine.make_plan(c,scenario=s,normal_goal=normal_goal())
    pd.testing.assert_frame_equal(c['history'],original)
    assert s.model_dump()==raw


def test_direct_planselection_handoff_uses_existing_contract_without_fake_provider():
    c,s=account(),compound()
    selection=select_plan(build_case(profile_from_engine(c),s),'rules').selection
    result=engine.make_plan(c,scenario=s,normal_goal=normal_goal(),selection=selection)['crisis_plan']
    assert result['lead_module']=='M5'
    assert result['module_proposal']==selection.model_dump()
    assert result['classification'] is None  # bare proposal has no provider metadata


def test_supplied_cash_shared_with_classifier_without_altering_official_B():
    c,s=account(),compound()
    oldB=c['B']
    result=make_crisis_plan(c,s,normal_goal=normal_goal(),opening_cash=10000.)
    case=build_case(profile_from_engine(c),s,planning_cash=10000.)
    assert result['classification_input_hash']==__import__('plan_classification.case',fromlist=['case_hash']).case_hash(case)
    assert result['no_action']['opening_cash']==10000
    assert case.planning_cash_basis=='supplied_scenario'
    assert c['B']==oldB


def test_known_extra_obligation_included_once_in_both_baseline_and_crisis():
    from investment_triggers import AnalystEvidence,KnownExpense
    facts=AnalystEvidence(source='Explicit additional tuition record',available_cash=5000.,
                          known_expenses=(KnownExpense(900.,2,'Tuition'),))
    result=engine.make_plan(account(),scenario=ShockScenario(phase='normal'),analyst_evidence=facts)['crisis_plan']
    assert result['no_action']['schedule'][2]['one_off_cost']==900
    assert result['baseline_without_crisis']['schedule'][2]['one_off_cost']==900
    assert result['no_action']['ending_cash']==7700
    assert not result['G25']


def test_unquantified_known_obligation_is_not_discarded():
    from investment_triggers import AnalystEvidence,KnownExpense
    facts=AnalystEvidence(source='Explicit tuition record',known_expenses=(KnownExpense(None,2,'Tuition'),))
    result=engine.make_plan(account(),scenario=ShockScenario(phase='normal'),analyst_evidence=facts)['crisis_plan']
    assert not result['funding_result_complete']
    assert result['no_action']['full_funding_need'] is None


def test_monthly_improvement_is_a_target_not_an_applied_cut():
    result=make_crisis_plan(account(),compound(),normal_goal=normal_goal())
    assert result['required_monthly_improvement']==560
    assert result['no_action']['additional_cash_needed']==3360
    income=ShockScenario(effects=[{'type':'income_multiplier','value':.55,'duration_months':6}])
    assert make_crisis_plan(account(),income,normal_goal=normal_goal())['required_monthly_improvement']==250


def test_unknown_or_subcent_rebuild_bound_has_no_false_date():
    result=make_recovery_plan({**snapshot(),'supported_monthly_contribution':.004})
    assert result['monthly_contribution']==0 and result['months_to_target'] is None


def test_cost_changes_and_pauses_cannot_consume_known_fixed_obligations():
    s=ShockScenario(effects=[{'type':'expense_delta','value':-2200.,'ongoing':True}])
    with pytest.raises(ValueError,match='fixed obligations'):
        execute_scenario(account(),s)
    transfer=ExistingGoalTransfer(event_id='inconsistent',month=1,amount=2200.,source='Synthetic',
            included_in_baseline=True,pause_approved=True,pause_fee=0.)
    with pytest.raises(ValueError,match='Paused transfers exceed'):
        make_crisis_plan(account(),compound(),normal_goal=normal_goal(),existing_transfers=[transfer])


def test_pending_bill_protects_allocation_headroom():
    c=account(income=6500.,spending=3500.,cash=25000.)
    s=ShockScenario(effects=[{'type':'one_off_cost','value':16000.,'start_month':8}])
    goal=NormalGoal(name='Allocation review',monthly_contribution=1500.,reserve_target=10500.)
    result=make_crisis_plan(c,s,normal_goal=goal)
    assert result['goal_contribution_revised']==0
    assert result['G25']
    assert result['no_action']['pending_effects'][0]['value']==16000


def test_immediate_hold_cannot_fund_an_immediate_repair_and_release_is_not_income():
    s=ShockScenario(effects=[{'type':'liquidity_hold','value':2000.,'start_month':0,'duration_months':2},
                            {'type':'one_off_cost','value':1500.,'start_month':0}])
    p=execute_scenario(account(),s)
    assert p['first_shortfall_month']==0 and p['additional_cash_needed']==500
    assert p['funding_result_complete']
    assert p['schedule'][2]['held_cash']==2000
    assert p['schedule'][3]['held_cash']==0
    assert sum(r['one_off_receipt'] for r in p['schedule'])==0


def test_impossible_monetary_magnitude_is_rejected_before_infinite_cash():
    s=ShockScenario(effects=[{'type':'income_delta','value':1e308,'ongoing':True}])
    with pytest.raises(ValueError,match='supported'):
        execute_scenario(account(),s)
