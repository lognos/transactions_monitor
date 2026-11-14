"""HTTP request bodies. Contract: docs/contracts.md §4."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class AskBody(BaseModel):
    question: str


class ChatBody(BaseModel):
    message: str


class EvaluatePendingBody(BaseModel):
    refresh: bool = False


class SimulateBody(BaseModel):
    count: int = Field(default=3, ge=1, le=10)
    mode: Literal["random", "signals", "sequential"] = "random"
    policy_only: bool = False


class DecideBody(BaseModel):
    verdict: Literal["approved", "rejected"]
    comments: str | None = None


class OverrideBody(BaseModel):
    result: Literal["pass", "flag", "no_pass"] | None
    reason: str | None = None

    @model_validator(mode="after")
    def reason_required(self) -> "OverrideBody":
        if self.result is not None and not (self.reason or "").strip():
            raise ValueError("reason is required when overriding a check")
        return self
