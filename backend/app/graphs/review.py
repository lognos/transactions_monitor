"""
backend/app/graphs/review.py
LangGraph `Review` subgraph: handles reviewer Q&A and human-in-the-loop decisions.

Graph topology (`docs/plan-agent.md`):
    START -> load_review
      --[question]--> answer_question -> END
      --[decision]--> policy_gate
        --[deny]----> record_denied -> END
        --[allow]---> record_decision
          --[has comments]--> learn_from_feedback -> store_precedent -> END
          --[no comments]---> store_precedent -> END

Integration contract for future agents / parent graphs:
    Question mode input:
        {"eval_id": "EVAL-...", "principal_id": "ana",
         "input": {"kind": "question", "question": "Why did C-04 fail?"}}
    Decision mode input:
        {"eval_id": "EVAL-...", "principal_id": "ana",
         "input": {"kind": "decision", "verdict": "validated_with_comments",
                   "comments": "Payroll customers spike at month-end."}}

Invariants enforced:
    - `check_gate` runs before any decision is recorded; denials are audited (`decision.denied`).
    - `learn_from_feedback` strictly discards any adjustment targeting a `hard` criterion.
    - `store_precedent` uses a deterministic template (`precedent_text_template`), never an LLM.
    - All DB writes go through `write_with_audit`.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from app.db import get_async_db
from app.graphs._deps import (
    agent_actor,
    check_gate,
    human_actor,
    make_insert,
    make_update,
    new_id,
    utc_now_iso,
    write_with_audit,
)
from app.llm import get_structured_llm
from app.memory import (
    active_adjustments,
    build_structured_query,
    precedent_text_template,
    search_memory,
)
from app.models import AnswerOutput, LearnOutput
from app.prompts import build_answer_messages, build_learn_messages

logger = logging.getLogger(__name__)


class AlreadyDecidedError(Exception):
    """Raised when attempting to decide an evaluation that already has a decision."""


# ---------------------------------------------------------------------------
# Graph State (docs/contracts.md §7)
# ---------------------------------------------------------------------------


class ReviewState(TypedDict, total=False):
    """State passed between nodes of the Review graph."""

    eval_id: str
    principal_id: str
    input: Dict[str, Any]
    evaluation: Dict[str, Any]
    txn: Dict[str, Any]
    customer: Dict[str, Any]
    policy: Dict[str, Any]
    principal: Dict[str, Any]
    answer: Dict[str, Any]
    gate: Dict[str, Any]
    decision: Dict[str, Any]
    memory_created: List[Dict[str, Any]]


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


async def load_review(state: ReviewState) -> Dict[str, Any]:
    """Load evaluation, transaction, customer, active policy, and acting principal."""
    db = get_async_db()
    eval_id = state["eval_id"]
    principal_id = state["principal_id"]

    principal = await db["principals"].find_one({"_id": principal_id})
    if not principal:
        raise PermissionError(f"Unknown principal: {principal_id}")

    evaluation = await db["evaluations"].find_one({"eval_id": eval_id}, {"_id": 0})
    if not evaluation:
        raise KeyError(f"Evaluation not found: {eval_id}")

    if state.get("input", {}).get("kind") == "decision" and evaluation.get("status") == "decided":
        raise AlreadyDecidedError(f"Evaluation {eval_id} already has a decision.")

    txn = await db["transactions"].find_one({"txn_id": evaluation["txn_id"]}, {"_id": 0})
    if not txn:
        raise KeyError(f"Transaction not found: {evaluation['txn_id']}")

    customer = await db["customers"].find_one({"customer_id": txn["customer_id"]}, {"_id": 0})
    if not customer:
        raise KeyError(f"Customer not found: {txn['customer_id']}")

    policy = await db["policies"].find_one(
        {"txn_type": txn["type"], "active": True}, {"_id": 0}
    )
    if not policy:
        raise KeyError(f"No active policy for txn_type={txn['type']}")

    return {
        "evaluation": evaluation,
        "txn": txn,
        "customer": customer,
        "policy": policy,
        "principal": principal,
        "memory_created": [],
    }


async def answer_question(state: ReviewState) -> Dict[str, Any]:
    """Answer a reviewer's question strictly from policy, evaluation, and memory."""
    evaluation = state["evaluation"]
    txn = state["txn"]
    customer = state["customer"]
    policy = state["policy"]
    principal_id = state["principal_id"]
    question = state["input"]["question"]

    structured_query = build_structured_query(
        txn_type=txn["type"],
        amount=txn.get("amount"),
        customer_segment=customer.get("segment"),
        extra_context=question,
    )
    precedents = await search_memory(
        query=structured_query,
        txn_type=txn["type"],
        kind="precedent",
        k=4,
    )
    adjustments = await active_adjustments(txn_type=txn["type"])

    messages = build_answer_messages(
        question=question,
        txn=txn,
        customer=customer,
        evaluation=evaluation,
        policy=policy,
        precedents=precedents,
        adjustments=adjustments,
    )

    structured_llm = get_structured_llm(AnswerOutput)
    output: AnswerOutput = await structured_llm.ainvoke(messages)

    # Filter citations to IDs actually present in policy or retrieved memory
    valid_criteria = {c["id"] for c in policy.get("criteria", [])}
    valid_precedents = {p["memory_id"] for p in precedents}
    valid_adjustments = {a["memory_id"] for a in adjustments}
    prec_labels = {p["memory_id"]: p.get("text", "")[:80] for p in precedents}
    adj_labels = {a["memory_id"]: a.get("text", "")[:80] for a in adjustments}

    clean_citations: List[Dict[str, Any]] = []
    for cit in output.citations:
        if cit.type == "policy" and cit.ref in valid_criteria:
            clean_citations.append({"type": "policy", "ref": cit.ref})
        elif cit.type == "precedent" and cit.ref in valid_precedents:
            clean_citations.append(
                {
                    "type": "precedent",
                    "ref": cit.ref,
                    "label": cit.label or prec_labels.get(cit.ref, ""),
                }
            )
        elif cit.type == "adjustment" and cit.ref in valid_adjustments:
            clean_citations.append(
                {
                    "type": "adjustment",
                    "ref": cit.ref,
                    "label": cit.label or adj_labels.get(cit.ref, ""),
                }
            )

    thread_entry = {
        "question": question,
        "answer": output.answer,
        "citations": clean_citations,
        "asked_by": principal_id,
        "ts": utc_now_iso(),
    }
    updated_thread = list(evaluation.get("thread", [])) + [thread_entry]

    await write_with_audit(
        actor=agent_actor(principal_id),
        event="question.answered",
        txn_id=txn["txn_id"],
        ref={"collection": "evaluations", "id": evaluation["eval_id"]},
        detail={
            "question": question,
            "citations": [c["ref"] for c in clean_citations],
        },
        writes=[
            make_update(
                "evaluations",
                {"eval_id": evaluation["eval_id"]},
                {"$push": {"thread": thread_entry}},
            )
        ],
    )

    return {
        "answer": {
            "answer": output.answer,
            "citations": clean_citations,
            "thread": updated_thread,
        }
    }


async def policy_gate(state: ReviewState) -> Dict[str, Any]:
    """Run deterministic policy gate before allowing a human decision."""
    gate = await check_gate(
        principal=state["principal"],
        txn=state["txn"],
        evaluation=state["evaluation"],
        verdict=state["input"]["verdict"],
    )
    return {"gate": gate}


async def record_denied(state: ReviewState) -> Dict[str, Any]:
    """Record a `decision.denied` audit event without modifying transactions/decisions."""
    principal = state["principal"]
    txn = state["txn"]
    evaluation = state["evaluation"]
    gate = state["gate"]
    verdict = state["input"]["verdict"]

    await write_with_audit(
        actor=human_actor(principal),
        event="decision.denied",
        txn_id=txn["txn_id"],
        ref={"collection": "evaluations", "id": evaluation["eval_id"]},
        detail={
            "verdict": verdict,
            "amount": txn.get("amount"),
            "gate": gate,
        },
        writes=[],
    )
    return {}


async def record_decision(state: ReviewState) -> Dict[str, Any]:
    """Persist an allowed decision and update evaluation & transaction statuses."""
    principal = state["principal"]
    txn = state["txn"]
    evaluation = state["evaluation"]
    gate = state["gate"]
    verdict = state["input"]["verdict"]
    comments = (state["input"].get("comments") or "").strip()

    agreed_with_agent = (verdict != "rejected") == (
        evaluation.get("recommendation") == "pass"
    )
    new_txn_status = "rejected" if verdict == "rejected" else "passed"

    decision_id = new_id("DEC")
    now = utc_now_iso()
    decision_doc: Dict[str, Any] = {
        "decision_id": decision_id,
        "eval_id": evaluation["eval_id"],
        "txn_id": txn["txn_id"],
        "reviewer_id": principal["_id"],
        "verdict": verdict,
        "comments": comments,
        "agreed_with_agent": agreed_with_agent,
        "gate": gate,
        "ts": now,
    }

    await write_with_audit(
        actor=human_actor(principal),
        event="decision.recorded",
        txn_id=txn["txn_id"],
        ref={"collection": "decisions", "id": decision_id},
        detail={
            "verdict": verdict,
            "agreed_with_agent": agreed_with_agent,
            "gate": gate,
        },
        writes=[
            make_insert("decisions", decision_doc),
            make_update(
                "evaluations",
                {"eval_id": evaluation["eval_id"]},
                {"$set": {"status": "decided"}},
            ),
            make_update(
                "transactions",
                {"txn_id": txn["txn_id"]},
                {"$set": {"status": new_txn_status}},
            ),
        ],
    )

    updated_txn = {**txn, "status": new_txn_status}
    return {"decision": decision_doc, "txn": updated_txn}


async def learn_from_feedback(state: ReviewState) -> Dict[str, Any]:
    """
    Extract a reusable `adjustment` memory from reviewer comments, strictly
    enforcing that adjustments may only target `judgment` criteria.
    """
    policy = state["policy"]
    judgment_criteria = [
        c for c in policy.get("criteria", []) if c.get("kind") == "judgment"
    ]
    judgment_ids = {c["id"] for c in judgment_criteria}

    comments = (state["input"].get("comments") or "").strip()
    if not comments or not judgment_criteria:
        return {}

    messages = build_learn_messages(
        verdict=state["input"]["verdict"],
        comments=comments,
        txn=state["txn"],
        customer=state["customer"],
        evaluation_checks=state["evaluation"].get("checks", []),
        judgment_criteria=judgment_criteria,
    )

    structured_llm = get_structured_llm(LearnOutput)
    try:
        output: LearnOutput = await structured_llm.ainvoke(messages)
    except Exception as exc:
        logger.warning("learn_from_feedback LLM failed: %s", exc)
        return {}

    if not output.should_create or output.criterion_id not in judgment_ids:
        logger.info(
            "Skipping adjustment creation (should_create=%s, criterion_id=%s).",
            output.should_create,
            output.criterion_id,
        )
        return {}

    if not output.text or not output.condition:
        return {}

    txn = state["txn"]
    decision = state["decision"]
    principal_id = state["principal_id"]
    mem_id = new_id("MEM")

    adj_doc: Dict[str, Any] = {
        "memory_id": mem_id,
        "kind": "adjustment",
        "txn_type": txn["type"],
        "text": output.text.strip(),
        "scope": {
            "criterion_id": output.criterion_id,
            "condition": output.condition.strip(),
        },
        "source_decision_id": decision["decision_id"],
        "source_txn_id": txn["txn_id"],
        "author_id": principal_id,
        "active": True,
        "created_at": utc_now_iso(),
    }

    await write_with_audit(
        actor=agent_actor(principal_id),
        event="memory.created",
        txn_id=txn["txn_id"],
        ref={"collection": "memory", "id": mem_id},
        detail={
            "kind": "adjustment",
            "criterion_id": output.criterion_id,
            "source_decision_id": decision["decision_id"],
            "author_id": principal_id,
        },
        writes=[make_insert("memory", adj_doc)],
    )

    created = list(state.get("memory_created", [])) + [
        {"memory_id": mem_id, "kind": "adjustment", "text": adj_doc["text"]}
    ]
    return {"memory_created": created}


async def store_precedent(state: ReviewState) -> Dict[str, Any]:
    """Store a templated historical `precedent` memory (no LLM)."""
    txn = state["txn"]
    customer = state["customer"]
    decision = state["decision"]
    principal_id = state["principal_id"]

    text = precedent_text_template(
        txn_type=txn["type"],
        amount=txn["amount"],
        customer_segment=customer.get("segment", "unknown"),
        verdict=decision["verdict"],
        reviewer_id=principal_id,
        comments=decision.get("comments", ""),
    )

    mem_id = new_id("MEM")
    prec_doc: Dict[str, Any] = {
        "memory_id": mem_id,
        "kind": "precedent",
        "txn_type": txn["type"],
        "text": text,
        "scope": None,
        "source_decision_id": decision["decision_id"],
        "source_txn_id": txn["txn_id"],
        "author_id": principal_id,
        "active": True,
        "created_at": utc_now_iso(),
    }

    await write_with_audit(
        actor=agent_actor(principal_id),
        event="memory.created",
        txn_id=txn["txn_id"],
        ref={"collection": "memory", "id": mem_id},
        detail={
            "kind": "precedent",
            "criterion_id": None,
            "source_decision_id": decision["decision_id"],
            "author_id": principal_id,
        },
        writes=[make_insert("memory", prec_doc)],
    )

    created = list(state.get("memory_created", [])) + [
        {"memory_id": mem_id, "kind": "precedent", "text": text}
    ]
    return {"memory_created": created}


# ---------------------------------------------------------------------------
# Routing Functions
# ---------------------------------------------------------------------------


def _route_input_kind(state: ReviewState) -> Literal["answer_question", "policy_gate"]:
    if state.get("input", {}).get("kind") == "question":
        return "answer_question"
    return "policy_gate"


def _route_gate(state: ReviewState) -> Literal["record_denied", "record_decision"]:
    if state.get("gate", {}).get("result") == "deny":
        return "record_denied"
    return "record_decision"


def _route_comments(state: ReviewState) -> Literal["learn_from_feedback", "store_precedent"]:
    comments = (state.get("input", {}).get("comments") or "").strip()
    if comments:
        return "learn_from_feedback"
    return "store_precedent"


# ---------------------------------------------------------------------------
# Graph Builder & Compiled Subgraph
# ---------------------------------------------------------------------------


def build_review_graph():
    """Construct and compile the Review `StateGraph`."""
    builder = StateGraph(ReviewState)
    builder.add_node("load_review", load_review)
    builder.add_node("answer_question", answer_question)
    builder.add_node("policy_gate", policy_gate)
    builder.add_node("record_denied", record_denied)
    builder.add_node("record_decision", record_decision)
    builder.add_node("learn_from_feedback", learn_from_feedback)
    builder.add_node("store_precedent", store_precedent)

    builder.add_edge(START, "load_review")
    builder.add_conditional_edges(
        "load_review",
        _route_input_kind,
        {"answer_question": "answer_question", "policy_gate": "policy_gate"},
    )
    builder.add_edge("answer_question", END)
    builder.add_conditional_edges(
        "policy_gate",
        _route_gate,
        {"record_denied": "record_denied", "record_decision": "record_decision"},
    )
    builder.add_edge("record_denied", END)
    builder.add_conditional_edges(
        "record_decision",
        _route_comments,
        {
            "learn_from_feedback": "learn_from_feedback",
            "store_precedent": "store_precedent",
        },
    )
    builder.add_edge("learn_from_feedback", "store_precedent")
    builder.add_edge("store_precedent", END)

    return builder.compile()


review_graph = build_review_graph()
