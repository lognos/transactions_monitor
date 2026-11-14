"""DB lane: connection, audit chain, policy gate. See docs/plan-db.md."""

from app.db.client import COLLECTIONS, close_client, get_client, get_db, ping

__all__ = ["COLLECTIONS", "close_client", "get_client", "get_db", "ping"]
