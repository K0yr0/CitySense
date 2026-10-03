"""Mobile API tests (backend/api/mobile.py, owner A): fake DB, fake fusion/triage, no network.

The contract is the mobile one: PublicIncident never leaks sensor_* / verify_* / evidence /
timeline / report texts; reporting, answering and routes need a Bearer token; the 25 m
question obeys GPS accuracy, distance, once-per-incident and work_status = done.
The PostGIS test at the end runs every SQL statement for real, only with CITYECHO_TEST_DB=1.
"""
from __future__ import annotations

import importlib
import os
import sys
import types
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend import config
from backend.api import deps
from backend.api import mobile
from backend.auth import store, tokens
from backend.fusion import trust as trust_mod
from backend.main import app

T0 = datetime(2026, 10, 1, 8, 0, tzinfo=timezone.utc)
SECRET = "mobile-test-secret-" + "z" * 40
PUBLIC_KEYS = {"id", "type", "lon", "lat", "address", "department", "status", "confidence", "work_status",
               "report_count", "first_seen", "last_seen"}
REPORT_KEYS = {"report_id", "text", "created_at", "category", "department", "photo_url", "incident",
               "others_count", "message"}
ROUTE_KEYS = {"id", "name", "kind", "start", "end", "line", "mode", "created_at"}
USER = {"id": 1, "email": "ala@example.com", "name": "Ala", "role": "citizen"}


# --------------------------------------------------------------------------- fakes

class FakeConn:
    @contextmanager
    def transaction(self):
        yield


class FakeDB:
    """backend.db.fetch_one/fetch_all answering by SQL substring (newest rule wins)."""

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
    mod = types.ModuleType(name)
    mod.__dict__.update(attrs)
    monkeypatch.setitem(sys.modules, name, mod)
    parent, _, child = name.rpartition(".")
    monkeypatch.setattr(importlib.import_module(parent), child, mod, raising=False)
    return mod


def incident_row(**kw) -> dict:
    """Full incidents row (what B's load_incident returns), incl. fields that must never leak."""
    row = dict(id=7, segment_id=101, type="road_damage", status="likely", score=0.91, department="ZDM",
               address="Marszałkowska", summary="secret summary", lon=21.0122, lat=52.2297, report_count=24,
               sensor_count=2, sensor_rides=2, sensor_confirmed=True, found_before_report=False,
               max_severity=0.8, max_urgency=4, first_seen=T0, last_seen=T0 + timedelta(hours=5),
               verify_vehicle="bus 175", verify_eta_min=4, verify_requested_at=T0, verified_at=None,
               confidence=0.7, sensor_confidence=0.6, citizen_confidence=0.7, yes_count=24, no_count=0,
               sensor_misses=0, last_miss_at=None, work_status="todo", raw_text="someone's text")
    row.update(kw)
    return row


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setattr(config, "settings", replace(config.settings, auth_secret=SECRET, auth_dev_login=False))
    conn, fdb = FakeConn(), FakeDB()
    install(monkeypatch, "backend.db", fetch_one=fdb.fetch_one, fetch_all=fdb.fetch_all)
    monkeypatch.setattr(trust_mod, "fetch_one", fdb.fetch_one)
    monkeypatch.setattr(trust_mod, "fetch_all", fdb.fetch_all)
    calls: list[tuple] = []

    def contributor_for_user(conn, user_id, device_token=None):
        calls.append(("contributor_for_user", user_id))
        return {"id": 42, "trust": 0.75, "correct": 3, "incorrect": 1}

    monkeypatch.setattr(store, "contributor_for_user", contributor_for_user)
    monkeypatch.setattr(trust_mod, "record_vote",
                        lambda conn, iid, cid, answer, resolved=False: calls.append(("vote", iid, cid, answer, resolved)))
    install(monkeypatch, "backend.fusion.incidents",
            refresh_incident=lambda conn, iid: calls.append(("refresh", iid)) or {},
            ingest_evidence=lambda conn, ids: calls.append(("ingest", list(ids))) or [7])
    install(monkeypatch, "backend.fusion.verify",
            request_verification=lambda conn, iid: calls.append(("request_verification", iid)))
    app.dependency_overrides[deps.get_db] = lambda: conn
    token = tokens.issue_token(USER)
    yield SimpleNamespace(db=fdb, calls=calls, client=TestClient(app), mp=monkeypatch,
                          auth={"Authorization": f"Bearer {token}"})
    app.dependency_overrides.clear()
    mobile._osrm_cache.clear()


# --------------------------------------------------------------------------- pure helpers

def test_public_incident_never_leaks():
    out = mobile.public_incident(incident_row())
    assert set(out) == PUBLIC_KEYS
    assert out["work_status"] == "todo" and out["confidence"] == 0.7 and out["report_count"] == 24
    assert out["first_seen"] == T0.isoformat()
    assert mobile.public_incident(incident_row(work_status=None, confidence=None))["work_status"] == "todo"


def test_health_class_thresholds():
    assert [mobile.health_class(h) for h in (None, float("nan"), 0.0, 0.39, 0.4, 0.69, 0.7, 1.0)] == \
        ["unknown", "unknown", "poor", "poor", "fair", "fair", "good", "good"]


def test_messages_are_turkish_and_separate_the_two_states():
    assert mobile.report_message(incident_row(report_count=1, status="candidate")) == \
        "İlk bildiren sensin. Değerlendiriliyor. Departmana iletildi: ZDM."
    assert mobile.report_message(incident_row(work_status="in_progress")) == \
        "23 kişi daha bildirdi. Belediye ilgileniyor. Departmana iletildi: ZDM."
    assert mobile.report_message(incident_row(work_status="done", status="verified")) == \
        "23 kişi daha bildirdi. Yapıldı: belediye onardı."
    assert mobile.report_message(None, "ZDM").startswith("Bildirimin alındı.")
    assert mobile.detail_message(incident_row(status="verified"), reporter=False) == \
        "24 kişi bildirdi · Doğrulandı · Departmana iletildi: ZDM"
    assert "ilgili birim" in mobile.report_message(incident_row(department="inne"))


def test_parse_ids_and_natural_sort():
    assert mobile.parse_ids("12, 7,x,,7,²,-3,99999999999999999999") == [12, 7, -3]
    assert len(mobile.parse_ids(",".join(map(str, range(1000))))) == mobile.MAX_EXCLUDE_IDS
    assert mobile.parse_ids(None) == []
    assert sorted(["N11", "175", "17", "4", "N01"], key=mobile.natural_key) == ["4", "17", "175", "N01", "N11"]


def test_stitch_path_flips_segments():
    a = [[0, 0], [1, 0]]
    b = [[2, 0], [1, 0]]  # stored backwards
    c = [[2, 0], [3, 0]]
    assert mobile.stitch_path([a, b, [], c]) == [[0, 0], [1, 0], [2, 0], [3, 0]]


def test_route_summary_and_poor_runs():
    segs = [
        {"health": 0.9, "length_m": 25, "covered_m": 25, "along_m": 10, "lon": 21, "lat": 52},
        {"health": 0.2, "length_m": 25, "covered_m": 25, "along_m": 35, "lon": 21.1, "lat": 52.1},
        {"health": None, "length_m": 25, "covered_m": 25, "along_m": 60, "lon": 21.2, "lat": 52.2},
        {"health": 0.3, "length_m": 25, "covered_m": 20, "along_m": 85, "lon": 21.3, "lat": 52.3},
        {"health": 0.5, "length_m": 25, "covered_m": 25, "along_m": 110, "lon": 21.4, "lat": 52.4},
        {"health": 0.1, "length_m": 25, "covered_m": 25, "along_m": 135, "lon": 21.5, "lat": 52.5},
    ]
    s = mobile.route_summary(segs)
    assert s == {"good_m": 25.0, "fair_m": 25.0, "poor_m": 70.0, "unknown_m": 25.0, "overall": "fair"}
    halved = mobile.route_summary(segs, route_length_m=72.5)  # parallel ways counted twice -> scaled
    assert halved["poor_m"] == 35.0 and halved["good_m"] == 12.5
    warns = mobile.poor_road_warnings(segs)
    assert [(w["distance_along_m"], w["message"]) for w in warns] == [
        (35.0, "İleride kötü yol (~45 m)"), (135.0, "İleride kötü yol (~25 m)")]
    assert mobile.route_summary([])["overall"] == "unknown"
    assert not mobile.runs_along({"length_m": 25, "covered_m": 3})  # a cross street
    assert round(mobile.path_length_m([[21.0, 52.0], [21.0, 52.001]])) == 111


# --------------------------------------------------------------------------- map (public)

def test_incidents_list_is_public_and_hides_closed(env):
    env.db.on("from incidents i", [incident_row(), incident_row(id=8)])
    r = env.client.get("/mobile/incidents?bbox=20.9,52.1,21.2,52.3&limit=10")
    assert r.status_code == 200
    body = r.json()["incidents"]
    assert [i["id"] for i in body] == [7, 8] and all(set(i) == PUBLIC_KEYS for i in body)
    sql, params = env.db.sql_with("from incidents i")[-1]
    assert params["hidden"] == ["dismissed", "closed"] and params["min_lon"] == 20.9 and params["limit"] == 10
    assert "order by i.last_seen desc" in sql
    assert env.client.get("/mobile/incidents?bbox=1,2,3").status_code == 400


def test_incident_detail_anonymous_and_signed_in(env):
    env.db.on("from incidents i", lambda p: incident_row() if p["id"] == 7 else None)
    assert env.client.get("/mobile/incidents/99").status_code == 404

    anon = env.client.get("/mobile/incidents/7").json()
    assert set(anon) == PUBLIC_KEYS | {"my_answer", "i_reported", "message"}
    assert anon["my_answer"] is None and anon["i_reported"] is False
    assert anon["message"] == "24 kişi bildirdi · Muhtemelen gerçek bir sorun · Departmana iletildi: ZDM"
    assert not env.db.sql_with("as my_answer")  # no per-user lookup without a token

    env.db.on("as my_answer", {"my_answer": False, "i_reported": True})
    mine = env.client.get("/mobile/incidents/7", headers=env.auth).json()
    assert mine["my_answer"] == "no" and mine["i_reported"] is True
    assert mine["message"].startswith("23 kişi daha bildirdi")
    assert env.db.sql_with("as my_answer")[-1][1] == {"id": 7, "user_id": 1}
    stale = env.client.get("/mobile/incidents/7", headers={"Authorization": "Bearer not.a.jwt"})
    assert stale.status_code == 200 and stale.json()["my_answer"] is None


def test_segments_need_bbox_and_return_classes_only(env):
    assert env.client.get("/mobile/segments").status_code == 422
    env.db.on("from segments s", [
        {"id": 1, "mode": "road", "health": 0.8, "geojson": '{"type":"LineString","coordinates":[[21,52],[21.1,52.1]]}'},
        {"id": 2, "mode": "tram", "health": 0.1, "geojson": '{"type":"LineString","coordinates":[[21,52],[21.1,52]]}'},
    ])
    r = env.client.get("/mobile/segments?bbox=20.9,52.1,21.2,52.3&mode=tram")
    assert r.status_code == 200
    assert r.json() == {"segments": [
        {"id": 1, "mode": "road", "health_class": "good", "path": [[21.0, 52.0], [21.1, 52.1]]},
        {"id": 2, "mode": "tram", "health_class": "poor", "path": [[21.0, 52.0], [21.1, 52.0]]}]}
    sql, params = env.db.sql_with("from segments s")[-1]
    assert "s.health is not null" in sql and params["mode"] == "tram" and params["limit"] == 5000


def test_lines_sorted_naturally(env):
    env.db.on("from rides r", [{"line": "175", "mode": "road"}, {"line": "17", "mode": "tram"},
                               {"line": "4", "mode": "tram"}])
    assert env.client.get("/mobile/lines").json() == {"lines": [
        {"line": "4", "mode": "tram"}, {"line": "17", "mode": "tram"}, {"line": "175", "mode": "road"}]}
    env.client.get("/mobile/lines?mode=road")
    assert env.db.sql_with("from rides r")[-1][1] == {"mode": "road"}


# --------------------------------------------------------------------------- 25 m question

def test_question_rules(env):
    q = "/mobile/question?lon=21.0122&lat=52.2297"
    assert env.client.get(q + "&accuracy_m=5").status_code == 401
    assert env.client.get(q + "&accuracy_m=30", headers=env.auth).json() == {"incident": None, "distance_m": None}
    assert not env.db.sql_with("distance_m")  # bad GPS: not even asked

    assert env.client.get(q + "&accuracy_m=10", headers=env.auth).json() == {"incident": None, "distance_m": None}
    env.db.on("distance_m", {**incident_row(), "distance_m": 12.345})
    body = env.client.get(q + "&accuracy_m=10&exclude=3,x,4", headers=env.auth).json()
    assert set(body["incident"]) == PUBLIC_KEYS and body["distance_m"] == 12.3
    sql, params = env.db.sql_with("distance_m")[-1]
    assert params["radius"] == 25 and params["open"] == ["candidate", "likely"] and params["user_id"] == 1
    assert params["exclude"] == [3, 4] and "i.id <> all(%(exclude)s::bigint[])" in sql
    assert "work_status <> 'done'" in sql and "citizen_responses" in sql
    env.client.get(q + "&accuracy_m=10", headers=env.auth)
    assert env.db.sql_with("distance_m")[-1][1]["exclude"] == []


def answer(env, incident_id=7, **kw):
    body = {"answer": "yes", "lon": 21.0122, "lat": 52.2297, "accuracy_m": 8, **kw}
    return env.client.post(f"/mobile/incidents/{incident_id}/answer", json=body, headers=env.auth)


def test_answer_rejections(env):
    assert env.client.post("/mobile/incidents/7/answer", json={"answer": "yes", "lon": 21, "lat": 52,
                                                              "accuracy_m": 5}).status_code == 401
    assert answer(env, accuracy_m=26).status_code == 422
    assert answer(env, answer="maybe").status_code == 422
    assert answer(env).status_code == 404
    env.db.on("as distance_m", {**incident_row(work_status="done"), "distance_m": 3})
    assert answer(env).status_code == 409
    env.db.on("as distance_m", {**incident_row(status="verified"), "distance_m": 3})
    assert answer(env).status_code == 409
    env.db.on("as distance_m", {**incident_row(), "distance_m": 25.5})
    assert answer(env).status_code == 403
    env.db.on("as distance_m", {**incident_row(), "distance_m": 3})
    env.db.on("as answered", {"answered": 1})
    assert answer(env).status_code == 409
    assert not [c for c in env.calls if c[0] in ("vote", "refresh")]


def test_answer_records_weighted_vote(env):
    env.db.on("from incidents i\nwhere i.id", incident_row(status="verified", confidence=0.9))  # after refresh
    env.db.on("as distance_m", {**incident_row(), "distance_m": 3})  # newest rule wins for the target query
    env.db.on("select trust from contributors", {"trust": 0.8})
    r = answer(env, answer="no")
    assert r.status_code == 200
    assert r.json() == {"incident_id": 7, "status": "verified", "confidence": 0.9, "work_status": "todo",
                        "contributor_trust": 0.8}
    assert ("vote", 7, 42, False, False) in env.calls and ("refresh", 7) in env.calls


# --------------------------------------------------------------------------- reports

def fake_pipeline(env, *, evidence_id=99, category="road_damage"):
    seen = {}

    def process_report(conn, text, **kw):
        seen.update(text=text, **kw)
        return {"report_id": 500, "evidence_id": evidence_id, "photo_url": "/photos/x.jpg" if kw["photo_bytes"] else None,
                "structured": {"category": category, "department": "ZDM"}}

    install(env.mp, "backend.triage.pipeline", process_report=process_report)
    return seen


def test_create_report_requires_login_and_validates(env):
    fake_pipeline(env)
    assert env.client.post("/mobile/reports", data={"text": "dziura"}).status_code == 401
    assert env.client.post("/mobile/reports", data={"text": "   "}, headers=env.auth).status_code == 422
    assert env.client.post("/mobile/reports", data={"text": "x", "lon": 500, "lat": 1},
                           headers=env.auth).status_code == 422


def test_create_report_joins_incident(env):
    seen = fake_pipeline(env)
    full = incident_row(sensor_count=0, verify_requested_at=None, status="candidate")
    env.db.on("from incidents i\nwhere i.id", incident_row(status="candidate", report_count=24,
                                                             work_status="in_progress"))
    env.db.on("i.sensor_count", full)  # B's load_incident
    r = env.client.post("/mobile/reports", data={"text": " Duża dziura ", "lon": "21.0122", "lat": "52.2297"},
                        files={"photo": ("p.jpg", b"\xff\xd8jpeg", "image/jpeg")}, headers=env.auth)
    assert r.status_code == 200
    body = r.json()
    assert set(body) == REPORT_KEYS and set(body["incident"]) == PUBLIC_KEYS
    assert body["report_id"] == 500 and body["text"] == "Duża dziura" and body["photo_url"] == "/photos/x.jpg"
    assert body["others_count"] == 23
    assert body["message"] == "23 kişi daha bildirdi. Belediye ilgileniyor. Departmana iletildi: ZDM."
    assert seen["contributor_id"] == 42 and seen["source"] == "web" and seen["pin"] == (21.0122, 52.2297)
    assert seen["photo_bytes"] == b"\xff\xd8jpeg"
    assert ("ingest", [99]) in env.calls and ("request_verification", 7) in env.calls


def test_create_report_without_location(env):
    fake_pipeline(env, evidence_id=None, category="streetlight")
    body = env.client.post("/mobile/reports", data={"text": "lampa"}, headers=env.auth).json()
    assert body["incident"] is None and body["others_count"] == 0
    assert body["message"].startswith("Bildirimin alındı.") and body["message"].endswith("Departmana iletildi: ZDM.")


def test_my_reports(env):
    assert env.client.get("/mobile/reports").status_code == 401
    env.db.on("join users u on u.contributor_id = r.contributor_id", [
        {"id": 2, "raw_text": "b", "created_at": T0, "category": "road_damage", "department": "ZDM",
         "photo_url": None, "incident_id": 7},
        {"id": 1, "raw_text": "a", "created_at": T0, "category": "other", "department": "inne",
         "photo_url": None, "incident_id": None}])
    env.db.on("where i.id = any", [incident_row(report_count=1, work_status="done")])
    reports = env.client.get("/mobile/reports", headers=env.auth).json()["reports"]
    assert [r["report_id"] for r in reports] == [2, 1] and all(set(r) == REPORT_KEYS for r in reports)
    assert reports[0]["incident"]["work_status"] == "done"
    assert reports[0]["message"] == "İlk bildiren sensin. Yapıldı: belediye onardı."
    assert reports[1]["incident"] is None
    assert env.db.sql_with("where i.id = any")[-1][1] == {"ids": [7]}


def test_me(env):
    env.db.on("from users where id", {"id": 1, "email": "ala@example.com", "name": "Ala", "role": "citizen"})
    body = env.client.get("/mobile/me", headers=env.auth).json()
    assert body == {"user": USER, "trust": 0.6, "correct": 0, "incorrect": 0, "reports_count": 0, "answers_count": 0}
    env.db.on("as answers_count", {"id": 42, "trust": 0.75, "correct": 3, "incorrect": 1, "reports_count": 5,
                                   "answers_count": 2})
    body = env.client.get("/mobile/me", headers=env.auth).json()
    assert (body["trust"], body["reports_count"], body["answers_count"]) == (0.75, 5, 2)
    env.db.on("from users where id", None)
    assert env.client.get("/mobile/me", headers=env.auth).status_code == 401


# --------------------------------------------------------------------------- favourite routes

def route_row(**kw):
    row = dict(id=3, name="Ev → İş", kind="points", start_lon=21.0, start_lat=52.23, end_lon=21.01, end_lat=52.229,
               line=None, mode=None, created_at=T0)
    row.update(kw)
    return row


def test_routes_crud(env):
    assert env.client.get("/mobile/routes").status_code == 401
    post = lambda body: env.client.post("/mobile/routes", json=body, headers=env.auth)  # noqa: E731
    assert post({"name": "x", "kind": "points", "start": [21, 52]}).status_code == 422
    assert post({"name": "x", "kind": "points", "start": [21, 52], "end": [21, 52]}).status_code == 422
    assert post({"name": "x", "kind": "points", "start": [221, 52], "end": [21, 52]}).status_code == 422
    assert post({"name": "x", "kind": "line"}).status_code == 422
    assert post({"name": " ", "kind": "line", "line": "17"}).status_code == 422
    assert post({"name": "x", "kind": "bus", "line": "17"}).status_code == 422

    env.db.on("insert into favorite_routes", lambda p: route_row(kind=p["kind"], line=p["line"], mode=p["mode"],
                                                                 start_lon=p["start_lon"], start_lat=p["start_lat"]))
    r = post({"name": " Tramvay ", "kind": "line", "line": "17", "mode": "tram", "start": [21, 52]})
    assert r.status_code == 200
    body = r.json()
    assert set(body) == ROUTE_KEYS and body["kind"] == "line" and body["line"] == "17" and body["start"] is None
    params = env.db.sql_with("insert into favorite_routes")[-1][1]
    assert params["user_id"] == 1 and params["name"] == "Tramvay" and params["start_lon"] is None

    env.db.on("count(*) as n", {"n": mobile.MAX_ROUTES_PER_USER})
    assert post({"name": "x", "kind": "line", "line": "4"}).status_code == 409

    env.db.on("from favorite_routes where user_id", [route_row()])
    routes = env.client.get("/mobile/routes", headers=env.auth).json()["routes"]
    assert routes[0]["start"] == [21.0, 52.23] and routes[0]["end"] == [21.01, 52.229]

    assert env.client.delete("/mobile/routes/3", headers=env.auth).status_code == 404
    env.db.on("delete from favorite_routes", {"id": 3})
    assert env.client.delete("/mobile/routes/3", headers=env.auth).json() == {"ok": True}
    assert env.db.sql_with("delete from favorite_routes")[-1][1] == {"id": 3, "user_id": 1}


def test_route_quality_points_falls_back_to_straight_line(env, monkeypatch):
    def broken_get(*a, **kw):
        raise TimeoutError("OSRM down")

    import httpx
    monkeypatch.setattr(httpx, "get", broken_get)
    assert env.client.get("/mobile/routes/3/quality", headers=env.auth).status_code == 404
    env.db.on("from favorite_routes where id", route_row())
    env.db.on("ST_DWithin(s.geom::geography", [
        {"id": 1, "mode": "road", "health": 0.2, "geojson": '{"coordinates":[[21,52.23],[21.001,52.23]]}',
         "length_m": 25, "covered_m": 25, "along_m": 100, "lon": 21.0005, "lat": 52.23},
        {"id": 2, "mode": "road", "health": 0.9, "geojson": '{"coordinates":[[21,52.23],[21,52.231]]}',
         "length_m": 25, "covered_m": 2, "along_m": 120, "lon": 21.0, "lat": 52.2305}])  # cross street
    env.db.on("from incidents i, r", [{**incident_row(), "along_m": 50.04}])
    body = env.client.get("/mobile/routes/3/quality", headers=env.auth).json()
    assert body["path"] == [[21.0, 52.23], [21.01, 52.229]]
    assert [s["id"] for s in body["segments"]] == [1] and body["segments"][0]["health_class"] == "poor"
    assert body["summary"]["poor_m"] == 25.0 and body["summary"]["overall"] == "poor"
    assert [(w["kind"], w["distance_along_m"]) for w in body["warnings"]] == [("incident", 50.0), ("poor_road", 100.0)]
    assert body["warnings"][0]["message"] == "İleride yol hasarı: Marszałkowska"
    params = env.db.sql_with("ST_DWithin(s.geom::geography")[-1][1]
    assert params["mode"] == "road" and params["corridor"] == 30 and '"LineString"' in params["route"]
    inc_params = env.db.sql_with("from incidents i, r")[-1][1]
    assert inc_params["statuses"] == ["candidate", "likely", "verified"]


def test_route_quality_uses_osrm(env, monkeypatch):
    import httpx

    seen = {}

    def fake_get(url, params=None, timeout=None, headers=None):
        seen.update(url=url, params=params, timeout=timeout)
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {
            "routes": [{"geometry": {"coordinates": [[21.0, 52.23], [21.005, 52.23], [21.01, 52.229]]}}]})

    monkeypatch.setattr(httpx, "get", fake_get)
    env.db.on("from favorite_routes where id", route_row())
    body = env.client.get("/mobile/routes/3/quality", headers=env.auth).json()
    assert body["path"] == [[21.0, 52.23], [21.005, 52.23], [21.01, 52.229]]
    assert seen["url"].endswith("/route/v1/driving/21.0,52.23;21.01,52.229") and seen["timeout"] == 5
    assert seen["params"] == {"overview": "full", "geometries": "geojson"}
    assert body["summary"]["overall"] == "unknown" and body["warnings"] == []


def test_route_quality_line(env):
    env.db.on("from favorite_routes where id", route_row(kind="line", line="17", mode="tram", start_lon=None,
                                                         start_lat=None, end_lon=None, end_lat=None))
    body = env.client.get("/mobile/routes/3/quality", headers=env.auth).json()
    assert body["path"] == [] and body["segments"] == [] and body["summary"]["overall"] == "unknown"

    env.db.on("from ride_segments rs", [
        {"ride_id": 1, "segment_id": 10, "geojson": '{"coordinates":[[21,52],[21.001,52]]}'},
        {"ride_id": 1, "segment_id": 11, "geojson": '{"coordinates":[[21.002,52],[21.001,52]]}'},
        {"ride_id": 2, "segment_id": 12, "geojson": '{"coordinates":[[21,52.0001],[21.001,52.0001]]}'}])
    env.db.on("s.id = any", [{"id": 10, "mode": "tram", "health": 0.8, "geojson": '{"coordinates":[[21,52],[21.001,52]]}',
                              "length_m": 68, "covered_m": 68, "along_m": 34, "lon": 21.0005, "lat": 52}])
    body = env.client.get("/mobile/routes/3/quality", headers=env.auth).json()
    assert body["path"] == [[21.0, 52.0], [21.001, 52.0], [21.002, 52.0]]
    assert body["summary"]["overall"] == "good"
    assert env.db.sql_with("from ride_segments rs")[-1][1] == {"line": "17", "mode": "tram"}
    assert env.db.sql_with("s.id = any")[-1][1]["ids"] == [10, 11, 12]


# --------------------------------------------------------------------------- store.contributor_for_user

class FakeStoreDB:
    def __init__(self, users):
        self.users = users  # user_id -> contributor_id | None
        self.contributors: dict[str, int] = {}

    def fetch_one(self, conn, sql, params=None):
        p = params or {}
        if "insert into contributors" in sql:
            cid = self.contributors.setdefault(p["hash"], len(self.contributors) + 1)
            return {"id": cid, "trust": 0.6, "correct": 0, "incorrect": 0}
        if "join contributors c on c.id = u.contributor_id" in sql:
            cid = self.users.get(p["user_id"])
            return {"id": cid, "trust": 0.9, "correct": 5, "incorrect": 0} if cid else None
        if "update users set contributor_id" in sql:
            if p["user_id"] not in self.users or self.users[p["user_id"]] is not None \
                    or p["contributor_id"] in self.users.values():
                return None
            self.users[p["user_id"]] = p["contributor_id"]
            return {"contributor_id": p["contributor_id"]}
        raise AssertionError(sql)


@pytest.fixture
def store_db(monkeypatch):
    def make(users):
        fdb = FakeStoreDB(users)
        install(monkeypatch, "backend.db", fetch_one=fdb.fetch_one, fetch_all=lambda *a, **k: [])
        monkeypatch.setattr(trust_mod, "fetch_one", fdb.fetch_one)
        return fdb
    return make


def test_contributor_for_user(store_db):
    fdb = store_db({1: 7, 2: None, 3: None})
    assert store.contributor_for_user(None, 1)["id"] == 7  # already linked: reused

    row = store.contributor_for_user(None, 2, "device-token-1")  # links the device's contributor
    assert fdb.users[2] == row["id"] == fdb.contributors[trust_mod.contributor_hash("device-token-1")]

    row3 = store.contributor_for_user(None, 3, "device-token-1")  # owned by user 2 -> fresh random one
    assert fdb.users[3] == row3["id"] != fdb.users[2]

    with pytest.raises(LookupError):
        store.contributor_for_user(None, 99)


# --------------------------------------------------------------------------- real PostGIS (opt-in)

@pytest.mark.skipif(os.getenv("CITYECHO_TEST_DB") != "1", reason="set CITYECHO_TEST_DB=1 to run against PostGIS")
def test_mobile_sql_runs_on_postgis():
    """Every SQL statement of the mobile router parses and runs (inside a rolled-back transaction)."""
    import json

    import psycopg
    from psycopg.rows import dict_row

    from backend import db

    pt = {"lon": 21.0122, "lat": 52.2297}
    route = json.dumps({"type": "LineString", "coordinates": [[21.0, 52.23], [21.01, 52.229]]})
    with psycopg.connect(config.settings.database_url, row_factory=dict_row) as conn:
        try:
            user = db.fetch_one(conn, "insert into users (email) values ('mobile-sql-test@test.pl') returning id")
            uid = user["id"]
            cid = store.contributor_for_user(conn, uid)["id"]
            assert store.contributor_for_user(conn, uid)["id"] == cid
            db.fetch_all(conn, mobile.PUBLIC_SELECT + "where i.id = any(%(ids)s)", {"ids": [1, 2]})
            db.fetch_one(conn, mobile.MY_INCIDENT_SQL, {"id": 1, "user_id": uid})
            db.fetch_one(conn, mobile.QUESTION_SQL, {**pt, "radius": 25, "open": ["candidate", "likely"],
                                                     "user_id": uid, "exclude": [1, 2]})
            db.fetch_one(conn, mobile.QUESTION_SQL, {**pt, "radius": 25, "open": ["candidate", "likely"],
                                                     "user_id": uid, "exclude": []})
            db.fetch_one(conn, mobile.ANSWER_TARGET_SQL, {**pt, "id": 1})
            db.fetch_one(conn, mobile.ALREADY_ANSWERED_SQL, {"id": 1, "contributor_id": cid})
            db.fetch_all(conn, mobile.MY_REPORTS_SQL, {"user_id": uid, "limit": 10})
            assert db.fetch_one(conn, mobile.ME_SQL, {"user_id": uid})["reports_count"] == 0
            db.fetch_all(conn, mobile.SEGMENTS_SQL, {"min_lon": 20.9, "min_lat": 52.1, "max_lon": 21.2,
                                                     "max_lat": 52.3, "mode": None, "limit": 5})
            db.fetch_all(conn, mobile.LINES_SQL, {"mode": None})
            r = db.fetch_one(conn, mobile.ROUTE_INSERT_SQL, {"user_id": uid, "name": "t", "kind": "points",
                                                             "start_lon": 21.0, "start_lat": 52.23, "end_lon": 21.01,
                                                             "end_lat": 52.229, "line": None, "mode": None})
            assert mobile.route_json(r)["start"] == [21.0, 52.23]
            db.fetch_one(conn, mobile.ROUTE_SQL, {"id": r["id"], "user_id": uid})
            db.fetch_all(conn, mobile.ROUTES_SQL, {"user_id": uid})
            db.fetch_all(conn, mobile.CORRIDOR_SEGMENTS_SQL, {"route": route, "mode": "road", "corridor": 30})
            db.fetch_all(conn, mobile.LINE_SEGMENTS_SQL, {"route": route, "ids": [1, 2]})
            db.fetch_all(conn, mobile.LINE_RIDE_SEGMENTS_SQL, {"line": "17", "mode": None})
            db.fetch_all(conn, mobile.ROUTE_INCIDENTS_SQL, {"route": route, "corridor": 30,
                                                           "statuses": ["candidate", "likely", "verified"]})
            assert db.fetch_one(conn, mobile.ROUTE_DELETE_SQL, {"id": r["id"], "user_id": uid})
        finally:
            conn.rollback()
