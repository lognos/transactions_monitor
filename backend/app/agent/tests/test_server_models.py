"""Public evaluation routes report model outages without leaking provider payloads."""
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from app.agent.graphs.evaluate import ModelUnavailableError
from app.server.deps import current_principal
from app.server.main import app


class ModelErrorTests(unittest.IsolatedAsyncioTestCase):
    async def test_single_evaluate_reports_model_unavailable(self):
        db = MagicMock()
        db.transactions.find_one = AsyncMock(return_value={
            'txn_id': 'SIM-test', 'status': 'pending', 'customer_id': 'CUS-test',
        })
        db.evaluations.find_one = AsyncMock(return_value=None)
        app.dependency_overrides[current_principal] = lambda: {'_id': 'ana'}
        self.addCleanup(app.dependency_overrides.clear)
        with patch('app.server.main.get_db', return_value=db), patch(
            'app.server.main.agent.run_evaluate',
            new=AsyncMock(side_effect=ModelUnavailableError('private provider payload')),
        ):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
                base_url='http://test',
            ) as client:
                response = await client.post('/transactions/SIM-test/evaluate')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['error']['code'], 'model_unavailable')
        self.assertNotIn('private provider payload', response.text)
