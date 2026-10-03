"""Signed-in user endpoints (owner A). GET /users/me."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.api.deps import DB
from backend.auth import CurrentUser
from backend.auth import store

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me")
def me(user: CurrentUser, conn: DB) -> dict:
    """{id, email, name, role} of the signed-in user, fresh from the database (401 if the account is gone)."""
    row = store.get_user(conn, user["id"])
    if row is None:
        raise HTTPException(401, "user no longer exists", headers={"WWW-Authenticate": "Bearer"})
    return store.public_user(row)
