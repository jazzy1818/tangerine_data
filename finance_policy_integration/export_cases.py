"""Build the local finance review package from real histories and hypothetical inputs."""
import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
from pathlib import Path
import subprocess
from uuid import NAMESPACE_URL, uuid5

import engine
from backup_comparison import build_comparison, safe_mode_status
from finance_actions import source_commit
from plan_classification.schemas import ShockScenario
from web_app.contracts import RunInput
from web_app.service import preview

ROOT = Path(__file__).resolve().parents[1]
REVIEW_COLUMNS = ('case_id', 'account_id', 'scenario', 'candidate', 'finance_policy_clause', 'priority',
                  'evidence_status', 'action_status', 'result_before', 'result_after', 'remaining_gap',
                  'first_shortfall', 'complete', 'bank_review_flags', 'finance_reviewer_verdict',
                  'finance_reviewer_notes')


def effect(kind, value=None, **terms):
    return {'type': kind, 'value': value, **terms}


def cases():
    with (ROOT / 'reports/classification/account_features.csv').open() as handle:
        cohort = sorted(csv.DictReader(handle), key=lambda row: int(row['account_id']))
    shared = Counter(engine.load_data()['dispositions']['account_id'])
    used = set()

    def pick(test, *, key=None):
        ordered = sorted(cohort, key=key) if key else cohort
        selected = next(row for row in ordered if int(row['account_id']) not in used and test(row))
        account_id = int(selected['account_id'])
        used.add(account_id)
        return engine.know_customer(account_id)

    def sample(case_id, title, customer, *effects, phase=None, **context):
        scenario = {'phase': phase or ('active' if effects else 'normal'), 'effects': effects}
        return case_id, title, customer, scenario, context

    def positive(row):
        return float(row['I']) > float(row['S']) > 0 and float(row['B']) > 0

    def structural(row):
        return 0 < float(row['B']) < 6 * (float(row['S']) - float(row['I']))

    stable = pick(lambda row: positive(row) and row['deficit_month_share'] != ''
                  and float(row['deficit_month_share']) <= .15)
    yield sample('01-stable', 'Stable surplus and normal review', stable)
    yield sample('02-structural', 'Recurring deficit with no authorized intervention', pick(structural))
    thin = pick(lambda row: 0 < float(row['B']) < .75 * float(row['S']))
    yield sample('03-thin-repair', 'Thin buffer and immediate repair', thin,
                 effect('one_off_cost', thin['S'], start_month=0, effect_id='repair'))
    yield sample('04-negative-b', 'Negative historical buffer', pick(lambda row: float(row['B']) < 0))
    yield sample('05-zero-inflow', 'Zero typical inflow and organizer income reduction',
                 pick(lambda row: float(row['I']) == 0 < float(row['S'])),
                 effect('income_multiplier', .55, duration_months=6))
    yield sample('06-zero-spending', 'Zero typical spending and repair equal to spending',
                 pick(lambda row: float(row['S']) == 0), effect('one_off_cost', 0, start_month=0))
    yield sample('07-zero-bills', 'Zero recorded household bills and 15% bill shock',
                 pick(lambda row: float(row['H']) == 0), effect('household_bills_percent', 15., duration_months=6))
    loan = pick(lambda row: row['active_loan'] == 'True' and float(row['F']) > 100.)
    loan_payment = round(float(loan['history']['loan_payments'].median()), 2)
    if loan_payment <= 0:
        raise ValueError('The sampled account lacks a positive included loan payment. Recheck the sampling rule.')
    reduction = min(loan_payment, 250.)
    yield sample('08-deferral', 'Active loan with hypothetical included deferral and a $50 catch-up premium', loan,
                 effect('debt_payment_delta', -reduction, start_month=1, duration_months=2, effect_id='loan-deferral',
                        obligation_account_id=loan['account_id'], obligation_payment=loan_payment,
                        obligation_source='Hypothetical judge terms; payment amount from the median recorded loan outflow',
                        payment_in_baseline=True, debt_change_kind='deferral', repayment_month=4,
                        repayment_amount=round(2 * reduction + 50., 2)))
    shortest = pick(lambda row: True, key=lambda row: (int(row['recent_months']), int(row['months_observed'])))
    yield sample('09-short-recent', 'Shortest available recent history; no invented current evidence', shortest)
    joint = pick(lambda row: shared[int(row['account_id'])] > 1)
    yield sample('10-shared', 'Shared access and a hypothetical emergency expense', joint,
                 effect('one_off_cost', 300., start_month=0))
    yield sample('11-income', 'Temporary reduction in account inflows', pick(positive),
                 effect('income_multiplier', .55, duration_months=6))
    combined = pick(lambda row: float(row['B']) > 0 and float(row['S']) - float(row['F']) > 200.
                    and float(row['B']) < 6 * (float(row['S']) - .55 * float(row['I'])))
    scheduled = [{'account_id': combined['account_id'], 'event_id': f'approved-goal-{month}', 'month': month,
                  'amount': 100., 'source': 'Hypothetical judge approval for included payments', 'pause_fee': 0.,
                  'pause_approved': True, 'included_in_baseline': True} for month in range(1, 7)]
    yield sample('12-compound', 'Compound income, bills and repair with a supplied pause schedule', combined,
                 effect('income_multiplier', .55, duration_months=6),
                 effect('household_bills_percent', 15., duration_months=6),
                 effect('one_off_cost', 250., start_month=0), existing_transfers=scheduled)
    late = pick(structural)
    gap = round(late['S'] - late['I'], 2)
    yield sample('13-late-receipt', 'Receipt arrives after the first shortage', late,
                 effect('one_off_receipt', round(gap * 2, 2), start_month=3), opening_cash=round(gap * 1.5, 2))
    hold = pick(lambda row: 0 < float(row['B']) < float(row['S']))
    yield sample('14-hold', 'Temporary hold limits access to existing cash', hold,
                 effect('liquidity_hold', round(hold['B'] + 50., 2), start_month=0, duration_months=2))
    yield sample('15-unknown', 'Unpriced income change', pick(positive),
                 effect('income_delta', None, evidence='unknown'))
    recovery = pick(lambda row: float(row['S']) > 0)
    yield sample('16-recovery', 'Separate hypothetical recovery checkpoint', recovery, phase='recovery',
                 recovery_snapshot={'account_id': recovery['account_id'], 'source': 'Hypothetical judge checkpoint',
                    'assessment_month': '2026-11', 'cash_basis': 'judge_specified', 'available_cash': 3000.,
                    'monthly_spending': 2400., 'stable_cash_flow': True, 'obligations_covered': True,
                    'supported_monthly_contribution': 300.})
    yield sample('17-windfall', 'One-time receipt and a positive normal cash position', pick(positive),
                 effect('one_off_receipt', 3000., start_month=0))
    yield sample('18-zero-opening', 'Explicit zero opening cash; historical B remains separate', pick(positive),
                 opening_cash=0.)
    assumed = pick(lambda row: float(row['B']) > 0)
    yield sample('19-conditional', 'Unconfirmed spending change kept in a separate comparison', assumed,
                 effect('expense_delta', 100., evidence='assumed', duration_months=6))


class VisibleText(HTMLParser):
    """Capture the rendered review text, including collapsed evidence sections."""
    blocks = {'section', 'p', 'h1', 'h2', 'h3', 'h4', 'li', 'tr', 'summary', 'div', 'br', 'label'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.svg = 0

    def handle_starttag(self, tag, attrs):
        if tag == 'svg':
            self.svg += 1
        elif not self.svg and tag in self.blocks:
            self.parts.append('\n')
        elif not self.svg and tag in ('td', 'th'):
            self.parts.append(' | ')

    def handle_endtag(self, tag):
        if tag == 'svg':
            self.svg -= 1
        elif not self.svg and tag in self.blocks:
            self.parts.append('\n')

    def handle_data(self, data):
        if not self.svg:
            self.parts.append(data)

    def text(self):
        return '\n'.join(' '.join(line.split()) for line in ''.join(self.parts).splitlines() if line.strip())


def render_reviews(runs):
    javascript = """
      import {readFileSync} from 'node:fs';
      import {runView} from './web_app/static/reviews.js';
      const runs=JSON.parse(readFileSync(0, 'utf8'));
      process.stdout.write(JSON.stringify(runs.map(runView)));
    """
    rendered = subprocess.check_output(['node', '--input-type=module', '-e', javascript],
                                       cwd=ROOT, input=json.dumps(runs), text=True)
    for html in json.loads(rendered):
        parser = VisibleText()
        parser.feed(html)
        capture = parser.text()
        if 'Recommended Financial Actions' not in capture:
            raise ValueError('The actual website renderer did not show the action plan.')
        yield capture


def review_rows(case_id, plan):
    priority = {item['action_id']: number for number, item in enumerate(plan['prioritized_actions'], 1)}
    for item in plan['candidate_action_decisions']:
        impact = item['impact']
        if impact:
            before_need = impact['before']['full_funding_need_cad']
            after_need = impact['after']['full_funding_need_cad']
        elif daily := item.get('daily_comparison'):
            before_need = daily['before_funding_need_cad']
            after_need = daily['after_funding_need_cad']
        else:
            before_need = after_need = None
        after = plan['comparison']['after']
        yield {
            'case_id': case_id, 'account_id': plan['account_id'],
            'scenario': json.dumps(plan['financial_diagnosis']['scenario'], separators=(',', ':')),
            'candidate': item['action_id'], 'finance_policy_clause': item['finance_policy_clause'],
            'priority': priority.get(item['action_id']), 'evidence_status': '; '.join(item['evidence']),
            'action_status': item['status'], 'result_before': before_need,
            'result_after': after_need, 'remaining_gap': plan['remaining_gap_cad'],
            'first_shortfall': json.dumps(after['first_shortfall']), 'complete': after['complete'],
            'bank_review_flags': ' | '.join(plan['bank_review_flags']),
            'finance_reviewer_verdict': '', 'finance_reviewer_notes': '',
        }


def export(output):
    commit = source_commit()
    if not commit:
        raise ValueError('Set TANGERINE_SOURCE_COMMIT to the reviewed code commit before exporting.')
    output.mkdir(parents=True, exist_ok=True)
    runs, records, rows = [], [], []
    generated = datetime.now(timezone.utc).isoformat()
    for case_id, title, customer, scenario, context in cases():
        request = RunInput(account_id=customer['account_id'], scenario=ShockScenario.model_validate(scenario),
                           request_id=uuid5(NAMESPACE_URL, case_id), title=title, **context)
        evidence = preview(request)
        plans = engine.make_plan(customer, scenario=request.scenario, opening_cash=request.opening_cash,
                                 existing_transfers=request.existing_transfers,
                                 recovery_snapshot=request.recovery_snapshot, include_timing_comparison=True)
        crisis = plans['crisis_plan']
        if crisis['runtime_validation']['status'] != 'passed':
            raise ValueError(f'{case_id}: {crisis["review_flags"]}')
        plan = crisis['finance_plan']
        comparison = build_comparison(crisis)
        label, reason = safe_mode_status(crisis, comparison)
        comparison['planning_status'] = {'label': label, 'reason': reason}
        result = {**evidence, 'plans': plans, 'classification': crisis['classification'], 'cash_comparison': comparison}
        saved = {'id': str(request.request_id), 'status': 'complete', 'created_at': generated,
                 'request': request.model_dump(mode='json'), 'result': result}
        runs.append(saved)
        decisions = plan['candidate_action_decisions']
        records.append({'case_id': case_id, 'title': title, 'raw_input_provenance': {
                'history': ['data/monthly_summary.csv', 'data/loans.csv', 'data/dispositions.csv'],
                'scenario': 'Hypothetical judge scenario, including any supplied approval or current cash',
                'history_count': len(customer['history']), 'account_access': customer['demographics'],
                'loan_status': customer['source_loan_status']},
            'request': saved['request'], 'organizer_reference': evidence['reference'],
            'normal_goal_plan': plans['goal_plan'], 'finance_plan': plan,
            'candidate_action_ids': [item['action_id'] for item in decisions],
            'accepted_action_ids': [item['action_id'] for item in decisions if item['disposition'] == 'accepted'],
            'conditional_action_ids': [item['action_id'] for item in decisions if item['status'] == 'CONDITIONAL_ONLY'],
            'excluded_action_ids_and_reasons': {item['action_id']: item['reason'] for item in decisions
                                               if item['disposition'] == 'excluded'},
            'action_fees_and_future_obligations': {'applied_fees_cad': crisis['applied_pause_fees'],
                                                   'future': plan['post_horizon_obligations']},
            'validation': crisis['runtime_validation']})
        rows.extend(review_rows(case_id, plan))
        print(f'{case_id}: {plan["status"]}', flush=True)
    captures = list(render_reviews(runs))
    (output / 'finance_acceptance_details.json').write_text(json.dumps(
        {'source_commit': commit, 'generated_at': generated, 'finance_approval': 'PENDING', 'cases': records},
        indent=2, allow_nan=False) + '\n')
    (output / 'rendered_reviews.txt').write_text('\n\n'.join(
        f'{record["case_id"]} — {record["title"]}\n{capture}'
        for record, capture in zip(records, captures, strict=True)) + '\n')
    with (output / 'finance_acceptance_cases.csv').open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    print(f'Exported {len(records)} distinct accounts, {len(rows)} decision rows and {len(captures)} UI text captures.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=Path(__file__).resolve().parent)
    export(parser.parse_args().out)
