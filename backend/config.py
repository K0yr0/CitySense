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


def _int(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    return int(raw) if raw else default


def _device_keys(name: str) -> dict[str, str]:
    """`id1:secret1,id2:secret2` -> {"id1": "secret1", ...}. Entries without a ':' are ignored."""
    keys: dict[str, str] = {}
    for item in _list(name, ""):
        device_id, sep, secret = item.partition(":")
        if sep and device_id.strip() and secret.strip():
            keys[device_id.strip()] = secret.strip()
    return keys


@dataclass(frozen=True)
class Settings:
    # Postgres + PostGIS. For Supabase: Project Settings -> Database -> Connection string (URI).
    database_url: str = os.getenv("DATABASE_URL", "postgresql://localhost:5432/cityecho")

    # Claude API (triage, photo check, incident summaries). Empty key -> keyword fallback.
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    anthropic_model: str = os.getenv("ANTHROPIC_MODEL", "claude-opus-5-5")

    # Warsaw open data API (live ZTM vehicle positions).
    warsaw_api_key: str = os.getenv("WARSAW_API_KEY", "")
    # dane.um.warszawa.pl: POST {"type": 1|2} with the user token in the Authorization header.
    ztm_url: str = os.getenv("ZTM_URL", "https://dane.um.warszawa.pl/api/action/get_ztm_lokalizacja_pojazdow")

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
        default_factory=lambda: _list("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000,http://localhost:8081")
    )

    # --- Auth (backend/auth) ---
    # OAuth client ids whose Google ID tokens we accept (web, iOS, Android). Empty -> Google login off.
    google_client_ids: list[str] = field(default_factory=lambda: _list("GOOGLE_CLIENT_IDS", ""))
    # HS256 key for our own session tokens. Empty -> random per process (tokens die on restart).
    auth_secret: str = os.getenv("AUTH_SECRET", "")
    auth_token_days: int = _int("AUTH_TOKEN_DAYS", 30)
    # Google accounts that get role=admin at login (compared lower-case).
    admin_emails: list[str] = field(
        default_factory=lambda: [e.lower() for e in _list("ADMIN_EMAILS", "")]
    )
    # POST /auth/dev {email}: login without Google, for local testing only. Never enable in production.
    auth_dev_login: bool = _bool("AUTH_DEV_LOGIN", False)

    # --- Simulated vehicles (POST /devices/stream, owner C) ---
    # DEVICE_KEYS=bus-17-01:secret,tram-4-01:secret -> {"bus-17-01": "secret", ...}
    device_keys: dict[str, str] = field(default_factory=lambda: _device_keys("DEVICE_KEYS"))

    @property
    def has_llm(self) -> bool:
        return bool(self.anthropic_api_key)


settings = Settings()
settings.cache_dir.mkdir(parents=True, exist_ok=True)
