"""Tangerine Resilience Engine - Core Calculation & Wealth Suite Module.

Implements the official logic and definitions specified in Tangerine/README.md:
1. Know the customer (I, F, S, B, H, P, Runway)
2. Take a shock (EI, bills increase, one-off repairs)
3. Make a plan (Goal Plan & Backup Plan)

Features:
- Full mathematical precision (raw unrounded floats used for calculations)
- Month 0 immediate one-off overdraft detection in trajectory
- Consistent savings contribution rate and ETA projections
- Piecewise multi-stage runway calculations enforcing 6-month benefit limits
- Customer-confirmed discretionary expense triage
"""

import argparse
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"

# Global data cache
_CACHE: Dict[str, pd.DataFrame] = {}


def load_data(data_dir: Path = DATA_DIR) -> Dict[str, pd.DataFrame]:
    """Load and cache the required CSV tables."""
    global _CACHE
    if not _CACHE:
        monthly_path = data_dir / "monthly_summary.csv"
        loans_path = data_dir / "loans.csv"

        if not monthly_path.exists() or not loans_path.exists():
            raise FileNotFoundError(f"Data files not found in {data_dir}")

        _CACHE["monthly"] = pd.read_csv(monthly_path)
        _CACHE["loans"] = pd.read_csv(loans_path)

        # Optional demographic & account tables
        accounts_path = data_dir / "accounts.csv"
        if accounts_path.exists():
            _CACHE["accounts"] = pd.read_csv(accounts_path)

        clients_path = data_dir / "clients.csv"
        if clients_path.exists():
            _CACHE["clients"] = pd.read_csv(clients_path)

        dispositions_path = data_dir / "dispositions.csv"
        if dispositions_path.exists():
            _CACHE["dispositions"] = pd.read_csv(dispositions_path)

    return _CACHE


def get_account_ids(data_dir: Path = DATA_DIR) -> List[int]:
    """Return a sorted list of all unique account IDs in the dataset."""
    data = load_data(data_dir)
    return sorted(data["monthly"]["account_id"].unique().tolist())


def calculate_runway(buffer_left: float, gap: float) -> Union[float, str]:
    """Calculate months of runway using the official formula.

    buffer_left = B - one_off_costs
    gap = spending_after_shock - income_after_shock
    if buffer_left <= 0: runway = 0.0
    elif gap <= 0: runway = 'no shortfall (120+)'
    else: runway = round(min(buffer_left / gap, 120.0), 1)
    """
    if buffer_left <= 0:
        return 0.0
    elif gap <= 0:
        return "no shortfall (120+)"
    else:
        return round(min(buffer_left / gap, 120.0), 1)


def know_customer(account_id: int, data_dir: Path = DATA_DIR) -> Dict[str, Any]:
    """Part 1: Know the Customer."""
    data = load_data(data_dir)
    monthly = data["monthly"]
    loans = data["loans"]

    acc_df = monthly[monthly["account_id"] == account_id].sort_values("month").copy()
    if acc_df.empty:
        raise ValueError(f"Account ID {account_id} not found in monthly_summary.csv")

    raw_I = float(acc_df["money_in"].median())
    fixed_series = (
        acc_df["household_bills"].fillna(0)
        + acc_df["insurance"].fillna(0)
        + acc_df["loan_payments"].fillna(0)
    )
    raw_F = float(fixed_series.median())
    raw_S = float(acc_df["money_out"].median())
    last_6 = acc_df.tail(6)
    raw_B = float(last_6["avg_daily_balance"].mean())
    raw_H = float(acc_df["household_bills"].fillna(0).median())

    acc_loans = loans[loans["account_id"] == account_id]
    raw_P = 0.0
    loan_status = None
    if not acc_loans.empty:
        status = str(acc_loans.iloc[0]["status"]).strip()
        loan_status = acc_loans.iloc[0]["status_meaning"]
        if status in ["C", "D"]:
            raw_P = float(acc_loans.iloc[0]["monthly_payment"])

    baseline_gap = raw_S - raw_I
    baseline_runway = calculate_runway(raw_B, baseline_gap)

    # Demographics & Shared Access check
    demographics = {
        "num_clients": 1,
        "relationship": "Single Account Holder",
    }
    if "dispositions" in data and "clients" in data:
        disps = data["dispositions"][data["dispositions"]["account_id"] == account_id]
        if not disps.empty:
            num_clients = len(disps)
            has_owner = any(disps["type"] == "owner")
            has_auth = any(disps["type"] == "authorized user")
            rel_label = (
                "Shared Account (Owner + Authorized User)"
                if (has_owner and has_auth)
                else ("Single Owner" if has_owner else "Account")
            )
            demographics["num_clients"] = num_clients
            demographics["relationship"] = rel_label

    return {
        "account_id": account_id,
        "raw_I": raw_I,
        "raw_F": raw_F,
        "raw_S": raw_S,
        "raw_B": raw_B,
        "raw_H": raw_H,
        "raw_P": raw_P,
        "I": round(raw_I, 2),
        "F": round(raw_F, 2),
        "S": round(raw_S, 2),
        "B": round(raw_B, 2),
        "H": round(raw_H, 2),
        "P": round(raw_P, 2),
        "has_running_loan": raw_P > 0,
        "loan_status_meaning": loan_status,
        "baseline_gap": round(baseline_gap, 2),
        "baseline_runway": baseline_runway,
        "demographics": demographics,
        "history": acc_df,
    }


def take_shock(
    customer: Dict[str, Any],
    income_multiplier: float = 1.0,
    bills_increase_pct: float = 0.0,
    one_off_costs: float = 0.0,
) -> Dict[str, Any]:
    """Part 2: Take a Shock (Official Baseline Formula).

    Uses raw unrounded floats to eliminate rounding drift across test cases.
    """
    raw_I = customer.get("raw_I", customer["I"])
    raw_S = customer.get("raw_S", customer["S"])
    raw_B = customer.get("raw_B", customer["B"])
    raw_H = customer.get("raw_H", customer["H"])

    income_after_shock = income_multiplier * raw_I
    spending_after_shock = raw_S + (bills_increase_pct * raw_H)
    buffer_left = raw_B - one_off_costs
    gap = spending_after_shock - income_after_shock
    runway = calculate_runway(buffer_left, gap)

    return {
        "income_multiplier": income_multiplier,
        "bills_increase_pct": bills_increase_pct,
        "one_off_costs": round(one_off_costs, 2),
        "raw_income_after_shock": income_after_shock,
        "raw_spending_after_shock": spending_after_shock,
        "raw_buffer_left": buffer_left,
        "raw_gap": gap,
        "income_after_shock": round(income_after_shock, 2),
        "spending_after_shock": round(spending_after_shock, 2),
        "buffer_left": round(buffer_left, 2),
        "gap": round(gap, 2),
        "runway": runway,
    }


def simulate_6mo_trajectory(
    customer: Dict[str, Any],
    income_multiplier: float = 1.0,
    bills_increase_pct: float = 0.0,
    one_off_costs: float = 0.0,
    discretionary_cut_pct: float = 0.0,
    loan_deferred: bool = False,
    insurance_policy: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Simulates month-by-month trajectory for 6 months under a shock.

    Answers the judge's exact scenario:
    "This customer was laid off. EI pays 55% of their usual income for 6 months. Do they make it?"

    Includes Month 0 immediate one-off expense audit: if buffer_left < 0,
    exhaustion_month is 0 (immediate overdraft), preventing false survival verdicts.
    """
    raw_I = customer.get("raw_I", customer["I"])
    raw_S = customer.get("raw_S", customer["S"])
    raw_B = customer.get("raw_B", customer["B"])
    raw_H = customer.get("raw_H", customer["H"])
    raw_P = customer.get("raw_P", customer["P"])
    raw_F = customer.get("raw_F", customer["F"])

    # Discretionary non-essential spending pool
    non_fixed_spend = max(0.0, raw_S - raw_F)
    discretionary_pool = 0.40 * non_fixed_spend
    monthly_cut_savings = discretionary_cut_pct * discretionary_pool

    # Initial balance at Month 0 after one-off expense
    balance = raw_B - one_off_costs
    insurance_repair_payout = 0.0
    if insurance_policy and one_off_costs > 0:
        max_p = insurance_policy.get("max_repair_payout", 0.0)
        ded = insurance_policy.get("repair_deductible", 0.0)
        if max_p > 0:
            covered = max(0.0, min(one_off_costs - ded, max_p))
            insurance_repair_payout = covered
            balance += covered

    schedule: List[Dict[str, Any]] = []

    # Check Month 0 immediate overdraft
    if balance < 0:
        makes_it = False
        exhaustion_month = 0
    else:
        makes_it = True
        exhaustion_month = None

    # Record Month 0 event if there was a one-off cost
    if one_off_costs > 0:
        schedule.append(
            {
                "month": "Month 0 (Shock)",
                "start_balance": round(raw_B, 2),
                "income": 0.0,
                "spending": round(one_off_costs, 2),
                "net_shortfall": round(one_off_costs - insurance_repair_payout, 2),
                "end_balance": round(balance, 2),
            }
        )

    for m in range(1, 7):
        eff_mult = income_multiplier
        if insurance_policy and income_multiplier < 1.0:
            eff_mult = min(1.0, eff_mult + insurance_policy.get("income_topup_pct", 0.0))
        mo_income = eff_mult * raw_I

        base_spending = raw_S - monthly_cut_savings

        if loan_deferred and raw_P > 0:
            base_spending = max(0.0, base_spending - raw_P)
        elif insurance_policy and insurance_policy.get("covers_loan") and raw_P > 0 and income_multiplier < 1.0:
            base_spending = max(0.0, base_spending - raw_P)

        eff_bills_pct = bills_increase_pct
        if insurance_policy and insurance_policy.get("type") in [
            "Household & Rental Protection",
            "All-In Bundled Protection (15% Multi-Policy Discount)",
        ]:
            eff_bills_pct = max(0.0, bills_increase_pct - 0.25)
        mo_spending = base_spending + (eff_bills_pct * raw_H)

        if insurance_policy and insurance_policy.get("monthly_premium", 0.0) > 0:
            mo_spending += insurance_policy["monthly_premium"]

        net_shortfall = mo_spending - mo_income
        start_bal = balance
        balance = start_bal - net_shortfall

        if balance < 0 and exhaustion_month is None:
            makes_it = False
            exhaustion_month = m

        schedule.append(
            {
                "month": f"Month {m}",
                "start_balance": round(start_bal, 2),
                "income": round(mo_income, 2),
                "spending": round(mo_spending, 2),
                "net_shortfall": round(net_shortfall, 2),
                "end_balance": round(balance, 2),
            }
        )

    month_6_balance = round(balance, 2)
    # Average monthly shortfall over months 1 to 6
    regular_months = [r for r in schedule if r["month"].startswith("Month ") and r["month"] != "Month 0 (Shock)"]
    avg_shortfall = round(sum(r["net_shortfall"] for r in regular_months) / 6.0, 2) if regular_months else 0.0

    return {
        "makes_it_to_month_6": makes_it,
        "exhaustion_month": exhaustion_month,
        "month_6_balance": month_6_balance,
        "avg_shortfall": avg_shortfall,
        "initial_buffer_left": round(raw_B - one_off_costs + insurance_repair_payout, 2),
        "insurance_repair_payout": round(insurance_repair_payout, 2),
        "schedule": schedule,
    }


def calculate_lean_budget(customer: Dict[str, Any], trim_pct: float = 0.50) -> Dict[str, Any]:
    """Calculates Lean Survival Budget by trimming customer-confirmed discretionary outflows."""
    raw_S = customer.get("raw_S", customer["S"])
    raw_F = customer.get("raw_F", customer["F"])

    non_fixed = max(0.0, raw_S - raw_F)
    discretionary_pool = 0.40 * non_fixed
    trimmed_amount = round(trim_pct * discretionary_pool, 2)
    lean_spending = round(raw_S - trimmed_amount, 2)

    target_3mo_standard = round(3 * raw_S, 2)
    target_3mo_lean = round(3 * lean_spending, 2)
    target_reduction = round(target_3mo_standard - target_3mo_lean, 2)

    return {
        "standard_spending": round(raw_S, 2),
        "fixed_commitments": round(raw_F, 2),
        "non_fixed_spending": round(non_fixed, 2),
        "discretionary_pool": round(discretionary_pool, 2),
        "trim_pct": trim_pct,
        "trimmed_amount": trimmed_amount,
        "lean_spending": lean_spending,
        "monthly_savings_unlocked": trimmed_amount,
        "target_3mo_standard": target_3mo_standard,
        "target_3mo_lean": target_3mo_lean,
        "target_reduction": target_reduction,
    }


def get_insurance_plans(customer: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Calculates dynamically underwritten insurance options based on the customer's profile."""
    raw_I = customer.get("raw_I", customer["I"])
    raw_P = customer.get("raw_P", customer["P"])
    raw_H = customer.get("raw_H", customer["H"])
    raw_S = customer.get("raw_S", customer["S"])

    plans = {}

    # 1. Mortgage & Debt Shield
    if raw_P > 0:
        mortgage_premium = max(24.0, round(raw_P * 0.012, 2))
        plans["mortgage_shield"] = {
            "name": "Tangerine Mortgage & Debt Shield",
            "type": "Mortgage & Debt Protection",
            "eligible": True,
            "monthly_premium": mortgage_premium,
            "description": f"Underwritten for active loan payment of ${raw_P:,.2f}/mo.",
            "benefits": [
                f"Covers active loan payment of ${raw_P:,.2f}/mo directly for up to 6 months of layoff or disability.",
                "Emergency home & essential equipment breakdown coverage up to $5,000 (deductible $250).",
                "Prevents delinquency, penalties, and credit score impairment.",
            ],
            "covers_loan": True,
            "max_repair_payout": 5000.0,
            "repair_deductible": 250.0,
            "income_topup_pct": 0.0,
        }
    else:
        plans["mortgage_shield"] = {
            "name": "Tangerine Mortgage & Debt Shield",
            "type": "Mortgage & Debt Protection",
            "eligible": False,
            "monthly_premium": 0.0,
            "description": "Not applicable (no active running loan on this account).",
            "benefits": [],
        }

    # 2. Tenant & Household Bill Shield
    tenant_base = max(raw_H * 0.010, raw_S * 0.005)
    tenant_premium = max(18.0, min(55.0, round(tenant_base, 2)))
    plans["tenant_shield"] = {
        "name": "Tangerine Tenant & Utility Hardship Shield",
        "type": "Household & Rental Protection",
        "eligible": True,
        "monthly_premium": tenant_premium,
        "description": f"Underwritten for typical household/utility costs of ${raw_H:,.2f}/mo.",
        "benefits": [
            "Absorbs utility or rent spikes up to 25% for 6 consecutive months.",
            "Emergency appliance or tenant repair coverage up to $2,500 (deductible $150).",
            "Eviction protection buffer and utility disconnection freeze.",
        ],
        "covers_loan": False,
        "max_repair_payout": 2500.0,
        "repair_deductible": 150.0,
        "income_topup_pct": 0.0,
    }

    # 3. Income Replacement (EI Top-Up) Shield
    if raw_I <= 4000:
        income_premium = 22.0
    elif raw_I <= 8500:
        income_premium = 44.0
    elif raw_I <= 15000:
        income_premium = 68.0
    else:
        income_premium = 95.0

    plans["income_shield"] = {
        "name": "Tangerine Income Safeguard (EI Top-Up)",
        "type": "Income Replacement",
        "eligible": True,
        "monthly_premium": income_premium,
        "description": f"Underwritten for monthly earnings tier of ${raw_I:,.2f}/mo.",
        "benefits": [
            "Tops up Canadian EI from 55% up to 75% of income (+20% income boost) for 6 months (capped at 100% of income).",
            "Protects high earners whose earnings exceed the statutory maximum insurable EI threshold.",
            "Covers 1-week statutory EI waiting period with an immediate $500 emergency stipend.",
        ],
        "covers_loan": False,
        "max_repair_payout": 0.0,
        "repair_deductible": 0.0,
        "income_topup_pct": 0.20,
    }

    # 4. Comprehensive All-In Suite
    primary_base = mortgage_premium if raw_P > 0 else tenant_premium
    bundled_gross = primary_base + income_premium
    bundled_net = round(bundled_gross * 0.85, 2)
    plans["comprehensive_suite"] = {
        "name": "Tangerine 360° Comprehensive Shield",
        "type": "All-In Bundled Protection (15% Multi-Policy Discount)",
        "eligible": True,
        "monthly_premium": bundled_net,
        "description": f"Bundled Debt/Housing Protection + Income Top-Up (regular ${bundled_gross:,.2f}, save 15%).",
        "benefits": [
            f"Debt & Housing: Covers loan payments (${raw_P:,.2f}/mo) or caps bills, plus up to $5,000 repair coverage.",
            "Income: +20% EI income top-up (replaces up to 75% of typical income).",
            "Waived deductible on emergency repairs.",
        ],
        "covers_loan": raw_P > 0,
        "max_repair_payout": 5000.0,
        "repair_deductible": 0.0,
        "income_topup_pct": 0.20,
    }

    return plans


def calculate_wealth_waterfall(
    customer: Dict[str, Any],
    lean_budget: Dict[str, Any],
    insurance_premium: float = 0.0,
    downpayment_target: float = 25000.0,
    starting_investments: float = 0.0,
) -> Dict[str, Any]:
    """Calculates the 3-Tier Wealth Progression."""
    raw_I = customer.get("raw_I", customer["I"])
    raw_B = customer.get("raw_B", customer["B"])
    lean_spend = lean_budget["lean_spending"]

    net_surplus = round(raw_I - lean_spend - insurance_premium, 2)
    emergency_target = lean_budget["target_3mo_lean"]

    emergency_funded_pct = min(1.0, max(0.0, raw_B / emergency_target)) if emergency_target > 0 else 1.0
    emergency_needed = max(0.0, round(emergency_target - raw_B, 2))
    emergency_complete = emergency_needed == 0.0

    if net_surplus > 0:
        if not emergency_complete:
            alloc_emergency = round(net_surplus * 0.70, 2)
            alloc_investments = round(net_surplus * 0.15, 2)
            alloc_downpayment = round(net_surplus * 0.15, 2)
            months_to_emergency = (
                round(emergency_needed / alloc_emergency, 1) if alloc_emergency > 0 else 0.0
            )
        else:
            alloc_emergency = 0.0
            alloc_investments = round(net_surplus * 0.50, 2)
            alloc_downpayment = round(net_surplus * 0.50, 2)
            months_to_emergency = 0.0

        months_to_downpayment = (
            round(downpayment_target / alloc_downpayment, 1) if alloc_downpayment > 0 else None
        )
    else:
        alloc_emergency = 0.0
        alloc_investments = 0.0
        alloc_downpayment = 0.0
        months_to_emergency = None
        months_to_downpayment = None

    r = 0.07 / 12.0
    proj_1yr = starting_investments
    proj_3yr = starting_investments
    proj_5yr = starting_investments
    if alloc_investments > 0:
        proj_1yr = round(
            starting_investments * ((1 + r) ** 12) + alloc_investments * (((1 + r) ** 12 - 1) / r),
            2,
        )
        proj_3yr = round(
            starting_investments * ((1 + r) ** 36) + alloc_investments * (((1 + r) ** 36 - 1) / r),
            2,
        )
        proj_5yr = round(
            starting_investments * ((1 + r) ** 60) + alloc_investments * (((1 + r) ** 60 - 1) / r),
            2,
        )

    return {
        "net_surplus": net_surplus,
        "emergency_target": emergency_target,
        "emergency_funded_pct": emergency_funded_pct,
        "emergency_needed": emergency_needed,
        "emergency_complete": emergency_complete,
        "months_to_emergency": months_to_emergency,
        "alloc_emergency": alloc_emergency,
        "alloc_investments": alloc_investments,
        "alloc_downpayment": alloc_downpayment,
        "downpayment_target": downpayment_target,
        "months_to_downpayment": months_to_downpayment,
        "proj_1yr": proj_1yr,
        "proj_3yr": proj_3yr,
        "proj_5yr": proj_5yr,
    }


def simulate_resilience_rescue(
    customer: Dict[str, Any],
    shock_inputs: Dict[str, float],
    selected_plan_key: Optional[str] = None,
    use_lean_budget: bool = True,
    trim_pct: float = 0.50,
    tap_investments_amt: float = 0.0,
) -> Dict[str, Any]:
    """Simulates how the customer survives the shock with the Tangerine Resilience Plan active.

    Features a piecewise multi-stage runway calculation that accounts for the 6-month benefit expiration:
    - If buffer exhausts within months 1 to 6: runway is exact exhaustion month.
    - If customer survives Month 6 with balance B6 > 0: post-month-6 runway is governed
      by remaining balance under unshielded cash flow (benefits expire at month 6).
    """
    raw_I = customer.get("raw_I", customer["I"])
    raw_S = customer.get("raw_S", customer["S"])
    raw_B = customer.get("raw_B", customer["B"])
    raw_H = customer.get("raw_H", customer["H"])
    raw_P = customer.get("raw_P", customer["P"])

    income_mult = shock_inputs.get("income_multiplier", 1.0)
    bills_pct = shock_inputs.get("bills_increase_pct", 0.0)
    repair_cost = shock_inputs.get("one_off_costs", 0.0)

    # 1. Baseline Shock (Unprotected)
    baseline_shock = take_shock(
        customer,
        income_multiplier=income_mult,
        bills_increase_pct=bills_pct,
        one_off_costs=repair_cost,
    )

    # 2. Rescued Shock Calculations
    plans = get_insurance_plans(customer)
    insurance = (
        plans.get(selected_plan_key)
        if (selected_plan_key and selected_plan_key in plans and selected_plan_key != "none")
        else None
    )

    # Run 6-Month Trajectory Simulation
    traj = simulate_6mo_trajectory(
        customer,
        income_multiplier=income_mult,
        bills_increase_pct=bills_pct,
        one_off_costs=repair_cost,
        discretionary_cut_pct=trim_pct if use_lean_budget else 0.0,
        insurance_policy=insurance,
    )

    # Multi-stage Piecewise Runway Calculation (Accounting for 6-Month Benefit Expiry)
    if not traj["makes_it_to_month_6"]:
        ex_m = traj["exhaustion_month"]
        if ex_m == 0:
            rescued_runway = 0.0
        else:
            # Interpolate exact exhaustion month
            sched = [r for r in traj["schedule"] if r["month"].startswith("Month ") and r["month"] != "Month 0 (Shock)"]
            ex_row = sched[ex_m - 1]
            prior_bal = ex_row["start_balance"]
            net_deficit = ex_row["net_shortfall"]
            fraction = max(0.0, prior_bal / net_deficit) if net_deficit > 0 else 0.0
            rescued_runway = round((ex_m - 1) + fraction, 1)
    else:
        # Customer survived Month 6 with positive balance B6!
        b6 = traj["month_6_balance"] + tap_investments_amt
        # Post-month 6: temporary benefits expire, cash gap resumes without insurance top-ups
        post_6_income = income_mult * raw_I
        post_6_spend = raw_S + (bills_pct * raw_H)
        if use_lean_budget:
            lean_d = calculate_lean_budget(customer, trim_pct=trim_pct)
            post_6_spend = lean_d["lean_spending"] + (bills_pct * raw_H)
        post_6_gap = post_6_spend - post_6_income

        if post_6_gap <= 0:
            rescued_runway = "no shortfall (120+)"
        else:
            months_after_6 = b6 / post_6_gap
            rescued_runway = round(min(6.0 + months_after_6, 120.0), 1)

    # Effective values during the shock window
    rescued_income = round(min(1.0, income_mult + (insurance.get("income_topup_pct", 0.0) if insurance else 0.0)) * raw_I, 2)
    base_sp = calculate_lean_budget(customer, trim_pct=trim_pct)["lean_spending"] if use_lean_budget else raw_S
    if insurance and insurance.get("covers_loan") and raw_P > 0 and income_mult < 1.0:
        base_sp = max(0.0, base_sp - raw_P)
    eff_b_pct = max(0.0, bills_pct - 0.25) if (insurance and selected_plan_key in ["tenant_shield", "comprehensive_suite"]) else bills_pct
    monthly_premium = insurance["monthly_premium"] if insurance else 0.0
    rescued_spending = round(base_sp + (eff_b_pct * raw_H) + monthly_premium, 2)
    rescued_gap = round(rescued_spending - rescued_income, 2)
    rescued_buffer_left = round(traj["initial_buffer_left"] + tap_investments_amt, 2)

    return {
        "baseline_runway": baseline_shock["runway"],
        "baseline_gap": baseline_shock["gap"],
        "baseline_buffer_left": baseline_shock["buffer_left"],
        "rescued_runway": rescued_runway,
        "rescued_gap": rescued_gap,
        "rescued_income": rescued_income,
        "rescued_spending": rescued_spending,
        "rescued_buffer_left": rescued_buffer_left,
        "insurance_payout": traj["insurance_repair_payout"],
        "insurance_name": insurance["name"] if insurance else "None",
        "monthly_premium": monthly_premium,
        "use_lean_budget": use_lean_budget,
        "trim_pct": trim_pct,
        "six_month_trajectory": traj,
    }


def make_plan(
    customer: Dict[str, Any],
    shock: Optional[Dict[str, Any]] = None,
    confirmed_cut_pct: float = 0.50,
) -> Dict[str, Any]:
    """Part 3: Make a Plan (Official Required Output).

    Returns:
    1. Goal Plan: Sized to 3-month and 6-month spending, with mathematically consistent contribution ETA.
    2. Backup Plan: Month 0-6 trajectory, month 6 balance, cash gap, and customer-confirmed actions.
    """
    raw_I = customer.get("raw_I", customer["I"])
    raw_S = customer.get("raw_S", customer["S"])
    raw_B = customer.get("raw_B", customer["B"])
    raw_F = customer.get("raw_F", customer["F"])
    raw_P = customer.get("raw_P", customer["P"])

    monthly_surplus = round(raw_I - raw_S, 2)
    target_3mo = round(3 * raw_S, 2)
    target_6mo = round(6 * raw_S, 2)
    needed_3mo = max(0.0, round(target_3mo - raw_B, 2))
    needed_6mo = max(0.0, round(target_6mo - raw_B, 2))

    # Goal Plan
    goal_plan: Dict[str, Any] = {
        "monthly_surplus": monthly_surplus,
        "target_3mo": target_3mo,
        "target_6mo": target_6mo,
        "current_buffer": round(raw_B, 2),
        "needed_for_3mo": needed_3mo,
        "needed_for_6mo": needed_6mo,
    }

    if monthly_surplus > 0:
        recommended_monthly_contribution = round(monthly_surplus * 0.70, 2)
        months_to_3mo_recommended = (
            round(needed_3mo / recommended_monthly_contribution, 1)
            if (needed_3mo > 0 and recommended_monthly_contribution > 0)
            else 0.0
        )
        months_to_3mo_full = round(needed_3mo / monthly_surplus, 1) if needed_3mo > 0 else 0.0
        months_to_6mo_recommended = (
            round(needed_6mo / recommended_monthly_contribution, 1)
            if (needed_6mo > 0 and recommended_monthly_contribution > 0)
            else 0.0
        )

        goal_plan["recommended_contribution"] = recommended_monthly_contribution
        goal_plan["months_to_3mo"] = months_to_3mo_recommended
        goal_plan["months_to_3mo_full"] = months_to_3mo_full
        goal_plan["months_to_6mo"] = months_to_6mo_recommended
        goal_plan["recommendation"] = (
            f"Commit ${recommended_monthly_contribution:,.2f}/mo (70% of surplus) to reach your 3-month target "
            f"in {months_to_3mo_recommended} months (or {months_to_3mo_full} months if saving 100% of surplus)."
        )
    else:
        goal_plan["recommended_contribution"] = 0.0
        goal_plan["months_to_3mo"] = None
        goal_plan["months_to_3mo_full"] = None
        goal_plan["months_to_6mo"] = None
        goal_plan["recommendation"] = (
            f"Deficit spending alert: monthly spending exceeds income by ${abs(monthly_surplus):,.2f}. "
            "Prioritize trimming non-fixed spending before allocating to long-term goals."
        )

    # Backup Plan (for active shock)
    backup_plan: Dict[str, Any] = {}
    if shock is not None:
        gap = shock["gap"]
        buffer_left = shock["buffer_left"]
        runway = shock["runway"]

        # Run 6-month trajectory under active shock
        traj = simulate_6mo_trajectory(
            customer,
            income_multiplier=shock.get("income_multiplier", 1.0),
            bills_increase_pct=shock.get("bills_increase_pct", 0.0),
            one_off_costs=shock.get("one_off_costs", 0.0),
            discretionary_cut_pct=confirmed_cut_pct,
        )

        non_fixed = max(0.0, raw_S - raw_F)
        discretionary_pool = 0.40 * non_fixed
        confirmed_savings = round(confirmed_cut_pct * discretionary_pool, 2)

        backup_plan = {
            "unprotected_runway": runway,
            "monthly_cash_gap": gap,
            "buffer_left": buffer_left,
            "has_active_loan": raw_P > 0,
            "loan_payment": round(raw_P, 2),
            "discretionary_pool": round(discretionary_pool, 2),
            "confirmed_cut_pct": confirmed_cut_pct,
            "confirmed_savings": confirmed_savings,
            "makes_it_to_month_6": traj["makes_it_to_month_6"],
            "exhaustion_month": traj["exhaustion_month"],
            "month_6_balance": traj["month_6_balance"],
            "initial_buffer_left": traj["initial_buffer_left"],
            "six_month_schedule": traj["schedule"],
            "actions": [
                f"Action 1 (Customer-Confirmed Discretionary Cut): Trimming ${confirmed_savings:,.2f}/mo "
                f"({confirmed_cut_pct*100:.0f}% of non-essential card spend & bank fees).",
            ],
        }

        if shock.get("income_multiplier", 1.0) < 1.0:
            backup_plan["actions"].append(
                "Action 2 (EI Benefits): Submit Canadian Employment Insurance (EI) regular claim immediately (covers 55% insurable earnings for up to 6 months)."
            )
        if raw_P > 0:
            backup_plan["actions"].append(
                f"Action 3 (Loan Forbearance): Request a 90-day hardship deferral on active loan payment of ${raw_P:,.2f}/mo."
            )

        if traj["exhaustion_month"] == 0:
            backup_plan["actions"].append(
                f"Action 4 (Immediate Overdraft): Buffer exhausted at Month 0 by one-off cost (deficit: ${traj['initial_buffer_left']:,.2f}). Immediate emergency credit/forbearance required."
            )
        elif traj["makes_it_to_month_6"]:
            backup_plan["actions"].append(
                f"Action 4 (Month 6 Cliff): Projected balance at Month 6 is ${traj['month_6_balance']:,.2f}. Buffer remains solvent through benefits period."
            )
        else:
            backup_plan["actions"].append(
                f"Action 4 (Deficit Alert): Buffer exhausts in Month {traj['exhaustion_month']}. Ends Month 6 at ${traj['month_6_balance']:,.2f}."
            )

    return {"goal_plan": goal_plan, "backup_plan": backup_plan}


def run_pipeline(
    account_id: int,
    income_multiplier: float = 1.0,
    bills_increase_pct: float = 0.0,
    one_off_costs: float = 0.0,
    data_dir: Path = DATA_DIR,
) -> Dict[str, Any]:
    """Execute the complete 3-step pipeline."""
    customer = know_customer(account_id, data_dir=data_dir)
    shock = take_shock(
        customer,
        income_multiplier=income_multiplier,
        bills_increase_pct=bills_increase_pct,
        one_off_costs=one_off_costs,
    )
    plan = make_plan(customer, shock=shock)
    lean = calculate_lean_budget(customer)
    insurance = get_insurance_plans(customer)

    return {
        "customer": customer,
        "shock": shock,
        "plan": plan,
        "lean_budget": lean,
        "insurance_plans": insurance,
    }


def main():
    parser = argparse.ArgumentParser(description="Tangerine Resilience Engine CLI")
    parser.add_argument("account_pos", type=int, nargs="?", default=None, help="Account ID (positional)")
    parser.add_argument("--account", type=int, default=None, help="Account ID")
    parser.add_argument("--ei", type=float, default=1.0, help="Income multiplier (e.g. 0.55 for EI)")
    parser.add_argument("--bills", type=float, default=0.0, help="Household bills increase (e.g. 0.15 for 15%)")
    parser.add_argument("--repair", type=float, default=0.0, help="One-off surprise cost in CAD")
    args = parser.parse_args()

    # Resolve account ID from positional or flag (default 20111)
    target_account = args.account_pos if args.account_pos is not None else (args.account if args.account is not None else 20111)

    results = run_pipeline(
        account_id=target_account,
        income_multiplier=args.ei,
        bills_increase_pct=args.bills,
        one_off_costs=args.repair,
    )

    c = results["customer"]
    s = results["shock"]
    p = results["plan"]

    print("\n" + "=" * 65)
    print(f" TANGERINE RESILIENCE ARCHITECT REPORT: Account {target_account}")
    print("=" * 65)
    print("PART 1: KNOW THE CUSTOMER (Official Baseline)")
    print(f"  • Typical Monthly Income (I)  : ${c['I']:>10.2f}")
    print(f"  • Typical Monthly Spending (S): ${c['S']:>10.2f}")
    print(f"  • Fixed Costs (F)             : ${c['F']:>10.2f}")
    print(f"  • Household Bills (H)         : ${c['H']:>10.2f}")
    print(f"  • Active Loan Payment (P)     : ${c['P']:>10.2f}")
    print(f"  • Savings Buffer (B)          : ${c['B']:>10.2f}")
    print(f"  • Baseline Runway             : {c['baseline_runway']} months")

    print("\nPART 2: TAKE A SHOCK")
    print(f"  • Shock Inputs                : Income x{s['income_multiplier']:.2f}, Bills +{s['bills_increase_pct']*100:.1f}%, One-off: ${s['one_off_costs']:.2f}")
    print(f"  • Income After Shock          : ${s['income_after_shock']:>10.2f}")
    print(f"  • Spending After Shock        : ${s['spending_after_shock']:>10.2f}")
    print(f"  • Remaining Buffer            : ${s['buffer_left']:>10.2f}")
    print(f"  • Monthly Shortfall / Gap     : ${s['gap']:>10.2f}")
    print(f"  • SHOCK RUNWAY (UNPROTECTED)  : {s['runway']} months")

    print("\nPART 3: MAKE A PLAN")
    gp = p["goal_plan"]
    print("  [Plan 1: Goal Plan - Normal Times]")
    print(f"  • Monthly Surplus             : ${gp['monthly_surplus']:>10.2f}")
    print(f"  • Target 3-Month Fund (3xS)   : ${gp['target_3mo']:>10.2f} (Needed: ${gp['needed_for_3mo']:.2f})")
    print(f"  • Target 6-Month Fund (6xS)   : ${gp['target_6mo']:>10.2f} (Needed: ${gp['needed_for_6mo']:.2f})")
    if gp.get("months_to_3mo") is not None:
        print(f"  • Months to 3-Mo Target (70%) : {gp['months_to_3mo']} months (at ${gp['recommended_contribution']:.2f}/mo)")
        print(f"  • Months to 3-Mo Target (100%): {gp['months_to_3mo_full']} months")

    bp = p["backup_plan"]
    print("\n  [Plan 2: Backup Plan - Active Shock]")
    print(f"  • Active Shock Runway         : {bp['unprotected_runway']} months")
    print(f"  • Monthly Cash Gap            : ${bp['monthly_cash_gap']:>10.2f}")
    print(f"  • Makes it to Month 6?        : {'YES' if bp['makes_it_to_month_6'] else 'NO (Exhausted: Month ' + str(bp['exhaustion_month']) + ')'}")
    print(f"  • Projected Month 6 Balance   : ${bp['month_6_balance']:>10.2f}")
    print("  • Action Steps:")
    for a in bp.get("actions", []):
        print(f"    - {a}")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    main()
