"""Simulation failures must not produce incomplete evaluations or unaudited writes."""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app.agent import simulator
from app.agent.graphs import evaluate


class SimulatorTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.rows = [
            {"transaction_id": "SOURCE-1", "payment_method": "WIRE", "amount_cad": "12000",
             "source_account_id": "CUS-1", "transaction_datetime": "2026-11-14T12:00:00Z"},
            {"transaction_id": "SOURCE-2", "payment_method": "WIRE", "amount_cad": "60000",
             "source_account_id": "CUS-2", "transaction_datetime": "2026-11-14T12:01:00Z"},
        ]
        self.policy = {"txn_type": "wire", "version": 1, "active": True, "criteria": []}
        self.db = MagicMock()
        self.db.policies.find_one = AsyncMock(return_value=self.policy)
        self.db.customers.find_one = AsyncMock(return_value=None)
        self.audit = AsyncMock()
        self.invoke = AsyncMock(return_value={"evaluation": {
            "eval_id": "EVAL-1", "recommendation": "pass", "checks": [],
        }})
        for target, name, value in [
            (simulator, "get_db", lambda: self.db),
            (simulator, "_load_csv_rows", lambda: self.rows),
            (simulator, "write_with_audit", self.audit),
            (evaluate.evaluate_graph, "ainvoke", self.invoke),
        ]:
            patcher = patch.object(target, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def assert_no_direct_writes(self):
        for collection in (self.db.policies, self.db.customers, self.db.transactions):
            collection.insert_one.assert_not_called()
            collection.update_one.assert_not_called()

    async def test_live_simulation_always_uses_sim_id_and_supplies_atomic_creation_state(self):
        existing_customer = {"customer_id": "CUS-1", "typical_amount": 4000, "segment": "business"}
        self.db.customers.find_one.return_value = existing_customer
        result = await simulator.simulate_transactions(
            principal_id="ana", count=1, mode="sequential", policy_only=False,
        )
        state = self.invoke.await_args.args[0]
        self.assertTrue(result["simulated"][0]["txn_id"].startswith("SIM-"))
        self.assertEqual(state["txn"]["source_txn_id"], "SOURCE-1")
        self.assertEqual(state["txn"]["status"], "pending")
        self.assertTrue(state["simulation"])
        self.assertFalse(state["insert_customer"])
        self.assertEqual(state["customer"], existing_customer)
        self.assertEqual(state["policy"], self.policy)
        self.assert_no_direct_writes()
        self.audit.assert_not_awaited()

    async def test_model_failure_stops_batch_without_rules_fallback_or_ingestion(self):
        self.invoke.side_effect = evaluate.ModelUnavailableError("PRIVATE_PROVIDER_PAYLOAD")
        with patch.object(simulator, "_evaluate_policy_only", new=AsyncMock()) as fallback:
            result = await simulator.simulate_transactions(
                principal_id="ana", count=2, mode="sequential", policy_only=False,
            )
        self.assertEqual(result["simulated"], [])
        self.assertEqual(len(result["failed"]), 1)
        self.assertEqual(result["failed"][0]["code"], "model_unavailable")
        self.assertFalse(result["failed"][0]["created"])
        self.assertNotIn("PRIVATE_PROVIDER_PAYLOAD", str(result))
        self.invoke.assert_awaited_once()
        fallback.assert_not_awaited()
        self.audit.assert_not_awaited()
        self.assert_no_direct_writes()

    async def test_other_evaluation_failure_is_sanitized_without_rules_fallback(self):
        self.invoke.side_effect = RuntimeError("PRIVATE_DATABASE_PAYLOAD")
        with patch.object(simulator, "_evaluate_policy_only", new=AsyncMock()) as fallback:
            result = await simulator.simulate_transactions(
                principal_id="ana", count=1, mode="sequential", policy_only=False,
            )
        self.assertEqual(result["simulated"], [])
        self.assertFalse(result["failed"][0]["created"])
        self.assertNotIn("PRIVATE_DATABASE_PAYLOAD", str(result))
        fallback.assert_not_awaited()
        self.assert_no_direct_writes()

    async def test_missing_policy_never_fabricates_policy_or_ingests_transaction(self):
        self.db.policies.find_one.return_value = None
        result = await simulator.simulate_transactions(principal_id="ana", count=1, mode="sequential")
        self.assertEqual(result["simulated"], [])
        self.assertFalse(result["failed"][0]["created"])
        self.invoke.assert_not_awaited()
        self.audit.assert_not_awaited()
        self.assert_no_direct_writes()

    async def test_explicit_policy_only_creation_is_one_audited_write(self):
        self.policy["criteria"] = [{"id": "C-02", "description": "Account open", "kind": "hard",
                                    "check": "test_account", "params": {}}]
        check = AsyncMock(return_value={"result": "pass", "evidence": "Account open"})
        with patch.dict(simulator.CHECKS, {"test_account": check}):
            result = await simulator.simulate_transactions(
                principal_id="ana", count=1, mode="sequential", policy_only=True,
            )
        self.assertEqual(result["failed"], [])
        self.invoke.assert_not_awaited()
        self.audit.assert_awaited_once()
        audit = self.audit.await_args.kwargs
        self.assertEqual(audit["event"], "evaluation.created")
        self.assertEqual(audit["actor"]["on_behalf_of"], "ana")
        writes = audit["writes"]
        self.assertEqual([(w.collection, w.op) for w in writes],
                         [("customers", "insert"), ("transactions", "insert"), ("evaluations", "insert")])
        self.assertEqual(writes[1].document["status"], "awaiting_review")
        evaluation = writes[2].document
        self.assertEqual(evaluation["effective_recommendation"], "pass")
        self.assertEqual(evaluation["checks"][0]["effective_result"], "pass")
        self.assertIsNone(evaluation["checks"][0]["override"])
        self.assert_no_direct_writes()
