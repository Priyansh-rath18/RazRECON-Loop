import pandas as pd
import random
from datetime import timedelta
import sys

sys.path.append(".")
from src.generator.generate_data import MutationTracker, pick_targets

random.seed(99)  # different seed, so these are genuinely fresh cases


def seed_borderline_cases(df_orders, df_payments, df_refunds, df_settlements, df_bank,
                            tracker: MutationTracker, n: int = 5):
    """
    Seeds deliberately borderline/ambiguous cases — small enough discrepancies
    that RESOLVE is plausible, but not certain enough for high confidence.
    Designed to test whether the policy engine's REVIEW band (0.75-0.89
    confidence + RESOLVE recommendation) can genuinely be reached.
    """
    df_settlements_mutated = df_settlements.copy()
    df_bank_mutated = df_bank.copy()
    df_refunds_mutated = df_refunds.copy()

    targets = pick_targets(df_payments, tracker, n)

    for i, pid in enumerate(targets):
        idx = df_settlements_mutated[df_settlements_mutated["payment_id"] == pid].index[0]
        utr = df_settlements_mutated.loc[idx, "UTR"]

        if i == 0:
            formatted_utr = f"{utr[:3]}-{utr[3:6]}-{utr[6:9]}-{utr[9:12]}"
            df_bank_mutated.loc[df_bank_mutated["UTR"] == utr, "UTR"] = formatted_utr
            small_gap = round(random.uniform(3, 8), 2)
            df_bank_mutated.loc[df_bank_mutated["UTR"] == formatted_utr, "credit_amount"] += small_gap
            reason = "Small unexplained amount gap combined with UTR formatting difference"

        elif i == 1:
            df_settlements_mutated.loc[idx, "settlement_time"] += timedelta(days=random.randint(5, 6))
            small_gap = round(random.uniform(2, 6), 2)
            df_bank_mutated.loc[df_bank_mutated["UTR"] == utr, "credit_amount"] += small_gap
            reason = "Borderline settlement delay with a small amount gap"

        elif i == 2:
            payment_amount = df_payments[df_payments["payment_id"] == pid]["amount"].values[0]
            payment_time = df_payments[df_payments["payment_id"] == pid]["payment_time"].values[0]
            small_refund = round(payment_amount * random.uniform(0.02, 0.05), 2)
            new_refund = {
                "refund_id": f"REF-BORDERLINE-{pid}",
                "payment_id": pid,
                "refund_amount": small_refund,
                "refund_time": pd.Timestamp(payment_time) + timedelta(days=2),
                "status": "processed"
            }
            df_refunds_mutated = pd.concat([df_refunds_mutated, pd.DataFrame([new_refund])], ignore_index=True)
            reason = "Very small partial refund not yet reflected in settlement"

        elif i == 3:
            unusual_utr = f"{utr[:3]}.{utr[3:6]}.{utr[6:9]}.{utr[9:12]}"
            df_bank_mutated.loc[df_bank_mutated["UTR"] == utr, "UTR"] = unusual_utr
            reason = "Unusual UTR formatting variant (dot-separated) not previously seen"

        else:
            original_fee = df_settlements_mutated.loc[idx, "fee"]
            small_fee_shift = round(original_fee * random.uniform(1.06, 1.12), 2)
            df_settlements_mutated.loc[idx, "net_amount"] = round(
                df_settlements_mutated.loc[idx, "net_amount"] - (small_fee_shift - original_fee), 2
            )
            df_settlements_mutated.loc[idx, "fee"] = small_fee_shift
            reason = "Fee slightly outside tolerance by a small, ambiguous margin"

        tracker.log(
            payment_id=pid,
            mutation_type="BORDERLINE_CASE",
            changed_fields=["various_small"],
            chain_affected=["settlement", "bank", "refund"],
            expected_exception="AMBIGUOUS_MINOR_DISCREPANCY",
            expected_outcome="REVIEW",
            should_auto_resolve=False,
            reasoning_note=reason
        )

    return df_settlements_mutated, df_bank_mutated, df_refunds_mutated


if __name__ == "__main__":
    import json

    df_orders = pd.read_csv("data/mutated/orders.csv")

    df_payments = pd.read_csv("data/mutated/payments.csv")
    df_payments["payment_time"] = pd.to_datetime(df_payments["payment_time"])

    df_refunds = pd.read_csv("data/mutated/refunds.csv")
    df_refunds["refund_time"] = pd.to_datetime(df_refunds["refund_time"])

    df_settlements = pd.read_csv("data/mutated/settlements.csv")
    df_settlements["settlement_time"] = pd.to_datetime(df_settlements["settlement_time"])

    df_bank = pd.read_csv("data/mutated/bank_entries.csv")

    with open("data/ground_truth/ground_truth.json") as f:
        existing_ground_truth = json.load(f)

    tracker = MutationTracker()
    tracker.selected_payment_ids = {r["payment_id"] for r in existing_ground_truth}
    tracker.ground_truth_records = []

    df_settlements_new, df_bank_new, df_refunds_new = seed_borderline_cases(
        df_orders, df_payments, df_refunds, df_settlements, df_bank, tracker, n=5
    )

    print(f"New borderline cases created: {len(tracker.ground_truth_records)}")
    for r in tracker.ground_truth_records:
        print(f"  {r['payment_id']}: {r['expected_truth']['reasoning_note']}")

    df_settlements_new.to_csv("data/mutated/settlements.csv", index=False)
    df_bank_new.to_csv("data/mutated/bank_entries.csv", index=False)
    df_refunds_new.to_csv("data/mutated/refunds.csv", index=False)

    combined_ground_truth = existing_ground_truth + tracker.ground_truth_records
    with open("data/ground_truth/ground_truth.json", "w") as f:
        json.dump(combined_ground_truth, f, indent=2, default=str)

    print(f"\nUpdated data/mutated/ files and ground_truth.json")
    print(f"Total ground truth records now: {len(combined_ground_truth)}")