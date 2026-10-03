"""Vehicle rides: file upload (CSV / Sensor Logger .zip) and chunked live streaming from the PWA.

Orchestration (ARCHITECTURE.md §5.7):
sensor.pipeline.process_ride -> fusion.ingest_evidence -> fusion.verify.check_ride_verifications
"""
from __future__ import annotations

import hashlib
import logging
import re
import shutil
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

from backend.api.deps import DB, db_session
from backend.config import REPO_ROOT, settings
from backend.models import Mode

log = logging.getLogger(__name__)
router = APIRouter(prefix="/rides", tags=["rides"])

RIDES_DIR = settings.data_dir / "rides"
STREAM_TTL_S = 30 * 60           # idle sessions are dropped after 30 min
MAX_STREAM_SAMPLES = 500_000     # ~80 min at 100 Hz

_streams: dict[str, dict[str, Any]] = {}  # session_id -> {"vehicle_line", "mode", "samples", "touched"}
_streams_lock = threading.Lock()


def _count(value: Any) -> int:
    """process_ride may report counts or lists; normalize to an int."""
    if value is None:
        return 0
    return len(value) if isinstance(value, (list, tuple, set, dict)) else int(value)


def process_and_fuse(conn, df, *, vehicle_line: str | None, mode: str,
                     device_hash: str | None = None, source_file: str | None = None) -> dict:
    """Run one ride through the sensor pipeline, fuse its evidence and check pending verifications."""
    from backend.fusion import incidents as fusion_incidents, verify
    from backend.sensor import pipeline as sensor_pipeline

    res = sensor_pipeline.process_ride(conn, df, vehicle_line=vehicle_line, mode=mode,
                                       device_hash=device_hash, source_file=source_file)
    ride_id = int(res["ride_id"])
    evidence_ids = [int(e) for e in res.get("evidence_ids") or []]
    incident_ids = fusion_incidents.ingest_evidence(conn, evidence_ids) if evidence_ids else []
    verified = verify.check_ride_verifications(conn, ride_id)
    return {
        "ride_id": ride_id,
        "bumps": _count(res.get("bumps")),
        "dark_gaps": _count(res.get("dark_gaps")),
        "segments_covered": _count(res.get("segments_covered")),
        "evidence_ids": evidence_ids,
        "incident_ids": [int(i) for i in incident_ids],
        "verified_incident_ids": [int(i) for i in verified or []],
    }


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)) if path.is_relative_to(REPO_ROOT) else str(path)


def _load_ride_file(path: Path):
    from backend.sensor import ingest

    try:
        df = ingest.load_sensor_logger(path)
    except Exception as exc:
        raise HTTPException(400, f"could not read ride file: {exc}") from exc
    if df is None or len(df) == 0:
        raise HTTPException(400, "ride file contains no samples")
    return df


@router.post("/upload")
def upload_ride(
    conn: DB,
    file: UploadFile = File(...),
    vehicle_line: str | None = Form(None),
    mode: Mode = Form(Mode.TRAM),
) -> dict:
    """Save the upload to data/rides/, parse it and process it like a finished ride."""
    name = Path(file.filename or "ride.csv").name
    if Path(name).suffix.lower() not in (".csv", ".zip"):
        raise HTTPException(400, "upload a .csv or a Sensor Logger .zip export")
    RIDES_DIR.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", name)
    dest = RIDES_DIR / f"{datetime.now(timezone.utc):%Y%m%dT%H%M%S}_{uuid4().hex[:6]}_{safe}"
    with dest.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    df = _load_ride_file(dest)
    return process_and_fuse(conn, df, vehicle_line=(vehicle_line or "").strip() or None, mode=mode.value,
                            source_file=_rel(dest))


class StreamChunk(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)
    vehicle_line: str | None = None
    mode: Mode = Mode.TRAM
    samples: list[dict[str, Any]] = Field(default_factory=list)  # {"t","ax","ay","az","lat","lon","speed_kmh","lux"?}
    final: bool = False


def _expire_streams(now: float) -> None:
    for sid in [s for s, buf in _streams.items() if now - buf["touched"] > STREAM_TTL_S]:
        log.info("dropping idle ride stream %s", sid)
        del _streams[sid]


def _save_stream_csv(df, session_id: str) -> str | None:
    """Keep a replayable copy of a live ride in data/rides/ (best effort)."""
    try:
        RIDES_DIR.mkdir(parents=True, exist_ok=True)
        path = RIDES_DIR / f"stream_{datetime.now(timezone.utc):%Y%m%dT%H%M%S}_{re.sub(r'[^A-Za-z0-9_-]', '_', session_id)[:40]}.csv"
        df.to_csv(path, index=False)
        return _rel(path)
    except Exception as exc:
        log.warning("could not save stream %s: %s", session_id, exc)
        return None


@router.post("/stream")
def stream_ride(chunk: StreamChunk, request: Request) -> dict:
    """Buffer PWA sample chunks per session; the `final` chunk processes the whole ride."""
    with _streams_lock:
        now = time.monotonic()
        _expire_streams(now)
        buf = _streams.setdefault(chunk.session_id, {"samples": [], "vehicle_line": None,
                                                     "mode": chunk.mode.value, "touched": now})
        if len(buf["samples"]) + len(chunk.samples) > MAX_STREAM_SAMPLES:
            raise HTTPException(413, f"ride stream too long (max {MAX_STREAM_SAMPLES} samples); send final")
        buf["samples"].extend(chunk.samples)
        buf["vehicle_line"] = chunk.vehicle_line or buf["vehicle_line"]
        buf["mode"] = chunk.mode.value
        buf["touched"] = now
        if not chunk.final:
            return {"session_id": chunk.session_id, "buffered": len(buf["samples"])}
        samples, vehicle_line, mode = list(buf["samples"]), buf["vehicle_line"], buf["mode"]

    if not samples:
        with _streams_lock:
            _streams.pop(chunk.session_id, None)
        raise HTTPException(400, "ride stream has no samples")

    try:
        result = _finish_stream(request, chunk.session_id, samples, vehicle_line=vehicle_line, mode=mode)
    except Exception:
        # keep the buffer (minus this final chunk) so the client can simply resend `final`
        with _streams_lock:
            if (buf := _streams.get(chunk.session_id)) is not None:
                del buf["samples"][len(samples) - len(chunk.samples):]
        raise
    with _streams_lock:
        _streams.pop(chunk.session_id, None)
    return result


def _finish_stream(request: Request, session_id: str, samples: list[dict], *,
                   vehicle_line: str | None, mode: str) -> dict:
    from backend.sensor import ingest

    try:
        df = ingest.from_samples(samples)
    except Exception as exc:
        raise HTTPException(400, f"could not parse ride samples: {exc}") from exc
    if df is None or len(df) == 0:
        raise HTTPException(400, "ride stream has no usable samples")
    source_file = _save_stream_csv(df, session_id) or f"stream:{session_id}"
    device_hash = hashlib.sha256(session_id.encode()).hexdigest()[:16]
    with db_session(request.app) as conn:  # connection only for the final chunk
        return process_and_fuse(conn, df, vehicle_line=vehicle_line, mode=mode,
                                device_hash=device_hash, source_file=source_file)
