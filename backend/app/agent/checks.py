"""Deterministic checks. Contract: docs/contracts.md §5.3.

A policy criterion names its function in `check`. Each function returns
{"result": "pass" | "no_pass" | "flag", "evidence": str}.
"""

from collections.abc import Awaitable, Callable
from typing import Any

CheckOutcome = dict[str, str]
CheckFn = Callable[[dict[str, Any], dict[str, Any], dict[str, Any], Any], Awaitable[CheckOutcome]]

CHECKS: dict[str, CheckFn] = {}


def check(name: str) -> Callable[[CheckFn], CheckFn]:
    def register(fn: CheckFn) -> CheckFn:
        CHECKS[name] = fn
        return fn

    return register


# Must-have for the demo: sanctions_screen (C-01), duplicate (C-03),
# travel_rule_fields (W-01), eft_report_threshold (W-02), cheque_date_valid (Q-01).
# Optional: account_ok (C-02), structuring_24h (C-05), hold_period_applied (Q-02).
#
# @check("sanctions_screen")
# async def sanctions_screen(txn, customer, params, db) -> CheckOutcome: ...
