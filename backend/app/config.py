"""Application configuration, loaded from environment variables.

Secrets (e.g. an optional LLM API key) are only ever read from the environment
and are never written to the database or returned by the API.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (avoids an extra dependency). Existing env vars win."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(PROJECT_DIR / ".env")


def _bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    host: str = os.environ.get("FAIRCLICK_HOST", "127.0.0.1")
    port: int = int(os.environ.get("FAIRCLICK_PORT", "8000"))
    data_dir: Path = Path(os.environ.get("FAIRCLICK_DATA_DIR", str(BACKEND_DIR / "data")))
    headless: bool = _bool("FAIRCLICK_HEADLESS", True)
    step_delay_ms: int = int(os.environ.get("FAIRCLICK_STEP_DELAY_MS", "250"))
    max_steps: int = int(os.environ.get("FAIRCLICK_MAX_STEPS", "40"))
    approval_timeout_s: int = int(os.environ.get("FAIRCLICK_APPROVAL_TIMEOUT_S", "900"))
    # Optional LLM provider. Empty => deterministic rule-based demo mode.
    llm_provider: str = os.environ.get("FAIRCLICK_LLM_PROVIDER", "none").lower()
    anthropic_api_key: str = field(default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY", ""), repr=False)
    anthropic_model: str = os.environ.get("FAIRCLICK_ANTHROPIC_MODEL", "claude-opus-5-5")
    # Overrides the base URL the agent uses for the simulated sites (set by tests).
    site_base_url: str = os.environ.get("FAIRCLICK_SITE_BASE_URL", "")

    @property
    def app_db_path(self) -> Path:
        return self.data_dir / "fairclick.db"

    @property
    def sim_db_path(self) -> Path:
        # Simulated-website "customer" data is kept in a separate database from
        # FairClick's own configuration and records.
        return self.data_dir / "sim_sites.db"

    @property
    def evidence_dir(self) -> Path:
        return self.data_dir / "evidence"

    @property
    def base_url(self) -> str:
        return self.site_base_url or f"http://{self.host}:{self.port}"


settings = Settings()


def ensure_dirs() -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.evidence_dir.mkdir(parents=True, exist_ok=True)
