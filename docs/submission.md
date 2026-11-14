# Hackathon Submission Draft

## Project Title
**AUDITFLOW AI — Policy-Governed Banking Payment Exception Agent**

---

## Project Description
Banks and payment operations teams face a strict compliance dilemma when deploying AI agents: they cannot deploy an agent that learns from human reviewers unless they can prove **who taught it what, when, and under which policy**—especially with Canadian regulatory expectations like **OSFI Guideline E-23** (Model Risk Management for AI) and **FINTRAC** (PCMLTFA travel rule and EFTR reporting) tightening governance requirements.

**AuditFlow AI** is a policy-governed, auditable banking transaction validation and payment exception agent built with **LangGraph**, **LangChain**, **FastAPI**, **Next.js**, and **MongoDB Atlas**.

### What it does
- **Deterministic Hard Checks + LLM Judgment Separation**: Evaluates banking transactions (`wire`, `cheque`, `eft`, `interac`, `pad`, `bill_payment`) against versioned policy checklists. Statutory and deterministic rules (sanctions screening, duplicate detection, FINTRAC travel-rule fields, $10,000 EFTR reporting flags, cheque date validity, Interac limits, account standing) execute in deterministic Python (`CHECKS`) and can never be overridden by the LLM or prompt-injected transaction memos. Only `judgment` criteria (such as customer amount profile consistency and new-beneficiary rationale) are evaluated by the LLM with structured outputs (`RecommendOutput`).
- **Human-in-the-Loop Policy Gate**: Every reviewer decision (`validated`, `validated_with_comments`, `rejected`) passes through a deterministic policy gate (`check_gate`) before any write occurs—enforcing role-based approval limits (e.g., analyst CAD 50,000 limit vs. supervisor unlimited) and blocking overrides on hard check failures. Denied attempts are still recorded as `decision.denied` audit events.
- **Governed Memory & Continuous Learning**: Reviewer comments can generate scoped `adjustment` memories (restricted strictly in code to `judgment` criteria, never `hard` rules) alongside templated `precedent` memories, each attributed to its author and source decision. Re-evaluating pending/undecided transactions immediately applies new adjustments with full citation provenance ("Learned from Ana").
- **Cryptographic Hash-Chained Audit Trail**: Every evaluation, Q&A turn, gate denial, decision, and memory creation is written atomically inside a MongoDB transaction alongside a SHA-256 hash-chained `audit_log` entry (`chain_head`), verifiable end-to-end via `GET /audit/verify`.
- **CSV Simulation & Signal Generation**: Includes a simulation engine backed by `AuditFlow_All_Transactions_Consolidated.csv` with UI controls (**Simulate CSV** and **Force signal**) to stream realistic Canadian banking transactions and policy violations into the review queue.

---

## Public GitHub Repository
`https://github.com/lognos/transactions_monitor`

---

## 1 Minute Demo Video
`<TODO: Paste YouTube / Loom demo link before submitting>`

---

## Problem Statement
- [x] **Problem Statement 1: Agents You Can Audit**
- [ ] Problem Statement 2: Memory You Can Govern
- [ ] Problem Statement 3: Finish the Job

*(Primary track: **Problem Statement 1: Agents You Can Audit**; also implements governed, scoped agent memory with full attribution.)*

---

## Describe your use of MongoDB products to build the submitted project.
MongoDB Atlas serves as the unified identity, policy, memory, and tamper-evident audit layer for the entire agent lifecycle (`txn_validation` database across 9 collections):

1. **Multi-Document ACID Transactions + Hash-Chained `audit_log` (`chain_head`)**: Every state mutation after seeding goes through a single `write_with_audit` helper that increments `chain_head.seq`, applies the business writes (`evaluations`, `decisions`, `transactions`, `memory`), and appends a SHA-256 hash-chained event (`hash = sha256(prev_hash + canonical_json(event))`) in one atomic MongoDB transaction.
2. **Schema Validation & Strict Indexing**: `audit_log` is protected by a MongoDB `$jsonSchema` validator (`validationLevel: "strict"`) requiring `seq`, `ts`, `actor` (including `on_behalf_of`), `event`, `txn_id`, `ref`, `detail`, `prev_hash`, and `hash`, alongside unique indexes on `txn_id`, `eval_id`, `memory_id`, and `seq`.
3. **Atlas Vector Search with Automated Embedding (`voyage-4`)**: The `memory` collection uses a `vectorSearch` index (`memory_text_idx`) with `autoEmbed` (`voyage-4`) on `text` and pre-filters on `txn_type`, `kind`, `active`, and `scope.criterion_id` to retrieve relevant historical precedents during evaluation and reviewer Q&A, while `active_adjustments` queries active reviewer-authored rules directly.
4. **MongoDB Aggregation Pipelines**: `GET /transactions` uses `$lookup`, `$filter`, and `$map` to join transactions, customers, and the latest non-superseded evaluation in a single query for the reviewer queue.

---

## Partner Technologies Used
- [ ] ElevenLabs
- [x] **LangChain** *(LangChain + LangGraph `StateGraph` for the `Evaluate` and `Review` subgraphs, structured outputs via `with_structured_output`, and LangSmith tracing)*
- [ ] N/A

---

## Do you have any feedback for MongoDB?
*(Optional — e.g., Atlas Vector Search `autoEmbed` with `voyage-4` made semantic precedent retrieval effortless without managing a separate embedding pipeline, and multi-document transactions on `chain_head` + `audit_log` made building a tamper-evident audit log straightforward.)*
