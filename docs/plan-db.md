# Plan 1 — DB

Owner: Facundo. Shapes and names come from [contracts.md](contracts.md).

## Goal

MongoDB Atlas is the identity, policy and audit layer. This lane delivers the database, plus the three small Python modules everything else writes through.

Done when a seeded transaction can be saved together with an audit event, and `verify_chain` passes, then fails after one record is edited by hand.

## Deliverables

| File | What it does |
| --- | --- |
| `backend/scripts/setup_db.py` | Creates the nine collections, indexes, the `audit_log` validator, the vector index. Safe to re-run |
| `backend/app/db.py` | One `AsyncMongoClient`, collection handles, session helper |
| `backend/app/audit.py` | `write_with_audit`, `verify_chain` (contracts §5.1) |
| `backend/app/gate.py` | `check_gate` (contracts §5.2) |

Seeding (`seed.py`) belongs to the Scenarios lane and runs after `setup_db.py`.

## Atlas setup

1. Free cluster, database `txn_validation`. Add everyone's IP or allow all for the day.
2. One database user for the app. Put `MONGODB_URI` and `DB_NAME` in a shared `.env` that is never committed.
3. Confirm in the first 20 minutes:
   - multi-document transactions work on the cluster
   - Vector Search with Automated Embedding is available on the tier, and the exact index and query syntax

## How the audit write works

`write_with_audit` runs one transaction:
1. Read `chain_head` and increment `seq`. This update makes concurrent writers conflict and retry, so the chain stays linear.
2. Build the audit event with `prev_hash = chain_head.hash`, compute `hash`.
3. Apply the caller's `writes` (inserts and updates on other collections).
4. Insert the audit event, update `chain_head` with the new `seq` and `hash`.
5. Commit. On a transient conflict, retry the whole transaction.

`verify_chain` reads `audit_log` in `seq` order, recomputes each hash, and reports the first `seq` where `prev_hash` or `hash` doesn't match.

## Gate

`check_gate` loads the active policy for the transaction type and applies the three deny rules in contracts §5.2. It is pure apart from that read, so it is easy to test with four cases:

| Case | Expected |
| --- | --- |
| Ana (limit 50,000) validates a 4,000 wire | allow, `D-01` |
| Ana validates a 60,000 wire | deny, amount over limit |
| Ana validates an evaluation with a hard `no_pass` | deny, hard check failed |
| Auditor tries to decide anything | deny, no rule for role |

## Steps

| When | Step | Check |
| --- | --- | --- |
| 0:00–0:20 | Cluster, user, `.env`, confirm transactions and vector search availability | A script connects and pings |
| 0:20–0:45 | `setup_db.py`: collections, unique indexes, `audit_log` validator, `chain_head` genesis document | Re-running it changes nothing |
| 0:45–1:15 | `audit.py`: `write_with_audit` and `verify_chain` | Ten events written, verify passes |
| 1:15–1:30 | Hand `write_with_audit` to the Agent lane, replacing its stub | **Checkpoint 1:** an evaluation appears in `audit_log` |
| 1:30–1:50 | `gate.py` and its four cases | All four pass |
| 1:50–2:15 | Vector index on `memory.text`, `search_memory` working with the Agent lane | A query returns seeded precedents filtered by `txn_type` |
| 2:15–2:30 | Tamper test: edit one `audit_log` record in Atlas, run verify | **Checkpoint 2:** verify reports the right `seq` |
| 2:30–3:15 | Aggregation for the per-transaction timeline if `GET /audit` needs more than a `find`. Help wherever the demo is weakest | Scenario 5 runs |

## Atlas features to point at in the demo

- Multi-document transaction: decision, status change and audit event commit together.
- `$jsonSchema` validator on `audit_log`: a malformed event is rejected by the database.
- Vector Search with Automated Embedding on `memory`.
- Unique index on `decisions.eval_id`: a second decision on the same evaluation is impossible.

## Risks

| Risk | Mitigation |
| --- | --- |
| Automated Embedding not available on the tier | Create embeddings in code with an embedding API and a standard vector index, or fall back to the non-vector paths in the Agent plan |
| Transaction retry logic eats time | Use the driver's `with_transaction` helper, which already retries transient errors |
| Two people run `setup_db.py` or seed at once | One person owns running them; scripts are idempotent |

## Stretch

- A read-only database user for the auditor view.
- Change stream on `audit_log` for a live feed in the UI.
