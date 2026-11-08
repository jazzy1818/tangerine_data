"""Bank-facing Tangerine datathon app for account profiles and shock planning."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import daily_simulation as ds
import engine
import gemini_advisor as ga

st.set_page_config(
    page_title="Tangerine Mission Control",
    page_icon="🍊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# App styling
st.markdown(
    """
    <style>
    .tangerine-header {
        background: linear-gradient(135deg, #F37021 0%, #D45300 100%);
        padding: 24px;
        border-radius: 12px;
        color: white;
        margin-bottom: 24px;
    }
    .tangerine-header h1 {
        color: white !important;
        margin: 0;
        font-size: 2.2rem;
        font-weight: 800;
    }
    .tangerine-header p {
        color: #FFE6D6;
        margin: 6px 0 0 0;
        font-size: 1.1rem;
    }
    .runway-badge-safe {
        background-color: #E6F4EA;
        color: #137333;
        font-weight: bold;
        padding: 8px 16px;
        border-radius: 20px;
        display: inline-block;
        font-size: 1.1rem;
    }
    .runway-badge-warning {
        background-color: #FFF3E0;
        color: #B06000;
        font-weight: bold;
        padding: 8px 16px;
        border-radius: 20px;
        display: inline-block;
        font-size: 1.1rem;
    }
    .runway-badge-danger {
        background-color: #FCE8E6;
        color: #C5221F;
        font-weight: bold;
        padding: 8px 16px;
        border-radius: 20px;
        display: inline-block;
        font-size: 1.1rem;
    }
    .stButton>button {
        border-radius: 8px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# Header
st.markdown(
    """
    <div class="tangerine-header">
        <h1>🍊 Tangerine Mission Control</h1>
        <p>Bank analyst decision support · Sheridan Datathon 2026</p>
    </div>
    """,
    unsafe_allow_html=True,
)


@st.cache_data
def get_all_accounts():
    return engine.get_account_ids()


def set_account_preset(account_id):
    st.session_state["account_selector"] = account_id


def set_shock_preset(inflow_multiplier, bills_change, one_off_cost, use_typical_spending=False):
    st.session_state["slider_income_mult"] = inflow_multiplier
    st.session_state["slider_bills_increase"] = bills_change
    st.session_state["slider_repair_cost"] = one_off_cost
    st.session_state["repair_uses_typical_spending"] = use_typical_spending


def set_manual_repair_cost():
    st.session_state["repair_uses_typical_spending"] = False


def money(value):
    return f"-${abs(value):,.2f}" if value < 0 else f"${value:,.2f}"


def review_flags(flags):
    if flags:
        st.markdown("**Bank review flags**")
        for flag in flags:
            st.write(f"• {flag}")


try:
    account_ids = get_all_accounts()
except (ValueError, FileNotFoundError) as exc:
    st.error(str(exc))
    st.stop()
if not account_ids:
    st.error("No accounts are available in the supplied monthly data.")
    st.stop()

for key, default in {
    "account_selector": 20111 if 20111 in account_ids else account_ids[0],
    "slider_income_mult": 1.0,
    "slider_bills_increase": 0.0,
    "slider_repair_cost": 0.0,
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

with st.sidebar:
    st.header("👤 Customer Lookup")

    st.markdown("**Quick Preset Accounts:**")
    col_q1, col_q2 = st.columns(2)
    col_q1.button(
        "20111 (Loan)",
        on_click=set_account_preset,
        args=(20111,),
        width="stretch",
    )
    col_q2.button(
        "55447 (Active Loan)",
        on_click=set_account_preset,
        args=(55447,),
        width="stretch",
    )
    col_q1.button(
        "20134 (Bills+Loan)",
        on_click=set_account_preset,
        args=(20134,),
        width="stretch",
    )
    col_q2.button(
        "22812 (Timing Example)",
        on_click=set_account_preset,
        args=(22812,),
        width="stretch",
    )

    account_id = st.number_input(
        "Enter Account ID:",
        min_value=int(min(account_ids)),
        max_value=int(max(account_ids)),
        step=1,
        key="account_selector",
    )

    st.markdown("---")
    st.caption("Use an account ID and the judge’s twist. Missing evidence appears as bank review flags.")

try:
    customer = engine.know_customer(account_id)
except (ValueError, FileNotFoundError) as exc:
    st.error(str(exc))
    st.stop()
if st.session_state.get("repair_uses_typical_spending", False):
    st.session_state["slider_repair_cost"] = customer["raw_S"]

tab1, tab2, tab3, tab4 = st.tabs([
    "1. Know the Customer",
    "2. Take a Shock",
    "3. Goal and Backup Plans",
    "4. Daily Replay and Advisor",
])

with tab1:
    st.subheader(f"Baseline Financial Profile: Account #{account_id}")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Typical Monthly Money In (I)", f"${customer['I']:,.2f}")
    with col2:
        st.metric("Typical Monthly Spending (S)", f"${customer['S']:,.2f}")
    with col3:
        st.metric("Fixed Costs (F)", f"${customer['F']:,.2f}")
    with col4:
        st.metric("Historical Buffer Proxy (B)", f"${customer['B']:,.2f}")

    col5, col6, col7 = st.columns(3)
    with col5:
        st.metric("Household Bills (H)", f"${customer['H']:,.2f}")
    with col6:
        loan_label = f"${customer['P']:,.2f}" if customer['P'] > 0 else "$0.00 (None)"
        st.metric("Active Loan Payment at End of 2025 (P)", loan_label)
    with col7:
        baseline_rw = customer["baseline_runway"]
        if isinstance(baseline_rw, (int, float)):
            badge_html = (
                f"<div class='runway-badge-safe'>⏱️ {baseline_rw:.1f} Months</div>"
                if baseline_rw >= 6
                else f"<div class='runway-badge-danger'>⚠️ {baseline_rw:.1f} Months</div>"
            )
        else:
            badge_html = f"<div class='runway-badge-safe'>🛡️ {baseline_rw}</div>"
        st.markdown(f"**Baseline Runway:**<br>{badge_html}", unsafe_allow_html=True)

    # Demographics & Shared Account Profile
    demo = customer.get("demographics", {})
    st.caption(
        f"📋 **Account Relationship:** {demo.get('relationship', 'Single Owner')} "
        f"| Total Associated Clients: {demo.get('num_clients', 1)}"
    )

    st.markdown("---")
    st.markdown("#### 📈 Historical Cash Flow & Balance (from `monthly_summary.csv`)")

    hist_df = customer["history"].set_index("month")
    chart_data = hist_df[["money_in", "money_out", "avg_daily_balance"]].rename(
        columns={
            "money_in": "Money In ($)",
            "money_out": "Money Out ($)",
            "avg_daily_balance": "Avg Daily Balance ($)",
        }
    )
    st.line_chart(chart_data)


# ==========================================
# PART 2: TAKE A SHOCK
# ==========================================
with tab2:
    st.subheader("⚡ Simulate a Shock (Live Twist Simulator)")
    st.write(
        "Enter the judge-specified changes. The 55% preset is a competition assumption about account inflow."
    )

    # Preset twist buttons with callbacks that reliably update widget keys
    st.markdown("**Quick Preset Twist Cards:**")
    pcol1, pcol2, pcol3, pcol4 = st.columns(4)

    pcol1.button(
        "📋 Twist 1: Layoff (EI 55%)",
        on_click=set_shock_preset,
        args=(0.55, 0.0, 0.0),
        width="stretch",
    )
    pcol2.button(
        "🔥 Twist 2: Furnace Repair (1 mo S)",
        on_click=set_shock_preset,
        args=(1.0, 0.0, float(customer["raw_S"]), True),
        width="stretch",
    )
    pcol3.button(
        "💥 Twist 3: Layoff + 15% Bills",
        on_click=set_shock_preset,
        args=(0.55, 0.15, 0.0),
        width="stretch",
    )
    pcol4.button(
        "🔄 Reset to Normal",
        on_click=set_shock_preset,
        args=(1.0, 0.0, 0.0),
        width="stretch",
    )

    # Shock Sliders bound to session state keys
    scol1, scol2, scol3 = st.columns(3)
    with scol1:
        income_mult = st.slider(
            "Account Inflow Multiplier (0.55 = 55%):",
            min_value=0.0,
            max_value=1.5,
            step=0.05,
            key="slider_income_mult",
        )
    with scol2:
        bills_increase = st.slider(
            "Household Bills Change (e.g. 0.15 = +15%):",
            min_value=-0.50,
            max_value=1.00,
            step=0.05,
            key="slider_bills_increase",
        )
    with scol3:
        repair_cost = st.number_input(
            "One-Off Surprise Cost ($CAD):",
            min_value=0.0,
            max_value=100000.0,
            step=500.0,
            key="slider_repair_cost",
            on_change=set_manual_repair_cost,
        )

    # Compute official baseline shock
    shock = engine.take_shock(
        customer,
        income_multiplier=income_mult,
        bills_increase_pct=bills_increase,
        one_off_costs=repair_cost,
    )

    st.markdown("---")
    st.markdown("#### 🚨 Official Numbers Under Shock")

    mcol1, mcol2, mcol3, mcol4, mcol5 = st.columns(5)
    with mcol1:
        st.metric(
            "Money In After Shock",
            f"${shock['income_after_shock']:,.2f}",
            delta=f"{(income_mult - 1.0)*100:+.0f}%",
        )
    with mcol2:
        st.metric(
            "Spending After Shock",
            f"${shock['spending_after_shock']:,.2f}",
            delta=f"${shock['spending_after_shock'] - customer['S']:+,.2f}",
        )
    with mcol3:
        st.metric(
            "Historical Proxy After One-Off Cost",
            f"${shock['buffer_left']:,.2f}",
            delta=f"-${repair_cost:,.2f}" if repair_cost > 0 else None,
        )
    with mcol4:
        st.metric(
            "Monthly Shortfall (Gap)",
            f"${shock['gap']:,.2f}",
            delta=f"${shock['gap'] - customer['baseline_gap']:+,.2f}",
        )
    with mcol5:
        post_rw = shock["runway"]
        if isinstance(post_rw, (int, float)):
            if post_rw <= 3:
                badge_html = f"<div class='runway-badge-danger'>🚨 {post_rw:.1f} Months</div>"
            elif post_rw <= 6:
                badge_html = f"<div class='runway-badge-warning'>⚠️ {post_rw:.1f} Months</div>"
            else:
                badge_html = f"<div class='runway-badge-safe'>⏱️ {post_rw:.1f} Months</div>"
        else:
            badge_html = f"<div class='runway-badge-safe'>🛡️ {post_rw}</div>"
        st.markdown(f"**Official Shock Runway:**<br>{badge_html}", unsafe_allow_html=True)

    # Optional module classifier: proposals only; the existing plans remain independent.
    try:
        from plan_classification.ui import render_classification
        render_classification(customer, income_mult, bills_increase, repair_cost)
    except Exception:
        st.warning("The optional classifier is unavailable. The financial simulator remains available.")


with tab3:
    st.subheader(f"Goal and Backup Plans for Account {account_id}")
    plans = engine.make_plan(customer, shock=shock)
    goal = plans["goal_plan"]
    backup = plans["backup_plan"]

    st.markdown("### Plan 1 · Goal Plan")
    surplus_col, three_col, six_col = st.columns(3)
    surplus_col.metric("Typical Monthly Surplus", money(goal["monthly_surplus"]))
    three_col.metric("Illustrative 3-Month Reserve", money(goal["target_3mo"]))
    six_col.metric("Illustrative 6-Month Reserve", money(goal["target_6mo"]))
    st.write(goal["recommendation"])
    st.caption(goal["contribution_basis"])
    if backup["remaining_cash_needed"] > 0 and goal["recommended_contribution"] > 0:
        st.caption("The contribution estimate describes normal conditions. Prioritize the modeled funding gap during this shock.")

    for months, column in ((3, three_col), (6, six_col)):
        target = goal[f"target_{months}mo"]
        remaining = goal[f"needed_for_{months}mo"]
        eta = goal[f"months_to_{months}mo"]
        column.caption(f"Gap using historical proxy: {money(remaining)}")
        if target > 0:
            column.progress(min(1.0, max(0.0, customer["B"] / target)))
        if eta is not None and remaining > 0:
            column.caption(f"Illustrative time at modeled contribution: {eta:.1f} months")
    review_flags(goal["review_flags"])

    st.markdown("### Plan 2 · Backup Plan")
    st.caption(
        "No-action projection under the judge’s shock. The historical buffer is an opening proxy, "
        "and unverified spending reductions, outside cash, and payouts are excluded."
    )
    start_col, end_col, gap_col = st.columns(3)
    start_col.metric("Opening Proxy After Immediate Cost", money(backup["initial_buffer_left"]))
    end_col.metric("Month 6 Closing Balance", money(backup["month_6_balance"]))
    gap_col.metric("Extra Starting Cash Needed", money(backup["remaining_cash_needed"]))
    shortage = backup["exhaustion_month"]
    if shortage == 0:
        st.warning("The opening cash proxy goes below zero immediately.")
    elif shortage is not None:
        st.warning(f"The first projected month-end below zero is month {shortage}.")
    else:
        st.info("The projected balance stays nonnegative at the modeled checkpoints through month six.")
    schedule = pd.DataFrame(backup["six_month_schedule"]).rename(columns={
        "month": "Month",
        "start_balance": "Opening balance (CAD)",
        "income": "Money in (CAD)",
        "spending": "Money out (CAD)",
        "net_shortfall": "Shortfall (CAD)",
        "end_balance": "Closing balance (CAD)",
    })
    st.dataframe(schedule.set_index("Month"), width="stretch")
    st.markdown("**Analyst action notes**")
    for action in backup["actions"]:
        st.write(f"• {action}")
    review_flags(backup["review_flags"])

with tab4:
    st.subheader(f"Daily Replay for Account {account_id}")
    st.caption(
        "Historical replay using a pre-window opening proxy and dated cash flows. "
        "It is separate from the official runway calculation."
    )

    with st.expander("Portfolio replay findings"):
        try:
            discovery = ds.get_macro_discovery_data()
        except (FileNotFoundError, ValueError) as exc:
            st.info(f"Portfolio replay unavailable. {exc}")
        else:
            st.caption(discovery["methodology"])
            for point in discovery["summary_points"]:
                st.write(f"• {point}")

    replay_inputs = {
        "income_multiplier": income_mult,
        "bills_increase_pct": bills_increase,
        "one_off_costs": repair_cost,
        "shift_bill_days": 7,
    }
    try:
        baseline = ds.simulate_daily_cashflow(account_id, **replay_inputs)
    except (FileNotFoundError, ValueError) as exc:
        baseline = {"available": False, "reason": f"Daily replay unavailable. {exc}"}
    if not baseline["available"]:
        st.info(baseline["reason"])
    else:
        st.caption(
            f"{baseline['replay_start_date']} to {baseline['replay_end_date']}. "
            f"Opening cash proxy: {money(baseline['initial_balance'])}. {baseline['opening_balance_basis']} "
            "Shortfalls are based on end-of-day cash, with an opening-day check for immediate costs."
        )
        comparison = None
        if baseline["has_bill_to_shift"]:
            candidate = ds.simulate_daily_cashflow(account_id, bill_shift_approved=True, **replay_inputs)
            if candidate["available"] and candidate["shift_bill_days"]:
                comparison = candidate

        baseline_gap = baseline["extra_cash_needed"]
        helpful_move = (
            comparison is not None
            and baseline["first_shortfall_date"] is not None
            and comparison["extra_cash_needed"] <= baseline_gap
            and (
                comparison["first_shortfall_date"] is None
                or comparison["first_shortfall_date"] >= baseline["first_shortfall_date"]
            )
            and (
                comparison["extra_cash_needed"] < baseline_gap
                or comparison["first_shortfall_date"] is None
                or comparison["first_shortfall_date"] > baseline["first_shortfall_date"]
            )
        )
        if comparison is not None:
            bill = baseline["bill_candidate"]
            st.write(
                f"**Conditional comparison.** One recurring bill, with a median historical payment of "
                f"{money(bill['median_payment'])}, moves from {bill['first_original_date']} "
                f"to {bill['first_shifted_date']} on the first modeled payment. Biller approval, "
                "actual current dates, and any fees require bank review."
            )

        paths = [("No action", baseline)]
        if comparison is not None:
            paths.append(("Conditional bill move", comparison))
        st.dataframe(pd.DataFrame([
            {
                "Scenario": label,
                "First shortfall": result["first_shortfall_date"] or "None within replay",
                "Extra starting cash needed (CAD)": result["extra_cash_needed"],
                "Closing balance (CAD)": result["end_balance"],
            }
            for label, result in paths
        ]).set_index("Scenario"), width="stretch")

        figure = go.Figure()
        figure.add_hline(y=0, line_dash="dash", line_color="#C5221F")
        for label, result in paths:
            timeline = pd.DataFrame(result["timeline"])
            figure.add_trace(go.Scatter(
                x=timeline["date"], y=timeline["balance"], mode="lines", name=label,
            ))
        figure.update_layout(
            xaxis_title="Date",
            yaxis_title="Modeled balance (CAD)",
            margin=dict(l=20, r=20, t=30, b=20),
            hovermode="x unified",
            height=400,
        )
        st.plotly_chart(figure, width="stretch")

        with st.expander("Daily balance ledger"):
            st.dataframe(pd.DataFrame(baseline["timeline"]), width="stretch")

        effect_types = [
            name for name, active in (
                ("inflow_change", income_mult != 1.0),
                ("bill_change", bills_increase != 0),
                ("one_off_expense", repair_cost > 0),
            )
            if active
        ]
        shock_type = "compound" if len(effect_types) > 1 else next(iter(effect_types), "none")
        advisory = ga.consult_gemini_advisor(
            shock_type=shock_type,
            days_to_shortfall=baseline["days_to_shortfall"],
            cash_needed=baseline_gap,
            has_bill_to_shift=helpful_move,
            has_one_off=repair_cost > 0,
        )
        advice = advisory["plan"]
        st.markdown("**Analyst review**")
        st.write(advice["title"])
        st.write(advice["rationale"])
        review_flags(advice["bank_review_flags"])
        st.caption("Selector: Gemini" if advisory["is_ai_live"] else "Selector: Local rules")
