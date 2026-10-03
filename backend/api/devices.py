"""Simulated (or real) vehicle sensor devices (owner C). Contract: docs/ARCHITECTURE.md §8.5.

    POST /devices/stream
      X-Device-Key: <device_id>:<secret>          # pair from DEVICE_KEYS (settings.device_keys)
      {"vehicle_line", "mode", "samples": [...same fields as /rides/stream...], "final"?: bool}
      -> {"device_id", "buffered"} | (final) same as /rides/upload

One open ride per device, buffered in memory like /rides/stream; the final chunk runs
process_ride -> ingest_evidence -> check_ride_verifications (rides.process_and_fuse).
Every authenticated chunk upserts the `devices` row (hash of the key, never the secret) and
its `last_seen_at`.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import threading
import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from backend.api import rides
from backend.api.deps import db_session
from backend.config import settings
from backend.models import Mode

log = logging.getLogger(__name__)
router = APIRouter(prefix="/devices", tags=["devices"])

_buffers: dict[str, dict[str, Any]] = {}  # device_id -> {"vehicle_line", "mode", "samples", "touched"}
_buffers_lock = threading.Lock()


def key_hash(device_id: str, secret: str) -> str:
    return hashlib.sha256(f"{device_id}:{secret}".encode()).hexdigest()


def device_hash(device_id: str) -> str:
    """rides.device_hash for a device (same 16-hex shape as /rides/stream sessions)."""
    return hashlib.sha256(device_id.encode()).hexdigest()[:16]


def authenticate(x_device_key: Annotated[str | None, Header()] = None) -> tuple[str, str]:
    """`X-Device-Key: <device_id>:<secret>` checked against DEVICE_KEYS -> (device_id, key hash); 401 otherwise."""
    device_id, _, secret = (x_device_key or "").strip().partition(":")
    expected = settings.device_keys.get(device_id)
    if not expected or not hmac.compare_digest(secret.encode(), expected.encode()):
        raise HTTPException(401, "invalid or missing X-Device-Key", headers={"WWW-Authenticate": "X-Device-Key"})
    return device_id, key_hash(device_id, secret)


Device = Annotated[tuple[str, str], Depends(authenticate)]


class DeviceChunk(BaseModel):
    vehicle_line: str | None = Field(None, max_length=32)
    mode: Mode = Mode.ROAD
    samples: list[dict[str, Any]] = Field(default_factory=list)  # {"t","ax","ay","az","lat","lon","speed_kmh","lux"?}
    final: bool = False


def _touch_device(conn, device_id: str, hashed: str, vehicle_line: str | None, mode: str) -> None:
    from backend import db

    db.fetch_one(
        conn,
        """insert into devices (id, key_hash, vehicle_line, mode, last_seen_at)
           values (%s, %s, %s, %s, now())
           on conflict (id) do update
              set key_hash = excluded.key_hash,
                  vehicle_line = coalesce(excluded.vehicle_line, devices.vehicle_line),
                  mode = excluded.mode,
                  last_seen_at = excluded.last_seen_at
           returning id""",
        (device_id, hashed, vehicle_line, mode),
    )


def _expire(now: float) -> None:
    for dev in [d for d, buf in _buffers.items() if now - buf["touched"] > rides.STREAM_TTL_S]:
        log.info("dropping idle device ride %s", dev)
        del _buffers[dev]


@router.post("/stream")
def stream(chunk: DeviceChunk, device: Device, request: Request) -> dict:
    """Buffer one device's sample chunks; the `final` chunk processes the whole ride."""
    device_id, hashed = device
    if not chunk.final:  # before buffering: a DB error then leaves nothing to dedupe on retry
        with db_session(request.app) as conn:
            _touch_device(conn, device_id, hashed, chunk.vehicle_line, chunk.mode.value)
    with _buffers_lock:
        now = time.monotonic()
        _expire(now)
        buf = _buffers.setdefault(device_id, {"samples": [], "vehicle_line": None,
                                              "mode": chunk.mode.value, "touched": now})
        if len(buf["samples"]) + len(chunk.samples) > rides.MAX_STREAM_SAMPLES:
            raise HTTPException(413, f"ride too long (max {rides.MAX_STREAM_SAMPLES} samples); send final")
        buf["samples"].extend(chunk.samples)
        buf["vehicle_line"] = chunk.vehicle_line or buf["vehicle_line"]
        buf["mode"] = chunk.mode.value
        buf["touched"] = now
        if not chunk.final:
            return {"device_id": device_id, "buffered": len(buf["samples"])}
        samples, vehicle_line, mode = list(buf["samples"]), buf["vehicle_line"], buf["mode"]

    if not samples:
        with _buffers_lock:
            _buffers.pop(device_id, None)
        raise HTTPException(400, "device ride has no samples")

    try:
        result = _finish(request, device_id, hashed, samples, vehicle_line=vehicle_line, mode=mode)
    except Exception:
        # keep the buffer (minus this final chunk) so the device can simply resend `final`
        with _buffers_lock:
            if (buf := _buffers.get(device_id)) is not None:
                del buf["samples"][len(samples) - len(chunk.samples):]
        raise
    with _buffers_lock:
        _buffers.pop(device_id, None)
    return result


def _finish(request: Request, device_id: str, hashed: str, samples: list[dict], *,
            vehicle_line: str | None, mode: str) -> dict:
    from backend.sensor import ingest

    try:
        df = ingest.from_samples(samples)
    except Exception as exc:
        raise HTTPException(400, f"could not parse device samples: {exc}") from exc
    if df is None or len(df) == 0:
        raise HTTPException(400, "device ride has no usable samples")
    source_file = rides._save_stream_csv(df, f"device_{device_id}") or f"device:{device_id}"
    with db_session(request.app) as conn:
        _touch_device(conn, device_id, hashed, vehicle_line, mode)
        return rides.process_and_fuse(conn, df, vehicle_line=vehicle_line, mode=mode,
                                      device_hash=device_hash(device_id), source_file=source_file)
