"""Reset and load demo data. Specification: docs/plan-scenarios.md.

Run from backend/ after setup_db:  uv run python -m scripts.seed

Resets every collection (including audit_log, memory, chain_head) so a
rehearsal always starts clean. All data here is written at the event.
"""

import asyncio
import json
from pathlib import Path

from app.db import close_client, get_db
from app.db.audit import GENESIS_HASH

PRINCIPALS: list[dict] = []  # TODO(scenarios)
CUSTOMERS: list[dict] = []  # TODO(scenarios)
TRANSACTIONS: list[dict] = []  # TODO(scenarios)
POLICY_FILE = Path(__file__).resolve().parents[2] / "data" / "hackathon_policies.json"
POLICIES: list[dict] = json.loads(POLICY_FILE.read_text(encoding="utf-8"))
PRECEDENTS: list[dict] = []  # TODO(scenarios): memory docs, kind "precedent", author_id "seed"

SEED = {
    "principals": PRINCIPALS,
    "customers": CUSTOMERS,
    "transactions": TRANSACTIONS,
    "policies": POLICIES,
    "memory": PRECEDENTS,
}
RESET_ONLY = ["evaluations", "decisions", "audit_log"]


async def main() -> None:
    db = get_db()
    for name in [*SEED, *RESET_ONLY]:
        await db[name].delete_many({})
    for name, docs in SEED.items():
        if docs:
            await db[name].insert_many(docs)
        print(f"{name}: {len(docs)}")
    await db.chain_head.replace_one(
        {"_id": "head"}, {"_id": "head", "seq": 0, "hash": GENESIS_HASH}, upsert=True
    )
    await close_client()


if __name__ == "__main__":
    asyncio.run(main())
