"""Local read-only finance export. Run from the repository with the prepared Python."""
import csv
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import sys
import pandas as pd
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import engine
from crisis_response import make_crisis_plan
from plan_classification import build_case, profile_from_engine, ShockScenario
from scenario_execution import execute_scenario
from daily_simulation import get_macro_discovery_data
from recovery_plan import make_recovery_plan

OUT = Path(__file__).resolve().parent
def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args], text=True).strip()
def write(name, rows):
    fields = list(dict.fromkeys(k for r in rows for k in r))
    with (OUT / name).open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator='\n')
        w.writeheader()
        w.writerows(rows)
def dump(name, obj):
    (OUT / name).write_text(json.dumps(obj, indent=2, default=str, allow_nan=False)+'\n')

metadata = dict(branch=git('branch', '--show-current'), commit=git('rev-parse', 'HEAD'),
                status_at_export=git('status', '--short'), tracked_changes=git('diff', '--stat'),
                staged_changes=git('diff', '--cached', '--stat'),
                exported_at=datetime.now(timezone.utc).isoformat(),
                finance_review_status='Pending human finance review')
monthly = list(csv.DictReader((ROOT/'data/monthly_summary.csv').open()))
loans = list(csv.DictReader((ROOT/'data/loans.csv').open()))
metrics, shocks, evidence = [], [], []
for aid in [22812, 20111]:
    rows = sorted([r for r in monthly if int(r['account_id']) == aid], key=lambda r:r['month'])
    med = lambda key: statistics.median(float(r[key]) for r in rows)
    loan = [r for r in loans if int(r['account_id']) == aid]
    assert len(loan) <= 1
    values = dict(I=med('money_in'), S=med('money_out'), H=med('household_bills'),
        F=statistics.median(sum(float(r[k]) for k in ['household_bills','insurance','loan_payments']) for r in rows),
        B=statistics.mean(float(r['avg_daily_balance']) for r in rows[-6:]),
        P=float(loan[0]['monthly_payment']) if loan and loan[0]['status'] in ['C','D'] else 0.)
    customer = engine.know_customer(aid)
    metrics.append(dict(account_id=aid, **values, B_months=';'.join(r['month'] for r in rows[-6:]),
        loan_status=loan[0]['status'] if loan else 'NO_LOAN',
        calculation_source='Python statistics over local CSV; loan C/D = running at end-2025',
        **{'engine_raw_'+k:customer['raw_'+k] for k in values}))
    for r in rows:
        evidence.append({**r, 'fixed_cost_monthly_sum':sum(float(r[k]) for k in ['household_bills','insurance','loan_payments']),
                         'included_in_B':r['month'] in [x['month'] for x in rows[-6:]]})
    for name, multiplier, bills, cost in [('Job loss',.55,0.,0.),('Furnace repair',1.,0.,values['S']),('Combined shock',.55,.15,0.)]:
        actual = engine.take_shock(customer, multiplier, bills, cost)
        b, gap = actual['raw_buffer_left'], actual['raw_gap']
        raw = 0. if b <= 0 else ('no shortfall (120+)' if gap <= 0 else min(b/gap,120.))
        shocks.append(dict(account_id=aid, scenario=name, **{k:customer['raw_'+k] for k in values},
            post_shock_income=actual['raw_income_after_shock'], post_shock_monthly_spending=actual['raw_spending_after_shock'],
            one_time_expense=actual['raw_one_off_costs'], remaining_buffer=b, monthly_funding_gap=gap,
            official_runway_before_rounding=raw, official_runway_rounded=actual['runway'],
            calculation_source='engine.know_customer -> engine.take_shock -> engine.calculate_runway; unrounded ratio reconstructed using README rules'))
write('official_account_metrics.csv', metrics)
write('official_shock_results.csv', shocks)
write('account_monthly_evidence.csv', evidence)
write('account_loan_evidence.csv', [r for r in loans if int(r['account_id']) in [22812,20111]])
write('runway_boundary_observed.csv',[
    dict(buffer_left=b,gap=g,official_runway=engine.calculate_runway(b,g))
    for b,g in [(0.,100.),(-1.,-1.),(100.,0.),(100.,-5.),(12000.,1.),(60.,.5),(5.,3.)]])

def customer(i,s,b,h=0.,p=0.,included=None):
    c = dict(account_id=17, I=i,S=s,B=b,H=h,F=h+p,P=p,
             raw_I=i,raw_S=s,raw_B=b,raw_H=h,raw_F=h+p,raw_P=p,has_running_loan=p>0)
    c['history']=pd.DataFrame(dict(account_id=17,month=pd.period_range('2025-01',periods=12,freq='M').astype(str),
        money_in=i,money_out=s,household_bills=h,insurance=0.,loan_payments=included if included is not None else 0.,
        avg_daily_balance=b,month_end_balance=b,min_balance=b,days_below_zero=0))
    # History is a constant synthetic profile adapter, not measured bank data.
    # Missing debt-inclusion evidence must remain missing in the actual execution.
    if p and included is None: c['history']=c['history'].drop(columns=['loan_payments'])
    if included is not None: c['included_loan_payment']=included
    return c
ledgers, summaries, raw_results = [], [], {}
def record(case,path,result,action,flags=()):
    raw_results[case+' '+path]=result
    first = next((c for c in result['checkpoints'] if c['cash']<0),None)
    summaries.append(dict(case=case,path=path,status='RUN',first_negative_month=first['month'] if first else '',
        first_negative_phase=('Immediate' if first['month']==0 else first['phase'].title()) if first else '',
        first_negative_shortfall=-first['cash'] if first else '',lowest_accessible_cash=result['minimum_cash'],
        additional_starting_cash_known_components=result['additional_cash_needed'],
        complete_shock_funding_requirement=result['full_funding_need'],complete=result['funding_result_complete'],
        cash_needed_before_receipt=(max(0., -min(c['cash'] for c in result['checkpoints'] if c['month']<3)) if case=='B' else None),
        action_status=action, warnings=' | '.join([*flags,*result['review_flags'],*result['unresolved_effects']]),
        calculation_source='scenario_execution.execute_scenario (directly or via crisis_response.make_crisis_plan)'))
    for cp in result['checkpoints']:
        m, phase = cp['month'], cp['phase']
        row=result['schedule'][m]
        opening = row['start_balance'] if phase=='start' else result['checkpoints'][2*m]['cash']
        ledgers.append(dict(case=case,path=path,month=m,phase='Immediate' if m==0 else phase.title(),
            engine_phase=phase,opening_cash=opening,
            one_time_receipt=row['one_off_receipt'] if phase=='start' else 0.,
            one_time_expense=row['one_off_cost']-row.get('deferred_repayment',0.) if phase=='start' else 0.,
            income=row['income'] if phase=='end' else 0.,spending=row['spending'] if phase=='end' else 0.,
            action_cash_effect=row['paused_existing_outflow']-row['proposed_contribution'] if phase=='end' else 0.,
            fees=row['action_fees'] if phase=='start' else 0.,
            repayments=row.get('deferred_repayment',0.) if phase=='start' else 0.,
            fees_or_repayments_note='Repayments are separate from one_time_expense. Subtract fees and repayments once each.',
            closing_accessible_cash=cp['cash'],period_complete=row['period_complete'],action_status=action))

compound=dict(effects=[dict(type='one_off_cost',value=1500.,start_month=0),
    dict(type='income_multiplier',value=.55,duration_months=6),
    dict(type='household_bills_percent',value=15.,duration_months=6)])
a=customer(3000.,2400.,3000.,400.)
record('A','No intervention',execute_scenario(a,compound,opening_cash=3000.),'No action')
normal=dict(name='Future proposed investment',monthly_contribution=300.,reserve_target=7200.)
plan=make_crisis_plan(a,compound,normal_goal=normal,opening_cash=3000.)
dump('case_A_proposed_pause_raw.json',plan)
record('A','Pause future proposed investment',plan['revised_goal'],'Hypothetical proposal; no existing outflow; no cash credit',plan['review_flags'])
transfers=[dict(event_id=f'included-{m}',month=m,amount=300.,source='User synthetic approved existing outflow',
               included_in_baseline=True,pause_approved=True,pause_fee=0.) for m in range(1,7)]
plan=make_crisis_plan(a,compound,normal_goal={**normal,'monthly_contribution':0.},opening_cash=3000.,existing_transfers=transfers)
dump('case_A_existing_pause_raw.json',plan)
record('A','Pause approved existing outflow',plan['supported_pause'],'Confirmed within synthetic case; zero fee; hypothetical real-world action',plan['review_flags'])
record('B','Start Month 3 receipt',execute_scenario(customer(1800.,2400.,1000.),dict(effects=[
    dict(type='one_off_receipt',value=2000.,start_month=3,evidence='user_confirmed')]),opening_cash=1000.),'Confirmed receipt within synthetic case')
for path,inc,effects in [('Original payments',300.,[]),('Approved deferral',300.,[True]),('Deferral without baseline evidence',None,[False])]:
    es=[] if not effects else [dict(type='debt_payment_delta',value=-300.,start_month=1,duration_months=2,
        evidence='user_confirmed',debt_change_kind='deferral',repayment_month=4,repayment_amount=650.)]
    record('C',path,execute_scenario(customer(2200.,2400.,300.,p=300.,included=inc),
        dict(phase='active' if es else 'normal',effects=es),opening_cash=300.),
        'Approved within synthetic case' if es else 'No intervention')
recovery_results={}
for path,contribution in [('Supported contribution',300.),('Unknown contribution',None)]:
    inputs=dict(source='Tangerine-Team-Execution-Prompts.pdf, Phase 1 Case D, page 3',
        assessment_month='2026-11',cash_basis='judge_specified',available_cash=3000.,
        monthly_spending=2400.,stable_cash_flow=True,obligations_covered=True,
        supported_monthly_contribution=contribution)
    result=make_recovery_plan(inputs, reserve_months=3.)
    recovery_results[path]=dict(inputs=inputs,result=result)
    summaries.append(dict(case='D',path=path,status='RUN',
        complete=result['months_to_target'] is not None,completeness_scope='Conditional recovery target and timeline only; no crisis cash ledger',
        action_status='Synthetic assumptions explicitly supplied by PDF; no action taken',
        reserve_target=result['reserve_target'],reserve_gap=result['reserve_gap'],supported_contribution=contribution,
        engine_monthly_contribution=result['monthly_contribution'],monthly_surplus=result['monthly_surplus'],
        months_to_target=result['months_to_target'],recovery_status=result['status'],
        warnings=' | '.join(result['review_flags']),calculation_source='recovery_plan.make_recovery_plan'))
    ledgers.append(dict(case='D',path=path,status='NO_CHECKPOINT_API',
        warnings='Recovery target/ETA computed; this API exposes no dated cash checkpoints. See case summary and recovery_engine_raw.json.'))
dump('recovery_engine_raw.json',recovery_results)
# The PDF labels all A-E inputs synthetic. Reuse A's unchanged synthetic
# baseline solely as the explicitly declared E harness; invent no shock value.
e_scenario=ShockScenario(description='Income changes.',effects=[
    dict(type='income_delta',value=None,evidence='unknown')])
e_plan=make_crisis_plan(a,e_scenario,normal_goal=normal,opening_cash=3000.)
e_case=build_case(profile_from_engine(a),e_scenario,planning_cash=3000.)
dump('case_E_unknown_raw.json',dict(plan=e_plan,missing_details=e_case.missing_details))
record('E','Income changes; synthetic baseline from Case A',e_plan['no_action'],
    'Unknown income event; no confirmed action', ['Synthetic baseline from Case A (cash 3000, inflow 3000, spending 2400, bills 400). Start month=1 is a schema default, not supplied timing evidence. Direction/amount/timing/duration remain unknown.',*e_case.missing_details])
write('synthetic_checkpoint_ledger.csv',ledgers)
write('synthetic_case_summary.csv',summaries)
dump('synthetic_engine_raw.json',raw_results)
daily=get_macro_discovery_data()
dump('daily_replay_raw.json',daily)
write('daily_replay_verification.csv',[dict(status='RECOMPUTED',calculation_source='daily_simulation.get_macro_discovery_data',
    eligible_accounts=daily['total_accounts'],hidden_shortfall_accounts=daily['intra_month_overdrafts'],
    qualifying_bill_shift_accounts=daily['accounts_with_movable_bill'],shortfalls_eliminated=daily['overdrafts_resolved_by_shift'],
    denominator=daily['accounts_with_movable_bill'],resolution_pct_unrounded=100*daily['overdrafts_resolved_by_shift']/daily['accounts_with_movable_bill'],
    resolution_pct_engine=daily['resolution_rate_pct'],month_end_balance_delta=daily['month_end_balance_delta'],
    assumptions='Conditional approval; zero fee; every shifted payment remains in original month; opening proxy uses up to six completed pre-July months',
    methodology=daily['methodology'])])
dump('environment_record.json',metadata)
hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [
    ROOT/'data/monthly_summary.csv',ROOT/'data/loans.csv',ROOT/'data/transactions.csv',ROOT/'engine.py',ROOT/'crisis_response.py',ROOT/'scenario_execution.py',ROOT/'daily_simulation.py',
    ROOT/'recovery_plan.py',ROOT/'app.py',ROOT/'tailored_advice.py',Path(__file__).resolve()]}
dump('source_sha256.json',hashes)
print(json.dumps(dict(metrics=len(metrics),shocks=len(shocks),monthly_records=len(evidence),checkpoints=len(ledgers),summaries=len(summaries),daily=daily),indent=2))
