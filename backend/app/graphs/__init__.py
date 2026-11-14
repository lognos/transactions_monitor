"""
backend/app/graphs/__init__.py
Public interface for the Policy & Validation Agent LangGraph subgraphs.

Designed for drop-in integration into a broader LangGraph architecture:

1. Direct async invocation:
    ```python
    from app.graphs import evaluate_graph, review_graph

    eval_result = await evaluate_graph.ainvoke({
        "txn_id": "TXN-0001",
        "principal_id": "ana",
    })
    evaluation = eval_result["evaluation"]

    ask_result = await review_graph.ainvoke({
        "eval_id": evaluation["eval_id"],
        "principal_id": "ana",
        "input": {"kind": "question", "question": "Why did C-04 fail?"},
    })

    decide_result = await review_graph.ainvoke({
        "eval_id": evaluation["eval_id"],
        "principal_id": "ana",
        "input": {
            "kind": "decision",
            "verdict": "validated_with_comments",
            "comments": "Payroll customers spike at month-end.",
        },
    })
    ```

2. Composing inside a parent `StateGraph`:
    Either add `evaluate_graph` / `review_graph` directly as compiled subgraph
    nodes (`builder.add_node("policy_evaluate", evaluate_graph)`), or rebuild
    with `build_evaluate_graph()` / `build_review_graph()` if you need custom
    checkpointers or hooks.
"""

from app.graphs.evaluate import EvalState, build_evaluate_graph, evaluate_graph
from app.graphs.review import (
    AlreadyDecidedError,
    ReviewState,
    build_review_graph,
    review_graph,
)

__all__ = [
    "EvalState",
    "ReviewState",
    "AlreadyDecidedError",
    "build_evaluate_graph",
    "build_review_graph",
    "evaluate_graph",
    "review_graph",
]
