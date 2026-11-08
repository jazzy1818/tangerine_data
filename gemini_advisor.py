"""Bank-facing action review with a local fallback for the existing replay."""

import json
import math
import os
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict

try:
    from google import genai
    from google.genai import types
    HAVE_GOOGLE_GENAI = True
except ImportError:
    HAVE_GOOGLE_GENAI = False

PLAYBOOK_PATH = Path(__file__).resolve().parent / "shock_playbook.json"
BILL_MOVE = "move_recurring_bill"
SHOCK_TYPES = {"none", "inflow_change", "bill_change", "one_off_expense", "compound"}


class AdvisorSelection(BaseModel):
    """Gemini can select the supported timing scenario or abstain."""

    model_config = ConfigDict(extra="forbid", strict=True)
    primary_action_id: Literal["move_recurring_bill"] | None


def load_playbook_actions() -> List[Dict[str, Any]]:
    """Read the local playbook, falling back to no candidates if it is invalid."""
    try:
        data = json.loads(PLAYBOOK_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    actions = data.get("actions") if isinstance(data, dict) else None
    if not isinstance(actions, list):
        return []
    return [action for action in actions if isinstance(action, dict)]


def consult_gemini_advisor(
    shock_type: str,
    days_to_shortfall: Optional[int],
    cash_needed: Optional[float],
    has_bill_to_shift: bool,
    has_one_off: bool,
    denied_action_ids: Optional[List[str]] = None,
    confirmed_action_ids: Optional[List[str]] = None,
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Select an analyst review action without applying it to projected cash.

    The caller supplies a bill candidate only after checking that the conditional
    replay has a meaningful benefit. Exact replay amounts and dates stay local.
    """
    need_known = cash_needed is not None and math.isfinite(cash_needed) and cash_needed >= 0
    needs_funding = need_known and cash_needed > 0
    resolved_ids = set(denied_action_ids or []) | set(confirmed_action_ids or [])
    bill_card = next(
        (
            action
            for action in load_playbook_actions()
            if action.get("id") == BILL_MOVE
            and isinstance(action.get("title"), str)
            and isinstance(action.get("bank_review"), str)
        ),
        None,
    )
    # The date shift is the only existing action wired to the bank-facing replay.
    candidate = (
        BILL_MOVE
        if needs_funding and has_bill_to_shift and BILL_MOVE not in resolved_ids and bill_card
        else None
    )
    selected = candidate
    source = "deterministic_rules"

    effective_key = api_key or os.environ.get("GEMINI_API_KEY")
    if candidate and HAVE_GOOGLE_GENAI and effective_key:
        if days_to_shortfall is None:
            timing = "unknown"
        elif days_to_shortfall <= 7:
            timing = "within_7_days"
        elif days_to_shortfall <= 30:
            timing = "within_30_days"
        else:
            timing = "later"
        if cash_needed < 1000:
            funding_band = "under_1k"
        elif cash_needed < 5000:
            funding_band = "1k_to_under_5k"
        else:
            funding_band = "5k_or_more"
        context = {
            "shock": shock_type if shock_type in SHOCK_TYPES else "unspecified",
            "shortfall_timing": timing,
            "funding_need_band": funding_band,
            "allowed_action_ids": [candidate],
        }
        prompt = (
            "Select one allowed action for conditional bank analyst review, or return null "
            "for primary_action_id to abstain. A bill-date move remains hypothetical until "
            "its terms and authorization are verified. Return only the structured selection.\n"
            + json.dumps(context)
        )
        try:
            with genai.Client(
                api_key=effective_key,
                http_options=types.HttpOptions(
                    timeout=3500,
                    retry_options=types.HttpRetryOptions(attempts=1),
                ),
            ) as client:
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=AdvisorSelection,
                        temperature=0.2,
                    ),
                )
            selection = AdvisorSelection.model_validate_json(response.text)
            if selection.primary_action_id not in (None, candidate):
                raise ValueError("Advisor returned an unavailable action")
            selected = selection.primary_action_id
            source = "gemini-2.5-flash"
        except Exception:
            # Keep request details and provider exceptions out of the interface.
            source = "deterministic_fallback"

    flags = ["CURRENT_LIQUID_CASH_UNVERIFIED"]
    if selected:
        title = bill_card["title"]
        status = "conditional"
        rationale = bill_card["bank_review"]
        flags.extend(["BANK_REVIEW_REQUIRED", "BILLER_APPROVAL_UNVERIFIED"])
    elif needs_funding or not need_known:
        title = "Bank review required"
        status = "bank_review_required"
        rationale = (
            "The replay shows a remaining funding gap. The available evidence does not support "
            "applying an action to close it."
            if needs_funding
            else "The replay does not provide a reliable funding result. Available cash and timing need analyst review."
        )
        flags.append("BANK_REVIEW_REQUIRED")
    else:
        title = "Maintain and review"
        status = "maintain_and_review"
        rationale = "The modeled path shows no funding gap over the replay window."

    if needs_funding:
        flags.extend(["UNRESOLVED_FUNDING_GAP", "ADJUSTABLE_SPENDING_UNVERIFIED"])
        if has_one_off:
            flags.append("REPAIR_PAYMENT_TERMS_UNVERIFIED")

    return {
        "source": source,
        "is_ai_live": source == "gemini-2.5-flash",
        "plan": {
            "primary_action_id": selected,
            "title": title,
            "status": status,
            "rationale": rationale,
            "bank_review_flags": flags,
        },
    }
