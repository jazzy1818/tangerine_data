"""Offline plain-text shock reader and its visible defaults."""
import pytest

from plan_classification import ShockScenario
from web_app.shock_text import finalize, parse


def read(text, horizon=6):
    effects, duration = parse(text)
    finished, horizon, defaults, questions = finalize(effects, horizon=horizon, global_duration=duration)
    ShockScenario(phase='active' if finished else 'normal', horizon_months=horizon, effects=finished)
    return [(e['type'], e['value'], e['start_month'], e.get('duration_months')) for e in finished], horizon, defaults, questions


@pytest.mark.parametrize('text,expected', [
    ('lost job', [('income_multiplier', .55, 1, 6)]),
    ('Customer got laid off', [('income_multiplier', .55, 1, 6)]),
    ('rent went up', [('household_bills_percent', 15., 1, 6)]),
    ('bills up 10%', [('household_bills_percent', 10., 1, 6)]),
    ('rent up $300 a month', [('household_bills_delta', 300., 1, 6)]),
    ('$2,000 car repair', [('one_off_cost', 2000., 0, None)]),
    ('car repair in 2 months costing $1,800', [('one_off_cost', 1800., 2, None)]),
    ('income falls to 55% for 6 months, bills rise 15%, and a $1,500 repair is due now',
     [('income_multiplier', .55, 1, 6), ('household_bills_percent', 15., 1, 6), ('one_off_cost', 1500., 0, None)]),
    ('got a $5k bonus', [('one_off_receipt', 5000., 0, None)]),
    ('pay cut 20%', [('income_multiplier', .8, 1, 6)]),
    ('hours cut so pay drops by $800 a month for 4 months', [('income_delta', -800., 1, 4)]),
    ('Customer lost their job. Rent is also going up by $250.50 per month.',
     [('income_multiplier', .55, 1, 6), ('household_bills_delta', 250.5, 1, 6)]),
])
def test_plain_text_shocks(text, expected):
    assert read(text)[0] == expected


def test_defaults_are_visible_and_unknown_amounts_stay_unknown():
    effects, _, defaults, questions = read('lost job')
    assert any('55%' in d for d in defaults)
    effects, _, defaults, questions = read('car broke down')
    assert effects == [('one_off_cost', None, 0, None)] and questions


def test_longer_stated_duration_extends_plan_period():
    effects, horizon, defaults, _ = read('income dropped by 30% for a year')
    assert effects == [('income_multiplier', .7, 1, 12)] and horizon == 12
