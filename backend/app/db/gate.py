"""Policy gate. Contract: docs/contracts.md §5.2."""

from typing import Any

from app.db.client import get_db


async def check_gate(
    *, principal: dict[str, Any], txn: dict[str, Any], evaluation: dict[str, Any], verdict: str
) -> dict[str, Any]:
    """Return {"result": "allow" | "deny", "rule_id": str | None, "reason": str}.

    Deny, in this order:
      1. no decision rule for the principal's role
      2. txn amount over the rule's max_amount
      3. verdict validates, a hard check is no_pass, and the rule cannot override
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
        return {
            "result": "deny",
            "rule_id": rule_id,
            "reason": f"Amount {amount} exceeds {role} limit {max_amount}. A supervisor must decide.",
        }

    if verdict in ("validated", "validated_with_comments"):
        has_hard_fail = any(
            chk.get("kind") == "hard" and chk.get("result") == "no_pass"
            for chk in evaluation.get("checks", [])
        )
        if has_hard_fail and not rule.get("can_override_hard_fail", False):
            return {
                "result": "deny",
                "rule_id": rule_id,
                "reason": "Cannot validate when a hard check failed.",
            }

    return {
        "result": "allow",
        "rule_id": rule_id,
        "reason": f"{role} within policy limits",
    }
