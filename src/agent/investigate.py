import pandas as pd
import sys
sys.path.append("../matching")  # adjust if needed depending on how you run it
from src.matching.match_engine import normalize_utr

def gather_related_records(payment_id: str, df_orders, df_payments, df_refunds,
                             df_settlements, df_bank) -> dict:
    """
    Gathers the full financial lifecycle for one payment_id —
    order, payment, refund(s), settlement, bank entry.
    """
    payment_row = df_payments[df_payments["payment_id"] == payment_id]
    payment = payment_row.iloc[0].to_dict() if len(payment_row) > 0 else None

    order = None
    if payment is not None:
        order_row = df_orders[df_orders["order_id"] == payment["order_id"]]
        if len(order_row) > 0:
            order = order_row.iloc[0].to_dict()

    refund_rows = df_refunds[df_refunds["payment_id"] == payment_id]
    refunds = refund_rows.to_dict(orient="records") if len(refund_rows) > 0 else []

    settlement_row = df_settlements[df_settlements["payment_id"] == payment_id]
    settlement = settlement_row.iloc[0].to_dict() if len(settlement_row) > 0 else None

    bank_entries = []
    if settlement is not None:
        bank_rows = df_bank[df_bank["UTR"].apply(normalize_utr) == normalize_utr(settlement["UTR"])]
        if len(bank_rows) > 0:
            bank_entries = bank_rows.to_dict(orient="records")

    return {
        "payment_id": payment_id,
        "order": order,
        "payment": payment,
        "refunds": refunds,
        "settlement": settlement,
        "bank_entries": bank_entries
    }


if __name__ == "__main__":
    import json

    df_orders = pd.read_csv("data/mutated/orders.csv")
    df_payments = pd.read_csv("data/mutated/payments.csv")
    df_refunds = pd.read_csv("data/mutated/refunds.csv")
    df_settlements = pd.read_csv("data/mutated/settlements.csv")
    df_bank = pd.read_csv("data/mutated/bank_entries.csv")

    with open("data/stage2_results.json") as f:
        stage2_results = json.load(f)

    # find one exception case to test on
    exception_case = next(r for r in stage2_results if r["bank_match"]["status"] == "EXCEPTION")
    test_payment_id = exception_case["payment_id"]

    print(f"Testing on: {test_payment_id}")
    result = gather_related_records(test_payment_id, df_orders, df_payments, df_refunds,
                                       df_settlements, df_bank)
    print(json.dumps(result, indent=2, default=str))