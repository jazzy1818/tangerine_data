"""Offline portfolio audit of fixed and variable liquid-saving review capacity."""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import subprocess

import engine
from investment_triggers import evaluate_investment_triggers


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--baseline',type=Path,required=True,help='Pre-change account-level evaluation CSV')
    parser.add_argument('--output',type=Path,default=Path('reports/savings_access'))
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    with args.baseline.open() as f:before={int(r['account_id']):r for r in csv.DictReader(f)}
    result=[];goals=Counter();blockers=Counter();counts=Counter()
    for aid,history in engine.load_data()['monthly'].groupby('account_id'):
        aid=int(aid);r=evaluate_investment_triggers({'account_id':aid,'history':history,
            'source_loan_status': None})
        # Use the same no-extra-evidence baseline as the original count audit.
        # Actual arrears status is supplied below, never silently ignored.
        loans=engine.load_data()['loans'];loan=loans.loc[loans.account_id.eq(aid)]
        if not loan.empty and loan.iloc[0]['status']=='D':
            r=evaluate_investment_triggers({'account_id':aid,'history':history,'source_loan_status':'D'})
        flex=r['flexible_reserve_savings'];base=before[aid]
        assert float(base['normal_monthly_allocation'])==r['normal_monthly_allocation'],aid
        assert float(base['reserve_monthly_earmark'])==r['reserve_monthly_earmark'],aid
        counts['accounts']+=1
        counts['fixed_allocation_candidates']+=r['normal_monthly_allocation']>0
        counts['fixed_reserve_earmarks']+=r['reserve_monthly_earmark']>0
        counts['variable_liquid_savings_reviews']+=flex['status']=='conditional_review'
        counts['verified_current_set_asides']+=flex['current_set_aside'] is not None
        counts['runtime_blocks']+=r['runtime_validation']['status']!='passed'
        goals[r['primary_goal']]+=1
        for trigger in r['triggers']:
            if trigger['state']=='active':blockers[trigger['id']+' '+trigger['name']]+=1
        result.append(dict(account_id=aid,before_fixed_allocation=base['normal_monthly_allocation'],
            after_fixed_allocation=r['normal_monthly_allocation'],before_fixed_reserve_earmark=base['reserve_monthly_earmark'],
            after_fixed_reserve_earmark=r['reserve_monthly_earmark'],variable_review_status=flex['status'],
            opportunity_months=flex['opportunity_months'],observed_months=flex['observed_months'],
            typical_positive_month_amount=flex['typical_positive_month_amount'],
            current_set_aside=flex['current_set_aside'],months_to_target=flex['months_to_target'],
            fixed_monthly_commitment=flex['fixed_monthly_commitment'],reason=flex['reason'],
            history_end=r['features'].get('history_end'),primary_goal=r['primary_goal'],runtime=r['runtime_validation']['status']))
    with (args.output/'account_comparison.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(result[0]),lineterminator='\n');w.writeheader();w.writerows(result)
    summary=dict(counts=counts,primary_goals=goals,active_triggers=blockers,
        source_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        source_sha256={name:hashlib.sha256(Path(name).read_bytes()).hexdigest()
            for name in ['investment_triggers.py','goal_validation.py','data/monthly_summary.csv','data/loans.csv']},
        interpretation='Variable historical savings-review opportunities are not fixed investment eligibility or verified accessible cash. No current amount, standing transfer, target date or security recommendation is inferred.')
    (args.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
