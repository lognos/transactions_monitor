"""Settings read from the repo-root .env (never committed)."""

import os
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env")
load_dotenv(REPO_ROOT / "backend" / ".env")


def _require(*names: str) -> str:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    raise RuntimeError(f"Set one of {', '.join(names)} in {REPO_ROOT / '.env'}")


class Settings:
    @property
    def mongodb_configured(self) -> bool:
        return bool(os.getenv("MONGODB_URI") or os.getenv("MONGODB_CONNECTION_STRING"))

    @property
    def mongodb_uri(self) -> str:
        return _require("MONGODB_URI", "MONGODB_CONNECTION_STRING")

    db_name: str = os.getenv("DB_NAME", "txn_validation")
    # "<provider>:<model>" as understood by langchain's init_chat_model.
    llm_model: str = os.getenv("LLM_MODEL", "google_genai:gemini-2.5-flash")
    cors_origins: list[str] = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
    agent_id: str = "agent-01"


settings = Settings()
