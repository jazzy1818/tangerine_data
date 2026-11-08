"""Bank-facing Tangerine datathon app for account profiles and shock planning."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import daily_simulation as ds
import engine
import gemini_advisor as ga
from investment_triggers import AnalystEvidence

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
    clear_account_evidence()


def clear_account_evidence():
    st.session_state.pop('classification_result', None)
    for key in list(st.session_state):
        if key.startswith('transfer_') or key == 'tailored_explanation':
            del st.session_state[key]
    st.session_state['recovery_supplied'] = False
    st.session_state.pop('recovery_month', None)
    for key in ('recovery_cash', 'recovery_income', 'recovery_spending', 'recovery_rate'):
        st.session_state[key] = None
    st.session_state['recovery_stable'] = False
    st.session_state['recovery_covered'] = False


def set_shock_preset(inflow_multiplier, bills_change, one_off_cost, use_typical_spending=False):
    st.session_state['classification_input_mode'] = 'Current shock controls'
    st.session_state.pop('classification_result', None)
    st.session_state["slider_income_mult"] = inflow_multiplier
    st.session_state["slider_bills_increase"] = bills_change
    st.session_state["slider_repair_cost"] = one_off_cost
    st.session_state["repair_uses_typical_spending"] = use_typical_spending


def set_manual_repair_cost():
    st.session_state["repair_uses_typical_spending"] = False


def money(value):
    if value is None:
        return "Not established"
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
        on_change=clear_account_evidence,
    )

    st.markdown("---")
    st.caption("Use an account ID and the judge’s twist. Missing evidence appears as bank review flags.")
    with st.expander("Judge event context (optional)"):
        judge_event = st.text_input("Judge-supplied event description", key="judge_event")
        judge_event_effect = st.selectbox(
            "Additional financial effect of this event",
            ["Not quantified", "Explicitly no additional financial effect"],
            key="judge_event_effect",
        )
        st.caption("No dollar effect is inferred from the description. Numeric twist inputs remain separate, explicit scenario effects.")

judge_evidence = (AnalystEvidence(
    source="Judge-entered event context",
    event_description=judge_event,
    event_financial_effect="unspecified" if judge_event_effect == "Not quantified" else "none",
) if judge_event.strip() else None)

try:
    customer = engine.know_customer(account_id)
except (ValueError, FileNotFoundError) as exc:
    st.error(str(exc))
    st.stop()
if st.session_state.get("repair_uses_typical_spending", False):
    st.session_state["slider_repair_cost"] = customer["raw_S"]

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "1. Know the Customer",
    "2. Take a Shock",
    "3. Goal and Backup Plans",
    "4. Daily Replay and Advisor",
    "5. Allocation Review",
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

    # One selected structured scenario drives both classification and finance.
    from plan_classification import scenario_from_engine, ShockScenario
    from plan_classification.ui import render_classification
    handoff = render_classification(customer, income_mult, bills_increase, repair_cost, event_evidence=judge_evidence)
    if not handoff or handoff['scenario'] is None:
        st.warning('Scenario input is incomplete or invalid. The baseline remains visible, but no stale slider scenario is applied.')
        active_scenario = ShockScenario(effects=[{'type': 'unspecified_event', 'value': None, 'evidence': 'unknown'}])
        classification_selection = None
    else:
        active_scenario = handoff['scenario']
        classification_selection = handoff['selection_result']
    shock = engine.scenario_reference(customer, active_scenario)
    st.caption('Organizer formula for standard presets; other scenarios show a first-period reference only. The backup timeline applies all dates and durations.')

    st.markdown("---")
    st.markdown("#### 🚨 Official Numbers Under Shock")

    mcol1, mcol2, mcol3, mcol4, mcol5 = st.columns(5)
    with mcol1:
        st.metric(
            "Money In After Shock",
            money(shock['income_after_shock']),
            delta=None,
        )
    with mcol2:
        st.metric(
            "Spending After Shock",
            money(shock['spending_after_shock']),
            delta=None,
        )
    with mcol3:
        st.metric(
            "Historical Proxy After One-Off Cost",
            f"${shock['buffer_left']:,.2f}",
            delta=None,
        )
    with mcol4:
        st.metric(
            "Monthly Shortfall (Gap)",
            money(shock['gap']),
            delta=None,
        )
    with mcol5:
        post_rw = shock["runway"]
        if post_rw is None:
            badge_html = '<div>Not established: first-period effects are incomplete.</div>'
        elif isinstance(post_rw, (int, float)):
            if post_rw <= 3:
                badge_html = f"<div class='runway-badge-danger'>🚨 {post_rw:.1f} Months</div>"
            elif post_rw <= 6:
                badge_html = f"<div class='runway-badge-warning'>⚠️ {post_rw:.1f} Months</div>"
            else:
                badge_html = f"<div class='runway-badge-safe'>⏱️ {post_rw:.1f} Months</div>"
        else:
            badge_html = f"<div class='runway-badge-safe'>🛡️ {post_rw}</div>"
        st.markdown(f"**Official Shock Runway:**<br>{badge_html}", unsafe_allow_html=True)



with tab3:
    st.subheader(f"Goal and Backup Plans for Account {account_id}")
    recovery_snapshot = None
    with st.expander('Judge-supplied recovery checkpoint (optional)'):
        if st.checkbox('An updated recovery checkpoint is supplied', key='recovery_supplied'):
            from recovery_plan import RecoverySnapshot
            checkpoint_month = st.text_input('Checkpoint month (YYYY-MM)', value='', key='recovery_month')
            rcash = st.number_input('Accessible cash at checkpoint (CAD)', value=None, key='recovery_cash')
            rincome = st.number_input('Updated recurring inflows (CAD/month)', min_value=0., value=None, key='recovery_income')
            rspending = st.number_input('Updated recurring spending (CAD/month)', min_value=.01, value=None, key='recovery_spending')
            rrate = st.number_input('Supported rebuild contribution (CAD/month; leave blank if unknown)', min_value=0., value=None, key='recovery_rate')
            rstable = st.checkbox('Scenario explicitly establishes stable cash flow', key='recovery_stable')
            rcovered = st.checkbox('Scenario explicitly establishes coverage of upcoming obligations', key='recovery_covered')
            if None not in (rcash, rincome, rspending):
                try:
                    recovery_snapshot = RecoverySnapshot(source='Judge-supplied conditional recovery checkpoint',
                        account_id=customer['account_id'],
                        assessment_month=checkpoint_month, cash_basis='judge_specified', available_cash=rcash,
                        monthly_inflow=rincome, monthly_spending=rspending, supported_monthly_contribution=rrate,
                        stable_cash_flow=rstable, obligations_covered=rcovered)
                except ValueError as exc:
                    st.warning(str(exc))
            else:
                st.info('Recovery amounts remain unknown. Crisis calculations continue without a rebuild date.')
    from transfer_ui import render_transfers
    transfers = render_transfers(active_scenario.horizon_months)
    try:
        plans = engine.make_plan(customer, shock=engine.take_shock(customer), analyst_evidence=judge_evidence,
            scenario=active_scenario, selection_result=classification_selection, existing_transfers=transfers,
            recovery_snapshot=recovery_snapshot, include_timing_comparison=True)
    except ValueError as exc:
        st.error(f'Supplied action evidence cannot be applied: {exc}. Correct or clear the schedule. No revised advice is issued.')
        st.stop()
    crisis = plans['crisis_plan']
    if crisis['runtime_validation']['status'] != 'passed':
        st.error('Financial validation blocked this result. Review the supplied evidence before issuing advice.')
        review_flags(crisis['review_flags'])
        st.stop()
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
        column.caption(f"Gap using conservative opening estimate: {money(remaining)}")
        if target > 0:
            column.progress(min(1.0, max(0.0, goal["current_buffer"] / target)))
        if eta is not None and remaining > 0:
            column.caption(f"Illustrative time at modeled contribution: {eta:.1f} months")
    review_flags(goal["review_flags"])

    st.markdown("### Plan 2 · Backup Plan")
    st.write(f"**Lead module:** {crisis['lead_module'] or 'BANK_REVIEW'} · **Goal:** {crisis['goal_status']} · **G25:** {crisis['G25']}")
    st.caption('All financial effects are calculated, independently of the classifier’s limit of two supporting labels.')
    st.write('Affected modules: ' + (', '.join(crisis['affected_modules']) or 'None established'))
    st.caption(f"Scenario execution: {crisis['scenario_hash'][:12]} · Proposal status: {crisis['selection_status']}")
    if crisis['required_monthly_improvement'] is not None:
        st.write(f"Calculated improvement target: {money(crisis['required_monthly_improvement'])}/month, plus {money(crisis['immediate_cash_target'])} needed before monthly improvements can help.")
        st.caption('This is a funding target, not evidence that this amount can be cut from spending. No unverified cut is applied.')
    st.caption(
        "No-action projection under the selected structured scenario. The historical buffer is an opening proxy, "
        "and unverified spending reductions, outside cash, and payouts are excluded."
    )
    if not backup["funding_result_complete"]:
        st.warning("This projection covers quantified effects only. Missing or additional event/expense effects prevent a full funding conclusion; see Allocation Review for additional evidence.")
    start_col, end_col, gap_col = st.columns(3)
    start_col.metric("Opening Proxy After Immediate Cost", money(backup["initial_buffer_left"]))
    end_col.metric(f"Month {active_scenario.horizon_months} Closing Balance", money(backup["month_6_balance"]))
    gap_col.metric("Extra Starting Cash Needed", money(backup["remaining_cash_needed"]))
    shortage = backup["exhaustion_month"]
    if shortage == 0:
        st.warning("The opening cash proxy goes below zero immediately.")
    elif shortage is not None:
        st.warning(f"The first negative quantified-component checkpoint is month {shortage} ({crisis['no_action']['first_shortfall_phase']}). Actual outcomes remain unestablished when effects are unresolved.")
    else:
        st.info("The quantified cash path stays nonnegative at the modeled checkpoints. This is not a daily-solvency or complete-funding claim when effects are unresolved.")
    schedule = pd.DataFrame(backup["six_month_schedule"]).rename(columns={
        "month": "Month",
        "start_balance": "Opening balance (CAD)",
        "income": "Money in (CAD)",
        "spending": "Money out (CAD)",
        "net_shortfall": "Shortfall (CAD)",
        "end_balance": "Closing balance (CAD)",
    })
    st.dataframe(schedule.set_index("Month"), width="stretch")
    st.markdown('**Goal and supported-pause comparison**')
    st.caption('A proposed pause adds $0 to the no-action path. Reserve earmarks remain liquid. Existing outflow relief is counted only with supplied schedule, inclusion, approval and fees.')
    st.dataframe(pd.DataFrame([{
        'Path': label, 'Closing cash (quantified components)': crisis[key]['ending_cash'],
        'Extra starting cash needed (quantified components)': crisis[key]['additional_cash_needed'],
        'Full funding conclusion established': crisis[key]['funding_result_complete'],
    } for label, key in [('Before shock (no proposed transfer)', 'baseline_without_crisis'), ('No new action', 'no_action'), ('Continue proposed goal', 'continue_goal'),
                          ('Revised goal only', 'revised_goal'), ('Supported existing-transfer pause', 'supported_pause'),
                          ('Applied revised plan', 'applied_plan')]]), hide_index=True)
    from tailored_advice import explain_plan, validate_advice
    validate_advice(crisis['advice'], crisis)
    st.markdown('**Personalized action plan**')
    explanation = explain_plan(crisis)
    if st.button('Use Gemini to emphasize validated findings', key='tailored_explain'):
        st.session_state['tailored_explanation'] = explain_plan(crisis, backend='gemini')
    cached = st.session_state.get('tailored_explanation')
    if cached and cached['fingerprint'] == crisis['advice']['fingerprint']:
        explanation = cached
    st.caption('Explanation emphasis: ' + explanation['actual_backend'] +
        (' · local fallback: ' + explanation['fallback_reason'] if explanation['fallback_reason'] else ''))
    # All mandatory facts remain visible regardless of model emphasis.
    for card_id, sentence in crisis['advice']['cards'].items():
        if card_id in explanation['focus_ids']:
            st.info(sentence)
        else:
            st.write(sentence)
    if crisis['advice']['transfer_sources']:
        st.dataframe(crisis['advice']['transfer_sources'], hide_index=True)
    st.markdown('**Recovery assessment**')
    st.write(crisis['recovery']['status'])
    if crisis['recovery'].get('reserve_gap') is not None:
        st.write(f"Reserve gap: {money(crisis['recovery']['reserve_gap'])}. Supported monthly rebuild: {money(crisis['recovery']['monthly_contribution'])}.")
    st.write(f"Rebuild timeline: {crisis['recovery']['months_to_target']} months" if crisis['recovery']['months_to_target'] is not None else 'Rebuild date not established.')
    review_flags(crisis['recovery']['review_flags'])
    if crisis['timing_comparison'] is not None:
        timing = crisis['timing_comparison']
        st.markdown('**Conditional M7 historical timing comparison**')
        st.write(f"Extra starting-cash need before: {money(timing['no_action']['extra_cash_needed'])}; after: {money(timing['conditional_bill_move']['extra_cash_needed'])}.")
        st.caption(' '.join(timing['conditions']))
    st.markdown("**Analyst action notes**")
    for action in backup["actions"]:
        st.write(f"• {action}")
    review_flags(backup["review_flags"])

with tab5:
    allocation = plans["investment_plan"]
    st.subheader("Normal-goal allocation and investment readiness")
    st.caption("This tab contains normal-goal capacity and default stress diagnostics. The active structured scenario and its validated cash paths are in Goal and Backup Plans.")
    st.caption("Bank analyst decision support · conditional estimates · no ETF selection or trade")
    st.write(allocation["recommendation"])
    normal_col, selected_col, stress_col = st.columns(3)
    normal_col.metric("Normal monthly allocation (conditional)", money(allocation["normal_monthly_allocation"]))
    selected_col.metric("Selected shock monthly allocation", money(crisis["goal_contribution_revised"] if crisis["goal_before_crisis"]["kind"] == "PROPOSED_TRANSFER" else 0.))
    stress_col.metric("Monthly allocation passing all listed scenarios", money(allocation["all_scenarios_monthly_allocation"]))
    st.write(f"**Primary goal:** {allocation['primary_goal']}")
    st.write(f"**Investment suitability:** {allocation['investment_suitability']}")
    if not allocation.get("funding_result_complete", False):
        st.warning("Some supplied effects are unquantified. Paths below show only quantified components; they do not establish full funding or affordability.")
    if crisis["goal_status"] in ("PAUSED", "REDUCED"):
        st.warning("The selected shock calls for reducing or pausing optional allocations. Pausing does not guarantee the funding gap is resolved.")
    features = allocation["features"]
    if features:
        st.caption(
            f"Observed window: {features['history_start']} to {features['history_end']} "
            f"({features['history_months']} months). Opening cash basis: {features['cash_basis']}. "
            "Monthly stress projections are assumptions, not six months of future observations."
        )
        st.dataframe(pd.DataFrame([{
            "Median net flow": features["median_realized_surplus"],
            "Weakest monthly net flow": features["minimum_realized_surplus"],
            "Lower-quartile net flow": features["lower_quartile_surplus"],
            "Operating floor": features["operating_cash_floor"],
            "Illustrative reserve target": features["reserve_target"],
            "Opening cash estimate": features["opening_cash_estimate"],
            "Estimated reserve gap": features["reserve_gap"],
        }]), hide_index=True, width="stretch")
    st.markdown("**Trigger evidence**")
    st.dataframe(pd.DataFrame(allocation["triggers"]), hide_index=True, width="stretch")
    if allocation["candidate_results"]:
        st.markdown("**Candidate contribution comparison**")
        st.dataframe(pd.DataFrame(allocation["candidate_results"]), hide_index=True, width="stretch")
    for result in allocation["scenario_results"]:
        with st.expander(result["scenario"]):
            st.caption(str(result["assumptions"]))
            paths = []
            for label, key in (("No allocation", "no_allocation"), ("Continue normal amount", "continue_normal_allocation"), ("Revised amount", "revised_allocation")):
                path = result[key]
                paths.append({"Policy": label, "Monthly allocation": path["monthly_contribution"],
                              "Minimum cash": path["minimum_cash"], "Closing cash": path["ending_cash"],
                              "Required floor": path["required_cash_floor"], "Preserves floor": path["preserves_cash_floor"],
                              "Extra starting cash to avoid negative balance": path["additional_cash_needed"]})
            st.dataframe(pd.DataFrame(paths), hide_index=True, width="stretch")
            chart = pd.DataFrame({label: [point["closing_cash"] for point in result[key]["schedule"]]
                                  for label, key in (("No allocation", "no_allocation"), ("Continue normal amount", "continue_normal_allocation"), ("Revised amount", "revised_allocation"))})
            chart.index.name = "Month"
            st.line_chart(chart)
            st.dataframe(pd.DataFrame(result["revised_allocation"]["schedule"]), hide_index=True, width="stretch")
    with st.expander("Historical replay, assumptions and policy"):
        st.caption("In-sample diagnostic: the same window sizes the contribution and shows its historical effect. Not an out-of-sample backtest. Contributions are conservatively debited at the start of each observed month; their effects accumulate.")
        if allocation["historical_replay"]:
            st.dataframe(pd.DataFrame(allocation["historical_replay"]), hide_index=True, width="stretch")
        st.json(allocation["policy"])
        st.json(allocation["data_provenance"])
    review_flags(allocation["bank_review_flags"])
    st.markdown("**Reassess when**")
    for condition in allocation["next_review_conditions"]:
        st.write(f"• {condition}")

with tab4:
    from scenario_execution import organizer_inputs
    replay_controls = organizer_inputs(active_scenario)
    if replay_controls is None:
        st.info('The selected scenario needs dated effects unsupported by this historical daily replay. No old slider scenario is substituted. Use the structured backup plan; daily solvency remains unverified.')
    else:
        income_mult = replay_controls['income_multiplier']
        bills_increase = replay_controls['bills_increase_pct']
        repair_cost = replay_controls['one_off_costs']
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
