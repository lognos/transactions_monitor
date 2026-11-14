"use client";

import { ArrowUp, LoaderCircle, X } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Badge, Button } from "@/components/ui";
import { cn } from "@/lib/cn";
import type { Citation, OverrideReport } from "@/lib/types";

export interface ChatMessage {
  id: string;
  role: "user" | "agent";
  text: string;
  citations?: Citation[];
  txnId?: string;
  evaluationId?: string;
  author?: string;
  override?: OverrideReport | null;
}

export interface ChatPanelProps {
  messages: ChatMessage[];
  focus?: { txnId: string; evaluationId?: string; criterionIds: string[] } | null;
  busy: boolean;
  disabled?: boolean;
  error?: string | null;
  onClearFocus: () => void;
  onSend: (message: string) => void;
  onCitation: (criterionId: string) => void;
}

export function ChatPanel({
  messages,
  focus,
  busy,
  disabled = false,
  error,
  onClearFocus,
  onSend,
  onCitation,
}: ChatPanelProps) {
  const [draft, setDraft] = useState("");
  const bottom = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    bottom.current?.scrollIntoView({ block: "nearest", behavior: "instant" });
  }, [messages, busy]);

  function send(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const message = draft.trim();
    if (!message || busy || disabled) return;
    onSend(message);
    setDraft("");
    input.current?.focus();
  }

  return (
    <section id="chat-pane" aria-label="Chat with the validation agent" className="flex h-full min-h-0 flex-col bg-surface-1/40">

      <div role="log" aria-label="Conversation with validation agent" aria-live="polite" aria-relevant="additions text" className="min-h-48 flex-1 space-y-5 overflow-y-auto p-5">
        {messages.map((message) => (
          <article key={message.id} aria-label={message.role === "user" ? "Your message" : "Agent response"}
            className={cn("space-y-2", message.role === "user"
              ? "ml-auto w-fit max-w-[calc(100%-1.5rem)] rounded-2xl border border-border-subtle bg-surface-2 px-4 py-3"
              : "py-2")}>
            {message.txnId && <p className="font-mono text-xs text-text-subtle">{message.txnId}</p>}
            {message.role === "agent" && message.override && (
              <p className={cn("flex flex-wrap items-center gap-x-2 gap-y-1 border-l-2 py-1 pl-3 text-base font-medium",
                message.override.status === "applied" ? "border-status-info-border text-status-info-fg"
                  : message.override.status === "denied" ? "border-status-negative-border text-status-negative-fg"
                    : "border-status-attention-border text-status-attention-fg")}>
                <span>{message.override.status === "applied" ? "Override applied" : message.override.status === "denied" ? "Override denied" : "Override needs a reason"}</span>
                <span className="font-mono">{message.override.criterion_id}</span>
                <span>{message.override.status === "applied"
                  ? `${message.override.from.replaceAll("_", "-").toUpperCase()} → ${message.override.to.replaceAll("_", "-").toUpperCase()}`
                  : "No check changed"}</span>
              </p>
            )}
            <p className="whitespace-pre-wrap break-words text-base leading-relaxed">{message.text}</p>
            {!!message.citations?.length && (
              <div className="flex flex-wrap gap-2" aria-label="Answer citations">
                {message.citations.map((citation, index) => {
                  const opensReferences = Boolean(focus?.evaluationId && message.evaluationId === focus.evaluationId && message.txnId === focus.txnId && focus.criterionIds.includes(citation.ref));
                  const content = <Badge tone="info" className="max-w-full whitespace-normal break-words text-sm">{citation.ref}{citation.label && <span className="font-normal"> · {citation.label}</span>}</Badge>;
                  return opensReferences ? (
                    <button key={`${citation.type}-${citation.ref}-${index}`} type="button" onClick={() => onCitation(citation.ref)} aria-label={`Open references for ${citation.ref}`} className="max-w-full rounded-md text-left transition-opacity hover:opacity-80 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-border-focus">{content}</button>
                  ) : (
                    <span key={`${citation.type}-${citation.ref}-${index}`} className="max-w-full">{content}</span>
                  );
                })}
              </div>
            )}
          </article>
        ))}
        {busy && <p className="flex items-center gap-2 text-sm text-text-muted" role="status"><LoaderCircle className="size-4 animate-spin" aria-hidden="true" /> Agent is reviewing the context…</p>}
        <div ref={bottom} />
      </div>

      <div className="shrink-0 space-y-3 px-4 pt-2 pb-4">
        {focus && (
          <div className="flex items-center gap-2 text-sm">
            <span className="text-text-muted">About:</span>
            <button type="button" onClick={onClearFocus} aria-label={`Clear focus on ${focus.txnId}`} className="inline-flex items-center gap-2 rounded-md border border-status-info-border bg-status-info-bg px-2.5 py-1 text-status-info-fg focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-border-focus">
              <span className="font-mono">{focus.txnId}</span><X className="size-4" aria-hidden="true" />
            </button>
          </div>
        )}
        {error && <p role="alert" className="rounded-md border border-status-negative-border bg-status-negative-bg px-3 py-2 text-sm text-status-negative-fg">{error}</p>}
        <form onSubmit={send} className="rounded-[28px] border border-border-default bg-surface-2 p-3 shadow-sm transition-colors focus-within:border-border-focus">
          <label htmlFor="chat-question" className="sr-only">Ask the validation agent</label>
          <textarea ref={input} id="chat-question" value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
              event.preventDefault();
              event.currentTarget.form?.requestSubmit();
            }
          }} rows={2} disabled={disabled} placeholder={focus ? `Ask about ${focus.txnId}…` : "Ask about a policy…"} className="block min-h-16 max-h-48 w-full min-w-0 resize-none overflow-y-auto border-0 bg-transparent px-2 py-2 text-base leading-relaxed text-text-default placeholder:text-text-subtle focus:outline-none disabled:opacity-50 [field-sizing:content]" />
          <div className="mt-2 flex justify-end">
            <Button type="submit" disabled={busy || disabled || !draft.trim()} aria-label="Send question" className="h-10 w-10 shrink-0 rounded-full bg-text-default p-0 text-surface-base hover:bg-text-default hover:opacity-80 disabled:opacity-35">
              {busy ? <LoaderCircle className="size-5 animate-spin" aria-hidden="true" /> : <ArrowUp className="size-5" strokeWidth={2.5} aria-hidden="true" />}
            </Button>
          </div>
        </form>
      </div>
    </section>
  );
}
