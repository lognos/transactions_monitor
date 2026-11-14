# Interface and data contracts

Single source of truth for names and shapes shared between the four lanes (DB, UI, Agent, Scenarios).
Freeze this in the first 20 minutes. After that, a change needs a message to the whole team.

Contents: [1 Conventions](#1-conventions) · [2 Enums](#2-enums) · [3 Collections](#3-collections) · [4 HTTP API](#4-http-api) · [5 Internal Python interfaces](#5-internal-python-interfaces) · [6 LLM structured outputs](#6-llm-structured-outputs) · [7 Graph state](#7-graph-state)

---

> **Pending proposal:** the Approve / Reject verdicts and the check-override fields (section 8, and the lines in sections 2, 3.4, 4 and 5 that mention `approved`, `effective_result` or `override`) are proposed and not agreed yet.

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
| `verdict` | `approved`, `rejected` (acts on the transaction, see §8) |
| `override_via` | `panel`, `chat` |
| `memory_kind` | `precedent`, `adjustment` |
| `role` | `analyst`, `supervisor`, `auditor`, `agent` |
| `gate_result` | `allow`, `deny` |
| `audit_event` | `evaluation.created`, `question.answered`, `decision.denied`, `decision.recorded`, `memory.created`, `check.overridden`, `check.override_reverted` |

Derived rules (code, not LLM):
- `recommendation = no_pass` if any check is `no_pass`, otherwise `pass`.
- `effective_result` of a check = `override.result` if it has an override, else `result`.
- `effective_recommendation = no_pass` if any `effective_result` is `no_pass`, otherwise `pass`. `recommendation` stays the agent's original and is never rewritten.
- `agreed_with_agent = (verdict == approved) == (recommendation == pass)`, using the agent's original recommendation.
- Transaction status after a decision: `approved` → `passed`, `rejected` → `rejected`.
- `approved` is only accepted when `effective_recommendation` is `pass`, that is, every `no_pass` check has been overridden to `pass` or `flag`.
- `comments` is required only when the verdict differs from `effective_recommendation`. In practice that is `rejected` on a `pass`. Otherwise it is optional.

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
    { "rule_id": "D-01", "role": "analyst", "max_amount": 50000, "can_override_hard_fail": true },
    { "rule_id": "D-02", "role": "supervisor", "max_amount": null, "can_override_hard_fail": true }
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
      "evidence": "counterparty.address is missing",
      "explanation": "The travel rule requires the beneficiary's name, address and account number to travel with a wire. The address is missing, so the wire cannot proceed until it is corrected. This is a mandatory rule and no reviewer can override it.",
      "facts": [ { "label": "Beneficiary name", "value": "Northwind Trading" }, { "label": "Beneficiary address", "value": "Missing" } ],
      "regulation_ref": "FINTRAC travel rule",
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
- `status`: `awaiting_review`, `decided`, or `superseded` (replaced by a newer evaluation of the same transaction after a refresh).
- Top-level `precedents_used` and `adjustments_used` are the union of the per-check lists.
- Each check carries three levels of detail. `evidence` is one line for the checklist row. `explanation` is two to four sentences for the references dialog saying why the check passed, failed or was flagged, in words a reviewer can repeat to an auditor. `facts` lists the values that were examined (`label`, `value` as display strings). Hard checks produce all three in code; judgment checks get `evidence` and `explanation` from the LLM and `facts` from the node.

Index: unique on `eval_id`; `{txn_id: 1}`.

### 3.6 `decisions`
Only allowed decisions are stored. A denied attempt exists only as a `decision.denied` audit event.
```json
{
  "decision_id": "DEC-9c0d1e2f", "eval_id": "EVAL-3fa91c20", "txn_id": "TXN-0003",
  "reviewer_id": "ana", "verdict": "approved",
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
  "detail": { "verdict": "approved", "gate": { "result": "allow", "rule_id": "D-01" } },
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

Base URL `http://localhost:8010` (port 8000 is taken on some of our machines). JSON in and out. Header `X-Principal-Id` on every call.

| # | Method and path | Purpose |
| --- | --- | --- |
| 1 | `GET /principals` | Fill the login screen. The only call that needs no `X-Principal-Id` |
| 2 | `GET /transactions?status=pending` | Transactions list, each with the agent's latest recommendation |
| 3 | `POST /transactions/{txn_id}/evaluate` | Run the Evaluate graph for one transaction (`?refresh=true` to redo it) |
| 4 | `GET /evaluations/{eval_id}` | Checks dialog |
| 5 | `POST /evaluations/{eval_id}/ask` | Chat about one transaction |
| 6 | `POST /evaluations/{eval_id}/decide` | Validate or reject |
| 7 | `GET /audit?txn_id=TXN-0003` | Timeline for one transaction (omit `txn_id` for all) |
| 8 | `GET /audit/verify` | Verify the hash chain |
| 9 | `POST /transactions/evaluate-pending` | Evaluate every pending transaction so the list shows recommendations |
| 10 | `GET /evaluations/{eval_id}/checks/{criterion_id}/references` | References dialog for one check |
| 11 | `POST /chat` | Chat with no transaction in focus |

### Responses

**2 `GET /transactions`** → `200`
```json
{ "transactions": [ { "txn_id": "TXN-0001", "type": "wire", "amount": 4000, "currency": "CAD",
    "customer_name": "Harbour Dental", "counterparty_name": "Medisupply Inc", "memo": "…",
    "status": "awaiting_review", "eval_id": "EVAL-3fa91c20", "recommendation": "no_pass",
    "failed_checks": ["W-01", "C-04"], "created_at": "…" } ] }
```
`eval_id`, `recommendation` and `failed_checks` come from the latest evaluation that is not `superseded`. All three are `null` / `[]` for a transaction that has not been evaluated.

**3 `POST /transactions/{txn_id}/evaluate`** (no body) → `200` an `evaluations` document (§3.5) plus:
```json
{ "transaction": { "…full transaction…" }, "customer": { "customer_id": "…", "name": "…", "segment": "…", "typical_amount": 2500 } }
```
Calling it again on a transaction that is `awaiting_review` returns the existing evaluation. With `?refresh=true` it runs a new evaluation and marks the old one `superseded`. A decided transaction is never re-evaluated.

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
{ "verdict": "approved", "comments": "Payroll customers spike at month-end, that's normal." }
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

**9 `POST /transactions/evaluate-pending`**
```json
{ "refresh": false }
```
Evaluates every `pending` transaction. With `"refresh": true` it also re-evaluates those `awaiting_review`, which is how a new adjustment reaches transactions already in the list. Runs the evaluations concurrently. → `200`
```json
{ "evaluated": [ { "txn_id": "TXN-0004", "eval_id": "EVAL-77c1d0aa", "recommendation": "pass", "changed": true } ],
  "failed": [ { "txn_id": "TXN-0005", "error": "…" } ] }
```
`changed` is true when the recommendation differs from the superseded evaluation.

**10 `GET /evaluations/{eval_id}/checks/{criterion_id}/references`** → `200`
```json
{
  "check": { "criterion_id": "C-04", "result": "pass", "source": "llm", "evidence": "…",
    "explanation": "The amount is 3.4 times this customer's typical payment, which would normally fail. Ana's guidance says payroll customers spike at month-end; this is a payroll customer and the cheque is dated at month-end, so the guidance applies and the check passes.",
    "facts": [ { "label": "Amount", "value": "CAD 9,400" }, { "label": "Typical amount", "value": "CAD 2,800" }, { "label": "Ratio", "value": "3.4x" } ] },
  "policy": { "txn_type": "cheque", "version": 1, "criterion_id": "C-04",
    "description": "Amount consistent with the customer's usual profile", "kind": "judgment",
    "regulation_ref": "FINTRAC suspicious-transaction indicators", "params": { "ratio_hint": 3 } },
  "adjustments": [ { "memory_id": "MEM-5e6f7a8b", "text": "…", "condition": "…",
    "author_id": "ana", "author_name": "Ana", "source_txn_id": "TXN-0003", "created_at": "…" } ],
  "precedents": [ { "memory_id": "MEM-11aa22bb", "text": "…", "author_id": "seed", "author_name": null,
    "source_txn_id": null, "verdict": null, "created_at": "…" } ]
}
```
Read-only, built by the server from `evaluations`, `policies`, `memory` and `decisions`. `adjustments` and `precedents` are the ones that check used; both are empty for most hard checks. `verdict` is the reviewer verdict of the source decision when there is one.

**11 `POST /chat`**
```json
{ "message": "What is our rule for wires over $10,000?" }
```
→ `200` `{ "answer": "…", "citations": [ { "type": "policy", "ref": "W-02", "label": "…" } ] }`

General questions answered from policies and memory, with no transaction in focus. The UI keeps this conversation in the page; it is not stored. Audited as `question.answered` with `txn_id: null`. When a transaction is in focus the UI calls `/evaluations/{eval_id}/ask` instead.

### Errors
All errors use `{ "error": { "code": "...", "message": "..." } }`.

| HTTP | `code` | When |
| --- | --- | --- |
| 401 | `unknown_principal` | Missing or unknown `X-Principal-Id` |
| 403 | `gate_denied` | Policy gate said no |
| 404 | `not_found` | Unknown transaction or evaluation |
| 409 | `already_decided` | Evaluation already has a decision |
| 409 | `checks_not_cleared` | `approved` while a check is still effectively `no_pass`. Body lists them in `blocking_checks` |
| 422 | `invalid_request` | Bad verdict, comments missing where required, or override reason missing |

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

The same function gates an override: pass `action="override"` and the check. It applies rules 1 and 2, plus:

3. The check is `hard` and the role's rule has `can_override_hard_fail: false`. (Both seeded roles have `true`: there is no hard blocker, but it stays policy data.)

"Every no_pass check cleared before approving" is not a gate rule. It is a precondition the agent lane checks before calling the gate, returned as `409 checks_not_cleared`.

### 5.3 Deterministic checks
```python
CheckFn = Callable[[dict, dict, dict, Db], Awaitable[CheckOutcome]]   # (txn, customer, params, db)
# CheckOutcome: {"result": "pass" | "no_pass" | "flag", "evidence": str,
#                "explanation": str, "facts": [{"label": str, "value": str}]}
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

### 5.5 Agent entry points
The only three functions the server imports from `app.agent`. Owned by the Agent lane.
```python
async def run_evaluate(*, txn_id: str, principal_id: str, refresh: bool = False) -> dict
# -> {"evaluation", "transaction", "customer"}
# refresh=True: write a new evaluation and mark the previous awaiting_review one "superseded".

async def run_chat(*, message: str, principal_id: str) -> dict
# -> {"answer": str, "citations": [...]}   general question, no transaction in focus

async def run_review(*, eval_id: str, principal_id: str, review_input: dict) -> dict
# review_input: {"kind": "question", "question": str}
#            or {"kind": "decision", "verdict": "approved" | "rejected", "comments": str | None}
#            or {"kind": "override", "criterion_id": str, "result": "pass" | "flag" | "no_pass" | None,
#                "reason": str, "via": "panel" | "chat"}      (result None = revert)
# -> question: {"answer", "evaluation"}
# -> decision: {"gate", "decision", "txn", "memory_created"}   (decision is None when the gate denies)
```
The server turns these into the HTTP responses in §4, including the 403 on a gate denial. A function that is not built yet raises `NotImplementedError`, which the server returns as `501 not_implemented`.

## 6. LLM structured outputs

See §8 for the optional `action` on `AnswerOutput`.

Pydantic models passed to `with_structured_output`. The LLM never writes to the database; nodes do.

**RecommendOutput**
```json
{
  "judgment_checks": [
    { "criterion_id": "C-04", "result": "no_pass", "evidence": "Amount is 3.6x the typical amount and the payee is new.",
      "explanation": "Two to four sentences: what was compared, which precedent or adjustment decided it, and what would change the result.",
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

## 8. Check overrides and decisions

**Status: proposed, not agreed yet.** Waiting for Ben and Zach to confirm. Do not build against this section until this line is removed. Once agreed: where this section and an earlier example disagree, this section wins.

### 8.1 Rules
1. The reviewer has two decisions on a transaction: **Approve** (`approved`) and **Reject** (`rejected`).
2. To approve, no check may be effectively `no_pass`. The reviewer clears each failed check by overriding it to `pass` or `flag`, and every override needs a reason.
3. Any check can be overridden, hard or judgment, in any direction. There is no hard blocker. The amount limit (gate rule 2) still applies to overrides and decisions.
4. The agent's original `result` and `recommendation` are never changed. Overrides sit beside them.
5. Rejecting needs a comment only when the effective recommendation is `pass`. Approving never needs one, because the override reasons already explain it.
6. An override can be made from the checks dialog or by asking in chat. Both run the same code and are marked `via: panel` or `via: chat`.
7. An override can be reverted until the transaction is decided.
8. Learning happens at the decision, not at the override. Judgment-check overrides become adjustments. Hard-check overrides are stored in the precedent only and never become an adjustment (invariant 4).
9. A refresh never re-evaluates an evaluation that has an active override.

UI label for an overridden check: "Analyst override" or "Supervisor override" (by role), with the agent's original result shown beside it.

### 8.2 Data
A check with an override:
```json
{ "criterion_id": "C-04", "kind": "judgment", "source": "llm", "result": "no_pass", "evidence": "…",
  "effective_result": "pass",
  "override": { "result": "pass", "reason": "Payroll customers spike at month-end, that's normal.",
    "by": "ana", "role": "analyst", "via": "panel", "ts": "2026-11-14T14:09:00Z",
    "gate": { "result": "allow", "rule_id": "D-01" } } }
```
- Every check carries `effective_result`. `override` is `null` when there is none.
- `evaluations` gains `effective_recommendation`.
- `decisions` gains `effective_recommendation` and `overrides`: `[{ "criterion_id", "kind", "from", "to", "reason", "via" }]`, a snapshot at decision time.
- A `memory` adjustment created from an override has `scope.criterion_id` taken from the override, not guessed by the model.

Audit `detail`:

| Event | `detail` |
| --- | --- |
| `check.overridden` | `criterion_id`, `kind`, `from`, `to`, `reason`, `via`, `gate` |
| `check.override_reverted` | `criterion_id`, `from`, `to` |
| `decision.denied` | now also used for a denied override: adds `action` (`decision` or `override`) and `criterion_id` |
| `decision.recorded` | adds `effective_recommendation`, `overrides` (criterion ids) |

### 8.3 HTTP
**`POST /evaluations/{eval_id}/checks/{criterion_id}/override`**
```json
{ "result": "pass", "reason": "Payroll customers spike at month-end, that's normal." }
```
`result` is `pass`, `flag` or `no_pass`; `null` reverts. `reason` is required unless reverting. → `200` the updated evaluation (same shape as `GET /evaluations/{eval_id}`). `403 gate_denied`, `409 already_decided`, `404`, `422` as elsewhere.

**`POST /evaluations/{eval_id}/decide`** body is now `{ "verdict": "approved" | "rejected", "comments": "…" | null }`.
`409 checks_not_cleared`:
```json
{ "error": { "code": "checks_not_cleared", "message": "Clear W-01 and C-04 before approving." },
  "blocking_checks": ["W-01", "C-04"] }
```

**`POST /evaluations/{eval_id}/ask`** response gains `"override": { "criterion_id", "from", "to", "status": "applied" | "denied" | "needs_reason" } | null` and `"evaluation"` (the updated evaluation) when an override was applied.

**`GET /transactions`** items gain `effective_recommendation` and `override_count`. **References** (call 10) `check` gains `effective_result` and `override`.

### 8.4 Chat overrides
`AnswerOutput` gains an optional action. The model only extracts intent; code applies it through the same override path.
```json
{ "answer": "…", "citations": [],
  "action": { "type": "override_check", "criterion_id": "C-04", "result": "pass", "reason": "…" } }
```
- Only read from the reviewer's own message. Never from the transaction memo or any stored text.
- Applied only if `criterion_id` is a check on the focused evaluation. If the reason is missing, nothing is written and the agent asks for it (`status: needs_reason`).
- The answer states exactly what was changed.

