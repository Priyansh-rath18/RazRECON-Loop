import json
import pandas as pd
from src.agent.investigate import gather_related_records
from src.agent.reason import reason_over_case_with_retry
from src.agent.policy import apply_policy
from src.agent.execution import execute_with_verification_loop
from src.agent.priority import calculate_priority

TARGET_IDS = ["PAY-00136", "PAY-00146", "PAY-00190"]

df_orders = pd.read_csv("data/mutated/orders.csv")
df_payments = pd.read_csv("data/mutated/payments.csv")
df_refunds = pd.read_csv("data/mutated/refunds.csv")
df_settlements = pd.read_csv("data/mutated/settlements.csv")
df_bank = pd.read_csv("data/mutated/bank_entries.csv")

with open("data/stage2_results.json") as f:
    stage2_results = json.load(f)

# find the matching stage2 case + amount_at_risk for each target
stage2_lookup = {r["payment_id"]: r for r in stage2_results}

results = []

for pid in TARGET_IDS:
    print(f"\n{'='*60}")
    print(f"Investigating: {pid}")
    print(f"{'='*60}")

    case = stage2_lookup[pid]
    settlement_row = df_settlements[df_settlements["payment_id"] == pid]
    amount_at_risk = float(settlement_row.iloc[0]["gross_amount"]) if len(settlement_row) > 0 else 0.0
    case["amount_at_risk"] = amount_at_risk

    related = gather_related_records(pid, df_orders, df_payments, df_refunds, df_settlements, df_bank)
    agent_result = reason_over_case_with_retry(related, case)
    policy_result = apply_policy(agent_result, amount_at_risk)

    print(f"Root cause: {agent_result['root_cause']}")
    print(f"Confidence: {agent_result['confidence']}")
    print(f"Agent recommended: {agent_result['recommended_action']}")
    print(f"Policy final action: {policy_result['final_action']}")
    print(f"Policy reason: {policy_result['policy_reason']}")

    loop_result = execute_with_verification_loop(
        pid, policy_result["final_action"], policy_result["policy_reason"],
        agent_result, amount_at_risk
    )

    priority_result = calculate_priority(
        amount_at_risk=amount_at_risk,
        confidence=agent_result["confidence"],
        root_cause=agent_result["root_cause"],
        is_top_cash_risk=False,
        recurrence_count=1,
        settlement_time=str(settlement_row.iloc[0]["settlement_time"]) if len(settlement_row) > 0 else None
    )
    print(f"Priority: {priority_result['priority']}")

    results.append({
        "payment_id": pid,
        "agent_investigation": agent_result,
        "policy_decision": policy_result,
        "execution": loop_result["execution"],
        "verification": loop_result["verification"],
        "priority": priority_result
    })

with open("data/borderline_results.json", "w") as f:
    json.dump(results, f, indent=2, default=str)

print(f"\n\nSaved to data/borderline_results.json")