"""Policy gate. Contract: docs/contracts.md §5.2, §8."""

from typing import Any, Literal

from app.db.client import get_db


async def check_gate(
    *,
    principal: dict[str, Any],
    txn: dict[str, Any],
    evaluation: dict[str, Any],
    verdict: str | None = None,
    action: Literal["decide", "override"] = "decide",
    check: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return {"result": "allow" | "deny", "rule_id": str | None, "reason": str}.

    Deny, in this order:
      1. no decision rule for the principal's role
      2. txn amount over the rule's max_amount
      3. when action == "override" and check.kind == "hard", rule.can_override_hard_fail is false
    """
    db = get_db()
    txn_type = txn.get("type")
    policy = await db.policies.find_one({"txn_type": txn_type, "active": True}, {"_id": 0})
    if not policy:
        return {
            "result": "deny",
            "rule_id": None,
            "reason": f"No active policy found for transaction type '{txn_type}'.",
        }

    role = principal.get("role")
    rule = next(
        (r for r in policy.get("decision_rules", []) if r.get("role") == role),
        None,
    )
    if rule is None:
        return {
            "result": "deny",
            "rule_id": None,
            "reason": f"Role '{role}' is not authorized to decide transactions.",
        }

    rule_id = rule.get("rule_id")
    max_amount = rule.get("max_amount")
    amount = txn.get("amount", 0)
    if max_amount is not None and amount > max_amount:
        verb = "override" if action == "override" else "decide"
        return {
            "result": "deny",
            "rule_id": rule_id,
            "reason": f"Amount {amount} exceeds {role} limit {max_amount}. A supervisor must {verb}.",
        }

    if action == "override":
        if check is None:
            raise ValueError("check is required when action='override'")
        if check.get("kind") == "hard" and not rule.get("can_override_hard_fail", False):
            return {
                "result": "deny",
                "rule_id": rule_id,
                "reason": f"Role '{role}' cannot override hard check '{check.get('criterion_id', '')}'.",
            }

    return {
        "result": "allow",
        "rule_id": rule_id,
        "reason": f"{role} within policy limits",
    }
