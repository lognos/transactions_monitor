"""
backend/app/memory.py
Implements the contract interface for memory and precedent retrieval (contracts §5.4):
- search_memory: Vector search over Atlas memory_text_idx with relevance floor & optional criterion_id filter
- active_adjustments: Retrieves active reviewer adjustments (plain find, no vector search)
- build_structured_query: Synthesizes injection-free queries from structured check metadata
- precedent_text_template: Generates templated precedent text
"""

from typing import List, Dict, Any, Optional
from backend.app.db import get_async_db, get_sync_db

INDEX_NAME = "memory_text_idx"

_CRITERION_LABELS: Dict[str, str] = {
    "C-01": "Canadian sanctions screening",
    "C-02": "account status check",
    "C-03": "duplicate item clearing",
    "C-04": "customer profile amount consistency",
    "C-05": "24-hour structuring aggregation",
    "W-01": "FINTRAC Travel Rule originator and beneficiary address",
    "W-02": "FINTRAC EFT reporting threshold",
    "W-03": "wire business purpose",
    "Q-01": "cheque date validity",
    "Q-02": "cheque hold period",
}


def precedent_text_template(
    *,
    txn_type: str,
    amount: float,
    customer_segment: str,
    verdict: str,
    reviewer_id: str,
    comments: Optional[str] = None,
) -> str:
    """Generates templated summary for a precedent (contracts §3.7). No LLM used."""
    base = (
        f"{txn_type.capitalize()} transfer of CAD {amount:,.0f} for "
        f"{customer_segment} customer {verdict} by {reviewer_id}."
    )
    if comments:
        base += f" Reviewer note: {comments}"
    return base


def build_structured_query(
    *,
    txn_type: str,
    amount: Optional[float] = None,
    customer_segment: Optional[str] = None,
    failed_criteria: Optional[List[Dict[str, Any]]] = None,
    extra_context: Optional[str] = None,
) -> str:
    """
    Synthesizes a clean, injection-free vector search query from structured
    transaction and deterministic check metadata.
    Intentionally excludes untrusted fields (memo, raw counterparty text) per AGENTS.md invariant #8.
    """
    parts: List[str] = [f"{txn_type} transaction"]
    if customer_segment:
        parts.append(f"for {customer_segment} customer")
    if amount is not None:
        parts.append(f"amount CAD {amount:,.0f}")

    if failed_criteria:
        criteria_phrases = []
        for chk in failed_criteria:
            cid = chk.get("criterion_id", "")
            label = _CRITERION_LABELS.get(cid, chk.get("description", cid))
            evidence = chk.get("evidence", "")
            phrase = f"{cid} {label}".strip()
            if evidence:
                phrase += f": {evidence}"
            criteria_phrases.append(phrase)
        parts.append(" | ".join(criteria_phrases))

    if extra_context:
        parts.append(extra_context.strip())

    return " ".join(parts)


def _build_filter(txn_type: str, kind: str, criterion_id: Optional[str] = None) -> Dict[str, Any]:
    filter_doc: Dict[str, Any] = {
        "txn_type": txn_type,
        "kind": kind,
        "active": True,
    }
    if criterion_id:
        filter_doc["scope.criterion_id"] = criterion_id
    return filter_doc


def _build_vector_pipeline(
    query: str,
    txn_type: str,
    kind: str,
    k: int,
    criterion_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    return [
        {
            "$vectorSearch": {
                "index": INDEX_NAME,
                "path": "text",
                "query": query,
                "numCandidates": k * 10,
                "limit": k * 2,
                "filter": _build_filter(txn_type, kind, criterion_id),
            }
        },
        {
            "$project": {
                "_id": 0,
                "memory_id": 1,
                "kind": 1,
                "txn_type": 1,
                "text": 1,
                "scope": 1,
                "source_decision_id": 1,
                "author_id": 1,
                "score": {"$meta": "vectorSearchScore"},
            }
        },
    ]


def _filter_by_score(results: List[Dict[str, Any]], k: int, min_score: float) -> List[Dict[str, Any]]:
    return [r for r in results if r.get("score", 0) >= min_score][:k]


def _keyword_fallback_score(
    docs: List[Dict[str, Any]],
    query: str,
    k: int,
    min_score: float,
) -> List[Dict[str, Any]]:
    query_terms = [w.lower() for w in query.split() if len(w) > 3]
    scored_docs: List[Dict[str, Any]] = []
    for doc in docs:
        text_lower = doc.get("text", "").lower()
        matches = sum(1 for term in query_terms if term in text_lower)
        score = 0.5 + (matches / (len(query_terms) + 1)) * 0.5 if query_terms else 0.5
        if score >= min_score:
            doc_copy = dict(doc)
            doc_copy["score"] = round(score, 3)
            scored_docs.append(doc_copy)
    scored_docs.sort(key=lambda x: x.get("score", 0), reverse=True)
    return scored_docs[:k]


async def active_adjustments(*, txn_type: str) -> List[Dict[str, Any]]:
    """
    Plain find on active adjustments for a given transaction type (contracts §5.4).
    Adjustments are only created for judgment criteria and alter subsequent evaluations.
    """
    db = get_async_db()
    cursor = db.memory.find(
        {"txn_type": txn_type, "kind": "adjustment", "active": True},
        {"_id": 0},
    )
    return await cursor.to_list(length=100)


async def search_memory(
    *,
    query: str,
    txn_type: str,
    kind: str,
    k: int = 4,
    min_score: float = 0.68,
    criterion_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Performs Atlas Vector Search over memory documents using memory_text_idx (contracts §5.4).
    Filters on txn_type, kind (precedent/adjustment/policy), active=True, and optional scope.criterion_id.
    Applies min_score threshold to suppress out-of-domain noise.
    """
    db = get_async_db()
    pipeline = _build_vector_pipeline(query, txn_type, kind, k, criterion_id)

    try:
        cursor = await db.memory.aggregate(pipeline)
        results = await cursor.to_list(length=k * 2)
        if results is not None:
            return _filter_by_score(results, k, min_score)
    except Exception:
        # Fallback if search index is still rebuilding after definition update
        pass

    filter_doc = _build_filter(txn_type, kind, criterion_id)
    cursor = db.memory.find(filter_doc, {"_id": 0})
    docs = await cursor.to_list(length=50)
    return _keyword_fallback_score(docs, query, k, min_score)


def search_memory_sync(
    *,
    query: str,
    txn_type: str,
    kind: str,
    k: int = 4,
    min_score: float = 0.68,
    criterion_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Synchronous version for test scripts and verification tooling."""
    db = get_sync_db()
    pipeline = _build_vector_pipeline(query, txn_type, kind, k, criterion_id)

    try:
        results = list(db.memory.aggregate(pipeline))
        if results is not None:
            return _filter_by_score(results, k, min_score)
    except Exception:
        pass

    filter_doc = _build_filter(txn_type, kind, criterion_id)
    docs = list(db.memory.find(filter_doc, {"_id": 0}))
    return _keyword_fallback_score(docs, query, k, min_score)
