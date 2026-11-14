"use client";

import { CheckCircle2, Fingerprint, LoaderCircle, ShieldCheck, ShieldX } from "lucide-react";
import { Badge, Button } from "@/components/ui";
import type { AuditEvent, Principal, VerifyResponse } from "@/lib/types";

export interface AuditPanelProps {
  events: AuditEvent[];
  loading: boolean;
  error?: string | null;
  focusTxnId?: string | null;
  verification?: VerifyResponse | null;
  verifying: boolean;
  onVerify: () => void;
  principals: Principal[];
}

function detailText(event: AuditEvent): string {
  const detail = event.detail;
  const gate = detail.gate && typeof detail.gate === "object" ? detail.gate as Record<string, unknown> : null;
  switch (event.event) {
    case "evaluation.created": {
      const failed = Array.isArray(detail.failed) ? detail.failed.join(", ") : "";
      const adjustments = Array.isArray(detail.adjustments_used) ? detail.adjustments_used.length : 0;
      return [String(detail.recommendation || "Evaluated").replaceAll("_", " ").toUpperCase(), failed ? `Failed checks: ${failed}` : "No failed checks", adjustments ? `${adjustments} learned adjustment${adjustments === 1 ? "" : "s"} used` : null].filter(Boolean).join(" · ");
    }
    case "question.answered":
      return typeof detail.question === "string" ? detail.question : "Answered a reviewer question";
    case "decision.denied":
      return ["Decision denied", typeof gate?.reason === "string" ? gate.reason : null, typeof detail.amount === "number" ? `CAD ${detail.amount.toLocaleString()}` : null].filter(Boolean).join(" · ");
    case "decision.recorded":
      return [String(detail.verdict || "Decision recorded").replaceAll("_", " "), typeof detail.agreed_with_agent === "boolean" ? detail.agreed_with_agent ? "Agreed with agent" : "Reviewer overrode recommendation" : null, typeof gate?.rule_id === "string" ? `Gate ${gate.rule_id}` : null].filter(Boolean).join(" · ");
    case "memory.created":
      return [detail.kind === "adjustment" ? "Learned adjustment" : "Previous decision saved as precedent", typeof detail.criterion_id === "string" ? detail.criterion_id : null, typeof detail.author_id === "string" ? `Author: ${detail.author_id}` : null].filter(Boolean).join(" · ");
    default:
      return event.ref.id;
  }
}

export function AuditPanel({ events, loading, error, focusTxnId, verification, verifying, onVerify, principals }: AuditPanelProps) {
  function person(id: string) {
    return principals.find((principal) => principal._id === id)?.name || id;
  }

  return (
    <section aria-label="Audit timeline" className="space-y-5 p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-lg font-medium">Audit trail</h3>
          <p className="text-sm text-text-muted">{focusTxnId ? `Events for ${focusTxnId}` : "Events across all transactions"}</p>
        </div>
        <Button variant="ghost" onClick={onVerify} disabled={verifying} className="h-10 text-sm">
          {verifying ? <LoaderCircle className="size-4 animate-spin" aria-hidden="true" /> : <ShieldCheck className="size-4" aria-hidden="true" />}
          {verifying ? "Verifying…" : "Verify chain"}
        </Button>
      </div>
      {verification && (
        <div role={verification.ok ? "status" : "alert"} className={`flex items-start gap-3 rounded-lg border p-4 ${verification.ok ? "border-status-positive-border bg-status-positive-bg text-status-positive-fg" : "border-status-negative-border bg-status-negative-bg text-status-negative-fg"}`}>
          {verification.ok ? <CheckCircle2 className="mt-0.5 size-6 shrink-0" aria-hidden="true" /> : <ShieldX className="mt-0.5 size-6 shrink-0" aria-hidden="true" />}
          <div>
            <p className="text-lg font-semibold">{verification.ok ? `Chain intact, ${verification.checked} events` : verification.broken_at_seq !== null ? `Broken at event #${verification.broken_at_seq}` : "Chain verification failed"}</p>
            <p className="text-sm">{verification.ok ? "Verified the complete audit chain." : verification.reason || "The chain could not be verified."}</p>
          </div>
        </div>
      )}
      {error && <p role="alert" className="rounded-lg border border-status-negative-border bg-status-negative-bg p-4 text-status-negative-fg">{error}</p>}
      {loading ? <p role="status" className="flex items-center gap-2 py-8 text-text-muted"><LoaderCircle className="size-5 animate-spin" aria-hidden="true" /> Loading audit events…</p> : events.length === 0 ? <p className="rounded-lg border border-border-subtle bg-surface-1 p-5 text-text-muted">No audit events{focusTxnId ? ` for ${focusTxnId}` : ""} yet. Evaluations, questions and decisions appear here.</p> : (
        <ol className="space-y-4" aria-label="Audit events in sequence">
          {events.map((event) => (
            <li key={event.seq} className="relative rounded-lg border border-border-subtle bg-surface-1 p-4">
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <span className="font-mono text-sm text-text-subtle">#{event.seq}</span>
                <Badge tone={event.event === "decision.denied" ? "negative" : event.event === "memory.created" ? "info" : "neutral"} className="text-sm">{event.event}</Badge>
                {event.txn_id && <span className="font-mono text-sm text-text-muted">{event.txn_id}</span>}
                <time dateTime={event.ts} className="ml-auto text-xs text-text-subtle">{new Date(event.ts).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit" })}</time>
              </div>
              <p className="text-base"><span className="font-medium">{person(event.actor.id)}</span><span className="text-text-muted"> · {event.actor.role}</span>{event.actor.on_behalf_of && <span className="text-text-muted"> on behalf of <span className="font-medium text-text-default">{person(event.actor.on_behalf_of)}</span></span>}</p>
              <p className="mt-1 break-words text-base text-text-muted">{detailText(event)}</p>
              <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-border-subtle pt-2 text-xs text-text-subtle">
                <Fingerprint className="size-4" aria-hidden="true" />
                <span>Hash</span><code title={event.hash}>{event.hash.slice(0, 12)}…</code>
                <span className="ml-auto break-all font-mono">{event.ref.id}</span>
              </div>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
