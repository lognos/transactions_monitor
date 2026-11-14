"""Ingest consolidated CSV transactions into MongoDB (customers & transactions).

Run from backend/:
    uv run python -m scripts.ingest_csv
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from app.agent.ingest import load_csv_transactions
from app.db import close_client, get_db

DEFAULT_CSV = Path(__file__).resolve().parents[2] / "data" / "AuditFlow_All_Transactions_Consolidated.csv"


async def main(csv_path: Path = DEFAULT_CSV) -> None:
    db = get_db()
    customers, txns = load_csv_transactions(csv_path)

    for cust in customers:
        await db.customers.update_one(
            {"customer_id": cust["customer_id"]},
            {"$set": cust},
            upsert=True,
        )

    for txn in txns:
        await db.transactions.update_one(
            {"txn_id": txn["txn_id"]},
            {"$set": txn},
            upsert=True,
        )

    print(f"Ingested {len(customers)} customers and {len(txns)} transactions from {csv_path.name}")
    await close_client()


if __name__ == "__main__":
    asyncio.run(main())
