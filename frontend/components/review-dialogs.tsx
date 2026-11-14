"use client";

import { useId, useState } from "react";
import { BookOpen, LoaderCircle, Sparkles, X } from "lucide-react";
import { Badge, Button, Dialog, Select, type BadgeTone } from "@/components/ui";
import type { Check, CheckOverride, CheckResult, Evaluation, Principal, ReferencesResponse, Verdict } from "@/lib/types";

const resultTone: Record<CheckResult, BadgeTone> = { pass: "positive", no_pass: "negative", flag: "attention" };
const resultText: Record<CheckResult, string> = { pass: "PASS", no_pass: "NO-PASS", flag: "FLAG" };
const whyText: Record<CheckResult, string> = { pass: "Why it passed", no_pass: "Why it did not pass", flag: "Why it was flagged" };
const verdictText: Record<Verdict, string> = {
  approved: "Approved",
  rejected: "Rejected",
};

function timestamp(value: string) {
  return new Intl.DateTimeFormat("en-CA", {
    dateStyle: "medium", timeStyle: "short", timeZone: "America/Toronto",
  }).format(new Date(value));
}

function Loading({ children }: { children: string }) {
  return <p role="status" className="flex items-center gap-3 py-8 text-text-muted"><LoaderCircle aria-hidden="true" className="size-5 animate-spin" />{children}</p>;
}

function ErrorBanner({ message }: { message: string }) {
  return <p role="alert" className="rounded-lg border border-status-negative-border bg-status-negative-bg p-4 text-status-negative-fg">{message}</p>;
}

export interface TransactionDetailsProps {
  evaluation?: Evaluation;
  loading: boolean;
  error?: string | null;
  busy: boolean;
  overrideBusy?: boolean;
  decisionError?: string | null;
  principals: Principal[];
  onClose: () => void;
  onReferences: (criterionId: string) => void;
  onDecide: (verdict: Verdict, comments?: string) => void;
  onOverride: (criterionId: string, result: CheckResult | null, reason?: string) => Promise<void>;
}

// Inline panel shown under the transactions list in the artifacts pane.
export function TransactionDetails(props: TransactionDetailsProps) {
  const { evaluation, loading, error, onClose } = props;
  return (
    <section aria-label="Transaction details" className="flex min-h-0 flex-1 flex-col border-t-2 border-border-default bg-surface-1">
      <header className="flex items-center justify-between gap-3 border-b border-border-subtle px-5 py-2">
        <h3 className="text-sm font-medium">{evaluation && <span className="font-mono">{evaluation.txn_id} · </span>}Transaction details</h3>
        <button type="button" aria-label="Close transaction details" onClick={onClose} className="rounded p-1 text-text-muted hover:bg-surface-3 hover:text-text-default focus-visible:outline-2 focus-visible:outline-border-focus">
          <X className="size-4" aria-hidden="true" />
        </button>
      </header>
      <div className="min-h-0 flex-1 overflow-y-auto p-5">
        {loading && !evaluation && <Loading>Loading transaction checks…</Loading>}
        {error && <ErrorBanner message={error} />}
        {evaluation && <CheckDetails key={evaluation.eval_id} {...props} evaluation={evaluation} />}
      </div>
    </section>
  );
}

function CheckDetails({ evaluation, busy, overrideBusy, decisionError, principals, onReferences, onDecide, onOverride }: TransactionDetailsProps & { evaluation: Evaluation }) {
  const [commentMode, setCommentMode] = useState<"optional" | "reject" | null>(null);
  const [comments, setComments] = useState("");
  const commentsId = useId();
  const blockingId = useId();
  const { transaction, customer, decision } = evaluation;
  const canDecide = evaluation.status === "awaiting_review" && !decision;
  const blockedBy = evaluation.checks.filter((check) => check.effective_result === "no_pass");
  const effectiveRecommendation = evaluation.effective_recommendation;
  const actionsBusy = busy || overrideBusy;
  const rejectCommentRequired = effectiveRecommendation === "pass";

  return (
    <div className="space-y-4">
      <section className="rounded-lg border border-border-subtle bg-surface-2/50 p-3" aria-label="Transaction summary">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="text-base font-medium"><span className="capitalize">{transaction.type}</span> · {transaction.currency} {transaction.amount.toLocaleString("en-CA")}</div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={resultTone[evaluation.recommendation]} className="px-2.5 py-0.5 text-sm">Agent original: {resultText[evaluation.recommendation]}</Badge>
            {effectiveRecommendation !== evaluation.recommendation && <Badge tone={resultTone[effectiveRecommendation]} className="px-2.5 py-0.5 text-sm">Effective: {resultText[effectiveRecommendation]}</Badge>}
          </div>
        </div>
        <dl className="mt-2 grid gap-x-6 gap-y-1.5 text-sm sm:grid-cols-2 2xl:grid-cols-4">
          <div><dt className="text-text-subtle">Customer</dt><dd>{customer.name}</dd></div>
          <div><dt className="text-text-subtle">Counterparty</dt><dd>{transaction.counterparty.name}</dd></div>
          <div className="sm:col-span-2"><dt className="text-text-subtle">Transaction memo</dt><dd className="break-words">{transaction.memo || "No memo supplied"}</dd></div>
          <div><dt className="text-text-subtle">Status</dt><dd className="capitalize">{decision ? verdictText[decision.verdict] : transaction.status.replaceAll("_", " ")}</dd></div>
          <div><dt className="text-text-subtle">Policy</dt><dd className="capitalize">{transaction.type} · version {evaluation.policy_version}</dd></div>
        </dl>
      </section>

      <section aria-label="Checks">
        <ul className="divide-y divide-border-subtle rounded-lg border border-border-subtle">
          {evaluation.checks.map((check) => <CheckRow key={check.criterion_id} check={check} editable={canDecide} busy={Boolean(actionsBusy)} principals={principals} onReferences={onReferences} onOverride={onOverride} />)}
        </ul>
      </section>

      <section>
        <h3 className="font-medium">Agent’s original rationale</h3>
        <p className="mt-1 text-text-muted">{evaluation.rationale}</p>
      </section>

      {decision && <section role="status" className="rounded-lg border border-status-info-border bg-status-info-bg p-4 text-status-info-fg">
        <p className="text-lg font-medium">{verdictText[decision.verdict]}</p>
        <p className="mt-1 text-sm">By {principals.find((person) => person._id === decision.reviewer_id)?.name ?? decision.reviewer_id} · {timestamp(decision.ts)} (Toronto)</p>
        {decision.comments && <p className="mt-2">{decision.comments}</p>}
      </section>}
      {evaluation.status === "superseded" && <p role="status" className="rounded-lg border border-status-attention-border bg-status-attention-bg p-4 text-status-attention-fg">A newer evaluation replaced this checklist. Reopen the transaction to review its current recommendation.</p>}

      {decisionError && <ErrorBanner message={decisionError} />}

      {canDecide && <section className="space-y-4 border-t border-border-subtle pt-5" aria-label="Reviewer decision">
        {blockedBy.length > 0 && <p id={blockingId} className="text-sm text-status-attention-fg">Clear {blockedBy.map((check) => `${check.criterion_id} (${check.description})`).join("; ")} before approving. Change each failed result to PASS or FLAG and give a reason.</p>}
        <div className="flex flex-wrap gap-3">
          <Button disabled={actionsBusy || blockedBy.length > 0} aria-describedby={blockedBy.length ? blockingId : undefined} onClick={() => onDecide("approved", comments.trim() || undefined)} className="h-10 text-base">Approve</Button>
          <Button variant="danger" disabled={actionsBusy} onClick={() => {
            if (rejectCommentRequired) setCommentMode("reject");
            else onDecide("rejected", comments.trim() || undefined);
          }} className="h-10 text-base">Reject</Button>
          {!commentMode && <Button variant="ghost" disabled={actionsBusy} onClick={() => setCommentMode("optional")} className="h-10 text-sm">Add comment (optional)</Button>}
        </div>
        {commentMode && <form className="space-y-3" onSubmit={(event) => {
          event.preventDefault();
          if (commentMode === "reject" && (!rejectCommentRequired || comments.trim()) && !actionsBusy) onDecide("rejected", comments.trim() || undefined);
        }}>
          <label htmlFor={commentsId} className="block font-medium">{commentMode === "reject" ? "Reason for rejection" : "Reviewer comment"} <span className="text-sm font-normal text-text-muted">({commentMode === "reject" && rejectCommentRequired ? "required" : "optional"})</span></label>
          {commentMode === "reject" && rejectCommentRequired && <p className="text-sm text-text-muted">The effective recommendation is PASS. Explain why you are rejecting this transaction.</p>}
          <textarea id={commentsId} value={comments} disabled={actionsBusy} onChange={(event) => setComments(event.target.value)} rows={3} required={commentMode === "reject" && rejectCommentRequired} placeholder="Explain your decision…" className="w-full rounded-lg border border-border-default bg-surface-base px-3 py-2 text-base text-text-default placeholder:text-text-subtle focus-visible:outline-2 focus-visible:outline-border-focus disabled:opacity-50" />
          <div className="flex gap-3">
            {commentMode === "reject" && <Button type="submit" variant="danger" disabled={actionsBusy || (rejectCommentRequired && !comments.trim())} className="h-10 text-base">{busy ? "Recording…" : "Confirm rejection"}</Button>}
            <Button variant="ghost" disabled={actionsBusy} onClick={() => { setCommentMode(null); setComments(""); }} className="h-10 text-sm">Cancel comment</Button>
          </div>
        </form>}
        {busy && <p role="status" className="flex items-center gap-2 text-text-muted"><LoaderCircle className="size-4 animate-spin" aria-hidden="true" />Recording decision…</p>}
      </section>}
    </div>
  );
}

function OverrideProvenance({ override, principals }: { override: CheckOverride; principals: Principal[] }) {
  const roleLabel = `${override.role[0].toUpperCase()}${override.role.slice(1)} override`;
  const name = principals.find((person) => person._id === override.by)?.name ?? override.by;
  return <div className="rounded-lg border border-status-info-border bg-status-info-bg p-3">
    <p className="flex flex-wrap items-center gap-2 text-sm font-medium"><Badge tone="info" className="text-sm">{roleLabel}</Badge><span>{name} · via {override.via}</span></p>
    <p className="mt-2 break-words text-base font-medium">{override.reason}</p>
    <p className="mt-1 text-sm text-text-muted">{timestamp(override.ts)} (Toronto)</p>
  </div>;
}

function CheckRow({ check, editable, busy, principals, onReferences, onOverride }: {
  check: Check;
  editable: boolean;
  busy: boolean;
  principals: Principal[];
  onReferences: (criterionId: string) => void;
  onOverride: TransactionDetailsProps["onOverride"];
}) {
  const [editing, setEditing] = useState(false);
  const [result, setResult] = useState<CheckResult>(check.effective_result);
  const [reason, setReason] = useState("");
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const resultId = useId();
  const reasonId = useId();
  const formId = useId();
  const disabled = busy || working;

  async function saveOverride(nextResult: CheckResult | null, nextReason?: string) {
    if (disabled || !editable) return;
    setWorking(true);
    setError(null);
    try {
      await onOverride(check.criterion_id, nextResult, nextReason);
      setEditing(false);
      setReason("");
    } catch (error) {
      setError(error instanceof Error ? error.message : "Could not update this check. Try again.");
    } finally {
      setWorking(false);
    }
  }

  return <li className="space-y-2 px-4 py-3">
    <div className="flex flex-wrap items-center gap-3">
      <span className="font-mono text-sm text-accent-fg">{check.criterion_id}</span>
      <h3 className="min-w-40 flex-1 text-sm font-medium">{check.description}</h3>
      <Badge tone={check.source === "rule" ? "neutral" : "info"} className="text-sm">{check.source === "rule" ? "rule" : "LLM"}</Badge>
      <div className="flex flex-wrap items-center gap-2">
        {check.override && <span className="text-sm text-text-muted">Agent original: <span className="font-medium">{resultText[check.result]}</span></span>}
        <button type="button" onClick={() => onReferences(check.criterion_id)} aria-label={`References for ${check.criterion_id}: effective ${resultText[check.effective_result]}`} className="rounded-md focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-border-focus">
          <Badge tone={resultTone[check.effective_result]} className="gap-2 px-3 py-1 text-sm hover:opacity-80">{check.override ? "Effective: " : ""}{resultText[check.effective_result]}<BookOpen className="size-3.5" aria-hidden="true" /></Badge>
        </button>
      </div>
      {check.adjustments_used.length > 0 && <Badge tone="positive" icon={Sparkles} className="text-sm">learned</Badge>}
      {editable && <Button variant="action-sm" disabled={disabled} aria-label={`Change result for ${check.criterion_id}`} aria-expanded={editing} aria-controls={formId} onClick={() => {
        setResult(check.effective_result); setReason(check.override?.reason ?? ""); setError(null); setEditing(true);
      }}>Change result</Button>}
      {editable && check.override && <Button variant="action-sm" disabled={disabled} aria-label={`Revert override for ${check.criterion_id}`} onClick={() => { void saveOverride(null); }}>Revert</Button>}
    </div>
    <p className="break-words text-sm text-text-muted">{check.evidence}</p>
    {check.override && <OverrideProvenance override={check.override} principals={principals} />}
    {error && <ErrorBanner message={error} />}
    {editing && editable && <form id={formId} aria-label={`Override ${check.criterion_id}`} className="space-y-3 rounded-lg border border-border-default bg-surface-2/50 p-3" onSubmit={(event) => {
      event.preventDefault();
      if (reason.trim()) void saveOverride(result, reason.trim());
    }}>
      <div className="flex flex-wrap items-center gap-3">
        <label htmlFor={resultId} className="text-sm font-medium">New result for {check.criterion_id}</label>
        <Select id={resultId} value={result} disabled={disabled} onChange={(event) => setResult(event.target.value as CheckResult)}>
          <option value="pass">PASS</option><option value="flag">FLAG</option><option value="no_pass">NO-PASS</option>
        </Select>
      </div>
      <label htmlFor={reasonId} className="block text-sm font-medium">Reason for changing {check.criterion_id} <span className="font-normal text-text-muted">(required)</span></label>
      <textarea id={reasonId} rows={2} required value={reason} disabled={disabled} onChange={(event) => setReason(event.target.value)} placeholder="Explain why this result should change…" className="w-full rounded-lg border border-border-default bg-surface-base px-3 py-2 text-sm text-text-default placeholder:text-text-subtle focus-visible:outline-2 focus-visible:outline-border-focus disabled:opacity-50" />
      <div className="flex gap-2">
        <Button type="submit" disabled={disabled || !reason.trim()} aria-label={`Save override for ${check.criterion_id}`}>{working ? "Saving…" : "Save override"}</Button>
        <Button variant="ghost" disabled={disabled} aria-label={`Cancel override for ${check.criterion_id}`} onClick={() => { setEditing(false); setError(null); }}>Cancel</Button>
      </div>
    </form>}
    {working && <p role="status" className="flex items-center gap-2 text-sm text-text-muted"><LoaderCircle className="size-4 animate-spin" aria-hidden="true" />Updating {check.criterion_id}…</p>}
  </li>;
}

export interface ReferencesDialogProps {
  open: boolean;
  loading: boolean;
  error?: string | null;
  references?: ReferencesResponse;
  principals?: Principal[];
  onClose: () => void;
}

export function ReferencesDialog({ open, loading, error, references, principals = [], onClose }: ReferencesDialogProps) {
  return (
    <Dialog open={open} onClose={onClose} className="max-w-3xl" title={references ? `${references.check.criterion_id} · References` : "Check references"} description="Why this check got its result, and the policy and decisions behind it.">
      {loading && <Loading>Loading references…</Loading>}
      {error && <ErrorBanner message={error} />}
      {references && <div className="space-y-6">
        {references.check.override && <section aria-label="Reviewer override">
          <div className="mb-3 flex flex-wrap items-center gap-3">
            <span className="text-sm text-text-muted">Agent original: {resultText[references.check.result]}</span>
            <Badge tone={resultTone[references.check.effective_result]} className="px-3 py-1 text-base">Effective: {resultText[references.check.effective_result]}</Badge>
          </div>
          <OverrideProvenance override={references.check.override} principals={principals} />
        </section>}
        <section>
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <Badge tone={resultTone[references.check.result]} className="px-3 py-1 text-base">{references.check.override ? "Agent original: " : ""}{resultText[references.check.result]}</Badge>
            <Badge tone={references.check.source === "llm" ? "info" : "neutral"} className="text-sm">{references.check.source === "llm" ? "LLM" : "rule"}</Badge>
          </div>
          <h3 className="text-lg font-medium">{references.check.override ? "Agent’s original assessment" : whyText[references.check.result]}</h3>
          <p className="mt-1 text-base leading-relaxed">{references.check.explanation || references.check.evidence}</p>
          {references.check.facts.length > 0 && <>
            <h4 className="mt-4 text-xs font-medium tracking-wider text-text-subtle uppercase">What was checked</h4>
            <dl className="mt-2 grid grid-cols-[minmax(8rem,auto)_1fr] gap-x-6 gap-y-1.5 text-sm">
              {references.check.facts.map((fact) => <div key={fact.label} className="contents">
                <dt className="text-text-muted">{fact.label}</dt><dd className="break-words font-medium">{fact.value}</dd>
              </div>)}
            </dl>
          </>}
        </section>
        <section className="rounded-lg border border-border-subtle bg-surface-2/50 p-4">
          <h3 className="text-lg font-medium">Policy rule</h3>
          <p className="mt-1 font-medium">{references.policy.criterion_id} · {references.policy.description}</p>
          <p className="mt-1 text-sm text-text-muted"><span className="capitalize">{references.policy.txn_type}</span> · version {references.policy.version} · {references.policy.kind === "hard" ? "hard / deterministic" : "judgment"}</p>
          <p className="mt-3 text-text-muted"><span className="font-medium text-text-default">Regulation: </span>{references.policy.regulation_ref || "No regulation reference supplied"}</p>
        </section>

        {references.adjustments.length === 0 && references.precedents.length === 0 ? <p className="rounded-lg border border-border-subtle p-4 text-text-muted">{references.check.override ? "No learned adjustments or previous decisions were used by the agent for this check." : "This check has no references beyond its policy rule."}</p> : <>
          <section>
            <h3 className="flex items-center gap-2 text-lg font-medium"><Sparkles className="size-5 text-status-positive-fg" aria-hidden="true" />Learned adjustments</h3>
            {references.adjustments.length === 0 ? <p className="mt-2 text-text-muted">No learned adjustments were used for this check.</p> : <ul className="mt-3 space-y-3">
              {references.adjustments.map((adjustment) => <li key={adjustment.memory_id} className="rounded-lg border-2 border-status-positive-border bg-status-positive-bg p-4">
                <p className="text-lg font-medium text-status-positive-fg">Learned from {principals.find((person) => person._id === adjustment.author_id)?.name ?? adjustment.author_name ?? adjustment.author_id}</p>
                <p className="mt-2 text-lg">{adjustment.text}</p>
                {adjustment.condition && <p className="mt-3 text-text-muted">Applies when: {adjustment.condition}</p>}
                <p className="mt-3 text-sm text-text-muted">From <span className="font-mono">{adjustment.source_txn_id}</span> · {timestamp(adjustment.created_at)} (Toronto)</p>
                <p className="mt-1 font-mono text-xs text-text-subtle">{adjustment.memory_id}</p>
              </li>)}
            </ul>}
          </section>
          <section>
            <h3 className="text-lg font-medium">Previous decisions</h3>
            {references.precedents.length === 0 ? <p className="mt-2 text-text-muted">No previous decisions were used as precedents for this check.</p> : <ul className="mt-3 space-y-3">
              {references.precedents.map((precedent) => <li key={precedent.memory_id} className="rounded-lg border border-border-subtle p-4">
                <p>{precedent.text}</p>
                <p className="mt-2 text-sm text-text-muted">{precedent.author_id === "seed" ? "Seeded precedent" : `Reviewed by ${principals.find((person) => person._id === precedent.author_id)?.name ?? precedent.author_name ?? precedent.author_id}`}{precedent.verdict ? ` · ${verdictText[precedent.verdict]}` : ""}</p>
                <p className="mt-1 text-sm text-text-muted">{precedent.source_txn_id ? `${precedent.source_txn_id} · ` : ""}{timestamp(precedent.created_at)} (Toronto)</p>
                <p className="mt-1 font-mono text-xs text-text-subtle">{precedent.memory_id}</p>
              </li>)}
            </ul>}
          </section>
        </>}
      </div>}
    </Dialog>
  );
}
