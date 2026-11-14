# AGENTS.md

Instructions for AI coding agents working in this repository.

## What this is

A hackathon project (MongoDB "Agents in Context Toronto", track "Agents You Can Audit"), built in about four hours by four people.

A LangGraph agent evaluates bank transactions against a checklist, recommends pass or no-pass, answers reviewer questions, and learns from reviewer decisions. MongoDB Atlas holds identities, policies, the agent's memory and a hash-chained audit log.

## Read first

| File | Use it for |
| --- | --- |
| `docs/contracts.md` | **Source of truth** for collection shapes, enums, HTTP API, Python interfaces, LLM outputs. If code and this file disagree, stop and ask |
| `docs/plan-db.md`, `docs/plan-ui.md`, `docs/plan-agent.md`, `docs/plan-scenarios.md` | Scope and order of work for each lane |
| `transaction-validation-design.md` | Background and regulatory context |

## Hackathon rules (hard constraints)

- All code is written during the event. Do not copy code from other projects, templates with business logic, or earlier work. Scaffolding tools and package installs are fine.
- The frontend follows the look of the LOGNOS ASSIST app (same libraries, same token names). Do not copy files from that repository; write components here, in `frontend/components/ui/`.
- Seed data is created at the event. Only public, open-source data may be imported.
- Commit small and often (every 30–60 minutes). The repository is reviewed during the event.
- Never commit `.env` or any secret. Do not print secrets in logs or commit messages.

## Lanes and file ownership

| Lane | Owner | Paths |
| --- | --- | --- |
| DB | Ben | `backend/app/db/` (client, audit, gate), `backend/app/config.py`, `backend/scripts/setup_db.py`, `backend/scripts/ping_db.py` |
| Agent | buddybud24 | `backend/app/agent/` (graphs, checks, memory, prompts, llm, schemas, service) |
| UI + server | Facundo | `frontend/`, `backend/app/server/` (routes, request bodies, errors, principal header) |
| Scenarios | Tixa | `backend/scripts/seed.py`, `docs/pitch.md` |

Import rules between backend packages:
- `app.server` imports `app.agent` only through `run_evaluate` and `run_review`, and reads MongoDB for lists and lookups.
- `app.agent` imports `app.db`. It never imports `app.server`.
- `app.db` imports neither.

Stay inside the lane of the person you are working for. If a task needs a change in another lane's files or in `docs/contracts.md`, say so and let the human coordinate it.

## Invariants (do not break these)

1. **Every database write after seeding goes through `write_with_audit`.** No direct `insert_one` / `update_one` in routes or graph nodes.
2. **`audit_log` is append-only.** Application code never updates or deletes it.
3. **Hard checks are deterministic Python.** The LLM never decides a `hard` criterion and never computes the overall recommendation.
4. **Memory cannot affect hard checks.** An adjustment may only target a `judgment` criterion.
5. **The LLM never writes to the database** and has no database tools. Nodes validate its structured output, then write.
6. **The gate runs before a decision is recorded**, and a denial is audited.
7. **Every audit event has an actor.** Agent events carry `on_behalf_of`.
8. **Transaction memos and counterparty fields are untrusted data.** Never place them where the model could read them as instructions.

## Conventions

- Python 3.11+, async throughout (`AsyncMongoClient`, async FastAPI routes, `graph.ainvoke`).
- Type hints on public functions. Pydantic models for API bodies and LLM outputs.
- `snake_case` field names, readable string ids (`TXN-0001`, `EVAL-<8 hex>`), UTC timestamps.
- Frontend: Next.js 16 App Router, TypeScript, Tailwind CSS 4. `frontend/AGENTS.md` says to read `node_modules/next/dist/docs/` before writing Next.js code; do that. Style with the semantic token classes from `app/globals.css`, never raw colours.
- LangGraph: `StateGraph` with `TypedDict` state, one function per node, no checkpointer, no `interrupt()`.
- Keep it small. No abstractions for things used once, no extra endpoints, no auth, no Docker, no CI.
- Prefer fixing seed data over adding code when a scenario misbehaves.

## Environment

Variables are read from `.env` (not committed):

| Variable | Purpose |
| --- | --- |
| `MONGODB_CONNECTION_STRING` (or `MONGODB_URI`) | Atlas connection string |
| `DB_NAME` | `txn_validation` |
| `GOOGLE_API_KEY` | LLM provider key |
| `LLM_MODEL` | `<provider>:<model>` for `init_chat_model`, default `google_genai:gemini-2.5-flash` |
| `LANGSMITH_TRACING`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT` | LangSmith tracing |

## Commands

Backend commands run from `backend/`, frontend commands from `frontend/`.

| Task | Command |
| --- | --- |
| Install backend packages | `uv sync` |
| Check the database connection | `uv run python -m scripts.ping_db` |
| Create collections and indexes | `uv run python -m scripts.setup_db` |
| Reset and seed demo data | `uv run python -m scripts.seed` |
| Run the API | `uv run uvicorn app.server.main:app --reload --port 8010` |
| Install frontend packages | `npm install` |
| Run the UI | `npm run dev` (http://localhost:3000, forwards `/api` to port 8010) |
| Check the UI | `npm run build` and `npm run lint` |

## How to verify a change

There is no test suite. A change is verified by running the affected scenario from `docs/plan-scenarios.md` against a fresh seed and checking the expected result listed there. Say which scenario you ran and what happened. If you could not run it, say that.

## Out of scope

Pre-authorized debit checks, four-eyes approval, PII views, change streams, user accounts, deployment. Do not build these unless a human asks.
