"""Citizen mobile app endpoints (owner A): map, reports, the 25 m pop-up, Yes/No answers (100 m), favourite routes.

The citizen never sees sensor data, evidence, timelines, other people's report texts or any
sensor_* / verify_* field (docs/ARCHITECTURE.md §8.4): every incident leaves this router as a
PublicIncident built by `public_incident`, and road health only as a colour class.
Looking at the map is public; reporting, answering and routes need `Authorization: Bearer`.

Two separate states, never mixed: the confidence `status` (fusion engine) and the city's
`work_status` (todo / in_progress / done, written by the web admin). Once `work_status` is
done the "is it still there?" question stops, so later NO answers can't count against anyone.

Short status lines (`message`) are written in the app's language from `Accept-Language`
(en / pl / uk, default en); everything else is language-neutral data.
"""
from __future__ import annotations

import logging
import math
import re
from datetime import datetime, timezone
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field, model_validator

from backend.api import incidents as incidents_api
from backend.api import reports as reports_api
from backend.api import serializers as ser
from backend.api.deps import DB
from backend.api.segments import _parse_bbox
from backend.auth import CurrentUser, OptionalUser
from backend.models import Mode

log = logging.getLogger(__name__)
router = APIRouter(prefix="/mobile", tags=["mobile"])

QUESTION_RADIUS_M = 25.0      # the automatic "is there a pothole here?" pop-up asks within this radius
ANSWER_RADIUS_M = 100.0       # a Yes/No answer (pop-up or tapped problem) counts within this radius
MAX_ACCURACY_M = 25.0         # both need phone GPS accuracy at or below this
ROUTE_CORRIDOR_M = 30.0       # segments / incidents this close to a favourite route count
GOOD_AT, FAIR_AT = 0.7, 0.4   # health >= 0.7 good, >= 0.4 fair, below poor, null unknown
HEALTH_CLASSES = ("good", "fair", "poor", "unknown")
OPEN_STATUSES = ser.OPEN_STATUSES  # candidate, likely: the question is only asked for these
HIDDEN_STATUSES = ("dismissed", "closed")  # not on the map (detail still opens for old links)
ALONG_MIN_RATIO = 0.3         # a corridor segment must run along the route, not across it
MAX_ROUTES_PER_USER = 50
MAX_EXCLUDE_IDS = 200         # /question?exclude=: incidents skipped with "Not now"
MAX_TEXT_LEN = 4000
OSRM_URL = "https://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}"
OSRM_TIMEOUT_S = 5.0
# Index prefilter for metric checks, in degrees (>= 30 m at Warsaw's latitude); exact check follows.
BOX_DEG = 0.001

LANGS = ("en", "pl", "uk")
DEFAULT_LANG = "en"

# Citizen-facing texts. Plurals: {"one", "few", "many", "other"} picked by plural_form ({n} = the number).
TEXTS: dict[str, dict[str, Any]] = {
    "en": {
        "type": {"road_damage": "road damage", "tram_track": "tram track defect", "streetlight": "streetlight out",
                 "flooding": "flooding", "waste": "litter", "other": "problem"},
        "received": "Report received",
        "no_location": "We couldn't place it on the map; marking the spot helps",
        "first": "You're the first to report this",
        "others": {"one": "{n} other person reported this", "other": "{n} other people reported this"},
        "nobody": "No reports yet",
        "count": {"one": "{n} person reported this", "other": "{n} people reported this"},
        "done": "Fixed by the city",
        "in_progress": "The city is working on it",
        "verified": "Verified",
        "likely": "Likely a real problem",
        "candidate": "Under review",
        "dismissed": "Checks found no problem here",
        "closed": "Closed",
        "sent_to": "Sent to {department}",
        "sent_to_other": "Sent to the relevant office",
        "poor_road": "Bad road (~{m} m)",
        "incident": "{label}",
    },
    "pl": {
        "type": {"road_damage": "uszkodzona jezdnia", "tram_track": "usterka torowiska",
                 "streetlight": "niedziałająca latarnia", "flooding": "podtopienie", "waste": "śmieci",
                 "other": "problem"},
        "received": "Zgłoszenie przyjęte",
        "no_location": "Nie udało się ustalić miejsca; zaznaczenie go na mapie pomoże",
        "first": "To pierwsze zgłoszenie tego problemu",
        "others": {"one": "{n} inna osoba też to zgłosiła", "few": "{n} inne osoby też to zgłosiły",
                   "many": "{n} innych osób też to zgłosiło", "other": "{n} innej osoby też to zgłosiło"},
        "nobody": "Brak zgłoszeń",
        "count": {"one": "{n} osoba to zgłosiła", "few": "{n} osoby to zgłosiły", "many": "{n} osób to zgłosiło",
                  "other": "{n} osoby to zgłosiło"},
        "done": "Naprawione przez miasto",
        "in_progress": "Miasto się tym zajmuje",
        "verified": "Potwierdzone",
        "likely": "Prawdopodobnie prawdziwy problem",
        "candidate": "W trakcie weryfikacji",
        "dismissed": "Kontrole nie wykazały tu problemu",
        "closed": "Zamknięte",
        "sent_to": "Przekazano do: {department}",
        "sent_to_other": "Przekazano do właściwej jednostki",
        "poor_road": "Zła nawierzchnia (~{m} m)",
        "incident": "{label}",
    },
    "uk": {
        "type": {"road_damage": "пошкоджена дорога", "tram_track": "дефект трамвайної колії",
                 "streetlight": "не працює ліхтар", "flooding": "підтоплення", "waste": "сміття",
                 "other": "проблема"},
        "received": "Повідомлення отримано",
        "no_location": "Не вдалося визначити місце; позначка на мапі допоможе",
        "first": "Ви перші повідомили про це",
        "others": {"one": "Ще {n} людина повідомила про це", "few": "Ще {n} людини повідомили про це",
                   "many": "Ще {n} людей повідомили про це", "other": "Ще {n} людини повідомили про це"},
        "nobody": "Ще немає повідомлень",
        "count": {"one": "{n} людина повідомила про це", "few": "{n} людини повідомили про це",
                  "many": "{n} людей повідомили про це", "other": "{n} людини повідомили про це"},
        "done": "Виправлено містом",
        "in_progress": "Місто працює над цим",
        "verified": "Підтверджено",
        "likely": "Ймовірно, справжня проблема",
        "candidate": "На перевірці",
        "dismissed": "Перевірки не виявили тут проблеми",
        "closed": "Закрито",
        "sent_to": "Передано до: {department}",
        "sent_to_other": "Передано до відповідної служби",
        "poor_road": "Погана дорога (~{m} м)",
        "incident": "{label}",
    },
}


def request_lang(accept_language: str | None = Header(None)) -> str:
    """First supported language in Accept-Language ("pl-PL,pl;q=0.9,en;q=0.8" -> "pl"); default en."""
    for part in (accept_language or "").split(","):
        code = part.split(";", 1)[0].strip().lower().split("-", 1)[0]
        if code in LANGS:
            return code
    return DEFAULT_LANG


Lang = Annotated[str, Depends(request_lang)]


def plural_form(n: int, forms: dict[str, str], lang: str) -> str:
    """CLDR plural category for whole numbers (pl/uk: one/few/many, en: one/other), {n} filled in."""
    mod10, mod100 = n % 10, n % 100
    if lang == "pl":
        cat = "one" if n == 1 else "few" if 2 <= mod10 <= 4 and not 12 <= mod100 <= 14 else "many"
    elif lang == "uk":
        cat = ("one" if mod10 == 1 and mod100 != 11
               else "few" if 2 <= mod10 <= 4 and not 12 <= mod100 <= 14 else "many")
    else:
        cat = "one" if n == 1 else "other"
    return forms.get(cat, forms["other"]).replace("{n}", str(n))


def _texts(lang: str) -> dict[str, Any]:
    return TEXTS.get(lang, TEXTS[DEFAULT_LANG])


# --------------------------------------------------------------------------- SQL

PUBLIC_COLS = """i.id, i.type, ST_X(i.geom) as lon, ST_Y(i.geom) as lat, i.address, i.department,
       i.status, i.confidence, i.work_status, i.report_count, i.first_seen, i.last_seen"""

PUBLIC_SELECT = f"select {PUBLIC_COLS}\nfrom incidents i\n"

POINT = "ST_SetSRID(ST_MakePoint(%(lon)s::float8, %(lat)s::float8), 4326)"

# Did this user answer (explicitly) / report this incident? Via users.contributor_id.
MY_INCIDENT_SQL = """
select
  (select cr.answer from citizen_responses cr
     join users u on u.contributor_id = cr.contributor_id
    where u.id = %(user_id)s and cr.incident_id = %(id)s and cr.report_id is null) as my_answer,
  exists (select 1 from reports r
            join users u on u.contributor_id = r.contributor_id
            join evidence e on e.report_id = r.id
            join incident_evidence ie on ie.evidence_id = e.id
           where u.id = %(user_id)s and ie.incident_id = %(id)s) as i_reported
"""

# Nearest askable incident: open, not fixed, within 25 m, never answered or reported by this user.
QUESTION_SQL = f"""
select {PUBLIC_COLS},
       ST_Distance(i.geom::geography, {POINT}::geography) as distance_m
from incidents i
where i.status = any(%(open)s) and i.work_status <> 'done'
  and i.id <> all(%(exclude)s::bigint[])
  and i.geom && ST_Expand({POINT}, {BOX_DEG})
  and ST_DWithin(i.geom::geography, {POINT}::geography, %(radius)s)
  and not exists (select 1 from citizen_responses cr
                    join users u on u.contributor_id = cr.contributor_id
                   where cr.incident_id = i.id and u.id = %(user_id)s)
order by distance_m, i.id
limit 1
"""

ANSWER_TARGET_SQL = f"""
select {PUBLIC_COLS},
       ST_Distance(i.geom::geography, {POINT}::geography) as distance_m
from incidents i
where i.id = %(id)s
"""

ALREADY_ANSWERED_SQL = """
select 1 as answered from citizen_responses where incident_id = %(id)s and contributor_id = %(contributor_id)s
"""

CONTRIBUTOR_TRUST_SQL = "select trust from contributors where id = %(id)s"

MY_REPORTS_SQL = """
select r.id, r.raw_text, r.created_at, r.category, r.department, r.photo_url,
       (select ie.incident_id from evidence e
          join incident_evidence ie on ie.evidence_id = e.id
         where e.report_id = r.id order by ie.incident_id limit 1) as incident_id
from reports r
join users u on u.contributor_id = r.contributor_id
where u.id = %(user_id)s
order by r.created_at desc, r.id desc
limit %(limit)s
"""

ME_SQL = """
select c.id, c.trust, c.correct, c.incorrect,
       (select count(*) from reports r where r.contributor_id = c.id) as reports_count,
       (select count(*) from citizen_responses cr
         where cr.contributor_id = c.id and cr.report_id is null) as answers_count
from users u
join contributors c on c.id = u.contributor_id
where u.id = %(user_id)s
"""

SEGMENTS_SQL = """
select s.id, s.mode, s.health, ST_AsGeoJSON(s.geom, 6) as geojson
from segments s
where s.health is not null
  and s.geom && ST_MakeEnvelope(%(min_lon)s, %(min_lat)s, %(max_lon)s, %(max_lat)s, 4326)
  and (%(mode)s::text is null or s.mode = %(mode)s::text)
order by s.id
limit %(limit)s
"""

LINES_SQL = """
select distinct r.vehicle_line as line, r.mode
from rides r
where r.vehicle_line is not null and r.vehicle_line <> ''
  and (%(mode)s::text is null or r.mode = %(mode)s::text)
"""

ROUTE_COLS = """id, name, kind, ST_X(start_geom) as start_lon, ST_Y(start_geom) as start_lat,
       ST_X(end_geom) as end_lon, ST_Y(end_geom) as end_lat, line, mode, created_at"""

ROUTES_SQL = f"select {ROUTE_COLS}\nfrom favorite_routes where user_id = %(user_id)s order by created_at desc, id desc"

ROUTE_SQL = f"select {ROUTE_COLS}\nfrom favorite_routes where id = %(id)s and user_id = %(user_id)s"

ROUTE_COUNT_SQL = "select count(*) as n from favorite_routes where user_id = %(user_id)s"

ROUTE_INSERT_SQL = f"""
insert into favorite_routes (user_id, name, kind, start_geom, end_geom, line, mode)
values (%(user_id)s, %(name)s, %(kind)s,
        ST_SetSRID(ST_MakePoint(%(start_lon)s::float8, %(start_lat)s::float8), 4326),
        ST_SetSRID(ST_MakePoint(%(end_lon)s::float8, %(end_lat)s::float8), 4326),
        %(line)s, %(mode)s)
returning {ROUTE_COLS}
"""

ROUTE_DELETE_SQL = "delete from favorite_routes where id = %(id)s and user_id = %(user_id)s returning id"

# Segments a line's rides covered, in ride order (the path is stitched from the longest ride).
LINE_RIDE_SEGMENTS_SQL = """
select rs.ride_id, rs.segment_id, ST_AsGeoJSON(s.geom, 6) as geojson
from ride_segments rs
join rides r on r.id = rs.ride_id
join segments s on s.id = rs.segment_id
where r.vehicle_line = %(line)s and (%(mode)s::text is null or r.mode = %(mode)s::text)
order by rs.ride_id, rs.passed_at nulls last, rs.segment_id
"""

# `route` = the path as a GeoJSON LineString; distance along it = locate(point) * length (metres).
# covered_m = how much of the route a segment runs along (cross streets in the corridor ~ 0 m).
ROUTE_CTE = """
with r as (
    select g, ST_Length(g::geography) as len
    from (select ST_SetSRID(ST_GeomFromGeoJSON(%(route)s::text), 4326) as g) x
)
"""

ROUTE_SEGMENTS_SELECT = ROUTE_CTE + """
select s.id, s.mode, s.health, ST_AsGeoJSON(s.geom, 6) as geojson,
       ST_Length(s.geom::geography) as length_m,
       ST_X(ST_LineInterpolatePoint(s.geom, 0.5)) as lon, ST_Y(ST_LineInterpolatePoint(s.geom, 0.5)) as lat,
       ST_LineLocatePoint(r.g, ST_LineInterpolatePoint(s.geom, 0.5)) * r.len as along_m,
       abs(ST_LineLocatePoint(r.g, ST_EndPoint(s.geom)) - ST_LineLocatePoint(r.g, ST_StartPoint(s.geom)))
         * r.len as covered_m
from segments s, r
"""

CORRIDOR_SEGMENTS_SQL = ROUTE_SEGMENTS_SELECT + f"""
where s.mode = %(mode)s and s.geom && ST_Expand(r.g, {BOX_DEG})
  and ST_DWithin(s.geom::geography, r.g::geography, %(corridor)s)
order by along_m, s.id
"""

LINE_SEGMENTS_SQL = ROUTE_SEGMENTS_SELECT + """
where s.id = any(%(ids)s)
order by along_m, s.id
"""

ROUTE_INCIDENTS_SQL = ROUTE_CTE + f"""
select {PUBLIC_COLS},
       ST_LineLocatePoint(r.g, i.geom) * r.len as along_m
from incidents i, r
where i.status = any(%(statuses)s) and i.work_status <> 'done'
  and i.geom && ST_Expand(r.g, {BOX_DEG})
  and ST_DWithin(i.geom::geography, r.g::geography, %(corridor)s)
order by along_m, i.id
"""

# --------------------------------------------------------------------------- pure helpers


def health_class(health: Any) -> str:
    """segments.health (0 bad .. 1 healthy) -> good / fair / poor / unknown."""
    if health is None:
        return "unknown"
    h = float(health)
    if math.isnan(h):
        return "unknown"
    return "good" if h >= GOOD_AT else "fair" if h >= FAIR_AT else "poor"


def public_incident(row: dict) -> dict:
    """PublicIncident (§8.4): never sensor_*, verify_*, evidence, timeline or report texts."""
    return {
        "id": int(row["id"]),
        "type": row.get("type"),
        "lon": ser.num(row.get("lon"), 7),
        "lat": ser.num(row.get("lat"), 7),
        "address": row.get("address"),
        "department": row.get("department"),
        "status": row.get("status"),
        "confidence": ser.num(row.get("confidence")) or 0.0,
        "work_status": row.get("work_status") or "todo",
        "report_count": int(row.get("report_count") or 0),
        "first_seen": ser.iso(row.get("first_seen")),
        "last_seen": ser.iso(row.get("last_seen")),
    }


def public_segment(row: dict) -> dict:
    seg = ser.segment_json(row)
    return {"id": seg["id"], "mode": seg["mode"], "health_class": health_class(row.get("health")),
            "path": seg["path"]}


def _sent_to(department: str | None, t: dict[str, Any]) -> str:
    return t["sent_to_other"] if department == "inne" else t["sent_to"].format(department=department)


def status_parts(incident: dict | None, *, reporter: bool, department: str | None = None,
                 lang: str = DEFAULT_LANG) -> list[str]:
    """Short status pieces: who reported, what the city / the engine says, where it went."""
    t = _texts(lang)
    if incident is None:
        parts = [t["received"], t["no_location"]]
        if department:
            parts.append(_sent_to(department, t))
        return parts

    count = int(incident.get("report_count") or 0)
    parts: list[str] = []
    if reporter:
        others = max(count - 1, 0)
        parts.append(t["first"] if others == 0 else plural_form(others, t["others"], lang))
    else:
        parts.append(t["nobody"] if count == 0 else plural_form(count, t["count"], lang))

    work, status = incident.get("work_status") or "todo", incident.get("status")
    if work in ("done", "in_progress"):
        parts.append(t[work])
    elif status in ("verified", "likely", "candidate", "dismissed", "closed"):
        parts.append(t[status])

    department = incident.get("department") or department
    if department and work != "done":
        parts.append(_sent_to(department, t))
    return parts


def report_message(incident: dict | None, department: str | None = None, lang: str = DEFAULT_LANG) -> str:
    """For the reporter: "23 other people reported this. The city is working on it. Sent to ZDM."."""
    return ". ".join(status_parts(incident, reporter=True, department=department, lang=lang)) + "."


def detail_message(incident: dict, *, reporter: bool, lang: str = DEFAULT_LANG) -> str:
    """One line for the incident sheet: "24 people reported this · Verified · Sent to ZDM"."""
    return " · ".join(status_parts(incident, reporter=reporter, lang=lang))


def parse_ids(raw: str | None, limit: int = MAX_EXCLUDE_IDS) -> list[int]:
    """'12, 7,x,,7' -> [12, 7]: unique ints in order, non-ints ignored, at most `limit`."""
    out: dict[int, None] = {}
    for part in (raw or "").split(","):
        part = part.strip()
        if re.fullmatch(r"-?[0-9]{1,18}", part):
            out[int(part)] = None
            if len(out) >= limit:
                break
    return list(out)


def natural_key(line: str) -> list[tuple[int, Any]]:
    """'4' < '17' < '175' < 'N01' < 'N11' (digits compared as numbers)."""
    return [(0, int(t)) if t.isascii() and t.isdigit() else (1, t) for t in re.split(r"([0-9]+)", line) if t]


def _d2(a: list[float], b: list[float]) -> float:
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2


def stitch_path(paths: list[list[list[float]]]) -> list[list[float]]:
    """Concatenate segment polylines in order, flipping each to continue from the previous end."""
    out: list[list[float]] = []
    for path in paths:
        if not path:
            continue
        if out:
            if _d2(out[-1], path[-1]) < _d2(out[-1], path[0]):
                path = path[::-1]
            if path[0] == out[-1]:
                path = path[1:]
        out.extend(path)
    return out


def _covered(s: dict) -> float:
    """Metres of the route a segment runs along (its length projected on the route, at most its length)."""
    length = float(s.get("length_m") or 0)
    covered = s.get("covered_m")
    return length if covered is None else min(float(covered), length)


def runs_along(s: dict) -> bool:
    """True unless the segment mostly crosses the route (projects onto < 30 % of its length)."""
    return _covered(s) >= ALONG_MIN_RATIO * float(s.get("length_m") or 0)


def path_length_m(path: list[list[float]]) -> float:
    """Length of a [[lon, lat], ...] polyline in metres (equirectangular; fine at city scale)."""
    total = 0.0
    for (x1, y1), (x2, y2) in zip(path, path[1:]):
        k = math.cos(math.radians((y1 + y2) / 2))
        total += math.hypot((x2 - x1) * 111_320 * k, (y2 - y1) * 110_540)
    return total


def route_summary(segments: list[dict], route_length_m: float | None = None) -> dict:
    """Metres per health class along the route; overall = class of the length-weighted mean health.

    Parallel ways (dual carriageways, the two rails of a tram line) both run along the route, so
    the per-class metres are scaled down proportionally when they add up to more than the route.
    """
    metres = dict.fromkeys(HEALTH_CLASSES, 0.0)
    weighted = measured = 0.0
    for s in segments:
        length = _covered(s)
        metres[health_class(s.get("health"))] += length
        if s.get("health") is not None:
            weighted += float(s["health"]) * length
            measured += length
    total = sum(metres.values())
    scale = route_length_m / total if route_length_m and total > route_length_m else 1.0
    out = {f"{c}_m": round(m * scale, 1) for c, m in metres.items()}
    out["overall"] = health_class(weighted / measured) if measured > 0 else "unknown"
    return out


def poor_road_warnings(segments: list[dict], lang: str = DEFAULT_LANG) -> list[dict]:
    """One warning per run of poor segments along the route (good/fair segments end a run)."""
    warnings: list[dict] = []
    run: dict | None = None

    def flush() -> None:
        if run:
            warnings.append({"kind": "poor_road", "incident_id": None, "lon": ser.num(run["lon"], 7),
                             "lat": ser.num(run["lat"], 7), "distance_along_m": round(run["along"], 1),
                             "message": _texts(lang)["poor_road"].format(m=max(round(run["length"]), 1))})

    for s in sorted(segments, key=lambda s: float(s.get("along_m") or 0)):
        cls = health_class(s.get("health"))
        if cls == "poor":
            if run is None:
                run = {"lon": s.get("lon"), "lat": s.get("lat"), "along": float(s.get("along_m") or 0), "length": 0.0}
            run["length"] += _covered(s)
        elif cls in ("good", "fair"):
            flush()
            run = None
    flush()
    return warnings


def incident_warning(row: dict, lang: str = DEFAULT_LANG) -> dict:
    t = _texts(lang)
    label = t["type"].get(row.get("type") or "", t["type"]["other"])
    address = row.get("address")
    return {"kind": "incident", "incident_id": int(row["id"]), "lon": ser.num(row.get("lon"), 7),
            "lat": ser.num(row.get("lat"), 7), "distance_along_m": round(float(row.get("along_m") or 0), 1),
            # The app adds where it is ("2 km ahead: ..."), so the message is just what and where.
            "message": t["incident"].format(label=label[:1].upper() + label[1:]) + (f" · {address}" if address else "")}


def route_json(row: dict) -> dict:
    """FavoriteRoute."""
    def point(lon: Any, lat: Any) -> list[float] | None:
        return None if lon is None or lat is None else [ser.num(lon, 7), ser.num(lat, 7)]

    return {
        "id": int(row["id"]),
        "name": row.get("name"),
        "kind": row.get("kind"),
        "start": point(row.get("start_lon"), row.get("start_lat")),
        "end": point(row.get("end_lon"), row.get("end_lat")),
        "line": row.get("line"),
        "mode": row.get("mode"),
        "created_at": ser.iso(row.get("created_at")),
    }


# --------------------------------------------------------------------------- DB helpers


def _load_public(conn, incident_id: int) -> dict | None:
    from backend import db

    return db.fetch_one(conn, PUBLIC_SELECT + "where i.id = %(id)s", {"id": incident_id})


def _contributor(conn, user: dict) -> dict:
    """The signed-in user's contributor (created and linked on first use); 401 for a deleted account."""
    from backend.auth import store

    try:
        return store.contributor_for_user(conn, int(user["id"]))
    except LookupError as exc:
        raise HTTPException(401, "account not found", headers={"WWW-Authenticate": "Bearer"}) from exc


_osrm_cache: dict[tuple[float, float, float, float], list[list[float]]] = {}


def osrm_route(start: list[float], end: list[float]) -> list[list[float]] | None:
    """Driving path [[lon, lat], ...] from the public OSRM router, or None (timeout, error, no route)."""
    key = (round(start[0], 6), round(start[1], 6), round(end[0], 6), round(end[1], 6))
    if key in _osrm_cache:
        return _osrm_cache[key]
    import httpx

    url = OSRM_URL.format(lon1=key[0], lat1=key[1], lon2=key[2], lat2=key[3])
    try:
        resp = httpx.get(url, params={"overview": "full", "geometries": "geojson"}, timeout=OSRM_TIMEOUT_S,
                         headers={"User-Agent": "CityEcho/1.0 (smart city demo)"})
        resp.raise_for_status()
        coords = resp.json()["routes"][0]["geometry"]["coordinates"]
        path = [[float(c[0]), float(c[1])] for c in coords]
    except Exception as exc:  # network, timeout, NoRoute: fall back to a straight line
        log.warning("OSRM route failed (%s); using a straight line", exc)
        return None
    if len(path) < 2:
        return None
    if len(_osrm_cache) > 256:
        _osrm_cache.clear()
    _osrm_cache[key] = path
    return path


def _line_path(conn, line: str, mode: str | None) -> tuple[list[list[float]], list[int]]:
    """(path, segment ids) for a bus/tram line from its rides' ride_segments."""
    from backend import db

    rows = db.fetch_all(conn, LINE_RIDE_SEGMENTS_SQL, {"line": line, "mode": mode})
    by_ride: dict[Any, list[dict]] = {}
    for r in rows:
        by_ride.setdefault(r["ride_id"], []).append(r)
    if not by_ride:
        return [], []
    longest = max(by_ride.values(), key=len)
    path = stitch_path([public_segment({"id": r["segment_id"], "geojson": r["geojson"]})["path"] for r in longest])
    ids = list(dict.fromkeys(int(r["segment_id"]) for r in rows))
    return path, ids


# --------------------------------------------------------------------------- models


class AnswerIn(BaseModel):
    answer: Literal["yes", "no"]
    lon: float = Field(ge=-180, le=180)
    lat: float = Field(ge=-90, le=90)
    accuracy_m: float = Field(ge=0, description="phone GPS accuracy in metres; must be <= 25 (MAX_ACCURACY_M)")


class RouteIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    kind: Literal["points", "line"]
    start: tuple[float, float] | None = Field(None, description="[lon, lat]")
    end: tuple[float, float] | None = Field(None, description="[lon, lat]")
    line: str | None = Field(None, min_length=1, max_length=20)
    mode: Mode | None = None

    @model_validator(mode="after")
    def _check(self) -> "RouteIn":
        self.name = self.name.strip()
        if not self.name:
            raise ValueError("name must not be empty")
        if self.kind == "points":
            if self.start is None or self.end is None:
                raise ValueError("kind 'points' needs start and end")
            for lon, lat in (self.start, self.end):
                if not (-180 <= lon <= 180 and -90 <= lat <= 90):
                    raise ValueError(f"invalid coordinates lon={lon} lat={lat}")
            if tuple(self.start) == tuple(self.end):
                raise ValueError("start and end must differ")
            self.line = None
        else:
            if not self.line or not self.line.strip():
                raise ValueError("kind 'line' needs line")
            self.line = self.line.strip()
            self.start = self.end = None
        return self


# --------------------------------------------------------------------------- endpoints


@router.get("/ping")
def ping() -> dict:
    return {"ok": True}


@router.get("/incidents")
def list_incidents(
    conn: DB,
    bbox: str | None = Query(None, description="minLon,minLat,maxLon,maxLat"),
    limit: int = Query(500, ge=1, le=5000),
) -> dict:
    """Map pins: PublicIncidents (no dismissed / closed), newest activity first."""
    from backend import db

    where, params = ["i.status <> all(%(hidden)s)"], {"hidden": list(HIDDEN_STATUSES), "limit": limit}
    if bbox:
        where.append("i.geom && ST_MakeEnvelope(%(min_lon)s, %(min_lat)s, %(max_lon)s, %(max_lat)s, 4326)")
        params.update(_parse_bbox(bbox))
    sql = PUBLIC_SELECT + "where " + " and ".join(where) + "\norder by i.last_seen desc, i.id desc limit %(limit)s"
    return {"incidents": [public_incident(r) for r in db.fetch_all(conn, sql, params)]}


@router.get("/incidents/{incident_id}")
def get_incident(incident_id: int, conn: DB, user: OptionalUser, lang: Lang) -> dict:
    """Short incident sheet: PublicIncident + my_answer, i_reported and a status line."""
    from backend import db

    row = _load_public(conn, incident_id)
    if row is None:
        raise HTTPException(404, f"incident {incident_id} not found")
    mine = (db.fetch_one(conn, MY_INCIDENT_SQL, {"id": incident_id, "user_id": int(user["id"])}) or {}) if user else {}
    answer = mine.get("my_answer")
    reported = bool(mine.get("i_reported"))
    out = public_incident(row)
    out.update(my_answer=None if answer is None else ("yes" if answer else "no"), i_reported=reported,
               message=detail_message(row, reporter=reported, lang=lang))
    return out


@router.get("/segments")
def list_segments(
    conn: DB,
    bbox: str = Query(..., description="minLon,minLat,maxLon,maxLat"),
    mode: Mode | None = None,
    limit: int = Query(5000, ge=1, le=20_000),
) -> dict:
    """Measured segments only, health as a colour class (never the raw value)."""
    from backend import db

    params = {**_parse_bbox(bbox), "mode": mode.value if mode else None, "limit": limit}
    return {"segments": [public_segment(r) for r in db.fetch_all(conn, SEGMENTS_SQL, params)]}


@router.get("/lines")
def list_lines(conn: DB, mode: Mode | None = None) -> dict:
    """Bus/tram lines that have recorded rides (for line-based favourite routes)."""
    from backend import db

    rows = db.fetch_all(conn, LINES_SQL, {"mode": mode.value if mode else None})
    rows = sorted(rows, key=lambda r: (natural_key(str(r["line"])), r.get("mode") or ""))
    return {"lines": [{"line": str(r["line"]), "mode": r.get("mode")} for r in rows]}


@router.get("/question")
def question(
    conn: DB,
    user: CurrentUser,
    lon: float = Query(..., ge=-180, le=180),
    lat: float = Query(..., ge=-90, le=90),
    accuracy_m: float = Query(..., ge=0),
    exclude: str | None = Query(None, description="comma-separated incident ids the user skipped (\"Not now\")"),
) -> dict:
    """The incident to ask "is it still there?" about, or null (bad GPS / nothing within 25 m)."""
    from backend import db

    if accuracy_m > MAX_ACCURACY_M:
        return {"incident": None, "distance_m": None}
    row = db.fetch_one(conn, QUESTION_SQL, {"lon": lon, "lat": lat, "radius": QUESTION_RADIUS_M,
                                            "open": list(OPEN_STATUSES), "user_id": int(user["id"]),
                                            "exclude": parse_ids(exclude)})
    if row is None:
        return {"incident": None, "distance_m": None}
    return {"incident": public_incident(row), "distance_m": round(float(row["distance_m"]), 1)}


def record_answer(conn, user: dict, incident_id: int, answer: str, lon: float, lat: float,
                  accuracy_m: float) -> dict:
    """The one place a citizen Yes/No is accepted (this router and backend/api/responses.py).

    Signed-in user, GPS accuracy <= MAX_ACCURACY_M, within ANSWER_RADIUS_M of the incident, incident
    still open and not fixed, once per user. Weighted by trust; the incident is re-assessed.
    """
    from backend import db
    from backend.fusion import incidents as fusion_incidents, trust

    if accuracy_m > MAX_ACCURACY_M:
        raise HTTPException(422, f"GPS accuracy must be <= {MAX_ACCURACY_M:g} m")
    row = db.fetch_one(conn, ANSWER_TARGET_SQL, {"id": incident_id, "lon": lon, "lat": lat})
    if row is None:
        raise HTTPException(404, f"incident {incident_id} not found")
    if (row.get("work_status") or "todo") == "done":
        raise HTTPException(409, "the city already fixed this")
    if row.get("status") not in OPEN_STATUSES:
        raise HTTPException(409, f"incident {incident_id} is {row.get('status')}")
    if float(row["distance_m"]) > ANSWER_RADIUS_M:
        raise HTTPException(403, f"you must be within {ANSWER_RADIUS_M:g} m of the incident")
    contributor = _contributor(conn, user)
    cid = int(contributor["id"])
    if db.fetch_one(conn, ALREADY_ANSWERED_SQL, {"id": incident_id, "contributor_id": cid}):
        raise HTTPException(409, "already answered")

    trust.record_vote(conn, incident_id, cid, answer == "yes")
    fusion_incidents.refresh_incident(conn, incident_id)
    out = public_incident(_load_public(conn, incident_id) or row)
    trust_row = db.fetch_one(conn, CONTRIBUTOR_TRUST_SQL, {"id": cid}) or contributor  # settle may move it
    return {"incident_id": incident_id, "status": out["status"], "confidence": out["confidence"],
            "work_status": out["work_status"], "contributor_trust": ser.num(trust_row.get("trust"))}


@router.post("/incidents/{incident_id}/answer")
def answer(incident_id: int, body: AnswerIn, conn: DB, user: CurrentUser) -> dict:
    """YES/NO from within 100 m (GPS accuracy <= 25 m), once per incident, weighted by trust."""
    return record_answer(conn, user, incident_id, body.answer, body.lon, body.lat, body.accuracy_m)


@router.post("/reports")
def create_report(
    conn: DB,
    user: CurrentUser,
    lang: Lang,
    text: str = Form(...),
    lon: float | None = Form(None),
    lat: float | None = Form(None),
    photo: UploadFile | None = File(None),
) -> dict:
    """Submit a complaint as the signed-in user (multipart). Same pipeline as POST /reports."""
    from backend.triage import pipeline as triage_pipeline

    text = text.strip()
    if not text:
        raise HTTPException(422, "text must not be empty")
    if len(text) > MAX_TEXT_LEN:
        raise HTTPException(422, f"text too long (max {MAX_TEXT_LEN} characters)")
    try:
        pin = reports_api._pin(lon, lat)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    photo_bytes = photo.file.read(reports_api.MAX_PHOTO_BYTES + 1) if photo is not None else None
    if photo_bytes and len(photo_bytes) > reports_api.MAX_PHOTO_BYTES:
        raise HTTPException(413, "photo too large (max 15 MB)")

    contributor = _contributor(conn, user)
    created_at = datetime.now(timezone.utc)
    result = triage_pipeline.process_report(conn, text, pin=pin, photo_bytes=photo_bytes or None,
                                            created_at=created_at, source="web",
                                            contributor_id=int(contributor["id"]))
    incident_ids = reports_api._ingest(conn, result.get("evidence_id"))
    incident = incidents_api.load_incident(conn, incident_ids[0]) if incident_ids else None
    incident = reports_api._maybe_request_verification(conn, incident)
    public = _load_public(conn, int(incident["id"])) if incident else None

    structured = result.get("structured") or {}
    return _mobile_report({"id": result["report_id"], "raw_text": text, "created_at": created_at,
                           "category": structured.get("category"), "department": structured.get("department"),
                           "photo_url": result.get("photo_url")}, public, lang)


def _mobile_report(report: dict, incident: dict | None, lang: str = DEFAULT_LANG) -> dict:
    """MobileReport from a reports row (+ public incident row or None)."""
    department = (incident or {}).get("department") or report.get("department")
    return {
        "report_id": int(report["id"]),
        "text": report.get("raw_text"),
        "created_at": ser.iso(report.get("created_at")),
        "category": report.get("category"),
        "department": department,
        "photo_url": report.get("photo_url"),
        "incident": public_incident(incident) if incident else None,
        "others_count": max(int(incident.get("report_count") or 0) - 1, 0) if incident else 0,
        "message": report_message(incident, department, lang),
    }


@router.get("/reports")
def my_reports(conn: DB, user: CurrentUser, lang: Lang, limit: int = Query(100, ge=1, le=500)) -> dict:
    """The signed-in user's own reports, newest first, each with its incident's public view."""
    from backend import db

    rows = db.fetch_all(conn, MY_REPORTS_SQL, {"user_id": int(user["id"]), "limit": limit})
    ids = sorted({int(r["incident_id"]) for r in rows if r.get("incident_id") is not None})
    incidents = {int(i["id"]): i for i in db.fetch_all(conn, PUBLIC_SELECT + "where i.id = any(%(ids)s)",
                                                       {"ids": ids})} if ids else {}
    return {"reports": [_mobile_report(r, incidents.get(int(r["incident_id"])) if r.get("incident_id") else None, lang)
                        for r in rows]}


@router.get("/me")
def me(conn: DB, user: CurrentUser) -> dict:
    """Profile: user, earned trust and activity counts (defaults before the first report/answer)."""
    from backend import db
    from backend.auth import store
    from backend.fusion import trust

    row = store.get_user(conn, int(user["id"]))
    if row is None:
        raise HTTPException(401, "account not found", headers={"WWW-Authenticate": "Bearer"})
    stats = db.fetch_one(conn, ME_SQL, {"user_id": int(user["id"])}) or {}
    return {
        "user": store.public_user(row),
        "trust": ser.num(stats.get("trust")) if stats else round(trust.DEFAULT_TRUST, 4),
        "correct": int(stats.get("correct") or 0),
        "incorrect": int(stats.get("incorrect") or 0),
        "reports_count": int(stats.get("reports_count") or 0),
        "answers_count": int(stats.get("answers_count") or 0),
    }


@router.get("/routes")
def list_routes(conn: DB, user: CurrentUser) -> dict:
    from backend import db

    return {"routes": [route_json(r) for r in db.fetch_all(conn, ROUTES_SQL, {"user_id": int(user["id"])})]}


@router.post("/routes")
def create_route(body: RouteIn, conn: DB, user: CurrentUser) -> dict:
    """Save a favourite route: start/end pins or a bus/tram line."""
    from backend import db

    uid = int(user["id"])
    if int((db.fetch_one(conn, ROUTE_COUNT_SQL, {"user_id": uid}) or {}).get("n") or 0) >= MAX_ROUTES_PER_USER:
        raise HTTPException(409, f"at most {MAX_ROUTES_PER_USER} favourite routes")
    start, end = body.start or (None, None), body.end or (None, None)
    row = db.fetch_one(conn, ROUTE_INSERT_SQL, {
        "user_id": uid, "name": body.name, "kind": body.kind,
        "start_lon": start[0], "start_lat": start[1], "end_lon": end[0], "end_lat": end[1],
        "line": body.line, "mode": body.mode.value if body.mode else None,
    })
    return route_json(row)


@router.delete("/routes/{route_id}")
def delete_route(route_id: int, conn: DB, user: CurrentUser) -> dict:
    from backend import db

    if db.fetch_one(conn, ROUTE_DELETE_SQL, {"id": route_id, "user_id": int(user["id"])}) is None:
        raise HTTPException(404, f"route {route_id} not found")
    return {"ok": True}


@router.get("/routes/{route_id}/quality")
def route_quality(route_id: int, conn: DB, user: CurrentUser, lang: Lang) -> dict:
    """Road quality along a favourite route: coloured segments, metres per class, warnings ahead."""
    from backend import db

    row = db.fetch_one(conn, ROUTE_SQL, {"id": route_id, "user_id": int(user["id"])})
    if row is None:
        raise HTTPException(404, f"route {route_id} not found")
    route = route_json(row)

    if route["kind"] == "line":
        path, ids = _line_path(conn, route["line"], route["mode"])
        sql, extra = LINE_SEGMENTS_SQL, {"ids": ids}
    else:
        path = osrm_route(route["start"], route["end"]) or [route["start"], route["end"]]
        sql, extra = CORRIDOR_SEGMENTS_SQL, {"mode": route["mode"] or Mode.ROAD.value, "corridor": ROUTE_CORRIDOR_M}

    segments: list[dict] = []
    warnings: list[dict] = []
    if len(path) >= 2:
        import json

        geojson = json.dumps({"type": "LineString", "coordinates": path})
        segments = db.fetch_all(conn, sql, {"route": geojson, **extra})
        if route["kind"] == "points":
            segments = [s for s in segments if runs_along(s)]  # drop cross streets inside the corridor
        incidents = db.fetch_all(conn, ROUTE_INCIDENTS_SQL, {
            "route": geojson, "corridor": ROUTE_CORRIDOR_M,
            "statuses": [*OPEN_STATUSES, "verified"]})
        warnings = [incident_warning(r, lang) for r in incidents] + poor_road_warnings(segments, lang)
        warnings.sort(key=lambda w: (w["distance_along_m"], w["kind"]))

    return {
        "route": route,
        "path": path,
        "segments": [public_segment(s) for s in segments],
        "summary": route_summary(segments, path_length_m(path)),
        "warnings": warnings,
    }
