"""Build the exact same privacy-minimized case for every selection backend."""
import hashlib
import json
import math

from .schemas import (ClassificationCase, CustomerProfile, FinancialConstraints,
                      MONEY_EFFECTS, NormalizedEffect, ShockScenario)


def canonical_json(case: ClassificationCase) -> str:
    return json.dumps(case.model_dump(mode='json'), sort_keys=True, separators=(',', ':'), allow_nan=False)


def case_hash(case: ClassificationCase) -> str:
    return hashlib.sha256(canonical_json(case).encode()).hexdigest()


def scenario_from_engine(income_multiplier=1.0, bills_increase_pct=0.0, one_off_costs=0.0):
    effects = []
    if income_multiplier != 1:
        effects.append({'type': 'income_multiplier', 'value': income_multiplier, 'duration_months': 6})
    if bills_increase_pct:
        effects.append({'type': 'household_bills_percent', 'value': bills_increase_pct * 100,
                        'ongoing': True})
    if one_off_costs:
        effects.append({'type': 'one_off_cost', 'value': one_off_costs, 'start_month': 0})
    return ShockScenario(effects=effects, phase='active' if effects else 'normal')


def build_case(profile: CustomerProfile, scenario: ShockScenario,
               constraints: FinancialConstraints | None = None, *, planning_cash: float | None = None) -> ClassificationCase:
    constraints = constraints or FinancialConstraints()
    b, f = profile.baseline, profile.features
    scale = max(b.I, b.S, 1.0)  # Never transmit this CAD scale, IDs, dates, or narrative.
    reasons, missing, effects = set(), [], []
    income, spending, immediate_buffer = b.I, b.S, b.B
    if planning_cash is not None:
        if isinstance(planning_cash, bool) or not math.isfinite(planning_cash):
            raise ValueError('Supplied planning cash must be finite')
        immediate_buffer = planning_cash
    families = set()
    if scenario.phase == 'active' and not scenario.effects:
        missing.append('Provide financial effects, or explicitly mark the scenario as normal/no financial change.')
    for index, effect in enumerate(scenario.effects):
        t, v = effect.type, effect.value
        if effect.start_month > scenario.horizon_months:
            continue
        unit = ('cash_scale' if t in MONEY_EFFECTS else 'ratio' if t == 'income_multiplier'
                else 'days' if t == 'payment_delay_days' else 'unknown' if t == 'unspecified_event' else 'percent')
        cash_delta = None
        if v is not None and effect.evidence != 'unknown':
            if t == 'income_multiplier': cash_delta = (v - 1) * b.I
            elif t in {'income_delta', 'one_off_receipt'}: cash_delta = v
            elif t in {'expense_delta', 'household_bills_delta', 'debt_payment_delta', 'one_off_cost'}: cash_delta = -v
            elif t == 'expense_percent': cash_delta = -v * b.S / 100
            elif t == 'household_bills_percent': cash_delta = -v * b.H / 100
        effects.append(NormalizedEffect(type=t, value=v/scale if v is not None and t in MONEY_EFFECTS else v,
                                       unit=unit, start_month=effect.start_month,
                                       duration_months=effect.duration_months, ongoing=effect.ongoing,
                                       cashflow_delta_to_scale=cash_delta/scale if cash_delta is not None else None,
                                       evidence=effect.evidence))
        neutral = (t == 'income_multiplier' and v == 1) or (t != 'income_multiplier' and v == 0)
        if (not neutral and t not in {'one_off_cost', 'one_off_receipt', 'investment_return', 'unspecified_event'}
                and effect.duration_months is None and not effect.ongoing):
            missing.append(f'Confirm the duration of effect {index + 1} ({t}), or mark it explicitly ongoing.')
        if v is None or effect.evidence == 'unknown':
            missing.append(f'Confirm the financial value and timing of effect {index + 1} ({t}).')
            continue
        if effect.evidence == 'assumed':
            missing.append(f'Confirm the assumed effect {index + 1} ({t}).')
        if neutral:
            continue
        if t in {'income_multiplier', 'income_delta'}:
            delta = (v - 1) * b.I if t == 'income_multiplier' else v
            if delta:
                reasons.add('income_reduction' if delta < 0 else 'income_increase')
                families.add('income')
            if effect.active(1):
                income += delta
        elif t in {'expense_delta', 'expense_percent', 'household_bills_percent', 'household_bills_delta'}:
            delta = v * b.S / 100 if t == 'expense_percent' else v * b.H / 100 if t == 'household_bills_percent' else v
            if delta:
                reasons.add('cost_increase' if delta > 0 else 'cost_reduction')
                families.add('cost')
            if effect.active(1):
                spending += delta
        elif t == 'debt_payment_delta':
            reasons.add('debt_payment_change')
            if v < 0:
                reasons.add('cost_reduction')
            families.add('debt')
            if effect.active(1):
                spending += v  # S already includes existing debt payments; add only the change.
        elif t in {'one_off_cost', 'one_off_receipt'}:
            reasons.add('one_off_expense' if t == 'one_off_cost' else 'windfall')
            families.add('one_off_cost' if t == 'one_off_cost' else 'receipt')
            if effect.active(0):
                immediate_buffer += -v if t == 'one_off_cost' else v
        elif t in {'liquidity_hold', 'payment_delay_days'}:
            reasons.add('timing_or_access')
            families.add('timing')
            # Holds are a restriction, not a permanent loss or an official runway adjustment.
        elif t == 'investment_return':
            reasons.add('investment_change')
            missing.append('Confirm invested assets, sale/settlement, and any actual cash effect.')
    # Validate sign feasibility in every affected period without creating a second financial solver.
    for month in range(1, scenario.horizon_months + 1):
        inc, out, household, debt = b.I, b.S, b.H, b.P
        for e in scenario.effects:
            if not e.active(month) or e.value is None or e.evidence == 'unknown':
                continue
            t, v = e.type, e.value
            if t == 'income_multiplier': inc += (v-1)*b.I
            elif t == 'income_delta': inc += v
            elif t == 'expense_delta': out += v
            elif t == 'expense_percent': out += v*b.S/100
            elif t in {'household_bills_delta', 'household_bills_percent'}:
                delta = v if t == 'household_bills_delta' else v*b.H/100
                out += delta
                household += delta
            elif t == 'debt_payment_delta':
                out += v
                if debt is not None: debt += v
        if min(inc, out, household) < -1e-9 or (debt is not None and debt < -1e-9):
            raise ValueError(f'Effects imply negative inflow, spending, bills, or loan payment in month {month}.')
    if len(families) > 1:
        reasons.add('compound_effects')
    if not families and not missing:
        reasons.add('no_new_effect')
    if immediate_buffer <= 0:
        reasons.add('immediate_liquidity_pressure')
    if spending > income:
        reasons.add('recurring_shortfall')
    else:
        if income > spending:
            reasons.add('surplus_available')
    if b.S > 0 and immediate_buffer / b.S < constraints.reserve_target_months:
        reasons.add('reserve_below_target')
    if (f.recovered_overdraft_month_share or 0) > 0:
        reasons.add('historical_timing_stress')
    if constraints.timing_mismatch_confirmed:
        reasons.add('timing_or_access')
    if constraints.essential_obligations_at_risk or f.loan_in_arrears:
        reasons.add('essential_obligations_at_risk')
    if scenario.phase == 'recovery':
        reasons.add('recovery')
    if len(constraints.allowed_modules) < 8:
        reasons.add('restricted_modules')
    if missing:
        reasons.add('missing_details')
    gap = spending-income
    # An uncapped first-period screening feature; never claim this models expiry or future effects.
    runway = 0.0 if immediate_buffer <= 0 else immediate_buffer/gap if gap > 0 else None
    return ClassificationCase(
        planning_cash_basis='historical_proxy' if planning_cash is None else 'supplied_scenario',
        features=f, effects=effects, phase=scenario.phase, horizon_months=scenario.horizon_months,
        constraints=constraints, observed_reasons=sorted(reasons), missing_details=list(dict.fromkeys(missing)),
        first_period_gap_to_scale=gap/scale, immediate_buffer_to_scale=immediate_buffer/scale,
        first_period_runway_months=runway,
        first_period_no_shortfall=immediate_buffer > 0 and gap <= 0,
    )
