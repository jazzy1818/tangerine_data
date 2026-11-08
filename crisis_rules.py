"""Shared G25 rule used by both goal triggers and crisis runtime validation."""


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
