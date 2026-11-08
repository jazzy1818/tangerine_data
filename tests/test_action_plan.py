"""Finance Decision Policy v1.1 §8 anchors A–E, checked on the action-plan layer."""
import pandas as pd

from action_plan import build_action_plan, MAX_PRIMARY
from crisis_response import NormalGoal, make_crisis_plan
from plan_classification import ShockScenario
from test_crisis_execution import account, compound, normal_goal

STATUSES = {'SUPPORTED_MODELED', 'CONDITIONAL_ONLY', 'TARGET_ONLY', 'BLOCKED_OR_UNKNOWN', 'MAINTAIN'}


def transfers():
    return [dict(event_id=f'saving-{m}', month=m, amount=300., source='Synthetic judge schedule',
                 included_in_baseline=True, pause_approved=True, pause_fee=0.) for m in range(1, 7)]


def build(customer, scenario, goal=None, **kwargs):
    goal = goal or normal_goal()
    crisis = make_crisis_plan(customer, scenario, normal_goal=goal, **kwargs)
    return crisis, build_action_plan(customer, crisis, scenario=scenario, opening_cash=kwargs.get('opening_cash'))


def by_id(plan, action_id):
    return next(a for a in plan['candidate_action_decisions'] if a['action_id'] == action_id)


def check_contract(plan):
    assert len(plan['prioritized_actions']) <= MAX_PRIMARY
    for a in plan['candidate_action_decisions']:
        assert a['status'] in STATUSES and a['not_executed'] is True
        assert a['decision'] in ('selected', 'considered', 'excluded')
        if a['decision'] == 'excluded':
            assert a['reason']
        if a['status'] in ('TARGET_ONLY', 'CONDITIONAL_ONLY', 'BLOCKED_OR_UNKNOWN'):
            # Never posted to the supported ledger.
            assert a['effect_on_horizon_need_cad'] in (None, 0.) or a['status'] == 'CONDITIONAL_ONLY'


def test_a_compound_shock_no_action_and_proposal_pause_frees_nothing():
    crisis, plan = build(account(), compound())
    check_contract(plan)
    d = plan['diagnosis']
    assert d['first_shortfall']['label'] == 'Month 2 end' and d['first_shortfall']['need'] == 120.
    assert d['no_action_horizon_need'] == 3360.
    assert plan['comparison']['identical'] and plan['comparison']['identical_reason']
    hold = by_id(plan, 'hold-goal-contribution')
    assert hold['effect_on_horizon_need_cad'] == 0. and 'CAD 0.00' in hold['instruction']
    assert by_id(plan, 'cover-earliest-shortfall')['status'] == 'TARGET_ONLY'


def test_a_confirmed_existing_pause_then_260_target_only():
    crisis, plan = build(account(), compound(), existing_transfers=transfers())
    check_contract(plan)
    after = plan['comparison']['supported_actions']
    assert after['first_shortfall']['label'] == 'Month 3 end' and after['first_shortfall']['need'] == 30.
    assert after['full_funding_need'] == 1560.
    assert plan['comparison']['funding_improvement'] == 1800.
    gap = by_id(plan, 'close-monthly-gap')
    assert gap['status'] == 'TARGET_ONLY' and gap['amount_cad'] == 260.
    assert any(a['status'] == 'SUPPORTED_MODELED' and a['action_id'].startswith('pause-') for a in plan['candidate_action_decisions'])


def test_b_late_receipt_does_not_cure_earlier_shortfall():
    scenario = ShockScenario(effects=[dict(type='one_off_receipt', value=2000., start_month=3)])
    crisis, plan = build(account(income=1800., spending=2400., cash=1000.), scenario,
                         goal=NormalGoal(name='None', monthly_contribution=0., reserve_target=0.))
    check_contract(plan)
    d = plan['diagnosis']
    assert d['first_shortfall']['label'] == 'Month 2 end' and d['first_shortfall']['need'] == 200.
    assert d['no_action_horizon_need'] == 600.
    receipt = by_id(plan, 'keep-receipt-m3')
    assert 'cannot cover that earlier gap' in receipt['instruction']


def test_c_supplied_deferral_and_conditional_bridge_never_posts_relief():
    customer = account(income=2200., spending=2400., cash=300.)
    goal = NormalGoal(name='No new transfer', monthly_contribution=0., reserve_target=0.)
    deferral = ShockScenario(effects=[dict(type='debt_payment_delta', value=-300., duration_months=2,
        debt_change_kind='deferral', repayment_month=4, repayment_amount=650., obligation_payment=300.,
        obligation_source='Synthetic loan schedule', payment_in_baseline=True)])
    _, plan = build(customer, deferral, goal=goal)
    assert plan['diagnosis']['first_shortfall']['label'] == 'Month 4 start'
    assert plan['diagnosis']['no_action_horizon_need'] == 950.
    # Original path with an observed loan payment: the bridge is a separate comparison only.
    history = customer['history'].assign(loan_payments=300.)
    customer = {**customer, 'history': history, 'raw_P': 300., 'P': 300., 'raw_F': 700., 'F': 700., 'has_running_loan': True}
    _, plan = build(customer, ShockScenario(phase='normal'), goal=goal)
    assert plan['diagnosis']['first_shortfall']['label'] == 'Month 2 end'
    assert plan['diagnosis']['no_action_horizon_need'] == 900.
    bridge = by_id(plan, 'loan-payment-bridge')
    assert bridge['status'] == 'CONDITIONAL_ONLY'
    assert 'buys time' in bridge['instruction'] and bridge['effect_on_horizon_need_cad'] >= 0
    assert plan['comparison']['identical']


def test_d_supplied_recovery_checkpoint_rebuild_14_months():
    snapshot = dict(account_id=17, assessment_month='2026-06', source='Synthetic checkpoint', cash_basis='judge_specified',
                    available_cash=3000., monthly_inflow=2700., monthly_spending=2400.,
                    supported_monthly_contribution=300., earmarked_near_term_cash=0.,
                    stable_cash_flow=True, obligations_covered=True)
    _, plan = build(account(), ShockScenario(phase='normal'), recovery_snapshot=snapshot)
    rebuild = by_id(plan, 'rebuild-reserve')
    assert rebuild['status'] == 'SUPPORTED_MODELED'
    assert 'CAD 7,200.00' in rebuild['instruction'] and 'CAD 4,200.00' in rebuild['instruction'] and '14 months' in rebuild['instruction']


def test_e_unspecified_income_change_keeps_need_unknown():
    scenario = ShockScenario(effects=[dict(type='income_multiplier', value=None, evidence='unknown')])
    _, plan = build(account(), scenario)
    check_contract(plan)
    assert plan['diagnosis']['no_action_horizon_need'] is None
    assert by_id(plan, 'confirm-missing-details')['status'] == 'BLOCKED_OR_UNKNOWN'
    assert plan['outcome'] == 'REVIEW_REQUIRED'


def test_stable_account_gets_maintain_not_invented_advice():
    _, plan = build(account(income=3000., spending=2400., cash=8000.), ShockScenario(phase='normal'),
                    goal=NormalGoal(name='None', monthly_contribution=0., reserve_target=0.))
    assert [a['status'] for a in plan['prioritized_actions']] == ['MAINTAIN']
    assert plan['outcome'] == 'MAINTAIN'
