"""Policy gate. Contract: docs/contracts.md §5.2."""

from typing import Any

from app.db.client import get_db


async def check_gate(
    *,
    principal: dict[str, Any],
    txn: dict[str, Any],
    evaluation: dict[str, Any],
    verdict: str | None = None,
    action: str = "decision",
    check: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return {"result": "allow" | "deny", "rule_id": str | None, "reason": str}.

    Gates a decision (action="decision") or a check override (action="override",
    with the check being overridden). Contract: docs/contracts.md §5.2 and §8.

    Deny, in this order:
      1. no decision rule for the principal's role
      2. txn amount over the rule's max_amount
      3. override only: the check is hard and the rule has can_override_hard_fail false

    Whether every failed check was cleared before approving is a precondition
    checked by the caller, not a gate rule.
    """
    db = get_db()
    txn_type = txn.get("type")
    policy = await db.policies.find_one({"txn_type": txn_type, "version": evaluation["policy_version"]}, {"_id": 0})
    if not policy:
        return {
            "result": "deny",
            "rule_id": None,
            "reason": f"Evaluation policy version not found for transaction type '{txn_type}'.",
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
            "reason": f"Role '{role}' is not authorized to {'override checks' if action == 'override' else 'decide transactions'}.",
        }

    rule_id = rule.get("rule_id")
    max_amount = rule.get("max_amount")
    amount = txn.get("amount", 0)
    if max_amount is not None and amount > max_amount:
        return {
            "result": "deny",
            "rule_id": rule_id,
            "reason": f"Amount {amount} exceeds {role} limit {max_amount}. A supervisor must {'authorize this override' if action == 'override' else 'decide'}.",
        }

    if (
        action == "override"
        and (check or {}).get("kind") == "hard"
        and not rule.get("can_override_hard_fail", False)
    ):
        return {
            "result": "deny",
            "rule_id": rule_id,
            "reason": f"Role '{role}' may not override hard check {(check or {}).get('criterion_id')}.",
        }

    return {
        "result": "allow",
        "rule_id": rule_id,
        "reason": f"{role} within policy limits",
    }
