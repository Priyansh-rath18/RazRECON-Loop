import json
from src.agent.agentic_controller import run_agentic_investigation
import time
# 5 cases chosen to span different root causes and outcomes
CASES_TO_CAPTURE = [
    {"payment_id": "PAY-00046", "amount_at_risk": 172425.68, "label": "Missing Bank Entry (High Value)"},
    {"payment_id": "PAY-00069", "amount_at_risk": 3374.12, "label": "Over-Refund (Blocked Action)"},
    {"payment_id": "PAY-00004", "amount_at_risk": 37104.24, "label": "Duplicate Transaction (Auto-Resolved)"},
    {"payment_id": "PAY-00065", "amount_at_risk": 167174.78, "label": "Amount Mismatch"},
    {"payment_id": "PAY-00151", "amount_at_risk": 21694.53, "label": "Tax Mismatch"},
]

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

with open("data/captured_traces.json", "w") as f:
    json.dump(captured_traces, f, indent=2, default=str)

print(f"\nSaved {len(captured_traces)} traces to data/captured_traces.json")