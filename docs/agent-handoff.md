# Agent branch handoff

Branch: `zach-agent`. Reconciled with `origin/main` at `2dc3dc3` on November 14, 2026.

## What this branch contains

- Earlier local policy/context retrieval work is preserved in commit `bce6c90`, including the legacy local-demo evaluation path and 20 isolated tests.
- The documented `app.agent` review path implements questions, filtered citations, approve/reject, panel and chat overrides, reverts, policy gating, audited decisions, and feedback memory. Original check results remain unchanged. Hard-check overrides appear in precedents but cannot produce learned adjustments.
- Decision and override writes compare the original checks and review status; the audit writer rejects unmatched updates rather than recording a successful stale write.
- Main through `2dc3dc3` is merged into this branch. The frontend defaults to the real API and retains main's latest branding.
- The queue excludes raw imported records that lack canonical type/amount/status fields. Its display also guards incomplete records. No database records were migrated, deleted, or seeded.

## Merge coordination

The merge conflicts with main have been resolved. The result combines main's customer context, effective-result initialization, model factory, branding, data, seed and database setup with this branch's isolated chat intent extraction, reason-required no-write behavior, criterion-fixed learning, refresh protection and conditional audited writes.

The gate uses the evaluation's policy version. Refresh skips overridden evaluations inside the graph and only supersedes an existing evaluation, comparing its prior checks to protect against concurrent overrides. Reverting a check without an override is a no-op.

Earlier `app.main` / `app.graphs` / local-demo code is retained as a separate legacy path. The frontend must use `app.server.main:app`. Legacy policy tests exercise that separate path, not the production Agent implementation.

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

- 22 isolated review/evaluation/audit tests pass, including an HTTP flow through blocked approval, override, question, and approval with mocked DB/model dependencies.
- 20 earlier policy/context tests pass.
- Frontend lint, TypeScript, and fixture override scenarios pass. Production build, lint, TypeScript, and fixture scenarios were checked after reconciling main. The build requires Google Fonts downloads.
- Live checks confirmed the integrated API routes, MongoDB health, reviewer loading, and transaction-list schema through the frontend proxy.
- At the last check, the live queue had 13 canonical transactions and zero pending records. Other collection entries were raw CSV imports, excluded from review until normalized.

Re-run from `backend/`:

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

Main now supplies the simulator dataset at `data/AuditFlow_All_Transactions_Consolidated.csv` in the repository root. The simulator resolves that path, but its live ingestion flow remains unverified. Do not reset the shared database just to run the demo.

## Follow-up alignment with Zach's override requirements

- A missing chat override reason now returns `needs_reason` without writing a thread entry, audit event, or override.
- Chat action extraction uses a separate model call containing only the current reviewer message and valid check IDs. The context-rich answer call cannot authorize writes. Ordinary questions therefore use two model calls.
- Each judgment override uses an `OverrideGuidance` schema containing only condition and text; code fixes the criterion from the override. Hard overrides are excluded from the learning payload. Model failures still skip that adjustment and preserve the recorded decision.
- Refresh protection also exists in the evaluation graph, so direct `run_evaluate(refresh=True)` calls preserve active overrides, not just HTTP requests.
- Tests cover these cases, multiple judgment adjustments, no model call for panel overrides, and ignoring an action returned by the context-rich answer call.
