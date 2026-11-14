"use client";

// Shell only: header with the "acting as" dropdown, the queue, and an empty
// review panel. Views to build are listed in docs/plan-ui.md.

import { useQuery } from "@tanstack/react-query";
import { ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { Badge, Select } from "@/components/ui";
import { api, setPrincipal } from "@/lib/api";
import { cn } from "@/lib/cn";

export default function Home() {
  const [actingAs, setActingAs] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const health = useQuery({ queryKey: ["health"], queryFn: api.health });
  const principals = useQuery({ queryKey: ["principals"], queryFn: api.principals });
  const people = principals.data?.principals ?? [];
  const principalId = actingAs || people[0]?._id || "";

  useEffect(() => {
    setPrincipal(principalId || null);
  }, [principalId]);

  const queue = useQuery({
    queryKey: ["transactions", principalId],
    queryFn: () => {
      setPrincipal(principalId);
      return api.transactions();
    },
    enabled: Boolean(principalId),
  });
  const transactions = queue.data?.transactions ?? [];
  const error = principals.error ?? queue.error;

  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex items-center gap-4 border-b border-border-subtle bg-surface-1 px-5 py-3">
        <ShieldCheck className="size-5 text-accent-fg" aria-hidden="true" />
        <h1 className="mr-auto text-base font-medium">Transaction Validation</h1>
        <Badge tone={health.data?.ok ? "positive" : health.isPending ? "neutral" : "negative"}>
          {health.isPending ? "checking…" : health.data?.ok ? `db: ${health.data.db}` : "backend unreachable"}
        </Badge>
        <label className="flex items-center gap-2 text-sm font-light text-text-muted">
          Acting as
          <Select id="acting-as" value={principalId} onChange={(e) => setActingAs(e.target.value)}>
            {people.length === 0 && <option value="">no principals seeded</option>}
            {people.map((p) => (
              <option key={p._id} value={p._id}>
                {p.name} · {p.role}
              </option>
            ))}
          </Select>
        </label>
      </header>

      {error && (
        <div className="border-b border-status-negative-border bg-status-negative-bg px-5 py-2 text-sm text-status-negative-fg">
          {error.message}
        </div>
      )}

      <main className="grid flex-1 grid-cols-[320px_1fr]">
        <aside className="border-r border-border-subtle p-4">
          <h2 className="mb-3 text-xs font-medium tracking-wider text-text-subtle uppercase">Queue</h2>
          {transactions.length === 0 && (
            <p className="text-sm font-light text-text-subtle">No transactions yet.</p>
          )}
          <ul className="flex flex-col gap-1.5">
            {transactions.map((t) => (
              <li key={t.txn_id}>
                <button
                  type="button"
                  onClick={() => setSelectedId(t.txn_id)}
                  className={cn(
                    "grid w-full grid-cols-[auto_1fr_auto] items-center gap-3 rounded-md border px-3 py-2 text-left text-sm transition-colors",
                    "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-border-focus",
                    selectedId === t.txn_id
                      ? "border-accent bg-accent-subtle text-text-default"
                      : "border-border-subtle text-text-muted hover:bg-surface-2",
                  )}
                >
                  <span className="font-mono text-xs">{t.txn_id}</span>
                  <span className="font-light">{t.type}</span>
                  <span>
                    {t.currency} {t.amount.toLocaleString()}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </aside>

        <section className="p-6">
          <p className="text-sm font-light text-text-subtle">
            {selectedId ? (
              <>
                TODO: review card for <span className="font-mono">{selectedId}</span> (evaluate, checklist,
                questions, decision buttons).
              </>
            ) : (
              "Select a transaction to evaluate it."
            )}
          </p>
        </section>
      </main>
    </div>
  );
}
