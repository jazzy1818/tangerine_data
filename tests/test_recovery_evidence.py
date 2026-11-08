"""A supported recovery contribution need not invent a monthly income."""
import pytest
from pydantic import ValidationError

from recovery_plan import make_recovery_plan


def pdf_checkpoint(**changes):
    return dict(source='Team execution PDF, Phase 1 Case D, page 3',
                assessment_month='2026-11', cash_basis='judge_specified',
                available_cash=3000., monthly_spending=2400.,
                stable_cash_flow=True, obligations_covered=True,
                supported_monthly_contribution=300., **changes)


def test_pdf_supported_contribution_without_inventing_income():
    result = make_recovery_plan(pdf_checkpoint())
    assert result['reserve_target'] == 7200.
    assert result['reserve_gap'] == 4200.
    assert result['monthly_contribution'] == 300.
    assert result['months_to_target'] == 14
    assert result['monthly_surplus'] is None
    assert any(flag.startswith('INFLOW_UNQUANTIFIED:') for flag in result['review_flags'])


@pytest.mark.parametrize('bound', [None, 0., .004])
def test_no_date_without_a_positive_posted_contribution(bound):
    result = make_recovery_plan({**pdf_checkpoint(), 'supported_monthly_contribution': bound})
    assert result['months_to_target'] is None
    assert result['monthly_surplus'] is None
    assert result['monthly_contribution'] == 0.


@pytest.mark.parametrize('updates', [
    {'stable_cash_flow': False}, {'obligations_covered': False},
    {'available_cash': -1.}, {'earmarked_near_term_cash': 3001.},
    {'monthly_inflow': 2200.},
])
def test_supported_bound_cannot_override_adverse_evidence(updates):
    result = make_recovery_plan({**pdf_checkpoint(), **updates})
    assert result['status'] == 'ACTIVE_CRISIS'
    assert result['monthly_contribution'] == 0.
    assert result['months_to_target'] is None


def test_known_surplus_still_caps_supported_contribution():
    result = make_recovery_plan(pdf_checkpoint(monthly_inflow=2500.))
    assert result['monthly_surplus'] == 100.
    assert result['monthly_contribution'] == 100.
    assert result['months_to_target'] == 42


def test_surplus_alone_does_not_supply_contribution_support():
    result = make_recovery_plan({**pdf_checkpoint(monthly_inflow=3000.),
                                 'supported_monthly_contribution': None})
    assert result['months_to_target'] is None


@pytest.mark.parametrize('field', ['source', 'stable_cash_flow', 'obligations_covered'])
def test_required_evidence_cannot_be_omitted(field):
    supplied = pdf_checkpoint()
    supplied.pop(field)
    with pytest.raises(ValidationError):
        make_recovery_plan(supplied)


def test_crisis_plan_accepts_pdf_recovery_without_altering_crisis_cash():
    import engine
    from crisis_response import make_crisis_plan
    from plan_classification.schemas import ShockScenario

    customer = engine.know_customer(22812)
    normal = dict(name='Reserve', monthly_contribution=0., reserve_target=7200.)
    baseline = make_crisis_plan(customer, ShockScenario(phase='normal'), normal_goal=normal)
    recovery = make_crisis_plan(customer, ShockScenario(phase='normal'), normal_goal=normal,
                                recovery_snapshot=pdf_checkpoint())
    assert recovery['runtime_validation']['status'] == 'passed'
    assert recovery['recovery']['months_to_target'] == 14
    assert recovery['no_action'] == baseline['no_action']
