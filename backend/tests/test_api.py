"""HTTP API tests: TestClient + fake DB connection + monkeypatched pipelines/fusion.

No PostGIS needed: `backend.db`, the sensor/triage pipelines and fusion are replaced by
fake modules (installed in sys.modules), so these tests only check orchestration and the
JSON contract of docs/ARCHITECTURE.md §6.
"""
from __future__ import annotations

import importlib
import sys
import types
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.api import deps, serializers as ser
from backend.api import rides as rides_api
from backend.fusion import trust as trust_mod
from backend.main import PHOTOS_DIR, app

T0 = datetime(2026, 10, 1, 8, 0, tzinfo=timezone.utc)

SUMMARY_KEYS = {
    "id", "type", "status", "score", "department", "lon", "lat", "address",
    "report_count", "sensor_count", "sensor_rides", "sensor_confirmed", "found_before_report",
    "has_sensor", "has_report", "max_severity", "max_urgency",
    "first_seen", "last_seen", "verify_vehicle", "verify_eta_min",
    "confidence", "sensor_confidence", "citizen_confidence", "yes_count", "no_count",
    "sensor_misses", "awaiting_verification",
}
DETAIL_KEYS = SUMMARY_KEYS | {"summary", "reports", "evidence", "timeline", "signal"}
REPORT_STATUS_KEYS = {"report_id", "incident_id", "status", "category", "department", "others_count",
                      "sensor_confirmed", "verify_vehicle", "verify_eta_min", "confidence",
                      "contributor_trust", "message"}
RIDE_KEYS = {"ride_id", "bumps", "dark_gaps", "segments_covered", "evidence_ids", "incident_ids",
             "verified_incident_ids"}
STATS_KEYS = {"reports_total", "incidents_total", "found_before_report", "candidate_total", "likely_total",
              "verified_total", "awaiting_verification", "contributors_total", "avg_verification_min",
              "rides_total", "segments_measured"}
TIMELINE_KINDS = {"first_report", "report", "sensor", "proactive", "verification_requested", "sensor_miss",
                  "response", "verified", "dismissed"}
RESPONSE_KEYS = {"incident_id", "status", "confidence", "sensor_confidence", "citizen_confidence",
                 "yes_count", "no_count", "contributor_trust"}


# --------------------------------------------------------------------------- fakes

class FakeConn:
    """Stand-in psycopg connection; counts savepoints (conn.transaction())."""

    def __init__(self) -> None:
        self.savepoints = 0

    @contextmanager
    def transaction(self):
        self.savepoints += 1
        yield


class FakeDB:
    """Replaces backend.db.fetch_one/fetch_all: answers by SQL substring (newest rule wins)."""

    def __init__(self) -> None:
        self.rules: list[tuple[str, object]] = []
        self.calls: list[tuple[str, object]] = []

    def on(self, needle: str, result) -> None:
        self.rules.insert(0, (needle, result))

    def _answer(self, sql, params):
        self.calls.append((sql, params))
        for needle, result in self.rules:
            if needle in sql:
                return result(params) if callable(result) else result
        return None

    def fetch_one(self, conn, sql, params=None):
        return self._answer(sql, params)

    def fetch_all(self, conn, sql, params=None):
        return self._answer(sql, params) or []

    def sql_with(self, needle: str) -> list[tuple[str, object]]:
        return [(s, p) for s, p in self.calls if needle in s]


def install(monkeypatch, name: str, **attrs) -> types.ModuleType:
    """Put a fake module at `name` (sys.modules + attribute on the parent package)."""
    mod = types.ModuleType(name)
    mod.__dict__.update(attrs)
    monkeypatch.setitem(sys.modules, name, mod)
    parent, _, child = name.rpartition(".")
    monkeypatch.setattr(importlib.import_module(parent), child, mod, raising=False)
    return mod


def incident_row(**kw) -> dict:
    row = dict(id=7, segment_id=101, type="tram_track", status="likely", score=0.91,
               department="Tramwaje Warszawskie", address="Marszałkowska", summary=None,
               lon=21.0122, lat=52.2297, report_count=24, sensor_count=0, sensor_rides=0,
               sensor_confirmed=False, found_before_report=False, max_severity=0.0, max_urgency=4,
               first_seen=T0, last_seen=T0 + timedelta(hours=5), verify_vehicle=None, verify_eta_min=None,
               verify_requested_at=None, verified_at=None, confidence=0.7, sensor_confidence=None,
               citizen_confidence=0.7, yes_count=24, no_count=0, sensor_misses=0, last_miss_at=None)
    row.update(kw)
    return row


class FakeDF(list):
    """Enough of a DataFrame for the API layer (len + to_csv)."""

    def to_csv(self, path, index=False):
        open(path, "w").write("t,ax\n")


@pytest.fixture
def env(monkeypatch, tmp_path):
    conn, fdb = FakeConn(), FakeDB()
    install(monkeypatch, "backend.db", fetch_one=fdb.fetch_one, fetch_all=fdb.fetch_all)
    monkeypatch.setattr(trust_mod, "fetch_one", fdb.fetch_one)   # real trust module, fake DB
    monkeypatch.setattr(trust_mod, "fetch_all", fdb.fetch_all)
    db_opened = []

    def fake_get_db():
        db_opened.append(1)
        yield conn

    app.dependency_overrides[deps.get_db] = fake_get_db
    monkeypatch.setattr(rides_api, "RIDES_DIR", tmp_path / "rides")
    rides_api._streams.clear()
    yield SimpleNamespace(conn=conn, db=fdb, client=TestClient(app), mp=monkeypatch,
                          db_opened=db_opened, tmp=tmp_path)
    app.dependency_overrides.clear()
    rides_api._streams.clear()


def fake_fusion(env, *, ingest=lambda conn, ids: [], verify_request=None, check=lambda conn, rid: []):
    calls: list[tuple] = []

    def ingest_evidence(conn, ids):
        calls.append(("ingest_evidence", list(ids)))
        return ingest(conn, ids)

    def request_verification(conn, incident_id):
        calls.append(("request_verification", incident_id))
        return verify_request(conn, incident_id) if verify_request else None

    def check_ride_verifications(conn, ride_id):
        calls.append(("check_ride_verifications", ride_id))
        return check(conn, ride_id)

    def refresh_incident(conn, incident_id):
        calls.append(("refresh_incident", incident_id))
        return {}

    install(env.mp, "backend.fusion.incidents", ingest_evidence=ingest_evidence, refresh_incident=refresh_incident)
    install(env.mp, "backend.fusion.verify", request_verification=request_verification,
            check_ride_verifications=check_ride_verifications, live_vehicles=lambda kind="tram": [])
    return calls


# --------------------------------------------------------------------------- meta

def test_health(env):
    r = env.client.get("/health")
    assert r.status_code == 200 and r.json() == {"ok": True}


def test_photos_are_served(env):
    name = f"test_{uuid4().hex}.jpg"
    (PHOTOS_DIR / name).write_bytes(b"\xff\xd8jpeg")
    try:
        r = env.client.get(f"/photos/{name}")
        assert r.status_code == 200 and r.content == b"\xff\xd8jpeg"
    finally:
        (PHOTOS_DIR / name).unlink()


def test_cors_and_json_errors(env):
    pre = env.client.options("/reports", headers={"Origin": "http://localhost:3000",
                                                  "Access-Control-Request-Method": "POST"})
    assert pre.status_code == 200
    assert pre.headers["access-control-allow-origin"] == "http://localhost:3000"

    def boom(params):
        raise RuntimeError("db down")

    env.db.on("as reports_total", boom)
    r = env.client.get("/stats", headers={"Origin": "http://localhost:3000"})
    assert r.status_code == 500
    assert "db down" in r.json()["detail"]
    assert r.headers["access-control-allow-origin"] == "http://localhost:3000"


# --------------------------------------------------------------------------- segments

def test_segments_shape_and_filters(env):
    env.db.on("from segments s", [
        {"id": 1, "mode": "tram", "health": 0.8234, "rides": 3,
         "geojson": '{"type":"LineString","coordinates":[[21.01,52.23],[21.0103,52.2302]]}'},
        {"id": 2, "mode": "tram", "health": None, "rides": 0,
         "geojson": '{"type":"LineString","coordinates":[[21.02,52.24],[21.0203,52.2402]]}'},
    ])
    r = env.client.get("/segments", params={"bbox": "20.9,52.1,21.2,52.4", "mode": "tram", "measured_only": "true"})
    assert r.status_code == 200
    segs = r.json()["segments"]
    assert set(r.json()) == {"segments"}
    assert all(set(s) == {"id", "mode", "health", "rides", "path"} for s in segs)
    assert segs[0] == {"id": 1, "mode": "tram", "health": 0.823, "rides": 3,
                       "path": [[21.01, 52.23], [21.0103, 52.2302]]}
    assert segs[1]["health"] is None
    sql, params = env.db.sql_with("from segments s")[-1]
    assert "ST_MakeEnvelope" in sql and "s.mode = %(mode)s" in sql and "s.health is not null" in sql
    assert params == {"limit": 20000, "min_lon": 20.9, "min_lat": 52.1, "max_lon": 21.2, "max_lat": 52.4,
                      "mode": "tram"}


def test_segments_without_filters_and_bad_input(env):
    env.db.on("from segments s", [])
    r = env.client.get("/segments")
    assert r.status_code == 200 and r.json() == {"segments": []}
    sql, _ = env.db.sql_with("from segments s")[-1]
    assert "where" not in sql
    assert env.client.get("/segments", params={"bbox": "1,2,3"}).status_code == 400
    assert env.client.get("/segments", params={"bbox": "21.2,52.1,20.9,52.4"}).status_code == 400
    assert env.client.get("/segments", params={"mode": "metro"}).status_code == 422


# --------------------------------------------------------------------------- incidents

def test_incident_list(env):
    env.db.on("from incidents i", [incident_row(), incident_row(id=8, report_count=0, sensor_count=3,
                                                                sensor_rides=2, found_before_report=True)])
    r = env.client.get("/incidents", params={"department": "ZDM", "status": "candidate,likely", "limit": 50})
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"incidents"}
    first, second = body["incidents"]
    assert set(first) == SUMMARY_KEYS and set(second) == SUMMARY_KEYS
    assert first["has_report"] is True and first["has_sensor"] is False
    assert second["has_report"] is False and second["has_sensor"] is True and second["found_before_report"] is True
    assert first["first_seen"] == "2026-10-01T08:00:00+00:00"
    assert first["verify_vehicle"] is None and first["verify_eta_min"] is None
    sql, params = env.db.sql_with("from incidents i")[-1]
    assert "order by i.score desc" in sql
    assert params == {"limit": 50, "department": "ZDM", "statuses": ["candidate", "likely"]}
    assert first["confidence"] == 0.7 and first["citizen_confidence"] == 0.7 and first["sensor_confidence"] is None
    assert first["yes_count"] == 24 and first["awaiting_verification"] is False


def _detail_fixture(env, incident: dict, summarize=None):
    env.db.on("from incidents i", lambda p: incident if p["id"] == incident["id"] else None)
    env.db.on("join reports r", [
        {"id": 55, "raw_text": "Szyna pęknięta na Marszałkowskiej", "summary_en": "Cracked rail", "urgency": 4,
         "created_at": T0, "photo_url": "/photos/a.jpg"},
        {"id": 56, "raw_text": "Tramwaj mocno trzęsie", "summary_en": "Tram shakes", "urgency": 3,
         "created_at": T0 + timedelta(hours=1), "photo_url": None},
    ])
    bump = {"kind": "bump", "speed_kmh": 31.0, "raw_peak": 7.2, "signal": [0.1, 2.5, 0.3], "signal_fs": 100,
            "peak_index": 1}
    env.db.on("left join rides rd", [
        {"id": 900, "source": "report", "type": "tram_track", "severity": 0.8, "ts": T0, "ride_id": None,
         "report_id": 55, "details": {"kind": "report", "urgency": 4}, "vehicle_line": None, "ride_mode": None},
        {"id": 901, "source": "sensor", "type": "tram_track", "severity": 0.4, "ts": T0 + timedelta(hours=2),
         "ride_id": 3, "report_id": None, "details": {**bump, "signal": [9.0]}, "vehicle_line": "17", "ride_mode": "tram"},
        {"id": 902, "source": "sensor", "type": "tram_track", "severity": 0.9, "ts": T0 + timedelta(hours=3),
         "ride_id": 4, "report_id": None, "details": bump, "vehicle_line": "17", "ride_mode": "tram"},
    ])
    env.db.on("update incidents set summary", {"id": incident["id"]})
    calls = []

    def summarize_reports(texts):
        calls.append(texts)
        if summarize is None:
            raise RuntimeError("LLM offline")
        return summarize

    install(env.mp, "backend.triage.structure", summarize_reports=summarize_reports)
    return calls


def test_incident_detail_shape_timeline_signal_and_cached_summary(env):
    inc = incident_row(status="verified", report_count=2, sensor_count=2, sensor_rides=2, sensor_confirmed=True,
                       verify_vehicle="tram 17", verify_eta_min=6, verify_requested_at=T0 + timedelta(minutes=90),
                       verified_at=T0 + timedelta(hours=3), confidence=0.93)
    calls = _detail_fixture(env, inc, summarize="Cracked tram rail on Marszałkowska.")
    r = env.client.get("/incidents/7")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == DETAIL_KEYS
    assert body["summary"] == "Cracked tram rail on Marszałkowska."
    assert calls == [["Szyna pęknięta na Marszałkowskiej", "Tramwaj mocno trzęsie"]]
    (sql, params), = env.db.sql_with("update incidents set summary")
    assert params == {"s": "Cracked tram rail on Marszałkowska.", "id": 7}
    assert env.conn.savepoints == 1

    assert all(set(rep) == {"id", "raw_text", "summary_en", "urgency", "created_at", "photo_url"} for rep in body["reports"])
    assert all(set(ev) == {"id", "source", "type", "severity", "ts", "ride_id", "report_id", "details"}
               for ev in body["evidence"])
    assert body["signal"] == {"fs": 100, "values": [0.1, 2.5, 0.3], "peak_index": 1}  # strongest bump (0.9)

    kinds = [t["kind"] for t in body["timeline"]]
    assert kinds == ["first_report", "report", "verification_requested", "sensor", "sensor", "verified"]
    assert all(set(t) == {"ts", "kind", "label"} for t in body["timeline"])
    assert body["timeline"][-1]["label"] == "Verified (confidence 93%); contributor trust updated"
    assert body["awaiting_verification"] is False  # sensors answered the request
    assert body["timeline"][3]["label"].startswith("Tram 17 sensors detected a bump")


def test_incident_detail_summary_failures_are_ignored(env):
    calls = _detail_fixture(env, incident_row(report_count=2), summarize=None)  # summarize raises
    r = env.client.get("/incidents/7")
    assert r.status_code == 200 and r.json()["summary"] is None and len(calls) == 1
    assert not env.db.sql_with("update incidents set summary")


def test_incident_detail_uses_cached_summary_and_404(env):
    calls = _detail_fixture(env, incident_row(summary="cached", report_count=5), summarize="new")
    assert env.client.get("/incidents/7").json()["summary"] == "cached"
    assert calls == []
    assert env.client.get("/incidents/999").status_code == 404


def test_incident_detail_misses_answers_and_proactive(env):
    inc = incident_row(status="candidate", report_count=1, verify_vehicle="tram 17",
                       verify_requested_at=T0 + timedelta(minutes=30), found_before_report=True,
                       sensor_misses=2, last_miss_at=T0 + timedelta(hours=6))
    _detail_fixture(env, inc, summarize="x")
    env.db.on("from citizen_responses cr", [
        {"answer": False, "created_at": T0 + timedelta(hours=7), "trust": 0.8}])
    body = env.client.get("/incidents/7").json()
    kinds = [t["kind"] for t in body["timeline"]]
    assert set(kinds) <= TIMELINE_KINDS
    assert kinds[-2:] == ["sensor_miss", "response"]
    assert body["timeline"][-2]["label"] == "A passing vehicle found no anomaly (2 clean passes so far)"
    assert body["timeline"][-1]["label"] == "Citizen answered NO, not there (trust 0.80)"
    assert "proactive" in kinds and body["summary"] is None  # report_count < 2: no LLM summary
    assert body["awaiting_verification"] is False  # the vehicle already passed after the request


def test_verify_incident(env):
    state = incident_row()
    env.db.on("from incidents i", lambda p: state if p["id"] == 7 else None)

    def request_verification(conn, incident_id):
        state.update(verify_vehicle="tram 17", verify_eta_min=6, verify_requested_at=T0)
        return {"vehicle": "tram 17", "line": "17", "eta_min": 6, "distance_m": 1800.0}

    calls = fake_fusion(env, verify_request=request_verification)
    r = env.client.post("/incidents/7/verify")
    assert r.status_code == 200
    assert r.json() == {"incident_id": 7, "status": "likely", "vehicle": "tram 17", "eta_min": 6}
    assert calls == [("request_verification", 7)]
    assert env.client.post("/incidents/404/verify").status_code == 404


# --------------------------------------------------------------------------- reports

def _report_pipeline(env, *, evidence_id=900, category="tram_track", department="Tramwaje Warszawskie",
                     fail_on: str | None = None):
    calls = []

    def process_report(conn, text, *, pin=None, photo_bytes=None, created_at=None, source="web", structured=None,
                       contributor_id=None):
        if fail_on and fail_on in text:
            raise RuntimeError("triage exploded")
        calls.append({"text": text, "pin": pin, "photo_bytes": photo_bytes, "created_at": created_at, "source": source})
        if contributor_id is not None:
            calls[-1]["contributor_id"] = contributor_id
        rid = 54 + len(calls)
        return {"report_id": rid, "evidence_id": evidence_id and evidence_id + len(calls) - 1,
                "structured": {"category": category, "department": department, "urgency": 4},
                "duplicate_of": None, "lon": 21.0, "lat": 52.2, "photo_url": None}

    install(env.mp, "backend.triage.pipeline", process_report=process_report)
    return calls


def test_create_report_requests_verification(env):
    pipeline_calls = _report_pipeline(env)
    state = incident_row(report_count=24)
    env.db.on("from incidents i", lambda p: state)

    def request_verification(conn, incident_id):
        state.update(verify_vehicle="tram 17", verify_eta_min=6, verify_requested_at=T0 + timedelta(hours=6))
        return {"vehicle": "tram 17", "eta_min": 6}

    calls = fake_fusion(env, ingest=lambda conn, ids: [7], verify_request=request_verification)
    r = env.client.post("/reports", data={"text": "  Pęknięta szyna  ", "lon": "21.0", "lat": "52.2"},
                        files={"photo": ("p.jpg", b"\xff\xd8photo", "image/jpeg")})
    assert r.status_code == 200
    body = r.json()
    assert set(body) == REPORT_STATUS_KEYS
    assert body == {
        "report_id": 55, "incident_id": 7, "status": "likely", "category": "tram_track",
        "department": "Tramwaje Warszawskie", "others_count": 23, "sensor_confirmed": False,
        "verify_vehicle": "tram 17", "verify_eta_min": 6, "confidence": 0.7, "contributor_trust": None,
        "message": "23 others reported this. Tram 17 will verify in ~6 min. Status: likely (70% confidence). "
                   "Sent to Tramwaje Warszawskie.",
    }
    assert pipeline_calls == [{"text": "Pęknięta szyna", "pin": (21.0, 52.2), "photo_bytes": b"\xff\xd8photo",
                               "created_at": None, "source": "web"}]
    assert calls == [("ingest_evidence", [900]), ("request_verification", 7)]


def test_create_report_with_sensor_evidence_skips_verification(env):
    _report_pipeline(env)
    env.db.on("from incidents i", incident_row(report_count=2, sensor_count=3, sensor_rides=2, sensor_confirmed=True,
                                               status="verified", verify_vehicle="tram 17", confidence=0.91))
    calls = fake_fusion(env, ingest=lambda conn, ids: [7])
    body = env.client.post("/reports", data={"text": "Dziura"}).json()
    assert ("request_verification", 7) not in calls
    assert body["sensor_confirmed"] is True and body["others_count"] == 1
    assert body["message"] == "1 other person reported this. Verified by tram 17 sensors. Sent to Tramwaje Warszawskie."


def test_create_report_without_location(env):
    pipeline_calls = _report_pipeline(env, evidence_id=None, category="waste", department="Straż Miejska")
    calls = fake_fusion(env)
    r = env.client.post("/reports", data={"text": "Śmieci gdzieś", "lon": "", "lat": ""})
    assert r.status_code == 200
    body = r.json()
    assert set(body) == REPORT_STATUS_KEYS
    assert body["incident_id"] is None and body["status"] is None and body["others_count"] == 0
    assert body["message"].endswith("Sent to Straż Miejska.") and "pin" in body["message"]
    assert pipeline_calls[0]["pin"] is None and calls == []


def test_create_report_validation(env):
    _report_pipeline(env)
    fake_fusion(env)
    assert env.client.post("/reports", data={"text": "   "}).status_code == 422
    assert env.client.post("/reports", data={}).status_code == 422
    assert env.client.post("/reports", data={"text": "x", "lon": "500", "lat": "52"}).status_code == 422


def test_report_status(env):
    env.db.on("left join incident_evidence", lambda p: {"id": 55, "category": "tram_track",
                                                        "department": "Tramwaje Warszawskie", "incident_id": 7}
              if p["id"] == 55 else None)
    env.db.on("from incidents i", incident_row(status="verified", sensor_confirmed=True, sensor_count=1,
                                               verify_vehicle="tram 17", verify_eta_min=6, report_count=24))
    r = env.client.get("/reports/55/status")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == REPORT_STATUS_KEYS
    assert body["message"] == "23 others reported this. Verified by tram 17 sensors. Sent to Tramwaje Warszawskie."
    assert env.client.get("/reports/999/status").status_code == 404


def test_bulk_isolates_bad_records(env):
    pipeline_calls = _report_pipeline(env, fail_on="BOOM")
    calls = fake_fusion(env, ingest=lambda conn, ids: [7] if ids[0] % 2 == 0 else [8, 7])
    payload = {"reports": [
        {"text": "Dziura na Puławskiej", "created_at": "2026-09-30T10:00:00", "lon": 21.02, "lat": 52.2,
         "source": "synthetic"},
        {"text": "BOOM this one crashes the pipeline"},
        {"created_at": "2026-09-30T11:00:00"},                      # no text -> invalid record
        {"text": "Bad source", "source": "twitter"},                # invalid source
        {"text": "Kolejna dziura"},
    ]}
    r = env.client.post("/reports/bulk", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"processed", "report_ids", "incident_ids"}
    assert body == {"processed": 2, "report_ids": [55, 56], "incident_ids": [7, 8]}
    assert pipeline_calls[0]["created_at"] == datetime(2026, 9, 30, 10, tzinfo=timezone.utc)
    assert pipeline_calls[0]["pin"] == (21.02, 52.2) and pipeline_calls[0]["source"] == "synthetic"
    assert pipeline_calls[1]["source"] == "19115" and pipeline_calls[1]["pin"] is None
    assert not any(c[0] == "request_verification" for c in calls)
    assert env.conn.savepoints == 3  # ok, BOOM (rolled back), ok; invalid records never touch the DB


# --------------------------------------------------------------------------- rides

def _sensor_fakes(env, *, ride_id=3, fail=False):
    calls = []

    def load_sensor_logger(path):
        calls.append(("load", str(path)))
        if "broken" in str(path):
            raise ValueError("no accelerometer columns")
        return FakeDF([{"t": 0.0}] * 3)

    def from_samples(samples):
        calls.append(("from_samples", len(samples)))
        return FakeDF(samples)

    def process_ride(conn, df, *, vehicle_line, mode, device_hash=None, source_file=None):
        calls.append(("process_ride", {"n": len(df), "vehicle_line": vehicle_line, "mode": mode,
                                       "device_hash": device_hash, "source_file": source_file}))
        if fail:
            raise RuntimeError("mapmatch failed")
        return {"ride_id": ride_id, "evidence_ids": [11, 12], "bumps": 2, "dark_gaps": 1, "segments_covered": 40}

    install(env.mp, "backend.sensor.ingest", load_sensor_logger=load_sensor_logger, from_samples=from_samples)
    install(env.mp, "backend.sensor.pipeline", process_ride=process_ride)
    return calls


def test_ride_upload_orchestration(env):
    sensor_calls = _sensor_fakes(env)
    fusion_calls = fake_fusion(env, ingest=lambda conn, ids: [7, 8], check=lambda conn, rid: [7])
    r = env.client.post("/rides/upload", files={"file": ("tram 17 ride.csv", b"t,ax\n0,1\n", "text/csv")},
                        data={"vehicle_line": "17", "mode": "tram"})
    assert r.status_code == 200
    body = r.json()
    assert set(body) == RIDE_KEYS
    assert body == {"ride_id": 3, "bumps": 2, "dark_gaps": 1, "segments_covered": 40, "evidence_ids": [11, 12],
                    "incident_ids": [7, 8], "verified_incident_ids": [7]}
    saved = list((env.tmp / "rides").iterdir())
    assert len(saved) == 1 and saved[0].name.endswith("tram_17_ride.csv") and saved[0].read_bytes() == b"t,ax\n0,1\n"
    assert sensor_calls[0] == ("load", str(saved[0]))
    assert sensor_calls[1][1]["vehicle_line"] == "17" and sensor_calls[1][1]["mode"] == "tram"
    assert fusion_calls == [("ingest_evidence", [11, 12]), ("check_ride_verifications", 3)]


def test_ride_upload_rejects_bad_input(env):
    _sensor_fakes(env)
    fake_fusion(env)
    csv = {"file": ("ride.csv", b"t\n", "text/csv")}
    assert env.client.post("/rides/upload", files={"file": ("ride.txt", b"x", "text/plain")}).status_code == 400
    assert env.client.post("/rides/upload", files=csv, data={"mode": "metro"}).status_code == 422
    r = env.client.post("/rides/upload", files={"file": ("broken.zip", b"PK", "application/zip")})
    assert r.status_code == 400 and "no accelerometer" in r.json()["detail"]


def _chunk(sid, n, *, final=False, start=0, line="17"):
    samples = [{"t": (start + i) / 100, "ax": 0.1, "ay": 0.2, "az": 9.8, "lat": 52.2, "lon": 21.0, "speed_kmh": 20}
               for i in range(n)]
    return {"session_id": sid, "vehicle_line": line, "mode": "tram", "samples": samples, "final": final}


def test_ride_stream_buffers_until_final(env):
    sensor_calls = _sensor_fakes(env, ride_id=9)
    fusion_calls = fake_fusion(env, ingest=lambda conn, ids: [7], check=lambda conn, rid: [])
    r1 = env.client.post("/rides/stream", json=_chunk("abc", 3))
    r2 = env.client.post("/rides/stream", json=_chunk("abc", 2, start=3, line=None))
    other = env.client.post("/rides/stream", json=_chunk("other", 4))
    assert r1.status_code == 200 and r1.json() == {"session_id": "abc", "buffered": 3}
    assert r2.json() == {"session_id": "abc", "buffered": 5}
    assert other.json() == {"session_id": "other", "buffered": 4}
    assert env.db_opened == [] and sensor_calls == []  # buffering never touches the DB

    r = env.client.post("/rides/stream", json=_chunk("abc", 1, start=5, final=True))
    assert r.status_code == 200
    body = r.json()
    assert set(body) == RIDE_KEYS and body["ride_id"] == 9 and body["incident_ids"] == [7]
    assert sensor_calls[0] == ("from_samples", 6)
    meta = sensor_calls[1][1]
    assert meta["n"] == 6 and meta["vehicle_line"] == "17" and meta["mode"] == "tram"
    assert len(meta["device_hash"]) == 16 and meta["source_file"].endswith(".csv")
    assert fusion_calls == [("ingest_evidence", [11, 12]), ("check_ride_verifications", 9)]
    assert env.db_opened == [1]
    assert "abc" not in rides_api._streams and rides_api._streams["other"]["samples"]


def test_ride_stream_failed_final_can_be_retried(env):
    _sensor_fakes(env, fail=True)
    fake_fusion(env)
    env.client.post("/rides/stream", json=_chunk("s1", 4))
    r = env.client.post("/rides/stream", json=_chunk("s1", 2, start=4, final=True))
    assert r.status_code == 500
    assert len(rides_api._streams["s1"]["samples"]) == 4  # final chunk removed again, buffer kept

    sensor_calls = _sensor_fakes(env)
    r = env.client.post("/rides/stream", json=_chunk("s1", 2, start=4, final=True))
    assert r.status_code == 200 and sensor_calls[0] == ("from_samples", 6)
    assert "s1" not in rides_api._streams


def test_ride_stream_empty_final_size_cap_and_expiry(env):
    _sensor_fakes(env)
    fake_fusion(env)
    r = env.client.post("/rides/stream", json={"session_id": "empty", "mode": "road", "samples": [], "final": True})
    assert r.status_code == 400 and "empty" not in rides_api._streams

    env.mp.setattr(rides_api, "MAX_STREAM_SAMPLES", 3)
    assert env.client.post("/rides/stream", json=_chunk("big", 4)).status_code == 413
    rides_api._streams["stale"] = {"samples": [{}], "vehicle_line": None, "mode": "tram", "touched": -1e9}
    assert env.client.post("/rides/stream", json=_chunk("ok", 1)).status_code == 200  # expiry sweep survives "big"
    assert "stale" not in rides_api._streams


# --------------------------------------------------------------------------- stats / vehicles

def test_stats(env):
    env.db.on("as reports_total", {"reports_total": 412, "incidents_total": 57, "found_before_report": 4,
                                   "candidate_total": 30, "likely_total": 15, "verified_total": 12,
                                   "awaiting_verification": 3, "contributors_total": 140,
                                   "avg_verification_min": Decimal("6.4666"), "rides_total": 8,
                                   "segments_measured": 912})
    r = env.client.get("/stats")
    assert r.status_code == 200
    assert set(r.json()) == STATS_KEYS
    assert r.json()["avg_verification_min"] == 6.5 and r.json()["reports_total"] == 412

    env.db.on("as reports_total", {k: 0 for k in STATS_KEYS} | {"avg_verification_min": None})
    assert env.client.get("/stats").json()["avg_verification_min"] is None


def test_live_vehicles(env):
    seen = []

    def live_vehicles(kind="tram"):
        seen.append(kind)
        return [{"id": "4321", "line": "17", "lon": 21.01, "lat": 52.23, "ts": T0, "kind": kind, "brigade": "3"},
                {"id": "x", "line": "9", "lon": None, "lat": None, "ts": None, "kind": kind}]

    install(env.mp, "backend.fusion.verify", live_vehicles=live_vehicles)
    r = env.client.get("/vehicles/live", params={"kind": "bus"})
    assert r.status_code == 200
    assert r.json() == {"vehicles": [{"id": "4321", "line": "17", "lon": 21.01, "lat": 52.23,
                                      "ts": "2026-10-01T08:00:00+00:00", "kind": "bus"}]}
    assert seen == ["bus"]
    assert env.client.get("/vehicles/live", params={"kind": "metro"}).status_code == 422

    def broken(kind="tram"):
        raise ConnectionError("ZTM down")

    install(env.mp, "backend.fusion.verify", live_vehicles=broken)
    assert env.client.get("/vehicles/live").json() == {"vehicles": []}


# --------------------------------------------------------------------------- serializers

def test_status_messages():
    msg = ser.status_message
    assert msg(incident=incident_row(found_before_report=True, sensor_confirmed=True), others=0,
               department="ZDM") == ("You're the first to report this. Found by sensors before any report. "
                                     "Status: likely (70% confidence). Sent to ZDM.")
    assert msg(incident=incident_row(verify_vehicle="tram 17", verify_requested_at=T0), others=2,
               department=None) == "2 others reported this. Tram 17 will verify soon. Status: likely (70% confidence)."
    assert "no anomaly" in msg(incident=incident_row(status="candidate", sensor_misses=1, last_miss_at=T0),
                               others=0, department="ZDM")
    assert "dismissed" in msg(incident=incident_row(status="dismissed"), others=0, department=None)


def test_incident_summary_handles_naive_and_string_timestamps():
    row = incident_row(first_seen=datetime(2026, 10, 1, 8), last_seen="2026-10-01T09:00:00+00:00", score=None)
    out = ser.incident_summary(row)
    assert out["first_seen"] == "2026-10-01T08:00:00+00:00" and out["last_seen"] == "2026-10-01T09:00:00+00:00"
    assert out["score"] == 0.0 and list(out) == list(ser.SUMMARY_KEYS)


# --------------------------------------------------------------------------- citizen YES/NO + trust

def _respond_fixture(env, status="likely", trust=0.6):
    state = incident_row(status=status)
    env.db.on("from incidents i", lambda p: state if p["id"] == 7 else None)
    env.db.on("insert into contributors", {"id": 31, "trust": trust, "correct": 0, "incorrect": 0})
    calls = fake_fusion(env)
    return state, calls


def test_citizen_yes_no_is_recorded_weighted_and_reassessed(env):
    state, calls = _respond_fixture(env, trust=0.8)
    votes = []
    env.conn.execute = lambda sql, params=None: votes.append((sql, params))
    r = env.client.post("/incidents/7/responses", json={"answer": "no", "contributor": "browser-token-1"})
    assert r.status_code == 200
    body = r.json()
    assert set(body) == RESPONSE_KEYS
    assert body["incident_id"] == 7 and body["status"] == "likely" and body["contributor_trust"] == 0.8
    (sql, params), = [v for v in votes if "citizen_responses" in v[0]]
    assert params == {"incident_id": 7, "contributor_id": 31, "answer": False, "settled": False}
    assert calls == [("refresh_incident", 7)]
    (_, contributor_params), = env.db.sql_with("insert into contributors")
    assert contributor_params["hash"] == trust_mod.contributor_hash("browser-token-1")  # never the raw token


def test_answers_on_verified_incident_do_not_earn_trust(env):
    _respond_fixture(env, status="verified")
    votes = []
    env.conn.execute = lambda sql, params=None: votes.append(params)
    assert env.client.post("/incidents/7/responses", json={"answer": "yes", "contributor": "browser-token-1"}).status_code == 200
    assert votes[-1]["settled"] is True


def test_citizen_response_validation(env):
    _respond_fixture(env, status="dismissed")
    ok = {"answer": "yes", "contributor": "browser-token-1"}
    assert env.client.post("/incidents/7/responses", json=ok).status_code == 409
    assert env.client.post("/incidents/404/responses", json=ok).status_code == 404
    assert env.client.post("/incidents/7/responses", json={"answer": "maybe", "contributor": "browser-token-1"}).status_code == 422
    assert env.client.post("/incidents/7/responses", json={"answer": "yes", "contributor": "short"}).status_code == 422


def test_report_with_contributor_returns_trust(env):
    pipeline_calls = _report_pipeline(env)
    env.db.on("from incidents i", incident_row(sensor_count=1, status="verified"))
    env.db.on("insert into contributors", {"id": 31, "trust": 0.72, "correct": 2, "incorrect": 1})
    fake_fusion(env, ingest=lambda conn, ids: [7])
    body = env.client.post("/reports", data={"text": "Dziura", "contributor": "browser-token-1"}).json()
    assert pipeline_calls[0]["contributor_id"] == 31 and body["contributor_trust"] == 0.72


def test_awaiting_verification_flag():
    asked = T0 + timedelta(hours=1)
    assert ser.awaiting_verification(incident_row(verify_requested_at=asked)) is True
    assert ser.awaiting_verification(incident_row(verify_requested_at=asked, sensor_count=1)) is False
    assert ser.awaiting_verification(incident_row(verify_requested_at=asked, last_miss_at=asked + timedelta(minutes=5))) is False
    assert ser.awaiting_verification(incident_row(verify_requested_at=asked, status="verified")) is False
    assert ser.awaiting_verification(incident_row()) is False
