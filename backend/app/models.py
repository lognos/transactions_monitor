from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


class DecideRequest(BaseModel):
    verdict: Literal['validated', 'validated_with_comments', 'rejected']
    comments: str | None = None

    @model_validator(mode='after')
    def require_comments(self) -> 'DecideRequest':
        self.comments = self.comments.strip() if self.comments else None
        if self.verdict != 'validated' and not self.comments:
            raise ValueError('Comments are required for this verdict.')
        return self


class JudgmentCheck(BaseModel):
    criterion_id: str
    result: Literal['pass', 'no_pass']
    evidence: str
    precedents_used: list[str] = Field(default_factory=list)
    adjustments_used: list[str] = Field(default_factory=list)


class RecommendOutput(BaseModel):
    judgment_checks: list[JudgmentCheck]
    rationale: str


class LearnOutput(BaseModel):
    should_create: bool
    criterion_id: str = ''
    condition: str = ''
    text: str = ''


@dataclass(frozen=True)
class Write:
    collection: str
    id: str
    values: dict
    operation: Literal['insert', 'update'] = 'insert'


class WorkflowError(Exception):
    def __init__(self, status: int, code: str, message: str, **extra: dict):
        self.status = status
        self.body = {'error': {'code': code, 'message': message}, **extra}


def new_id(prefix: str) -> str:
    return f'{prefix}-{uuid4().hex[:8]}'


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
