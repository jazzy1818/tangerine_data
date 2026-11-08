"""Evidence-bound advice. Every sentence is generated from validated cash paths.

Gemini may select emphasis from approved sentence IDs. It cannot supply prose,
amounts, products, or actions. This restriction is enforced on every response.
"""
import hashlib
import json
from pydantic import BaseModel, ConfigDict
from plan_classification.config import resolve_provider


def _cad(value):
    return f'CAD {value:,.2f}'


def _shortfall(path):
    m = path['first_shortfall_month']
    return 'none at the modeled checkpoints' if m is None else f"Month {m} ({path['first_shortfall_phase']})"


def build_advice(plan):
    if plan.get('runtime_validation', {}).get('status') != 'passed':
        raise ValueError('Advice requires a validated crisis plan')
    base, revised = plan['no_action'], plan['applied_plan']
    cards = {}
    cards['diagnosis'] = (f"For this scenario, opening cash is {_cad(base['opening_cash'])} "
        f"({base['opening_basis']}). First shortfall: {_shortfall(base)}. "
        f"Extra starting cash needed for quantified components across {base['horizon_months']} months: {_cad(base['additional_cash_needed'])}.")
    first = base['schedule'][1]
    income = 'not established' if first['income'] is None else _cad(first['income'])
    cards['cash_flow'] = (f"Month 1 inflow: {income}; spending: {_cad(first['spending'])}. "
        'Later months follow the supplied effect dates and durations in the ledger.')
    events = [f"Month {row['month']}: receipt {_cad(row['one_off_receipt'])}, cost {_cad(row['one_off_cost'])}"
              for row in base['schedule'] if row['one_off_receipt'] or row['one_off_cost']]
    if events:
        cards['dated_events'] = '; '.join(events) + '. Later receipts cannot fund earlier shortfalls.'
    n = plan['goal_contribution_before']; r = plan['goal_contribution_revised']
    cards['goal'] = (f"The prior goal amount is {_cad(n)}/month; the supported revised amount is {_cad(r)}/month "
        f"({plan['goal_before_crisis']['kind']}). Goal status: {plan['goal_status']}. "
        'Pausing a future proposal adds CAD 0.00 to existing cash; reserve earmarks remain liquid.')
    if plan['applied_transfer_ids']:
        selected = [t for t in plan['existing_transfers'] if t['event_id'] in plan['applied_transfer_ids']]
        gross = sum(t['amount'] for t in selected); fees = sum(t['pause_fee'] for t in selected)
        cards['pause'] = (f"Model the supplied approved pauses for {len(selected)} scheduled payments already included in spending. "
            f"Avoided payments: {_cad(gross)}; fees: {_cad(fees)}; net cash retained: {_cad(gross-fees)}. "
            'This is a modeled plan; no banking instruction has been executed.')
    else:
        cards['pause'] = 'No existing-transfer pause is applied: no supplied schedule passes the evidence and financial-benefit checks for a stated funding, timing or reserve purpose.'
    if plan['pause_decisions']:
        cards['pause_decisions'] = '; '.join(f"{d['event_id']}: {d['status']} ({d['reason']})" for d in plan['pause_decisions']) + '.'
    if plan['G25'] is None:
        cards['goal_review'] = 'Goal held for review: the unknown financial impact does not establish G25 deterioration. The full funding need remains unestablished.'
    cards['outcome'] = (f"Under the revised plan, first shortfall: {_shortfall(revised)}; "
        f"extra starting cash needed for quantified components: {_cad(revised['additional_cash_needed'])}; "
        f"closing cash: {_cad(revised['ending_cash'])}. "
        f"Funding-need improvement against no new action: {_cad(base['additional_cash_needed']-revised['additional_cash_needed'])}.")
    if plan['required_monthly_improvement'] is not None and base['additional_cash_needed'] > 0:
        cards['funding_target'] = (f"Before applying actions, the calculated funding target is {_cad(plan['immediate_cash_target'])} upfront "
            f"plus {_cad(plan['required_monthly_improvement'])} per month. "
            'This is a required improvement, not evidence that spending can be reduced by that amount. '
            'Any supplied reduction must have dates and amounts and be replayed before its benefit is claimed.')
    if revised['additional_cash_needed'] > 0:
        cards['gap'] = (f"A funding gap of {_cad(revised['additional_cash_needed'])} remains over this horizon. "
            'Prioritize the obligations at the first shortfall and review evidenced funding or spending changes. '
            'The available data does not establish reducible spending, credit eligibility, insurance proceeds or a specific bank product.')
    else:
        cards['gap'] = 'The revised quantified path is nonnegative at its monthly checkpoints; this does not establish daily solvency or investment suitability.'
    if not revised['funding_result_complete']:
        cards['incomplete'] = 'Projection incomplete: these amounts cover quantified components only. A complete funding requirement is not established.'
    timing = plan.get('timing_comparison')
    if timing is not None and timing['funding_gap_improvement'] > 0:
        before, after = timing['no_action'], timing['conditional_bill_move']
        cards['bill_timing'] = (f"Separate conditional daily replay: moving the candidate bill reduces extra starting-cash need "
            f"from {_cad(before['extra_cash_needed'])} to {_cad(after['extra_cash_needed'])}. "
            'Biller approval, effective dates and fees remain unverified. This benefit is not applied to the monthly plan; '
            'the daily replay uses its own stated historical cash-flow basis and does not resolve an ongoing monthly deficit.')
    recovery = plan['recovery']
    if recovery.get('reserve_gap') is not None:
        eta = recovery['months_to_target']
        cards['recovery'] = (f"Separate supplied recovery checkpoint: {recovery['status']}; reserve gap {_cad(recovery['reserve_gap'])}; "
            f"supported rebuild {_cad(recovery['monthly_contribution'])}/month. "
            + (f'Conditional rebuild timeline: {eta} months.' if eta is not None else 'Rebuild timeline is not established.'))
    else:
        cards['recovery'] = 'Recovery is not established. Updated cash, inflows, spending, stability and obligation coverage are required before setting a rebuild date.'
    # Reviews remain mandatory in the UI even when Gemini chooses other emphasis.
    result = {'cards': cards, 'review_flags': plan['review_flags'],
              'transfer_sources': [{'event_id': t['event_id'], 'source': t['source']} for t in plan['existing_transfers']],
              'runtime_validation': {'status': 'passed', 'policy': 'grounded-advice-v1'}}
    result['fingerprint'] = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()
    return result


def validate_advice(advice, plan):
    if advice != build_advice(plan):
        raise ValueError('Advice differs from the validated financial evidence')
    return advice


class Emphasis(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    focus_ids: list[str]


def explain_plan(plan, *, backend='local', client=None, api_key=None, model=None):
    advice = validate_advice(plan['advice'], plan)
    cards = advice['cards']
    result = {'actual_backend': 'local', 'requested_backend': backend, 'fallback_reason': None,
              'fingerprint': advice['fingerprint'], 'focus_ids': [], 'cards': cards, 'api_calls':0}
    if backend == 'local':
        return result
    if backend != 'gemini':
        raise ValueError('Unknown explanation backend')
    try:key,model=resolve_provider('explanation',api_key=api_key,model=model)
    except ValueError:return {**result,'fallback_reason':'invalid_provider_settings'}
    if client is None and not key:
        return {**result, 'fallback_reason': 'credentials_unavailable'}
    calls=0
    try:
        from google import genai
        from google.genai import types
        owned = client is None
        if owned:
            client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=5000,
                retry_options=types.HttpRetryOptions(attempts=1)))
        # Account IDs, narratives, source strings and exact CAD never leave here.
        context = {'allowed_ids': list(cards), 'goal_status': plan['goal_status'],
            'has_supported_pause': bool(plan['applied_transfer_ids']),
            'has_remaining_gap': plan['applied_plan']['additional_cash_needed'] > 0,
            'projection_complete': plan['applied_plan']['funding_result_complete'],
            'recovery_status': plan['recovery']['status'], 'effective_module': plan['lead_module']}
        try:
            calls += 1
            response = client.models.generate_content(model=model,
                contents='Choose up to three allowed_ids to emphasize for this analyst. Return focus_ids only. '+json.dumps(context),
                config=types.GenerateContentConfig(response_mime_type='application/json', response_json_schema={'type':'object','properties':{'focus_ids':{'type':'array',
                        'items':{'type':'string','enum':list(cards)},'maxItems':3}},
                        'required':['focus_ids'],'additionalProperties':False}, **({'temperature':0} if model.startswith('gemini-2.') else {})))
            focus = Emphasis.model_validate_json(response.text).focus_ids
            if len(focus) > 3 or len(set(focus)) != len(focus) or any(i not in cards for i in focus):
                raise ValueError('Unapproved explanation content')
        finally:
            if owned:
                client.close()
        return {**result, 'actual_backend': 'gemini', 'focus_ids': focus, 'api_calls':calls}
    except Exception:
        return {**result, 'fallback_reason': 'provider_or_validation_failure', 'api_calls':calls}
