"""Verification loop (spec §C3): the next tram/bus through a reported spot checks it.

1. A report-only incident asks `next_vehicle_for` which live ZTM vehicle reaches it
   first (nearest approaching vehicle, on a line passing the point when GTFS is present)
   and records the request ("tram 17, ~6 min").
2. Every uploaded ride is checked against the open incidents it passed
   (`check_ride_verifications`): a detection is a sensor hit, a clean pass by a vehicle
   that could have felt the problem is a sensor miss. Both feed the confidence engine,
   which moves the incident between candidate / likely / verified / dismissed.

Live positions come from the Warsaw open-data API (busestrams_get). In DEMO_MODE, without
an API key, or on any error, the clearly labelled sample `data/demo/ztm_snapshot.json` is used.
"""
from __future__ import annotations

import json
import logging
import math
import time
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any

import httpx

from backend.config import settings
from backend.db import fetch_all, fetch_one
from backend.fusion.incidents import MATCH_RADIUS_M, refresh_incident
from backend.models import IncidentStatus, IssueType, Mode

log = logging.getLogger(__name__)

KIND_CODES = {"bus": 1, "tram": 2}  # ZTM `type` parameter
AVG_SPEED_KMH = {"tram": 18.0, "bus": 20.0}  # average commercial speed incl. stops
DETOUR_FACTOR = 1.3  # straight line -> street distance
SEARCH_RADIUS_M = 3000.0
STALE_AFTER_S = 300
CACHE_TTL_S = 30.0
HTTP_TIMEOUT_S = 5.0
GTFS_LINE_RADIUS_M = 50.0
WARSAW_BBOX = (20.85, 52.10, 21.27, 52.37)  # minLon, minLat, maxLon, maxLat
SNAPSHOT_PATH = settings.data_dir / "demo" / "ztm_snapshot.json"
GTFS_DIR = settings.data_dir / "gtfs"

try:
    from zoneinfo import ZoneInfo

    _WARSAW_TZ = ZoneInfo("Europe/Warsaw")
except Exception:  # no tz database: CEST is the right offset for most of the hackathon season
    _WARSAW_TZ = timezone(timedelta(hours=2))

_REF_LON, _REF_LAT = 21.0, 52.23
_M_PER_DEG = 111_320.0

# kind -> (monotonic time, source "live" | "sample", vehicles)
_CACHE: dict[str, tuple[float, str, list[dict]]] = {}
# kind -> {vehicle id: (lon, lat)} from the previous snapshot, used to tell approaching vehicles
_PREVIOUS: dict[str, dict[str, tuple[float, float]]] = {}


# -------------------------------------------------------------------------- geometry


def haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Great-circle distance in metres."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 2 * 6_371_000 * math.asin(math.sqrt(a))


def _to_xy(lon: Any, lat: Any) -> tuple[Any, Any]:
    """Local metric projection around Warsaw (good to < 1 % within the city); works on arrays."""
    return ((lon - _REF_LON) * _M_PER_DEG * math.cos(math.radians(_REF_LAT)),
            (lat - _REF_LAT) * _M_PER_DEG)


def eta_minutes(distance_m: float, kind: str) -> int:
    """Straight-line distance × detour / average speed, rounded up, at least 1 minute."""
    minutes = distance_m * DETOUR_FACTOR / (AVG_SPEED_KMH[kind] / 3.6) / 60
    return max(1, math.ceil(round(minutes, 6)))


# -------------------------------------------------------------------------- ZTM positions


def _kind(kind_or_mode: str) -> str:
    """'tram' (or mode 'tram') -> 'tram'; 'bus' / 'road' -> 'bus'."""
    return "tram" if str(kind_or_mode) == Mode.TRAM else "bus"


def _parse_ztm_time(raw: str) -> datetime:
    """ZTM 'YYYY-MM-DD HH:MM:SS' (Warsaw local time) -> tz-aware UTC."""
    ts = datetime.fromisoformat(str(raw).strip())
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=_WARSAW_TZ)
    return ts.astimezone(timezone.utc)


def parse_ztm(payload: Any, kind: str, now: datetime | None = None) -> list[dict]:
    """Raw ZTM vehicle positions -> [{"id", "line", "lon", "lat", "ts", "kind"}].

    Accepts the bare list returned by dane.um.warszawa.pl/get_ztm_lokalizacja_pojazdow and the
    older {"result": [...]} wrapper (also used by the sample snapshot). Raises ValueError when
    no list is found (the API reports errors as a string or {"result": "false", "error": ...}).
    Drops malformed rows and positions outside Warsaw; when `now` is given, also positions
    older than STALE_AFTER_S.
    """
    result = payload if isinstance(payload, list) else payload.get("result") if isinstance(payload, dict) else None
    if not isinstance(result, list):
        raise ValueError(f"ZTM API error: {payload!r}"[:300])
    min_lon, min_lat, max_lon, max_lat = WARSAW_BBOX
    vehicles = []
    for item in result:
        try:
            lon, lat = float(item["Lon"]), float(item["Lat"])
            ts = _parse_ztm_time(item["Time"])
            line, vehicle_id = str(item["Lines"]).strip(), str(item["VehicleNumber"]).strip()
        except (KeyError, TypeError, ValueError):
            continue
        if not (min_lon <= lon <= max_lon and min_lat <= lat <= max_lat):
            continue
        if now is not None and (now - ts).total_seconds() > STALE_AFTER_S:
            continue
        vehicles.append({"id": vehicle_id, "line": line, "lon": lon, "lat": lat, "ts": ts, "kind": kind})
    return vehicles


def _fetch_ztm(kind: str) -> Any:
    """One POST to the live API (token in the Authorization header); raises on any network / HTTP / JSON problem."""
    resp = httpx.post(settings.ztm_url, json={"type": KIND_CODES[kind]},
                      headers={"Authorization": settings.warsaw_api_key}, timeout=HTTP_TIMEOUT_S)
    resp.raise_for_status()
    return resp.json()


def load_snapshot(kind: str) -> tuple[list[dict], dict[str, tuple[float, float]]]:
    """Sample snapshot -> (vehicles, previous positions). No staleness filter: the sample is static."""
    try:
        data = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
        vehicles = parse_ztm(data.get(kind, {"result": []}), kind)
        previous = parse_ztm(data.get("previous", {}).get(kind, {"result": []}), kind)
    except (OSError, ValueError, AttributeError) as exc:
        log.warning("ZTM sample snapshot unavailable (%s)", exc)
        return [], {}
    return vehicles, {v["id"]: (v["lon"], v["lat"]) for v in previous}


def live_vehicles(kind: str = "tram") -> list[dict]:
    """Current positions of Warsaw trams or buses (30 s cache), falling back to the sample snapshot."""
    kind = _kind(kind)
    cached = _CACHE.get(kind)
    if cached and time.monotonic() - cached[0] < CACHE_TTL_S:
        return list(cached[2])

    vehicles: list[dict] | None = None
    source, previous = "sample", {}
    if not settings.demo_mode and settings.warsaw_api_key:
        try:
            vehicles = parse_ztm(_fetch_ztm(kind), kind, now=datetime.now(timezone.utc))
            if not vehicles:
                raise ValueError("no fresh positions in the response")
            source = "live"
            if cached and cached[1] == "live":
                previous = {v["id"]: (v["lon"], v["lat"]) for v in cached[2]}
        except Exception as exc:  # offline, timeout, HTTP error, bad JSON, API error string
            log.warning("ZTM live positions unavailable (%s); using the sample snapshot", exc)
            vehicles = None
    if vehicles is None:
        vehicles, previous = load_snapshot(kind)

    _PREVIOUS[kind] = previous
    _CACHE[kind] = (time.monotonic(), source, vehicles)
    return list(vehicles)


# -------------------------------------------------------------------------- GTFS (optional)


def _gtfs_kind(route_type: str) -> str | None:
    try:
        t = int(route_type)
    except (TypeError, ValueError):
        return None
    if t == 0 or 900 <= t < 1000:
        return "tram"
    if t == 3 or 700 <= t < 800:
        return "bus"
    return None


@lru_cache(maxsize=1)
def _gtfs_index() -> tuple[Any, list, list[set[tuple[str, str]]]] | None:
    """STRtree over GTFS shapes (local metres) with the (line, kind) pairs using each shape.

    None when data/gtfs/{shapes,trips,routes}.txt are missing or unreadable.
    """
    paths = {name: GTFS_DIR / f"{name}.txt" for name in ("shapes", "trips", "routes")}
    if not all(p.exists() for p in paths.values()):
        return None
    try:
        import numpy as np
        import pandas as pd
        from shapely import LineString, STRtree

        routes = pd.read_csv(paths["routes"], usecols=["route_id", "route_short_name", "route_type"], dtype=str)
        trips = pd.read_csv(paths["trips"], usecols=["route_id", "shape_id"], dtype=str).dropna().drop_duplicates()
        shapes = pd.read_csv(paths["shapes"], usecols=["shape_id", "shape_pt_lat", "shape_pt_lon",
                                                       "shape_pt_sequence"], dtype={"shape_id": str})
        owners_by_shape: dict[str, set[tuple[str, str]]] = {}
        for row in trips.merge(routes, on="route_id").itertuples(index=False):
            kind = _gtfs_kind(row.route_type)
            if kind:
                owners_by_shape.setdefault(row.shape_id, set()).add((str(row.route_short_name).strip(), kind))
        geoms, owners = [], []
        for shape_id, pts in shapes.sort_values(["shape_id", "shape_pt_sequence"]).groupby("shape_id", sort=False):
            if shape_id in owners_by_shape and len(pts) >= 2:
                x, y = _to_xy(pts["shape_pt_lon"].to_numpy(float), pts["shape_pt_lat"].to_numpy(float))
                geoms.append(LineString(np.column_stack([x, y])))
                owners.append(owners_by_shape[shape_id])
    except Exception as exc:
        log.warning("GTFS shapes unreadable (%s); line filter disabled", exc)
        return None
    return (STRtree(geoms), geoms, owners) if geoms else None


def gtfs_lines_near(lon: float, lat: float, kind: str, radius_m: float = GTFS_LINE_RADIUS_M) -> set[str] | None:
    """Lines of `kind` whose GTFS shape passes within `radius_m`; None = unknown (no GTFS / no match)."""
    index = _gtfs_index()
    if index is None:
        return None
    from shapely import Point

    tree, geoms, owners = index
    point = Point(*_to_xy(lon, lat))
    lines = {line for i in tree.query(point.buffer(radius_m)) if geoms[i].distance(point) <= radius_m
             for line, line_kind in owners[i] if line_kind == kind}
    return lines or None


# -------------------------------------------------------------------------- choosing a vehicle


def _approaching(previous: dict[str, tuple[float, float]] | None, vehicle: dict,
                 lon: float, lat: float, dist: float) -> bool | None:
    """True/False when the distance to the point shrank/grew since the previous snapshot; None = unknown."""
    prev = (previous or {}).get(vehicle["id"])
    if prev is None:
        return None
    prev_dist = haversine_m(lon, lat, prev[0], prev[1])
    if abs(prev_dist - dist) < 1.0:  # standing at a stop
        return None
    return dist < prev_dist


def pick_vehicle(vehicles: list[dict], lon: float, lat: float, kind: str,
                 previous: dict[str, tuple[float, float]] | None = None,
                 lines: set[str] | None = None) -> dict | None:
    """Best vehicle within SEARCH_RADIUS_M: approaching > unknown heading > moving away, then nearest."""
    best_key, best = None, None
    for v in vehicles:
        if v.get("kind", kind) != kind or (lines and v["line"] not in lines):
            continue
        dist = haversine_m(lon, lat, v["lon"], v["lat"])
        if dist > SEARCH_RADIUS_M:
            continue
        approaching = _approaching(previous, v, lon, lat, dist)
        key = ({True: 0, None: 1, False: 2}[approaching], dist)
        if best_key is None or key < best_key:
            best_key, best = key, (v, dist, approaching)
    if best is None:
        return None
    v, dist, approaching = best
    return {"vehicle": f"{kind} {v['line']}", "line": v["line"], "eta_min": eta_minutes(dist, kind),
            "distance_m": round(dist, 1), "vehicle_id": v["id"], "approaching": approaching}


def next_vehicle_for(lon: float, lat: float, mode: str) -> dict | None:
    """Next tram (mode 'tram') or bus (mode 'road') likely to pass (lon, lat), with ETA.

    {"vehicle": "tram 17", "line": "17", "eta_min": 6, "distance_m": 1530.2, "vehicle_id", "approaching"}
    """
    kind = _kind(mode)
    vehicles = live_vehicles(kind)
    return pick_vehicle(vehicles, lon, lat, kind, previous=_PREVIOUS.get(kind),
                        lines=gtfs_lines_near(lon, lat, kind))


# -------------------------------------------------------------------------- DB functions

SQL_VERIFY_CONTEXT = """
select i.id, i.type, i.status, ST_X(i.geom) as lon, ST_Y(i.geom) as lat, s.mode as segment_mode,
       exists (select 1 from incident_evidence ie join evidence e on e.id = ie.evidence_id
               where ie.incident_id = i.id and e.source = 'sensor') as has_sensor
from incidents i
left join segments s on s.id = i.segment_id
where i.id = %(id)s
"""

SQL_SET_VERIFY_REQUEST = """
update incidents
set verify_vehicle = %(vehicle)s, verify_eta_min = %(eta_min)s, verify_requested_at = now()
where id = %(id)s
"""

# Unresolved (or verified) incidents whose spot this ride passed, with the ride's mode.
SQL_RIDE_CANDIDATES = """
select i.id, i.type, i.status, rd.mode as ride_mode,
       exists (select 1 from incident_evidence ie join evidence e on e.id = ie.evidence_id
               where ie.incident_id = i.id and e.source = 'sensor' and e.ride_id = %(ride_id)s) as detected
from incidents i
join rides rd on rd.id = %(ride_id)s
where i.status in ('candidate', 'likely', 'verified')
  and exists (select 1 from ride_segments rs join segments s on s.id = rs.segment_id
              where rs.ride_id = %(ride_id)s
                and (rs.segment_id = i.segment_id
                     or ST_DWithin(s.geom::geography, i.geom::geography, %(radius_m)s::float8)))
order by i.id
"""

SQL_SENSOR_MISS = """
update incidents set sensor_misses = sensor_misses + 1, last_miss_at = now()
where id = %(id)s
"""

OPEN_STATUSES = (IncidentStatus.CANDIDATE, IncidentStatus.LIKELY)


def verification_mode(issue_type: str, segment_mode: str | None) -> str:
    """Tram verifies track issues and anything on a tram segment; buses verify roads."""
    if issue_type == IssueType.TRAM_TRACK or segment_mode == Mode.TRAM:
        return Mode.TRAM.value
    return Mode.ROAD.value


def can_request_verification(status: str, has_sensor: bool) -> bool:
    """Only report-only incidents that are still unresolved need a vehicle to check them."""
    return not has_sensor and status in OPEN_STATUSES


def can_detect(issue_type: str, ride_mode: str | None) -> bool:
    """Could this ride have felt the problem? Buses feel road damage, trams feel track damage.

    Streetlights (night-only), flooding and waste are never counted as misses.
    """
    return ((issue_type == IssueType.ROAD_DAMAGE and ride_mode == Mode.ROAD)
            or (issue_type == IssueType.TRAM_TRACK and ride_mode == Mode.TRAM))


def ride_outcome(status: str, issue_type: str, ride_mode: str | None, detected: bool) -> str | None:
    """What a ride passing an incident means for its sensor confidence: 'hit', 'miss' or None."""
    if detected and status in (*OPEN_STATUSES, IncidentStatus.VERIFIED):
        return "hit"
    if status in OPEN_STATUSES and can_detect(issue_type, ride_mode):
        return "miss"
    return None


def request_verification(conn, incident_id: int) -> dict | None:
    """Ask the next vehicle through a report-only incident to verify it.

    Returns {"incident_id", "status", "vehicle", "eta_min"} or None (not eligible / no vehicle).
    """
    inc = fetch_one(conn, SQL_VERIFY_CONTEXT, {"id": incident_id})
    if inc is None or not can_request_verification(inc["status"], bool(inc["has_sensor"])):
        return None
    vehicle = next_vehicle_for(float(inc["lon"]), float(inc["lat"]),
                               verification_mode(inc["type"], inc.get("segment_mode")))
    if vehicle is None:
        return None
    conn.execute(SQL_SET_VERIFY_REQUEST, {"id": incident_id, "vehicle": vehicle["vehicle"],
                                          "eta_min": vehicle["eta_min"]})
    return {"incident_id": incident_id, "status": inc["status"],
            "vehicle": vehicle["vehicle"], "eta_min": vehicle["eta_min"]}


def check_ride_verifications(conn, ride_id: int) -> list[int]:
    """Feed every incident this ride passed (segment match or within 40 m) back to the confidence engine.

    Hit (this ride's evidence is linked; `ingest_evidence` ran first) -> re-assess.
    Miss (a capable vehicle passed without detecting) -> sensor_misses += 1, re-assess.
    Returns the ids of incidents this ride detected that are now verified.
    """
    rows = fetch_all(conn, SQL_RIDE_CANDIDATES, {"ride_id": ride_id, "radius_m": MATCH_RADIUS_M})
    verified: list[int] = []
    for row in rows:
        outcome = ride_outcome(row["status"], row["type"], row.get("ride_mode"), bool(row["detected"]))
        if outcome is None:
            continue
        if outcome == "miss":
            conn.execute(SQL_SENSOR_MISS, {"id": row["id"]})
        refreshed = refresh_incident(conn, row["id"])
        if outcome == "hit" and refreshed.get("status") == IncidentStatus.VERIFIED:
            verified.append(int(row["id"]))
    return verified
