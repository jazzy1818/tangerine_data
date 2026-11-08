"""Fault-injection tests: production guards must actually block invalid output."""

from copy import deepcopy
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import engine
import investment_triggers as it
from goal_validation import enforce_goal_validations
from test_investment_triggers import customer


class RuntimeEnforcementTests(unittest.TestCase):
    def run_corrupted(self, mutation, account=None, evidence=None, shock=None):
        def corrupt(plan, facts):
            damaged = deepcopy(plan)
            mutation(damaged)
            return enforce_goal_validations(damaged, facts)
        with patch('investment_triggers.enforce_goal_validations', side_effect=corrupt):
            return it.evaluate_investment_triggers(account or customer(), shock, evidence=evidence)

    def assert_blocked(self, result):
        self.assertEqual(result['runtime_validation']['status'], 'blocked')
        self.assertEqual(result['primary_goal'], 'DATA_LIMITED_REVIEW')
        self.assertEqual(result['normal_monthly_allocation'], 0)
        self.assertEqual(result['selected_scenario_monthly_allocation'], 0)
        self.assertFalse(result['automatic_trade_allowed'])
        self.assertEqual(result['security_recommendations'], [])
        self.assertEqual(result['proposed_actions'], [])
        self.assertFalse(result['funding_result_complete'])
        self.assertEqual(result['scenario_results'], [])
        self.assertEqual(result['trigger_ids'], ['G24'])
        self.assertTrue(any(flag.startswith('RUNTIME_VALIDATION_BLOCKED:') for flag in result['bank_review_flags']))

    def test_every_return_including_insufficient_history_is_enforced(self):
        with patch('investment_triggers.enforce_goal_validations', wraps=enforce_goal_validations) as guard:
            valid = it.evaluate_investment_triggers(customer())
            short = it.evaluate_investment_triggers(customer([3000]))
        self.assertEqual(guard.call_count, 2)
        for result in (valid, short):
            self.assertTrue(result['runtime_validation']['enforced'])
            self.assertEqual(len(result['runtime_validation']['checks']), 40)
            self.assertEqual(result['runtime_validation']['status'], 'passed')

    def test_dashboard_cli_pipeline_receives_enforced_results(self):
        result = engine.run_pipeline(20111, income_multiplier=.55, bills_increase_pct=.15)
        self.assertTrue(result['plan']['investment_plan']['runtime_validation']['enforced'])
        self.assertEqual(result['plan']['investment_plan']['runtime_validation']['status'], 'passed')

    def test_unsupported_etf_or_trade_is_blocked(self):
        for mutation in (lambda p: p.update(security_recommendations=['UNSUPPORTED_ETF']),
                         lambda p: p.update(automatic_trade_allowed=True),
                         lambda p: p.update(investment_suitability='VERIFIED')):
            self.assert_blocked(self.run_corrupted(mutation))

    def test_reserve_shortfall_cannot_leak_a_positive_investment_amount(self):
        result = self.run_corrupted(lambda p: p.update(normal_monthly_allocation=1500),
                                    account=customer(cash=4000, minimum=3800))
        self.assert_blocked(result)
        checks = {row['case_id']: row['status'] for row in result['runtime_validation']['checks']}
        self.assertEqual(checks['S01'], 'blocked')

    def test_unknown_cash_cannot_be_upgraded_to_verified_excess(self):
        def mutation(plan):
            for trigger in plan['triggers']:
                if trigger['id'] == 'G17':
                    trigger['state'] = 'active'
        self.assert_blocked(self.run_corrupted(mutation))

    def test_amount_cannot_exceed_calculated_historical_capacity(self):
        self.assert_blocked(self.run_corrupted(lambda plan: plan.update(normal_monthly_allocation=100000)))

    def test_unknown_expense_cannot_be_marked_fully_funded(self):
        facts = it.AnalystEvidence(source='Explicit test scenario', known_expenses=(it.KnownExpense(None, 2, 'Tuition'),))
        result = self.run_corrupted(lambda p: p.update(funding_result_complete=True), evidence=facts)
        self.assert_blocked(result)
        self.assertTrue(any('S15' in issue for issue in result['runtime_validation']['violations']))

    def test_known_expense_cannot_be_demoted_to_debt_optimization(self):
        facts = it.AnalystEvidence(source='Explicit test scenario', costly_debt_verified=True,
                                  known_expenses=(it.KnownExpense(6000, 1, 'Tuition'),))
        result = self.run_corrupted(lambda p: p.update(primary_goal='MANAGE_DEBT_OBLIGATIONS'), evidence=facts)
        self.assert_blocked(result)

    def test_shock_deficit_cannot_be_presented_as_maintain(self):
        result = self.run_corrupted(lambda p: p.update(primary_goal='MAINTAIN_AND_REVIEW'),
                                    shock={'income_multiplier': 0., 'bills_increase_pct': 0., 'one_off_costs': 0.})
        self.assert_blocked(result)

    def test_invented_recurring_income_is_blocked(self):
        def mutation(plan):
            path = plan['scenario_results'][0]['no_allocation']
            path['monthly_net_before_contribution'] += 5000
        self.assert_blocked(self.run_corrupted(mutation))

    def test_fake_receipt_or_double_debited_loan_is_blocked(self):
        for field, amount in (('one_off_receipt', 5000), ('extra_expenses', 500)):
            def mutation(plan):
                plan['scenario_results'][0]['no_allocation']['schedule'][1][field] += amount
            self.assert_blocked(self.run_corrupted(mutation))

    def test_claiming_final_cash_without_matching_path_is_blocked(self):
        def mutation(plan):
            plan['scenario_results'][0]['no_allocation']['ending_cash'] += 1000
        self.assert_blocked(self.run_corrupted(mutation))

    def test_nonfinite_projection_is_blocked(self):
        def mutation(plan):
            plan['scenario_results'][0]['no_allocation']['schedule'][1]['closing_cash'] = float('nan')
        self.assert_blocked(self.run_corrupted(mutation))

    def test_missing_projection_field_fails_closed_without_stopping_analysis(self):
        def mutation(plan):
            del plan['scenario_results'][0]['no_allocation']['schedule'][1]['closing_cash']
        self.assert_blocked(self.run_corrupted(mutation))

    def test_validation_is_not_removed_by_python_optimization(self):
        root = Path(__file__).resolve().parents[1]
        script = '''
import sys
sys.path.insert(0, 'tests')
from test_investment_triggers import customer
import investment_triggers as it
original = it.enforce_goal_validations
def corrupt(plan, facts):
    plan['automatic_trade_allowed'] = True
    return original(plan, facts)
it.enforce_goal_validations = corrupt
result = it.evaluate_investment_triggers(customer())
if result['automatic_trade_allowed'] or result['runtime_validation']['status'] != 'blocked':
    raise RuntimeError('Production enforcement was bypassed')
'''
        completed = subprocess.run([sys.executable, '-O', '-c', script], cwd=root, capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == '__main__':
    unittest.main()
