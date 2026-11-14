"""HTTP request bodies. Contract: docs/contracts.md §4."""

from typing import Literal

from pydantic import BaseModel, model_validator


class AskBody(BaseModel):
    question: str


class ChatBody(BaseModel):
    message: str


class EvaluatePendingBody(BaseModel):
    refresh: bool = False


class DecideBody(BaseModel):
    verdict: Literal["validated", "validated_with_comments", "rejected"]
    comments: str | None = None

    @model_validator(mode="after")
    def comments_required(self) -> "DecideBody":
        if self.verdict != "validated" and not (self.comments or "").strip():
            raise ValueError(f"comments are required for verdict '{self.verdict}'")
        return self
