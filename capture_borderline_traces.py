import json
import time
from src.agent.agentic_controller import run_agentic_investigation

CASES_TO_CAPTURE = [
    {"payment_id": "PAY-00136", "amount_at_risk": 0, "label": "Borderline Case (Delay + Small Gap)"},
    {"payment_id": "PAY-00146", "amount_at_risk": 0, "label": "Borderline Case (Fee Margin)"},
    {"payment_id": "PAY-00190", "amount_at_risk": 0, "label": "Borderline Case (Small Refund)"},
]

# pull real amount_at_risk from settlements, same as run_borderline_check.py did
import pandas as pd
df_settlements = pd.read_csv("data/mutated/settlements.csv")
for c in CASES_TO_CAPTURE:
    row = df_settlements[df_settlements["payment_id"] == c["payment_id"]]
    c["amount_at_risk"] = float(row.iloc[0]["gross_amount"]) if len(row) > 0 else 0.0

captured_traces = []

for case in CASES_TO_CAPTURE:
    print(f"\nCapturing trace for {case['payment_id']} ({case['label']})...")
    result = run_agentic_investigation(case["payment_id"], case["amount_at_risk"])
    captured_traces.append({
        "payment_id": case["payment_id"],
        "label": case["label"],
        "amount_at_risk": case["amount_at_risk"],
        "trace": result["tool_call_log"],
        "final_summary": result["final_summary"],
        "turns_used": result["turns_used"]
    })
    time.sleep(15)

# merge into existing captured_traces.json rather than overwriting
with open("data/captured_traces.json") as f:
    existing_traces = json.load(f)

combined = existing_traces + captured_traces

with open("data/captured_traces.json", "w") as f:
    json.dump(combined, f, indent=2, default=str)

print(f"\nAdded {len(captured_traces)} new traces. Total traces now: {len(combined)}")