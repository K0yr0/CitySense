"""FastAPI dependencies for routes that need a user.

    from backend.auth import CurrentUser, OptionalUser, AdminUser, require_admin

    @router.post("/x")
    def x(user: CurrentUser): ...            # 401 without a valid "Authorization: Bearer <token>"

    router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])   # 403 unless admin

The user is the dict {id, email, name, role} from the token (no DB lookup).
"""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend import config
from backend.auth.tokens import InvalidToken, decode_token, user_from_claims
from backend.models import Role

bearer = HTTPBearer(auto_error=False, description="Session token from POST /auth/google")
Credentials = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(401, detail, headers={"WWW-Authenticate": "Bearer"})


def current_user(creds: Credentials) -> dict[str, Any]:
    """The signed-in user, or 401."""
    if creds is None or not creds.credentials:
        raise _unauthorized("not signed in")
    try:
        return user_from_claims(decode_token(creds.credentials))
    except InvalidToken as exc:
        raise _unauthorized(f"invalid session token: {exc}") from exc


def optional_user(creds: Credentials) -> dict[str, Any] | None:
    """The signed-in user, or None (no token *or* an invalid/expired one: public routes keep working)."""
    if creds is None or not creds.credentials:
        return None
    try:
        return user_from_claims(decode_token(creds.credentials))
    except InvalidToken:
        return None


def require_admin(user: Annotated[dict[str, Any], Depends(current_user)]) -> dict[str, Any]:
    """The signed-in admin, or 403. The email must *still* be in ADMIN_EMAILS (instant revocation)."""
    email = (user.get("email") or "").lower()
    if user.get("role") != Role.ADMIN.value or email not in config.settings.admin_emails:
        raise HTTPException(403, "admin only")
    return user


CurrentUser = Annotated[dict[str, Any], Depends(current_user)]
OptionalUser = Annotated[dict[str, Any] | None, Depends(optional_user)]
AdminUser = Annotated[dict[str, Any], Depends(require_admin)]
