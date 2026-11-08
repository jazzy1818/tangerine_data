"""Tangerine Resilience Architect - Web Application.

A financial resilience engine for real bank customers.
Complies with Sheridan Datathon 2026 Tangerine Track guidelines.
Features:
- Part 1: Know the Customer (Official Baseline)
- Part 2: Take a Shock (Live Twist Simulator)
- Part 3: Make a Plan (Plan 1: Goal Plan & Plan 2: Backup Plan with 6-Month Trajectory)
  + Extended Tangerine Wealth Waterfall & Underwritten Protection Suite
- Part 4: Live ETF & Market Intelligence (Real Yahoo Finance API + Dynamic Ticker Screener)
"""

from pathlib import Path
import os
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import engine
import etf_service
import daily_simulation as ds
import gemini_advisor as ga

st.set_page_config(
    page_title="Tangerine Resilience Architect",
    page_icon="🍊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom Tangerine Orange & Clean Styling
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
    .metric-card {
        background-color: #F8F9FA;
        border: 1px solid #E9ECEF;
        border-radius: 10px;
        padding: 16px;
        text-align: center;
    }
    .etf-card {
        background-color: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 10px;
        padding: 16px;
        margin-bottom: 12px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    }
    .plan-box {
        background-color: #FAFAFA;
        border: 1px solid #E0E0E0;
        border-radius: 10px;
        padding: 20px;
        margin-bottom: 20px;
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
        <h1>🍊 Tangerine Resilience Architect</h1>
        <p>Know the Customer · Take a Shock · Goal & Backup Plans · Live Market Intelligence | Sheridan Datathon 2026</p>
    </div>
    """,
    unsafe_allow_html=True,
)


@st.cache_data
def get_all_accounts():
    return engine.get_account_ids()


account_ids = get_all_accounts()

# -------------------------------------------------------------
# Callback Functions for Reliable Preset Overwrites & Playbook
# -------------------------------------------------------------
def set_account_preset(acc: int):
    st.session_state["account_selector"] = int(acc)
    # Also reset playbook when switching accounts
    reset_playbook()


def set_shock_preset(ei: float, bills: float, repair: float):
    st.session_state["slider_income_mult"] = float(ei)
    st.session_state["slider_bills_increase"] = float(bills)
    st.session_state["slider_repair_cost"] = float(repair)


def approve_biller_shift():
    st.session_state["biller_approved"] = True
    if "move_recurring_bill" in st.session_state.get("denied_actions", []):
        st.session_state["denied_actions"].remove("move_recurring_bill")
    if "move_recurring_bill" not in st.session_state.get("confirmed_actions", []):
        st.session_state["confirmed_actions"].append("move_recurring_bill")


def deny_biller_shift():
    st.session_state["biller_approved"] = False
    if "move_recurring_bill" not in st.session_state.get("denied_actions", []):
        st.session_state["denied_actions"].append("move_recurring_bill")
    if "move_recurring_bill" in st.session_state.get("confirmed_actions", []):
        st.session_state["confirmed_actions"].remove("move_recurring_bill")


def set_confirmed_cut(cut_pct: float):
    st.session_state["confirmed_spending_cut"] = float(cut_pct)
    if "reduce_confirmed_spending" not in st.session_state.get("confirmed_actions", []):
        st.session_state["confirmed_actions"].append("reduce_confirmed_spending")


def confirm_generic_action(action_id: str):
    if action_id not in st.session_state.get("confirmed_actions", []):
        st.session_state["confirmed_actions"].append(action_id)
    if action_id in st.session_state.get("denied_actions", []):
        st.session_state["denied_actions"].remove(action_id)


def deny_generic_action(action_id: str):
    if action_id not in st.session_state.get("denied_actions", []):
        st.session_state["denied_actions"].append(action_id)
    if action_id in st.session_state.get("confirmed_actions", []):
        st.session_state["confirmed_actions"].remove(action_id)


def reset_playbook():
    st.session_state["denied_actions"] = []
    st.session_state["confirmed_actions"] = []
    st.session_state["biller_approved"] = None
    st.session_state["confirmed_spending_cut"] = 0.0


# Initialize session state keys if not present
if "account_selector" not in st.session_state:
    st.session_state["account_selector"] = 20111

if "slider_income_mult" not in st.session_state:
    st.session_state["slider_income_mult"] = 1.0

if "slider_bills_increase" not in st.session_state:
    st.session_state["slider_bills_increase"] = 0.0

if "slider_repair_cost" not in st.session_state:
    st.session_state["slider_repair_cost"] = 0.0

if "selected_insurance_key" not in st.session_state:
    st.session_state["selected_insurance_key"] = "none"

if "denied_actions" not in st.session_state:
    st.session_state["denied_actions"] = []

if "confirmed_actions" not in st.session_state:
    st.session_state["confirmed_actions"] = []

if "biller_approved" not in st.session_state:
    st.session_state["biller_approved"] = None

if "confirmed_spending_cut" not in st.session_state:
    st.session_state["confirmed_spending_cut"] = 0.0

if "gemini_api_key_input" not in st.session_state:
    st.session_state["gemini_api_key_input"] = ""


# Sidebar: Customer Selector & Settings
with st.sidebar:
    st.header("👤 Customer Lookup")

    st.markdown("**Quick Preset Accounts:**")
    col_q1, col_q2 = st.columns(2)
    col_q1.button(
        "20111 (Loan)",
        on_click=set_account_preset,
        args=(20111,),
        use_container_width=True,
    )
    col_q2.button(
        "55447 (Mortgage)",
        on_click=set_account_preset,
        args=(55447,),
        use_container_width=True,
    )
    col_q1.button(
        "20134 (Bills+Loan)",
        on_click=set_account_preset,
        args=(20134,),
        use_container_width=True,
    )
    col_q2.button(
        "22812 (High Spend)",
        on_click=set_account_preset,
        args=(22812,),
        use_container_width=True,
    )

    account_id = st.number_input(
        "Enter Account ID:",
        min_value=int(min(account_ids)),
        max_value=int(max(account_ids)),
        step=1,
        key="account_selector",
    )

    st.markdown("---")
    st.markdown("### ⚙️ Plan Customization Settings")
    lean_trim_slider = st.slider(
        "Discretionary Spend Trim %:",
        min_value=0.10,
        max_value=0.90,
        value=0.50,
        step=0.05,
        key="trim_slider_key",
        help="Percentage of non-essential discretionary outflows trimmed during Lean Budget mode (groceries and basic shelter remain protected).",
    )
    downpayment_goal = st.number_input(
        "Real Estate Down Payment Goal ($CAD):",
        min_value=10000.0,
        max_value=250000.0,
        value=25000.0,
        step=5000.0,
        key="downpayment_input_key",
    )

    st.markdown("---")
    st.markdown("### 🤖 Gemini AI Advisor Settings")
    st.text_input(
        "Gemini API Key (Optional):",
        type="password",
        key="gemini_api_key_input",
        help="If provided, live reasoning is powered by Gemini 2.5 Flash via google-genai SDK. Otherwise, uses high-speed local deterministic resilience engine.",
    )
    st.caption("🔒 **Zero-PII Isolation:** Strictly coarse action tokens only. No account IDs, client names, birth dates, or exact balances are ever transmitted.")

    st.markdown("---")
    st.markdown("### ℹ️ Official Baseline Legend")
    st.caption(
        "• **I**: Median of `money_in`\n"
        "• **S**: Median of `money_out`\n"
        "• **F**: Median of bills + insurance + loans\n"
        "• **B**: Mean of `avg_daily_balance` (last 6 mo)\n"
        "• **H**: Median of `household_bills`\n"
        "• **P**: Active loan monthly payment\n"
        "• **Runway**: buffer_left ÷ shortfall"
    )

try:
    customer = engine.know_customer(account_id)
    lean_budget = engine.calculate_lean_budget(customer, trim_pct=lean_trim_slider)
    insurance_plans = engine.get_insurance_plans(customer)
except Exception as e:
    st.error(f"Error loading Account {account_id}: {e}")
    st.stop()

# Main Navigation Tabs
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "1️⃣ Know the Customer",
    "2️⃣ Take a Shock (Live Twist)",
    "3️⃣ Required Plans & Wealth Suite",
    "4️⃣ 🛡️ Survive a 'No' (Daily Replay & Gemini Advisor)",
    "5️⃣ 📊 Live ETF & Market Intelligence",
])

# ==========================================
# PART 1: KNOW THE CUSTOMER
# ==========================================
with tab1:
    st.subheader(f"Baseline Financial Profile: Account #{account_id}")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Typical Income (I)", f"${customer['I']:,.2f}")
    with col2:
        st.metric("Typical Spending (S)", f"${customer['S']:,.2f}")
    with col3:
        st.metric("Fixed Costs (F)", f"${customer['F']:,.2f}")
    with col4:
        st.metric("Savings Buffer (B)", f"${customer['B']:,.2f}")

    col5, col6, col7 = st.columns(3)
    with col5:
        st.metric("Household Bills (H)", f"${customer['H']:,.2f}")
    with col6:
        loan_label = f"${customer['P']:,.2f}" if customer['P'] > 0 else "$0.00 (None)"
        st.metric("Active Loan Payment (P)", loan_label)
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
        "Apply live twist cards from the judges to test this customer's resilience under financial stress."
    )

    # Preset twist buttons with callbacks that reliably update widget keys
    st.markdown("**Quick Preset Twist Cards:**")
    pcol1, pcol2, pcol3, pcol4 = st.columns(4)

    pcol1.button(
        "📋 Twist 1: Layoff (EI 55%)",
        on_click=set_shock_preset,
        args=(0.55, 0.0, 0.0),
        use_container_width=True,
    )
    pcol2.button(
        "🔥 Twist 2: Furnace Repair (1 mo S)",
        on_click=set_shock_preset,
        args=(1.0, 0.0, float(customer["raw_S"])),
        use_container_width=True,
    )
    pcol3.button(
        "💥 Twist 3: Layoff + 15% Bills",
        on_click=set_shock_preset,
        args=(0.55, 0.15, 0.0),
        use_container_width=True,
    )
    pcol4.button(
        "🔄 Reset to Normal",
        on_click=set_shock_preset,
        args=(1.0, 0.0, 0.0),
        use_container_width=True,
    )

    # Shock Sliders bound to session state keys
    scol1, scol2, scol3 = st.columns(3)
    with scol1:
        income_mult = st.slider(
            "Income Multiplier (e.g. 0.55 = EI 55%):",
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
        )

    # Compute official baseline shock
    shock = engine.take_shock(
        customer,
        income_multiplier=income_mult,
        bills_increase_pct=bills_increase,
        one_off_costs=repair_cost,
    )

    st.markdown("---")
    st.markdown("#### 🚨 Official Baseline Numbers Under Shock")

    mcol1, mcol2, mcol3, mcol4, mcol5 = st.columns(5)
    with mcol1:
        st.metric(
            "Income After Shock",
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
            "Buffer Left",
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
        st.markdown(f"**Unprotected Runway:**<br>{badge_html}", unsafe_allow_html=True)

    # Optional module classifier: proposals only; the existing plans remain independent.
    try:
        from plan_classification.ui import render_classification
        render_classification(customer, income_mult, bills_increase, repair_cost)
    except Exception:
        st.warning("The optional classifier is unavailable. The financial simulator remains available.")


# ==========================================
# PART 3: REQUIRED PLANS & WEALTH SUITE
# ==========================================
with tab3:
    st.subheader(f"📋 Financial Plans & Resilience Suite: Account #{account_id}")

    # Official Required Plans generated directly from engine.make_plan()
    official_plans = engine.make_plan(customer, shock=shock)
    gp = official_plans["goal_plan"]
    bp = official_plans["backup_plan"]

    # -------------------------------------------------------------
    # SECTION A: REQUIRED PLAN 1 — THE GOAL PLAN (NORMAL TIMES)
    # -------------------------------------------------------------
    st.markdown("### 🎯 Plan 1: Goal Plan (Normal Times)")
    st.caption("Fulfills official requirement: building an emergency fund based on their own numbers.")

    gp_col1, gp_col2, gp_col3 = st.columns(3)
    with gp_col1:
        st.metric("Monthly Surplus (I - S)", f"${gp['monthly_surplus']:,.2f}")
    with gp_col2:
        st.metric(
            "3-Month Target (3 × S)",
            f"${gp['target_3mo']:,.2f}",
            help="Sized to 3 months of typical spending.",
        )
    with gp_col3:
        st.metric(
            "6-Month Target (6 × S)",
            f"${gp['target_6mo']:,.2f}",
            help="Sized to 6 months of typical spending.",
        )

    # Emergency Fund Funding Status Progress Bars
    gprog1, gprog2 = st.columns(2)
    with gprog1:
        pct_3mo = min(1.0, max(0.0, customer["B"] / gp["target_3mo"])) if gp["target_3mo"] > 0 else 1.0
        st.markdown(f"**3-Month Emergency Buffer:** `{pct_3mo*100:.0f}% funded` (Needed: `${gp['needed_for_3mo']:,.2f}`)")
        st.progress(pct_3mo)
        if gp.get("months_to_3mo") is not None:
            if gp["months_to_3mo"] == 0:
                st.success("🎉 Target 3-month buffer is already fully funded!")
            else:
                st.info(f"⏳ At current monthly surplus, 3-month buffer target will be reached in **{gp['months_to_3mo']} months**.")
        else:
            st.warning("Customer is in deficit spending. Surplus must be positive to fund savings.")

    with gprog2:
        pct_6mo = min(1.0, max(0.0, customer["B"] / gp["target_6mo"])) if gp["target_6mo"] > 0 else 1.0
        st.markdown(f"**6-Month Emergency Buffer:** `{pct_6mo*100:.0f}% funded` (Needed: `${gp['needed_for_6mo']:,.2f}`)")
        st.progress(pct_6mo)
        if gp.get("months_to_6mo") is not None:
            if gp["months_to_6mo"] == 0:
                st.success("🎉 Target 6-month buffer is already fully funded!")
            else:
                st.info(f"⏳ At current monthly surplus, 6-month buffer target will be reached in **{gp['months_to_6mo']} months**.")

    st.markdown(f"**Action Recommendation:** {gp['recommendation']}")

    st.markdown("---")

    # -------------------------------------------------------------
    # SECTION B: REQUIRED PLAN 2 — THE BACKUP PLAN (ACTIVE SHOCK RESPONSE)
    # -------------------------------------------------------------
    st.markdown("### 🛡️ Plan 2: Backup Plan (Active Shock Response)")
    st.caption("Fulfills official requirement: month-by-month trajectory and customer-confirmed triage steps.")

    confirmed_cut = st.select_slider(
        "Customer-Confirmed Discretionary Cut:",
        options=[0.0, 0.25, 0.50, 0.75],
        value=0.50,
        format_func=lambda x: f"{int(x*100)}% Cut (Saves ${x*bp['discretionary_pool']:,.2f}/mo)",
        key="confirmed_cut_slider",
        help="The customer explicitly reviews non-essential debits and confirms what portion to cut during the crisis.",
    )

    # Re-evaluate backup plan with customer's confirmed cut
    official_plans = engine.make_plan(customer, shock=shock, confirmed_cut_pct=confirmed_cut)
    bp = official_plans["backup_plan"]

    b_metric1, b_metric2, b_metric3 = st.columns(3)
    with b_metric1:
        st.metric("Active Shock Runway", f"{bp['unprotected_runway']} months")
    with b_metric2:
        st.metric("Monthly Cash Gap", f"${bp['monthly_cash_gap']:,.2f}/mo")
    with b_metric3:
        if bp["exhaustion_month"] == 0:
            makes_it_label = "❌ NO (Month 0 Overdraft)"
        elif bp["makes_it_to_month_6"]:
            makes_it_label = "✅ YES (Through Month 6)"
        else:
            makes_it_label = f"❌ NO (Month {bp['exhaustion_month']})"
        st.metric("Makes it to Month 6?", makes_it_label)

    # 6-Month Month-by-Month Trajectory Table
    st.markdown("#### 📅 Trajectory Under Active Shock:")
    traj_table = pd.DataFrame(bp["six_month_schedule"]).rename(
        columns={
            "month": "Month",
            "start_balance": "Start Balance ($)",
            "income": "Money In ($)",
            "spending": "Money Out ($)",
            "net_shortfall": "Net Deficit ($)",
            "end_balance": "Ending Balance ($)",
        }
    )
    st.dataframe(traj_table.set_index("Month"), use_container_width=True)

    # Callout on Month 6 Verdict
    if bp["exhaustion_month"] == 0:
        st.error(
            f"🚨 **Verdict:** Immediate Overdraft at Month 0. Initial savings buffer (${customer['B']:,.2f}) is insufficient to cover the one-off repair (${shock['one_off_costs']:,.2f}) by **${abs(bp['initial_buffer_left']):,.2f}**."
        )
    elif bp["makes_it_to_month_6"]:
        st.success(
            f"🎉 **Verdict:** This customer **makes it through the 6-month shock period** with a projected balance of **${bp['month_6_balance']:,.2f}** remaining at Month 6."
        )
    else:
        st.error(
            f"🚨 **Verdict:** Buffer exhausts in **Month {bp['exhaustion_month']}**. Customer ends Month 6 at a deficit of **${bp['month_6_balance']:,.2f}** without intervention."
        )

    # Customer-Confirmed Action Checklist
    st.markdown("#### 📋 Customer-Confirmed Action Steps:")
    for act in bp["actions"]:
        st.markdown(f"- {act}")

    st.info(
        "💡 **Critical Assumption Check for Judges:** Monthly summaries hide day-by-day cash timing crunches. "
        "Does this plan survive if the biller refuses to move a payment date? "
        "👉 **Head to Tab 4: 🛡️ Survive a 'No'** to simulate daily cash timing, test biller approvals, and view live Gemini advisory!"
    )

    st.markdown("---")

    # -------------------------------------------------------------
    # SECTION C: EXTENDED TANGERINE WEALTH & PROTECTION SUITE
    # -------------------------------------------------------------
    st.markdown("### 🚀 Extended Suite: Wealth Waterfall & Underwritten Protection")
    st.caption("Optional product enhancements: expense trimming, calibrated insurance shields, and down payment milestones.")

    # 1. Lean Budget Breakdown
    st.markdown("#### ✂️ 1. Lean Budget Analysis (Pruning Discretionary Waste)")
    lb_col1, lb_col2, lb_col3 = st.columns(3)
    with lb_col1:
        st.metric("Standard Spending (S)", f"${lean_budget['standard_spending']:,.2f}/mo")
    with lb_col2:
        st.metric(
            f"Lean Spending ({lean_trim_slider*100:.0f}% Trim)",
            f"${lean_budget['lean_spending']:,.2f}/mo",
            delta=f"-${lean_budget['monthly_savings_unlocked']:,.2f}/mo unlocked",
        )
    with lb_col3:
        st.metric(
            "Lean 3-Mo Emergency Target",
            f"${lean_budget['target_3mo_lean']:,.2f}",
            delta=f"-${lean_budget['target_reduction']:,.2f} target saved",
        )

    st.caption(
        f"Essential variable floor: ${customer['S'] - lean_budget['discretionary_pool']:,.2f}/mo (groceries & basic transit). "
        f"Trimmable discretionary pool: ${lean_budget['discretionary_pool']:,.2f}/mo."
    )

    # 2. Insurance Shield Selector (DEFAULTS TO NONE)
    st.markdown("#### 🛡️ 2. Underwritten Protection Options (Optional)")
    plan_options_list = ["none"]
    plan_labels = {"none": "None (Unprotected Baseline)"}

    for key, plan in insurance_plans.items():
        if plan.get("eligible"):
            plan_options_list.append(key)
            plan_labels[key] = f"{plan['name']} — ${plan['monthly_premium']:,.2f}/month"

    selected_plan_key = st.radio(
        "Select Insurance Policy to Simulate:",
        options=plan_options_list,
        format_func=lambda k: plan_labels[k],
        index=0,  # CRITICAL: Default to None (Unprotected Baseline)
        horizontal=False,
        key="insurance_selector_radio",
    )

    if selected_plan_key != "none":
        active_plan = insurance_plans[selected_plan_key]
        st.info(
            f"**{active_plan['name']}** (${active_plan['monthly_premium']:,.2f}/mo)\n\n"
            f"*{active_plan['description']}*\n\n"
            + "\n".join([f"• {b}" for b in active_plan["benefits"]])
        )
        current_premium = active_plan["monthly_premium"]
    else:
        st.caption("No insurance policy active. Simulating unprotected baseline.")
        current_premium = 0.0

    # 3. Wealth Waterfall & Down Payment
    st.markdown("#### 🌊 3. Wealth Waterfall & Real Estate Milestone")
    waterfall = engine.calculate_wealth_waterfall(
        customer,
        lean_budget=lean_budget,
        insurance_premium=current_premium,
        downpayment_target=downpayment_goal,
    )

    w_col1, w_col2, w_col3 = st.columns(3)
    with w_col1:
        st.metric("Net Monthly Surplus", f"${waterfall['net_surplus']:,.2f}")
    with w_col2:
        st.metric("To Index ETFs (Mo.)", f"${waterfall['alloc_investments']:,.2f}")
    with w_col3:
        st.metric("To Down Payment (Mo.)", f"${waterfall['alloc_downpayment']:,.2f}")

    if waterfall["months_to_downpayment"]:
        st.success(
            f"🏡 At current savings flow, customer reaches **${downpayment_goal:,.0f} down payment in {waterfall['months_to_downpayment']} months**!"
        )

    # 4. Rescued Shock Simulation (Uses Sidebar Trim Slider & Capped Benefits)
    st.markdown("#### ⚡ 4. Live Plan Impact on Shock Runway")
    rescue_sim = engine.simulate_resilience_rescue(
        customer,
        shock_inputs={
            "income_multiplier": income_mult,
            "bills_increase_pct": bills_increase,
            "one_off_costs": repair_cost,
        },
        selected_plan_key=selected_plan_key if selected_plan_key != "none" else None,
        use_lean_budget=True,
        trim_pct=lean_trim_slider,
    )

    rcol1, rcol2 = st.columns(2)
    with rcol1:
        st.markdown("**❌ Unprotected Shock:**")
        st.markdown(f"• Shortfall: `${rescue_sim['baseline_gap']:,.2f}/mo`")
        st.markdown(f"• Remaining Buffer: `${rescue_sim['baseline_buffer_left']:,.2f}`")
        b_rw = rescue_sim["baseline_runway"]
        st.markdown(f"• Runway: `{b_rw}` months")

    with rcol2:
        st.markdown("**🛡️ With Lean Budget & Selected Protection:**")
        st.markdown(f"• Shortfall: `${rescue_sim['rescued_gap']:,.2f}/mo`")
        st.markdown(f"• Remaining Buffer: `${rescue_sim['rescued_buffer_left']:,.2f}`")
        r_rw = rescue_sim["rescued_runway"]
        st.markdown(f"• Rescued Runway: `{r_rw}` months")


# ==========================================
# PART 4: SURVIVE A "NO" (DAILY REPLAY & GEMINI ADVISOR)
# ==========================================
with tab4:
    st.subheader(f"🛡️ Interactive Resilience Engine: Surviving a 'No' (Account #{account_id})")
    st.write(
        "A plan is only as good as the assumptions that hold. When a shock hits, customers face cash timing crunches "
        "before month-ends. Here, judges can test real-world dependencies: What if the biller refuses to move the payment date? "
        "What if lifestyle cuts are rejected? The engine recalculates what is still possible."
    )

    # 1. The Pitch Discovery: Macro 131-Account Replay
    with st.expander("💡 The Pitch Discovery: 131 Accounts Trapped in Intra-Month Deficits (July–Dec 2025 Replay)", expanded=False):
        disc = ds.get_macro_discovery_data()
        st.markdown(
            """
            **The Discovery Pitch Angle:** In our day-by-day replay across all **4,500 accounts** in July–December 2025 under simulated shock:
            - **131 accounts** went negative *between month-ends* despite clearing every monthly close with a positive balance.
            - **103 accounts** had a regular monthly household bill preceding their regular income deposit.
            - **43 of those 103 (41.7%)** were **completely rescued from overdraft** purely by shifting the household bill 7 days.
            - **$0.00 Net Savings Impact:** Shifting the bill required zero additional dollars, merely synchronizing cash outflows with inflows.
            - **The Crucial Catch:** Bill-date changes strictly require biller approval. When the biller says **NO**, the engine must adapt.
            """
        )
        dcol1, dcol2, dcol3, dcol4 = st.columns(4)
        with dcol1:
            st.metric("Intra-Month Timing Overdrafts", f"{disc['intra_month_overdrafts']} accounts")
        with dcol2:
            st.metric("Eligible Household Bills", f"{disc['accounts_with_movable_bill']} accounts")
        with dcol3:
            st.metric("Rescued 100% by Timing", f"{disc['overdrafts_resolved_by_shift']} accounts", delta="41.7% of eligible")
        with dcol4:
            st.metric("Month-End Balance Impact", "$0.00", delta="Zero External Capital")

        # Distribution breakdown table
        dist_df = pd.DataFrame(disc["distribution"])
        st.dataframe(dist_df.set_index("Category"), use_container_width=True)

    # 2. Demo Anchor Callout Banner
    if account_id == 22812:
        st.success(
            "🎯 **Prime Demo Anchor Active: Account #22812 (High Spend + Timing Mismatch)**\n\n"
            "• **Regular Inflow:** Paycheck deposit hits on the **12th** of each month (~$14,271).\n\n"
            "• **Household Bill:** Fixed bill debited on the **7th** ($2,350.32) — **5 days BEFORE the deposit arrives!**\n\n"
            "• **The Action Verdict:** Shifting this bill 7 days (to the 14th) **buys 27 days of breathing room** (delays overdraft from Nov 7 to Dec 4), "
            "but honestly still leaves **$5,698 in starting cash required** over 6 months."
        )
    else:
        st.info("💡 **Tip for Judges:** Click `22812 (High Spend)` in the sidebar quick picks to test the primary bill-timing demo case!")

    # 3. Daily Simulation Computation
    is_shift_approved = (
        st.session_state.get("biller_approved") is True
        and "move_recurring_bill" not in st.session_state.get("denied_actions", [])
    )
    shift_days = 7 if is_shift_approved else 0
    active_cut_pct = st.session_state.get("confirmed_spending_cut", 0.0)

    # Run baseline simulation (unshifted, unmitigated)
    baseline_sim = ds.simulate_daily_cashflow(
        account_id=account_id,
        initial_balance=customer["B"],
        income_multiplier=income_mult,
        bills_increase_pct=bills_increase,
        one_off_costs=repair_cost,
        shift_bill_days=0,
        bill_shift_approved=False,
        spending_cut_pct=0.0,
    )

    # Run active simulation (with approved actions)
    active_sim = ds.simulate_daily_cashflow(
        account_id=account_id,
        initial_balance=customer["B"],
        income_multiplier=income_mult,
        bills_increase_pct=bills_increase,
        one_off_costs=repair_cost,
        shift_bill_days=shift_days,
        bill_shift_approved=is_shift_approved,
        spending_cut_pct=active_cut_pct,
    )

    has_bill = customer["H"] > 0
    has_repair = repair_cost > 0

    # 4. Consult Gemini Advisor / Deterministic Rules
    effective_api_key = st.session_state.get("gemini_api_key_input") or os.environ.get("GEMINI_API_KEY")
    advisor_res = ga.consult_gemini_advisor(
        shock_type=f"Income x{income_mult:.2f}, Bills +{bills_increase*100:.0f}%, Repair ${repair_cost:,.0f}",
        days_to_shortfall=baseline_sim["days_to_shortfall"],
        cash_needed=active_sim["extra_cash_needed"],
        has_bill_to_shift=has_bill,
        has_one_off=has_repair,
        denied_action_ids=st.session_state.get("denied_actions", []),
        confirmed_action_ids=st.session_state.get("confirmed_actions", []),
        api_key=effective_api_key,
    )
    plan = advisor_res["plan"]

    # 5. Advisor Question & Interactive "Survive a NO" Card
    st.markdown("### 🤖 Resilience Advisor Action Card")

    # Status badge
    if advisor_res.get("is_ai_live"):
        st.caption("🟢 **AI Engine Status:** Active — Reasoning with **Gemini 2.5 Flash** (Zero-PII Isolation)")
    else:
        st.caption("⚡ **Engine Status:** Active — Running **Deterministic Resilience Engine** (Zero-Fail Offline Mode)")

    st.markdown(
        f"""
        <div style="background-color: #FFF9F5; border: 2px solid #F37021; border-radius: 12px; padding: 20px; margin-bottom: 20px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                <span style="background-color: #F37021; color: white; padding: 4px 12px; border-radius: 12px; font-weight: bold; font-size: 0.85rem;">
                    ACTION: {plan['primary_action_id'].upper().replace('_', ' ')}
                </span>
                <span style="color: #666; font-size: 0.9rem;">
                    <b>Approval Required:</b> {plan['approval_entity']}
                </span>
            </div>
            <h3 style="margin-top: 5px; color: #2D3748;">💬 Interactive Confirmation Question:</h3>
            <p style="font-size: 1.15rem; font-weight: 600; color: #1A202C;">"{plan['confirmation_question']}"</p>
            <p style="color: #4A5568; margin-bottom: 8px;"><b>Advisor Rationale:</b> {plan['rationale']}</p>
            <p style="color: #718096; font-size: 0.9rem;"><b>Fallback if Rejected by Judge:</b> {plan['fallback_preview']}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Interactive Response Buttons
    btn_col1, btn_col2, btn_col3 = st.columns([2, 2, 1])

    with btn_col1:
        if plan["primary_action_id"] == "move_recurring_bill":
            st.button(
                "✅ YES — Biller Approved (Shift Bill 7 Days)",
                on_click=approve_biller_shift,
                use_container_width=True,
                type="primary",
            )
        elif plan["primary_action_id"] == "reduce_confirmed_spending":
            st.button(
                "✅ YES — Confirm 30% Spending Cut",
                on_click=lambda: set_confirmed_cut(0.30),
                use_container_width=True,
                type="primary",
            )
        else:
            st.button(
                "✅ YES — Confirm Action",
                on_click=lambda: confirm_generic_action(plan["primary_action_id"]),
                use_container_width=True,
                type="primary",
            )

    with btn_col2:
        if plan["primary_action_id"] == "move_recurring_bill":
            st.button(
                "❌ NO — Biller Denied (Payment Immovable)",
                on_click=deny_biller_shift,
                use_container_width=True,
            )
        elif plan["primary_action_id"] == "reduce_confirmed_spending":
            st.button(
                "❌ NO — Spending Cuts Are Off-Limits",
                on_click=lambda: deny_generic_action("reduce_confirmed_spending"),
                use_container_width=True,
            )
        else:
            st.button(
                "❌ NO — Action Unavailable",
                on_click=lambda: deny_generic_action(plan["primary_action_id"]),
                use_container_width=True,
            )

    with btn_col3:
        st.button("🔄 Reset Plan", on_click=reset_playbook, use_container_width=True)

    # Feedback message based on user interaction
    if st.session_state.get("biller_approved") is True:
        st.success(
            "🎉 **Action Applied:** Biller confirmed 7-day payment date shift (Nov 7 ➔ Nov 14). Daily trajectory updated!"
        )
    elif st.session_state.get("biller_approved") is False:
        st.warning(
            "🚨 **Action Blocked:** Biller refused schedule change. The engine struck `move_recurring_bill` and recalculated alternative actions!"
        )

    if active_cut_pct > 0:
        st.info(f"✂️ **Confirmed Spending Cut:** {active_cut_pct*100:.0f}% discretionary cut active in simulation.")

    st.markdown("---")

    # 6. Real-Time Comparative Metrics
    st.markdown("### 📊 Day-by-Day Impact Comparison")
    met1, met2, met3, met4 = st.columns(4)

    with met1:
        base_sf = baseline_sim["first_shortfall_date"]
        st.metric(
            "Baseline First Shortfall",
            base_sf if base_sf else "None (Solvent)",
            help="Date balance first drops below zero without intervention.",
        )

    with met2:
        act_sf = active_sim["first_shortfall_date"]
        days_gained = (
            (pd.to_datetime(act_sf) - pd.to_datetime(base_sf)).days
            if base_sf and act_sf
            else (180 if base_sf and not act_sf else 0)
        )
        st.metric(
            "Action First Shortfall",
            act_sf if act_sf else "None (Solvent)",
            delta=f"+{days_gained} Days Gained" if days_gained > 0 else None,
        )

    with met3:
        st.metric(
            "Extra Starting Cash Needed",
            f"${active_sim['extra_cash_needed']:,.2f}",
            delta=f"-${baseline_sim['extra_cash_needed'] - active_sim['extra_cash_needed']:,.2f} Saved"
            if active_sim["extra_cash_needed"] < baseline_sim["extra_cash_needed"]
            else None,
            help="Peak deficit: exact dollar amount of external cash required to prevent any overdraft.",
        )

    with met4:
        st.metric(
            "Projected Dec 31 Balance",
            f"${active_sim['end_balance']:,.2f}",
            delta=f"${active_sim['end_balance'] - baseline_sim['end_balance']:+,.2f}",
        )

    # 7. Plotly Interactive Trajectory Chart
    st.markdown("#### 📈 Daily Cash Balance Trajectory (July 1 – Dec 31, 2025)")

    df_base = pd.DataFrame(baseline_sim["timeline"])
    df_act = pd.DataFrame(active_sim["timeline"])

    fig = go.Figure()

    # Zero Line
    fig.add_hline(y=0, line_dash="dash", line_color="#C5221F", annotation_text="Overdraft Threshold ($0)")

    # Baseline Line
    fig.add_trace(
        go.Scatter(
            x=df_base["date"],
            y=df_base["balance"],
            mode="lines",
            name="Unprotected Baseline",
            line=dict(color="#C5221F", width=2, dash="dash"),
            hovertemplate="<b>Date:</b> %{x}<br><b>Baseline:</b> $%{y:,.2f}<extra></extra>",
        )
    )

    # Active Action Line
    fig.add_trace(
        go.Scatter(
            x=df_act["date"],
            y=df_act["balance"],
            mode="lines+markers",
            name="With Confirmed Actions",
            line=dict(color="#137333" if active_sim["extra_cash_needed"] == 0 else "#F37021", width=3),
            marker=dict(size=4),
            hovertemplate="<b>Date:</b> %{x}<br><b>Action Balance:</b> $%{y:,.2f}<extra></extra>",
        )
    )

    fig.update_layout(
        xaxis_title="Date",
        yaxis_title="Account Balance ($CAD)",
        margin=dict(l=20, r=20, t=30, b=20),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        height=400,
    )

    st.plotly_chart(fig, use_container_width=True)

    # 8. Detailed Daily Event Ledger (Expandable)
    with st.expander("🔍 View Detailed Daily Event Ledger", expanded=False):
        ledger_df = df_act[["date", "description", "delta", "balance"]].rename(
            columns={
                "date": "Date",
                "description": "Cash Flow Event",
                "delta": "Net Amount ($)",
                "balance": "Ending Daily Balance ($)",
            }
        )
        st.dataframe(ledger_df, use_container_width=True)


# ==========================================
# PART 5: LIVE ETF & MARKET INTELLIGENCE
# ==========================================
with tab5:
    st.subheader("📊 Live Index Funds & ETF Market Intelligence")
    st.write(
        "Powered by real-time market data from the **Yahoo Finance API**. Tracks leading Canadian and global index ETFs, compares historical performance, and delivers algorithmic asset-allocation advice."
    )

    # 0. Live Any-Ticker Explorer (Real-Time API Search)
    st.markdown("### 🔍 Live Ticker Explorer (Any Global ETF or Stock)")
    st.write(
        "Search any ticker symbol live across the **Toronto Stock Exchange (TSX)**, **NYSE**, or **NASDAQ** (e.g. `VFV.TO`, `XEQT.TO`, `SPY`, `QQQ`, `TD.TO`, `BNS.TO`, `ENB.TO`, `CASH.TO`):"
    )

    t_search_col1, t_search_col2, t_search_col3 = st.columns([3, 1, 1])
    with t_search_col1:
        custom_ticker = st.text_input(
            "Enter Stock or ETF Ticker Symbol:",
            value="VFV.TO",
            help="Canadian stocks end with .TO (e.g. VFV.TO, XEQT.TO, TD.TO). US stocks do not (e.g. SPY, QQQ, AAPL).",
        )
    with t_search_col2:
        ticker_period = st.selectbox(
            "Chart Range:",
            options=["1mo", "6mo", "1y", "2y", "5y"],
            index=2,
            key="custom_period",
        )
    with t_search_col3:
        st.markdown("<br>", unsafe_allow_html=True)
        refresh_live = st.button("🔄 Fetch Live", use_container_width=True)

    if custom_ticker:
        with st.spinner(f"Querying live market feed for '{custom_ticker}'..."):
            ticker_data = etf_service.fetch_live_ticker_details(custom_ticker, period=ticker_period)

        if ticker_data.get("success"):
            live_col1, live_col2, live_col3, live_col4 = st.columns(4)
            with live_col1:
                st.metric(
                    label=f"{ticker_data['symbol']} Live Price ({ticker_data['currency']})",
                    value=f"${ticker_data['last_price']:.2f}",
                    delta=f"${ticker_data['day_change']:+.2f} ({ticker_data['day_change_pct']:+.2f}%)",
                )
            with live_col2:
                st.metric(
                    label=f"{ticker_period.upper()} Period Return",
                    value=f"{ticker_data['period_change_pct']:+.1f}%",
                    delta=f"Prev Close: ${ticker_data['prev_close']:.2f}" if "prev_close" in ticker_data else None,
                )
            with live_col3:
                st.metric(
                    label="Day Range (Low – High)",
                    value=f"${ticker_data['day_low']:.2f} – ${ticker_data['day_high']:.2f}",
                )
            with live_col4:
                st.metric(
                    label="52-Week Range",
                    value=f"${ticker_data['52w_low']:.2f} – ${ticker_data['52w_high']:.2f}",
                )

            st.caption(
                f"🟢 **Live Data Verified**: Exchange: **{ticker_data['exchange']}** | Currency: **{ticker_data['currency']}** | As of: **{ticker_data['as_of']}** | Volume: **{ticker_data['volume']:,} shares**"
            )

            if "chart_df" in ticker_data and not ticker_data["chart_df"].empty:
                st.line_chart(ticker_data["chart_df"])
        else:
            st.warning(
                f"⚠️ Live market data for '{custom_ticker}' is currently unavailable (network feed offline). "
                "Real-time feeds will automatically sync when network access is enabled."
            )

    st.markdown("---")

    # 1. Customer-Specific Algorithmic Recommendation
    st.markdown("### 🧠 Personalized ETF Recommendation for Account #" + str(account_id))
    rec = etf_service.recommend_etf_for_customer(
        months_to_downpayment=waterfall["months_to_downpayment"],
        emergency_funded=waterfall["emergency_complete"],
    )

    st.success(
        f"**Target Asset Recommendation: {rec['name']}** ({rec['recommended_allocation_pct']}% Allocation)\n\n"
        f"*{rec['rationale']}*"
    )

    st.markdown("---")

    # 2. Live Market Quotes & Performance Cards
    st.markdown("### 📈 Curated Market Dashboard (TSX Quotes)")
    with st.spinner("Fetching market quotes from Yahoo Finance API..."):
        etf_summaries = etf_service.get_etf_summary(period="1y")

    # Display in 5 cards with truthful N/A handling if feed fails
    any_offline = any(not item.get("is_live", False) for item in etf_summaries)
    if any_offline:
        st.caption("ℹ️ *Note: Some or all market feeds are currently offline in this environment. Values display N/A rather than fabricated numbers.*")

    card_cols = st.columns(len(etf_summaries))
    for i, item in enumerate(etf_summaries):
        with card_cols[i]:
            if item.get("is_live", False) and item["last_price"] is not None:
                price_str = f"${item['last_price']:.2f}"
                return_str = f"{item['return_pct']:+.1f}%"
                return_color = "#137333" if item["return_pct"] >= 0 else "#C5221F"
            else:
                price_str = "N/A (Offline)"
                return_str = "N/A"
                return_color = "#888888"

            st.markdown(
                f"""
                <div class="etf-card">
                    <h3 style="margin:0; color:#F37021;">{item['ticker']}</h3>
                    <p style="margin:2px 0 8px 0; font-size:0.85rem; color:#666;">{item['category']}</p>
                    <h2 style="margin:0;">{price_str}</h2>
                    <p style="margin:4px 0; color:{return_color}; font-weight:bold;">
                        1Y Return: {return_str}
                    </p>
                    <hr style="margin:8px 0;">
                    <p style="margin:2px 0; font-size:0.8rem;"><b>Yield:</b> ~{item['yield_est']}%</p>
                    <p style="margin:2px 0; font-size:0.8rem;"><b>MER:</b> {item['mer']}%</p>
                    <p style="margin:2px 0; font-size:0.8rem;"><b>Risk:</b> {item['risk_level']}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown("---")

    # 3. Interactive Historical Comparison Chart
    st.markdown("### 📉 Historical Trajectory Comparison (Base 100%)")
    st.write("Compare the normalized price action of all curated index ETFs over time:")

    time_period = st.selectbox("Select Time Horizon:", options=["6mo", "1y", "2y", "5y"], index=1)
    with st.spinner("Loading historical price series..."):
        hist_chart_df = etf_service.get_etf_historical_trends(period=time_period)

    if not hist_chart_df.empty:
        st.line_chart(hist_chart_df)
        st.caption("Normalized to 100 at the start of the period to show comparative total growth across asset classes.")
    else:
        st.info("Historical series syncing when market API connection is available.")
