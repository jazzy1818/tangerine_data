"""One-time liquid reserve estimate from a supplied, account-specific snapshot."""
from datetime import date
from decimal import Decimal
from typing import Annotated

from pydantic import Field

from plan_classification.schemas import Contract


CAD = Annotated[Decimal, Field(ge=0, le=10**12, decimal_places=2)]


class SavingsEvidence(Contract):
    account_id: int = Field(ge=1)
    as_of: date | None = None
    protect_through: date | None = None
    unallocated_cash: CAD | None = None
    unpaid_commitments: CAD | None = None
    cash_cushion: CAD | None = None
    remaining_reserve_goal: CAD | None = None


def assess_savings(evidence: SavingsEvidence | None, *, account_id: int,
                   opening_cash: float | None, cash_source: str) -> dict:
    fields = {
        'as_of': 'the cash snapshot date',
        'protect_through': 'the date through which commitments need to be covered',
        'unallocated_cash': 'cleared, unallocated cash',
        'unpaid_commitments': 'total unpaid commitments through the review date',
        'cash_cushion': 'the cash cushion to keep after those commitments',
        'remaining_reserve_goal': 'the remaining emergency savings goal',
    }
    if evidence is None:
        outstanding = list(fields.values())
    elif evidence.account_id != account_id:
        outstanding = ['a savings snapshot confirmed for this account']
    else:
        outstanding = [label for field, label in fields.items() if getattr(evidence, field) is None]
        if evidence.as_of is not None and evidence.as_of != date.today():
            outstanding.append('a cash snapshot reconfirmed on the day of this review')
        if evidence.as_of and evidence.protect_through and evidence.protect_through < evidence.as_of:
            outstanding.append('a commitments end date on or after the cash snapshot date')
        if (opening_cash is not None and evidence.unallocated_cash is not None
                and evidence.unallocated_cash > Decimal(str(opening_cash))):
            outstanding.append('cash figures that agree with the supplied accessible balance')
    if opening_cash is None or not cash_source:
        outstanding.append('the accessible cash balance and its source')
    if outstanding:
        return {'status': 'needs_evidence', 'amount': None, 'outstanding': outstanding}

    room = evidence.unallocated_cash - evidence.unpaid_commitments - evidence.cash_cushion
    amount = min(max(Decimal(0), room), evidence.remaining_reserve_goal)
    status = 'no_room'
    if room >= 0 and evidence.remaining_reserve_goal == 0:
        status = 'goal_met'
    elif amount > 0:
        status = 'available'
    return {
        'status': status, 'amount': float(amount),
        'room_after_commitments_and_cushion': float(room),
        **evidence.model_dump(mode='json', exclude={'account_id'}),
    }
