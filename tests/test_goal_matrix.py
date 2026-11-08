"""Acceptance audit keyed to the unchanged bank-facing CSV.

Fixtures below are explicitly synthetic examples, NOT discovered customer facts.
They instantiate the qualitative checkpoint descriptions. Additional scenario
facts are attached only to rows that explicitly state them; missing dollar values,
deadlines, goals, cash or risk data are not manufactured to force a CSV outcome.
"""

import csv
from pathlib import Path
import unittest

import pandas as pd

from investment_triggers import AnalystEvidence, KnownExpense, evaluate_investment_triggers

ROOT = Path(__file__).resolve().parents[1]
MATRIX = list(csv.DictReader((ROOT / 'Tangerine_Goal_Trigger_Test_Matrix_v2_Bank_Facing.csv').open()))

# Preserve these differences explicitly; do not weaken the evidence gates just
# to claim literal agreement with an under-specified/contradictory expected label.
AUDIT_NOTES = {
    'S10': 'No loan in one table cannot establish current cash or other debts. DATA_LIMITED_REVIEW is retained rather than inferring sufficient finances for MAINTAIN.',
    'S11': 'Conflict: G17 requires verified available cash/obligations. With historical proxy only, G17 must be unknown, while G24 is active and primary goal is DATA_LIMITED_REVIEW.',
    'S12': 'Verified cash does not establish all obligations/earmarks. G17 stays unknown without an obligations review; investment readiness review is allowed, but never a security recommendation.',
    'S20': 'Goal completion alone supplies neither current cash nor a next objective. ALLOCATE_SURPLUS is conditional in the must_not_do column; missing evidence yields DATA_LIMITED_REVIEW.',
}


def fixture(case):
    """Representative synthetic record; never loaded by the application."""
    months = pd.period_range('2025-01', periods=12, freq='M')
    h = pd.DataFrame({
        'account_id': 1, 'month': months.astype(str), 'money_in': 6500.0,
        'money_out': 3500.0, 'household_bills': 1000.0,
        'insurance': 100.0, 'loan_payments': 0.0, 'avg_daily_balance': 25000.0,
        'month_end_balance': 25000.0, 'min_balance': 20000.0, 'days_below_zero': 0,
    })
    c, shock, facts, transactions = {'account_id': 1, 'history': h}, None, {}, None
    def low_reserve():
        h['avg_daily_balance'] = h['month_end_balance'] = 4000.0
        h['min_balance'] = 3800.0
    if case in ('S01', 'S07', 'S09', 'S17', 'S19', 'S33', 'S36', 'S37', 'S39'):
        low_reserve()
    if case == 'S02':
        h['money_in'] = [3400.] * 8 + [6500.] * 4
    elif case == 'S03':
        h['money_in'] = [3300., 6500., 3300., 6500., 3300., 6500., 3300., 6500., 3300., 6500., 6500., 6500.]
    elif case == 'S04':
        h.loc[1, ['min_balance', 'days_below_zero']] = [-100., 2]
    elif case == 'S05':
        h['month_end_balance'] = [25000.] * 6 + [10000.] * 6
        h['avg_daily_balance'] = h['month_end_balance']
        h['min_balance'] = h['month_end_balance'] - 1000
    elif case == 'S06':
        h['money_in'] = [3600., 13500.] * 6
        h.loc[1, ['min_balance', 'days_below_zero']] = [-100., 2]
        tx = []
        for month in months:
            tx.extend([
                {'account_id': 1, 'date': str(month) + '-10', 'signed_amount': -1000., 'purpose': 'household bills', 'partner_bank': 'AB', 'partner_account': '123'},
                {'account_id': 1, 'date': str(month) + '-25', 'signed_amount': 6500., 'purpose': '', 'partner_bank': 'CD', 'partner_account': '456'},
            ])
        transactions = pd.DataFrame(tx)
    elif case == 'S07':
        h['money_in'], h['insurance'] = 3700., 2100.
    elif case == 'S08':
        h['loan_payments'] = 1500.
        c['source_loan_status'] = 'C'
    elif case in ('S09', 'S33'):
        facts['costly_debt_verified'] = True  # Stated in the checkpoint, no APR number invented.
        if case == 'S33':
            facts['known_expenses'] = (KnownExpense(None, 1, 'Incoming bill; amount not supplied'),)
    elif case == 'S10':
        c['source_loan_status'] = None
    elif case == 'S12':
        facts.update(available_cash=25000., objective='Documented long-horizon goal', horizon_months=120)
    elif case == 'S13':
        facts['available_cash'] = 25000.
    elif case == 'S14':
        facts.update(objective='House purchase', horizon_months=18,
                     known_expenses=(KnownExpense(None, 18, 'House purchase; amount not supplied'),))
    elif case == 'S15':
        facts['known_expenses'] = (KnownExpense(None, None, 'Tuition; amount and timing not supplied'),)
    elif case == 'S16':
        h.loc[1, 'money_in'] = 50000.  # An observed account deposit, not a verified inheritance.
    elif case in ('S17', 'S30'):
        facts['windfall_verified'] = True  # Amount/availability NOT added to current cash.
    elif case == 'S18':
        h['money_in'] = [3400.] * 3 + [4000.] * 3 + [6500.] * 6
    elif case == 'S19':
        facts['prior_shock_verified'] = True
    elif case == 'S20':
        facts['goal_completed_verified'] = True
    elif case == 'S21':
        c['history'] = h.iloc[:1].copy()
    elif case == 'S22':
        h['avg_daily_balance'] = h['month_end_balance'] = -500.
        h['min_balance'], h['days_below_zero'] = -600., 2
    elif case == 'S23':
        c['source_loan_status'] = 'A'
    elif case == 'S24':
        h['cash_withdrawals_genuine'] = 3000.
    elif case == 'S26':
        c['demographics'] = {'relationship': 'Account'}  # No sole control is asserted.
    elif case in ('S27', 'S34'):
        # Explicit numeric test shock, rather than guessing a financial effect
        # merely from a free-text event name. These are illustrative test inputs.
        h['money_in'] = 6000.
        shock = {'income_multiplier': .55, 'bills_increase_pct': 0., 'one_off_costs': 0.}
        if case == 'S34':
            facts['goal_completed_verified'] = True
    elif case in ('S28', 'S29'):
        facts.update(event_description='Backflip' if case == 'S28' else 'Divorce',
                     event_financial_effect='none' if case == 'S28' else 'unspecified')
    elif case == 'S32':
        facts['known_expenses'] = (KnownExpense(None, 2, 'Goal deadline; amount not supplied'),)
    elif case == 'S35':
        h.loc[1, 'money_out'] = 15500.  # Observed purchase, no recurring-cost assumption.
    elif case == 'S36':
        h['money_in'] = [3600., 13500.] * 6
        h['household_bills'], h['loan_payments'] = 800., 2200.
    elif case == 'S37':
        h['money_in'] = 3400.
        shock = {'income_multiplier': .55, 'bills_increase_pct': 0., 'one_off_costs': 0.}
    elif case == 'S38':
        facts['equities_excluded'] = True
    elif case == 'S40':
        h['money_in'] = [0.] * 10 + [50000., 0.]
    evidence = AnalystEvidence(source=f'SYNTHETIC acceptance fixture for {case}', **facts) if facts else AnalystEvidence()
    return c, shock, evidence, transactions


def assess(case):
    customer, shock, evidence, transactions = fixture(case)
    return evaluate_investment_triggers(customer, shock, evidence=evidence, transactions=transactions)


class GoalMatrixTests(unittest.TestCase):
    def test_manifest_has_all_forty_original_cases(self):
        self.assertEqual([row['case_id'] for row in MATRIX], [f'S{i:02}' for i in range(1, 41)])

    def check_case(self, row):
        case = row['case_id']
        result = assess(case)
        self.assertTrue(result['runtime_validation']['enforced'])
        self.assertEqual(result['runtime_validation']['status'], 'passed', result['runtime_validation']['violations'])
        self.assertEqual([check['case_id'] for check in result['runtime_validation']['checks']],
                         [f'S{i:02}' for i in range(1, 41)])
        states = {trigger['id']: trigger['state'] for trigger in result['triggers']}
        self.assertFalse(result['automatic_trade_allowed'])
        self.assertEqual(result['security_recommendations'], [])
        self.assertGreaterEqual(result['normal_monthly_allocation'], 0)
        self.assertGreaterEqual(result['reserve_monthly_earmark'], 0)
        expected_goal = 'DATA_LIMITED_REVIEW' if case in ('S10', 'S20') else row['expected_primary_goal']
        self.assertEqual(result['primary_goal'], expected_goal, AUDIT_NOTES.get(case, row['scenario']))
        for trigger in row['expected_trigger_ids'].split(','):
            expected_state = 'unknown' if case in ('S11', 'S12') and trigger == 'G17' else 'active'
            self.assertEqual(states[trigger], expected_state, f'{case}: {trigger}; {AUDIT_NOTES.get(case, row["scenario"])}')
        flags = '\n'.join(result['bank_review_flags'])
        if case in ('S01', 'S07', 'S09', 'S17', 'S19', 'S22', 'S33', 'S39'):
            self.assertEqual(result['normal_monthly_allocation'], 0)
        if case in ('S02', 'S03', 'S04', 'S05', 'S06', 'S18', 'S21', 'S22', 'S35', 'S36', 'S37', 'S40'):
            self.assertEqual(result['normal_monthly_allocation'], 0)
        if case in ('S08', 'S23'):
            self.assertEqual(states['G13'], 'unknown')
            self.assertEqual(states['G14'], 'unknown')
        if case in ('S09', 'S33'):
            self.assertGreater(result['features']['operating_cash_floor'], 0)
        if case == 'S10':
            self.assertIn('not evidence of being debt-free', flags)
        if case in ('S11', 'S31'):
            self.assertIn('CURRENT_LIQUID_CASH_UNVERIFIED', flags)
            self.assertEqual(result['proposed_actions'], [])
        if case in ('S13', 'S20', 'S26', 'S38'):
            self.assertEqual(result['proposed_actions'], [])
        if case in ('S14', 'S15', 'S32', 'S33'):
            self.assertIn('KNOWN_EXPENSE_UNQUANTIFIED', flags)
            self.assertFalse(result['funding_result_complete'])
            self.assertFalse(any(r['all_tested_scenarios_pass'] for r in result['candidate_results']))
        if case in ('S16', 'S17', 'S30'):
            baseline = result['scenario_results'][0]['no_allocation']
            # No unspecified receipt is invented or promoted to recurring salary.
            self.assertEqual(baseline['initial_cash_after_costs'], result['features']['opening_cash_estimate'])
        if case == 'S19':
            self.assertIn('CURRENT_LIQUID_CASH_UNVERIFIED', flags)
        if case == 'S23':
            self.assertIn('LOAN_FINISHED_IN_SOURCE', flags)
        if case == 'S24':
            self.assertIn('ADJUSTABLE_SPENDING_UNVERIFIED', flags)
        if case == 'S25':
            self.assertIn('COVERAGE_UNVERIFIED', flags)
        if case == 'S26':
            self.assertIn('ACCOUNT_CONTROL_UNVERIFIED', flags)
        if case in ('S27', 'S34'):
            self.assertTrue(result['pause_optional_contributions'])
            self.assertEqual(result['selected_scenario_monthly_allocation'], 0)
        if case == 'S28':
            self.assertEqual(result['scenario_results'][0]['no_allocation']['schedule'][0]['extra_expenses'], 0)
        if case == 'S29':
            self.assertIn('SHOCK_UNDER_SPECIFIED', flags)
            self.assertFalse(result['funding_result_complete'])
        if case == 'S36':
            self.assertIn('BUILD_EMERGENCY_RESERVE', result['supporting_goals'])
            self.assertIn('MANAGE_DEBT_OBLIGATIONS', result['supporting_goals'])
        if case == 'S37':
            self.assertGreater(result['features']['selected_scenario_additional_cash_needed'], 0)
        if case == 'S38':
            self.assertIn('EQUITIES_EXCLUDED', flags)
        if case == 'S39':
            # Reserve earmarks never count as newly created money.
            path = result['scenario_results'][0]['no_allocation']
            self.assertEqual(path['ending_cash'], path['initial_cash_after_costs'] + 6 * path['monthly_net_before_contribution'])


def _test_for(row):
    def test(self):
        self.check_case(row)
    return test


for _row in MATRIX:
    setattr(GoalMatrixTests, f'test_{_row["case_id"]}', _test_for(_row))


if __name__ == '__main__':
    unittest.main()
