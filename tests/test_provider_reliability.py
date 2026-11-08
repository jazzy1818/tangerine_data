"""Provider reliability and privacy use synthetic settings and mocked transports only."""
import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock,patch
import pytest
from plan_classification import config,build_case,profile_from_engine,ShockScenario,select_plan
from test_crisis_execution import account,compound,normal_goal
from crisis_response import make_crisis_plan
import gemini_advisor as ga
from tailored_advice import explain_plan


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path,monkeypatch,provider_configuration):
    file=tmp_path/'.env';file.write_text('')
    monkeypatch.setattr(config,'ENV_FILE',file)
    monkeypatch.delenv('GEMINI_API_KEY',raising=False)
    monkeypatch.delenv('OPENROUTER_API_KEY',raising=False)
    return file


def test_daily_default_is_local_even_with_inherited_key(monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY','synthetic-shell-key')
    with patch('gemini_advisor.genai.Client') as client:
        result=ga.consult_gemini_advisor('compound',5,1500,True,True)
    assert client.call_count==0
    assert result['actual_backend']=='local'


@pytest.mark.parametrize('backend',['jev','gemini'])
def test_bad_settings_fall_back_without_echoing_values(backend,isolated_settings):
    isolated_settings.write_text('GEMINI_API_KEY="synthetic-secret-unclosed\n')
    case=build_case(profile_from_engine(account()),compound())
    out=select_plan(case,backend)
    assert out.actual_backend=='rule_baseline' and out.api_calls==0
    assert out.fallback_reason=='invalid_provider_settings'
    assert 'synthetic-secret' not in out.model_dump_json()


def test_explanation_uses_project_file_without_exporting_key(isolated_settings,monkeypatch):
    isolated_settings.write_text('GEMINI_API_KEY=synthetic-file-key\nGEMINI_EXPLANATION_MODEL=gemini-test-explanation\n')
    monkeypatch.setenv('GEMINI_API_KEY','synthetic-shell-key')
    p=make_crisis_plan(account(),compound(),normal_goal=normal_goal())
    client=Mock();client.models.generate_content.return_value=SimpleNamespace(text='{"focus_ids":["gap"]}')
    with patch('google.genai.Client',return_value=client) as factory:
        out=explain_plan(p,backend='gemini')
    assert factory.call_args.kwargs['api_key']=='synthetic-file-key'
    assert client.models.generate_content.call_args.kwargs['model']=='gemini-test-explanation'
    assert out['actual_backend']=='gemini'
    import os
    assert os.environ['GEMINI_API_KEY']=='synthetic-shell-key'


def test_settings_precedence_empty_override_and_explicit_key(isolated_settings,monkeypatch):
    from plan_classification.config import resolve_provider
    monkeypatch.setenv('GEMINI_API_KEY','synthetic-shell')
    isolated_settings.write_text('GEMINI_API_KEY=\nGEMINI_ADVISOR_MODEL=gemini-file-daily\n')
    assert resolve_provider('daily')==('','gemini-file-daily')
    assert resolve_provider('daily',api_key='synthetic-explicit',model='gemini-explicit')==('synthetic-explicit','gemini-explicit')


def test_same_synthetic_normalized_case_goes_to_both_classifiers():
    from test_backend_audit import Response,jev_data,gemini_data,Gemini
    from plan_classification.case import canonical_json
    c=account(cash=28173.42);c['account_id']=81234567;c['history']['account_id']=81234567
    scenario=ShockScenario(description='PRIVATE-NOTE-DO-NOT-SEND',effects=[
        dict(type='income_multiplier',value=.55,duration_months=6,effect_id='PRIVATE-EFFECT-ID'),
        dict(type='one_off_cost',value=1234.56,start_month=0,effect_id='PRIVATE-INVOICE-ID')])
    case=build_case(profile_from_engine(c),scenario)
    captured={}
    def post(url,**kwargs):
        captured.update(kwargs);return Response(jev_data(case))
    jev=select_plan(case,'jev',api_key='synthetic-request-key',transport=post)
    gemini=Gemini([gemini_data()])
    result=select_plan(case,'gemini',client=gemini)
    assert jev.actual_backend=='jev' and result.actual_backend=='gemini'
    assert captured['json']['state']==json.loads(gemini.calls[0]['contents'])==json.loads(canonical_json(case))
    payload=json.dumps(captured['json'])+gemini.calls[0]['contents']
    for forbidden in ['81234567','28173.42','1234.56','PRIVATE-NOTE','PRIVATE-INVOICE','PRIVATE-EFFECT','synthetic-request-key','account_id','transactions','history']:
        assert forbidden not in payload
    assert captured['headers']['Authorization']=='Bearer synthetic-request-key'


def test_untrusted_classifier_prose_is_not_accepted_as_advice():
    from test_backend_audit import Gemini,gemini_data
    case=build_case(profile_from_engine(account()),compound())
    response=json.dumps(dict(lead_module='M5',reason_codes=['compound_effects'],
        rationale='APPROVED CAD 4000 guaranteed relief loan; buy ETF NOW.',
        needs_clarification=['APPROVED trading authority.']))
    result=select_plan(case,'gemini',client=Gemini([gemini_data(text=response)]))
    assert result.actual_backend=='gemini' and result.rationale_source=='evidence_template'
    assert 'APPROVED' not in result.model_dump_json() and '4000' not in result.selection.rationale
    p=make_crisis_plan(account(),compound(),normal_goal=normal_goal(),selection_result=result)
    local=make_crisis_plan(account(),compound(),normal_goal=normal_goal())
    assert p['applied_plan']==local['applied_plan'] and p['no_action']==local['no_action']
    assert 'APPROVED' not in json.dumps(p['advice'])


def test_explanation_payload_excludes_local_cards_and_errors_are_redacted(caplog):
    p=make_crisis_plan(account(),compound(),normal_goal=normal_goal())
    original=deepcopy(p)
    client=Mock();client.models.generate_content.side_effect=RuntimeError('synthetic-key PRIVATE-NOTE CAD 3360')
    result=explain_plan(p,backend='gemini',client=client)
    assert result['actual_backend']=='local' and result['api_calls']==1
    payload=client.models.generate_content.call_args.kwargs['contents']
    assert all(x not in payload for x in ['3360','3000','account_id','source','PRIVATE-NOTE'])
    assert 'synthetic-key' not in json.dumps(result)+caplog.text
    assert p==original


def test_daily_remote_receives_only_bands_and_accepts_no_new_action(isolated_settings,caplog):
    isolated_settings.write_text('GEMINI_API_KEY=synthetic-daily-key\nGEMINI_ADVISOR_MODEL=gemini-test-daily\n')
    client=Mock();client.models.generate_content.return_value=SimpleNamespace(text='{"primary_action_id":"invented_relief_loan"}')
    with patch('gemini_advisor.genai.Client') as factory:
        factory.return_value.__enter__.return_value=client
        out=ga.consult_gemini_advisor('PRIVATE-NOTE',5,1234.56,True,True,backend='gemini')
    assert out['actual_backend']=='local' and out['fallback_used'] and out['api_calls']==1
    args=client.models.generate_content.call_args.kwargs
    assert args['model']=='gemini-test-daily'
    assert all(x not in args['contents'] for x in ['PRIVATE-NOTE','1234.56','synthetic-daily-key'])
    assert '1k_to_under_5k' in args['contents']
    assert out['plan']['primary_action_id']=='move_recurring_bill'
    assert 'invented_relief_loan' not in json.dumps(out)+caplog.text


def test_missing_keys_and_provider_timeouts_leave_all_routes_usable():
    case=build_case(profile_from_engine(account()),compound())
    for name in ['jev','gemini']:
        r=select_plan(case,name)
        assert r.actual_backend=='rule_baseline' and r.api_calls==0
    out=ga.consult_gemini_advisor('compound',5,1500,True,True,backend='gemini')
    assert out['actual_backend']=='local' and out['api_calls']==0
    p=make_crisis_plan(account(),compound(),normal_goal=normal_goal())
    assert explain_plan(p,backend='gemini')['fallback_reason']=='credentials_unavailable'
    def timeout(*args,**kwargs):raise RuntimeError('PRIVATE-PROVIDER-BODY synthetic-key')
    r=select_plan(case,'jev',api_key='synthetic-key',transport=timeout)
    assert r.actual_backend=='rule_baseline' and r.api_calls==2
    assert 'PRIVATE' not in r.model_dump_json() and 'synthetic-key' not in r.model_dump_json()


def test_financial_override_is_separate_from_successful_provider_label():
    from test_backend_audit import Gemini,gemini_data
    case=build_case(profile_from_engine(account()),compound())
    response=json.dumps(dict(lead_module='M6',reason_codes=['compound_effects'],rationale='Restore reserves.'))
    proposal=select_plan(case,'gemini',client=Gemini([gemini_data(text=response)]))
    assert proposal.actual_backend=='gemini' and proposal.selection.lead_module=='M6'
    p=make_crisis_plan(account(),compound(),normal_goal=normal_goal(),selection_result=proposal)
    assert p['lead_module']!='M6' and p['selection_status']=='financial_eligibility_override'
    assert p['classification']['actual_backend']=='gemini'
    assert p['no_action']['additional_cash_needed']==3360


def test_valid_daily_abstention_is_a_provider_success_with_no_new_action(isolated_settings):
    isolated_settings.write_text('GEMINI_API_KEY=synthetic-key\n')
    client=Mock();client.models.generate_content.return_value=SimpleNamespace(text='{"primary_action_id":null}')
    with patch('gemini_advisor.genai.Client') as factory:
        factory.return_value.__enter__.return_value=client
        out=ga.consult_gemini_advisor('compound',5,1500,True,True,backend='gemini')
    assert out['actual_backend']=='gemini' and not out['fallback_used']
    assert out['api_calls']==1 and out['plan']['primary_action_id'] is None


def sdk_response(text):
    from google.genai import types
    return types.HttpResponse(headers={},body=json.dumps({'candidates':[{
        'content':{'parts':[{'text':text}],'role':'model'},'finishReason':'STOP'}]}))


def test_explanation_actual_sdk_wire_schema_and_payload_without_network():
    from google import genai
    p=make_crisis_plan(account(),compound(),normal_goal=normal_goal())
    with genai.Client(api_key='synthetic-never-transmitted') as client:
        with patch.object(client._api_client,'request',return_value=sdk_response('{"focus_ids":["gap"]}')) as request:
            out=explain_plan(p,backend='gemini',client=client)
    assert out['actual_backend']=='gemini' and out['api_calls']==1
    body=request.call_args.args[2]
    schema=body['generationConfig']['responseJsonSchema']
    assert schema['additionalProperties'] is False
    assert schema['properties']['focus_ids']['maxItems']==3
    assert set(schema['properties']['focus_ids']['items']['enum'])==set(p['advice']['cards'])
    assert 'responseSchema' not in body['generationConfig']
    assert 'additional_properties' not in json.dumps(body)
    assert '3360' not in json.dumps(body)


def test_daily_actual_sdk_wire_schema_without_network(isolated_settings):
    from contextlib import nullcontext
    from google import genai
    isolated_settings.write_text('GEMINI_API_KEY=synthetic-key\n')
    with genai.Client(api_key='synthetic-never-transmitted') as client:
        with patch.object(client._api_client,'request',return_value=sdk_response('{"primary_action_id":"move_recurring_bill"}')) as request, \
             patch('gemini_advisor.genai.Client',return_value=nullcontext(client)):
            out=ga.consult_gemini_advisor('compound',5,1234.56,True,True,backend='gemini')
    assert out['actual_backend']=='gemini' and out['api_calls']==1
    body=request.call_args.args[2]
    assert body['generationConfig']['responseJsonSchema']['additionalProperties'] is False
    assert 'responseSchema' not in body['generationConfig']
    assert 'additional_properties' not in json.dumps(body)
    assert '1234.56' not in json.dumps(body)


def test_whitespace_override_is_blank_and_does_not_bypass_file_precedence(isolated_settings):
    from plan_classification.config import resolve_provider
    isolated_settings.write_text('GEMINI_API_KEY=synthetic-file-key\n')
    assert resolve_provider('daily',api_key='   ')[0]=='synthetic-file-key'


def test_missing_google_sdk_keeps_all_gemini_routes_local(isolated_settings,monkeypatch):
    isolated_settings.write_text('GEMINI_API_KEY=synthetic-file-key\n')
    case=build_case(profile_from_engine(account()),compound())
    p=make_crisis_plan(account(),compound(),normal_goal=normal_goal())
    with patch.dict('sys.modules',{'google':None,'google.genai':None}):
        r=select_plan(case,'gemini')
        assert r.actual_backend=='rule_baseline' and r.api_calls==0
        out=explain_plan(p,backend='gemini')
        assert out['actual_backend']=='local' and out['api_calls']==0
    monkeypatch.setattr(ga,'HAVE_GOOGLE_GENAI',False)
    daily=ga.consult_gemini_advisor('compound',5,1500,True,True,backend='gemini')
    assert daily['actual_backend']=='local' and daily['api_calls']==0
