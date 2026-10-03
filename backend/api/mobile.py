"""Citizen mobile app endpoints (owner A). Day 0 stub: only the ping."""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/mobile", tags=["mobile"])


@router.get("/ping")
def ping() -> dict:
    return {"ok": True}
