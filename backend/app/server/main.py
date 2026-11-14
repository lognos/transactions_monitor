"""FastAPI app. Routes and shapes: docs/contracts.md §4.

The server reads MongoDB for lists and lookups. Anything that evaluates,
answers or decides goes through app.agent (run_evaluate, run_review, run_chat).
"""

import asyncio
import inspect
from contextlib import asynccontextmanager
from typing import Any, Literal

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import agent
from app.config import settings
from app.db import close_client, get_db, ping
from app.db.audit import verify_chain
from app.server.deps import current_principal
from app.server.errors import ApiError, install_error_handlers
from app.server.references import get_check_references, label_citations
from app.server.schemas import (
    AskBody, ChatBody, DecideBody, EvaluatePendingBody, OverrideBody, SimulateBody,
)
from app.server.serialization import public_data

NO_ID = {"_id": 0}


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await close_client()


app = FastAPI(title="Transaction Validation Agent", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
install_error_handlers(app)

Principal = Depends(current_principal)


@app.get("/health")
async def health() -> dict[str, Any]:
    try:
        await ping()
        return {"ok": True, "db": settings.db_name}
    except Exception as exc:  # report, don't crash: this is the connection check
        return {"ok": False, "db": settings.db_name, "error": type(exc).__name__}


@app.get("/principals")
async def list_principals() -> dict[str, Any]:
    """No identity needed: this fills the login screen."""
    principals = await get_db().principals.find({"type": "human"}).to_list()
    return {"principals": [{**public_data(p), "_id": p["_id"]} for p in principals]}


async def _transaction_rows(query: dict[str, Any]) -> list[dict[str, Any]]:
    cursor = await get_db().transactions.aggregate([
        # Raw CSV imports share this collection, but are not review-ready.
        # Do not invent workflow status or amounts for unnormalized records.
        {"$match": {"$and": [query, {
            "txn_id": {"$type": "string"},
            "type": {"$in": ["wire", "cheque", "eft", "interac", "pad", "bill_payment"]},
            "amount": {"$type": "number"},
            "currency": {"$type": "string"},
            "status": {"$in": ["pending", "awaiting_review", "passed", "rejected"]},
            "created_at": {"$type": ["date", "string"]},
        }]}},
        {"$sort": {"created_at": 1, "txn_id": 1}},
        {"$lookup": {
            "from": "customers", "localField": "customer_id",
            "foreignField": "customer_id", "as": "customer",
        }},
        {"$lookup": {
            "from": "evaluations", "let": {"txn_id": "$txn_id"},
            "pipeline": [
                {"$match": {"$expr": {"$eq": ["$txn_id", "$$txn_id"]},
                            "status": {"$ne": "superseded"}}},
                {"$sort": {"created_at": -1, "eval_id": -1}},
                {"$limit": 1},
                {"$project": {"_id": 0, "eval_id": 1, "recommendation": 1,
                              "effective_recommendation": 1, "checks": 1}},
            ],
            "as": "latest",
        }},
        {"$set": {"latest": {"$arrayElemAt": ["$latest", 0]}}},
        {"$project": {
            "_id": 0, "txn_id": 1, "type": 1, "amount": 1, "currency": 1,
            "memo": 1, "status": 1, "created_at": 1,
            "customer_name": {"$ifNull": [{"$arrayElemAt": ["$customer.name", 0]}, None]},
            "counterparty_name": {"$ifNull": ["$counterparty.name", None]},
            "eval_id": {"$ifNull": ["$latest.eval_id", None]},
            "recommendation": {"$ifNull": ["$latest.recommendation", None]},
            "effective_recommendation": {"$ifNull": [
                "$latest.effective_recommendation", "$latest.recommendation", None,
            ]},
            "override_count": {"$size": {"$filter": {
                "input": {"$ifNull": ["$latest.checks", []]},
                "as": "check", "cond": {"$ne": [{"$ifNull": ["$$check.override", None]}, None]},
            }}},
            "failed_checks": {"$map": {
                "input": {"$filter": {
                    "input": {"$ifNull": ["$latest.checks", []]},
                    "as": "check", "cond": {"$eq": [
                        {"$ifNull": ["$$check.effective_result", "$$check.result"]}, "no_pass",
                    ]},
                }},
                "as": "check", "in": "$$check.criterion_id",
            }},
        }},
    ])
    return await cursor.to_list()


@app.get("/transactions")
async def list_transactions(
    status: Literal["pending", "awaiting_review", "passed", "rejected"] | None = None,
    _: dict = Principal,
) -> dict[str, Any]:
    query = {"status": status} if status else {}
    return public_data({"transactions": await _transaction_rows(query)})


def _require_refresh_support() -> None:
    # Check before invoking the agent, so an internal TypeError is never mistaken
    # for an unavailable interface (or retried after it has already written).
    try:
        inspect.signature(agent.run_evaluate).bind(txn_id="", principal_id="", refresh=False)
    except TypeError as exc:
        raise NotImplementedError("agent.run_evaluate refresh parameter") from exc


@app.post("/transactions/evaluate-pending")
async def evaluate_pending(
    body: EvaluatePendingBody, principal: dict = Principal,
) -> dict[str, Any]:
    _require_refresh_support()
    statuses = ["pending", "awaiting_review"] if body.refresh else ["pending"]
    txns = await _transaction_rows({"status": {"$in": statuses}})
    if body.refresh:
        txns = [txn for txn in txns if txn["override_count"] == 0]

    async def evaluate_one(txn: dict[str, Any]) -> dict[str, Any]:
        result = await evaluate(txn["txn_id"], refresh=body.refresh, principal=principal)
        return {
            "txn_id": txn["txn_id"], "eval_id": result["eval_id"],
            "recommendation": result["recommendation"],
            "changed": txn["effective_recommendation"] is not None
            and txn["effective_recommendation"] != result["effective_recommendation"],
        }

    results = await asyncio.gather(*(evaluate_one(txn) for txn in txns), return_exceptions=True)
    evaluated, failed = [], []
    for txn, result in zip(txns, results):
        if isinstance(result, Exception):
            if isinstance(result, ApiError):
                message = result.message
            elif isinstance(result, NotImplementedError):
                message = f"Not built yet: {result}"
            else:
                # Driver/provider exceptions can contain credentials or payloads.
                message = f"Evaluation failed ({type(result).__name__}). Retry this transaction."
            failed.append({"txn_id": txn["txn_id"], "error": message})
        else:
            evaluated.append(result)
    return public_data({"evaluated": evaluated, "failed": failed})


@app.post("/transactions/simulate")
async def simulate(
    body: SimulateBody, principal: dict = Principal,
) -> dict[str, Any]:
    result = await agent.run_simulate(
        principal_id=principal["_id"],
        count=body.count,
        mode=body.mode,
        policy_only=body.policy_only,
    )
    return public_data(result)


@app.post("/transactions/{txn_id}/evaluate")
async def evaluate(
    txn_id: str, refresh: bool = False, principal: dict = Principal,
) -> dict[str, Any]:
    db = get_db()
    txn = await db.transactions.find_one({"txn_id": txn_id}, NO_ID)
    if txn is None:
        raise ApiError(404, "not_found", f"Unknown transaction '{txn_id}'")
    if txn["status"] in ("passed", "rejected"):
        raise ApiError(409, "already_decided", f"Transaction '{txn_id}' already has a decision")
    existing = await db.evaluations.find_one(
        {"txn_id": txn_id, "status": {"$ne": "superseded"}}, NO_ID,
        sort=[("created_at", -1), ("eval_id", -1)],
    )
    if existing and existing["status"] == "decided":
        raise ApiError(409, "already_decided", f"Transaction '{txn_id}' already has a decision")
    # Section 8 protects overrides from every refresh, including a direct call.
    has_overrides = existing and any(c.get("override") is not None for c in existing["checks"])
    if existing and (has_overrides or (txn["status"] == "awaiting_review" and not refresh)):
        customer = await db.customers.find_one({"customer_id": txn["customer_id"]}, NO_ID)
        return public_data({**existing, "transaction": txn, "customer": customer})
    _require_refresh_support()
    result = await agent.run_evaluate(
        txn_id=txn_id, principal_id=principal["_id"], refresh=refresh,
    )
    return public_data({
        **result["evaluation"],
        "transaction": result["transaction"],
        "customer": result["customer"],
    })


async def _evaluation_or_404(eval_id: str) -> dict[str, Any]:
    evaluation = await get_db().evaluations.find_one({"eval_id": eval_id}, NO_ID)
    if evaluation is None:
        raise ApiError(404, "not_found", f"Unknown evaluation '{eval_id}'")
    return public_data(evaluation)


def _require_reviewable(evaluation: dict[str, Any]) -> None:
    if evaluation["status"] == "decided":
        raise ApiError(409, "already_decided", f"Evaluation '{evaluation['eval_id']}' already has a decision")
    if evaluation["status"] == "superseded":
        raise ApiError(422, "invalid_request", "This evaluation was superseded. Open the latest evaluation.")


def _review_gate(result: dict[str, Any], kind: str) -> dict[str, Any]:
    gate = result.get("gate")
    if not isinstance(gate, dict) or gate.get("result") not in ("allow", "deny"):
        raise NotImplementedError(f"agent.run_review {kind} gate result")
    return gate


def _checks_not_cleared(blocking_checks: list[str]) -> ApiError:
    return ApiError(
        409, "checks_not_cleared", f"Clear {' and '.join(blocking_checks)} before approving.",
        extra={"blocking_checks": blocking_checks},
    )


@app.get("/evaluations/{eval_id}")
async def get_evaluation(eval_id: str, _: dict = Principal) -> dict[str, Any]:
    db = get_db()
    evaluation = await _evaluation_or_404(eval_id)
    txn = await db.transactions.find_one({"txn_id": evaluation["txn_id"]}, NO_ID)
    if txn is None:
        raise ApiError(404, "not_found", f"Unknown transaction '{evaluation['txn_id']}'")
    customer = await db.customers.find_one({"customer_id": txn["customer_id"]}, NO_ID)
    decision = await db.decisions.find_one({"eval_id": eval_id}, NO_ID)
    return public_data({**evaluation, "transaction": txn, "customer": customer, "decision": decision})


@app.get("/evaluations/{eval_id}/checks/{criterion_id}/references")
async def references(eval_id: str, criterion_id: str, _: dict = Principal) -> dict[str, Any]:
    return public_data(await get_check_references(eval_id, criterion_id))


@app.post("/evaluations/{eval_id}/checks/{criterion_id}/override")
async def override_check(
    eval_id: str, criterion_id: str, body: OverrideBody, principal: dict = Principal,
) -> dict[str, Any]:
    evaluation = await _evaluation_or_404(eval_id)
    if not any(check["criterion_id"] == criterion_id for check in evaluation["checks"]):
        raise ApiError(404, "not_found", f"Unknown criterion '{criterion_id}' in '{eval_id}'")
    _require_reviewable(evaluation)
    result = await agent.run_review(
        eval_id=eval_id, principal_id=principal["_id"],
        review_input={"kind": "override", "criterion_id": criterion_id,
                      "result": body.result, "reason": body.reason or "", "via": "panel"},
    )
    gate = _review_gate(result, "override")
    if gate["result"] == "deny":
        txn = await get_db().transactions.find_one({"txn_id": evaluation["txn_id"]}, NO_ID)
        message = await _gate_denial_message(gate, evaluation, txn, principal, action="override")
        raise ApiError(403, "gate_denied", message, extra={"gate": gate})
    # Only the agent writes; return its persisted result, including context.
    return await get_evaluation(eval_id, principal)


@app.post("/chat")
async def chat(body: ChatBody, principal: dict = Principal) -> dict[str, Any]:
    run_chat = getattr(agent, "run_chat", None)
    if run_chat is None:
        raise NotImplementedError("agent.run_chat")
    result = await run_chat(message=body.message, principal_id=principal["_id"])
    return public_data({
        "answer": result["answer"],
        "citations": await label_citations(result["citations"]),
    })


@app.post("/evaluations/{eval_id}/ask")
async def ask(eval_id: str, body: AskBody, principal: dict = Principal) -> dict[str, Any]:
    evaluation = await _evaluation_or_404(eval_id)
    result = await agent.run_review(
        eval_id=eval_id,
        principal_id=principal["_id"],
        review_input={"kind": "question", "question": body.question},
    )
    answer = result.get("answer")
    if not isinstance(answer, dict) or not isinstance(result.get("evaluation"), dict):
        raise NotImplementedError("agent.run_review question answer and evaluation")
    override = result.get("override")
    updated_evaluation = None
    if override is not None:
        override = {key: override[key] for key in ("criterion_id", "from", "to", "status")}
        if override["status"] == "applied":
            updated_evaluation = await get_evaluation(eval_id, principal)
    thread = (updated_evaluation or result["evaluation"])["thread"]
    # Include labels in history too, so reopening a conversation keeps its chips.
    citations = list(answer["citations"])
    for turn in thread:
        citations.extend(turn.get("citations", []))
    labelled = await label_citations(citations, evaluation=evaluation)
    labels = {(c["type"], c["ref"]): c["label"] for c in labelled}
    return public_data({
        "answer": answer["answer"], "citations": labelled[:len(answer["citations"])],
        "override": override, "evaluation": updated_evaluation,
        "thread": [{**turn, "citations": [
            {**c, "label": labels[(c["type"], c["ref"])]} for c in turn.get("citations", [])
        ]} for turn in thread],
    })


async def _gate_denial_message(
    gate: dict[str, Any], evaluation: dict[str, Any], txn: dict[str, Any] | None,
    principal: dict[str, Any], action: str = "decide",
) -> str:
    if txn is None:
        return f"{gate['reason'].rstrip('.')}. Ask an authorized reviewer to review the policy requirements."
    policy = await get_db().policies.find_one(
        {"txn_type": txn["type"], "version": evaluation["policy_version"]}, NO_ID,
    )
    rules = (policy or {}).get("decision_rules", [])
    rule = next((r for r in rules if r["rule_id"] == gate.get("rule_id")), None)
    if rule is None:
        if policy and not any(r["role"] == principal["role"] for r in rules):
            verb = "override checks" if action == "override" else "decide"
            return f"Role '{principal['role']}' cannot {verb}. An authorized reviewer must {verb}."
    else:
        limit = rule.get("max_amount")
        if limit is not None and txn["amount"] > limit:
            supervisor = any(
                r["role"] == "supervisor"
                and (r.get("max_amount") is None or txn["amount"] <= r["max_amount"])
                for r in rules
            )
            reviewer = "A supervisor" if supervisor else "A reviewer with a higher limit"
            verb = "authorize this override" if action == "override" else "decide"
            return f"Amount {txn['amount']:g} exceeds {principal['role']} limit {limit:g}. {reviewer} must {verb}."
    return f"{gate['reason'].rstrip('.')}. Review the policy requirements before retrying."


@app.post("/evaluations/{eval_id}/decide")
async def decide(eval_id: str, body: DecideBody, principal: dict = Principal) -> dict[str, Any]:
    evaluation = await _evaluation_or_404(eval_id)
    _require_reviewable(evaluation)
    if body.verdict == "approved":
        blocking_checks = [check["criterion_id"] for check in evaluation["checks"]
                           if check["effective_result"] == "no_pass"]
        if blocking_checks:
            raise _checks_not_cleared(blocking_checks)
    elif evaluation["effective_recommendation"] == "pass" and not (body.comments or "").strip():
        raise ApiError(422, "invalid_request", "Comments are required when rejecting an effective pass.")
    result = await agent.run_review(
        eval_id=eval_id,
        principal_id=principal["_id"],
        review_input={"kind": "decision", "verdict": body.verdict, "comments": body.comments},
    )
    if result.get("blocking_checks"):
        raise _checks_not_cleared(result["blocking_checks"])
    gate = _review_gate(result, "decision")
    if gate["result"] == "deny":
        txn = result.get("txn") or await get_db().transactions.find_one({"txn_id": evaluation["txn_id"]}, NO_ID)
        message = await _gate_denial_message(gate, evaluation, txn, principal)
        raise ApiError(403, "gate_denied", message, extra={"gate": gate})
    if not isinstance(result.get("decision"), dict) or not isinstance(result.get("txn"), dict):
        raise NotImplementedError("agent.run_review decision and txn")
    return public_data({
        "decision": result["decision"],
        "transaction_status": result["txn"]["status"],
        "memory_created": result.get("memory_created") or [],
    })


@app.get("/audit")
async def audit(txn_id: str | None = None, _: dict = Principal) -> dict[str, Any]:
    query = {"txn_id": txn_id} if txn_id else {}
    events = await get_db().audit_log.find(query, NO_ID).sort("seq", 1).to_list()
    return public_data({"events": events})


@app.get("/audit/verify")
async def audit_verify(_: dict = Principal) -> dict[str, Any]:
    return public_data(await verify_chain())
