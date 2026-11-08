"""Mandatory runtime enforcement of the bank-facing S01-S40 checkpoints.

This is production policy, NOT a test runner. Every allocation evaluation must
call enforce_goal_validations, including insufficient-data returns. No account
IDs, fixture values, free-text event matching, CSV reads, feature flags, or test
imports activate these rules. Conditions are derived from the actual inputs.

The original CSV's evidence exceptions S10/S11/S12/S20 remain intentional:
unknown facts must never be manufactured to satisfy an expected class label.
Keep this layer in place when adding a new selector, model, goal, or UI route.
"""

from copy import deepcopy
from dataclasses import dataclass
from math import isfinite
from typing import Callable, Mapping

POLICY_VERSION = 'bank-facing-v2-runtime-1'


def _all(*values):
    """Three-valued AND: absent evidence is unknown, never silently false."""
    if any(value is False for value in values):
        return False
    return None if any(value is None for value in values) else True


def _trigger(plan, code):
    return next((item['state'] for item in plan.get('triggers', []) if item['id'] == code), 'unknown')


def _has_flag(plan, name):
    return any(flag.startswith(name + ':') for flag in plan.get('bank_review_flags', []))


def _no_investment(plan, facts):
    if plan['normal_monthly_allocation'] != 0:
        return 'Fixed investment allocation must be zero under this condition.'
    if plan['primary_goal'] in ('INVESTMENT_READINESS_REVIEW', 'ALLOCATE_SURPLUS'):
        return 'Protective needs must take priority over a long-term allocation goal.'
    return None


def _no_forced_action(plan, facts):
    return None if not plan['proposed_actions'] else 'Missing goals, cash, or authority must not produce an action instruction.'


def _proxy_review(plan, facts):
    if _trigger(plan, 'G17') == 'active':
        return 'Historical balances cannot establish verified excess cash (G17).'
    if not _has_flag(plan, 'CURRENT_LIQUID_CASH_UNVERIFIED'):
        return 'Historical cash must carry an explicit unverified-current-cash flag.'
    if plan['primary_goal'] == 'INVESTMENT_READINESS_REVIEW':
        return 'A conditional surplus estimate without supplied current cash requires data review.'
    return _no_forced_action(plan, facts)


def _incomplete(plan, facts):
    if plan['funding_result_complete']:
        return 'Unquantified effects cannot establish full funding.'
    if any(row['all_tested_scenarios_pass'] or row['baseline_pass'] for row in plan['candidate_results']):
        return 'An incomplete scenario cannot pass full affordability.'
    if any(row.get('funding_result_complete') for row in plan['scenario_results']):
        return 'Scenario paths must remain explicitly incomplete.'
    return None


def _loan_unknown(plan, facts):
    if _trigger(plan, 'G14') == 'active':
        return 'Historical loan status cannot establish a future payment release.'
    if not facts.get('costly_debt') and _trigger(plan, 'G13') == 'active':
        return 'Payment size or loan status cannot establish a costly-debt APR.'
    return None


def _short_history(plan, facts):
    if plan['normal_monthly_allocation'] or plan['reserve_monthly_earmark']:
        return 'Insufficient/conflicting history cannot establish fixed contribution amounts.'
    if plan['primary_goal'] != 'DATA_LIMITED_REVIEW' or _trigger(plan, 'G24') != 'active':
        return 'Insufficient/conflicting history must return data review (G24).'
    return None


def _deficit_response(plan, facts):
    if plan['selected_scenario_monthly_allocation'] != 0:
        return 'Do not continue an investment contribution through a modeled cash-flow deficit.'
    if facts.get('goal_worsened') and _trigger(plan, 'G25') != 'active':
        return 'A quantified shock that prevents contributions must activate G25.'
    if plan['primary_goal'] not in ('STABILIZE_CASHFLOW', 'NO_FEASIBLE_CONTRIBUTION',
                                     'DATA_LIMITED_REVIEW', 'PROTECT_OPERATING_CASH'):
        return 'A current shock deficit requires a protective/review goal, not a growth or maintain recommendation.'
    return None


def _expense_priority(plan, facts):
    if facts.get('expense_unknown'):
        issue = _incomplete(plan, facts) or _no_investment(plan, facts)
        if issue:
            return issue
    if facts.get('known_expenses') and plan['primary_goal'] in ('INVESTMENT_READINESS_REVIEW',
            'ALLOCATE_SURPLUS', 'MANAGE_DEBT_OBLIGATIONS', 'MAINTAIN_AND_REVIEW'):
        return 'Documented near-term obligations take priority over debt/investment optimization or maintaining without a plan.'
    return None


def _reserve_depletion(plan, facts):
    if _trigger(plan, 'G15') != 'active':
        return 'Documented reserve depletion must activate G15.'
    if plan['primary_goal'] == 'REBUILD_AFTER_SHOCK' and not facts.get('prior_shock'):
        return 'Falling balances alone cannot establish a previous shock.'
    return _no_investment(plan, facts)


def _overlay_goals(plan, facts):
    goals = {plan['primary_goal'], *plan['supporting_goals']}
    if not {'BUILD_EMERGENCY_RESERVE', 'MANAGE_DEBT_OBLIGATIONS'}.issubset(goals):
        return 'Irregular-income plans must retain reserve and loan-payment protection overlays.'
    return _no_investment(plan, facts)


def _remaining_gap(plan, facts):
    if plan['selected_scenario_monthly_allocation']:
        return 'An unresolved funding gap cannot support an optional investment contribution.'
    if plan['features'].get('selected_scenario_additional_cash_needed', 0) <= 0:
        return 'The remaining quantified funding gap must be reported, not treated as resolved.'
    return None


def _flag_required(name):
    def check(plan, facts):
        return None if _has_flag(plan, name) else f'Required bank-review flag missing: {name}.'
    return check


def _accounting_guard(plan, facts):
    issues = _accounting_errors(plan, facts)
    return issues[0] if issues else None


def _suitability_review(plan, facts):
    if plan['security_recommendations'] or plan['automatic_trade_allowed']:
        return 'Supplied cash does not authorize an ETF or trade.'
    if not facts['obligations_reviewed'] and _trigger(plan, 'G17') == 'active':
        return 'Cash alone does not establish excess after total obligations.'
    return None


@dataclass(frozen=True)
class Checkpoint:
    case_id: str
    requirement: str
    applies: Callable
    check: Callable


# These conditions run for every account/scenario, independent of the test CSV.
# Shared checks are intentional: different scenarios must obey the same invariant.
CHECKPOINTS = (
    Checkpoint('S01', 'Reserve before investing', lambda f: _all(f.get('history_valid'), f.get('reserve_shortfall'), f.get('sustained_surplus')), _no_investment),
    Checkpoint('S02', 'Deficit history does not support fixed investments', lambda f: _all(f.get('history_valid'), f.get('negative_history')), _no_investment),
    Checkpoint('S03', 'Unreliable surplus cannot fund a fixed investment transfer', lambda f: _all(f.get('history_valid'), f.get('negative_history')), _no_investment),
    Checkpoint('S04', 'Daily cash risk overrides month-end comfort', lambda f: _all(f.get('history_valid'), f.get('timing_risk')), _no_investment),
    Checkpoint('S05', 'Deterioration blocks new fixed investment commitments', lambda f: _all(f.get('history_valid'), f.get('deteriorating')), _no_investment),
    Checkpoint('S06', 'Dated timing must be evidenced; protect operating cash', lambda f: _all(f.get('history_valid'), f.get('timing_mismatch'), f.get('timing_risk')), _no_investment),
    Checkpoint('S07', 'Low reserves and fixed-cost pressure do not justify investments', lambda f: _all(f.get('history_valid'), f.get('reserve_shortfall'), f.get('fixed_pressure')), _no_investment),
    Checkpoint('S08', 'Loan payments are not APR or relief evidence', lambda f: _all(f.get('history_valid'), f.get('loan_pressure')), _loan_unknown),
    Checkpoint('S09', 'Verified costly debt takes priority over investing', lambda f: _all(f.get('history_valid'), f.get('costly_debt')), _no_investment),
    Checkpoint('S10', 'No loan row does not mean debt-free elsewhere', lambda f: f.get('no_loan_in_source'), _flag_required('NO_LOAN_IN_SOURCE')),
    Checkpoint('S11', 'Historical reserve proxy does not verify excess available cash', lambda f: not f['cash_verified'], _proxy_review),
    Checkpoint('S12', 'Cash alone does not verify suitability or all obligations', lambda f: _all(f.get('history_valid'), f['cash_verified']), _suitability_review),
    Checkpoint('S13', 'No documented objective means no forced action', lambda f: not f['objective_documented'], _no_forced_action),
    Checkpoint('S14', 'Near-term goal funds are not long-term investment capacity', lambda f: f['short_horizon'], _no_investment),
    Checkpoint('S15', 'Unknown expense amount/deadline stays unquantified', lambda f: f.get('expense_unknown'), _incomplete),
    Checkpoint('S16', 'An unusual deposit is not verified unrestricted recurring income', lambda f: _all(f.get('history_valid'), f.get('unusual_inflow')), _flag_required('TRANSFERS_NOT_NEW_WEALTH')),
    Checkpoint('S17', 'A windfall with low reserves is not an investment transfer', lambda f: _all(f.get('history_valid'), f['windfall_verified'], f.get('reserve_shortfall')), _no_investment),
    Checkpoint('S18', 'An inflow rise with deficit months does not justify investing', lambda f: _all(f.get('history_valid'), f.get('rising_with_deficits')), _no_investment),
    Checkpoint('S19', 'Rebuild reserves only with evidence; do not invent event causes', lambda f: _all(f.get('history_valid'), f.get('depleted')), _reserve_depletion),
    Checkpoint('S20', 'A completed goal does not establish the next objective or current cash', lambda f: _all(f['goal_completed'], not f['objective_documented'] or not f['cash_verified']), _no_forced_action),
    Checkpoint('S21', 'Insufficient/conflicting history requires data review', lambda f: not f['history_valid'], _short_history),
    Checkpoint('S22', 'Negative historical cash cannot justify negative or forced investments', lambda f: _all(f.get('history_valid'), f.get('negative_cash')), _no_investment),
    Checkpoint('S23', 'Finished source loan does not prove newly freed payments', lambda f: f.get('finished_loan'), _loan_unknown),
    Checkpoint('S24', 'Unlabeled spending does not establish adjustable purchases', lambda f: f.get('unlabeled_spending'), _flag_required('ADJUSTABLE_SPENDING_UNVERIFIED')),
    Checkpoint('S25', 'Insurance payments do not establish a funded payout', lambda f: f.get('insurance_recorded'), _flag_required('COVERAGE_UNVERIFIED')),
    Checkpoint('S26', 'Unverified ownership/control cannot authorize allocation actions', lambda f: not f['control_verified'], _flag_required('ACCOUNT_CONTROL_UNVERIFIED')),
    Checkpoint('S27', 'Shock-driven deficit pauses optional investment contributions', lambda f: _all(f.get('financial_change'), f.get('shock_deficit')), _deficit_response),
    Checkpoint('S28', 'A no-effect event creates no additional financial effects', lambda f: f['no_effect_event'], _accounting_guard),
    Checkpoint('S29', 'Unspecified event never becomes invented dollar amounts', lambda f: f['unspecified_event'], _incomplete),
    Checkpoint('S30', 'One-off receipts are never recurring income', lambda f: f['windfall_verified'] or f.get('receipt_supplied'), _accounting_guard),
    Checkpoint('S31', 'Unverified current cash permits estimates, not action instructions', lambda f: not f['cash_verified'], _proxy_review),
    Checkpoint('S32', 'Known upcoming obligations dominate investment selection', lambda f: f.get('known_expenses'), _expense_priority),
    Checkpoint('S33', 'Preserve incoming obligations before debt/investment optimization', lambda f: _all(f.get('known_expenses'), f.get('costly_debt'), f.get('reserve_shortfall')), _expense_priority),
    Checkpoint('S34', 'Goal completion does not override a current shock deficit', lambda f: _all(f['goal_completed'], f.get('financial_change'), f.get('shock_deficit')), _deficit_response),
    Checkpoint('S35', 'One exceptional deficit does not establish recurring costs', lambda f: _all(f.get('history_valid'), f.get('exceptional_deficit')), _no_investment),
    Checkpoint('S36', 'Irregular-income plans retain loan and reserve protection', lambda f: _all(f.get('history_valid'), f.get('volatile'), f.get('loan_pressure'), f.get('reserve_shortfall')), _overlay_goals),
    Checkpoint('S37', 'Pausing does not erase an unresolved funding gap', lambda f: _all(f.get('financial_change'), f.get('funding_gap')), _remaining_gap),
    Checkpoint('S38', 'An equity exclusion cannot authorize an investment instruction', lambda f: f['equities_excluded'], _no_forced_action),
    Checkpoint('S39', 'Reserve transfers do not create new wealth', lambda f: f.get('reserve_shortfall'), _accounting_guard),
    Checkpoint('S40', 'Sparse zero-inflow history cannot fund a fixed investment transfer', lambda f: _all(f.get('history_valid'), f.get('sparse')), _no_investment),
)


def _accounting_errors(plan, facts):
    """Enforce S07/S16/S17/S25/S28/S30/S39 for every numeric path.

    A payout, return, salary rise or new wealth cannot appear unless the explicit
    scenario inputs actually contain the corresponding cash effect. Never add
    fixed/loan payments twice, or debit liquid reserve earmarks as investments.
    """
    errors = []
    for result in plan.get('scenario_results', []):
        assumptions = result['assumptions']
        expected_net = (facts['income'] * assumptions['income_multiplier'] - facts['spending']
                        - facts['bills'] * assumptions['bills_increase_pct'])
        expected_receipt = assumptions.get('one_off_receipt', 0.0)
        expenses = facts['quantified_expenses']
        expected_opening = (facts['opening'] + expected_receipt - assumptions['one_off_costs']
                            - sum(e.amount for e in expenses if e.due_month == 0))
        for key in ('no_allocation', 'continue_normal_allocation', 'revised_allocation'):
            path = result[key]
            schedule = path['schedule']
            summary_values = [path[name] for name in ('monthly_contribution', 'monthly_net_before_contribution',
                'initial_cash_after_costs', 'ending_cash', 'minimum_cash', 'additional_cash_needed',
                'required_cash_floor', 'allocated_total')]
            if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) for value in summary_values):
                errors.append('Cash projections must contain finite numeric amounts, not NaN or boolean values.')
                continue
            if len(schedule) != facts['projection_months'] + 1:
                errors.append('Projection must include exactly one opening checkpoint and the configured monthly checkpoints.')
                continue
            if key == 'no_allocation' and path['monthly_contribution'] != 0:
                errors.append('The no-allocation path must not contain investment transfers.')
            if abs(path['monthly_net_before_contribution'] - expected_net) > .011:
                errors.append('Recurring net cash flow differs from explicit scenario inputs (possible double counting or invented income).')
            if abs(path['initial_cash_after_costs'] - expected_opening) > .011:
                errors.append('Opening cash includes an unprovided receipt or omits an immediate expense.')
            receipt_total = sum(row.get('one_off_receipt', 0.0) for row in schedule)
            if abs(receipt_total - expected_receipt) > .011:
                errors.append('One-off receipt must be counted exactly once, never as recurring income.')
            for month, row in enumerate(schedule):
                if any(isinstance(row[name], bool) or not isinstance(row[name], (int, float)) or not isfinite(row[name])
                       for name in ('month', 'opening_cash', 'net_cash_flow', 'contribution', 'extra_expenses', 'closing_cash', 'one_off_receipt')):
                    errors.append('Cash schedule contains a nonfinite or invalid numeric value.')
                    continue
                known_cost = sum(e.amount for e in expenses if e.due_month == month)
                expected_cost = known_cost + (assumptions['one_off_costs'] if month == 0 else 0)
                if row['month'] != month or abs(row['extra_expenses'] - expected_cost) > .011:
                    errors.append('An expense is missing, duplicated, or not supported by supplied inputs.')
                if abs(row['net_cash_flow'] - (expected_net if month else 0)) > .011:
                    errors.append('Monthly schedule includes unprovided recurring income or omits spending.')
                previous = schedule[month - 1]['closing_cash'] if month else facts['opening']
                if abs(row['opening_cash'] - previous) > .011:
                    errors.append('Cash must carry forward between checkpoints without new unprovided funds.')
                expected_close = row['opening_cash'] + row['net_cash_flow'] + row.get('one_off_receipt', 0) - row['contribution'] - row['extra_expenses']
                if abs(row['closing_cash'] - expected_close) > .031:
                    errors.append('Cash accounting does not balance; transfers must not create wealth.')
                expected_transfer = 0 if month == 0 else path['monthly_contribution']
                if row['contribution'] != expected_transfer:
                    errors.append('Every investment contribution must actually leave available cash.')
            if abs(path['ending_cash'] - schedule[-1]['closing_cash']) > .011:
                errors.append('Reported ending cash must match the computed path.')
            if abs(path['allocated_total'] - sum(row['contribution'] for row in schedule)) > .011:
                errors.append('Reported contributions must match actual debits in the path.')
            minimum = min(row['closing_cash'] for row in schedule)
            if abs(path['minimum_cash'] - minimum) > .011:
                errors.append('Minimum cash must include every checkpoint, including Month 0.')
            if abs(path['additional_cash_needed'] - max(0.0, -minimum)) > .011:
                errors.append('A remaining funding gap cannot be erased or replaced by an unprovided funding source.')
            if path['preserves_cash_floor'] and minimum < path['required_cash_floor'] - .011:
                errors.append('A reserve breach cannot be reported as passing the cash floor.')
            if path['nonnegative_cash'] and minimum < -.011:
                errors.append('A negative cash path cannot be reported as nonnegative.')
    return errors


def enforce_goal_validations(plan, facts):
    """Always called by the evaluator; no disable flag and no Python asserts.

    Missing evidence creates nonblocking review flags. If a hard invariant fails,
    discard the unsupported recommendation/projections, retain observed features,
    and return DATA_LIMITED_REVIEW. A future selector cannot bypass this guard by
    merely returning a confident goal, ETF, positive contribution, or funding claim.
    """
    flags = plan['bank_review_flags']
    mandatory_flags = [('INVESTMENT_SUITABILITY_UNVERIFIED', 'No automatic security recommendation or trade is authorized.')]
    if not facts['cash_verified']:
        mandatory_flags.append(('CURRENT_LIQUID_CASH_UNVERIFIED', 'Historical balances remain estimates, not current available cash.'))
    if not facts['control_verified']:
        mandatory_flags.append(('ACCOUNT_CONTROL_UNVERIFIED', 'Account records do not authorize unrestricted use of these funds.'))
    if facts['unspecified_event']:
        mandatory_flags.append(('SHOCK_UNDER_SPECIFIED', 'Unknown effects remain unquantified; supported calculations may continue.'))
    if facts.get('no_loan_in_source'):
        mandatory_flags.append(('NO_LOAN_IN_SOURCE', 'Absence of a source loan is not evidence of being debt-free elsewhere.'))
    for name, reason in mandatory_flags:
        if not _has_flag(plan, name):
            flags.append(name + ': ' + reason)

    errors = []
    if plan.get('security_recommendations') or plan.get('automatic_trade_allowed'):
        errors.append('Security recommendations and automatic trades are forbidden by this evidence-limited tool.')
    if plan.get('investment_suitability') not in ('UNVERIFIED', 'ANALYST_REVIEW_REQUIRED'):
        errors.append('Cash-flow history cannot establish verified investment suitability.')
    if plan.get('conditional_vs_verified') != 'CONDITIONAL':
        errors.append('Historical projections must remain explicitly conditional.')
    amount_fields = ('normal_monthly_allocation', 'selected_scenario_monthly_allocation', 'all_scenarios_monthly_allocation', 'reserve_monthly_earmark')
    for name in amount_fields:
        value = plan.get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value < 0:
            errors.append(f'Invalid allocation amount: {name}.')
        elif facts.get('history_valid') and value > facts['allocation_limits'][name] + 1e-8:
            errors.append(f'Allocation exceeds the independent finance engine capacity: {name}.')
    if not errors:
        if max(plan['selected_scenario_monthly_allocation'], plan['all_scenarios_monthly_allocation']) > plan['normal_monthly_allocation']:
            errors.append('A stress-tested contribution cannot exceed its normal contribution.')
        if facts.get('history_valid'):
            try:
                errors.extend(_accounting_errors(plan, facts))
            except (KeyError, TypeError, ValueError, IndexError, AttributeError):
                errors.append('Malformed numeric projection cannot establish affordability.')
    if not facts['obligations_reviewed'] and _trigger(plan, 'G17') == 'active':
        errors.append('G17 requires supplied cash and reviewed obligations.')
    if plan['primary_goal'] == 'REBUILD_AFTER_SHOCK' and not facts['prior_shock']:
        errors.append('A prior shock must be explicitly supplied, not inferred from falling cash.')
    for code, established in (('G07', facts.get('timing_mismatch')), ('G13', facts['costly_debt']),
                              ('G14', False), ('G23', facts['goal_completed'])):
        if established is not True and _trigger(plan, code) == 'active':
            errors.append(f'{code} cannot be established without the required supplied evidence.')
    for action in plan.get('proposed_actions', []):
        if action.get('type') != 'CONDITIONAL_ALLOCATION_REVIEW' or action.get('status') != 'NOT_EXECUTED':
            errors.append('Only conditional analyst-review actions are allowed.')

    checks = []
    for rule in CHECKPOINTS:
        applies = rule.applies(facts)
        try:
            issue = rule.check(plan, facts) if applies is True else None
        except (KeyError, TypeError, ValueError, IndexError, AttributeError):
            issue = 'Missing/malformed output cannot establish compliance with this checkpoint.'
        if issue:
            errors.append(rule.case_id + ': ' + issue)
        checks.append({'case_id': rule.case_id, 'requirement': rule.requirement,
                       'status': 'blocked' if issue else 'passed' if applies is True else 'unknown' if applies is None else 'not_applicable'})
    audit = {'policy_version': POLICY_VERSION, 'enforced': True,
             'status': 'blocked' if errors else 'passed', 'checks': checks,
             'violations': list(dict.fromkeys(errors))}
    if errors:
        # Do not leave stale positive transfers, charts, or success claims behind
        # after suppressing an unsafe recommendation. Retain raw observations.
        plan = deepcopy(plan)
        for name in amount_fields:
            plan[name] = 0.0
        plan.update(primary_goal='DATA_LIMITED_REVIEW', supporting_goals=[],
                    recommendation='Runtime validation blocked an unsupported result. Retain liquidity and review the reported evidence; no allocation or security is recommended.',
                    security_recommendations=[], automatic_trade_allowed=False,
                    investment_suitability='UNVERIFIED', conditional_vs_verified='CONDITIONAL',
                    proposed_actions=[], candidate_results=[], scenario_results=[], historical_replay=[],
                    funding_result_complete=False, pause_optional_contributions=True,
                    reserve_earmark_months_to_target=None,
                    abstain_reason='Mandatory runtime checkpoint violation; unsupported outputs suppressed.')
        plan['bank_review_flags'].append('RUNTIME_VALIDATION_BLOCKED: ' + '; '.join(audit['violations']))
        for trigger in plan['triggers']:
            trigger['state'] = 'active' if trigger['id'] == 'G24' else 'unknown'
            trigger['reason'] = 'Original result blocked by runtime validation; analyst review required.'
        plan['trigger_ids'] = ['G24']
    plan['runtime_validation'] = audit
    return plan


def enforce_crisis_validations(plan):
    """Mandatory extension for the dated M1-M8 handoff; S01-S40 stay enabled.

    CAD ledgers have already been reconciled with the original ShockScenario by
    enforce_execution. Here enforce lifecycle, G25, proposals and recovery truth.
    No selector confidence, phase label or proposed pause may create funds.
    """
    from crisis_rules import evidenced_goal_worsened, first_shortfall_order
    baseline, shocked = plan['baseline_without_crisis'], plan['no_action']
    expected = evidenced_goal_worsened(baseline, shocked,
        normal_contribution=plan['normal_feasible_contribution'],
        scenario_contribution=plan['goal_contribution_revised'])
    if plan['goal_review_required'] != (not shocked['funding_result_complete']):
        raise ValueError('Incomplete financial effects require an explicit goal review state')
    if plan['G25'] != expected:
        raise ValueError('G25 must describe deterioration, not merely an existing deficit or a changed scenario.')
    if plan['proposal_pause_cash_credit'] != 0:
        raise ValueError('Pausing a proposal cannot add cash to the no-action path.')
    if not shocked['funding_result_complete'] and plan['funding_result_complete']:
        raise ValueError('Partial effects cannot establish full funding.')
    if plan['lead_module'] == 'M6' and plan['recovery']['status'] != 'REBUILDING':
        raise ValueError('M6 requires a supported recovery checkpoint.')
    if plan['goal_status'] == 'NOT_SCHEDULED' and plan['goal_contribution_before'] != 0:
        raise ValueError('A missing contribution must not be confused with a paused transfer.')
    # Always reconcile the selected intervention with supplied individual records.
    from decimal import Decimal
    applied = plan['applied_plan']
    earlier = first_shortfall_order(applied)
    prior = first_shortfall_order(plan['revised_goal'])
    if ((earlier is not None and (prior is None or earlier < prior)) or
        applied['additional_cash_needed'] > plan['revised_goal']['additional_cash_needed'] + .005):
        raise ValueError('Applied action worsens funding or first shortfall')
    ids = plan['applied_transfer_ids']
    from pause_decisions import pause_purpose
    if ids and pause_purpose(plan['revised_goal'], applied, plan['protected_reserve_floor']) is None:
        raise ValueError('Applied pause lacks a supported funding, timing or reserve purpose')
    decisions = plan['pause_decisions']
    if set(ids) != {d['event_id'] for d in decisions if d['status'] == 'included'}:
        raise ValueError('Pause decision audit does not match applied payments')
    if plan['G25_state'] != ('unknown' if expected is None else 'active' if expected else 'inactive'):
        raise ValueError('G25 uncertainty state does not match evidence')
    records = {t['event_id']: t for t in plan['existing_transfers']}
    if (len(decisions) != len(records) or {d['event_id'] for d in decisions} != set(records)
        or any(not d['reason'] for d in decisions)):
        raise ValueError('Every supplied payment needs one explained decision')
    if len(ids) != len(set(ids)) or any(i not in records for i in ids):
        raise ValueError('Applied action IDs are not unique supplied records')
    for i in ids:
        t = records[i]
        if not (t['included_in_baseline'] and t['pause_approved'] and t['pause_fee'] is not None
                and t['pause_fee'] < t['amount'] and t['month'] <= applied['horizon_months']):
            raise ValueError('Applied pause lacks evidence or benefit')
    delta = Decimal(0)
    for before, after in zip(shocked['schedule'], applied['schedule'], strict=True):
        entries = [records[i] for i in ids if records[i]['month'] == after['month']]
        released = sum((Decimal(str(t['amount'])) for t in entries), Decimal(0)).quantize(Decimal('.01'))
        fees = sum((Decimal(str(t['pause_fee'])) for t in entries), Decimal(0)).quantize(Decimal('.01'))
        if abs(float(released)-after['paused_existing_outflow']) > .005 or abs(float(fees)-after['action_fees']) > .005:
            raise ValueError('Applied releases/fees do not match source records')
        delta += released-fees-Decimal(str(after['proposed_contribution']))
        if abs(Decimal(str(after['end_balance']))-Decimal(str(before['end_balance']))-delta) > Decimal('.005'):
            raise ValueError('Revised cash improvement does not reconcile')
    plan['runtime_validation'] = {'enforced': True, 'status': 'passed', 'policy_version': 'crisis-lifecycle-v2',
        'checks': ['original_CAD_ledger', 'all_effects_independent_of_module_labels', 'G25_evidenced_deterioration_or_unknown', 'goal_review_separate_from_G25', 'individual_pause_purpose',
                   'proposal_pause_zero_credit', 'existing_outflow_evidence', 'partial_funding', 'M6_recovery_evidence']}
    return plan
