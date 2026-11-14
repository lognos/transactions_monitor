# Policy & Validation Agent (`backend/app/`)

Modular LangGraph policy evaluation & human-in-the-loop review engine for Canadian banking transactions (`wire`, `cheque`, `interac`), backed by MongoDB Atlas and deterministic Python compliance rules.

## Quick Handoff Guide (Integrating into a Broader LangGraph)

### 1. Subgraph Entrypoints (`app.graphs`)

Import the compiled subgraphs or builders directly:

```python
from app.graphs import (
    evaluate_graph,        # Compiled StateGraph[EvalState]
    review_graph,          # Compiled StateGraph[ReviewState]
    build_evaluate_graph,  # Re-compilable factory (e.g. to attach a checkpointer)
    build_review_graph,    # Re-compilable factory
    EvalState,
    ReviewState,
)
```

#### Composing as Subgraph Nodes in a Parent `StateGraph`
Because `EvalState` and `ReviewState` are standard `TypedDict` schemas, you can mount them directly:

```python
parent = StateGraph(ParentState)
parent.add_node("policy_evaluate", evaluate_graph)
parent.add_node("policy_review", review_graph)
```

#### Direct Invocation
```python
# 1) Evaluate a pending transaction
eval_out = await evaluate_graph.ainvoke({
    "txn_id": "TXN-0001",
    "principal_id": "ana",
})
evaluation = eval_out["evaluation"]

# 2) Ask a question about the evaluation
ask_out = await review_graph.ainvoke({
    "eval_id": evaluation["eval_id"],
    "principal_id": "ana",
    "input": {"kind": "question", "question": "Why did C-04 fail?"},
})

# 3) Submit a human decision (enforces policy gate + learns adjustments)
decide_out = await review_graph.ainvoke({
    "eval_id": evaluation["eval_id"],
    "principal_id": "ana",
    "input": {
        "kind": "decision",
        "verdict": "approved",
        "comments": "Payroll customers spike at month-end, that is normal.",
    },
})
```

---

### 2. Module Map

| File | Responsibility |
| --- | --- |
| `models.py` | Domain literals, HTTP schemas, and LLM structured outputs (`RecommendOutput`, `AnswerOutput`, `LearnOutput`) |
| `llm.py` | Temperature-0 chat model factory (`get_chat_model`, `get_structured_llm`) supporting OpenAI & Gemini + LangSmith |
| `prompts.py` | Prompt templates isolating untrusted `memo`/`counterparty` fields and prioritizing active adjustments |
| `checks.py` | Deterministic `hard` compliance checks (`CHECKS` registry) |
| `memory.py` | Atlas Vector Search (`search_memory`), structured query builder (`build_structured_query`), and `active_adjustments` |
| `graphs/evaluate.py` | `load -> run_checks -> retrieve_context -> recommend -> save_evaluation` |
| `graphs/review.py` | `load_review -> (answer_question \| policy_gate -> record_denied \| record_decision -> learn_from_feedback -> store_precedent)` |
| `graphs/_deps.py` | Bridge to DB-lane `app.audit` (`write_with_audit`, `verify_chain`) and `app.gate` (`check_gate`) with contract-compliant fallbacks |
| `main.py` | FastAPI HTTP surface (`docs/contracts.md` §4) |

---

### 3. Environment & Running Locally

Set in `.env` (never commit `.env`):
- `MONGODB_URI` (or `.local` fallback) and `DB_NAME=txn_validation`
- `OPENAI_API_KEY` or `GOOGLE_API_KEY` / `GEMINI_API_KEY` (optional `LLM_PROVIDER`, `LLM_MODEL`)
- Optional LangSmith tracing: `LANGSMITH_TRACING=true`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT`

Run the API from `backend/`:
```bash
uvicorn app.main:app --reload --port 8000
```

---

### 4. Architectural Invariants Preserved

1. **Deterministic Hard Checks:** `hard` criteria are evaluated strictly in Python (`checks.py`), and the overall `recommendation` is computed in Python (`save_evaluation`).
2. **Untrusted Data Isolation:** `memo` and `counterparty` fields are excluded from vector queries (`build_structured_query`) and wrapped in `<untrusted_transaction_data>` tags in prompts.
3. **Memory Scope Guard:** `learn_from_feedback` discards any adjustment not targeting a `judgment` criterion.
4. **Grounded Citations:** `save_evaluation` and `answer_question` strip any memory/criterion IDs not present in the retrieved context.
5. **Audit Trail:** All writes go through `write_with_audit` (`graphs/_deps.py` automatically switches to `app.audit` / `app.gate` once merged).
