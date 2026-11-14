"""
scripts/demo_vector_query.py
Demonstrates the live MongoDB Atlas Vector Search connection, executing
sample queries against the 'memory' collection per docs/contracts.md §3.7 & §5.4.
"""

import os
import sys
import asyncio

# Add root directory to python path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from backend.app.db import get_sync_db
from backend.app.memory import search_memory, active_adjustments

async def run_demo():
    print("=" * 80)
    print("FOUR-EYES / AUDITFLOW AI: MONGODB ATLAS VECTOR SEARCH DEMONSTRATION")
    print("=" * 80)

    sync_db = get_sync_db()
    
    # 1. Verify Vector Search Index Status on Atlas
    indexes = list(sync_db.memory.list_search_indexes())
    print("\n[+] Atlas Search Indexes on 'txn_validation.memory':")
    for idx in indexes:
        print(f"    - Name: {idx.get('name')}")
        print(f"      Status: {idx.get('status')}")
        print(f"      Queryable: {idx.get('queryable')}")
        print(f"      Type: {idx.get('type')}")

    # 2. Query 1: Scenario 2 - Wire Missing Address (Travel Rule W-01)
    query_1 = "Beneficiary street address missing for international wire transfer"
    print("\n" + "-" * 80)
    print(f"DEMO QUERY 1 (Wire / Travel Rule W-01): '{query_1}'")
    print("-" * 80)
    results_1 = await search_memory(query=query_1, txn_type="wire", kind="precedent", k=3)
    for i, doc in enumerate(results_1, 1):
        print(f"  [{i}] ID: {doc.get('memory_id')} | Score: {doc.get('score', 0):.4f} | Author: {doc.get('author_id')}")
        print(f"      Text: {doc.get('text')}\n")

    # 3. Query 2: Scenario 3 - Cheque Month-End Surge (Profile Check C-04 & Adjustments)
    query_2 = "Cheque amount is much higher than usual volume for customer"
    print("-" * 80)
    print(f"DEMO QUERY 2 (Cheque Profile C-04 & Precedents): '{query_2}'")
    print("-" * 80)
    results_2 = await search_memory(query=query_2, txn_type="cheque", kind="precedent", k=3)
    for i, doc in enumerate(results_2, 1):
        print(f"  [{i}] ID: {doc.get('memory_id')} | Score: {doc.get('score', 0):.4f} | Author: {doc.get('author_id')}")
        print(f"      Text: {doc.get('text')}\n")

    # 4. Query 3: Active Adjustments (Contracts §5.4 Plain Find)
    print("-" * 80)
    print("DEMO 3: Active Adjustments (Learned from Reviewer Feedback - contracts §5.4):")
    print("-" * 80)
    adjustments = await active_adjustments(txn_type="cheque")
    for i, adj in enumerate(adjustments, 1):
        print(f"  [{i}] ID: {adj.get('memory_id')} | Criterion: {adj.get('scope', {}).get('criterion_id')} | Author: {adj.get('author_id')}")
        print(f"      Condition: {adj.get('scope', {}).get('condition')}")
        print(f"      Guidance: {adj.get('text')}\n")

    # 5. Query 4: Interac e-Transfer Fraud & Velocity
    query_4 = "Interac e-Transfer to new recipient email sudden large amount"
    print("-" * 80)
    print(f"DEMO QUERY 4 (Interac e-Transfer Fraud & Velocity): '{query_4}'")
    print("-" * 80)
    results_4 = await search_memory(query=query_4, txn_type="interac", kind="precedent", k=2)
    for i, doc in enumerate(results_4, 1):
        print(f"  [{i}] ID: {doc.get('memory_id')} | Score: {doc.get('score', 0):.4f} | Author: {doc.get('author_id')}")
        print(f"      Text: {doc.get('text')}\n")

    print("=" * 80)
    print("[✓] Vector Search & MongoDB Atlas connection successfully demonstrated!")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(run_demo())
