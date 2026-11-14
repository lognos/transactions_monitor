# Agent branch handoff

Branch: `zach-agent`. Prepared against `origin/main` at `2dc3dc3` on November 14, 2026.

## What this branch contains

- Earlier local policy/context retrieval work is preserved in commit `bce6c90`, including the legacy local-demo evaluation path and 20 isolated tests.
- The documented `app.agent` review path implements questions, filtered citations, approve/reject, panel and chat overrides, reverts, policy gating, audited decisions, and feedback memory. Original check results remain unchanged. Hard-check overrides appear in precedents but cannot produce learned adjustments.
- Decision and override writes compare the original checks and review status; the audit writer rejects unmatched updates rather than recording a successful stale write.
- The frontend and supporting Agent/server code were brought over from main at `dcf4281` without merging branch history. The frontend defaults to the real API.
- The queue excludes raw imported records that lack canonical type/amount/status fields. Its display also guards incomplete records. No database records were migrated, deleted, or seeded.

## Merge coordination

Main advanced to `2dc3dc3` during this work and now contains an independently updated review implementation. Do not blindly choose this branch for all conflicts.

Reconcile `backend/app/agent/graphs/review.py`, `schemas.py`, `service.py`, `prompts.py`, `backend/app/db/gate.py`, and `backend/app/server/main.py`. Preserve main's latest branding changes in the frontend while retaining this branch's incomplete-row guard. Keep main's database setup and seed updates for the new override contract.

Main removed the legacy `app.main` / `app.graphs` / local-demo files, while this branch preserves earlier work there. Decide whether to retain them as a separate demo or port their policy/context behavior into `app.agent`; do not accidentally route the frontend to the old server. Those legacy tests exercise a separate path, not the production Agent implementation.

## Run the integrated application

From `backend/`:

```sh
.venv/bin/python -m uvicorn app.server.main:app --reload --port 8010
```

From `frontend/`:

```sh
NEXT_PUBLIC_API_SOURCE=backend npm run dev
```

The frontend proxies `/api` to port 8010 unless `API_URL` overrides it. `app.main:app` is the legacy demo and does not provide the queue or question endpoints. Environment credentials are not committed.

## Validation

- 13 isolated review/gate tests pass, including an HTTP flow through blocked approval, override, question, and approval with mocked DB/model dependencies.
- 20 earlier policy/context tests pass.
- Frontend lint, TypeScript, and fixture override scenarios pass. Production build passed after permitting Google Fonts downloads; lint and TypeScript were rerun after the small queue guard change.
- Live checks confirmed the integrated API routes, MongoDB health, reviewer loading, and transaction-list schema through the frontend proxy.
- At the last check, the live queue had 13 canonical transactions and zero pending records. Other collection entries were raw CSV imports, excluded from review until normalized.

Re-run after resolving the merge, from `backend/`:

```sh
LANGSMITH_TRACING=false LANGCHAIN_TRACING_V2=false .venv/bin/python -m unittest discover -s app/agent/tests -v
LANGSMITH_TRACING=false LANGCHAIN_TRACING_V2=false .venv/bin/python -m unittest discover -s tests -v
```

From `frontend/`:

```sh
npm run lint
npx tsc --noEmit
node scripts/verify-fixture-overrides.mjs
npm run build
```

## Remaining live verification

Use fresh normalized test transactions to exercise evaluation → questions → override/revert → approve/reject → audit verification against Atlas and the real model. Confirm a judgment adjustment changes a subsequent similar evaluation and is cited. Full live learning and audit replay were not verified. Check existing policy documents for the intended hard-override permission; changing code defaults does not migrate stored policies.

The imported simulator expects `backend/data/AuditFlow_All_Transactions_Consolidated.csv`, which was not present in this checkout. Restore the intended dataset or configure the ingestion path before testing simulation. Do not reset the shared database just to run the demo.
