"""Finance-owned decision output from the validated scenario and its cash paths."""
from functools import lru_cache
import os
from pathlib import Path
import re
import subprocess
import sys

from backup_comparison import build_comparison, pause_exclusion_reason
from crisis_rules import cash_path_metrics, funding_target
from scenario_execution import enforce_execution, execute_scenario, money

POLICY_VERSION = 'finance-decision-v1.1'
SCENARIO_EVIDENCE = {'judge_specified': 'JUDGE_SPECIFIED', 'user_confirmed': 'BANK_CONFIRMED',
                     'assumed': 'ASSUMED_FOR_COMPARISON', 'unknown': 'UNKNOWN_OR_CONFLICTING'}
MODULE_RATIONALE = {
    'M1': 'Review the dated change to recurring inflows.',
    'M2': 'Review recurring spending or the structural cash-flow gap.',
    'M3': 'Address the dated expense or immediate accessible-cash need.',
    'M4': 'Protect evidenced loan payments and review any proposed change to the terms.',
    'M5': 'Several changes need to be assessed together in the same ledger.',
    'M6': 'A separately supplied recovery checkpoint supports reserve review.',
    'M7': 'Check when money becomes accessible relative to the payment.',
    'M8': 'Review the supplied receipt or improved inflows after protecting commitments.',
}


@lru_cache(maxsize=1)
def source_commit():
    supplied = os.environ.get('TANGERINE_SOURCE_COMMIT', '')
    if re.fullmatch(r'[0-9a-f]{40}', supplied):
        return supplied
    commands = [['git', 'rev-parse', 'HEAD']]
    if sys.platform == 'darwin':
        commands.append(['arch', '-x86_64', *commands[0]])
    for command in commands:
        try:
            value = subprocess.check_output(command, cwd=Path(__file__).resolve().parent,
                                            stderr=subprocess.DEVNULL, timeout=2, text=True).strip()
        except (OSError, subprocess.SubprocessError):
            continue
        if re.fullmatch(r'[0-9a-f]{40}', value):
            return value
    return None


def _point(month, phase):
    return {'month': month, 'phase': phase}


def _impact(before, after, *, basis):
    """Signed improvement. Keep partial diagnostics separate from a full impact."""
    left, right = cash_path_metrics(before), cash_path_metrics(after)
    gap_change = None
    cash_change_at_first = None
    if left['complete'] and right['complete']:
        gap_change = round(left['full_funding_need_cad'] - right['full_funding_need_cad'], 2)
        first = left['first_shortfall']
        if first:
            matching = next(point for point in after['checkpoints']
                            if (point['month'], point['phase']) == (first['month'], first['phase']))
            cash_change_at_first = round(matching['cash'] - first['cash'], 2)
    return {'basis': basis, 'before': left, 'after': right,
            'funding_improvement_cad': gap_change, 'cash_change_at_original_shortfall_cad': cash_change_at_first}


def _action(crisis, identity, modules, title, status, clause, reason, *, evidence,
            disposition='review', starts_at=None, ends_at=None, amount_cad=None,
            frequency=None, fee_cad=None, repayment=None, impact=None, event_ids=(),
            required_review=None, cash_treatment='No cash change is credited to the supported path.',
            tradeoffs=(), review_checkpoint=None):
    return {'action_id': identity, 'scenario_hash': crisis['scenario_hash'], 'module_ids': modules,
            'title': title, 'status': status, 'finance_policy_clause': clause, 'reason': reason,
            'disposition': disposition, 'evidence': evidence, 'starts_at': starts_at, 'ends_at': ends_at,
            'amount_cad': amount_cad, 'frequency': frequency, 'fee_cad': fee_cad, 'repayment': repayment,
            'impact': impact, 'affected_event_ids': list(event_ids), 'required_review': required_review,
            'cash_treatment': cash_treatment, 'tradeoffs': list(tradeoffs),
            'review_checkpoint': review_checkpoint, 'not_executed': True}


def _pause_actions(crisis):
    records = {item['event_id']: item for item in crisis['existing_transfers']}
    modules = [module for module in ('M1', 'M2', 'M5', 'M6') if module in crisis['affected_modules']] or ['M2']
    candidates = []
    for decision in crisis['pause_decisions']:
        transfer = records[decision['event_id']]
        selected = decision['status'] == 'included'
        reason = ('This payment passes the modeled funding, timing or reserve check in the selected sequence.'
                  if selected else pause_exclusion_reason(decision, transfer))
        # The schedule is operator-supplied evidence in this exercise. A free
        # text source does not independently verify a real bank authorization.
        evidence = ['JUDGE_SPECIFIED']
        if not (transfer['included_in_baseline'] and transfer['pause_approved'] and transfer['pause_fee'] is not None):
            evidence = ['UNKNOWN_OR_CONFLICTING']
        month = transfer['month']
        item = _action(crisis, 'pause:' + transfer['event_id'], modules, 'Pause an existing scheduled transfer',
            'SUPPORTED_MODELED' if selected else 'BLOCKED_OR_UNKNOWN', '§§2, 3, 5 M5', reason,
            evidence=evidence, disposition='accepted' if selected else 'excluded',
            starts_at=_point(month, 'end'), ends_at=_point(month, 'end'),
            amount_cad=transfer['amount'], frequency='one scheduled payment', fee_cad=transfer['pause_fee'],
            event_ids=[transfer['event_id']], review_checkpoint=_point(month, 'start'),
            required_review='Confirm authorization and effective date before the scheduled payment.' if selected else reason,
            cash_treatment='Retain the included outflow at month end. Any fee posts at month start.' if selected
                else 'No cash change is credited to the supported path.',
            tradeoffs=['Delays the original savings goal.'] if selected else ())
        item['evidence_detail'] = {'source': transfer['source'], 'included_in_baseline': transfer['included_in_baseline'],
                                   'pause_approved': transfer['pause_approved']}
        item['evaluated_paths'] = {key: decision[key] for key in ('standalone', 'cumulative_before', 'cumulative_trial')
                                   if key in decision}
        if 'cumulative_trial' in decision:
            before, trial = decision['cumulative_before'], decision['cumulative_trial']
            item['impact'] = {'basis': 'Cumulative candidate trial in selection order', 'before': before, 'after': trial,
                'funding_improvement_cad': round(before['full_funding_need_cad'] - trial['full_funding_need_cad'], 2)
                    if before['complete'] and trial['complete'] else None}
        candidates.append(item)
    return candidates


def _deferral_actions(crisis, customer, scenario):
    result = []
    base = crisis['no_action']
    for index, effect in enumerate(scenario.effects):
        if effect.debt_change_kind != 'deferral':
            continue
        identity = scenario.effect_identity(index)
        posted = any(identity in row['applied_effect_ids'] for row in base['schedule'])
        impact = None
        limitation = None
        if posted and base['funding_result_complete']:
            remaining = [other for number, other in enumerate(scenario.effects) if number != index]
            reference = type(scenario).model_validate({
                **scenario.model_dump(), 'effects': remaining, 'phase': scenario.phase if remaining else 'normal'})
            opening = None if base['opening_basis'] == 'HISTORICAL_PROXY' else base['opening_cash']
            try:
                path = execute_scenario(customer, reference, opening_cash=opening)
                enforce_execution(path, customer, reference, opening_cash=opening)
            except ValueError as error:
                limitation = 'A separate no-deferral comparison cannot be established. ' + str(error)
            else:
                impact = _impact(path, base, basis='Separate comparison with and without the stipulated deferral')
        term = effect.duration_months
        premium = (float(money(effect.repayment_amount) + term * money(effect.value))
                   if effect.repayment_amount is not None and term and effect.value is not None else None)
        tradeoffs = ['The original loan terms and any outstanding balance still require review.']
        if limitation:
            tradeoffs.append(limitation)
        if impact and impact['funding_improvement_cad'] is not None and impact['funding_improvement_cad'] < 0:
            tradeoffs.insert(0, 'The deferral increases total funding need over the modeled horizon.')
        reason = ('This change is already stipulated in the scenario. Compare the timing benefit and repayment cost separately.'
                  if posted else 'Relief and repayment were withheld. Confirm the included payment, approval, dates and repayment.')
        if effect.start_month > scenario.horizon_months:
            reason = 'The deferral starts beyond this comparison. Review the future payment schedule.'
        result.append(_action(crisis, 'deferral:' + identity, ['M4'], 'Review the loan deferral and catch-up payment',
            'CONDITIONAL_ONLY' if posted else 'BLOCKED_OR_UNKNOWN', '§§3, 5 M4', reason,
            evidence=[SCENARIO_EVIDENCE[effect.evidence] if posted else 'UNKNOWN_OR_CONFLICTING'],
            disposition='conditional' if posted else 'excluded', starts_at=_point(effect.start_month, 'end'),
            ends_at=_point(effect.start_month + term - 1, 'end') if term else None,
            amount_cad=-effect.value if effect.value is not None else None, frequency='per deferred month',
            repayment={'due': _point(effect.repayment_month, 'start') if effect.repayment_month else None,
                       'amount_cad': effect.repayment_amount, 'extra_over_deferred_principal_cad': premium,
                       'beyond_horizon': bool(effect.repayment_month and effect.repayment_month > scenario.horizon_months)},
            impact=impact, event_ids=[identity], review_checkpoint=_point(effect.start_month, 'start'),
            required_review='Confirm authorization, baseline inclusion, full fees and repayment terms with the lender.',
            cash_treatment='The separate comparison adds no cash to the primary action path.',
            tradeoffs=tradeoffs))
    return result


def _assumption_comparison(crisis, customer, scenario):
    effects = [scenario.effect_identity(index) for index, effect in enumerate(scenario.effects)
               if effect.evidence == 'assumed' and effect.value is not None and effect.start_month <= scenario.horizon_months]
    if not effects:
        return None, None
    base = crisis['no_action']
    opening = None if base['opening_basis'] == 'HISTORICAL_PROXY' else base['opening_cash']
    options = {'opening_cash': opening, 'include_assumptions': True}
    try:
        path = execute_scenario(customer, scenario, **options)
        enforce_execution(path, customer, scenario, **options)
    except ValueError as error:
        return _action(crisis, 'scenario-assumptions', [], 'Review the assumed scenario terms', 'BLOCKED_OR_UNKNOWN',
            '§2', str(error), evidence=['ASSUMED_FOR_COMPARISON'], disposition='excluded', event_ids=effects,
            required_review='Correct the terms and supply authorization before counting any benefit.'), None
    return _action(crisis, 'scenario-assumptions', [], 'Review the separate assumed scenario', 'CONDITIONAL_ONLY',
        '§2', 'Assumed effects appear only in this separate known-components comparison.',
        evidence=['ASSUMED_FOR_COMPARISON'], disposition='conditional', event_ids=effects,
        required_review='Verify the assumed amounts, timing and authority before counting any benefit.'), path


def _review_checkpoint(crisis, after, scenario):
    if not after['complete'] and scenario.phase != 'recovery':
        return {'checkpoint': _point(0, 'start'), 'reason': 'Confirm missing material scenario terms before relying on the projection.'}
    upcoming = []
    first = after['first_shortfall']
    if first:
        upcoming.append((first['month'], first['phase'], 'Review available funding and protected payments before the first remaining shortfall.'))
    for effect in scenario.effects:
        if (effect.type == 'income_multiplier' and effect.value is not None and effect.value < 1
                or effect.type == 'income_delta' and effect.value is not None and effect.value < 0):
            if effect.duration_months:
                upcoming.append((effect.start_month + effect.duration_months, 'start', 'Confirm replacement inflow before temporary income ends.'))
        if effect.repayment_month:
            upcoming.append((effect.repayment_month, 'start', 'Review the cash available before the loan catch-up is due.'))
        if effect.type in ('one_off_receipt', 'one_off_cost') and effect.start_month > 0:
            upcoming.append((effect.start_month, 'start', 'Verify the dated receipt or expense before relying on its timing.'))
        if effect.type == 'liquidity_hold' and effect.value:
            upcoming.append((effect.start_month, 'start', 'Confirm the restricted amount and access dates before the cash hold starts.'))
    for record in crisis['existing_transfers']:
        if record['event_id'] in crisis['applied_transfer_ids']:
            upcoming.append((record['month'], 'start', 'Confirm the pause is in effect and check the fee before this payment.'))
    if not upcoming:
        if crisis['recovery'].get('assessment_month'):
            return {'checkpoint': None, 'calendar_month': crisis['recovery']['assessment_month'],
                    'reason': 'Reassess stability and contribution capacity at the supplied recovery checkpoint.'}
        return {'checkpoint': None, 'reason': 'Reassess when new cash, income or obligation evidence is available.'}
    month, phase, reason = min(upcoming, key=lambda item: (item[0], item[1] == 'end'))
    return {'checkpoint': _point(month, phase), 'reason': reason}


def build_finance_plan(crisis, customer, scenario, case):
    comparison = build_comparison(crisis)
    before, applied = crisis['no_action'], crisis['applied_plan']
    matched = _impact(before, applied, basis='Same shock, opening cash and horizon')
    after = matched['after']
    modules = [module for module in [crisis['lead_module'], *crisis['support_modules']] if module]
    candidates = _pause_actions(crisis) + _deferral_actions(crisis, customer, scenario)
    principal = []
    review = _review_checkpoint(crisis, after, scenario)
    first = after['first_shortfall']
    gap = after['full_funding_need_cad']
    stale_normal = scenario.phase == 'normal' and 'stale_history' in case.features.quality_flags
    recurring_gap = next((row for row in applied['schedule'][1:] if after['complete'] and
                          money(row['spending']) > money(row['quantified_income']) + money(row['paused_existing_outflow'])), None)
    target = None
    if gap:
        upfront, recurring = funding_target(applied)
        target = {'upfront_cad': upfront, 'uniform_monthly_improvement_cad': recurring,
                  'monthly_effect_from': _point(1, 'end'), 'remaining_need_cad': gap}
        receipt_after = next((row for row in applied['schedule'] if row['one_off_receipt'] > 0 and
                              (row['month'], 0) > (first['month'], first['phase'] == 'end')), None)
        why = 'Protect the obligations at the earliest remaining shortfall.'
        if receipt_after:
            why += f" The Month {receipt_after['month']} start receipt arrives after that shortage."
        principal.append(_action(crisis, 'remaining-funding-target', modules, 'Cover the remaining funding gap',
            'TARGET_ONLY', '§§3–5', why,
            evidence=['DERIVED'], starts_at=_point(first['month'], first['phase']), amount_cad=gap,
            frequency='additional starting cash across the horizon',
            required_review='Identify a dated source of cash or an authorized adjustable expense, then rerun the full ledger.',
            review_checkpoint=_point(first['month'], first['phase'])))
    elif recurring_gap:
        month = recurring_gap['month']
        deficit = money(recurring_gap['spending']) - money(recurring_gap['quantified_income']) - money(recurring_gap['paused_existing_outflow'])
        principal.append(_action(crisis, 'review-recurring-deficit', ['M2'], 'Address the recurring cash-flow deficit',
            'TARGET_ONLY', '§§4, 5 M2', 'Existing cash covers the modeled checkpoints while spending still exceeds inflows in some periods.',
            evidence=['DERIVED'], starts_at=_point(month, 'end'), amount_cad=float(deficit),
            frequency=f'of recurring deficit in Month {month}',
            required_review='Confirm recurring inflows and which costs can actually change. Review later months in the ledger.'))
    if stale_normal:
        review = {'checkpoint': _point(0, 'start'), 'reason': 'Obtain recent cash and commitment evidence before changing the plan.'}
        principal.insert(0, _action(crisis, 'review-stale-history', [], 'Verify the current account position',
            'BLOCKED_OR_UNKNOWN', '§6', 'The account history is stale for a current savings or spending decision.',
            evidence=['OBSERVED', 'UNKNOWN_OR_CONFLICTING'], required_review=review['reason'], review_checkpoint=review['checkpoint']))
    if not after['complete'] and scenario.phase != 'recovery':
        detail = comparison['evidence_notes'] + list(case.missing_details)
        principal.append(_action(crisis, 'verify-material-inputs', modules, 'Verify the missing financial terms',
            'BLOCKED_OR_UNKNOWN', '§§2–3', 'Full funding need is not established.',
            evidence=['UNKNOWN_OR_CONFLICTING'], required_review=' '.join(dict.fromkeys(detail)) or review['reason'],
            review_checkpoint=_point(0, 'start')))
    assumption, assumption_path = _assumption_comparison(crisis, customer, scenario)
    if assumption:
        principal.append(assumption)
    accepted = [item for item in candidates if item['disposition'] == 'accepted']
    if accepted:
        first_month = min(item['starts_at']['month'] for item in accepted)
        last_month = max(item['ends_at']['month'] for item in accepted)
        impact = _impact(crisis['revised_goal'], applied, basis='Revised goal, before and after the selected pause bundle')
        earliest_change = impact['cash_change_at_original_shortfall_cad']
        reason = ('The modeled pauses improve cash at the original shortfall.' if earliest_change and earliest_change > 0
                  else 'The pauses support later cash or the reserve. They do not cover an earlier shortage.')
        if impact['before']['first_shortfall'] is None:
            reason = 'The modeled pauses help protect the reserve under the supplied terms.'
        pause = _action(crisis, 'selected-pause-bundle', accepted[0]['module_ids'], 'Pause the approved existing transfers',
            'SUPPORTED_MODELED', '§§2–5', reason, evidence=sorted({code for item in accepted for code in item['evidence']}),
            disposition='accepted', starts_at=_point(first_month, 'end'), ends_at=_point(last_month, 'end'),
            amount_cad=comparison['gross_pause'], frequency='total across selected payments',
            fee_cad=comparison['pause_fees'], impact=impact, review_checkpoint=_point(first_month, 'start'),
            event_ids=crisis['applied_transfer_ids'], required_review='Verify each payment, approval and fee before acting.',
            cash_treatment='Only included payments are retained, once each. Fees post at month start.',
            tradeoffs=['The original savings goal is delayed. Any earlier funding requirement remains visible.'])
        principal.insert(0 if earliest_change and earliest_change > 0 else len(principal), pause)
    if crisis['goal_contribution_before'] > crisis['goal_contribution_revised']:
        principal.append(_action(crisis, 'resize-future-goal', modules, 'Hold or resize the future contribution',
            'CONDITIONAL_ONLY', '§§5–6', 'Keep planned contributions within the modeled capacity and review the original goal.',
            evidence=['DERIVED'], amount_cad=crisis['goal_contribution_revised'], frequency='per month if reviewed',
            starts_at=_point(1, 'end'), required_review='Reassess the goal after liquidity and required payments are covered.',
            cash_treatment='A future proposal releases CAD 0.00 into the no-action ledger.'))
    timing = crisis.get('timing_comparison')
    if timing:
        daily_before, daily_after = timing['no_action'], timing['conditional_bill_move']
        prior_day, later_day = daily_before['first_shortfall_date'], daily_after['first_shortfall_date']
        later = prior_day is not None and (later_day is None or later_day > prior_day)
        earlier = later_day is not None and (prior_day is None or later_day < prior_day)
        improvement = timing['funding_gap_improvement']
        useful = not earlier and improvement >= 0 and (later or improvement > 0)
        payment = daily_before['bill_candidate']
        item = _action(crisis, 'historical-bill-shift', ['M7'], 'Review whether the bill date can move',
            'CONDITIONAL_ONLY' if useful else 'BLOCKED_OR_UNKNOWN', '§5 M7',
            'The separate daily replay shows a benefit under its assumptions.' if useful else
            'The replay did not improve timing or funding without a worse outcome elsewhere.',
            evidence=['OBSERVED', 'ASSUMED_FOR_COMPARISON'], disposition='conditional' if useful else 'excluded',
            amount_cad=payment['median_payment'], frequency='median recorded payment',
            required_review='Confirm the specific bill, effective date, approval and fee. Keep the daily cash basis separate.')
        item['daily_comparison'] = {'basis': timing['basis'], 'funding_improvement_cad': improvement,
            'before_first_day': prior_day, 'after_first_day': later_day,
            'before_funding_need_cad': daily_before['extra_cash_needed'], 'after_funding_need_cad': daily_after['extra_cash_needed'],
            'first_original_date': payment['first_original_date'], 'first_shifted_date': payment['first_shifted_date']}
        candidates.append(item)
        if useful:
            principal.append(item)
    recovery = crisis['recovery']
    if scenario.phase == 'recovery' or recovery.get('assessment_month'):
        known = recovery['status'] in ('REBUILDING', 'RESERVE_RESTORED')
        principal.append(_action(crisis, 'review-recovery-checkpoint', ['M6'], 'Review the separate reserve checkpoint',
            'CONDITIONAL_ONLY' if known else 'BLOCKED_OR_UNKNOWN', '§5 M6',
            recovery.get('reason') or 'A dated, stable recovery checkpoint is needed.',
            evidence=[{'judge_specified': 'JUDGE_SPECIFIED', 'observed': 'OBSERVED',
                       'simulated': 'ASSUMED_FOR_COMPARISON'}.get(recovery.get('cash_basis'), 'UNKNOWN_OR_CONFLICTING')],
            amount_cad=recovery['monthly_contribution'] or None, frequency='per month at the supplied checkpoint',
            required_review='Confirm cash, covered obligations, stability and a sustainable contribution before committing.'))
    principal.extend(item for item in candidates if item['action_id'].startswith('deferral:'))
    if 'M8' in crisis['affected_modules'] and gap == 0 and after['complete']:
        principal.append(_action(crisis, 'review-accessible-surplus', ['M8'], 'Review accessible surplus against the customer’s goal',
            'CONDITIONAL_ONLY', '§5 M8', 'Consider available funds after required payments and reserves are protected.',
            evidence=['DERIVED'], required_review='Confirm accessibility, near-term commitments and the customer’s goal.'))
    if not principal:
        principal.append(_action(crisis, 'maintain-and-monitor', modules, 'Maintain the current viable plan',
            'MAINTAIN', '§§4, 6', 'No new action is justified on the modeled evidence.',
            evidence=['DERIVED'], required_review=review['reason']))
    candidates.extend(item for item in principal if item not in candidates)
    approval_flags = []
    if accepted or any(item['action_id'].startswith('deferral:') and item['status'] == 'CONDITIONAL_ONLY'
                       for item in candidates):
        approval_flags.append('SUPPLIED_ACTION_TERMS: Approvals are supplied scenario evidence. Independently verify authorization, effective dates and fees before acting; hypothetical approvals do not establish bank execution.')
    profile = customer.get('history')
    history = (str(profile['month'].min()), str(profile['month'].max())) if profile is not None and not profile.empty else None
    return {
        'policy_version': POLICY_VERSION, 'finance_approval': 'PENDING', 'source_commit': source_commit(),
        'account_id': customer['account_id'], 'scenario_hash': crisis['scenario_hash'],
        'horizon_months': scenario.horizon_months, 'opening_cash_basis': before['opening_basis'],
        'financial_diagnosis': {'scenario': crisis['scenario'], 'opening_cash_cad': before['opening_cash'],
            'baseline': {key: customer.get('raw_' + key, customer.get(key)) for key in ('I', 'S', 'F', 'H', 'B', 'P')},
            'observed_window': history, 'first_month_inflow_cad': before['schedule'][1]['income'],
            'first_month_spending_cad': before['schedule'][1]['spending'],
            'first_month_recurring_gap_cad': round(before['schedule'][1]['spending'] - before['schedule'][1]['income'], 2)
                if before['schedule'][1]['period_complete'] and before['schedule'][1]['income'] is not None else None,
            'evidence': ['OBSERVED', 'DERIVED'],
            'effect_evidence': [{'effect_id': scenario.effect_identity(index),
                'provenance': SCENARIO_EVIDENCE[effect.evidence]} for index, effect in enumerate(scenario.effects)],
            'one_offs_and_repayments': [{key: row[key] for key in ('month', 'one_off_receipt', 'one_off_cost', 'deferred_repayment')}
                for row in before['schedule'] if row['one_off_receipt'] or row['one_off_cost']],
            **matched['before']},
        'lead_module': crisis['lead_module'], 'support_modules': crisis['support_modules'],
        'module_rationale': {module: MODULE_RATIONALE[module] for module in modules},
        'status': ('REVIEW_REQUIRED' if not after['complete'] or stale_normal else 'SUPPORTED_MODELED' if accepted
                   else 'NO_SUPPORTABLE_ACTION' if gap or recurring_gap else 'MAINTAIN' if principal[0]['status'] == 'MAINTAIN'
                   else 'CONDITIONAL_REVIEW'),
        'prioritized_actions': principal[:3], 'candidate_action_decisions': candidates,
        'comparison': matched, 'no_action': before, 'supported_action': applied,
        'all_eligible_pauses_comparison': (_impact(before, crisis['supported_pause'],
            basis='Separate comparison of all eligible pause terms before selecting the supported bundle')
            if crisis['existing_transfer_pause_credit'] else None),
        'conditional_assumption_path': assumption_path,
        'remaining_gap_cad': gap, 'required_target_only': target,
        'bank_review_flags': list(dict.fromkeys([*crisis['review_flags'], *comparison['evidence_notes'], *approval_flags])),
        'next_review_checkpoint': review, 'post_horizon_obligations': [
            item for item in applied['pending_effects'] if item['type'] in ('one_off_cost', 'deferred_repayment')
            and item['start_month'] is not None and item['start_month'] > scenario.horizon_months],
        'normal_goal_impact': {'status': crisis['goal_status'], 'before': crisis['goal_before_crisis'],
            'revised_monthly_cad': crisis['goal_contribution_revised'], 'proposal_pause_cash_credit_cad': 0.0},
        'recovery_checkpoint': recovery,
        'model_limitations': ['Monthly checkpoints do not establish day-to-day solvency.',
            'Recorded account inflows do not establish wages or household finances.',
            'Supplied approvals are scenario evidence. Every intervention is modeled and unexecuted.',
            'Pause selection evaluates standalone and cumulative trials in fee, month and ID order.'],
    }
