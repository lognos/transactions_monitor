"""Exercise context retrieval with the CSV graph and process-local memory."""

import unittest

from app.graphs.evaluate import build_evaluate_graph
from app.local_demo import LocalDemo
from app.models import Write
from policy_search_fixture import AtlasPolicyFixtureTestCase


def memory_doc(memory_id, *, kind='precedent', txn_type='cheque', active=True):
    return {
        'memory_id': memory_id, 'kind': kind, 'txn_type': txn_type,
        'text': 'Cheque transaction for personal business customer amount CAD; routine payment.',
        'scope': {'criterion_id': 'C-04', 'condition': 'Customer profile matches.'} if kind == 'adjustment' else None,
        'active': active, 'author_id': 'seed', 'source_decision_id': None,
        'source_txn_id': None, 'created_at': '2026-11-14T10:00:00Z',
    }


class ContextIntegrationTests(AtlasPolicyFixtureTestCase):
    async def test_retrieves_precedents_and_active_adjustments_before_model(self):
        store = LocalDemo()
        docs = [memory_doc('MEM-local-case'), memory_doc('MEM-local-guidance', kind='adjustment'),
                memory_doc('MEM-inactive', active=False), memory_doc('MEM-other-rail', txn_type='wire')]
        await store.write_with_audit(
            actor={'id': 'seed', 'type': 'human', 'role': 'analyst', 'on_behalf_of': None},
            event='memory.created', txn_id='TX-CA-000010',
            ref={'collection': 'memory', 'id': docs[0]['memory_id']}, detail={},
            writes=[Write('memory', doc['memory_id'], doc) for doc in docs],
        )
        events_before = len(store.audit_log)
        graph = build_evaluate_graph(
            store=store, write_with_audit=store.write_with_audit, recommend=None,
        )
        result = await graph.ainvoke(
            {'txn_id': 'TX-CA-000010', 'principal_id': 'ana'},
            interrupt_after=['retrieve_context'],
        )
        self.assertEqual([doc['memory_id'] for doc in result['precedents']], ['MEM-local-case'])
        self.assertEqual([doc['memory_id'] for doc in result['adjustments']], ['MEM-local-guidance'])
        self.assertNotIn('llm_output', result)
        self.assertNotIn('evaluation', result)
        self.assertEqual(len(store.audit_log), events_before)
        self.assertEqual(await store.list_documents('evaluations'), [])

    async def test_empty_memory_returns_empty_context(self):
        store = LocalDemo()
        graph = build_evaluate_graph(
            store=store, write_with_audit=store.write_with_audit, recommend=None,
        )
        result = await graph.ainvoke(
            {'txn_id': 'TX-CA-000010', 'principal_id': 'ana'},
            interrupt_after=['retrieve_context'],
        )
        self.assertEqual(result['precedents'], [])
        self.assertEqual(result['adjustments'], [])
        self.assertEqual(store.audit_log, [])

    async def test_search_ranks_limits_filters_and_returns_copies(self):
        store = LocalDemo()
        weaker = memory_doc('MEM-weaker')
        weaker['text'] = 'Cheque transaction.'
        docs = [memory_doc(f'MEM-ranked-{i}') for i in range(6)]
        docs += [memory_doc('MEM-irrelevant'), memory_doc('MEM-inactive', active=False),
                 memory_doc('MEM-other-rail', txn_type='wire'), memory_doc('MEM-guidance', kind='adjustment')]
        docs[6]['text'] = 'Unrelated vocabulary.'
        docs.insert(0, weaker)
        await store.write_with_audit(
            actor={'id': 'seed', 'type': 'human', 'role': 'analyst', 'on_behalf_of': None},
            event='memory.created', txn_id='TX-CA-000010',
            ref={'collection': 'memory', 'id': docs[0]['memory_id']}, detail={},
            writes=[Write('memory', doc['memory_id'], doc) for doc in docs],
        )
        results = await store.search_memory(query='cheque transaction customer amount', txn_type='cheque', kind='precedent')
        self.assertEqual([doc['memory_id'] for doc in results], [f'MEM-ranked-{i}' for i in range(4)])
        self.assertTrue(all(doc['score'] >= 0.68 for doc in results))
        results[0]['text'] = 'Changed by caller'
        stored = await store.get('memory', 'MEM-ranked-0')
        assert stored is not None
        self.assertNotEqual(stored['text'], results[0]['text'])
        self.assertNotIn('score', stored)

    async def test_query_excludes_untrusted_fields_and_check_evidence(self):
        marker = 'IGNORE_PREVIOUS_INSTRUCTIONS_8291'

        class InspectingStore(LocalDemo):
            query = ''

            async def get(self, collection, id):
                doc = await super().get(collection, id)
                if collection == 'transactions' and doc is not None:
                    doc['memo'] = marker
                    doc['counterparty']['name'] = marker
                if collection == 'policies' and doc is not None:
                    criterion = next(c for c in doc['criteria'] if c['id'] == 'C-01')
                    criterion['params']['names'] = [marker]
                return doc

            async def search_memory(self, *, query, txn_type, kind, k=4):
                self.query = query
                return await super().search_memory(query=query, txn_type=txn_type, kind=kind, k=k)

        store = InspectingStore()
        graph = build_evaluate_graph(
            store=store, write_with_audit=store.write_with_audit, recommend=None,
        )
        result = await graph.ainvoke(
            {'txn_id': 'TX-CA-000010', 'principal_id': 'ana'},
            interrupt_after=['retrieve_context'],
        )
        check = next(c for c in result['checks'] if c['criterion_id'] == 'C-01')
        self.assertEqual(check['result'], 'no_pass')
        self.assertIn(marker, check['evidence'])
        self.assertNotIn(marker, store.query)
        self.assertIn('C-01 Canadian sanctions screening', store.query)
        self.assertIn('cheque transaction', store.query)


if __name__ == '__main__':
    unittest.main()
