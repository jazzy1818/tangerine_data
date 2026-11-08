"""Execute the shared ShockScenario in CAD; classifier ratios never enter cash.

Month 0 is immediate. Recurring flows are month-end checkpoints, with separate
month-start access checks. This does not establish daily solvency. Unsupported
or unquantified effects remain visible and prevent a complete funding claim.
"""
from decimal import Decimal, ROUND_HALF_UP
from hashlib import sha256
import json

from plan_classification.schemas import ShockScenario


def money(value):
    number = Decimal(str(value))
    # Bound the public CAD ledger so float serialization still preserves cents;
    # reject impossible magnitudes rather than overflow or emit infinite cash.
    if not number.is_finite() or abs(number) > Decimal('1000000000000'):
        raise ValueError('CAD amounts must be finite and within the supported ±1 trillion range')
    return number.quantize(Decimal('.01'), rounding=ROUND_HALF_UP)


def amount(value):
    return float(money(value))


def scenario_hash(scenario):
    # Execution hash includes the original CAD amounts and local event identity.
    return sha256(scenario.model_dump_json().encode()).hexdigest()


def _base(customer, key):
    return money(customer.get('raw_' + key, customer.get(key)))


def period_values(customer, scenario, month):
    income, spending, bills = (_base(customer, k) for k in ('I', 'S', 'H'))
    baseline_income, baseline_spending = income, spending
    protected = _base(customer, 'F')
    household = bills
    recorded_payment = customer.get('raw_P', customer.get('P'))
    recorded_loan = money(recorded_payment) if recorded_payment is not None else None
    loan = recorded_loan
    included_payment = customer.get('included_loan_payment')
    history = customer.get('history')
    if history is not None and 'loan_payments' in history:
        included_payment = float(history['loan_payments'].median())
    included_payment = money(included_payment) if included_payment is not None else None
    other_fixed = max(Decimal(0), protected - bills - (included_payment or Decimal(0)))
    receipt = cost = held = Decimal(0)
    unknown, applied = [], []
    debt_changes, repayments, pending_deferrals = {}, {}, []
    income_unknown = spending_unknown = False
    income_expired = False
    explicit_income = False
    loan_changed = False
    for index, effect in enumerate(scenario.effects):
        kind, v = effect.type, effect.value
        identity = effect.effect_id or f'effect-{index + 1}'
        if effect.start_month > scenario.horizon_months:
            continue
        if effect.obligation_account_id is not None and effect.obligation_account_id != customer.get('account_id'):
            unknown.append(f'{identity}: payment evidence belongs to another account; no relief or repayment applied')
            continue
        active = effect.active(month)
        repayment_due = effect.debt_change_kind == 'deferral' and month == effect.repayment_month
        if kind in ('income_multiplier', 'income_delta') and v is not None:
            adverse = (v < 1 if kind == 'income_multiplier' else v < 0)
            end = effect.start_month + effect.duration_months if effect.duration_months else None
            if adverse and end is not None and month >= end:
                income_expired = True
        if not active and not repayment_due:
            continue
        if kind == 'unspecified_event':
            unknown.append(f'{identity}: financial effects unspecified')
            continue
        if v is None or effect.evidence == 'unknown':
            unknown.append(f'{identity}: magnitude/evidence unknown')
            income_unknown |= kind in ('income_multiplier', 'income_delta')
            spending_unknown |= kind in ('expense_delta', 'expense_percent', 'household_bills_percent', 'household_bills_delta', 'debt_payment_delta')
            continue
        if v == (1 if kind == 'income_multiplier' else 0):
            if kind == 'income_multiplier':
                explicit_income = True
            continue
        if effect.evidence == 'assumed':
            unknown.append(f'{identity}: conditional operator assumption, not verified fact')
        if kind not in ('one_off_cost', 'one_off_receipt', 'investment_return') and effect.duration_months is None and not effect.ongoing:
            unknown.append(f'{identity}: duration unknown')
            if month > effect.start_month:
                income_unknown |= kind in ('income_multiplier', 'income_delta')
                spending_unknown |= kind not in ('income_multiplier', 'income_delta', 'liquidity_hold', 'payment_delay_days')
                if kind != 'liquidity_hold':
                    continue
        if kind == 'income_multiplier':
            income += money(baseline_income * Decimal(str(v - 1)))
            explicit_income = True
        elif kind == 'income_delta':
            income += money(v)
            explicit_income = True
        elif kind == 'debt_payment_delta':
            payment = recorded_loan
            change = money(v)
            if effect.obligation_payment is not None:
                if not (effect.payment_in_baseline and effect.obligation_source):
                    unknown.append(f'{identity}: supplied loan payment lacks source/baseline inclusion; relief not applied')
                    continue
                payment = money(effect.obligation_payment)
            if v < 0 and payment is None:
                unknown.append(f'{identity}: loan payment unknown; supply sourced payment included in spending; relief not applied')
                continue
            if payment is not None and payment + change < 0:
                raise ValueError(f'Reduction exceeds the specific loan payment in month {month}')
            if v < 0 and effect.obligation_payment is None:
                if included_payment is None:
                    unknown.append(f'{identity}: loan payment inclusion in baseline spending unknown; relief not applied')
                    continue
                if included_payment + change < 0:
                    raise ValueError(f'Reduction exceeds the loan payment included in baseline spending in month {month}')
            # Both legs depend on the same payment evidence and assumption status.
            if repayment_due:
                repayments[index] = money(effect.repayment_amount)
                cost += repayments[index]
            else:
                loan = payment + change if payment is not None else None
                loan_changed = True
                spending += change
                protected += change
                debt_changes[index] = change
                if effect.debt_change_kind == 'deferral' and (
                    effect.repayment_unresolved or effect.repayment_month > scenario.horizon_months
                ):
                    reason = ('deferred loan obligation unresolved; repayment not established'
                              if effect.repayment_unresolved else 'deferred repayment beyond horizon remains owed')
                    unknown.append(f'{identity}: {reason}')
                    if month == effect.start_month:
                        pending_deferrals.append({
                            'effect_id': effect.effect_id, 'type': 'deferred_repayment',
                            'start_month': effect.repayment_month, 'value': effect.repayment_amount,
                            'unresolved': effect.repayment_unresolved,
                        })
        elif kind in ('expense_delta', 'household_bills_delta'):
            spending += money(v)
            if kind != 'expense_delta':
                protected += money(v)
            if kind == 'household_bills_delta':
                household += money(v)
        elif kind == 'expense_percent':
            spending += money(baseline_spending * Decimal(str(v)) / 100)
        elif kind == 'household_bills_percent':
            change = money(bills * Decimal(str(v)) / 100)
            spending += change
            protected += change
            household += change
        elif kind == 'one_off_cost':
            cost += money(v)
        elif kind == 'one_off_receipt':
            receipt += money(v)
        elif kind == 'liquidity_hold':
            held += money(v)
        elif kind in ('payment_delay_days', 'investment_return'):
            # A generic day delay has no identified event; an asset return has no
            # supplied holding or settlement. Neither changes checking cash.
            unknown.append(f'{identity}: {kind} needs dated events or asset/settlement evidence; not applied to cash')
            continue
        applied.append(identity)
    if month and income_expired and not explicit_income:
        income_unknown = True
        unknown.append('Income after temporary reduction ends is not established; no automatic return to 100%.')
    if month == 0:
        income = spending = Decimal(0)
    if income < 0 or spending < 0:
        raise ValueError(f'Scenario implies negative inflow or spending in month {month}')
    protected = max(protected, household + other_fixed + ((loan or Decimal(0)) if loan_changed else Decimal(0)))
    if month and (household < 0 or protected < 0 or spending < protected):
        raise ValueError(f'Scenario cuts below known fixed obligations in month {month}; supply the specific supported obligation change.')
    # For an unknown entire income, only zero dollars are established, NOT a
    # claim of zero actual income. Actual amount is None in the displayed ledger.
    if income_unknown:
        income = Decimal(0)
    return dict(income=income, spending=spending, receipt=receipt, cost=cost,
                held=held, income_unknown=income_unknown, spending_unknown=spending_unknown,
                unknown=unknown, applied=applied, protected=protected,
                debt_changes=debt_changes, repayments=repayments, pending_deferrals=pending_deferrals)


def _calculate(customer, scenario, *, opening_cash=None, contribution=0.,
               spending_releases=None, release_fees=None):
    cash = _base(customer, 'B') if opening_cash is None else money(opening_cash)
    if not cash.is_finite():
        raise ValueError('Opening cash must be finite')
    if contribution < 0:
        raise ValueError('Contribution cannot be negative')
    releases = spending_releases or {}
    fees = release_fees or {}
    for value in [contribution, *releases.values(), *fees.values()]:
        if not Decimal(str(value)).is_finite() or value < 0:
            raise ValueError('Cash effects must be finite and nonnegative')
    initial = cash
    rows, checkpoints, flags, unknowns = [], [], [], []
    pending = [e.model_dump(mode='json') for e in scenario.effects if e.start_month > scenario.horizon_months]
    complete = not (scenario.phase == 'active' and not scenario.effects)
    if not complete:
        unknowns.append('Active event has no supplied financial effects; no-impact must be explicitly marked normal.')
    if scenario.phase == 'recovery':
        complete = False
        unknowns.append('Recovery phase alone does not establish updated cash or income; this is a baseline reference, with recovery assessed separately.')
    for month in range(scenario.horizon_months + 1):
        p = period_values(customer, scenario, month)
        pending.extend(p['pending_deferrals'])
        release = money(releases.get(month, 0)) if month else Decimal(0)
        fee = money(fees.get(month, 0)) if month else Decimal(0)
        if month and release > p['spending'] - p['protected']:
            raise ValueError('Paused transfers exceed spending already included in this period')
        start = cash
        cash = money(cash + p['receipt'] - p['cost'] - fee)
        checkpoints.append({'month': month, 'phase': 'start', 'cash': float(cash - p['held'])})
        transfer = money(contribution) if month else Decimal(0)
        if month:
            cash = money(cash + p['income'] - p['spending'] + release - transfer)
        if p['unknown']:
            complete = False
            unknowns.extend(p['unknown'])
        if p['held'] > max(Decimal(0), cash):
            flags.append(f'ACCESS_SHORTFALL: Honoring the modeled payments while preserving held funds requires additional accessible cash in month {month}; no borrowing is assumed.')
        accessible = money(cash - p['held'])
        checkpoints.append({'month': month, 'phase': 'end', 'cash': float(accessible)})
        rows.append({'month': month, 'start_balance': float(start),
                     'income': None if p['income_unknown'] else float(p['income']),
                     'quantified_income': float(p['income']), 'spending': float(p['spending']),
                     'one_off_receipt': float(p['receipt']), 'one_off_cost': float(p['cost']),
                     'deferred_repayment': float(sum(p['repayments'].values())),
                     'paused_existing_outflow': float(release), 'action_fees': float(fee),
                     'proposed_contribution': float(transfer), 'held_cash': float(p['held']),
                     'total_cash': float(cash), 'end_balance': float(accessible),
                     'period_complete': not p['unknown'], 'applied_effect_ids': p['applied']})
    first = next((c for c in checkpoints if c['cash'] < 0), None)
    minimum = min(c['cash'] for c in checkpoints)
    gap = amount(max(0., -minimum))
    if unknowns:
        flags.append('PARTIAL_PROJECTION: Only quantified components are included; no complete funding conclusion is established.')
    if any(e['start_month'] is not None and e['start_month'] > scenario.horizon_months for e in pending):
        flags.append('BEYOND_HORIZON: Supplied effects outside this horizon remain scheduled; they are not treated as paid or received.')
    if any(e.type in ('income_multiplier', 'income_delta') and e.value is not None
           and (e.value < 1 if e.type == 'income_multiplier' else e.value < 0)
           and e.duration_months is not None and e.start_month + e.duration_months > scenario.horizon_months
           for e in scenario.effects):
        flags.append('POST_BENEFIT_INCOME_UNVERIFIED: This horizon does not establish replacement income after temporary inflows end.')
    return {'opening_cash': float(initial), 'opening_basis': 'HISTORICAL_PROXY' if opening_cash is None else 'SUPPLIED_SCENARIO',
            'horizon_months': scenario.horizon_months, 'scenario_hash': scenario_hash(scenario),
            'schedule': rows, 'checkpoints': checkpoints, 'ending_cash': rows[-1]['end_balance'],
            'minimum_cash': amount(minimum), 'first_shortfall_month': first['month'] if first else None,
            'first_shortfall_phase': first['phase'] if first else None,
            'additional_cash_needed': gap, 'full_funding_need': gap if complete else None,
            'funding_result_complete': complete, 'makes_it_through_horizon': complete and first is None,
            'unresolved_effects': list(dict.fromkeys(unknowns)), 'pending_effects': pending,
            'review_flags': list(dict.fromkeys(flags)), 'resolution': 'MONTH_START_AND_END'}


def execute_scenario(customer, scenario, *, opening_cash=None, contribution=0.,
                     spending_releases=None, release_fees=None):
    """Validated monthly execution, separate from the unchanged official formula."""
    scenario = ShockScenario.model_validate(scenario)
    result = _calculate(customer, scenario, opening_cash=opening_cash, contribution=contribution,
                        spending_releases=spending_releases, release_fees=release_fees)
    return result


def enforce_execution(result, customer, scenario, **kwargs):
    """Reconcile every checkpoint with original CAD inputs before presentation.

    Always runs at the crisis-plan boundary, independently of classifier output.
    No Python assert or enable/disable flag. Raises only for an internal invalid
    result; the orchestrator returns a nonblocking review result in that case.
    """
    expected = _calculate(customer, scenario, **kwargs)
    if result != expected:
        raise ValueError('Runtime cash-ledger validation failed: output differs from supplied effects.')
    return {'enforced': True, 'status': 'passed', 'policy_version': 'dated-cash-v1'}


def organizer_inputs(scenario):
    """Lossless adapter only for the unchanged organizer six-month presets."""
    if (scenario.horizon_months != 6 or scenario.phase == 'recovery'
        or (scenario.phase == 'active' and not scenario.effects)):
        return None
    inputs = {'income_multiplier': 1., 'bills_increase_pct': 0., 'one_off_costs': 0.}
    for e in scenario.effects:
        if e.value is None or e.evidence not in ('judge_specified', 'user_confirmed'):
            return None
        if e.type == 'one_off_cost' and e.start_month == 0:
            inputs['one_off_costs'] += e.value
        elif e.type == 'income_multiplier' and e.start_month == 1 and (e.duration_months == 6 or e.ongoing):
            inputs['income_multiplier'] = e.value
        elif e.type == 'household_bills_percent' and e.start_month == 1 and (e.duration_months == 6 or e.ongoing):
            inputs['bills_increase_pct'] = e.value / 100
        else:
            return None
    return inputs
