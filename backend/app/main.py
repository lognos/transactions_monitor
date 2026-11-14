"""
backend/app/main.py
FastAPI HTTP surface for the Policy & Validation Agent (`docs/contracts.md` §4).

Run from `backend/`:
    uvicorn app.main:app --reload --port 8000

All endpoints require `X-Principal-Id` header matching a document in `principals`.
Errors conform to `{"error": {"code": "...", "message": "..."}}`.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.db import get_async_db
from app.graphs import AlreadyDecidedError, evaluate_graph, review_graph
from app.graphs._deps import verify_chain
from app.models import AskRequest, DecideRequest

app = FastAPI(
    title="Transaction Policy & Validation Agent",
    version="0.1.0",
    description="Auditable LangGraph policy evaluation and human-in-the-loop review API.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _error_response(
    status_code: int,
    code: str,
    message: str,
    extra: Optional[Dict[str, Any]] = None,
) -> JSONResponse:
    payload: Dict[str, Any] = {"error": {"code": code, "message": message}}
    if extra:
        payload.update(extra)
    return JSONResponse(status_code=status_code, content=payload)


@app.exception_handler(HTTPException)
async def _http_exc_handler(_, exc: HTTPException) -> JSONResponse:
    if isinstance(exc.detail, dict) and "error" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return _error_response(exc.status_code, "http_error", str(exc.detail))


async def require_principal(
    x_principal_id: Optional[str] = Header(default=None, alias="X-Principal-Id"),
) -> Dict[str, Any]:
    """Validate `X-Principal-Id` against `principals` collection (`contracts.md` §1, §4)."""
    if not x_principal_id:
        raise HTTPException(
            status_code=401,
            detail={
                "error": {
                    "code": "unknown_principal",
                    "message": "Missing X-Principal-Id header.",
                }
            },
        )
    db = get_async_db()
    principal = await db["principals"].find_one({"_id": x_principal_id})
    if not principal:
        raise HTTPException(
            status_code=401,
            detail={
                "error": {
                    "code": "unknown_principal",
                    "message": f"Unknown principal '{x_principal_id}'.",
                }
            },
        )
    return principal


def _customer_summary(customer: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "customer_id": customer.get("customer_id"),
        "name": customer.get("name"),
        "segment": customer.get("segment"),
        "typical_amount": customer.get("typical_amount"),
    }


# ---------------------------------------------------------------------------
# 1. GET /principals
# ---------------------------------------------------------------------------


@app.get("/principals")
async def list_principals(principal: Dict[str, Any] = Depends(require_principal)):
    """Return available principals for the UI 'acting as' selector."""
    db = get_async_db()
    docs = await db["principals"].find({}).to_list(length=None)
    return {"principals": docs}


# ---------------------------------------------------------------------------
# 2. GET /transactions
# ---------------------------------------------------------------------------


@app.get("/transactions")
async def list_transactions(
    status: Optional[str] = Query(default=None),
    principal: Dict[str, Any] = Depends(require_principal),
):
    """List transactions (optionally filtered by status) with customer_name and latest eval_id."""
    db = get_async_db()
    query: Dict[str, Any] = {"status": status} if status else {}
    txns = await db["transactions"].find(query, {"_id": 0}).sort("created_at", 1).to_list(length=None)

    customers = {
        c["customer_id"]: c.get("name")
        for c in await db["customers"].find({}, {"_id": 0, "customer_id": 1, "name": 1}).to_list(length=None)
    }

    eval_map: Dict[str, str] = {}
    eval_cursor = db["evaluations"].find({}, {"_id": 0, "txn_id": 1, "eval_id": 1}).sort("created_at", -1)
    async for ev in eval_cursor:
        eval_map.setdefault(ev["txn_id"], ev["eval_id"])

    items = [
        {
            "txn_id": t["txn_id"],
            "type": t["type"],
            "amount": t["amount"],
            "currency": t.get("currency", "CAD"),
            "customer_name": customers.get(t["customer_id"], t["customer_id"]),
            "counterparty_name": (t.get("counterparty") or {}).get("name"),
            "memo": t.get("memo"),
            "status": t["status"],
            "eval_id": eval_map.get(t["txn_id"]),
            "created_at": t.get("created_at"),
        }
        for t in txns
    ]
    return {"transactions": items}


# ---------------------------------------------------------------------------
# 3. POST /transactions/{txn_id}/evaluate
# ---------------------------------------------------------------------------


@app.post("/transactions/{txn_id}/evaluate")
async def evaluate_transaction(
    txn_id: str,
    principal: Dict[str, Any] = Depends(require_principal),
):
    """Run the Evaluate graph, or return the existing evaluation if `awaiting_review`."""
    db = get_async_db()
    txn = await db["transactions"].find_one({"txn_id": txn_id}, {"_id": 0})
    if not txn:
        return _error_response(404, "not_found", f"Transaction '{txn_id}' not found.")

    if txn.get("status") == "awaiting_review":
        existing = await db["evaluations"].find_one(
            {"txn_id": txn_id}, {"_id": 0}, sort=[("created_at", -1)]
        )
        if existing:
            customer = await db["customers"].find_one(
                {"customer_id": txn["customer_id"]}, {"_id": 0}
            )
            return {
                **existing,
                "transaction": txn,
                "customer": _customer_summary(customer or {}),
            }

    try:
        result = await evaluate_graph.ainvoke(
            {"txn_id": txn_id, "principal_id": principal["_id"]}
        )
    except KeyError as exc:
        return _error_response(404, "not_found", str(exc))

    return {
        **result["evaluation"],
        "transaction": result["txn"],
        "customer": _customer_summary(result["customer"]),
    }


# ---------------------------------------------------------------------------
# 4. GET /evaluations/{eval_id}
# ---------------------------------------------------------------------------


@app.get("/evaluations/{eval_id}")
async def get_evaluation(
    eval_id: str,
    principal: Dict[str, Any] = Depends(require_principal),
):
    """Fetch a stored evaluation with its transaction, customer summary, and decision."""
    db = get_async_db()
    evaluation = await db["evaluations"].find_one({"eval_id": eval_id}, {"_id": 0})
    if not evaluation:
        return _error_response(404, "not_found", f"Evaluation '{eval_id}' not found.")

    txn = await db["transactions"].find_one({"txn_id": evaluation["txn_id"]}, {"_id": 0})
    customer = (
        await db["customers"].find_one({"customer_id": txn["customer_id"]}, {"_id": 0})
        if txn
        else {}
    )
    decision = await db["decisions"].find_one({"eval_id": eval_id}, {"_id": 0})

    return {
        **evaluation,
        "transaction": txn,
        "customer": _customer_summary(customer or {}),
        "decision": decision,
    }


# ---------------------------------------------------------------------------
# 5. POST /evaluations/{eval_id}/ask
# ---------------------------------------------------------------------------


@app.post("/evaluations/{eval_id}/ask")
async def ask_evaluation(
    eval_id: str,
    body: AskRequest,
    principal: Dict[str, Any] = Depends(require_principal),
):
    """Answer a reviewer's question about an evaluation via the Review graph."""
    try:
        result = await review_graph.ainvoke(
            {
                "eval_id": eval_id,
                "principal_id": principal["_id"],
                "input": {"kind": "question", "question": body.question},
            }
        )
    except KeyError as exc:
        return _error_response(404, "not_found", str(exc))
    except PermissionError as exc:
        return _error_response(401, "unknown_principal", str(exc))

    return result["answer"]


# ---------------------------------------------------------------------------
# 6. POST /evaluations/{eval_id}/decide
# ---------------------------------------------------------------------------


@app.post("/evaluations/{eval_id}/decide")
async def decide_evaluation(
    eval_id: str,
    body: DecideRequest,
    principal: Dict[str, Any] = Depends(require_principal),
):
    """Submit a human reviewer decision via the Review graph (enforces policy gate)."""
    comments = (body.comments or "").strip()
    if body.verdict in ("validated_with_comments", "rejected") and not comments:
        return _error_response(
            422,
            "invalid_request",
            f"Comments are required for verdict '{body.verdict}'.",
        )

    try:
        result = await review_graph.ainvoke(
            {
                "eval_id": eval_id,
                "principal_id": principal["_id"],
                "input": {
                    "kind": "decision",
                    "verdict": body.verdict,
                    "comments": comments,
                },
            }
        )
    except KeyError as exc:
        return _error_response(404, "not_found", str(exc))
    except PermissionError as exc:
        return _error_response(401, "unknown_principal", str(exc))
    except AlreadyDecidedError as exc:
        return _error_response(409, "already_decided", str(exc))

    gate = result.get("gate", {})
    if gate.get("result") == "deny":
        return _error_response(
            403,
            "gate_denied",
            gate.get("reason", "Decision denied by policy gate."),
            extra={"gate": gate},
        )

    return {
        "decision": result["decision"],
        "transaction_status": result["txn"]["status"],
        "memory_created": result.get("memory_created", []),
    }


# ---------------------------------------------------------------------------
# 7. GET /audit & 8. GET /audit/verify
# ---------------------------------------------------------------------------


@app.get("/audit")
async def get_audit_log(
    txn_id: Optional[str] = Query(default=None),
    principal: Dict[str, Any] = Depends(require_principal),
):
    """Return audit_log events in ascending `seq` order, optionally filtered by `txn_id`."""
    db = get_async_db()
    query: Dict[str, Any] = {"txn_id": txn_id} if txn_id else {}
    events = (
        await db["audit_log"].find(query, {"_id": 0}).sort("seq", 1).to_list(length=None)
    )
    return {"events": events}


@app.get("/audit/verify")
async def verify_audit_chain(principal: Dict[str, Any] = Depends(require_principal)):
    """Verify the tamper-evident SHA-256 hash chain in `audit_log`."""
    return await verify_chain()
