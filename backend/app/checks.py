from calendar import monthrange
from collections.abc import Awaitable, Callable
from datetime import date
from typing import Literal, TypedDict


class CheckOutcome(TypedDict):
    result: Literal['pass', 'no_pass', 'flag']
    evidence: str


def sanctions_screen(txn: dict, params: dict) -> CheckOutcome:
    name = txn['counterparty']['name'].strip().casefold()
    names = {value.strip().casefold() for value in params['names']}
    if name in names:
        return {'result': 'no_pass', 'evidence': 'Counterparty matches a listed name.'}
    return {'result': 'pass', 'evidence': 'No matching name in the demo sanctions list.'}


async def duplicate(txn: dict, customer: dict, params: dict, db) -> CheckOutcome:
    for candidate in await db.list_transactions():
        if candidate['txn_id'] == txn['txn_id']:
            continue
        if (
            candidate['counterparty']['name'].strip().casefold()
            == txn['counterparty']['name'].strip().casefold()
            and candidate['amount'] == txn['amount']
            and candidate['created_at'][:10] == txn['created_at'][:10]
        ):
            return {'result': 'no_pass', 'evidence': f"Matches {candidate['txn_id']} by payee, amount and date."}
    return {'result': 'pass', 'evidence': 'No matching payee, amount and date.'}


async def cheque_date_valid(txn: dict, customer: dict, params: dict, db) -> CheckOutcome:
    try:
        cheque_date = date.fromisoformat(txn['type_specific']['cheque_date'])
        deposit = date.fromisoformat(txn['created_at'][:10])
    except (KeyError, TypeError, ValueError):
        return {'result': 'no_pass', 'evidence': 'Missing or invalid cheque or deposit date.'}
    year, month = divmod(deposit.year * 12 + deposit.month - 1 - 6, 12)
    month += 1
    oldest = date(year, month, min(deposit.day, monthrange(year, month)[1]))
    if not oldest <= cheque_date <= deposit:
        return {'result': 'no_pass', 'evidence': 'Cheque is post-dated or more than six months old.'}
    return {'result': 'pass', 'evidence': 'Cheque date is within six months of the deposit date.'}


async def check_sanctions(txn: dict, customer: dict, params: dict, db) -> CheckOutcome:
    return sanctions_screen(txn, params)


CheckFn = Callable[[dict, dict, dict, object], Awaitable[CheckOutcome]]
CHECKS: dict[str, CheckFn] = {
    'sanctions_screen': check_sanctions,
    'duplicate': duplicate,
    'cheque_date_valid': cheque_date_valid,
}
