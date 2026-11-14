"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, CheckCheck, FileClock, ListChecks, LoaderCircle, RefreshCw, ShieldCheck, Sparkles, X } from "lucide-react";
import { useEffect, useRef, useState, type CSSProperties } from "react";
import { AuditPanel } from "@/components/audit-panel";
import { ChatPanel, type ChatMessage } from "@/components/chat-panel";
import { ChecksDialog, ReferencesDialog } from "@/components/review-dialogs";
import { Badge, Button, Select } from "@/components/ui";
import { api, getApiMode, setPrincipal } from "@/lib/api";
import { cn } from "@/lib/cn";
import type { Evaluation, MemoryItem, Recommendation, TransactionSummary, Verdict } from "@/lib/types";

const statusLabels = { pending: "Pending", awaiting_review: "Awaiting review", passed: "Passed", rejected: "Rejected" };
const recommendationLabel = (value: Recommendation) => value === "pass" ? "PASS" : "NO-PASS";
const messageOf = (error: unknown) => error instanceof Error ? error.message : "Something went wrong. Please try again.";
type QueueData = { transactions: TransactionSummary[] };
type ChangedRow = { before: Recommendation | null; after: Recommendation };

export default function Home() {
  const client = useQueryClient();
  const [principalId, setPrincipalId] = useState("ana");
  const [focusedTxnId, setFocusedTxnId] = useState<string | null>(null);
  const [checksOpen, setChecksOpen] = useState(false);
  const [reference, setReference] = useState<{ evalId: string; criterionId: string } | null>(null);
  const [tab, setTab] = useState<"transactions" | "audit">("transactions");
  const [loadingRows, setLoadingRows] = useState<string[]>([]);
  const [queueError, setQueueError] = useState<string | null>(null);
  const [changedRows, setChangedRows] = useState<Record<string, ChangedRow>>({});
  const [adjustments, setAdjustments] = useState<MemoryItem[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [chatWidth, setChatWidth] = useState(34);
  const [resizing, setResizing] = useState(false);
  const splitPane = useRef<HTMLElement>(null);
  const autoAttempted = useRef(new Set<string>());
  const queueRunning = useRef(false);

  useEffect(() => {
    const pane = splitPane.current;
    if (!pane) return;
    const observer = new ResizeObserver(([entry]) => {
      const width = entry.contentRect.width;
      if (width >= 1024) setChatWidth((current) => Math.max(300 / width * 100, Math.min((width - 430) / width * 100, current)));
    });
    observer.observe(pane);
    return () => observer.disconnect();
  }, []);

  function resizeChat(percent: number) {
    const width = splitPane.current?.getBoundingClientRect().width;
    if (width) setChatWidth(Math.max(300 / width * 100, Math.min((width - 430) / width * 100, percent)));
  }

  const health = useQuery({ queryKey: ["health"], queryFn: api.health });
  const principals = useQuery({ queryKey: ["principals"], queryFn: api.principals });
  const people = principals.data?.principals.filter((person) => person.type === "human") ?? [];
  const queue = useQuery({ queryKey: ["transactions"], queryFn: () => api.transactions(), enabled: Boolean(principals.data) });
  const transactions = queue.data?.transactions ?? [];
  const focusedTxn = transactions.find((txn) => txn.txn_id === focusedTxnId);
  const evalId = focusedTxn?.eval_id;
  const evaluation = useQuery({ queryKey: ["evaluation", evalId], queryFn: () => api.evaluation(evalId!), enabled: Boolean(evalId) });
  const references = useQuery({
    queryKey: ["references", reference?.evalId, reference?.criterionId],
    queryFn: () => api.references(reference!.evalId, reference!.criterionId), enabled: Boolean(reference),
  });
  const audit = useQuery({
    queryKey: ["audit", focusedTxnId], queryFn: () => api.audit(focusedTxnId ?? undefined),
    enabled: tab === "audit" && Boolean(principals.data),
  });
  const verify = useMutation({ mutationFn: api.verifyChain });

  const evaluateQueue = useMutation({
    mutationFn: (refresh: boolean) => api.evaluatePending(refresh),
    onMutate: (refresh) => {
      queueRunning.current = true;
      setQueueError(null);
      verify.reset();
      const before = client.getQueryData<QueueData>(["transactions"])?.transactions ?? [];
      setLoadingRows(before.filter((txn) => txn.status === "pending" || (refresh && txn.status === "awaiting_review")).map((txn) => txn.txn_id));
      return { before };
    },
    onSuccess: async (result, _refresh, context) => {
      setChangedRows((previous) => {
        const next = { ...previous };
        for (const item of result.evaluated) {
          if (item.changed) next[item.txn_id] = {
            before: context?.before.find((txn) => txn.txn_id === item.txn_id)?.recommendation ?? null,
            after: item.recommendation,
          };
        }
        return next;
      });
      setQueueError(result.failed.length ? result.failed.map((item) => `${item.txn_id}: ${item.error}`).join(" · ") : null);
      await Promise.all([
        client.invalidateQueries({ queryKey: ["transactions"] }),
        client.invalidateQueries({ queryKey: ["evaluation"] }),
        client.invalidateQueries({ queryKey: ["audit"] }),
      ]);
    },
    onError: (error) => setQueueError(`Could not evaluate the queue: ${messageOf(error)}`),
    onSettled: () => { queueRunning.current = false; setLoadingRows([]); },
  });

  const evaluate = evaluateQueue.mutate;
  useEffect(() => {
    const pending = queue.data?.transactions.filter((txn) => txn.status === "pending" && !autoAttempted.current.has(txn.txn_id)) ?? [];
    if (!pending.length || queueRunning.current) return;
    pending.forEach((txn) => autoAttempted.current.add(txn.txn_id));
    queueRunning.current = true;
    evaluate(false);
  }, [queue.data, evaluate]);

  const decision = useMutation({
    mutationFn: ({ evaluationId, verdict, comments }: { evaluationId: string; verdict: Verdict; comments?: string }) => api.decide(evaluationId, verdict, comments),
    onSuccess: async (result, variables) => {
      verify.reset();
      client.setQueryData<Evaluation>(["evaluation", variables.evaluationId], (old) => old ? {
        ...old, status: "decided", decision: result.decision,
        transaction: { ...old.transaction, status: result.transaction_status },
      } : old);
      client.setQueryData<QueueData>(["transactions"], (old) => old ? {
        transactions: old.transactions.map((txn) => txn.txn_id === result.decision.txn_id ? { ...txn, status: result.transaction_status } : txn),
      } : old);
      const learned = result.memory_created.filter((item) => item.kind === "adjustment");
      if (learned.length) {
        setAdjustments(learned);
        setChangedRows({});
        setChecksOpen(false);
        setTab("transactions");
        // Refresh errors belong to the queue: the decision has already succeeded.
        evaluateQueue.mutate(true);
      }
      await Promise.all([
        client.invalidateQueries({ queryKey: ["transactions"] }),
        client.invalidateQueries({ queryKey: ["audit"] }),
      ]);
    },
    onError: () => { verify.reset(); void client.invalidateQueries({ queryKey: ["audit"] }); },
  });

  const chat = useMutation({
    mutationFn: ({ text, evaluationId }: { text: string; evaluationId?: string; txnId?: string }) => evaluationId ? api.ask(evaluationId, text) : api.chat(text),
    onSuccess: (answer, request) => {
      setMessages((previous) => [...previous, { id: crypto.randomUUID(), role: "agent", text: answer.answer, citations: answer.citations, txnId: request.txnId, evaluationId: request.evaluationId }]);
      verify.reset();
      void client.invalidateQueries({ queryKey: ["audit"] });
    },
  });

  function changePrincipal(id: string) {
    setPrincipal(id);
    setPrincipalId(id);
    decision.reset();
  }
  function openTransaction(txn: TransactionSummary) {
    setFocusedTxnId(txn.txn_id);
    decision.reset();
    setChecksOpen(true);
  }
  function openReferences(criterionId: string) {
    if (evalId && evaluation.data?.checks.some((check) => check.criterion_id === criterionId)) setReference({ evalId, criterionId });
  }
  function sendMessage(text: string) {
    if (chat.isPending || (focusedTxnId && !evalId)) return;
    setMessages((previous) => [...previous, {
      id: crypto.randomUUID(), role: "user", text, txnId: focusedTxnId ?? undefined,
      author: people.find((person) => person._id === principalId)?.name ?? principalId,
    }]);
    chat.mutate({ text, evaluationId: evalId ?? undefined, txnId: focusedTxnId ?? undefined });
  }

  const mode = getApiMode();
  const error = principals.error ?? queue.error;
  const changedEntries = Object.entries(changedRows);
  const busy = evaluateQueue.isPending || decision.isPending;

  return (
    <div className="flex min-h-screen flex-col lg:h-dvh lg:overflow-hidden">
      <header className="flex flex-wrap items-center gap-x-5 gap-y-3 border-b border-border-subtle bg-surface-1 px-5 py-4">
        <div className="mr-auto flex items-center gap-3">
          <span className="rounded-lg border border-status-info-border bg-accent-subtle p-2"><ShieldCheck className="size-6 text-accent-fg" aria-hidden="true" /></span>
          <div><h1 className="text-lg font-medium">Transaction Validation</h1><p className="text-sm text-text-muted">Agent recommendations. Human decisions.</p></div>
        </div>
        {mode !== "backend" && <Badge tone="attention">{mode === "fixtures" ? "Fixture demo" : "Mixed data sources"}</Badge>}
        <Badge tone={health.data?.ok ? "positive" : health.isPending ? "neutral" : "negative"}>
          {health.isPending ? "checking…" : health.data?.ok ? `db: ${health.data.db}` : "backend unreachable"}
        </Badge>
        <label className="flex items-center gap-2 text-sm text-text-muted">Acting as
          <Select id="acting-as" value={principalId} disabled={decision.isPending} onChange={(event) => changePrincipal(event.target.value)}>
            {!people.length && <option value="ana">Loading principals…</option>}
            {people.map((person) => <option key={person._id} value={person._id}>{person.name} · {person.role}</option>)}
          </Select>
        </label>
      </header>
      {error && <div role="alert" className="border-b border-status-negative-border bg-status-negative-bg px-5 py-3 text-status-negative-fg">{messageOf(error)}</div>}

      <main ref={splitPane} style={{ "--chat-width": `${chatWidth}%` } as CSSProperties}
        className={cn("grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[minmax(300px,var(--chat-width))_10px_minmax(420px,1fr)]", resizing && "cursor-col-resize select-none")}>
        <ChatPanel messages={messages} focus={focusedTxnId ? { txnId: focusedTxnId, evaluationId: evalId ?? undefined, criterionIds: evaluation.data?.checks.map((check) => check.criterion_id) ?? [] } : null}
          busy={chat.isPending} disabled={!principals.data || Boolean(focusedTxnId && (!evalId || loadingRows.includes(focusedTxnId)))} error={chat.error?.message}
          onClearFocus={() => { setFocusedTxnId(null); if (!chat.isPending) chat.reset(); }} onSend={sendMessage} onCitation={openReferences} />
        <div role="separator" aria-label="Resize chat and artifacts panes" aria-orientation="vertical" aria-controls="chat-pane artifacts-pane"
          aria-valuenow={Math.round(chatWidth)} aria-valuemin={0} aria-valuemax={100} aria-valuetext={`Chat width ${Math.round(chatWidth)} percent`}
          tabIndex={0} title="Drag to resize · Arrow keys to adjust · Double-click to reset"
          className={cn("group hidden touch-none items-center justify-center border-x border-border-subtle bg-surface-1 cursor-col-resize hover:bg-accent-subtle focus-visible:bg-accent-subtle focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-border-focus lg:flex", resizing && "bg-accent-subtle")}
          onDoubleClick={() => resizeChat(34)}
          onPointerDown={(event) => { if (event.button !== 0) return; event.preventDefault(); event.currentTarget.focus(); event.currentTarget.setPointerCapture(event.pointerId); setResizing(true); }}
          onPointerMove={(event) => {
            if (!event.currentTarget.hasPointerCapture(event.pointerId)) return;
            const bounds = splitPane.current?.getBoundingClientRect();
            if (bounds) resizeChat((event.clientX - bounds.left) / bounds.width * 100);
          }}
          onPointerUp={(event) => { if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId); }}
          onLostPointerCapture={() => setResizing(false)}
          onKeyDown={(event) => {
            if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
            event.preventDefault();
            resizeChat(event.key === "Home" ? 0 : event.key === "End" ? 100 : chatWidth + (event.key === "ArrowLeft" ? -2 : 2));
          }}>
          <span aria-hidden="true" className="h-12 w-1 rounded-full bg-border-default group-hover:bg-accent group-focus-visible:bg-accent" />
        </div>
        <section id="artifacts-pane" aria-label="Artifacts" className="flex min-h-0 flex-col border-t border-border-subtle bg-surface-base lg:border-t-0">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border-subtle px-5 py-4">
            <h2 className="text-xs font-medium tracking-[0.16em] text-text-muted uppercase">Artifacts</h2>
            <div role="tablist" aria-label="Artifacts" className="flex gap-1 rounded-lg border border-border-subtle bg-surface-1 p-1">
              {(["transactions", "audit"] as const).map((value, index) => {
                const Icon = value === "transactions" ? ListChecks : FileClock;
                return <button key={value} type="button" role="tab" id={`${value}-tab`} aria-controls={`${value}-panel`} aria-selected={tab === value} tabIndex={tab === value ? 0 : -1}
                  onClick={() => setTab(value)} onKeyDown={(event) => {
                    if (["ArrowRight", "ArrowLeft", "Home", "End"].includes(event.key)) {
                      event.preventDefault();
                      const next = event.key === "Home" ? "transactions" : event.key === "End" ? "audit" : index === 0 ? "audit" : "transactions";
                      setTab(next); document.getElementById(`${next}-tab`)?.focus();
                    }
                  }} className={cn("flex items-center gap-2 rounded-md px-4 py-2 text-sm font-medium focus-visible:outline-2 focus-visible:outline-border-focus", tab === value ? "bg-surface-3 text-text-default" : "text-text-muted hover:bg-surface-2")}>
                  <Icon className="size-4" aria-hidden="true" />{value === "transactions" ? "Transactions" : "Audit"}
                </button>;
              })}
            </div>
          </div>
          {tab === "transactions" ? <div id="transactions-panel" role="tabpanel" aria-labelledby="transactions-tab" className="min-h-0 flex-1 overflow-y-auto p-5">
            <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
              <div><h3 className="text-xl font-medium">Review queue</h3><p className="text-sm text-text-muted">{transactions.length} transactions · {transactions.filter((txn) => txn.status === "awaiting_review").length} awaiting review</p></div>
              <Button variant="ghost" disabled={busy || !queue.data} onClick={() => evaluateQueue.mutate(false)}>
                {evaluateQueue.isPending ? <LoaderCircle className="size-4 animate-spin" aria-hidden="true" /> : <RefreshCw className="size-4" aria-hidden="true" />}
                {evaluateQueue.isPending ? "Evaluating…" : "Evaluate queue"}
              </Button>
            </div>
            {adjustments.length > 0 && <div role="status" className="mb-5 rounded-xl border-2 border-status-positive-border bg-status-positive-bg p-5 text-status-positive-fg">
              <div className="flex items-start justify-between gap-3"><h3 className="flex items-center gap-2 text-2xl font-medium"><Sparkles className="size-6" aria-hidden="true" />Memory updated</h3>
                <button type="button" aria-label="Dismiss memory update" onClick={() => { setAdjustments([]); setChangedRows({}); }} className="rounded p-1 focus-visible:outline-2 focus-visible:outline-border-focus"><X className="size-5" /></button></div>
              {adjustments.map((item) => <p key={item.memory_id} className="mt-2 text-base leading-relaxed">{item.text}</p>)}
              <p className="mt-2 font-medium">{evaluateQueue.isPending ? "Applying the new guidance to undecided transactions…" : `${changedEntries.length} recommendation${changedEntries.length === 1 ? "" : "s"} changed`}</p>
              {queueError && <Button variant="ghost" className="mt-3" disabled={busy} onClick={() => evaluateQueue.mutate(true)}>Retry applying memory</Button>}
            </div>}
            {queueError && <div role="alert" className="mb-4 rounded-lg border border-status-negative-border bg-status-negative-bg p-4 text-status-negative-fg">{queueError}</div>}
            {changedEntries.length > 0 && <div aria-live="polite" className="mb-4 flex flex-col gap-2">
              {changedEntries.map(([id, change]) => <p key={id} className="flex flex-wrap items-center gap-3 text-xl font-medium text-status-positive-fg"><CheckCheck className="size-6" aria-hidden="true" />{id}<span>{change.before ? recommendationLabel(change.before) : "Pending"}</span><ArrowRight className="size-5" aria-label="changed to" />{recommendationLabel(change.after)}</p>)}
            </div>}
            {queue.isLoading && <p role="status" className="flex items-center gap-2 py-8 text-text-muted"><LoaderCircle className="size-5 animate-spin" />Loading transactions…</p>}
            {!queue.isLoading && queue.data && !transactions.length && <p className="rounded-lg border border-border-subtle p-8 text-center text-text-muted">No transactions in the queue.</p>}
            <ul className="space-y-3" aria-label="Transactions">
              {transactions.map((txn) => {
                const loading = loadingRows.includes(txn.txn_id);
                const changed = changedRows[txn.txn_id];
                return <li key={txn.txn_id}>
                  <button type="button" disabled={loading || decision.isPending} onClick={() => openTransaction(txn)} aria-busy={loading}
                    className={cn("w-full rounded-xl border p-4 text-left transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-border-focus disabled:cursor-wait",
                      changed ? "border-2 border-status-positive-border bg-status-positive-bg" : focusedTxnId === txn.txn_id ? "border-accent bg-accent-subtle" : "border-border-default bg-surface-1 hover:bg-surface-2")}>
                    <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
                      <div className="flex items-center gap-3"><span className="font-mono text-base font-medium">{txn.txn_id}</span><span className="text-sm text-text-muted capitalize">{txn.type}</span></div>
                      <span className="text-lg font-medium">{txn.currency} {txn.amount.toLocaleString("en-CA")}</span>
                    </div>
                    <div className="mt-2 flex flex-wrap items-end justify-between gap-3">
                      <div><p className="text-base text-text-default">{txn.customer_name}</p><p className="mt-0.5 text-sm text-text-muted">{statusLabels[txn.status]}</p></div>
                      <div className="flex flex-wrap items-center justify-end gap-2">
                        {loading ? <span role="status" className="flex items-center gap-2 text-accent-fg"><LoaderCircle className="size-5 animate-spin" aria-hidden="true" />Evaluating…</span> : txn.recommendation ? <>
                          {changed && <span className="text-sm font-medium text-status-positive-fg">Changed to</span>}
                          <Badge tone={txn.recommendation === "pass" ? "positive" : "negative"} className="px-3 py-1 text-base">{recommendationLabel(txn.recommendation)}</Badge>
                          <span className="text-sm text-text-muted">{txn.failed_checks.length} failed {txn.failed_checks.length === 1 ? "check" : "checks"}</span>
                        </> : <Badge>Not evaluated</Badge>}
                      </div>
                    </div>
                  </button>
                </li>;
              })}
            </ul>
          </div> : <div id="audit-panel" role="tabpanel" aria-labelledby="audit-tab" className="min-h-0 flex-1 overflow-y-auto p-5">
            <AuditPanel events={audit.data?.events ?? []} loading={audit.isLoading} error={audit.error?.message ?? verify.error?.message} focusTxnId={focusedTxnId}
              verification={verify.data} verifying={verify.isPending} onVerify={() => verify.mutate()} principals={people} />
          </div>}
        </section>
      </main>
      <ChecksDialog open={checksOpen} evaluation={evaluation.data} loading={Boolean(evalId) && evaluation.isPending}
        error={evaluation.error?.message ?? (checksOpen && !evalId ? "This transaction has no evaluation yet. Close this dialog and use Evaluate queue to retry." : null)}
        busy={decision.isPending} decisionError={decision.error?.message} principals={people} principalId={principalId} onPrincipalChange={changePrincipal}
        onClose={() => setChecksOpen(false)} onReferences={openReferences} onDecide={(verdict, comments) => { if (evalId) decision.mutate({ evaluationId: evalId, verdict, comments }); }} />
      <ReferencesDialog open={Boolean(reference)} references={references.data} loading={references.isPending} error={references.error?.message} onClose={() => setReference(null)} />
    </div>
  );
}
