"""Policy gate. Contract: docs/contracts.md §5.2."""

from typing import Any


async def check_gate(
    *, principal: dict[str, Any], txn: dict[str, Any], evaluation: dict[str, Any], verdict: str
) -> dict[str, Any]:
    """Return {"result": "allow" | "deny", "rule_id": str | None, "reason": str}.

    Deny, in this order:
      1. no decision rule for the principal's role
      2. txn amount over the rule's max_amount
      3. verdict validates, a hard check is no_pass, and the rule cannot override
    """
    raise NotImplementedError("db.gate.check_gate")
