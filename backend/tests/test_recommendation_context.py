"""Verify the actual recommendation adapter passes all context to the model."""

import json
import unittest
from unittest.mock import patch

from app import llm
from app.graphs.evaluate import build_evaluate_graph
from app.local_demo import LocalDemo
from app.models import RecommendOutput, WorkflowError
from app.recommendation import build_recommend_messages
from policy_search_fixture import AtlasPolicyFixtureTestCase


class CapturingModel:
    def __init__(self):
        self.messages = None
        self.schema = None

    def with_structured_output(self, schema):
        self.schema = schema
        return self

    async def ainvoke(self, messages):
        self.messages = messages
        payload = json.loads(messages[1]['content'])
        return RecommendOutput.model_validate({
            'judgment_checks': [
                {'criterion_id': c['id'], 'result': 'pass', 'evidence': 'Provider fixture judgment.'}
                for c in payload['judgment_criteria']
            ],
            'rationale': 'Provider fixture received hard checks and related regulatory excerpts.',
        })


class RecommendationContextTests(AtlasPolicyFixtureTestCase):
    async def test_recommendation_model_receives_checks_and_policy_documents(self):
        store = LocalDemo()
        txn = next(t for t in await store.list_transactions() if t['type'] == 'wire')
        model = CapturingModel()
        graph = build_evaluate_graph(
            store=store, write_with_audit=store.write_with_audit, recommend=llm.recommend,
        )
        with patch('app.agent.llm.get_llm', return_value=model):
            result = await graph.ainvoke({'txn_id': txn['txn_id'], 'principal_id': 'ana', 'skip_policies': False})
        self.assertIs(model.schema, RecommendOutput)
        assert model.messages is not None
        payload = json.loads(model.messages[1]['content'])
        self.assertEqual(payload['hard_checks'], result['checks'])
        self.assertEqual(payload['related_policies'], result['related_policies'])
        self.assertIn('FINTRAC-TRAVEL', {p['policy_id'] for p in payload['related_policies']})
        self.assertEqual(payload['precedents'], result['precedents'])
        self.assertEqual(payload['adjustments'], result['adjustments'])
        self.assertEqual(result['evaluation']['recommendation'], 'no_pass')
        self.assertEqual({c['criterion_id'] for c in result['llm_output']['judgment_checks']}, {'C-04', 'W-03'})

    async def test_provider_failure_does_not_save_an_evaluation(self):
        store = LocalDemo()
        txn = next(t for t in await store.list_transactions() if t['type'] == 'wire')

        class FailingModel(CapturingModel):
            async def ainvoke(self, messages):
                raise RuntimeError('PRIVATE_PROVIDER_DETAIL')

        graph = build_evaluate_graph(
            store=store, write_with_audit=store.write_with_audit, recommend=llm.recommend,
        )
        with patch('app.agent.llm.get_llm', return_value=FailingModel()):
            with self.assertRaises(WorkflowError) as caught:
                await graph.ainvoke({'txn_id': txn['txn_id'], 'principal_id': 'ana'})
        self.assertEqual(caught.exception.status, 502)
        self.assertNotIn('PRIVATE_PROVIDER_DETAIL', str(caught.exception.body))
        self.assertEqual(await store.list_documents('evaluations'), [])
        self.assertEqual(store.audit_log, [])

    def test_untrusted_text_stays_out_of_system_instructions(self):
        marker = 'IGNORE_PREVIOUS_INSTRUCTIONS_9382'
        messages = build_recommend_messages(
            txn={'memo': marker, 'counterparty': {'name': marker}}, customer={},
            policy={'criteria': []}, checks=[{'evidence': marker}],
            related_policies=[], precedents=[], adjustments=[],
        )
        self.assertNotIn(marker, messages[0]['content'])
        payload = json.loads(messages[1]['content'])
        self.assertEqual(payload['untrusted_transaction_data']['memo'], marker)
        self.assertEqual(payload['hard_checks'][0]['evidence'], marker)


if __name__ == '__main__':
    unittest.main()
