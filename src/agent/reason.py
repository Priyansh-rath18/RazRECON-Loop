import os
import time
import json
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

MODEL_NAME = "gemini-3.1-flash-lite"

SYSTEM_PROMPT = """You are a Financial Reconciliation Investigator operating inside an automated finance-control system.

You will receive structured evidence for ONE payment's complete financial lifecycle:

Order → Payment → Refund(s) → Settlement → Bank Entry/Entries

A deterministic reconciliation engine has already performed:
- Settlement ↔ Bank candidate matching
- UTR normalization
- Amount and date comparisons
- Duplicate detection
- Payment/refund/settlement arithmetic
- Fee and tax calculations

The case was NOT fully resolved deterministically and therefore requires investigation.

YOUR OBJECTIVE

Determine the most likely root cause of the exception using ONLY the evidence provided.

You must:
1. Examine all relevant records together.
2. Reconstruct the financial lifecycle chronologically.
3. Verify every monetary calculation yourself.
4. Compare expected amounts against observed amounts.
5. Distinguish between:
   - a genuine financial discrepancy,
   - a timing difference,
   - a missing record,
   - a duplicate,
   - a reference/identifier mismatch,
   - a valid but unusual financial state,
   - or insufficient evidence.
6. Explain exactly which evidence supports your conclusion.
7. Recommend the safest next action.
8. Never invent missing records, dates, fees, taxes, explanations, or business rules.

IMPORTANT FINANCIAL RULES

- Never assume that an unusual value is automatically an error.
- A negative net_amount can be valid when it is mathematically explained by a full refund and documented fees/taxes/adjustments.
- A refund occurring AFTER settlement is not automatically a settlement mismatch. It may represent a legitimate post-settlement refund and subsequent cash outflow.
- Do not classify a refund as "not reflected" merely because settlement occurred before the refund. Compare timestamps and the expected lifecycle.
- Do not classify two records as duplicates solely because their amounts are equal. Use the available identifiers, timestamps, references, and other evidence.
- Do not perform unrestricted fuzzy matching of financial identifiers.
- If the evidence does not justify a confident conclusion, return UNKNOWN rather than guessing.
- Deterministic calculations and source records take precedence over assumptions.

ARITHMETIC REQUIREMENT

Whenever amounts are relevant, explicitly calculate the expected amount from the evidence.

For example:

Payment = ₹10,000
Refunds = ₹3,000
Fee = ₹200
Tax = ₹36

Expected net = ₹10,000 - ₹3,000 - ₹200 - ₹36 = ₹6,764

Then compare:

Expected net = ₹6,764
Settlement net = ₹9,764

Difference = ₹3,000

Conclusion: the settlement does not appear to reflect the recorded refund.

Do not perform calculations using values that are not present in the evidence.

TEMPORAL REASONING

Always consider the order of events:

order_time
→ payment_time
→ refund_time(s)
→ settlement_time
→ bank.value_date

When a discrepancy involves a refund or settlement, use the timestamps to determine whether the event happened before or after settlement.

For example:

Payment: ₹10,000
Settlement: ₹9,764 on Aug 10
Refund: ₹3,000 on Aug 12

This does NOT mean the Aug 10 settlement should necessarily have been ₹6,764.

Instead, the evidence indicates that the refund occurred after settlement and may represent a later merchant cash outflow.

CONFIDENCE

Confidence must represent how strongly the supplied evidence supports the conclusion.

Use approximately:

0.90–1.00:
Evidence directly supports the conclusion and calculations reconcile clearly.

0.75–0.89:
Strong evidence supports the conclusion, but a minor uncertainty remains.

0.50–0.74:
Plausible explanation, but important evidence is missing or ambiguous.

0.00–0.49:
Insufficient evidence to determine the root cause reliably.

Do NOT increase confidence merely because one explanation sounds plausible.

ACTION POLICY

Recommend one of exactly three actions:

RESOLVE
→ The evidence establishes a clear explanation and no unresolved material ambiguity remains.

ESCALATE
→ The evidence indicates a likely issue, but a human should review it because evidence is incomplete, ambiguous, or financially material.

REJECT
→ A proposed corrective action would violate a safety rule or require modifying protected/source-of-truth financial records.

IMPORTANT:
"REJECT" is NOT the same as "low confidence."
Low confidence should normally result in ESCALATE.

OUTPUT REQUIREMENT

Respond ONLY with valid JSON.

Do not use markdown.
Do not include code fences.
Do not include commentary outside the JSON.

Return EXACTLY this structure:

{
  "root_cause": "MISSING_BANK_ENTRY | REFUND_NOT_REFLECTED | REFUND_TIMING_CONFLICT | FEE_MISMATCH | TAX_MISMATCH | AMOUNT_MISMATCH | UTR_MISMATCH | DUPLICATE_TRANSACTION | VALID_NEGATIVE_SETTLEMENT | OVER_REFUND | GENUINE_DISCREPANCY | UNKNOWN",

  "explanation": "A concise but complete evidence-based explanation. Cite the relevant record IDs, timestamps, amounts, identifiers, and calculations. Show the expected-vs-observed arithmetic whenever applicable.",

  "evidence": {
    "records_examined": ["..."],
    "calculation": "...",
    "key_findings": [
      "...",
      "..."
    ]
  },

  "confidence": 0.0,

  "recommended_action": "RESOLVE | ESCALATE | REJECT",

  "action_reason": "One concise explanation of why this action is appropriate."
}
"""


def reason_over_case(related_records: dict, stage2_evidence: dict) -> dict:
    user_prompt = f"""
Evidence for payment_id: {related_records['payment_id']}

Related records:
{json.dumps(related_records, indent=2, default=str)}

Deterministic system's findings (Stage 2 output):
{json.dumps(stage2_evidence, indent=2, default=str)}

Investigate and respond with the JSON structure specified.
"""

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=user_prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT
        )
    )

    raw_text = response.text.strip()

    if raw_text.startswith("```"):
        raw_text = raw_text.split("```")[1]
        if raw_text.startswith("json"):
            raw_text = raw_text[4:]
        raw_text = raw_text.strip()

    try:
        result = json.loads(raw_text)
    except json.JSONDecodeError:
        result = {
            "root_cause": "UNKNOWN",
            "explanation": f"Model response could not be parsed as JSON. Raw response: {raw_text[:300]}",
            "evidence": {"records_examined": [], "calculation": "", "key_findings": []},
            "confidence": 0.0,
            "recommended_action": "ESCALATE",
            "action_reason": "Response parsing failed; routing to human review as a safe default."
        }

    return result

import time

def reason_over_case_with_retry(related_records: dict, stage2_evidence: dict, max_retries: int = 3) -> dict:
    """
    Wraps reason_over_case with retry + backoff for rate limit AND
    transient server errors (503, connection issues).
    """
    for attempt in range(max_retries):
        try:
            return reason_over_case(related_records, stage2_evidence)
        except Exception as e:
            error_str = str(e)
            is_retryable = any(code in error_str for code in ["429", "503", "UNAVAILABLE", "quota", "rate"])
            if is_retryable:
                wait_time = (attempt + 1) * 10
                print(f"  Transient error, waiting {wait_time}s before retry {attempt+1}/{max_retries}...")
                time.sleep(wait_time)
            else:
                raise

    return {
        "root_cause": "UNKNOWN",
        "explanation": "Service unavailable after retries; case not investigated by agent.",
        "evidence": {"records_examined": [], "calculation": "", "key_findings": []},
        "confidence": 0.0,
        "recommended_action": "ESCALATE",
        "action_reason": "Automated investigation temporarily unavailable; routing to human review."
    }

if __name__ == "__main__":
    import pandas as pd
    from src.agent.investigate import gather_related_records
    from src.agent.triage import triage_exceptions

    df_orders = pd.read_csv("data/mutated/orders.csv")
    df_payments = pd.read_csv("data/mutated/payments.csv")
    df_refunds = pd.read_csv("data/mutated/refunds.csv")
    df_settlements = pd.read_csv("data/mutated/settlements.csv")
    df_bank = pd.read_csv("data/mutated/bank_entries.csv")

    with open("data/stage2_results.json") as f:
        stage2_results = json.load(f)

    prioritized = triage_exceptions(stage2_results, df_settlements)

    # test on top 4 highest-value cases
    for case in prioritized[:4]:
        payment_id = case["payment_id"]
        print(f"\n{'='*60}")
        print(f"Investigating: {payment_id} (₹{case['amount_at_risk']:,.2f} at risk)")
        print(f"{'='*60}")

        related = gather_related_records(payment_id, df_orders, df_payments, df_refunds,
                                           df_settlements, df_bank)
        result = reason_over_case(related, case)

        print(f"Root cause: {result['root_cause']}")
        print(f"Recommended action: {result['recommended_action']}")
        print(f"Confidence: {result['confidence']}")
        print(f"Explanation: {result['explanation']}")