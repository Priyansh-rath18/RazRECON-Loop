import json


def optimize_resolution_order(audit_trail: list, total_uncertainty: float, capacity: int) -> dict:
    """
    Greedily ranks unresolved cases by cash-risk-reduction-per-case, so a
    human with limited review time resolves the highest-impact cases first.
    REJECT_ACTION cases get a compliance-severity boost, since they represent
    policy violations, not purely financial exposure.
    """
    # only rank cases that still need human attention (not already auto-resolved)
    actionable = [
        r for r in audit_trail
        if r["policy_decision"]["final_action"] in ("ESCALATE", "REVIEW", "REJECT_ACTION")
    ]

    def sort_key(case):
        compliance_boost = 1_000_000 if case["policy_decision"]["final_action"] == "REJECT_ACTION" else 0
        return case["amount_at_risk"] + compliance_boost

    ranked = sorted(actionable, key=sort_key, reverse=True)
    selected = ranked[:capacity]

    cumulative = 0.0
    plan = []
    for case in selected:
        cumulative += case["amount_at_risk"]
        reduction_pct = round(cumulative / total_uncertainty * 100, 1) if total_uncertainty > 0 else 0
        plan.append({
            "case_id": case["case_id"],
            "payment_id": case["payment_id"],
            "root_cause": case["agent_investigation"]["root_cause"],
            "amount_at_risk": case["amount_at_risk"],
            "final_action": case["policy_decision"]["final_action"],
            "priority": case["priority"]["priority"],
            "cumulative_reduction_pct": reduction_pct,
            "note": "Compliance-critical — reviewed regardless of amount" if case["policy_decision"]["final_action"] == "REJECT_ACTION" else None
        })

    total_reduction_pct = round(cumulative / total_uncertainty * 100, 1) if total_uncertainty > 0 else 0
    remaining_uncertainty = round(total_uncertainty - cumulative, 2)

    return {
        "capacity": capacity,
        "total_actionable_cases": len(actionable),
        "plan": plan,
        "total_reduction_pct": total_reduction_pct,
        "remaining_uncertainty": remaining_uncertainty,
        "original_uncertainty": total_uncertainty
    }


if __name__ == "__main__":
    with open("data/audit_trail.json") as f:
        audit_trail = json.load(f)

    total_uncertainty = sum(
        r["amount_at_risk"] for r in audit_trail
        if r["policy_decision"]["final_action"] in ("ESCALATE", "REVIEW", "REJECT_ACTION")
    )

    for capacity in [5, 10]:
        result = optimize_resolution_order(audit_trail, total_uncertainty, capacity)
        print(f"\n--- Capacity: {capacity} cases ---")
        print(f"Total actionable cases: {result['total_actionable_cases']}")
        for p in result["plan"]:
            note = f" ({p['note']})" if p["note"] else ""
            print(f"  {p['case_id']} · ₹{p['amount_at_risk']:,.2f} · {p['root_cause']} · "
                  f"cumulative: {p['cumulative_reduction_pct']}%{note}")
        print(f"Total reduction: {result['total_reduction_pct']}% · "
              f"Remaining uncertainty: ₹{result['remaining_uncertainty']:,.2f}")