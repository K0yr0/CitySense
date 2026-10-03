"""Google Sign-In: verify an ID token from the mobile app or web admin.

The token's audience must be one of GOOGLE_CLIENT_IDS (web, iOS, Android client ids).
Tests swap `verify_google_id_token` for a fake so nothing touches the network.
"""
from __future__ import annotations

from typing import Any

from backend import config


class GoogleLoginError(Exception):
    """The ID token is invalid, expired, for another app, or has no verified email."""


class GoogleNotConfigured(Exception):
    """GOOGLE_CLIENT_IDS is empty."""


def _google_verify(token: str, audience: list[str]) -> dict[str, Any]:
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token

    # Fetches (and caches per request object) Google's public certs; checks signature, exp, iss, aud.
    return dict(id_token.verify_oauth2_token(token, google_requests.Request(), audience=audience,
                                             clock_skew_in_seconds=10))


def verify_google_id_token(token: str) -> dict[str, Any]:
    """{sub, email, name} of a valid Google ID token. Raises GoogleLoginError / GoogleNotConfigured."""
    audience = config.settings.google_client_ids
    if not audience:
        raise GoogleNotConfigured("GOOGLE_CLIENT_IDS is not set")
    try:
        claims = _google_verify(token, audience)
    except GoogleLoginError:
        raise
    except Exception as exc:  # ValueError (bad token) or transport errors from google-auth
        raise GoogleLoginError(f"invalid Google ID token: {exc}") from exc
    email = (claims.get("email") or "").strip().lower()
    if not claims.get("sub") or not email:
        raise GoogleLoginError("Google ID token has no subject or email")
    if claims.get("email_verified") is False or str(claims.get("email_verified")).lower() == "false":
        raise GoogleLoginError("Google email is not verified")
    return {"sub": str(claims["sub"]), "email": email, "name": claims.get("name")}
