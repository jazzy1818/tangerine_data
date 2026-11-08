"""Recovery is an evidence checkpoint, never an automatic salary reset."""
from math import floor

from pydantic import Field, field_validator
from plan_classification.schemas import Contract


class RecoverySnapshot(Contract):
    account_id: int | None = Field(default=None, ge=1)
    source: str = Field(min_length=1)
    assessment_month: str = Field(min_length=1)
    cash_basis: str = Field(pattern='^(judge_specified|observed|simulated)$')
    available_cash: float = Field(ge=-1e12, le=1e12)
    monthly_inflow: float | None = Field(default=None, ge=0, le=1e12)
    monthly_spending: float = Field(gt=0, le=1e12)
    stable_cash_flow: bool = Field(strict=True)
    obligations_covered: bool = Field(strict=True)
    supported_monthly_contribution: float | None = Field(default=None, ge=0, le=1e12)
    earmarked_near_term_cash: float = Field(default=0, ge=0, le=1e12)

    @field_validator('assessment_month')
    @classmethod
    def valid_month(cls, value):
        import re
        if not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', value):
            raise ValueError('Checkpoint month must be YYYY-MM')
        return value


def make_recovery_plan(snapshot=None, *, reserve_months=3.):
    """No snapshot -> unknown recovery; all timelines remain conditional."""
    if snapshot is None:
        return {'status': 'RECOVERY_UNVERIFIED', 'lead_module': None, 'trigger_ids': [],
                'monthly_contribution': 0., 'months_to_target': None, 'reserve_gap': None,
                'review_flags': ['RECOVERY_UNVERIFIED: Updated cash, spending, stability and obligation coverage are required; a supported contribution is needed for a rebuild date. No automatic income recovery is assumed.']}
    snapshot = RecoverySnapshot.model_validate(snapshot)
    target = round(snapshot.monthly_spending * reserve_months, 2)
    usable_cash = snapshot.available_cash - snapshot.earmarked_near_term_cash
    gap = round(max(0., target - usable_cash), 2)
    surplus = (round(snapshot.monthly_inflow - snapshot.monthly_spending, 2)
               if snapshot.monthly_inflow is not None else None)
    flags = ['CONDITIONAL_RECOVERY: Timeline uses the supplied checkpoint; simulated cash is not verified current funds.']
    if surplus is None:
        flags.append('INFLOW_UNQUANTIFIED: Monthly inflow and surplus remain unknown; any rebuild date uses only the explicitly supported contribution, stability and obligation coverage.')
    result = {'source': snapshot.source, 'assessment_month': snapshot.assessment_month,
              'cash_basis': snapshot.cash_basis, 'reserve_target': target, 'reserve_gap': gap,
              'current_cash': snapshot.available_cash, 'monthly_surplus': surplus,
              'monthly_contribution': 0., 'months_to_target': None, 'review_flags': flags}
    if (usable_cash < 0 or (surplus is not None and surplus < 0)
            or not snapshot.obligations_covered or not snapshot.stable_cash_flow):
        return {**result, 'status': 'ACTIVE_CRISIS', 'lead_module': None, 'trigger_ids': ['G01'],
                'reason': 'Cash-flow stability and obligation coverage are not established; rebuilding cannot begin.'}
    if gap == 0:
        return {**result, 'status': 'RESERVE_RESTORED', 'lead_module': None, 'trigger_ids': [],
                'reason': 'Reassess the normal goal with updated evidence; no investment suitability is inferred.'}
    bound = snapshot.supported_monthly_contribution
    # A newly supplied regime does not automatically inherit an old savings rate.
    # Use an explicit supported bound, or leave ETA unknown.
    supported = min(surplus, bound) if surplus is not None and bound is not None else bound
    rate = floor(max(0., supported) * 100 + 1e-8) / 100 if supported is not None else 0.
    rate_cents = round(rate * 100)
    gap_cents = round(gap * 100)
    result.update(status='REBUILDING', lead_module='M6', trigger_ids=['G15'],
                  monthly_contribution=rate, months_to_target=(gap_cents + rate_cents - 1) // rate_cents if rate_cents > 0 else None,
                  reason='Rebuild liquid reserves; contributions remain liquid cash, not investment returns.')
    return result
