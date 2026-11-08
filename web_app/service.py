"""One website request -> one canonical case -> existing guarded planning engine."""
import json
import logging

import engine
from action_plan import build_action_plan
from backup_comparison import build_comparison, safe_mode_status
from plan_classification import build_case, profile_from_engine, select_plan
from plan_classification.case import case_hash
from plan_classification.request_log import append_request, request_record
from scenario_execution import execute_scenario

from . import store
from .analytics import records

logger = logging.getLogger('tangerine.website')


def customer_view(customer):
    profile = profile_from_engine(customer)
    return {'account_id': customer['account_id'],
            'metrics': {key: customer[key] for key in ('I', 'S', 'F', 'H', 'B', 'P', 'baseline_gap', 'baseline_runway')},
            'loan_status': customer['loan_status_meaning'], 'source_loan_status': customer['source_loan_status'],
            'profile': profile.model_dump(mode='json'),
            'history': records(customer['history'][['month', 'money_in', 'money_out', 'avg_daily_balance',
                'month_end_balance', 'household_bills', 'insurance', 'loan_payments', 'days_below_zero']]),
            'basis': 'Official full-history medians; buffer is the average of the last six monthly average balances.'}


def preview(request):
    customer = engine.know_customer(request.account_id)
    profile = profile_from_engine(customer)
    case = build_case(profile, request.scenario, planning_cash=request.opening_cash)
    path = execute_scenario(customer, request.scenario, opening_cash=request.opening_cash)
    # Validate action evidence before accepting a paid request, even for previews.
    if request.recovery_snapshot and request.recovery_snapshot.account_id not in (None, request.account_id):
        raise ValueError('Recovery checkpoint belongs to a different account.')
    if len({t.event_id for t in request.existing_transfers}) != len(request.existing_transfers):
        raise ValueError('Each scheduled transfer needs a unique event_id.')
    notes = []
    if profile.features.loan_in_arrears:
        notes.append('Loan arrears are recorded before these changes. Confirm the current payment position with the customer.')
    for effect in case.effects:
        if effect.value not in (None, 0, 1 if effect.type == 'income_multiplier' else 0) and effect.cashflow_delta_to_scale == 0:
            notes.append('This percentage change has no cash impact because no amount is recorded for the affected category. Confirm the actual amount with the customer.')
    if request.scenario.description:
        notes.append('The description is context only. Only the listed structured effects change the calculations; add an unknown event when its financial impact is unquantified.')
    return {'customer': customer_view(customer), 'scenario': request.scenario.model_dump(mode='json'),
            'reference': engine.scenario_reference(customer, request.scenario),
            'case': case.model_dump(mode='json'), 'input_hash': case_hash(case),
            'projection': path, 'notes': list(dict.fromkeys(notes))}


def execute_run(session_id, request):
    run_id = str(request.request_id)
    try:
        customer = engine.know_customer(request.account_id)
        evidence = preview(request)
        kwargs = dict(shock=engine.take_shock(customer), scenario=request.scenario,
                      opening_cash=request.opening_cash, normal_goal=request.normal_goal,
                      existing_transfers=request.existing_transfers, recovery_snapshot=request.recovery_snapshot)
        # Keep all existing runtime guards and check the full plan before a paid API call.
        plans = engine.make_plan(customer, **kwargs)
        if plans['crisis_plan'].get('runtime_validation', {}).get('status') != 'passed':
            raise ValueError('The financial engine requires review. No classifier API call was made.')
        build_comparison(plans['crisis_plan'])
        case = build_case(profile_from_engine(customer), request.scenario, planning_cash=request.opening_cash)
        selected = select_plan(case, request.backend)
        record = request_record(selected)
        log_warning = None
        try:
            append_request(record)
        except OSError:
            log_warning = 'The text request log could not be appended; request metadata remains in this saved result.'
        plans = engine.make_plan(customer, selection_result=selected, **kwargs)
        # Finance-owned action plan (policy v1.1): reads the validated ledgers only.
        plans['action_plan'] = build_action_plan(customer, plans['crisis_plan'], scenario=request.scenario,
                                                 goal_plan=plans.get('goal_plan'), opening_cash=request.opening_cash)
        comparison = build_comparison(plans['crisis_plan'])
        status, reason = safe_mode_status(plans['crisis_plan'], comparison)
        comparison['planning_status'] = {'label': status, 'reason': reason}
        # Normalize NumPy scalars using the same JSON-safe encoding as the HTTP layer.
        from fastapi.encoders import jsonable_encoder
        import numpy as np
        result = jsonable_encoder({**evidence, 'classification': selected.model_dump(mode='json'),
                                   'plans': plans, 'cash_comparison': comparison,
                                   'request_log': record, 'log_warning': log_warning},
                                  custom_encoder={np.int64: int, np.float64: float, np.bool_: bool})
        json.dumps(result, allow_nan=False)
        store.finish(session_id, run_id, result=result)
        logger.info('run=%s status=complete provider=%s calls=%s', run_id, selected.actual_backend, selected.api_calls)
    except ValueError as error:
        # Domain validation messages contain no credentials or provider response bodies.
        store.finish(session_id, run_id, error=str(error))
        logger.warning('run=%s status=failed type=%s', run_id, type(error).__name__)
    except Exception as error:
        store.finish(session_id, run_id, error='Analysis could not finish. Check the terminal and request log before retrying an API run.')
        logger.error('run=%s status=failed type=%s', run_id, type(error).__name__)
