"""Memory retrieval. Contract: docs/contracts.md §3.7, §5.4."""

from typing import Any

VECTOR_INDEX = "memory_text_idx"


async def search_memory(*, query: str, txn_type: str, kind: str, k: int = 4) -> list[dict[str, Any]]:
    """Vector search on memory.text, filtered by txn_type, kind and active."""
    raise NotImplementedError("agent.memory.search_memory")


async def active_adjustments(*, txn_type: str) -> list[dict[str, Any]]:
    """Plain find: every active adjustment for the transaction type."""
    raise NotImplementedError("agent.memory.active_adjustments")


def precedent_text(*, txn: dict[str, Any], evaluation: dict[str, Any], decision: dict[str, Any]) -> str:
    """Templated one-paragraph case summary stored as a precedent. No LLM."""
    raise NotImplementedError("agent.memory.precedent_text")
