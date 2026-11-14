"""Process-local dependencies for running the cheque slice without Atlas."""

import asyncio
import hashlib
import json
from collections import defaultdict
from csv import DictReader
from copy import deepcopy
from contextlib import asynccontextmanager
from pathlib import Path
from statistics import median

from .models import Write, utc_now


def _load_transactions() -> tuple[dict[str, dict], dict[str, dict]]:
    """Read the selected columns from the supplied synthetic transaction export."""
    transactions: dict[str, dict] = {}
    customers: dict[str, dict] = {}
    posted_amounts: dict[str, list[float]] = defaultdict(list)
    path = Path(__file__).with_name('data') / 'transactions.csv'
    with path.open(encoding='utf-8-sig', newline='') as source:
        for row in DictReader(source):
            txn_id = row['transaction_id']
            if txn_id in transactions:
                raise ValueError(f'Duplicate transaction ID in {path.name}: {txn_id}')
            customer_id = row['source_account_id']
            txn_type = row['payment_method'].lower()
            amount = float(row['amount_cad'])
            source_status = row['sender_account_status'].lower()
            customers[customer_id] = {
                'customer_id': customer_id, 'name': row['payer_name'],
                'segment': row['sender_account_holder_type'].lower(),
                'risk_rating': None, 'country': 'CA',
                'kyc_status': row['sender_kyc_status'].lower(),
                'account_status': 'open' if source_status == 'active' else source_status,
                'balance': float(row['sender_available_balance_cad']),
            }
            if row['posting_status'] == 'POSTED' and amount > 0:
                posted_amounts[customer_id].append(amount)

            details = {
                'direction': row['direction'].lower(),
                'posting_status': row['posting_status'].lower(),
                'risk_flag': row['risk_flag'] == 'true',
                'compliance_cleared': row['compliance_cleared'] == 'true',
                'payment_reference': row['payment_reference'] or None,
                'original_transaction_id': row['original_transaction_id'] or None,
                'source_document_amount': float(row['source_document_amount_cad']),
                'return_reason_code': row['return_reason_code'] or None,
            }
            if txn_type == 'cheque':
                details.update(
                    cheque_date=None, hold_days_applied=None,
                    deposit_channel={'BRANCH_CAPTURE': 'branch'}.get(row['cheque_capture_channel']),
                    written_amount=float(row['cheque_written_amount_cad']),
                    presented_amount=float(row['cheque_presented_amount_cad']),
                )
            elif txn_type == 'wire':
                details.update(
                    originator={'name': row['payer_name'], 'account': customer_id, 'address': None},
                    international=None, new_beneficiary=row['destination_is_new'] == 'true',
                )

            transactions[txn_id] = {
                'txn_id': txn_id, 'type': txn_type, 'amount': amount, 'currency': row['currency'],
                'customer_id': customer_id,
                'counterparty': {
                    'name': row['payee_name'], 'account': row['destination_account_id'],
                    'address': None, 'country': None,
                },
                'memo': row['description'], 'created_at': row['transaction_datetime'],
                'status': 'pending', 'type_specific': details,
            }
    for customer_id, customer in customers.items():
        amounts = posted_amounts[customer_id]
        customer['typical_amount'] = median(amounts) if amounts else None

    return transactions, customers


def _cheque_policy() -> dict:
    return {
        'txn_type': 'cheque', 'version': 1, 'active': True,
        'criteria': [
            {'id': 'C-01', 'kind': 'hard', 'check': 'sanctions_screen',
             'description': 'Counterparty is clear of the demo sanctions list',
             'params': {'names': ['Example Blocked Company']}, 'regulation_ref': 'Demo sanctions policy'},
            {'id': 'C-03', 'kind': 'hard', 'check': 'duplicate',
             'description': 'No duplicate transaction', 'params': {}, 'regulation_ref': 'Bank policy'},
            {'id': 'C-04', 'kind': 'judgment', 'check': None,
             'description': 'Amount is consistent with the customer profile',
             'params': {'ratio_hint': 3}, 'regulation_ref': 'FINTRAC suspicious-transaction indicators'},
            {'id': 'Q-01', 'kind': 'hard', 'check': 'cheque_date_valid',
             'description': 'Cheque is neither stale-dated nor post-dated',
             'params': {}, 'regulation_ref': 'Bank practice'},
        ],
        'decision_rules': [
            {'rule_id': 'D-01', 'role': 'analyst', 'max_amount': 50000, 'can_override_hard_fail': False},
            {'rule_id': 'D-02', 'role': 'supervisor', 'max_amount': None, 'can_override_hard_fail': False},
        ],
    }


class LocalDemo:
    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.audit_log: list[dict] = []
        transactions, customers = _load_transactions()
        self._collections: dict[str, dict[str, dict]] = {
            'principals': {
                'ana': {'_id': 'ana', 'type': 'human', 'name': 'Ana', 'role': 'analyst', 'approval_limit': 50000},
                'aud': {'_id': 'aud', 'type': 'human', 'name': 'Auditor', 'role': 'auditor', 'approval_limit': 0},
            },
            'customers': customers,
            'transactions': transactions,
            'policies': {'cheque': _cheque_policy()},
            'evaluations': {}, 'decisions': {}, 'memory': {},
        }

    @asynccontextmanager
    async def transaction(self):
        async with self.lock:
            collections = self._collections.copy()
            audit_log = self.audit_log
            self.audit_log = audit_log.copy()
            try:
                yield
            except BaseException:
                self._collections = collections
                self.audit_log = audit_log
                raise

    async def get(self, collection: str, id: str) -> dict | None:
        return deepcopy(self._collections[collection].get(id))

    async def list_documents(self, collection: str) -> list[dict]:
        return deepcopy(list(self._collections[collection].values()))

    async def list_transactions(self) -> list[dict]:
        return await self.list_documents('transactions')

    async def latest_evaluation(self, txn_id: str) -> dict | None:
        for evaluation in reversed(self._collections['evaluations'].values()):
            if evaluation['txn_id'] == txn_id:
                return deepcopy(evaluation)
        return None

    async def decision_for(self, eval_id: str) -> dict | None:
        return next((item for item in await self.list_documents('decisions') if item['eval_id'] == eval_id), None)

    async def active_adjustments(self, *, txn_type: str) -> list[dict]:
        return [item for item in await self.list_documents('memory')
                if item['active'] and item['kind'] == 'adjustment' and item['txn_type'] == txn_type]

    async def check_gate(self, *, principal: dict, txn: dict, evaluation: dict, verdict: str) -> dict:
        policy = await self.get('policies', txn['type'])
        rule = next((item for item in policy['decision_rules'] if item['role'] == principal['role']), None)
        if rule is None:
            return {'result': 'deny', 'rule_id': None, 'reason': 'role has no decision rule'}
        rule_id, limit = rule['rule_id'], rule['max_amount']
        if limit is not None and txn['amount'] > limit:
            return {'result': 'deny', 'rule_id': rule_id, 'reason': 'amount over limit'}
        hard_fail = any(item['kind'] == 'hard' and item['result'] == 'no_pass' for item in evaluation['checks'])
        if verdict.startswith('validated') and hard_fail and not rule['can_override_hard_fail']:
            return {'result': 'deny', 'rule_id': rule_id, 'reason': 'hard check failed'}
        return {'result': 'allow', 'rule_id': rule_id, 'reason': 'decision permitted by policy'}

    async def write_with_audit(
        self, *, actor: dict, event: str, txn_id: str, ref: dict, detail: dict, writes: list[Write],
    ) -> dict:
        changes = {}
        for write in writes:
            documents = changes.setdefault(write.collection, self._collections[write.collection].copy())
            if write.operation == 'update':
                documents[write.id] = {**documents[write.id], **deepcopy(write.values)}
            else:
                if write.id in documents:
                    raise ValueError(f'{write.collection} already contains {write.id}')
                documents[write.id] = deepcopy(write.values)
        prev_hash = self.audit_log[-1]['hash'] if self.audit_log else '0' * 64
        entry = {
            'seq': len(self.audit_log) + 1, 'ts': utc_now(), 'actor': actor,
            'event': event, 'txn_id': txn_id, 'ref': ref, 'detail': detail, 'prev_hash': prev_hash,
        }
        canonical = json.dumps(entry, sort_keys=True, separators=(',', ':'))
        entry['hash'] = hashlib.sha256((prev_hash + canonical).encode()).hexdigest()
        self._collections.update(changes)
        self.audit_log.append(deepcopy(entry))
        return entry
