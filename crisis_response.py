"""One scenario -> classifier proposal -> deterministic, guarded crisis decision.

M1-M8 are response labels. All effects execute regardless of the two-label support
limit. Proposals never add cash. Existing transfers require explicit included
schedule, approval and fee evidence before a pause changes the no-action path.
"""
from collections import defaultdict
from copy import deepcopy
from math import isfinite
from decimal import Decimal

from pydantic import Field, model_validator, field_validator
from plan_classification import build_case, profile_from_engine, select_plan
from plan_classification.backends import validate_selection
from plan_classification.case import case_hash
from plan_classification.schemas import Contract, PlanSelection, SelectionResult, ShockScenario
from crisis_rules import evidenced_goal_worsened, funding_target
from recovery_plan import make_recovery_plan
from scenario_execution import execute_scenario, enforce_execution, money, period_values, scenario_hash


class NormalGoal(Contract):
    name: str = Field(min_length=1)
    monthly_contribution: float = Field(ge=0)
    reserve_target: float = Field(ge=0)
    reserve_months: float = Field(default=3., gt=0, le=24)
    contribution_type: str = Field(default='PROPOSAL', pattern='^PROPOSAL$')
    kind: str = Field(default='PROPOSED_TRANSFER', pattern='^(PROPOSED_TRANSFER|LIQUID_RESERVE_EARMARK)$')
    source: str = Field(default='Guarded normal-goal assessment', min_length=1)


class ExistingGoalTransfer(Contract):
    event_id: str = Field(min_length=1)
    account_id: int | None = Field(default=None, ge=1)
    month: int = Field(ge=1, le=120)
    amount: float = Field(gt=0)
    source: str = Field(min_length=1)
    included_in_baseline: bool = Field(strict=True)
    pause_approved: bool = Field(default=False, strict=True)
    pause_fee: float | None = Field(default=None, ge=0)

    @field_validator('amount', 'pause_fee')
    @classmethod
    def posted_cents(cls, value):
        if value is not None and (abs(value) > 1e12 or Decimal(str(value)) != Decimal(str(value)).quantize(Decimal('.01'))):
            raise ValueError('Transfer amounts and fees must be posted CAD cents within the supported range')
        return value


_SUPPORTED_MODULE = {
    'income_multiplier': 'M1', 'income_delta': 'M1', 'expense_delta': 'M2', 'expense_percent': 'M2',
    'household_bills_percent': 'M2', 'household_bills_delta': 'M2', 'one_off_cost': 'M3',
    'debt_payment_delta': 'M4', 'liquidity_hold': 'M7', 'payment_delay_days': 'M7',
    'one_off_receipt': 'M8', 'investment_return': 'M8',
}


def _monthly_capacity(customer, scenario, path, target, limit):
    # A deferred/known future bill is still owed. Protect its supplied amount;
    # an unreceived future receipt never becomes today's investable funds.
    target += sum(e.value for e in scenario.effects if e.type == 'one_off_cost'
                  and e.value is not None and e.evidence != 'unknown' and e.start_month > scenario.horizon_months)
    if not path['funding_result_complete'] or path['opening_cash'] < target:
        return 0.
    bounds = [limit]
    for row in path['schedule'][1:]:
        # A fixed proposal cannot draw down reserves or exceed recurring surplus.
        bounds.extend([row['quantified_income'] - row['spending'],
                       (row['end_balance'] - target) / row['month']])
    for check in path['checkpoints']:
        # Earlier transfers affect month-start cash before receipts can rescue it.
        if check['phase'] == 'start' and check['month'] > 1:
            bounds.append((check['cash'] - target) / (check['month'] - 1))
    return max(0., int(max(0., min(bounds)) * 100 + 1e-8) / 100)


def make_crisis_plan(customer, scenario, *, normal_goal, selection_result=None,
                     opening_cash=None, existing_transfers=(), recovery_snapshot=None,
                     data_dir=None, include_timing_comparison=False, baseline_effects=(), module_proposal=None):
    scenario = ShockScenario.model_validate(scenario)
    normal = NormalGoal.model_validate(normal_goal)
    transfers = [ExistingGoalTransfer.model_validate(t) for t in existing_transfers]
    if any(t.account_id not in (None, customer['account_id']) for t in transfers):
        raise ValueError('Scheduled transfer belongs to a different account')
    if len({t.event_id for t in transfers}) != len(transfers):
        raise ValueError('Duplicate scheduled transfer event_id; no double pause credit is allowed')
    baseline_scenario = ShockScenario(phase='active' if baseline_effects else 'normal',
        effects=list(baseline_effects), horizon_months=scenario.horizon_months)
    kwargs = {'opening_cash': opening_cash}
    no_action = execute_scenario(customer, scenario, **kwargs)
    baseline = execute_scenario(customer, baseline_scenario, **kwargs)
    flags = list(no_action['review_flags'])
    flags.append('CONDITIONAL_PROJECTION: Historical full-history medians and the supplied effects are not verified future cash flows; month-start/end checkpoints do not establish daily solvency.')
    if opening_cash is None:
        flags.append('CURRENT_LIQUID_CASH_UNVERIFIED: Opening cash uses the competition historical buffer proxy, not a live accessible balance.')
    else:
        flags.append('SUPPLIED_SCENARIO_CASH: Opening cash is explicitly supplied for this scenario, not verified live banking data.')
    source_cap = normal.monthly_contribution
    floor = normal.reserve_target if normal.kind == 'PROPOSED_TRANSFER' else min(normal.reserve_target, float(customer['S']))
    base_capacity = _monthly_capacity(customer, baseline_scenario, baseline, floor, source_cap)
    capacity = _monthly_capacity(customer, scenario, no_action, floor, source_cap)
    # A proposed liquid-reserve earmark is not a second outflow. Its amount is
    # still paused as a goal decision if a crisis prevents further earmarking.
    worsened = evidenced_goal_worsened(baseline, no_action,
        normal_contribution=base_capacity, scenario_contribution=capacity)
    if source_cap == 0:
        goal_status = 'NOT_SCHEDULED'
    elif not no_action['funding_result_complete']:
        goal_status = 'REVIEW_REQUIRED'
    elif not worsened and base_capacity < source_cap:
        goal_status = 'BASELINE_REVIEW_REQUIRED'
    elif capacity >= source_cap:
        goal_status = 'MAINTAINED'
    elif capacity > 0:
        goal_status = 'REDUCED'
    else:
        goal_status = 'PAUSED'
    debit = source_cap if normal.kind == 'PROPOSED_TRANSFER' else 0.
    revised_debit = capacity if normal.kind == 'PROPOSED_TRANSFER' else 0.
    continued = execute_scenario(customer, scenario, contribution=debit, **kwargs)
    revised = execute_scenario(customer, scenario, contribution=revised_debit, **kwargs)
    releases, fees = defaultdict(float), defaultdict(float)
    for t in transfers:
        if t.month > scenario.horizon_months:
            flags.append(f'BEYOND_HORIZON: Transfer {t.event_id} remains outside this horizon.')
        elif t.included_in_baseline and t.pause_approved and t.pause_fee is not None and t.pause_fee < t.amount:
            releases[t.month] += t.amount
            fees[t.month] += t.pause_fee
        else:
            flags.append(f'TRANSFER_PAUSE_UNVERIFIED: {t.event_id} lacks complete pause evidence or its fee consumes the benefit; no cash is credited.')
    comparison = execute_scenario(customer, scenario, spending_releases=dict(releases), release_fees=dict(fees), **kwargs)
    from pause_decisions import select_pauses
    applied, applied_releases, applied_fees, eligible_ids, pause_decisions = select_pauses(
        customer, scenario, transfers, revised, floor=floor,
        contribution=revised_debit, opening_cash=opening_cash)
    for decision in pause_decisions:
        if decision['status'] == 'excluded':
            flags.append('PAUSE_NOT_APPLIED: ' + decision['event_id'] + ': ' + decision['reason'])
    if source_cap == 0 and eligible_ids:
        goal_status = 'EXISTING_TRANSFERS_PAUSED'
    upfront, monthly_target = funding_target(no_action)
    # Shared source for model selection, independently checked even if selection
    # was supplied by UI. Never trust a stale account/scenario fingerprint.
    case = build_case(profile_from_engine(customer), scenario, planning_cash=opening_cash)
    if case.features.quality_flags:
        flags.append('HISTORICAL_PROFILE_REVIEW: ' + ', '.join(case.features.quality_flags))
    if customer.get('raw_P', customer.get('P', 0)):
        flags.append('LOAN_TERMS_UNVERIFIED: Recorded payment pressure does not establish current APR, deferral approval or payment release.')
    proposal_status = 'local_baseline'
    if selection_result is not None:
        try:
            candidate = SelectionResult.model_validate(selection_result)
            if candidate.input_hash != case_hash(case):
                raise ValueError('Stale classifier result')
            validate_selection(candidate.selection, case)
            selected = candidate
            proposal_status = 'accepted_proposal'
        except (ValueError, TypeError):
            selected = select_plan(case, backend='rules')
            proposal_status = 'rejected_stale_or_invalid_proposal'
            flags.append('CLASSIFICATION_REJECTED: Proposal does not match this case; local rules used.')
    else:
        selected = select_plan(case, backend='rules')
    selected_plan = selected.selection
    metadata = selected.model_dump(mode='json')
    if module_proposal is not None:
        if selection_result is not None:
            raise ValueError('Provide a PlanSelection or SelectionResult, not both')
        try:
            selected_plan = validate_selection(PlanSelection.model_validate(module_proposal), case)
            metadata = None  # Do not invent a provider/version for a bare proposal.
            proposal_status = 'external_proposal_structurally_validated'
        except (ValueError, TypeError):
            proposal_status = 'rejected_invalid_external_proposal'
            flags.append('CLASSIFICATION_REJECTED: Invalid external PlanSelection; local baseline retained.')
    in_scope_effects = [effect for effect in scenario.effects
                        if effect.value is not None and effect.evidence in ('judge_specified', 'user_confirmed')
                        and effect.start_month <= scenario.horizon_months]
    modules = list(dict.fromkeys(_SUPPORTED_MODULE[e.type] for e in in_scope_effects
                                if e.type in _SUPPORTED_MODULE
                                and e.value != (1 if e.type == 'income_multiplier' else 0)))
    adverse = set()
    for e in in_scope_effects:
        if (e.type == 'income_multiplier' and e.value < 1) or (e.type == 'income_delta' and e.value < 0):
            adverse.add('income')
        elif e.type in ('expense_delta','expense_percent','household_bills_delta','household_bills_percent','debt_payment_delta','one_off_cost','liquidity_hold') and e.value > 0:
            adverse.add(_SUPPORTED_MODULE[e.type])
    if len(adverse) > 1:
        modules.append('M5')
    recurring_deficit = any(row['quantified_income'] < row['spending'] for row in no_action['schedule'][1:])
    if recurring_deficit:
        modules.append('M2')
    if 'essential_obligations_at_risk' in case.observed_reasons or (recurring_deficit and customer.get('raw_P', customer.get('P', 0))):
        modules.append('M4')
    if no_action['first_shortfall_month'] == 0:
        modules.append('M3')
    if any(e.type in ('income_delta', 'expense_delta', 'expense_percent', 'household_bills_percent', 'household_bills_delta')
           and (e.value > 0 if e.type == 'income_delta' else e.value < 0)
           for e in in_scope_effects):
        modules.append('M8')
    recovery = make_recovery_plan(recovery_snapshot, reserve_months=normal.reserve_months)
    if recovery_snapshot is not None:
        from recovery_plan import RecoverySnapshot
        bound_account = RecoverySnapshot.model_validate(recovery_snapshot).account_id
        if bound_account is not None and bound_account != customer['account_id']:
            raise ValueError('Recovery checkpoint belongs to a different account')
    if recovery['lead_module'] == 'M6':
        modules.append('M6')
    lead = selected_plan.lead_module
    if lead == 'M6' and recovery['status'] != 'REBUILDING':
        # Reserve-below-target screening is not evidence of post-crisis recovery.
        flags.append('MODULE_REVIEW_REQUIRED: M6 proposal does not establish recovery; updated checkpoint required.')
        lead = next((m for m in modules if m != 'M6'), None)
    if lead not in modules:
        lead = next(iter(modules), None)
    if lead == 'M8' and no_action['additional_cash_needed'] > 0:
        lead = 'M3' if no_action['first_shortfall_month'] == 0 else 'M2'
    if lead != selected_plan.lead_module:
        proposal_status = 'financial_eligibility_override'
        flags.append('MODULE_ELIGIBILITY_OVERRIDE: Classification proposal is retained for audit; the finance engine selected a supported protective/review response.')
    for question in selected_plan.needs_clarification:
        flags.append('BANK_REVIEW_REQUIRED: ' + question)
    if scenario.phase == 'recovery' and recovery_snapshot is None:
        flags.extend(recovery['review_flags'])
    if recovery_snapshot is not None:
        flags.append('RECOVERY_CHECKPOINT_SEPARATE: Updated recovery cash is separately supplied; it is not assumed to follow from an unfunded crisis balance.')
    timing = None
    if include_timing_comparison:
        # Reuse only for compatible historical replay. Never silently flatten a
        # delayed/custom scenario into the old slider triple.
        from daily_simulation import simulate_daily_cashflow
        from pathlib import Path
        compatible = (scenario.horizon_months == 6 and all(
            e.type in ('income_multiplier', 'household_bills_percent', 'one_off_cost')
            and e.start_month == (0 if e.type == 'one_off_cost' else 1)
            and e.value is not None and e.evidence in ('judge_specified', 'user_confirmed')
            and (e.type == 'one_off_cost' or e.duration_months == 6 or e.ongoing)
            for e in scenario.effects))
        if compatible:
            params = dict(income_multiplier=1., bills_increase_pct=0., one_off_costs=0., shift_bill_days=7)
            for e in scenario.effects:
                if e.type == 'income_multiplier': params['income_multiplier'] = e.value
                elif e.type == 'household_bills_percent': params['bills_increase_pct'] = e.value / 100
                else: params['one_off_costs'] += e.value
            if data_dir:
                params['data_dir'] = Path(data_dir)
            if opening_cash is not None:
                params['initial_balance'] = opening_cash
            before = simulate_daily_cashflow(customer['account_id'], **params)
            if before['available'] and before['has_bill_to_shift']:
                after = simulate_daily_cashflow(customer['account_id'], bill_shift_approved=True, **params)
                timing = {'status': 'CONDITIONAL', 'resolution': 'END_OF_DAY_HISTORICAL_REPLAY',
                          'basis': before['opening_balance_basis'], 'no_action': before, 'conditional_bill_move': after,
                          'funding_gap_improvement': round(before['extra_cash_needed'] - after['extra_cash_needed'], 2),
                          'conditions': ['Biller approval, actual effective dates and zero fee are unverified.',
                                         'Recorded daily flows differ from monthly medians; compare only these paired daily paths and their declared opening basis.']}
                modules.append('M7')
        else:
            flags.append('DAILY_REPLAY_NOT_APPLIED: This dated/custom scenario is not supported by the existing daily bill-shift replay; monthly results do not establish daily solvency.')
    result = {
        'scenario': scenario.model_dump(mode='json'), 'scenario_hash': scenario_hash(scenario),
        'classification_input_hash': case_hash(case), 'classification': metadata,
        'module_proposal': selected_plan.model_dump(mode='json'),
        'selection_status': proposal_status, 'lead_module': lead,
        'support_modules': [m for m in selected_plan.support_modules if m in modules and m != lead][:2],
        'affected_modules': list(dict.fromkeys(modules)),
        'goal_before_crisis': normal.model_dump(), 'goal_status': goal_status,
        'existing_transfers': [t.model_dump() for t in transfers],
        'goal_contribution_before': source_cap, 'goal_contribution_revised': capacity,
        'normal_feasible_contribution': base_capacity,
        'proposal_pause_cash_credit': 0., 'existing_transfer_pause_credit': round(sum(releases.values()), 2),
        'immediate_cash_target': round(upfront, 2),
        'required_monthly_improvement': monthly_target if no_action['funding_result_complete'] else None,
        'quantified_component_monthly_target': monthly_target,
        'improvement_status': 'CALCULATED_TARGET_NOT_VERIFIED_ADJUSTABLE_SPENDING',
        'G25': worsened, 'G25_state': 'unknown' if worsened is None else 'active' if worsened else 'inactive',
        'goal_review_required': not no_action['funding_result_complete'],
        'trigger_ids': ['G25'] if worsened else [],
        'no_action': no_action, 'baseline_without_crisis': baseline,
        'continue_goal': continued, 'revised_goal': revised, 'supported_pause': comparison,
        'applied_plan': applied,
        'applied_transfer_ids': eligible_ids,
        'pause_decisions': pause_decisions, 'protected_reserve_floor': floor,
        'applied_pause_fees': round(sum(applied_fees.values()), 2),
        'pause_fees': round(sum(fees.values()), 2),
        'pause_funding_gap_improvement': round(no_action['additional_cash_needed'] - comparison['additional_cash_needed'], 2),
        'timing_comparison': timing, 'recovery': recovery,
        'funding_result_complete': no_action['funding_result_complete'],
        'review_flags': list(dict.fromkeys(flags)),
        'next_review_conditions': ['Updated income after temporary benefits end', 'Confirmed payment terms or transfer-pause authority', 'Updated cash and obligations for reserve restoration'],
    }
    # Mandatory runtime boundary: changes to models/selectors cannot change CAD.
    try:
        for path, extra in ((no_action, {}), (baseline, {}),
                            (continued, {'contribution': debit}), (revised, {'contribution': revised_debit}),
                            (comparison, {'spending_releases': dict(releases), 'release_fees': dict(fees)}),
                            (applied, {'contribution': revised_debit, 'spending_releases': applied_releases, 'release_fees': applied_fees})):
            applied_scenario = baseline_scenario if path is baseline else scenario
            enforce_execution(path, customer, applied_scenario, **kwargs, **extra)
        from goal_validation import enforce_crisis_validations
        if recovery != make_recovery_plan(recovery_snapshot, reserve_months=normal.reserve_months):
            raise ValueError('Recovery output no longer matches the supplied checkpoint')
        validated = enforce_crisis_validations(result)
        from tailored_advice import build_advice
        validated['advice'] = build_advice(validated)
        from finance_actions import build_finance_plan
        validated['finance_plan'] = build_finance_plan(validated, customer, scenario, case)
        return validated
    except ValueError as error:
        result.update(goal_status='REVIEW_REQUIRED', lead_module=None, support_modules=[],
                      funding_result_complete=False, runtime_validation={'enforced': True, 'status': 'blocked'},
                      review_flags=[*flags, 'RUNTIME_VALIDATION_BLOCKED: ' + str(error)])
        # Do not present a failed ledger as a usable funding solution.
        for key in ('no_action', 'baseline_without_crisis', 'continue_goal', 'revised_goal', 'supported_pause', 'applied_plan'):
            result[key] = None
        return result
