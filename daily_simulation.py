"""End-of-day historical cash-flow replay and conditional bill-date comparison."""

from functools import lru_cache
from math import isfinite
from pathlib import Path

import pandas as pd


DATA_DIR = Path(__file__).resolve().parent / "data"
REPLAY_START = "2025-07-01"
REPLAY_END = "2025-12-31"
_SERIES_COLUMNS = ["account_id", "partner_bank", "partner_account"]


@lru_cache(maxsize=2)
def load_transactions(data_dir=DATA_DIR):
    """Read only the fields needed for dated flows and recurring bills."""
    path = Path(data_dir) / "transactions.csv"
    if not path.exists():
        path = path.with_suffix(".csv.gz")
    if not path.exists():
        raise FileNotFoundError(f"transactions.csv or transactions.csv.gz not found in {data_dir}")
    columns = [*_SERIES_COLUMNS, "date", "purpose", "signed_amount"]
    transactions = pd.read_csv(
        path, usecols=columns, parse_dates=["date"], keep_default_na=False,
        dtype={"partner_bank": "string", "partner_account": "string"},
    )
    transactions["signed_amount"] = pd.to_numeric(transactions["signed_amount"], errors="coerce")
    return transactions


@lru_cache(maxsize=2)
def _load_monthly(data_dir):
    monthly = pd.read_csv(
        Path(data_dir) / "monthly_summary.csv",
        usecols=["account_id", "month", "avg_daily_balance"],
    )
    monthly["month"] = pd.PeriodIndex(monthly["month"], freq="M")
    return monthly.sort_values("month")


def _window(tx, start, end):
    return tx.loc[tx["date"].between(start, end)]


def _bill_mask(tx):
    return tx["purpose"].eq("household bills") & tx["signed_amount"].lt(0)


def _largest_recurring_bill(tx, start):
    """Choose one counterparty using six completed months before replay."""
    first_month = start.to_period("M")
    prior = _window(tx, (first_month - 6).start_time, first_month.start_time - pd.Timedelta(days=1))
    bills = prior.loc[
        _bill_mask(prior)
        & prior["partner_bank"].ne("")
        & ~prior["partner_account"].isin(["", "0", "0.0"]),
        [*_SERIES_COLUMNS, "date", "signed_amount"],
    ].assign(
        month=lambda rows: rows["date"].dt.to_period("M"),
        day=lambda rows: rows["date"].dt.day,
    )
    series = bills.groupby(_SERIES_COLUMNS, as_index=False).agg(
        payments=("date", "size"), months=("month", "nunique"),
        earliest_day=("day", "min"), latest_day=("day", "max"),
        median_debit=("signed_amount", "median"),
    )
    recurring = series.loc[
        series["payments"].eq(6) & series["months"].eq(6)
        & (series["latest_day"] - series["earliest_day"]).le(2)
    ]
    return recurring.sort_values(["median_debit", *_SERIES_COLUMNS]).drop_duplicates("account_id")


def _movable_payments(tx, recurring, days, end, expected_months):
    """Match the chosen series to the replay and keep dates inside their month."""
    matched = tx.loc[_bill_mask(tx)].merge(recurring, on=_SERIES_COLUMNS, how="inner")
    matched["shifted_date"] = matched["date"] + pd.Timedelta(days=days)
    matched["month"] = matched["date"].dt.to_period("M")
    matched["date_allowed"] = matched["shifted_date"].le(end) & matched["shifted_date"].dt.to_period("M").eq(matched["month"])
    coverage = matched.groupby("account_id").agg(
        payments=("date", "size"), months=("month", "nunique"), all_dates_allowed=("date_allowed", "all"),
    )
    eligible = coverage.index[
        coverage["payments"].eq(expected_months) & coverage["months"].eq(expected_months)
        & coverage["all_dates_allowed"]
    ]
    return matched.loc[matched["account_id"].isin(eligible)].sort_values("date")


def _shocked_amounts(tx, income_multiplier, bills_increase_pct):
    amounts = tx["signed_amount"].astype(float)
    amounts = amounts.where(amounts.le(0), amounts * income_multiplier)
    return amounts.where(~_bill_mask(tx), amounts * (1 + bills_increase_pct))


def simulate_daily_cashflow(
    account_id,
    initial_balance=None,
    income_multiplier=0.55,
    bills_increase_pct=0.15,
    one_off_costs=0.0,
    shift_bill_days=0,
    bill_shift_approved=False,
    start_date=REPLAY_START,
    end_date=REPLAY_END,
    data_dir=DATA_DIR,
):
    """Replay observed end-of-day flows with one optional conditional bill move.

    The default opening balance is an average from completed months before the
    replay. A supplied opening balance is a separate scenario input.
    """
    start, end = pd.Timestamp(start_date).normalize(), pd.Timestamp(end_date).normalize()
    if pd.isna(start) or pd.isna(end) or start > end or start.tzinfo is not None or end.tzinfo is not None:
        raise ValueError("Replay start date must be on or before the end date")
    if not all(isfinite(value) for value in (income_multiplier, bills_increase_pct, one_off_costs)):
        raise ValueError("Replay scenario amounts must be finite")
    if income_multiplier < 0 or bills_increase_pct < -1 or one_off_costs < 0 or shift_bill_days < 0 or shift_bill_days % 1:
        raise ValueError("Invalid replay scenario amounts")
    if initial_balance is not None and not isfinite(initial_balance):
        raise ValueError("Scenario opening balance must be finite")

    monthly = _load_monthly(data_dir)
    history = monthly.loc[monthly["account_id"].eq(account_id)].set_index("month")
    replay_months = pd.period_range(start, end, freq="M")
    if not replay_months.isin(history.index).all():
        return {"available": False, "reason": "Account history does not cover the full replay window."}

    if initial_balance is None:
        prior = history.loc[history.index < replay_months[0], "avg_daily_balance"].tail(6)
        if prior.empty or not prior.map(isfinite).all():
            return {"available": False, "reason": "No usable opening-balance history before the replay window."}
        initial_balance = float(prior.mean())
        opening_basis = f"Historical proxy from {len(prior)} completed account months before the replay"
    else:
        opening_basis = "Supplied scenario opening balance"

    transactions = load_transactions(data_dir)
    account = transactions.loc[transactions["account_id"].eq(account_id)]
    if account.empty:
        return {"available": False, "reason": "No transaction records for this account."}
    replay = _window(account, start, end)
    if not replay["signed_amount"].map(isfinite).all():
        return {"available": False, "reason": "Unusable transaction amounts within the replay window."}
    flows = _shocked_amounts(replay, income_multiplier, bills_increase_pct)
    daily = flows.groupby(replay["date"]).sum().reindex(pd.date_range(start, end), fill_value=0.0)

    candidate = None
    if shift_bill_days:
        recurring = _largest_recurring_bill(account, start)
        movable = _movable_payments(replay, recurring, shift_bill_days, end, len(replay_months))
        if not movable.empty:
            first = movable.iloc[0]
            candidate = {
                "observed_payments": int(first["payments"]),
                "matched_payments": len(movable),
                "median_payment": round(-float(first["median_debit"]), 2),
                "first_original_date": first["date"].strftime("%Y-%m-%d"),
                "first_shifted_date": first["shifted_date"].strftime("%Y-%m-%d"),
            }
            if bill_shift_approved:
                moved_amounts = movable["signed_amount"] * (1 + bills_increase_pct)
                daily = daily.sub(moved_amounts.groupby(movable["date"]).sum(), fill_value=0.0)
                daily = daily.add(moved_amounts.groupby(movable["shifted_date"]).sum(), fill_value=0.0)

    cash_after_cost = initial_balance - one_off_costs
    balances = (cash_after_cost + daily.cumsum()).round(2)
    opening_minimum = round(min(initial_balance, cash_after_cost), 2)
    min_balance = min(opening_minimum, balances.min())
    negative_days = balances.index[balances.lt(0)]
    first_shortfall = start if opening_minimum < 0 else next(iter(negative_days), None)
    month_ends = balances.groupby(balances.index.to_period("M")).last()
    timeline = [{
        "date": start.strftime("%Y-%m-%d"), "delta": 0.0, "balance": round(initial_balance, 2),
        "type": "initial_balance", "description": "Scenario opening balance before daily flows",
    }]
    if one_off_costs:
        timeline.append({
            "date": start.strftime("%Y-%m-%d"), "delta": -round(one_off_costs, 2),
            "balance": round(cash_after_cost, 2), "type": "one_off_repair",
            "description": "Immediate one-off scenario cost",
        })
    timeline.extend(
        {
            "date": day.strftime("%Y-%m-%d"), "delta": round(float(daily.loc[day]), 2),
            "balance": round(float(balance), 2), "type": "end_of_day", "description": "Net daily cash flow",
        }
        for day, balance in balances.items()
    )
    applied = bool(candidate and bill_shift_approved)
    return {
        "available": True,
        "account_id": account_id,
        "initial_balance": round(initial_balance, 2),
        "opening_balance_basis": opening_basis,
        "replay_start_date": start.strftime("%Y-%m-%d"),
        "replay_end_date": end.strftime("%Y-%m-%d"),
        "end_balance": round(float(balances.iloc[-1]), 2),
        "min_balance": round(float(min_balance), 2),
        "extra_cash_needed": round(max(0.0, -min_balance), 2),
        "first_shortfall_date": first_shortfall.strftime("%Y-%m-%d") if first_shortfall is not None else None,
        "days_to_shortfall": (first_shortfall - start).days if first_shortfall is not None else None,
        "makes_it_through_horizon": first_shortfall is None,
        "intra_month_only_shortfall": bool(
            opening_minimum >= 0 and len(negative_days) and month_ends.ge(0).all()
        ),
        "total_events": len(replay) + int(one_off_costs > 0),
        "timeline": timeline,
        "has_bill_to_shift": candidate is not None,
        "bill_candidate": candidate,
        "shift_bill_days": shift_bill_days if applied else 0,
        "bill_shift_approved": applied,
    }


def compare_bill_shift(account_id, initial_balance=None, income_multiplier=0.55, bills_increase_pct=0.15,
                       shift_days=7, data_dir=DATA_DIR):
    """Compare the same replay with and without the eligible bill-date change."""
    inputs = dict(
        initial_balance=initial_balance, income_multiplier=income_multiplier, bills_increase_pct=bills_increase_pct,
        shift_bill_days=shift_days, data_dir=data_dir,
    )
    baseline = simulate_daily_cashflow(account_id, **inputs)
    if not baseline["available"]:
        return baseline
    shifted = simulate_daily_cashflow(account_id, bill_shift_approved=True, **inputs)
    before, after = baseline["days_to_shortfall"], shifted["days_to_shortfall"]
    return {
        "available": True, "account_id": account_id, "baseline": baseline, "shifted": shifted,
        "days_bought": after - before if before is not None and after is not None else None,
        "cash_deficit_reduction": round(baseline["extra_cash_needed"] - shifted["extra_cash_needed"], 2),
        "remaining_cash_needed": shifted["extra_cash_needed"],
    }


def _daily_matrix(account_ids, days, amounts, tx):
    by_day = amounts.groupby([tx["account_id"], tx["date"]]).sum().unstack(fill_value=0.0)
    return by_day.reindex(index=account_ids, columns=days, fill_value=0.0)


@lru_cache(maxsize=2)
def get_macro_discovery_data(data_dir=DATA_DIR):
    """Reproduce the existing timing discovery with the same replay rules."""
    start, end = pd.Timestamp(REPLAY_START), pd.Timestamp(REPLAY_END)
    months = pd.period_range(start, end, freq="M")
    days = pd.date_range(start, end)
    month_ends = months.to_timestamp(how="end").normalize()
    monthly = _load_monthly(data_dir)
    coverage = monthly.loc[monthly["month"].isin(months)].groupby("account_id")["month"].nunique()
    prior = monthly.loc[monthly["month"].lt(months[0])].groupby("account_id").tail(6)
    opening = prior.groupby("account_id")["avg_daily_balance"].mean()
    opening = opening.loc[opening.index.intersection(coverage.index[coverage.eq(len(months))])]
    invalid_prior = prior.loc[~prior["avg_daily_balance"].map(isfinite), "account_id"]
    opening = opening.loc[~opening.index.isin(invalid_prior)]

    tx = load_transactions(data_dir)
    replay = _window(tx, start, end)
    invalid_replay = replay.loc[~replay["signed_amount"].map(isfinite), "account_id"]
    opening = opening.loc[opening.index.isin(tx["account_id"]) & ~opening.index.isin(invalid_replay)]
    replay = replay.loc[replay["account_id"].isin(opening.index)]
    amounts = _shocked_amounts(replay, 0.55, 0.15)
    daily = _daily_matrix(opening.index, days, amounts, replay)
    cash = daily.cumsum(axis=1).add(opening, axis=0).round(2)

    clears_monthly = opening.round(2).ge(0) & cash[month_ends].ge(0).all(axis=1)
    hidden = cash.index[clears_monthly & cash.lt(0).any(axis=1)]
    recurring = _largest_recurring_bill(tx.loc[tx["account_id"].isin(hidden)], start)
    movable = _movable_payments(replay, recurring, 7, end, len(months))
    candidates = pd.Index(movable["account_id"].unique())
    moved_amounts = movable["signed_amount"] * 1.15
    before = _daily_matrix(candidates, days, moved_amounts, movable)
    after = _daily_matrix(candidates, days, moved_amounts, movable.assign(date=movable["shifted_date"]))
    shifted = (daily.loc[candidates] - before + after).cumsum(axis=1).add(opening.loc[candidates], axis=0).round(2)
    resolved = int(shifted.ge(0).all(axis=1).sum())
    monthly_change = (
        round(float((shifted[month_ends] - cash.loc[candidates, month_ends]).abs().max().max()), 2)
        if len(candidates) else 0.0
    )
    total = len(opening)
    clear_count = int(clears_monthly.sum())
    return {
        "total_accounts": total,
        "nonnegative_month_end_accounts": clear_count,
        "intra_month_overdrafts": len(hidden),
        "accounts_with_movable_bill": len(candidates),
        "overdrafts_resolved_by_shift": resolved,
        "resolution_rate_pct": round(100 * resolved / len(candidates), 1) if len(candidates) else 0.0,
        "month_end_balance_delta": monthly_change,
        "methodology": (
            "July–December 2025 complete-history cohort. Start with the mean daily balance from up to six "
            "completed pre-July account months, scale all observed inflows to 55%, and increase identified "
            "household bills by 15%. Measure end-of-day cash, then replay a conditional seven-day move of one "
            "recurring bill identified from pre-July history. Every shifted payment stays in its original month."
        ),
        "summary_points": [
            f"{total:,} accounts met the replay data requirements.",
            f"{clear_count:,} started and closed each month nonnegative. {len(hidden):,} of these went negative between month-ends.",
            f"{len(candidates):,} of the timing-shortfall accounts had a qualifying bill-date scenario. "
            f"The conditional move avoided a daily shortfall for {resolved:,}.",
            "This replay assumes no fee for the date change. Historical payment records do not establish approval.",
        ],
        "distribution": [
            {"Category": "Negative opening balance or month-end", "Accounts": total - clear_count},
            {"Category": "No shortfall", "Accounts": clear_count - len(hidden)},
            {"Category": "Daily shortfall avoided in conditional replay", "Accounts": resolved},
            {"Category": "Daily shortfall remained after conditional move", "Accounts": len(candidates) - resolved},
            {"Category": "Daily shortfall and no qualifying bill move", "Accounts": len(hidden) - len(candidates)},
        ],
    }
