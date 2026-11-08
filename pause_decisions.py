"""Deterministic pause selection: evidence permits modeling; purpose permits advice."""
from collections import defaultdict
from crisis_rules import first_shortfall_order
from scenario_execution import execute_scenario


def pause_purpose(before, after, floor):
    if not before['funding_result_complete'] or not after['funding_result_complete']:
        return None
    prior, next_ = first_shortfall_order(before), first_shortfall_order(after)
    if ((next_ is not None and (prior is None or next_ < prior)) or
        after['additional_cash_needed'] > before['additional_cash_needed'] + .005):
        return None
    if after['additional_cash_needed'] < before['additional_cash_needed'] - .005:
        return 'reduces_funding_gap'
    if prior is not None and (next_ is None or next_ > prior):
        return 'delays_first_shortfall'
    old_gap = max(0., floor - before['minimum_cash'])
    new_gap = max(0., floor - after['minimum_cash'])
    old_total = sum(max(0., floor-p['cash']) for p in before['checkpoints'])
    new_total = sum(max(0., floor-p['cash']) for p in after['checkpoints'])
    if old_total > .005 and new_total < old_total - .005 and new_gap <= old_gap + .005:
        return 'protects_reserve_floor'
    return None


def select_pauses(customer, scenario, transfers, revised, *, floor, contribution, opening_cash):
    current = revised
    releases, fees, selected, decisions = defaultdict(float), defaultdict(float), [], {}
    # Fee-free relief is evaluated first. An expensive candidate cannot erase a
    # useful earlier decision. Sorting makes results independent of entry order.
    for t in sorted(transfers, key=lambda t: (t.pause_fee or 0., t.month, t.event_id)):
        row = {'event_id': t.event_id, 'status': 'excluded', 'reason': '', 'purpose': None}
        if t.month > scenario.horizon_months:
            row['reason'] = 'outside_horizon'
        elif not t.included_in_baseline or not t.pause_approved or t.pause_fee is None:
            row['reason'] = 'evidence_incomplete'
        elif t.pause_fee >= t.amount:
            row['reason'] = 'fee_consumes_benefit'
        else:
            trial_releases, trial_fees = dict(releases), dict(fees)
            trial_releases[t.month] = trial_releases.get(t.month, 0.) + t.amount
            trial_fees[t.month] = trial_fees.get(t.month, 0.) + t.pause_fee
            trial = execute_scenario(customer, scenario, opening_cash=opening_cash,
                contribution=contribution, spending_releases=trial_releases, release_fees=trial_fees)
            purpose = pause_purpose(current, trial, floor)
            if purpose:
                releases, fees = defaultdict(float, trial_releases), defaultdict(float, trial_fees)
                selected.append(t.event_id)
                current = trial
                row.update(status='included', reason='supported_financial_purpose', purpose=purpose)
            else:
                row['reason'] = ('projection_incomplete' if not current['funding_result_complete'] else
                    'advances_shortfall_or_worsens_gap' if (trial['additional_cash_needed'] > current['additional_cash_needed'] + .005
                        or (first_shortfall_order(trial) is not None and
                        (first_shortfall_order(current) is None or first_shortfall_order(trial) < first_shortfall_order(current))))
                    else 'no_shortfall_or_reserve_purpose')
        decisions[t.event_id] = row
    return current, dict(releases), dict(fees), selected, [decisions[t.event_id] for t in transfers]
