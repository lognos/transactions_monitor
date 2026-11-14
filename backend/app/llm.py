"""
backend/app/llm.py
Chat-model factory for the Policy & Validation Agent.

Design goals for multi-agent handoff:
- Temperature is pinned to 0 (`docs/plan-agent.md`) for deterministic auditability.
- Automatically loads `.env` at the repo root if variables are not already exported.
- Supports OpenAI (`langchain_openai.ChatOpenAI`) and Google Gemini
  (`langchain_google_genai.ChatGoogleGenerativeAI`), auto-detecting from env vars
  unless `LLM_PROVIDER` is explicitly set.
- LangSmith tracing activates automatically when `LANGSMITH_TRACING=true`,
  `LANGSMITH_API_KEY`, and `LANGSMITH_PROJECT` are present in the environment.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any, Optional, Type, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


def _load_dotenv_once() -> None:
    """Load `.env` from repository root if present, without overwriting existing env vars."""
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    env_path = os.path.join(repo_root, ".env")
    if not os.path.exists(env_path):
        return
    try:
        from dotenv import load_dotenv  # type: ignore

        load_dotenv(env_path, override=False)
        return
    except ImportError:
        pass

    with open(env_path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val


def resolve_provider() -> str:
    """Resolve active LLM provider from `LLM_PROVIDER` or available API keys."""
    _load_dotenv_once()
    explicit = os.getenv("LLM_PROVIDER", "").strip().lower()
    if explicit in {"openai", "google", "gemini"}:
        return "google" if explicit == "gemini" else explicit

    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    if os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"):
        return "google"

    raise RuntimeError(
        "No LLM API key found. Set OPENAI_API_KEY or GOOGLE_API_KEY/GEMINI_API_KEY "
        "(or set LLM_PROVIDER explicitly) in `.env` or environment variables."
    )


@lru_cache(maxsize=4)
def get_chat_model(model_override: Optional[str] = None) -> Any:
    """
    Return a LangChain chat model instance configured at temperature=0.

    Args:
        model_override: Optional model identifier (e.g. 'gpt-4o-mini', 'gemini-2.5-flash').
    """
    provider = resolve_provider()

    if provider == "openai":
        from langchain_openai import ChatOpenAI

        model_name = model_override or os.getenv("LLM_MODEL", "gpt-4o-mini")
        return ChatOpenAI(model=model_name, temperature=0)

    if provider == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI

        api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        model_name = model_override or os.getenv("LLM_MODEL", "gemini-2.5-flash")
        return ChatGoogleGenerativeAI(
            model=model_name,
            temperature=0,
            google_api_key=api_key,
        )

    raise ValueError(f"Unsupported LLM_PROVIDER: {provider}")


def get_structured_llm(schema: Type[T], model_override: Optional[str] = None) -> Any:
    """
    Return a runnable bound to a Pydantic output schema (`with_structured_output`).

    Note:
        The LLM never writes directly to MongoDB (`AGENTS.md` Invariant #5);
        calling nodes validate the returned Pydantic model and persist via `write_with_audit`.
    """
    chat_model = get_chat_model(model_override=model_override)
    return chat_model.with_structured_output(schema)
