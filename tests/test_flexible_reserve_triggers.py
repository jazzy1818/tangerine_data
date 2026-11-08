"""Variable liquid savings need different evidence from fixed investment debits."""
from copy import deepcopy
from unittest.mock import patch

import pytest

from goal_validation import enforce_goal_validations
from investment_triggers import AnalystEvidence, KnownExpense, evaluate_investment_triggers
from test_investment_triggers import customer as base_customer


def customer(*args,**kwargs):
    result=base_customer(*args,**kwargs)
    result['history']['household_bills']=200.
    return result


def irregular():
    return customer([500,-100,600,400,-50,700],cash=1500,spending=1000,minimum=1400)


def test_surplus_month_savings_without_fixed_investment_commitment():
    result=evaluate_investment_triggers(irregular())
    review=result['flexible_reserve_savings']
    assert result['runtime_validation']['status']=='passed'
    assert result['normal_monthly_allocation']==result['reserve_monthly_earmark']==0
    assert review['status']=='conditional_review'
    assert review['opportunity_months']==4
    assert [r['conditional_liquid_savings'] for r in review['review_months']]==[375,0,400,300,0,400]
    assert review['current_set_aside'] is None and review['months_to_target'] is None
    assert not review['fixed_monthly_commitment']
    assert result['proposed_actions']==[]
    assert 'REVIEW_FLEXIBLE_RESERVE_SAVINGS' in result['supporting_goals']


def test_small_savings_not_subject_to_investment_minimum_surplus_ratio():
    result=evaluate_investment_triggers(customer([10]*6,cash=1500,spending=1000,minimum=1400))
    assert result['normal_monthly_allocation']==0
    assert result['flexible_reserve_savings']['typical_positive_month_amount']==7.5


@pytest.mark.parametrize('kind',['recent_liquidity','unknown_expense','known_expense','arrears','cash_depleted','goal_met','deficit','bad_history'])
def test_protection_blocks_variable_savings_review(kind):
    c=irregular();kwargs={}
    if kind=='recent_liquidity':c['history'].loc[5,'min_balance']=900
    elif kind=='unknown_expense':kwargs['evidence']=AnalystEvidence(source='Synthetic',known_expenses=(KnownExpense(None,1,'Rent'),))
    elif kind=='known_expense':kwargs['evidence']=AnalystEvidence(source='Synthetic',known_expenses=(KnownExpense(1000,1,'Rent'),))
    elif kind=='arrears':c['source_loan_status']='D'
    elif kind=='cash_depleted':kwargs['evidence']=AnalystEvidence(source='Synthetic',available_cash=100)
    elif kind=='goal_met':c=customer([100]*6,cash=4000,spending=1000,minimum=3500)
    elif kind=='deficit':c=customer([-100]*6,cash=1500,spending=1000,minimum=1400)
    elif kind=='bad_history':c['history']=c['history'].iloc[:2]
    result=evaluate_investment_triggers(c,**kwargs)
    assert result['flexible_reserve_savings']['status']!='conditional_review'
    assert result['runtime_validation']['status']=='passed'


def test_active_or_unspecified_shock_does_not_offer_variable_savings():
    for kwargs in [dict(shock=dict(income_multiplier=.55,bills_increase_pct=0.,one_off_costs=0.)),
                   dict(evidence=AnalystEvidence(source='Synthetic',event_description='Income changes',event_financial_effect='unspecified'))]:
        r=evaluate_investment_triggers(irregular(),**kwargs)
        assert r['flexible_reserve_savings']['status']=='not_supported'


def test_variable_review_never_adds_cash_or_changes_existing_projection():
    r=evaluate_investment_triggers(irregular())
    assert r['scenario_results'][0]['no_allocation']['ending_cash']==4200
    assert r['security_recommendations']==[] and not r['automatic_trade_allowed']
    assert all(m['conditional_liquid_savings']<=400 for m in r['flexible_reserve_savings']['review_months'])


@pytest.mark.parametrize('tamper',['amount','current_cash','fixed','eta'])
def test_runtime_guard_rejects_invented_savings_or_commitment(tamper):
    def corrupt(plan,facts):
        plan=deepcopy(plan);review=plan['flexible_reserve_savings']
        if tamper=='amount':review['review_months'][0]['conditional_liquid_savings']=9999
        elif tamper=='current_cash':review['current_set_aside']=100
        elif tamper=='fixed':review['fixed_monthly_commitment']=True
        else:review['months_to_target']=3
        return enforce_goal_validations(plan,facts)
    with patch('investment_triggers.enforce_goal_validations',side_effect=corrupt):
        r=evaluate_investment_triggers(irregular())
    assert r['runtime_validation']['status']=='blocked'
    assert r['flexible_reserve_savings']['status']=='blocked'
    assert r['flexible_reserve_savings']['review_months']==[]
