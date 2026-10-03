"""Row -> JSON helpers shared by the routers.

Output shapes follow docs/ARCHITECTURE.md §6 exactly. The frontend depends on the
key names, so add new keys here only together with the contract.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any

SUMMARY_KEYS = (
    "id", "type", "status", "score", "department", "lon", "lat", "address",
    "report_count", "sensor_count", "sensor_rides", "sensor_confirmed", "found_before_report",
    "has_sensor", "has_report", "max_severity", "max_urgency",
    "first_seen", "last_seen", "verify_vehicle", "verify_eta_min",
    "confidence", "sensor_confidence", "citizen_confidence", "yes_count", "no_count",
    "sensor_misses", "awaiting_verification", "work_status", "work_status_changed_at",
)

OPEN_STATUSES = ("candidate", "likely")


def pct(confidence: Any) -> int:
    """0–1 -> whole percent; confidence is never certain, so below 1 shows at most 99."""
    x = min(1.0, max(0.0, float(confidence or 0)))
    return round(100 * x) if x >= 1 else min(99, round(100 * x))


# --- scalars -----------------------------------------------------------------

def to_dt(value: Any) -> datetime | None:
    """datetime / ISO string -> tz-aware UTC datetime (naive values are taken as UTC)."""
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return None


def iso(value: Any) -> str | None:
    """ISO-8601 string for a timestamp (UTC assumed when naive); strings pass through."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return to_dt(value).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def num(value: Any, digits: int = 4) -> float | None:
    return None if value is None else round(float(value), digits)


def _int(value: Any, default: int | None = 0) -> int | None:
    return default if value is None else int(value)


def _json(value: Any) -> Any:
    if isinstance(value, (str, bytes)):
        try:
            return json.loads(value)
        except ValueError:
            return {}
    return value if value is not None else {}


def capitalize(text: str) -> str:
    return text[:1].upper() + text[1:]


def vehicle_label(row: dict) -> str:
    """'tram 17' / 'bus 175' from a row carrying vehicle_line + ride_mode (evidence joined with rides)."""
    kind = "tram" if row.get("ride_mode") == "tram" else "bus" if row.get("ride_mode") == "road" else "vehicle"
    line = row.get("vehicle_line")
    return f"{kind} {line}" if line else f"a {kind}"


# --- incidents ---------------------------------------------------------------

def awaiting_verification(row: dict) -> bool:
    """A vehicle was asked to check this report-only incident and has not passed it yet."""
    requested, missed = to_dt(row.get("verify_requested_at")), to_dt(row.get("last_miss_at"))
    return (requested is not None and row.get("status") in OPEN_STATUSES
            and not _int(row.get("sensor_count")) and (missed is None or missed < requested))


def incident_summary(row: dict) -> dict:
    """IncidentSummary (§6). `has_sensor` / `has_report` / `awaiting_verification` are derived."""
    report_count = _int(row.get("report_count"))
    sensor_count = _int(row.get("sensor_count"))
    return {
        "id": int(row["id"]),
        "type": row.get("type"),
        "status": row.get("status"),
        "score": num(row.get("score")) or 0.0,
        "department": row.get("department"),
        "lon": num(row.get("lon"), 7),
        "lat": num(row.get("lat"), 7),
        "address": row.get("address"),
        "report_count": report_count,
        "sensor_count": sensor_count,
        "sensor_rides": _int(row.get("sensor_rides")),
        "sensor_confirmed": bool(row.get("sensor_confirmed")),
        "found_before_report": bool(row.get("found_before_report")),
        "has_sensor": sensor_count > 0,
        "has_report": report_count > 0,
        "max_severity": num(row.get("max_severity")) or 0.0,
        "max_urgency": _int(row.get("max_urgency")),
        "first_seen": iso(row.get("first_seen")),
        "last_seen": iso(row.get("last_seen")),
        "verify_vehicle": row.get("verify_vehicle"),
        "verify_eta_min": _int(row.get("verify_eta_min"), None),
        "confidence": num(row.get("confidence")) or 0.0,
        "sensor_confidence": num(row.get("sensor_confidence")),
        "citizen_confidence": num(row.get("citizen_confidence")),
        "yes_count": _int(row.get("yes_count")),
        "no_count": _int(row.get("no_count")),
        "sensor_misses": _int(row.get("sensor_misses")),
        "awaiting_verification": awaiting_verification(row),
        # City work (migration 200), independent of the confidence `status`.
        "work_status": row.get("work_status") or "todo",
        "work_status_changed_at": iso(row.get("work_status_changed_at")),
    }


def report_json(row: dict) -> dict:
    return {
        "id": int(row["id"]),
        "raw_text": row.get("raw_text"),
        "summary_en": row.get("summary_en"),
        "urgency": _int(row.get("urgency"), None),
        "created_at": iso(row.get("created_at")),
        "photo_url": row.get("photo_url"),
    }


def evidence_json(row: dict) -> dict:
    ride_id = _int(row.get("ride_id"), None)
    return {
        "id": int(row["id"]),
        "source": row.get("source"),
        "type": row.get("type"),
        "severity": num(row.get("severity")) or 0.0,
        "ts": iso(row.get("ts")),
        "ride_id": ride_id,
        "report_id": _int(row.get("report_id"), None),
        "details": _json(row.get("details")),
        # "tram 17" / "bus 175" when the evidence comes from a ride (joined from rides), else None.
        "vehicle": vehicle_label(row) if ride_id is not None else None,
    }


def response_json(row: dict) -> dict:
    """One explicit citizen YES/NO answer for the admin view: never who answered, only their trust."""
    return {
        "answer": "yes" if row.get("answer") else "no",
        "trust": num(row.get("trust"), 3),
        "created_at": iso(row.get("created_at")),
        "settled": bool(row.get("settled")),  # already scored against the final outcome
    }


def strongest_signal(evidence: list[dict]) -> dict | None:
    """`signal` of the most severe sensor bump: {"fs", "values", "peak_index"} or None."""
    bumps = [
        (e, d) for e in evidence
        if e.get("source") == "sensor"
        and (d := _json(e.get("details"))).get("kind") == "bump" and d.get("signal")
    ]
    if not bumps:
        return None
    _, details = max(bumps, key=lambda pair: float(pair[0].get("severity") or 0))
    return {
        "fs": int(details.get("signal_fs") or 100),
        "values": [float(v) for v in details["signal"]],
        "peak_index": int(details.get("peak_index") or 0),
    }


def build_timeline(incident: dict, reports: list[dict], evidence: list[dict],
                   responses: list[dict] | None = None) -> list[dict]:
    """Chronological [{"ts", "kind", "label"}] from reports, sensor evidence, citizen answers
    and the confidence lifecycle.

    `evidence` rows may carry `vehicle_line` / `ride_mode` (joined from rides) for nicer labels;
    `responses` are explicit YES/NO answers ({"answer", "trust", "created_at"}), not reports.
    """
    events: list[tuple[datetime, str, str]] = []

    def add(ts: Any, kind: str, label: str) -> None:
        if (dt := to_dt(ts)) is not None:
            events.append((dt, kind, label))

    for n, r in enumerate(sorted(reports, key=lambda r: to_dt(r.get("created_at")) or datetime.max.replace(tzinfo=timezone.utc)), 1):
        summary = (r.get("summary_en") or "").strip()
        label = "First citizen report" if n == 1 else f"Citizen report #{n}"
        add(r.get("created_at"), "first_report" if n == 1 else "report", f"{label}: {summary}" if summary else label)

    rides_seen: list[Any] = []
    for e in sorted((e for e in evidence if e.get("source") == "sensor"), key=lambda e: to_dt(e.get("ts")) or datetime.min.replace(tzinfo=timezone.utc)):
        what = "a dark streetlight gap" if _json(e.get("details")).get("kind") == "dark_gap" else "a bump"
        sev = float(e.get("severity") or 0)
        add(e.get("ts"), "sensor", f"{capitalize(vehicle_label(e))} sensors detected {what} (severity {sev:.2f})")
        if e.get("ride_id") not in rides_seen:
            rides_seen.append(e.get("ride_id"))
            if incident.get("found_before_report") and len(rides_seen) == 2:
                add(e.get("ts"), "proactive", "Found by sensors before any report (2 independent rides)")

    vehicle = incident.get("verify_vehicle")
    if incident.get("verify_requested_at"):
        eta = incident.get("verify_eta_min")
        who = capitalize(vehicle) if vehicle else "Next vehicle"
        add(incident["verify_requested_at"], "verification_requested",
            f"Verification requested: {who} will pass" + (f" in ~{eta} min" if eta is not None else ""))
    for r in responses or []:
        answer = "YES, still there" if r.get("answer") else "NO, not there"
        add(r.get("created_at"), "response", f"Citizen answered {answer} (trust {float(r.get('trust') or 0):.2f})")
    misses = _int(incident.get("sensor_misses"))
    if misses and incident.get("last_miss_at"):
        add(incident["last_miss_at"], "sensor_miss",
            "A passing vehicle found no anomaly" + (f" ({misses} clean passes so far)" if misses > 1 else ""))
    pct_label = f"confidence {pct(incident.get('confidence'))}%"
    if incident.get("verified_at"):
        add(incident["verified_at"], "verified", f"Verified ({pct_label}); contributor trust updated")
    if incident.get("status") == "dismissed":
        add(incident.get("last_miss_at") or incident.get("last_seen"), "dismissed",
            f"Dismissed: no problem found ({pct_label}); contributor trust updated")

    events.sort(key=lambda ev: ev[0])  # stable: same-ts events keep insertion order
    return [{"ts": iso(ts), "kind": kind, "label": label} for ts, kind, label in events]


# --- reports -----------------------------------------------------------------

def status_message(*, incident: dict | None, others: int, department: str | None) -> str:
    """Human status line, e.g. "23 others reported this. Tram 17 will verify in ~6 min. Sent to ZDM."."""
    parts: list[str] = []
    if incident is None:
        parts.append("Thanks, your report was received. We could not place it on the map yet; adding a location pin helps.")
    else:
        parts.append(f"{others} others reported this." if others > 1
                     else "1 other person reported this." if others == 1
                     else "You're the first to report this.")
        status, vehicle, eta = incident.get("status"), incident.get("verify_vehicle"), incident.get("verify_eta_min")
        if incident.get("found_before_report"):
            parts.append("Found by sensors before any report.")
        if status == "verified":
            parts.append(f"Verified by {vehicle} sensors." if vehicle and incident.get("sensor_confirmed")
                         else "Verified.")
        elif status == "closed":
            parts.append("This issue has been resolved.")
        elif status == "dismissed":
            parts.append("Checks found no problem here, so it was dismissed.")
        elif awaiting_verification(incident) and vehicle:
            parts.append(f"{capitalize(vehicle)} will verify " + (f"in ~{eta} min." if eta is not None else "soon."))
        elif _int(incident.get("sensor_misses")):
            parts.append("A passing vehicle found no anomaly yet; more checks will follow.")
        if status in OPEN_STATUSES:
            parts.append(f"Status: {status} ({pct(incident.get('confidence'))}% confidence).")
    if department:
        parts.append(f"Sent to {department}.")
    return " ".join(parts)


def report_status(report: dict, incident: dict | None, contributor_trust: float | None = None) -> dict:
    """ReportStatus (§6). `report` needs id, category, department; `incident` is a raw incident row or None."""
    others = max(_int(incident.get("report_count")) - 1, 0) if incident else 0
    department = (incident or {}).get("department") or report.get("department")
    return {
        "report_id": int(report["id"]),
        "incident_id": int(incident["id"]) if incident else None,
        "status": incident.get("status") if incident else None,
        "category": report.get("category"),
        "department": department,
        "others_count": others,
        "sensor_confirmed": bool(incident and incident.get("sensor_confirmed")),
        "verify_vehicle": incident.get("verify_vehicle") if incident else None,
        "verify_eta_min": _int(incident.get("verify_eta_min"), None) if incident else None,
        "confidence": num(incident.get("confidence")) if incident else None,
        "contributor_trust": num(contributor_trust),
        "message": status_message(incident=incident, others=others, department=department),
    }


# --- segments / vehicles -----------------------------------------------------

def segment_json(row: dict) -> dict:
    """Segment row with `geojson` (ST_AsGeoJSON) or `path` -> {"id", "mode", "health", "rides", "path"}."""
    path = row.get("path")
    if path is None:
        geo = _json(row.get("geojson"))
        path = geo.get("coordinates", []) if isinstance(geo, dict) else []
    return {
        "id": int(row["id"]),
        "mode": row.get("mode"),
        "health": num(row.get("health"), 3),
        "rides": _int(row.get("rides")),
        "path": [[float(x), float(y)] for x, y, *_ in path],
    }


def vehicle_json(v: dict) -> dict:
    return {
        "id": str(v.get("id")),
        "line": None if v.get("line") is None else str(v.get("line")),
        "lon": num(v.get("lon"), 6),
        "lat": num(v.get("lat"), 6),
        "ts": iso(v.get("ts")),
        "kind": v.get("kind"),
    }
