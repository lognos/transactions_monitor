"""Local CSV -> policy screening integration; no Atlas or LLM required."""

import unittest
import csv
from pathlib import Path

from app.graphs.evaluate import build_evaluate_graph
from app.local_demo import LocalDemo


class PolicyIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_one_csv_transaction_runs_remote_cheque_policy(self):
        store = LocalDemo()

        async def unexpected_recommend(**kwargs):
            self.fail('The model must not run before the run_checks breakpoint.')

        graph = build_evaluate_graph(
            store=store, write_with_audit=store.write_with_audit,
            recommend=unexpected_recommend,
        )
        result = await graph.ainvoke(
            {'txn_id': 'TX-CA-000010', 'principal_id': 'ana'},
            interrupt_after=['run_checks'],
        )
        self.assertEqual(result['txn']['txn_id'], 'TX-CA-000010')
        self.assertEqual(result['policy']['txn_type'], 'cheque')
        self.assertEqual(
            {check['criterion_id'] for check in result['checks']},
            {'C-01', 'C-02', 'C-03', 'A-01', 'S-01', 'Q-01', 'Q-02', 'R-01'},
        )
        self.assertTrue(all(check['source'] == 'rule' for check in result['checks']))
        self.assertNotIn('evaluation', result)
        self.assertEqual(store.audit_log, [])
        self.assertTrue(all(txn['status'] == 'pending' for txn in await store.list_transactions()))

    async def test_each_csv_payment_method_loads_its_own_policy(self):
        store = LocalDemo()
        graph = build_evaluate_graph(
            store=store, write_with_audit=store.write_with_audit, recommend=None,
        )
        examples = {}
        for txn in await store.list_transactions():
            examples.setdefault(txn['type'], txn['txn_id'])
        self.assertEqual(len(examples), 6)
        for txn_type, txn_id in examples.items():
            with self.subTest(txn_type=txn_type):
                result = await graph.ainvoke(
                    {'txn_id': txn_id, 'principal_id': 'ana'},
                    interrupt_after=['run_checks'],
                )
                self.assertEqual(result['policy']['txn_type'], txn_type)
                self.assertEqual(
                    {check['criterion_id'] for check in result['checks']},
                    {c['id'] for c in result['policy']['criteria'] if c['kind'] == 'hard'},
                )

    async def test_csv_amount_mismatch_reaches_policy_check(self):
        store = LocalDemo()
        csv_path = Path(__file__).parents[1] / 'app' / 'data' / 'transactions.csv'
        with csv_path.open(encoding='utf-8-sig', newline='') as source:
            row = next(row for row in csv.DictReader(source)
                       if float(row['amount_cad']) != float(row['source_document_amount_cad']))
        graph = build_evaluate_graph(
            store=store, write_with_audit=store.write_with_audit, recommend=None,
        )
        result = await graph.ainvoke(
            {'txn_id': row['transaction_id'], 'principal_id': 'ana'},
            interrupt_after=['run_checks'],
        )
        check = next(c for c in result['checks'] if c['criterion_id'] == 'A-01')
        self.assertEqual(check['result'], 'no_pass')
        self.assertIn('Amount mismatch', check['evidence'])


if __name__ == '__main__':
    unittest.main()
