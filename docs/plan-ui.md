# Plan 2 — UI and server

Owner: Facundo. Request and response shapes come from [contracts.md](contracts.md) §4.

> **Proposed, not agreed yet:** decisions become Approve / Reject, and reviewers can override individual checks. See [contracts.md §8](contracts.md#8-check-overrides-and-decisions). Until the team confirms, this plan stands as written.

This lane owns both sides of the HTTP contract: `frontend/` and the FastAPI routes in `backend/app/server/`. The server is thin: it reads MongoDB for lists and lookups and calls the agent through three functions (contracts §5.5).

## Goal

One screen, split in two, that makes five scenarios readable from the back of a room in three minutes:
- **Left: chat** with the agent.
- **Right: artifacts**, the list of transactions with the agent's recommendation for each.

Clicking a transaction opens its details in a panel under the list, in the same right-hand pane: summary, checklist, rationale and decision buttons. The list stays visible above it, in compact one-line rows. Clicking a pass / no-pass badge opens a dialog that explains why the check got that result (`explanation` and `facts`, contracts §3.5) and shows the policy, learned adjustments and previous decisions behind it.

Note: the layout sketch and the "Checks dialog" rows below predate this change. Read "checks dialog" as the details panel.

Done when all five scenarios in [plan-scenarios.md](plan-scenarios.md) can be clicked through without touching anything but the page.

## Stack

Same libraries and visual style as the LOGNOS ASSIST frontend, scaffolded in `frontend/`:

| Piece | Choice |
| --- | --- |
| Framework | Next.js 16 (App Router), React 19, TypeScript |
| Styling | Tailwind CSS 4, tokens in `app/globals.css` (surface, border, text, accent and status roles; dark by default) |
| Fonts | Inter and Roboto Mono through `next/font` |
| Helpers | `clsx` + `tailwind-merge` (`lib/cn.ts`), `lucide-react` icons, TanStack Query for data fetching |
| UI components | `components/ui/`: `Button`, `Badge`, `Select` exist. `Dialog` is to be written |

Already in place: `lib/api.ts` (one typed function per HTTP call), `lib/types.ts` (contract shapes), and `app/page.tsx` with the header, the "acting as" dropdown, the connection badge and a simple queue. The page layout is replaced by the split below.

Hackathon rule: the look follows ASSIST, but every file here is written at the event. Do not copy component or stylesheet files from the ASSIST repository. New components use the semantic token classes (`bg-surface-1`, `text-text-muted`, `border-border-subtle`, `bg-status-positive-bg`), never raw colours.

Badge mapping: `pass` → `positive`, `no_pass` → `negative`, `flag` → `attention`, `rule` tag → `neutral`, `LLM` tag → `info`.

## Layout

```
┌────────────────────────────────────────────────────────────────────────────┐
│ Transaction Validation        db: ok     Acting as: [ Ana · analyst    ▾ ] │
├───────────────────────────────┬────────────────────────────────────────────┤
│ CHAT                          │ ARTIFACTS   [Transactions] [Audit]         │
│                               │                           [Evaluate queue] │
│ Ana: Why did TXN-0002 fail?   │ TXN-0001  Wire    CAD  4,000   PASS        │
│                               │ TXN-0002  Wire    CAD 12,000   NO-PASS ·2  │
│ Agent: W-01 failed because…   │ TXN-0003  Cheque  CAD  9,000   NO-PASS ·1  │
│   [W-01] [MEM-11aa]           │ TXN-0004  Cheque  CAD  9,400   NO-PASS ·1  │
│                               │ TXN-0005  Wire    CAD 60,000   PASS        │
│ About: TXN-0002  ✕            │                                            │
│ [ Ask a question…      ] [▶]  │                                            │
└───────────────────────────────┴────────────────────────────────────────────┘

Click a row ─► Checks dialog                Click a badge ─► References dialog
┌──────────────────────────────────────┐    ┌──────────────────────────────────┐
│ TXN-0004 · Cheque · CAD 9,400   PASS │    │ C-04 · Consistent with profile   │
│ customer · counterparty · memo       │    │ PASS · LLM                       │
│ C-01 Sanctions screening  rule [PASS]│    │ Policy: cheque v1, judgment,     │
│ Q-01 Cheque date valid    rule [PASS]│    │   FINTRAC suspicious-txn…        │
│ C-04 Consistent w/ profile LLM [PASS]│    │ Learned adjustments              │
│      evidence…                       │    │   "Payroll customers spike…"     │
│ Rationale…                           │    │   Ana · from TXN-0003 · 14:10    │
│ [Validate] [Validate w/ comments]    │    │ Previous decisions               │
│ [Reject w/ comments]                 │    │   Cheque 8,400 … validated (sam) │
└──────────────────────────────────────┘    └──────────────────────────────────┘
```

## Views

| View | Shows | API calls |
| --- | --- | --- |
| **Header** | App name, connection badge, "acting as" dropdown. The selected id is sent as `X-Principal-Id` on every call | `GET /health`, `GET /principals` |
| **Chat (left)** | Message list and input. Agent answers show citation chips. A "About: TXN-…" chip shows the transaction in focus and can be cleared | With a transaction in focus: `POST /evaluations/{id}/ask`. With none: `POST /chat` |
| **Transactions (right)** | One row per transaction: id, type, amount, customer, status, recommendation badge, count of failed checks. "Evaluate queue" button | `GET /transactions`, `POST /transactions/evaluate-pending` |
| **Audit (right, second tab)** | Timeline of audit events (who, on whose behalf, event, key detail, short hash), filterable to the transaction in focus, and a "Verify chain" button with a pass or fail banner | `GET /audit`, `GET /audit/verify` |
| **Checks dialog** | Transaction summary, recommendation, one row per check (id, description, `rule` / `LLM` tag, clickable result badge, evidence), rationale, the three decision buttons | `GET /evaluations/{id}`, `POST /evaluations/{id}/decide` |
| **References dialog** | For one check: the policy criterion and regulation reference, learned adjustments with their author, previous decisions used as precedents | `GET /evaluations/{id}/checks/{criterion_id}/references` |

## Behaviour that carries the demo

- **List shows recommendations.** On load, if any transaction is `pending`, call evaluate-pending and show a per-row spinner until it returns. The "Evaluate queue" button does the same on demand.
- **Focus.** Opening a transaction's checks dialog puts it in focus for the chat. Closing the dialog keeps the focus, so the presenter can ask about it. The chip in the chat clears it.
- **Citation chips in chat** open the same references dialog when they point at a check's criterion, so chat and checklist lead to the same evidence.
- **Decisions.** "Validate with comments" and "Reject with comments" open a text box in the dialog; submit stays disabled until there is text.
- **After a decision** that creates an adjustment: show a "Memory updated" banner with its text, then call evaluate-pending with `refresh: true`. Rows whose recommendation changed get a visible highlight. This is the proof moment in scenario 3: TXN-0004 flips from NO-PASS to PASS.
- **Learned adjustments are loud.** In the references dialog, an adjustment shows its text, "Learned from Ana", the source transaction and the time. In the checks dialog, a check that used an adjustment gets a small "learned" marker next to its badge.
- **Gate denial (403).** A red banner inside the checks dialog with the server's message. The dialog stays open so the presenter can switch to the supervisor and retry.
- **Stacked dialogs.** The references dialog opens on top of the checks dialog. Escape closes the top one only. Focus returns to the badge that opened it.
- **Verify chain.** Green banner "Chain intact, N events" or red banner "Broken at event #12".
- Text large enough to project.

## Server work

| Step | Detail |
| --- | --- |
| `GET /transactions` | Add `customer_name`, `counterparty_name`, `eval_id`, `recommendation`, `failed_checks` from the latest evaluation that is not superseded. One aggregation, not a lookup per row |
| `POST /transactions/evaluate-pending` | New. Run `run_evaluate` concurrently for pending transactions (and awaiting-review ones when `refresh` is true). Collect per-transaction failures instead of failing the whole call. Compute `changed` |
| `POST /transactions/{id}/evaluate` | Add `?refresh=true` |
| `GET /evaluations/{id}/checks/{criterion_id}/references` | New, read-only. Join the check with its policy criterion, the memory documents it used, and the source decisions |
| `POST /chat` | New. Calls `run_chat`. Add citation labels |
| `POST /evaluations/{id}/ask` | Add citation labels |
| `POST /evaluations/{id}/decide` | Reviewer-readable 403 message |

## Steps

| When | Step | Check |
| --- | --- | --- |
| 0:00–0:20 | Agree contracts. Fixtures from contracts §4 for all five scenarios | Page renders from fixtures |
| 0:20–1:00 | Split layout, transactions list with recommendation badges, `Dialog` component, checks dialog | List and dialog look right for a pass and a no-pass fixture |
| 1:00–1:30 | Server: list fields and evaluate-pending. Switch the list to the real API | **Checkpoint 1:** "Clean pass" from the page |
| 1:30–2:00 | Decision buttons, comment box, 403 banner. Server: 403 message | "Over the limit" shows the denial |
| 2:00–2:30 | References dialog and its server route. Refresh after a decision, changed-row highlight | **Checkpoint 2:** "The agent learns" reads clearly |
| 2:30–2:50 | Chat panel: focused questions, then general chat. Citation chips | Answer shows with citations |
| 2:50–3:15 | Audit tab and "Verify chain" | Scenario 5 runs |
| 3:15+ | Fixes only. Check it at the projector resolution | — |

## Working without the backend

Build against fixtures first. Each function in `lib/api.ts` can return fixture data until its endpoint works, so switching to the real API is a one-line change per call. `/api/*` is forwarded to port 8010 by `next.config.ts`.

## Cut order

1. General chat with no transaction in focus (disable the input until a transaction is selected).
2. Audit timeline (show `audit_log` in Atlas instead). Keep the "Verify chain" button.
3. Citation chips opening the references dialog (plain text citations).
