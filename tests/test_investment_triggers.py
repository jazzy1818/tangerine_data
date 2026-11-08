"""Behavior tests for allocation sizing and investment review gates."""

import copy
import json
import random
import unittest

import pandas as pd

import engine
from investment_triggers import (
    AnalystEvidence, InvestmentPolicy, KnownExpense, StressScenario,
    evaluate_investment_triggers, simulate_allocation,
)


def customer(surpluses=None, cash=25000.0, spending=3500.0, minimum=20000.0):
    surpluses = surpluses if surpluses is not None else [3000, 3000, 2000, 3000, 3000, 3000]
    count = len(surpluses)
    history = pd.DataFrame({
        'month': pd.period_range('2025-01', periods=count, freq='M').astype(str),
        'money_in': [spending + value for value in surpluses], 'money_out': spending,
        'household_bills': 1000.0, 'insurance': 100.0, 'loan_payments': 0.0,
        'avg_daily_balance': cash, 'month_end_balance': cash,
        'min_balance': minimum, 'days_below_zero': 0,
    })
    return {'history': history}


def state(result, trigger):
    return next(row['state'] for row in result['triggers'] if row['id'] == trigger)


class InvestmentTriggerTests(unittest.TestCase):
    def test_user_example_and_suitability_gate(self):
        result = evaluate_investment_triggers(customer())
        self.assertEqual(result['normal_monthly_allocation'], 1500)
        self.assertEqual(result['primary_goal'], 'DATA_LIMITED_REVIEW')
        self.assertIn('POTENTIAL_SURPLUS_ALLOCATION', result['supporting_goals'])
        self.assertEqual(result['security_recommendations'], [])
        self.assertFalse(result['automatic_trade_allowed'])
        self.assertEqual(result['investment_suitability'], 'UNVERIFIED')
        self.assertEqual(state(result, 'G16'), 'active')
        self.assertEqual(state(result, 'G17'), 'unknown')
        self.assertEqual(len(result['triggers']), 26)
        json.dumps(result, allow_nan=False)

    def test_reserve_first_no_double_allocation(self):
        result = evaluate_investment_triggers(customer(cash=4000, minimum=3800))
        self.assertEqual(result['primary_goal'], 'BUILD_EMERGENCY_RESERVE')
        self.assertEqual(result['normal_monthly_allocation'], 0)
        self.assertEqual(result['features']['reserve_gap'], 6500)
        # Earmarking retained liquid savings is not an investment cash withdrawal.
        self.assertEqual(result['reserve_monthly_earmark'], 1500)
        baseline = result['scenario_results'][0]['no_allocation']
        self.assertEqual(baseline['ending_cash'], 22000)

    def test_negative_days_override_positive_monthly_surplus(self):
        c = customer()
        c['history'].loc[1, ['min_balance', 'days_below_zero']] = [-100, 2]
        result = evaluate_investment_triggers(c)
        self.assertEqual(result['primary_goal'], 'PROTECT_OPERATING_CASH')
        self.assertEqual(result['normal_monthly_allocation'], 0)
        self.assertEqual(state(result, 'G10'), 'active')

    def test_small_positive_minimum_is_also_timing_risk(self):
        result = evaluate_investment_triggers(customer(minimum=100))
        self.assertEqual(result['normal_monthly_allocation'], 0)
        self.assertEqual(result['primary_goal'], 'PROTECT_OPERATING_CASH')

    def test_deficit_months_never_support_fixed_investment(self):
        result = evaluate_investment_triggers(customer([3000, -200, 3000, -200, 3000, 3000]))
        self.assertEqual(result['normal_monthly_allocation'], 0)
        self.assertEqual(result['primary_goal'], 'SMOOTH_IRREGULAR_INCOME')
        self.assertEqual(state(result, 'G03'), 'active')

    def test_negative_median_stabilizes(self):
        result = evaluate_investment_triggers(customer([-100] * 6))
        self.assertEqual(result['primary_goal'], 'STABILIZE_CASHFLOW')
        self.assertEqual(result['normal_monthly_allocation'], 0)

    def test_thin_surplus_not_forced(self):
        result = evaluate_investment_triggers(customer([50] * 6))
        self.assertEqual(state(result, 'G02'), 'active')
        self.assertEqual(result['normal_monthly_allocation'], 0)

    def test_income_volatility_and_apparent_windfall(self):
        c = customer([100, 10000, 100, 10000, 100, 10000])
        self.assertEqual(state(evaluate_investment_triggers(c), 'G04'), 'active')
        c = customer([3000, 3000, 100000, 3000, 3000, 3000])
        result = evaluate_investment_triggers(c)
        self.assertEqual(state(result, 'G21'), 'active')
        self.assertLessEqual(result['normal_monthly_allocation'], 2250)

    def test_deterioration_blocks_new_allocation(self):
        result = evaluate_investment_triggers(customer([5000] * 3 + [200] * 3))
        self.assertEqual(state(result, 'G05'), 'active')
        self.assertEqual(result['normal_monthly_allocation'], 0)

    def test_stale_average_cannot_hide_latest_cash_depletion(self):
        c = customer()
        c['history'].loc[5, 'month_end_balance'] = 100
        c['history'].loc[5, 'min_balance'] = 0
        result = evaluate_investment_triggers(c)
        self.assertEqual(result['features']['opening_cash_estimate'], 100)
        self.assertEqual(result['normal_monthly_allocation'], 0)

    def test_short_duplicate_gapped_and_malformed_history_fail_closed(self):
        examples = [customer([3000]), customer()]
        examples[1]['history'].loc[1, 'month'] = '2025-01'
        gap = customer()
        gap['history'].loc[5, 'month'] = '2025-08'
        examples.append(gap)
        for column, value in [('money_in', float('nan')), ('money_out', -1),
                              ('month', 'bad-month'), ('days_below_zero', 45),
                              ('insurance', -1), ('min_balance', 30000)]:
            c = customer()
            c['history'].loc[1, column] = value
            examples.append(c)
        for c in examples:
            with self.subTest(history=c['history'].to_dict()):
                result = evaluate_investment_triggers(c)
                self.assertEqual(result['primary_goal'], 'DATA_LIMITED_REVIEW')
                self.assertEqual(result['normal_monthly_allocation'], 0)
                json.dumps(result, allow_nan=False)

    def test_missing_timing_and_fixed_fields(self):
        for column in ['min_balance', 'month_end_balance', 'days_below_zero', 'insurance']:
            c = customer()
            c['history'] = c['history'].drop(columns=column)
            result = evaluate_investment_triggers(c)
            self.assertEqual(result['normal_monthly_allocation'], 0)
            self.assertEqual(state(result, 'G24'), 'active')

    def test_zero_spending_and_negative_balance(self):
        c = customer(spending=0)
        c['history'][['household_bills', 'insurance']] = 0
        self.assertEqual(evaluate_investment_triggers(c)['primary_goal'], 'DATA_LIMITED_REVIEW')
        c = customer(cash=-500, minimum=-600)
        result = evaluate_investment_triggers(c)
        self.assertEqual(result['primary_goal'], 'STABILIZE_CASHFLOW')
        self.assertEqual(result['normal_monthly_allocation'], 0)

    def test_selected_job_loss_pauses_and_reports_remaining_gap(self):
        shock = {'income_multiplier': .55, 'bills_increase_pct': .15, 'one_off_costs': 30000}
        result = evaluate_investment_triggers(customer(), shock)
        self.assertEqual(result['normal_monthly_allocation'], 1500)
        self.assertEqual(result['selected_scenario_monthly_allocation'], 0)
        self.assertTrue(result['pause_optional_contributions'])
        self.assertEqual(result['primary_goal'], 'STABILIZE_CASHFLOW')
        self.assertEqual(state(result, 'G25'), 'active')
        self.assertGreater(result['features']['selected_scenario_additional_cash_needed'], 0)

    def test_scenario_amount_can_reduce_without_full_pause(self):
        shock = {'income_multiplier': .65, 'bills_increase_pct': 0, 'one_off_costs': 0}
        result = evaluate_investment_triggers(customer(), shock)
        self.assertEqual(result['normal_monthly_allocation'], 1500)
        self.assertEqual(result['selected_scenario_monthly_allocation'], 725)
        self.assertEqual(result['all_scenarios_monthly_allocation'], 0)
        self.assertTrue(result['pause_optional_contributions'])

    def test_allocation_is_debited_and_minimum_includes_month_zero(self):
        kwargs = dict(opening_cash=20000, monthly_inflow=6000, monthly_spending=3500,
                      household_bills=1000, cash_floor=10500, scenario=StressScenario('Baseline'))
        zero = simulate_allocation(**kwargs, contribution=0)
        fixed = simulate_allocation(**kwargs, contribution=1500)
        self.assertEqual(zero['ending_cash'] - fixed['ending_cash'], 9000)
        self.assertEqual(fixed['minimum_cash'], 20000)
        kwargs['scenario'] = StressScenario('Immediate repair', one_off_costs=21000)
        self.assertEqual(simulate_allocation(**kwargs, contribution=0)['first_shortfall_month'], 0)

    def test_fixed_payments_not_added_twice(self):
        c = customer()
        c['history']['loan_payments'] = 1500
        result = evaluate_investment_triggers(c)
        self.assertEqual(state(result, 'G12'), 'active')
        self.assertEqual(result['primary_goal'], 'MANAGE_DEBT_OBLIGATIONS')
        self.assertEqual(result['scenario_results'][0]['no_allocation']['monthly_net_before_contribution'], 3000)
        self.assertEqual(result['normal_monthly_allocation'], 0)

    def test_explicit_expense_is_debited_once_and_respected(self):
        evidence = AnalystEvidence(source='Judge card', known_expenses=(KnownExpense(12000, 2, 'Tuition'),))
        result = evaluate_investment_triggers(customer(), evidence=evidence)
        self.assertEqual(result['primary_goal'], 'PREPARE_KNOWN_EXPENSE')
        path = result['scenario_results'][0]['no_allocation']
        self.assertEqual(path['ending_cash'], 25000 + 6 * 3000 - 12000)
        self.assertEqual(path['schedule'][2]['extra_expenses'], 12000)
        self.assertEqual(state(result, 'G20'), 'active')

    def test_beyond_horizon_obligation_is_held_not_spent_twice(self):
        evidence = AnalystEvidence(source='Judge card', known_expenses=(KnownExpense(10000, 12, 'Tuition'),))
        result = evaluate_investment_triggers(customer(), evidence=evidence)
        path = result['scenario_results'][0]['no_allocation']
        self.assertEqual(path['required_cash_floor'], 20500)
        self.assertEqual(path['ending_cash'], 43000)

    def test_short_horizon_blocks_long_term_allocation(self):
        evidence = AnalystEvidence(source='Judge card', horizon_months=12, objective='Home deposit')
        result = evaluate_investment_triggers(customer(), evidence=evidence)
        self.assertEqual(result['normal_monthly_allocation'], 0)
        self.assertEqual(result['primary_goal'], 'PREPARE_KNOWN_EXPENSE')

    def test_verified_cash_does_not_verify_suitability(self):
        result = evaluate_investment_triggers(customer(), evidence=AnalystEvidence(source='Judge card', available_cash=25000))
        self.assertEqual(state(result, 'G17'), 'unknown')
        # Cash alone does not establish that obligations have been reviewed.
        self.assertEqual(result['investment_suitability'], 'UNVERIFIED')
        self.assertEqual(result['security_recommendations'], [])

    def test_complete_profile_still_cannot_auto_approve_security(self):
        evidence = AnalystEvidence(source='Authorized scenario', available_cash=25000, sole_control_verified=True,
                                   objective='Long-term wealth', horizon_months=120, risk_tolerance='Moderate',
                                   capacity_for_loss='Documented', holdings_reviewed=True, obligations_reviewed=True)
        result = evaluate_investment_triggers(customer(), evidence=evidence)
        self.assertEqual(result['investment_suitability'], 'ANALYST_REVIEW_REQUIRED')
        self.assertFalse(result['automatic_trade_allowed'])
        self.assertEqual(result['security_recommendations'], [])

    def test_expensive_debt_blocks_investment_without_invented_payoff(self):
        result = evaluate_investment_triggers(customer(), evidence=AnalystEvidence(source='Judge card', costly_debt_verified=True))
        self.assertEqual(result['primary_goal'], 'MANAGE_DEBT_OBLIGATIONS')
        self.assertEqual(result['normal_monthly_allocation'], 0)

    def test_history_replay_accumulates_transfers(self):
        result = evaluate_investment_triggers(customer())
        replay = result['historical_replay']
        self.assertEqual(replay[-1]['cumulative_allocations'], 9000)
        self.assertEqual(replay[-1]['adjusted_minimum_cash'], 11000)

    def test_historical_assessment_excludes_future_rows_and_customer_metrics(self):
        original = customer()
        future = customer([3000, 3000, 2000, 3000, 3000, 3000] + [-3000] * 6)
        future.update(raw_I=0, raw_B=-100000, B=-100000)
        old = evaluate_investment_triggers(original, as_of='2025-06')
        actual = evaluate_investment_triggers(future, as_of='2025-06')
        self.assertEqual(old, actual)

    def test_policy_and_scenario_validation(self):
        for kwargs in [{'allocation_fraction': 2}, {'projection_months': 0}, {'minimum_history_months': 1}, {'reserve_months': float('nan')}]:
            with self.assertRaises(ValueError):
                InvestmentPolicy(**kwargs)
        for kwargs in [{'income_multiplier': -1}, {'bills_increase_pct': -2}, {'one_off_costs': float('inf')}]:
            with self.assertRaises(ValueError):
                StressScenario('Invalid', **kwargs)
        with self.assertRaises(ValueError):
            AnalystEvidence(available_cash=25000)
        with self.assertRaises(ValueError):
            AnalystEvidence(source='Judge card', sole_control_verified='false')

    def test_assessment_does_not_mutate_inputs(self):
        c = customer()
        original = copy.deepcopy(c['history'])
        evaluate_investment_triggers(c)
        pd.testing.assert_frame_equal(original, c['history'])

    def test_zero_cash_requires_source_too(self):
        with self.assertRaises(ValueError):
            AnalystEvidence(available_cash=0)

    def test_unverified_timing_and_loan_release_stay_unknown(self):
        result = evaluate_investment_triggers(customer())
        for trigger in ['G07', 'G13', 'G14', 'G17', 'G19', 'G20', 'G23']:
            self.assertEqual(state(result, trigger), 'unknown')

    def test_mixed_accounts_are_not_pooled_into_one_profile(self):
        c = customer()
        c['history']['account_id'] = [1, 1, 1, 2, 2, 2]
        result = evaluate_investment_triggers(c)
        self.assertEqual(result['primary_goal'], 'DATA_LIMITED_REVIEW')

    def test_candidate_amounts_never_overdraw_cash_floor(self):
        rng = random.Random(42)
        for _ in range(30):
            surplus = rng.uniform(2000, 5000)
            c = customer([surplus] * 6, cash=rng.uniform(15000, 40000), minimum=13000)
            result = evaluate_investment_triggers(c)
            normal = result['normal_monthly_allocation']
            self.assertLessEqual(normal, .75 * surplus)
            for scenario in result['scenario_results']:
                revised = scenario['revised_monthly_allocation']
                self.assertLessEqual(revised, normal)
                if revised > 0:
                    self.assertTrue(scenario['revised_allocation']['preserves_cash_floor'])
                    self.assertLessEqual(revised, scenario['revised_allocation']['monthly_net_before_contribution'] + .01)

    def test_stricter_reserve_policy_does_not_increase_allocation(self):
        c = customer()
        loose = evaluate_investment_triggers(c)
        strict = evaluate_investment_triggers(c, policy=InvestmentPolicy(reserve_months=6))
        self.assertLessEqual(strict['normal_monthly_allocation'], loose['normal_monthly_allocation'])

    def test_immediate_expense_and_in_horizon_expense_count_once_each(self):
        expenses = (KnownExpense(1000, 0, 'Immediate'), KnownExpense(2000, 3, 'Later'))
        result = simulate_allocation(opening_cash=20000, monthly_inflow=6000, monthly_spending=3500,
                                     household_bills=1000, contribution=1500, cash_floor=10000,
                                     scenario=StressScenario('Repair', one_off_costs=500), known_expenses=expenses)
        self.assertEqual(result['initial_cash_after_costs'], 18500)
        self.assertEqual(result['ending_cash'], 22500)

    def test_unknown_expense_does_not_turn_into_a_zero_cost(self):
        facts = AnalystEvidence(source='Explicit test scenario', known_expenses=(KnownExpense(None, 2, 'Tuition'),))
        result = evaluate_investment_triggers(customer(), evidence=facts)
        self.assertEqual(result['primary_goal'], 'PREPARE_KNOWN_EXPENSE')
        self.assertEqual(result['normal_monthly_allocation'], 0)
        self.assertIsNone(result['features']['known_expenses'][0]['amount'])
        self.assertFalse(result['funding_result_complete'])
        self.assertTrue(all(not row['funding_result_complete'] for row in result['scenario_results']))

    def test_unquantified_event_keeps_known_effects_without_inventing_more(self):
        facts = AnalystEvidence(source='Explicit test scenario', event_description='Divorce', event_financial_effect='unspecified')
        result = evaluate_investment_triggers(customer(), {'income_multiplier': 1., 'bills_increase_pct': 0., 'one_off_costs': 1000.}, evidence=facts)
        self.assertEqual(result['primary_goal'], 'DATA_LIMITED_REVIEW')
        self.assertFalse(result['funding_result_complete'])
        self.assertEqual(result['scenario_results'][-1]['no_allocation']['initial_cash_after_costs'], 24000)

    def test_one_off_receipt_never_becomes_recurring_income(self):
        c = customer()
        before = evaluate_investment_triggers(c)
        result = evaluate_investment_triggers(c, {'income_multiplier': 1., 'bills_increase_pct': 0., 'one_off_receipt': 5000.})
        path = result['scenario_results'][-1]['no_allocation']
        self.assertEqual(path['initial_cash_after_costs'], 30000)
        self.assertEqual(path['monthly_net_before_contribution'], 3000)
        self.assertEqual(path['ending_cash'], 48000)
        self.assertEqual(sum(row['one_off_receipt'] for row in path['schedule']), 5000)
        self.assertEqual(result['normal_monthly_allocation'], before['normal_monthly_allocation'])

    def test_verified_cash_and_reviewed_obligations_establish_only_excess_cash(self):
        facts = AnalystEvidence(source='Explicit test scenario', available_cash=25000, obligations_reviewed=True)
        result = evaluate_investment_triggers(customer(), evidence=facts)
        self.assertEqual(state(result, 'G17'), 'active')
        self.assertEqual(result['primary_goal'], 'MAINTAIN_AND_REVIEW')
        self.assertEqual(result['security_recommendations'], [])

    def test_real_account_and_official_metrics_remain_unchanged(self):
        c = engine.know_customer(20111)
        shock = engine.take_shock(c, .55, .15, 1000)
        before = copy.deepcopy(shock)
        plans = engine.make_plan(c, shock)
        self.assertEqual(shock, before)
        self.assertIn('investment_plan', plans)
        self.assertEqual(len(plans['investment_plan']['triggers']), 26)
        rows = c['history']
        expected = engine.calculate_runway(float(rows.tail(6).avg_daily_balance.mean()) - 1000,
                                           float(rows.money_out.median()) + .15 * float(rows.household_bills.median()) - .55 * float(rows.money_in.median()))
        self.assertEqual(shock['runway'], expected)


if __name__ == '__main__':
    unittest.main()
