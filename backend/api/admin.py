"""Municipal web admin endpoints (owner B). Every route here requires an admin (router-level dependency)."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.auth import AdminUser, require_admin

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("/ping")
def ping(user: AdminUser) -> dict:
    return {"ok": True, "user": user}
