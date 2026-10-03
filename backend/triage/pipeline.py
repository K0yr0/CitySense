"""Citizen report -> structured, located, de-duplicated report row + evidence row.

structure -> (vision.anonymize + check_photo) -> geocode (fallback to pin) -> embed
-> find_duplicate -> db.insert_report -> nearest segment -> db.insert_evidence.
Never calls fusion: the API layer passes the returned evidence id to fusion.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from backend import db
from backend.config import settings
from backend.models import EvidenceIn, IssueType, Mode, Source, TriageResult
from backend.triage import dedup, geocode, structure, vision

log = logging.getLogger(__name__)

MIN_GEOCODE_CONFIDENCE = 0.5
PIN_CONFIDENCE = 0.9
SEGMENT_MAX_DIST_M = 60.0
PIN_AGREE_M = 1000.0  # a pin this close to a coarser geocode confirms it and is more precise


def _save_photo(jpeg: bytes) -> str:
    photos = settings.cache_dir / "photos"
    photos.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}.jpg"
    (photos / name).write_bytes(jpeg)
    return f"/photos/{name}"


def _handle_photo(photo_bytes: bytes, claimed: IssueType) -> tuple[str | None, dict]:
    """Anonymize, check and save a photo. Un-anonymizable photos are dropped, never stored."""
    try:
        clean = vision.anonymize(photo_bytes)
    except Exception as exc:
        log.warning("photo anonymization failed, photo dropped: %s", exc)
        return None, {"category": claimed.value, "severity": 0.5, "matches_claim": None,
                      "notes": "photo rejected: could not be anonymized"}
    try:
        check = vision.check_photo(clean, claimed)
    except Exception as exc:
        log.warning("photo check failed: %s", exc)
        check = {"category": claimed.value, "severity": 0.5, "matches_claim": None,
                 "notes": "vision unavailable"}
    if not vision.blur_available():  # metadata-stripped only: faces/plates may still be visible
        log.warning("face/plate blur unavailable, photo not stored")
        return None, check
    return _save_photo(clean), check


def _locate(location_text: str | None, pin: tuple[float, float] | None
            ) -> tuple[float | None, float | None, float | None]:
    """(lon, lat, confidence): confident geocode of the text, else the user's pin, else unlocated.
    A street-level geocode with a pin within PIN_AGREE_M yields the pin (the geocode is a street
    centroid, the pin the actual spot); a far-away pin loses (reported from elsewhere)."""
    hit = geocode.geocode(location_text) if location_text else None
    if hit is not None and hit[2] >= MIN_GEOCODE_CONFIDENCE:
        if pin is None or hit[2] >= PIN_CONFIDENCE or \
                dedup.haversine_m(hit[0], hit[1], pin[0], pin[1]) > PIN_AGREE_M:
            return hit
    if pin is not None:
        return float(pin[0]), float(pin[1]), PIN_CONFIDENCE
    return None, None, None


def process_report(conn, text: str, *, pin: tuple[float, float] | None = None,
                   photo_bytes: bytes | None = None, created_at: datetime | None = None,
                   source: str = "web", structured: TriageResult | None = None,
                   contributor_id: int | None = None) -> dict:
    """Run one complaint through triage and persist it. See ARCHITECTURE.md §5.5."""
    created_at = created_at or datetime.now(timezone.utc)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)

    triage = structured if structured is not None else structure.structure(text)
    if not isinstance(triage, TriageResult):
        triage = TriageResult.model_validate(triage)
    category = IssueType(triage.category)
    sdict = triage.model_dump(mode="json")

    photo_url = None
    if photo_bytes:
        photo_url, sdict["photo_check"] = _handle_photo(photo_bytes, category)

    lon, lat, confidence = _locate(triage.location_text, pin)
    located = lon is not None

    emb = dedup.embed([text])[0]
    duplicate_of = (dedup.find_duplicate(conn, category=category.value, lon=lon, lat=lat,
                                         created_at=created_at, embedding=emb)
                    if located else None)

    report_id = db.insert_report(
        conn, raw_text=text, structured=sdict, lon=lon, lat=lat, location_confidence=confidence,
        embedding=[float(x) for x in emb], duplicate_of=duplicate_of, photo_url=photo_url,
        source=source, created_at=created_at, contributor_id=contributor_id)

    evidence_id = None
    if located:
        mode = Mode.TRAM if category == IssueType.TRAM_TRACK else Mode.ROAD
        segment_id = db.nearest_segment(conn, lon, lat, mode=mode.value, max_dist_m=SEGMENT_MAX_DIST_M)
        evidence_id = db.insert_evidence(conn, EvidenceIn(
            source=Source.REPORT, type=category, lon=lon, lat=lat,
            severity=triage.urgency / 5, ts=created_at, segment_id=segment_id, report_id=report_id,
            details={"kind": "report", "urgency": triage.urgency, "summary_en": triage.summary_en,
                     "hazard_to_people": triage.hazard_to_people,
                     "location_confidence": confidence, "location_text": triage.location_text}))

    return {"report_id": report_id, "evidence_id": evidence_id, "structured": sdict,
            "duplicate_of": duplicate_of, "lon": lon, "lat": lat, "photo_url": photo_url}
