"""Citizen YES/NO answers: POST /incidents/{id}/responses (owner A; moved out of incidents.py on Day 0).

Same rules as the mobile app's POST /mobile/incidents/{id}/answer, through the same function
(backend.api.mobile.record_answer): sign-in required, the phone's position with GPS accuracy
<= 25 m, within 100 m of the problem, once per user, weighted by trust. The anonymous
"contributor token" version was removed (docs/SECURITY.md A1): with it anyone could vote from
anywhere, and every new random token counted as a new person.

Incident rows are read with backend.api.incidents.load_incident (owner B); only B's fusion code
writes `incidents`.
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.api import mobile
from backend.api import serializers as ser
from backend.api.deps import DB
from backend.api.incidents import load_incident
from backend.auth import CurrentUser

router = APIRouter(tags=["responses"])


class CitizenResponseIn(BaseModel):
    answer: Literal["yes", "no"]
    lon: float = Field(ge=-180, le=180)
    lat: float = Field(ge=-90, le=90)
    accuracy_m: float = Field(ge=0, description="phone GPS accuracy in metres; must be <= 25")


@router.post("/incidents/{incident_id}/responses")
def respond(incident_id: int, body: CitizenResponseIn, conn: DB, user: CurrentUser) -> dict:
    """Citizen answers "Is this problem still there?" YES/NO (sign-in, within 100 m, GPS <= 25 m)."""
    result = mobile.record_answer(conn, user, incident_id, body.answer, body.lon, body.lat, body.accuracy_m)
    out = ser.incident_summary(load_incident(conn, incident_id) or {"id": incident_id})
    return {
        "incident_id": incident_id,
        "status": result["status"],
        "confidence": result["confidence"],
        "sensor_confidence": out.get("sensor_confidence"),
        "citizen_confidence": out.get("citizen_confidence"),
        "yes_count": out.get("yes_count"),
        "no_count": out.get("no_count"),
        "contributor_trust": result["contributor_trust"],
    }
