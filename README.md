# AuditFlow AI

> **Agents in Context Toronto: A MongoDB Hackathon** (Nov 14, 2026)  
> **Track 1 — Agents You Can Audit:** *Build an agent using MongoDB Atlas as the identity, policy and audit layer, where every action is tied to an identity, checked against policy before it runs, and recorded so a reviewer can reconstruct it afterward.*

An auditable agent for bank transaction review. A LangGraph agent pre-screens a reviewer's queue across six Canadian payment types (wire, cheque, Interac e-Transfer, EFT, PAD, bill payment), recommends `pass` or `no_pass` per check, answers questions with citations to policy and past decisions, and learns from reviewer overrides. **MongoDB Atlas** (`txn_validation`) is the identity, policy, memory and audit layer.

**The agent proposes; Atlas decides and remembers.**

---

## How it works

1. **Evaluate.** The agent loads a transaction and the customer profile, runs the policy's `hard` checks as deterministic Python, retrieves precedents and learned adjustments with Atlas Vector Search, and asks the LLM to judge only the `judgment` criteria. The overall recommendation is computed in code.
2. **Review.** On a split screen (chat on the left, transaction queue on the right), the reviewer opens a transaction's checklist and clicks any result to see the policy, regulation and past decisions behind it.
3. **Override.** The reviewer can override any single check, from the checklist or by asking in chat, with a mandatory reason. The agent's original result is never overwritten; the check shows an "Analyst override" or "Supervisor override" tag beside it.
4. **Decide.** **Approve** is only possible once no check is still failing. **Reject** needs a comment only when the recommendation was a pass.
5. **Learn.** At the decision, each override of a judgment check becomes a learned adjustment on that exact check. The next similar transaction is evaluated with it and cites who taught it. Overrides of hard checks are recorded but never become adjustments.
6. **Audit.** Every action is in a hash-chained log. "Verify chain" recomputes it and points to the first tampered event.

### What Atlas does

| Layer | How |
| --- | --- |
| Identity | Every request names its principal (`X-Principal-Id`). Every audit event records who acted, in what role, and on whose behalf the agent ran |
| Policy | Versioned checklists and approval limits stored as data in `policies`. A deterministic gate checks role and amount limit before any decision or override; denials are audited |
| Memory | Precedents and learned adjustments in `memory`, retrieved with Atlas Vector Search (automated Voyage embeddings) |
| Audit | `write_with_audit` commits each write and its SHA-256 hash-chained event in one multi-document transaction, serialized through `chain_head`. A `$jsonSchema` validator guards `audit_log` |

### Safety rules in the code

- Hard checks are deterministic; the LLM never decides them or the overall recommendation.
- The LLM never writes to the database. In chat it only extracts an override request; code applies it through the same gate.
- Transaction memos and counterparty fields are treated as untrusted data.
- If the model is unavailable, the evaluation fails and the transaction stays pending. An outage is never stored as a judgment.
- Each transaction has exactly one live evaluation.

### Code map

| Path | What |
| --- | --- |
| `backend/app/agent/graphs/evaluate.py` | Evaluate graph: load, run checks, retrieve context, recommend, save |
| `backend/app/agent/graphs/review.py` | Review graph: answer question, apply override, policy gate, record decision or denial, learn from feedback, store precedent |
| `backend/app/agent/checks.py` | Deterministic checks and default policies for the six payment types |
| `backend/app/db/gate.py` | Policy gate for decisions and overrides |
| `backend/app/db/audit.py` | Hash-chained audit writes and chain verification |
| `backend/app/server/` | FastAPI routes (contract in `docs/contracts.md` §4 and §8) |
| `frontend/` | Next.js 16 app: chat, transaction queue, checklist, references, audit timeline |

---

## Quick start

### 1. Environment
Copy `.env.example` to `.env` at the repo root and set:

| Variable | Purpose |
| --- | --- |
| `MONGODB_CONNECTION_STRING` (or `MONGODB_URI`) | Atlas connection string |
| `DB_NAME` | `txn_validation` |
| `GOOGLE_API_KEY` (or `OPENAI_API_KEY`) | LLM provider key |
| `LLM_MODEL` | `<provider>:<model>`, for example `google_genai:gemini-2.5-flash` |
| `QUEUE_LIMIT` | Open transactions shown in the queue and pre-evaluated by the agent (default 8) |
| `LOGFIRE_WRITE_TOKEN` | Optional server telemetry |
| `LANGSMITH_*` | Optional LangGraph tracing |

### 2. Backend (`backend/`)
```bash
cd backend
uv sync
uv run python -m scripts.ping_db     # check the connection
uv run python -m scripts.setup_db    # collections, indexes, validator, vector index (safe to re-run)
uv run python -m scripts.seed        # WARNING: resets every collection, including audit_log and memory
uv run uvicorn app.server.main:app --reload --port 8010
```

### 3. Frontend (`frontend/`)
```bash
cd frontend
npm install
npm run dev   # http://localhost:3000, forwards /api to localhost:8010
```

From the repo root, `make backend` and `make frontend` run the two servers.

### 4. Tests
```bash
cd backend
uv run python -m unittest app.agent.tests.test_review app.agent.tests.test_review_audit
```

---

## Demo

- [`SUBMISSION.md`](SUBMISSION.md): 60-second demo shot list with voiceover, and the project description.
- Screen recordings: [`flow.mp4`](flow.mp4), [`flow2.mp4`](flow2.mp4).
- The five scenarios are in [`docs/plan-scenarios.md`](docs/plan-scenarios.md): clean pass, hard fail with a prompt-injection memo, the agent learns from an override, the amount limit, and audit replay with tamper detection.

---

## Documentation map

| File | Purpose |
| --- | --- |
| [`AGENTS.md`](AGENTS.md) | Repo rules, invariants, lane ownership, and commands |
| [`docs/contracts.md`](docs/contracts.md) | **Source of truth** for collections, enums, HTTP API, Python interfaces, and LLM schemas. §8 covers overrides and Approve / Reject |
| [`transaction-validation-design.md`](transaction-validation-design.md) | Workflow overview, auditable learning guardrails, checklists, and Canadian regulatory context |
| [`docs/plan-db.md`](docs/plan-db.md) | DB lane scope (`app/db/`, `setup_db.py`) |
| [`docs/plan-agent.md`](docs/plan-agent.md) | Agent lane scope (`app/agent/` LangGraph graphs, checks, memory, prompts) |
| [`docs/plan-ui.md`](docs/plan-ui.md) | UI and server lane scope (`frontend/`, `app/server/`) |
| [`docs/plan-scenarios.md`](docs/plan-scenarios.md) | Demo scenarios, seed data spec, and pitch outline |
| [`docs/fintrac_policy_update_checker.md`](docs/fintrac_policy_update_checker.md) | FINTRAC policy update checker and ingestion loop (`scripts/`) |

---

## Team

Facundo, Ben, Zach, Tixa.

## Hackathon constraints
- **Track:** Problem 1 — *Agents You Can Audit* (all code and seed data written during the event; public repo; MongoDB Atlas Sandbox).
- **No Streamlit / no passive dashboards:** built with FastAPI, Next.js 16 (App Router) and Tailwind CSS 4.
- **Submissions due:** 5:00 PM EST (with 1-minute demo video). Judging: 3-min live demo + Q&A (Technical Demo 35%, Implementation Difficulty 30%, Impact 20%, Creativity 15%).
