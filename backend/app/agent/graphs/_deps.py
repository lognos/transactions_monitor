"""Shared helpers and DB-lane bridges for the LangGraph subgraphs.

Imports `write_with_audit`, `verify_chain`, `Write` from `app.db.audit`
and `check_gate` from `app.db.gate` (owned by the DB lane).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.config import settings
from app.db.audit import Write, verify_chain, write_with_audit
from app.db.gate import check_gate


def utc_now_iso() -> str:
    """Return current UTC timestamp as ISO 8601 string with Z suffix."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def new_id(prefix: str) -> str:
    """Generate a readable contract ID like EVAL-3fa91c20, DEC-9c0d1e2f, MEM-5e6f7a8b."""
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def agent_actor(on_behalf_of: Optional[str]) -> Dict[str, Any]:
    """Build the `actor` subdocument for agent-initiated actions (`AGENTS.md` #7)."""
    return {
        "id": settings.agent_id,
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


def make_insert(collection: str, document: Dict[str, Any]) -> Write:
    """Create an insert Write operation compatible with `app.db.audit.Write`."""
    return Write(collection=collection, op="insert", document=document)


def make_update(collection: str, filt: Dict[str, Any], update: Dict[str, Any]) -> Write:
    """Create an update Write operation compatible with `app.db.audit.Write`."""
    return Write(collection=collection, op="update", filter=filt, update=update)


__all__ = [
    "agent_actor",
    "check_gate",
    "human_actor",
    "make_insert",
    "make_update",
    "new_id",
    "utc_now_iso",
    "verify_chain",
    "write_with_audit",
]
