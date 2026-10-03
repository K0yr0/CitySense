"""PostgreSQL/PostGIS access layer (psycopg 3, dict rows).

Usage:
    with get_conn() as conn:          # commits on success, rolls back on error
        rid = insert_ride(conn, vehicle_line="17", mode="tram", started_at=ts)

Every helper takes an open connection as first argument and never commits
itself. Geometries are built in SQL with ST_SetSRID(ST_MakePoint(lon, lat), 4326);
coordinates are always (lon, lat).
"""
from __future__ import annotations

import json
import math
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import partial
from typing import Any, Iterator

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from backend.config import settings
from backend.models import EvidenceIn

_pool = None
_pool_lock = threading.Lock()


# --------------------------------------------------------------------------- connections

def _get_pool():
    """Create the connection pool on first use (so importing this module never connects)."""
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                from psycopg_pool import ConnectionPool

                _pool = ConnectionPool(
                    settings.database_url,
                    min_size=1,
                    max_size=10,
                    # prepare_threshold=None keeps us compatible with pgbouncer / Supabase pooler.
                    kwargs={"row_factory": dict_row, "prepare_threshold": None},
                    check=ConnectionPool.check_connection,
                    open=True,
                    timeout=10,  # fail fast when the DB is unreachable instead of hanging requests
                    name="cityecho",
                )
    return _pool


def close_pool() -> None:
    """Close the pool (e.g. on API shutdown). Safe to call when it was never opened."""
    global _pool
    with _pool_lock:
        if _pool is not None:
            _pool.close()
            _pool = None


@contextmanager
def get_conn() -> Iterator[psycopg.Connection]:
    """Yield a pooled connection with dict rows; commit on success, roll back on error."""
    with _get_pool().connection() as conn:
        try:
            yield conn
            conn.commit()
        except BaseException:
            if not conn.closed:
                conn.rollback()
            raise


def _cursor(conn: psycopg.Connection):
    """Cursor that always returns dict rows, whatever the connection's row factory."""
    return conn.cursor(row_factory=dict_row)


# --------------------------------------------------------------------------- value helpers

def _json_default(obj: Any) -> Any:
    if hasattr(obj, "tolist"):  # numpy scalars / arrays
        return obj.tolist()
    if isinstance(obj, datetime):
        return obj.isoformat()
    if hasattr(obj, "model_dump"):  # pydantic models
        return obj.model_dump(mode="json")
    return str(obj)


_dumps = partial(json.dumps, default=_json_default, ensure_ascii=False)


def _jsonb(obj: Any) -> Jsonb:
    return Jsonb(obj if obj is not None else {}, dumps=_dumps)


def _float(x: Any) -> float | None:
    if x is None:
        return None
    x = float(x)
    return None if math.isnan(x) else x


def _int(x: Any) -> int | None:
    return None if x is None else int(x)


def _str(x: Any) -> str | None:
    return None if x is None else str(x)  # StrEnum -> its value


def _ts(x: datetime | None) -> datetime | None:
    """tz-aware UTC datetime (pandas Timestamps converted, naive assumed UTC)."""
    if x is None or x != x:  # None or pandas NaT
        return None
    if hasattr(x, "to_pydatetime"):
        x = x.to_pydatetime()
    return x.replace(tzinfo=timezone.utc) if x.tzinfo is None else x


def _clamp01(x: Any) -> float:
    x = _float(x)
    return 0.0 if x is None else max(0.0, min(1.0, x))


# --------------------------------------------------------------------------- map matching

NEAREST_SEGMENTS_SQL = """
with pts as (
    select p.ord, p.lat, ST_SetSRID(ST_MakePoint(p.lon, p.lat), 4326) as pt
    from unnest(%(lons)s::float8[], %(lats)s::float8[]) with ordinality as p(lon, lat, ord)
)
select pts.ord, n.id
from pts
left join lateral (
    select s.id
    from segments s
    where (%(mode)s::text is null or s.mode = %(mode)s::text)
      -- cheap index-backed box prefilter (degrees), then the exact metric check
      and s.geom && ST_Expand(pts.pt,
                              %(max_dist_m)s::float8 / (111320.0 * greatest(cos(radians(pts.lat)), 0.01)),
                              %(max_dist_m)s::float8 / 110540.0)
      and ST_DWithin(s.geom::geography, pts.pt::geography, %(max_dist_m)s::float8)
    order by s.geom::geography <-> pts.pt::geography, s.id
    limit 1
) n on true
order by pts.ord
"""


def nearest_segments(
    conn: psycopg.Connection,
    coords: list[tuple[float, float]],
    mode: str | None = None,
    max_dist_m: float = 20,
) -> list[int | None]:
    """Nearest segment id (or None) for every (lon, lat), in input order, in one query."""
    if not coords:
        return []
    params = {
        "lons": [float(c[0]) for c in coords],
        "lats": [float(c[1]) for c in coords],
        "mode": _str(mode),
        "max_dist_m": float(max_dist_m),
    }
    out: list[int | None] = [None] * len(coords)
    with _cursor(conn) as cur:
        cur.execute(NEAREST_SEGMENTS_SQL, params)
        for row in cur.fetchall():
            if row["id"] is not None:
                out[int(row["ord"]) - 1] = int(row["id"])
    return out


def nearest_segment(
    conn: psycopg.Connection, lon: float, lat: float, mode: str | None = None, max_dist_m: float = 20
) -> int | None:
    """Nearest segment id within `max_dist_m` metres of (lon, lat), optionally of one mode."""
    return nearest_segments(conn, [(lon, lat)], mode, max_dist_m)[0]


# --------------------------------------------------------------------------- inserts

def insert_ride(
    conn: psycopg.Connection,
    *,
    vehicle_line: str | None,
    mode: str,
    started_at: datetime | None,
    ended_at: datetime | None = None,
    device_hash: str | None = None,
    source_file: str | None = None,
) -> int:
    with _cursor(conn) as cur:
        cur.execute(
            """
            insert into rides (vehicle_line, mode, started_at, ended_at, device_hash, source_file)
            values (%s, %s, %s, %s, %s, %s)
            returning id
            """,
            (_str(vehicle_line), _str(mode), _ts(started_at), _ts(ended_at), device_hash, source_file),
        )
        return int(cur.fetchone()["id"])


def insert_report(
    conn: psycopg.Connection,
    *,
    raw_text: str,
    structured: dict,
    lon: float | None,
    lat: float | None,
    location_confidence: float | None,
    embedding: list[float] | None,
    duplicate_of: int | None = None,
    photo_url: str | None = None,
    source: str = "web",
    created_at: datetime | None = None,
) -> int:
    """Insert a citizen report; category/urgency/department are copied out of `structured`."""
    if hasattr(structured, "model_dump"):
        structured = structured.model_dump(mode="json")
    structured = dict(structured or {})
    lon, lat = _float(lon), _float(lat)
    if lon is None or lat is None:
        lon = lat = None
    params = {
        "raw_text": raw_text,
        "photo_url": photo_url,
        "structured": _jsonb(structured),
        "category": _str(structured.get("category")),
        "urgency": _int(structured.get("urgency")),
        "department": _str(structured.get("department")),
        "embedding": None if embedding is None else [float(v) for v in embedding],
        "lon": lon,
        "lat": lat,
        "location_confidence": _float(location_confidence),
        "duplicate_of": _int(duplicate_of),
        "source": _str(source) or "web",
        "created_at": _ts(created_at),
    }
    with _cursor(conn) as cur:
        cur.execute(
            """
            insert into reports (raw_text, photo_url, structured, category, urgency, department,
                                 embedding, geom, location_confidence, duplicate_of, source, created_at)
            values (%(raw_text)s, %(photo_url)s, %(structured)s, %(category)s, %(urgency)s, %(department)s,
                    %(embedding)s::real[],
                    ST_SetSRID(ST_MakePoint(%(lon)s::float8, %(lat)s::float8), 4326),
                    %(location_confidence)s, %(duplicate_of)s, %(source)s,
                    coalesce(%(created_at)s::timestamptz, now()))
            returning id
            """,
            params,
        )
        return int(cur.fetchone()["id"])


def insert_evidence(conn: psycopg.Connection, ev: EvidenceIn) -> int:
    """Insert one evidence row (sensor peak or located report)."""
    params = {
        "segment_id": _int(ev.segment_id),
        "source": _str(ev.source),
        "type": _str(ev.type),
        "severity": _clamp01(ev.severity),
        "ts": _ts(ev.ts),
        "ride_id": _int(ev.ride_id),
        "report_id": _int(ev.report_id),
        "lon": float(ev.lon),
        "lat": float(ev.lat),
        "details": _jsonb(ev.details),
    }
    with _cursor(conn) as cur:
        cur.execute(
            """
            insert into evidence (segment_id, source, type, severity, ts, ride_id, report_id, geom, details)
            values (%(segment_id)s, %(source)s, %(type)s, %(severity)s, %(ts)s, %(ride_id)s, %(report_id)s,
                    ST_SetSRID(ST_MakePoint(%(lon)s::float8, %(lat)s::float8), 4326), %(details)s)
            returning id
            """,
            params,
        )
        return int(cur.fetchone()["id"])


def upsert_ride_segments(conn: psycopg.Connection, ride_id: int, rows: list[dict]) -> None:
    """Write per-ride segment RMS (keys: segment_id, rms, samples, passed_at); re-runs overwrite."""
    params = [
        (int(ride_id), int(r["segment_id"]), float(r["rms"]), _int(r.get("samples")), _ts(r.get("passed_at")))
        for r in rows
        if r.get("segment_id") is not None and _float(r.get("rms")) is not None
    ]
    if not params:
        return
    with conn.cursor() as cur:
        cur.executemany(
            """
            insert into ride_segments (ride_id, segment_id, rms, samples, passed_at)
            values (%s, %s, %s, %s, %s)
            on conflict (ride_id, segment_id) do update
               set rms = excluded.rms, samples = excluded.samples, passed_at = excluded.passed_at
            """,
            params,
        )


def recompute_segment_health(conn: psycopg.Connection) -> None:
    """Refresh segments.health / health_rides from ride_segments (see db/functions.sql)."""
    conn.execute("select recompute_segment_health()")


# --------------------------------------------------------------------------- generic reads

def fetch_one(conn: psycopg.Connection, sql: str, params: dict | tuple | None = None) -> dict | None:
    with _cursor(conn) as cur:
        cur.execute(sql, params)
        return cur.fetchone()


def fetch_all(conn: psycopg.Connection, sql: str, params: dict | tuple | None = None) -> list[dict]:
    with _cursor(conn) as cur:
        cur.execute(sql, params)
        return list(cur.fetchall())
