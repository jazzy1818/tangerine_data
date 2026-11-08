"""Finance-owned action plan (Tangerine Financial Decision Policy v1.1, §§2–7).

Turns an already validated crisis plan into an ordered, evidence-labelled set of
actions. This module never changes the supported cash ledger: it reads the
engine's no-action and applied paths, and any extra comparison is a separate
replay through the same `execute_scenario` arithmetic, labelled CONDITIONAL_ONLY.

Status meanings (policy §2):
  SUPPORTED_MODELED  supplied evidence supports including the cash effect (not executed)
  CONDITIONAL_ONLY   separate what-if comparison; never in the supported ledger
  TARGET_ONLY        required amount; no cash credited until a source is verified
  BLOCKED_OR_UNKNOWN cannot quantify/execute from the evidence available
  MAINTAIN           no change justified; keep the current plan and review
"""
from decimal import Decimal, ROUND_CEILING
from functools import lru_cache
import subprocess

from plan_classification.schemas import ShockScenario
from scenario_execution import execute_scenario, scenario_hash

POLICY_VERSION = 'finance-decision-policy-v1.1'
MODULE_NAMES = {'M1': 'Income Continuity', 'M2': 'Cost Rebalancing', 'M3': 'Emergency Liquidity',
                'M4': 'Debt & Obligation Defense', 'M5': 'Multi-Shock Stabilization',
                'M6': 'Reserve Restoration', 'M7': 'Cash-Flow Timing & Access',
                'M8': 'Surplus & Windfall Allocation'}
MAX_PRIMARY = 3


@lru_cache(maxsize=1)
def source_commit():
    try:
        return subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], capture_output=True, text=True,
                              timeout=2, check=True).stdout.strip() or 'unknown'
    except (OSError, subprocess.SubprocessError):
        return 'unknown'


def _cad(value):
    return 'not established' if value is None else f'CAD {value:,.2f}'


def _when(month, phase):
    if month is None:
        return None
    if month == 0:
        return 'Month 0 (immediately)'
    return f'Month {month} {"start" if phase == "start" else "end"}'


def _first(path):
    if path is None or path['first_shortfall_month'] is None:
        return None
    month, phase = path['first_shortfall_month'], path['first_shortfall_phase']
    cash = next(c['cash'] for c in path['checkpoints'] if c['month'] == month and c['phase'] == phase)
    return {'month': month, 'phase': phase, 'label': _when(month, phase), 'cash': cash, 'need': round(-cash, 2)}


def _lowest(path):
    point = min(path['checkpoints'], key=lambda c: (c['cash'], c['month'], c['phase'] != 'start'))
    return {'month': point['month'], 'phase': point['phase'], 'label': _when(point['month'], point['phase']),
            'cash': point['cash']}


def _path_summary(path):
    if path is None:
        return None
    return {'opening_cash': path['opening_cash'], 'opening_basis': path['opening_basis'],
            'first_shortfall': _first(path), 'lowest_cash': _lowest(path),
            'known_components_need': path['additional_cash_needed'],
            'full_funding_need': path['full_funding_need'], 'complete': path['funding_result_complete'],
            'ending_cash': path['ending_cash'],
            'fees': round(sum(r['action_fees'] for r in path['schedule']), 2),
            'repayments': round(sum(r['deferred_repayment'] for r in path['schedule']), 2),
            'checkpoints': path['checkpoints']}


def _included_loan_payment(customer):
    """The same observed payment basis the ledger uses for a loan reduction."""
    history = customer.get('history')
    if history is not None and 'loan_payments' in history:
        value = float(history['loan_payments'].median())
    else:
        value = customer.get('included_loan_payment')
    return round(value, 2) if value else None


def _action(action_id, modules, title, *, status, priority, instruction, rationale, evidence,
            amount=None, frequency=None, starts=None, ends=None, cash_treatment, first_effect=None,
            horizon_effect=None, outstanding=None, downsides=(), review=None, decision='candidate', reason=''):
    return {'action_id': action_id, 'module_ids': list(modules),
            'module_names': [MODULE_NAMES[m] for m in modules], 'title': title, 'status': status,
            'priority': priority, 'instruction': instruction, 'rationale': rationale,
            'evidence': list(evidence), 'amount_cad': amount, 'frequency': frequency,
            'starts_at': starts, 'ends_at': ends, 'cash_treatment': cash_treatment,
            'effect_on_first_shortfall': first_effect, 'effect_on_horizon_need_cad': horizon_effect,
            'outstanding_need_after_cad': outstanding, 'downsides': list(downsides),
            'required_review': review, 'decision': decision, 'reason': reason, 'not_executed': True}


def _targets(path):
    """Same formula as crisis_response: upfront cash, then a level monthly improvement
    that keeps every later checkpoint non-negative (policy §3, TARGET_ONLY)."""
    upfront = max([0.] + [-c['cash'] for c in path['checkpoints']
                          if c['month'] == 0 or (c['month'] == 1 and c['phase'] == 'start')])
    monthly = Decimal(0)
    for c in path['checkpoints']:
        periods = c['month'] - (1 if c['phase'] == 'start' else 0)
        if periods > 0:
            monthly = max(monthly, max(Decimal(0), -Decimal(str(c['cash'])) - Decimal(str(upfront))) / periods)
    return round(upfront, 2), float(monthly.quantize(Decimal('.01'), rounding=ROUND_CEILING))


def _income_end(scenario):
    ends = [e.start_month + e.duration_months for e in scenario.effects
            if e.type in ('income_multiplier', 'income_delta') and e.value is not None
            and (e.value < 1 if e.type == 'income_multiplier' else e.value < 0) and e.duration_months]
    return min(ends) if ends else None


def _loan_bridge(customer, scenario, opening_cash, base, payment):
    """Conditional emergency bridge: a hypothetical deferral replayed once, from the
    original scenario, with its catch-up inside the horizon (policy §8 example C)."""
    first = _first(base)
    horizon = scenario.horizon_months
    if first is None or first['month'] == 0 or horizon < 2:
        return None, 'No month-end loan payment falls before the earliest shortfall, so relief cannot be timely.'
    # Defer up to three payments; the catch-up falls in the last plan month so the
    # bridge can move the earliest shortfall. Total owed is unchanged (fee unknown → 0).
    months = max(1, min(3, horizon - 1))
    repay_month = horizon
    deferral = {'effect_id': 'conditional-loan-bridge', 'type': 'debt_payment_delta', 'value': -payment,
                'start_month': 1, 'duration_months': months, 'evidence': 'assumed',
                'debt_change_kind': 'deferral', 'repayment_month': repay_month,
                'repayment_amount': round(payment * months, 2)}
    original = scenario.model_dump(mode='json')
    # A replayed deferral is a change, so a no-shock baseline becomes 'active' for this comparison only.
    trial = ShockScenario.model_validate({**original, 'phase': 'active' if original['phase'] == 'normal' else original['phase'],
                                          'effects': [*original['effects'], deferral]})
    path = execute_scenario(customer, trial, opening_cash=opening_cash)
    return {'path': path, 'months': months, 'repay_month': repay_month,
            'repayment': round(payment * months, 2)}, None


def build_action_plan(customer, crisis, *, scenario, goal_plan=None, opening_cash=None):
    scenario = ShockScenario.model_validate(scenario)
    base, applied = crisis.get('no_action'), crisis.get('applied_plan')
    out = {'policy_version': POLICY_VERSION, 'source_commit': source_commit(),
           'account_id': customer['account_id'], 'scenario_hash': scenario_hash(scenario),
           'horizon_months': scenario.horizon_months}
    if base is None or applied is None:
        out.update(outcome='REVIEW_REQUIRED', headline='The financial engine could not validate this scenario. No action is recommended until the inputs are reviewed.',
                   prioritized_actions=[], candidate_action_decisions=[], comparison=None,
                   diagnosis=None, required_target_only=[], bank_review_flags=crisis.get('review_flags', []),
                   next_review_checkpoint='Before any customer discussion', model_limitations=[])
        return out

    complete = base['funding_result_complete']
    first, lowest = _first(base), _lowest(base)
    month1 = base['schedule'][1] if len(base['schedule']) > 1 else None
    monthly_gap = round(month1['spending'] - month1['quantified_income'], 2) if month1 else None
    one_offs = [{'month': r['month'], 'receipt': r['one_off_receipt'], 'cost': r['one_off_cost']}
                for r in base['schedule'] if r['one_off_receipt'] or r['one_off_cost']]
    need = base['full_funding_need']
    known = base['additional_cash_needed']
    basis = ('historical estimate, not verified current cash'
             if base['opening_basis'] == 'HISTORICAL_PROXY' else 'supplied cash figure')
    lead = crisis.get('lead_module')
    diagnosis = {
        'opening_cash': base['opening_cash'], 'opening_cash_basis': base['opening_basis'],
        'month1_inflow': month1['income'] if month1 else None,
        'month1_spending': month1['spending'] if month1 else None,
        'month1_net_gap': monthly_gap, 'one_off_events': one_offs,
        'first_shortfall': first, 'lowest_cash': lowest,
        'no_action_horizon_need': need, 'known_components_need': known, 'complete': complete,
        'unresolved_effects': base['unresolved_effects'],
        'lead_module': lead, 'lead_module_name': MODULE_NAMES.get(lead),
        'support_modules': crisis.get('support_modules', []),
        'module_reason': _module_reason(lead, scenario, base),
    }

    candidates = []
    payment = _included_loan_payment(customer)
    horizon = scenario.horizon_months
    # Remaining targets are measured after supported actions (policy §8 A: $260/month).
    target_upfront, target_monthly = _targets(applied)
    if not applied['funding_result_complete']:
        target_monthly = None

    # 1. Earliest shortfall: quantified cash needed, TARGET_ONLY (policy §4.1, M3).
    if first is not None:
        whole = need if need is not None else known
        candidates.append(_action(
            'cover-earliest-shortfall', ['M3'] if first['month'] == 0 else [lead or 'M1'],
            f"Arrange {_cad(first['need'])} of accessible cash " + ('immediately' if first['month'] == 0 else f"before {first['label']}"),
            status='TARGET_ONLY', priority=10,
            instruction=(f"Cash first runs out at {first['label']}, short by {_cad(first['need'])}. "
                         f"Covering the whole {horizon}-month plan needs {_cad(whole)}"
                         f"{'' if need is not None else ' (known amounts only)'}. "
                         'Review the customer\'s other accessible funds, documented benefits or an approved credit option with them.'),
            rationale='Policy priority 1: prevent or quantify the earliest negative accessible-cash checkpoint.',
            evidence=['DERIVED: dated cash ledger from recorded medians and the supplied shock'],
            amount=first['need'], frequency='one-time, by the shortfall date', starts='now', ends=first['label'],
            cash_treatment='Target only. No cash is credited until a source is verified.',
            outstanding=whole,
            downsides=['Source of funds is not established', 'Any new credit is not assumed to be available'],
            review=f"Confirm a funding source before {first['label']}"))

    # 2. Existing transfer pauses already decided by the guarded engine (M1/M5).
    for decision in crisis.get('pause_decisions', []):
        applied_id = decision['status'] != 'excluded'
        improvement = round(base['additional_cash_needed'] - applied['additional_cash_needed'], 2)
        candidates.append(_action(
            f"pause-{decision['event_id']}", ['M1', 'M5'] if 'M5' in crisis.get('affected_modules', []) else ['M1'],
            f"Pause scheduled payment {decision['event_id']}",
            status='SUPPORTED_MODELED' if applied_id else 'BLOCKED_OR_UNKNOWN', priority=15,
            instruction=decision['reason'],
            rationale='A confirmed outflow already inside spending can be released once, with its fee posted once.',
            evidence=['BANK_CONFIRMED (as supplied): included in spending, pause approved, fee known'] if applied_id
                     else ['UNKNOWN_OR_CONFLICTING: inclusion, approval or fee evidence is incomplete'],
            cash_treatment='Releases the included outflow once; creates no new wealth.' if applied_id else 'No cash credited.',
            first_effect=(_first(applied) or {}).get('label') if applied_id else None,
            horizon_effect=-improvement if applied_id else 0.,
            outstanding=applied['full_funding_need'] if applied_id else None,
            downsides=['Delays the original savings goal'] if applied_id else [],
            decision='candidate' if applied_id else 'excluded', reason=decision['reason']))

    # 3. Loan payment relief: CONDITIONAL emergency bridge, costed (M4, policy §5 M4, ex. C).
    if first is not None and payment and payment > 0:
        bridge, why_not = _loan_bridge(customer, scenario, opening_cash, base, payment)
        if bridge is None:
            candidates.append(_action('loan-payment-bridge', ['M4'], 'Ask the lender about temporary payment relief',
                status='BLOCKED_OR_UNKNOWN', priority=20, instruction=why_not,
                rationale='Relief must arrive at or before the shortfall it is meant to prevent.',
                evidence=[f'OBSERVED: median loan payment {_cad(payment)} in recorded spending'],
                cash_treatment='No cash credited.', decision='excluded', reason=why_not))
        else:
            path = bridge['path']
            new_first = _first(path)
            moved = new_first is None or (new_first['month'], new_first['phase'] != 'start') > (first['month'], first['phase'] != 'start')
            m = bridge['months']
            label = f"Months 1–{m}" if m > 1 else 'Month 1'
            text = (f"If the lender approves skipping {m} payment{'s' if m > 1 else ''} of {_cad(payment)} ({label}) "
                    f"with a {_cad(bridge['repayment'])} catch-up at Month {bridge['repay_month']} start and no fee, "
                    f"the first shortfall moves from {first['label']} to "
                    f"{new_first['label'] if new_first else 'none within the plan'}. "
                    f"Total need over {horizon} months: {_cad(path['additional_cash_needed'])} "
                    f"(was {_cad(base['additional_cash_needed'])}). This buys time; it does not reduce what is owed.")
            candidates.append(_action(
                'loan-payment-bridge', ['M4'], 'Ask the lender about temporary payment relief',
                status='CONDITIONAL_ONLY', priority=20 if moved else 60, instruction=text,
                rationale='Policy priority 2: defend obligations; a deferral is a costed bridge, never a saving.',
                evidence=[f'OBSERVED: median loan payment {_cad(payment)} already in recorded spending',
                          'ASSUMED_FOR_COMPARISON: deferral terms, zero fee and approval are hypothetical'],
                amount=payment, frequency=f'{m} month{"s" if m > 1 else ""}', starts='Month 1',
                ends=f"Month {bridge['repay_month']} start (catch-up)",
                cash_treatment='Separate comparison only; not posted to the supported plan.',
                first_effect=new_first['label'] if new_first else 'no shortfall within the plan',
                horizon_effect=round(path['additional_cash_needed'] - base['additional_cash_needed'], 2),
                outstanding=path['additional_cash_needed'],
                downsides=['Lender approval, fees and interest are unknown', f"Catch-up of {_cad(bridge['repayment'])} is still owed"],
                review='Lender terms: approval, fee, interest and repayment date',
                decision='candidate' if moved else 'excluded',
                reason='' if moved else 'Relief would not move the earliest shortfall.'))
    elif first is not None:
        candidates.append(_action('loan-payment-bridge', ['M4'], 'Ask the lender about temporary payment relief',
            status='BLOCKED_OR_UNKNOWN', priority=90, instruction='No loan payment is recorded in this account\'s spending.',
            rationale='Relief can only release a payment the account actually makes.',
            evidence=['OBSERVED: no recurring loan payment in the history'], cash_treatment='No cash credited.',
            decision='excluded', reason='No recorded loan payment to defer.'))

    # 4. Recurring gap: required monthly improvement, TARGET_ONLY (M1/M2, policy §4.3).
    if target_monthly and target_monthly > 0:
        candidates.append(_action(
            'close-monthly-gap', ['M2'] if lead != 'M1' else ['M1', 'M2'],
            f"Close a monthly gap of {_cad(target_monthly)}",
            status='TARGET_ONLY', priority=30,
            instruction=(f"To stay at or above CAD 0 through Month {horizon}, inflow must rise or adjustable spending fall by "
                         f"{_cad(target_monthly)} per month from Month 1"
                         f"{' on top of the supported actions' if applied['checkpoints'] != base['checkpoints'] else ''}"
                         f"{f', after {_cad(target_upfront)} upfront' if target_upfront else ''}. "
                         'Review documented income sources and spending the customer confirms is adjustable; '
                         'rent, loan payments and insurance are not assumed to be cuttable.'),
            rationale='Policy priority 3: structural deficits need a recurring fix; a delay alone is not a solution.',
            evidence=['DERIVED: minimum monthly improvement that keeps every checkpoint non-negative'],
            amount=target_monthly, frequency='monthly', starts='Month 1', ends=f'Month {horizon}',
            cash_treatment='Target only. No spending cut or income is assumed.',
            downsides=['Which costs are adjustable is not established from transaction data'],
            review='Confirm specific, verified changes with the customer'))
    elif month1 and monthly_gap and monthly_gap > 0 and first is None and complete:
        candidates.append(_action(
            'watch-monthly-deficit', ['M2'], f"Plan for spending above inflow by {_cad(monthly_gap)} a month",
            status='TARGET_ONLY', priority=40,
            instruction=(f"Cash covers this plan, but it falls by about {_cad(monthly_gap)} each month. "
                         f"Ending cash is {_cad(base['ending_cash'])}. Review before the deficit continues past Month {horizon}."),
            rationale='A covered horizon does not prove the deficit is sustainable.',
            evidence=['DERIVED: Month 1 inflow minus spending'], amount=monthly_gap, frequency='monthly',
            cash_treatment='Target only.', review=f'Before Month {horizon} end'))

    # 5. A proposed goal contribution (main plan) that the shock makes unaffordable.
    before, revised = crisis.get('goal_contribution_before') or 0., crisis.get('goal_contribution_revised') or 0.
    if before > 0 and revised < before:
        candidates.append(_action(
            'hold-goal-contribution', ['M1'], f"Hold the planned {_cad(before)} monthly savings amount",
            status='SUPPORTED_MODELED', priority=50,
            instruction=(f"Reduce the planned savings amount from {_cad(before)} to {_cad(revised)} a month until the shock passes. "
                         'Because it was a proposal, this frees CAD 0.00 of existing cash; it avoids a new commitment.'),
            rationale='Suspend new non-essential commitments that would worsen the cash path (policy M1.3).',
            evidence=['DERIVED: guarded affordability check before and after the shock'],
            amount=round(before - revised, 2), frequency='monthly', starts='Month 1',
            cash_treatment='Proposal never entered spending: CAD 0.00 cash effect.', horizon_effect=0.,
            downsides=['Delays the reserve goal']))

    # 6. Dated receipts: keep them liquid while a need remains (M8, policy §5 M8.6).
    receipts = [r for r in one_offs if r['receipt']]
    for r in receipts:
        late = first is not None and (r['month'], 0) > (first['month'], 0 if first['phase'] == 'start' else 1)
        if known > 0:
            candidates.append(_action(
                f"keep-receipt-m{r['month']}", ['M8'], f"Keep the {_cad(r['receipt'])} receipt in accessible cash",
                status='SUPPORTED_MODELED', priority=45,
                instruction=(f"Use the receipt at {_when(r['month'], 'start')} toward the remaining need rather than allocating it."
                             + (f" It arrives after the first shortfall ({first['label']}), so it cannot cover that earlier gap." if late else '')),
                rationale='A windfall with an unresolved funding need goes first to the quantified deficit.',
                evidence=['JUDGE_SPECIFIED: supplied receipt amount and date'],
                amount=r['receipt'], starts=_when(r['month'], 'start'),
                cash_treatment='Already in the scenario ledger once; nothing extra is credited.', horizon_effect=0.))
        else:
            candidates.append(_action(
                f"review-receipt-m{r['month']}", ['M8'], f"Hold the {_cad(r['receipt'])} receipt in liquid savings pending review",
                status='CONDITIONAL_ONLY', priority=55,
                instruction=('No shortfall remains. Keep it accessible until the customer\'s goals, time horizon and risk '
                             'profile are confirmed; no investment product is selected from transaction data.'),
                rationale='Investment needs suitability evidence (policy M8.5).',
                evidence=['JUDGE_SPECIFIED: supplied receipt'], amount=r['receipt'],
                cash_treatment='No allocation is modeled.', review='Suitability review before any investment'))

    # 7. Bill timing (M7): only the existing conditional daily replay, on its own basis.
    timing = crisis.get('timing_comparison')
    if timing:
        candidates.append(_action(
            'bill-date-shift', ['M7'], 'Ask billers to move a payment date',
            status='CONDITIONAL_ONLY', priority=35,
            instruction=f"A 7-day bill move in the daily replay changes the daily-basis need by {_cad(timing['funding_gap_improvement'])}.",
            rationale='Timing fixes help within-month shortages but do not fix a monthly deficit.',
            evidence=['ASSUMED_FOR_COMPARISON: historical daily replay; biller approval unverified'],
            cash_treatment='Daily replay basis only; not mixed into the monthly plan.',
            review='Biller approval and effective dates'))

    # 8. Recovery (M6): only from a separately supplied checkpoint.
    recovery = crisis.get('recovery') or {}
    if recovery.get('status') == 'REBUILDING':
        eta = recovery.get('months_to_target')
        candidates.append(_action(
            'rebuild-reserve', ['M6'], f"Rebuild the reserve by {_cad(recovery['monthly_contribution'])} a month",
            status='SUPPORTED_MODELED', priority=25,
            instruction=(f"Target {_cad(recovery['reserve_target'])}; gap {_cad(recovery['reserve_gap'])}; "
                         + (f'about {eta} months at the supported amount.' if eta else 'timeline open until a contribution is supported.')),
            rationale='Reserve restoration after obligations and stable cash flow are confirmed.',
            evidence=['BANK_CONFIRMED (as supplied): recovery checkpoint'], amount=recovery['monthly_contribution'],
            frequency='monthly', cash_treatment='Liquid reserve; no investment returns assumed.'))

    # 9. Unknown parts: block the full funding claim and say what to confirm.
    if not complete:
        names = {'one_off_cost': 'the one-time cost amount', 'one_off_receipt': 'the amount of money coming in',
                 'income_multiplier': 'how much income changes', 'income_delta': 'how much income changes',
                 'household_bills_percent': 'how much bills change', 'household_bills_delta': 'how much bills change',
                 'expense_delta': 'how much spending changes', 'expense_percent': 'how much spending changes',
                 'debt_payment_delta': 'the loan payment change', 'unspecified_event': 'what changes financially and by how much'}
        missing = list(dict.fromkeys(names.get(e.type, 'the amount of this change') for e in scenario.effects
                                     if e.value is None or e.evidence == 'unknown'))
        missing = missing or [u for u in base['unresolved_effects'] if 'conditional operator assumption' not in u] or base['unresolved_effects']
        candidates.append(_action(
            'confirm-missing-details', [lead or 'M1'], 'Confirm the missing amounts or dates',
            status='BLOCKED_OR_UNKNOWN', priority=5,
            instruction='Confirm ' + '; '.join(missing[:4]) + '. Until then the plan shows known amounts only and the full funding need is not established.',
            rationale='No complete funding claim for an unpriced material effect (policy §3, example E).',
            evidence=['UNKNOWN_OR_CONFLICTING: ' + m for m in missing[:4]],
            cash_treatment='Known components only; no guessed impact.', review='Bank-side confirmation'))

    # 10. Nothing to fix: maintain and monitor.
    if first is None and complete and not any(c['priority'] < 40 and c['decision'] != 'excluded' for c in candidates):
        candidates.append(_action(
            'maintain-and-review', [lead or 'M8'], 'No change needed: keep the current plan',
            status='MAINTAIN', priority=1,
            instruction=(f"Cash stays at or above CAD 0 at every checkpoint (lowest {_cad(lowest['cash'])} at {lowest['label']}). "
                         f"Keep the main plan and review again by Month {horizon}."),
            rationale='No safe change is justified when no shortfall is projected.',
            evidence=['DERIVED: complete dated ledger'], cash_treatment='Ledger unchanged.'))

    ordered = sorted(candidates, key=lambda c: (c['decision'] == 'excluded', c['priority']))
    primary = [c for c in ordered if c['decision'] != 'excluded'][:MAX_PRIMARY]
    for c in ordered:
        if c in primary:
            c['decision'] = 'selected'
        elif c['decision'] != 'excluded':
            c['decision'] = 'considered'
            c['reason'] = c['reason'] or 'Lower priority than the selected actions; still available for review.'

    statuses = {c['status'] for c in primary}
    outcome = ('MAINTAIN' if 'MAINTAIN' in statuses or (first is None and complete) else
               'REVIEW_REQUIRED' if not complete else
               'SUPPORTED_ACTIONS' if 'SUPPORTED_MODELED' in statuses and applied['additional_cash_needed'] < known else
               'NO_SUPPORTABLE_ACTION')
    supported = _path_summary(applied)
    no_action = _path_summary(base)
    same = applied['checkpoints'] == base['checkpoints']
    targets = [{'action_id': c['action_id'], 'amount_cad': c['amount_cad'], 'frequency': c['frequency'],
                'by': c['ends_at']} for c in candidates if c['status'] == 'TARGET_ONLY']
    out.update(
        outcome=outcome, headline=_headline(scenario, diagnosis, horizon, basis),
        diagnosis=diagnosis, prioritized_actions=primary, candidate_action_decisions=ordered,
        comparison={'no_action': no_action, 'supported_actions': supported, 'identical': same,
                    'identical_reason': ('No action passes the evidence gates for posting cash, so both paths match. '
                                         'Targets and conditional options above show what would change the outcome.') if same and first is not None else None,
                    'funding_improvement': round(base['additional_cash_needed'] - applied['additional_cash_needed'], 2)},
        required_target_only=targets,
        normal_goal_impact=_goal_impact(crisis, goal_plan),
        bank_review_flags=crisis.get('review_flags', []),
        next_review_checkpoint=_next_review(scenario, first, horizon),
        model_limitations=[f'Opening cash is a {basis}.',
                           'Bank inflows are not verified wages; one account may not show all household finances.',
                           'Month-start and month-end checkpoints do not establish daily solvency.',
                           'Supported or conditional actions are not executed banking instructions.'])
    return out


def _module_reason(lead, scenario, base):
    reasons = {'M1': 'Recurring income falls under the supplied shock.',
               'M2': 'Recurring spending exceeds inflow in the projection.',
               'M3': 'A one-time cost or the first checkpoint creates immediate cash pressure.',
               'M4': 'Recorded loan payments are at risk once cash runs short.',
               'M5': 'Several adverse effects interact in one ledger.',
               'M6': 'A supplied recovery checkpoint supports reserve rebuilding.',
               'M7': 'Cash timing or access drives the shortage.',
               'M8': 'Additional funds or surplus need a protected allocation.'}
    return reasons.get(lead, 'No financial response module applies.')


def _headline(scenario, d, horizon, basis):
    first = d['first_shortfall']
    start = f"Starting from {_cad(d['opening_cash'])} ({basis})"
    if first is None and d['complete']:
        return f"{start}, cash stays above zero for all {horizon} months. Lowest point: {_cad(d['lowest_cash']['cash'])} at {d['lowest_cash']['label']}."
    if first is None:
        return f"{start}, no shortfall appears in the known amounts, but some parts of the shock are not quantified yet."
    need = d['no_action_horizon_need']
    tail = (f"Covering all {horizon} months needs {_cad(need)}." if need is not None
            else f"Known amounts alone need {_cad(d['known_components_need'])}; the full need is not established.")
    when = 'immediately' if first['month'] == 0 else f"at {first['label']}"
    return f"{start}, cash runs out {when} (short {_cad(first['need'])}). {tail}"


def _goal_impact(crisis, goal_plan):
    status = crisis.get('goal_status')
    text = {'MAINTAINED': 'Keep the normal goal: it remains affordable under this shock.',
            'REDUCED': 'Reduce the normal goal contribution while the shock lasts.',
            'PAUSED': 'Pause the proposed normal-goal contribution while the shock lasts.',
            'NOT_SCHEDULED': 'No fixed contribution is scheduled; the normal goal stays a reserve target to revisit after the shock.',
            'EXISTING_TRANSFERS_PAUSED': 'Confirmed existing transfers are paused under supplied terms; revisit the goal afterwards.',
            'BASELINE_REVIEW_REQUIRED': 'The normal goal needs review even before this shock.',
            'REVIEW_REQUIRED': 'Hold the normal goal for review until the missing amounts are confirmed.'}.get(status, 'Review the normal goal.')
    return {'goal_status': status, 'primary_goal': (goal_plan or {}).get('primary_goal'),
            'contribution_before': crisis.get('goal_contribution_before'),
            'contribution_after': crisis.get('goal_contribution_revised'), 'summary': text}


def _next_review(scenario, first, horizon):
    options = []
    if first is not None:
        options.append((max(first['month'] - 1, 0), 'Now: confirm a funding source for the immediate shortfall' if first['month'] == 0
                        else f"Before {first['label']}: confirm a funding source for the first shortfall"))
    end = _income_end(scenario)
    if end is not None and end <= horizon:
        options.append((end, f'Month {end}: confirm income once the temporary reduction ends'))
    for e in scenario.effects:
        if e.repayment_month and e.repayment_month <= horizon:
            options.append((e.repayment_month, f'Month {e.repayment_month}: deferred loan catch-up is due'))
    if not options:
        options.append((horizon, f'Month {horizon}: reassess with updated balances'))
    return min(options)[1]
