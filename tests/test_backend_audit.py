"""Regression checks from the backend audit; all remote responses are mocked."""
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import requests

from plan_classification import FinancialConstraints, build_case, get_customer_profile, select_plan
from plan_classification.case import scenario_from_engine
from plan_classification.schemas import PlanSelection


@pytest.fixture
def case():
    return build_case(get_customer_profile(22812), scenario_from_engine(.55))


def selection_json():
    return PlanSelection(lead_module='M1', reason_codes=['income_reduction'],
                         rationale='Recurring inflow decreased.').model_dump_json()


def jev_data(case, **overrides):
    answers = {'lead_module': {'type': 'choice', 'choice': 'M1', 'confidence': .8,
                               'probabilities': {m: 1.0 if m == 'M1' else 0.0
                                                 for m in case.constraints.allowed_modules}}}
    answers.update({f'support_{m}': {'type': 'noul', 'noul': .1}
                    for m in case.constraints.allowed_modules})
    return {'answers': answers, 'model': 'typesafe/jev-1.14',
            'usage': {'input_tokens': 100, 'output_tokens': 50, 'cost': .01}, **overrides}


class Response:
    status_code = 200
    def __init__(self, data): self.data = data
    def json(self): return self.data


class Gemini:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.models = self
        self.calls = []
    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        result = next(self.responses)
        if isinstance(result, Exception): raise result
        return result


def gemini_data(**overrides):
    data = dict(text=selection_json(), model_version='gemini-3.5-flash-lite',
                usage_metadata=SimpleNamespace(prompt_token_count=10, candidates_token_count=20,
                                               thoughts_token_count=30, total_token_count=60))
    return SimpleNamespace(**{**data, **overrides})


@pytest.mark.parametrize('bad_model', [123, True, {}, [], ''])
def test_invalid_jev_model_metadata_cannot_break_fallback(case, bad_model):
    result = select_plan(case, 'jev', api_key='fake',
                         transport=lambda *a, **k: Response(jev_data(case, model=bad_model)))
    assert result.actual_backend == 'rule_baseline'
    assert result.fallback_reason == 'invalid_jev_response'
    assert result.invalid_outputs == 2
    assert result.model_version == 'typesafe/jev-1.14'
    assert result.input_tokens == 200
    assert result.cost_usd == pytest.approx(.02)


@pytest.mark.parametrize('bad_model', [123, True, {}, [], ''])
def test_invalid_gemini_model_metadata_cannot_break_fallback(case, bad_model):
    client = Gemini([gemini_data(model_version=bad_model)] * 2)
    result = select_plan(case, 'gemini', client=client, model='gemini-3.5-flash-lite')
    assert result.actual_backend == 'rule_baseline'
    assert result.fallback_reason == 'invalid_gemini_response'
    assert result.invalid_outputs == 2
    assert result.model_version == 'gemini-3.5-flash-lite'
    assert result.thought_tokens == 60


def test_jev_sums_cost_even_for_invalid_decisions(case):
    bad = jev_data(case)
    bad['answers']['lead_module']['choice'] = 'M99'
    responses = iter([bad, jev_data(case)])
    result = select_plan(case, 'jev', api_key='fake',
                         transport=lambda *a, **k: Response(next(responses)))
    assert result.actual_backend == 'jev'
    assert result.api_calls == 2 and result.invalid_outputs == 1
    assert result.input_tokens == 200 and result.output_tokens == 100
    assert result.total_tokens == 300 and result.cost_usd == pytest.approx(.02)
    assert result.usage_complete is True


def test_jev_partial_usage_reports_known_amount_and_incompleteness(case):
    first = jev_data(case, usage=None)
    first['answers']['lead_module']['choice'] = 'M99'
    responses = iter([first, jev_data(case)])
    result = select_plan(case, 'jev', api_key='fake',
                         transport=lambda *a, **k: Response(next(responses)))
    assert result.actual_backend == 'jev'
    assert result.input_tokens == 100 and result.cost_usd == .01
    assert result.usage_complete is False


@pytest.mark.parametrize('usage', [None, {}, {'input_tokens': -5, 'output_tokens': True, 'cost': float('nan')}])
def test_unknown_or_invalid_jev_usage_is_never_zero(case, usage):
    result = select_plan(case, 'jev', api_key='fake',
                         transport=lambda *a, **k: Response(jev_data(case, usage=usage)))
    assert result.actual_backend == 'jev'
    assert result.input_tokens is None and result.output_tokens is None
    assert result.cost_usd is None and result.total_tokens is None
    assert result.usage_complete is False


def test_jev_json_decode_failure_is_incomplete_usage(case):
    class InvalidJson:
        status_code = 200
        def json(self): raise ValueError('bad provider response')
    result = select_plan(case, 'jev', api_key='fake', transport=lambda *a, **k: InvalidJson())
    assert result.fallback_used
    assert result.usage_complete is False and result.input_tokens is None


def test_jev_timeout_has_unknown_usage(case):
    def timeout(*a, **k): raise requests.Timeout('secret-error-body')
    result = select_plan(case, 'jev', api_key='fake', transport=timeout)
    assert result.fallback_used and result.api_calls == 2
    assert result.input_tokens is None and result.cost_usd is None
    assert result.usage_complete is False
    assert 'secret-error-body' not in result.model_dump_json()


def test_gemini_sums_visible_thought_and_total_tokens(case):
    result = select_plan(case, 'gemini', client=Gemini([gemini_data(text='bad json'), gemini_data()]))
    assert result.actual_backend == 'gemini' and result.api_calls == 2
    assert result.input_tokens == 20 and result.output_tokens == 40
    assert result.thought_tokens == 60 and result.total_tokens == 120
    assert result.usage_complete is True
    assert result.cost_usd is None


def test_gemini_unknown_usage_and_known_zero_are_distinct(case):
    unknown = select_plan(case, 'gemini', client=Gemini([gemini_data(usage_metadata=None)]))
    assert unknown.input_tokens is None and unknown.output_tokens is None
    assert unknown.thought_tokens is None and unknown.total_tokens is None
    assert unknown.usage_complete is False
    zero = SimpleNamespace(prompt_token_count=0, candidates_token_count=0,
                           thoughts_token_count=0, total_token_count=0)
    known = select_plan(case, 'gemini', client=Gemini([gemini_data(usage_metadata=zero)]))
    assert known.input_tokens == known.output_tokens == known.thought_tokens == known.total_tokens == 0
    assert known.usage_complete is True


def test_no_remote_request_when_constraints_allow_only_one_module(case):
    only = case.model_copy(update={'constraints': FinancialConstraints(allowed_modules=['M2'])})
    def unexpected_call(*args, **kwargs): raise AssertionError('No decision is needed.')
    result = select_plan(only, 'jev', api_key='fake', transport=unexpected_call)
    assert result.selection.lead_module == 'M2' and result.api_calls == 0
    assert result.actual_backend == 'rule_baseline' and result.fallback_reason == 'single_allowed_module'
    client = Gemini([])
    result = select_plan(only, 'gemini', client=client)
    assert not client.calls and result.api_calls == 0
    assert result.selection.lead_module == 'M2'


def test_gemini_new_default_omits_deprecated_sampling_parameters(case, monkeypatch):
    monkeypatch.delenv('GEMINI_CLASSIFIER_MODEL', raising=False)
    client = Gemini([gemini_data()])
    select_plan(case, 'gemini', client=client)
    assert client.calls[0]['model'] == 'gemini-3.5-flash-lite'
    assert not {'temperature', 'top_p', 'top_k'} & client.calls[0]['config'].keys()
    legacy = Gemini([gemini_data()])
    select_plan(case, 'gemini', model='gemini-2.5-flash', client=legacy)
    assert legacy.calls[0]['config']['temperature'] == 0


def test_actual_google_sdk_serializes_and_parses_without_network(case):
    from google import genai
    from google.genai import types
    response = types.HttpResponse(headers={}, body=json.dumps({
        'candidates': [{'content': {'parts': [{'text': selection_json()}], 'role': 'model'},
                        'finishReason': 'STOP'}],
        'usageMetadata': {'promptTokenCount': 10, 'candidatesTokenCount': 20,
                          'thoughtsTokenCount': 30, 'totalTokenCount': 60},
        'modelVersion': 'gemini-3.5-flash-lite',
    }))
    with genai.Client(api_key='fake-never-transmitted') as client:
        with patch.object(client._api_client, 'request', return_value=response) as request:
            result = select_plan(case, 'gemini', model='gemini-3.5-flash-lite', client=client)
    assert request.call_count == 1
    assert result.actual_backend == 'gemini' and result.selection.lead_module == 'M1'
    assert result.thought_tokens == 30 and result.total_tokens == 60
    body = request.call_args.args[2]
    assert body['generationConfig']['responseMimeType'] == 'application/json'
    assert 'temperature' not in body['generationConfig']
    schema = body['generationConfig']['responseJsonSchema']
    assert 'responseSchema' not in body['generationConfig']
    assert schema['properties']['lead_module']['enum'] == [f'M{i}' for i in range(1,9)]
    assert schema['additionalProperties'] is False
    assert 'additional_properties' not in json.dumps(schema)
    assert 'max_items' not in json.dumps(schema)
    assert 'minItems' not in json.dumps(schema)
    assert schema['properties']['support_modules']['maxItems'] == 2
    assert 'maxItems' not in schema['properties']['reason_codes']
    assert 'maxItems' not in schema['properties']['needs_clarification']
    # These are local validation rules, outside the API's supported JSON Schema subset.
    assert 'minLength' not in schema['properties']['rationale']
    assert 'maxLength' not in schema['properties']['rationale']


def test_local_validation_still_enforces_support_limit():
    with pytest.raises(ValueError, match='at most 2'):
        PlanSelection(lead_module='M1', support_modules=['M2','M3','M4'],
                      reason_codes=['income_reduction'], rationale='Income changed.')


@pytest.mark.parametrize('code,attempts', [(400,1),(401,1),(403,1),(404,1),(408,2),(429,2),(500,2),(503,2)])
def test_gemini_http_status_is_safe_and_retries_only_transient_errors(case, code, attempts):
    from google.genai.errors import APIError
    error = APIError(code, {'error': {'message': 'SECRET raw provider body', 'status': 'ERROR'}})
    result = select_plan(case, 'gemini', client=Gemini([error,error]))
    assert result.actual_backend == 'rule_baseline'
    assert result.fallback_reason == f'gemini_http_{code}'
    assert result.api_calls == attempts
    assert result.input_tokens is None and not result.usage_complete
    assert 'SECRET' not in result.model_dump_json()
