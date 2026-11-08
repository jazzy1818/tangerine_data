"""Deterministic, bank-facing surplus allocation review; no securities or trades.

Official judging metrics stay in engine.py. This module uses trailing observations
and explicit policy/scenario assumptions. Historical capacity and replay are
in-sample diagnostics, never a promise about future cash or investment suitability.
All cash leaving for an allocation is debited; returns, insurance and new credit
are not assumed. Reserve earmarks remain liquid cash, not newly created wealth.
"""

from dataclasses import asdict, dataclass
from copy import deepcopy
from math import ceil, floor, isfinite
from typing import Optional

import pandas as pd
from goal_validation import enforce_goal_validations
from crisis_rules import goal_worsened


@dataclass(frozen=True)
class InvestmentPolicy:
    """Configurable illustrative bank policy, not regulatory suitability rules."""

    history_months: int = 12
    minimum_history_months: int = 6
    projection_months: int = 6
    reserve_months: float = 3.0
    operating_cash_months: float = 1.0
    allocation_fraction: float = 0.75
    minimum_surplus_ratio: float = 0.05
    fixed_payment_ratio: float = 0.60
    loan_payment_ratio: float = 0.20
    inflow_volatility_ratio: float = 0.50
    deterioration_ratio: float = 0.25
    unusual_inflow_multiple: float = 3.0
    near_term_months: int = 24

    def __post_init__(self):
        for name in ("history_months", "minimum_history_months", "projection_months", "near_term_months"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if not 6 <= self.minimum_history_months <= self.history_months:
            raise ValueError("Use at least six months, within the configured history window")
        for name, value in asdict(self).items():
            if not isfinite(value) or value < 0:
                raise ValueError(f"Invalid policy value: {name}")
        for name in ("allocation_fraction", "minimum_surplus_ratio", "fixed_payment_ratio", "loan_payment_ratio", "deterioration_ratio"):
            if not 0 < getattr(self, name) <= 1:
                raise ValueError(f"{name} must be in (0, 1]")
        if self.reserve_months < self.operating_cash_months or self.operating_cash_months <= 0:
            raise ValueError("Reserve months must cover the positive operating cash floor")
        if self.unusual_inflow_multiple <= 1:
            raise ValueError("Unusual inflow multiple must exceed one")


@dataclass(frozen=True)
class KnownExpense:
    """Additional scenario obligation, not an expense already in monthly outflows.

    due_month is relative to the assessment (0 means immediate). Do not repeat
    the judge's one-off expense here. Evidence must be supplied by the analyst's
    authorized record/scenario, never inferred from demographics.
    """

    amount: Optional[float]
    due_month: Optional[int]
    description: str

    def __post_init__(self):
        if self.amount is not None and (not isfinite(self.amount) or self.amount <= 0):
            raise ValueError("Known expense must have a positive finite amount")
        if self.due_month is not None and (isinstance(self.due_month, bool) or not isinstance(self.due_month, int) or self.due_month < 0):
            raise ValueError("Expense due month must be a nonnegative integer")
        if not self.description.strip():
            raise ValueError("Known expense needs a description")


@dataclass(frozen=True)
class AnalystEvidence:
    """Optional facts explicitly provided by an authorized record or scenario.

    The competition adapter supplies none of these by default. Values describe
    the assessment date, not automatically today's financial circumstances.
    Even a complete profile only enables analyst review, not product approval.
    """

    source: str = ""
    available_cash: Optional[float] = None
    sole_control_verified: bool = False
    known_expenses: tuple[KnownExpense, ...] = ()
    objective: Optional[str] = None
    horizon_months: Optional[int] = None
    risk_tolerance: Optional[str] = None
    capacity_for_loss: Optional[str] = None
    holdings_reviewed: bool = False
    obligations_reviewed: bool = False
    costly_debt_verified: bool = False
    goal_completed_verified: bool = False
    prior_shock_verified: bool = False
    windfall_verified: bool = False
    equities_excluded: Optional[bool] = None
    event_description: str = ""
    event_financial_effect: Optional[str] = None

    def __post_init__(self):
        if not isinstance(self.source, str):
            raise ValueError("Evidence source must be text")
        for name in ("sole_control_verified", "holdings_reviewed", "obligations_reviewed", "costly_debt_verified", "goal_completed_verified", "prior_shock_verified", "windfall_verified"):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be a boolean")
        for name in ("source", "objective", "risk_tolerance", "capacity_for_loss"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or (name != "source" and not value.strip())):
                raise ValueError(f"{name} must contain text when supplied")
        if any(not isinstance(expense, KnownExpense) for expense in self.known_expenses):
            raise ValueError("Known expenses must be KnownExpense records")
        if self.equities_excluded is not None and not isinstance(self.equities_excluded, bool):
            raise ValueError("Equity preference must be explicitly boolean or unknown")
        if not isinstance(self.event_description, str):
            raise ValueError("Event description must be text")
        if self.event_financial_effect not in (None, "unspecified", "none", "quantified"):
            raise ValueError("Event financial effect must be unspecified, none, or quantified")
        if self.event_description and self.event_financial_effect is None:
            raise ValueError("An event needs an explicit financial-effect status; never infer dollars from its name")
        if self.event_financial_effect is not None and not self.event_description.strip():
            raise ValueError("An event status requires a description")
        supplied = self.available_cash is not None or any((
            self.sole_control_verified, self.known_expenses, self.objective,
            self.horizon_months is not None, self.risk_tolerance, self.capacity_for_loss,
            self.holdings_reviewed, self.obligations_reviewed, self.costly_debt_verified,
            self.goal_completed_verified,
            self.prior_shock_verified, self.windfall_verified,
            self.equities_excluded is not None, self.event_description,
        ))
        if supplied and not self.source.strip():
            raise ValueError("Additional facts require an evidence source")
        if self.available_cash is not None and (not isfinite(self.available_cash) or self.available_cash < 0):
            raise ValueError("Available cash must be finite and nonnegative")
        if self.horizon_months is not None and (
            isinstance(self.horizon_months, bool) or not isinstance(self.horizon_months, int) or self.horizon_months < 1
        ):
            raise ValueError("Investment horizon must be a positive integer")


@dataclass(frozen=True)
class StressScenario:
    name: str
    income_multiplier: float = 1.0
    bills_increase_pct: float = 0.0
    one_off_costs: float = 0.0
    one_off_receipt: float = 0.0

    def __post_init__(self):
        if not self.name.strip():
            raise ValueError("Scenario needs a name")
        if not all(isfinite(x) for x in (self.income_multiplier, self.bills_increase_pct, self.one_off_costs, self.one_off_receipt)):
            raise ValueError("Scenario values must be finite")
        if self.income_multiplier < 0 or self.bills_increase_pct < -1 or self.one_off_costs < 0 or self.one_off_receipt < 0:
            raise ValueError("Scenario cannot create negative inflows, household bills, or one-off costs")


def _down(value):
    """Never round a proposed transfer above its computed capacity."""
    return floor(max(0.0, value) * 100 + 1e-8) / 100


def _money(value):
    return round(float(value), 2)


def _flexible_reserve_review(rows, policy, *, reserve_gap, cash_floor,
                             opening, expenses, blocked):
    """Retrospective variable liquid-saving capacity, never a standing transfer.

    A deficit month contributes zero, rather than disqualifying every other
    month. Earmarked money stays accessible; it is neither an investment debit
    nor extra cash in any projection. Today's affordable amount needs a separate
    current, account-specific obligations/cash review.
    """
    result = {'status': 'not_supported', 'current_set_aside': None,
              'fixed_monthly_commitment': False, 'months_to_target': None,
              'basis': 'HISTORICAL_CONDITIONAL_REVIEW', 'review_months': [],
              'opportunity_months': 0, 'observed_months': len(rows),
              'typical_positive_month_amount': 0.,
              'allocation_fraction': policy.allocation_fraction,
              'remaining_reserve_goal': _down(reserve_gap),
              'rule': 'In a positive month only: min(fraction × realized surplus, cash above protected cushion/obligations, remaining reserve goal). Keep funds liquid; skip deficit months.',
              'required_evidence': ['Current accessible cash and account authority',
                  'Reliable next income date and all commitments through then',
                  'Remaining reserve goal and its source/policy',
                  'Confirm this month has a realized surplus; do not use a forecast as cash'],
              'reason': blocked or 'Insufficient observed positive months with protected cash.'}
    if blocked:
        return result
    hold = cash_floor + sum(e.amount for e in expenses)
    for _, row in rows.iterrows():
        net = float(row['money_in'] - row['money_out'])
        room = max(0., float(row['min_balance']) - hold)
        candidate = _down(min(max(0., net) * policy.allocation_fraction, room, reserve_gap))
        result['review_months'].append({'month': str(row['_month']),
            'observed_surplus': _money(net), 'protected_cash': _money(hold),
            'observed_minimum_cash': _money(row['min_balance']),
            'conditional_liquid_savings': candidate})
    amounts = [r['conditional_liquid_savings'] for r in result['review_months'] if r['conditional_liquid_savings'] > 0]
    result['opportunity_months'] = len(amounts)
    # At least half the completed months must show a protected opportunity.
    # Also require capacity in the most recent month, not just distant history.
    if (len(amounts) >= ceil(len(rows) / 2) and result['review_months'][-1]['conditional_liquid_savings'] > 0
            and opening >= hold):
        result.update(status='conditional_review',
            typical_positive_month_amount=_down(float(pd.Series(amounts).median())),
            reason='Variable liquid-reserve saving merits review. This is not a fixed monthly commitment or verified cash available today.')
    return result


def simulate_allocation(*, opening_cash, monthly_inflow, monthly_spending,
                        household_bills, contribution, cash_floor, scenario,
                        months=6, known_expenses=()):
    """Month-end conditional path including an opening checkpoint.

    Outflows already include fixed costs and loan payments. Neither is added
    again. Allocations leave accessible cash; no return or redemption is assumed.
    Future obligations beyond the horizon are protected as an extra cash floor.
    Daily solvency is not established by monthly projections.
    """
    if isinstance(months, bool) or not isinstance(months, int) or months < 1:
        raise ValueError("Projection months must be a positive integer")
    values = (opening_cash, monthly_inflow, monthly_spending, household_bills, contribution, cash_floor)
    if not all(isfinite(x) for x in values) or min(values[1:]) < 0:
        raise ValueError("Projection inputs must be finite; flows, contribution and floor nonnegative")
    if household_bills > monthly_spending:
        raise ValueError("Household bills must already be part of monthly spending")
    if any(e.amount is None or e.due_month is None for e in known_expenses):
        raise ValueError("Cannot quantify an expense without both amount and timing")
    net = monthly_inflow * scenario.income_multiplier - monthly_spending - household_bills * scenario.bills_increase_pct
    future_hold = sum(e.amount for e in known_expenses if e.due_month > months)
    required_floor = cash_floor + future_hold
    balance = opening_cash + scenario.one_off_receipt - scenario.one_off_costs - sum(e.amount for e in known_expenses if e.due_month == 0)
    initial = balance
    minimum = balance
    breach = 0 if balance < required_floor - 1e-8 else None
    shortfall = 0 if balance < -1e-8 else None
    schedule = [{"month": 0, "opening_cash": _money(opening_cash), "net_cash_flow": 0.0,
                 "contribution": 0.0, "one_off_receipt": scenario.one_off_receipt,
                 "extra_expenses": _money(opening_cash + scenario.one_off_receipt - balance), "closing_cash": _money(balance)}]
    for month in range(1, months + 1):
        start = balance
        expense = sum(e.amount for e in known_expenses if e.due_month == month)
        balance += net - contribution - expense
        minimum = min(minimum, balance)
        if balance < required_floor - 1e-8 and breach is None:
            breach = month
        if balance < -1e-8 and shortfall is None:
            shortfall = month
        schedule.append({"month": month, "opening_cash": _money(start), "net_cash_flow": _money(net),
                         "contribution": contribution, "one_off_receipt": 0.0, "extra_expenses": _money(expense), "closing_cash": _money(balance)})
    return {
        "scenario": scenario.name, "monthly_contribution": contribution,
        "monthly_net_before_contribution": _money(net), "initial_cash_after_costs": _money(initial),
        "minimum_cash": _money(minimum), "ending_cash": _money(balance),
        "required_cash_floor": _money(required_floor), "first_floor_breach_month": breach,
        "first_shortfall_month": shortfall, "preserves_cash_floor": breach is None,
        "nonnegative_cash": shortfall is None,
        "additional_cash_needed": ceil(max(0.0, -minimum) * 100 - 1e-8) / 100,
        "allocated_total": _money(months * contribution), "schedule": schedule,
    }


def _capacity(opening, income, spending, bills, cash_floor, scenario, months, expenses):
    """Maximum fixed monthly amount preserving the floor at all checkpoints.

    Also cap at net inflow: investing is not funded by drawing down a reserve.
    """
    net = income * scenario.income_multiplier - spending - bills * scenario.bills_increase_pct
    required = cash_floor + sum(e.amount for e in expenses if e.due_month > months)
    start = opening + scenario.one_off_receipt - scenario.one_off_costs - sum(e.amount for e in expenses if e.due_month == 0)
    if start < required:
        return 0.0
    bounds = [net]
    for month in range(1, months + 1):
        due = sum(e.amount for e in expenses if 0 < e.due_month <= month)
        bounds.append((start + month * net - due - required) / month)
    return _down(min(bounds))


def _history_frame(history, policy, as_of):
    issues = []
    if not isinstance(history, pd.DataFrame) or history.empty:
        return pd.DataFrame(), ["No monthly history is available."]
    required = {"month", "money_in", "money_out", "household_bills", "avg_daily_balance"}
    if not required.issubset(history.columns):
        return pd.DataFrame(), ["Required monthly cash-flow fields are missing."]
    rows = history.copy()
    try:
        rows["_month"] = pd.PeriodIndex(rows["month"], freq="M")
        if rows["_month"].isna().any():
            raise ValueError("Missing month")
        if as_of is not None:
            rows = rows.loc[rows["_month"] <= pd.Period(as_of, freq="M")]
    except (ValueError, TypeError):
        return pd.DataFrame(), ["Month values or the assessment month are invalid."]
    if rows.empty:
        return pd.DataFrame(), ["No observations exist at or before the assessment month."]
    # Calendar window, not merely the last N rows: missing months cannot vanish.
    last = rows["_month"].max()
    rows = rows.loc[rows["_month"] >= last - policy.history_months + 1].sort_values("_month")
    if rows["_month"].duplicated().any():
        issues.append("Duplicate account-month records.")
    if len(rows) != last.ordinal - rows["_month"].min().ordinal + 1:
        issues.append("Missing calendar months in the observation window.")
    if len(rows) < policy.minimum_history_months:
        issues.append(f"At least {policy.minimum_history_months} completed monthly observations are required.")
    for column in required - {"month"}:
        rows[column] = pd.to_numeric(rows[column], errors="coerce")
        if not rows[column].map(lambda x: isfinite(x)).all():
            issues.append(f"Nonfinite or missing {column}.")
    if (rows[["money_in", "money_out", "household_bills"]] < 0).any().any():
        issues.append("Negative inflow or spending amount.")
    if (rows["household_bills"] > rows["money_out"] + .01).any():
        issues.append("Household bills exceed total outflows.")
    for column in ("min_balance", "month_end_balance", "days_below_zero", "insurance", "loan_payments"):
        if column in rows:
            rows[column] = pd.to_numeric(rows[column], errors="coerce")
            if not rows[column].map(isfinite).all():
                issues.append(f"Nonfinite or missing {column}.")
    if "days_below_zero" in rows:
        days = rows["days_below_zero"]
        if ((days < 0) | (days > rows["_month"].dt.days_in_month) | (days != days.round())).any():
            issues.append("Invalid negative-balance day count.")
    if {"min_balance", "month_end_balance"}.issubset(rows):
        if (rows["min_balance"] > rows["month_end_balance"] + .01).any():
            issues.append("Minimum balance exceeds closing balance.")
    if {"insurance", "loan_payments"}.issubset(rows):
        fixed = rows[["household_bills", "insurance", "loan_payments"]]
        if (fixed < 0).any().any() or (fixed.sum(axis=1) > rows["money_out"] + .01).any():
            issues.append("Fixed-cost components are negative or exceed total spending.")
    return rows, issues


def _payment_timing(rows, transactions, spending):
    """Find a dated recurring bill before the first credit in >=3 months.

    Only labeled household bills with a stable counterparty and one payment per
    month qualify. This establishes a historical pattern, not current due dates,
    paycheck identity, essential-spending classification, or biller approval.
    """
    required = {"date", "signed_amount", "purpose", "partner_bank", "partner_account"}
    if not isinstance(transactions, pd.DataFrame) or not required.issubset(transactions):
        return None, []
    tx = transactions
    if "account_id" in tx:
        if "account_id" not in rows or rows["account_id"].nunique() != 1:
            return None, []
        tx = tx.loc[tx["account_id"].eq(rows.iloc[0]["account_id"])]
    tx = tx.copy()
    tx["date"] = pd.to_datetime(tx["date"], errors="coerce")
    tx["signed_amount"] = pd.to_numeric(tx["signed_amount"], errors="coerce")
    if tx.empty or tx["date"].isna().any() or not tx["signed_amount"].map(isfinite).all():
        return None, []
    if not pd.api.types.is_datetime64_any_dtype(tx["date"]) or tx["date"].dt.tz is not None:
        return None, []
    tx = tx.loc[tx["date"].between(rows["_month"].min().start_time, rows["_month"].max().end_time)].copy()
    if tx.empty:
        return None, []
    tx["month"] = tx["date"].dt.to_period("M")
    bills = tx.loc[tx["purpose"].eq("household bills") & tx["signed_amount"].lt(0)
                   & tx["partner_bank"].notna() & tx["partner_account"].notna()].copy()
    for column in ("partner_bank", "partner_account"):
        bills = bills.loc[~bills[column].astype(str).isin(["", "0", "0.0"])]
    if bills["month"].nunique() < 3:
        return None, []
    found = []
    for _, series in bills.groupby(["partner_bank", "partner_account"]):
        dates = []
        for month, payment in series.groupby("month"):
            if len(payment) != 1:
                continue
            bill = payment.iloc[0]
            credits = tx.loc[tx["month"].eq(month) & tx["signed_amount"].gt(0)]
            if (not credits.empty and bill["date"] < credits["date"].min()
                    and -bill["signed_amount"] >= .25 * spending
                    and credits["signed_amount"].sum() >= -bill["signed_amount"]):
                dates.append(str(month))
        if len(dates) >= 3:
            found.append({"months": dates, "observed_months": len(dates),
                          "basis": "Labeled recurring household bill precedes the first observed monthly credit"})
    return bool(found), found


def evaluate_investment_triggers(customer, shock=None, *, policy=None, evidence=None, as_of=None, transactions=None):
    """Return explainable tri-state triggers, candidate sizes and stress results.

    `as_of` excludes future history. Only complete supplied monthly records should
    be passed (an ongoing calendar month is not treated as a completed month).
    All optional evidence must apply to this assessment date. Official metrics in
    `customer` are deliberately not used for sizing: they may include later rows.
    """
    policy = policy or InvestmentPolicy()
    evidence = evidence or AnalystEvidence()
    rows, issues = _history_frame(customer.get("history"), policy, as_of)
    if not rows.empty and "account_id" in rows:
        ids = rows["account_id"].unique()
        if len(ids) != 1 or ("account_id" in customer and ids[0] != customer["account_id"]):
            issues.append("History contains mixed or mismatched account IDs.")
    # Mandatory S01-S40 runtime policy. This context comes from actual inputs,
    # never a CSV case ID or test fixture. ALL returns pass through enforcement.
    validation_facts = {
        'history_valid': not bool(issues),
        'cash_verified': evidence.available_cash is not None,
        'obligations_reviewed': evidence.obligations_reviewed,
        'control_verified': evidence.sole_control_verified,
        'objective_documented': bool(evidence.objective),
        'short_horizon': evidence.horizon_months is not None and evidence.horizon_months <= policy.near_term_months,
        'costly_debt': evidence.costly_debt_verified,
        'prior_shock': evidence.prior_shock_verified,
        'goal_completed': evidence.goal_completed_verified,
        'windfall_verified': evidence.windfall_verified,
        'equities_excluded': evidence.equities_excluded,
        'unspecified_event': evidence.event_financial_effect == 'unspecified',
        'no_effect_event': evidence.event_financial_effect == 'none',
        'no_loan_in_source': customer['source_loan_status'] is None if 'source_loan_status' in customer else None,
        'finished_loan': customer['source_loan_status'] in ('A', 'B') if 'source_loan_status' in customer else None,
    }
    flags = [
        "INVESTMENT_SUITABILITY_UNVERIFIED: Competition data does not justify a security recommendation.",
        "CONDITIONAL_ESTIMATE: Historical account net flows are not verified recurring income or total household savings.",
    ]
    triggers = {}
    def record(code, name, state, reason):
        triggers[code] = {"id": code, "name": name, "state": "unknown" if state is None else "active" if state else "inactive", "reason": reason}

    names = {
        "G01": "Negative cash flow", "G02": "Thin surplus", "G03": "Unreliable surplus",
        "G04": "Volatile inflows", "G05": "Deteriorating trajectory", "G06": "Negative balances",
        "G07": "Payment timing mismatch", "G08": "Reserve shortfall", "G09": "No feasible fixed contribution",
        "G10": "Strong buffer but fragile timing", "G11": "Fixed-payment pressure", "G12": "Loan-payment pressure",
        "G13": "Verified costly debt", "G14": "Loan payment freed", "G15": "Reserve depletion",
        "G16": "Sustained surplus", "G17": "Verified excess cash", "G18": "Potential investment review",
        "G19": "Known short-term goal", "G20": "Known upcoming expense", "G21": "Unusual inflow",
        "G22": "Changed cash-flow pattern", "G23": "Verified goal completion", "G24": "Data or evidence limitations",
        "G25": "Shock restricts allocation", "G26": "Maintain and review",
    }
    for code, name in names.items():
        record(code, name, None, "Not established by supplied records.")
    base = {
        "policy": asdict(policy), "primary_goal": "DATA_LIMITED_REVIEW", "supporting_goals": [],
        "normal_monthly_allocation": 0.0, "selected_scenario_monthly_allocation": 0.0,
        "all_scenarios_monthly_allocation": 0.0, "reserve_monthly_earmark": 0.0,
        "pause_optional_contributions": False, "investment_suitability": "UNVERIFIED",
        "security_recommendations": [], "automatic_trade_allowed": False,
        "conditional_vs_verified": "CONDITIONAL", "features": {}, "triggers": [],
        "funding_result_complete": False,
        "bank_review_flags": flags, "scenario_results": [], "candidate_results": [],
        "historical_replay": [], "proposed_actions": [],
        "flexible_reserve_savings": _flexible_reserve_review(rows, policy, reserve_gap=0., cash_floor=0.,
            opening=0., expenses=(), blocked='Monthly data has not established a savings review.'),
        "next_review_conditions": ["New completed month or material inflow/spending change", "Negative balance or reserve breach", "New judge shock, obligation, or verified suitability evidence"],
        "data_provenance": {"observations": "monthly_summary.csv supplied account history", "assessment_month": str(rows['_month'].max()) if not rows.empty else as_of,
                            "additional_evidence": evidence.source or "NOT_AVAILABLE", "projection": "ASSUMED; constant monthly flows; no investment returns"},
    }
    validation_facts['flexible_reserve_savings'] = deepcopy(base['flexible_reserve_savings'])
    # Fail closed on malformed/short history while preserving a useful review result.
    if issues:
        for issue in issues:
            flags.append("DATA_LIMITED_REVIEW: " + issue)
        record("G24", names["G24"], True, "; ".join(issues))
        base.update(recommendation="Review the monthly data before sizing a fixed allocation; no amount is established.",
                    abstain_reason="Insufficient or conflicting monthly history.", triggers=list(triggers.values()), trigger_ids=["G24"])
        return enforce_goal_validations(base, validation_facts)

    realized = rows["money_in"] - rows["money_out"]
    # Keep judging medians separate: these are conservative trailing-window inputs.
    income = float(rows["money_in"].median())
    spending = float(rows["money_out"].median())
    bills = float(rows["household_bills"].median())
    buffer_proxy = float(rows.tail(6)["avg_daily_balance"].mean())
    timing_columns = {"min_balance", "month_end_balance", "days_below_zero"}
    timing_known = timing_columns.issubset(rows.columns)
    closing = float(rows.iloc[-1]["month_end_balance"]) if "month_end_balance" in rows else buffer_proxy
    opening = evidence.available_cash if evidence.available_cash is not None else min(buffer_proxy, closing)
    floor_cash = policy.operating_cash_months * spending
    reserve = policy.reserve_months * spending
    reserve_gap = max(0.0, reserve - opening)
    # Only near-term explicitly supplied expenses participate in this horizon.
    relevant_expenses = tuple(e for e in evidence.known_expenses if e.due_month is None or e.due_month <= policy.near_term_months)
    expense_unknown = any(e.amount is None or e.due_month is None for e in relevant_expenses)
    expenses = tuple(e for e in relevant_expenses if e.amount is not None and e.due_month is not None)
    min_surplus = float(realized.min())
    q25 = float(realized.quantile(.25))
    median_surplus = float(realized.median())
    negative_days = int(rows["days_below_zero"].sum()) if "days_below_zero" in rows else None
    min_balance = float(rows["min_balance"].min()) if "min_balance" in rows else None
    timing_risk = (negative_days is not None and negative_days > 0) or (min_balance is not None and min_balance < floor_cash)
    timing_mismatch, timing_evidence = _payment_timing(rows, transactions, spending)
    half = len(rows) // 2
    old = float(realized.iloc[:half].median())
    new = float(realized.iloc[-half:].median())
    meaningful_change = abs(new - old) > policy.deterioration_ratio * max(abs(old), spending, .01)
    deteriorating = meaningful_change and new < old
    if "month_end_balance" in rows:
        earlier_balance = float(rows.iloc[:half]["month_end_balance"].median())
        recent_balance = float(rows.iloc[-half:]["month_end_balance"].median())
        deteriorating = deteriorating or earlier_balance - recent_balance > policy.deterioration_ratio * max(abs(earlier_balance), spending, .01)
    depleted = reserve_gap > 0 and float(rows.iloc[:half]["avg_daily_balance"].mean()) >= reserve
    income_q25 = float(rows["money_in"].quantile(.25))
    income_q75 = float(rows["money_in"].quantile(.75))
    zero_inflows = int(rows["money_in"].eq(0).sum())
    sparse = zero_inflows >= len(rows) / 2 and float(rows["money_in"].max()) > 0
    volatile = income_q75 - income_q25 > policy.inflow_volatility_ratio * max(income, .01) or (zero_inflows > 0 and income_q75 > 0) or sparse
    unusual_inflow = float(rows["money_in"].max()) > policy.unusual_inflow_multiple * max(income, .01)
    windfall = unusual_inflow or evidence.windfall_verified
    fixed_known = {"insurance", "loan_payments"}.issubset(rows.columns)
    fixed = float(rows[["household_bills", "insurance", "loan_payments"]].sum(axis=1).median()) if fixed_known else None
    loan = float(rows["loan_payments"].median()) if "loan_payments" in rows else None
    fixed_pressure = fixed is not None and fixed > policy.fixed_payment_ratio * income
    loan_pressure = loan is not None and loan > policy.loan_payment_ratio * income
    positive_sustained = bool((realized > 0).all())
    exceptional_deficit = int((realized < 0).sum()) == 1 and min_surplus < -spending
    # A changed share of deficit months can shift a median without establishing
    # a new inflow regime. Require a sustained non-overlapping rise instead.
    rising_with_deficits = (bool((realized < 0).any()) and
        float(rows.iloc[-half:]["money_in"].min()) >
        (1 + policy.deterioration_ratio) * float(rows.iloc[:half]["money_in"].max()))
    thin = median_surplus <= policy.minimum_surplus_ratio * spending
    history_cap = _down(policy.allocation_fraction * min(min_surplus, q25))
    if thin or timing_risk or deteriorating or volatile or not timing_known or spending <= 0:
        history_cap = 0.0
    # Conservative start-of-month debit test. Cumulative removals must not be
    # forgotten at each month's boundary. This is in-sample, not a backtest.
    historical_cap = history_cap
    if timing_known:
        for index, (_, row) in enumerate(rows.iterrows(), 1):
            historical_cap = min(historical_cap, max(0.0, (float(row["min_balance"]) - floor_cash) / index))
    historical_cap = _down(historical_cap)
    baseline = StressScenario("Baseline")
    scenarios = [baseline, StressScenario("Household bills +15%", bills_increase_pct=.15),
                 StressScenario("Inflow at 55%", income_multiplier=.55),
                 StressScenario("Repair equal to typical spending", one_off_costs=spending),
                 StressScenario("Combined: 55% inflow, bills +15%, repair", .55, .15, spending)]
    selected = StressScenario("Selected judge scenario", shock["income_multiplier"], shock["bills_increase_pct"],
                              shock.get("raw_one_off_costs", shock.get("one_off_costs", 0.0)),
                              shock.get("one_off_receipt", 0.0)) if shock is not None else baseline
    financial_change = selected != StressScenario(selected.name)
    # Explicit numeric effects remain usable even when another event is not
    # quantified. Never infer extra dollars from an event name or stop analysis.
    if shock is not None:
        scenarios.append(selected)
    kwargs = dict(opening_cash=opening, monthly_inflow=income, monthly_spending=spending,
                  household_bills=bills, months=policy.projection_months, known_expenses=expenses)
    def capacity(scenario, floor_value):
        return _capacity(opening, income, spending, bills, floor_value, scenario, policy.projection_months, expenses)
    normal = min(historical_cap, capacity(baseline, reserve))
    # High obligation burden merits debt/liquidity review before longer-term allocation.
    if fixed_pressure or loan_pressure or evidence.costly_debt_verified or not fixed_known or expense_unknown:
        normal = 0.0
    if evidence.horizon_months is not None and evidence.horizon_months <= policy.near_term_months:
        normal = 0.0
    normal = _down(normal)
    selected_amount = _down(min(normal, capacity(selected, reserve)))
    robust = _down(min([normal] + [capacity(s, reserve) for s in scenarios]))
    # Reserve earmarks are retained liquid cash. Unlike an investment transfer,
    # do not cumulatively subtract them from historical total liquid balances.
    reserve_earmark = _down(min(history_cap, capacity(selected, floor_cash))) if reserve_gap > 0 else 0.0
    pause = normal > 0 and selected_amount < normal
    for scenario in scenarios:
        no_transfer = simulate_allocation(**kwargs, contribution=0.0, cash_floor=reserve, scenario=scenario)
        continued = simulate_allocation(**kwargs, contribution=normal, cash_floor=reserve, scenario=scenario)
        revised = min(normal, capacity(scenario, reserve))
        results = {"scenario": scenario.name, "assumptions": asdict(scenario), "no_allocation": no_transfer,
                   "funding_result_complete": not expense_unknown and evidence.event_financial_effect != "unspecified",
                   "continue_normal_allocation": continued, "revised_monthly_allocation": revised,
                   "revised_allocation": simulate_allocation(**kwargs, contribution=revised, cash_floor=reserve, scenario=scenario)}
        base["scenario_results"].append(results)
    candidates = sorted({0.0, selected_amount, robust, *[_down(normal * x) for x in (.25, .5, .75, 1)], *[x for x in (500.0, 1000.0, 1500.0) if x <= normal]})
    for amount in candidates:
        failures = [s.name for s in scenarios if not simulate_allocation(**kwargs, contribution=amount, cash_floor=reserve, scenario=s)["preserves_cash_floor"] or amount > capacity(s, reserve)]
        base["candidate_results"].append({"monthly_allocation": amount, "baseline_pass": not expense_unknown and evidence.event_financial_effect != "unspecified" and amount <= normal and simulate_allocation(**kwargs, contribution=amount, cash_floor=reserve, scenario=baseline)["preserves_cash_floor"],
                                          "all_tested_scenarios_pass": not failures and not expense_unknown and evidence.event_financial_effect != "unspecified", "failed_scenarios": failures})
    if timing_known:
        for index, (_, row) in enumerate(rows.iterrows(), 1):
            base["historical_replay"].append({"month": str(row["_month"]), "observed_net_flow": _money(row["money_in"] - row["money_out"]),
                "observed_minimum_cash": _money(row["min_balance"]), "cumulative_allocations": _money(index * normal),
                "adjusted_minimum_cash": _money(row["min_balance"] - index * normal),
                "adjusted_closing_cash": _money(row["month_end_balance"] - index * normal)})
    selected_no = simulate_allocation(**kwargs, contribution=0.0, cash_floor=floor_cash, scenario=selected)
    baseline_no = simulate_allocation(**kwargs, contribution=0.0, cash_floor=floor_cash, scenario=baseline)
    worsened = goal_worsened(baseline_gap=baseline_no['additional_cash_needed'], scenario_gap=selected_no['additional_cash_needed'],
        baseline_first=baseline_no['first_shortfall_month'], scenario_first=selected_no['first_shortfall_month'],
        normal_contribution=normal, scenario_contribution=selected_amount)
    shock_deficit = selected_no["monthly_net_before_contribution"] < 0 or not selected_no["nonnegative_cash"]
    flexible_block = ('An active/unknown shock needs crisis review first.' if financial_change or evidence.event_financial_effect == 'unspecified'
        else 'Complete daily-balance and fixed-obligation history is required.' if not timing_known or not fixed_known
        else 'Unknown upcoming commitments must be quantified first.' if expense_unknown
        else 'The reserve goal is already covered.' if reserve_gap <= 0
        else 'Protect cash and resolve the current deficit or deteriorating trajectory first.' if shock_deficit or median_surplus <= 0 or deteriorating
        else 'Review arrears or verified costly debt before a new savings suggestion.' if customer.get('source_loan_status') == 'D' or evidence.costly_debt_verified
        else None)
    flexible = _flexible_reserve_review(rows, policy, reserve_gap=reserve_gap, cash_floor=floor_cash,
        opening=opening, expenses=expenses, blocked=flexible_block)
    goal_missing = not evidence.objective
    profile_missing = [label for label, value in (("objective", evidence.objective), ("horizon", evidence.horizon_months),
                       ("risk tolerance", evidence.risk_tolerance), ("capacity for loss", evidence.capacity_for_loss),
                       ("existing holdings", evidence.holdings_reviewed), ("total obligations", evidence.obligations_reviewed)) if not value]
    flags.append("SUITABILITY_REVIEW_REQUIRED: " + ("Missing " + ", ".join(profile_missing) if profile_missing else "Profile supplied; product-level assessment remains an analyst responsibility."))
    if evidence.available_cash is None:
        flags.append("CURRENT_LIQUID_CASH_UNVERIFIED: Opening estimate is the lower of the historical six-month average balance and latest closing balance.")
    if not evidence.sole_control_verified:
        flags.append("ACCOUNT_CONTROL_UNVERIFIED: Account access/ownership does not establish unrestricted personal control.")
    if not timing_known:
        flags.append("TIMING_UNVERIFIED: Daily minimum, closing balance and negative-day fields are required to size a fixed allocation.")
    if expense_unknown:
        flags.append("KNOWN_EXPENSE_UNQUANTIFIED: Amount or deadline is not supplied; no contribution or funding result is invented.")
    if evidence.windfall_verified and selected.one_off_receipt == 0:
        flags.append("WINDFALL_AMOUNT_NOT_SUPPLIED: No additional cash is counted; confirmed event identity is not a supplied dollar amount.")
    if evidence.event_financial_effect == "unspecified":
        flags.append("SHOCK_UNDER_SPECIFIED: Event supplied without quantified financial effects; retain supported baseline calculations only.")
    if evidence.equities_excluded:
        flags.append("EQUITIES_EXCLUDED: Explicit supplied preference prohibits equity recommendations.")
    if customer.get("source_loan_status") in ("A", "B"):
        flags.append("LOAN_FINISHED_IN_SOURCE: End-of-2025 status does not establish a current payment, APR, or newly freed cash.")
    if "source_loan_status" in customer and customer["source_loan_status"] is None:
        flags.append("NO_LOAN_IN_SOURCE: No loan row in the supplied table is not evidence of being debt-free elsewhere.")
    if "insurance" in rows and bool(rows["insurance"].gt(0).any()):
        flags.append("COVERAGE_UNVERIFIED: Recorded insurance payments do not establish covered benefits or a payout; none is funded.")
    unknown_outflow_columns = [c for c in ("cash_withdrawals_genuine", "card_withdrawals", "transfers_out_other") if c in rows]
    unlabeled_spending = None
    if unknown_outflow_columns:
        unlabeled = rows[unknown_outflow_columns].apply(pd.to_numeric, errors="coerce")
        unlabeled_spending = bool(unlabeled.isna().any().any()) or bool((unlabeled.sum(axis=1) > .5 * rows["money_out"]).any())
        if unlabeled_spending:
            flags.append("ADJUSTABLE_SPENDING_UNVERIFIED: Withdrawals/transfers do not establish discretionary purchases or feasible spending cuts.")
    if depleted and not evidence.prior_shock_verified:
        flags.append("DEPLETION_CAUSE_UNVERIFIED: A falling historical balance does not establish a prior shock or its cause.")
    flags.extend(["HISTORICAL_REPLAY_IN_SAMPLE: Amounts are sized from this same window; this is not out-of-sample performance.",
                  "SCENARIOS_NOT_EXHAUSTIVE: Monthly paths do not establish intramonth or future solvency; no guarantee across all events.",
                  "TRANSFERS_NOT_NEW_WEALTH: Account inflows may include transfers; no investment return, payout, credit or asset sale is assumed."])
    def set_trigger(code, state, reason):
        record(code, names[code], state, reason)
    set_trigger("G01", bool((realized < 0).any()) or selected_no["monthly_net_before_contribution"] < 0,
                f"Observed deficit months: {int((realized < 0).sum())}; selected modeled monthly net flow: {selected_no['monthly_net_before_contribution']:.2f}. Observations and scenario effects are distinct.")
    set_trigger("G02", thin, f"Median realized surplus {median_surplus:.2f}; threshold {policy.minimum_surplus_ratio * spending:.2f}.")
    set_trigger("G03", not positive_sustained, "A fixed allocation requires every month in the window to have positive net cash flow.")
    set_trigger("G04", volatile, "Inflow IQR and zero-inflow months identify variability/sparsity; deposits are not salary.")
    set_trigger("G05", deteriorating, "Recent-half net flows and closing balances compared with earlier half; cause and permanence unknown.")
    set_trigger("G06", bool(negative_days or (min_balance is not None and min_balance < 0)) if timing_known else None, "Recorded negative-balance days and monthly minima.")
    # Monthly minima alone cannot prove which bill arrived before which deposit.
    set_trigger("G07", timing_mismatch, "Dated recurring household bills before first monthly credits in at least three observed months; current dates/essential status require review." if timing_mismatch is not None else "Insufficient dated, labeled recurring-bill evidence; no payment-timing relationship is inferred.")
    set_trigger("G08", reserve_gap > 0, f"Estimated cash {opening:.2f} versus illustrative reserve {reserve:.2f}.")
    set_trigger("G09", historical_cap <= 0 or (shock_deficit and selected_amount == 0), "No positive fixed amount passes the historical policy or selected deficit scenario. This is not proof that every possible intervention is exhausted." )
    set_trigger("G10", timing_risk and opening >= reserve if timing_known else None, "Average buffer does not eliminate observed daily liquidity risk.")
    set_trigger("G11", fixed_pressure if fixed_known else None, "Fixed costs are already included in outflows; no double counting.")
    set_trigger("G12", loan_pressure if loan is not None else None, "Observed payment/inflow ratio; no debt APR or current loan balance inferred.")
    set_trigger("G13", True if evidence.costly_debt_verified else None, "Costly debt only established by additional sourced evidence.")
    set_trigger("G14", None, "No verified future loan completion date or released payment is supplied.")
    set_trigger("G15", depleted or (reserve_gap > 0 and evidence.prior_shock_verified),
                "Historical buffer crossed below the reserve convention; event cause unknown.")
    set_trigger("G16", positive_sustained and not thin, f"{int((realized > 0).sum())}/{len(rows)} positive months; minimum surplus {min_surplus:.2f}.")
    set_trigger("G17", opening > reserve + sum(e.amount for e in expenses) if evidence.available_cash is not None and not expense_unknown and evidence.obligations_reviewed else None, "Requires explicitly supplied available cash and reviewed obligations; historical B alone is insufficient.")
    set_trigger("G18", normal > 0, "Potential allocation review only; a product recommendation remains gated by suitability.")
    set_trigger("G19", True if relevant_expenses or (evidence.horizon_months and evidence.horizon_months <= policy.near_term_months) else None, "Only explicit near-term obligations or horizon can establish this trigger.")
    set_trigger("G20", True if relevant_expenses else None, "Only supplied obligations count; unknown amount/timing stays unquantified, known expenses are debited once.")
    set_trigger("G21", windfall, "A supplied windfall identity does not establish its amount or recurrence." if evidence.windfall_verified else "An unusual observed inflow may be an internal transfer; source and recurrence are unverified.")
    set_trigger("G22", meaningful_change, "Comparing median net flows across equal earlier/recent halves; no permanent salary assumption.")
    set_trigger("G23", True if evidence.goal_completed_verified else None, "Completion requires additional sourced evidence.")
    set_trigger("G24", evidence.available_cash is None or not evidence.sole_control_verified or bool(profile_missing) or not timing_known or not fixed_known or sparse or expense_unknown or evidence.event_financial_effect == "unspecified",
                "Current cash, control, complete obligations or suitability information is missing.")
    set_trigger("G25", financial_change and worsened,
                f"Normal allocation {normal:.2f}; selected-scenario allocation {selected_amount:.2f}. No contribution assumes prior savings occurred.")

    if spending <= 0 or sparse or evidence.event_financial_effect == "unspecified":
        primary, reason = "DATA_LIMITED_REVIEW", "Sparse cash flow, unsupported spending data, or an unquantified event prevents a more precise plan. No financial effect is invented."
    elif financial_change and selected_no["additional_cash_needed"] > 0 and normal <= 0:
        primary, reason = "NO_FEASIBLE_CONTRIBUTION", "No positive optional contribution is supported under this shock. Report the remaining funding gap; unverified actions cannot be counted as funds."
    elif shock_deficit or opening < 0 or median_surplus < 0 or exceptional_deficit or rising_with_deficits:
        primary, reason = "STABILIZE_CASHFLOW", "Protect essential cash flow; the selected path or observed history indicates funding pressure."
    elif timing_risk:
        primary, reason = "PROTECT_OPERATING_CASH", "Daily balance history fails the operating cushion; do not commit to a fixed investment transfer."
    elif not timing_known:
        primary, reason = "DATA_LIMITED_REVIEW", "Cash-flow timing is unverified; retain liquidity and review the available history."
    elif evidence.prior_shock_verified and reserve_gap > 0:
        primary, reason = "REBUILD_AFTER_SHOCK", "A supplied prior shock and estimated reserve gap support rebuilding liquid reserves; the historical cash proxy remains unverified."
    elif deteriorating:
        primary, reason = "STABILIZE_CASHFLOW", "Historical balances or net flows have deteriorated. Cause and permanence are not established."
    elif not positive_sustained or volatile:
        primary, reason = "SMOOTH_IRREGULAR_INCOME", "Use flexible surplus review rather than a fixed investment commitment."
    elif relevant_expenses:
        primary, reason = "PREPARE_KNOWN_EXPENSE", "Protect explicitly supplied upcoming obligations before investment or debt optimization. Unknown amounts/deadlines remain unquantified."
    elif evidence.costly_debt_verified or loan_pressure:
        primary, reason = "MANAGE_DEBT_OBLIGATIONS", "Protect debt payments and operating cash before longer-term allocations; no debt-payoff savings are invented."
    elif reserve_gap > 0:
        primary, reason = "BUILD_EMERGENCY_RESERVE", f"Estimated reserve gap is CAD {reserve_gap:,.2f}; retain liquid reserves first."
    elif evidence.horizon_months and evidence.horizon_months <= policy.near_term_months:
        primary, reason = "PREPARE_KNOWN_EXPENSE", "The documented short horizon calls for protected goal savings; no amount or equity allocation is inferred."
    elif evidence.equities_excluded or evidence.event_financial_effect == "none":
        primary, reason = "MAINTAIN_AND_REVIEW", "No justified investment change follows from the supplied preference or no-effect event; retain liquidity without a forced product."
    elif evidence.windfall_verified:
        primary, reason = "ALLOCATE_SURPLUS", "Review the supplied one-off windfall for reserve and goal allocation. Only explicitly quantified receipts enter projected cash, never recurring income."
    elif evidence.available_cash is None or customer.get("source_loan_status") in ("A", "B"):
        primary, reason = "DATA_LIMITED_REVIEW", "Potential surplus is descriptive only: current cash, ownership, and relevant obligations are not established by the competition records."
    elif goal_missing:
        primary, reason = "MAINTAIN_AND_REVIEW", "No documented objective supports a forced savings or investment change."
    elif evidence.goal_completed_verified or evidence.windfall_verified:
        primary, reason = "ALLOCATE_SURPLUS", "Review allocation against the supplied objective, reserve and obligations. No security, return, or recurring income is inferred."
    elif normal > 0:
        primary, reason = "INVESTMENT_READINESS_REVIEW", "Potential surplus allocation opportunity — investment suitability not verified from competition data."
    else:
        primary, reason = "MAINTAIN_AND_REVIEW", "No positive long-term allocation passes the configured policy; maintain liquidity."
    set_trigger("G26", primary == "MAINTAIN_AND_REVIEW" or goal_missing, "No documented investment objective means no forced product or trade.")
    supporting = []
    if reserve_gap > 0 and primary != "BUILD_EMERGENCY_RESERVE":
        supporting.append("BUILD_EMERGENCY_RESERVE")
    if loan_pressure and primary != "MANAGE_DEBT_OBLIGATIONS":
        supporting.append("MANAGE_DEBT_OBLIGATIONS")
    if timing_mismatch and primary != "PROTECT_OPERATING_CASH":
        supporting.append("PROTECT_OPERATING_CASH")
    if normal > 0 and primary != "INVESTMENT_READINESS_REVIEW":
        supporting.append("POTENTIAL_SURPLUS_ALLOCATION")
    recommendation = reason
    if normal > 0:
        recommendation += f" Conditional normal allocation: CAD {normal:,.2f}/month; CAD {robust:,.2f}/month passes every listed stress scenario."
    if pause:
        recommendation += f" Under the selected shock, reduce optional allocations to CAD {selected_amount:,.2f}/month" + (" (pause)." if selected_amount == 0 else ".")
    if reserve_gap > 0 and reserve_earmark > 0:
        recommendation += f" Illustrative liquid-reserve earmark: CAD {reserve_earmark:,.2f}/month; this stays in liquid cash."
    if flexible['status'] == 'conditional_review' and reserve_earmark == 0:
        supporting.append('REVIEW_FLEXIBLE_RESERVE_SAVINGS')
        recommendation += (f" Variable liquid-reserve saving merits review: {flexible['opportunity_months']}/{len(rows)} observed months had protected capacity. "
                           "Skip deficit months; confirm current cash, commitments through the next reliable income, and the remaining reserve goal before setting money aside. No fixed monthly amount or date is established.")
    if selected_no["additional_cash_needed"] > 0:
        recommendation += f" Even with no allocation, the selected path needs CAD {selected_no['additional_cash_needed']:,.2f} additional starting cash to avoid a negative balance."
    features = {
        "history_months": len(rows), "history_start": str(rows["_month"].min()), "history_end": str(rows["_month"].max()),
        "median_monthly_inflow": _money(income), "median_monthly_spending": _money(spending),
        "median_realized_surplus": _money(median_surplus), "minimum_realized_surplus": _money(min_surplus),
        "lower_quartile_surplus": _money(q25), "positive_months_share": float((realized > 0).mean()),
        "deficit_months_share": float((realized < 0).mean()), "negative_balance_days": negative_days,
        "minimum_observed_balance": _money(min_balance) if min_balance is not None else None,
        "historical_buffer_proxy": _money(buffer_proxy), "opening_cash_estimate": _money(opening),
        "cash_basis": "SUPPLIED_EVIDENCE" if evidence.available_cash is not None else "HISTORICAL_PROXY",
        "operating_cash_floor": _money(floor_cash), "reserve_target": _money(reserve), "reserve_gap": _money(reserve_gap),
        "historical_allocation_capacity": historical_cap,
        "known_expenses": [asdict(e) for e in relevant_expenses],
        "unquantified_known_expense": expense_unknown,
        "timing_evidence": timing_evidence,
        "event_financial_effect": evidence.event_financial_effect or "NOT_SUPPLIED",
        "selected_scenario_additional_cash_needed": selected_no["additional_cash_needed"],
    }
    base.update(primary_goal=primary, supporting_goals=supporting, recommendation=recommendation,
                flexible_reserve_savings=flexible,
                normal_monthly_allocation=normal, selected_scenario_monthly_allocation=selected_amount,
                all_scenarios_monthly_allocation=robust, reserve_monthly_earmark=reserve_earmark,
                reserve_earmark_months_to_target=ceil(reserve_gap / reserve_earmark) if reserve_earmark > 0 else None,
                pause_optional_contributions=pause, features=features,
                investment_suitability="UNVERIFIED" if profile_missing else "ANALYST_REVIEW_REQUIRED",
                funding_result_complete=not expense_unknown and evidence.event_financial_effect != "unspecified",
                abstain_reason="No security selection: supplied history is not a product suitability assessment.",
                triggers=list(triggers.values()), trigger_ids=[code for code, value in triggers.items() if value["state"] == "active"],
                proposed_actions=([{"type": "CONDITIONAL_ALLOCATION_REVIEW", "normal_monthly_amount": normal,
                                   "selected_scenario_monthly_amount": selected_amount, "status": "NOT_EXECUTED"}]
                                  if evidence.objective and evidence.available_cash is not None and not evidence.equities_excluded and not expense_unknown else []))
    validation_facts.update({
        'flexible_reserve_savings': deepcopy(flexible),
        'allocation_limits': {
            'normal_monthly_allocation': normal,
            'selected_scenario_monthly_allocation': selected_amount,
            'all_scenarios_monthly_allocation': robust,
            'reserve_monthly_earmark': reserve_earmark,
        },
        'reserve_shortfall': reserve_gap > 0, 'sustained_surplus': positive_sustained,
        'negative_history': bool((realized < 0).any()), 'negative_cash': buffer_proxy < 0,
        'timing_risk': timing_risk, 'timing_mismatch': timing_mismatch,
        'deteriorating': deteriorating, 'fixed_pressure': fixed_pressure,
        'loan_pressure': loan_pressure, 'volatile': volatile, 'sparse': sparse,
        'unusual_inflow': unusual_inflow, 'depleted': depleted or (reserve_gap > 0 and evidence.prior_shock_verified),
        'exceptional_deficit': exceptional_deficit, 'rising_with_deficits': rising_with_deficits,
        'financial_change': financial_change, 'shock_deficit': shock_deficit,
        'goal_worsened': worsened,
        'funding_gap': selected_no['additional_cash_needed'] > 0,
        'expense_unknown': expense_unknown, 'known_expenses': bool(relevant_expenses),
        'insurance_recorded': bool(rows['insurance'].gt(0).any()) if 'insurance' in rows else None,
        'unlabeled_spending': unlabeled_spending, 'receipt_supplied': selected.one_off_receipt > 0,
        'income': income, 'spending': spending, 'bills': bills, 'opening': opening,
        'projection_months': policy.projection_months, 'quantified_expenses': expenses,
    })
    return enforce_goal_validations(base, validation_facts)
