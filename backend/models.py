"""Shared vocabulary and data shapes used across sensor, triage, fusion and API.

Keep these the single source of truth: enum values are stored verbatim in the
database (`evidence.type`, `incidents.status`, `incidents.department`, ...).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class IssueType(StrEnum):
    ROAD_DAMAGE = "road_damage"
    TRAM_TRACK = "tram_track"
    STREETLIGHT = "streetlight"
    FLOODING = "flooding"
    WASTE = "waste"
    OTHER = "other"


class Source(StrEnum):
    SENSOR = "sensor"
    REPORT = "report"


class Mode(StrEnum):
    ROAD = "road"
    TRAM = "tram"


class Department(StrEnum):
    ZDM = "ZDM"
    TRAMWAJE = "Tramwaje Warszawskie"
    MPWIK = "MPWiK"
    STRAZ_MIEJSKA = "Straż Miejska"
    OTHER = "inne"


class IncidentStatus(StrEnum):
    """Confidence-driven lifecycle (backend.fusion.confidence): candidate -> likely -> verified.

    `dismissed` is the negative counterpart of `verified` (enough evidence that nothing is
    there); both are terminal and settle contributor trust. `closed` = handled by the city.
    """

    CANDIDATE = "candidate"
    LIKELY = "likely"
    VERIFIED = "verified"
    DISMISSED = "dismissed"
    CLOSED = "closed"


class WorkStatus(StrEnum):
    """City work on an incident (`incidents.work_status`, written only by the web admin, owner B).

    Independent of `IncidentStatus`: confidence says *is it real*, work status says *is it fixed*.
    """

    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"


class Role(StrEnum):
    """`users.role`: admin when the Google email is in ADMIN_EMAILS (set at every login)."""

    CITIZEN = "citizen"
    ADMIN = "admin"


@dataclass
class EvidenceIn:
    """One piece of evidence ready to be written to the `evidence` table."""

    source: Source
    type: IssueType
    lon: float
    lat: float
    severity: float  # 0–1
    ts: datetime  # timezone-aware
    segment_id: int | None = None
    ride_id: int | None = None
    report_id: int | None = None
    details: dict[str, Any] = field(default_factory=dict)


class TriageResult(BaseModel):
    """Structured form of a citizen complaint, produced by backend.triage.structure."""

    category: IssueType = IssueType.OTHER
    location_text: str | None = None
    urgency: int = Field(default=2, ge=1, le=5)  # 5 = risk to life, 1 = cosmetic
    hazard_to_people: bool = False
    department: Department = Department.OTHER
    summary_en: str = ""
    summary_tr: str = ""
    needs_clarification: bool = False
