"""Tangerine Resilience Engine - official calculations and bank-facing plans.

Implements the official logic and definitions specified in Tangerine/README.md:
1. Know the customer (I, F, S, B, H, P, Runway)
2. Take a shock (EI, bills increase, one-off repairs)
3. Make a plan (Goal Plan & Backup Plan)

Features:
- Full mathematical precision (raw unrounded floats used for calculations)
- Month 0 immediate one-off overdraft detection in trajectory
- Consistent savings contribution rate and ETA projections
- Unprotected six-month shock projections and bank-review flags
"""

import argparse
from math import ceil, isfinite
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import pandas as pd
from investment_triggers import evaluate_investment_triggers

ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"

_CACHE: Dict[Path, Dict[str, pd.DataFrame]] = {}


def load_data(data_dir: Path = DATA_DIR) -> Dict[str, pd.DataFrame]:
    """Load and cache the required CSV tables."""
    data_dir = Path(data_dir).resolve()
    if data_dir not in _CACHE:
        monthly_path = data_dir / "monthly_summary.csv"
        loans_path = data_dir / "loans.csv"

        if not monthly_path.exists() or not loans_path.exists():
            raise FileNotFoundError(f"Data files not found in {data_dir}")

        data = {"monthly": pd.read_csv(monthly_path), "loans": pd.read_csv(loans_path)}
        dispositions_path = data_dir / "dispositions.csv"
        if dispositions_path.exists():
            data["dispositions"] = pd.read_csv(dispositions_path)
        _CACHE[data_dir] = data

    return _CACHE[data_dir]


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
    if not isfinite(buffer_left) or not isfinite(gap):
        raise ValueError("Runway requires a finite balance and cash gap.")
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

    cost_columns = ["household_bills", "insurance", "loan_payments"]
    required = ["money_in", "money_out", "avg_daily_balance", *cost_columns]
    try:
        valid_amounts = all(map(isfinite, acc_df[required].to_numpy().flat))
    except (KeyError, TypeError):
        valid_amounts = False
    if not valid_amounts or acc_df["month"].isna().any():
        raise ValueError(f"Account ID {account_id} has incomplete official metric data.")

    raw_I = float(acc_df["money_in"].median())
    fixed_series = acc_df[cost_columns].sum(axis=1)
    raw_F = float(fixed_series.median())
    raw_S = float(acc_df["money_out"].median())
    last_6 = acc_df.tail(6)
    raw_B = float(last_6["avg_daily_balance"].mean())
    raw_H = float(acc_df["household_bills"].median())

    acc_loans = loans[loans["account_id"] == account_id]
    raw_P = 0.0
    loan_status = None
    status = None
    if not acc_loans.empty:
        status = str(acc_loans.iloc[0]["status"]).strip()
        if len(acc_loans) != 1 or status not in {"A", "B", "C", "D"}:
            raise ValueError(f"Account ID {account_id} has ambiguous loan status data.")
        loan_status = acc_loans.iloc[0]["status_meaning"]
        if status in ["C", "D"]:
            raw_P = float(acc_loans.iloc[0]["monthly_payment"])
            if not isfinite(raw_P) or raw_P < 0:
                raise ValueError(f"Account ID {account_id} has an invalid active loan payment.")

    baseline_gap = raw_S - raw_I
    baseline_runway = calculate_runway(raw_B, baseline_gap)

    # Demographics & Shared Access check
    demographics = {
        "num_clients": None,
        "relationship": "Account access records unavailable",
    }
    if "dispositions" in data:
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
        "source_loan_status": status,
        "data_dir": str(data_dir),
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
    if not all(isfinite(value) for value in (income_multiplier, bills_increase_pct, one_off_costs)):
        raise ValueError("Shock inputs must be finite numbers.")
    if income_multiplier < 0 or bills_increase_pct < -1 or one_off_costs < 0:
        raise ValueError("Shock inputs cannot create negative income, bills, or one-off costs.")

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
        "raw_one_off_costs": one_off_costs,
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
    *,
    confirmed_monthly_cut: float = 0.0,
) -> Dict[str, Any]:
    """Project the six-month judge scenario without unverified funds or relief."""
    shock = take_shock(customer, income_multiplier, bills_increase_pct, one_off_costs)
    raw_B = customer.get("raw_B", customer["B"])
    raw_S = customer.get("raw_S", customer["S"])
    raw_F = customer.get("raw_F", customer["F"])
    monthly_income = shock["raw_income_after_shock"]
    spending_before_cut = shock["raw_spending_after_shock"]
    cut_limit = min(max(0.0, raw_S - raw_F), spending_before_cut)
    if not isfinite(confirmed_monthly_cut) or not 0 <= confirmed_monthly_cut <= cut_limit:
        raise ValueError("A confirmed cut must be finite and fit within the modeled non-fixed spending.")

    monthly_spending = spending_before_cut - confirmed_monthly_cut
    monthly_gap = monthly_spending - monthly_income
    initial_balance = shock["raw_buffer_left"]
    balance = initial_balance
    minimum_balance = balance
    exhaustion_month = 0 if balance < 0 else None

    schedule: List[Dict[str, Any]] = []
    if one_off_costs > 0 or exhaustion_month == 0:
        schedule.append({
            "month": "Month 0 (Shock)",
            "start_balance": round(raw_B, 2),
            "income": 0.0,
            "spending": round(one_off_costs, 2),
            "net_shortfall": round(one_off_costs, 2),
            "end_balance": round(balance, 2),
        })

    for month in range(1, 7):
        start_balance = balance
        balance -= monthly_gap
        minimum_balance = min(minimum_balance, balance)
        if balance < 0 and exhaustion_month is None:
            exhaustion_month = month
        schedule.append({
            "month": f"Month {month}",
            "start_balance": round(start_balance, 2),
            "income": round(monthly_income, 2),
            "spending": round(monthly_spending, 2),
            "net_shortfall": round(monthly_gap, 2),
            "end_balance": round(balance, 2),
        })

    # Round up when the modeled gap contains a fraction of a cent.
    remaining_cash_needed = ceil(max(0.0, -minimum_balance) * 100 - 1e-9) / 100
    return {
        "makes_it_to_month_6": exhaustion_month is None,
        "exhaustion_month": exhaustion_month,
        "month_6_balance": round(balance, 2),
        "avg_shortfall": round(monthly_gap, 2),
        "initial_buffer_left": round(initial_balance, 2),
        "remaining_cash_needed": remaining_cash_needed,
        "schedule": schedule,
    }


def make_plan(
    customer: Dict[str, Any],
    shock: Optional[Dict[str, Any]] = None,
    *,
    confirmed_monthly_cut: float = 0.0,
    analyst_evidence=None,
) -> Dict[str, Any]:
    """Return historical reserve estimates and a conditional shock projection."""
    raw_I = customer.get("raw_I", customer["I"])
    raw_S = customer.get("raw_S", customer["S"])
    raw_B = customer.get("raw_B", customer["B"])
    raw_P = customer.get("raw_P", customer["P"])
    monthly_surplus = round(raw_I - raw_S, 2)
    transactions = None
    if customer.get("data_dir"):
        from daily_simulation import load_transactions
        try:
            transactions = load_transactions(Path(customer["data_dir"]))
        except (OSError, ValueError):
            # Optional dated evidence remains unknown; monthly metrics still work.
            pass
    # MANDATORY: every UI/CLI goal uses the S01-S40 runtime enforcement inside
    # evaluate_investment_triggers. Never substitute unchecked model/selector
    # output here; missing facts stay unknown and violations require review.
    investment_plan = evaluate_investment_triggers(customer, shock, transactions=transactions, evidence=analyst_evidence)
    allocation_features = investment_plan["features"]
    planning_spending = allocation_features.get("median_monthly_spending", raw_S)
    planning_cash = allocation_features.get("opening_cash_estimate", raw_B)
    target_3mo = round(3 * planning_spending, 2)
    target_6mo = round(6 * planning_spending, 2)
    needed_3mo = max(0.0, round(target_3mo - planning_cash, 2))
    needed_6mo = max(0.0, round(target_6mo - planning_cash, 2))
    goal_flags = investment_plan["bank_review_flags"]
    # Reserve earmarks stay liquid. Investment allocations are a separate review,
    # never the same contribution counted toward two goals.
    contribution = investment_plan["reserve_monthly_earmark"]

    goal_plan: Dict[str, Any] = {
        "monthly_surplus": monthly_surplus,
        "target_3mo": target_3mo,
        "target_6mo": target_6mo,
        "current_buffer": round(planning_cash, 2),
        "needed_for_3mo": needed_3mo,
        "needed_for_6mo": needed_6mo,
        "recommended_contribution": contribution,
        "months_to_3mo": round(needed_3mo / contribution, 1) if contribution > 0 else None,
        "months_to_6mo": round(needed_6mo / contribution, 1) if contribution > 0 else None,
        "contribution_basis": (
            "Conditional liquid-reserve earmark capped at 75% of the weaker of the minimum and "
            "lower-quartile trailing net flows, subject to operating-cash and selected-scenario checks. "
            "Policy and detailed calculations are shown in Allocation Review. Transfers do not create wealth."
        ),
        "review_flags": goal_flags,
    }
    goal_plan["recommendation"] = investment_plan["recommendation"]
    goal_plan["primary_goal"] = investment_plan["primary_goal"]

    backup_plan: Dict[str, Any] = {}
    if shock is not None:
        traj = simulate_6mo_trajectory(
            customer,
            income_multiplier=shock["income_multiplier"],
            bills_increase_pct=shock["bills_increase_pct"],
            one_off_costs=shock.get("raw_one_off_costs", shock["one_off_costs"]),
            confirmed_monthly_cut=confirmed_monthly_cut,
        )
        review_flags = [
            "BANK_REVIEW_REQUIRED: The six-month projection uses a historical opening balance. "
            "Spending flexibility, new credit and insurance payouts are unverified.",
        ]
        if shock["income_multiplier"] < 1:
            review_flags.append(
                "BANK_REVIEW_REQUIRED: Lower inflow is a scenario assumption. "
                "Benefit eligibility and income after Month 6 are unverified."
            )
        if raw_P > 0:
            review_flags.append(
                f"BANK_REVIEW_REQUIRED: CAD {raw_P:,.2f}/month is recorded for an active loan at the end "
                "of 2025. Current terms, interest and relief are unverified."
            )

        exhaustion_month = traj["exhaustion_month"]
        if exhaustion_month is None:
            actions = ["Monitor the modeled balance and preserve essential obligations through Month 6."]
        else:
            first_gap = "at the start of the scenario" if exhaustion_month == 0 else f"in Month {exhaustion_month}"
            actions = [
                f"Prioritize essential obligations. The first modeled shortfall occurs {first_gap}. "
                f"The unresolved six-month funding need is CAD {traj['remaining_cash_needed']:,.2f}."
            ]

        backup_plan = {
            "projection_scope": "Official full-history medians and numeric judge twist only; additional evidence is in investment_plan.scenario_results.",
            "funding_result_complete": investment_plan["funding_result_complete"] and not bool(analyst_evidence and analyst_evidence.known_expenses),
            "unprotected_runway": shock["runway"],
            "monthly_cash_gap": shock["gap"],
            "buffer_left": shock["buffer_left"],
            "has_active_loan": raw_P > 0,
            "loan_payment": round(raw_P, 2),
            "confirmed_savings": confirmed_monthly_cut,
            "makes_it_to_month_6": traj["makes_it_to_month_6"],
            "exhaustion_month": exhaustion_month,
            "month_6_balance": traj["month_6_balance"],
            "initial_buffer_left": traj["initial_buffer_left"],
            "remaining_cash_needed": traj["remaining_cash_needed"],
            "six_month_schedule": traj["schedule"],
            "actions": actions,
            "review_flags": review_flags,
        }

    return {"goal_plan": goal_plan, "backup_plan": backup_plan, "investment_plan": investment_plan}


def run_pipeline(
    account_id: int,
    income_multiplier: float = 1.0,
    bills_increase_pct: float = 0.0,
    one_off_costs: float = 0.0,
    data_dir: Path = DATA_DIR,
    *,
    analyst_evidence=None,
) -> Dict[str, Any]:
    """Execute the complete 3-step pipeline."""
    customer = know_customer(account_id, data_dir=data_dir)
    shock = take_shock(
        customer,
        income_multiplier=income_multiplier,
        bills_increase_pct=bills_increase_pct,
        one_off_costs=one_off_costs,
    )
    plan = make_plan(customer, shock=shock, analyst_evidence=analyst_evidence)

    return {
        "customer": customer,
        "shock": shock,
        "plan": plan,
    }


def main():
    parser = argparse.ArgumentParser(description="Tangerine Resilience Engine CLI")
    parser.add_argument("account_pos", type=int, nargs="?", default=None, help="Account ID (positional)")
    parser.add_argument("--account", type=int, default=None, help="Account ID")
    parser.add_argument("--ei", type=float, default=1.0, help="Income multiplier (e.g. 0.55 for EI)")
    parser.add_argument("--bills", type=float, default=0.0, help="Household bills increase (e.g. 0.15 for 15 percent)")
    parser.add_argument("--repair", type=float, default=0.0, help="One-off surprise cost in CAD")
    args = parser.parse_args()

    if args.account_pos is not None and args.account is not None and args.account_pos != args.account:
        parser.error("The positional account ID and --account must match when both are supplied.")
    target_account = args.account_pos if args.account_pos is not None else (args.account if args.account is not None else 20111)

    try:
        results = run_pipeline(
            account_id=target_account,
            income_multiplier=args.ei,
            bills_increase_pct=args.bills,
            one_off_costs=args.repair,
        )
    except (ValueError, FileNotFoundError) as error:
        parser.error(str(error))

    c = results["customer"]
    s = results["shock"]
    p = results["plan"]

    def runway_label(value: Union[float, str]) -> str:
        return value if isinstance(value, str) else f"{value:.1f} months"

    print("\n" + "=" * 65)
    print(f" TANGERINE RESILIENCE ARCHITECT REPORT: Account {target_account}")
    print("=" * 65)
    print("PART 1: KNOW THE CUSTOMER (Official Baseline)")
    print(f"  • Typical Monthly Money In (I): ${c['I']:>10.2f}")
    print(f"  • Typical Monthly Spending (S): ${c['S']:>10.2f}")
    print(f"  • Fixed Costs (F)             : ${c['F']:>10.2f}")
    print(f"  • Household Bills (H)         : ${c['H']:>10.2f}")
    print(f"  • 2025 Active Loan Payment (P): ${c['P']:>10.2f}")
    print(f"  • Historical Buffer (B)       : ${c['B']:>10.2f}")
    print(f"  • Baseline Runway             : {runway_label(c['baseline_runway'])}")

    print("\nPART 2: TAKE A SHOCK")
    print(f"  • Shock Inputs                : Inflow x{s['income_multiplier']:.2f}, Bills {s['bills_increase_pct']:+.1%}, One-off: ${s['one_off_costs']:.2f}")
    print(f"  • Inflow After Shock          : ${s['income_after_shock']:>10.2f}")
    print(f"  • Spending After Shock        : ${s['spending_after_shock']:>10.2f}")
    print(f"  • Remaining Buffer            : ${s['buffer_left']:>10.2f}")
    print(f"  • Monthly Shortfall / Gap     : ${s['gap']:>10.2f}")
    print(f"  • SHOCK RUNWAY (UNPROTECTED)  : {runway_label(s['runway'])}")

    print("\nPART 3: MAKE A PLAN")
    gp = p["goal_plan"]
    print("  [Plan 1: Goal Plan - Normal Times]")
    print(f"  • Monthly Surplus             : ${gp['monthly_surplus']:>10.2f}")
    print(f"  • Illustrative 3-Month Reserve: ${gp['target_3mo']:>10.2f} (Needed: ${gp['needed_for_3mo']:.2f})")
    print(f"  • Illustrative 6-Month Reserve: ${gp['target_6mo']:>10.2f} (Needed: ${gp['needed_for_6mo']:.2f})")
    print(f"  • Reserve Review              : {gp['recommendation']}")
    for flag in gp["review_flags"]:
        print(f"    - {flag}")

    bp = p["backup_plan"]
    print("\n  [Plan 2: Backup Plan - Active Shock]")
    print(f"  • Active Shock Runway         : {runway_label(bp['unprotected_runway'])}")
    print(f"  • Monthly Cash Gap            : ${bp['monthly_cash_gap']:>10.2f}")
    print(f"  • Makes it to Month 6?        : {'YES' if bp['makes_it_to_month_6'] else 'NO (Exhausted: Month ' + str(bp['exhaustion_month']) + ')'}")
    print(f"  • Projected Month 6 Balance   : ${bp['month_6_balance']:>10.2f}")
    print(f"  • Unresolved Funding Need     : ${bp['remaining_cash_needed']:>10.2f}")
    print("  • Analyst Review:")
    for item in [*bp["actions"], *bp["review_flags"]]:
        print(f"    - {item}")
    investment = p["investment_plan"]
    print("\nALLOCATION REVIEW (Conditional, no security selection)")
    print(f"  • Goal                        : {investment['primary_goal']}")
    print(f"  • Normal allocation           : ${investment['normal_monthly_allocation']:,.2f}/mo")
    print(f"  • Selected scenario allocation: ${investment['selected_scenario_monthly_allocation']:,.2f}/mo")
    print(f"  • All listed stress scenarios : ${investment['all_scenarios_monthly_allocation']:,.2f}/mo")
    print(f"  • Active triggers             : {', '.join(investment['trigger_ids'])}")
    print(f"  • Suitability                 : {investment['investment_suitability']}")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    main()
