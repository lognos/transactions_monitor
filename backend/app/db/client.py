"""One shared AsyncMongoClient for the process."""

from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

from app.config import settings

# Collection names from docs/contracts.md §3.
COLLECTIONS = [
    "principals",
    "customers",
    "transactions",
    "policies",
    "evaluations",
    "decisions",
    "memory",
    "audit_log",
    "chain_head",
]

_client: AsyncMongoClient | None = None


def get_client() -> AsyncMongoClient:
    global _client
    if _client is None:
        _client = AsyncMongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=8000)
    return _client


def get_db() -> AsyncDatabase:
    return get_client()[settings.db_name]


async def ping() -> bool:
    await get_client().admin.command("ping")
    return True


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None
