"""Validated, versioned contracts for module selection, independent of plan execution."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ModuleId = Literal['M1', 'M2', 'M3', 'M4', 'M5', 'M6', 'M7', 'M8']
MODULES = {
    'M1': 'Income Continuity',
    'M2': 'Cost Rebalancing',
    'M3': 'Emergency Liquidity',
    'M4': 'Debt & Obligation Defense',
    'M5': 'Multi-Shock Stabilization',
    'M6': 'Reserve Restoration',
    'M7': 'Cash-Flow Timing & Access',
    'M8': 'Surplus & Windfall Allocation',
}
MODULE_DESCRIPTIONS = {
    'M1': 'Recurring inflow loss or disruption.',
    'M2': 'Changed recurring living costs or an unsustainable recurring budget.',
    'M3': 'One-off expenses or immediate liquidity pressure.',
    'M4': 'Changed debt payments, arrears, or threatened essential obligations.',
    'M5': 'Coordinate several financial problems without duplicating their effects.',
    'M6': 'Restore an accessible reserve after depletion or during recovery.',
    'M7': 'Delayed payments, frozen cash, or within-month liquidity timing.',
    'M8': 'Allocate positive surplus, raises, or windfalls; liquidity priorities still apply.',
}


class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False, validate_assignment=True,
                              str_strip_whitespace=True)


class CustomerFeatures(Contract):
    """Ratios are not probabilities. None explicitly represents an undefined ratio."""
    surplus_margin: float | None = Field(le=1)
    reserve_months: float | None
    fixed_cost_ratio: float | None = Field(ge=0)
    debt_payment_ratio: float | None = Field(ge=0)
    inflow_iqr_ratio: float | None = Field(ge=0)
    deficit_month_share: float | None = Field(ge=0, le=1)
    negative_balance_month_share: float | None = Field(ge=0, le=1)
    recovered_overdraft_month_share: float | None = Field(ge=0, le=1)
    balance_change_to_spending: float | None
    active_loan: bool | None
    loan_in_arrears: bool | None
    months_observed: int = Field(ge=1)
    recent_months: int = Field(ge=0, le=12)
    stale_months: int = Field(ge=0)
    quality_flags: list[str] = Field(default_factory=list)


class Baseline(Contract):
    I: float = Field(ge=0)
    S: float = Field(ge=0)
    F: float = Field(ge=0)
    H: float = Field(ge=0)
    B: float
    P: float | None = Field(default=None, ge=0)
    runway: float | str


class CustomerProfile(Contract):
    account_id: int
    as_of: str
    last_month: str
    baseline: Baseline
    features: CustomerFeatures


EffectType = Literal[
    'income_multiplier', 'income_delta', 'expense_delta', 'expense_percent',
    'household_bills_percent', 'household_bills_delta', 'debt_payment_delta',
    'one_off_cost', 'one_off_receipt', 'liquidity_hold', 'payment_delay_days',
    'investment_return', 'unspecified_event',
]
ONE_TIME = {'one_off_cost', 'one_off_receipt'}
MONEY_EFFECTS = {
    'income_delta', 'expense_delta', 'household_bills_delta', 'debt_payment_delta',
    'one_off_cost', 'one_off_receipt', 'liquidity_hold',
}


class ShockEffect(Contract):
    type: EffectType
    value: float | None = Field(default=None, strict=True)
    start_month: int = Field(default=1, ge=0, le=120)
    duration_months: int | None = Field(default=None, ge=1, le=120)
    ongoing: bool = False
    evidence: Literal['judge_specified', 'user_confirmed', 'assumed', 'unknown'] = 'judge_specified'

    @model_validator(mode='after')
    def valid_effect(self):
        v = self.value
        if self.ongoing and (self.duration_months is not None or self.type in ONE_TIME | {'unspecified_event'}):
            raise ValueError('ongoing requires a recurring/access effect with no finite duration.')
        if self.type == 'unspecified_event':
            if v is not None:
                raise ValueError('An unspecified event cannot have an invented numeric value.')
            return self
        if v is not None:
            if self.type in {'income_multiplier', 'one_off_cost', 'one_off_receipt',
                             'liquidity_hold', 'payment_delay_days'} and v < 0:
                raise ValueError(f'{self.type} must be nonnegative.')
            if self.type in {'expense_percent', 'household_bills_percent', 'investment_return'} and v < -100:
                raise ValueError('A percentage decrease cannot exceed 100%.')
        if self.type in ONE_TIME and self.duration_months is not None:
            raise ValueError('One-off events cannot repeat; omit duration_months.')
        if self.type not in ONE_TIME and self.start_month == 0:
            raise ValueError('Recurring/access effects start at month 1 or later; month 0 is for one-offs.')
        return self

    def active(self, month: int) -> bool:
        if self.type in ONE_TIME:
            return month == self.start_month
        return month >= self.start_month and (
            self.duration_months is None or month < self.start_month + self.duration_months)


class ShockScenario(Contract):
    # Narrative is LOCAL ONLY, excluded from the canonical classifier input.
    description: str = Field(default='', max_length=2000)
    phase: Literal['active', 'recovery', 'normal'] = 'active'
    horizon_months: int = Field(default=6, ge=1, le=120)
    effects: list[ShockEffect] = Field(default_factory=list, max_length=32)

    @model_validator(mode='after')
    def no_double_counting(self):
        if self.phase == 'normal' and any(
            effect.value is None or effect.evidence == 'unknown'
            or (effect.value != 1 if effect.type == 'income_multiplier' else effect.value != 0)
            for effect in self.effects
        ):
            raise ValueError('A normal/no-change scenario cannot contain financial shocks; use phase active.')
        for i, left in enumerate(self.effects):
            for right in self.effects[i + 1:]:
                # Provenance cannot make the same financial charge a second event.
                if left.model_dump(exclude={'evidence'}) == right.model_dump(exclude={'evidence'}):
                    raise ValueError('Duplicate effects: combine distinct costs before submission.')
                overlap = any(left.active(m) and right.active(m) for m in range(121))
                if not overlap:
                    continue
                if left.type == right.type and left.type not in ONE_TIME | {'unspecified_event'}:
                    raise ValueError(f'Overlapping {left.type} effects: supply one net change per period.')
                pair = {left.type, right.type}
                outflows = {'expense_delta', 'expense_percent', 'household_bills_delta',
                            'household_bills_percent', 'debt_payment_delta'}
                if ('expense_percent' in pair and pair <= outflows) or pair == {
                    'household_bills_delta', 'household_bills_percent'}:
                    raise ValueError('Overlapping broad/category cost changes need an explicit net delta.')
        return self


class FinancialConstraints(Contract):
    allowed_modules: list[ModuleId] = Field(default_factory=lambda: list(MODULES), min_length=1)
    reserve_target_months: float = Field(default=3, gt=0, le=24)
    essential_obligations_at_risk: bool | None = None
    timing_mismatch_confirmed: bool | None = None
    # Module selection never treats these actions as approved.
    spending_cuts_confirmed: bool = False
    credit_approved: bool = False
    insurance_payout_confirmed: bool = False

    @model_validator(mode='after')
    def unique_allowed(self):
        if len(set(self.allowed_modules)) != len(self.allowed_modules):
            raise ValueError('allowed_modules must be unique.')
        return self


ReasonCode = Literal[
    'income_reduction', 'income_increase', 'cost_increase', 'cost_reduction',
    'one_off_expense', 'windfall', 'debt_payment_change', 'timing_or_access',
    'compound_effects', 'reserve_below_target', 'recurring_shortfall',
    'immediate_liquidity_pressure', 'historical_timing_stress', 'recovery',
    'surplus_available', 'missing_details', 'no_new_effect', 'investment_change',
    'essential_obligations_at_risk', 'restricted_modules',
]


class NormalizedEffect(Contract):
    type: EffectType
    value: float | None
    unit: Literal['ratio', 'percent', 'days', 'cash_scale', 'unknown']
    start_month: int = Field(ge=0, le=120)
    duration_months: int | None = Field(ge=1, le=120)
    ongoing: bool = False
    cashflow_delta_to_scale: float | None = None
    evidence: Literal['judge_specified', 'user_confirmed', 'assumed', 'unknown']


class ClassificationCase(Contract):
    schema_version: Literal['1.1'] = '1.1'
    features: CustomerFeatures
    effects: list[NormalizedEffect]
    phase: Literal['active', 'recovery', 'normal']
    horizon_months: int = Field(ge=1, le=120)
    constraints: FinancialConstraints
    observed_reasons: list[ReasonCode]
    missing_details: list[str]
    # Screening features only. The existing finance engine owns full cash paths.
    first_period_gap_to_scale: float
    immediate_buffer_to_scale: float
    first_period_runway_months: float | None
    first_period_no_shortfall: bool


class PlanSelection(Contract):
    lead_module: ModuleId
    support_modules: list[ModuleId] = Field(default_factory=list, max_length=2)
    reason_codes: list[ReasonCode] = Field(min_length=1, max_length=20)
    needs_clarification: list[str] = Field(default_factory=list, max_length=96)
    rationale: str = Field(min_length=1, max_length=1200)

    @model_validator(mode='after')
    def distinct_modules(self):
        if self.lead_module in self.support_modules or len(set(self.support_modules)) != len(self.support_modules):
            raise ValueError('Lead and supporting modules must be distinct.')
        if len(set(self.reason_codes)) != len(self.reason_codes):
            raise ValueError('reason_codes must be unique.')
        return self


class SelectionResult(Contract):
    selection: PlanSelection
    requested_backend: Literal['rules', 'jev', 'gemini']
    actual_backend: Literal['rule_baseline', 'jev', 'gemini']
    fallback_used: bool = False
    fallback_reason: str | None = None
    implementation_version: str
    model_version: str | None = None
    prompt_version: str | None = None
    input_hash: str
    elapsed_ms: float = Field(ge=0)
    api_calls: int = Field(default=0, ge=0)
    invalid_outputs: int = Field(default=0, ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    thought_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    usage_complete: bool = False
    cost_usd: float | None = Field(default=None, ge=0)
    provider_confidence: float | None = Field(default=None, ge=0, le=1)
    module_probabilities: dict[ModuleId, float] | None = None
    rationale_source: Literal['rules', 'model', 'evidence_template'] = 'rules'
