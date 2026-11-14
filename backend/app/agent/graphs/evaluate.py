"""
backend/app/graphs/evaluate.py
LangGraph `Evaluate` subgraph: evaluates a single transaction against policy.

Graph topology (`docs/plan-agent.md`):
    START -> load -> run_checks -> retrieve_context -> recommend -> save_evaluation -> END

Integration contract for future agents / parent graphs:
    Input state:
        {"txn_id": "TXN-0001", "principal_id": "ana"}
    Output state:
        Full `EvalState` including `evaluation` (matching `docs/contracts.md` §3.5),
        `txn`, `customer`, `policy`, `checks`, `precedents`, `adjustments`, `llm_output`.

Invariants enforced:
    - Hard checks are 100% deterministic Python (`app.checks.CHECKS`).
    - Overall `recommendation` is computed in Python, never by the LLM.
    - Untrusted `memo` and `counterparty` fields are excluded from vector queries
      and quarantined in prompts.
    - Hallucinated memory IDs returned by the LLM are stripped before saving.
    - Every DB write goes through `write_with_audit` with `on_behalf_of=principal_id`.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, TypedDict

from langgraph.graph import END, START, StateGraph

from app.agent.checks import CHECKS
from app.agent.graphs._deps import (
    agent_actor,
    make_insert,
    make_update,
    new_id,
    utc_now_iso,
    write_with_audit,
)
from app.agent.llm import get_structured_llm
from app.agent.memory import active_adjustments, build_structured_query, search_memory
from app.agent.prompts import build_recommend_messages
from app.agent.schemas import RecommendOutput
from app.db import get_db

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Graph State (docs/contracts.md §7)
# ---------------------------------------------------------------------------


class EvalState(TypedDict, total=False):
    """State passed between nodes of the Evaluate graph."""

    txn_id: str
    principal_id: str
    txn: Dict[str, Any]
    customer: Dict[str, Any]
    policy: Dict[str, Any]
    checks: List[Dict[str, Any]]
    precedents: List[Dict[str, Any]]
    adjustments: List[Dict[str, Any]]
    llm_output: Dict[str, Any]
    evaluation: Dict[str, Any]


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


async def load(state: EvalState) -> Dict[str, Any]:
    """Load transaction, customer profile, and active policy from MongoDB."""
    db = get_db()
    txn_id = state["txn_id"]

    txn = await db["transactions"].find_one({"txn_id": txn_id}, {"_id": 0})
    if not txn:
        raise KeyError(f"Transaction not found: {txn_id}")

    customer = await db["customers"].find_one(
        {"customer_id": txn["customer_id"]}, {"_id": 0}
    )
    if not customer:
        raise KeyError(f"Customer not found: {txn['customer_id']}")

    policy = await db["policies"].find_one(
        {"txn_type": txn["type"], "active": True}, {"_id": 0}
    )
    if not policy:
        raise KeyError(f"No active policy for txn_type={txn['type']}")

    return {"txn": txn, "customer": customer, "policy": policy}


async def run_checks(state: EvalState) -> Dict[str, Any]:
    """Execute all deterministic `hard` criteria via `app.checks.CHECKS`."""
    db = get_db()
    txn = state["txn"]
    customer = state["customer"]
    policy = state["policy"]

    hard_results: List[Dict[str, Any]] = []
    for criterion in policy.get("criteria", []):
        if criterion.get("kind") != "hard":
            continue

        check_name = criterion.get("check")
        check_fn = CHECKS.get(check_name) if check_name else None
        if check_fn is None:
            outcome = {
                "result": "no_pass",
                "evidence": f"Missing deterministic check handler: {check_name}",
            }
        else:
            outcome = await check_fn(
                txn, customer, criterion.get("params") or {}, db
            )

        hard_results.append(
            {
                "criterion_id": criterion["id"],
                "description": criterion["description"],
                "kind": "hard",
                "source": "rule",
                "result": outcome["result"],
                "evidence": outcome["evidence"],
                "regulation_ref": criterion.get("regulation_ref", ""),
                "precedents_used": [],
                "adjustments_used": [],
            }
        )

    return {"checks": hard_results}


async def retrieve_context(state: EvalState) -> Dict[str, Any]:
    """Retrieve relevant historical precedents (vector search) and active adjustments (find)."""
    txn = state["txn"]
    customer = state["customer"]
    hard_checks = state.get("checks", [])

    failed_hard = [
        {"criterion_id": c["criterion_id"], "evidence": c["evidence"]}
        for c in hard_checks
        if c.get("result") == "no_pass"
    ]

    structured_query = build_structured_query(
        txn_type=txn["type"],
        amount=txn.get("amount"),
        customer_segment=customer.get("segment"),
        failed_criteria=failed_hard,
    )

    precedents = await search_memory(
        query=structured_query,
        txn_type=txn["type"],
        kind="precedent",
        k=4,
    )
    adjustments = await active_adjustments(txn_type=txn["type"])

    return {"precedents": precedents, "adjustments": adjustments}


async def recommend(state: EvalState) -> Dict[str, Any]:
    """Invoke the LLM to evaluate `judgment` criteria only (`RecommendOutput`)."""
    policy = state["policy"]
    judgment_criteria = [
        c for c in policy.get("criteria", []) if c.get("kind") == "judgment"
    ]

    if not judgment_criteria:
        return {
            "llm_output": RecommendOutput(
                judgment_checks=[],
                rationale="All applicable policy criteria were evaluated deterministically.",
            ).model_dump()
        }

    messages = build_recommend_messages(
        txn=state["txn"],
        customer=state["customer"],
        hard_checks=state.get("checks", []),
        judgment_criteria=judgment_criteria,
        precedents=state.get("precedents", []),
        adjustments=state.get("adjustments", []),
    )

    structured_llm = get_structured_llm(RecommendOutput)

    last_err: Exception | None = None
    for attempt in range(2):
        try:
            output: RecommendOutput = await structured_llm.ainvoke(messages)
            return {"llm_output": output.model_dump()}
        except Exception as exc:
            last_err = exc
            logger.warning("recommend LLM attempt %d failed: %s", attempt + 1, exc)

    # Fallback per docs/plan-agent.md Risks: mark judgment checks no_pass on parse failure
    fallback = RecommendOutput(
        judgment_checks=[
            {
                "criterion_id": c["id"],
                "result": "no_pass",
                "evidence": f"model output invalid ({last_err})",
                "precedents_used": [],
                "adjustments_used": [],
            }
            for c in judgment_criteria
        ],
        rationale="Automatic evaluation failed to parse model judgment; escalated for manual review.",
    )
    return {"llm_output": fallback.model_dump()}


async def save_evaluation(state: EvalState) -> Dict[str, Any]:
    """
    Merge hard & judgment checks, compute `recommendation` in Python,
    strip ungrounded memory IDs, and persist via `write_with_audit`.
    """
    txn = state["txn"]
    policy = state["policy"]
    principal_id = state.get("principal_id") or "ana"
    hard_by_id = {c["criterion_id"]: c for c in state.get("checks", [])}

    valid_precedent_ids = {
        p["memory_id"] for p in state.get("precedents", []) if p.get("memory_id")
    }
    valid_adjustment_ids = {
        a["memory_id"] for a in state.get("adjustments", []) if a.get("memory_id")
    }

    llm_output = state.get("llm_output") or {}
    llm_by_id = {
        jc["criterion_id"]: jc for jc in llm_output.get("judgment_checks", [])
    }

    merged_checks: List[Dict[str, Any]] = []
    all_precedents_used: List[str] = []
    all_adjustments_used: List[str] = []

    for criterion in policy.get("criteria", []):
        cid = criterion["id"]
        if criterion.get("kind") == "hard":
            if cid in hard_by_id:
                merged_checks.append(hard_by_id[cid])
            else:
                merged_checks.append(
                    {
                        "criterion_id": cid,
                        "description": criterion["description"],
                        "kind": "hard",
                        "source": "rule",
                        "result": "no_pass",
                        "evidence": "Hard criterion result missing from run_checks.",
                        "regulation_ref": criterion.get("regulation_ref", ""),
                        "precedents_used": [],
                        "adjustments_used": [],
                    }
                )
            continue

        raw_jc = llm_by_id.get(cid)
        if raw_jc is None:
            jc_entry = {
                "criterion_id": cid,
                "description": criterion["description"],
                "kind": "judgment",
                "source": "llm",
                "result": "no_pass",
                "evidence": "Judgment criterion omitted from model output.",
                "regulation_ref": criterion.get("regulation_ref", ""),
                "precedents_used": [],
                "adjustments_used": [],
            }
        else:
            p_used = [
                mid for mid in raw_jc.get("precedents_used", []) if mid in valid_precedent_ids
            ]
            a_used = [
                mid for mid in raw_jc.get("adjustments_used", []) if mid in valid_adjustment_ids
            ]
            all_precedents_used.extend(m for m in p_used if m not in all_precedents_used)
            all_adjustments_used.extend(m for m in a_used if m not in all_adjustments_used)
            jc_entry = {
                "criterion_id": cid,
                "description": criterion["description"],
                "kind": "judgment",
                "source": "llm",
                "result": raw_jc["result"],
                "evidence": raw_jc["evidence"],
                "regulation_ref": criterion.get("regulation_ref", ""),
                "precedents_used": p_used,
                "adjustments_used": a_used,
            }
        merged_checks.append(jc_entry)

    recommendation = (
        "no_pass"
        if any(c.get("result") == "no_pass" for c in merged_checks)
        else "pass"
    )
    failed_ids = [c["criterion_id"] for c in merged_checks if c.get("result") == "no_pass"]

    eval_id = new_id("EVAL")
    actor = agent_actor(principal_id)
    now = utc_now_iso()

    evaluation_doc: Dict[str, Any] = {
        "eval_id": eval_id,
        "txn_id": txn["txn_id"],
        "actor": actor,
        "policy_version": policy.get("version", 1),
        "checks": merged_checks,
        "recommendation": recommendation,
        "rationale": llm_output.get("rationale", ""),
        "precedents_used": all_precedents_used,
        "adjustments_used": all_adjustments_used,
        "thread": [],
        "status": "awaiting_review",
        "created_at": now,
    }

    await write_with_audit(
        actor=actor,
        event="evaluation.created",
        txn_id=txn["txn_id"],
        ref={"collection": "evaluations", "id": eval_id},
        detail={
            "recommendation": recommendation,
            "policy_version": policy.get("version", 1),
            "failed": failed_ids,
            "precedents_used": all_precedents_used,
            "adjustments_used": all_adjustments_used,
        },
        writes=[
            make_insert("evaluations", evaluation_doc),
            make_update(
                "transactions",
                {"txn_id": txn["txn_id"]},
                {"$set": {"status": "awaiting_review"}},
            ),
        ],
    )

    return {"checks": merged_checks, "evaluation": evaluation_doc}


# ---------------------------------------------------------------------------
# Graph Builder & Compiled Subgraph
# ---------------------------------------------------------------------------


def build_evaluate_graph():
    """Construct and compile the Evaluate `StateGraph`."""
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
