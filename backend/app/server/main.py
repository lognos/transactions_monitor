"""FastAPI app. Routes and shapes: docs/contracts.md §4.

The server reads MongoDB for lists and lookups. Anything that evaluates,
answers or decides goes through app.agent (run_evaluate, run_review).
"""

from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import agent
from app.config import settings
from app.db import close_client, get_db, ping
from app.db.audit import verify_chain
from app.server.deps import current_principal
from app.server.errors import ApiError, install_error_handlers
from app.server.schemas import AskBody, DecideBody

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
    """No header needed: this fills the "acting as" dropdown."""
    principals = await get_db().principals.find({"type": "human"}).to_list()
    return {"principals": principals}


@app.get("/transactions")
async def list_transactions(status: str | None = None, _: dict = Principal) -> dict[str, Any]:
    query = {"status": status} if status else {}
    txns = await get_db().transactions.find(query, NO_ID).sort("created_at", 1).to_list()
    # TODO(server): add customer_name, counterparty_name and latest eval_id per contracts §4.
    return {"transactions": txns}


@app.post("/transactions/{txn_id}/evaluate")
async def evaluate(txn_id: str, principal: dict = Principal) -> dict[str, Any]:
    db = get_db()
    txn = await db.transactions.find_one({"txn_id": txn_id}, NO_ID)
    if txn is None:
        raise ApiError(404, "not_found", f"Unknown transaction '{txn_id}'")
    if txn["status"] == "awaiting_review":
        existing = await db.evaluations.find_one(
            {"txn_id": txn_id, "status": "awaiting_review"}, NO_ID
        )
        if existing:
            customer = await db.customers.find_one({"customer_id": txn["customer_id"]}, NO_ID)
            return {**existing, "transaction": txn, "customer": customer}
    result = await agent.run_evaluate(txn_id=txn_id, principal_id=principal["_id"])
    return {
        **result["evaluation"],
        "transaction": result["transaction"],
        "customer": result["customer"],
    }


async def _evaluation_or_404(eval_id: str) -> dict[str, Any]:
    evaluation = await get_db().evaluations.find_one({"eval_id": eval_id}, NO_ID)
    if evaluation is None:
        raise ApiError(404, "not_found", f"Unknown evaluation '{eval_id}'")
    return evaluation


@app.get("/evaluations/{eval_id}")
async def get_evaluation(eval_id: str, _: dict = Principal) -> dict[str, Any]:
    db = get_db()
    evaluation = await _evaluation_or_404(eval_id)
    txn = await db.transactions.find_one({"txn_id": evaluation["txn_id"]}, NO_ID)
    customer = await db.customers.find_one({"customer_id": txn["customer_id"]}, NO_ID)
    decision = await db.decisions.find_one({"eval_id": eval_id}, NO_ID)
    return {**evaluation, "transaction": txn, "customer": customer, "decision": decision}


@app.post("/evaluations/{eval_id}/ask")
async def ask(eval_id: str, body: AskBody, principal: dict = Principal) -> dict[str, Any]:
    await _evaluation_or_404(eval_id)
    result = await agent.run_review(
        eval_id=eval_id,
        principal_id=principal["_id"],
        review_input={"kind": "question", "question": body.question},
    )
    return {**result["answer"], "thread": result["evaluation"]["thread"]}


@app.post("/evaluations/{eval_id}/decide")
async def decide(eval_id: str, body: DecideBody, principal: dict = Principal) -> dict[str, Any]:
    evaluation = await _evaluation_or_404(eval_id)
    if evaluation["status"] == "decided":
        raise ApiError(409, "already_decided", f"Evaluation '{eval_id}' already has a decision")
    result = await agent.run_review(
        eval_id=eval_id,
        principal_id=principal["_id"],
        review_input={"kind": "decision", "verdict": body.verdict, "comments": body.comments},
    )
    gate = result["gate"]
    if gate["result"] == "deny":
        raise ApiError(403, "gate_denied", gate["reason"], extra={"gate": gate})
    return {
        "decision": result["decision"],
        "transaction_status": result["txn"]["status"],
        "memory_created": result["memory_created"] or [],
    }


@app.get("/audit")
async def audit(txn_id: str | None = None, _: dict = Principal) -> dict[str, Any]:
    query = {"txn_id": txn_id} if txn_id else {}
    events = await get_db().audit_log.find(query, NO_ID).sort("seq", 1).to_list()
    return {"events": events}


@app.get("/audit/verify")
async def audit_verify(_: dict = Principal) -> dict[str, Any]:
    return await verify_chain()
