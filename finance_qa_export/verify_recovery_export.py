"""Standalone Case D arithmetic; no engine imports or test fixtures.

Prepare freezes a fresh calculation before the next observed export. This is a
retrospective check, not a claim that earlier engine results were never seen.
"""
import argparse
import csv
from datetime import datetime, timezone
from decimal import Decimal, ROUND_CEILING
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument('--prepare', action='store_true')
args = parser.parse_args()

if args.prepare:
    cash, spending, reserve_months = Decimal('3000'), Decimal('2400'), Decimal('3')
    target = spending * reserve_months
    gap = max(Decimal('0'), target - cash)
    expected = {
        'calculated_at': datetime.now(timezone.utc).isoformat(),
        'source': 'Tangerine-Team-Execution-Prompts.pdf, Phase 1 Case D, page 3',
        'review_status': 'Pending human finance review',
        'method': 'Standalone Decimal arithmetic; no engine imports; retrospective check',
        'inputs': dict(current_cash=str(cash), monthly_essential_spending=str(spending),
                       reserve_months=str(reserve_months), stable_cash_flow=True,
                       obligations_covered=True, monthly_inflow=None),
        'formulas': dict(reserve_target='essential spending * reserve months',
                         reserve_gap='max(0, target - accessible cash)',
                         months_to_target='ceil(gap / supported monthly contribution); unknown when contribution unknown'),
        'paths': {}
    }
    for path, rate in [('Supported contribution', Decimal('300')), ('Unknown contribution', None)]:
        expected['paths'][path] = dict(reserve_target=float(target), reserve_gap=float(gap),
            monthly_contribution=float(rate) if rate is not None else 0.,
            months_to_target=int((gap / rate).to_integral_value(rounding=ROUND_CEILING)) if rate else None,
            monthly_surplus=None)
    (OUT/'recovery_expected.json').write_text(json.dumps(expected, indent=2)+'\n')
    print('Prepared standalone recovery calculations; pending human finance review.')
else:
    expected = json.loads((OUT/'recovery_expected.json').read_text())
    observed = json.loads((OUT/'recovery_engine_raw.json').read_text())
    rows = []
    for path, values in expected['paths'].items():
        for metric, value in values.items():
            actual = observed[path]['result'][metric]
            rows.append(dict(case='D', path=path, metric=metric, expected=value, observed=actual,
                comparison='MATCH' if value == actual else 'MISMATCH',
                expected_calculated_at=expected['calculated_at'],
                review_status='Pending human finance review'))
    with (OUT/'recovery_expected_observed.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    mismatches = [r for r in rows if r['comparison'] != 'MATCH']
    print(f'Compared {len(rows)} recovery fields; {len(mismatches)} mismatches. Pending human finance review.')
    if mismatches:
        raise SystemExit(1)
