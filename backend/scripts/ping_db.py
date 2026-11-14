"""Connection check. Run from backend/:  uv run python -m scripts.ping_db"""

import asyncio

from app.config import settings
from app.db import COLLECTIONS, close_client, get_db, ping


async def main() -> None:
    await ping()
    existing = set(await get_db().list_collection_names())
    print(f"Connected. Database: {settings.db_name}")
    for name in COLLECTIONS:
        print(f"  {'ok     ' if name in existing else 'missing'} {name}")
    await close_client()


if __name__ == "__main__":
    asyncio.run(main())
