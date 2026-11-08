"""Retrospective finance arithmetic from raw inputs; no application imports.

Run --prepare BEFORE the fresh observed export, then run without arguments.
This does not replace the finance reviewer's pre-existing independent workbook.
"""
import argparse
from collections import defaultdict
import csv
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_EVEN
import json
from pathlib import Path
from statistics import median
import subprocess

OUT=Path(__file__).resolve().parent
ROOT=OUT.parent
D=Decimal
CENT=D('.01')
def cents(v): return D(str(v)).quantize(CENT,rounding=ROUND_HALF_EVEN)
def save(name,value): (OUT/name).write_text(json.dumps(value,indent=2,default=str)+'\n')
def table(name,rows):
    fields=list(dict.fromkeys(k for r in rows for k in r))
    with (OUT/name).open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,lineterminator='\n');w.writeheader();w.writerows(rows)
def csv_rows(name): return list(csv.DictReader((OUT/name).open()))
def load(name): return json.loads((OUT/name).read_text())

def daily_expectations(history):
    daily=defaultdict(lambda:defaultdict(lambda:D(0)))
    past_bills=defaultdict(list); replay_bills=defaultdict(list)
    have_tx=set();invalid=set()
    start,end=date(2025,7,1),date(2025,12,31)
    with (ROOT/'data/transactions.csv').open() as f:
        for row in csv.DictReader(f):
            aid=int(row['account_id']);have_tx.add(aid)
            day=date.fromisoformat(row['date'][:10]);v=D(row['signed_amount'])
            if start<=day<=end and not v.is_finite(): invalid.add(aid);continue
            bill=row['purpose']=='household bills' and v<0
            key=(aid,row['partner_bank'],row['partner_account'])
            if bill and date(2025,1,1)<=day<start and key[1] and key[2] not in ['', '0', '0.0']:
                past_bills[key].append((day,v))
            if start<=day<=end:
                daily[aid][day]+=v*D('.55') if v>0 else v*(D('1.15') if bill else 1)
                if bill: replay_bills[key].append((day,v))
    days=[start+timedelta(days=i) for i in range((end-start).days+1)]
    months={f'2025-{m:02}' for m in range(7,13)}
    results=[]
    for aid, hist in sorted(history.items()):
        prior=sorted((m,v) for m,v in hist if m<'2025-07')[-6:]
        if not prior or not months.issubset({m for m,v in hist}) or aid not in have_tx or aid in invalid:
            continue
        if not all(v.is_finite() for m,v in prior):continue
        opening=sum((v for m,v in prior),D(0))/len(prior)
        cash=opening;values=[];closing={}
        for day in days:
            cash+=daily[aid][day];values.append(cents(cash));closing[day.month]=cents(cash)
        clear=cents(opening)>=0 and all(v>=0 for v in closing.values())
        hidden=clear and min(values)<0
        eligible=False;resolved=False;after_min=None;month_delta=None;chosen=None
        if hidden:
            options=[]
            for key, payments in past_bills.items():
                if key[0]!=aid:continue
                ds=[d.day for d,v in payments]
                if len(payments)==6 and len({d.month for d,v in payments})==6 and max(ds)-min(ds)<=2:
                    options.append((median([v for d,v in payments]),key))
            if options:
                chosen=min(options)[1];payments=replay_bills[chosen]
                eligible=(len(payments)==6 and len({d.month for d,v in payments})==6
                          and all((d+timedelta(days=7)).month==d.month and d+timedelta(days=7)<=end for d,v in payments))
                if eligible:
                    changes=defaultdict(lambda:D(0))
                    for day,v in payments:
                        changes[day]-=v*D('1.15');changes[day+timedelta(days=7)]+=v*D('1.15')
                    cash=opening;after=[];after_closing={}
                    for day in days:
                        cash+=daily[aid][day]+changes[day];after.append(cents(cash));after_closing[day.month]=cents(cash)
                    resolved=min(after)>=0;after_min=min(after)
                    month_delta=max(abs(after_closing[m]-closing[m]) for m in closing)
        results.append(dict(account_id=aid,opening_proxy=opening,nonnegative_month_ends=clear,
            hidden_shortfall=hidden,qualifying_bill_shift=eligible,shortfall_eliminated=resolved,
            before_minimum=min(values),after_minimum=after_min,month_end_balance_delta=month_delta,
            selected_bill_bank=chosen[1] if chosen and eligible else None,
            selected_bill_account=chosen[2] if chosen and eligible else None))
    table('daily_independent_account_evidence.csv',results)
    total=len(results);hidden=sum(r['hidden_shortfall'] for r in results)
    candidates=sum(r['qualifying_bill_shift'] for r in results);resolved=sum(r['shortfall_eliminated'] for r in results)
    return dict(total_accounts=total,nonnegative_month_end_accounts=sum(r['nonnegative_month_ends'] for r in results),
        intra_month_overdrafts=hidden,accounts_with_movable_bill=candidates,overdrafts_resolved_by_shift=resolved,
        resolution_rate_pct=round(D(100)*resolved/candidates,1) if candidates else D(0),
        month_end_balance_delta=max((r['month_end_balance_delta'] for r in results if r['month_end_balance_delta'] is not None),default=D(0)))

def prepare():
    history=defaultdict(list);selected=defaultdict(list)
    with (ROOT/'data/monthly_summary.csv').open() as f:
        for row in csv.DictReader(f):
            aid=int(row['account_id']);history[aid].append((row['month'],D(row['avg_daily_balance'])))
            if aid in [22812,20111]:selected[aid].append(row)
    loans=defaultdict(list)
    with (ROOT/'data/loans.csv').open() as f:
        for row in csv.DictReader(f):loans[int(row['account_id'])].append(row)
    metrics={};shocks=[];input_rows=[]
    for aid,rows in selected.items():
        rows.sort(key=lambda r:r['month'])
        for r in rows:
            if not all(D(r[k]).is_finite() for k in ['money_in','money_out','avg_daily_balance','household_bills','insurance','loan_payments']):
                raise ValueError(f'Nonfinite source for {aid}')
        if len({r['month'] for r in rows})!=len(rows):raise ValueError('Duplicate account-month')
        loan=loans[aid]
        if len(loan)>1:raise ValueError('Ambiguous loan rows')
        med=lambda k:median([D(r[k]) for r in rows])
        v=dict(I=med('money_in'),S=med('money_out'),H=med('household_bills'),
            F=median([sum((D(r[k]) for k in ['household_bills','insurance','loan_payments']),D(0)) for r in rows]),
            B=sum((D(r['avg_daily_balance']) for r in rows[-6:]),D(0))/len(rows[-6:]),
            P=D(loan[0]['monthly_payment']) if loan and loan[0]['status'] in ['C','D'] else D(0))
        metrics[str(aid)]=v
        input_rows.append(dict(case=f'Account {aid}',source='Local monthly_summary.csv and loans.csv',
            units='CAD',horizon='All observed months; last six for B',monthly_rows=len(rows),
            B_months=';'.join(r['month'] for r in rows[-6:]),loan_status=loan[0]['status'] if loan else 'NO_LOAN',**v))
        for name,mult,pct,cost in [('Job loss',D('.55'),D(0),D(0)),('Furnace repair',D(1),D(0),v['S']),('Combined shock',D('.55'),D('.15'),D(0))]:
            income=mult*v['I'];spending=v['S']+pct*v['H'];buffer=v['B']-cost;gap=spending-income
            raw=D(0) if buffer<=0 else ('no shortfall (120+)' if gap<=0 else min(buffer/gap,D(120)))
            rounded=raw if isinstance(raw,str) else raw.quantize(D('.1'),rounding=ROUND_HALF_EVEN)
            shocks.append(dict(account_id=aid,scenario=name,post_shock_income=income,
                post_shock_monthly_spending=spending,one_time_expense=cost,remaining_buffer=buffer,
                monthly_funding_gap=gap,official_runway_before_rounding=raw,official_runway_rounded=rounded))
    ledger=[];summaries=[]
    cases=[('A','No intervention',3000,1650,2460,1500,False,True),
        ('A','Pause future proposed investment',3000,1650,2460,1500,False,True),
        ('A','Pause approved existing outflow',3000,1650,2460,1500,True,True),
        ('B','Start Month 3 receipt',1000,1800,2400,0,False,True),
        ('C','Original payments',300,2200,2400,0,False,True),
        ('C','Approved deferral',300,2200,2400,0,False,True),
        ('C','Deferral without baseline evidence',300,2200,2400,0,False,False),
        ('E','Income changes; synthetic baseline from Case A',3000,None,2400,0,False,False)]
    for case,path,cash,income,spending,repair,pause,complete in cases:
        input_rows.append(dict(case=case,path=path,source='Team PDF Phase 1 p3; E explicitly reuses A baseline',
            units='CAD',horizon='6 months',opening_cash=cash,post_shock_income=income,post_shock_spending=spending,
            immediate_repair=repair,pause_existing=pause,evidence='Synthetic; unknown income/deferral inclusion remains unknown where specified'))
        cash=D(cash);points=[]
        for m in range(7):
            receipt=D(2000) if case=='B' and m==3 else D(0)
            cost=D(repair) if m==0 else D(0)
            repayment=D(650) if case=='C' and path=='Approved deferral' and m==4 else D(0)
            spend=D(spending)-(D(300) if case=='C' and path=='Approved deferral' and m in [1,2] else D(0)) if m else D(0)
            incoming=D(income) if income is not None and m else D(0)
            action=D(300) if m and pause else D(0)
            for phase in ['start','end']:
                before=cash
                if phase=='start':cash+=receipt-cost-repayment
                else:cash+=incoming-spend+action
                row=dict(case=case,path=path,month=m,engine_phase=phase,opening_cash=before,
                    one_time_receipt=receipt if phase=='start' else D(0),one_time_expense=cost if phase=='start' else D(0),
                    income=(None if case=='E' and m else incoming) if phase=='end' else D(0),
                    spending=spend if phase=='end' else D(0),action_cash_effect=action if phase=='end' else D(0),
                    fees=D(0),repayments=repayment if phase=='start' else D(0),closing_accessible_cash=cash)
                points.append(row);ledger.append(row)
        negative=next((r for r in points if r['closing_accessible_cash']<0),None)
        minimum=min(r['closing_accessible_cash'] for r in points);needed=max(D(0),-minimum)
        summaries.append(dict(case=case,path=path,first_negative_month=negative['month'] if negative else None,
            first_negative_phase=negative['engine_phase'].title() if negative else None,
            first_negative_shortfall=-negative['closing_accessible_cash'] if negative else None,
            lowest_accessible_cash=minimum,additional_starting_cash_known_components=needed,
            complete_shock_funding_requirement=needed if complete else None,complete=complete,
            cash_needed_before_receipt=max(D(0),-min(r['closing_accessible_cash'] for r in points if r['month']<3)) if case=='B' else None))
    expected=dict(calculated_at=datetime.now(timezone.utc).isoformat(),
        method='Standalone Decimal arithmetic from raw CSVs and PDF; no engine imports. Retrospective check, not blind review.',
        formulas=dict(I='median(money_in)',S='median(money_out)',H='median(household_bills)',
            F='median(household_bills + insurance + loan_payments for each month)',B='mean(last 6 chronological avg_daily_balance)',
            P='running C/D monthly payment else zero',checkpoint='opening + receipt - cost + income - spending + action - fees - repayments',
            funding='max(0,-minimum accessible cash); full amount unknown for incomplete effects'),
        metrics=metrics,shocks=shocks,summaries=summaries,daily=daily_expectations(history))
    expected['runway_boundaries']=[]
    for b,g in [(0,100),(-1,-1),(100,0),(100,-5),(12000,1),(60,D('.5')),(5,3)]:
        raw=D(0) if b<=0 else ('no shortfall (120+)' if g<=0 else min(D(b)/D(g),D(120)))
        expected['runway_boundaries'].append(raw if isinstance(raw,str) else raw.quantize(D('.1')))
    save('finance_expected.json',expected)
    table('finance_inputs.csv',input_rows);table('synthetic_expected_checkpoints.csv',ledger)
    table('synthetic_expected_summaries.csv',summaries)
    print('Standalone expectations prepared from raw inputs; pending human finance review.')

def compare():
    expected=load('finance_expected.json');findings=[]
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    def check(group,case,metric,want,got,rule='exact',where=''):
        if want is None:match=got is None or got==''
        elif rule=='money':match=got is not None and got!='' and cents(want)==cents(got)
        elif rule=='raw':
            try:match=abs(D(str(want))-D(str(got)))<=D('0.000000001')
            except Exception:match=want==got
        elif rule=='one_decimal':
            try:match=D(str(want)).quantize(D('.1'))==D(str(got)).quantize(D('.1'))
            except Exception:match=want==got
        else:match=str(want)==str(got)
        findings.append(dict(group=group,case=case,checkpoint=where,metric=metric,expected=want,observed=got,
            comparison='MATCH' if match else 'MISMATCH',comparison_rule=rule,
            commit=commit,
            review_status='Pending human finance review'))
    metrics={r['account_id']:r for r in csv_rows('official_account_metrics.csv')}
    for aid,values in expected['metrics'].items():
        for key,want in values.items():check('Official metrics',aid,key,want,metrics[aid]['engine_raw_'+key],'raw')
    shocks={(r['account_id'],r['scenario']):r for r in csv_rows('official_shock_results.csv')}
    for row in expected['shocks']:
        got=shocks[(str(row['account_id']),row['scenario'])]
        for key in row.keys()-{'account_id','scenario'}:
            check('Organizer shock',f"{row['account_id']} {row['scenario']}",key,row[key],got[key],
                'one_decimal' if key=='official_runway_rounded' else 'raw')
    for want,row in zip(expected['runway_boundaries'],csv_rows('runway_boundary_observed.csv'),strict=True):
        check('Runway boundary',f"B_left={row['buffer_left']}, gap={row['gap']}",'official runway',want,row['official_runway'],'one_decimal')
    ledger={(r['case'],r['path'],r['month'],r['engine_phase']):r for r in csv_rows('synthetic_checkpoint_ledger.csv') if r.get('month')!=''}
    for row in csv_rows('synthetic_expected_checkpoints.csv'):
        key=tuple(row[k] for k in ['case','path','month','engine_phase']);got=ledger[key]
        for metric in row.keys()-{'case','path','month','engine_phase'}:
            check('Synthetic checkpoint',row['case']+' '+row['path'],metric,row[metric] or None,got[metric],'money',f"{row['month']} {row['engine_phase']}")
    summary={(r['case'],r['path']):r for r in csv_rows('synthetic_case_summary.csv')}
    for row in expected['summaries']:
        got=summary[(row['case'],row['path'])]
        for metric in row.keys()-{'case','path'}:
            rule='exact' if metric in ['complete','first_negative_phase','first_negative_month'] else 'money'
            check('Synthetic summary',row['case']+' '+row['path'],metric,row[metric],got[metric],rule)
    raw_daily=load('daily_replay_raw.json')
    for key,want in expected['daily'].items():check('Independent daily replay','cohort',key,want,raw_daily[key],'raw')
    e=load('case_E_unknown_raw.json');plan=e['plan'];questions=e['missing_details']
    for key,want in [('goal_review_required',True),('goal_status','REVIEW_REQUIRED'),('G25_state','unknown')]:
        check('Unknown-income guard','E',key,want,plan[key])
    check('Unknown-income guard','E','complete funding unknown',None,plan['no_action']['full_funding_need'])
    for word in ['duration','value','timing']:
        check('Unknown-income guard','E','asks for '+word,True,any(word in q.lower() for q in questions))
    for key,values in load('recovery_expected.json')['paths'].items():
        actual=load('recovery_engine_raw.json')[key]['result']
        for metric,want in values.items():check('Recovery','D '+key,metric,want,actual[metric],'raw' if want is not None else 'exact')
    table('finance_findings.csv',findings)
    mismatches=[r for r in findings if r['comparison']=='MISMATCH']
    table('finance_open_issues.csv',mismatches or [dict(status='Pending human finance review',
        issue='No automated numerical mismatches; compare to original independent Excel workbook and obtain named sign-off.',
        owner='Finance teammate')])
    save('finance_check_summary.json',dict(commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        checked_at=datetime.now(timezone.utc).isoformat(),comparison_count=len(findings),mismatches=len(mismatches),
        review_status='Pending human finance review',daily=raw_daily))
    print(f'{len(findings)} field comparisons, {len(mismatches)} mismatches. Pending human finance review.')
    if mismatches:raise SystemExit(1)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--prepare',action='store_true');args=parser.parse_args()
    prepare() if args.prepare else compare()
