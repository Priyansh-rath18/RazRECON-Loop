import json
from src.agent.execution import execute_with_verification_loop

SCENARIOS = [
    {
        "label": "Low Confidence Auto-Resolve Correction",
        "payment_id": "SIM-PAY-001",
        "final_action": "AUTO_RESOLVE",
        "policy_reason": "Initial policy pass: high confidence assumed",
        "agent_result": {"root_cause": "UTR_MISMATCH", "confidence": 0.72},
        "amount_at_risk": 1500.0,
        "description": "A case initially marked safe to auto-resolve, but the confidence (0.72) doesn't actually clear the 0.90 threshold required for automation."
    },
    {
        "label": "Materiality-Driven Correction",
        "payment_id": "SIM-PAY-002",
        "final_action": "AUTO_RESOLVE",
        "policy_reason": "Initial policy pass: assumed low-value case",
        "agent_result": {"root_cause": "FEE_MISMATCH", "confidence": 0.95},
        "amount_at_risk": 85000.0,
        "description": "High agent confidence (0.95), but the amount at risk (₹85,000) exceeds the materiality threshold — the re-check catches what the initial pass missed."
    },
    {
        "label": "Confidence Just Below Threshold",
        "payment_id": "SIM-PAY-003",
        "final_action": "AUTO_RESOLVE",
        "policy_reason": "Initial policy pass: near-threshold confidence rounded up",
        "agent_result": {"root_cause": "TAX_MISMATCH", "confidence": 0.89},
        "amount_at_risk": 2200.0,
        "description": "Confidence (0.89) sits just one point under the 0.90 auto-resolve threshold — small enough to be missed casually, caught by the strict re-check."
    },
]

results = []
for s in SCENARIOS:
    loop_result = execute_with_verification_loop(
        s["payment_id"], s["final_action"], s["policy_reason"],
        s["agent_result"], s["amount_at_risk"]
    )
    results.append({
        "label": s["label"],
        "description": s["description"],
        "payment_id": s["payment_id"],
        "root_cause": s["agent_result"]["root_cause"],
        "confidence": s["agent_result"]["confidence"],
        "amount_at_risk": s["amount_at_risk"],
        "original_action": s["final_action"],
        "execution": loop_result["execution"],
        "verification": loop_result["verification"],
    })

with open("data/verification_scenarios.json", "w") as f:
    json.dump(results, f, indent=2, default=str)

print(f"Saved {len(results)} scenarios to data/verification_scenarios.json")
for r in results:
    corrected = r["verification"].get("corrected", False)
    print(f"  {r['label']}: corrected={corrected}, final_action={r['execution']['action_taken']}")