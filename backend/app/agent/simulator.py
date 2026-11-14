"""CSV simulation engine for bringing consolidated transactions into the queue.

Reads `data/AuditFlow_All_Transactions_Consolidated.csv`, normalizes rows via
`app.agent.ingest.normalize_csv_row`, requires matching active policies in MongoDB,
and processes each transaction through the policy/agent evaluation pipeline.
"""

from __future__ import annotations

import csv
import random
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Literal

from app.agent.checks import CHECKS
from app.agent.graphs._deps import (
    agent_actor,
    make_insert,
    new_id,
    utc_now_iso,
    write_with_audit,
)
from app.agent.ingest import normalize_csv_row
from app.db import get_db

DEFAULT_CSV_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "AuditFlow_All_Transactions_Consolidated.csv"
)


@lru_cache(maxsize=2)
def _load_csv_rows(csv_path: str = str(DEFAULT_CSV_PATH)) -> List[Dict[str, Any]]:
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"Simulation CSV not found: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _is_signal_row(row: Dict[str, Any]) -> bool:
    method = str(row.get("payment_method", "")).strip().upper()
    try:
        amount = float(row.get("amount_cad") or 0)
    except (TypeError, ValueError):
        amount = 0.0
    account_issue = (
        str(row.get("sender_account_status", "ACTIVE")).strip().upper() != "ACTIVE"
        or str(row.get("receiver_account_status", "ACTIVE")).strip().upper() != "ACTIVE"
        or str(row.get("compliance_cleared", "true")).strip().lower() == "false"
    )
    limit_signal = (
        (method == "INTERAC_E_TRANSFER" and amount > 3000)
        or (method == "WIRE" and amount >= 10000)
    )
    return account_issue or limit_signal


async def _ensure_policy_in_db(txn_type: str) -> Dict[str, Any]:
    db = get_db()
    existing = await db.policies.find_one({"txn_type": txn_type, "active": True}, {"_id": 0})
    if existing:
        return existing
    raise ValueError(f"No active policy for transaction type '{txn_type}'")


async def _evaluate_policy_only(
    *, txn: Dict[str, Any], customer: Dict[str, Any], policy: Dict[str, Any], principal_id: str,
    insert_customer: bool,
) -> Dict[str, Any]:
    """Run deterministic policy checks and persist an evaluation via `write_with_audit`."""
    db = get_db()
    checks: List[Dict[str, Any]] = []
    for criterion in policy.get("criteria", []):
        if criterion.get("kind") != "hard":
            continue
        check_name = criterion.get("check")
        check_fn = CHECKS.get(check_name) if check_name else None
        if check_fn is None:
            outcome = {
                "result": "no_pass",
                "evidence": f"Missing deterministic check handler: {check_name}",
                "explanation": f"No deterministic handler registered for '{check_name}'.",
                "facts": [],
            }
        else:
            outcome = await check_fn(txn, customer, criterion.get("params") or {}, db)
        checks.append(
            {
                "criterion_id": criterion["id"],
                "description": criterion["description"],
                "kind": "hard",
                "source": "rule",
                "result": outcome["result"],
                "effective_result": outcome["result"],
                "override": None,
                "evidence": outcome["evidence"],
                "explanation": outcome.get("explanation") or outcome["evidence"],
                "facts": outcome.get("facts") or [],
                "regulation_ref": criterion.get("regulation_ref", ""),
                "precedents_used": [],
                "adjustments_used": [],
            }
        )

    failed_ids = [c["criterion_id"] for c in checks if c["result"] == "no_pass"]
    recommendation = "no_pass" if failed_ids else "pass"
    rationale = (
        f"Deterministic policy screening failed on {', '.join(failed_ids)}."
        if failed_ids
        else "All deterministic policy checks passed (policy-only simulation mode)."
    )

    eval_id = new_id("EVAL")
    actor = agent_actor(principal_id)
    evaluation_doc = {
        "eval_id": eval_id,
        "txn_id": txn["txn_id"],
        "actor": actor,
        "policy_version": policy.get("version", 1),
        "checks": checks,
        "recommendation": recommendation,
        "effective_recommendation": recommendation,
        "rationale": rationale,
        "precedents_used": [],
        "adjustments_used": [],
        "thread": [],
        "status": "awaiting_review",
        "created_at": utc_now_iso(),
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
            "precedents_used": [],
            "adjustments_used": [],
        },
        writes=[
            *([make_insert("customers", customer)] if insert_customer else []),
            make_insert("transactions", {**txn, "status": "awaiting_review"}),
            make_insert("evaluations", evaluation_doc),
        ],
    )
    return evaluation_doc


async def simulate_transactions(
    *,
    principal_id: str,
    count: int = 3,
    mode: Literal["random", "signals", "sequential"] = "random",
    policy_only: bool = False,
) -> Dict[str, Any]:
    """Pull `count` rows from the consolidated CSV, ingest, and evaluate them."""
    from app.agent.graphs.evaluate import ModelUnavailableError, evaluate_graph

    rows = _load_csv_rows()
    pool = [r for r in rows if _is_signal_row(r)] if mode == "signals" else list(rows)
    if not pool:
        pool = list(rows)

    db = get_db()
    if mode == "sequential":
        selected = pool[:count]
    else:
        selected = random.sample(pool, k=min(count, len(pool)))

    simulated: List[Dict[str, Any]] = []
    failed: List[Dict[str, Any]] = []

    for row in selected:
        customer_doc, txn_doc = normalize_csv_row(row)
        txn_doc["status"] = "pending"
        txn_doc["queued_at"] = utc_now_iso()  # top of the reviewer queue; created_at stays the source date
        txn_doc["source_txn_id"] = txn_doc["txn_id"]
        txn_doc["txn_id"] = new_id("SIM")
        created = False

        try:
            policy = await _ensure_policy_in_db(txn_doc["type"])
            existing_customer = await db.customers.find_one(
                {"customer_id": customer_doc["customer_id"]}, {"_id": 0},
            )
            insert_customer = existing_customer is None
            customer = existing_customer if existing_customer is not None else customer_doc

            if policy_only:
                evaluation = await _evaluate_policy_only(
                    txn=txn_doc, customer=customer, policy=policy, principal_id=principal_id,
                    insert_customer=insert_customer,
                )
            else:
                state = await evaluate_graph.ainvoke(
                    {"txn_id": txn_doc["txn_id"], "principal_id": principal_id, "refresh": False,
                     "simulation": True, "insert_customer": insert_customer,
                     "txn": txn_doc, "customer": customer, "policy": policy}
                )
                evaluation = state["evaluation"]
            created = True

            failed_checks = [
                c["criterion_id"]
                for c in evaluation.get("checks", [])
                if c.get("result") == "no_pass"
            ]
            simulated.append(
                {
                    "txn_id": txn_doc["txn_id"],
                    "type": txn_doc["type"],
                    "amount": txn_doc["amount"],
                    "eval_id": evaluation["eval_id"],
                    "recommendation": evaluation["recommendation"],
                    "failed_checks": failed_checks,
                }
            )
        except ModelUnavailableError:
            failed.append({
                "txn_id": txn_doc["txn_id"], "code": "model_unavailable",
                "created": False,
                "error": "The model is unavailable or over its quota. No simulated transaction was created.",
            })
            # Do not consume more quota or ingest more transactions after a model outage.
            break
        except Exception as exc:
            failed.append({"txn_id": txn_doc["txn_id"], "created": created,
                           "error": f"Simulation failed ({type(exc).__name__})."})

    return {"simulated": simulated, "failed": failed}
