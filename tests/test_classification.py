"""Offline contract/edge-case tests, not a Jev-vs-Gemini quality benchmark."""
import json
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
import requests
from pydantic import ValidationError

import engine
from plan_classification import (FinancialConstraints, ShockScenario, build_case,
                                 get_customer_profile, select_plan)
from plan_classification.backends import JEV_ENDPOINT, jev_payload, validate_selection
from plan_classification.case import canonical_json, scenario_from_engine
from plan_classification.features import (build_account_features, profile_from_engine,
                                         profile_from_history, validate_monthly)
from plan_classification.schemas import MODULES, PlanSelection


@pytest.fixture
def history():
    return pd.DataFrame({
        'account_id': [17]*12, 'month': pd.period_range('2025-01', periods=12, freq='M').astype(str),
        'money_in': [4000.]*12, 'money_out': [3200.]*12,
        'household_bills': [1200.]*12, 'insurance': [100.]*12,
        'loan_payments': [0.]*12, 'avg_daily_balance': [4000.]*12,
        'month_end_balance': [4000.]*12, 'min_balance': [1000.]*12, 'days_below_zero': [0]*12,
    })


@pytest.fixture
def profile(history):
    return profile_from_history(17, history, as_of='2025-12')


def case_for(profile, effects=None, phase='active', constraints=None):
    return build_case(profile, ShockScenario(effects=effects or [], phase=phase), constraints)


def test_official_example(profile):
    b = profile.baseline
    assert (b.I,b.S,b.F,b.H,b.B,b.P) == (4000,3200,1300,1200,4000,0)
    assert profile.features.reserve_months == 1.25
    assert b.runway == 'no shortfall (120+)'
    case = build_case(profile, scenario_from_engine(.55,.15,0))
    assert case.first_period_gap_to_scale == 1180/4000
    assert case.first_period_runway_months == pytest.approx(4000/1180)
    assert select_plan(case).selection.lead_module == 'M5'


def test_fixed_cost_sum_before_median_and_last_six(history):
    history.loc[:,'household_bills'] = [0,0,100,100,100,100]*2
    history.loc[:,'insurance'] = [100,100,0,0,0,0]*2
    history.loc[:,'avg_daily_balance'] = np.arange(12)*100
    p = profile_from_history(17,history.sample(frac=1,random_state=3),as_of='2025-12')
    assert p.baseline.F == 100
    assert p.baseline.B == 850


@pytest.mark.parametrize('status,payment,active,arrears', [('A',0,False,False),('B',0,False,False),('C',200,True,False),('D',200,True,True)])
def test_loan_snapshot(history,status,payment,active,arrears):
    p = profile_from_history(17,history,{'status':status,'monthly_payment':200},as_of='2025-12')
    assert p.baseline.P == payment
    assert p.features.active_loan == active
    assert p.features.loan_in_arrears == arrears


def test_no_future_leakage(history):
    p = profile_from_history(17,history,{'status':'D','monthly_payment':200},as_of='2025-06',loan_snapshot_available=False)
    changed = history.copy()
    changed.loc[changed.month > '2025-06','money_in'] = 1e12
    q = profile_from_history(17,changed,as_of='2025-06',loan_snapshot_available=False)
    assert p == q
    assert p.features.months_observed == 6
    assert p.baseline.P is None
    assert p.features.loan_in_arrears is None


def test_zero_denominators_and_negative_buffer(history):
    history['money_in']=0
    history['money_out']=0
    history['avg_daily_balance']=-50
    p=profile_from_history(17,history,as_of='2025-12')
    assert p.features.surplus_margin is None
    assert p.features.reserve_months is None
    assert p.features.debt_payment_ratio is None
    assert p.baseline.runway == 0
    case=case_for(p,phase='normal')
    assert 'NaN' not in canonical_json(case)
    assert 'Infinity' not in canonical_json(case)
    assert select_plan(case).selection.lead_module == 'M3'


def test_short_history_sparse_missing_and_stale(history):
    history=history.iloc[[0,2]].drop(columns=['days_below_zero'])
    p=profile_from_history(17,history,as_of='2025-12')
    assert p.features.months_observed == 2
    assert p.features.stale_months == 9
    assert p.features.negative_balance_month_share is None
    assert {'missing_calendar_months','missing_days_below_zero','stale_history'} <= set(p.features.quality_flags)


@pytest.mark.parametrize('error', ['duplicate','missing_column','nan','infinity','negative_flow','bad_month'])
def test_bad_data_rejected(history,error):
    if error=='duplicate': history=pd.concat([history,history.iloc[[0]]])
    elif error=='missing_column': history=history.drop(columns='money_in')
    elif error=='nan': history.loc[0,'money_in']=float('nan')
    elif error=='infinity': history.loc[0,'money_in']=float('inf')
    elif error=='negative_flow': history.loc[0,'money_out']=-1
    elif error=='bad_month': history.loc[0,'month']='2025-13'
    with pytest.raises(ValueError): validate_monthly(history)


@pytest.mark.parametrize('effects,phase,module', [
    ([{'type':'income_multiplier','value':.55}],'active','M1'),
    ([{'type':'household_bills_percent','value':15}],'active','M2'),
    ([{'type':'one_off_cost','value':1000,'start_month':0}],'active','M3'),
    ([{'type':'debt_payment_delta','value':100}],'active','M4'),
    ([{'type':'income_multiplier','value':.55},{'type':'household_bills_percent','value':15}],'active','M5'),
    ([], 'recovery','M6'),
    ([{'type':'liquidity_hold','value':2500,'duration_months':2}],'active','M7'),
    ([{'type':'one_off_receipt','value':10000,'start_month':0}],'active','M8'),
    ([{'type':'income_multiplier','value':1.1}],'active','M8'),
    ([{'type':'household_bills_percent','value':-10}],'active','M8'),
])
def test_all_module_baseline_routes(profile,effects,phase,module):
    result=select_plan(case_for(profile,effects,phase))
    assert result.selection.lead_module==module
    assert result.actual_backend=='rule_baseline'
    assert result.fallback_used is False


def test_large_one_off_immediate_failure(profile):
    c=case_for(profile,[{'type':'one_off_cost','value':6000,'start_month':0}])
    assert c.immediate_buffer_to_scale == -.5
    assert c.first_period_runway_months == 0
    assert select_plan(c).selection.lead_module == 'M3'


def test_investment_is_not_cash(profile):
    c=case_for(profile,[{'type':'investment_return','value':-25}])
    assert c.immediate_buffer_to_scale == 1
    assert c.missing_details
    assert 'investment_change' in c.observed_reasons


def test_hold_preserves_cash_and_timing(profile):
    c=case_for(profile,[{'type':'liquidity_hold','value':2500,'duration_months':2}])
    assert c.immediate_buffer_to_scale == 1
    assert c.effects[0].value == .625
    assert c.effects[0].duration_months == 2
    assert c.first_period_no_shortfall


def test_unknowns_not_invented(profile):
    c=case_for(profile,[{'type':'income_multiplier','value':None}])
    assert c.first_period_gap_to_scale == -.2
    assert c.missing_details
    assert 'income_reduction' not in c.observed_reasons
    assert select_plan(c).selection.needs_clarification
    assert case_for(profile).missing_details
    assert not case_for(profile,phase='normal').missing_details


def test_inactive_and_neutral_effects(profile):
    c=case_for(profile,[{'type':'income_multiplier','value':1},
                        {'type':'one_off_cost','value':500,'start_month':8}])
    assert 'compound_effects' not in c.observed_reasons
    assert 'one_off_expense' not in c.observed_reasons


@pytest.mark.parametrize('effects', [
    [{'type':'income_multiplier','value':-1}],
    [{'type':'one_off_cost','value':-100}],
    [{'type':'expense_percent','value':-101}],
    [{'type':'income_multiplier','value':float('inf')}],
    [{'type':'one_off_cost','value':10,'duration_months':3}],
    [{'type':'income_multiplier','value':.5,'start_month':0}],
    [{'type':'income_multiplier','value':.5},{'type':'income_multiplier','value':.7}],
    [{'type':'one_off_cost','value':100},{'type':'one_off_cost','value':100}],
    [{'type':'expense_percent','value':10},{'type':'household_bills_percent','value':10}],
])
def test_invalid_effects(effects):
    with pytest.raises(ValueError): ShockScenario(effects=effects)


def test_sequential_income_effects_allowed(profile):
    c=case_for(profile,[{'type':'income_multiplier','value':.55,'duration_months':6},
                        {'type':'income_multiplier','value':0,'start_month':7}])
    assert c.first_period_gap_to_scale == .25


def test_impossible_future_effect_rejected(profile):
    with pytest.raises(ValueError,match='month 4'):
        case_for(profile,[{'type':'income_delta','value':-9999,'start_month':4}])


def test_zero_new_debt_cost_no_double_count(profile):
    c=case_for(profile,[{'type':'debt_payment_delta','value':100}])
    assert c.first_period_gap_to_scale == -.175


def test_constraints_respected(profile):
    c=case_for(profile,[{'type':'income_multiplier','value':.55}],
               constraints=FinancialConstraints(allowed_modules=['M2']))
    result=select_plan(c)
    assert result.selection.lead_module=='M2'
    assert result.selection.support_modules==[]
    assert result.selection.needs_clarification


def test_profile_engine_adapter_agrees():
    c=engine.know_customer(22812)
    p=profile_from_engine(c)
    q=get_customer_profile(22812)
    assert p==q


def test_all_account_baselines_against_independent_reference():
    # Bulk numerical verification, not classifier evaluation.
    frame=build_account_features().set_index('account_id')
    m=pd.read_csv('data/monthly_summary.csv').sort_values(['account_id','month'])
    l=pd.read_csv('data/loans.csv').set_index('account_id')
    expected=m.groupby('account_id')[['money_in','money_out','household_bills']].median()
    expected['F']=m.assign(fixed=m.household_bills+m.insurance+m.loan_payments).groupby('account_id').fixed.median()
    expected['B']=m.groupby('account_id').tail(6).groupby('account_id').avg_daily_balance.mean()
    for ours,theirs in [('I','money_in'),('S','money_out'),('H','household_bills'),('F','F'),('B','B')]:
        np.testing.assert_allclose(frame[ours],expected[theirs],rtol=0,atol=1e-9)
    loan_payment=l.monthly_payment.where(l.status.isin(['C','D']),0).reindex(frame.index,fill_value=0)
    np.testing.assert_array_equal(frame.P,loan_payment)
    assert len(frame)==4500


def test_ids_and_narrative_do_not_reach_models(profile):
    scenario=ShockScenario(description='Account 9876543, name SECRET, api_key TOPSECRET',
                           effects=[{'type':'one_off_cost','value':1234.56,'start_month':0}])
    case=build_case(profile,scenario)
    payload=json.dumps(jev_payload(case,'typesafe/jev-1.14'))
    for forbidden in ['account_id','SECRET','9876543','1234.56','avg_daily_balance','birth_date','gender']:
        assert forbidden not in payload
    assert json.loads(payload)['state']==json.loads(canonical_json(case))


def jev_response(case,lead='M1'):
    modules=case.constraints.allowed_modules
    answers={'lead_module': {'type':'choice','choice':lead,'confidence':.8,
                             'probabilities':{m: .9 if m==lead else .1/(len(modules)-1) for m in modules}}}
    answers.update({f'support_{m}':{'type':'noul','noul':.8 if m=='M6' else .1} for m in modules})
    return {'model':'typesafe/jev-1.14','answers':answers,'usage':{'input_tokens':50,'output_tokens':0,'cost':.0001}}


class FakeResponse:
    def __init__(self,data=None,status=200): self.data,self.status_code=data,status
    def json(self): return self.data


def test_real_jev_wire_contract_and_shared_input(profile):
    case=case_for(profile,[{'type':'income_multiplier','value':.55}])
    captured=[]
    def post(url,**kwargs):
        captured.append((url,kwargs))
        return FakeResponse(jev_response(case))
    result=select_plan(case,'jev',api_key='test-secret',transport=post)
    assert result.actual_backend=='jev' and not result.fallback_used
    assert result.selection.lead_module=='M1'
    assert result.selection.support_modules==['M6']
    assert result.rationale_source=='evidence_template'
    assert result.provider_confidence==.8
    assert captured[0][0]==JEV_ENDPOINT
    assert captured[0][1]['json']['state']==json.loads(canonical_json(case))
    assert captured[0][1]['allow_redirects'] is False
    assert captured[0][1]['timeout']==(3.,15.)
    assert 'test-secret' not in result.model_dump_json()


@pytest.mark.parametrize('fault',['module','probability','sum','missing_support','non_json','unauthorized','timeout'])
def test_jev_failures_use_explicit_baseline(profile,fault):
    case=case_for(profile,[{'type':'income_multiplier','value':.55}])
    data=jev_response(case)
    if fault=='module': data['answers']['lead_module']['choice']='M99'
    if fault=='probability': data['answers']['lead_module']['confidence']=float('nan')
    if fault=='sum': data['answers']['lead_module']['probabilities']['M1']=.1
    if fault=='missing_support': del data['answers']['support_M2']
    if fault=='non_json': data=[]
    def post(*args,**kwargs):
        if fault=='timeout': raise requests.Timeout('SECRET should never reach logs')
        return FakeResponse(data,401 if fault=='unauthorized' else 200)
    result=select_plan(case,'jev',api_key='SECRET',transport=post)
    assert result.actual_backend=='rule_baseline'
    assert result.fallback_used
    assert result.api_calls==(1 if fault=='unauthorized' else 2)
    assert 'SECRET' not in result.model_dump_json()


class FakeGemini:
    def __init__(self,responses): self.responses=iter(responses); self.calls=[]; self.models=self
    def generate_content(self,**kwargs):
        self.calls.append(kwargs)
        result=next(self.responses)
        if isinstance(result,Exception): raise result
        return SimpleNamespace(text=result,model_version='fake-gemini',usage_metadata=SimpleNamespace(prompt_token_count=10,candidates_token_count=20))


def valid_selection(case):
    return PlanSelection(lead_module='M1',support_modules=[],reason_codes=['income_reduction'],rationale='Recurring inflow decreased.').model_dump_json()


def test_gemini_shared_input_and_validation(profile):
    case=case_for(profile,[{'type':'income_multiplier','value':.55}])
    client=FakeGemini([valid_selection(case)])
    result=select_plan(case,'gemini',client=client)
    assert result.actual_backend=='gemini' and not result.fallback_used
    assert result.api_calls==1
    assert json.loads(client.calls[0]['contents'])==jev_payload(case,'test')['state']
    schema = client.calls[0]['config']['response_json_schema']
    assert schema['properties']['lead_module']['enum'] == list(MODULES)
    assert schema['additionalProperties'] is False
    assert result.input_tokens==10


@pytest.mark.parametrize('bad',[ 'not json', '{"lead_module":"M99"}',
    '{"lead_module":"M1","reason_codes":["windfall"],"rationale":"Invented."}',
    '{"lead_module":"M1","support_modules":["M1"],"reason_codes":["income_reduction"],"rationale":"Duplicate."}',
])
def test_gemini_invalid_then_success(profile,bad):
    case=case_for(profile,[{'type':'income_multiplier','value':.55}])
    result=select_plan(case,'gemini',client=FakeGemini([bad,valid_selection(case)]))
    assert result.actual_backend=='gemini'
    assert result.invalid_outputs==1 and result.api_calls==2
    assert result.input_tokens==20


def test_gemini_exhausted_and_no_exception_secrets(profile):
    case=case_for(profile,[{'type':'income_multiplier','value':.55}])
    result=select_plan(case,'gemini',client=FakeGemini([RuntimeError('SECRET'),RuntimeError('SECRET')]))
    assert result.fallback_used and result.api_calls==2
    assert 'SECRET' not in result.model_dump_json()


def test_missing_keys_and_jeff_alias(profile,monkeypatch):
    monkeypatch.delenv('GEMINI_API_KEY',raising=False)
    monkeypatch.delenv('OPENROUTER_API_KEY',raising=False)
    case=case_for(profile,phase='normal')
    for name in ['gemini','jev','jeff']:
        result=select_plan(case,name)
        assert result.fallback_used and result.api_calls==0
        assert result.requested_backend==('jev' if name=='jeff' else name)


def test_unknown_details_preserved_even_if_model_omits(profile):
    case=case_for(profile,[{'type':'income_multiplier','value':.55}, {'type':'one_off_cost','value':None}])
    result=select_plan(case,'gemini',client=FakeGemini([valid_selection(case)]))
    assert result.selection.needs_clarification==case.missing_details


def test_allowed_modules_enforced_for_remote(profile):
    case=case_for(profile,[{'type':'income_multiplier','value':.55}],constraints=FinancialConstraints(allowed_modules=['M2']))
    result=select_plan(case,'gemini',client=FakeGemini([valid_selection(case)]*2))
    assert result.actual_backend=='rule_baseline'
    assert result.selection.lead_module=='M2'


def test_installed_google_sdk_accepts_config():
    from google.genai import types
    from plan_classification.backends import _gemini_config
    config=types.GenerateContentConfig(**_gemini_config('gemini-3.5-flash-lite'))
    assert config.response_json_schema['additionalProperties'] is False
    assert config.response_schema is None
    assert types.HttpOptions(timeout=15000,retry_options=types.HttpRetryOptions(attempts=1)).timeout==15000


def test_debt_relief_is_positive_opportunity(history):
    p=profile_from_history(17,history,{'status':'C','monthly_payment':200},as_of='2025-12')
    case=case_for(p,[{'type':'debt_payment_delta','value':-100, 'obligation_payment':200.,
        'obligation_source':'Explicit synthetic payment included in spending', 'payment_in_baseline':True}])
    assert select_plan(case).selection.lead_module=='M8'
    assert 'cost_reduction' in case.observed_reasons


def test_empty_optional_jev_usage_valid(profile):
    case=case_for(profile,[{'type':'income_multiplier','value':.55}])
    data=jev_response(case)
    data['usage']=None
    result=select_plan(case,'jev',api_key='test',transport=lambda *a,**k: FakeResponse(data))
    assert result.actual_backend=='jev'
    assert result.input_tokens is None


def test_whitespace_rationale_invalid():
    with pytest.raises(ValueError):
        PlanSelection(lead_module='M1',reason_codes=['income_reduction'],rationale='  ')


def test_engine_adapter_uses_global_cutoff_for_stale_account():
    monthly=engine.load_data()['monthly']
    ends=monthly.groupby('account_id').month.max()
    account_id=int(ends.loc[ends<monthly.month.max()].index[0])
    adapted=profile_from_engine(engine.know_customer(account_id))
    assert adapted==get_customer_profile(account_id)
    assert adapted.features.stale_months>0
