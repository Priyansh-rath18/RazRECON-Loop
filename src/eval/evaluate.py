# src/eval/evaluate.py

import json
import pandas as pd

def load_ground_truth(path="data/ground_truth/ground_truth.json") -> dict:
    """
    Loads ground truth and converts it into a dict keyed by payment_id
    for fast lookup. Payment_ids NOT in this dict are implicitly "should be clean".
    """
    with open(path, "r") as f:
        records = json.load(f)

    lookup = {r["payment_id"]: r for r in records}
    return lookup


def load_stage2_results(path="data/stage2_results.json") -> list:
    with open(path, "r") as f:
        return json.load(f)

def classify_result(actual_record: dict, ground_truth_lookup: dict) -> str:
    """
    Compares one settlement's actual Stage 2 output against its expected outcome,
    using the ground truth's should_auto_resolve field rather than a blunt
    "in ground truth = should not be clean" assumption.

      - TRUE_CLEAN: correctly resolved as clean (untouched, or a mutation that
                    SHOULD auto-resolve, e.g. UTR formatting, delayed settlement)
      - TRUE_EXCEPTION: correctly flagged as needing attention
      - FALSE_CLEAN: should have been flagged (should_auto_resolve=False), but
                     Stage 2 marked it clean anyway — the dangerous case
      - FALSE_EXCEPTION: should have auto-resolved, but Stage 2 flagged it
                         unnecessarily — a false positive, annoying not dangerous
    """
    payment_id = actual_record["payment_id"]

    actually_clean = (
        actual_record["bank_match"]["status"] == "MATCHED"
        and actual_record["lifecycle_check"] is not None
        and actual_record["lifecycle_check"]["status"] == "PASS"
    )

    if payment_id in ground_truth_lookup:
        expected_clean = ground_truth_lookup[payment_id]["expected_truth"]["should_auto_resolve"]
    else:
        expected_clean = True  # untouched chain — should always be clean

    if expected_clean and actually_clean:
        classification = "TRUE_CLEAN"
    elif not expected_clean and not actually_clean:
        classification = "TRUE_EXCEPTION"
    elif not expected_clean and actually_clean:
        classification = "FALSE_CLEAN"
    else:
        classification = "FALSE_EXCEPTION"

    return classification

    # what Stage 2 actually concluded
    actually_clean = (
        actual_record["bank_match"]["status"] == "MATCHED"
        and actual_record["lifecycle_check"] is not None
        and actual_record["lifecycle_check"]["status"] == "PASS"
    )

    # what SHOULD have happened, per ground truth (or implicit "clean" if absent)
    if payment_id in ground_truth_lookup:
        expected_clean = False  # anything in ground_truth was deliberately mutated — should NOT be clean
    else:
        expected_clean = True   # no ground truth entry = untouched chain = should be clean

    if expected_clean and actually_clean:
        classification = "TRUE_CLEAN"
    elif not expected_clean and not actually_clean:
        classification = "TRUE_EXCEPTION"
    elif not expected_clean and actually_clean:
        classification = "FALSE_CLEAN"
    else:  # expected_clean and not actually_clean
        classification = "FALSE_EXCEPTION"

    return classification

def compute_metrics(classifications: list) -> dict:
    """
    Converts raw classification counts into the named evaluation metrics
    from the project blueprint.
    """
    from collections import Counter
    counts = Counter(classifications)

    true_clean = counts.get("TRUE_CLEAN", 0)
    true_exception = counts.get("TRUE_EXCEPTION", 0)
    false_clean = counts.get("FALSE_CLEAN", 0)
    false_exception = counts.get("FALSE_EXCEPTION", 0)

    total = true_clean + true_exception + false_clean + false_exception

    # Match rate: overall correctness across the whole dataset
    match_rate = round((true_clean + true_exception) / total, 4) if total > 0 else 0

    # Exception precision: of everything WE flagged as an exception, how many really were
    flagged_as_exception = true_exception + false_exception
    exception_precision = round(true_exception / flagged_as_exception, 4) if flagged_as_exception > 0 else None

    # Exception recall: of everything that SHOULD have been flagged, how many did we catch
    should_have_been_flagged = true_exception + false_clean
    exception_recall = round(true_exception / should_have_been_flagged, 4) if should_have_been_flagged > 0 else None

    # False-resolution rate: of cases that should've been flagged, how many did we silently mark clean
    # this is the critical safety metric from the blueprint
    false_resolution_rate = round(false_clean / should_have_been_flagged, 4) if should_have_been_flagged > 0 else 0

    return {
        "total_records": total,
        "true_clean": true_clean,
        "true_exception": true_exception,
        "false_clean": false_clean,
        "false_exception": false_exception,
        "match_rate": match_rate,
        "exception_precision": exception_precision,
        "exception_recall": exception_recall,
        "false_resolution_rate": false_resolution_rate
    }


if __name__ == "__main__":
    ground_truth_lookup = load_ground_truth()
    stage2_results = load_stage2_results()

    classifications = [classify_result(r, ground_truth_lookup) for r in stage2_results]

    from collections import Counter
    print(Counter(classifications))
        # Diagnose what's inside FALSE_CLEAN
    false_clean_ids = [
        r["payment_id"] for r, c in zip(stage2_results, classifications) if c == "FALSE_CLEAN"
    ]

    print(f"\n--- FALSE_CLEAN breakdown by mutation type ---")
    from collections import Counter
    mutation_types_missed = Counter(
        ground_truth_lookup[pid]["what_happened"]["mutation_type"]
        for pid in false_clean_ids
    )
    for mtype, count in mutation_types_missed.most_common():
        print(f"  {mtype}: {count}")
        # Isolate the 2 TAX_MISMATCH false-clean cases specifically
    tax_mismatch_missed = [
        pid for pid, gt in ground_truth_lookup.items()
        if gt["what_happened"]["mutation_type"] == "TAX_MISMATCH"
    ]

    print(f"\n--- All TAX_MISMATCH ground truth entries ---")
    for pid in tax_mismatch_missed:
        print(pid)

    # cross-reference with settlements to see actual fee/tax values
    df_settlements = pd.read_csv("data/mutated/settlements.csv")
    df_payments = pd.read_csv("data/mutated/payments.csv")

    for pid in tax_mismatch_missed:
        settlement = df_settlements[df_settlements["payment_id"] == pid].iloc[0]
        payment = df_payments[df_payments["payment_id"] == pid].iloc[0]

        expected_fee = round(payment["amount"] * 0.02, 2)
        expected_tax = round(expected_fee * 0.18, 2)

        print(f"\n{pid}:")
        print(f"  payment amount: {payment['amount']}")
        print(f"  actual fee: {settlement['fee']}  |  expected fee: {expected_fee}  |  fee_diff: {round(abs(settlement['fee'] - expected_fee), 2)}")
        print(f"  actual tax: {settlement['tax']}  |  expected tax: {expected_tax}  |  tax_diff: {round(abs(settlement['tax'] - expected_tax), 2)}")

    metrics = compute_metrics(classifications)

    print(f"\n--- Stage 3: Evaluation Metrics ---")
    print(f"Total records evaluated: {metrics['total_records']}")
    print(f"Match rate: {metrics['match_rate']*100:.1f}%")
    print(f"Exception precision: {metrics['exception_precision']*100:.1f}%")
    print(f"Exception recall: {metrics['exception_recall']*100:.1f}%")
    print(f"False-resolution rate: {metrics['false_resolution_rate']*100:.1f}%")
    print(f"\nRaw counts: TRUE_CLEAN={metrics['true_clean']}, TRUE_EXCEPTION={metrics['true_exception']}, "
          f"FALSE_CLEAN={metrics['false_clean']}, FALSE_EXCEPTION={metrics['false_exception']}")
    with open("data/eval_metrics.json", "w") as f:
        json.dump(metrics, f, indent=2, default=str)
    print(f"\nSaved evaluation metrics to data/eval_metrics.json")