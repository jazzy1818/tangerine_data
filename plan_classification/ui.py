"""Small optional integration for the existing Streamlit shock tab."""
import json

import streamlit as st

from . import build_case, profile_from_engine, scenario_from_engine, select_plan
from .case import case_hash
from .config import classifier_settings
from .request_log import append_request, request_record
from .schemas import MAX_SHOCK_EFFECTS, MODULES, ONE_TIME, ShockEffect, ShockScenario


# Values are stored in the same explicit units as the shared scenario schema.
EFFECT_INPUTS = {
    'income_multiplier': ('Income level', 'Multiplier (0.55 = 55% of usual inflow)', .55, 0., .05),
    'income_delta': ('Recurring income change', 'Income change (CAD/month; negative means less)', -500., None, 100.),
    'expense_delta': ('Recurring spending change', 'Spending change (CAD/month; negative means less)', 250., None, 50.),
    'expense_percent': ('Percentage spending change', 'Spending change (%; 15 means +15%)', 15., -100., 1.),
    'household_bills_percent': ('Percentage household-bill change', 'Household-bill change (%; 15 means +15%)', 15., -100., 1.),
    'household_bills_delta': ('Household-bill amount change', 'Household-bill change (CAD/month)', 250., None, 50.),
    'debt_payment_delta': ('Loan-payment change', 'Loan-payment change (CAD/month)', 100., None, 50.),
    'one_off_cost': ('One-time expense', 'One-time expense (CAD)', 1000., 0., 100.),
    'one_off_receipt': ('One-time receipt / windfall', 'One-time receipt (CAD)', 1000., 0., 100.),
    'liquidity_hold': ('Temporarily inaccessible cash', 'Amount temporarily inaccessible (CAD)', 1000., 0., 100.),
    'payment_delay_days': ('Payment delay', 'Payment delay (days)', 7., 0., 1.),
    'investment_return': ('Investment-value change', 'Investment-value change (%; not bank cash)', -25., -100., 1.),
    'unspecified_event': ('Unknown financial effect', '', 0., None, 1.),
}


def _clear_classification_result():
    st.session_state.pop('classification_result', None)


def _render_request_history():
    st.markdown('**Classification request logs**')
    history = st.session_state.get('classification_request_history', [])
    st.caption('Last 100 requests in this browser session. Each row covers one classification, '
               'including any retry. A persistent copy is saved to logs/classification.jsonl. '
               'Keys, account IDs, balances, and scenario text are excluded.')
    if not history:
        st.info('No classification requests yet. Choose a classifier and click Classify scenario.')
        return
    columns = ('timestamp_utc', 'requested_backend', 'status', 'actual_backend',
               'lead_module', 'model_version', 'api_calls', 'elapsed_ms', 'fallback_reason',
               'validation_errors', 'total_tokens', 'cost_usd')
    st.dataframe([{name: row.get(name) for name in columns} for row in reversed(history)],
                 hide_index=True, use_container_width=True)
    st.caption('Blank token or cost values mean the provider did not report them.')
    st.download_button('Download request logs (JSONL)',
                       ''.join(json.dumps(row) + '\n' for row in history),
                       file_name='classification_requests.jsonl', mime='application/x-ndjson',
                       key='classification_log_download')


def _remove_guided_effect(index):
    effects = st.session_state.get('classification_guided_effects', [])
    if 0 <= index < len(effects):
        st.session_state['classification_guided_effects'] = effects[:index] + effects[index + 1:]
    _clear_classification_result()


def _clear_guided_effects():
    st.session_state['classification_guided_effects'] = []
    _clear_classification_result()


def _remember_guided_setting(name, widget_key):
    # Streamlit removes widget keys when switching input modes. Keep scenario
    # metadata separately so returning to the editor cannot silently reset it.
    settings = dict(st.session_state.get('classification_guided_settings', {}))
    settings[name] = st.session_state[widget_key]
    st.session_state['classification_guided_settings'] = settings
    _clear_classification_result()


def _render_guided_scenario(account_id=None):
    """Build a scenario with widgets; only explicitly added effects are classified."""
    if 'classification_guided_effects' not in st.session_state:
        st.session_state['classification_guided_effects'] = []
    st.caption('Add each financial effect, then classify the listed scenario. '
               'Amounts can stay unknown. Editing a listed effect means removing it and adding its replacement.')
    settings = st.session_state.get('classification_guided_settings', {})
    phase = st.selectbox('Scenario phase', ['active', 'recovery', 'normal'],
                         index=['active', 'recovery', 'normal'].index(settings.get('phase', 'active')),
                         format_func=lambda value: {'active': 'Active scenario', 'recovery': 'Recovery',
                                                    'normal': 'Normal / no new shock'}[value],
                         key='classification_guided_phase', on_change=_remember_guided_setting,
                         args=('phase', 'classification_guided_phase'))
    horizon = st.number_input('Classification horizon (months)', min_value=1, max_value=120,
                              value=settings.get('horizon', 6), key='classification_guided_horizon',
                              on_change=_remember_guided_setting,
                              args=('horizon', 'classification_guided_horizon'))
    description = st.text_input('Scenario note (kept locally)', value=settings.get('note', ''), max_chars=2000,
                                key='classification_guided_note', on_change=_remember_guided_setting,
                                args=('note', 'classification_guided_note'))
    kind = st.selectbox('Financial effect', list(EFFECT_INPUTS),
                        format_func=lambda value: EFFECT_INPUTS[value][0],
                        key='classification_guided_type', on_change=_clear_classification_result)
    _, label, default, minimum, step = EFFECT_INPUTS[kind]
    if kind == 'unspecified_event':
        value = None
        st.info('The financial effect is unknown; classification will retain a request for details.')
    else:
        unknown = st.checkbox('Amount / magnitude is unknown', key='classification_guided_value_unknown',
                               on_change=_clear_classification_result)
        amount = st.number_input(label, min_value=minimum, value=default, step=step, disabled=unknown,
                                  key=f'classification_guided_value_{kind}', on_change=_clear_classification_result)
        value = None if unknown else amount
    is_one_time = kind in ONE_TIME
    immediate = is_one_time or kind == 'liquidity_hold'
    start = st.number_input('Effect starts in month (0 = immediate expense, receipt or hold)',
                            min_value=0 if immediate else 1, max_value=120,
                            value=0 if immediate else 1,
                            key='classification_guided_start_hold' if kind == 'liquidity_hold' else 'classification_guided_start_oneoff' if is_one_time else 'classification_guided_start_recurring',
                            on_change=_clear_classification_result)
    duration, ongoing = None, False
    if not is_one_time and kind not in {'unspecified_event', 'investment_return'}:
        duration_mode = st.selectbox('How long does this effect last?',
                                     ['Unknown duration', 'Known duration', 'Ongoing (confirmed)'],
                                     key='classification_guided_duration_mode', on_change=_clear_classification_result)
        if duration_mode == 'Known duration':
            duration = st.number_input('Duration (months)', min_value=1, max_value=120, value=6,
                                        key='classification_guided_duration', on_change=_clear_classification_result)
        elif duration_mode == 'Ongoing (confirmed)':
            ongoing = True
        else:
            st.caption('The effect duration will remain unresolved; no end date is assumed.')
    evidence = st.selectbox('Source of this effect',
                            ['judge_specified', 'user_confirmed', 'assumed', 'unknown'],
                            format_func=lambda value: value.replace('_', ' ').capitalize(),
                            key='classification_guided_evidence', on_change=_clear_classification_result)
    obligation = {}
    if kind == 'debt_payment_delta':
        st.caption('A reduction is bounded by the specific recorded payment. Supply an override only when the scenario explicitly establishes the payment and its inclusion in spending.')
        if st.checkbox('Scenario supplies the existing payment amount', key='classification_debt_supplied'):
            obligation['obligation_account_id'] = account_id
            obligation['obligation_payment'] = st.number_input('Existing loan payment (CAD/month)', min_value=0., value=None, key='classification_debt_payment')
            obligation['obligation_source'] = st.text_input('Payment evidence source', key='classification_debt_source').strip() or None
            obligation['payment_in_baseline'] = st.checkbox('Payment explicitly included in baseline spending', key='classification_debt_included')
        change_kind = st.selectbox('Nature of loan payment change', ['payment_change', 'deferral'], key='classification_debt_kind')
        obligation['debt_change_kind'] = change_kind
        if change_kind == 'deferral':
            unresolved = st.checkbox('Repayment remains unresolved', value=True, key='classification_debt_unresolved')
            obligation['repayment_unresolved'] = unresolved
            if not unresolved:
                obligation['repayment_month'] = st.number_input('Deferred repayment month', min_value=1, max_value=240, value=7, key='classification_debt_repayment_month')
                obligation['repayment_amount'] = st.number_input('Full deferred repayment (CAD)', min_value=0., value=None, key='classification_debt_repayment_amount')
    identity = st.text_input('Effect / obligation ID (optional; local only)', key='classification_guided_effect_id',
                             help='Use the same ID for a repeated invoice, different IDs for distinct obligations.',
                             on_change=_clear_classification_result)
    if st.button('Add effect to scenario', key='classification_guided_add'):
        try:
            effect = ShockEffect(type=kind, value=value, start_month=start,
                                 duration_months=duration, ongoing=ongoing, evidence=evidence,
                                 effect_id=identity.strip() or None, **obligation)
            combined = [*st.session_state['classification_guided_effects'], effect.model_dump(mode='json')]
            checked = ShockScenario(effects=combined, phase=phase, horizon_months=horizon)
            st.session_state['classification_guided_effects'] = [e.model_dump(mode='json') for e in checked.effects]
            _clear_classification_result()
        except ValueError as exc:
            st.error(f'This effect was not added: {exc}')
    effects = st.session_state['classification_guided_effects']
    st.markdown('**Effects included in this scenario**')
    if not effects:
        st.caption('No effects added. Use Normal / no new shock only when that is intentional.')
    for index, effect in enumerate(effects):
        title, unit, *_ = EFFECT_INPUTS[effect['type']]
        amount_text = 'unknown magnitude' if effect['value'] is None else f"{effect['value']:g} — {unit}"
        timing = f"month {effect['start_month']}"
        if effect['type'] not in ONE_TIME and effect['type'] not in {'unspecified_event', 'investment_return'}:
            timing += (f", {effect['duration_months']} months" if effect.get('duration_months') else
                       ', ongoing' if effect.get('ongoing') else ', duration unknown')
        st.write(f"{index + 1}. {title}: {amount_text}; {timing}; {effect['evidence'].replace('_', ' ')}.")
        st.button(f'Remove effect {index + 1}', key=f'classification_guided_remove_{index}',
                  on_click=_remove_guided_effect, args=(index,))
    if effects:
        st.button('Clear all effects', key='classification_guided_clear', on_click=_clear_guided_effects)
    return ShockScenario(description=description, phase=phase, horizon_months=horizon, effects=effects)


def render_classification(customer, income_multiplier, bills_increase_pct, one_off_costs, event_evidence=None):
    with st.expander('Classify this scenario into one of the eight plan modules'):
        st.caption('Select a response family using Jev, Gemini, or the local baseline. '
                   'The selection is a proposal for the planning engine.')
        choice = st.selectbox('Classifier', ['Local baseline', 'Jev (OpenRouter)', 'Gemini'], key='classification_backend')
        backend = {'Local baseline': 'rules', 'Jev (OpenRouter)': 'jev', 'Gemini': 'gemini'}[choice]
        # Reserve the log area before validation so earlier runs remain visible
        # even while the operator is editing an incomplete scenario.
        history_area = st.container()
        mode = st.radio('Scenario source', ['Current shock controls', 'Guided scenario editor', 'Custom structured scenario'],
                        horizontal=True, key='classification_input_mode')
        try:
            scenario = scenario_from_engine(income_multiplier, bills_increase_pct, one_off_costs)
            if mode == 'Guided scenario editor':
                scenario = _render_guided_scenario(customer['account_id'])
            elif mode == 'Custom structured scenario':
                st.caption('Use financial effects for windfalls, debt changes, holds, delays, or combinations. '
                           'Percent values use percentage points (15 means 15%). Month 0 is immediate; '
                           'recurring effects start at month 1. Use value: null for an unknown amount.')
                raw = st.text_area('Scenario JSON', value=scenario.model_dump_json(indent=2), height=260,
                                   key='classification_scenario_json')
                scenario = ShockScenario.model_validate_json(raw)
            if (event_evidence and event_evidence.event_financial_effect == 'unspecified'
                and not any(e.type == 'unspecified_event' for e in scenario.effects)):
                if len(scenario.effects) >= MAX_SHOCK_EFFECTS:
                    raise ValueError(f'An unquantified judge event takes one of the {MAX_SHOCK_EFFECTS} effect slots. '
                                     'Remove an effect, or clear the optional event if it does not apply.')
                scenario = ShockScenario(phase='active' if scenario.phase == 'normal' else scenario.phase,
                    horizon_months=scenario.horizon_months, description=scenario.description,
                    effects=[*scenario.effects, ShockEffect(type='unspecified_event', evidence='unknown')])
        except ValueError as exc:
            st.error(f'Check the scenario inputs. {exc}')
            with history_area:
                _render_request_history()
            return {'scenario': None, 'selection_result': None, 'input_error': str(exc)}
        handoff = {'scenario': scenario, 'selection_result': None, 'input_error': None}
        key = None
        if backend != 'rules':
            try:
                settings = classifier_settings()
            except ValueError as exc:
                st.error(str(exc))
                with history_area:
                    _render_request_history()
                return handoff
            provider = 'OpenRouter' if backend == 'jev' else 'Gemini'
            variable = 'OPENROUTER_API_KEY' if backend == 'jev' else 'GEMINI_API_KEY'
            widget = 'classification_openrouter_key' if backend == 'jev' else 'classification_gemini_key'
            key = st.text_input(f'{provider} API key override (optional)', type='password', key=widget,
                                help='Leave blank to use the project .env file or process environment.')
            if key or settings.get(variable):
                st.caption(f'{provider} key configured. The API is called only when you click Classify scenario.')
            else:
                st.warning(f'Add {variable} to .env or enter it above to use {provider}.')
        profile = profile_from_engine(customer)
        try:
            case = build_case(profile, scenario)
            # Reject invalid financial inputs before a paid classification call;
            # the same executor is used by the actual backup plan.
            from scenario_execution import execute_scenario
            execute_scenario(customer, scenario)
        except ValueError as exc:
            st.error(str(exc))
            with history_area:
                _render_request_history()
            return {'scenario': None, 'selection_result': None, 'input_error': str(exc)}
        st.caption('API classifiers receive derived ratios and structured effects. '
                   'Account IDs, exact balances, demographics, histories, and narrative text are excluded.')
        if st.checkbox('Inspect classifier inputs', key='classification_inspect'):
            st.json(case.model_dump(mode='json'))
        if case.missing_details:
            st.warning('Some scenario details are unresolved; any classification is provisional.')
        fingerprint = (customer['account_id'], case_hash(case), backend)
        if st.button('Classify scenario', key='classification_run'):
            with st.spinner('Selecting a plan module…'):
                result = select_plan(case, backend, **({'api_key': key} if backend != 'rules' else {}))
            st.session_state['classification_result'] = (fingerprint, result.model_dump(mode='json'))
            record = request_record(result)
            history = st.session_state.get('classification_request_history', [])
            st.session_state['classification_request_history'] = [*history, record][-100:]
            try:
                append_request(record)
            except OSError:
                st.warning('The request is visible in this session, but its log could not be saved to disk.')
        saved = st.session_state.get('classification_result')
        if saved and saved[0] == fingerprint:
            result = saved[1]
            handoff['selection_result'] = result
            selection = result['selection']
            if result['fallback_used']:
                st.warning(f"{choice} unavailable ({result['fallback_reason']}). Showing the local baseline.")
            st.write(f"**{selection['lead_module']} — {MODULES[selection['lead_module']]}**")
            if selection['support_modules']:
                st.write('Supporting modules: ' + ', '.join(selection['support_modules']))
            st.write(selection['rationale'])
            for question in selection['needs_clarification']:
                st.info('Bank analyst review: ' + question)
            st.caption(f"Source: {result['actual_backend']} · {result['elapsed_ms']:.0f} ms · "
                       f"API calls: {result['api_calls']}")
            if result['provider_confidence'] is not None:
                st.caption(f"Provider confidence: {result['provider_confidence']:.3f}. "
                           'This is not a probability of financial success.')
            st.download_button('Download classification JSON', json.dumps(result, indent=2),
                               file_name='plan_selection.json', mime='application/json',
                               key='classification_download')
        with history_area:
            _render_request_history()
        return handoff
