"""Simulated (or real) vehicle sensor devices (owner C).

Day 0 stub. Request format is fixed in docs/ARCHITECTURE.md §8:
header `X-Device-Key: <device_id>:<secret>` (keys from settings.device_keys),
body {"vehicle_line", "mode", "samples": [...same fields as /rides/stream...], "final"?: bool}.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/devices", tags=["devices"])


@router.post("/stream")
def stream() -> dict:
    raise HTTPException(501, "not implemented yet (owner: C)")
