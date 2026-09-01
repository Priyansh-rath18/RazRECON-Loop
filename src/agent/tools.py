import pandas as pd
from src.matching.match_engine import normalize_utr, lifecycle_check
from src.agent.policy import apply_policy

# Data loaded once, module-level, so tools can access it
_df_orders = pd.read_csv("data/mutated/orders.csv")
_df_payments = pd.read_csv("data/mutated/payments.csv")
_df_refunds = pd.read_csv("data/mutated/refunds.csv")
_df_settlements = pd.read_csv("data/mutated/settlements.csv")
_df_bank = pd.read_csv("data/mutated/bank_entries.csv")


def get_payment(payment_id: str) -> dict:
    """Fetch the payment record for a given payment_id."""
    row = _df_payments[_df_payments["payment_id"] == payment_id]
    if len(row) == 0:
        return {"found": False, "reason": "No payment record exists for this payment_id."}
    return {"found": True, "payment": row.iloc[0].to_dict()}


def get_refunds(payment_id: str) -> dict:
    """Fetch all refund records for a given payment_id."""
    rows = _df_refunds[_df_refunds["payment_id"] == payment_id]
    return {"count": len(rows), "refunds": rows.to_dict(orient="records")}


def get_settlement(payment_id: str) -> dict:
    """Fetch the settlement record for a given payment_id."""
    row = _df_settlements[_df_settlements["payment_id"] == payment_id]
    if len(row) == 0:
        return {"found": False, "reason": "No settlement record exists for this payment_id."}
    return {"found": True, "settlement": row.iloc[0].to_dict()}


def search_bank_transactions(utr: str) -> dict:
    """Search bank entries by UTR (normalized match)."""
    normalized_target = normalize_utr(utr)
    rows = _df_bank[_df_bank["UTR"].apply(normalize_utr) == normalized_target]
    return {"count": len(rows), "bank_entries": rows.to_dict(orient="records")}


def calculate_reconciliation(payment_id: str) -> dict:
    """
    Runs the deterministic lifecycle check for a payment_id —
    computes expected net vs actual net, with proportional tolerance.
    """
    result = lifecycle_check(payment_id, _df_payments, _df_refunds, _df_settlements)
    return result if result is not None else {"error": "No settlement found to check."}


def check_action_policy(proposed_action: str, amount_at_risk: float, confidence: float) -> dict:
    """
    Checks whether a proposed action is permitted, given amount at risk
    and confidence, using the deterministic policy engine.
    """
    fake_agent_result = {
        "root_cause": "AGENT_PROPOSED",
        "recommended_action": proposed_action,
        "confidence": confidence
    }
    return apply_policy(fake_agent_result, amount_at_risk)


def create_escalation(payment_id: str, reason: str, priority: str) -> dict:
    """
    Creates a structured escalation record. This is the agent's actual
    'action' — it does not modify source data, only creates a case for review.
    """
    return {
        "action": "CREATE_ESCALATION",
        "payment_id": payment_id,
        "reason": reason,
        "priority": priority,
        "status": "ESCALATED"
    }

if __name__ == "__main__":
    print(get_payment("PAY-00046"))
    print(get_refunds("PAY-00046"))
    print(calculate_reconciliation("PAY-00046"))
    print(check_action_policy("RESOLVE", amount_at_risk=172425.68, confidence=0.95))