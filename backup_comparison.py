"""Read-only comparison of two validated paths for the same account and shock."""
from collections import Counter
from decimal import Decimal, InvalidOperation
import math
import plotly.graph_objects as go
import streamlit as st

BEFORE='Shock only'
AFTER='With supported actions'
EVIDENCE_PROMPTS = {
    'financial effects unspecified': 'Enter the cash impact and when it happens, or confirm the event has no additional cash impact.',
    'magnitude/evidence unknown': 'Confirm the amount or percentage and its source.',
    'conditional operator assumption, not verified fact': 'Verify the assumed change before relying on the result.',
    'duration unknown': 'Confirm how long the change lasts or mark it as ongoing.',
    'payment evidence belongs to another account; no relief or repayment applied':
        'Supply loan terms for the selected account. The other account’s relief and repayment are withheld.',
    'supplied loan payment lacks source/baseline inclusion; relief not applied':
        'Provide the loan-payment source and confirm that the payment is already included in normal spending.',
    'loan payment unknown; supply sourced payment included in spending; relief not applied':
        'Provide the loan payment amount and source, and confirm it is included in normal spending.',
    'loan payment inclusion in baseline spending unknown; relief not applied':
        'Confirm how much of the loan payment is already included in normal spending.',
    'deferred loan obligation unresolved; repayment not established':
        'Confirm the deferred repayment amount and due month.',
    'deferred repayment beyond horizon remains owed':
        'The deferred repayment is still owed. Extend the projection to include its due month.',
    'payment_delay_days needs dated events or asset/settlement evidence; not applied to cash':
        'Identify the specific payment and confirm its current and proposed dates.',
    'investment_return needs dated events or asset/settlement evidence; not applied to cash':
        'Identify the holding and when the proceeds would become accessible cash.',
}
PAUSE_EXCLUSIONS = {
    'outside_horizon': 'The payment is scheduled beyond this projection.',
    'fee_consumes_benefit': 'The pause fee is at least as large as the payment.',
    'projection_incomplete': 'Resolve the missing scenario details before relying on a pause.',
    'advances_shortfall_or_worsens_gap': 'The pause would move the shortage earlier or increase the funding need.',
    'no_shortfall_or_reserve_purpose': 'The modeled pause does not improve the shortage or protect the reserve.',
}


def _money(value):
    if isinstance(value,bool):raise ValueError('Cash cannot be a boolean')
    try:d=Decimal(str(value))
    except (InvalidOperation,ValueError,TypeError) as exc:raise ValueError('Cash must be numeric posted CAD cents') from exc
    if not d.is_finite() or abs(d)>Decimal('1e12') or d!=d.quantize(Decimal('.01')):
        raise ValueError('Cash must be finite posted CAD cents')
    return d


def _cad(value):return f'CAD {value:,.2f}'


def _point_label(point):
    return f"Month {point['month']} ({point['phase']})" if point else None


def _evidence_notes(crisis, left, right):
    effect_numbers = {
        effect['effect_id'] or f'effect-{number}': number
        for number, effect in enumerate(crisis['scenario']['effects'], 1)
    }
    notes = []
    for issue in dict.fromkeys(left['unresolved_effects'] + right['unresolved_effects']):
        identity, _, reason = issue.rpartition(': ')
        if reason in EVIDENCE_PROMPTS and identity in effect_numbers:
            notes.append(f"Event {effect_numbers[identity]} · {EVIDENCE_PROMPTS[reason]}")
        elif issue.startswith('Income after temporary reduction ends'):
            notes.append('Confirm the new income amount and when it starts after the temporary reduction ends.')
        else:
            notes.append(issue)
    return notes


def _pause_exclusion(decision, transfer):
    reason = decision['reason']
    if reason == 'evidence_incomplete':
        missing = []
        if not transfer['included_in_baseline']:
            missing.append('whether the payment is already included in normal spending')
        if not transfer['pause_approved']:
            missing.append('permission to pause it')
        if transfer['pause_fee'] is None:
            missing.append('the pause fee, including zero if confirmed')
        return f"Confirm {' and '.join(missing)}."
    return PAUSE_EXCLUSIONS.get(reason, 'Review the payment decision and its supporting evidence.')


def _checked_path(path):
    if not isinstance(path,dict):raise ValueError('A validated cash path is unavailable')
    horizon=path['horizon_months']
    if isinstance(horizon,bool) or not isinstance(horizon,int) or not 1<=horizon<=120:
        raise ValueError('Invalid projection horizon')
    expected=[(m,phase) for m in range(horizon+1) for phase in ('start','end')]
    points=path['checkpoints']
    if any(type(p['month']) is not int for p in points) or [(p['month'],p['phase']) for p in points]!=expected:
        raise ValueError('Monthly start/end checkpoints must be complete, unique and ordered')
    values=[_money(p['cash']) for p in points]
    first=next((p for p in points if _money(p['cash'])<0),None)
    gap=max(Decimal(0),-min(values))
    if (path['first_shortfall_month']!=(first['month'] if first else None)
        or path['first_shortfall_phase']!=(first['phase'] if first else None)
        or _money(path['additional_cash_needed'])!=gap
        or _money(path['ending_cash'])!=values[-1]
        or _money(path['minimum_cash'])!=min(values)):
        raise ValueError('Displayed cash facts do not reconcile with source checkpoints')
    complete=path['funding_result_complete']
    if type(complete) is not bool:raise ValueError('Funding completeness must be explicit')
    full=path['full_funding_need']
    if (complete and (full is None or _money(full)!=gap)) or (not complete and full is not None):
        raise ValueError('A partial path cannot establish the full funding need')
    return {'points':points,'first':first,'gap':float(gap),'full_need':float(gap) if complete else None,
            'complete':complete,'ending_cash':float(values[-1]),'minimum_cash':path['minimum_cash'],
            'schedule':path['schedule']}


def build_comparison(crisis):
    """No engine call, changed contribution, inferred action or balance mutation."""
    if crisis.get('runtime_validation',{}).get('status')!='passed' or crisis['runtime_validation'].get('enforced') is not True:
        raise ValueError('Financial runtime validation must pass before comparing paths')
    left,right=crisis['no_action'],crisis['applied_plan']
    before,after=_checked_path(left),_checked_path(right)
    for name in ('horizon_months','scenario_hash','opening_cash','opening_basis'):
        if left[name]!=right[name]:raise ValueError('Both paths must use the same scenario, horizon and opening basis')
    if left['scenario_hash']!=crisis['scenario_hash'] or left['horizon_months']!=crisis['scenario']['horizon_months']:
        raise ValueError('Paths do not match the selected scenario')
    complete=before['complete'] and after['complete'] and crisis['funding_result_complete']
    identical=all(a['cash']==b['cash'] for a,b in zip(before['points'],after['points'],strict=True))
    selected=set(crisis['applied_transfer_ids'])
    records={t['event_id']: t for t in crisis['existing_transfers']}
    if not selected <= records.keys():raise ValueError('Applied payment evidence is missing')
    gross=sum((_money(r['paused_existing_outflow']) for r in right['schedule']),Decimal(0))
    fees=_money(crisis['applied_pause_fees'])
    proposed=sum((_money(r['proposed_contribution']) for r in right['schedule']),Decimal(0))
    actions=[]
    if selected:
        actions.append(f"{len(selected)} supported transfer pauses retain {_cad(gross)} before {_cad(fees)} of fees ({_cad(gross-fees)} net).")
    if proposed:
        actions.append(f"The revised plan includes {_cad(proposed)} of proposed new transfers across the evaluated months; those transfers leave bill-paying cash.")
    if crisis['goal_before_crisis']['kind']=='LIQUID_RESERVE_EARMARK':
        actions.append('Reserve earmarks remain liquid; changing an earmark creates no extra cash.')
    elif crisis['goal_contribution_before']>crisis['goal_contribution_revised']:
        actions.append(f"The future contribution proposal changes from {_cad(crisis['goal_contribution_before'])} to {_cad(crisis['goal_contribution_revised'])} per month. Pausing a proposal adds CAD 0.00 to the no-new-action path because it was outside normal spending.")
    if not selected:
        if records:
            actions.append('No existing-transfer pause is applied.')
        else:actions.append('No evidenced existing-transfer schedule is supplied; no pause relief is credited.')
    exclusions = Counter(
        _pause_exclusion(decision, records[decision['event_id']])
        for decision in crisis['pause_decisions'] if decision['status'] == 'excluded'
    )
    for explanation, count in exclusions.items():
        label = 'payment' if count == 1 else 'payments'
        actions.append(f"{count} scheduled {label} left unchanged. {explanation}")
    if identical:actions.insert(0,'The two cash paths are identical. The revised plan posts no net cash change relative to taking no new action.')
    if complete:
        b,a=_point_label(before['first']),_point_label(after['first'])
        if b and a:
            timing=f"First shortfall {'remains at '+b if b==a else 'moves from '+b+' to '+a}."
        elif b:timing=f'First shortfall without action: {b}. The revised path stays nonnegative at the monthly checkpoints.'
        elif a:timing=f'No shortfall without a new action; the revised path first goes negative in {a}.'
        else:timing='Cash stays at or above $0 across modeled checkpoints.'
        improvement = round(before['gap'] - after['gap'], 2)
        if improvement > 0:
            funding=f"The modeled revised plan reduces the funding gap from {_cad(before['gap'])} to {_cad(after['gap'])}, a decrease of {_cad(improvement)}."
        elif improvement < 0:
            funding=f"The modeled revised plan increases the funding gap from {_cad(before['gap'])} to {_cad(after['gap'])}, an increase of {_cad(-improvement)}."
        else:funding=f"The funding gap is unchanged at {_cad(after['gap'])}."
        summary=timing+' '+funding
    else:
        summary='Partial projection · Known components. Missing evidence can change the shortfall and required cash. Full funding need: Not established.'
    pending = list(dict.fromkeys(
        (effect['type'], effect['start_month'])
        for effect in left['pending_effects'] + right['pending_effects']
        if effect['start_month'] is not None and effect['start_month'] > left['horizon_months']
    ))
    return {'before':before,'after':after,'complete':bool(complete),'identical':identical,
            'summary':summary,'actions':actions,'gross_pause':float(gross),'pause_fees':float(fees),
            'funding_improvement':before['gap']-after['gap'],'horizon':left['horizon_months'],
            'opening_basis':left['opening_basis'], 'pending':pending,
            'evidence_notes':_evidence_notes(crisis, left, right)}


def safe_mode_status(crisis, view):
    # Reflect the existing guarded decision; never change contributions or cash.
    if not view['complete'] or crisis['goal_status'] in ('REVIEW_REQUIRED','BASELINE_REVIEW_REQUIRED'):
        return ('Review required','Incomplete evidence or an existing goal review prevents an unrestricted contribution conclusion.')
    if crisis['goal_status'] in ('PAUSED','REDUCED','EXISTING_TRANSFERS_PAUSED') or view['after']['gap']>0:
        return ('Modeled liquidity protection','Follow the engine’s revised contribution and supported pause decisions. Any remaining cash requirement is shown below.')
    return ('No additional restriction established','The current engine result does not call for an additional contribution restriction in this scenario; investment suitability remains separate.')


def _posted_events(row, phase):
    if phase == 'end':
        events = (
            ('Paused existing outflow retained', row['paused_existing_outflow']),
            ('Proposed transfer out', row['proposed_contribution']),
        )
    else:
        repayment = row.get('deferred_repayment', 0.)
        events = (
            ('One-off receipt', row['one_off_receipt']),
            ('One-off cost', round(row['one_off_cost'] - repayment, 2)),
            ('Deferred loan repayment', repayment),
            ('Action fee', row['action_fees']),
        )
    return ''.join(f'<br>{label}: {_cad(amount)}' for label, amount in events if amount)


def comparison_figure(view):
    fig=go.Figure()
    all_cash=[]
    # The wider dashed trace stays visible behind the solid trace where cash paths overlap.
    for key, name, color, dash, width in (
        ('before', BEFORE, '#2563eb', 'dash', 5),
        ('after', AFTER, '#b45309', 'solid', 2.5),
    ):
        path=view[key];points=path['points'];all_cash.extend(p['cash'] for p in points)
        schedule = {row['month']: row for row in path['schedule']}
        labels, sizes, symbols = [], [], []
        for point in points:
            month, phase = point['month'], point['phase']
            posted = _posted_events(schedule[month], phase)
            labels.append([month, phase, posted])
            if point == path['first']:
                sizes.append(12)
                symbols.append('diamond-open')
            else:
                sizes.append(9 if posted else 4)
                symbols.append('circle-open' if posted else 'circle')
        fig.add_trace(go.Scatter(x=[p['month']*2+(p['phase']=='end') for p in points],y=[p['cash'] for p in points],
            mode='lines+markers',name=name,line=dict(color=color,dash=dash,width=width),
            marker=dict(symbol=symbols,size=sizes),customdata=labels,
            hovertemplate=('Month %{customdata[0]} (%{customdata[1]})<br>'
                + ('Accessible cash' if view['complete'] else 'Known components')
                + ': CAD %{y:,.2f}%{customdata[2]}<extra>%{fullData.name}</extra>')))
    first_b,first_a=view['before']['first'],view['after']['first']
    common=first_b is not None and first_b==first_a
    for point,label,color,offset in [(first_b,'Both paths' if common else BEFORE,'#2563eb',-65),
                                     (None if common else first_a,AFTER,'#b45309',65)]:
        if point is not None:
            fig.add_annotation(x=point['month']*2+(point['phase']=='end'),y=point['cash'],
                text=f"{label}<br>M{point['month']} {point['phase']}",
                showarrow=True,arrowhead=2,ax=0,ay=offset,bgcolor='white',bordercolor=color,font=dict(color=color))
    fig.add_hline(y=0,line_dash='dot',line_color='#374151',annotation_text='CAD 0',annotation_position='bottom right')
    step=max(1,math.ceil(view['horizon']/6))
    months=set(range(0,view['horizon']+1,step))|{view['horizon']}
    months.update(p['month'] for p in (first_b,first_a) if p is not None)
    low,high=min(0,*all_cash),max(0,*all_cash);padding=max(50.,(high-low)*.1)
    fig.update_layout(title='Cash by checkpoint' if view['complete'] else 'Known components',
        xaxis=dict(title='Modeled month',tickvals=[m*2 for m in sorted(months)],
                   ticktext=[f'M{m}' for m in sorted(months)],automargin=True),
        yaxis=dict(title='Accessible cash (CAD)',range=[low-padding,high+padding],tickprefix='$',
                   separatethousands=True,automargin=True),
        legend=dict(orientation='h',y=1.08,yanchor='bottom',x=0),
        height=380,margin=dict(t=96,b=55,l=48,r=14))
    return fig


def render_backup_comparison(crisis):
    try:view=build_comparison(crisis)
    except (ValueError,KeyError,TypeError) as exc:
        st.error(f'Cash comparison unavailable: {exc}. No comparison or funding conclusion is issued.')
        return
    mode, reason = safe_mode_status(crisis, view)
    st.info('Financial Safe Mode · ' + mode + '. ' + reason)
    st.caption('Planning status only: the existing engine determines amounts; no account setting or banking instruction is changed.')
    st.markdown('#### Analyst summary · impact of the modeled revised plan')
    columns=st.columns(2)
    for col,key,label in [(columns[0],'before','without new action'),(columns[1],'after','revised plan')]:
        first=view[key]['first']
        value=_point_label(first) or ('None at checkpoints' if view['complete'] else 'Not established')
        col.metric(('First shortfall' if view['complete'] else 'First shortfall · Known components')+' · '+label,value)
        need=view[key]['full_need'] if view['complete'] else None
        col.metric('Extra cash needed · '+label,'Not established' if need is None else _cad(need))
        prefix = '' if view['complete'] else 'Known components · '
        col.caption(f"{prefix}Lowest modeled cash: {_cad(view[key]['minimum_cash'])}")
        col.caption(f"{prefix}Ending cash: {_cad(view[key]['ending_cash'])}")
    if not view['complete']:st.warning(view['summary'])
    else:st.write(view['summary'])
    if not view['complete']:
        st.caption(f"Known components · extra cash: {_cad(view['before']['gap'])} without new action and {_cad(view['after']['gap'])} under the revised plan.")
        if view['evidence_notes']:
            st.markdown('**What to confirm**')
            for note in view['evidence_notes']:
                st.write(note)
    for kind, month in view['pending']:
        st.caption(f"Scheduled for Month {month}: {kind.replace('_', ' ')}. This falls outside the {view['horizon']}-month chart.")
    for action in view['actions']:st.write(action)
    st.plotly_chart(comparison_figure(view),key='backup_cash_comparison',width='stretch')
    st.caption(f"Monthly projection · opening basis: {view['opening_basis']}. Both lines use the same account and selected shock. Lines connect start/end checkpoints; they do not establish daily or intramonth solvency. No banking instruction is executed.")
    st.caption('Open circles mark posted cash changes. A diamond marks the first shortfall. Hover for the exact start or end checkpoint, cash, and any posted events.')
    st.markdown('**Next analyst review**')
    for condition in crisis['next_review_conditions']:st.caption(condition)
    return view
