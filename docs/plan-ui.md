# Plan 2 — UI

Owner: buddybud24. Request and response shapes come from [contracts.md](contracts.md) §4.

## Goal

One page, three views, no login. It has to make five scenarios readable from the back of a room in three minutes.

Done when all five scenarios in [plan-scenarios.md](plan-scenarios.md) can be clicked through without touching anything but the page.

## Stack

Recommended: Vite + React, plain CSS, `fetch`. No router, no state library, no component kit.
The owner can swap this for whatever they are fastest in. The contract is the HTTP API, not the framework.

## Layout

```
┌──────────────────────────────────────────────────────────────────────┐
│ Transaction Validation          Acting as: [ Ana · analyst      ▾ ]  │
├───────────────┬──────────────────────────────────────────────────────┤
│ QUEUE         │ TXN-0002 · Wire · CAD 12,000        Agent: NO-PASS   │
│ TXN-0001  ●   │ Customer · counterparty · memo                       │
│ TXN-0002  ●   │ ──────────────────────────────────────────────────── │
│ TXN-0003  ●   │ C-01  Sanctions screening            rule   PASS     │
│ TXN-0004  ●   │ W-01  Beneficiary info complete      rule   NO-PASS  │
│ TXN-0005  ●   │ C-04  Consistent with profile        LLM    NO-PASS  │
│               │        evidence · precedents · adjustments used      │
│ [Queue|Audit] │ ──────────────────────────────────────────────────── │
│               │ Rationale                                            │
│               │ Ask a question [______________________] [Ask]        │
│               │ thread…                                              │
│               │ [Validate] [Validate with comments] [Reject…]        │
└───────────────┴──────────────────────────────────────────────────────┘
```

## Views

| View | Shows | API calls |
| --- | --- | --- |
| **Header** | App name, "Acting as" dropdown. The selected id is sent as `X-Principal-Id` on every call | `GET /principals` |
| **Queue** | Transactions with id, type, amount, status dot. Clicking one evaluates it, or reloads its evaluation if it has one | `GET /transactions`, `POST /transactions/{id}/evaluate`, `GET /evaluations/{id}` |
| **Review card** | Transaction summary, recommendation pill, one row per check, rationale, question box and thread, three decision buttons | `POST /evaluations/{id}/ask`, `POST /evaluations/{id}/decide` |
| **Audit** | Timeline of events for the selected transaction (who, on whose behalf, event, key detail, short hash) and a "Verify chain" button with a pass or fail banner | `GET /audit?txn_id=`, `GET /audit/verify` |

## Details that carry the demo

- **Check rows:** criterion id in monospace, description, a `rule` or `LLM` tag, and a `PASS` / `NO-PASS` / `FLAG` pill. Evidence on a second line.
- **Adjustments used:** when a check lists `adjustments_used`, show the adjustment text and its author on the row ("Learned from ana, 14:10"). This is the proof moment in scenario 3, so make it obvious.
- **Decision buttons:** "Validate with comments" and "Reject with comments" open a text box; the submit button stays disabled until there is text.
- **After a decision:** show the new status and, if `memory_created` contains an adjustment, a banner with its text ("Memory updated: …").
- **Gate denial (403):** a red banner with `error.message`. Leave the card open so the presenter can switch to the supervisor and retry.
- **Loading:** evaluating takes a few seconds. Show a spinner on the card, not a blank page.
- **Verify chain:** green banner "Chain intact, N events" or red banner "Broken at event #12".
- Font size large enough to project. No dark-on-dark.

## Steps

| When | Step | Check |
| --- | --- | --- |
| 0:00–0:20 | Agree contracts. Scaffold the app. Copy the example JSON from contracts §4 into a local fixture file | Page renders from fixtures |
| 0:20–1:10 | Header with dropdown, queue, review card with check rows, all from fixtures | Card looks right for a pass and a no-pass fixture |
| 1:10–1:30 | Switch queue and evaluate to the real API | **Checkpoint 1:** "Clean pass" evaluates from the page |
| 1:30–2:00 | Decision buttons, comment box, 403 banner, status refresh | "Over the limit" shows the denial |
| 2:00–2:30 | Adjustment display on check rows and the "Memory updated" banner | **Checkpoint 2:** "The agent learns" reads clearly |
| 2:30–2:50 | Question box and thread | Answer shows with citations |
| 2:50–3:15 | Audit tab and "Verify chain" | Scenario 5 runs |
| 3:15+ | Fixes only. Check it on the projector resolution | — |

## Working without the backend

Build against the fixture file first. Keep one function per API call in a single `api.js`, each returning the fixture until its endpoint exists, so switching to the real API is a one-line change per call. The backend must allow the UI's origin (CORS) or the UI proxies `/api` to port 8000.

## Cut order

1. Question thread styling (plain text is fine).
2. Audit timeline (show `audit_log` in Atlas instead). Keep the "Verify chain" button.
3. "Reject with comments" (not needed by any scenario beyond scenario 2, where plain reject with a short comment is enough).
