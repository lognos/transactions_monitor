"""The merged DB audit writer must enforce review compare-and-set updates."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.db import audit


class ReviewAuditTests(unittest.IsolatedAsyncioTestCase):
    async def test_stale_write_never_appends_success_event(self):
        db = MagicMock()
        db.chain_head.find_one_and_update = AsyncMock(return_value={'seq': 1, 'hash': audit.GENESIS_HASH})
        db.audit_log.insert_one = AsyncMock()
        db.chain_head.update_one = AsyncMock()
        collection = SimpleNamespace(update_one=AsyncMock(return_value=SimpleNamespace(matched_count=0)))
        db.__getitem__.return_value = collection
        session = MagicMock()
        async def transaction(callback):
            return await callback(session)
        session.with_transaction = transaction
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value=session)
        context.__aexit__ = AsyncMock(return_value=False)
        client = SimpleNamespace(start_session=lambda: context)
        with patch.object(audit, 'get_db', return_value=db), patch.object(audit, 'get_client', return_value=client):
            with self.assertRaisesRegex(ValueError, 'Missing or changed'):
                await audit.write_with_audit(
                    actor={'id': 'ana', 'type': 'human', 'role': 'analyst'},
                    event='check.overridden', txn_id='TXN-1',
                    ref={'collection': 'evaluations', 'id': 'EVAL-1'}, detail={},
                    writes=[audit.Write('evaluations', 'update', filter={'eval_id': 'EVAL-1'},
                                        update={'$set': {'status': 'decided'}})],
                )
        db.audit_log.insert_one.assert_not_awaited()
        db.chain_head.update_one.assert_not_awaited()
