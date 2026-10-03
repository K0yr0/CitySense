"""Our own session tokens: HS256 JWTs signed with AUTH_SECRET, valid AUTH_TOKEN_DAYS.

Claims: sub (user id as str), email, name, role, iat, exp, iss="cityecho".
The API trusts these claims without a DB lookup (stateless); a user's role is
re-derived from ADMIN_EMAILS at every login.
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from backend import config

log = logging.getLogger(__name__)

ALGORITHM = "HS256"
ISSUER = "cityecho"
_EPHEMERAL_SECRET = secrets.token_urlsafe(48)  # used only when AUTH_SECRET is empty


class InvalidToken(Exception):
    """Missing, malformed, tampered or expired session token."""


_warned = False


def _secret() -> str:
    global _warned
    secret = config.settings.auth_secret
    if not secret:
        if not _warned:
            log.warning("AUTH_SECRET is empty: using a random per-process key (tokens die on restart)")
            _warned = True
        return _EPHEMERAL_SECRET
    return secret


def issue_token(user: dict[str, Any], *, now: datetime | None = None) -> str:
    """Session token for a user row {id, email, name, role}."""
    import jwt

    now = now or datetime.now(timezone.utc)
    claims = {
        "sub": str(user["id"]),
        "email": user.get("email"),
        "name": user.get("name"),
        "role": user.get("role"),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=config.settings.auth_token_days)).timestamp()),
        "iss": ISSUER,
    }
    return jwt.encode(claims, _secret(), algorithm=ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    """Verified claims of a session token. Raises InvalidToken."""
    import jwt

    try:
        return jwt.decode(token, _secret(), algorithms=[ALGORITHM], issuer=ISSUER,
                          options={"require": ["sub", "exp", "iat", "iss"]})
    except jwt.PyJWTError as exc:
        raise InvalidToken(str(exc)) from exc


def user_from_claims(claims: dict[str, Any]) -> dict[str, Any]:
    """The public user shape {id, email, name, role} from verified claims."""
    try:
        user_id = int(claims["sub"])
    except (KeyError, TypeError, ValueError) as exc:
        raise InvalidToken("bad subject") from exc
    return {"id": user_id, "email": claims.get("email"), "name": claims.get("name"), "role": claims.get("role")}
