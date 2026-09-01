import json
import os
import time
from dotenv import load_dotenv
from google import genai
from google.genai import types
from src.agent.tools import (
    get_payment, get_refunds, get_settlement, search_bank_transactions,
    calculate_reconciliation, check_action_policy, create_escalation
)

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

MODEL_NAME = "gemini-3.1-flash-lite"

TOOL_FUNCTIONS = {
    "get_payment": get_payment,
    "get_refunds": get_refunds,
    "get_settlement": get_settlement,
    "search_bank_transactions": search_bank_transactions,
    "calculate_reconciliation": calculate_reconciliation,
    "check_action_policy": check_action_policy,
    "create_escalation": create_escalation,
}

CONTROLLER_SYSTEM_PROMPT = """You are a Financial Reconciliation Agent with access to tools.
You do NOT receive pre-gathered evidence — you must investigate by calling tools yourself.

For the given payment_id, investigate the exception step by step:
1. Gather the relevant records using get_payment, get_refunds, get_settlement, search_bank_transactions as needed.
2. Run calculate_reconciliation to verify the financial math deterministically.
3. Determine the root cause based on what you find.
4. Decide a proposed_action (RESOLVE, ESCALATE, or REJECT).
5. ALWAYS call check_action_policy before finalizing — it may override your proposed action. You must respect its result.
6. If the final action is ESCALATE, call create_escalation to formally log it.
7. Once done, respond with a final plain-text summary of your investigation, root cause, and final action — no more tool calls after this.

Be efficient: don't call tools you don't need. Don't call the same tool twice with the same arguments.
"""


def run_agentic_investigation(payment_id: str, amount_at_risk: float, max_turns: int = 10) -> dict:
    """
    Runs the full multi-turn, tool-calling investigation loop for one payment_id.
    Includes retry protection for rate limits and a small pause between turns
    to stay under the free-tier's per-minute request cap.
    """
    tools = types.Tool(function_declarations=TOOL_DEFINITIONS)

    conversation = [
        types.Content(role="user", parts=[types.Part(text=
            f"Investigate payment_id: {payment_id}. The estimated amount at risk is ₹{amount_at_risk:,.2f}. "
            f"Begin your investigation.")])
    ]

    tool_call_log = []

    for turn in range(max_turns):
        response = None
        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model=MODEL_NAME,
                    contents=conversation,
                    config=types.GenerateContentConfig(
                        system_instruction=CONTROLLER_SYSTEM_PROMPT,
                        tools=[tools]
                    )
                )
                break
            except Exception as e:
                error_str = str(e)
                if any(code in error_str for code in ["429", "503", "UNAVAILABLE", "quota", "rate"]):
                    wait_time = 35
                    print(f"    Rate limited, waiting {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    raise

        if response is None:
            return {
                "payment_id": payment_id,
                "final_summary": "Investigation failed after retries.",
                "tool_call_log": tool_call_log,
                "turns_used": turn
            }

        candidate = response.candidates[0]
        conversation.append(candidate.content)

        function_calls = [part.function_call for part in candidate.content.parts if part.function_call]

        if not function_calls:
            final_text = "".join(part.text or "" for part in candidate.content.parts)
            return {
                "payment_id": payment_id,
                "final_summary": final_text,
                "tool_call_log": tool_call_log,
                "turns_used": turn + 1
            }

        function_response_parts = []
        for fc in function_calls:
            tool_name = fc.name
            tool_args = dict(fc.args)
            tool_call_log.append({"tool": tool_name, "args": tool_args})

            print(f"  [Turn {turn+1}] Agent calling: {tool_name}({tool_args})")

            if tool_name in TOOL_FUNCTIONS:
                result = TOOL_FUNCTIONS[tool_name](**tool_args)
            else:
                result = {"error": f"Unknown tool: {tool_name}"}

            function_response_parts.append(
                types.Part.from_function_response(name=tool_name, response={"result": result})
            )

        conversation.append(types.Content(role="tool", parts=function_response_parts))

        time.sleep(3)

    return {
        "payment_id": payment_id,
        "final_summary": "Max turns reached without a final answer.",
        "tool_call_log": tool_call_log,
        "turns_used": max_turns
    }


TOOL_DEFINITIONS = [
    types.FunctionDeclaration(
        name="get_payment",
        description="Fetch the payment record for a given payment_id.",
        parameters={
            "type": "object",
            "properties": {"payment_id": {"type": "string"}},
            "required": ["payment_id"]
        }
    ),
    types.FunctionDeclaration(
        name="get_refunds",
        description="Fetch all refund records for a given payment_id. May return zero, one, or multiple refunds.",
        parameters={
            "type": "object",
            "properties": {"payment_id": {"type": "string"}},
            "required": ["payment_id"]
        }
    ),
    types.FunctionDeclaration(
        name="get_settlement",
        description="Fetch the settlement record for a given payment_id.",
        parameters={
            "type": "object",
            "properties": {"payment_id": {"type": "string"}},
            "required": ["payment_id"]
        }
    ),
    types.FunctionDeclaration(
        name="search_bank_transactions",
        description="Search bank entries by UTR, using normalized matching (ignores formatting differences like hyphens).",
        parameters={
            "type": "object",
            "properties": {"utr": {"type": "string"}},
            "required": ["utr"]
        }
    ),
    types.FunctionDeclaration(
        name="calculate_reconciliation",
        description="Runs the deterministic financial lifecycle check for a payment_id: computes expected settlement net (payment - refunds - fee - tax) and compares against actual settlement net. Returns PASS or FAIL with details.",
        parameters={
            "type": "object",
            "properties": {"payment_id": {"type": "string"}},
            "required": ["payment_id"]
        }
    ),
    types.FunctionDeclaration(
        name="check_action_policy",
        description="Checks whether a proposed action (RESOLVE, ESCALATE, or REJECT) is permitted given the amount at risk and your confidence. ALWAYS call this before finalizing any action — it enforces hard safety rules you cannot override.",
        parameters={
            "type": "object",
            "properties": {
                "proposed_action": {"type": "string", "enum": ["RESOLVE", "ESCALATE", "REJECT"]},
                "amount_at_risk": {"type": "number"},
                "confidence": {"type": "number"}
            },
            "required": ["proposed_action", "amount_at_risk", "confidence"]
        }
    ),
    types.FunctionDeclaration(
        name="create_escalation",
        description="Creates a formal escalation case for human review. Use this as your final action when check_action_policy confirms ESCALATE is the correct outcome.",
        parameters={
            "type": "object",
            "properties": {
                "payment_id": {"type": "string"},
                "reason": {"type": "string"},
                "priority": {"type": "string", "enum": ["LOW", "MEDIUM", "HIGH"]}
            },
            "required": ["payment_id", "reason", "priority"]
        }
    ),
]


if __name__ == "__main__":
    print(f"Total tools defined: {len(TOOL_DEFINITIONS)}")

    print(f"\n--- Running agentic investigation on PAY-00046 ---")
    result = run_agentic_investigation("PAY-00046", amount_at_risk=172425.68)

    print(f"\nTurns used: {result['turns_used']}")
    print(f"Tool calls made: {len(result['tool_call_log'])}")
    for call in result['tool_call_log']:
        print(f"  - {call['tool']}({call['args']})")
    print(f"\nFinal summary:\n{result['final_summary']}")