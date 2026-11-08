"""Regression checks for ambiguous and duplicated financial inputs."""
import pytest

from plan_classification.schemas import ShockEffect, ShockScenario


def test_duplicate_charge_cannot_change_identity_through_evidence():
    with pytest.raises(ValueError, match='Duplicate'):
        ShockScenario(effects=[
            {'type': 'one_off_cost', 'value': 3000, 'start_month': 0, 'evidence': 'judge_specified'},
            {'type': 'one_off_cost', 'value': 3000, 'start_month': 0, 'evidence': 'user_confirmed'},
        ])


@pytest.mark.parametrize('value', [True, False, '55%', '0.55'])
def test_effect_amount_requires_numeric_json(value):
    with pytest.raises(ValueError):
        ShockEffect(type='income_multiplier', value=value)


@pytest.mark.parametrize('effect', [
    {'type': 'income_multiplier', 'value': .55, 'duration_months': 6, 'ongoing': True},
    {'type': 'one_off_cost', 'value': 200, 'ongoing': True},
    {'type': 'unspecified_event', 'ongoing': True},
])
def test_ongoing_is_explicit_and_consistent(effect):
    with pytest.raises(ValueError, match='ongoing'):
        ShockEffect(**effect)


def test_known_and_unknown_duration_remain_distinguishable():
    unknown = ShockEffect(type='household_bills_percent', value=15)
    ongoing = ShockEffect(type='household_bills_percent', value=15, ongoing=True)
    fixed = ShockEffect(type='household_bills_percent', value=15, duration_months=6)
    assert unknown.duration_months is None and not unknown.ongoing
    assert ongoing.ongoing and ongoing.duration_months is None
    assert fixed.duration_months == 6 and not fixed.ongoing


def test_no_change_phase_rejects_conflicting_financial_effect():
    with pytest.raises(ValueError, match='normal/no-change'):
        ShockScenario(phase='normal', effects=[{'type': 'income_multiplier', 'value': .55}])
    assert ShockScenario(phase='normal', effects=[{'type': 'income_multiplier', 'value': 1}])
