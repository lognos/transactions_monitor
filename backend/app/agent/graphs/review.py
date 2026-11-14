"""Review graph: one reviewer message in (question or decision). See docs/plan-agent.md."""

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph


class ReviewState(TypedDict, total=False):
    eval_id: str
    principal_id: str
    input: dict[str, Any]  # {"kind": "question" | "decision", "question", "verdict", "comments"}
    evaluation: dict[str, Any]
    txn: dict[str, Any]
    principal: dict[str, Any]
    answer: dict[str, Any]
    gate: dict[str, Any]
    decision: dict[str, Any]
    memory_created: list[dict[str, Any]]


async def load_review(state: ReviewState) -> dict[str, Any]:
    """Read the evaluation, its transaction and the acting principal."""
    raise NotImplementedError("review.load_review")


async def answer_question(state: ReviewState) -> dict[str, Any]:
    """LLM: answer from policy and memory only. Append to the thread, audit."""
    raise NotImplementedError("review.answer_question")


async def policy_gate(state: ReviewState) -> dict[str, Any]:
    """Call db.gate.check_gate and put the result in state["gate"]."""
    raise NotImplementedError("review.policy_gate")


async def record_denied(state: ReviewState) -> dict[str, Any]:
    """Audit a decision.denied event. No decision document is stored."""
    raise NotImplementedError("review.record_denied")


async def record_decision(state: ReviewState) -> dict[str, Any]:
    """Store the decision, update evaluation and transaction status, audit."""
    raise NotImplementedError("review.record_decision")


async def learn_from_feedback(state: ReviewState) -> dict[str, Any]:
    """LLM: distil the comment into an adjustment (judgment criteria only)."""
    raise NotImplementedError("review.learn_from_feedback")


async def store_precedent(state: ReviewState) -> dict[str, Any]:
    """Store the decided case as a precedent (templated text, no LLM)."""
    raise NotImplementedError("review.store_precedent")


def route_input(state: ReviewState) -> str:
    return "answer_question" if state["input"]["kind"] == "question" else "policy_gate"


def route_gate(state: ReviewState) -> str:
    return "record_denied" if state["gate"]["result"] == "deny" else "record_decision"


def route_feedback(state: ReviewState) -> str:
    return "learn_from_feedback" if state["input"].get("comments") else "store_precedent"


def build_review_graph():
    builder = StateGraph(ReviewState)
    builder.add_node("load_review", load_review)
    builder.add_node("answer_question", answer_question)
    builder.add_node("policy_gate", policy_gate)
    builder.add_node("record_denied", record_denied)
    builder.add_node("record_decision", record_decision)
    builder.add_node("learn_from_feedback", learn_from_feedback)
    builder.add_node("store_precedent", store_precedent)

    builder.add_edge(START, "load_review")
    builder.add_conditional_edges("load_review", route_input, ["answer_question", "policy_gate"])
    builder.add_edge("answer_question", END)
    builder.add_conditional_edges("policy_gate", route_gate, ["record_denied", "record_decision"])
    builder.add_edge("record_denied", END)
    builder.add_conditional_edges(
        "record_decision", route_feedback, ["learn_from_feedback", "store_precedent"]
    )
    builder.add_edge("learn_from_feedback", "store_precedent")
    builder.add_edge("store_precedent", END)
    return builder.compile()


review_graph = build_review_graph()
