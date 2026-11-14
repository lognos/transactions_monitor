"use client";

import { ArrowUp, LoaderCircle, Mic, Square, X } from "lucide-react";
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
  draft?: string;
  onDraftChange?: (value: string) => void;
  focusInputSignal?: number;
  onClearFocus: () => void;
  onSend: (message: string) => void;
  onTranscribe?: (audio: Blob) => Promise<{ text: string }>;
  onCitation: (criterionId: string) => void;
}

type VoiceState = "idle" | "recording" | "transcribing";

function pickAudioMimeType(): string | undefined {
  if (typeof MediaRecorder === "undefined" || typeof MediaRecorder.isTypeSupported !== "function") return undefined;
  return ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"]
    .find((type) => MediaRecorder.isTypeSupported(type));
}

function formatDuration(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins}:${secs.toString().padStart(2, "0")}`;
}

export function ChatPanel({
  messages,
  focus,
  busy,
  disabled = false,
  error,
  draft: controlledDraft,
  onDraftChange,
  focusInputSignal,
  onClearFocus,
  onSend,
  onTranscribe,
  onCitation,
}: ChatPanelProps) {
  const [uncontrolledDraft, setUncontrolledDraft] = useState("");
  const draft = controlledDraft ?? uncontrolledDraft;
  const setDraft = (next: string | ((prev: string) => string)) => {
    const value = typeof next === "function" ? next(draft) : next;
    if (onDraftChange) onDraftChange(value);
    else setUncontrolledDraft(value);
  };
  const [voiceState, setVoiceState] = useState<VoiceState>("idle");
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    bottom.current?.scrollIntoView({ block: "nearest", behavior: "instant" });
  }, [messages, busy]);

  useEffect(() => {
    if (focusInputSignal) input.current?.focus();
  }, [focusInputSignal]);

  useEffect(() => {
    return () => {
      if (timerRef.current !== null) window.clearInterval(timerRef.current);
      if (recorderRef.current && recorderRef.current.state !== "inactive") recorderRef.current.stop();
      streamRef.current?.getTracks().forEach((track) => track.stop());
    };
  }, []);

  function stopStream() {
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  }

  async function toggleVoice() {
    if (!onTranscribe || busy || disabled || voiceState === "transcribing") return;

    if (voiceState === "recording") {
      recorderRef.current?.stop();
      return;
    }

    if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setVoiceError("Voice recording is not supported in this browser.");
      return;
    }

    setVoiceError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const mimeType = pickAudioMimeType();
      const recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
      recorderRef.current = recorder;
      chunksRef.current = [];

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };

      recorder.onstop = async () => {
        stopStream();
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" });
        chunksRef.current = [];
        recorderRef.current = null;

        if (blob.size === 0) {
          setVoiceState("idle");
          setVoiceError("No audio was captured. Please try again.");
          return;
        }

        setVoiceState("transcribing");
        try {
          const { text } = await onTranscribe(blob);
          const cleaned = text.trim();
          if (!cleaned) {
            setVoiceError("No speech detected in the recording.");
          } else {
            setDraft((prev) => (prev.trim() ? `${prev.trim()} ${cleaned}` : cleaned));
            input.current?.focus();
          }
        } catch (err) {
          setVoiceError(err instanceof Error ? err.message : "Could not transcribe audio.");
        } finally {
          setVoiceState("idle");
        }
      };

      recorder.onerror = () => {
        stopStream();
        recorderRef.current = null;
        setVoiceState("idle");
        setVoiceError("Microphone recording failed.");
      };

      setRecordingSeconds(0);
      setVoiceState("recording");
      recorder.start();
      timerRef.current = window.setInterval(() => setRecordingSeconds((s) => s + 1), 1000);
    } catch {
      stopStream();
      setVoiceState("idle");
      setVoiceError("Microphone access was denied or unavailable.");
    }
  }

  function send(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const message = draft.trim();
    if (!message || busy || disabled || voiceState !== "idle") return;
    onSend(message);
    setDraft("");
    input.current?.focus();
  }

  const activeError = voiceError || error;

  return (
    <section id="chat-pane" aria-label="Chat with the validation agent" className="flex h-full min-h-0 flex-col bg-surface-1/40">

      <div role="log" aria-label="Conversation with validation agent" aria-live="polite" aria-relevant="additions text" className="min-h-48 flex-1 space-y-5 overflow-y-auto p-5">
        {messages.map((message) => (
          <article key={message.id} aria-label={message.role === "user" ? "Your message" : "Agent response"}
            className={cn("space-y-2", message.role === "user"
              ? "ml-auto w-fit max-w-[calc(100%-1.5rem)] rounded-2xl border border-border-subtle bg-surface-2 px-4 py-3"
              : "py-2")}>
            {message.txnId && <p className="font-mono text-xs text-text-subtle">{message.txnId}</p>}
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
        {activeError && <p role="alert" className="rounded-md border border-status-negative-border bg-status-negative-bg px-3 py-2 text-sm text-status-negative-fg">{activeError}</p>}
        {voiceState !== "idle" && (
          <p role="status" className="flex items-center gap-2 text-xs text-text-muted">
            {voiceState === "recording" ? (
              <>
                <span aria-hidden="true" className="size-2 animate-pulse rounded-full bg-status-negative-fg" />
                Recording {formatDuration(recordingSeconds)} · Click stop to transcribe with ElevenLabs
              </>
            ) : (
              <>
                <LoaderCircle className="size-3.5 animate-spin" aria-hidden="true" />
                Transcribing speech…
              </>
            )}
          </p>
        )}
        <form onSubmit={send} className="rounded-[28px] border border-border-default bg-surface-2 p-3 shadow-sm transition-colors focus-within:border-border-focus">
          <label htmlFor="chat-question" className="sr-only">Ask the validation agent</label>
          <textarea ref={input} id="chat-question" value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
              event.preventDefault();
              event.currentTarget.form?.requestSubmit();
            }
          }} rows={2} disabled={disabled || voiceState === "transcribing"} placeholder={focus ? `Ask about ${focus.txnId}…` : "Ask about a policy…"} className="block min-h-16 max-h-48 w-full min-w-0 resize-none overflow-y-auto border-0 bg-transparent px-2 py-2 text-base leading-relaxed text-text-default placeholder:text-text-subtle focus:outline-none disabled:opacity-50 [field-sizing:content]" />
          <div className="mt-2 flex items-center justify-end gap-2">
            {onTranscribe && (
              <Button
                type="button"
                variant={voiceState === "recording" ? "danger" : "ghost"}
                disabled={busy || disabled || voiceState === "transcribing"}
                onClick={toggleVoice}
                aria-label={voiceState === "recording" ? "Stop recording" : voiceState === "transcribing" ? "Transcribing audio" : "Ask by voice (ElevenLabs)"}
                title={voiceState === "recording" ? "Stop recording" : "Voice input (ElevenLabs Speech-to-Text)"}
                className="h-10 w-10 shrink-0 rounded-full p-0"
              >
                {voiceState === "recording" ? (
                  <Square className="size-4 fill-current" aria-hidden="true" />
                ) : voiceState === "transcribing" ? (
                  <LoaderCircle className="size-5 animate-spin" aria-hidden="true" />
                ) : (
                  <Mic className="size-5" aria-hidden="true" />
                )}
              </Button>
            )}
            <Button type="submit" disabled={busy || disabled || voiceState !== "idle" || !draft.trim()} aria-label="Send question" className="h-10 w-10 shrink-0 rounded-full bg-text-default p-0 text-surface-base hover:bg-text-default hover:opacity-80 disabled:opacity-35">
              {busy ? <LoaderCircle className="size-5 animate-spin" aria-hidden="true" /> : <ArrowUp className="size-5" strokeWidth={2.5} aria-hidden="true" />}
            </Button>
          </div>
        </form>
      </div>
    </section>
  );
}
