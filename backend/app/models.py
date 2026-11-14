"""
backend/app/models.py
Pydantic models for the Policy & Validation Agent.

Covers:
1. Domain enums / literals aligned with `docs/contracts.md` §2.
2. LLM structured output schemas (`RecommendOutput`, `AnswerOutput`, `LearnOutput`)
   used with LangChain `.with_structured_output(...)` (`docs/contracts.md` §6).
3. FastAPI HTTP request/response schemas (`docs/contracts.md` §4).

Note for future integrators:
    These models are the strict boundary between untrusted LLM outputs,
    deterministic Python logic, MongoDB documents, and the HTTP API.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# 1. Domain Literals (docs/contracts.md §2)
# ---------------------------------------------------------------------------

TxnType = Literal["wire", "cheque", "interac"]
TxnStatus = Literal["pending", "awaiting_review", "passed", "rejected"]
CheckKind = Literal["hard", "judgment"]
CheckSource = Literal["rule", "llm"]
CheckResult = Literal["pass", "no_pass", "flag"]
Recommendation = Literal["pass", "no_pass"]
Verdict = Literal["validated", "validated_with_comments", "rejected"]
MemoryKind = Literal["precedent", "adjustment"]
Role = Literal["analyst", "supervisor", "auditor", "agent"]
GateResult = Literal["allow", "deny"]
CitationType = Literal["policy", "precedent", "adjustment"]


# ---------------------------------------------------------------------------
# 2. LLM Structured Output Schemas (docs/contracts.md §6)
# ---------------------------------------------------------------------------


class JudgmentCheckOutput(BaseModel):
    """Single judgment criterion evaluation produced by the LLM."""

    criterion_id: str = Field(
        ...,
        description="Criterion ID from the policy (e.g. 'C-04', 'W-03').",
    )
    result: Literal["pass", "no_pass"] = Field(
        ...,
        description="Judgment outcome: 'pass' or 'no_pass'.",
    )
    evidence: str = Field(
        ...,
        description="Concise factual justification grounded in transaction profile, policy, and memory.",
    )
    precedents_used: List[str] = Field(
        default_factory=list,
        description="List of precedent memory_ids (e.g. 'MEM-11aa22bb') actually relied upon.",
    )
    adjustments_used: List[str] = Field(
        default_factory=list,
        description="List of active adjustment memory_ids (e.g. 'MEM-5e6f7a8b') applied.",
    )


class RecommendOutput(BaseModel):
    """Structured output for the Evaluate graph's `recommend` node."""

    judgment_checks: List[JudgmentCheckOutput] = Field(
        ...,
        description="Exactly one entry per judgment criterion in the active policy.",
    )
    rationale: str = Field(
        ...,
        description="One or two sentences summarizing the overall judgment for the human reviewer.",
    )


class Citation(BaseModel):
    """Source citation for an AnswerOutput or evaluation Q&A thread entry."""

    type: CitationType = Field(
        ...,
        description="Citation source category: 'policy', 'precedent', or 'adjustment'.",
    )
    ref: str = Field(
        ...,
        description="Criterion ID (e.g. 'C-04') or memory_id (e.g. 'MEM-11aa22bb').",
    )
    label: Optional[str] = Field(
        default=None,
        description="Optional human-readable label for UI display.",
    )


class AnswerOutput(BaseModel):
    """Structured output for the Review graph's `answer_question` node."""

    answer: str = Field(
        ...,
        description=(
            "Direct answer grounded strictly in the supplied policy, evaluation, and memory. "
            "Must explicitly state if the supplied context does not cover the question."
        ),
    )
    citations: List[Citation] = Field(
        default_factory=list,
        description="Supporting policy criteria, precedents, or adjustments.",
    )


class LearnOutput(BaseModel):
    """Structured output for the Review graph's `learn_from_feedback` node."""

    should_create: bool = Field(
        ...,
        description="True only if the reviewer comment contains reusable future guidance.",
    )
    criterion_id: Optional[str] = Field(
        default=None,
        description="Target judgment criterion ID (e.g. 'C-04'). Must NOT be a hard criterion.",
    )
    condition: Optional[str] = Field(
        default=None,
        description="Plain-language condition describing when this adjustment applies.",
    )
    text: Optional[str] = Field(
        default=None,
        description="One or two sentences of actionable guidance written for a future evaluator.",
    )


# ---------------------------------------------------------------------------
# 3. HTTP API Request / Response Schemas (docs/contracts.md §4)
# ---------------------------------------------------------------------------


class AskRequest(BaseModel):
    """Body for POST /evaluations/{eval_id}/ask."""

    question: str = Field(..., min_length=1, description="Reviewer's question about the evaluation.")


class AskResponse(BaseModel):
    """Response for POST /evaluations/{eval_id}/ask."""

    answer: str
    citations: List[Dict[str, Any]]
    thread: List[Dict[str, Any]]


class DecideRequest(BaseModel):
    """Body for POST /evaluations/{eval_id}/decide."""

    verdict: Verdict
    comments: Optional[str] = Field(
        default=None,
        description="Required when verdict is 'validated_with_comments' or 'rejected'.",
    )


class MemoryCreatedItem(BaseModel):
    """Summary of a memory document created during a decision."""

    memory_id: str
    kind: MemoryKind
    text: str


class DecideResponse(BaseModel):
    """Response for POST /evaluations/{eval_id}/decide."""

    decision: Dict[str, Any]
    transaction_status: TxnStatus
    memory_created: List[MemoryCreatedItem] = Field(default_factory=list)


class ErrorDetail(BaseModel):
    """Standard error payload per docs/contracts.md §4."""

    code: str
    message: str


class ErrorResponse(BaseModel):
    """Top-level error wrapper."""

    error: ErrorDetail
    gate: Optional[Dict[str, Any]] = None
