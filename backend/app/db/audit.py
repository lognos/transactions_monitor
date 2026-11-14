"""Hash-chained audit log. Contract: docs/contracts.md §3.8, §3.9, §5.1.

Every application write after seeding goes through write_with_audit.
"""

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Literal

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


async def write_with_audit(
    *,
    actor: dict[str, Any],
    event: str,
    txn_id: str,
    ref: dict[str, str],
    detail: dict[str, Any],
    writes: list[Write],
) -> dict[str, Any]:
    """Apply `writes` and append one audit event in a single transaction.

    Steps (docs/plan-db.md): bump chain_head.seq, build the event with
    prev_hash = chain_head.hash, apply writes, insert the event, update chain_head.
    """
    raise NotImplementedError("db.audit.write_with_audit")


async def verify_chain() -> dict[str, Any]:
    """Return {"ok", "checked", "broken_at_seq", "reason"}."""
    raise NotImplementedError("db.audit.verify_chain")
