"""Explicit Atlas search fixtures for offline graph tests; never production data."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch


async def search_policy_fixture(*, query, txn_type, kind, k=4):
    assert kind == 'policy'
    if 'W-01' in query:
        policy_id, text = 'FINTRAC-TRAVEL', 'Test fixture: beneficiary address travel requirements.'
    elif 'W-02' in query:
        policy_id, text = 'FINTRAC-EFTR', 'Test fixture: reporting threshold for international transfers.'
    elif 'C-03' in query or 'A-01' in query:
        policy_id, text = 'PAYCAN-RULE-A4', 'Test fixture: returned and duplicate items.'
    else:
        return []
    return [{'memory_id': f'MEM-TEST-{policy_id}', 'kind': 'policy', 'text': text, 'score': 0.95,
             'scope': {'policy_id': policy_id, 'source_url': f'https://example.test/{policy_id}',
                       'statutory_authority': 'Test regulatory reference'}}]


class AtlasPolicyFixtureTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        patcher = patch('app.regulatory_context.search_memory', side_effect=search_policy_fixture)
        self.policy_search = patcher.start()
        self.addCleanup(patcher.stop)
        # Offline graph tests must not persist fixture evaluations to live Atlas.
        settings_patcher = patch('app.local_demo.settings', SimpleNamespace(mongodb_configured=False))
        settings_patcher.start()
        self.addCleanup(settings_patcher.stop)
