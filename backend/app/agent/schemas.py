"""LLM structured outputs. Contract: docs/contracts.md §6."""

from typing import Literal

from pydantic import BaseModel, Field


class JudgmentCheck(BaseModel):
    criterion_id: str
    result: Literal["pass", "no_pass"]
    evidence: str
    precedents_used: list[str] = Field(default_factory=list)
    adjustments_used: list[str] = Field(default_factory=list)


class RecommendOutput(BaseModel):
    judgment_checks: list[JudgmentCheck]
    rationale: str


class Citation(BaseModel):
    type: Literal["policy", "precedent", "adjustment"]
    ref: str


class AnswerOutput(BaseModel):
    answer: str
    citations: list[Citation] = Field(default_factory=list)


class LearnOutput(BaseModel):
    should_create: bool
    criterion_id: str | None = None
    condition: str | None = None
    text: str | None = None
