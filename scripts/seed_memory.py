"""
scripts/seed_memory.py
Seeds expected precedent cases and regulatory policy knowledge into the
MongoDB Atlas 'memory' collection, adhering strictly to docs/contracts.md §3.7
and docs/plan-scenarios.md §Seed data.
"""

import os
import sys
from pymongo import MongoClient

# Add root directory to python path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from backend.app.db import get_sync_db

SEED_DATA = [
    # --- 1. WIRES PASSED (Routine amounts, known beneficiaries) ---
    {
        "memory_id": "MEM-WIRE-01",
        "kind": "precedent",
        "txn_type": "wire",
        "text": "Wire transfer of CAD 3,500 to Medisupply Inc for routine dental supplies. Known beneficiary, address complete, passed all checks and validated by ana.",
        "scope": None,
        "source_decision_id": None,
        "source_txn_id": None,
        "author_id": "seed",
        "active": True,
        "created_at": "2026-11-14T10:00:00Z"
    },
    {
        "memory_id": "MEM-WIRE-02",
        "kind": "precedent",
        "txn_type": "wire",
        "text": "Wire transfer of CAD 4,000 to Apex Equipment Ltd for monthly maintenance. Known beneficiary with 2-year history, domestic routing, validated by ana.",
        "scope": None,
        "source_decision_id": None,
        "source_txn_id": None,
        "author_id": "seed",
        "active": True,
        "created_at": "2026-11-14T10:05:00Z"
    },
    {
        "memory_id": "MEM-WIRE-03",
        "kind": "precedent",
        "txn_type": "wire",
        "text": "Wire transfer of CAD 2,800 to Ontario Power Distribution. Routine utility settlement, within normal monthly operating band, validated by sam.",
        "scope": None,
        "source_decision_id": None,
        "source_txn_id": None,
        "author_id": "seed",
        "active": True,
        "created_at": "2026-11-14T10:10:00Z"
    },

    # --- 2. WIRES REJECTED (Missing beneficiary / Travel Rule violation) ---
    {
        "memory_id": "MEM-WIRE-04",
        "kind": "precedent",
        "txn_type": "wire",
        "text": "Wire transfer of CAD 12,000 to Northwind Trading rejected by ana. Beneficiary street address missing under FINTRAC Travel Rule (W-01); memo urged skipping checks.",
        "scope": None,
        "source_decision_id": None,
        "source_txn_id": "TXN-0002",
        "author_id": "seed",
        "active": True,
        "created_at": "2026-11-14T10:15:00Z"
    },
    {
        "memory_id": "MEM-WIRE-05",
        "kind": "precedent",
        "txn_type": "wire",
        "text": "Wire transfer of CAD 15,500 rejected by sam. Incomplete originator account details violating Travel Rule requirements for cross-border electronic funds transfers.",
        "scope": None,
        "source_decision_id": None,
        "source_txn_id": None,
        "author_id": "seed",
        "active": True,
        "created_at": "2026-11-14T10:20:00Z"
    },

    # --- 3. WIRES REJECTED (New beneficiary, amount far above typical) ---
    {
        "memory_id": "MEM-WIRE-06",
        "kind": "precedent",
        "txn_type": "wire",
        "text": "Wire transfer of CAD 45,000 to new overseas supplier rejected by sam. Amount was 15x customer typical volume with no prior business relationship (failed C-04).",
        "scope": None,
        "source_decision_id": None,
        "source_txn_id": None,
        "author_id": "seed",
        "active": True,
        "created_at": "2026-11-14T10:25:00Z"
    },
    {
        "memory_id": "MEM-WIRE-07",
        "kind": "precedent",
        "txn_type": "wire",
        "text": "Wire transfer of CAD 38,000 to unverified offshore entity rejected by ana. Failed customer profile consistency (C-04) and triggered AML suspicious transfer indicators.",
        "scope": None,
        "source_decision_id": None,
        "source_txn_id": None,
        "author_id": "seed",
        "active": True,
        "created_at": "2026-11-14T10:30:00Z"
    },

    # --- 4. CHEQUES REJECTED (Amount far above typical for non-payroll customer) ---
    {
        "memory_id": "MEM-CHQ-01",
        "kind": "precedent",
        "txn_type": "cheque",
        "text": "Cheque of CAD 8,500 rejected for non-payroll retail customer by ana. Amount was 4x typical weekly volume with no seasonal justification (failed C-04).",
        "scope": None,
        "source_decision_id": None,
        "source_txn_id": None,
        "author_id": "seed",
        "active": True,
        "created_at": "2026-11-14T10:35:00Z"
    },
    {
        "memory_id": "MEM-CHQ-02",
        "kind": "precedent",
        "txn_type": "cheque",
        "text": "Cheque of CAD 11,200 rejected for dental clinic customer by sam. Irregular surge with unknown payee, failed profile consistency check (C-04).",
        "scope": None,
        "source_decision_id": None,
        "source_txn_id": None,
        "author_id": "seed",
        "active": True,
        "created_at": "2026-11-14T10:40:00Z"
    },

    # --- 5. CHEQUE PASSED (Routine amount) ---
    {
        "memory_id": "MEM-CHQ-03",
        "kind": "precedent",
        "txn_type": "cheque",
        "text": "Cheque of CAD 2,400 for standard vendor payment passed and validated by ana. Routine amount, valid cheque date, within normal operating band.",
        "scope": None,
        "source_decision_id": None,
        "source_txn_id": None,
        "author_id": "seed",
        "active": True,
        "created_at": "2026-11-14T10:45:00Z"
    },

    # --- 6. INTERAC E-TRANSFERS (Routine pass & Fraud rejection) ---
    {
        "memory_id": "MEM-INT-01",
        "kind": "precedent",
        "txn_type": "interac",
        "text": "Interac e-Transfer of CAD 1,200 passed and validated by ana. Autodeposit enabled, known recipient, routine business expense within daily limit.",
        "scope": None,
        "source_decision_id": None,
        "source_txn_id": None,
        "author_id": "seed",
        "active": True,
        "created_at": "2026-11-14T10:50:00Z"
    },
    {
        "memory_id": "MEM-INT-02",
        "kind": "precedent",
        "txn_type": "interac",
        "text": "Interac e-Transfer of CAD 4,800 rejected by sam. Rapid velocity burst to newly registered recipient email, triggered account takeover (ATO) fraud indicator.",
        "scope": None,
        "source_decision_id": None,
        "source_txn_id": None,
        "author_id": "seed",
        "active": True,
        "created_at": "2026-11-14T10:55:00Z"
    },

    # --- 7. CANADIAN REGULATORY POLICIES IN MEMORY ---
    {
        "memory_id": "MEM-POL-01",
        "kind": "precedent",
        "txn_type": "wire",
        "text": "FINTRAC Travel Rule Regulation (W-01): International electronic funds transfers must carry full originator name, street address, and account number. Missing address requires mandatory no_pass.",
        "scope": None,
        "source_decision_id": None,
        "source_txn_id": None,
        "author_id": "seed",
        "active": True,
        "created_at": "2026-11-14T11:00:00Z"
    },
    {
        "memory_id": "MEM-POL-02",
        "kind": "precedent",
        "txn_type": "wire",
        "text": "Canadian Sanctions Law (C-01): SEMA and OSFI consolidated sanctions lists enforce zero dealing with designated Russian, Iranian, or DPRK entities. Triggers immediate hard stop.",
        "scope": None,
        "source_decision_id": None,
        "source_txn_id": None,
        "author_id": "seed",
        "active": True,
        "created_at": "2026-11-14T11:05:00Z"
    },
    {
        "memory_id": "MEM-POL-03",
        "kind": "precedent",
        "txn_type": "cheque",
        "text": "Payments Canada Rule A4 (C-03): Duplicate cheque presentments with matching image hash or serial number are returned within 30 business days recourse window.",
        "scope": None,
        "source_decision_id": None,
        "source_txn_id": None,
        "author_id": "seed",
        "active": True,
        "created_at": "2026-11-14T11:10:00Z"
    },
    {
        "memory_id": "MEM-POL-04",
        "kind": "precedent",
        "txn_type": "cheque",
        "text": "Payments Canada Rule A1 (Q-01): Cheques dated more than 6 months (180 days) prior are stale-dated and ineligible for clearing. Post-dated cheques cannot be cleared prior to date.",
        "scope": None,
        "source_decision_id": None,
        "source_txn_id": None,
        "author_id": "seed",
        "active": True,
        "created_at": "2026-11-14T11:15:00Z"
    },
    {
        "memory_id": "MEM-POL-05",
        "kind": "precedent",
        "txn_type": "interac",
        "text": "Interac Operating Rules: Retail e-Transfers capped at $3,000 / $5,000 CAD per 24 hours. Autodeposited transactions are final and non-cancellable by the sender.",
        "scope": None,
        "source_decision_id": None,
        "source_txn_id": None,
        "author_id": "seed",
        "active": True,
        "created_at": "2026-11-14T11:20:00Z"
    },

    # --- 8. SAMPLE REVIEWER ADJUSTMENT (Learned from Ana) ---
    {
        "memory_id": "MEM-ADJ-01",
        "kind": "adjustment",
        "txn_type": "cheque",
        "text": "For payroll customers, cheque amounts several times the typical amount at month-end are expected. Do not fail C-04 for that reason alone.",
        "scope": {
            "criterion_id": "C-04",
            "condition": "customer segment is payroll and date is within 3 days of month-end"
        },
        "source_decision_id": "DEC-9c0d1e2f",
        "source_txn_id": "TXN-0003",
        "author_id": "ana",
        "active": True,
        "created_at": "2026-11-14T11:25:00Z"
    }
]

def seed_memory():
    db = get_sync_db()
    print(f"[*] Seeding {len(SEED_DATA)} memory records into 'txn_validation.memory' in MongoDB Atlas...")

    # Ensure unique index on memory_id
    db.memory.create_index("memory_id", unique=True)
    db.memory.create_index([("txn_type", 1), ("kind", 1), ("active", 1)])

    inserted = 0
    updated = 0
    for doc in SEED_DATA:
        res = db.memory.replace_one({"memory_id": doc["memory_id"]}, doc, upsert=True)
        if res.upserted_id:
            inserted += 1
        else:
            updated += 1

    print(f"[+] Seeding complete: {inserted} inserted, {updated} updated.")
    print(f"[+] Total documents in 'memory' collection: {db.memory.count_documents({})}")

if __name__ == "__main__":
    seed_memory()
