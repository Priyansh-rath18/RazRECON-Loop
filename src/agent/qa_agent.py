import os
import json
import re
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
MODEL_NAME = "gemini-3.1-flash-lite"

QA_SYSTEM_PROMPT = """You are a Settlement Q&A assistant for a finance reconciliation system.
You will be given a user's question AND a set of real case records retrieved from the system's
audit trail. Answer using ONLY the data provided — never invent case details, amounts, or
statuses not present in the records given to you.

If the provided records don't contain enough information to answer, say so clearly rather
than guessing. Be concise and cite the specific case_id / payment_id in your answer.
"""


def find_relevant_cases(question: str, audit_trail: list, max_cases: int = 5) -> list:
    question_lower = question.lower()
    question_normalized = question_lower.replace("-", " ").replace("_", " ")

    id_matches = re.findall(r'(PAY-\d{5}|CASE-\d{4})', question, re.IGNORECASE)
    if id_matches:
        ids = [m.upper() for m in id_matches]
        matched = [r for r in audit_trail if r["payment_id"] in ids or r["case_id"] in ids]
        if matched:
            return matched

    keywords = {
        "missing bank": "MISSING_BANK_ENTRY",
        "over refund": "OVER_REFUND",
        "amount mismatch": "AMOUNT_MISMATCH",
        "duplicate": "DUPLICATE_TRANSACTION",
        "tax": "TAX_MISMATCH",
        "fee": "FEE_MISMATCH",
        "refund timing": "REFUND_TIMING_CONFLICT",
    }
    for kw, root_cause in keywords.items():
        if kw in question_normalized:
            matched = [r for r in audit_trail if r["agent_investigation"]["root_cause"] == root_cause]
            if matched:
                return sorted(matched, key=lambda r: r["amount_at_risk"], reverse=True)[:max_cases]

    action_keywords = {
        "blocked": "REJECT_ACTION", "rejected": "REJECT_ACTION",
        "auto resolved": "AUTO_RESOLVE", "auto resolve": "AUTO_RESOLVE",
        "escalated": "ESCALATE",
    }
    for kw, action in action_keywords.items():
        if kw in question_normalized:
            matched = [r for r in audit_trail if r["policy_decision"]["final_action"] == action]
            if matched:
                return sorted(matched, key=lambda r: r["amount_at_risk"], reverse=True)[:max_cases]

    if "critical" in question_normalized:
        matched = [r for r in audit_trail if r["priority"]["priority"] == "CRITICAL"]
        if matched:
            return sorted(matched, key=lambda r: r["amount_at_risk"], reverse=True)[:max_cases]

    return sorted(audit_trail, key=lambda r: r["amount_at_risk"], reverse=True)[:max_cases]


def summarize_case_for_qa(case: dict) -> dict:
    """Compact representation of one case — enough to answer questions, not the full raw JSON."""
    return {
        "case_id": case["case_id"],
        "payment_id": case["payment_id"],
        "root_cause": case["agent_investigation"]["root_cause"],
        "confidence": case["agent_investigation"]["confidence"],
        "amount_at_risk": case["amount_at_risk"],
        "priority": case["priority"]["priority"],
        "final_action": case["policy_decision"]["final_action"],
        "policy_reason": case["policy_decision"]["policy_reason"],
        "verified": case["verification"]["verified"],
        "explanation_summary": case["agent_investigation"]["explanation"][:300],
    }


def answer_question(question: str, audit_trail: list) -> dict:
    relevant_cases = find_relevant_cases(question, audit_trail)
    compact_cases = [summarize_case_for_qa(c) for c in relevant_cases]

    user_prompt = f"""
User question: {question}

Retrieved case records (grounded data — answer only from this):
{json.dumps(compact_cases, indent=2, default=str)}
"""

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=user_prompt,
        config=types.GenerateContentConfig(system_instruction=QA_SYSTEM_PROMPT)
    )

    return {
        "question": question,
        "answer": response.text,
        "cases_used": [c["case_id"] for c in compact_cases]
    }


if __name__ == "__main__":
    with open("data/audit_trail.json") as f:
        audit_trail = json.load(f)

    test_questions = [
        "Why didn't PAY-00046 settle?",
        "Show me all missing bank entry cases",
        "What was blocked and why?",
    ]

    for q in test_questions:
        print(f"\nQ: {q}")
        result = answer_question(q, audit_trail)
        print(f"A: {result['answer']}")
        print(f"Cases used: {result['cases_used']}")