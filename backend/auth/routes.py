"""POST /auth/google and POST /auth/dev: exchange a Google ID token (or, locally, an email) for our session token."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend import config
from backend.api.deps import DB
from backend.auth import google, store
from backend.auth.tokens import issue_token

router = APIRouter(prefix="/auth", tags=["auth"])

CONTRIBUTOR_FIELD = Field(None, min_length=8, max_length=200,
                          description="anonymous contributor token kept on the device; its trust carries over")


class GoogleLoginIn(BaseModel):
    id_token: str = Field(min_length=10, description="Google ID token (JWT) from Google Sign-In")
    contributor: str | None = CONTRIBUTOR_FIELD


class DevLoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=320, pattern=r"^[^@\s]+@[^@\s]+$")
    contributor: str | None = CONTRIBUTOR_FIELD


def _session(user: dict[str, Any]) -> dict[str, Any]:
    out = store.public_user(user)
    return {"token": issue_token(out), "user": out}


@router.post("/google")
def google_login(body: GoogleLoginIn, conn: DB) -> dict:
    """Verify a Google ID token, upsert the user, link the device's contributor -> {token, user}."""
    try:
        claims = google.verify_google_id_token(body.id_token)
    except google.GoogleNotConfigured as exc:
        raise HTTPException(503, "Google login is not configured (GOOGLE_CLIENT_IDS)") from exc
    except google.GoogleLoginError as exc:
        raise HTTPException(401, str(exc)) from exc
    user = store.login(conn, email=claims["email"], name=claims.get("name"), google_sub=claims["sub"],
                       contributor=body.contributor)
    return _session(user)


@router.post("/dev")
def dev_login(body: DevLoginIn, conn: DB) -> dict:
    """Local testing only (AUTH_DEV_LOGIN=1): sign in as any email without Google. 404 otherwise."""
    if not config.settings.auth_dev_login:
        raise HTTPException(404, "Not Found")
    email = body.email.strip().lower()
    user = store.login(conn, email=email, name=email.split("@", 1)[0], contributor=body.contributor)
    return _session(user)
