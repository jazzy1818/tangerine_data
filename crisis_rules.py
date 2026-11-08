"""Shared G25 rule used by both goal triggers and crisis runtime validation."""
from decimal import Decimal, ROUND_CEILING


def goal_worsened(*, baseline_gap, scenario_gap, baseline_first=None,
                  scenario_first=None, normal_contribution=0., scenario_contribution=0.):
    """A changed object or an improving deficit is not a new goal interruption."""
    earlier = scenario_first is not None and (baseline_first is None or scenario_first < baseline_first)
    return (scenario_gap > baseline_gap + .005 or earlier
            or scenario_contribution < normal_contribution - .005)


def first_shortfall_order(path):
    month = path.get('first_shortfall_month')
    if month is None:
        return None
    return month * 2 + (0 if path.get('first_shortfall_phase') == 'start' else 1)


def funding_target(path):
    """Extra upfront cash plus a uniform month-end improvement from Month 1."""
    upfront, recurring = Decimal(0), Decimal(0)
    for point in path['checkpoints']:
        periods = point['month'] - (point['phase'] == 'start')
        need = -Decimal(str(point['cash']))
        if periods <= 0:
            upfront = max(upfront, need)
        else:
            recurring = max(recurring, (need - upfront) / periods)
    return float(upfront), float(recurring.quantize(Decimal('.01'), rounding=ROUND_CEILING))


def cash_path_metrics(path):
    points = path['checkpoints']
    first = next((point for point in points if point['cash'] < 0), None)
    return {
        'first_shortfall': {**first, 'need_cad': -first['cash']} if first else None,
        'lowest_checkpoint': min(points, key=lambda point: point['cash']),
        'full_funding_need_cad': path['full_funding_need'],
        'known_components_need_cad': path['additional_cash_needed'],
        'ending_cash_cad': path['ending_cash'],
        'complete': path['funding_result_complete'],
    }


def evidenced_goal_worsened(baseline, scenario, *, normal_contribution, scenario_contribution):
    """Tri-state G25: missing capacity is a review hold, not proven deterioration.

    Complete matched prefixes can prove an earlier shortage before a later unknown
    event. Capacity changes require complete paths on both sides.
    """
    complete = baseline['funding_result_complete'] and scenario['funding_result_complete']
    if complete:
        return goal_worsened(baseline_gap=baseline['additional_cash_needed'],
            scenario_gap=scenario['additional_cash_needed'], baseline_first=first_shortfall_order(baseline),
            scenario_first=first_shortfall_order(scenario), normal_contribution=normal_contribution,
            scenario_contribution=scenario_contribution)
    rows = []
    for left, right in zip(baseline['schedule'], scenario['schedule'], strict=True):
        if not left['period_complete'] or not right['period_complete']:
            break
        rows.append(left['month'])
    for month in rows:
        b = [p for p in baseline['checkpoints'] if p['month'] <= month]
        s = [p for p in scenario['checkpoints'] if p['month'] <= month]
        if max(0., -min(p['cash'] for p in s)) > max(0., -min(p['cash'] for p in b)) + .005:
            return True
        first_b = next((i for i,p in enumerate(b) if p['cash'] < 0), None)
        first_s = next((i for i,p in enumerate(s) if p['cash'] < 0), None)
        if first_s is not None and (first_b is None or first_s < first_b):
            return True
    return None
