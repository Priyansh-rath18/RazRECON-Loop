MATERIALITY_THRESHOLD = 50000  # ₹50,000
CONFIDENCE_THRESHOLD = 0.75
AUTO_RESOLVE_THRESHOLD = 0.90


def apply_policy(agent_result: dict, amount_at_risk: float) -> dict:
    """
    Deterministic policy gate — applies hard rules to the agent's recommendation,
    and can override it. The agent proposes; this function decides.
    """
    exception_type = agent_result.get("root_cause", "")
    recommended_action = agent_result.get("recommended_action", "ESCALATE")
    confidence = agent_result.get("confidence", 0.0)

    # Rule 1: hard rejects — always win, regardless of everything else
    if exception_type == "OVER_REFUND":
        return {
            "final_action": "REJECT_ACTION",
            "policy_reason": "Refund exceeds original payment amount — a hard safety rule violation. This action cannot be auto-approved under any confidence level."
        }

    # Rule 2: materiality — high-value cases always get human review
    if amount_at_risk > MATERIALITY_THRESHOLD:
        if recommended_action != "ESCALATE":
            return {
                "final_action": "ESCALATE",
                "policy_reason": f"Amount at risk (₹{amount_at_risk:,.2f}) exceeds materiality threshold (₹{MATERIALITY_THRESHOLD:,.2f}); escalating regardless of agent recommendation."
            }

    # Rule 3: low confidence never auto-resolves
    if confidence < CONFIDENCE_THRESHOLD:
        return {
            "final_action": "ESCALATE",
            "policy_reason": f"Agent confidence ({confidence}) below required threshold ({CONFIDENCE_THRESHOLD}) for automated action."
        }

    # Rule 4: follow agent recommendation, with a confidence-based split on RESOLVE
    if recommended_action == "RESOLVE":
        if confidence >= AUTO_RESOLVE_THRESHOLD:
            return {
                "final_action": "AUTO_RESOLVE",
                "policy_reason": f"High confidence ({confidence}) and complete evidence support automatic resolution."
            }
        else:
            return {
                "final_action": "REVIEW",
                "policy_reason": f"Agent recommends resolution but confidence ({confidence}) is below the auto-resolve threshold ({AUTO_RESOLVE_THRESHOLD}); routing to human confirmation."
            }
    elif recommended_action == "REJECT":
        return {
            "final_action": "REJECT_ACTION",
            "policy_reason": agent_result.get("action_reason", "Agent identified a policy violation.")
        }
    else:  # ESCALATE
        return {
            "final_action": "ESCALATE",
            "policy_reason": agent_result.get("action_reason", "Agent recommends human review.")
        }


if __name__ == "__main__":
    # test against your PAY-00046 result from earlier
    test_agent_result = {
        "root_cause": "REFUND_TIMING_CONFLICT",
        "recommended_action": "ESCALATE",
        "confidence": 0.85
    }
    result = apply_policy(test_agent_result, amount_at_risk=172425.68)
    print(result)

    # test the materiality override — agent says RESOLVE but amount is huge
    test_2 = {"root_cause": "FEE_MISMATCH", "recommended_action": "RESOLVE", "confidence": 0.95}
    result_2 = apply_policy(test_2, amount_at_risk=75000)
    print(result_2)

    # test a genuine auto-resolve — small amount, high confidence, RESOLVE
    test_3 = {"root_cause": "UTR_MISMATCH", "recommended_action": "RESOLVE", "confidence": 0.98}
    result_3 = apply_policy(test_3, amount_at_risk=2000)
    print(result_3)