"""HTTP inputs. Financial contracts stay owned by the existing engine modules."""
from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from crisis_response import ExistingGoalTransfer, NormalGoal
from plan_classification.schemas import Contract, ShockScenario
from recovery_plan import RecoverySnapshot
from .savings import SavingsEvidence


class ReviewDetails(Contract):
    purpose: Literal['cash_flow', 'unexpected_cost', 'debt', 'recovery', 'savings', 'other'] = 'cash_flow'
    prepared_by: str = Field(default='', max_length=120)
    customer_priority: str = Field(default='', max_length=2000)
    cash_source: str = Field(default='', max_length=500)


class ScenarioInput(Contract):
    account_id: int = Field(ge=1)
    scenario: ShockScenario
    opening_cash: float | None = Field(default=None, ge=-1e12, le=1e12)
    normal_goal: NormalGoal | None = None
    existing_transfers: list[ExistingGoalTransfer] = Field(default_factory=list, max_length=120)
    recovery_snapshot: RecoverySnapshot | None = None
    review_details: ReviewDetails = Field(default_factory=ReviewDetails)
    savings_evidence: SavingsEvidence | None = None


class RunInput(ScenarioInput):
    request_id: UUID
    backend: Literal['rules', 'jev', 'gemini'] = 'rules'
    title: str = Field(default='Scenario review', min_length=1, max_length=120)


class ReviewUpdate(Contract):
    version: int = Field(ge=0)
    status: Literal['in_progress', 'awaiting_information', 'ready_to_discuss', 'follow_up', 'closed'] = 'in_progress'
    owner: str = Field(default='', max_length=120)
    follow_up_date: date | None = None
    notes: str = Field(default='', max_length=4000)
    completed_items: list[str] = Field(default_factory=list, max_length=30)

    @model_validator(mode='after')
    def review_fields(self):
        if self.status == 'follow_up' and self.follow_up_date is None:
            raise ValueError('Choose a date for the follow-up.')
        if len(set(self.completed_items)) != len(self.completed_items) or any(len(s) > 100 for s in self.completed_items):
            raise ValueError('Follow-up checklist entries must be unique and no longer than 100 characters.')
        return self
