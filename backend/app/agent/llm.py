"""Chat model factory for the Policy & Validation Agent.

- Temperature is pinned to 0 (`docs/plan-agent.md`) for deterministic auditability.
- Reads `settings.llm_model` (from `app.config`), defaulting to `google_genai:gemini-2.5-flash`,
  and supports `init_chat_model` as well as explicit `LLM_PROVIDER` / `OPENAI_API_KEY` /
  `GOOGLE_API_KEY` / `GEMINI_API_KEY` fallbacks.
- LangSmith tracing activates automatically via `LANGSMITH_TRACING=true`,
  `LANGSMITH_API_KEY`, and `LANGSMITH_PROJECT`.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any, Optional, Type, TypeVar

from pydantic import BaseModel

from app.config import settings

T = TypeVar("T", bound=BaseModel)


@lru_cache(maxsize=4)
def get_llm(model_override: Optional[str] = None) -> Any:
    """Return a LangChain chat model instance configured at temperature=0."""
    model_spec = model_override or settings.llm_model

    # If model_spec uses "<provider>:<model>" (e.g. "google_genai:gemini-2.5-flash"),
    # use langchain's init_chat_model directly.
    if ":" in model_spec:
        from langchain.chat_models import init_chat_model

        return init_chat_model(model_spec, temperature=0)

    explicit = os.getenv("LLM_PROVIDER", "").strip().lower()
    if explicit == "openai" or (not explicit and os.getenv("OPENAI_API_KEY")):
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model=model_spec, temperature=0)

    if explicit in {"google", "gemini", "google_genai"} or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"):
        from langchain_google_genai import ChatGoogleGenerativeAI

        api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        return ChatGoogleGenerativeAI(
            model=model_spec,
            temperature=0,
            google_api_key=api_key,
        )

    from langchain.chat_models import init_chat_model

    return init_chat_model(model_spec, temperature=0)


def get_chat_model(model_override: Optional[str] = None) -> Any:
    """Alias for `get_llm`."""
    return get_llm(model_override=model_override)


def get_structured_llm(schema: Type[T], model_override: Optional[str] = None) -> Any:
    """Return a runnable bound to a Pydantic output schema (`with_structured_output`).

    Note:
        The LLM never writes directly to MongoDB (`AGENTS.md` Invariant #5);
        calling nodes validate the returned Pydantic model and persist via `write_with_audit`.
    """
    return get_llm(model_override=model_override).with_structured_output(schema)
