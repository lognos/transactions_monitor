# Transaction Validation Agent

> **Agents in Context Toronto: A MongoDB Hackathon** (Nov 14, 2026)  
> **Track 1 — Agents You Can Audit:** *Build an agent using MongoDB Atlas as the identity, policy and audit layer, where every action is tied to an identity, checked against policy before it runs, and recorded so a reviewer can reconstruct it afterward.*

A LangGraph agent evaluates bank transactions against a regulatory checklist, recommends `pass` or `no_pass`, answers reviewer questions with policy/precedent citations, and learns from reviewer decisions. **MongoDB Atlas** (`txn_validation`) holds identities, versioned policies, the agent's memory (precedents & learned adjustments), and a hash-chained append-only audit log.

---

## Architecture

1. **Evaluate Graph (`backend/app/agent/graphs/evaluate.py`):** Loads transaction & customer profile, runs deterministic Python `hard` checks from `policies`, retrieves precedents & active adjustments via Atlas Vector Search (`memory`), and uses an LLM to evaluate `judgment` criteria and produce a rationale.
2. **Review Graph (`backend/app/agent/graphs/review.py`):** Handles reviewer Q&A (`AnswerQuestion`) and decisions (`PolicyGate` → `RecordDecision` → `LearnFromFeedback` / `StorePrecedent`).
3. **Deterministic Policy Gate (`backend/app/db/gate.py`):** Checks reviewer role, amount limits, and hard-fail overrides *before* any decision is recorded. Denials are audited.
4. **Tamper-Evident Audit Log (`backend/app/db/audit.py`):** Every write after seeding goes through `write_with_audit` in a multi-document transaction serialized via `chain_head`, computing `sha256(prev_hash + canonical_json(event))`.

---

## Quick Start

### 1. Environment
Copy `.env.example` to `.env` and set `MONGODB_CONNECTION_STRING` (or `MONGODB_URI`), `DB_NAME=txn_validation`, `GOOGLE_API_KEY`, and optionally `LANGSMITH_*` variables.

### 2. Backend (`backend/`)
```bash
cd backend
uv sync
uv run python -m scripts.ping_db
uv run python -m scripts.setup_db
uv run python -m scripts.seed
uv run uvicorn app.server.main:app --reload --port 8010
```

### 3. Frontend (`frontend/`)
```bash
cd frontend
npm install
npm run dev   # http://localhost:3000 (proxies /api -> localhost:8010)
```

---

## Documentation Map

| File | Purpose |
| --- | --- |
| [`AGENTS.md`](AGENTS.md) | Repo rules, invariants, lane ownership, and commands |
| [`docs/contracts.md`](docs/contracts.md) | **Source of truth** for collections, enums, HTTP API, Python interfaces, and LLM schemas |
| [`transaction-validation-design.md`](transaction-validation-design.md) | Workflow overview, auditable learning guardrails, checklists, and Canadian regulatory context |
| [`docs/plan-db.md`](docs/plan-db.md) | DB lane scope (`app/db/`, `setup_db.py`) |
| [`docs/plan-agent.md`](docs/plan-agent.md) | Agent lane scope (`app/agent/` LangGraph graphs, checks, memory, prompts) |
| [`docs/plan-ui.md`](docs/plan-ui.md) | UI & server lane scope (`frontend/`, `app/server/`) |
| [`docs/plan-scenarios.md`](docs/plan-scenarios.md) | Demo scenarios, seed data spec, and 3-minute pitch outline |
| [`docs/fintrac_policy_update_checker.md`](docs/fintrac_policy_update_checker.md) | FINTRAC policy update checker & vector DB ingestion loop (`scripts/`) |

---

## Hackathon Constraints
- **Track:** Problem 1 — *Agents You Can Audit* (all code & seed data written during the event; public repo; MongoDB Atlas Sandbox).
- **No Streamlit / no passive dashboards:** Built with FastAPI + Next.js 16 (App Router) + Tailwind CSS 4.
- **Submissions due:** 5:00 PM EST (with 1-minute demo video). Judging: 3-min live demo + Q&A (Technical Demo 35%, Implementation Difficulty 30%, Impact 20%, Creativity 15%).
