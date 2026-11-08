"""Read-only ETF illustrations: no cash-buffer investment or financial-engine call."""
from decimal import Decimal, ROUND_HALF_UP
import math
import pandas as pd


def cad(value):
    if isinstance(value, bool):
        raise ValueError('A monetary value cannot be a boolean')
    d=Decimal(str(value))
    if not d.is_finite() or abs(d)>Decimal('1e12'):
        raise ValueError('Unsupported monetary amount')
    return d.quantize(Decimal('.01'),rounding=ROUND_HALF_UP)


def contribution_paths(plans, crisis):
    """Unknown and zero remain distinct; use posted amounts from dated rows."""
    allocation=plans['investment_plan']
    normal=None
    if allocation.get('runtime_validation',{}).get('status')=='passed':
        n=cad(allocation['normal_monthly_allocation'])
        if n<0: raise ValueError('Normal contribution cannot be negative')
        normal=float(n)
    result={'normal_monthly':normal,'shock_monthly':None,'months':[],
            'status':'Shock contribution not established','reason':'Projection requires a passed, complete crisis plan.'}
    if crisis.get('runtime_validation',{}).get('status')!='passed': return result
    path=crisis.get('applied_plan')
    if not path or not path.get('funding_result_complete') or not crisis.get('funding_result_complete'): return result
    rows=path['schedule'][1:]
    if any(not r.get('period_complete',False) for r in rows):return result
    months=[r['month'] for r in rows]
    if not months or months!=list(range(1,len(months)+1)) or len(rows)!=path['horizon_months']:
        raise ValueError('Contribution path must contain every evaluated month exactly once')
    values=[cad(r['proposed_contribution']) for r in rows]
    if any(v<0 for v in values): raise ValueError('Negative investment contribution')
    if crisis['goal_before_crisis']['kind']=='LIQUID_RESERVE_EARMARK':
        if any(values): raise ValueError('A liquid reserve earmark cannot contain investment debits')
        reason='This goal builds liquid reserves: CAD 0.00 of new ETF contributions.'
    elif crisis['goal_before_crisis']['kind']=='PROPOSED_TRANSFER':
        reason='Conditional proposed transfers from the validated dated schedule; no trade or suitability approval.'
        if not any(values):
            reason=f"Goal status {crisis.get('goal_status','review required')}: the validated schedule has CAD 0.00 of new ETF contributions. Cash retained by pauses stays in the crisis cash plan."
    else: raise ValueError('Unknown goal kind')
    return {**result,'shock_monthly':[float(v) for v in values],'months':months,
            'status':'Modeled contribution','reason':reason}


def forward_values(monthly, horizon, move_pct=0):
    if isinstance(horizon,bool) or not isinstance(horizon,int) or not 1<=horizon<=len(monthly):
        raise ValueError('Horizon exceeds the evaluated contribution path')
    if move_pct not in (-10,0,10): raise ValueError('Choose a supported hypothetical end-of-horizon move')
    amounts=[cad(v) for v in monthly[:horizon]]
    if any(v<0 for v in amounts): raise ValueError('Contributions cannot be negative')
    cumulative=[]; total=Decimal(0)
    for v in amounts:
        total=cad(total+v);cumulative.append(float(total))
    gain=cad(total*Decimal(str(move_pct))/100)
    return {'monthly':[float(v) for v in amounts],'cumulative':cumulative,
            'contributed':float(total),'market_gain_loss':float(gain),'ending_value':float(cad(total+gain)),
            'starting_investment':0.,'timing':'One move at the end of the selected horizon'}


def historical_view(history, months, *, as_of):
    if months not in (6,12,36):raise ValueError('Unsupported historical window')
    end=pd.Timestamp(as_of).normalize()
    start=end-pd.DateOffset(months=months)
    frame=history.loc[(history['date']>=start)&(history['date']<=end)].copy()
    if len(frame)<2:raise ValueError('Fewer than two valid trading dates in this window')
    first,last=float(frame.iloc[0]['adjusted_price']),float(frame.iloc[-1]['adjusted_price'])
    frame['normalized_value']=1000.*frame['adjusted_price']/first
    if not all(math.isfinite(v) for v in frame['normalized_value']):raise ValueError('Historical normalization overflow')
    # Permit ordinary weekends/holidays without calling a complete window short.
    shortened=frame.iloc[0]['date']>start+pd.Timedelta(days=7)
    return frame,{'period_change_pct':100.*(last/first-1.),'ending_value':1000.*last/first,
        'start':frame.iloc[0]['date'].date().isoformat(),'end':frame.iloc[-1]['date'].date().isoformat(),
        'shortened':bool(shortened),'stale':frame.iloc[-1]['date']<end-pd.Timedelta(days=7)}


def monthly_replay(history, monthly_amount):
    """Today's conditional amount, synthetic adjusted-price units, calendar dates."""
    amount=cad(monthly_amount)
    if amount<0:raise ValueError('Replay contribution cannot be negative')
    if history.empty:raise ValueError('No replay history')
    first,last=history.iloc[0]['date'],history.iloc[-1]['date']
    # Anchor each scheduled date to the selected period's first trading date.
    dates=[first+pd.DateOffset(months=k) for k in range((last.year-first.year)*12+last.month-first.month+1)]
    dates=[d for d in dates if d<=last]
    units=0.;trades=[]
    for scheduled in dates:
        eligible=history.loc[history['date']>=scheduled]
        if eligible.empty:continue
        row=eligible.iloc[0];units+=float(amount)/float(row['adjusted_price'])
        trades.append({'scheduled_date':scheduled.date().isoformat(),'modeled_purchase_date':row['date'].date().isoformat(),
                       'contribution':float(amount),'adjusted_price':float(row['adjusted_price'])})
    total=cad(amount*len(trades));ending=cad(units*float(history.iloc[-1]['adjusted_price']))
    return {'trades':trades,'total_contributed':float(total),'ending_value':float(ending),
            'difference':float(cad(ending-total))}
