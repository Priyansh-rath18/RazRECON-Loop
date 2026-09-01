import json

if __name__ == "__main__":
    with open("data/audit_trail.json") as f:
        audit_trail = json.load(f)

    print(f"--- Auto-resolved cases ---")
    for r in audit_trail:
        if r["policy_decision"]["final_action"] == "AUTO_RESOLVE":
            print(f"{r['case_id']} - {r['payment_id']}: {r['agent_investigation']['root_cause']} "
                  f"(confidence: {r['agent_investigation']['confidence']}, "
                  f"amount at risk: ₹{r['amount_at_risk']:,.2f})")
            print(f"  Reason: {r['policy_decision']['policy_reason']}")