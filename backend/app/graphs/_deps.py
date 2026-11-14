"""
backend/app/graphs/_deps.py
DB-lane dependency bridge & shared utilities for the LangGraph subgraphs.

Why this file exists:
    Per `AGENTS.md`, `backend/app/audit.py` and `backend/app/gate.py` are owned
    by the DB lane. This module imports `write_with_audit`, `verify_chain`, and
    `check_gate` when those modules are present, and falls back to contract-compliant
    in-process implementations (`docs/contracts.md` §5.1, §5.2) when running
    standalone before DB-lane modules are merged.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.db import get_async_db

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared ID & Timestamp Helpers (docs/contracts.md §1)
# ---------------------------------------------------------------------------


def utc_now_iso() -> str:
    """Return current UTC timestamp as ISO 8601 string with Z suffix."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def new_id(prefix: str) -> str:
    """Generate a readable contract ID like EVAL-3fa91c20, DEC-9c0d1e2f, MEM-5e6f7a8b."""
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def agent_actor(on_behalf_of: Optional[str]) -> Dict[str, Any]:
    """Build the `actor` subdocument for agent-initiated actions (`AGENTS.md` #7)."""
    return {
        "id": "agent-01",
        "type": "agent",
        "role": "agent",
        "on_behalf_of": on_behalf_of,
    }


def human_actor(principal: Dict[str, Any]) -> Dict[str, Any]:
    """Build the `actor` subdocument for human-initiated actions."""
    return {
        "id": principal.get("_id"),
        "type": principal.get("type", "human"),
        "role": principal.get("role", "analyst"),
        "on_behalf_of": None,
    }


# ---------------------------------------------------------------------------
# Write Operation Descriptor
# ---------------------------------------------------------------------------

try:
    from app.audit import Write as AuditWrite  # type: ignore
except ImportError:
    AuditWrite = None


@dataclass
class FallbackWrite:
    """Fallback write descriptor used when `app.audit.Write` is not yet available."""

    collection: str
    op: str  # "insert_one" | "update_one"
    document: Optional[Dict[str, Any]] = None
    filter: Optional[Dict[str, Any]] = None
    update: Optional[Dict[str, Any]] = None


def make_insert(collection: str, document: Dict[str, Any]) -> Any:
    """Create an insert write operation compatible with `app.audit` or fallback."""
    if AuditWrite is not None:
        return AuditWrite(collection=collection, op="insert_one", document=document)
    return FallbackWrite(collection=collection, op="insert_one", document=document)


def make_update(collection: str, filt: Dict[str, Any], update: Dict[str, Any]) -> Any:
    """Create an update write operation compatible with `app.audit` or fallback."""
    if AuditWrite is not None:
        return AuditWrite(collection=collection, op="update_one", filter=filt, update=update)
    return FallbackWrite(collection=collection, op="update_one", filter=filt, update=update)


# ---------------------------------------------------------------------------
# Audit & Gate Bridges (docs/contracts.md §5.1, §5.2)
# ---------------------------------------------------------------------------

try:
    from app.audit import write_with_audit, verify_chain  # type: ignore

    USING_STUB_AUDIT = False
except ImportError:
    USING_STUB_AUDIT = True

    def _canonical_json(obj: Dict[str, Any]) -> str:
        return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)

    async def write_with_audit(
        *,
        actor: Dict[str, Any],
        event: str,
        txn_id: str,
        ref: Dict[str, Any],
        detail: Dict[str, Any],
        writes: List[Any],
    ) -> Dict[str, Any]:
        """
        Temporary fallback implementation of `write_with_audit` (`contracts.md` §5.1).
        Replaced automatically when DB lane's `backend/app/audit.py` is present.
        """
        logger.warning("Using fallback write_with_audit (backend/app/audit.py not found).")
        db = get_async_db()

        for w in writes:
            coll = db[w.collection]
            if w.op == "insert_one" and w.document is not None:
                await coll.insert_one(dict(w.document))
            elif w.op == "update_one" and w.filter is not None and w.update is not None:
                await coll.update_one(w.filter, w.update)

        head = await db["chain_head"].find_one({"_id": "head"})
        prev_seq = head["seq"] if head else 0
        prev_hash = head["hash"] if head else "0" * 64
        seq = prev_seq + 1

        event_body = {
            "seq": seq,
            "ts": utc_now_iso(),
            "actor": actor,
            "event": event,
            "txn_id": txn_id,
            "ref": ref,
            "detail": detail,
            "prev_hash": prev_hash,
        }
        digest = hashlib.sha256((prev_hash + _canonical_json(event_body)).encode("utf-8")).hexdigest()
        audit_doc = {**event_body, "hash": digest}

        await db["audit_log"].insert_one(dict(audit_doc))
        await db["chain_head"].update_one(
            {"_id": "head"},
            {"$set": {"seq": seq, "hash": digest}},
            upsert=True,
        )
        return audit_doc

    async def verify_chain() -> Dict[str, Any]:
        """Fallback hash-chain verifier (`contracts.md` §5.1)."""
        logger.warning("Using fallback verify_chain (backend/app/audit.py not found).")
        db = get_async_db()
        cursor = db["audit_log"].find({}).sort("seq", 1)
        events = await cursor.to_list(length=None)
        expected_prev = "0" * 64
        checked = 0
        for ev in events:
            checked += 1
            if ev.get("prev_hash") != expected_prev:
                return {
                    "ok": False,
                    "checked": checked,
                    "broken_at_seq": ev.get("seq"),
                    "reason": "prev_hash mismatch",
                }
            body = {k: v for k, v in ev.items() if k not in ("_id", "hash")}
            expected_hash = hashlib.sha256(
                (expected_prev + _canonical_json(body)).encode("utf-8")
            ).hexdigest()
            if ev.get("hash") != expected_hash:
                return {
                    "ok": False,
                    "checked": checked,
                    "broken_at_seq": ev.get("seq"),
                    "reason": "hash mismatch",
                }
            expected_prev = expected_hash
        return {"ok": True, "checked": checked, "broken_at_seq": None, "reason": None}


try:
    from app.gate import check_gate  # type: ignore

    USING_STUB_GATE = False
except ImportError:
    USING_STUB_GATE = True

    async def check_gate(
        *,
        principal: Dict[str, Any],
        txn: Dict[str, Any],
        evaluation: Dict[str, Any],
        verdict: str,
    ) -> Dict[str, Any]:
        """
        Temporary fallback implementation of `check_gate` (`contracts.md` §5.2).
        Replaced automatically when DB lane's `backend/app/gate.py` is present.
        """
        logger.warning("Using fallback check_gate (backend/app/gate.py not found).")
        db = get_async_db()
        policy = await db["policies"].find_one({"txn_type": txn.get("type"), "active": True})
        rules = (policy or {}).get("decision_rules", [])
        role = principal.get("role")

        rule = next((r for r in rules if r.get("role") == role), None)
        if rule is None:
            return {
                "result": "deny",
                "rule_id": None,
                "reason": f"role '{role}' has no decision authority",
            }

        max_amount = rule.get("max_amount")
        amount = txn.get("amount", 0)
        if max_amount is not None and amount > max_amount:
            return {
                "result": "deny",
                "rule_id": rule.get("rule_id"),
                "reason": f"amount {amount} exceeds {role} limit {max_amount}",
            }

        has_hard_fail = any(
            c.get("kind") == "hard" and c.get("result") == "no_pass"
            for c in evaluation.get("checks", [])
        )
        if verdict.startswith("validated") and has_hard_fail and not rule.get("can_override_hard_fail", False):
            return {
                "result": "deny",
                "rule_id": rule.get("rule_id"),
                "reason": "cannot override failed hard check",
            }

        return {
            "result": "allow",
            "rule_id": rule.get("rule_id"),
            "reason": f"{role} within limit",
        }
