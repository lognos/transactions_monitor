"""The agent's public interface. Contract: docs/contracts.md §5.5."""

import asyncio
from typing import Any, Literal

from app.agent.graphs._deps import agent_actor, write_with_audit
from app.agent.graphs.evaluate import evaluate_graph
from app.agent.graphs.review import review_graph
from app.agent.llm import get_structured_llm
from app.agent.memory import active_adjustments, search_memory
from app.agent.prompts import build_chat_messages
from app.agent.schemas import AnswerOutput
from app.agent.simulator import simulate_transactions
from app.db import get_db


async def run_evaluate(*, txn_id: str, principal_id: str, refresh: bool = False) -> dict[str, Any]:
    """Run the Evaluate graph. Returns {"evaluation", "transaction", "customer"}."""
    state = await evaluate_graph.ainvoke(
        {"txn_id": txn_id, "principal_id": principal_id, "refresh": refresh}
    )
    return {
        "evaluation": state["evaluation"],
        "transaction": state["txn"],
        "customer": state["customer"],
    }


async def run_chat(*, message: str, principal_id: str) -> dict[str, Any]:
    """Answer a general question from active policies and memory (no transaction in focus)."""
    db = get_db()
    policies = await db.policies.find({"active": True}, {"_id": 0}).to_list(length=50)
    txn_types = [p["txn_type"] for p in policies if p.get("txn_type")]

    prec_lists = await asyncio.gather(
        *(search_memory(query=message, txn_type=t, kind="precedent", k=2) for t in txn_types)
    )
    adj_lists = await asyncio.gather(
        *(active_adjustments(txn_type=t) for t in txn_types)
    )

    precedents_by_id: dict[str, dict[str, Any]] = {}
    for plist in prec_lists:
        for item in plist:
            mid = item.get("memory_id")
            if mid and (mid not in precedents_by_id or item.get("score", 0) > precedents_by_id[mid].get("score", 0)):
                precedents_by_id[mid] = item
    precedents = sorted(precedents_by_id.values(), key=lambda x: x.get("score", 0), reverse=True)[:4]

    adjustments_by_id: dict[str, dict[str, Any]] = {}
    for alist in adj_lists:
        for item in alist:
            mid = item.get("memory_id")
            if mid:
                adjustments_by_id[mid] = item
    adjustments = list(adjustments_by_id.values())

    messages = build_chat_messages(
        message=message,
        policies=policies,
        precedents=precedents,
        adjustments=adjustments,
    )
    output: AnswerOutput = await get_structured_llm(AnswerOutput).ainvoke(messages)

    valid_policy_ids = {
        c["id"] for p in policies for c in p.get("criteria", []) if c.get("id")
    }
    valid_precedent_ids = set(precedents_by_id.keys())
    valid_adjustment_ids = set(adjustments_by_id.keys())

    citations = [
        c.model_dump()
        for c in output.citations
        if (
            (c.type == "policy" and c.ref in valid_policy_ids)
            or (c.type == "precedent" and c.ref in valid_precedent_ids)
            or (c.type == "adjustment" and c.ref in valid_adjustment_ids)
        )
    ]

    await write_with_audit(
        actor=agent_actor(principal_id),
        event="question.answered",
        txn_id=None,
        ref={"collection": "policies", "id": "general"},
        detail={"question": message, "citations": citations},
        writes=[],
    )

    return {"answer": output.answer, "citations": citations}


async def run_review(*, eval_id: str, principal_id: str, review_input: dict[str, Any]) -> dict[str, Any]:
    """Run the Review graph for one reviewer message.

    review_input: {"kind": "question", "question": str}
               or {"kind": "decision", "verdict": "approved" | "rejected", "comments": str | None}
               or {"kind": "override", "criterion_id": str, "result": str | None, "reason": str}

    Returns the keys the server needs:
      question -> {"answer", "evaluation"}
      decision -> {"gate", "decision", "txn", "memory_created"}  (decision is None when denied)
    """
    state = await review_graph.ainvoke(
        {"eval_id": eval_id, "principal_id": principal_id, "input": review_input}
    )
    return {
        key: state.get(key)
        for key in ("answer", "evaluation", "gate", "decision", "txn", "memory_created", "override", "blocking_checks")
    }


async def run_simulate(
    *,
    principal_id: str,
    count: int = 3,
    mode: Literal["random", "signals", "sequential"] = "random",
    policy_only: bool = False,
) -> dict[str, Any]:
    """Pull transactions from the consolidated CSV and run policy/agent evaluation."""
    return await simulate_transactions(
        principal_id=principal_id,
        count=count,
        mode=mode,
        policy_only=policy_only,
    )
