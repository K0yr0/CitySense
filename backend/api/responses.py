"""Citizen YES/NO answers: POST /incidents/{id}/responses (owner A; moved out of incidents.py on Day 0).

The URL and JSON shapes are unchanged (docs/ARCHITECTURE.md §6). Incident rows are read with
backend.api.incidents.load_incident (owner B); only B's fusion code writes `incidents`.
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.api import serializers as ser
from backend.api.deps import DB
from backend.api.incidents import load_incident

router = APIRouter(tags=["responses"])


class CitizenResponseIn(BaseModel):
    answer: Literal["yes", "no"]
    contributor: str = Field(min_length=8, max_length=200, description="random token the browser keeps")


@router.post("/incidents/{incident_id}/responses")
def respond(incident_id: int, body: CitizenResponseIn, conn: DB) -> dict:
    """Citizen answers "Is this problem still there?" YES/NO.

    The answer is weighted by the contributor's trust, the incident is re-assessed by the
    confidence engine, and the answer is scored (trust update) once the incident resolves.
    """
    from backend.fusion import incidents as fusion_incidents, trust

    incident = load_incident(conn, incident_id)
    if incident is None:
        raise HTTPException(404, f"incident {incident_id} not found")
    if incident.get("status") in ("closed", "dismissed"):
        raise HTTPException(409, f"incident {incident_id} is {incident['status']}")
    try:
        contributor = trust.contributor_for(conn, body.contributor)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    trust.record_vote(conn, incident_id, int(contributor["id"]), body.answer == "yes",
                      resolved=incident.get("status") == "verified")
    fusion_incidents.refresh_incident(conn, incident_id)
    out = ser.incident_summary(load_incident(conn, incident_id) or incident)
    return {
        "incident_id": incident_id,
        "status": out["status"],
        "confidence": out["confidence"],
        "sensor_confidence": out["sensor_confidence"],
        "citizen_confidence": out["citizen_confidence"],
        "yes_count": out["yes_count"],
        "no_count": out["no_count"],
        "contributor_trust": ser.num(contributor.get("trust")),
    }
