"""Environment-driven settings shared by every backend module.

Values come from the process environment, with a `.env` file at the repo root
loaded first. Import the singleton: `from backend.config import settings`.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _list(name: str, default: str) -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    # Postgres + PostGIS. For Supabase: Project Settings -> Database -> Connection string (URI).
    database_url: str = os.getenv("DATABASE_URL", "postgresql://localhost:5432/cityecho")

    # Claude API (triage, photo check, incident summaries). Empty key -> keyword fallback.
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    anthropic_model: str = os.getenv("ANTHROPIC_MODEL", "claude-opus-5-5")

    # Warsaw open data API (live ZTM vehicle positions).
    warsaw_api_key: str = os.getenv("WARSAW_API_KEY", "")
    ztm_url: str = os.getenv("ZTM_URL", "https://api.um.warszawa.pl/api/action/busestrams_get/")
    ztm_resource_id: str = os.getenv("ZTM_RESOURCE_ID", "f2e5503e-927d-4ad3-9500-4ab9e55deb59")

    # Nominatim requires an identifying User-Agent and max 1 request/second.
    nominatim_user_agent: str = os.getenv("NOMINATIM_USER_AGENT", "cityecho-hackathon")
    nominatim_url: str = os.getenv("NOMINATIM_URL", "https://nominatim.openstreetmap.org/search")

    # Embeddings: sentence-transformers model if installed, else hashing fallback.
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-base")

    # Demo mode: prefer offline fallbacks (cached ZTM snapshot, cached geocodes) over live calls.
    demo_mode: bool = _bool("DEMO_MODE", False)

    data_dir: Path = REPO_ROOT / "data"
    cache_dir: Path = REPO_ROOT / "data" / "cache"
    cors_origins: list[str] = field(
        default_factory=lambda: _list("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
    )

    @property
    def has_llm(self) -> bool:
        return bool(self.anthropic_api_key)


settings = Settings()
settings.cache_dir.mkdir(parents=True, exist_ok=True)
