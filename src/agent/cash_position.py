import pandas as pd
import json
from datetime import datetime, timedelta


OPENING_CASH = 1000000.0  # ₹10,00,000 baseline, for demo purposes


def calculate_cash_position(df_settlements: pd.DataFrame, df_refunds: pd.DataFrame,
                              df_bank: pd.DataFrame, prioritized_exceptions: list,
                              horizon_days: int, reference_date: datetime) -> dict:
    """
    Projects cash position over the given horizon:
    opening_cash + expected_inflows - expected_outflows, with unresolved
    exceptions surfaced separately as cash uncertainty.
    """
    horizon_end = reference_date + timedelta(days=horizon_days)

    # Expected inflows: settlements within horizon that have NOT yet been
    # confirmed by a matching bank entry (i.e., money expected but not yet landed)
    matched_utrs = set(df_bank["UTR"].str.replace("-", "").str.upper())

    df_settlements_copy = df_settlements.copy()
    df_settlements_copy["settlement_time"] = pd.to_datetime(df_settlements_copy["settlement_time"])
    df_settlements_copy["utr_normalized"] = df_settlements_copy["UTR"].str.replace("-", "").str.upper()

    pending_settlements = df_settlements_copy[
        (df_settlements_copy["settlement_time"] <= horizon_end)
        & (~df_settlements_copy["utr_normalized"].isin(matched_utrs))
    ]
    expected_inflows = pending_settlements["net_amount"].clip(lower=0).sum()

    # Expected outflows: refunds within horizon
    df_refunds_copy = df_refunds.copy()
    df_refunds_copy["refund_time"] = pd.to_datetime(df_refunds_copy["refund_time"])
    pending_refunds = df_refunds_copy[df_refunds_copy["refund_time"] <= horizon_end]
    expected_outflows = pending_refunds["refund_amount"].sum()

    # Cash uncertainty: total amount at risk from unresolved exceptions
    # (already prioritized/sorted by triage)
    cash_uncertainty = sum(c["amount_at_risk"] for c in prioritized_exceptions)

    projected_cash = OPENING_CASH + expected_inflows - expected_outflows

    return {
        "horizon_days": horizon_days,
        "opening_cash": OPENING_CASH,
        "expected_inflows": round(float(expected_inflows), 2),
        "expected_outflows": round(float(expected_outflows), 2),
        "projected_cash": round(float(projected_cash), 2),
        "cash_uncertainty": round(float(cash_uncertainty), 2),
        "top_uncertainty_contributors": [
            {"payment_id": c["payment_id"], "amount_at_risk": c["amount_at_risk"]}
            for c in prioritized_exceptions[:3]
        ]
    }


def cash_forecast(df_settlements, df_refunds, df_bank, prioritized_exceptions,
                    reference_date: datetime = None) -> list:
    """
    Produces the standard 1/3/7-day cash forecast.
    """
    if reference_date is None:
        reference_date = datetime.now()

    return [
        calculate_cash_position(df_settlements, df_refunds, df_bank, prioritized_exceptions,
                                  horizon_days=h, reference_date=reference_date)
        for h in [1, 3, 7]
    ]


if __name__ == "__main__":
    from src.agent.triage import triage_exceptions

    df_settlements = pd.read_csv("data/mutated/settlements.csv")
    df_refunds = pd.read_csv("data/mutated/refunds.csv")
    df_bank = pd.read_csv("data/mutated/bank_entries.csv")

    with open("data/stage2_results.json") as f:
        stage2_results = json.load(f)

    prioritized = triage_exceptions(stage2_results, df_settlements)

    forecast = cash_forecast(df_settlements, df_refunds, df_bank, prioritized,
                               reference_date=datetime(2026, 8, 15))

    for f in forecast:
        print(f"\n--- {f['horizon_days']}-day forecast ---")
        print(f"Opening cash: ₹{f['opening_cash']:,.2f}")
        print(f"Expected inflows: ₹{f['expected_inflows']:,.2f}")
        print(f"Expected outflows: ₹{f['expected_outflows']:,.2f}")
        print(f"Projected cash: ₹{f['projected_cash']:,.2f}")
        print(f"Cash uncertainty (unresolved exceptions): ₹{f['cash_uncertainty']:,.2f}")
        print(f"Top contributors to uncertainty:")
        for c in f["top_uncertainty_contributors"]:
            print(f"  {c['payment_id']}: ₹{c['amount_at_risk']:,.2f}")