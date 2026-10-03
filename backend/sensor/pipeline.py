"""Ride pipeline: one recorded ride (SAMPLE_COLUMNS frame) -> ride, ride_segments, evidence rows.

Does not call fusion; the API layer runs `fusion.ingest_evidence` on the returned ids.
"""
from __future__ import annotations

import math
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from backend import db
from backend.models import EvidenceIn, IssueType, Mode, Source
from backend.sensor import detect, lights, mapmatch, track_score

GLITCH_DIST_M = 40.0      # an unmatched bump farther than this from the matched track is a GPS glitch
LIGHT_MATCH_DIST_M = 30.0  # lamps stand beside the carriageway, a bit off the road centreline
MAX_SIGNAL_POINTS = 200


def _utc(value: Any) -> datetime | None:
    """Any timestamp-like value -> tz-aware UTC datetime (None for missing)."""
    if value is None:
        return None
    ts = pd.Timestamp(value)
    if pd.isna(ts):
        return None
    ts = ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
    return ts.to_pydatetime()


def _num(value: Any) -> float | None:
    """JSON-safe float (None for NaN/inf: Postgres jsonb rejects NaN)."""
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _signal(values: Any) -> list[float]:
    arr = np.nan_to_num(np.asarray(values if values is not None else [], dtype=float).ravel())
    if len(arr) > MAX_SIGNAL_POINTS:  # detect already downsamples; this is only a guard
        arr = arr[np.linspace(0, len(arr) - 1, MAX_SIGNAL_POINTS).round().astype(int)]
    return [round(float(v), 4) for v in arr]


def _nearest_sample(t: np.ndarray, value: float) -> int:
    if len(t) < 2:
        return 0
    i = int(np.clip(np.searchsorted(t, value), 1, len(t) - 1))
    return i - 1 if abs(value - t[i - 1]) <= abs(t[i] - value) else i


def _bump_evidence(df: pd.DataFrame, bumps: pd.DataFrame, seg_ids: np.ndarray, ride_id: int,
                   issue: IssueType, fallback_ts: datetime | None) -> list[EvidenceIn]:
    """One EvidenceIn per bump; segment from the nearest sample; GPS glitches dropped."""
    if bumps is None or bumps.empty:
        return []
    t = df["t"].to_numpy(dtype=float)
    matched = np.array([s is not None for s in seg_ids], dtype=bool)
    track_lon = df["lon"].to_numpy(dtype=float)[matched]
    track_lat = df["lat"].to_numpy(dtype=float)[matched]
    out = []
    for b in bumps.itertuples(index=False):
        lon, lat = _num(b.lon), _num(b.lat)
        if lon is None or lat is None:
            continue
        seg = seg_ids[_nearest_sample(t, float(b.t))]
        if seg is None and matched.any():
            if float(mapmatch.haversine_m(lon, lat, track_lon, track_lat).min()) > GLITCH_DIST_M:
                continue
        out.append(EvidenceIn(
            source=Source.SENSOR, type=issue, lon=lon, lat=lat,
            severity=float(np.clip(_num(b.severity) or 0.0, 0, 1)),
            ts=_utc(b.ts) or fallback_ts, segment_id=seg, ride_id=ride_id,
            details={
                "kind": "bump",
                "speed_kmh": _num(b.speed_kmh),
                "raw_peak": _num(b.raw_peak),
                "signal": _signal(b.signal),
                "signal_fs": int(b.signal_fs),
                "peak_index": int(b.peak_index),
            },
        ))
    return out


def _light_evidence(conn, gaps: pd.DataFrame, ride_id: int, fallback_ts: datetime | None) -> list[EvidenceIn]:
    """Streetlight evidence, matched to *road* segments (lamps belong to streets, not tracks)."""
    if gaps is None or gaps.empty:
        return []
    seg_ids = mapmatch.match_points(conn, gaps["lon"], gaps["lat"], Mode.ROAD, max_dist_m=LIGHT_MATCH_DIST_M)
    return [
        EvidenceIn(
            source=Source.SENSOR, type=IssueType.STREETLIGHT, lon=float(g.lon), lat=float(g.lat),
            severity=float(np.clip(g.severity, 0, 1)), ts=_utc(g.ts) or fallback_ts,
            segment_id=seg, ride_id=ride_id,
            details={"kind": "dark_gap", "expected_lux": _num(g.expected_lux), "observed_lux": _num(g.observed_lux)},
        )
        for g, seg in zip(gaps.itertuples(index=False), seg_ids)
    ]


def process_ride(conn, df: pd.DataFrame, *, vehicle_line: str | None, mode: str | Mode,
                 device_hash: str | None = None, source_file: str | None = None) -> dict:
    """Store one ride and turn its bumps and dark gaps into evidence (ARCHITECTURE.md §5.3).

    Returns {"ride_id", "evidence_ids", "bumps", "dark_gaps", "segments_covered"}.
    """
    mode = Mode(mode)
    df = df.sort_values("t").reset_index(drop=True) if "t" in df else df.reset_index(drop=True)
    ts = pd.to_datetime(df["ts"], utc=True, errors="coerce") if "ts" in df else pd.Series(dtype="datetime64[ns, UTC]")
    started, ended = _utc(ts.min()), _utc(ts.max())
    ride_id = db.insert_ride(conn, vehicle_line=vehicle_line, mode=mode.value, started_at=started,
                             ended_at=ended, device_hash=device_hash, source_file=source_file)
    result = {"ride_id": ride_id, "evidence_ids": [], "bumps": 0, "dark_gaps": 0, "segments_covered": 0}
    if df.empty:
        return result

    # Vibration per covered segment -> ride_segments (feeds health map + verification loop).
    hp = detect.highpass(df)
    seg_ids = mapmatch.match_points(conn, df["lon"], df["lat"], mode)
    pass_rows = track_score.segment_pass_stats(df, hp, seg_ids)
    db.upsert_ride_segments(conn, ride_id, pass_rows)
    result["segments_covered"] = len(pass_rows)

    # Bumps -> road_damage / tram_track evidence (no dedup here: fusion clusters them).
    issue = IssueType.TRAM_TRACK if mode == Mode.TRAM else IssueType.ROAD_DAMAGE
    bump_ev = _bump_evidence(df, detect.detect_bumps(df), seg_ids, ride_id, issue, started)
    result["evidence_ids"] += [db.insert_evidence(conn, ev) for ev in bump_ev]
    result["bumps"] = len(bump_ev)

    # Night lux rhythm -> streetlight evidence.
    light_ev = _light_evidence(conn, lights.find_dark_gaps(df), ride_id, started)
    result["evidence_ids"] += [db.insert_evidence(conn, ev) for ev in light_ev]
    result["dark_gaps"] = len(light_ev)

    db.recompute_segment_health(conn)
    return result
