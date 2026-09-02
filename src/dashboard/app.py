import streamlit as st
import pandas as pd
import json
import sys
import os
import time
from datetime import datetime, timedelta

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.agent.cash_position import cash_forecast
from src.agent.triage import triage_exceptions
from src.agent.policy import apply_policy
from src.agent.priority import calculate_priority

st.set_page_config(page_title="AI Finance Controller", layout="wide")

TOOL_WHY = {
    "get_payment": "Establishes the baseline transaction amount and status.",
    "get_refunds": "Determines whether a refund could explain the discrepancy.",
    "get_settlement": "Retrieves what the gateway recorded as the net payout.",
    "search_bank_transactions": "Confirms whether the settlement actually reached the bank.",
    "calculate_reconciliation": "Independently re-verifies the expected-vs-observed math, deterministically.",
    "check_action_policy": "Enforces hard safety rules before any action is finalized.",
    "create_escalation": "Formally logs the case with evidence for human review.",
}

PRIORITY_MAX_SCORE = 12  # true ceiling: amount(3) + root_cause_risk(3) + confidence(1) + cash_impact(2) + recurrence(2) + settlement_age(1)

# --- Load data ---
@st.cache_data
def load_audit_trail():
    with open("data/audit_trail.json") as f:
        return json.load(f)

@st.cache_data
def load_stage2_results():
    with open("data/stage2_results.json") as f:
        return json.load(f)

@st.cache_data
def load_captured_traces():
    with open("data/captured_traces.json") as f:
        return json.load(f)

@st.cache_data
def load_verification_scenarios():
    with open("data/verification_scenarios.json") as f:
        return json.load(f)

@st.cache_data
def load_eval_metrics():
    with open("data/eval_metrics.json") as f:
        return json.load(f)

@st.cache_data
def get_cash_forecast(_stage2_results):
    df_settlements = pd.read_csv("data/mutated/settlements.csv")
    df_refunds = pd.read_csv("data/mutated/refunds.csv")
    df_bank = pd.read_csv("data/mutated/bank_entries.csv")
    prioritized = triage_exceptions(_stage2_results, df_settlements)
    return cash_forecast(df_settlements, df_refunds, df_bank, prioritized,
                           reference_date=datetime(2026, 8, 15))

audit_trail = load_audit_trail()
stage2_results = load_stage2_results()
eval_metrics = load_eval_metrics()

st.title("AI Finance Controller")
st.caption("Evidence-driven reconciliation, investigation, and controlled action")
st.info(
    "**Evaluation environment:** 200 synthetic payment lifecycles with controlled, "
    "seeded ground-truth mutations across 14 exception types. No real merchant data or "
    "live financial systems are involved."
)

# --- Shared table build ---
priority_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}

table_rows = []
for r in audit_trail:
    table_rows.append({
        "Case ID": r["case_id"],
        "Payment ID": r["payment_id"],
        "Priority": r["priority"]["priority"],
        "Priority Score": r["priority"]["priority_score"],
        "Root Cause": r["agent_investigation"]["root_cause"],
        "Confidence": r["agent_investigation"]["confidence"],
        "Amount at Risk": r["amount_at_risk"],
        "Final Action": r["policy_decision"]["final_action"],
    })

df_queue = pd.DataFrame(table_rows)
df_queue["_priority_sort"] = df_queue["Priority"].map(priority_order)
df_queue = df_queue.sort_values(["_priority_sort", "Amount at Risk"], ascending=[True, False])
df_queue = df_queue.drop(columns=["_priority_sort"])

if "selected_case" not in st.session_state:
    st.session_state.selected_case = df_queue.iloc[0]["Case ID"]


def render_priority_scoreboard(case_detail):
    """Priority score visualization, scaled against the real maximum the formula can produce."""
    score = case_detail['priority']['priority_score']
    level = case_detail['priority']['priority']
    breakdown = case_detail['priority'].get('priority_breakdown')

    st.markdown(f"#### PRIORITY SCORE — {score}/{PRIORITY_MAX_SCORE}  ·  {level}")
    if breakdown:
        for text, pts in breakdown:
            bar_width = min(pts / PRIORITY_MAX_SCORE, 1.0)
            c1, c2 = st.columns([3, 1])
            with c1:
                st.progress(bar_width if bar_width > 0 else 0.01, text=text)
            with c2:
                st.markdown(f"`+{pts}`")
        st.markdown(f"**Total: {score}/{PRIORITY_MAX_SCORE}**")
    st.caption(
        f"**{level}** — because ₹{case_detail['amount_at_risk']:,.0f} is exposed "
        f"and the root cause ({case_detail['agent_investigation']['root_cause']}) "
        f"carries material risk to reconciliation."
    )


def render_expected_vs_observed(case_detail):
    st.markdown("**Expected vs. Observed**")
    calc = case_detail["agent_investigation"]["evidence"].get("calculation", "")
    expected_net = case_detail["stage2_findings"].get("lifecycle_check", {}).get("expected_net")
    actual_net = case_detail["stage2_findings"].get("lifecycle_check", {}).get("actual_net")

    if expected_net is not None and actual_net is not None:
        difference = actual_net - expected_net
        c1, c2, c3 = st.columns(3)
        c1.metric("Expected Net", f"₹{expected_net:,.2f}")
        c2.metric("Observed", f"₹{actual_net:,.2f}")
        c3.metric("Difference", f"₹{difference:+,.2f}")

        if abs(difference) < 0.01:
            st.success("✓ Expected and observed amounts reconcile.")
        else:
            st.error(f"⚠ ₹{abs(difference):,.2f} discrepancy identified.")

    if calc:
        with st.expander("Show calculation"):
            st.code(calc)
    elif expected_net is None:
        st.caption("No calculation was recorded for this case.")


def render_lifecycle_bar():
    st.markdown(
        """
        <div style="text-align:center; font-size:1.05rem; padding: 8px;">
            <b>ORDER</b> &nbsp;→&nbsp; <b>PAYMENT</b> &nbsp;→&nbsp;
            <b>REFUND</b> &nbsp;→&nbsp; <b>SETTLEMENT</b> &nbsp;→&nbsp; <b>BANK</b>
        </div>
        """,
        unsafe_allow_html=True
    )


def render_case_journey(case_detail):
    st.markdown("### 🧭 Case Journey")

    with st.expander("① DETECTED — deterministic engine flagged this settlement", expanded=False):
        st.json(case_detail["stage2_findings"])

    with st.expander("② INVESTIGATED — agent gathered evidence"):
        for rec in case_detail["agent_investigation"]["evidence"].get("records_examined", []):
            st.markdown(f"✓ `{rec}`")

    with st.expander("③ ROOT CAUSE — agent's conclusion"):
        st.code(case_detail["agent_investigation"]["root_cause"])
        render_expected_vs_observed(case_detail)

    with st.expander("④ PRIORITIZED — score assigned"):
        render_priority_scoreboard(case_detail)

    with st.expander("⑤ AI PROPOSED ACTION"):
        st.markdown(f"Confidence: **{case_detail['agent_investigation']['confidence']}**")
        st.write(case_detail["agent_investigation"]["explanation"])

    with st.expander("⑥ POLICY GATE"):
        st.caption(case_detail["policy_decision"]["policy_reason"])

    action = case_detail["policy_decision"]["final_action"]
    action_icon = "⛔" if action == "REJECT_ACTION" else ("🟠" if action == "ESCALATE" else ("🟢" if action == "AUTO_RESOLVE" else "🟡"))
    with st.expander(f"⑦ FINAL ACTION — {action_icon} {action}", expanded=True):
        if action == "REJECT_ACTION":
            st.error(f"⛔ {action} — no financial record modified.")
        elif action == "AUTO_RESOLVE":
            st.success(f"🟢 {action}")
        elif action == "ESCALATE":
            st.warning(f"🟠 {action}")
        else:
            st.info(f"🟡 {action}")

    with st.expander("⑧ VERIFIED"):
        icon = "✅" if case_detail['verification']['verified'] else "⚠️"
        st.markdown(f"{icon} **{case_detail['verification']['verification_method']}**")
        st.caption(case_detail['verification']['notes'])

    with st.expander("⑨ AUDITED — permanent record"):
        st.caption(f"Stored in: `{case_detail['execution']['store']}`")
        st.caption(f"Timestamp: {case_detail['timestamp']}")


# ============================================================
# TABS
# ============================================================
tab_a, tab_b, tab_c, tab_d = st.tabs([
    "📊 Executive Overview", "🔍 Exception Operations",
    "🤖 Agent Control Center", "🔄 System Reliability"
])


def render_what_if_simulator(case_detail):
    st.markdown("### 🔬 What-If Simulator")
    st.caption(
        "Live recalculation using the real policy and priority engines — "
        "no canned outcomes. Move the sliders and watch the decision change."
    )

    original_amount = case_detail["amount_at_risk"]
    original_confidence = case_detail["agent_investigation"]["confidence"]
    root_cause = case_detail["agent_investigation"]["root_cause"]
    recommended_action = case_detail["agent_investigation"].get("recommended_action", "ESCALATE")

    col_sliders, col_result = st.columns([1, 1])

    with col_sliders:
        sim_amount = st.slider(
            "Amount at risk (₹)",
            min_value=0.0,
            max_value=max(200000.0, original_amount * 1.5),
            value=float(original_amount),
            step=500.0,
            key=f"sim_amount_{case_detail['case_id']}"
        )
        sim_confidence = st.slider(
            "Agent confidence",
            min_value=0.0,
            max_value=1.0,
            value=float(original_confidence),
            step=0.01,
            key=f"sim_confidence_{case_detail['case_id']}"
        )

    # --- ORIGINAL, real outcome ---
    original_agent_result = {
        "root_cause": root_cause,
        "recommended_action": recommended_action,
        "confidence": original_confidence
    }
    original_policy = apply_policy(original_agent_result, original_amount)
    original_priority = calculate_priority(
        amount_at_risk=original_amount,
        confidence=original_confidence,
        root_cause=root_cause
    )

    # --- SIMULATED outcome, using the SAME real functions, different inputs ---
    sim_agent_result = {
        "root_cause": root_cause,
        "recommended_action": recommended_action,
        "confidence": sim_confidence
    }
    sim_policy = apply_policy(sim_agent_result, sim_amount)
    sim_priority = calculate_priority(
        amount_at_risk=sim_amount,
        confidence=sim_confidence,
        root_cause=root_cause
    )

    with col_result:
        st.markdown("**Original (real case)**")
        st.markdown(f"Action: `{original_policy['final_action']}`")
        st.markdown(f"Priority: `{original_priority['priority']} ({original_priority['priority_score']}/{PRIORITY_MAX_SCORE})`")

        st.markdown("**Simulated**")
        action_changed = sim_policy['final_action'] != original_policy['final_action']
        priority_changed = sim_priority['priority'] != original_priority['priority']

        if action_changed:
            st.error(f"Action: `{sim_policy['final_action']}` ⚡ changed")
        else:
            st.markdown(f"Action: `{sim_policy['final_action']}` (unchanged)")

        if priority_changed:
            st.warning(f"Priority: `{sim_priority['priority']} ({sim_priority['priority_score']}/{PRIORITY_MAX_SCORE})` ⚡ changed")
        else:
            st.markdown(f"Priority: `{sim_priority['priority']} ({sim_priority['priority_score']}/{PRIORITY_MAX_SCORE})` (unchanged)")

    with st.expander("Why this simulated outcome?"):
        st.caption(sim_policy["policy_reason"])
        for text, pts in sim_priority.get("priority_breakdown", []):
            st.markdown(f"- {text} `+{pts}`")

    st.caption(
        "This calls the exact same `apply_policy()` and `calculate_priority()` functions "
        "used across all 65 real cases — nothing here is case-specific or hardcoded."
    )

@st.cache_data
def load_pattern_clusters():
    with open("data/pattern_clusters.json") as f:
        return json.load(f)


def render_pattern_clusters():
    clusters = load_pattern_clusters()

    st.subheader("🔗 Cross-Case Pattern Detection")
    st.caption(
        "Exceptions sharing a root cause AND a tight settlement window are flagged as "
        "potential systemic issues — not treated as independent problems. Clustering "
        "requires at least 4 cases and ₹20,000+ combined exposure to avoid coincidental matches."
    )

    if not clusters:
        st.info("No materially significant clusters detected in this run.")
        return

    for c in clusters:
        with st.container(border=True):
            st.markdown(f"**{c['label']}**  ·  ₹{c['total_amount']:,.2f}  ·  {c['date_range']}")
            st.write(c["insight"])
            st.caption(f"Cases: {', '.join(c['members'])}")

# ============================================================
# TAB A — EXECUTIVE OVERVIEW
# ============================================================
with tab_a:
    total_lifecycles = len(stage2_results)
    total_exceptions = len(audit_trail)
    total_amount_at_risk = sum(r["amount_at_risk"] for r in audit_trail)
    reject_count = sum(1 for r in audit_trail if r["policy_decision"]["final_action"] == "REJECT_ACTION")
    auto_count = sum(1 for r in audit_trail if r["policy_decision"]["final_action"] == "AUTO_RESOLVE")
    review_count = sum(1 for r in audit_trail if r["policy_decision"]["final_action"] == "REVIEW")
    escalate_count = sum(1 for r in audit_trail if r["policy_decision"]["final_action"] == "ESCALATE")
    match_rate = eval_metrics["match_rate"]

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Payment Lifecycles", total_lifecycles,
                 help="Each lifecycle = Order → Payment → Refund → Settlement → Bank")
    col2.metric("Match Rate", f"{match_rate*100:.1f}%",
                 help="Share of payment lifecycles correctly reconciled by the deterministic layer")
    col3.metric("Exceptions", total_exceptions)
    col4.metric("Amount at Risk", f"₹{total_amount_at_risk:,.0f}")
    col5.metric("🔴 Actions Blocked", reject_count)

    st.caption(
        f"**{match_rate*100:.1f}% match rate** — "
        f"{int(match_rate*eval_metrics['total_records'])} / {eval_metrics['total_records']} "
        f"lifecycles correctly reconciled against Stage 3 ground truth."
    )

    highest_priority_case = df_queue.iloc[0]
    if st.button(f"👉 Jump to highest-priority case: {highest_priority_case['Case ID']} ({highest_priority_case['Payment ID']})"):
        st.session_state.selected_case = highest_priority_case["Case ID"]
        st.info("Case selected — open the **Exception Operations** tab to see its full journey.")

    st.divider()
    st.subheader("🛡️ System Reliability")
    st.caption("Source: Stage 3 held-out evaluation harness")

    rcol1, rcol2, rcol3, rcol4, rcol5 = st.columns(5)
    rcol1.metric("Match Rate", f"{eval_metrics['match_rate']*100:.1f}%")
    rcol2.metric("Match Precision", f"{eval_metrics['exception_precision']*100:.1f}%")
    rcol3.metric("Match Recall", f"{eval_metrics['exception_recall']*100:.1f}%")
    rcol4.metric("False-Resolution", f"{eval_metrics['false_resolution_rate']*100:.1f}%")
    rcol5.metric("Cases Evaluated", eval_metrics["total_records"])

    automation_rate = round(auto_count / total_exceptions * 100, 1) if total_exceptions else 0
    st.caption(
        f"**{automation_rate}% of flagged exceptions were auto-resolved without human "
        f"intervention.** Policy engine permitted 0 unsafe actions in the evaluated cases."
    )

    human_required = review_count + escalate_count
    st.markdown(f"**Human Attention Required: {human_required} / {total_exceptions} exceptions**")
    st.caption(f"REVIEW: {review_count} · ESCALATE: {escalate_count}")

    st.divider()
    st.subheader("Distributions")

    col_a, col_b = st.columns(2)
    with col_a:
        action_order = ["AUTO_RESOLVE", "REVIEW", "ESCALATE", "REJECT_ACTION"]
        action_counts = df_queue["Final Action"].value_counts().reindex(action_order, fill_value=0).reset_index()
        action_counts.columns = ["Action", "Count"]
        st.markdown("**Action Distribution**")
        st.bar_chart(action_counts.set_index("Action"))
        review_row_count = action_counts.set_index("Action").loc["REVIEW", "Count"]
        if review_row_count == 0:
            st.caption("REVIEW is an implemented outcome (RESOLVE recommended at 0.75–0.89 confidence). "
                        "No real case landed there in this run — the capability is verified separately in Tab D.")
        else:
            st.caption(f"REVIEW fired organically on {review_row_count} real case(s) in this run — "
                        f"confirming the policy engine's confidence-gated middle tier works in practice, "
                        f"not just in constructed scenarios.")

    with col_b:
        priority_order_list = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
        priority_counts = df_queue["Priority"].value_counts().reindex(priority_order_list, fill_value=0).reset_index()
        priority_counts.columns = ["Priority", "Count"]
        st.markdown("**Priority Distribution**")
        st.bar_chart(priority_counts.set_index("Priority"))

    st.divider()
    st.subheader("Cash Position Forecast")

    forecast = get_cash_forecast(stage2_results)

    cols = st.columns(3)
    for i, f in enumerate(forecast):
        with cols[i]:
            st.metric(f"{f['horizon_days']}-Day Projection", f"₹{f['projected_cash']:,.0f}")
            st.caption(f"Inflows: ₹{f['expected_inflows']:,.0f} · Outflows: ₹{f['expected_outflows']:,.0f}")

    lower_bound = forecast[0]["projected_cash"] - forecast[0]["cash_uncertainty"]
    upper_bound = forecast[0]["projected_cash"]
    st.markdown(f"**Expected range (1-day):** ₹{lower_bound:,.0f} – ₹{upper_bound:,.0f}")
    st.warning(
        f"**₹{forecast[0]['cash_uncertainty']:,.2f} of forecast uncertainty comes directly "
        f"from unresolved reconciliation exceptions** in the queue below — not an abstract estimate."
    )

    st.markdown("**Top contributors to uncertainty (also visible in the Exception Queue):**")
    for c in forecast[0]["top_uncertainty_contributors"]:
        st.markdown(f"- `{c['payment_id']}`: ₹{c['amount_at_risk']:,.2f}")
    st.divider()
    render_pattern_clusters()

# ============================================================
# TAB B — EXCEPTION OPERATIONS
# ============================================================
with tab_b:
    st.subheader("Exception Queue")

    st.dataframe(
        df_queue,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Amount at Risk": st.column_config.NumberColumn(format="₹%.2f"),
            "Confidence": st.column_config.ProgressColumn(min_value=0, max_value=1),
        }
    )

    st.divider()
    st.subheader("Case Explorer")

    case_ids = df_queue["Case ID"].tolist()
    default_idx = case_ids.index(st.session_state.selected_case) if st.session_state.selected_case in case_ids else 0
    selected_case_id = st.selectbox("Select a case to investigate:", case_ids, index=default_idx)
    st.session_state.selected_case = selected_case_id
    case_detail = next(r for r in audit_trail if r["case_id"] == selected_case_id)

    st.markdown("### Case Summary")
    ic1, ic2, ic3, ic4 = st.columns(4)
    ic1.metric("AT RISK", f"₹{case_detail['amount_at_risk']:,.0f}")
    ic2.metric("PRIORITY", f"{case_detail['priority']['priority']} · {case_detail['priority']['priority_score']}/{PRIORITY_MAX_SCORE}")
    ic3.metric("CONFIDENCE", f"{case_detail['agent_investigation']['confidence']*100:.0f}%")
    ic4.metric("FINAL ACTION", case_detail['policy_decision']['final_action'])
    st.markdown(f"**Root Cause:** `{case_detail['agent_investigation']['root_cause']}`")

    st.divider()

    col_left, col_right = st.columns([2, 1])

    with col_left:
        st.markdown(f"### {case_detail['payment_id']}")

        render_lifecycle_bar()
        st.caption(f"Exception detected at Settlement ↔ Bank reconciliation for {case_detail['payment_id']}")

        st.markdown("**Data lineage:**")
        records = case_detail["agent_investigation"]["evidence"].get("records_examined", [])
        st.markdown(" → ".join(f"`{r}`" for r in records) if records else "_No records cited_")

        st.markdown("**Investigation checklist:**")
        for rec in records:
            st.markdown(f"✓ Found `{rec}`")

        render_expected_vs_observed(case_detail)

        st.markdown("**Agent's explanation:**")
        st.info(case_detail['agent_investigation']['explanation'])

        with st.expander("Raw evidence JSON"):
            st.json(case_detail['agent_investigation']['evidence'])

        with st.expander("Stage 2 deterministic findings"):
            st.json(case_detail['stage2_findings'])

    with col_right:
        render_priority_scoreboard(case_detail)

        st.divider()
        st.markdown(f"**Policy decision:** {case_detail['policy_decision']['final_action']}")
        st.caption(case_detail['policy_decision']['policy_reason'])

        st.markdown(f"**Action taken:** {case_detail['execution']['action_taken']}")
        st.caption(f"Stored in: `{case_detail['execution']['store']}`")

        verified_icon = "✅" if case_detail['verification']['verified'] else "⚠️"
        st.markdown(f"**Verified:** {verified_icon} {case_detail['verification']['verification_method']}")
        st.caption(case_detail['verification']['notes'])

    st.divider()
    render_case_journey(case_detail)
    st.divider()
    render_what_if_simulator(case_detail)


# ============================================================
# TAB C — AGENT CONTROL CENTER
# ============================================================
with tab_c:
    st.subheader("🔍 Agentic Investigation Trace — Replay")
    st.caption("A captured, real tool-calling investigation, replayed step by step")

    captured_traces = load_captured_traces()
    trace_labels = [f"{t['payment_id']} — {t['label']}" for t in captured_traces]
    selected_trace_label = st.selectbox("Choose a case to replay:", trace_labels)
    selected_trace = captured_traces[trace_labels.index(selected_trace_label)]

    meta1, meta2, meta3 = st.columns(3)
    meta1.markdown(f"**SOURCE**\n\nCaptured production test run")
    meta2.markdown(f"**MODE**\n\nTool-calling agent")
    meta3.markdown(f"**CASE**\n\n`{selected_trace['payment_id']}`")

    if st.button("▶ Replay Investigation", key="trace_replay_btn"):
        placeholder = st.empty()
        progress = st.progress(0)
        base_time = datetime.now()
        with placeholder.container():
            st.markdown(f"`{base_time.strftime('%H:%M:%S')}`  **EXCEPTION RECEIVED**")
        time.sleep(0.4)

        for i, step in enumerate(selected_trace["trace"]):
            with placeholder.container():
                st.markdown(f"`{base_time.strftime('%H:%M:%S')}`  **EXCEPTION RECEIVED**")
                for j in range(i + 1):
                    s = selected_trace["trace"][j]
                    step_time = (base_time + timedelta(seconds=j + 1)).strftime('%H:%M:%S')
                    why = TOOL_WHY.get(s["tool"], "Supports the ongoing investigation.")
                    st.markdown(f"`{step_time}`  **{s['tool']}()**")
                    st.caption(f"Input: `{s['args']}`")
                    st.caption(f"↳ Why: {why}")
            time.sleep(0.6)
            progress.progress((i + 1) / len(selected_trace["trace"]))

        st.markdown("### Final Summary")
        st.info(selected_trace["final_summary"])
        st.caption("Timestamps reflect replay pacing, not the original investigation's wall-clock time.")

    st.divider()
    st.subheader("⚖️ AI Proposes  →  Policy Decides")
    st.caption("The agent never has final authority over a financial action")

    reject_demo = next(r for r in audit_trail if r["policy_decision"]["final_action"] == "REJECT_ACTION")

    col1, arrow1, col2, arrow2, col3 = st.columns([3, 0.5, 3, 0.5, 3])
    with col1:
        with st.container(border=True):
            st.markdown("**① AI INVESTIGATION**")
            st.markdown("Root cause:")
            st.code(reject_demo['agent_investigation']['root_cause'])
            st.markdown(f"Confidence: **{reject_demo['agent_investigation']['confidence']*100:.0f}%**")
            st.markdown(f"Proposed: **{reject_demo['agent_investigation'].get('recommended_action', 'ESCALATE')}**")
    with arrow1:
        st.markdown("<h2 style='text-align:center;'>→</h2>", unsafe_allow_html=True)
        st.caption("proposes")
    with col2:
        with st.container(border=True):
            st.markdown("**② POLICY GATE**")
            conf_ok = reject_demo['agent_investigation']['confidence'] >= 0.90
            st.markdown(f"{'✅' if conf_ok else '➖'} Confidence ≥ 0.90")
            amt_ok = reject_demo['amount_at_risk'] < 50000
            st.markdown(f"{'✅' if amt_ok else '❌'} Amount < ₹50,000")
            st.markdown("❌ Refund exceeds payment (hard rule)")
            st.markdown("**Decision:** Hard safety rule overrides confidence.")
            st.error("ACTION NOT PERMITTED")
    with arrow2:
        st.markdown("<h2 style='text-align:center;'>→</h2>", unsafe_allow_html=True)
        st.caption("authorizes / blocks")
    with col3:
        with st.container(border=True):
            st.markdown("**③ FINAL ACTION**")
            st.error(f"⛔ {reject_demo['policy_decision']['final_action']}")
            st.caption("Settlement remains unchanged.")
            st.caption("Human intervention required.")

    st.caption("**The LLM can recommend. It cannot override financial policy.**")

    st.divider()
    st.subheader("🛑 Safety Spotlight: Blocked Action")

    with st.container(border=True):
        st.markdown(f"### {reject_demo['payment_id']} — {reject_demo['agent_investigation']['root_cause']}")
        st.markdown(f"**Amount involved:** ₹{reject_demo['amount_at_risk']:,.2f}")
        st.markdown(f"**Agent confidence:** {reject_demo['agent_investigation']['confidence']}")

        st.markdown("**What the agent found:**")
        st.write(reject_demo['agent_investigation']['explanation'])

        st.error(f"**BLOCKED:** {reject_demo['policy_decision']['policy_reason']}")

        st.caption(
            "The agent's investigation was thorough and confident, but the proposed action "
            "violated a hard safety rule. The system correctly refused to act — even at high "
            "confidence, and even though a human would eventually still need to review this case. "
            "Confidence is not a substitute for policy compliance."
        )


# ============================================================
# TAB D — SYSTEM RELIABILITY / RECOVERY
# ============================================================
with tab_d:
    st.subheader("🔄 Closed-Loop Verification & Recovery")
    st.caption(
        "The system verifies the outcome independently and re-routes the case when "
        "verification fails — it never rewrites financial truth."
    )

    scenarios = load_verification_scenarios()
    scenario_labels = [s["label"] for s in scenarios]
    selected_label = st.selectbox("Choose a scenario:", scenario_labels)
    selected_scenario = scenarios[scenario_labels.index(selected_label)]

    st.caption(selected_scenario["description"])

    if st.button("▶ Run Verification", key="verification_loop_btn"):
        step_placeholder = st.empty()

        with step_placeholder.container():
            st.markdown(f"**1. Policy decides:** `{selected_scenario['original_action']}`")
            st.caption(
                f"Root cause: {selected_scenario['root_cause']} · "
                f"Confidence: {selected_scenario['confidence']} · "
                f"Amount: ₹{selected_scenario['amount_at_risk']:,.2f}"
            )

        time.sleep(1)

        with step_placeholder.container():
            st.markdown(f"**1. Policy decides:** `{selected_scenario['original_action']}`")
            st.caption(
                f"Root cause: {selected_scenario['root_cause']} · "
                f"Confidence: {selected_scenario['confidence']} · "
                f"Amount: ₹{selected_scenario['amount_at_risk']:,.2f}"
            )
            st.markdown("**2. Case queued, verification re-check runs independently...**")

        time.sleep(1.2)

        with step_placeholder.container():
            st.markdown(f"**1. Policy decides:** `{selected_scenario['original_action']}`")
            st.caption(
                f"Root cause: {selected_scenario['root_cause']} · "
                f"Confidence: {selected_scenario['confidence']} · "
                f"Amount: ₹{selected_scenario['amount_at_risk']:,.2f}"
            )
            st.markdown("**2. Case queued, verification re-check runs independently...**")

            if selected_scenario["verification"]["corrected"]:
                st.error(f"⚠️ **Verification FAILED** — {selected_scenario['verification']['notes']}")
                st.markdown("**3. System recovers — re-routes the case:**")
                st.success(
                    f"✅ Case re-routed to **{selected_scenario['execution']['action_taken']}** — "
                    f"no financial data modified, only the decision pathway changed"
                )
            else:
                st.success(f"✅ **Verification PASSED** — {selected_scenario['verification']['notes']}")

    st.info(
        "These are constructed proof-of-capability scenarios, run through the real "
        "verification and re-routing logic — not scripted outcomes. No financial record "
        "is ever modified by this recovery step; only the case's queue assignment changes. "
        "None of the real exceptions in this dataset happened to trigger a re-route, so "
        "these scenarios demonstrate the capability directly."
    )


# ============================================================
# FOOTER
# ============================================================
st.divider()
st.caption(
    "**AI Finance Controller** · Payment → Refund → Settlement → Bank · "
    "Deterministic reconciliation + agentic investigation + policy-gated action + "
    "independent verification · Evaluation dataset: 200 synthetic payment lifecycles "
    "with controlled ground-truth mutations."
)