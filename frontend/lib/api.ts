// One function per HTTP call in docs/contracts.md §4.
// Every call sends the acting principal in X-Principal-Id.

import type {
  AskResponse,
  AuditEvent,
  DecideResponse,
  Evaluation,
  Gate,
  Health,
  Principal,
  Transaction,
  TxnStatus,
  Verdict,
  VerifyResponse,
} from "./types";

let principalId: string | null = null;

export function setPrincipal(id: string | null) {
  principalId = id;
}

interface ErrorBody {
  error?: { code?: string; message?: string };
  gate?: Gate;
}

export class ApiError extends Error {
  status: number;
  code?: string;
  gate?: Gate;

  constructor(status: number, body: ErrorBody | null) {
    super(body?.error?.message ?? `Request failed (${status})`);
    this.status = status;
    this.code = body?.error?.code;
    this.gate = body?.gate;
  }
}

async function request<T>(method: "GET" | "POST", path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {};
  if (principalId) headers["X-Principal-Id"] = principalId;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const res = await fetch(`/api${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, data);
  return data as T;
}

export const api = {
  health: () => request<Health>("GET", "/health"),
  principals: () => request<{ principals: Principal[] }>("GET", "/principals"),
  transactions: (status?: TxnStatus) =>
    request<{ transactions: Transaction[] }>(
      "GET",
      status ? `/transactions?status=${status}` : "/transactions",
    ),
  evaluate: (txnId: string) => request<Evaluation>("POST", `/transactions/${txnId}/evaluate`),
  evaluation: (evalId: string) => request<Evaluation>("GET", `/evaluations/${evalId}`),
  ask: (evalId: string, question: string) =>
    request<AskResponse>("POST", `/evaluations/${evalId}/ask`, { question }),
  decide: (evalId: string, verdict: Verdict, comments?: string) =>
    request<DecideResponse>("POST", `/evaluations/${evalId}/decide`, { verdict, comments }),
  audit: (txnId?: string) =>
    request<{ events: AuditEvent[] }>("GET", txnId ? `/audit?txn_id=${txnId}` : "/audit"),
  verifyChain: () => request<VerifyResponse>("GET", "/audit/verify"),
};
