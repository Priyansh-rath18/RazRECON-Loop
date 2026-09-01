import json
import pandas as pd


def compute_amount_at_risk(case: dict, df_settlements: pd.DataFrame) -> float:
    """
    Estimates the financial amount at risk for one exception case.
    Uses the settlement's gross_amount as the base — the full transaction
    value that's unresolved, not just the net delta, since even a small
    net mismatch on a large transaction deserves attention.
    """
    settlement_row = df_settlements[df_settlements["payment_id"] == case["payment_id"]]
    if len(settlement_row) == 0:
        return 0.0
    return float(settlement_row.iloc[0]["gross_amount"])


def triage_exceptions(stage2_results: list, df_settlements: pd.DataFrame) -> list:
    """
    Filters to only the genuine exceptions (bank_match EXCEPTION or
    lifecycle_check FAIL), computes amount_at_risk for each, and
    sorts by that amount descending — highest-value cases first.
    """
    exceptions = []

    for case in stage2_results:
        is_exception = (
            case["bank_match"]["status"] == "EXCEPTION"
            or (case["lifecycle_check"] is not None and case["lifecycle_check"]["status"] == "FAIL")
        )
        if is_exception:
            amount_at_risk = compute_amount_at_risk(case, df_settlements)
            exceptions.append({
                **case,
                "amount_at_risk": amount_at_risk
            })

    exceptions.sort(key=lambda c: c["amount_at_risk"], reverse=True)
    return exceptions


if __name__ == "__main__":
    df_settlements = pd.read_csv("data/mutated/settlements.csv")

    with open("data/stage2_results.json") as f:
        stage2_results = json.load(f)

    prioritized = triage_exceptions(stage2_results, df_settlements)

    total_at_risk = sum(c["amount_at_risk"] for c in prioritized)

    print(f"Total exceptions: {len(prioritized)}")
    print(f"Total amount at risk: ₹{total_at_risk:,.2f}")
    print(f"\nTop 5 highest-value exceptions:")
    for c in prioritized[:5]:
        print(f"  {c['payment_id']}: ₹{c['amount_at_risk']:,.2f}")