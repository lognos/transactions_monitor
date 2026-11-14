"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, CheckCheck, FileClock, ListChecks, LoaderCircle, LogOut, RefreshCw, Sparkles, X } from "lucide-react";
import { useEffect, useRef, useState, type CSSProperties } from "react";
import { AuditPanel } from "@/components/audit-panel";
import { ChatPanel, type ChatMessage } from "@/components/chat-panel";
import { ReferencesDialog, TransactionDetails } from "@/components/review-dialogs";
import { MicrosoftLogo, TsxMark } from "@/components/tsx-mark";
import { Badge, Button } from "@/components/ui";
import { api, getApiMode, setPrincipal } from "@/lib/api";
import { cn } from "@/lib/cn";
import type { AskResponse, ChatResponse, CheckResult, Evaluation, MemoryItem, Recommendation, ReferencesResponse, TransactionSummary, Verdict } from "@/lib/types";

const statusLabels = { pending: "Pending", awaiting_review: "Awaiting review", passed: "Passed", rejected: "Rejected" };
const recommendationLabel = (value: Recommendation) => value === "pass" ? "PASS" : "NO-PASS";
const messageOf = (error: unknown) => error instanceof Error ? error.message : "Something went wrong. Please try again.";
type QueueData = { transactions: TransactionSummary[] };
type ChangedRow = { before: Recommendation | null; after: Recommendation };
// Sidebar text is hidden while the rail is collapsed (large screens only).
const reveal = "whitespace-nowrap lg:opacity-0 lg:transition-opacity lg:duration-150 lg:group-hover/side:opacity-100 lg:group-focus-within/side:opacity-100";

export default function Home() {
  const client = useQueryClient();
  // null = logged out. Logging in picks a seeded identity; there are no passwords in this demo.
  const [principalId, setPrincipalId] = useState<string | null>(null);
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
  }, [principalId]); // the split pane only exists while logged in

  function resizeChat(percent: number) {
    const width = splitPane.current?.getBoundingClientRect().width;
    if (width) setChatWidth(Math.max(300 / width * 100, Math.min((width - 430) / width * 100, percent)));
  }

  const health = useQuery({ queryKey: ["health"], queryFn: api.health });
  const principals = useQuery({ queryKey: ["principals"], queryFn: api.principals });
  const people = principals.data?.principals.filter((person) => person.type === "human") ?? [];
  const queue = useQuery({ queryKey: ["transactions"], queryFn: () => api.transactions(), enabled: Boolean(principals.data && principalId) });
  const transactions = queue.data?.transactions ?? [];
  const focusedTxn = transactions.find((txn) => txn.txn_id === focusedTxnId);
  const evalId = focusedTxn?.eval_id;
  const evaluation = useQuery({ queryKey: ["evaluation", evalId], queryFn: () => api.evaluation(evalId!), enabled: Boolean(evalId && principalId) });
  const references = useQuery({
    queryKey: ["references", reference?.evalId, reference?.criterionId],
    queryFn: () => api.references(reference!.evalId, reference!.criterionId), enabled: Boolean(reference && principalId),
  });
  const audit = useQuery({
    queryKey: ["audit", focusedTxnId], queryFn: () => api.audit(focusedTxnId ?? undefined),
    enabled: tab === "audit" && Boolean(principals.data && principalId),
  });
  const verify = useMutation({ mutationFn: api.verifyChain });

  const evaluateQueue = useMutation({
    mutationFn: (refresh: boolean) => api.evaluatePending(refresh),
    onMutate: (refresh) => {
      queueRunning.current = true;
      setQueueError(null);
      verify.reset();
      const before = client.getQueryData<QueueData>(["transactions"])?.transactions ?? [];
      setLoadingRows(before.filter((txn) => txn.status === "pending" || (refresh && txn.status === "awaiting_review" && txn.override_count === 0)).map((txn) => txn.txn_id));
      return { before };
    },
    onSuccess: async (result, _refresh, context) => {
      setChangedRows((previous) => {
        const next = { ...previous };
        for (const item of result.evaluated) {
          if (item.changed) next[item.txn_id] = {
            before: context?.before.find((txn) => txn.txn_id === item.txn_id)?.effective_recommendation ?? null,
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
    if (!principalId || !pending.length || queueRunning.current) return;
    pending.forEach((txn) => autoAttempted.current.add(txn.txn_id));
    queueRunning.current = true;
    evaluate(false);
  }, [queue.data, evaluate, principalId]);

  function applyUpdatedEvaluation(updated: Evaluation) {
    client.setQueryData<Evaluation>(["evaluation", updated.eval_id], updated);
    client.setQueryData<QueueData>(["transactions"], (old) => old ? {
      transactions: old.transactions.map((txn) => txn.txn_id === updated.txn_id ? {
        ...txn,
        eval_id: updated.eval_id,
        status: updated.transaction.status,
        recommendation: updated.recommendation,
        effective_recommendation: updated.effective_recommendation,
        failed_checks: updated.checks.filter((check) => check.effective_result === "no_pass").map((check) => check.criterion_id),
        override_count: updated.checks.filter((check) => check.override !== null).length,
      } : txn),
    } : old);
    client.setQueriesData<ReferencesResponse>({ queryKey: ["references", updated.eval_id] }, (old) => {
      if (!old) return old;
      const check = updated.checks.find((item) => item.criterion_id === old.check.criterion_id);
      return check ? { ...old, check: { ...old.check, result: check.result, effective_result: check.effective_result, override: check.override } } : old;
    });
    setChangedRows((previous) => {
      const next = { ...previous };
      delete next[updated.txn_id];
      return next;
    });
    verify.reset();
    void client.invalidateQueries({ queryKey: ["references", updated.eval_id] });
    void client.invalidateQueries({ queryKey: ["audit"] });
  }

  const override = useMutation({
    mutationFn: ({ evaluationId, criterionId, result, reason }: { evaluationId: string; criterionId: string; result: CheckResult | null; reason?: string }) => api.overrideCheck(evaluationId, criterionId, result, reason),
    onMutate: async ({ evaluationId }) => {
      await Promise.all([
        client.cancelQueries({ queryKey: ["evaluation", evaluationId] }),
        client.cancelQueries({ queryKey: ["transactions"] }),
      ]);
    },
    onSuccess: applyUpdatedEvaluation,
    onError: () => { verify.reset(); void client.invalidateQueries({ queryKey: ["audit"] }); },
  });

  const decision = useMutation({
    mutationFn: ({ evaluationId, verdict, comments }: { evaluationId: string; verdict: Verdict; comments?: string }) => api.decide(evaluationId, verdict, comments),
    onMutate: async ({ evaluationId }) => {
      await Promise.all([
        client.cancelQueries({ queryKey: ["evaluation", evaluationId] }),
        client.cancelQueries({ queryKey: ["transactions"] }),
      ]);
    },
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
      if (result.decision.verdict === "approved" && learned.length) {
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
    mutationFn: async ({ text, evaluationId }: { text: string; evaluationId?: string; txnId?: string }): Promise<AskResponse | ChatResponse> => evaluationId ? api.ask(evaluationId, text) : api.chat(text),
    onSuccess: async (answer, request) => {
      const report = "override" in answer ? answer.override : null;
      if (report?.status === "applied" && "evaluation" in answer && answer.evaluation) {
        await Promise.all([
          client.cancelQueries({ queryKey: ["evaluation", answer.evaluation.eval_id] }),
          client.cancelQueries({ queryKey: ["transactions"] }),
        ]);
        applyUpdatedEvaluation(answer.evaluation);
        decision.reset();
      }
      setMessages((previous) => [...previous, { id: crypto.randomUUID(), role: "agent", text: answer.answer, citations: answer.citations, txnId: request.txnId, evaluationId: request.evaluationId, override: report }]);
      verify.reset();
      void client.invalidateQueries({ queryKey: ["audit"] });
    },
  });

  function logIn(id: string) {
    setPrincipal(id);
    setPrincipalId(id);
    decision.reset();
    override.reset();
  }
  function logOut() {
    setPrincipal(null);
    setPrincipalId(null);
    setChecksOpen(false);
    setReference(null);
    decision.reset();
    override.reset();
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
    if (chat.isPending || override.isPending || decision.isPending || evaluateQueue.isPending || (focusedTxnId && !evalId)) return;
    setMessages((previous) => [...previous, {
      id: crypto.randomUUID(), role: "user", text, txnId: focusedTxnId ?? undefined,
      author: me?.name ?? principalId ?? "",
    }]);
    chat.mutate({ text, evaluationId: evalId ?? undefined, txnId: focusedTxnId ?? undefined });
  }

  const me = people.find((person) => person._id === principalId);
  const mode = getApiMode();
  const error = principals.error ?? queue.error;
  const changedEntries = Object.entries(changedRows);
  const busy = evaluateQueue.isPending || decision.isPending || override.isPending || chat.isPending;
  const detailsOpen = checksOpen && Boolean(focusedTxnId);

  return (
    <div className="flex min-h-screen flex-col lg:h-dvh lg:flex-row lg:overflow-hidden">
      {/* Sidebar: a narrow rail that expands over the content on hover or keyboard focus. */}
      <div className="relative shrink-0 lg:w-14">
      <aside aria-label="Sidebar" className="group/side flex flex-col gap-4 border-b border-border-subtle bg-surface-1 p-4 lg:absolute lg:inset-y-0 lg:left-0 lg:z-30 lg:w-14 lg:overflow-hidden lg:border-r lg:border-b-0 lg:px-2.5 lg:transition-[width,box-shadow] lg:duration-200 lg:hover:w-72 lg:hover:shadow-2xl lg:focus-within:w-72 lg:focus-within:shadow-2xl">
        <h1><TsxMark /></h1>
        <div className="flex flex-col gap-3 lg:mt-auto">
          <div className="flex flex-wrap gap-2 lg:hidden lg:group-hover/side:flex lg:group-focus-within/side:flex">
            {mode !== "backend" && <Badge tone="attention">{mode === "fixtures" ? "Fixture demo" : "Mixed data sources"}</Badge>}
            <Badge tone={health.data?.ok ? "positive" : health.isPending ? "neutral" : "negative"}>
              {health.isPending ? "checking…" : health.data?.ok ? `db: ${health.data.db}` : "backend unreachable"}
            </Badge>
          </div>
          {me ? <>
            <div className="flex items-center gap-3" title={`${me.name} · ${me.role}`}>
              <span aria-hidden="true" className="flex size-9 shrink-0 items-center justify-center rounded-full bg-accent-subtle text-sm font-medium text-accent-fg">{me.name.charAt(0)}</span>
              <div className={cn("min-w-0", reveal)}>
                <p className="truncate text-sm font-medium">{me.name}</p>
                <p className="text-xs text-text-muted capitalize">{me.role}{me.approval_limit != null ? ` · limit CAD ${me.approval_limit.toLocaleString("en-CA")}` : ""}</p>
              </div>
            </div>
            <Button variant="ghost" aria-label="Log out" title="Log out" className="w-full justify-start px-2.5 whitespace-nowrap" disabled={busy} onClick={logOut}>
              <LogOut className="size-4 shrink-0" aria-hidden="true" /><span className={reveal}>Log out</span>
            </Button>
          </> : <p className={cn("text-xs text-text-muted", reveal)}>Not logged in.</p>}
        </div>
      </aside>
      </div>

      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
      {error && <div role="alert" className="border-b border-status-negative-border bg-status-negative-bg px-5 py-3 text-status-negative-fg">{messageOf(error)}</div>}

      {!principalId ? <div className="flex flex-1 items-center justify-center p-6">
        <section aria-labelledby="login-title" className="flex w-full max-w-md flex-col items-center gap-8">
          <TsxMark size="lg" />
          <h2 id="login-title" className="sr-only">Sign in</h2>
          {principals.isPending && <p role="status" className="flex items-center gap-2 text-sm text-text-muted"><LoaderCircle className="size-4 animate-spin" aria-hidden="true" />Loading…</p>}
          {principals.data && !people.length && <p className="text-sm text-text-muted">No identities are seeded yet.</p>}
          <ul className="flex w-full flex-col gap-3">
            {people.map((person) => <li key={person._id}>
              <button type="button" onClick={() => logIn(person._id)}
                className="flex w-full items-center justify-center gap-3 rounded-lg border border-border-default bg-surface-2/50 px-6 py-4 text-sm text-text-default backdrop-blur-sm transition-all duration-200 hover:bg-surface-3/50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-border-focus">
                <MicrosoftLogo className="size-5 shrink-0" />
                <span className="font-light" style={{ fontFamily: "'Helvetica Neue', Helvetica, Arial, sans-serif" }}>
                  Sign in as {person.name}<span className="text-text-muted capitalize"> · {person.role}</span>
                </span>
              </button>
            </li>)}
          </ul>
        </section>
      </div> :
      <main ref={splitPane} style={{ "--chat-width": `${chatWidth}%` } as CSSProperties}
        className={cn("grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[minmax(300px,var(--chat-width))_10px_minmax(420px,1fr)]", resizing && "cursor-col-resize select-none")}>
        <ChatPanel messages={messages} focus={focusedTxnId ? { txnId: focusedTxnId, evaluationId: evalId ?? undefined, criterionIds: evaluation.data?.checks.map((check) => check.criterion_id) ?? [] } : null}
          busy={chat.isPending} disabled={!principals.data || override.isPending || decision.isPending || evaluateQueue.isPending || Boolean(focusedTxnId && (!evalId || loadingRows.includes(focusedTxnId)))} error={chat.error?.message}
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
          <div className="flex flex-wrap items-center gap-3 border-b border-border-subtle px-5 py-2">
            <div role="tablist" aria-label="Artifacts" className="flex gap-1 rounded-lg border border-border-subtle bg-surface-1 p-0.5">
              {(["transactions", "audit"] as const).map((value, index) => {
                const Icon = value === "transactions" ? ListChecks : FileClock;
                return <button key={value} type="button" role="tab" id={`${value}-tab`} aria-controls={`${value}-panel`} aria-selected={tab === value} tabIndex={tab === value ? 0 : -1}
                  onClick={() => setTab(value)} onKeyDown={(event) => {
                    if (["ArrowRight", "ArrowLeft", "Home", "End"].includes(event.key)) {
                      event.preventDefault();
                      const next = event.key === "Home" ? "transactions" : event.key === "End" ? "audit" : index === 0 ? "audit" : "transactions";
                      setTab(next); document.getElementById(`${next}-tab`)?.focus();
                    }
                  }} className={cn("flex items-center gap-2 rounded-md px-3 py-1 text-sm font-medium focus-visible:outline-2 focus-visible:outline-border-focus", tab === value ? "bg-surface-3 text-text-default" : "text-text-muted hover:bg-surface-2")}>
                  <Icon className="size-4" aria-hidden="true" />{value === "transactions" ? "Transactions" : "Audit"}
                </button>;
              })}
            </div>
            {tab === "transactions" && <>
              <p className="ml-auto text-xs text-text-muted">{transactions.length} transactions · {transactions.filter((txn) => txn.status === "awaiting_review").length} awaiting review</p>
              <Button variant="action-sm" disabled={busy || !queue.data} onClick={() => evaluateQueue.mutate(false)}>
                {evaluateQueue.isPending ? <LoaderCircle className="size-3.5 animate-spin" aria-hidden="true" /> : <RefreshCw className="size-3.5" aria-hidden="true" />}
                {evaluateQueue.isPending ? "Evaluating…" : "Evaluate queue"}
              </Button>
            </>}
          </div>
          {tab === "transactions" ? <div id="transactions-panel" role="tabpanel" aria-labelledby="transactions-tab" className="flex min-h-0 flex-1 flex-col">
           {/* List on top; it shrinks to make room when a transaction's details are open below. */}
           <div className={cn("overflow-y-auto px-5 py-3", detailsOpen ? "max-h-[40%] shrink-0" : "min-h-0 flex-1")}>
            {adjustments.length > 0 && <div role="status" className="mb-3 rounded-lg border-2 border-status-positive-border bg-status-positive-bg p-3 text-status-positive-fg">
              <div className="flex items-start justify-between gap-3"><h3 className="flex items-center gap-2 text-lg font-medium"><Sparkles className="size-5" aria-hidden="true" />Memory updated</h3>
                <button type="button" aria-label="Dismiss memory update" onClick={() => { setAdjustments([]); setChangedRows({}); }} className="rounded p-1 focus-visible:outline-2 focus-visible:outline-border-focus"><X className="size-5" /></button></div>
              {adjustments.map((item) => <p key={item.memory_id} className="mt-1 text-sm leading-relaxed">{item.text}</p>)}
              <p className="mt-1 text-sm font-medium">{evaluateQueue.isPending ? "Applying the new guidance to undecided transactions…" : `${changedEntries.length} recommendation${changedEntries.length === 1 ? "" : "s"} changed`}</p>
              {queueError && <Button variant="ghost" className="mt-3" disabled={busy} onClick={() => evaluateQueue.mutate(true)}>Retry applying memory</Button>}
            </div>}
            {queueError && <div role="alert" className="mb-4 rounded-lg border border-status-negative-border bg-status-negative-bg p-4 text-status-negative-fg">{queueError}</div>}
            {changedEntries.length > 0 && <div aria-live="polite" className="mb-4 flex flex-col gap-2">
              {changedEntries.map(([id, change]) => <p key={id} className="flex flex-wrap items-center gap-2 text-base font-medium text-status-positive-fg"><CheckCheck className="size-5" aria-hidden="true" />{id}<span>{change.before ? recommendationLabel(change.before) : "Pending"}</span><ArrowRight className="size-5" aria-label="changed to" />{recommendationLabel(change.after)}</p>)}
            </div>}
            {queue.isLoading && <p role="status" className="flex items-center gap-2 py-8 text-text-muted"><LoaderCircle className="size-5 animate-spin" />Loading transactions…</p>}
            {!queue.isLoading && queue.data && !transactions.length && <p className="rounded-lg border border-border-subtle p-8 text-center text-text-muted">No transactions in the queue.</p>}
            <ul className="space-y-1.5" aria-label="Transactions">
              {transactions.map((txn) => {
                const loading = loadingRows.includes(txn.txn_id);
                const changed = changedRows[txn.txn_id];
                return <li key={txn.txn_id}>
                  <button type="button" disabled={loading || decision.isPending || override.isPending} onClick={() => openTransaction(txn)} aria-busy={loading}
                    aria-expanded={detailsOpen && focusedTxnId === txn.txn_id}
                    className={cn("grid w-full grid-cols-[5.25rem_3.25rem_minmax(0,1fr)_auto_10.5rem] items-center gap-3 rounded-md border px-3 py-1.5 text-left text-sm transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-border-focus disabled:cursor-wait",
                      changed ? "border-2 border-status-positive-border bg-status-positive-bg" : txn.override_count > 0 ? "border-status-info-border bg-status-info-bg" : focusedTxnId === txn.txn_id ? "border-accent bg-accent-subtle" : "border-border-subtle bg-surface-1 hover:bg-surface-2")}>
                    <span className="font-mono text-xs font-medium">{txn.txn_id}</span>
                    <span className="text-xs text-text-muted capitalize">{txn.type}</span>
                    <span className="truncate">{txn.customer_name}<span className="ml-2 text-xs text-text-subtle">{statusLabels[txn.status]}</span></span>
                    <span className="font-medium">{txn.currency} {txn.amount.toLocaleString("en-CA")}</span>
                    <span className="flex flex-col items-end gap-1">
                      {loading ? <span role="status" className="flex items-center gap-1.5 text-xs text-accent-fg"><LoaderCircle className="size-3.5 animate-spin" aria-hidden="true" />Evaluating…</span> : txn.effective_recommendation ? <>
                        <span className="flex items-center gap-2"><span className="text-xs text-text-muted">{changed ? "changed · " : ""}{txn.failed_checks.length} failed</span>
                          <Badge tone={txn.effective_recommendation === "pass" ? "positive" : "negative"}>{recommendationLabel(txn.effective_recommendation)}</Badge></span>
                        {txn.recommendation && txn.effective_recommendation !== txn.recommendation && <span className="text-xs text-text-muted">Agent: <s>{recommendationLabel(txn.recommendation)}</s></span>}
                        {txn.override_count > 0 && <Badge tone="info" size="sm">{txn.override_count} {txn.override_count === 1 ? "override" : "overrides"}</Badge>}
                      </> : <Badge>Not evaluated</Badge>}
                    </span>
                  </button>
                </li>;
              })}
            </ul>
           </div>
           {detailsOpen && <TransactionDetails evaluation={evaluation.data} loading={Boolean(evalId) && evaluation.isPending}
             error={evaluation.error?.message ?? (!evalId ? "This transaction has no evaluation yet. Use Evaluate queue to retry." : null)}
             busy={decision.isPending} overrideBusy={override.isPending || chat.isPending || evaluateQueue.isPending} decisionError={decision.error?.message} principals={people}
             onOverride={async (criterionId, result, reason) => {
               if (!evalId) return;
               decision.reset();
               await override.mutateAsync({ evaluationId: evalId, criterionId, result, reason });
             }}
             onClose={() => setChecksOpen(false)} onReferences={openReferences} onDecide={(verdict, comments) => { if (evalId) decision.mutate({ evaluationId: evalId, verdict, comments }); }} />}
          </div> : <div id="audit-panel" role="tabpanel" aria-labelledby="audit-tab" className="min-h-0 flex-1 overflow-y-auto p-5">
            <AuditPanel events={audit.data?.events ?? []} loading={audit.isLoading} error={audit.error?.message ?? verify.error?.message} focusTxnId={focusedTxnId}
              verification={verify.data} verifying={verify.isPending} onVerify={() => verify.mutate()} principals={people} />
          </div>}
        </section>
      </main>}
      </div>
      <ReferencesDialog open={Boolean(reference)} references={references.data} loading={references.isPending} error={references.error?.message} principals={people} onClose={() => setReference(null)} />
    </div>
  );
}
