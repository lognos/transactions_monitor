"""Read-only check references and shared chat citation labels (§4)."""

from typing import Any

from app.db import get_db
from app.server.errors import ApiError

NO_ID = {"_id": 0}


async def _policy_for_evaluation(evaluation: dict[str, Any]) -> dict[str, Any] | None:
    db = get_db()
    txn = await db.transactions.find_one({"txn_id": evaluation["txn_id"]}, NO_ID)
    if txn is None:
        return None
    return await db.policies.find_one(
        {"txn_type": txn["type"], "version": evaluation["policy_version"]}, NO_ID
    )


async def _memories_and_authors(
    memory_ids: list[str],
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    if not memory_ids:
        return {}, {}
    db = get_db()
    memories = await db.memory.find({"memory_id": {"$in": memory_ids}}, NO_ID).to_list()
    author_ids = list({memory["author_id"] for memory in memories})
    authors = await db.principals.find(
        {"_id": {"$in": author_ids}}, {"_id": 1, "name": 1}
    ).to_list() if author_ids else []
    return (
        {memory["memory_id"]: memory for memory in memories},
        {author["_id"]: author["name"] for author in authors},
    )


async def get_check_references(eval_id: str, criterion_id: str) -> dict[str, Any]:
    """Resolve only the policy and memories actually used by this check."""
    db = get_db()
    evaluation = await db.evaluations.find_one({"eval_id": eval_id}, NO_ID)
    if evaluation is None:
        raise ApiError(404, "not_found", f"Unknown evaluation '{eval_id}'")
    check = next(
        (item for item in evaluation["checks"] if item["criterion_id"] == criterion_id), None
    )
    if check is None:
        raise ApiError(404, "not_found", f"Unknown criterion '{criterion_id}' in '{eval_id}'")

    policy = await _policy_for_evaluation(evaluation)
    criterion = next(
        (item for item in (policy or {}).get("criteria", []) if item["id"] == criterion_id),
        None,
    )
    if policy is None or criterion is None:
        raise ApiError(404, "not_found", f"Policy criterion '{criterion_id}' was not found")

    adjustment_ids = list(dict.fromkeys(check.get("adjustments_used", [])))
    precedent_ids = list(dict.fromkeys(check.get("precedents_used", [])))
    memories, authors = await _memories_and_authors(adjustment_ids + precedent_ids)
    decision_ids = list({
        memories[memory_id]["source_decision_id"]
        for memory_id in precedent_ids
        if memory_id in memories and memories[memory_id].get("source_decision_id")
    })
    decisions = await db.decisions.find(
        {"decision_id": {"$in": decision_ids}},
        {"_id": 0, "decision_id": 1, "verdict": 1},
    ).to_list() if decision_ids else []
    verdicts = {decision["decision_id"]: decision["verdict"] for decision in decisions}

    adjustments = []
    precedents = []
    for kind, memory_ids, destination in (
        ("adjustment", adjustment_ids, adjustments),
        ("precedent", precedent_ids, precedents),
    ):
        for memory_id in memory_ids:
            memory = memories.get(memory_id)
            if memory is None or memory["kind"] != kind:
                continue
            item = {
                "memory_id": memory_id,
                "text": memory["text"],
                "author_id": memory["author_id"],
                "author_name": authors.get(memory["author_id"]),
                "source_txn_id": memory.get("source_txn_id"),
                "created_at": memory["created_at"],
            }
            if kind == "adjustment":
                item["condition"] = (memory.get("scope") or {}).get("condition")
            else:
                item["verdict"] = verdicts.get(memory.get("source_decision_id"))
            destination.append(item)

    return {
        "check": {key: check[key] for key in ("criterion_id", "result", "source", "evidence")},
        "policy": {
            "txn_type": policy["txn_type"],
            "version": policy["version"],
            "criterion_id": criterion_id,
            **{key: criterion.get(key) for key in ("description", "kind", "regulation_ref", "params")},
        },
        "adjustments": adjustments,
        "precedents": precedents,
    }


async def label_citations(
    citations: list[dict[str, Any]], *, evaluation: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Add readable labels without changing or persisting the agent's citations."""
    policy_refs = {citation["ref"] for citation in citations if citation["type"] == "policy"}
    descriptions: dict[str, str] = {}
    if policy_refs:
        if evaluation is not None:
            policy = await _policy_for_evaluation(evaluation)
            policies = [policy] if policy is not None else []
        else:
            policies = await get_db().policies.find(
                {"active": True, "criteria.id": {"$in": list(policy_refs)}}, NO_ID
            ).sort("txn_type", 1).to_list()
        for policy in policies:
            for criterion in policy["criteria"]:
                if criterion["id"] in policy_refs:
                    descriptions.setdefault(criterion["id"], criterion["description"])

    memory_ids = list({
        citation["ref"] for citation in citations if citation["type"] in ("precedent", "adjustment")
    })
    memories, authors = await _memories_and_authors(memory_ids)
    labeled = []
    for citation in citations:
        ref = citation["ref"]
        label = ref
        if citation["type"] == "policy":
            label = descriptions.get(ref, ref)
        elif ref in memories and memories[ref]["kind"] == citation["type"]:
            memory = memories[ref]
            summary = " ".join(memory["text"].split())
            if len(summary) > 140:
                summary = summary[:137].rstrip() + "..."
            author = authors.get(memory["author_id"], memory["author_id"])
            label = f"{summary} — {author}"
        labeled.append({"type": citation["type"], "ref": ref, "label": label})
    return labeled
