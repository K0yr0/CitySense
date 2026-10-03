"""Citizen reports: submit (with photo), status lookup and bulk import (19115 / synthetic).

Orchestration (ARCHITECTURE.md §5.7):
process_report -> fusion.ingest_evidence -> request_verification when the incident is report-only and open.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from backend.api import incidents as incidents_api
from backend.api import serializers as ser
from backend.api.deps import DB, savepoint

log = logging.getLogger(__name__)
router = APIRouter(prefix="/reports", tags=["reports"])

MAX_PHOTO_BYTES = 15 * 1024 * 1024

REPORT_STATUS_SQL = """
select r.id, r.category, r.department, ie.incident_id
from reports r
left join evidence e on e.report_id = r.id
left join incident_evidence ie on ie.evidence_id = e.id
where r.id = %(id)s
order by ie.incident_id nulls last
limit 1
"""


class BulkReport(BaseModel):
    text: str = Field(min_length=1)
    created_at: datetime | None = None
    lon: float | None = None
    lat: float | None = None
    source: Literal["web", "19115", "synthetic"] = "19115"


class BulkRequest(BaseModel):
    reports: list[dict[str, Any]]  # validated one by one so a bad record can't sink the batch


def _pin(lon: float | None, lat: float | None) -> tuple[float, float] | None:
    if lon is None or lat is None:
        return None
    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        raise ValueError(f"invalid coordinates lon={lon} lat={lat}")
    return (lon, lat)


def _ingest(conn, evidence_id: int | None) -> list[int]:
    from backend.fusion import incidents as fusion_incidents

    return [int(i) for i in fusion_incidents.ingest_evidence(conn, [evidence_id])] if evidence_id else []


def _maybe_request_verification(conn, incident: dict | None) -> dict | None:
    """Report-only, open incident -> ask the next vehicle to verify. Failures only log."""
    if not incident or int(incident.get("sensor_count") or 0) > 0 or incident.get("status") != "open":
        return incident
    try:
        from backend.fusion import verify

        with savepoint(conn):
            verify.request_verification(conn, int(incident["id"]))
        return incidents_api.load_incident(conn, int(incident["id"])) or incident
    except Exception as exc:  # ZTM down etc. must not lose the citizen's report
        log.warning("verification request for incident %s failed: %s", incident.get("id"), exc)
        return incident


@router.post("")
def create_report(
    conn: DB,
    text: str = Form(...),
    lon: float | None = Form(None),
    lat: float | None = Form(None),
    photo: UploadFile | None = File(None),
) -> dict:
    """Submit one complaint (multipart). Returns ReportStatus."""
    from backend.triage import pipeline as triage_pipeline

    text = text.strip()
    if not text:
        raise HTTPException(422, "text must not be empty")
    try:
        pin = _pin(lon, lat)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    photo_bytes = photo.file.read(MAX_PHOTO_BYTES + 1) if photo is not None else None
    if photo_bytes and len(photo_bytes) > MAX_PHOTO_BYTES:
        raise HTTPException(413, "photo too large (max 15 MB)")

    result = triage_pipeline.process_report(conn, text, pin=pin, photo_bytes=photo_bytes or None, source="web")
    incident_ids = _ingest(conn, result.get("evidence_id"))
    incident = incidents_api.load_incident(conn, incident_ids[0]) if incident_ids else None
    incident = _maybe_request_verification(conn, incident)

    structured = result.get("structured") or {}
    report = {"id": result["report_id"], "category": structured.get("category"),
              "department": structured.get("department")}
    return ser.report_status(report, incident)


@router.get("/{report_id}/status")
def report_status(report_id: int, conn: DB) -> dict:
    """Current ReportStatus of a submitted report (polled by the citizen form)."""
    from backend import db

    row = db.fetch_one(conn, REPORT_STATUS_SQL, {"id": report_id})
    if row is None:
        raise HTTPException(404, f"report {report_id} not found")
    incident = incidents_api.load_incident(conn, int(row["incident_id"])) if row.get("incident_id") else None
    return ser.report_status(row, incident)


@router.post("/bulk")
def bulk_reports(body: BulkRequest, conn: DB) -> dict:
    """Fast import: no verification requests; each record runs in its own savepoint."""
    from backend.triage import pipeline as triage_pipeline

    report_ids: list[int] = []
    incident_ids: dict[int, None] = {}  # ordered set
    for n, raw in enumerate(body.reports):
        try:
            rec = BulkReport.model_validate(raw)
            created_at = rec.created_at
            if created_at is not None and created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            with savepoint(conn):
                result = triage_pipeline.process_report(conn, rec.text.strip(), pin=_pin(rec.lon, rec.lat),
                                                        created_at=created_at, source=rec.source)
                touched = _ingest(conn, result.get("evidence_id"))
        except Exception as exc:
            log.warning("bulk report #%d skipped: %s", n, exc)
            continue
        report_ids.append(int(result["report_id"]))
        incident_ids.update(dict.fromkeys(touched))
    return {"processed": len(report_ids), "report_ids": report_ids, "incident_ids": list(incident_ids)}
