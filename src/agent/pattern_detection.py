import json
from collections import defaultdict
import pandas as pd


def detect_patterns(audit_trail: list, df_settlements: pd.DataFrame,
                      min_cases: int = 4, min_total_amount: float = 20000.0) -> list:
    """
    Groups exceptions that share a root cause AND fall within a tight
    settlement-date window — a legitimate signal of a batch-level processing
    issue, as opposed to coincidental shared attributes (e.g. gateway, which
    is randomly assigned in this dataset and carries no real signal).

    A cluster only surfaces if it meets BOTH:
    - at least `min_cases` cases (default 4, not 3 — reduces coincidental clustering)
    - total amount at risk above `min_total_amount` (materiality filter)
    """
    settlement_lookup = df_settlements.set_index("payment_id")["settlement_time"].to_dict()

    enriched = []
    for r in audit_trail:
        pid = r["payment_id"]
        if pid not in settlement_lookup:
            continue
        enriched.append({
            "case_id": r["case_id"],
            "payment_id": pid,
            "root_cause": r["agent_investigation"]["root_cause"],
            "amount_at_risk": r["amount_at_risk"],
            "settlement_time": pd.Timestamp(settlement_lookup[pid]),
        })

    root_cause_groups = defaultdict(list)
    for e in enriched:
        if e["root_cause"]:
            root_cause_groups[e["root_cause"]].append(e)

    clusters = []
    for root_cause, members in root_cause_groups.items():
        members_sorted = sorted(members, key=lambda m: m["settlement_time"])
        window = []
        for m in members_sorted:
            if window and (m["settlement_time"] - window[0]["settlement_time"]).days > 3:
                _maybe_add_cluster(clusters, root_cause, window, min_cases, min_total_amount)
                window = [m]
            else:
                window.append(m)
        _maybe_add_cluster(clusters, root_cause, window, min_cases, min_total_amount)

    # sort by materiality — biggest, most concentrated issues first
    clusters.sort(key=lambda c: c["total_amount"], reverse=True)
    return clusters


def _maybe_add_cluster(clusters, root_cause, window, min_cases, min_total_amount):
    if len(window) < min_cases:
        return
    total_amount = sum(m["amount_at_risk"] for m in window)
    if total_amount < min_total_amount:
        return
    clusters.append({
        "cluster_type": "SAME_ROOT_CAUSE_TIME_WINDOW",
        "root_cause": root_cause,
        "label": f"{len(window)} cases: {root_cause} within 3 days",
        "members": [m["case_id"] for m in window],
        "payment_ids": [m["payment_id"] for m in window],
        "total_amount": total_amount,
        "date_range": f"{window[0]['settlement_time'].date()} to {window[-1]['settlement_time'].date()}",
        "insight": (
            f"{len(window)} '{root_cause}' exceptions, totaling ₹{total_amount:,.2f}, settled within a "
            f"3-day window ({window[0]['settlement_time'].date()} to {window[-1]['settlement_time'].date()}). "
            f"This concentration is consistent with a batch-level processing issue during that period, "
            f"rather than {len(window)} independent, unrelated problems."
        )
    })


if __name__ == "__main__":
    with open("data/audit_trail.json") as f:
        audit_trail = json.load(f)

    df_settlements = pd.read_csv("data/mutated/settlements.csv")

    clusters = detect_patterns(audit_trail, df_settlements)

    print(f"Found {len(clusters)} materially significant pattern cluster(s)")
    for c in clusters:
        print(f"\n{c['label']} — ₹{c['total_amount']:,.2f} ({c['date_range']})")
        print(f"  Cases: {c['members']}")

    with open("data/pattern_clusters.json", "w") as f:
        json.dump(clusters, f, indent=2, default=str)