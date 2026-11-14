"""Evaluation reuse and races, isolated from the model and shared database."""

import unittest
from copy import deepcopy
from unittest.mock import AsyncMock, MagicMock, patch

from app.agent.graphs import evaluate


class EvaluationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.txn = {"txn_id": "SIM-test", "customer_id": "CUS-test", "type": "cheque",
                    "amount": 9000, "status": "awaiting_review"}
        self.previous = {"eval_id": "EVAL-old", "txn_id": "SIM-test", "status": "awaiting_review",
                         "checks": [{"criterion_id": "C-04", "kind": "judgment", "result": "no_pass"}]}
        self.state = {"txn": deepcopy(self.txn), "principal_id": "ana", "refresh": True,
                      "customer": {}, "policy": {"version": 1, "criteria": []},
                      "previous_evaluation": deepcopy(self.previous)}
        self.documents = {"transactions": [deepcopy(self.txn)], "evaluations": [deepcopy(self.previous)]}

    async def audited_write(self, **kwargs):
        """Model the writer's atomic, match-required updates without a database."""
        documents = deepcopy(self.documents)
        for write in kwargs["writes"]:
            rows = documents[write.collection]
            if write.op == "insert":
                rows.append(deepcopy(write.document))
                continue

            def matches(row):
                for key, value in write.filter.items():
                    if isinstance(value, dict) and "$ne" in value:
                        if row.get(key) == value["$ne"]:
                            return False
                    elif row.get(key) != value:
                        return False
                return True

            matched = [row for row in rows if matches(row)]
            if write.op == "update" and len(matched) != 1:
                raise ValueError("Missing or changed document for audited update")
            for row in matched:
                row.update(deepcopy(write.update["$set"]))
        self.documents = documents

    async def test_regular_evaluation_reuses_existing_review_without_model(self):
        db = MagicMock()
        db.__getitem__.side_effect = lambda name: getattr(db, name)
        db.transactions.find_one = AsyncMock(return_value=self.txn)
        db.customers.find_one = AsyncMock(return_value={"customer_id": "CUS-test"})
        db.evaluations.find_one = AsyncMock(return_value=self.previous)
        with patch.object(evaluate, "get_db", return_value=db), \
             patch.object(evaluate, "get_structured_llm") as model, \
             patch.object(evaluate, "write_with_audit", new=AsyncMock()) as writer:
            result = await evaluate.evaluate_graph.ainvoke({"txn_id": "SIM-test", "principal_id": "ana"})
        self.assertEqual(result["evaluation"]["eval_id"], "EVAL-old")
        model.assert_not_called()
        writer.assert_not_awaited()

    async def test_decided_transaction_never_runs_evaluation(self):
        db = MagicMock()
        db.__getitem__.return_value.find_one = AsyncMock(return_value={**self.txn, "status": "passed"})
        with patch.object(evaluate, "get_db", return_value=db), \
             patch.object(evaluate, "get_structured_llm") as model:
            with self.assertRaisesRegex(ValueError, "already has a decision"):
                await evaluate.evaluate_graph.ainvoke({"txn_id": "SIM-test", "principal_id": "ana", "refresh": True})
        model.assert_not_called()

    async def test_decision_during_evaluation_cannot_reopen_transaction(self):
        self.documents["transactions"][0]["status"] = "passed"
        before = deepcopy(self.documents)
        with patch.object(evaluate, "write_with_audit", side_effect=self.audited_write):
            with self.assertRaisesRegex(ValueError, "Missing or changed"):
                await evaluate.save_evaluation(self.state)
        self.assertEqual(self.documents, before)

    async def test_override_during_refresh_aborts_without_superseding_it(self):
        self.documents["evaluations"][0]["checks"][0]["override"] = {"result": "pass", "reason": "Verified"}
        before = deepcopy(self.documents)
        with patch.object(evaluate, "write_with_audit", side_effect=self.audited_write):
            with self.assertRaisesRegex(ValueError, "Missing or changed"):
                await evaluate.save_evaluation(self.state)
        self.assertEqual(self.documents, before)

    async def test_concurrent_refreshes_leave_one_live_evaluation_and_retire_stale(self):
        self.documents["evaluations"].append({**deepcopy(self.previous), "eval_id": "EVAL-stale"})
        with patch.object(evaluate, "write_with_audit", side_effect=self.audited_write):
            saved = await evaluate.save_evaluation(self.state)
            with self.assertRaisesRegex(ValueError, "Missing or changed"):
                await evaluate.save_evaluation(self.state)
        live = [row["eval_id"] for row in self.documents["evaluations"] if row["status"] == "awaiting_review"]
        self.assertEqual(live, [saved["evaluation"]["eval_id"]])

    async def test_first_evaluation_does_not_require_stale_evaluations(self):
        self.documents["evaluations"] = []
        self.documents["transactions"][0]["status"] = "pending"
        self.state["txn"]["status"] = "pending"
        self.state["previous_evaluation"] = None
        with patch.object(evaluate, "write_with_audit", side_effect=self.audited_write):
            saved = await evaluate.save_evaluation(self.state)
        self.assertEqual(len(self.documents["evaluations"]), 1)
        self.assertEqual(self.documents["evaluations"][0]["eval_id"], saved["evaluation"]["eval_id"])

    async def test_simulation_inserts_customer_transaction_and_evaluation_atomically(self):
        self.documents = {"customers": [], "transactions": [], "evaluations": []}
        state = {**self.state, "simulation": True, "insert_customer": True,
                 "customer": {"customer_id": "CUS-test"}, "previous_evaluation": None}
        with patch.object(evaluate, "write_with_audit", side_effect=self.audited_write) as writer:
            saved = await evaluate.save_evaluation(state)
        writer.assert_awaited_once()
        self.assertEqual(writer.call_args.kwargs["event"], "evaluation.created")
        self.assertEqual(self.documents["customers"], [{"customer_id": "CUS-test"}])
        self.assertEqual(self.documents["transactions"], [saved["txn"]])
        self.assertEqual(self.documents["evaluations"], [saved["evaluation"]])
        self.assertEqual(saved["txn"]["status"], "awaiting_review")

    async def test_simulation_model_failure_never_persists_partial_transaction(self):
        model = MagicMock()
        model.ainvoke = AsyncMock(side_effect=RuntimeError("model unavailable"))
        state = {**self.state, "simulation": True, "insert_customer": False,
                 "policy": {"criteria": [{"id": "C-04", "kind": "judgment"}]}}
        with patch.object(evaluate, "get_db", return_value=MagicMock()), \
             patch.object(evaluate, "get_structured_llm", return_value=model), \
             patch.object(evaluate, "search_memory", new=AsyncMock(return_value=[])), \
             patch.object(evaluate, "active_adjustments", new=AsyncMock(return_value=[])), \
             patch.object(evaluate.asyncio, "sleep", new=AsyncMock()), \
             patch.object(evaluate, "write_with_audit", new=AsyncMock()) as writer:
            with self.assertRaises(evaluate.ModelUnavailableError):
                await evaluate.evaluate_graph.ainvoke(state)
        writer.assert_not_awaited()

    async def test_quota_failure_stops_after_first_call_without_writes(self):
        class RateLimitError(Exception):
            pass

        model = MagicMock()
        model.ainvoke = AsyncMock(side_effect=RateLimitError("private provider response"))
        state = {**self.state, "policy": {"criteria": [{"id": "C-04", "kind": "judgment"}]}}
        with patch.object(evaluate, "get_structured_llm", return_value=model), \
             patch.object(evaluate.asyncio, "sleep", new=AsyncMock()) as sleep, \
             patch.object(evaluate, "write_with_audit", new=AsyncMock()) as writer:
            with self.assertRaises(evaluate.ModelUnavailableError) as raised:
                await evaluate.recommend(state)
        self.assertNotIn("private provider response", str(raised.exception))
        model.ainvoke.assert_awaited_once()
        sleep.assert_not_awaited()
        writer.assert_not_awaited()

    def test_quota_detection_accepts_provider_status_codes(self):
        error = RuntimeError("private provider response")
        error.code = 429
        self.assertTrue(evaluate._is_quota_error(error))
        error.code = 500
        self.assertFalse(evaluate._is_quota_error(error))


if __name__ == "__main__":
    unittest.main()
