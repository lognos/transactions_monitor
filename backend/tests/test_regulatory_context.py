"""Regulatory sources follow checker findings into recommendation context."""

import unittest

from app.graphs.evaluate import build_evaluate_graph
from app.local_demo import LocalDemo
from app.models import JudgmentCheck, RecommendOutput
from app.policy_checks import DEFAULT_POLICIES
from app.regulatory_context import retrieve_related_policies
from policy_search_fixture import AtlasPolicyFixtureTestCase


class ReportingWireStore(LocalDemo):
    async def get(self, collection, id):
        doc = await super().get(collection, id)
        if collection == 'transactions' and doc is not None:
            doc['amount'] = 12000
            doc['type_specific']['international'] = True
        return doc


class RegulatoryContextTests(AtlasPolicyFixtureTestCase):
    async def test_policy_retrieval_is_skipped_by_default(self):
        store = ReportingWireStore()
        txn = next(t for t in await store.list_transactions() if t['type'] == 'wire')
        graph = build_evaluate_graph(
            store=store, write_with_audit=store.write_with_audit, recommend=None,
        )
        result = await graph.ainvoke(
            {'txn_id': txn['txn_id'], 'principal_id': 'ana'},
            interrupt_after=['retrieve_context'],
        )
        self.policy_search.assert_not_called()
        self.assertEqual(result['related_policies'], [])
        self.assertTrue(result['checks'])

    async def test_failed_and_flagged_checks_retrieve_source_policies(self):
        store = ReportingWireStore()
        txn = next(t for t in await store.list_transactions() if t['type'] == 'wire')
        graph = build_evaluate_graph(
            store=store, write_with_audit=store.write_with_audit, recommend=None,
        )
        result = await graph.ainvoke(
            {'txn_id': txn['txn_id'], 'principal_id': 'ana', 'skip_policies': False},
            interrupt_after=['retrieve_context'],
        )
        sources = {p['policy_id']: p for p in result['related_policies']}
        self.assertIn('FINTRAC-TRAVEL', sources)
        self.assertIn('FINTRAC-EFTR', sources)
        self.assertNotIn('CAN-SANCTIONS-SEMA', sources)
        travel = sources['FINTRAC-TRAVEL']
        self.assertIn('beneficiary', travel['text'].lower())
        self.assertTrue(travel['source_url'].startswith('https://'))
        self.assertEqual(travel['matched_checks'][0]['criterion_id'], 'W-01')
        self.assertEqual(travel['matched_checks'][0]['result'], 'no_pass')
        self.assertEqual(sources['FINTRAC-EFTR']['matched_checks'][0]['result'], 'flag')
        self.assertIn('precedents', result)
        self.assertIn('adjustments', result)
        self.assertEqual(store.audit_log, [])

    async def test_recommendation_receives_findings_and_retrieved_policies(self):
        store = ReportingWireStore()
        txn = next(t for t in await store.list_transactions() if t['type'] == 'wire')
        received = {}

        async def recommend(*, txn, customer, policy, checks, related_policies, precedents, adjustments):
            received.update(checks=checks, related_policies=related_policies,
                            precedents=precedents, adjustments=adjustments)
            return RecommendOutput(
                judgment_checks=[JudgmentCheck(criterion_id=c['id'], result='pass', evidence='Test judgment')
                                 for c in policy['criteria'] if c['kind'] == 'judgment'],
                rationale='Test recommendation received findings and source policies.',
            )

        graph = build_evaluate_graph(
            store=store, write_with_audit=store.write_with_audit, recommend=recommend,
        )
        result = await graph.ainvoke({'txn_id': txn['txn_id'], 'principal_id': 'ana', 'skip_policies': False})
        self.assertEqual(received['checks'], result['checks'])
        self.assertEqual(received['related_policies'], result['related_policies'])
        self.assertIn('FINTRAC-TRAVEL', {p['policy_id'] for p in received['related_policies']})
        self.assertEqual(result['evaluation']['recommendation'], 'no_pass')
        stored = await store.get('evaluations', result['evaluation']['eval_id'])
        self.assertEqual(stored, result['evaluation'])

    async def test_passed_checks_do_not_retrieve_regulatory_documents(self):
        result = await retrieve_related_policies(
            txn={'type': 'wire', 'amount': 12000}, customer={'segment': 'retail'},
            policy=DEFAULT_POLICIES['wire'],
            checks=[{'criterion_id': 'W-01', 'kind': 'hard', 'result': 'pass'}],
        )
        self.assertEqual(result, [])
        self.policy_search.assert_not_called()

    async def test_shared_source_is_deduplicated_and_keeps_both_findings(self):
        result = await retrieve_related_policies(
            txn={'type': 'cheque', 'amount': 12000}, customer={'segment': 'retail'},
            policy=DEFAULT_POLICIES['cheque'],
            checks=[{'criterion_id': cid, 'kind': 'hard', 'result': 'no_pass'} for cid in ['C-03', 'A-01']],
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['policy_id'], 'PAYCAN-RULE-A4')
        self.assertEqual({c['criterion_id'] for c in result[0]['matched_checks']}, {'C-03', 'A-01'})
        result[0]['text'] = 'Caller mutation'
        again = await retrieve_related_policies(
            txn={'type': 'cheque', 'amount': 12000}, customer={'segment': 'retail'},
            policy=DEFAULT_POLICIES['cheque'],
            checks=[{'criterion_id': 'A-01', 'kind': 'hard', 'result': 'no_pass'}],
        )
        self.assertNotEqual(again[0]['text'], 'Caller mutation')

    async def test_empty_atlas_results_do_not_create_local_source_documents(self):
        result = await retrieve_related_policies(
            txn={'type': 'wire', 'amount': 12000}, customer={'segment': 'retail'},
            policy=DEFAULT_POLICIES['wire'],
            checks=[{'criterion_id': 'C-02', 'kind': 'hard', 'result': 'no_pass'}],
        )
        self.assertEqual(result, [])
        self.policy_search.assert_awaited_once()


if __name__ == '__main__':
    unittest.main()
