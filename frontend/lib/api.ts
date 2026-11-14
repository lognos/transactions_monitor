// One function per HTTP call in docs/contracts.md §4.
// Every call sends the acting principal in X-Principal-Id.

import type {
  AskResponse,
  AuditEvent,
  ChatResponse,
  CheckResult,
  DecideResponse,
  Evaluation,
  EvaluatePendingResponse,
  Gate,
  Health,
  Principal,
  ReferencesResponse,
  SimulateResponse,
  TransactionSummary,
  TxnStatus,
  Verdict,
  VerifyResponse,
} from "./types";
import { FixtureError, fixtures } from "./fixtures";

// No default identity: nothing is sent as a reviewer until someone signs in.
let principalId = "";

export function setPrincipal(id: string | null) {
  principalId = id ?? "";
}

type ApiSource = "fixture" | "backend";
// Every endpoint defaults to the real FastAPI backend.
// Set NEXT_PUBLIC_API_SOURCE=fixture to fall back to in-memory fixtures.
const defaultSource: ApiSource = process.env.NEXT_PUBLIC_API_SOURCE === "fixture" ? "fixture" : "backend";
export const apiSources: Record<
  "health" | "principals" | "transactions" | "evaluate" | "evaluation" | "ask" |
  "decide" | "audit" | "verifyChain" | "evaluatePending" | "simulate" | "references" | "chat" | "overrideCheck",
  ApiSource
> = {
  health: defaultSource,
  principals: defaultSource,
  transactions: defaultSource,
  evaluate: defaultSource,
  evaluation: defaultSource,
  ask: defaultSource,
  decide: defaultSource,
  audit: defaultSource,
  verifyChain: defaultSource,
  evaluatePending: defaultSource,
  simulate: defaultSource,
  references: defaultSource,
  chat: defaultSource,
  overrideCheck: defaultSource,
};

export function getApiMode(): "fixtures" | "backend" | "mixed" {
  const sources = Object.values(apiSources);
  return sources.every((source) => source === "fixture") ? "fixtures"
    : sources.every((source) => source === "backend") ? "backend" : "mixed";
}

interface ErrorBody {
  error?: { code?: string; message?: string };
  gate?: Gate;
  blocking_checks?: string[];
}

export class ApiError extends Error {
  status: number;
  code?: string;
  gate?: Gate;
  blocking_checks?: string[];

  constructor(status: number, body: ErrorBody | null) {
    super(body?.error?.message ?? `Request failed (${status})`);
    this.status = status;
    this.code = body?.error?.code;
    this.gate = body?.gate;
    this.blocking_checks = body?.blocking_checks;
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

async function call<T>(name: keyof typeof apiSources, fixture: () => Promise<T>, backend: () => Promise<T>): Promise<T> {
  try {
    return await (apiSources[name] === "fixture" ? fixture() : backend());
  } catch (error) {
    if (error instanceof FixtureError) throw new ApiError(error.status, error.body);
    throw error;
  }
}

const pathId = encodeURIComponent;

export const api = {
  health: () => call("health", fixtures.health, () => request<Health>("GET", "/health")),
  principals: () => call("principals", fixtures.principals, () => request<{ principals: Principal[] }>("GET", "/principals")),
  transactions: (status?: TxnStatus) =>
    call("transactions", () => fixtures.transactions(principalId, status), () =>
      request<{ transactions: TransactionSummary[] }>("GET", status ? `/transactions?status=${status}` : "/transactions")),
  evaluate: (txnId: string, refresh = false) => call("evaluate", () => fixtures.evaluate(txnId, principalId, refresh), () =>
    request<Evaluation>("POST", `/transactions/${pathId(txnId)}/evaluate${refresh ? "?refresh=true" : ""}`)),
  evaluatePending: (refresh = false) => call("evaluatePending", () => fixtures.evaluatePending(principalId, refresh), () =>
    request<EvaluatePendingResponse>("POST", "/transactions/evaluate-pending", { refresh })),
  simulate: (options: { count?: number; mode?: "random" | "signals" | "sequential"; policy_only?: boolean } = {}) =>
    call("simulate", async () => ({ simulated: [], failed: [] }), () =>
      request<SimulateResponse>("POST", "/transactions/simulate", options)),
  evaluation: (evalId: string) => call("evaluation", () => fixtures.evaluation(evalId), () =>
    request<Evaluation>("GET", `/evaluations/${pathId(evalId)}`)),
  references: (evalId: string, criterionId: string) => call("references", () => fixtures.references(evalId, criterionId), () =>
    request<ReferencesResponse>("GET", `/evaluations/${pathId(evalId)}/checks/${pathId(criterionId)}/references`)),
  overrideCheck: (evalId: string, criterionId: string, result: CheckResult | null, reason?: string) =>
    call("overrideCheck", () => fixtures.overrideCheck(evalId, criterionId, principalId, result, reason), () =>
      request<Evaluation>("POST", `/evaluations/${pathId(evalId)}/checks/${pathId(criterionId)}/override`, { result, reason })),
  ask: (evalId: string, question: string) =>
    call("ask", () => fixtures.ask(evalId, principalId, question), () => request<AskResponse>("POST", `/evaluations/${pathId(evalId)}/ask`, { question })),
  chat: (message: string) => call("chat", () => fixtures.chat(principalId, message), () => request<ChatResponse>("POST", "/chat", { message })),
  decide: (evalId: string, verdict: Verdict, comments?: string) =>
    call("decide", () => fixtures.decide(evalId, principalId, verdict, comments), () =>
      request<DecideResponse>("POST", `/evaluations/${pathId(evalId)}/decide`, { verdict, comments })),
  audit: (txnId?: string) =>
    call("audit", () => fixtures.audit(txnId), () => request<{ events: AuditEvent[] }>("GET", txnId ? `/audit?txn_id=${pathId(txnId)}` : "/audit")),
  verifyChain: () => call("verifyChain", fixtures.verifyChain, () => request<VerifyResponse>("GET", "/audit/verify")),
};
