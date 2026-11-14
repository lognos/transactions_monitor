"""Retrieve active regulatory policy context from Atlas for checker findings."""

from collections.abc import Awaitable, Callable
from copy import deepcopy

from .context_memory import build_structured_query, search_memory
from .models import WorkflowError


async def retrieve_related_policies(
    *, txn: dict, customer: dict, policy: dict, checks: list[dict],
    search: Callable[..., Awaitable[list[dict]]] | None = None,
) -> list[dict]:
    """Vector-search each failed/flagged criterion and merge shared policy hits.

    Query only registered criterion metadata, never memo/counterparty/evidence.
    No local regulatory text or keyword fallback substitutes for Atlas results.
    """
    search = search or search_memory
    criteria = {criterion['id']: criterion for criterion in policy['criteria']}
    related: dict[str, dict] = {}
    for check in checks:
        if check['kind'] != 'hard' or check['result'] not in ('no_pass', 'flag'):
            continue
        criterion = criteria[check['criterion_id']]
        query = build_structured_query(
            txn_type=txn['type'], amount=txn['amount'], customer_segment=customer['segment'],
            failed_criteria=[{'criterion_id': criterion['id'], 'description': criterion['description']}],
            extra_context=f"{criterion['description']}. Regulation: {criterion['regulation_ref']}",
        )
        try:
            hits = await search(query=query, txn_type=txn['type'], kind='policy', k=4)
        except Exception as exc:
            code = getattr(exc, 'code', None)
            reason = f'{type(exc).__name__}' + (f', code {code}' if isinstance(code, int) else '')
            raise WorkflowError(502, 'policy_retrieval_failed', f'Atlas policy vector search failed ({reason}).') from exc
        for hit in hits:
            scope = hit.get('scope') or {}
            policy_id = scope.get('policy_id') or hit['memory_id']
            if policy_id not in related:
                related[policy_id] = {
                    'policy_id': policy_id, 'memory_id': hit['memory_id'],
                    'title': hit.get('title') or policy_id,
                    'regulation_ref': scope.get('statutory_authority'),
                    'text': hit['text'], 'source_url': scope.get('source_url'),
                    'source_kind': 'atlas_vector_search', 'document_available': bool(hit['text']),
                    'score': hit.get('score'), 'matched_checks': [],
                }
            match = {'criterion_id': criterion['id'], 'result': check['result']}
            if match not in related[policy_id]['matched_checks']:
                related[policy_id]['matched_checks'].append(match)
    return deepcopy(list(related.values()))
