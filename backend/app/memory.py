"""
backend/app/memory.py
Implements the contract interface for memory and precedent retrieval:
- search_memory: Vector search over Atlas memory_text_idx
- active_adjustments: Retrieves active reviewer adjustments (plain find, no vector search)
- precedent_text_template: Generates templated precedent text
"""

from typing import List, Dict, Any, Optional
from backend.app.db import get_async_db, get_sync_db

INDEX_NAME = "memory_text_idx"

def precedent_text_template(*, txn_type: str, amount: float, customer_segment: str, verdict: str, reviewer_id: str, comments: Optional[str] = None) -> str:
    """Generates templated summary for a precedent (contracts §3.7). No LLM used."""
    base = f"{txn_type.capitalize()} transfer of CAD {amount:,.0f} for {customer_segment} customer {verdict} by {reviewer_id}."
    if comments:
        base += f" Reviewer note: {comments}"
    return base

async def active_adjustments(*, txn_type: str) -> List[Dict[str, Any]]:
    """
    Plain find on active adjustments for a given transaction type (contracts §5.4).
    Adjustments are only created for judgment criteria and alter subsequent evaluations.
    """
    db = get_async_db()
    cursor = db.memory.find(
        {"txn_type": txn_type, "kind": "adjustment", "active": True},
        {"_id": 0}
    )
    return await cursor.to_list(length=100)

async def search_memory(*, query: str, txn_type: str, kind: str, k: int = 4, min_score: float = 0.68) -> List[Dict[str, Any]]:
    """
    Performs Atlas Vector Search over memory documents using the memory_text_idx index (contracts §5.4).
    Filters on txn_type, kind (precedent/adjustment/policy), and active=True.
    Applies min_score threshold to filter out irrelevant / out-of-domain noise.
    Falls back gracefully if the index is still indexing on Atlas.
    """
    db = get_async_db()
    
    # 1. Primary Vector Search Pipeline (Atlas Automated Embedding / Vector Search)
    pipeline = [
        {
            "$vectorSearch": {
                "index": INDEX_NAME,
                "path": "text",
                "query": query,
                "numCandidates": k * 10,
                "limit": k * 2,
                "filter": {
                    "txn_type": txn_type,
                    "kind": kind,
                    "active": True
                }
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
                "score": {"$meta": "vectorSearchScore"}
            }
        }
    ]

    try:
        cursor = await db.memory.aggregate(pipeline)
        results = await cursor.to_list(length=k * 2)
        filtered = [r for r in results if r.get("score", 0) >= min_score]
        if filtered:
            return filtered[:k]
        elif results and not filtered:
            # All results fell below relevance threshold
            return []
    except Exception as e:
        # Atlas search index may be PENDING or query syntax difference on specific tier
        pass

    # 2. Resilient Fallback: Text & Keyword Score Ranking
    query_terms = [w.lower() for w in query.split() if len(w) > 3]
    filter_doc = {"txn_type": txn_type, "kind": kind, "active": True}
    cursor = db.memory.find(filter_doc, {"_id": 0})
    docs = await cursor.to_list(length=50)

    scored_docs = []
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

def search_memory_sync(*, query: str, txn_type: str, kind: str, k: int = 4, min_score: float = 0.68) -> List[Dict[str, Any]]:
    """Synchronous version for test scripts and verification tooling."""
    db = get_sync_db()
    pipeline = [
        {
            "$vectorSearch": {
                "index": INDEX_NAME,
                "path": "text",
                "query": query,
                "numCandidates": k * 10,
                "limit": k * 2,
                "filter": {
                    "txn_type": txn_type,
                    "kind": kind,
                    "active": True
                }
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
                "score": {"$meta": "vectorSearchScore"}
            }
        }
    ]

    try:
        results = list(db.memory.aggregate(pipeline))
        filtered = [r for r in results if r.get("score", 0) >= min_score]
        if filtered:
            return filtered[:k]
        elif results and not filtered:
            return []
    except Exception:
        pass

    query_terms = [w.lower() for w in query.split() if len(w) > 3]
    filter_doc = {"txn_type": txn_type, "kind": kind, "active": True}
    docs = list(db.memory.find(filter_doc, {"_id": 0}))

    scored_docs = []
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
