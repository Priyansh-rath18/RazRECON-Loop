# src/matching/match_engine.py

import pandas as pd

def normalize_utr(utr: str) -> str:
    """Level 2+ normalization: uppercase, strip spaces and hyphens."""
    return utr.upper().replace(" ", "").replace("-", "")


def get_candidates(settlement_utr: str, df_bank: pd.DataFrame) -> pd.DataFrame:
    """
    Find all bank rows whose RAW utr matches exactly.
    This is Level 1's candidate pool only — raw match, no normalization.
    """
    return df_bank[df_bank["UTR"] == settlement_utr]


def match_level_1(settlement: pd.Series, df_bank: pd.DataFrame) -> dict:
    """
    Level 1 — EXACT: raw UTR match + exact amount.
    Also safety-checks for duplicates under NORMALIZED UTR, since a raw-UTR-only
    check can miss a duplicate whose UTR formatting was altered on one copy.
    Returns a bank_match result dict, or None if Level 1 doesn't resolve it.
    """
    raw_candidates = get_candidates(settlement["UTR"], df_bank)

    # Safety check: also look for candidates under normalized UTR,
    # so a duplicate hidden by formatting isn't silently missed.
    settlement_utr_normalized = normalize_utr(settlement["UTR"])
    normalized_candidates = df_bank[
        df_bank["UTR"].apply(normalize_utr) == settlement_utr_normalized
    ]

    if len(normalized_candidates) > 1:
        # duplicate exists — whether or not raw UTR caught it
        return {
            "status": "EXCEPTION",
            "method": "NONE",
            "bank_txn_id": None,
            "candidate_bank_txn_ids": normalized_candidates["bank_txn_id"].tolist(),
            "exception_type": "DUPLICATE_BANK_ENTRY",
            "evidence": {"utr_match": True, "amount_difference": None, "date_difference_days": None}
        }

    if len(raw_candidates) == 0:
        return None  # no raw UTR match at all — try Level 2/3

    # exactly one raw-UTR candidate, and confirmed no hidden duplicate — check exact amount
    bank_row = raw_candidates.iloc[0]
    amount_diff = round(abs(settlement["net_amount"] - bank_row["credit_amount"]), 2)

    if amount_diff == 0:
        return {
            "status": "MATCHED",
            "method": "EXACT",
            "bank_txn_id": bank_row["bank_txn_id"],
            "candidate_bank_txn_ids": [bank_row["bank_txn_id"]],
            "exception_type": None,
            "evidence": {"utr_match": True, "amount_difference": 0.0, "date_difference_days": 0}
        }

    return None  # UTR matched but amount didn't — let Level 2 evaluate it

def match_level_2(settlement: pd.Series, df_bank: pd.DataFrame) -> dict:
    """
    Level 2 — CONSTRAINED: normalized UTR + amount tolerance + date window.
    Catches delayed settlements and small rounding differences.
    """
    settlement_utr_normalized = normalize_utr(settlement["UTR"])
    candidates = df_bank[df_bank["UTR"].apply(normalize_utr) == settlement_utr_normalized]

    # duplicates already handled by Level 1's safety check — but re-check here too,
    # since Level 2 might be called independently in some future refactor
    if len(candidates) > 1:
        return {
            "status": "EXCEPTION",
            "method": "NONE",
            "bank_txn_id": None,
            "candidate_bank_txn_ids": candidates["bank_txn_id"].tolist(),
            "exception_type": "DUPLICATE_BANK_ENTRY",
            "evidence": {"utr_match": True, "amount_difference": None, "date_difference_days": None}
        }

    if len(candidates) == 0:
        return None  # no normalized-UTR match either — try Level 3

    bank_row = candidates.iloc[0]
    amount_diff = round(abs(settlement["net_amount"] - bank_row["credit_amount"]), 2)

    settlement_time = pd.Timestamp(settlement["settlement_time"])
    bank_time = pd.Timestamp(bank_row["value_date"])
    date_diff_days = (bank_time - settlement_time).days

    if amount_diff <= 5 and 0 <= date_diff_days <= 10:
        return {
            "status": "MATCHED",
            "method": "CONSTRAINED",
            "bank_txn_id": bank_row["bank_txn_id"],
            "candidate_bank_txn_ids": [bank_row["bank_txn_id"]],
            "exception_type": None,
            "evidence": {"utr_match": True, "amount_difference": amount_diff, "date_difference_days": date_diff_days}
        }

    return None  # normalized UTR matched but amount/date didn't fit tolerance — try Level 3

def normalize_utr_extended(utr: str) -> str:
    """
    Level 3 — extended normalization, for identifier variants beyond
    basic formatting (Level 2 handles spaces/hyphens/case).
    Extend this function as new real-world formatting patterns are observed.
    """
    normalized = normalize_utr(utr)  # base normalization first
    normalized = normalized.replace("/", "")       # slash-separated variants
    normalized = normalized.replace(".", "")        # dot-separated variants
    normalized = normalized.lstrip("0")               # strip leading zero-padding, if any
    return normalized


def match_level_3(settlement: pd.Series, df_bank: pd.DataFrame) -> dict:
    """
    Level 3 — NORMALIZED IDENTIFIER: extended normalization + independent evidence.
    Only fires when Level 2's basic normalization didn't resolve the case.
    Requires amount + date evidence, same tolerance as Level 2 — normalization
    alone should never be sufficient to create a financial match.
    """
    settlement_utr_extended = normalize_utr_extended(settlement["UTR"])
    candidates = df_bank[df_bank["UTR"].apply(normalize_utr_extended) == settlement_utr_extended]

    if len(candidates) > 1:
        return {
            "status": "EXCEPTION", "method": "NONE", "bank_txn_id": None,
            "candidate_bank_txn_ids": candidates["bank_txn_id"].tolist(),
            "exception_type": "DUPLICATE_BANK_ENTRY",
            "evidence": {"utr_match": True, "amount_difference": None, "date_difference_days": None}
        }

    if len(candidates) == 0:
        return None  # genuinely no identifiable match — true exception

    bank_row = candidates.iloc[0]
    amount_diff = round(abs(settlement["net_amount"] - bank_row["credit_amount"]), 2)
    settlement_time = pd.Timestamp(settlement["settlement_time"])
    bank_time = pd.Timestamp(bank_row["value_date"])
    date_diff_days = (bank_time - settlement_time).days

    if amount_diff <= 5 and 0 <= date_diff_days <= 10:
        return {
            "status": "MATCHED", "method": "NORMALIZED_IDENTIFIER",
            "bank_txn_id": bank_row["bank_txn_id"],
            "candidate_bank_txn_ids": [bank_row["bank_txn_id"]],
            "exception_type": None,
            "evidence": {"utr_match": True, "amount_difference": amount_diff, "date_difference_days": date_diff_days}
        }

    return None

def lifecycle_check(payment_id: str, df_payments: pd.DataFrame, df_refunds: pd.DataFrame,
                     df_settlements: pd.DataFrame) -> dict:
    """
    Stage 2B — validates the financial lifecycle against the TRUE expected
    fee/tax formula, not the settlement's own (possibly wrong) fee/tax fields.
    """
    payment = df_payments[df_payments["payment_id"] == payment_id]
    if len(payment) == 0:
        return {"status": "FAIL", "exception_type": "MISSING_PAYMENT_RECORD",
                 "expected_net": None, "actual_net": None}
    payment = payment.iloc[0]

    settlement = df_settlements[df_settlements["payment_id"] == payment_id]
    if len(settlement) == 0:
        return None
    settlement = settlement.iloc[0]

    total_refunds = df_refunds[df_refunds["payment_id"] == payment_id]["refund_amount"].sum()

    # TRUE expected fee/tax, independent of what settlement claims
    expected_fee = round(payment["amount"] * 0.02, 2)
    expected_tax = round(expected_fee * 0.18, 2)
    expected_net = round(payment["amount"] - total_refunds - expected_fee - expected_tax, 2)

    actual_net = settlement["net_amount"]
    net_diff = round(abs(expected_net - actual_net), 2)

    fee_diff = round(abs(settlement["fee"] - expected_fee), 2)
    tax_diff = round(abs(settlement["tax"] - expected_tax), 2)

    # proportional tolerance: flag if difference exceeds ₹0.50 OR 5% of the
    # expected value, whichever is larger — a flat ₹1 threshold under-flags
    # small transactions where even a large relative error is a small absolute one
    fee_tolerance = max(0.5, expected_fee * 0.05)
    tax_tolerance = max(0.5, expected_tax * 0.05)

    if fee_diff > fee_tolerance:
        return {"status": "FAIL", "exception_type": "FEE_MISMATCH",
                 "expected_net": expected_net, "actual_net": actual_net}
    if tax_diff > tax_tolerance:
        return {"status": "FAIL", "exception_type": "TAX_MISMATCH",
                 "expected_net": expected_net, "actual_net": actual_net}

    net_diff = round(abs(expected_net - actual_net), 2)
    net_tolerance = max(1.0, abs(expected_net) * 0.02) 
    if net_diff <= net_tolerance:
        if actual_net < 0:
            return {"status": "PASS", "exception_type": "VALID_NEGATIVE_SETTLEMENT",
                     "expected_net": expected_net, "actual_net": actual_net}
        return {"status": "PASS", "exception_type": None,
                 "expected_net": expected_net, "actual_net": actual_net}

    if total_refunds == 0 and actual_net < 0:
        exception_type = "NEGATIVE_NET_UNEXPLAINED"
    elif total_refunds > 0:
        exception_type = "REFUND_NOT_REFLECTED"
    else:
        exception_type = "AMOUNT_MISMATCH"

    return {"status": "FAIL", "exception_type": exception_type,
             "expected_net": expected_net, "actual_net": actual_net}



def run_stage_2(df_settlements: pd.DataFrame, df_bank: pd.DataFrame,
                 df_payments: pd.DataFrame, df_refunds: pd.DataFrame) -> list:
    """
    Runs Stage 2A (bank matching) + Stage 2B (lifecycle validation) for every
    settlement, producing one combined record per settlement.
    """
    combined_results = []

    for i, settlement in df_settlements.iterrows():
        payment_id = settlement["payment_id"]
        settlement_id = settlement["settlement_id"]

        # --- Stage 2A: bank matching, escalating through levels ---
        bank_result = match_level_1(settlement, df_bank)
        method_tried = "Level 1"
        if bank_result is None:
            bank_result = match_level_2(settlement, df_bank)
            method_tried = "Level 2"
        if bank_result is None:
            bank_result = match_level_3(settlement, df_bank)
            method_tried = "Level 3"

        if bank_result is None:
            # nothing matched at all — true bank-side exception
            candidates = df_bank[df_bank["UTR"].apply(normalize_utr) == normalize_utr(settlement["UTR"])]
            bank_match = {
                "status": "EXCEPTION",
                "method": "NONE",
                "bank_txn_id": None,
                "candidate_bank_txn_ids": candidates["bank_txn_id"].tolist(),
                "exception_type": "MISSING_BANK_ENTRY" if len(candidates) == 0 else "AMOUNT_MISMATCH",
                "evidence": {"utr_match": len(candidates) > 0, "amount_difference": None, "date_difference_days": None}
            }
        else:
            bank_match = bank_result

        # --- Stage 2B: lifecycle validation ---
        lifecycle_result = lifecycle_check(payment_id, df_payments, df_refunds, df_settlements)

        combined_results.append({
            "payment_id": payment_id,
            "settlement_id": settlement_id,
            "bank_match": bank_match,
            "lifecycle_check": lifecycle_result
        })

    return combined_results

if __name__ == "__main__":
    df_settlements = pd.read_csv("data/mutated/settlements.csv")
    df_bank = pd.read_csv("data/mutated/bank_entries.csv")
    df_payments = pd.read_csv("data/mutated/payments.csv")
    df_refunds = pd.read_csv("data/mutated/refunds.csv")

    # Final Stage 2 combined run
    final_results = run_stage_2(df_settlements, df_bank, df_payments, df_refunds)

    fully_clean = sum(1 for r in final_results
                        if r["bank_match"]["status"] == "MATCHED"
                        and r["lifecycle_check"] is not None
                        and r["lifecycle_check"]["status"] == "PASS")
    needs_attention = len(final_results) - fully_clean

    print(f"--- FINAL Stage 2 Combined Results ---")
    print(f"Total settlements: {len(final_results)}")
    print(f"Fully clean (bank matched AND lifecycle passed): {fully_clean}")
    print(f"Needs attention (Stage 4 candidates): {needs_attention}")

    # save combined results for Stage 3 to use
    import json
    with open("data/stage2_results.json", "w") as f:
        json.dump(final_results, f, indent=2, default=str)
    print(f"\nSaved combined results to data/stage2_results.json")