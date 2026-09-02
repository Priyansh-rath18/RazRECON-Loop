import json
import pandas as pd
from datetime import datetime

from src.agent.investigate import gather_related_records
from src.agent.reason import reason_over_case_with_retry
from src.agent.policy import apply_policy
from src.agent.triage import triage_exceptions


def build_audit_record(case: dict, agent_result: dict, policy_result: dict,
                         case_number: int) -> dict:
    """
    Assembles one complete, traceable audit record for a single case,
    combining Stage 2 findings, agent investigation, policy decision,
    the controlled action actually taken, and its verification —
    including automatic correction if verification fails.
    """
    from src.agent.execution import execute_with_verification_loop

    loop_result = execute_with_verification_loop(
        case["payment_id"], policy_result["final_action"], policy_result["policy_reason"],
        agent_result, case["amount_at_risk"]
    )

    return {
        "case_id": f"CASE-{case_number:04d}",
        "payment_id": case["payment_id"],
        "amount_at_risk": case["amount_at_risk"],
        "stage2_findings": {
            "bank_match": case["bank_match"],
            "lifecycle_check": case["lifecycle_check"]
        },
        "agent_investigation": {
            "root_cause": agent_result.get("root_cause"),
            "explanation": agent_result.get("explanation"),
            "evidence": agent_result.get("evidence"),
            "confidence": agent_result.get("confidence"),
            "recommended_action": agent_result.get("recommended_action")
        },
        "policy_decision": {
            "final_action": policy_result["final_action"],
            "policy_reason": policy_result["policy_reason"]
        },
        "execution": loop_result["execution"],
        "verification": loop_result["verification"],
        "timestamp": datetime.now().isoformat()
    }


def run_full_pipeline(limit: int = None) -> list:
    from src.agent.priority import calculate_priority, count_recurring_root_causes
    from src.agent.cash_position import cash_forecast

    df_orders = pd.read_csv("data/mutated/orders.csv")
    df_payments = pd.read_csv("data/mutated/payments.csv")
    df_refunds = pd.read_csv("data/mutated/refunds.csv")
    df_settlements = pd.read_csv("data/mutated/settlements.csv")
    df_bank = pd.read_csv("data/mutated/bank_entries.csv")

    with open("data/stage2_results.json") as f:
        stage2_results = json.load(f)

    prioritized_cases = triage_exceptions(stage2_results, df_settlements)

    if limit:
        prioritized_cases = prioritized_cases[:limit]

    # get top cash-risk contributors, to check against later
    forecast = cash_forecast(df_settlements, df_refunds, df_bank, prioritized_cases)
    top_cash_risk_ids = {c["payment_id"] for c in forecast[0]["top_uncertainty_contributors"]}

    audit_trail = []

    for i, case in enumerate(prioritized_cases, start=1):
        payment_id = case["payment_id"]
        print(f"Processing {i}/{len(prioritized_cases)}: {payment_id}...")

        related = gather_related_records(payment_id, df_orders, df_payments, df_refunds,
                                            df_settlements, df_bank)
        agent_result = reason_over_case_with_retry(related, case)
        policy_result = apply_policy(agent_result, case["amount_at_risk"])

        record = build_audit_record(case, agent_result, policy_result, case_number=i)
        audit_trail.append(record)

    # SECOND PASS: now that all root causes are known, compute recurrence + priority
    recurrence = count_recurring_root_causes(audit_trail)

    for record in audit_trail:
        root_cause = record["agent_investigation"]["root_cause"]
        settlement_row = df_settlements[df_settlements["payment_id"] == record["payment_id"]]
        settlement_time = settlement_row.iloc[0]["settlement_time"] if len(settlement_row) > 0 else None

        priority_result = calculate_priority(
            amount_at_risk=record["amount_at_risk"],
            confidence=record["agent_investigation"]["confidence"],
            root_cause=root_cause,
            is_top_cash_risk=record["payment_id"] in top_cash_risk_ids,
            recurrence_count=recurrence.get(root_cause, 1),
            settlement_time=settlement_time
        )
        record["priority"] = priority_result

    return audit_trail


if __name__ == "__main__":
    audit_trail = run_full_pipeline(limit=None)  # all 62 exceptions

    with open("data/audit_trail.json", "w") as f:
        json.dump(audit_trail, f, indent=2, default=str)

    print(f"\nSaved {len(audit_trail)} audit records to data/audit_trail.json")

    from collections import Counter
    actions = Counter(r["policy_decision"]["final_action"] for r in audit_trail)
    priorities = Counter(r["priority"]["priority"] for r in audit_trail)
    print(f"\nAction distribution: {dict(actions)}")
    print(f"Priority distribution: {dict(priorities)}")