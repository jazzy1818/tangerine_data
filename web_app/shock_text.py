"""Offline plain-text shock reader and the shared default rules.

Used when Gemini is unavailable or fails, and to apply the same visible defaults
to Gemini's extraction. Defaults come from the organizer README examples only:
  - a job loss with no amount -> EI at 55% of usual income (README "laid off" example)
  - bills/rent going up with no amount -> household bills +15% (README example)
  - no duration -> the plan period; no start -> now (one-time) / Month 1 (recurring)
Amounts that are genuinely missing (e.g. a repair with no price) stay unknown.
"""
import re

ONE_TIME = {'one_off_cost', 'one_off_receipt'}
RECURRING = {'income_multiplier', 'income_delta', 'expense_delta', 'expense_percent',
             'household_bills_percent', 'household_bills_delta', 'debt_payment_delta'}
JOB_LOSS = re.compile(r'\b(los[te]s?|losing)\b[^.;]*\b(job|work|employment)\b|\blaid[ -]?off\b|\blayoffs?\b|\bunemploy|\bfired\b|\bjob loss\b|\bredundan', re.I)
BILLS = re.compile(r'\b(bills?|rent|utilit\w*|hydro|heating|mortgage|groceries|living costs?|cost of living)\b', re.I)
UP = re.compile(r'\b(up|ris\w*|increas\w*|higher|goes up|went up|jump\w*|more)\b', re.I)
DOWN = re.compile(r'\b(down|drop\w*|fall\w*|fell|cut\w*|reduc\w*|lower|decreas\w*|less)\b', re.I)
INCOME = re.compile(r'\b(income|pay|paycheck|salary|wages?|earnings|hours)\b', re.I)
RAISE = re.compile(r'\b(raise|promotion|pay rise|new job)\b', re.I)
COST = re.compile(r'\b(repairs?|expense|emergency|medical|dental|vet|car|roof|furnace|appliance|funeral|wedding|tuition|fees?|fine|surgery|hospital|unexpected|one[- ]time|cost|bill of|pay off)\b', re.I)
RECEIPT = re.compile(r'\b(bonus|windfall|inherit\w*|gift|refund|settlement|lottery|severance|receiv\w*|tax return|payout)\b', re.I)
LOAN = re.compile(r'\b(loan|car payment|mortgage payment|debt payment|line of credit)\b', re.I)
MONEY = re.compile(r'(?:\$|cad\s*)\s?(\d[\d,]*(?:\.\d+)?)\s*(k|thousand)?|(\d[\d,]*(?:\.\d+)?)\s*(k|thousand)?\s*(?:dollars|cad|\$)', re.I)
PERCENT = re.compile(r'(\d+(?:\.\d+)?)\s*(?:%|percent)', re.I)
MONTHS = re.compile(r'\bfor\s+(?:the\s+next\s+)?(\d+|a|one|two|three|four|five|six|nine|twelve)\s+(months?|years?|weeks?)\b', re.I)
IN_MONTHS = re.compile(r'\b(?:in|after)\s+(\d+|one|two|three|four|five|six)\s+months?\b|\bnext month\b', re.I)
WORDS = {'a': 1, 'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'nine': 9, 'twelve': 12}


def _num(text):
    return int(text) if text.isdigit() else WORDS.get(text.lower(), 1)


def _money(clause):
    match = MONEY.search(clause)
    if not match:
        return None
    raw, scale = (match.group(1), match.group(2)) if match.group(1) else (match.group(3), match.group(4))
    value = float(raw.replace(',', ''))
    return round(value * (1000 if scale else 1), 2)


def _duration(clause):
    match = MONTHS.search(clause)
    if not match:
        return None
    n, unit = _num(match.group(1)), match.group(2).lower()
    return n * 12 if unit.startswith('year') else max(1, round(n / 4)) if unit.startswith('week') else n


def _start(clause):
    match = IN_MONTHS.search(clause)
    if not match:
        return None
    return 1 if match.group(0).lower() == 'next month' else _num(match.group(1))


def _clauses(text):
    parts = re.split(r'(?<!\d)\.(?!\d)|[;\n]+|,(?!\d{3})\s*(?:and\s+)?|\band\b(?=\s+(?:a|an|the|their|his|her|my|bills?|rent|income|pay|they|he|she|i|we)\b)|\bplus\b', text, flags=re.I)
    return [p.strip() for p in parts if p and p.strip()]


def parse(text):
    """Return (effects, durations_seen) from plain text, conservatively."""
    effects, seen = [], set()
    global_duration = _duration(text)

    def add(effect, clause):
        key = (effect['type'], effect.get('start_month'))
        if key in seen:
            return
        seen.add(key)
        effect.setdefault('_explicit_duration', _duration(clause))
        effect.setdefault('_explicit_start', _start(clause))
        effect['quote'] = clause
        effects.append(effect)

    for clause in _clauses(text):
        pct, cash = PERCENT.search(clause), _money(clause)
        if LOAN.search(clause) and cash is not None and (UP.search(clause) or DOWN.search(clause)):
            add({'type': 'debt_payment_delta', 'value': -cash if DOWN.search(clause) else cash}, clause)
        elif INCOME.search(clause) and pct and not BILLS.search(clause):
            value = float(pct.group(1)) / 100
            if re.search(r'\b(to|at|only|of)\s*\d', clause, re.I) or re.search(r'\d+\s*(?:%|percent)\s+of\b', clause, re.I):
                multiplier = value
            elif DOWN.search(clause) or JOB_LOSS.search(clause):
                multiplier = 1 - value
            else:
                multiplier = 1 + value
            add({'type': 'income_multiplier', 'value': round(multiplier, 4)}, clause)
        elif INCOME.search(clause) and cash is not None and not BILLS.search(clause) and (UP.search(clause) or DOWN.search(clause)):
            add({'type': 'income_delta', 'value': -cash if DOWN.search(clause) else cash}, clause)
        elif RAISE.search(clause) and pct:
            add({'type': 'income_multiplier', 'value': round(1 + float(pct.group(1)) / 100, 4)}, clause)
        elif JOB_LOSS.search(clause):
            add({'type': 'income_multiplier', 'value': None, '_default': 'job_loss'}, clause)
        elif RECEIPT.search(clause) and cash is not None:
            add({'type': 'one_off_receipt', 'value': cash}, clause)
        elif cash is not None and (COST.search(clause) or not BILLS.search(clause)) and not re.search(r'\b(per|a|each|every)\s+month\b|\bmonthly\b', clause, re.I):
            add({'type': 'one_off_cost', 'value': cash}, clause)
        elif BILLS.search(clause) and pct:
            sign = -1 if DOWN.search(clause) and not UP.search(clause) else 1
            add({'type': 'household_bills_percent', 'value': sign * float(pct.group(1))}, clause)
        elif BILLS.search(clause) and cash is not None:
            sign = -1 if DOWN.search(clause) and not UP.search(clause) else 1
            add({'type': 'household_bills_delta', 'value': sign * cash}, clause)
        elif BILLS.search(clause) and UP.search(clause):
            add({'type': 'household_bills_percent', 'value': None, '_default': 'bills_up'}, clause)
        elif COST.search(clause) and not cash:
            add({'type': 'one_off_cost', 'value': None}, clause)
    return effects, global_duration


def finalize(effects, *, horizon, global_duration=None):
    """Apply the visible default rules; return (effects, horizon, defaults, questions)."""
    defaults, questions, out = [], [], []
    durations = [e.get('_explicit_duration') or global_duration for e in effects if e['type'] in RECURRING]
    longest = max([d for d in durations if d] or [0])
    if longest > horizon:
        defaults.append(f'Plan period extended to {longest} months to cover the stated duration.')
        horizon = min(longest, 120)
    for index, e in enumerate(effects, 1):
        kind = e['type']
        effect = {'effect_id': e.get('effect_id') or f'text-{index}', 'type': kind, 'value': e.get('value'),
                  'evidence': 'judge_specified'}
        if kind == 'income_multiplier' and effect['value'] is None and e.get('_default') == 'job_loss':
            effect['value'] = .55
            defaults.append('Job loss with no amount: income falls to 55% (Employment Insurance, organizer standard shock).')
        if kind == 'household_bills_percent' and effect['value'] is None and e.get('_default') == 'bills_up':
            effect['value'] = 15.
            defaults.append('Bills going up with no amount: household bills +15% (organizer standard shock).')
        start = e.get('_explicit_start')
        if start is None and e.get('start_month') is not None and e.get('_timing_explicit'):
            start = e['start_month']
        if start is None:
            start = 0 if kind in ONE_TIME else 1
            if effect['value'] is not None:
                defaults.append('No start date given: one-time amounts happen now; recurring changes start in Month 1.')
        effect['start_month'] = start
        if kind in RECURRING:
            duration = e.get('_explicit_duration') or e.get('duration_months') or global_duration
            if e.get('ongoing'):
                effect['ongoing'] = True
            elif duration:
                effect['duration_months'] = duration
            else:
                effect['duration_months'] = max(1, horizon - start + 1)
                if effect['value'] is not None:
                    defaults.append(f'No duration given: recurring changes last for the {horizon}-month plan period.')
        if effect['value'] is None:
            effect['evidence'] = 'unknown'
            label = {'one_off_cost': 'How much is the one-time cost?', 'income_multiplier': 'How much will income change?',
                     'household_bills_percent': 'How much will bills change?'}.get(kind, 'What is the amount of this change?')
            questions.append(label)
        for key in ('obligation_account_id', 'obligation_payment', 'obligation_source', 'payment_in_baseline',
                    'debt_change_kind', 'repayment_month', 'repayment_amount', 'repayment_unresolved'):
            if e.get(key) not in (None, False, 'payment_change'):
                effect[key] = e[key]
        out.append(effect)
    return out, horizon, list(dict.fromkeys(defaults)), list(dict.fromkeys(questions))
