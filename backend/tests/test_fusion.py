"""Fusion engine tests: routing, score, ZTM parsing/fallback, ETA, vehicle choice, and the
incident / verification decision logic against a fake DB (no PostGIS, no network)."""
from __future__ import annotations

import dataclasses
import math
from datetime import datetime, timedelta, timezone

import pytest

from backend.fusion import confidence, incidents, trust, verify
from backend.fusion.routing import department_for
from backend.fusion.score import priority_score, score_breakdown
from backend.models import Department, IssueType

T0 = datetime(2026, 10, 1, 8, 0, tzinfo=timezone.utc)


class FakeDB:
    """Stands in for backend.db.fetch_one/fetch_all and conn.execute.

    `answers` maps a module SQL constant to a value or a callable(params) -> value.
    """

    def __init__(self, answers: dict | None = None):
        self.answers = answers or {}
        self.calls: list[tuple[str, dict | None]] = []

    def _answer(self, sql, params):
        self.calls.append((sql, params))
        ans = self.answers.get(sql)
        return ans(params) if callable(ans) else ans

    def fetch_one(self, conn, sql, params=None):
        return self._answer(sql, params)

    def fetch_all(self, conn, sql, params=None):
        return self._answer(sql, params) or []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))

    def executed(self, sql) -> list[dict | None]:
        return [p for s, p in self.calls if s is sql]


@pytest.fixture
def fake_db(monkeypatch):
    def install(answers):
        db = FakeDB(answers)
        for module in (incidents, verify, trust):
            monkeypatch.setattr(module, "fetch_one", db.fetch_one)
        for module in (verify, trust):
            monkeypatch.setattr(module, "fetch_all", db.fetch_all)
        return db
    return install


@pytest.fixture(autouse=True)
def clean_ztm_state():
    verify._CACHE.clear()
    verify._PREVIOUS.clear()
    yield
    verify._CACHE.clear()
    verify._PREVIOUS.clear()


# ---------------------------------------------------------------------------- routing


@pytest.mark.parametrize("issue_type, dept", [
    ("road_damage", "ZDM"), ("streetlight", "ZDM"), ("tram_track", "Tramwaje Warszawskie"),
    ("flooding", "MPWiK"), ("waste", "Straż Miejska"), ("other", "inne"), ("unknown_type", "inne"),
    (IssueType.TRAM_TRACK, Department.TRAMWAJE.value),
])
def test_routing_table(issue_type, dept):
    assert department_for(issue_type) == dept


# ---------------------------------------------------------------------------- score


def test_score_formula_terms():
    s = priority_score(sensor_severity=0.8, report_count=10, max_urgency=4, vulnerability=0.5, both_sources=False)
    expected = 0.35 * 0.8 + 0.25 * math.log(11) / math.log(51) + 0.20 * 4 / 5 + 0.20 * 0.5
    assert s == pytest.approx(expected, abs=1e-4)


def test_score_agreement_multiplier():
    kw = dict(sensor_severity=0.6, report_count=3, max_urgency=3, vulnerability=0.2)
    single = priority_score(**kw, both_sources=False)
    both = priority_score(**kw, both_sources=True)
    assert both == pytest.approx(single * 1.5, abs=1e-3)


def test_score_log_term_saturates_at_50_reports():
    b = score_breakdown(sensor_severity=0, report_count=50, max_urgency=0, vulnerability=0, both_sources=False)
    reports = next(t for t in b["terms"] if t["name"] == "reports")
    assert reports["points"] == pytest.approx(0.25, abs=1e-6)
    assert b["score"] == pytest.approx(0.25, abs=1e-6)
    many = priority_score(sensor_severity=0, report_count=5000, max_urgency=0, vulnerability=0, both_sources=False)
    assert many == pytest.approx(0.25, abs=1e-6)


def test_score_clamps_inputs_and_max_is_1_5():
    top = priority_score(sensor_severity=7, report_count=999, max_urgency=12, vulnerability=3, both_sources=True)
    assert top == pytest.approx(1.5)
    low = priority_score(sensor_severity=-1, report_count=-4, max_urgency=None, vulnerability=float("nan"),
                         both_sources=False)
    assert low == 0.0


def test_score_breakdown_shape():
    b = score_breakdown(sensor_severity=0.82, report_count=23, max_urgency=3, vulnerability=0.5, both_sources=True)
    assert [t["name"] for t in b["terms"]] == ["sensor_severity", "reports", "urgency", "vulnerability"]
    assert sum(t["weight"] for t in b["terms"]) == pytest.approx(1.0)
    assert b["multiplier"] == 1.5 and b["both_sources"] is True
    assert b["score"] == pytest.approx(b["base"] * 1.5, abs=1e-3)
    assert "log(51)" in b["formula"]


# ---------------------------------------------------------------------------- incident rules


def test_found_before_report():
    second_ride = T0 + timedelta(hours=1)
    assert incidents.found_before_report(2, second_ride, None) is True            # sensors only
    assert incidents.found_before_report(3, second_ride, T0 + timedelta(days=1)) is True
    assert incidents.found_before_report(2, second_ride, T0) is False             # citizen was first
    assert incidents.found_before_report(1, None, None) is False                  # one ride is not enough


def test_pick_address():
    assert incidents.pick_address("Marszałkowska", "near the Rotunda") == "Marszałkowska"
    assert incidents.pick_address(None, "Rondo Dmowskiego") == "Rondo Dmowskiego"
    assert incidents.pick_address(None, "  ", "kept") == "kept"
    assert incidents.pick_address(None, None) is None


# ---------------------------------------------------------------------------- ingest_evidence


def test_ingest_evidence_matching_paths(fake_db, monkeypatch):
    evidence = {
        1: {"id": 1, "source": "report", "type": "road_damage", "ts": T0, "duplicate_of": 10, "linked_incident_id": None,
            "report_id": 31},
        2: {"id": 2, "source": "sensor", "type": "road_damage", "ts": T0, "duplicate_of": None, "linked_incident_id": None},
        3: {"id": 3, "source": "sensor", "type": "tram_track", "ts": T0, "duplicate_of": None, "linked_incident_id": None},
        4: {"id": 4, "source": "sensor", "type": "road_damage", "ts": T0, "duplicate_of": None, "linked_incident_id": 7},
    }
    db = fake_db({
        incidents.SQL_EVIDENCE: lambda p: evidence.get(p["id"]),
        incidents.SQL_CANONICAL_INCIDENT: lambda p: {"incident_id": 5} if p["report_id"] == 10 else None,
        incidents.SQL_NEAREST_INCIDENT: lambda p: {"id": 7} if p["evidence_id"] == 2 else None,
        incidents.SQL_CREATE_INCIDENT: {"id": 9},
    })
    refreshed = []
    monkeypatch.setattr(incidents, "refresh_incident", lambda conn, iid: refreshed.append(iid) or {})

    touched = incidents.ingest_evidence(db, [1, 2, 3, 4, 99])

    assert touched == [5, 7, 9]
    assert refreshed == [5, 7, 9]
    links = db.executed(incidents.SQL_LINK)
    assert [(p["incident_id"], p["evidence_id"]) for p in links] == [(5, 1), (7, 2), (9, 3)]  # 4 already linked
    create = db.executed(incidents.SQL_CREATE_INCIDENT)
    assert create == [{"evidence_id": 3, "department": "Tramwaje Warszawskie"}]
    nearest = db.executed(incidents.SQL_NEAREST_INCIDENT)[0]
    assert nearest["radius_m"] == 40 and nearest["window_days"] == 7
    # the anonymous report became a YES answer on its incident (no contributor -> anon insert)
    assert db.executed(trust.SQL_REPORT_YES_ANON) == [{"incident_id": 5, "report_id": 31, "contributor_id": None}]


def test_ingest_duplicate_falls_back_to_spatial_match(fake_db, monkeypatch):
    ev = {"id": 1, "source": "report", "type": "waste", "ts": T0, "duplicate_of": 10, "linked_incident_id": None}
    db = fake_db({
        incidents.SQL_EVIDENCE: ev,
        incidents.SQL_CANONICAL_INCIDENT: None,     # canonical report not located / its incident closed
        incidents.SQL_NEAREST_INCIDENT: {"id": 3},
    })
    monkeypatch.setattr(incidents, "refresh_incident", lambda conn, iid: {})
    assert incidents.ingest_evidence(db, [1]) == [3]


# ---------------------------------------------------------------------------- refresh_incident


def _refresh(fake_db, context, aggregate, votes=()):
    db = fake_db({
        incidents.SQL_INCIDENT_CONTEXT: context,
        incidents.SQL_AGGREGATE: aggregate,
        incidents.SQL_UPDATE: lambda p: dict(p),
        trust.SQL_VOTES: [{"answer": yes, "trust": t} for yes, t in votes],
    })
    return db, incidents.refresh_incident(db, context["id"])


def test_refresh_verifies_when_sensor_agrees_with_reports(fake_db):
    """The verification loop: 23 citizen YES (likely) + one tram detection -> verified, trust settled."""
    context = {"id": 3, "type": "road_damage", "status": "likely", "address": None, "sensor_misses": 0,
               "segment_name": "Marszałkowska", "vulnerability": 0.5}
    aggregate = {"report_count": 23, "sensor_count": 2, "sensor_rides": 1, "max_severity": 0.82, "max_urgency": 3,
                 "first_seen": T0, "last_seen": T0 + timedelta(hours=5), "first_report_ts": T0,
                 "nth_ride_ts": None, "location_text": "Marszałkowska 100", "ride_severities": [0.82]}
    db, row = _refresh(fake_db, context, aggregate, votes=[(True, 0.6)] * 23)
    assert row["status"] == "verified"
    assert row["confidence"] == pytest.approx(confidence.assess([0.82], 0, [(True, 0.6)] * 23).confidence, abs=1e-4)
    assert row["confidence"] > confidence.VERIFIED_AT
    assert row["yes_count"] == 23 and row["no_count"] == 0
    assert row["sensor_confirmed"] is True and row["found_before_report"] is False
    assert row["department"] == "ZDM" and row["address"] == "Marszałkowska"
    assert row["score"] == priority_score(sensor_severity=0.82, report_count=23, max_urgency=3,
                                          vulnerability=0.5, both_sources=True)
    assert db.executed(incidents.SQL_AGGREGATE)[0]["nth_offset"] == 1
    assert db.executed(trust.SQL_SETTLE)[0]["real"] is True        # contributor trust updated


def test_refresh_sensor_only_two_rides_is_proactive_and_likely(fake_db):
    context = {"id": 4, "type": "tram_track", "status": "candidate", "address": None, "sensor_misses": 0,
               "segment_name": None, "vulnerability": 0.0}
    aggregate = {"report_count": 0, "sensor_count": 3, "sensor_rides": 2, "max_severity": 0.7, "max_urgency": 0,
                 "first_seen": T0, "last_seen": T0 + timedelta(days=1), "first_report_ts": None,
                 "nth_ride_ts": T0 + timedelta(days=1), "location_text": None, "ride_severities": [0.7, 0.6]}
    db, row = _refresh(fake_db, context, aggregate)
    assert row["status"] == "likely" and row["found_before_report"] is True
    assert row["citizen_confidence"] is None and row["sensor_confidence"] == pytest.approx(row["confidence"])
    assert row["department"] == "Tramwaje Warszawskie" and row["address"] is None
    assert row["score"] == pytest.approx(0.35 * 0.7)
    assert db.executed(trust.SQL_SETTLE) == []


def test_refresh_report_only_uses_location_text(fake_db):
    context = {"id": 5, "type": "flooding", "status": "candidate", "address": None, "sensor_misses": 0,
               "segment_name": None, "vulnerability": 0.2}
    aggregate = {"report_count": 2, "sensor_count": 0, "sensor_rides": 0, "max_severity": 0, "max_urgency": 4,
                 "first_seen": T0, "last_seen": T0, "first_report_ts": T0, "nth_ride_ts": None,
                 "location_text": "Plac Zbawiciela", "ride_severities": None}
    _, row = _refresh(fake_db, context, aggregate, votes=[(True, 0.6), (True, 0.6)])
    assert row["status"] == "candidate" and row["sensor_confirmed"] is False
    assert row["sensor_confidence"] is None and row["citizen_confidence"] == pytest.approx(row["confidence"])
    assert row["address"] == "Plac Zbawiciela" and row["department"] == "MPWiK"


def test_refresh_dismisses_after_clean_passes_and_settles_trust(fake_db):
    context = {"id": 6, "type": "road_damage", "status": "candidate", "address": None, "sensor_misses": 5,
               "segment_name": None, "vulnerability": 0.0}
    aggregate = {"report_count": 1, "sensor_count": 0, "sensor_rides": 0, "max_severity": 0, "max_urgency": 2,
                 "first_seen": T0, "last_seen": T0, "first_report_ts": T0, "nth_ride_ts": None,
                 "location_text": None, "ride_severities": None}
    db, row = _refresh(fake_db, context, aggregate, votes=[(True, 0.6)])
    assert row["status"] == "dismissed" and row["confidence"] < confidence.DISMISSED_BELOW
    assert db.executed(trust.SQL_SETTLE)[0]["real"] is False


def test_refresh_terminal_status_is_sticky(fake_db):
    context = {"id": 7, "type": "road_damage", "status": "verified", "address": None, "sensor_misses": 9,
               "segment_name": None, "vulnerability": 0.0}
    aggregate = {"report_count": 1, "sensor_count": 0, "sensor_rides": 0, "max_severity": 0, "max_urgency": 2,
                 "first_seen": T0, "last_seen": T0, "first_report_ts": T0, "nth_ride_ts": None,
                 "location_text": None, "ride_severities": None}
    db, row = _refresh(fake_db, context, aggregate, votes=[(True, 0.6)])
    assert row["status"] == "verified"
    assert db.executed(trust.SQL_SETTLE) == []          # settled once, when it first became verified


def test_refresh_missing_incident_raises(fake_db):
    db = fake_db({incidents.SQL_INCIDENT_CONTEXT: None})
    with pytest.raises(LookupError):
        incidents.refresh_incident(db, 404)


# ---------------------------------------------------------------------------- ZTM parsing


def _ztm(line, lon, lat, number, when: datetime):
    local = when.astimezone(verify._WARSAW_TZ).strftime("%Y-%m-%d %H:%M:%S")
    return {"Lines": line, "Lon": lon, "Lat": lat, "VehicleNumber": number, "Brigade": "3", "Time": local}


def test_parse_ztm_list_filters_stale_and_outside_warsaw():
    now = datetime(2026, 10, 2, 10, 0, tzinfo=timezone.utc)
    payload = {"result": [
        _ztm("17", 21.0115, 52.2310, "3112", now - timedelta(seconds=20)),
        _ztm("4", 21.0087, 52.2353, "3018", now - timedelta(minutes=10)),    # stale
        _ztm("18", 19.94, 50.06, "3304", now),                               # Kraków, outside Warsaw
        {"Lines": "15", "Lon": "bad", "Lat": 52.2, "VehicleNumber": "1", "Time": "x"},  # malformed
    ]}
    vehicles = verify.parse_ztm(payload, "tram", now=now)
    assert len(vehicles) == 1
    v = vehicles[0]
    assert (v["id"], v["line"], v["kind"]) == ("3112", "17", "tram")
    assert v["ts"] == now - timedelta(seconds=20) and v["ts"].tzinfo is not None


def test_parse_ztm_time_is_warsaw_local():
    v = verify.parse_ztm({"result": [{"Lines": "17", "Lon": 21.01, "Lat": 52.23, "VehicleNumber": "1",
                                      "Time": "2026-10-02 12:00:00"}]}, "tram")[0]
    assert v["ts"] == datetime(2026, 10, 2, 10, 0, tzinfo=timezone.utc)  # CEST = UTC+2


def test_parse_ztm_string_result_raises():
    with pytest.raises(ValueError):
        verify.parse_ztm({"result": "Błędna metoda lub parametry wywołania"}, "tram")


def _live_settings(monkeypatch):
    monkeypatch.setattr(verify, "settings", dataclasses.replace(verify.settings, demo_mode=False,
                                                                warsaw_api_key="test-key"))


def test_live_vehicles_string_error_falls_back_to_sample(monkeypatch):
    _live_settings(monkeypatch)
    monkeypatch.setattr(verify, "_fetch_ztm", lambda kind: {"result": "Błędna metoda lub parametry wywołania"})
    trams = verify.live_vehicles("tram")
    assert len(trams) >= 10 and all(v["kind"] == "tram" for v in trams)
    assert {"4", "15", "17", "18", "35"} <= {v["line"] for v in trams}
    assert verify._CACHE["tram"][1] == "sample" and verify._PREVIOUS["tram"]  # sample carries a previous frame
    buses = verify.live_vehicles("bus")
    assert buses and all(v["kind"] == "bus" for v in buses)


def test_live_vehicles_network_error_falls_back(monkeypatch):
    _live_settings(monkeypatch)

    def boom(kind):
        raise verify.httpx.ConnectTimeout("offline")
    monkeypatch.setattr(verify, "_fetch_ztm", boom)
    assert verify.live_vehicles("tram")


def test_live_vehicles_uses_live_data_cache_and_previous(monkeypatch):
    _live_settings(monkeypatch)
    calls = []

    def fetch(kind):
        calls.append(kind)
        lat = 52.2300 + 0.001 * len(calls)
        return {"result": [_ztm("17", 21.01, lat, "3112", datetime.now(timezone.utc))]}
    monkeypatch.setattr(verify, "_fetch_ztm", fetch)

    first = verify.live_vehicles("tram")
    assert [v["line"] for v in first] == ["17"] and verify._CACHE["tram"][1] == "live"
    verify.live_vehicles("tram")
    assert calls == ["tram"]                                   # second call served from the 30 s cache
    stamp, source, vehicles = verify._CACHE["tram"]
    verify._CACHE["tram"] = (stamp - verify.CACHE_TTL_S - 1, source, vehicles)  # expire it
    verify.live_vehicles("tram")
    assert calls == ["tram", "tram"]
    assert verify._PREVIOUS["tram"]["3112"] == (21.01, pytest.approx(52.231))


def test_live_vehicles_demo_mode_never_calls_api(monkeypatch):
    monkeypatch.setattr(verify, "settings", dataclasses.replace(verify.settings, demo_mode=True,
                                                                warsaw_api_key="test-key"))
    monkeypatch.setattr(verify, "_fetch_ztm", lambda kind: pytest.fail("network call in demo mode"))
    assert verify.live_vehicles("tram")


def test_snapshot_is_labelled_sample_inside_warsaw():
    data = verify.json.loads(verify.SNAPSHOT_PATH.read_text(encoding="utf-8"))
    assert "SAMPLE" in data["_comment"]
    vehicles, previous = verify.load_snapshot("tram")
    buses, _ = verify.load_snapshot("bus")
    assert 20 <= len(vehicles) + len(buses) <= 30 and previous


# ---------------------------------------------------------------------------- ETA + vehicle choice


def test_eta_math():
    assert verify.eta_minutes(1000, "tram") == 5     # 1300 m / 5 m/s = 260 s -> 4.33 -> 5
    assert verify.eta_minutes(2000, "bus") == 8      # 2600 m / 5.56 m/s = 468 s -> 7.8 -> 8
    assert verify.eta_minutes(10, "tram") == 1       # minimum one minute
    assert verify.eta_minutes(0, "bus") == 1
    assert verify.eta_minutes(1384.6153846, "tram") == 6  # exactly 6.0 min stays 6


def _offset(lon, lat, north_m=0.0):
    return lon, lat + north_m / 111_320.0


def test_next_vehicle_prefers_nearest_approaching_tram(monkeypatch):
    lon, lat = 21.0115, 52.2310
    vehicles = [
        {"id": "A", "line": "4", "kind": "tram", "lon": lon, "lat": _offset(lon, lat, 300)[1], "ts": T0},   # nearest, receding
        {"id": "B", "line": "17", "kind": "tram", "lon": lon, "lat": _offset(lon, lat, 900)[1], "ts": T0},  # approaching
        {"id": "C", "line": "18", "kind": "tram", "lon": lon, "lat": _offset(lon, lat, 1500)[1], "ts": T0}, # approaching, farther
        {"id": "D", "line": "35", "kind": "tram", "lon": lon, "lat": _offset(lon, lat, 5000)[1], "ts": T0}, # > 3 km
        {"id": "E", "line": "175", "kind": "bus", "lon": lon, "lat": _offset(lon, lat, 50)[1], "ts": T0},   # wrong kind
    ]
    monkeypatch.setattr(verify, "live_vehicles", lambda kind: vehicles)
    monkeypatch.setattr(verify, "gtfs_lines_near", lambda *a, **k: None)
    verify._PREVIOUS["tram"] = {
        "A": (lon, _offset(lon, lat, 150)[1]),
        "B": (lon, _offset(lon, lat, 1050)[1]),
        "C": (lon, _offset(lon, lat, 1650)[1]),
    }
    best = verify.next_vehicle_for(lon, lat, "tram")
    assert best["vehicle"] == "tram 17" and best["line"] == "17" and best["approaching"] is True
    assert best["distance_m"] == pytest.approx(900, abs=2)
    assert best["eta_min"] == verify.eta_minutes(best["distance_m"], "tram") == 4

    verify._PREVIOUS["tram"] = {}                                   # heading unknown -> nearest
    assert verify.next_vehicle_for(lon, lat, "tram")["line"] == "4"
    assert verify.next_vehicle_for(lon, lat, "road")["vehicle"] == "bus 175"
    assert verify.next_vehicle_for(21.20, 52.15, "tram") is None   # nothing within 3 km


def test_next_vehicle_respects_gtfs_lines(monkeypatch):
    lon, lat = 21.0115, 52.2310
    vehicles = [{"id": "A", "line": "4", "kind": "tram", "lon": lon, "lat": lat + 0.002, "ts": T0},
                {"id": "B", "line": "17", "kind": "tram", "lon": lon, "lat": lat + 0.008, "ts": T0}]
    monkeypatch.setattr(verify, "live_vehicles", lambda kind: vehicles)
    monkeypatch.setattr(verify, "gtfs_lines_near", lambda *a, **k: {"17"})
    assert verify.next_vehicle_for(lon, lat, "tram")["line"] == "17"


def test_next_vehicle_with_sample_snapshot(monkeypatch):
    monkeypatch.setattr(verify, "settings", dataclasses.replace(verify.settings, demo_mode=True))
    monkeypatch.setattr(verify, "gtfs_lines_near", lambda *a, **k: None)
    best = verify.next_vehicle_for(21.0115, 52.2310, "tram")      # Marszałkowska x Al. Jerozolimskie
    assert best is not None and best["vehicle"].startswith("tram ") and best["eta_min"] >= 1


def test_gtfs_lines_near_with_tiny_feed(tmp_path, monkeypatch):
    (tmp_path / "routes.txt").write_text("route_id,route_short_name,route_type\nR17,17,0\nR4,4,0\nR175,175,3\n")
    (tmp_path / "trips.txt").write_text("route_id,service_id,trip_id,shape_id\nR17,s,t1,S1\nR4,s,t2,S2\nR175,s,t3,S1\n")
    (tmp_path / "shapes.txt").write_text(
        "shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence\n"
        "S1,52.2400,21.0115,1\nS1,52.2200,21.0115,2\n"       # north-south through the point
        "S2,52.2400,21.0300,1\nS2,52.2200,21.0300,2\n"       # ~1.3 km east
    )
    monkeypatch.setattr(verify, "GTFS_DIR", tmp_path)
    verify._gtfs_index.cache_clear()
    try:
        assert verify.gtfs_lines_near(21.0116, 52.2310, "tram") == {"17"}
        assert verify.gtfs_lines_near(21.0116, 52.2310, "bus") == {"175"}
        assert verify.gtfs_lines_near(21.0500, 52.2310, "tram") is None
    finally:
        verify._gtfs_index.cache_clear()


# ---------------------------------------------------------------------------- verification decisions


def test_verification_mode_and_eligibility():
    assert verify.verification_mode("tram_track", "road") == "tram"
    assert verify.verification_mode("road_damage", "tram") == "tram"
    assert verify.verification_mode("road_damage", "road") == "road"
    assert verify.verification_mode("streetlight", None) == "road"
    assert verify.can_request_verification("candidate", False) is True
    assert verify.can_request_verification("likely", False) is True
    assert verify.can_request_verification("candidate", True) is False
    for resolved in ("verified", "dismissed", "closed"):
        assert verify.can_request_verification(resolved, False) is False


def test_request_verification_report_only(fake_db, monkeypatch):
    db = fake_db({verify.SQL_VERIFY_CONTEXT: {"id": 3, "type": "tram_track", "status": "likely", "lon": 21.01,
                                              "lat": 52.23, "segment_mode": "road", "has_sensor": False}})
    asked = []

    def fake_next(lon, lat, mode):
        asked.append(mode)
        return {"vehicle": "tram 17", "line": "17", "eta_min": 6, "distance_m": 1500.0}
    monkeypatch.setattr(verify, "next_vehicle_for", fake_next)

    out = verify.request_verification(db, 3)
    assert out == {"incident_id": 3, "status": "likely", "vehicle": "tram 17", "eta_min": 6}
    assert asked == ["tram"]
    assert db.executed(verify.SQL_SET_VERIFY_REQUEST) == [{"id": 3, "vehicle": "tram 17", "eta_min": 6}]


def test_request_verification_skips_sensor_backed_and_no_vehicle(fake_db, monkeypatch):
    ctx = {"id": 4, "type": "road_damage", "status": "candidate", "lon": 21.01, "lat": 52.23,
           "segment_mode": "road", "has_sensor": True}
    db = fake_db({verify.SQL_VERIFY_CONTEXT: ctx})
    monkeypatch.setattr(verify, "next_vehicle_for", lambda *a: pytest.fail("should not look for a vehicle"))
    assert verify.request_verification(db, 4) is None

    ctx.update(has_sensor=False)
    monkeypatch.setattr(verify, "next_vehicle_for", lambda *a: None)
    assert verify.request_verification(db, 4) is None
    assert db.executed(verify.SQL_SET_VERIFY_REQUEST) == []

    db = fake_db({verify.SQL_VERIFY_CONTEXT: None})
    assert verify.request_verification(db, 404) is None


@pytest.mark.parametrize("status, issue_type, ride_mode, detected, expected", [
    ("likely", "road_damage", "road", True, "hit"),
    ("verified", "road_damage", "road", True, "hit"),       # extra sensor evidence still counts
    ("candidate", "road_damage", "road", False, "miss"),    # a bus drove over it and felt nothing
    ("candidate", "tram_track", "tram", False, "miss"),
    ("candidate", "road_damage", "tram", False, None),      # a tram cannot feel a road pothole
    ("likely", "streetlight", "road", False, None),         # lamps only show up on night rides
    ("likely", "flooding", "road", False, None),
    ("verified", "road_damage", "road", False, None),       # terminal: misses no longer matter
    ("dismissed", "road_damage", "road", True, None),
    ("closed", "tram_track", "tram", True, None),
])
def test_ride_outcome_rules(status, issue_type, ride_mode, detected, expected):
    assert verify.ride_outcome(status, issue_type, ride_mode, detected) == expected


def test_check_ride_verifications(fake_db, monkeypatch):
    rows = [
        {"id": 1, "type": "road_damage", "status": "likely", "ride_mode": "road", "detected": True},
        {"id": 2, "type": "road_damage", "status": "candidate", "ride_mode": "road", "detected": False},
        {"id": 3, "type": "road_damage", "status": "candidate", "ride_mode": "road", "detected": True},
        {"id": 4, "type": "streetlight", "status": "candidate", "ride_mode": "road", "detected": False},
    ]
    db = fake_db({verify.SQL_RIDE_CANDIDATES: rows})
    refreshed = []
    after = {1: "verified", 2: "candidate", 3: "likely"}
    monkeypatch.setattr(verify, "refresh_incident",
                        lambda conn, iid: refreshed.append(iid) or {"id": iid, "status": after[iid]})

    assert verify.check_ride_verifications(db, 42) == [1]      # only hits that are now verified
    assert refreshed == [1, 2, 3]                              # hits and misses are re-assessed
    assert db.executed(verify.SQL_SENSOR_MISS) == [{"id": 2}]
    assert db.executed(verify.SQL_RIDE_CANDIDATES) == [{"ride_id": 42, "radius_m": 40}]
