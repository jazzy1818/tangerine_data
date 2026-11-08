"""Regressions for financial input completeness and discovery edge cases."""
import json

import pandas as pd
import pytest

import engine
from plan_classification import build_case, ShockScenario
from plan_classification.case import canonical_json, scenario_from_engine
from plan_classification.discovery import generate_report
from plan_classification.features import profile_from_engine, profile_from_history, validate_monthly


def history(*, household=100., insurance=1200., first_month='2025-01', account_id=17):
    return pd.DataFrame({
        'account_id': [account_id]*12,
        'month': pd.period_range(first_month, periods=12, freq='M').astype(str),
        'money_in': [4000.]*12, 'money_out': [3200.]*12,
        'household_bills': [household]*12, 'insurance': [insurance]*12,
        'loan_payments': [0.]*12, 'avg_daily_balance': [4000.]*12,
        'month_end_balance': [4000.]*12, 'min_balance': [1000.]*12,
        'days_below_zero': [0]*12,
    })


@pytest.fixture
def profile():
    return profile_from_history(17, history(), as_of='2025-12')


def test_future_household_cost_magnitude_survives_normalization():
    small = profile_from_history(17, history(), as_of='2025-12')
    large = profile_from_history(17, history(household=1200., insurance=100.), as_of='2025-12')
    assert small.features == large.features
    scenario = ShockScenario(effects=[{
        'type': 'household_bills_percent', 'value': 100, 'start_month': 2, 'ongoing': True,
    }])
    small_case, large_case = build_case(small, scenario), build_case(large, scenario)
    assert small_case.first_period_gap_to_scale == large_case.first_period_gap_to_scale
    assert small_case.effects[0].cashflow_delta_to_scale == -.025
    assert large_case.effects[0].cashflow_delta_to_scale == -.3
    assert canonical_json(small_case) != canonical_json(large_case)


@pytest.mark.parametrize('effect,expected', [
    ({'type': 'income_multiplier', 'value': .55, 'duration_months': 6}, -.45),
    ({'type': 'income_delta', 'value': 400, 'ongoing': True}, .1),
    ({'type': 'expense_delta', 'value': 200, 'ongoing': True}, -.05),
    ({'type': 'expense_percent', 'value': 10, 'ongoing': True}, -.08),
    ({'type': 'household_bills_delta', 'value': 200, 'ongoing': True}, -.05),
    ({'type': 'household_bills_percent', 'value': 20, 'ongoing': True}, -.005),
    ({'type': 'debt_payment_delta', 'value': 100, 'ongoing': True}, -.025),
    ({'type': 'one_off_cost', 'value': 1000, 'start_month': 0}, -.25),
    ({'type': 'one_off_receipt', 'value': 1000, 'start_month': 0}, .25),
    ({'type': 'liquidity_hold', 'value': 1000, 'duration_months': 2}, None),
    ({'type': 'investment_return', 'value': 20}, None),
    ({'type': 'payment_delay_days', 'value': 10, 'duration_months': 1}, None),
    ({'type': 'income_delta', 'value': 400, 'ongoing': True, 'evidence': 'unknown'}, None),
])
def test_signed_cashflow_effects_and_unknowns(profile, effect, expected):
    value = build_case(profile, ShockScenario(effects=[effect])).effects[0].cashflow_delta_to_scale
    if expected is None:
        assert value is None
    else:
        assert value == pytest.approx(expected)


def test_duration_must_be_declared_or_asked(profile):
    uncertain = build_case(profile, ShockScenario(effects=[{'type': 'income_delta', 'value': -500}]))
    assert any('duration' in question for question in uncertain.missing_details)
    known = build_case(profile, ShockScenario(effects=[{'type': 'income_delta', 'value': -500, 'ongoing': True}]))
    assert not known.missing_details
    assert known.effects[0].ongoing
    unknown_value = build_case(profile, ShockScenario(effects=[{'type': 'income_delta', 'value': None}]))
    assert any('duration' in question for question in unknown_value.missing_details)
    assert any('financial value' in question for question in unknown_value.missing_details)


def test_neutral_effect_does_not_ask_meaningless_duration(profile):
    case = build_case(profile, ShockScenario(effects=[{'type': 'income_multiplier', 'value': 1}]))
    assert not case.missing_details


def test_existing_engine_scenario_declares_duration(profile):
    case = build_case(profile, scenario_from_engine(.55, .15, 0))
    assert not case.missing_details
    assert case.effects[0].duration_months == 6
    assert case.effects[1].ongoing


def test_repeated_asset_clarification_is_deduplicated(profile):
    case = build_case(profile, ShockScenario(effects=[
        {'type': 'investment_return', 'value': -10, 'duration_months': 1},
        {'type': 'investment_return', 'value': -20, 'start_month': 2, 'duration_months': 1},
    ]))
    assert len(case.missing_details) == 1


@pytest.mark.parametrize('month,days,valid', [('2025-02',29,False),('2024-02',29,True),('2025-04',31,False)])
def test_negative_days_respect_calendar(month,days,valid):
    frame = history(first_month=month).iloc[:1].copy()
    frame['days_below_zero'] = days
    if valid:
        assert len(validate_monthly(frame)) == 1
    else:
        with pytest.raises(ValueError, match='days_below_zero'):
            validate_monthly(frame)


def test_day_validation_allows_duplicate_dataframe_index_labels():
    frame = history().iloc[:2].copy()
    frame.index = [0,0]
    assert len(validate_monthly(frame)) == 2


def test_engine_adapter_rejects_conflicting_raw_baseline():
    customer = engine.know_customer(22812)
    customer['raw_I'] += 1
    with pytest.raises(ValueError, match='disagrees'):
        profile_from_engine(customer)


def test_engine_adapter_rejects_nonfinite_payment():
    customer = engine.know_customer(22812)
    customer['raw_P'] = float('nan')
    with pytest.raises(ValueError):
        profile_from_engine(customer)


def test_report_handles_missing_optional_fields_and_zero_spending(tmp_path, monkeypatch):
    import plan_classification.discovery as discovery
    monkeypatch.setattr(discovery, '_plot', lambda *args: None)
    data = tmp_path/'data'
    data.mkdir()
    frame = history().drop(columns=['days_below_zero', 'month_end_balance', 'min_balance'])
    frame[['money_out','household_bills','insurance']] = 0.
    frame.to_csv(data/'monthly_summary.csv', index=False)
    findings = generate_report(data, tmp_path/'report')
    assert findings['cash_withdrawal_share_of_all_outflow'] is None
    assert findings['negative_balance_months_recovered_by_month_end'] == {'numerator':0,'denominator':0}
    encoded = (tmp_path/'report'/'findings.json').read_text()
    assert 'NaN' not in encoded
    assert json.loads(encoded)['cash_withdrawal_share_of_all_outflow'] is None
    report = (tmp_path/'report'/'discovery_report.md').read_text()
    assert '12 excluded for missing data' in report
    assert pd.read_csv(tmp_path/'report'/'matched_accounts.csv').empty


def test_report_excludes_missing_closing_balance_from_recovery_denominator(tmp_path, monkeypatch):
    import plan_classification.discovery as discovery
    monkeypatch.setattr(discovery, '_plot', lambda *args: None)
    data = tmp_path/'data'
    data.mkdir()
    frame = history()
    frame.loc[:1, 'days_below_zero'] = 2
    frame.loc[0, 'month_end_balance'] = float('nan')
    frame['cash_withdrawals_genuine'] = 100.
    frame.to_csv(data/'monthly_summary.csv', index=False)
    findings = generate_report(data, tmp_path/'report')
    assert findings['negative_balance_months_recovered_by_month_end'] == {'numerator':1,'denominator':1}
