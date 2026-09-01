from datetime import datetime
import pandas as pd

ROOT_CAUSE_RISK_WEIGHT = {
    "OVER_REFUND": 3,
    "MISSING_BANK_ENTRY": 3,
    "REFUND_TIMING_CONFLICT": 2,
    "AMOUNT_MISMATCH": 2,
    "REFUND_NOT_REFLECTED": 2,
    "FEE_MISMATCH": 1,
    "TAX_MISMATCH": 1,
    "DUPLICATE_TRANSACTION": 1,
    "UTR_MISMATCH": 1,
    "VALID_NEGATIVE_SETTLEMENT": 0,
    "GENUINE_DISCREPANCY": 2,
    "UNKNOWN": 2,
}


def calculate_priority(amount_at_risk: float, confidence: float, root_cause: str,
                         is_top_cash_risk: bool = False, recurrence_count: int = 1,
                         settlement_time: str = None) -> dict:
    """
    Combines financial materiality, agent confidence, root-cause inherent risk,
    real cash-forecast impact, systemic recurrence, and time-since-settlement
    into a single priority level + explanation.
    Confidence and priority are kept deliberately separate signals.
    """
    risk_weight = ROOT_CAUSE_RISK_WEIGHT.get(root_cause, 2)
    reasons = []  # list of (text, points) tuples
    score = 0

    if amount_at_risk > 100000:
        pts = 3
        reasons.append((f"High monetary exposure (₹{amount_at_risk:,.2f})", pts))
        score += pts
    elif amount_at_risk > 50000:
        pts = 2
        reasons.append((f"Material monetary exposure (₹{amount_at_risk:,.2f})", pts))
        score += pts
    elif amount_at_risk > 10000:
        pts = 1
        reasons.append((f"Moderate monetary exposure (₹{amount_at_risk:,.2f})", pts))
        score += pts

    score += risk_weight
    if risk_weight >= 3:
        reasons.append((f"Root cause '{root_cause}' carries inherent high risk", risk_weight))
    elif risk_weight == 0:
        reasons.append((f"Root cause '{root_cause}' is a known-safe pattern", 0))
    elif risk_weight > 0:
        reasons.append((f"Root cause '{root_cause}' operational risk", risk_weight))

    if confidence < 0.7:
        reasons.append((f"Low agent confidence ({confidence})", 1))
        score += 1

    if is_top_cash_risk:
        reasons.append(("Contributes to near-term cash-flow uncertainty", 2))
        score += 2

    if recurrence_count >= 3:
        reasons.append((f"Recurs {recurrence_count} times — possible systemic issue", 2))
        score += 2

    if settlement_time:
        try:
            days_since = (datetime.now() - pd.Timestamp(settlement_time)).days
            if days_since > 7:
                reasons.append((f"Settlement overdue ({days_since} days)", 1))
                score += 1
        except Exception:
            pass

    if score >= 6:
        level = "CRITICAL"
    elif score >= 4:
        level = "HIGH"
    elif score >= 2:
        level = "MEDIUM"
    else:
        level = "LOW"

    return {
        "priority": level,
        "priority_score": score,
        "priority_breakdown": reasons,
        "priority_reasoning": "; ".join(r[0] for r in reasons) if reasons else "No significant risk factors identified."
    }


def count_recurring_root_causes(all_cases: list) -> dict:
    """Counts how many times each root_cause appears across the current exception batch."""
    from collections import Counter
    return Counter(c.get("agent_investigation", {}).get("root_cause") for c in all_cases
                    if c.get("agent_investigation", {}).get("root_cause"))