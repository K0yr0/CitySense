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
)


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

def incident_summary(row: dict) -> dict:
    """IncidentSummary (§6). `has_sensor` / `has_report` are derived from the counts."""
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
    return {
        "id": int(row["id"]),
        "source": row.get("source"),
        "type": row.get("type"),
        "severity": num(row.get("severity")) or 0.0,
        "ts": iso(row.get("ts")),
        "ride_id": _int(row.get("ride_id"), None),
        "report_id": _int(row.get("report_id"), None),
        "details": _json(row.get("details")),
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
                   *, no_anomaly_ts: Any = None) -> list[dict]:
    """Chronological [{"ts", "kind", "label"}] from reports, sensor evidence and verification fields.

    `evidence` rows may carry `vehicle_line` / `ride_mode` (joined from rides) for nicer labels.
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
    if incident.get("confirmed_at"):
        add(incident["confirmed_at"], "confirmed", f"Verified by {vehicle} sensors" if vehicle else "Confirmed by vehicle sensors")
    if incident.get("status") == "no_anomaly":
        add(no_anomaly_ts or incident.get("verify_requested_at") or incident.get("last_seen"), "no_anomaly",
            f"{capitalize(vehicle) if vehicle else 'A vehicle'} passed without detecting an anomaly")

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
        elif status == "confirmed" and vehicle:
            parts.append(f"Verified by {vehicle} sensors.")
        elif status == "confirmed" or incident.get("sensor_confirmed"):
            parts.append("Confirmed by vehicle sensors.")
        elif status == "awaiting_verification" and vehicle:
            parts.append(f"{capitalize(vehicle)} will verify " + (f"in ~{eta} min." if eta is not None else "soon."))
        elif status == "no_anomaly":
            parts.append("A passing vehicle found no anomaly; an inspector will take a look.")
        elif status == "closed":
            parts.append("This issue has been resolved.")
    if department:
        parts.append(f"Sent to {department}.")
    return " ".join(parts)


def report_status(report: dict, incident: dict | None) -> dict:
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
