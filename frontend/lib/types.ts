// Shapes from docs/contracts.md. Keep in sync with that file.

export type Role = "analyst" | "supervisor" | "auditor" | "agent";
export type TxnType = "wire" | "cheque";
export type TxnStatus = "pending" | "awaiting_review" | "passed" | "rejected";
export type CheckResult = "pass" | "no_pass" | "flag";
export type Recommendation = "pass" | "no_pass";
export type Verdict = "validated" | "validated_with_comments" | "rejected";

export interface Principal {
  _id: string;
  type: "human" | "agent";
  name: string;
  role: Role;
  approval_limit?: number | null;
}

export interface Transaction {
  txn_id: string;
  type: TxnType;
  amount: number;
  currency: string;
  customer_id: string;
  counterparty: { name: string; account?: string; address?: string | null; country?: string };
  memo?: string;
  status: TxnStatus;
  created_at: string;
  type_specific?: Record<string, unknown>;
}

// GET /transactions returns a summary, not the full source transaction.
export interface TransactionSummary {
  txn_id: string;
  type: TxnType;
  amount: number;
  currency: string;
  customer_name: string;
  counterparty_name: string;
  memo?: string;
  status: TxnStatus;
  eval_id: string | null;
  recommendation: Recommendation | null;
  failed_checks: string[];
  created_at: string;
}

export interface Customer {
  customer_id: string;
  name: string;
  segment: string;
  typical_amount: number;
}

export interface Check {
  criterion_id: string;
  description: string;
  kind: "hard" | "judgment";
  source: "rule" | "llm";
  result: CheckResult;
  evidence: string;
  regulation_ref?: string;
  precedents_used: string[];
  adjustments_used: string[];
}

export interface Citation {
  type: "policy" | "precedent" | "adjustment";
  ref: string;
  label?: string;
}

export interface ThreadItem {
  question: string;
  answer: string;
  citations: Citation[];
  asked_by: string;
  ts: string;
}

export interface Gate {
  result: "allow" | "deny";
  rule_id: string | null;
  reason: string;
}

export interface Decision {
  decision_id: string;
  eval_id: string;
  txn_id: string;
  reviewer_id: string;
  verdict: Verdict;
  comments: string | null;
  agreed_with_agent: boolean;
  gate: Gate;
  ts: string;
}

export interface Evaluation {
  eval_id: string;
  txn_id: string;
  actor: { id: string; type: string; role: Role; on_behalf_of: string | null };
  policy_version: number;
  checks: Check[];
  recommendation: Recommendation;
  rationale: string;
  precedents_used: string[];
  adjustments_used: string[];
  thread: ThreadItem[];
  status: "awaiting_review" | "decided" | "superseded";
  created_at: string;
  transaction: Transaction;
  customer: Customer;
  decision?: Decision | null;
}

export interface MemoryItem {
  memory_id: string;
  kind: "precedent" | "adjustment";
  text: string;
}

export interface AuditEvent {
  seq: number;
  ts: string;
  actor: { id: string; type: string; role: Role; on_behalf_of: string | null };
  event: string;
  txn_id: string | null;
  ref: { collection: string; id: string };
  detail: Record<string, unknown>;
  prev_hash: string;
  hash: string;
}

export interface Health {
  ok: boolean;
  db: string;
  error?: string;
}

export interface AskResponse {
  answer: string;
  citations: Citation[];
  thread: ThreadItem[];
}

export interface DecideResponse {
  decision: Decision;
  transaction_status: TxnStatus;
  memory_created: MemoryItem[];
}

export interface VerifyResponse {
  ok: boolean;
  checked: number;
  broken_at_seq: number | null;
  reason: string | null;
}

export interface EvaluatePendingResponse {
  evaluated: {
    txn_id: string;
    eval_id: string;
    recommendation: Recommendation;
    changed: boolean;
  }[];
  failed: { txn_id: string; error: string }[];
}

export interface ChatResponse {
  answer: string;
  citations: Citation[];
}

export interface ReferencesResponse {
  check: Pick<Check, "criterion_id" | "result" | "source" | "evidence">;
  policy: {
    txn_type: TxnType;
    version: number;
    criterion_id: string;
    description: string;
    kind: Check["kind"];
    regulation_ref: string;
    params: Record<string, unknown>;
  };
  adjustments: {
    memory_id: string;
    text: string;
    condition: string;
    author_id: string;
    author_name: string | null;
    source_txn_id: string;
    created_at: string;
  }[];
  precedents: {
    memory_id: string;
    text: string;
    author_id: string;
    author_name: string | null;
    source_txn_id: string | null;
    verdict: Verdict | null;
    created_at: string;
  }[];
}
