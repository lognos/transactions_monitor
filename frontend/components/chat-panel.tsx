"use client";

import { Bot, LoaderCircle, MessageSquare, Send, X } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Badge, Button } from "@/components/ui";
import { cn } from "@/lib/cn";
import type { Citation } from "@/lib/types";

export interface ChatMessage {
  id: string;
  role: "user" | "agent";
  text: string;
  citations?: Citation[];
  txnId?: string;
  evaluationId?: string;
  author?: string;
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
    <section id="chat-pane" aria-labelledby="chat-heading" className="flex h-full min-h-0 flex-col bg-surface-1/40">
      <div className="flex items-center gap-3 border-b border-border-subtle px-5 py-4">
        <MessageSquare className="size-5 text-accent-fg" aria-hidden="true" />
        <h2 id="chat-heading" className="text-sm font-semibold tracking-wider uppercase">Chat</h2>
        <span className="ml-auto text-sm text-text-subtle">Validation agent</span>
      </div>

      <div role="log" aria-label="Conversation with validation agent" aria-live="polite" aria-relevant="additions text" className="min-h-48 flex-1 space-y-5 overflow-y-auto p-5">
        {messages.length === 0 && (
          <div className="my-8 space-y-3 rounded-xl border border-border-subtle bg-surface-1 p-5">
            <Bot className="size-7 text-accent-fg" aria-hidden="true" />
            <p className="text-lg font-medium">Follow the reasoning.</p>
            <p className="text-base text-text-muted">Ask about a policy, or open a transaction to discuss its checks and the decisions behind them.</p>
          </div>
        )}
        {messages.map((message) => (
          <article key={message.id} className={cn("space-y-2 rounded-xl border p-4", message.role === "user" ? "ml-6 border-border-subtle bg-surface-2" : "mr-3 border-accent/30 bg-accent-subtle")}>
            <div className="flex flex-wrap items-center gap-2 text-sm">
              {message.role === "agent" && <Bot className="size-4 text-accent-fg" aria-hidden="true" />}
              <span className="font-semibold">{message.author || (message.role === "agent" ? "Agent" : "You")}</span>
              {message.txnId && <span className="font-mono text-xs text-text-subtle">{message.txnId}</span>}
            </div>
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

      <div className="space-y-3 border-t border-border-subtle bg-surface-1 p-4">
        {focus ? (
          <div className="flex items-center gap-2 text-sm">
            <span className="text-text-muted">About:</span>
            <button type="button" onClick={onClearFocus} aria-label={`Clear focus on ${focus.txnId}`} className="inline-flex items-center gap-2 rounded-md border border-status-info-border bg-status-info-bg px-2.5 py-1 text-status-info-fg focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-border-focus">
              <span className="font-mono">{focus.txnId}</span><X className="size-4" aria-hidden="true" />
            </button>
          </div>
        ) : <p className="text-sm text-text-muted">General conversation · policies and memory</p>}
        {error && <p role="alert" className="rounded-md border border-status-negative-border bg-status-negative-bg px-3 py-2 text-sm text-status-negative-fg">{error}</p>}
        <form onSubmit={send} className="flex items-end gap-2">
          <label htmlFor="chat-question" className="sr-only">Ask the validation agent</label>
          <textarea ref={input} id="chat-question" value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
              event.preventDefault();
              event.currentTarget.form?.requestSubmit();
            }
          }} rows={2} disabled={disabled} placeholder={focus ? `Ask about ${focus.txnId}…` : "Ask about a policy…"} className="min-h-16 min-w-0 flex-1 resize-none rounded-lg border border-border-default bg-surface-base px-3 py-2 text-base placeholder:text-text-subtle focus-visible:outline-2 focus-visible:outline-border-focus disabled:opacity-50" />
          <Button type="submit" disabled={busy || disabled || !draft.trim()} aria-label="Send question" className="h-12 w-12 shrink-0 rounded-lg p-0">
            {busy ? <LoaderCircle className="size-5 animate-spin" aria-hidden="true" /> : <Send className="size-5" aria-hidden="true" />}
          </Button>
        </form>
        <p className="text-xs text-text-subtle">Enter to send · Shift + Enter for a new line</p>
      </div>
    </section>
  );
}
