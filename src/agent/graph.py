from typing import TypedDict, Optional
import json
import pandas as pd
from langgraph.graph import StateGraph, END

from src.agent.investigate import gather_related_records
from src.agent.reason import reason_over_case


class AgentState(TypedDict):
    payment_id: str
    stage2_case: dict          # the original Stage 2 finding, passed in
    related_records: Optional[dict]   # filled in by the Investigate node
    reasoning_result: Optional[dict]  # filled in by the Reason node
def investigate_node(state: AgentState) -> dict:
    """
    LangGraph node wrapping gather_related_records.
    Reads payment_id from state, returns related_records.
    """
    df_orders = pd.read_csv("data/mutated/orders.csv")
    df_payments = pd.read_csv("data/mutated/payments.csv")
    df_refunds = pd.read_csv("data/mutated/refunds.csv")
    df_settlements = pd.read_csv("data/mutated/settlements.csv")
    df_bank = pd.read_csv("data/mutated/bank_entries.csv")

    related = gather_related_records(
        state["payment_id"], df_orders, df_payments, df_refunds, df_settlements, df_bank
    )
    return {"related_records": related}


def reason_node(state: AgentState) -> dict:
    """
    LangGraph node wrapping reason_over_case.
    Reads related_records + stage2_case from state, returns reasoning_result.
    """
    result = reason_over_case(state["related_records"], state["stage2_case"])
    return {"reasoning_result": result}
def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("investigate", investigate_node)
    graph.add_node("reason", reason_node)

    graph.set_entry_point("investigate")
    graph.add_edge("investigate", "reason")
    graph.add_edge("reason", END)

    return graph.compile()

if __name__ == "__main__":
    from src.agent.triage import triage_exceptions

    df_settlements = pd.read_csv("data/mutated/settlements.csv")
    with open("data/stage2_results.json") as f:
        stage2_results = json.load(f)

    prioritized = triage_exceptions(stage2_results, df_settlements)

    app = build_graph()

    # run the graph on the single highest-priority case
    top_case = prioritized[0]
    initial_state = {
        "payment_id": top_case["payment_id"],
        "stage2_case": top_case,
        "related_records": None,
        "reasoning_result": None
    }

    final_state = app.invoke(initial_state)

    print(f"Case: {final_state['payment_id']}")
    print(json.dumps(final_state["reasoning_result"], indent=2))