"""Session-local, explicit provider actions. ETF controls/cache are independent."""
import hashlib
import json
import numpy as np
import streamlit as st
from plan_classification.config import provider_identity
from tailored_advice import explain_plan
import gemini_advisor as ga


def request_identity(route, context):
    # Context can contain local identifiers/amounts, but only its digest is kept
    # here. Neither the context nor credentials go to a provider or request log.
    def scalar(value):
        if isinstance(value,np.generic):return value.item()
        raise TypeError('Unsupported provider cache context value')
    return ('provider-demo-v1',provider_identity(route),
            hashlib.sha256(json.dumps(context,sort_keys=True,allow_nan=False,default=scalar).encode()).hexdigest())


def explanation_control(crisis, account_id):
    identity=request_identity('explanation',{'account':account_id,
        'normalized_case':crisis['classification_input_hash'],'scenario':crisis['scenario_hash'],
        'facts':crisis['advice']['fingerprint'],'effective_module':crisis['lead_module']})
    result=explain_plan(crisis)
    if st.button('Use Gemini to emphasize validated findings',key='tailored_explain'):
        result=explain_plan(crisis,backend='gemini')
        st.session_state['tailored_explanation']=(identity,result)
    saved=st.session_state.get('tailored_explanation')
    if saved and isinstance(saved,tuple) and saved[0]==identity:
        result=saved[1]
    return result


def render_explanation(crisis, account_id):
    """Optional provider emphasis never replaces the accepted local facts."""
    result = explanation_control(crisis, account_id)
    st.caption('Optional explanation emphasis only. The accepted plan and cash calculations come from Python.')
    st.caption('Explanation emphasis: ' + result['actual_backend'] +
        ' · requested: ' + result['requested_backend'] + f" · API calls: {result['api_calls']}" +
        (' · local fallback: ' + result['fallback_reason'] if result['fallback_reason'] else ''))
    # Every accepted fact remains visible, including facts outside provider emphasis.
    for card_id, sentence in crisis['advice']['cards'].items():
        if card_id in result['focus_ids']:
            st.info(sentence)
        else:
            st.write(sentence)
    return result


def daily_advisor_control(inputs, *, account_id, normalized_case, scenario_hash):
    identity=request_identity('daily',{'account':account_id,'normalized_case':normalized_case,
        'scenario':scenario_hash,'replay':inputs})
    # Always provide a useful offline result on cold launch and input changes.
    result=ga.consult_gemini_advisor(**inputs,backend='local')
    if st.button('Ask Gemini to review bill timing',key='daily_advisor_run'):
        result=ga.consult_gemini_advisor(**inputs,backend='gemini')
        st.session_state['daily_advisor_result']=(identity,result)
    saved=st.session_state.get('daily_advisor_result')
    if saved and saved[0]==identity:result=saved[1]
    return result
