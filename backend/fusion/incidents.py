"""Evidence -> incidents (spec §C1, §C4): cluster, link, assess confidence, score, route.

Each new evidence row (sensor peak or located citizen report) joins an existing
incident (same type, 40 m, 7 days) or opens a new one. A report also counts as its
author's YES answer. The incident is then recomputed from everything linked to it:
the confidence engine (`confidence.py`) turns sensor rides, clean passes and
trust-weighted citizen answers into a confidence and a status (candidate / likely /
verified / dismissed); reaching verified or dismissed settles contributor trust
(`trust.py`). Pure helpers (`found_before_report`, `pick_address`) hold the
remaining rules so they can be tested without PostGIS.
"""
from __future__ import annotations

from datetime import datetime

from backend.db import fetch_one
from backend.fusion import confidence, trust
from backend.fusion.routing import department_for
from backend.fusion.score import priority_score
from backend.models import IncidentStatus, Source

MATCH_RADIUS_M = 40
MATCH_WINDOW_DAYS = 7
PROACTIVE_MIN_RIDES = 2

# -------------------------------------------------------------------------- SQL

SQL_EVIDENCE = """
select e.id, e.source, e.type, e.ts, e.segment_id, e.report_id, r.duplicate_of,
       (select ie.incident_id from incident_evidence ie
         where ie.evidence_id = e.id order by ie.incident_id limit 1) as linked_incident_id
from evidence e
left join reports r on r.id = e.report_id
where e.id = %(id)s
"""

# Incident that already holds the canonical report's evidence (dedup said "same issue").
SQL_CANONICAL_INCIDENT = """
select ie.incident_id
from evidence e
join incident_evidence ie on ie.evidence_id = e.id
join incidents i on i.id = ie.incident_id
where e.report_id = %(report_id)s and i.status not in ('closed', 'dismissed')
order by i.last_seen desc
limit 1
"""

SQL_NEAREST_INCIDENT = """
select i.id
from incidents i, evidence ev
where ev.id = %(evidence_id)s
  and i.status not in ('closed', 'dismissed')
  and i.type = ev.type
  and ST_DWithin(i.geom::geography, ev.geom::geography, %(radius_m)s::float8)
  and i.last_seen > ev.ts - make_interval(days => %(window_days)s::int)
order by i.geom <-> ev.geom
limit 1
"""

SQL_CREATE_INCIDENT = """
insert into incidents (segment_id, type, geom, first_seen, last_seen, department, status)
select segment_id, type, geom, ts, ts, %(department)s, 'candidate'
from evidence
where id = %(evidence_id)s
returning id
"""

SQL_LINK = """
insert into incident_evidence (incident_id, evidence_id)
values (%(incident_id)s, %(evidence_id)s)
on conflict do nothing
"""

# Keep last_seen fresh inside one batch so the 7-day window sees the newest evidence.
SQL_TOUCH = """
update incidents
set first_seen = least(first_seen, %(ts)s), last_seen = greatest(last_seen, %(ts)s)
where id = %(incident_id)s
"""

SQL_INCIDENT_CONTEXT = """
select i.id, i.type, i.status, i.address, i.sensor_misses, s.name as segment_name,
       coalesce(s.vulnerability, 0) as vulnerability
from incidents i
left join segments s on s.id = i.segment_id
where i.id = %(id)s
"""

# One aggregate over all linked evidence. `nth_ride_ts` is the earliest detection
# of the PROACTIVE_MIN_RIDES-th distinct ride (rides ordered by first detection).
SQL_AGGREGATE = """
with ev as (
    select e.source, e.severity, e.ts, e.ride_id, e.details, r.urgency as report_urgency
    from incident_evidence ie
    join evidence e on e.id = ie.evidence_id
    left join reports r on r.id = e.report_id
    where ie.incident_id = %(id)s
), ride_first as (
    select ride_id, min(ts) as first_ts
    from ev
    where source = 'sensor'
    group by ride_id
)
select
    count(*) filter (where source = 'report')                    as report_count,
    count(*) filter (where source = 'sensor')                    as sensor_count,
    count(distinct ride_id) filter (where source = 'sensor')     as sensor_rides,
    coalesce(max(severity) filter (where source = 'sensor'), 0)  as max_severity,
    coalesce(max(coalesce(nullif(details->>'urgency', '')::numeric, report_urgency))
             filter (where source = 'report'), 0)::int            as max_urgency,
    min(ts)                                                      as first_seen,
    max(ts)                                                      as last_seen,
    min(ts) filter (where source = 'report')                     as first_report_ts,
    (select first_ts from ride_first order by first_ts
      offset %(nth_offset)s::int limit 1)                        as nth_ride_ts,
    (select array_agg(sev) from (
        select max(severity) as sev from ev where source = 'sensor' group by ride_id
     ) per_ride)                                                 as ride_severities,
    (select details->>'location_text' from ev
      where source = 'report' and coalesce(details->>'location_text', '') <> ''
      order by ts limit 1)                                       as location_text
from ev
"""

SQL_UPDATE = """
update incidents set
    -- the cached LLM summary goes stale once new reports merge in (right side = old value)
    summary             = case when report_count = %(report_count)s then summary end,
    report_count        = %(report_count)s,
    sensor_count        = %(sensor_count)s,
    sensor_rides        = %(sensor_rides)s,
    max_severity        = %(max_severity)s,
    max_urgency         = %(max_urgency)s,
    first_seen          = coalesce(%(first_seen)s, first_seen),
    last_seen           = coalesce(%(last_seen)s, last_seen),
    sensor_confirmed    = %(sensor_confirmed)s,
    found_before_report = %(found_before_report)s,
    department          = %(department)s,
    address             = %(address)s,
    score               = %(score)s,
    status              = %(status)s,
    confidence          = %(confidence)s,
    sensor_confidence   = %(sensor_confidence)s,
    citizen_confidence  = %(citizen_confidence)s,
    yes_count           = %(yes_count)s,
    no_count            = %(no_count)s,
    verified_at         = case when %(status)s = 'verified'
                               then coalesce(verified_at, now()) else verified_at end
where id = %(id)s
returning *, ST_X(geom) as lon, ST_Y(geom) as lat
"""

# -------------------------------------------------------------------------- pure rules


def found_before_report(sensor_rides: int, nth_ride_ts: datetime | None,
                        first_report_ts: datetime | None) -> bool:
    """Proactive flag: >= PROACTIVE_MIN_RIDES distinct rides saw it, and the ride that
    reached that threshold did so before the first citizen report (or there is none)."""
    if sensor_rides < PROACTIVE_MIN_RIDES or nth_ride_ts is None:
        return False
    return first_report_ts is None or nth_ride_ts < first_report_ts


def pick_address(segment_name: str | None, location_text: str | None,
                 current: str | None = None) -> str | None:
    """Segment street name, else the first report's location text, else keep the current one."""
    for candidate in (segment_name, location_text, current):
        if candidate and str(candidate).strip():
            return str(candidate).strip()
    return None


# -------------------------------------------------------------------------- DB functions


def _match_incident(conn, ev: dict) -> int | None:
    """Duplicate report -> canonical report's incident; else nearest same-type incident."""
    if ev["source"] == Source.REPORT and ev.get("duplicate_of"):
        row = fetch_one(conn, SQL_CANONICAL_INCIDENT, {"report_id": ev["duplicate_of"]})
        if row:
            return int(row["incident_id"])
    row = fetch_one(conn, SQL_NEAREST_INCIDENT, {
        "evidence_id": ev["id"], "radius_m": MATCH_RADIUS_M, "window_days": MATCH_WINDOW_DAYS,
    })
    return int(row["id"]) if row else None


def _create_incident(conn, ev: dict) -> int:
    row = fetch_one(conn, SQL_CREATE_INCIDENT, {
        "evidence_id": ev["id"], "department": department_for(ev["type"]),
    })
    return int(row["id"])


def ingest_evidence(conn, evidence_ids: list[int]) -> list[int]:
    """Attach each evidence row to an incident (existing or new), then refresh the touched ones.

    Evidence that is already linked is not re-matched; its incident is still refreshed
    and returned, so re-ingesting is idempotent. Returns unique incident ids in first-touch order.
    """
    touched: list[int] = []
    for evidence_id in evidence_ids:
        ev = fetch_one(conn, SQL_EVIDENCE, {"id": evidence_id})
        if ev is None:
            continue
        incident_id = ev.get("linked_incident_id")
        if incident_id is None:
            incident_id = _match_incident(conn, ev) or _create_incident(conn, ev)
            params = {"incident_id": incident_id, "evidence_id": ev["id"], "ts": ev["ts"]}
            conn.execute(SQL_LINK, params)
            conn.execute(SQL_TOUCH, params)
        incident_id = int(incident_id)
        if ev["source"] == Source.REPORT and ev.get("report_id"):
            trust.record_report_yes(conn, incident_id, int(ev["report_id"]))
        if incident_id not in touched:
            touched.append(incident_id)
    for incident_id in touched:
        refresh_incident(conn, incident_id)
    return touched


def refresh_incident(conn, incident_id: int) -> dict:
    """Recompute counts, confidence, status, department, address and score from linked evidence.

    Reaching `verified` / `dismissed` settles the trust of everyone who answered.
    Returns the updated incident row (plus `lon`, `lat`). Raises LookupError if it does not exist.
    """
    inc = fetch_one(conn, SQL_INCIDENT_CONTEXT, {"id": incident_id})
    if inc is None:
        raise LookupError(f"incident {incident_id} not found")
    agg = fetch_one(conn, SQL_AGGREGATE, {"id": incident_id, "nth_offset": PROACTIVE_MIN_RIDES - 1}) or {}
    votes = trust.votes_for(conn, incident_id)

    reports = int(agg.get("report_count") or 0)
    sensors = int(agg.get("sensor_count") or 0)
    rides = int(agg.get("sensor_rides") or 0)
    max_severity = float(agg.get("max_severity") or 0.0)
    max_urgency = int(agg.get("max_urgency") or 0)
    both = reports > 0 and sensors > 0
    ride_severities = [float(s or 0.0) for s in (agg.get("ride_severities") or [])]
    a = confidence.assess(ride_severities, int(inc.get("sensor_misses") or 0), votes)
    status = confidence.status_for(a.confidence, inc["status"])

    params = {
        "id": incident_id,
        "report_count": reports,
        "sensor_count": sensors,
        "sensor_rides": rides,
        "max_severity": max_severity,
        "max_urgency": max_urgency,
        "first_seen": agg.get("first_seen"),
        "last_seen": agg.get("last_seen"),
        "sensor_confirmed": sensors > 0,
        "found_before_report": found_before_report(rides, agg.get("nth_ride_ts"), agg.get("first_report_ts")),
        "department": department_for(inc["type"]),
        "address": pick_address(inc.get("segment_name"), agg.get("location_text"), inc.get("address")),
        "score": priority_score(sensor_severity=max_severity, report_count=reports, max_urgency=max_urgency,
                                vulnerability=float(inc.get("vulnerability") or 0.0), both_sources=both),
        "status": status,
        "confidence": round(a.confidence, 4),
        "sensor_confidence": None if a.sensor_confidence is None else round(a.sensor_confidence, 4),
        "citizen_confidence": None if a.citizen_confidence is None else round(a.citizen_confidence, 4),
        "yes_count": sum(1 for yes, _ in votes if yes),
        "no_count": sum(1 for yes, _ in votes if not yes),
    }
    row = fetch_one(conn, SQL_UPDATE, params)
    if status != inc["status"] and status in (IncidentStatus.VERIFIED, IncidentStatus.DISMISSED):
        trust.settle(conn, incident_id, real=status == IncidentStatus.VERIFIED)
    return dict(row) if row else {}
