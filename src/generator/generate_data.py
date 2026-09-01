# src/generator/generate_data.py

import pandas as pd
from faker import Faker
import random
from datetime import datetime, timedelta
import json

fake = Faker()
random.seed(42)  

START_DATE = datetime(2026, 8, 1)  # window start
WINDOW_DAYS = 30                   # orders spread across 30 days

class MutationTracker:
    """
    Tracks which payment_ids have already been mutated, to prevent
    accidental double-mutation (unless explicitly building a compound case).
    """
    def __init__(self):
        self.selected_payment_ids = set()
        self.ground_truth_records = []

    def select(self, payment_id: str) -> bool:
        """Returns True if this payment_id is free to mutate, False if already used."""
        if payment_id in self.selected_payment_ids:
            return False
        self.selected_payment_ids.add(payment_id)
        return True

    def log(self, payment_id: str, mutation_type: str, changed_fields: list,
            chain_affected: list, expected_exception: str, expected_outcome: str,
            should_auto_resolve: bool, reasoning_note: str):
        self.ground_truth_records.append({
            "payment_id": payment_id,
            "what_happened": {
                "mutation_type": mutation_type,
                "changed_fields": changed_fields,
                "chain_affected": chain_affected
            },
            "expected_truth": {
                "expected_exception": expected_exception,
                "expected_outcome": expected_outcome,
                "should_auto_resolve": should_auto_resolve,
                "reasoning_note": reasoning_note
            }
        })

def pick_targets(df_payments: pd.DataFrame, tracker: MutationTracker, n: int) -> list:
    """
    Randomly selects n payment_ids that haven't been mutated yet.
    """
    available = df_payments[~df_payments["payment_id"].isin(tracker.selected_payment_ids)]
    candidates = available.sample(n=n, random_state=random.randint(0, 999999))["payment_id"].tolist()
    
    chosen = []
    for pid in candidates:
        if tracker.select(pid):
            chosen.append(pid)
    return chosen

def generate_amount() -> float:
    """
    80% of orders are everyday small-to-mid transactions (₹100 - ₹5,000).
    20% are larger, business-scale payments (₹5,000 - ₹200,000).
    This mimics Razorpay's real skewed transaction distribution.
    """
    if random.random() < 0.8:
        amount = round(random.uniform(100, 5000), 2)
    else:
        amount = round(random.uniform(5000, 200000), 2)
    return amount


def generate_order_time(start_date: datetime, window_days: int = WINDOW_DAYS) -> datetime:
    """
    Spreads orders across the date window, at random times of day —
    payments businesses see activity all day, not just business hours.
    """
    random_days = random.randint(0, window_days)
    random_seconds = random.randint(0, 24 * 60 * 60 - 1)
    return start_date + timedelta(days=random_days, seconds=random_seconds)


def generate_orders(n: int) -> pd.DataFrame:
    """
    Generate n clean orders.
    Fields: order_id, amount, order_time, currency, status
    """
    orders = []

    for i in range(n):
        order_id = f"ORD-{i+1:05d}"
        amount = generate_amount()
        order_time = generate_order_time(START_DATE)
        currency = "INR"
        status = "completed"

        orders.append({
            "order_id": order_id,
            "amount": amount,
            "order_time": order_time,
            "currency": currency,
            "status": status
        })

    df = pd.DataFrame(orders)
    df = df.sort_values("order_time").reset_index(drop=True)  # chronological order
    return df

def generate_payments(df_orders: pd.DataFrame) -> pd.DataFrame:
    """
    Generate one payment per order.
    Fields: payment_id, order_id, amount, gateway, payment_time, status
    """
    payments = []
    
    gateways = ["UPI", "Card", "Netbanking", "Wallet"]
    
    for i, order in df_orders.iterrows():
        payment_id = f"PAY-{i+1:05d}"
        order_id = order["order_id"]
        
        # In clean cases, payment amount == order amount
        amount = order["amount"]
        
        
        payment_time = order["order_time"] + timedelta(seconds=random.randint(2, 50))
        
        gateway = random.choice(gateways)
        status = "success"
        
        payments.append({
            "payment_id": payment_id,
            "order_id": order_id,
            "amount": amount,
            "gateway": gateway,
            "payment_time": payment_time,
            "status": status
        })
    
    return pd.DataFrame(payments)

def generate_refunds(df_payments: pd.DataFrame, refund_rate: float = 0.15) -> pd.DataFrame:
    """
    Generate refunds for a random subset of payments.
    Fields: refund_id, payment_id, refund_amount, refund_time, status
    Not every payment gets a refund — only refund_rate fraction do.
    """
    refunds = []
    refund_counter = 1

    refunded_payments = df_payments.sample(frac=refund_rate, random_state=42)

    for i, payment in refunded_payments.iterrows():
        refund_id = f"REF-{refund_counter:05d}"
        payment_id = payment["payment_id"]

        is_partial = random.random() < 0.7

        if is_partial:
            fraction = random.uniform(0.2, 0.8)
            refund_amount = payment["amount"] * fraction
        else:
            refund_amount = payment["amount"]

        refund_time = payment["payment_time"] + timedelta(
            days=random.randint(1, 5),
            hours=random.randint(0, 23),
            minutes=random.randint(0, 59)
        )

        status = "processed"

        refunds.append({
            "refund_id": refund_id,
            "payment_id": payment_id,
            "refund_amount": round(refund_amount, 2),
            "refund_time": refund_time,
            "status": status
        })
        refund_counter += 1

    return pd.DataFrame(refunds)

def generate_settlements(df_payments: pd.DataFrame, df_refunds: pd.DataFrame) -> pd.DataFrame:
    """
    Generate one settlement per payment.
    Fields: settlement_id, payment_id, gross_amount, fee, tax, net_amount, settlement_time, UTR
    net_amount = gross_amount - refund_amount(if any) - fee - tax
    """
    settlements = []

    # build a quick lookup: payment_id -> total refunded amount (0 if none)
    refund_lookup = df_refunds.groupby("payment_id")["refund_amount"].sum().to_dict()

    for i, payment in df_payments.iterrows():
        settlement_id = f"SET-{i+1:05d}"
        payment_id = payment["payment_id"]
        gross_amount = payment["amount"]

        refund_amount = refund_lookup.get(payment_id, 0)

        fee = gross_amount * 0.02
        tax = fee * 0.18

        net_amount = gross_amount - refund_amount - fee - tax

        settlement_time = payment["payment_time"] + timedelta(
            days=random.randint(1, 3),
            hours=random.randint(0, 23),
            minutes=random.randint(0, 59)
        )

        UTR = f"UTR{random.randint(100000000, 999999999)}"

        settlements.append({
            "settlement_id": settlement_id,
            "payment_id": payment_id,
            "gross_amount": round(gross_amount, 2),
            "fee": round(fee, 2),
            "tax": round(tax, 2),
            "net_amount": round(net_amount, 2),
            "settlement_time": settlement_time,
            "UTR": UTR
        })

    return pd.DataFrame(settlements)

def generate_bank_entries(df_settlements: pd.DataFrame) -> pd.DataFrame:
    """
    Generate one bank entry per settlement (clean pass — no mutations yet).
    Fields: bank_txn_id, UTR, credit_amount, value_date, description
    """
    bank_entries = []

    for i, settlement in df_settlements.iterrows():
        bank_txn_id = f"BANK-{i+1:05d}"

        # In clean cases, UTR matches settlement's UTR exactly (mutations come later)
        UTR = settlement["UTR"]

        # In clean cases, credit_amount == settlement's net_amount
        credit_amount = settlement["net_amount"]

        value_date = settlement["settlement_time"] + timedelta(
            hours=random.randint(2, 23),
            minutes=random.randint(0, 59)
        )

        description = f"NEFT CR {UTR} RAZORPAY SETTLEMENT"

        bank_entries.append({
            "bank_txn_id": bank_txn_id,
            "UTR": UTR,
            "credit_amount": round(credit_amount, 2),
            "value_date": value_date,
            "description": description
        })

    return pd.DataFrame(bank_entries)

def save_to_csv(df_orders, df_payments, df_refunds, df_settlements, df_bank, output_dir="data/raw"):
    """
    Save all five entities to CSV files.
    """
    df_orders.to_csv(f"{output_dir}/orders.csv", index=False)
    df_payments.to_csv(f"{output_dir}/payments.csv", index=False)
    df_refunds.to_csv(f"{output_dir}/refunds.csv", index=False)
    df_settlements.to_csv(f"{output_dir}/settlements.csv", index=False)
    df_bank.to_csv(f"{output_dir}/bank_entries.csv", index=False)
    print(f"\nAll 5 CSVs saved to {output_dir}/")

def mutate_missing_bank(df_bank: pd.DataFrame, df_settlements: pd.DataFrame,
                          tracker: MutationTracker, n: int = 12) -> pd.DataFrame:
    """
    Deletes the bank entry for n randomly selected payment chains.
    Simulates: settlement happened, but the bank credit never landed (or is missing from the feed).
    """
    df_payments_ref = df_settlements[["payment_id", "UTR"]]  # to pick targets from
    
    targets = pick_targets(df_payments_ref, tracker, n)
    
    utrs_to_remove = df_settlements[df_settlements["payment_id"].isin(targets)]["UTR"].tolist()
    
    df_bank_mutated = df_bank[~df_bank["UTR"].isin(utrs_to_remove)].copy()
    
    for pid in targets:
        tracker.log(
            payment_id=pid,
            mutation_type="MISSING_BANK_ENTRY",
            changed_fields=["bank_entry_deleted"],
            chain_affected=["bank"],
            expected_exception="MISSING_BANK_RECORD",
            expected_outcome="ESCALATE",
            should_auto_resolve=False,
            reasoning_note="Settlement exists but no corresponding bank credit was found."
        )
    
    return df_bank_mutated

def mutate_duplicate_bank(df_bank: pd.DataFrame, df_settlements: pd.DataFrame,
                            tracker: MutationTracker, n: int = 8) -> pd.DataFrame:
    """
    Duplicates the bank entry for n randomly selected payment chains.
    Simulates: the same bank credit accidentally appears twice in the feed.
    """
    df_payments_ref = df_settlements[["payment_id", "UTR"]]
    targets = pick_targets(df_payments_ref, tracker, n)

    utrs_to_duplicate = df_settlements[df_settlements["payment_id"].isin(targets)]["UTR"].tolist()

    rows_to_duplicate = df_bank[df_bank["UTR"].isin(utrs_to_duplicate)].copy()

    # give duplicated rows a new bank_txn_id so they're not literally identical rows
    rows_to_duplicate["bank_txn_id"] = rows_to_duplicate["bank_txn_id"] + "-DUP"

    df_bank_mutated = pd.concat([df_bank, rows_to_duplicate], ignore_index=True)

    for pid in targets:
        tracker.log(
            payment_id=pid,
            mutation_type="DUPLICATE_BANK_ENTRY",
            changed_fields=["bank_entry_duplicated"],
            chain_affected=["bank"],
            expected_exception="DUPLICATE_TRANSACTION",
            expected_outcome="REVIEW",
            should_auto_resolve=False,
            reasoning_note="Same bank credit appears twice; must not be silently double-counted or deleted."
        )

    return df_bank_mutated

def mutate_utr_formatting(df_bank: pd.DataFrame, df_settlements: pd.DataFrame,
                            tracker: MutationTracker, n: int = 12) -> pd.DataFrame:
    """
    Reformats the UTR in the bank entry (adds hyphens) so it no longer
    string-matches the settlement's UTR exactly, but represents the same value.
    """
    df_bank_mutated = df_bank.copy()
    df_payments_ref = df_settlements[["payment_id", "UTR"]]
    targets = pick_targets(df_payments_ref, tracker, n)

    for pid in targets:
        utr = df_settlements[df_settlements["payment_id"] == pid]["UTR"].values[0]
        # UTR893276164 -> UTR-893-276-164
        prefix = utr[:3]       # "UTR"
        digits = utr[3:]       # "893276164"
        formatted_utr = f"{prefix}-{digits[0:3]}-{digits[3:6]}-{digits[6:9]}"

        df_bank_mutated.loc[df_bank_mutated["UTR"] == utr, "UTR"] = formatted_utr

        tracker.log(
            payment_id=pid,
            mutation_type="UTR_FORMATTING_MISMATCH",
            changed_fields=["UTR"],
            chain_affected=["bank"],
            expected_exception="UTR_MISMATCH",
            expected_outcome="RESOLVE",
            should_auto_resolve=True,
            reasoning_note="UTR differs only in formatting; normalized values match."
        )

    return df_bank_mutated


def mutate_missing_payment(df_payments: pd.DataFrame, tracker: MutationTracker,
                             n: int = 5) -> pd.DataFrame:
    """
    Removes the payment record entirely, simulating an order that exists
    but whose payment was never recorded on the gateway side.
    """
    targets = pick_targets(df_payments, tracker, n)

    df_payments_mutated = df_payments[~df_payments["payment_id"].isin(targets)].copy()

    for pid in targets:
        tracker.log(
            payment_id=pid,
            mutation_type="MISSING_PAYMENT",
            changed_fields=["payment_deleted"],
            chain_affected=["payment"],
            expected_exception="MISSING_PAYMENT_RECORD",
            expected_outcome="ESCALATE",
            should_auto_resolve=False,
            reasoning_note="Order exists but no payment record was found on the gateway."
        )

    return df_payments_mutated


def mutate_amount_mismatch(df_bank: pd.DataFrame, df_settlements: pd.DataFrame,
                             tracker: MutationTracker, n: int = 8) -> pd.DataFrame:
    """
    Alters the bank credit_amount to an unexplained value —
    doesn't match settlement net_amount by any known deduction.
    """
    df_bank_mutated = df_bank.copy()
    df_payments_ref = df_settlements[["payment_id", "UTR"]]
    targets = pick_targets(df_payments_ref, tracker, n)

    for pid in targets:
        utr = df_settlements[df_settlements["payment_id"] == pid]["UTR"].values[0]
        shift = random.choice([-1, 1]) * random.uniform(50, 2000)

        df_bank_mutated.loc[df_bank_mutated["UTR"] == utr, "credit_amount"] += shift

        tracker.log(
            payment_id=pid,
            mutation_type="AMOUNT_MISMATCH",
            changed_fields=["credit_amount"],
            chain_affected=["bank"],
            expected_exception="UNEXPLAINED_AMOUNT_DIFFERENCE",
            expected_outcome="ESCALATE",
            should_auto_resolve=False,
            reasoning_note="Bank credit does not match settlement net amount after known deductions."
        )

    return df_bank_mutated

def mutate_fee_mismatch(df_settlements: pd.DataFrame, tracker: MutationTracker,
                          n: int = 6) -> pd.DataFrame:
    """
    Alters the fee value after settlement was calculated, creating an
    unexplained discrepancy between what the fee should be and what's recorded.
    """
    df_settlements_mutated = df_settlements.copy()
    targets = pick_targets(df_settlements, tracker, n)

    for pid in targets:
        idx = df_settlements_mutated[df_settlements_mutated["payment_id"] == pid].index[0]
        original_fee = df_settlements_mutated.loc[idx, "fee"]

        new_fee = original_fee * random.uniform(1.3, 2.0)

        df_settlements_mutated.loc[idx, "fee"] = round(new_fee, 2)
        df_settlements_mutated.loc[idx, "net_amount"] = round(
            df_settlements_mutated.loc[idx, "net_amount"] - (new_fee - original_fee), 2
        )

        tracker.log(
            payment_id=pid,
            mutation_type="FEE_MISMATCH",
            changed_fields=["fee", "net_amount"],
            chain_affected=["settlement"],
            expected_exception="FEE_CALCULATION_ERROR",
            expected_outcome="REVIEW",
            should_auto_resolve=False,
            reasoning_note="Recorded fee does not match the standard 2% fee structure."
        )

    return df_settlements_mutated


def mutate_tax_mismatch(df_settlements: pd.DataFrame, tracker: MutationTracker,
                          n: int = 5) -> pd.DataFrame:
    """
    Alters the tax value, simulating incorrect GST calculation on the fee.
    """
    df_settlements_mutated = df_settlements.copy()
    targets = pick_targets(df_settlements, tracker, n)

    for pid in targets:
        idx = df_settlements_mutated[df_settlements_mutated["payment_id"] == pid].index[0]
        original_tax = df_settlements_mutated.loc[idx, "tax"]

        new_tax = original_tax * random.uniform(1.3, 2.0)

        df_settlements_mutated.loc[idx, "tax"] = round(new_tax, 2)
        df_settlements_mutated.loc[idx, "net_amount"] = round(
            df_settlements_mutated.loc[idx, "net_amount"] - (new_tax - original_tax), 2
        )

        tracker.log(
            payment_id=pid,
            mutation_type="TAX_MISMATCH",
            changed_fields=["tax", "net_amount"],
            chain_affected=["settlement"],
            expected_exception="TAX_CALCULATION_ERROR",
            expected_outcome="REVIEW",
            should_auto_resolve=False,
            reasoning_note="Recorded tax does not match the expected 18% GST on fee."
        )

    return df_settlements_mutated


def mutate_delayed_settlement(df_settlements: pd.DataFrame, tracker: MutationTracker,
                                n: int = 12) -> pd.DataFrame:
    """
    Pushes settlement_time significantly further out than normal (beyond
    the usual 1-3 day window), simulating a delayed settlement cycle.
    Should NOT be falsely flagged as missing — it's just late.
    """
    df_settlements_mutated = df_settlements.copy()
    targets = pick_targets(df_settlements, tracker, n)

    for pid in targets:
        idx = df_settlements_mutated[df_settlements_mutated["payment_id"] == pid].index[0]

        extra_delay = timedelta(days=random.randint(5, 10))
        df_settlements_mutated.loc[idx, "settlement_time"] += extra_delay

        tracker.log(
            payment_id=pid,
            mutation_type="DELAYED_SETTLEMENT",
            changed_fields=["settlement_time"],
            chain_affected=["settlement"],
            expected_exception="DELAYED_SETTLEMENT",
            expected_outcome="RESOLVE",
            should_auto_resolve=True,
            reasoning_note="Settlement arrived later than usual but is not missing or incorrect."
        )

    return df_settlements_mutated

def mutate_refund_not_reflected(df_settlements: pd.DataFrame, df_refunds: pd.DataFrame,
                                  tracker: MutationTracker, n: int = 2) -> pd.DataFrame:
    """
    Refund exists, but settlement's net_amount wasn't adjusted for it —
    settlement still shows the pre-refund net amount.
    """
    df_settlements_mutated = df_settlements.copy()

    # only select payment_ids that have a refund AND haven't been mutated yet
    refunded_ids = df_refunds["payment_id"].tolist()
    available = [pid for pid in refunded_ids if pid not in tracker.selected_payment_ids]
    targets = random.sample(available, min(n, len(available)))
    for pid in targets:
        tracker.select(pid)

    for pid in targets:
        idx = df_settlements_mutated[df_settlements_mutated["payment_id"] == pid].index[0]
        refund_amount = df_refunds[df_refunds["payment_id"] == pid]["refund_amount"].values[0]

        # add back the refund amount to net_amount, as if it was never deducted
        df_settlements_mutated.loc[idx, "net_amount"] = round(
            df_settlements_mutated.loc[idx, "net_amount"] + refund_amount, 2
        )

        tracker.log(
            payment_id=pid,
            mutation_type="REFUND_NOT_REFLECTED",
            changed_fields=["net_amount"],
            chain_affected=["settlement", "refund"],
            expected_exception="REFUND_NOT_DEDUCTED",
            expected_outcome="REVIEW",
            should_auto_resolve=False,
            reasoning_note=f"Settlement amount does not reflect the recorded ₹{refund_amount} refund."
        )

    return df_settlements_mutated


def mutate_refund_after_settlement(df_settlements: pd.DataFrame, df_refunds: pd.DataFrame,
                                     tracker: MutationTracker, n: int = 2) -> pd.DataFrame:
    """
    Shifts refund_time to be AFTER settlement_time — merchant already
    received settlement before the refund occurred. Not necessarily an error;
    it creates a subsequent liability rather than a settlement mismatch.
    """
    df_refunds_mutated = df_refunds.copy()

    refunded_ids = df_refunds["payment_id"].tolist()
    available = [pid for pid in refunded_ids if pid not in tracker.selected_payment_ids]
    targets = random.sample(available, min(n, len(available)))
    for pid in targets:
        tracker.select(pid)

    for pid in targets:
        settlement_time = df_settlements[df_settlements["payment_id"] == pid]["settlement_time"].values[0]
        idx = df_refunds_mutated[df_refunds_mutated["payment_id"] == pid].index[0]

        # push refund_time to a few days after settlement_time
        new_refund_time = pd.Timestamp(settlement_time) + timedelta(days=random.randint(1, 4))
        df_refunds_mutated.loc[idx, "refund_time"] = new_refund_time

        tracker.log(
            payment_id=pid,
            mutation_type="REFUND_AFTER_SETTLEMENT",
            changed_fields=["refund_time"],
            chain_affected=["refund", "settlement"],
            expected_exception="REFUND_TIMING_CONFLICT",
            expected_outcome="ESCALATE",
            should_auto_resolve=False,
            reasoning_note="Merchant already received settlement before the refund occurred; this creates a subsequent cash liability, not a settlement calculation error."
        )

    return df_refunds_mutated

def mutate_full_refund_negative_net(df_settlements: pd.DataFrame, df_refunds: pd.DataFrame,
                                      tracker: MutationTracker, n: int = 1) -> pd.DataFrame:
    """
    Picks a full-refund case (refund_amount == payment amount) and confirms/ensures
    net_amount goes negative, explicitly logging this as an expected, non-error pattern.
    """
    df_settlements_mutated = df_settlements.copy()

    # find refunds where refund_amount matches the settlement's gross_amount (full refunds)
    merged = df_refunds.merge(df_settlements[["payment_id", "gross_amount"]], on="payment_id")
    full_refund_ids = merged[abs(merged["refund_amount"] - merged["gross_amount"]) < 1]["payment_id"].tolist()

    available = [pid for pid in full_refund_ids if pid not in tracker.selected_payment_ids]
    targets = random.sample(available, min(n, len(available)))
    for pid in targets:
        tracker.select(pid)

    for pid in targets:
        tracker.log(
            payment_id=pid,
            mutation_type="FULL_REFUND_NEGATIVE_NET",
            changed_fields=[],  # no change needed — already negative from generation
            chain_affected=["settlement", "refund"],
            expected_exception="FULL_REFUND_FEE_LIABILITY",
            expected_outcome="RESOLVE",
            should_auto_resolve=True,
            reasoning_note="Full refund correctly results in negative net_amount; fee is not refunded to merchant."
        )

    return df_settlements_mutated


def mutate_multiple_refunds(df_refunds: pd.DataFrame, df_payments: pd.DataFrame,
                              tracker: MutationTracker, n: int = 1) -> pd.DataFrame:
    """
    Adds a second, smaller refund against a payment that already has one,
    simulating a partial refund issued twice.
    """
    df_refunds_mutated = df_refunds.copy()

    refunded_ids = df_refunds["payment_id"].tolist()
    available = [pid for pid in refunded_ids if pid not in tracker.selected_payment_ids]
    targets = random.sample(available, min(n, len(available)))
    for pid in targets:
        tracker.select(pid)

    new_rows = []
    for pid in targets:
        payment_amount = df_payments[df_payments["payment_id"] == pid]["amount"].values[0]
        existing_refund_time = df_refunds[df_refunds["payment_id"] == pid]["refund_time"].values[0]

        second_refund_amount = round(payment_amount * random.uniform(0.05, 0.15), 2)
        second_refund_time = pd.Timestamp(existing_refund_time) + timedelta(days=random.randint(1, 3))

        new_rows.append({
            "refund_id": f"REF-EXTRA-{pid}",
            "payment_id": pid,
            "refund_amount": second_refund_amount,
            "refund_time": second_refund_time,
            "status": "processed"
        })

        tracker.log(
            payment_id=pid,
            mutation_type="MULTIPLE_REFUNDS",
            changed_fields=["refund_added"],
            chain_affected=["refund", "settlement"],
            expected_exception="MULTIPLE_REFUNDS_UNACCOUNTED",
            expected_outcome="ESCALATE",
            should_auto_resolve=False,
            reasoning_note="A second refund was issued against a payment that already had one; settlement does not reflect the combined total."
        )

    df_refunds_mutated = pd.concat([df_refunds_mutated, pd.DataFrame(new_rows)], ignore_index=True)
    return df_refunds_mutated


def mutate_over_refund(df_refunds: pd.DataFrame, df_payments: pd.DataFrame,
                         tracker: MutationTracker, n: int = 1) -> pd.DataFrame:
    """
    Alters a refund amount to exceed the original payment amount — a clear
    policy violation that should never be silently allowed.
    """
    df_refunds_mutated = df_refunds.copy()

    refunded_ids = df_refunds["payment_id"].tolist()
    available = [pid for pid in refunded_ids if pid not in tracker.selected_payment_ids]
    targets = random.sample(available, min(n, len(available)))
    for pid in targets:
        tracker.select(pid)

    for pid in targets:
        payment_amount = df_payments[df_payments["payment_id"] == pid]["amount"].values[0]
        idx = df_refunds_mutated[df_refunds_mutated["payment_id"] == pid].index[0]

        over_amount = round(payment_amount * random.uniform(1.1, 1.3), 2)
        df_refunds_mutated.loc[idx, "refund_amount"] = over_amount

        tracker.log(
            payment_id=pid,
            mutation_type="OVER_REFUND",
            changed_fields=["refund_amount"],
            chain_affected=["refund"],
            expected_exception="REFUND_EXCEEDS_PAYMENT",
            expected_outcome="REJECT_ACTION",
            should_auto_resolve=False,
            reasoning_note="Refund amount exceeds the original payment amount — a hard policy violation."
        )

    return df_refunds_mutated


def mutate_refund_fee_discrepancy(df_settlements: pd.DataFrame, df_refunds: pd.DataFrame,
                                    tracker: MutationTracker, n: int = 1) -> pd.DataFrame:
    """
    Combines a refund with a fee that wasn't recalculated correctly after the refund —
    compound-ish but kept as a single-focus refund case.
    """
    df_settlements_mutated = df_settlements.copy()

    refunded_ids = df_refunds["payment_id"].tolist()
    available = [pid for pid in refunded_ids if pid not in tracker.selected_payment_ids]
    targets = random.sample(available, min(n, len(available)))
    for pid in targets:
        tracker.select(pid)

    for pid in targets:
        idx = df_settlements_mutated[df_settlements_mutated["payment_id"] == pid].index[0]
        original_fee = df_settlements_mutated.loc[idx, "fee"]
        wrong_fee = round(original_fee * random.uniform(1.2, 1.5), 2)

        df_settlements_mutated.loc[idx, "fee"] = wrong_fee
        df_settlements_mutated.loc[idx, "net_amount"] = round(
            df_settlements_mutated.loc[idx, "net_amount"] - (wrong_fee - original_fee), 2
        )

        tracker.log(
            payment_id=pid,
            mutation_type="REFUND_FEE_DISCREPANCY",
            changed_fields=["fee", "net_amount"],
            chain_affected=["settlement", "refund"],
            expected_exception="REFUND_FEE_RECALCULATION_ERROR",
            expected_outcome="REVIEW",
            should_auto_resolve=False,
            reasoning_note="Fee was not correctly recalculated after refund was processed."
        )

    return df_settlements_mutated
def mutate_compound_A(df_settlements: pd.DataFrame, df_refunds: pd.DataFrame,
                        df_bank: pd.DataFrame, df_payments: pd.DataFrame,
                        tracker: MutationTracker, n: int = 4) -> tuple:
    """
    Compound A: Partial refund + fee mismatch + UTR formatting, on fresh chains.
    """
    df_settlements_mutated = df_settlements.copy()
    df_refunds_mutated = df_refunds.copy()
    df_bank_mutated = df_bank.copy()

    targets = pick_targets(df_payments, tracker, n)
    new_refund_rows = []

    for pid in targets:
        payment_amount = df_payments[df_payments["payment_id"] == pid]["amount"].values[0]
        payment_time = df_payments[df_payments["payment_id"] == pid]["payment_time"].values[0]
        idx = df_settlements_mutated[df_settlements_mutated["payment_id"] == pid].index[0]

        # 1. add a partial refund
        refund_amount = round(payment_amount * random.uniform(0.2, 0.5), 2)
        refund_time = pd.Timestamp(payment_time) + timedelta(days=random.randint(1, 3))
        new_refund_rows.append({
            "refund_id": f"REF-COMPOUND-{pid}",
            "payment_id": pid,
            "refund_amount": refund_amount,
            "refund_time": refund_time,
            "status": "processed"
        })
        df_settlements_mutated.loc[idx, "net_amount"] = round(
            df_settlements_mutated.loc[idx, "net_amount"] - refund_amount, 2
        )

        # 2. fee mismatch
        original_fee = df_settlements_mutated.loc[idx, "fee"]
        new_fee = round(original_fee * random.uniform(1.3, 1.8), 2)
        df_settlements_mutated.loc[idx, "net_amount"] = round(
            df_settlements_mutated.loc[idx, "net_amount"] - (new_fee - original_fee), 2
        )
        df_settlements_mutated.loc[idx, "fee"] = new_fee

        # 3. UTR formatting
        utr = df_settlements_mutated.loc[idx, "UTR"]
        formatted_utr = f"{utr[:3]}-{utr[3:6]}-{utr[6:9]}-{utr[9:12]}"
        df_bank_mutated.loc[df_bank_mutated["UTR"] == utr, "UTR"] = formatted_utr

        tracker.log(
            payment_id=pid,
            mutation_type="COMPOUND_A_REFUND_FEE_UTR",
            changed_fields=["net_amount", "fee", "UTR"],
            chain_affected=["settlement", "refund", "bank"],
            expected_exception="COMPOUND_CASE",
            expected_outcome="ESCALATE",
            should_auto_resolve=False,
            reasoning_note="Partial refund, incorrect fee recalculation, and UTR formatting difference combined on one chain."
        )

    df_refunds_mutated = pd.concat([df_refunds_mutated, pd.DataFrame(new_refund_rows)], ignore_index=True)
    return df_settlements_mutated, df_refunds_mutated, df_bank_mutated

def mutate_compound_B(df_settlements: pd.DataFrame, df_bank: pd.DataFrame,
                        df_payments: pd.DataFrame, tracker: MutationTracker,
                        n: int = 3) -> tuple:
    """
    Compound B: Delayed settlement + missing bank entry, on fresh chains.
    """
    df_settlements_mutated = df_settlements.copy()
    df_bank_mutated = df_bank.copy()

    targets = pick_targets(df_payments, tracker, n)

    for pid in targets:
        idx = df_settlements_mutated[df_settlements_mutated["payment_id"] == pid].index[0]

        # 1. delay settlement
        df_settlements_mutated.loc[idx, "settlement_time"] += timedelta(days=random.randint(5, 10))

        # 2. remove bank entry
        utr = df_settlements_mutated.loc[idx, "UTR"]
        df_bank_mutated = df_bank_mutated[df_bank_mutated["UTR"] != utr]

        tracker.log(
            payment_id=pid,
            mutation_type="COMPOUND_B_DELAYED_MISSING_BANK",
            changed_fields=["settlement_time", "bank_entry_deleted"],
            chain_affected=["settlement", "bank"],
            expected_exception="COMPOUND_CASE",
            expected_outcome="ESCALATE",
            should_auto_resolve=False,
            reasoning_note="Settlement is delayed AND no bank entry has landed yet — ambiguous whether it's just late or genuinely missing."
        )

    return df_settlements_mutated, df_bank_mutated


def mutate_compound_C(df_settlements: pd.DataFrame, df_refunds: pd.DataFrame,
                        df_bank: pd.DataFrame, df_payments: pd.DataFrame,
                        tracker: MutationTracker, n: int = 3) -> tuple:
    """
    Compound C: Full refund + negative net_amount + UTR formatting, on fresh chains.
    """
    df_settlements_mutated = df_settlements.copy()
    df_refunds_mutated = df_refunds.copy()
    df_bank_mutated = df_bank.copy()

    targets = pick_targets(df_payments, tracker, n)
    new_refund_rows = []

    for pid in targets:
        payment_amount = df_payments[df_payments["payment_id"] == pid]["amount"].values[0]
        payment_time = df_payments[df_payments["payment_id"] == pid]["payment_time"].values[0]
        idx = df_settlements_mutated[df_settlements_mutated["payment_id"] == pid].index[0]

        # 1. full refund
        refund_time = pd.Timestamp(payment_time) + timedelta(days=random.randint(1, 3))
        new_refund_rows.append({
            "refund_id": f"REF-COMPOUND-{pid}",
            "payment_id": pid,
            "refund_amount": payment_amount,
            "refund_time": refund_time,
            "status": "processed"
        })
        # net goes negative: full refund minus fee/tax (fee/tax not refunded)
        fee = df_settlements_mutated.loc[idx, "fee"]
        tax = df_settlements_mutated.loc[idx, "tax"]
        df_settlements_mutated.loc[idx, "net_amount"] = round(-(fee + tax), 2)

        # 2. UTR formatting
        utr = df_settlements_mutated.loc[idx, "UTR"]
        formatted_utr = f"{utr[:3]}-{utr[3:6]}-{utr[6:9]}-{utr[9:12]}"
        df_bank_mutated.loc[df_bank_mutated["UTR"] == utr, "UTR"] = formatted_utr
        df_bank_mutated.loc[df_bank_mutated["UTR"] == formatted_utr, "credit_amount"] = df_settlements_mutated.loc[idx, "net_amount"]

        tracker.log(
            payment_id=pid,
            mutation_type="COMPOUND_C_FULLREFUND_NEGATIVE_UTR",
            changed_fields=["net_amount", "UTR", "credit_amount"],
            chain_affected=["settlement", "refund", "bank"],
            expected_exception="COMPOUND_CASE",
            expected_outcome="REVIEW",
            should_auto_resolve=False,
            reasoning_note="Full refund correctly produces negative net_amount, compounded by a UTR formatting difference requiring normalization."
        )

    df_refunds_mutated = pd.concat([df_refunds_mutated, pd.DataFrame(new_refund_rows)], ignore_index=True)
    return df_settlements_mutated, df_refunds_mutated, df_bank_mutated


def mutate_compound_D(df_settlements: pd.DataFrame, df_refunds: pd.DataFrame,
                        df_bank: pd.DataFrame, df_payments: pd.DataFrame,
                        tracker: MutationTracker, n: int = 3) -> tuple:
    """
    Compound D: Amount mismatch + delayed settlement + refund, on fresh chains.
    """
    df_settlements_mutated = df_settlements.copy()
    df_refunds_mutated = df_refunds.copy()
    df_bank_mutated = df_bank.copy()

    targets = pick_targets(df_payments, tracker, n)
    new_refund_rows = []

    for pid in targets:
        payment_amount = df_payments[df_payments["payment_id"] == pid]["amount"].values[0]
        payment_time = df_payments[df_payments["payment_id"] == pid]["payment_time"].values[0]
        idx = df_settlements_mutated[df_settlements_mutated["payment_id"] == pid].index[0]

        # 1. partial refund
        refund_amount = round(payment_amount * random.uniform(0.15, 0.4), 2)
        refund_time = pd.Timestamp(payment_time) + timedelta(days=random.randint(1, 3))
        new_refund_rows.append({
            "refund_id": f"REF-COMPOUND-{pid}",
            "payment_id": pid,
            "refund_amount": refund_amount,
            "refund_time": refund_time,
            "status": "processed"
        })
        df_settlements_mutated.loc[idx, "net_amount"] = round(
            df_settlements_mutated.loc[idx, "net_amount"] - refund_amount, 2
        )

        # 2. delayed settlement
        df_settlements_mutated.loc[idx, "settlement_time"] += timedelta(days=random.randint(5, 10))

        # 3. amount mismatch on bank side
        utr = df_settlements_mutated.loc[idx, "UTR"]
        shift = random.choice([-1, 1]) * random.uniform(50, 500)
        df_bank_mutated.loc[df_bank_mutated["UTR"] == utr, "credit_amount"] += shift

        tracker.log(
            payment_id=pid,
            mutation_type="COMPOUND_D_AMOUNT_DELAYED_REFUND",
            changed_fields=["net_amount", "settlement_time", "credit_amount"],
            chain_affected=["settlement", "refund", "bank"],
            expected_exception="COMPOUND_CASE",
            expected_outcome="ESCALATE",
            should_auto_resolve=False,
            reasoning_note="Refund, delay, and an unexplained bank amount difference together make this a genuinely ambiguous case requiring full investigation."
        )

    df_refunds_mutated = pd.concat([df_refunds_mutated, pd.DataFrame(new_refund_rows)], ignore_index=True)
    return df_settlements_mutated, df_refunds_mutated, df_bank_mutated


def mutate_compound_E(df_settlements: pd.DataFrame, df_bank: pd.DataFrame,
                        df_payments: pd.DataFrame, tracker: MutationTracker,
                        n: int = 3) -> tuple:
    """
    Compound E: Duplicate bank entry + UTR formatting, on fresh chains.
    """
    df_settlements_mutated = df_settlements.copy()
    df_bank_mutated = df_bank.copy()

    targets = pick_targets(df_payments, tracker, n)

    for pid in targets:
        idx = df_settlements_mutated[df_settlements_mutated["payment_id"] == pid].index[0]
        utr = df_settlements_mutated.loc[idx, "UTR"]

        # 1. duplicate the bank row
        original_row = df_bank_mutated[df_bank_mutated["UTR"] == utr].copy()
        original_row["bank_txn_id"] = original_row["bank_txn_id"] + "-DUP"
        df_bank_mutated = pd.concat([df_bank_mutated, original_row], ignore_index=True)

        # 2. reformat UTR on the ORIGINAL row only (duplicate keeps old format)
        formatted_utr = f"{utr[:3]}-{utr[3:6]}-{utr[6:9]}-{utr[9:12]}"
        original_index = df_bank_mutated[(df_bank_mutated["UTR"] == utr) & (~df_bank_mutated["bank_txn_id"].str.endswith("-DUP"))].index
        df_bank_mutated.loc[original_index, "UTR"] = formatted_utr

        tracker.log(
            payment_id=pid,
            mutation_type="COMPOUND_E_DUPLICATE_UTR",
            changed_fields=["bank_entry_duplicated", "UTR"],
            chain_affected=["bank"],
            expected_exception="COMPOUND_CASE",
            expected_outcome="REVIEW",
            should_auto_resolve=False,
            reasoning_note="Duplicate bank credit combined with inconsistent UTR formatting between the two entries."
        )

    return df_settlements_mutated, df_bank_mutated

def save_mutated_data(df_orders, df_payments_mutated, df_refunds_mutated,
                        df_settlements_mutated, df_bank_mutated, tracker,
                        output_dir="data/mutated", ground_truth_dir="data/ground_truth"):
    """
    Saves the final mutated dataset and the ground truth answer key.
    """
    df_orders.to_csv(f"{output_dir}/orders.csv", index=False)
    df_payments_mutated.to_csv(f"{output_dir}/payments.csv", index=False)
    df_refunds_mutated.to_csv(f"{output_dir}/refunds.csv", index=False)
    df_settlements_mutated.to_csv(f"{output_dir}/settlements.csv", index=False)
    df_bank_mutated.to_csv(f"{output_dir}/bank_entries.csv", index=False)

    with open(f"{ground_truth_dir}/ground_truth.json", "w") as f:
        json.dump(tracker.ground_truth_records, f, indent=2, default=str)

    print(f"\nMutated dataset saved to {output_dir}/")
    print(f"Ground truth saved to {ground_truth_dir}/ground_truth.json")
    print(f"Total mutated chains: {len(tracker.ground_truth_records)}")
    print(f"Total clean chains: {200 - len(tracker.selected_payment_ids)}")

if __name__ == "__main__":
    df_orders = generate_orders(200)
    print(df_orders.head(10))
    print(f"\nTotal orders generated: {len(df_orders)}")
    print(f"\nAmount distribution:")
    print(df_orders["amount"].describe())

    df_payments = generate_payments(df_orders)
    print(f"\n--- Payments ---")
    print(df_payments.head(10))
    print(f"\nTotal payments generated: {len(df_payments)}")

    df_refunds = generate_refunds(df_payments)
    print(f"\n--- Refunds ---")
    print(df_refunds.head(10))
    print(f"\nTotal refunds generated: {len(df_refunds)} (out of {len(df_payments)} payments)")

    df_settlements = generate_settlements(df_payments, df_refunds)
    print(f"\n--- Settlements ---")
    print(df_settlements.head(10))
    print(f"\nTotal settlements generated: {len(df_settlements)}")

    df_bank = generate_bank_entries(df_settlements)
    print(f"\n--- Bank Entries ---")
    print(df_bank.head(10))
    print(f"\nTotal bank entries generated: {len(df_bank)}")

    tracker = MutationTracker()
    df_bank_mutated = mutate_missing_bank(df_bank, df_settlements, tracker, n=12)
    
    print(f"\n--- Mutation: Missing Bank Entry ---")
    print(f"Original bank entries: {len(df_bank)}")
    print(f"Mutated bank entries: {len(df_bank_mutated)}")
    print(f"Difference: {len(df_bank) - len(df_bank_mutated)}")
    print(f"\nGround truth records so far: {len(tracker.ground_truth_records)}")
    print(tracker.ground_truth_records[0])  # inspect one record

    df_bank_mutated = mutate_duplicate_bank(df_bank_mutated, df_settlements, tracker, n=8)

    print(f"\n--- Mutation: Duplicate Bank Entry ---")
    print(f"Bank entries after both mutations: {len(df_bank_mutated)}")
    print(f"Ground truth records so far: {len(tracker.ground_truth_records)}")

    df_bank_mutated = mutate_utr_formatting(df_bank_mutated, df_settlements, tracker, n=12)
    df_payments_mutated = mutate_missing_payment(df_payments, tracker, n=5)
    df_bank_mutated = mutate_amount_mismatch(df_bank_mutated, df_settlements, tracker, n=8)

    print(f"\n--- After UTR, Missing Payment, Amount Mismatch mutations ---")
    print(f"Bank entries: {len(df_bank_mutated)}")
    print(f"Payments: {len(df_payments_mutated)} (should be 195)")
    print(f"Ground truth records so far: {len(tracker.ground_truth_records)} (should be 45)")

    df_settlements_mutated = mutate_fee_mismatch(df_settlements, tracker, n=6)
    df_settlements_mutated = mutate_tax_mismatch(df_settlements_mutated, tracker, n=5)
    df_settlements_mutated = mutate_delayed_settlement(df_settlements_mutated, tracker, n=12)

    print(f"\n--- After Fee, Tax, Delayed Settlement mutations ---")
    print(f"Settlements: {len(df_settlements_mutated)} (should still be 200)")
    print(f"Ground truth records so far: {len(tracker.ground_truth_records)} (should be 68)")

    df_settlements_mutated = mutate_refund_not_reflected(df_settlements_mutated, df_refunds, tracker, n=2)
    df_refunds_mutated = mutate_refund_after_settlement(df_settlements_mutated, df_refunds, tracker, n=2)

    print(f"\n--- After Refund mutations (partial set) ---")
    print(f"Ground truth records so far: {len(tracker.ground_truth_records)} (should be 72)")

    df_settlements_mutated = mutate_full_refund_negative_net(df_settlements_mutated, df_refunds, tracker, n=1)
    df_refunds_mutated = mutate_multiple_refunds(df_refunds_mutated, df_payments, tracker, n=1)
    df_refunds_mutated = mutate_over_refund(df_refunds_mutated, df_payments, tracker, n=1)
    df_settlements_mutated = mutate_refund_fee_discrepancy(df_settlements_mutated, df_refunds, tracker, n=1)

    print(f"\n--- After all Refund mutations ---")
    print(f"Ground truth records so far: {len(tracker.ground_truth_records)} (should be 76)")

    df_settlements_mutated, df_refunds_mutated, df_bank_mutated = mutate_compound_A(df_settlements_mutated, df_refunds_mutated, df_bank_mutated, df_payments, tracker, n=4)
    print(f"\n--- After Compound A ---")
    print(f"Ground truth records so far: {len(tracker.ground_truth_records)} (should be 80)")

    df_settlements_mutated, df_bank_mutated = mutate_compound_B(df_settlements_mutated, df_bank_mutated, df_payments, tracker, n=3)
    df_settlements_mutated, df_refunds_mutated, df_bank_mutated = mutate_compound_C(df_settlements_mutated, df_refunds_mutated, df_bank_mutated, df_payments, tracker, n=3)
    df_settlements_mutated, df_refunds_mutated, df_bank_mutated = mutate_compound_D(df_settlements_mutated, df_refunds_mutated, df_bank_mutated, df_payments, tracker, n=3)
    df_settlements_mutated, df_bank_mutated = mutate_compound_E(df_settlements_mutated, df_bank_mutated, df_payments, tracker, n=3)

    print(f"\n--- After all Compound mutations ---")
    print(f"Ground truth records so far: {len(tracker.ground_truth_records)} (should be 92)")

    save_mutated_data(df_orders, df_payments_mutated, df_refunds_mutated,df_settlements_mutated, df_bank_mutated, tracker)