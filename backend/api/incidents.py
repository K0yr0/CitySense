"""Incident queue, incident detail (merged reports, evidence, timeline, signal) and manual verification."""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from backend.api import serializers as ser
from backend.api.deps import DB, savepoint

log = logging.getLogger(__name__)
router = APIRouter(prefix="/incidents", tags=["incidents"])

MAX_SUMMARY_TEXTS = 20

INCIDENT_SELECT = """
select i.id, i.segment_id, i.type, i.status, i.score, i.department, i.address, i.summary,
       ST_X(i.geom) as lon, ST_Y(i.geom) as lat,
       i.report_count, i.sensor_count, i.sensor_rides, i.sensor_confirmed, i.found_before_report,
       i.max_severity, i.max_urgency, i.first_seen, i.last_seen,
       i.verify_vehicle, i.verify_eta_min, i.verify_requested_at, i.confirmed_at, i.verify_checks
from incidents i
"""

INCIDENT_REPORTS_SQL = """
select r.id, r.raw_text, r.structured->>'summary_en' as summary_en, r.urgency, r.created_at, r.photo_url
from incident_evidence ie
join evidence e on e.id = ie.evidence_id
join reports r on r.id = e.report_id
where ie.incident_id = %(id)s
order by r.created_at, r.id
"""

INCIDENT_EVIDENCE_SQL = """
select e.id, e.source, e.type, e.severity, e.ts, e.ride_id, e.report_id, e.details,
       rd.vehicle_line, rd.mode as ride_mode
from incident_evidence ie
join evidence e on e.id = ie.evidence_id
left join rides rd on rd.id = e.ride_id
where ie.incident_id = %(id)s
order by e.ts, e.id
"""

NO_ANOMALY_PASS_SQL = """
select max(rs.passed_at) as ts from ride_segments rs
where rs.segment_id = %(segment_id)s and rs.passed_at >= %(since)s
"""


def load_incident(conn, incident_id: int) -> dict | None:
    """Raw incident row (with lon/lat and verification fields) or None."""
    from backend import db

    return db.fetch_one(conn, INCIDENT_SELECT + "where i.id = %(id)s", {"id": incident_id})


def _lazy_summary(conn, incident: dict, reports: list[dict]) -> str | None:
    """LLM summary of the merged reports, cached in incidents.summary. Never raises."""
    texts = [r["raw_text"] for r in reports if r.get("raw_text")][:MAX_SUMMARY_TEXTS]
    if int(incident.get("report_count") or 0) < 2 or len(texts) < 2:
        return None
    try:
        from backend.triage import structure

        summary = (structure.summarize_reports(texts) or "").strip() or None
    except Exception as exc:  # LLM / fallback trouble must not break the detail view
        log.warning("summary for incident %s failed: %s", incident["id"], exc)
        return None
    if summary:
        try:
            from backend import db

            with savepoint(conn):
                db.fetch_one(conn, "update incidents set summary = %(s)s where id = %(id)s returning id",
                             {"s": summary, "id": incident["id"]})
        except Exception as exc:
            log.warning("caching summary for incident %s failed: %s", incident["id"], exc)
    return summary


@router.get("")
def list_incidents(
    conn: DB,
    department: str | None = None,
    status: str | None = Query(None, description="one status or a comma-separated list"),
    issue_type: str | None = Query(None, alias="type"),
    limit: int = Query(200, ge=1, le=5000),
) -> dict:
    """Incident queue sorted by score (desc)."""
    from backend import db

    where, params = [], {"limit": limit}
    if department:
        where.append("i.department = %(department)s")
        params["department"] = department
    if status:
        where.append("i.status = any(%(statuses)s)")
        params["statuses"] = [s.strip() for s in status.split(",") if s.strip()]
    if issue_type:
        where.append("i.type = %(type)s")
        params["type"] = issue_type
    sql = (INCIDENT_SELECT + ("where " + " and ".join(where) + "\n" if where else "")
           + "order by i.score desc, i.last_seen desc limit %(limit)s")
    return {"incidents": [ser.incident_summary(r) for r in db.fetch_all(conn, sql, params)]}


@router.get("/{incident_id}")
def get_incident(incident_id: int, conn: DB) -> dict:
    """IncidentSummary + summary, reports, evidence, timeline and the strongest sensor signal."""
    from backend import db

    incident = load_incident(conn, incident_id)
    if incident is None:
        raise HTTPException(404, f"incident {incident_id} not found")
    reports = db.fetch_all(conn, INCIDENT_REPORTS_SQL, {"id": incident_id})
    evidence = db.fetch_all(conn, INCIDENT_EVIDENCE_SQL, {"id": incident_id})

    no_anomaly_ts = None
    if incident.get("status") == "no_anomaly" and incident.get("segment_id") and incident.get("verify_requested_at"):
        row = db.fetch_one(conn, NO_ANOMALY_PASS_SQL,
                           {"segment_id": incident["segment_id"], "since": incident["verify_requested_at"]})
        no_anomaly_ts = (row or {}).get("ts")

    out = ser.incident_summary(incident)
    out.update(
        summary=incident.get("summary") or _lazy_summary(conn, incident, reports),
        reports=[ser.report_json(r) for r in reports],
        evidence=[ser.evidence_json(e) for e in evidence],
        timeline=ser.build_timeline(incident, reports, evidence, no_anomaly_ts=no_anomaly_ts),
        signal=ser.strongest_signal(evidence),
    )
    return out


@router.post("/{incident_id}/verify")
def verify_incident(incident_id: int, conn: DB) -> dict:
    """Ask the next tram/bus through the segment to verify (no-op for incidents that already have sensor evidence)."""
    from backend.fusion import verify

    if load_incident(conn, incident_id) is None:
        raise HTTPException(404, f"incident {incident_id} not found")
    result = verify.request_verification(conn, incident_id) or {}
    incident = load_incident(conn, incident_id) or {}
    eta = incident.get("verify_eta_min")
    eta = result.get("eta_min") if eta is None else eta
    return {
        "incident_id": incident_id,
        "status": incident.get("status"),
        "vehicle": incident.get("verify_vehicle") or result.get("vehicle"),
        "eta_min": None if eta is None else int(eta),
    }
