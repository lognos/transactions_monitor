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
- Seed data is created at the event. Only public, open-source data may be imported.
- Commit small and often (every 30–60 minutes). The repository is reviewed during the event.
- Never commit `.env` or any secret. Do not print secrets in logs or commit messages.

## Lanes and file ownership

| Lane | Owner | Paths |
| --- | --- | --- |
| DB | Facundo | `backend/scripts/setup_db.py`, `backend/app/db.py`, `backend/app/audit.py`, `backend/app/gate.py` |
| Agent | Ben | `backend/app/main.py`, `models.py`, `checks.py`, `memory.py`, `prompts.py`, `llm.py`, `backend/app/graphs/` |
| UI | buddybud24 | `frontend/` |
| Scenarios | Tixa | `backend/scripts/seed.py`, `docs/pitch.md` |

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
- LangGraph: `StateGraph` with `TypedDict` state, one function per node, no checkpointer, no `interrupt()`.
- Keep it small. No abstractions for things used once, no extra endpoints, no auth, no Docker, no CI.
- Prefer fixing seed data over adding code when a scenario misbehaves.

## Environment

Variables are read from `.env` (not committed):

| Variable | Purpose |
| --- | --- |
| `MONGODB_URI` | Atlas connection string |
| `DB_NAME` | `txn_validation` |
| LLM provider key | Whichever provider the team picks at kickoff |
| `LANGSMITH_TRACING`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT` | LangSmith tracing |

## Commands

Planned. Update this section as soon as the scaffolding exists.

| Task | Command |
| --- | --- |
| Create collections and indexes | `python backend/scripts/setup_db.py` |
| Reset and seed demo data | `python backend/scripts/seed.py` |
| Run the API | `uvicorn app.main:app --reload --port 8000` (from `backend/`) |
| Run the UI | `npm run dev` (from `frontend/`) |

## How to verify a change

There is no test suite. A change is verified by running the affected scenario from `docs/plan-scenarios.md` against a fresh seed and checking the expected result listed there. Say which scenario you ran and what happened. If you could not run it, say that.

## Out of scope

Pre-authorized debit checks, four-eyes approval, PII views, change streams, user accounts, deployment. Do not build these unless a human asks.
