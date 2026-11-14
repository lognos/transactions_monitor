"""Create collections and indexes. Safe to re-run.

Run from backend/:  uv run python -m scripts.setup_db
"""

import asyncio

from pymongo import ASCENDING

from app.db import COLLECTIONS, close_client, get_db
from app.db.audit import GENESIS_HASH

# (collection, keys, unique)
INDEXES = [
    ("transactions", [("txn_id", ASCENDING)], True),
    ("transactions", [("status", ASCENDING), ("created_at", ASCENDING)], False),
    ("customers", [("customer_id", ASCENDING)], True),
    ("policies", [("txn_type", ASCENDING), ("version", ASCENDING)], True),
    ("evaluations", [("eval_id", ASCENDING)], True),
    ("evaluations", [("txn_id", ASCENDING)], False),
    ("decisions", [("eval_id", ASCENDING)], True),
    ("memory", [("memory_id", ASCENDING)], True),
    ("audit_log", [("seq", ASCENDING)], True),
    ("audit_log", [("txn_id", ASCENDING), ("seq", ASCENDING)], False),
]


async def main() -> None:
    db = get_db()
    existing = set(await db.list_collection_names())
    for name in COLLECTIONS:
        if name not in existing:
            await db.create_collection(name)
            print(f"created {name}")

    for collection, keys, unique in INDEXES:
        await db[collection].create_index(keys, unique=unique)
    print(f"indexes ensured: {len(INDEXES)}")

    await db.chain_head.update_one(
        {"_id": "head"},
        {"$setOnInsert": {"seq": 0, "hash": GENESIS_HASH}},
        upsert=True,
    )
    print("chain_head ready")

    # TODO(db): $jsonSchema validator on audit_log (contracts §3.8).
    # TODO(db): vector index "memory_text_idx" on memory.text with filters
    #           txn_type, kind, active. Confirm Automated Embedding syntax first.

    await close_client()


if __name__ == "__main__":
    asyncio.run(main())
