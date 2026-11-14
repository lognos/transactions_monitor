"""Vector-policy retrieval contract, using an explicit test search provider."""

import unittest
from unittest.mock import AsyncMock

from app.models import WorkflowError
from app.policy_checks import DEFAULT_POLICIES
from app.regulatory_context import retrieve_related_policies


class AtlasContextAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_each_finding_searches_atlas_and_preserves_metadata(self):
        hit = {'memory_id': 'MEM-ATLAS-TRAVEL', 'text': 'Travel Rule beneficiary requirements.',
               'scope': {'policy_id': 'FINTRAC-TRAVEL', 'source_url': 'https://example.test/travel',
                         'statutory_authority': 'Travel Rule'}, 'score': 0.92}
        search = AsyncMock(return_value=[hit])
        result = await retrieve_related_policies(
            txn={'type': 'wire', 'amount': 12000, 'memo': 'UNTRUSTED_MARKER'},
            customer={'segment': 'retail'}, policy=DEFAULT_POLICIES['wire'],
            checks=[{'criterion_id': 'W-01', 'kind': 'hard', 'result': 'no_pass', 'evidence': 'UNTRUSTED_MARKER'},
                    {'criterion_id': 'W-02', 'kind': 'hard', 'result': 'flag'}], search=search,
        )
        self.assertEqual(search.await_count, 2)
        for call in search.await_args_list:
            self.assertEqual(call.kwargs['kind'], 'policy')
            self.assertNotIn('UNTRUSTED_MARKER', call.kwargs['query'])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['memory_id'], 'MEM-ATLAS-TRAVEL')
        self.assertEqual(result[0]['policy_id'], 'FINTRAC-TRAVEL')
        self.assertEqual(result[0]['score'], 0.92)
        self.assertEqual({c['criterion_id'] for c in result[0]['matched_checks']}, {'W-01', 'W-02'})

    async def test_vector_failure_is_visible_and_sanitized(self):
        search = AsyncMock(side_effect=RuntimeError('PRIVATE_CONNECTION_DETAILS'))
        with self.assertRaises(WorkflowError) as caught:
            await retrieve_related_policies(
                txn={'type': 'wire', 'amount': 12000}, customer={'segment': 'retail'},
                policy=DEFAULT_POLICIES['wire'],
                checks=[{'criterion_id': 'W-01', 'kind': 'hard', 'result': 'no_pass'}], search=search,
            )
        self.assertEqual(caught.exception.status, 502)
        self.assertEqual(caught.exception.body['error']['code'], 'policy_retrieval_failed')
        self.assertNotIn('PRIVATE_CONNECTION_DETAILS', str(caught.exception.body))


if __name__ == '__main__':
    unittest.main()
