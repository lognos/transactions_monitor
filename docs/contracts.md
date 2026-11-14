# Interface and data contracts

Single source of truth for names and shapes shared between the four lanes (DB, UI, Agent, Scenarios).
Freeze this in the first 20 minutes. After that, a change needs a message to the whole team.

Contents: [1 Conventions](#1-conventions) · [2 Enums](#2-enums) · [3 Collections](#3-collections) · [4 HTTP API](#4-http-api) · [5 Internal Python interfaces](#5-internal-python-interfaces) · [6 LLM structured outputs](#6-llm-structured-outputs) · [7 Graph state](#7-graph-state)

---

## 1. Conventions

- Field names are `snake_case`. Timestamps are UTC, ISO 8601 strings in JSON, `Date` in MongoDB.
- Amounts are numbers in CAD. No cents handling in the demo.
- Ids are readable strings, never ObjectIds, in anything the UI or audit log shows:
  `TXN-0001`, `CUS-001`, `EVAL-<8 hex>`, `DEC-<8 hex>`, `MEM-<8 hex>`.
- Database name: `txn_validation` (env `DB_NAME`).
- **Identity:** no login. Every request carries `X-Principal-Id: <principals._id>`. The API rejects unknown ids with 401.
- The agent's own identity is `agent-01`. Its `on_behalf_of` is the principal on the request.

## 2. Enums

| Name | Values |
| --- | --- |
| `txn_type` | `wire`, `cheque` |
| `txn_status` | `pending`, `awaiting_review`, `passed`, `rejected` |
| `check_kind` | `hard` (deterministic code), `judgment` (LLM) |
| `check_source` | `rule`, `llm` |
| `check_result` | `pass`, `no_pass`, `flag` (`flag` = reporting obligation, does not block) |
| `recommendation` | `pass`, `no_pass` |
| `verdict` | `validated`, `validated_with_comments`, `rejected` |
| `memory_kind` | `precedent`, `adjustment` |
| `role` | `analyst`, `supervisor`, `auditor`, `agent` |
| `gate_result` | `allow`, `deny` |
| `audit_event` | `evaluation.created`, `question.answered`, `decision.denied`, `decision.recorded`, `memory.created` |

Derived rules (code, not LLM):
- `recommendation = no_pass` if any check is `no_pass`, otherwise `pass`.
- `agreed_with_agent = (verdict != rejected) == (recommendation == pass)`.
- Transaction status after a decision: `validated*` → `passed`, `rejected` → `rejected`.
- `comments` is required for `validated_with_comments` and `rejected`.

## 3. Collections

Nine collections: eight from the schema diagram plus `chain_head` (one document).

### 3.1 `principals`
```json
{ "_id": "ana", "type": "human", "name": "Ana", "role": "analyst", "approval_limit": 50000 }
{ "_id": "agent-01", "type": "agent", "name": "Validation agent", "role": "agent" }
```

### 3.2 `customers` (source system)
```json
{
  "customer_id": "CUS-001", "name": "Maple Payroll Services", "segment": "payroll",
  "risk_rating": "low", "typical_amount": 2500, "country": "CA",
  "account_status": "open", "balance": 180000
}
```

### 3.3 `transactions` (source system)
```json
{
  "txn_id": "TXN-0002", "type": "wire", "amount": 12000, "currency": "CAD",
  "customer_id": "CUS-002",
  "counterparty": { "name": "Northwind Trading", "account": "GB29NWBK60161331926819", "address": null, "country": "GB" },
  "memo": "Invoice 4471",
  "created_at": "2026-11-14T14:02:00Z",
  "status": "pending",
  "type_specific": { }
}
```
`type_specific` by type:

| Type | Fields |
| --- | --- |
| `wire` | `originator` `{name, address, account}`, `international` (bool), `new_beneficiary` (bool) |
| `cheque` | `cheque_date` (date), `deposit_channel` (`branch`, `atm`, `mobile`), `hold_days_applied` (int) |

Index: unique on `txn_id`; `{status: 1, created_at: 1}`.

### 3.4 `policies`
One active document per `txn_type`. Criteria that apply to all types are repeated in each document.
```json
{
  "txn_type": "wire", "version": 1, "active": true,
  "criteria": [
    { "id": "C-01", "description": "Counterparty not on a sanctions list", "kind": "hard",
      "check": "sanctions_screen", "params": { "names": ["..."] }, "regulation_ref": "Canadian sanctions law" },
    { "id": "C-04", "description": "Amount consistent with the customer's usual profile", "kind": "judgment",
      "check": null, "params": { "ratio_hint": 3 }, "regulation_ref": "FINTRAC suspicious-transaction indicators" }
  ],
  "decision_rules": [
    { "rule_id": "D-01", "role": "analyst", "max_amount": 50000, "can_override_hard_fail": false },
    { "rule_id": "D-02", "role": "supervisor", "max_amount": null, "can_override_hard_fail": false }
  ]
}
```
- `check` is the name of a registered Python function (see §5.3). `null` for judgment criteria.
- A role with no decision rule (auditor, agent) cannot decide.

Index: unique on `{txn_type: 1, version: 1}`.

### 3.5 `evaluations`
```json
{
  "eval_id": "EVAL-3fa91c20", "txn_id": "TXN-0002",
  "actor": { "id": "agent-01", "type": "agent", "role": "agent", "on_behalf_of": "ana" },
  "policy_version": 1,
  "checks": [
    { "criterion_id": "W-01", "description": "Originator and beneficiary information complete",
      "kind": "hard", "source": "rule", "result": "no_pass",
      "evidence": "counterparty.address is missing", "regulation_ref": "FINTRAC travel rule",
      "precedents_used": [], "adjustments_used": [] }
  ],
  "recommendation": "no_pass",
  "rationale": "Beneficiary address is missing, so the transfer cannot proceed.",
  "precedents_used": ["MEM-11aa22bb"],
  "adjustments_used": [],
  "thread": [
    { "question": "Why did C-04 fail?", "answer": "...",
      "citations": [ { "type": "policy", "ref": "C-04" }, { "type": "precedent", "ref": "MEM-11aa22bb" } ],
      "asked_by": "ana", "ts": "2026-11-14T14:05:10Z" }
  ],
  "status": "awaiting_review",
  "created_at": "2026-11-14T14:03:00Z"
}
```
- `status`: `awaiting_review` or `decided`.
- Top-level `precedents_used` and `adjustments_used` are the union of the per-check lists.

Index: unique on `eval_id`; `{txn_id: 1}`.

### 3.6 `decisions`
Only allowed decisions are stored. A denied attempt exists only as a `decision.denied` audit event.
```json
{
  "decision_id": "DEC-9c0d1e2f", "eval_id": "EVAL-3fa91c20", "txn_id": "TXN-0003",
  "reviewer_id": "ana", "verdict": "validated_with_comments",
  "comments": "Payroll customers spike at month-end, that's normal.",
  "agreed_with_agent": false,
  "gate": { "result": "allow", "rule_id": "D-01", "reason": "analyst within limit" },
  "ts": "2026-11-14T14:10:00Z"
}
```
Index: unique on `eval_id` (one decision per evaluation).

### 3.7 `memory`
```json
{
  "memory_id": "MEM-5e6f7a8b", "kind": "adjustment", "txn_type": "cheque",
  "text": "For payroll customers, cheque amounts several times the typical amount at month-end are expected. Do not fail C-04 for that reason alone.",
  "scope": { "criterion_id": "C-04", "condition": "customer segment is payroll and date is within 3 days of month-end" },
  "source_decision_id": "DEC-9c0d1e2f", "source_txn_id": "TXN-0003",
  "author_id": "ana", "active": true, "created_at": "2026-11-14T14:10:01Z"
}
```
- `kind: precedent`: one per decision. `text` is a templated case summary (no LLM). `scope` is `null`.
- `kind: adjustment`: only created for a criterion whose `kind` is `judgment`. Enforced in code.
- Seeded precedents have `author_id: "seed"` and `source_decision_id: null`.

Vector index `memory_text_idx` on `text` (Automated Embedding), filter fields `txn_type`, `kind`, `active`.

### 3.8 `audit_log`
Append-only. Never updated or deleted by the application.
```json
{
  "seq": 17, "ts": "2026-11-14T14:10:00Z",
  "actor": { "id": "ana", "type": "human", "role": "analyst", "on_behalf_of": null },
  "event": "decision.recorded",
  "txn_id": "TXN-0003",
  "ref": { "collection": "decisions", "id": "DEC-9c0d1e2f" },
  "detail": { "verdict": "validated_with_comments", "gate": { "result": "allow", "rule_id": "D-01" } },
  "prev_hash": "…64 hex…", "hash": "…64 hex…"
}
```
- `hash = sha256(prev_hash + canonical_json(event))`, where `event` is the document without `hash` and `_id`.
- `canonical_json` = `json.dumps(obj, sort_keys=True, separators=(",", ":"))` with `ts` as its ISO string.
- First event uses `prev_hash` of 64 zeros.

`detail` by event:

| Event | `detail` |
| --- | --- |
| `evaluation.created` | `recommendation`, `policy_version`, `failed` (criterion ids), `precedents_used`, `adjustments_used` |
| `question.answered` | `question`, `citations` |
| `decision.denied` | `verdict`, `amount`, `gate` |
| `decision.recorded` | `verdict`, `agreed_with_agent`, `gate` |
| `memory.created` | `kind`, `criterion_id`, `source_decision_id`, `author_id` |

Index: unique on `seq`; `{txn_id: 1, seq: 1}`. `$jsonSchema` validator requires every field above.

### 3.9 `chain_head`
```json
{ "_id": "head", "seq": 17, "hash": "…64 hex…" }
```
Updated in the same transaction as each audit insert. This serializes writers.

## 4. HTTP API

Base URL `http://localhost:8000`. JSON in and out. Header `X-Principal-Id` on every call.

| # | Method and path | Purpose |
| --- | --- | --- |
| 1 | `GET /principals` | Fill the "acting as" dropdown |
| 2 | `GET /transactions?status=pending` | Queue |
| 3 | `POST /transactions/{txn_id}/evaluate` | Run the Evaluate graph |
| 4 | `GET /evaluations/{eval_id}` | Reload a review card |
| 5 | `POST /evaluations/{eval_id}/ask` | Ask a question |
| 6 | `POST /evaluations/{eval_id}/decide` | Validate or reject |
| 7 | `GET /audit?txn_id=TXN-0003` | Timeline for one transaction (omit `txn_id` for all) |
| 8 | `GET /audit/verify` | Verify the hash chain |

### Responses

**2 `GET /transactions`** → `200`
```json
{ "transactions": [ { "txn_id": "TXN-0001", "type": "wire", "amount": 4000, "currency": "CAD",
    "customer_name": "Harbour Dental", "counterparty_name": "Medisupply Inc", "memo": "…",
    "status": "pending", "eval_id": null, "created_at": "…" } ] }
```
`eval_id` is the latest evaluation for the transaction, or `null`.

**3 `POST /transactions/{txn_id}/evaluate`** (no body) → `200` an `evaluations` document (§3.5) plus:
```json
{ "transaction": { "…full transaction…" }, "customer": { "customer_id": "…", "name": "…", "segment": "…", "typical_amount": 2500 } }
```
Calling it again on a transaction that is `awaiting_review` returns the existing evaluation.

**4 `GET /evaluations/{eval_id}`** → same shape as 3, plus `"decision": {…} | null`.

**5 `POST /evaluations/{eval_id}/ask`**
```json
{ "question": "Have we passed anything like this before?" }
```
→ `200`
```json
{ "answer": "…", "citations": [ { "type": "precedent", "ref": "MEM-11aa22bb", "label": "Cheque, CAD 8,400, payroll, validated by sam" } ], "thread": [ "…full thread…" ] }
```

**6 `POST /evaluations/{eval_id}/decide`**
```json
{ "verdict": "validated_with_comments", "comments": "Payroll customers spike at month-end, that's normal." }
```
→ `200`
```json
{ "decision": { "…decisions document…" }, "transaction_status": "passed",
  "memory_created": [ { "memory_id": "MEM-5e6f7a8b", "kind": "adjustment", "text": "…" }, { "memory_id": "MEM-0a1b2c3d", "kind": "precedent", "text": "…" } ] }
```
→ `403` when the gate denies
```json
{ "error": { "code": "gate_denied", "message": "Amount 60000 exceeds analyst limit 50000. A supervisor must decide." },
  "gate": { "result": "deny", "rule_id": "D-01", "reason": "amount over limit" } }
```

**7 `GET /audit`** → `200` `{ "events": [ …audit_log documents, ascending seq… ] }`

**8 `GET /audit/verify`** → `200`
```json
{ "ok": false, "checked": 23, "broken_at_seq": 12, "reason": "hash mismatch" }
```

### Errors
All errors use `{ "error": { "code": "...", "message": "..." } }`.

| HTTP | `code` | When |
| --- | --- | --- |
| 401 | `unknown_principal` | Missing or unknown `X-Principal-Id` |
| 403 | `gate_denied` | Policy gate said no |
| 404 | `not_found` | Unknown transaction or evaluation |
| 409 | `already_decided` | Evaluation already has a decision |
| 422 | `invalid_request` | Bad verdict, or comments missing where required |

## 5. Internal Python interfaces

Owned by the DB lane, called by the Agent lane. Signatures are the contract; bodies are written at the event.

### 5.1 Audit
```python
async def write_with_audit(
    *, actor: dict, event: str, txn_id: str,
    ref: dict,            # {"collection": ..., "id": ...}
    detail: dict,
    writes: list[Write],  # inserts/updates to apply in the same transaction
) -> dict                 # the audit event written

async def verify_chain() -> dict   # {"ok", "checked", "broken_at_seq", "reason"}
```
Every application write goes through `write_with_audit`. Nothing else writes to MongoDB after seeding.

### 5.2 Gate
```python
async def check_gate(*, principal: dict, txn: dict, evaluation: dict, verdict: str) -> dict
# -> {"result": "allow" | "deny", "rule_id": str | None, "reason": str}
```
Deny, in this order:
1. No decision rule for the principal's role.
2. `txn.amount > rule.max_amount` (when `max_amount` is not null).
3. Verdict is `validated*`, a `hard` check is `no_pass`, and `can_override_hard_fail` is false.

### 5.3 Deterministic checks
```python
CheckFn = Callable[[dict, dict, dict, Db], Awaitable[CheckOutcome]]   # (txn, customer, params, db)
# CheckOutcome: {"result": "pass" | "no_pass" | "flag", "evidence": str}
CHECKS: dict[str, CheckFn]
```

| `check` name | Criterion | Must-have |
| --- | --- | --- |
| `sanctions_screen` | C-01 | Yes |
| `account_ok` | C-02 | Optional |
| `duplicate` | C-03 | Yes |
| `structuring_24h` | C-05 | Optional |
| `travel_rule_fields` | W-01 | Yes |
| `eft_report_threshold` | W-02 | Yes (returns `flag`) |
| `cheque_date_valid` | Q-01 | Yes |
| `hold_period_applied` | Q-02 | Optional |

Judgment criteria (no function): C-04 (all types), W-03 (wire).

### 5.4 Memory retrieval
```python
async def search_memory(*, query: str, txn_type: str, kind: str, k: int = 4) -> list[dict]
async def active_adjustments(*, txn_type: str) -> list[dict]   # plain find, no vector search
```

## 6. LLM structured outputs

Pydantic models passed to `with_structured_output`. The LLM never writes to the database; nodes do.

**RecommendOutput**
```json
{
  "judgment_checks": [
    { "criterion_id": "C-04", "result": "no_pass", "evidence": "Amount is 3.6x the typical amount and the payee is new.",
      "precedents_used": ["MEM-11aa22bb"], "adjustments_used": [] }
  ],
  "rationale": "One or two sentences for the reviewer."
}
```
- Exactly one entry per judgment criterion in the policy. `result` is `pass` or `no_pass`.
- Ids in `precedents_used` / `adjustments_used` must come from the retrieved context. The node drops any others.

**AnswerOutput**
```json
{ "answer": "…", "citations": [ { "type": "policy" | "precedent" | "adjustment", "ref": "C-04" } ] }
```

**LearnOutput**
```json
{ "should_create": true, "criterion_id": "C-04",
  "condition": "customer segment is payroll and date is within 3 days of month-end",
  "text": "Guidance in one or two sentences, written for a future evaluator." }
```
- `should_create: false` when the comment carries no reusable guidance.
- The node discards the output if `criterion_id` is not a judgment criterion.

## 7. Graph state

LangGraph `TypedDict` states. Keys only; values follow the shapes above.

**EvalState**: `txn_id`, `principal_id`, `txn`, `customer`, `policy`, `checks`, `precedents`, `adjustments`, `llm_output`, `evaluation`

**ReviewState**: `eval_id`, `principal_id`, `input` (`{"kind": "question" | "decision", "question", "verdict", "comments"}`), `evaluation`, `txn`, `principal`, `answer`, `gate`, `decision`, `memory_created`
