"""Create collections, indexes, validators, and vector index. Safe to re-run.

Run from backend/:  uv run python -m scripts.setup_db
"""

import asyncio

from pymongo import ASCENDING
from pymongo.operations import SearchIndexModel

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

AUDIT_LOG_SCHEMA = {
    "bsonType": "object",
    "required": [
        "seq",
        "ts",
        "actor",
        "event",
        "txn_id",
        "ref",
        "detail",
        "prev_hash",
        "hash",
    ],
    "properties": {
        "seq": {"bsonType": "int", "minimum": 1},
        "ts": {"bsonType": "string"},
        "actor": {
            "bsonType": "object",
            "required": ["id", "type", "role"],
            "properties": {
                "id": {"bsonType": "string"},
                "type": {"enum": ["human", "agent"]},
                "role": {"bsonType": "string"},
            },
        },
        "event": {
            "enum": [
                "evaluation.created",
                "question.answered",
                "check.overridden",
                "check.override_reverted",
                "decision.denied",
                "decision.recorded",
                "memory.created",
            ]
        },
        "txn_id": {"bsonType": ["string", "null"]},
        "ref": {
            "bsonType": "object",
            "required": ["collection", "id"],
            "properties": {
                "collection": {"bsonType": "string"},
                "id": {"bsonType": "string"},
            },
        },
        "detail": {"bsonType": "object"},
        "prev_hash": {"bsonType": "string"},
        "hash": {"bsonType": "string"},
    },
}

VECTOR_INDEX_NAME = "memory_text_idx"


async def _ensure_vector_index(db) -> None:
    cursor = await db.memory.list_search_indexes(name=VECTOR_INDEX_NAME)
    existing = await cursor.to_list(length=5)
    if existing:
        print(f"vector index ready: {VECTOR_INDEX_NAME}")
        return

    model = SearchIndexModel(
        name=VECTOR_INDEX_NAME,
        type="vectorSearch",
        definition={
            "fields": [
                {
                    "type": "autoEmbed",
                    "path": "text",
                    "model": "voyage-4",
                    "modality": "text",
                },
                {"type": "filter", "path": "txn_type"},
                {"type": "filter", "path": "kind"},
                {"type": "filter", "path": "active"},
                {"type": "filter", "path": "scope.criterion_id"},
            ]
        },
    )
    try:
        await db.memory.create_search_index(model)
        print(f"vector index created: {VECTOR_INDEX_NAME}")
    except Exception as exc:
        print(f"vector index skipped ({exc}); search_memory will use keyword fallback")


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

    await db.command(
        {
            "collMod": "audit_log",
            "validator": {"$jsonSchema": AUDIT_LOG_SCHEMA},
            "validationLevel": "strict",
        }
    )
    print("audit_log $jsonSchema validator ready")

    await db.chain_head.update_one(
        {"_id": "head"},
        {"$setOnInsert": {"seq": 0, "hash": GENESIS_HASH}},
        upsert=True,
    )
    print("chain_head ready")

    await _ensure_vector_index(db)

    await close_client()


if __name__ == "__main__":
    asyncio.run(main())
