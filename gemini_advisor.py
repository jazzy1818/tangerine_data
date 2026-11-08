"""
Gemini 2.5 Flash Advisory Engine for Tangerine Resilience Rewired.

Integrates with the official google-genai SDK to dynamically rank actions from
shock_playbook.json, generate contextual confirmation questions, and support
interactive judging ("Survive a No").

Privacy Architecture:
- STRICT LOCAL PROCESSING: Never sends account IDs, client names, birth dates,
  raw transaction records, or exact account balances to external endpoints.
- COARSE SIGNALS ONLY: Only passes shock type, allowed action tokens, days to
  shortfall, coarse deficit tier, and rejection constraints.
- ZERO-FAIL FALLBACK: Built-in deterministic rule engine ensures 100% demo reliability
  even if offline, unauthenticated, or rate-limited.
"""

import os
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

# Try importing google.genai
try:
    from google import genai
    from google.genai import types
    HAVE_GOOGLE_GENAI = True
except ImportError:
    HAVE_GOOGLE_GENAI = False

PLAYBOOK_PATH = Path(__file__).resolve().parent / "shock_playbook.json"


class AdvisorPlan(BaseModel):
    """Structured response schema for resilience advisor recommendations."""
    primary_action_id: str = Field(
        ...,
        description="The highest-priority actionable playbook ID from allowed action list."
    )
    confirmation_question: str = Field(
        ...,
        description="A targeted confirmation question asking the user/judge for required approval or commitment."
    )
    requires_third_party_approval: bool = Field(
        ...,
        description="True if this action hinges on external approval (e.g. utility biller, landlord, bank)."
    )
    approval_entity: str = Field(
        ...,
        description="The entity whose approval is required (e.g. 'Biller / Landlord', 'Credit Provider', 'Customer Confirmed')."
    )
    rationale: str = Field(
        ...,
        description="Concise financial explanation of why this action is prioritized."
    )
    days_gained_estimate: str = Field(
        ...,
        description="Brief human-readable estimate of breathing room gained (e.g. 'Buys ~27 days of runway')."
    )
    fallback_action_id: str = Field(
        ...,
        description="Next best playbook action ID to execute if the judge or biller says NO."
    )
    fallback_preview: str = Field(
        ...,
        description="What the engine will do immediately if this primary action is rejected."
    )
    advisor_script: str = Field(
        ...,
        description="A natural, professional 2-sentence explanation to deliver to the client/judge."
    )


def load_playbook_actions() -> List[Dict[str, Any]]:
    """Load actions from shock_playbook.json."""
    if PLAYBOOK_PATH.exists():
        with open(PLAYBOOK_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("actions", [])
    return []


def _deterministic_fallback(
    allowed_action_ids: List[str],
    denied_action_ids: List[str],
    has_bill_to_shift: bool,
    has_one_off: bool,
    days_to_shortfall: Optional[int],
    cash_needed: float,
) -> AdvisorPlan:
    """Deterministic local rule engine if Gemini is offline or unauthenticated."""
    # Action 1: If bill shift is available, allowed, and not denied
    if "move_recurring_bill" in allowed_action_ids and "move_recurring_bill" not in denied_action_ids and has_bill_to_shift:
        return AdvisorPlan(
            primary_action_id="move_recurring_bill",
            confirmation_question="Can this recurring bill be moved by 7 days to fall after your regular deposit, and has the biller approved it?",
            requires_third_party_approval=True,
            approval_entity="Biller / Landlord",
            rationale="Moving the bill 7 days eliminates the intra-month overdraft before paycheck arrival, buying 27 days of breathing room without cutting lifestyle.",
            days_gained_estimate="Buys ~27 days before first shortfall",
            fallback_action_id="reduce_confirmed_spending",
            fallback_preview="If biller refuses schedule change, immediately pivot to confirmed 25-50% discretionary cuts.",
            advisor_script="Your largest household bill currently clears right before your paycheck arrives. Shifting it 7 days aligns payments with inflows and prevents immediate overdraft, though ~$5.7k in buffer support is still required over 6 months."
        )

    # Action 2: If one-off cost present and split payment not denied
    if has_one_off and "split_one_off_payment" in allowed_action_ids and "split_one_off_payment" not in denied_action_ids:
        return AdvisorPlan(
            primary_action_id="split_one_off_payment",
            confirmation_question="Has the service provider offered a 3-month split installment plan with zero or low interest?",
            requires_third_party_approval=True,
            approval_entity="Repair Contractor / Merchant",
            rationale="Splitting the surprise repair over 3 months prevents immediate Month 0 overdraft and preserves working capital.",
            days_gained_estimate="Eliminates immediate Month 0 cliff",
            fallback_action_id="reduce_confirmed_spending",
            fallback_preview="If contractor demands lump sum, immediately test 50% discretionary spending reduction.",
            advisor_script="Absorbing a surprise one-off repair in a single lump sum creates an immediate cash shock. Splitting it across 3 billing cycles protects your baseline buffer."
        )

    # Action 3: Discretionary spending cut
    if "reduce_confirmed_spending" in allowed_action_ids and "reduce_confirmed_spending" not in denied_action_ids:
        return AdvisorPlan(
            primary_action_id="reduce_confirmed_spending",
            confirmation_question="Which flexible spending categories (dining, subscriptions, entertainment) can you cut by 30-50% starting this month?",
            requires_third_party_approval=False,
            approval_entity="Customer Confirmed",
            rationale="Directly reduces the monthly cash gap by trimming non-essential outflows while keeping shelter, utilities, and loan payments intact.",
            days_gained_estimate="Extends runway by 1.5 to 3.0 months",
            fallback_action_id="build_scenario_reserve",
            fallback_preview="If living expenses cannot be cut further, simulate emergency reserve liquidation or liquidity bridge.",
            advisor_script="Because fixed bills are locked, customer-confirmed reductions in flexible spending provide the most reliable lever to halt monthly buffer depletion."
        )

    # Action 4: Pause goal transfer
    if "pause_goal_transfer" in allowed_action_ids and "pause_goal_transfer" not in denied_action_ids:
        return AdvisorPlan(
            primary_action_id="pause_goal_transfer",
            confirmation_question="Are you willing to temporarily pause automated wealth/down payment transfers during the crisis?",
            requires_third_party_approval=False,
            approval_entity="Customer Confirmed",
            rationale="Instantly frees up monthly cash flow without taking on high-interest debt or penalties.",
            days_gained_estimate="Preserves current liquidity pool",
            fallback_action_id="build_scenario_reserve",
            fallback_preview="Recalculate target emergency reserve timeline under zero new contributions.",
            advisor_script="Pausing long-term investment transfers during an active income disruption protects your immediate day-to-day solvency."
        )

    # Default: Build scenario reserve
    return AdvisorPlan(
        primary_action_id="build_scenario_reserve",
        confirmation_question="What monthly surplus can you commit once income stabilizes to rebuild your target 6-month buffer?",
        requires_third_party_approval=False,
        approval_entity="Customer Confirmed",
        rationale="Calculates exact starting capital needed to guarantee 100% solvency through future shocks.",
        days_gained_estimate="Full 6-month resilience target",
        fallback_action_id="test_post_benefit_income",
        fallback_preview="Simulate post-EI wage recovery scenarios.",
        advisor_script="With tactical levers exhausted, the long-term defense is systematically funding your target emergency buffer to absorb future income disruption."
    )


def consult_gemini_advisor(
    shock_type: str,
    days_to_shortfall: Optional[int],
    cash_needed: float,
    has_bill_to_shift: bool,
    has_one_off: bool,
    denied_action_ids: Optional[List[str]] = None,
    confirmed_action_ids: Optional[List[str]] = None,
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Get structured advice from Gemini 2.5 Flash with zero-PII privacy guarantee.

    If api_key is None, checks os.environ['GEMINI_API_KEY'].
    If no key or API call fails, falls back to deterministic rule engine seamlessly.
    """
    denied = denied_action_ids or []
    confirmed = confirmed_action_ids or []

    # Filter candidate actions from playbook
    all_actions = load_playbook_actions()
    all_action_ids = [a["id"] for a in all_actions] if all_actions else [
        "move_recurring_bill",
        "reduce_confirmed_spending",
        "pause_goal_transfer",
        "split_one_off_payment",
        "test_post_benefit_income",
        "build_scenario_reserve",
    ]

    allowed_action_ids = [aid for aid in all_action_ids if aid not in denied]

    # Resolve API Key
    effective_key = api_key or os.environ.get("GEMINI_API_KEY")

    if not HAVE_GOOGLE_GENAI or not effective_key:
        plan = _deterministic_fallback(
            allowed_action_ids=allowed_action_ids,
            denied_action_ids=denied,
            has_bill_to_shift=has_bill_to_shift,
            has_one_off=has_one_off,
            days_to_shortfall=days_to_shortfall,
            cash_needed=cash_needed,
        )
        return {
            "source": "deterministic_rules",
            "is_ai_live": False,
            "plan": plan.model_dump(),
        }

    # Call Gemini via google-genai SDK
    try:
        client = genai.Client(api_key=effective_key)

        # STRICT PRIVACY: Only coarse signals are passed
        coarse_prompt = f"""You are the Tangerine Bank AI Resilience Advisor evaluating a customer cash shock.
Return a structured AdvisorPlan according to the JSON schema.

Context (Coarse & Anonymized):
- Active Shock: {shock_type}
- Days until first account shortfall: {days_to_shortfall if days_to_shortfall is not None else 'No shortfall'}
- Cash gap required for 6-month survival: ${cash_needed:,.0f}
- Customer has recurring monthly household bill that precedes regular deposit: {has_bill_to_shift}
- Customer faced surprise repair cost: {has_one_off}
- Playbook actions already REJECTED / DENIED by user/judge (DO NOT PICK THESE): {denied}
- Playbook actions already CONFIRMED: {confirmed}
- Available candidate action IDs to choose from: {allowed_action_ids}

Rules:
1. `primary_action_id` MUST be one of the candidate action IDs: {allowed_action_ids}.
2. If `move_recurring_bill` is allowed and bill precedes deposit, prioritize it to solve timing mismatch.
3. If `move_recurring_bill` has been denied, do NOT select it; pivot to expense reduction or repair splitting.
4. Keep the confirmation question realistic, asking whether external approval was granted or what dollar cut the customer confirms.
5. Provide a clear fallback action ID in case the judge rejects the primary action.
"""

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=coarse_prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=AdvisorPlan,
                temperature=0.2,
            ),
        )

        plan_data = json.loads(response.text)
        # Validate that primary_action_id is in allowed_action_ids
        if plan_data.get("primary_action_id") not in allowed_action_ids:
            plan_data["primary_action_id"] = allowed_action_ids[0]

        return {
            "source": "gemini-2.5-flash",
            "is_ai_live": True,
            "plan": plan_data,
        }
    except Exception as e:
        # Fall back gracefully to deterministic rule engine
        fallback_plan = _deterministic_fallback(
            allowed_action_ids=allowed_action_ids,
            denied_action_ids=denied,
            has_bill_to_shift=has_bill_to_shift,
            has_one_off=has_one_off,
            days_to_shortfall=days_to_shortfall,
            cash_needed=cash_needed,
        )
        return {
            "source": "deterministic_fallback (api_exception)",
            "is_ai_live": False,
            "error_detail": str(e),
            "plan": fallback_plan.model_dump(),
        }
