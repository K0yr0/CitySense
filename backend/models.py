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
    OPEN = "open"
    AWAITING_VERIFICATION = "awaiting_verification"
    CONFIRMED = "confirmed"
    NO_ANOMALY = "no_anomaly"
    CLOSED = "closed"


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
