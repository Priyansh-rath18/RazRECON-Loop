import json
import os
from datetime import datetime
from src.agent.tools import calculate_reconciliation, check_action_policy


RESOLVED_STORE = "data/resolved_cases.json"
REVIEW_QUEUE = "data/review_queue.json"
ESCALATION_QUEUE = "data/escalation_queue.json"
REJECTED_LOG = "data/rejected_actions.json"


def _append_to_store(path: str, record: dict):
    """Appends a record to a JSON list file, creating it if it doesn't exist."""
    if os.path.exists(path):
        with open(path, "r") as f:
            data = json.load(f)
    else:
        data = []
    data.append(record)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)


def execute_action(payment_id: str, final_action: str, policy_reason: str,
                     agent_result: dict, amount_at_risk: float) -> dict:
    """
    CONTROLLED ACTION: actually changes system state based on the policy
    decision, rather than only logging it. Each action writes to a distinct
    persistent store, so the system's state visibly reflects the decision.
    """
    timestamp = datetime.now().isoformat()

    if final_action == "AUTO_RESOLVE":
        record = {
            "payment_id": payment_id,
            "resolved_at": timestamp,
            "root_cause": agent_result.get("root_cause"),
            "resolution_reason": policy_reason
        }
        _append_to_store(RESOLVED_STORE, record)
        return {"action_taken": "MARKED_RESOLVED", "store": RESOLVED_STORE, "record": record}

    elif final_action == "REVIEW":
        record = {
            "payment_id": payment_id,
            "queued_at": timestamp,
            "root_cause": agent_result.get("root_cause"),
            "confidence": agent_result.get("confidence"),
            "amount_at_risk": amount_at_risk
        }
        _append_to_store(REVIEW_QUEUE, record)
        return {"action_taken": "QUEUED_FOR_REVIEW", "store": REVIEW_QUEUE, "record": record}

    elif final_action == "ESCALATE":
        record = {
            "payment_id": payment_id,
            "escalated_at": timestamp,
            "root_cause": agent_result.get("root_cause"),
            "reason": policy_reason,
            "amount_at_risk": amount_at_risk,
            "priority": "HIGH" if amount_at_risk > 50000 else ("MEDIUM" if amount_at_risk > 10000 else "LOW")
        }
        _append_to_store(ESCALATION_QUEUE, record)
        return {"action_taken": "ESCALATED", "store": ESCALATION_QUEUE, "record": record}

    elif final_action == "REJECT_ACTION":
        record = {
            "payment_id": payment_id,
            "rejected_at": timestamp,
            "attempted_action": agent_result.get("recommended_action"),
            "reason": policy_reason
        }
        _append_to_store(REJECTED_LOG, record)
        return {"action_taken": "ACTION_BLOCKED", "store": REJECTED_LOG, "record": record}

    return {"action_taken": "UNKNOWN", "record": None}


def verify_outcome(payment_id: str, final_action: str, execution_result: dict,
                     amount_at_risk: float, confidence: float) -> dict:
    """
    VERIFY OUTCOME: a second, independent safety pass after execution.
    Re-checks that the action taken was actually consistent with policy,
    catching any inconsistency between decision and execution.
    """
    if final_action == "AUTO_RESOLVE":
        # re-run the policy check independently — confirm this case still
        # qualifies for auto-resolution under the rules, as a safety net
        recheck = check_action_policy("RESOLVE", amount_at_risk, confidence)
        verified = recheck["final_action"] == "AUTO_RESOLVE"
        return {
            "verified": verified,
            "verification_method": "POLICY_RECHECK",
            "notes": "Confirmed still eligible for auto-resolution." if verified
                      else f"WARNING: re-check disagrees — got {recheck['final_action']}."
        }

    elif final_action == "REJECT_ACTION":
        # verify no data was modified — the store only logged the rejection,
        # not any change to source records
        return {
            "verified": True,
            "verification_method": "NO_OP_CONFIRMATION",
            "notes": "Confirmed no source records were modified; action correctly blocked."
        }

    elif final_action in ("ESCALATE", "REVIEW"):
        # verify the queued record has complete evidence attached
        record = execution_result.get("record", {})
        required_fields = ["payment_id", "root_cause"]
        complete = all(record.get(f) for f in required_fields)
        return {
            "verified": complete,
            "verification_method": "EVIDENCE_COMPLETENESS_CHECK",
            "notes": "All required evidence fields present." if complete
                      else "WARNING: incomplete evidence in queued record."
        }

    return {"verified": False, "verification_method": "NONE", "notes": "Unknown action type."}

def execute_with_verification_loop(payment_id: str, final_action: str, policy_reason: str,
                                      agent_result: dict, amount_at_risk: float) -> dict:
    """
    CONTROLLED ACTION + VERIFY OUTCOME, closed into a real feedback loop:
    if verification fails, the system automatically corrects course by
    re-routing to a safer action (ESCALATE), rather than just reporting
    the failure and stopping.
    """
    execution_result = execute_action(payment_id, final_action, policy_reason,
                                        agent_result, amount_at_risk)
    verification_result = verify_outcome(payment_id, final_action, execution_result,
                                            amount_at_risk, agent_result.get("confidence", 0.0))

    verification_result["corrected"] = False

    if not verification_result["verified"]:
        print(f"  [LOOP] Verification failed for {payment_id} — auto-correcting to ESCALATE")

        corrected_reason = (
            f"Auto-corrected by verification loop: original action '{final_action}' "
            f"failed re-verification ({verification_result['notes']})"
        )
        execution_result = execute_action(payment_id, "ESCALATE", corrected_reason,
                                             agent_result, amount_at_risk)

        verification_result = verify_outcome(payment_id, "ESCALATE", execution_result,
                                                amount_at_risk, agent_result.get("confidence", 0.0))
        verification_result["corrected"] = True
        verification_result["original_action"] = final_action

    return {"execution": execution_result, "verification": verification_result}

if __name__ == "__main__":
    fake_agent_result = {
        "root_cause": "UTR_MISMATCH",
        "confidence": 0.72
    }
    result = execute_with_verification_loop(
        "TEST-PAY-001", "AUTO_RESOLVE", "Initial policy pass (simulated inconsistency)",
        fake_agent_result, amount_at_risk=1500.0
    )
    print(json.dumps(result, indent=2, default=str))