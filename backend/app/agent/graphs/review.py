"""
backend/app/graphs/review.py
LangGraph `Review` subgraph: handles reviewer Q&A and human-in-the-loop decisions.

Graph topology (`docs/plan-agent.md`):
    START -> load_review
      --[question]--> answer_question -> END
      --[override]--> apply_override -> END
      --[decision]--> policy_gate
        --[blocked]-> END   (approving while a check is still effectively no_pass)
        --[deny]----> record_denied -> END
        --[allow]---> record_decision -> learn_from_feedback -> store_precedent -> END

Integration contract for future agents / parent graphs:
    Question mode input:
        {"eval_id": "EVAL-...", "principal_id": "ana",
         "input": {"kind": "question", "question": "Why did C-04 fail?"}}
    Decision mode input:
        {"eval_id": "EVAL-...", "principal_id": "ana",
         "input": {"kind": "decision", "verdict": "approved" | "rejected",
                   "comments": "Optional unless rejecting an effective pass."}}
    Override mode input (docs/contracts.md §8):
        {"eval_id": "EVAL-...", "principal_id": "ana",
         "input": {"kind": "override", "criterion_id": "C-04", "result": "pass",
                   "reason": "Payroll customers spike at month-end.", "via": "panel"}}
        result None reverts the override.

Invariants enforced:
    - `check_gate` runs before any decision is recorded; denials are audited (`decision.denied`).
    - `learn_from_feedback` strictly discards any adjustment targeting a `hard` criterion.
    - The agent's `result` and `recommendation` are never rewritten; overrides sit beside them.
    - A chat override is only extracted by the model; code applies it through the same gate.
    - `store_precedent` uses a deterministic template (`precedent_text_template`), never an LLM.
    - All DB writes go through `write_with_audit`.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from app.agent.graphs._deps import (
    agent_actor,
    check_gate,
    human_actor,
    make_insert,
    make_update,
    new_id,
    utc_now_iso,
    write_with_audit,
)
from app.agent.llm import get_structured_llm
from app.agent.memory import (
    active_adjustments,
    build_structured_query,
    precedent_text_template,
    search_memory,
)
from app.agent.prompts import build_answer_messages, build_learn_messages
from app.agent.schemas import AnswerOutput, LearnOutput
from app.db import get_db

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
    override: Dict[str, Any]
    blocking_checks: List[str]
    decision: Dict[str, Any]
    memory_created: List[Dict[str, Any]]


# ---------------------------------------------------------------------------
# Check overrides (docs/contracts.md §8)
# ---------------------------------------------------------------------------

_RESULT_LABEL = {"pass": "PASS", "no_pass": "NO-PASS", "flag": "FLAG"}
# A chat override must be asked for in the reviewer's own words.
_OVERRIDE_REQUEST = re.compile(
    r"\b(switch|change|override|overrule|flip|set|mark|update|make|turn|clear)\b", re.I
)


def _effective_result(check: Dict[str, Any]) -> str:
    override = check.get("override")
    return override["result"] if override else check["result"]


def _effective_recommendation(checks: List[Dict[str, Any]]) -> str:
    return "no_pass" if any(_effective_result(c) == "no_pass" for c in checks) else "pass"


def _with_effective(evaluation: Dict[str, Any]) -> Dict[str, Any]:
    """Fill the §8 view fields on evaluations stored before overrides existed."""
    checks = [
        {**c, "override": c.get("override"), "effective_result": _effective_result(c)}
        for c in evaluation.get("checks", [])
    ]
    return {**evaluation, "checks": checks, "effective_recommendation": _effective_recommendation(checks)}


async def _apply_override(
    state: ReviewState, *, criterion_id: str, result: str | None, reason: str, via: str
) -> Dict[str, Any]:
    """Gate, then record or revert one check override. No model call.

    Returns {"gate", "evaluation", "override": {criterion_id, from, to, status}}.
    """
    principal = state["principal"]
    txn = state["txn"]
    evaluation = state["evaluation"]
    eval_id = evaluation["eval_id"]
    check = next((c for c in evaluation["checks"] if c["criterion_id"] == criterion_id), None)
    if check is None:
        raise KeyError(f"Criterion not found in {eval_id}: {criterion_id}")
    if evaluation.get("status") != "awaiting_review":
        raise AlreadyDecidedError(f"Evaluation {eval_id} is {evaluation.get('status')}.")

    current = _effective_result(check)
    target = result if result is not None else check["result"]
    report = {"criterion_id": criterion_id, "from": current, "to": target}

    gate = await check_gate(
        principal=principal, txn=txn, evaluation=evaluation, action="override", check=check
    )
    if gate["result"] == "deny":
        await write_with_audit(
            actor=human_actor(principal),
            event="decision.denied",
            txn_id=txn["txn_id"],
            ref={"collection": "evaluations", "id": eval_id},
            detail={
                "action": "override", "criterion_id": criterion_id,
                "from": current, "to": target, "via": via,
                "amount": txn.get("amount"), "gate": gate,
            },
            writes=[],
        )
        return {"gate": gate, "evaluation": evaluation, "override": {**report, "status": "denied"}}

    if result is None and not check.get("override"):
        # Nothing to revert; not an event worth recording.
        return {"gate": gate, "evaluation": evaluation, "override": {**report, "status": "applied"}}

    override_doc = None if result is None else {
        "result": result,
        "reason": reason.strip(),
        "by": principal["_id"],
        "role": principal.get("role"),
        "via": via,
        "ts": utc_now_iso(),
        "gate": {"result": gate["result"], "rule_id": gate.get("rule_id")},
    }
    checks = [
        {**c, "override": override_doc, "effective_result": target}
        if c["criterion_id"] == criterion_id else c
        for c in evaluation["checks"]
    ]
    effective = _effective_recommendation(checks)

    if result is None:
        event, detail = "check.override_reverted", {
            "criterion_id": criterion_id, "from": current, "to": target, "via": via,
        }
    else:
        event, detail = "check.overridden", {
            "criterion_id": criterion_id, "kind": check.get("kind"),
            "from": current, "to": target, "reason": reason.strip(), "via": via,
            "gate": {"result": gate["result"], "rule_id": gate.get("rule_id")},
        }
    await write_with_audit(
        actor=human_actor(principal),
        event=event,
        txn_id=txn["txn_id"],
        ref={"collection": "evaluations", "id": eval_id},
        detail=detail,
        writes=[
            make_update(
                "evaluations",
                {"eval_id": eval_id, "checks.criterion_id": criterion_id},
                {"$set": {
                    "checks.$.override": override_doc,
                    "checks.$.effective_result": target,
                    "effective_recommendation": effective,
                }},
            )
        ],
    )
    updated = {**evaluation, "checks": checks, "effective_recommendation": effective}
    return {"gate": gate, "evaluation": updated, "override": {**report, "status": "applied"}}


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


async def load_review(state: ReviewState) -> Dict[str, Any]:
    """Load evaluation, transaction, customer, active policy, and acting principal."""
    db = get_db()
    eval_id = state["eval_id"]
    principal_id = state["principal_id"]

    principal = await db["principals"].find_one({"_id": principal_id})
    if not principal:
        raise PermissionError(f"Unknown principal: {principal_id}")

    evaluation = await db["evaluations"].find_one({"eval_id": eval_id}, {"_id": 0})
    if not evaluation:
        raise KeyError(f"Evaluation not found: {eval_id}")

    evaluation = _with_effective(evaluation)
    if state.get("input", {}).get("kind") in ("decision", "override") and evaluation.get("status") == "decided":
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
                    "label": getattr(cit, "label", None) or prec_labels.get(cit.ref, ""),
                }
            )
        elif cit.type == "adjustment" and cit.ref in valid_adjustments:
            clean_citations.append(
                {
                    "type": "adjustment",
                    "ref": cit.ref,
                    "label": getattr(cit, "label", None) or adj_labels.get(cit.ref, ""),
                }
            )

    # A chat override: the model only extracted the intent. Code decides and writes,
    # and code (not the model) words the outcome, so the answer cannot overstate it.
    answer_text = output.answer
    override_report = None
    action = output.action
    if (
        action is not None
        and _OVERRIDE_REQUEST.search(question)
        and evaluation.get("status") == "awaiting_review"
    ):
        check = next(
            (c for c in evaluation["checks"] if c["criterion_id"] == action.criterion_id), None
        )
        if check is not None:
            current = _effective_result(check)
            change = f"{action.criterion_id} from {_RESULT_LABEL[current]} to {_RESULT_LABEL[action.result]}"
            if not (action.reason or "").strip():
                override_report = {
                    "criterion_id": action.criterion_id, "from": current,
                    "to": action.result, "status": "needs_reason",
                }
                answer_text = (
                    f"I have not changed anything. To switch {change}, tell me the reason "
                    "for the override and I will record it."
                )
            elif current == action.result:
                answer_text = f"{action.criterion_id} is already {_RESULT_LABEL[current]}. Nothing was changed."
            else:
                applied = await _apply_override(
                    state, criterion_id=action.criterion_id, result=action.result,
                    reason=action.reason, via="chat",
                )
                override_report = applied["override"]
                evaluation = applied["evaluation"]
                if override_report["status"] == "applied":
                    role = str(state["principal"].get("role", "reviewer")).capitalize()
                    answer_text = (
                        f"Done. I switched {change} and tagged it \"{role} override\". "
                        f"Reason recorded: {action.reason.strip()} "
                        f"The agent's original result is kept beside it. The recommendation is now "
                        f"{_RESULT_LABEL[evaluation['effective_recommendation']]}."
                    )
                else:
                    answer_text = (
                        f"I could not switch {change}: {applied['gate']['reason']} Nothing was changed."
                    )

    thread_entry = {
        "question": question,
        "answer": answer_text,
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

    updated_evaluation = {**evaluation, "thread": updated_thread}
    return {
        "evaluation": updated_evaluation,
        "override": override_report,
        "answer": {
            "answer": answer_text,
            "citations": clean_citations,
            "thread": updated_thread,
        },
    }


async def policy_gate(state: ReviewState) -> Dict[str, Any]:
    """Run deterministic policy gate before allowing a human decision."""
    verdict = state["input"]["verdict"]
    if verdict not in ("approved", "rejected"):
        raise ValueError(f"Unknown verdict: {verdict}")
    if verdict == "approved":
        # Precondition, not a gate rule: every failed check must have been cleared.
        blocking = [
            c["criterion_id"] for c in state["evaluation"]["checks"]
            if _effective_result(c) == "no_pass"
        ]
        if blocking:
            return {"blocking_checks": blocking}
    gate = await check_gate(
        principal=state["principal"],
        txn=state["txn"],
        evaluation=state["evaluation"],
        verdict=verdict,
        action="decision",
    )
    return {"gate": gate}


async def apply_override(state: ReviewState) -> Dict[str, Any]:
    """Override (or revert) one check from the checks panel."""
    data = state["input"]
    return await _apply_override(
        state,
        criterion_id=data["criterion_id"],
        result=data.get("result"),
        reason=data.get("reason") or "",
        via=data.get("via") or "panel",
    )


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
            "action": "decision",
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

    # Against the agent's ORIGINAL recommendation, not the effective one.
    agreed_with_agent = (verdict == "approved") == (
        evaluation.get("recommendation") == "pass"
    )
    new_txn_status = "passed" if verdict == "approved" else "rejected"
    overrides = [
        {
            "criterion_id": c["criterion_id"], "kind": c.get("kind"),
            "from": c["result"], "to": c["override"]["result"],
            "reason": c["override"].get("reason", ""), "via": c["override"].get("via"),
        }
        for c in evaluation["checks"] if c.get("override")
    ]

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
        "effective_recommendation": evaluation["effective_recommendation"],
        "overrides": overrides,
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
            "effective_recommendation": evaluation["effective_recommendation"],
            "overrides": [o["criterion_id"] for o in overrides],
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


async def _create_adjustment(
    state: ReviewState, *, criterion_id: str, text: str, condition: str
) -> Dict[str, Any]:
    txn = state["txn"]
    decision = state["decision"]
    principal_id = state["principal_id"]
    mem_id = new_id("MEM")
    adj_doc: Dict[str, Any] = {
        "memory_id": mem_id,
        "kind": "adjustment",
        "txn_type": txn["type"],
        "text": text.strip(),
        "scope": {"criterion_id": criterion_id, "condition": condition.strip()},
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
            "criterion_id": criterion_id,
            "source_decision_id": decision["decision_id"],
            "author_id": principal_id,
        },
        writes=[make_insert("memory", adj_doc)],
    )
    return {"memory_id": mem_id, "kind": "adjustment", "text": adj_doc["text"]}


async def _draft_adjustment(state: ReviewState, *, feedback: str, judgment_criteria: List[Dict[str, Any]]) -> LearnOutput | None:
    messages = build_learn_messages(
        verdict=state["input"]["verdict"],
        comments=feedback,
        txn=state["txn"],
        customer=state["customer"],
        evaluation_checks=state["evaluation"].get("checks", []),
        judgment_criteria=judgment_criteria,
    )
    try:
        return await get_structured_llm(LearnOutput).ainvoke(messages)
    except Exception as exc:
        logger.warning("learn_from_feedback LLM failed: %s", exc)
        return None


async def learn_from_feedback(state: ReviewState) -> Dict[str, Any]:
    """
    Turn the reviewer's feedback into reusable `adjustment` memories. Runs at the
    decision, so a reverted override never reaches memory.

    - Each override of a `judgment` check becomes an adjustment on exactly that
      criterion; the model only words the condition and guidance.
    - Overrides of `hard` checks never become adjustments (invariant 4).
    - A decision comment may still teach an adjustment, on a judgment criterion only.
    """
    policy = state["policy"]
    judgment_criteria = [
        c for c in policy.get("criteria", []) if c.get("kind") == "judgment"
    ]
    judgment_ids = {c["id"] for c in judgment_criteria}
    if not judgment_criteria:
        return {}

    created = list(state.get("memory_created", []))
    learned: set[str] = set()
    segment = state["customer"].get("segment", "similar")

    for check in state["evaluation"].get("checks", []):
        override = check.get("override")
        cid = check["criterion_id"]
        if not override or cid not in judgment_ids or override["result"] == check["result"]:
            continue
        reason = (override.get("reason") or "").strip()
        if not reason:
            continue
        feedback = (
            f"The reviewer overrode criterion {cid} ({check.get('description', '')}) from "
            f"{check['result']} to {override['result']}. Reason given: {reason}"
        )
        output = await _draft_adjustment(state, feedback=feedback, judgment_criteria=judgment_criteria)
        if output is not None and not output.should_create:
            logger.info("Override reason for %s is case-specific; no adjustment.", cid)
            continue
        text = (output.text if output else None) or reason
        condition = (output.condition if output else None) or (
            f"{state['txn']['type']} transactions for {segment} customers in similar circumstances"
        )
        # The criterion comes from the override, never from the model.
        created.append(await _create_adjustment(state, criterion_id=cid, text=text, condition=condition))
        learned.add(cid)

    comments = (state["input"].get("comments") or "").strip()
    if comments:
        output = await _draft_adjustment(state, feedback=comments, judgment_criteria=judgment_criteria)
        if (
            output is not None and output.should_create and output.text and output.condition
            and output.criterion_id in judgment_ids and output.criterion_id not in learned
        ):
            created.append(await _create_adjustment(
                state, criterion_id=output.criterion_id, text=output.text, condition=output.condition,
            ))

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
        comments=" ".join(filter(None, [
            decision.get("comments", ""),
            *(
                f"Overrode {o['criterion_id']} ({o['kind']}) from {o['from']} to {o['to']}: {o['reason']}"
                for o in decision.get("overrides", [])
            ),
        ])),
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


def _route_input_kind(state: ReviewState) -> Literal["answer_question", "apply_override", "policy_gate"]:
    kind = state.get("input", {}).get("kind")
    if kind == "question":
        return "answer_question"
    if kind == "override":
        return "apply_override"
    if kind == "decision":
        return "policy_gate"
    raise ValueError(f"Unknown review input kind: {kind}")


def _route_gate(state: ReviewState) -> Literal["blocked", "record_denied", "record_decision"]:
    if state.get("blocking_checks"):
        return "blocked"
    if state.get("gate", {}).get("result") == "deny":
        return "record_denied"
    return "record_decision"


# ---------------------------------------------------------------------------
# Graph Builder & Compiled Subgraph
# ---------------------------------------------------------------------------


def build_review_graph():
    """Construct and compile the Review `StateGraph`."""
    builder = StateGraph(ReviewState)
    builder.add_node("load_review", load_review)
    builder.add_node("answer_question", answer_question)
    builder.add_node("apply_override", apply_override)
    builder.add_node("policy_gate", policy_gate)
    builder.add_node("record_denied", record_denied)
    builder.add_node("record_decision", record_decision)
    builder.add_node("learn_from_feedback", learn_from_feedback)
    builder.add_node("store_precedent", store_precedent)

    builder.add_edge(START, "load_review")
    builder.add_conditional_edges(
        "load_review",
        _route_input_kind,
        {
            "answer_question": "answer_question",
            "apply_override": "apply_override",
            "policy_gate": "policy_gate",
        },
    )
    builder.add_edge("answer_question", END)
    builder.add_edge("apply_override", END)
    builder.add_conditional_edges(
        "policy_gate",
        _route_gate,
        {"blocked": END, "record_denied": "record_denied", "record_decision": "record_decision"},
    )
    builder.add_edge("record_denied", END)
    builder.add_edge("record_decision", "learn_from_feedback")
    builder.add_edge("learn_from_feedback", "store_precedent")
    builder.add_edge("store_precedent", END)

    return builder.compile()


review_graph = build_review_graph()
