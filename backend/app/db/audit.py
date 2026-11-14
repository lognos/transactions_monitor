"""Hash-chained audit log. Contract: docs/contracts.md §3.8, §3.9, §5.1.

Every application write after seeding goes through write_with_audit.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from pymongo import ReturnDocument

from app.db.client import get_client, get_db

GENESIS_HASH = "0" * 64


@dataclass
class Write:
    """One insert or update to apply in the same transaction as the audit event."""

    collection: str
    op: Literal["insert", "update"]
    document: dict[str, Any] | None = None  # insert
    filter: dict[str, Any] | None = None  # update
    update: dict[str, Any] | None = None  # update, e.g. {"$set": {...}}


def canonical_json(obj: dict[str, Any]) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def compute_hash(prev_hash: str, event: dict[str, Any]) -> str:
    """event is the audit document without `hash` and `_id`."""
    return hashlib.sha256((prev_hash + canonical_json(event)).encode()).hexdigest()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


async def write_with_audit(
    *,
    actor: dict[str, Any],
    event: str,
    txn_id: str | None,
    ref: dict[str, str],
    detail: dict[str, Any],
    writes: list[Write],
) -> dict[str, Any]:
    """Apply `writes` and append one audit event in a single transaction.

    Steps (docs/plan-db.md): bump chain_head.seq, build the event with
    prev_hash = chain_head.hash, apply writes, insert the event, update chain_head.
    """
    client = get_client()
    db = get_db()
    ts = _utc_now_iso()

    async def _txn(session: Any) -> dict[str, Any]:
        head = await db.chain_head.find_one_and_update(
            {"_id": "head"},
            {"$inc": {"seq": 1}, "$setOnInsert": {"hash": GENESIS_HASH}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
            session=session,
        )
        new_seq = int(head["seq"])
        prev_hash = str(head["hash"])

        event_body: dict[str, Any] = {
            "seq": new_seq,
            "ts": ts,
            "actor": actor,
            "event": event,
            "txn_id": txn_id,
            "ref": ref,
            "detail": detail,
            "prev_hash": prev_hash,
        }
        event_hash = compute_hash(prev_hash, event_body)
        audit_doc = {**event_body, "hash": event_hash}

        for w in writes:
            col = db[w.collection]
            if w.op == "insert":
                if w.document is None:
                    raise ValueError(f"Insert write on {w.collection} missing document")
                await col.insert_one(dict(w.document), session=session)
            elif w.op == "update":
                if w.filter is None or w.update is None:
                    raise ValueError(f"Update write on {w.collection} missing filter/update")
                result = await col.update_one(w.filter, w.update, session=session)
                if result.matched_count != 1:
                    raise ValueError(f"Missing or changed document for audited update in {w.collection}")
            else:
                raise ValueError(f"Unsupported write op: {w.op}")

        await db.audit_log.insert_one(dict(audit_doc), session=session)
        await db.chain_head.update_one(
            {"_id": "head"},
            {"$set": {"hash": event_hash}},
            session=session,
        )
        return audit_doc

    async with client.start_session() as session:
        return await session.with_transaction(_txn)


async def verify_chain() -> dict[str, Any]:
    """Return {"ok", "checked", "broken_at_seq", "reason"}."""
    db = get_db()
    events = await db.audit_log.find({}, {"_id": 0}).sort("seq", 1).to_list(length=None)

    expected_prev = GENESIS_HASH
    checked = 0

    for expected_seq, doc in enumerate(events, start=1):
        seq = doc.get("seq")
        if seq != expected_seq:
            return {
                "ok": False,
                "checked": checked,
                "broken_at_seq": seq if seq is not None else expected_seq,
                "reason": f"sequence gap: expected {expected_seq}, got {seq}",
            }

        if doc.get("prev_hash") != expected_prev:
            return {
                "ok": False,
                "checked": checked,
                "broken_at_seq": seq,
                "reason": "prev_hash mismatch",
            }

        event_body = {k: v for k, v in doc.items() if k != "hash"}
        expected_hash = compute_hash(expected_prev, event_body)
        if doc.get("hash") != expected_hash:
            return {
                "ok": False,
                "checked": checked,
                "broken_at_seq": seq,
                "reason": "hash mismatch",
            }

        expected_prev = doc["hash"]
        checked += 1

    return {
        "ok": True,
        "checked": checked,
        "broken_at_seq": None,
        "reason": "ok",
    }
