"""The agent's public interface. Contract: docs/contracts.md §5.5."""

from typing import Any

from app.agent.graphs.evaluate import evaluate_graph
from app.agent.graphs.review import review_graph


async def run_evaluate(*, txn_id: str, principal_id: str) -> dict[str, Any]:
    """Run the Evaluate graph. Returns {"evaluation", "transaction", "customer"}."""
    state = await evaluate_graph.ainvoke({"txn_id": txn_id, "principal_id": principal_id})
    return {
        "evaluation": state["evaluation"],
        "transaction": state["txn"],
        "customer": state["customer"],
    }


async def run_review(*, eval_id: str, principal_id: str, review_input: dict[str, Any]) -> dict[str, Any]:
    """Run the Review graph for one reviewer message.

    review_input: {"kind": "question", "question": str}
               or {"kind": "decision", "verdict": str, "comments": str | None}

    Returns the keys the server needs:
      question -> {"answer", "evaluation"}
      decision -> {"gate", "decision", "txn", "memory_created"}  (decision is None when denied)
    """
    state = await review_graph.ainvoke(
        {"eval_id": eval_id, "principal_id": principal_id, "input": review_input}
    )
    return {
        key: state.get(key)
        for key in ("answer", "evaluation", "gate", "decision", "txn", "memory_created")
    }
