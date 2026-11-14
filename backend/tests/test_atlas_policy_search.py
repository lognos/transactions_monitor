"""Atlas policy searches must be vector-only and preserve source metadata."""

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from app.context_memory import search_memory


class AtlasPolicySearchTests(unittest.IsolatedAsyncioTestCase):
    async def test_policy_search_filters_policy_and_active_without_losing_shared_rails(self):
        document = {'memory_id': 'MEM-POL-TRAVEL', 'kind': 'policy', 'txn_type': 'wire',
                    'text': 'Travel Rule beneficiary address requirements.', 'score': 0.91,
                    'scope': {'policy_id': 'FINTRAC-TRAVEL', 'source_url': 'https://fintrac-canafe.canada.ca/'}}
        cursor = SimpleNamespace(to_list=AsyncMock(return_value=[document]))
        memory = SimpleNamespace(aggregate=AsyncMock(return_value=cursor))
        with patch('app.db.get_db', return_value=SimpleNamespace(memory=memory)):
            result = await search_memory(query='cheque account status', txn_type='cheque', kind='policy')
        pipeline = memory.aggregate.call_args.args[0]
        vector = pipeline[0]['$vectorSearch']
        self.assertEqual(vector['filter'], {'kind': 'policy', 'active': True})
        self.assertEqual(vector['query'], {'text': 'cheque account status'})
        self.assertEqual(vector['index'], 'memory_text_idx')
        self.assertEqual(result[0]['scope']['policy_id'], 'FINTRAC-TRAVEL')

    async def test_policy_search_does_not_silently_fall_back_to_find(self):
        memory = SimpleNamespace(aggregate=AsyncMock(side_effect=RuntimeError('VECTOR_UNAVAILABLE')),
                                 find=Mock(return_value=SimpleNamespace(to_list=AsyncMock(return_value=[]))))
        with patch('app.db.get_db', return_value=SimpleNamespace(memory=memory)):
            with self.assertRaises(RuntimeError):
                await search_memory(query='Travel Rule', txn_type='wire', kind='policy')
        memory.find.assert_not_called()


if __name__ == '__main__':
    unittest.main()
