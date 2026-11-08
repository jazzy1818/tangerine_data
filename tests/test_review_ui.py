"""Dashboard must disclose dated scope and incomplete funding prominently."""
import json

import pytest

from plan_classification.schemas import MAX_SHOCK_EFFECTS
from test_crisis_ui import app, custom, metric


def test_delayed_income_shock_has_dated_warning_without_official_green_runway(app):
    custom(app,{'effects':[dict(type='income_multiplier',value=0.,start_month=3,duration_months=4)]})
    assert metric(app,'Dated first shortfall')=='Month 6 (end)'
    assert any('Month 1 reference' in m.value for m in app.markdown)
    assert not any('Official Shock Runway' in m.value for m in app.markdown)
    assert not any('runway-badge-safe' in m.value and 'Months</div>' in m.value for m in app.tabs[1].markdown)


def test_unknown_event_has_partial_headlines_and_unknown_G25(app):
    custom(app,{'effects':[dict(type='unspecified_event')]})
    assert not app.exception
    assert any('**G25:** unknown' in m.value for m in app.markdown)
    assert metric(app,'Quantified Cash Need (partial estimate)')
    assert not any(m.label=='Extra Starting Cash Needed' for m in app.metric)
    assert any('Full funding need: Not established' in c.value for c in app.caption)
    assert any('Goal held for review' in m.value for m in app.info)


@pytest.mark.parametrize('label',['Layoff (EI 55%)','Furnace Repair','Layoff + 15% Bills'])
def test_organizer_presets_keep_official_scope(app,label):
    next(b for b in app.button if label in b.label).click().run()
    assert not app.exception
    assert any('Official Shock Runway' in m.value for m in app.markdown)
    assert not any('Month 1 reference — dated scenario' in m.value for m in app.markdown)


def test_account_switch_clears_debt_draft_before_adding_effect(app):
    app.number_input(key='account_selector').set_value(20111).run()
    app.radio(key='classification_input_mode').set_value('Guided scenario editor').run()
    app.selectbox(key='classification_guided_type').set_value('debt_payment_delta').run()
    app.number_input(key='classification_guided_horizon').set_value(9)
    app.checkbox(key='classification_debt_supplied').check()
    app.selectbox(key='classification_debt_kind').set_value('deferral').run()
    app.checkbox(key='classification_debt_unresolved').uncheck().run()
    app.number_input(key='classification_guided_value_debt_payment_delta').set_value(-100.)
    app.number_input(key='classification_debt_payment').set_value(300.)
    app.text_input(key='classification_debt_source').set_value('Synthetic payment for account 20111')
    app.checkbox(key='classification_debt_included').check()
    app.number_input(key='classification_debt_repayment_month').set_value(5)
    app.number_input(key='classification_debt_repayment_amount').set_value(600.)
    app.text_input(key='classification_guided_effect_id').set_value('old-loan').run()

    app.number_input(key='account_selector').set_value(22812).run()
    assert not app.exception
    assert app.number_input(key='classification_guided_horizon').value == 9
    assert not app.checkbox(key='classification_debt_supplied').value
    assert app.selectbox(key='classification_debt_kind').value == 'payment_change'
    assert app.text_input(key='classification_guided_effect_id').value == ''
    app.checkbox(key='classification_debt_supplied').check().run()
    assert app.number_input(key='classification_debt_payment').value is None
    assert app.text_input(key='classification_debt_source').value == ''
    assert not app.checkbox(key='classification_debt_included').value
    app.selectbox(key='classification_debt_kind').set_value('deferral').run()
    assert app.checkbox(key='classification_debt_unresolved').value
    app.checkbox(key='classification_debt_unresolved').uncheck().run()
    assert app.number_input(key='classification_debt_repayment_amount').value is None
    assert app.number_input(key='classification_debt_repayment_month').value != 5

    app.checkbox(key='classification_debt_supplied').uncheck()
    app.selectbox(key='classification_debt_kind').set_value('payment_change').run()
    app.button(key='classification_guided_add').click().run()
    assert not app.exception
    effect, = app.session_state['classification_guided_effects']
    assert effect['obligation_account_id'] is None
    assert effect['obligation_source'] is None
    assert effect['obligation_payment'] is None
    assert effect['repayment_amount'] is None
    assert effect['value'] != -100.


def test_optional_judge_note_at_effect_limit_shows_recoverable_error(app):
    effects = [dict(type='one_off_cost', value=10., start_month=1, effect_id=f'cost-{index}')
               for index in range(MAX_SHOCK_EFFECTS)]
    custom(app, {'effects': effects})
    assert metric(app, 'Month 6 Closing Balance')

    app.text_input(key='judge_event').set_value('Unquantified scenario detail').run()
    assert not app.exception
    assert any('Remove an effect' in error.value for error in app.error)
    assert metric(app, 'Typical Monthly Money In (I)')
    assert metric(app, 'Quantified Cash Need (partial estimate)')

    app.text_area(key='classification_scenario_json').set_value(json.dumps({'effects': effects[:-1]})).run()
    assert not app.exception
    assert not app.error
    assert metric(app, 'Quantified Cash Need (partial estimate)')
