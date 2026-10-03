"""Live ZTM tram/bus positions (cached / demo snapshot handled by fusion.verify)."""
from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter

from backend.api import serializers as ser

log = logging.getLogger(__name__)
router = APIRouter(prefix="/vehicles", tags=["vehicles"])


@router.get("/live")
def live_vehicles(kind: Literal["tram", "bus"] = "tram") -> dict:
    """{"vehicles": [{"id", "line", "lon", "lat", "ts", "kind"}]}; empty list if the feed is unavailable."""
    from backend.fusion import verify

    try:
        vehicles = verify.live_vehicles(kind) or []
    except Exception as exc:
        log.warning("live vehicles (%s) unavailable: %s", kind, exc)
        vehicles = []
    return {"vehicles": [ser.vehicle_json(v) for v in vehicles if v.get("lon") is not None and v.get("lat") is not None]}
