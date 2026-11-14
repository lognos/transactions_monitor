"""Evaluate graph: one transaction in, one evaluation out. See docs/plan-agent.md."""

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph


class EvalState(TypedDict, total=False):
    txn_id: str
    principal_id: str
    txn: dict[str, Any]
    customer: dict[str, Any]
    policy: dict[str, Any]
    checks: list[dict[str, Any]]
    precedents: list[dict[str, Any]]
    adjustments: list[dict[str, Any]]
    llm_output: dict[str, Any]
    evaluation: dict[str, Any]


async def load(state: EvalState) -> dict[str, Any]:
    """Read the transaction, its customer and the active policy for its type."""
    raise NotImplementedError("evaluate.load")


async def run_checks(state: EvalState) -> dict[str, Any]:
    """Run every hard criterion through the CHECKS registry."""
    raise NotImplementedError("evaluate.run_checks")


async def retrieve_context(state: EvalState) -> dict[str, Any]:
    """Fetch precedents (vector search) and active adjustments (find)."""
    raise NotImplementedError("evaluate.retrieve_context")


async def recommend(state: EvalState) -> dict[str, Any]:
    """LLM: judge the judgment criteria. Output shape: RecommendOutput."""
    raise NotImplementedError("evaluate.recommend")


async def save_evaluation(state: EvalState) -> dict[str, Any]:
    """Merge checks, compute the recommendation in code, write via write_with_audit."""
    raise NotImplementedError("evaluate.save_evaluation")


def build_evaluate_graph():
    builder = StateGraph(EvalState)
    builder.add_node("load", load)
    builder.add_node("run_checks", run_checks)
    builder.add_node("retrieve_context", retrieve_context)
    builder.add_node("recommend", recommend)
    builder.add_node("save_evaluation", save_evaluation)

    builder.add_edge(START, "load")
    builder.add_edge("load", "run_checks")
    builder.add_edge("run_checks", "retrieve_context")
    builder.add_edge("retrieve_context", "recommend")
    builder.add_edge("recommend", "save_evaluation")
    builder.add_edge("save_evaluation", END)
    return builder.compile()


evaluate_graph = build_evaluate_graph()
