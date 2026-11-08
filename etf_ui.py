"""Allocation Review fragment: market selection never invokes the finance engine."""
from datetime import datetime, timezone
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from etf_calculations import contribution_paths,forward_values,historical_view,monthly_replay
from etf_demo import CASES,demo_fit
from etf_market import CATALOG,SYMBOLS,MarketUnavailable,get_history


def dollars(v):return f'${v:,.2f}'


def _forward(plans,crisis):
    st.markdown('#### Selected account · Contribution outlook')
    st.caption('Modeled contribution · conditional capacity · Fit review required for the real account. Starting investment: CAD 0.00; the bank cash buffer is excluded.')
    try:paths=contribution_paths(plans,crisis)
    except (ValueError,KeyError) as exc:
        st.warning(f'Contribution outlook unavailable: {exc}')
        return
    available=min(6,int(crisis.get('scenario',{}).get('horizon_months',6)))
    if paths['months']:available=min(available,len(paths['months']))
    horizons=sorted({1,available}|{m for m in (3,6) if m<=available})
    if st.session_state.get('etf_forward_horizon') not in horizons:
        st.session_state['etf_forward_horizon']=available
    horizon=st.select_slider('Evaluated contribution horizon (months)',options=horizons,key='etf_forward_horizon') if len(horizons)>1 else available
    move=st.selectbox('Hypothetical single market move at the END of the selected horizon (%)',[-10,0,10],index=1,key='etf_market_move')
    st.caption('The same end-of-horizon move applies to both illustrations. Historical ETF returns never set this input. Investment value is separate from cash available for bills.')
    figure=go.Figure();results=[]
    for label,values in [('Normal plan',None if paths['normal_monthly'] is None else [paths['normal_monthly']]*available),
                         ('After selected shock',paths['shock_monthly'])]:
        if values is None:
            st.info(('Shock contribution not established. '+paths['reason']) if label=='After selected shock' else 'Normal contribution not established.')
            continue
        try:r=forward_values(values,horizon,move)
        except ValueError as exc:
            st.warning(str(exc));continue
        figure.add_trace(go.Scatter(x=list(range(horizon+1)),y=[0.]+r['cumulative'],mode='lines+markers',name=label))
        results.append({'Path':label,'Contributed (CAD)':r['contributed'],'Illustrative market gain/loss (CAD)':r['market_gain_loss'],'Ending investment value (CAD)':r['ending_value']})
        st.metric('Normal contributed' if label=='Normal plan' else 'Shock contributed',dollars(r['contributed']))
    st.caption(paths['reason'])
    if results:
        figure.update_layout(title='Modeled contribution · cumulative CAD (before hypothetical market move)',xaxis_title='Evaluated month',yaxis_title='Cumulative contributions (CAD)',height=310)
        st.plotly_chart(figure,key='etf_forward_chart',width='stretch')
        st.dataframe(pd.DataFrame(results),hide_index=True,width='stretch')


@st.fragment
def render_etf_explorer(plans,crisis):
    st.subheader('Investment what-if')
    st.markdown('#### Demo portfolios · Synthetic case')
    case_name=st.selectbox('Synthetic example (independent of selected account)',list(CASES),key='etf_demo_case')
    case=CASES[case_name]
    st.caption(f"Simulated portfolio · invented demonstration profiles. Supplied example: {case['goal']}, {case['years']} years, {'moderate' if case['risk']==1 else 'low'} risk tolerance and loss capacity. Reserve and liquidity needs are assumed covered ONLY for this synthetic example.")
    eligible,excluded=demo_fit(case_name)
    for rank,p in enumerate(eligible,1):
        with st.container(border=True):
            st.markdown(f"**{rank}. {p['name']} · {'Closest fit under this example’s rules' if rank==1 else 'Eligible example'}**")
            st.caption('Simulated portfolio')
            st.write('Why it appears: '+p['why'])
    for p in excluded:
        st.write(f"**{p['name']} · Outside the example’s limits**")
        st.caption('Simulated portfolio · '+p['why'])
    with st.expander('Simulated returns · teaching inputs, not portfolio forecasts'):
        fig=go.Figure(go.Bar(x=['−10%','0%','+10%'],y=[2160,2400,2640]))
        fig.update_layout(title='Simulated portfolio · one-time move on hypothetical CAD 2,400',yaxis_title='Illustrative value (CAD)',height=270)
        st.plotly_chart(fig,key='etf_demo_chart',width='stretch')
        st.caption('These teaching percentages apply equally to every fictional profile. They are not estimated returns or synthetic fund histories.')
    st.divider()
    st.markdown('#### Market snapshot · Real ETFs')
    st.markdown('**'+CATALOG['label']+'**')
    st.caption(f"Market data · {CATALOG['peer_group']}. Catalog date: {CATALOG['snapshot_date']}. {CATALOG['selection_method']}")
    for entry in CATALOG['entries']:
        st.write(f"**{entry['symbol']} · {entry['name']}**")
        st.caption(entry['inclusion_reason'])
        st.markdown(f"[Issuer source]({entry['source_url']}) · {entry['currency']} · Catalog record {entry['data_date']}")
    st.caption('Fund net assets and trailing one-year total returns: not established. The catalog is identical for every account and shock. History is Yahoo adjusted-price data, separate from issuer NAV-based returns.')
    symbol=st.selectbox('ETF to explore',SYMBOLS,key='etf_symbol')
    today=pd.Timestamp(datetime.now(timezone.utc).date())
    start=(today-pd.DateOffset(years=3)-pd.Timedelta(days=7)).date().isoformat()
    end=(today+pd.Timedelta(days=1)).date().isoformat()
    # Public history lives in session memory; changing account/shock cannot fetch.
    loaded=st.session_state.setdefault('etf_loaded_histories',{})
    errors=st.session_state.setdefault('etf_history_errors',{})
    if st.button('Show ETF history',key='etf_show_history'):
        try:
            with st.spinner('Loading public adjusted-price history…'):
                frame=get_history(symbol,start,end)
            loaded[symbol]={'frame':frame,'as_of':today.date().isoformat(),'requested_start':start,'requested_end':end,
                            'fetched_at':datetime.now(timezone.utc).isoformat()}
            errors.pop(symbol,None)
        except (MarketUnavailable,ValueError) as exc:
            errors[symbol]=str(exc)
    if symbol in errors:
        st.warning(errors[symbol])
        if symbol in loaded:st.info('Showing the last successful session result; its retrieval and last trading dates are shown below.')
    record=loaded.get(symbol)
    if record:
        st.markdown('#### Historical performance · Yahoo adjusted prices')
        months=st.selectbox('Historical display window',[6,12,36],index=1,format_func=lambda m:{6:'6 months',12:'1 year',36:'3 years'}[m],key='etf_history_months')
        try:
            view,summary=historical_view(record['frame'],months,as_of=today)
            st.caption(f"Market data · {symbol} · CAD · Yahoo Finance via yfinance. Actual available dates: {summary['start']} to {summary['end']}. Retrieved {record['fetched_at']}.")
            if summary['shortened']:st.warning('Shortened historical window: full requested history is unavailable. Only the actual available range is shown.')
            if summary['stale']:st.warning('Market history is stale: the last available trading date is more than seven days before the display date.')
            if record['frame'].attrs.get('discarded_rows') or record['frame'].attrs.get('duplicate_dates'):
                st.caption(f"Cleaning: {record['frame'].attrs.get('discarded_rows',0)} invalid rows removed; {record['frame'].attrs.get('duplicate_dates',0)} identical duplicate dates collapsed.")
            fig=go.Figure(go.Scatter(x=view['date'],y=view['normalized_value'],mode='lines',name=symbol))
            fig.update_layout(title=f'Market data · {symbol} · CAD 1,000 rebased adjusted-price illustration',xaxis_title='Trading date',yaxis_title='Normalized value (CAD)',height=330)
            st.plotly_chart(fig,key='etf_history_chart',width='stretch')
            st.metric('Historical illustration ending value',dollars(summary['ending_value']))
            st.metric('Historical adjusted-price change',f"{summary['period_change_pct']:.2f}%")
            st.caption('Illustration from adjusted closing prices. Issuer NAV-based total return may differ. Historical performance does not set future returns or establish account suitability.')
            if st.checkbox('Show hypothetical historical monthly-contribution replay',key='etf_replay'):
                paths=contribution_paths(plans,crisis)
                if paths['normal_monthly'] is None:st.info('Normal contribution is not established; replay unavailable.')
                else:
                    replay=monthly_replay(view,paths['normal_monthly'])
                    st.caption(f"Hypothetical replay · today’s conditional normal amount {dollars(paths['normal_monthly'])}/month. Dates anchored to the first displayed trading date, with month-end clipping; purchase on the first available trading date on/after each scheduled date. Synthetic adjusted-price units; excludes personal taxes and trading costs. These are not actual past account trades or holdings.")
                    st.dataframe(pd.DataFrame([{k:v for k,v in replay.items() if k!='trades'}]),hide_index=True)
                    st.dataframe(pd.DataFrame(replay['trades']),hide_index=True)
        except ValueError as exc:st.warning(f'Historical view unavailable: {exc}')
    else:
        st.info('No history is available for this symbol. The local contribution outlook remains usable; retry Show ETF history when provider access is available.' if symbol in errors else 'Choose an ETF and select Show ETF history. No market request is made until then; the local contribution outlook below works offline.')
    _forward(plans,crisis)
