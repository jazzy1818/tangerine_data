"""Jev (OpenRouter), Gemini (official SDK), and an explicitly separate offline baseline."""
import json
import math
import re
from time import perf_counter

import requests
from pydantic import ValidationError

from .case import canonical_json, case_hash
from .config import resolve_provider, PROVIDER_ROUTES
from .schemas import (ClassificationCase, MODULES, MODULE_DESCRIPTIONS,
                      PlanSelection, SelectionResult)

VERSION = '1.3.0'
PROMPT_VERSION = 'module-selection-1.2'
GEMINI_PROMPT_VERSION = 'module-selection-gemini-1.3'
JEV_ENDPOINT = 'https://openrouter.ai/api/v1/systemone'
POLICY = """Select the lead financial response family from the allowed modules using the supplied case.
Classify the financial problem, not the person's income bracket. Several interacting adverse
problems can need M5 with supporting modules; merely having two effects does not require M5.
M7 concerns timing/access; M6 concerns reserve restoration; M8 covers positive opportunities,
with obligations and accessible reserves considered first. Choose at most two supporting modules.
All currency effects are divided by the same hidden cash_scale = max(typical inflow, spending, 1).
Percent effects are percentage points; ratios are dimensionless. Missing values are unknown.
cashflow_delta_to_scale is the effect's signed cash-flow impact divided by cash_scale:
positive improves cash flow, negative worsens it; null means it cannot be quantified as cash.
First-period screening does not model benefit expiry, later effects, or daily cash timing.
features.reserve_months remains historical. When planning_cash_basis is supplied_scenario,
immediate_buffer_to_scale instead uses explicitly supplied scenario cash after immediate effects.
Historical overdraft recovery suggests a timing problem, not proof of its cause.
No fabricated benefits, cuts, funds, approvals, assets, or investment returns. Select modules only;
the separate finance engine will size and validate actions. Preserve unresolved input questions.
Reasons must come from observed_reasons. Do not invent dollar amounts or claim financial success.
"""


class _SelectionValidationError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def validate_selection(selection: PlanSelection, case: ClassificationCase) -> PlanSelection:
    selected = [selection.lead_module, *selection.support_modules]
    if not set(selected) <= set(case.constraints.allowed_modules):
        raise _SelectionValidationError('unsupported_modules', 'A selected module is not allowed.')
    if not set(selection.reason_codes) <= set(case.observed_reasons):
        raise _SelectionValidationError('unsupported_reason_codes', 'A reason is unsupported by the supplied facts.')
    # Preserve unresolved facts regardless of a remote model omitting them.
    questions = list(dict.fromkeys(case.missing_details + selection.needs_clarification))
    return PlanSelection(**{**selection.model_dump(), 'needs_clarification': questions})


def rule_baseline(case: ClassificationCase) -> PlanSelection:
    """Versioned demo fallback, not Jev, training labels, or the team's action engine."""
    r = set(case.observed_reasons)
    candidates = []
    adverse = []
    for reason, module in [('income_reduction', 'M1'), ('cost_increase', 'M2'),
                           ('one_off_expense', 'M3'), ('debt_payment_change', 'M4'),
                           ('timing_or_access', 'M7')]:
        if reason in r and (reason != 'debt_payment_change' or any(
            e.type == 'debt_payment_delta' and e.value is not None and e.value > 0
            and e.evidence != 'unknown' for e in case.effects)):
            adverse.append(module)
    if 'immediate_liquidity_pressure' in r:
        candidates.append('M3')
    if 'essential_obligations_at_risk' in r:
        candidates.append('M4')
    if len(adverse) >= 2:
        candidates.append('M5')
    candidates.extend(adverse)
    if r & {'income_increase', 'windfall', 'cost_reduction'}:
        candidates.append('M8')
    if 'recurring_shortfall' in r:
        candidates.append('M2')
    if 'historical_timing_stress' in r:
        candidates.append('M7')
    if r & {'recovery', 'reserve_below_target', 'missing_details'}:
        candidates.append('M6')
    candidates.extend(['M8' if 'surplus_available' in r else 'M6', *case.constraints.allowed_modules])
    allowed = case.constraints.allowed_modules
    ranked = list(dict.fromkeys(m for m in candidates if m in allowed))
    lead = ranked[0]
    # Only support directly indicated problems; never pad with arbitrary allowed modules.
    support = list(dict.fromkeys([*adverse, *(['M6'] if 'reserve_below_target' in r else [])]))
    support = [m for m in support if m != lead and m in allowed][:2]
    questions = list(dict.fromkeys(case.missing_details))
    if 'restricted_modules' in r and not any(m in allowed for m in adverse) and adverse:
        questions.append('Review module restrictions: the directly indicated response families are unavailable.')
    return validate_selection(PlanSelection(
        lead_module=lead, support_modules=support, reason_codes=case.observed_reasons,
        needs_clarification=questions,
        rationale=f'Local baseline proposes {MODULES[lead]}. Observed signals: ' +
                  ', '.join(s.replace('_', ' ') for s in case.observed_reasons) + '.',
    ), case)


def _result(case, backend, started, selection=None, failure=None, **metadata):
    return SelectionResult(
        selection=selection if selection is not None else rule_baseline(case),
        requested_backend=backend,
        actual_backend='rule_baseline' if failure or backend == 'rules' else backend,
        fallback_used=bool(failure), fallback_reason=failure,
        implementation_version=VERSION, input_hash=case_hash(case),
        elapsed_ms=(perf_counter()-started)*1000, **metadata,
    )


def _probability(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError('Invalid probability.')
    return float(value)


def _choice(answer, options):
    if answer['type'] != 'choice' or answer['choice'] not in options:
        raise ValueError('Invalid choice.')
    probabilities = answer['probabilities']
    if set(probabilities) != set(options):
        raise ValueError('Incomplete probability distribution.')
    probabilities = {k: _probability(v) for k, v in probabilities.items()}
    if not math.isclose(sum(probabilities.values()), 1.0, abs_tol=0.01):
        raise ValueError('Probabilities do not sum to one.')
    if probabilities[answer['choice']] + 1e-6 < max(probabilities.values()):
        raise ValueError('Choice does not match the probability distribution.')
    return answer['choice'], _probability(answer['confidence']), probabilities


class _Usage:
    """Sum provider-reported usage across attempts; unknown never means zero."""
    def __init__(self):
        self.values = {k: None for k in (
            'input_tokens', 'output_tokens', 'thought_tokens', 'total_tokens', 'cost_usd')}
        self.complete = True

    def record(self, values, required):
        for key in self.values:
            value = values.get(key)
            valid = (isinstance(value, (int, float)) and not isinstance(value, bool)
                     and math.isfinite(value) and value >= 0)
            if key != 'cost_usd':
                valid = valid and isinstance(value, int)
            if valid:
                self.values[key] = (self.values[key] or 0) + value
            elif key in required:
                self.complete = False

    def metadata(self):
        return {**self.values, 'usage_complete': self.complete}


def _resolved_model(value, requested):
    if value is None:
        return requested
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:/+@-]{0,199}',value):
        raise ValueError('Invalid response model identifier.')
    return value.strip()


def _jev_usage(data):
    usage = data.get('usage') if isinstance(data, dict) else None
    usage = usage if isinstance(usage, dict) else {}
    counts = {'input_tokens': usage.get('input_tokens'),
              'output_tokens': usage.get('output_tokens'), 'cost_usd': usage.get('cost')}
    if all(isinstance(counts[k], int) and not isinstance(counts[k], bool) and counts[k] >= 0
           for k in ('input_tokens', 'output_tokens')):
        counts['total_tokens'] = counts['input_tokens'] + counts['output_tokens']
    return counts


def _gemini_usage(response):
    usage = getattr(response, 'usage_metadata', None)
    return {
        'input_tokens': getattr(usage, 'prompt_token_count', None),
        'output_tokens': getattr(usage, 'candidates_token_count', None),
        'thought_tokens': getattr(usage, 'thoughts_token_count', None),
        'total_tokens': getattr(usage, 'total_token_count', None),
    }


def _gemini_json_schema(case: ClassificationCase | None = None):
    # Use the JSON Schema transport. google-genai's OpenAPI response_schema
    # conversion currently emits snake_case Schema fields (e.g. additional_properties)
    # that the server rejects. Large array bounds also expand the decoding grammar
    # enough to reject this schema. Keep only the small support-module bound on
    # the wire; local Pydantic validation still enforces every limit.
    schema = PlanSelection.model_json_schema()

    def supported(node):
        for key in ('minLength', 'maxLength', 'minItems', 'maxItems', 'default'):
            node.pop(key, None)
        for key in ('properties', '$defs'):
            for child in node.get(key, {}).values():
                supported(child)
        for key in ('items', 'additionalProperties'):
            if isinstance(node.get(key), dict):
                supported(node[key])
        for key in ('anyOf', 'oneOf', 'prefixItems'):
            for child in node.get(key, []):
                supported(child)

    supported(schema)
    properties = schema['properties']
    properties['support_modules']['maxItems'] = 2
    properties['support_modules']['description'] = (
        'Zero, one, or two unique supporting modules; never repeat the lead module.')
    properties['reason_codes']['description'] = (
        'One or more unique codes copied exactly from this case\'s observed_reasons. '
        'Do not add inferred reasons; a zero cash-flow effect does not imply a cost or income change.')
    properties['rationale']['description'] = 'Brief explanation in 1–3 sentences, at most 1200 characters.'
    if case is not None:
        # The generic contract lists all possible reasons/modules. Constrain
        # generation to this case, matching validate_selection's stricter checks.
        properties['lead_module']['enum'] = list(case.constraints.allowed_modules)
        properties['support_modules']['items']['enum'] = list(case.constraints.allowed_modules)
        properties['reason_codes']['items']['enum'] = list(dict.fromkeys(case.observed_reasons))
    return schema


def _gemini_config(model, case: ClassificationCase | None = None):
    config = {
        'system_instruction': POLICY + '\nModule definitions: ' + json.dumps(MODULE_DESCRIPTIONS),
        'response_mime_type': 'application/json',
        'response_json_schema': _gemini_json_schema(case),
        'max_output_tokens': 2048,
    }
    # Sampling controls are deprecated on 3.5 Flash-Lite/3.6 and later models.
    # Keep the documented low-temperature setup only for explicit legacy overrides.
    if model.startswith('gemini-2.'):
        config['temperature'] = 0
    return config


def _gemini_validation_code(exc):
    """Return fixed diagnostic codes, never raw model text or validation input."""
    if isinstance(exc, _SelectionValidationError):
        return f'gemini_{exc.code}'
    if isinstance(exc, ValidationError):
        errors = exc.errors(include_input=False, include_context=False, include_url=False)
        if any(error['type'] == 'json_invalid' for error in errors):
            return 'gemini_invalid_json'
        for field in ('reason_codes', 'support_modules', 'rationale'):
            if any(error['loc'] and error['loc'][0] == field for error in errors):
                return f'gemini_invalid_{field}'
        return 'gemini_schema_mismatch'
    return 'invalid_gemini_response'


def _gemini_retry_contents(case, code):
    # A fresh request with a fixed correction; rejected free text is never echoed.
    return canonical_json(case) + (
        f'\n\nThe previous output failed validation ({code}). Return a corrected JSON object only. '
        'Use an allowed lead_module and at most two distinct support_modules excluding the lead. '
        'reason_codes must be nonempty, unique, and copied exactly from observed_reasons. '
        'Do not infer additional reason codes from effects or module names. '
        'Keep rationale nonempty and under 1200 characters. '
        'Use arrays for support_modules and needs_clarification, including [] when empty. '
        'Use only the fields in the response schema.')


def jev_payload(case: ClassificationCase, model: str) -> dict:
    criteria = {m: f'{MODULES[m]}: {MODULE_DESCRIPTIONS[m]}' for m in case.constraints.allowed_modules}
    questions = {
        'lead_module': {'type': 'choice', 'instructions': POLICY, 'criteria': criteria},
    }
    # Each supporting question is independent, then lead duplicates are removed locally.
    for m, definition in criteria.items():
        questions[f'support_{m}'] = {
            'type': 'noul',
            'instructions': POLICY + f'\nIs {definition} useful as part of this response?',
        }
    return {'model': model, 'state': json.loads(canonical_json(case)), 'questions': questions}


def select_plan_jev(case: ClassificationCase, *, api_key: str | None = None,
                    model: str | None = None, transport=None) -> SelectionResult:
    started = perf_counter()
    try:
        key,model = resolve_provider('jev', api_key=api_key, model=model)
    except ValueError:
        return _result(case, 'jev', started, failure='invalid_provider_settings',
                       model_version=PROVIDER_ROUTES['jev'][2])
    metadata = dict(model_version=model, prompt_version=PROMPT_VERSION)
    if len(case.constraints.allowed_modules) == 1:
        return _result(case, 'jev', started, failure='single_allowed_module', **metadata)
    if not key:
        return _result(case, 'jev', started, failure='missing_openrouter_api_key', **metadata)
    calls, invalid = 0, 0
    usage = _Usage()
    failure = 'jev_unavailable'
    # Two attempts maximum; failures never expose provider bodies or credentials.
    for _ in range(2):
        usage_recorded = False
        try:
            calls += 1
            response = (transport or requests.post)(
                JEV_ENDPOINT, json=jev_payload(case, model),
                headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'},
                timeout=(3.0, 15.0), allow_redirects=False,
            )
            status = response.status_code
            if type(status) is not int or not 100 <= status <= 599:
                raise ValueError('Invalid provider status')
            if status != 200:
                usage.complete = False
                failure = f'jev_http_{status}'
                if status not in {408, 429, 500, 502, 503, 504}:
                    break
                continue
            data = response.json()
            usage.record(_jev_usage(data), {'input_tokens', 'output_tokens', 'cost_usd'})
            usage_recorded = True
            resolved_model = _resolved_model(data.get('model'), model)
            if key and key in resolved_model:raise ValueError('Invalid response metadata')
            answer = data['answers']['lead_module']
            lead, confidence, probabilities = _choice(answer, case.constraints.allowed_modules)
            scores = {}
            for m in case.constraints.allowed_modules:
                support = data['answers'][f'support_{m}']
                if support['type'] != 'noul':
                    raise ValueError('Invalid supporting answer.')
                scores[m] = _probability(support['noul'])
            supports = sorted((m for m in scores if m != lead and scores[m] >= .5),
                              key=lambda m: (-scores[m], m))[:2]
            selection = validate_selection(PlanSelection(
                lead_module=lead, support_modules=supports, reason_codes=case.observed_reasons,
                needs_clarification=list(dict.fromkeys(case.missing_details)),
                rationale=f'Jev selected {MODULES[lead]}. Application evidence summary: ' +
                          ', '.join(s.replace('_', ' ') for s in case.observed_reasons) +
                          '. This summary is not model-generated reasoning.',
            ), case)
            metadata['model_version'] = resolved_model
            return _result(case, 'jev', started, selection=selection, **metadata,
                           api_calls=calls, invalid_outputs=invalid, rationale_source='evidence_template',
                           **usage.metadata(), provider_confidence=confidence,
                           module_probabilities=probabilities)
        except (ValueError, KeyError, TypeError, AttributeError):
            if not usage_recorded:
                usage.complete = False
            invalid += 1
            failure = 'invalid_jev_response'
        except Exception:
            usage.complete = False
            failure = 'jev_transport_error'
    return _result(case, 'jev', started, failure=failure, **metadata,
                   api_calls=calls, invalid_outputs=invalid, **usage.metadata())


def select_plan_gemini(case: ClassificationCase, *, api_key: str | None = None,
                       model: str | None = None, client=None) -> SelectionResult:
    started = perf_counter()
    try:
        key,model = resolve_provider('gemini', api_key=api_key, model=model)
    except ValueError:
        return _result(case, 'gemini', started, failure='invalid_provider_settings',
                       model_version=PROVIDER_ROUTES['gemini'][2])
    metadata = dict(model_version=model, prompt_version=GEMINI_PROMPT_VERSION)
    if len(case.constraints.allowed_modules) == 1:
        return _result(case, 'gemini', started, failure='single_allowed_module', **metadata)
    if client is None and not key:
        return _result(case, 'gemini', started, failure='missing_gemini_api_key', **metadata)
    owned_client = client is None
    if owned_client:
        try:
            from google import genai
            from google.genai import types
            client = genai.Client(api_key=key, http_options=types.HttpOptions(
                timeout=15000, retry_options=types.HttpRetryOptions(attempts=1)))
        except ImportError:
            return _result(case, 'gemini', started, failure='missing_google_genai_sdk', **metadata)
        except Exception:
            return _result(case, 'gemini', started, failure='gemini_client_error', **metadata)
    calls, invalid = 0, 0
    failure = 'gemini_unavailable'
    usage = _Usage()
    validation_errors = []
    contents = canonical_json(case)
    try:
        for _ in range(2):
            usage_recorded = False
            try:
                calls += 1
                response = client.models.generate_content(
                    model=model, contents=contents,
                    config=_gemini_config(model, case),
                )
                usage.record(_gemini_usage(response), {
                    'input_tokens', 'output_tokens', 'thought_tokens', 'total_tokens'})
                usage_recorded = True
                if not isinstance(response.text, str) or not response.text.strip():
                    raise _SelectionValidationError('empty_response', 'Gemini returned no JSON text.')
                selection = validate_selection(PlanSelection.model_validate_json(response.text), case)
                metadata['model_version'] = _resolved_model(getattr(response, 'model_version', None), model)
                if key and key in metadata['model_version']:
                    metadata['model_version'] = model
                    raise ValueError('Invalid response metadata')
                # Accept the structured module/reasons, never arbitrary provider
                # financial prose or questions as an analyst recommendation.
                selection = PlanSelection(**{**selection.model_dump(),
                    'rationale': f'Gemini proposed {MODULES[selection.lead_module]}. Application evidence summary: '
                        + ', '.join(r.replace('_',' ') for r in selection.reason_codes) + '.',
                    'needs_clarification': list(dict.fromkeys(case.missing_details))})
                return _result(case, 'gemini', started, selection=selection, **metadata,
                               api_calls=calls, invalid_outputs=invalid, validation_errors=validation_errors,
                               **usage.metadata(),
                               rationale_source='evidence_template')
            except (ValueError, TypeError, ValidationError) as exc:
                if not usage_recorded:
                    usage.complete = False
                invalid += 1
                failure = _gemini_validation_code(exc)
                validation_errors.append(failure)
                contents = _gemini_retry_contents(case, failure)
            except Exception as exc:
                usage.complete = False
                code = getattr(exc, 'code', None)
                if isinstance(code, int) and not isinstance(code, bool) and 100 <= code <= 599:
                    failure = f'gemini_http_{code}'
                    if code not in {408, 429, 500, 502, 503, 504}:
                        break
                else:
                    failure = 'gemini_api_error'
    finally:
        if owned_client:
            try:
                client.close()
            except Exception:
                pass
    return _result(case, 'gemini', started, failure=failure, **metadata, api_calls=calls,
                   invalid_outputs=invalid, validation_errors=validation_errors, **usage.metadata())


def select_plan(case: ClassificationCase, backend='rules', **kwargs) -> SelectionResult:
    # Backwards compatibility with the team's spelling; always report the real name.
    backend = 'jev' if backend == 'jeff' else backend
    if backend == 'jev':
        return select_plan_jev(case, **kwargs)
    if backend == 'gemini':
        return select_plan_gemini(case, **kwargs)
    if backend == 'rules':
        return _result(case, 'rules', perf_counter(), selection=rule_baseline(case))
    raise ValueError('backend must be jev, gemini, or rules (jeff is an alias for jev).')
