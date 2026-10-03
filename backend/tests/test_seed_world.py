"""S6 mock world (scripts/seed_world.py, data/mock/): the plan is complete, consistent and deterministic.

No API needed: these tests check the plan the seeder would send. The end-to-end run is
`docker compose --profile mock run --rm mock` followed by `scripts/seed_world.py --check`.
"""
from __future__ import annotations

import io
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.append(str(SCRIPTS))
import gen_complaints as gc  # noqa: E402
import seed_world as sw  # noqa: E402
import simulate_buses as sim  # noqa: E402

NOW = datetime(2026, 10, 4, 10, 0, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def plan():
    return sw.build_plan(now=NOW, seed=2026, fast=False)


@pytest.fixture(scope="module")
def fast():
    return sw.build_plan(now=NOW, seed=2026, fast=True)


def test_plan_is_deterministic(plan):
    again = sw.build_plan(now=NOW, seed=2026, fast=False)
    assert again.complaints == plan.complaints
    assert [(r.device, r.trip, r.start) for r in again.rides] == [(r.device, r.trip, r.start) for r in plan.rides]


def test_history_is_in_the_past_and_in_order(plan):
    times = [datetime.fromisoformat(r["created_at"]) for r in plan.complaints]
    assert times == sorted(times) and max(times) < NOW
    assert min(times) > NOW - timedelta(days=plan.world["history_days"] + 1)
    starts = [r.start for r in plan.rides]
    assert starts == sorted(starts) and max(starts) <= NOW - timedelta(minutes=45)
    events = sw.timeline(plan)
    assert sum(len(x) for k, x in events if k == "reports") == len(plan.complaints)
    assert all(len(x) <= sw.REPORT_BATCH for k, x in events if k == "reports")
    assert sum(1 for k, _ in events if k == "ride") == len(plan.rides)


def test_sizes(plan, fast):
    assert len(plan.complaints) >= 300 and len(plan.rides) >= 40
    assert 50 <= len(fast.complaints) < len(plan.complaints) and len(fast.rides) < len(plan.rides)


def test_rides_use_known_devices_and_alternate_directions(plan):
    devices = {d for devs in plan.world["rides"]["devices"].values() for d in devs}
    assert {r.device for r in plan.rides + plan.final_rides} <= devices
    for dev in devices:
        trips = [r.trip for r in plan.rides + plan.final_rides if r.device == dev]
        assert trips == list(range(len(trips)))  # one trip counter per vehicle, no reuse


def test_stale_corridor_has_only_old_rides(plan):
    swi = [r for r in plan.rides + plan.final_rides if r.line == "SWI"]
    assert swi and all(r.start is not None and r.start < NOW - timedelta(days=9) for r in swi)
    for line in ("MAR", "JER"):
        assert any(r.start and r.start > NOW - timedelta(days=1) for r in plan.rides if r.line == line)


def test_final_rides_drive_without_the_repaired_defect(plan):
    repaired = {w["repairs_defect"] for w in plan.world["work"]["done"] if w.get("repairs_defect")}
    assert repaired and all(set(r.removed) == repaired for r in plan.final_rides)
    lines = {r.line for r in plan.final_rides}
    assert {fa["line"] for fa in plan.world["false_alarms"]} <= lines  # false alarms get clean passes
    for d in repaired:
        line = next(x["line"] for x in plan.defects if x["id"] == d)
        assert line in lines


def test_one_world_vehicles_confirm_the_complaints_they_pass(plan):
    """A pothole / track complaint a vehicle drives past must sit on a simulated defect, or the vehicle
    would count clean passes against real citizens (the old Świętokrzyska problem)."""
    routes = {("road", line): sim.route_for("road", line) for line in sim.BUS_LINES}
    routes[("tram", "17")] = sim.route_for("tram", "17")
    for issue_id, (lon, lat) in plan.centres.items():
        mode = sw.DETECTABLE.get(gc.SPOTS[issue_id - 1][3])
        if not mode or not any(r.locate(lon, lat)[1] <= sw.MATCH_M + 5 for (m, _), r in routes.items() if m == mode):
            continue
        nearest = min(sw.dist_m((d["lon"], d["lat"]), (lon, lat)) for d in plan.defects
                      if d["mode"] == mode and d["kind"] == "bump")
        assert nearest < 1.0, f"spot {issue_id} is passed by a {mode} line but has no defect"


def test_false_alarms_have_nothing_to_feel(plan):
    for fa in plan.world["false_alarms"]:
        at = (fa["lon"], fa["lat"])
        assert sim.route_for("road", fa["line"]).locate(*at)[1] < 1.0
        assert min(sw.dist_m((d["lon"], d["lat"]), at) for d in plan.defects) > 150
        assert min(sw.dist_m(c, at) for c in plan.centres.values()) > 100


def test_persona_plan_refers_to_real_places(plan, fast):
    keys = {p["key"] for p in plan.personas["personas"]}
    assert set(plan.world["answers"]) <= keys
    for p in plan.personas["personas"]:
        assert p["email"].endswith("@cityecho.test")
        for rep in p.get("reports", []):
            lon, lat = sw.target_of(rep["at"], plan)
            assert 20.9 < lon < 21.2 and 52.1 < lat < 52.3
    fast_spots = set(fast.world["fast_spots"])
    for item in plan.world["work"]["done"] + plan.world["work"]["in_progress"]:
        assert item["spot"] in fast_spots  # the city's work exists in --fast too
    spot_reports = {rep["at"]["spot"] for p in plan.personas["personas"] for rep in p.get("reports", []) if "spot" in rep["at"]}
    assert spot_reports <= fast_spots


def test_persona_answers_include_truthful_and_wrong(plan):
    policies = {p["key"]: p.get("answers") for p in plan.personas["personas"]}
    assert {policies[k] for k in plan.world["answers"]} == {"truthful", "wrong"}
    reporters = {p["key"]: {str(r["at"]) for r in p.get("reports", [])} for p in plan.personas["personas"]}
    for key, todo in plan.world["answers"].items():  # nobody answers about their own report
        own = reporters[key]
        assert not any(str({"spot": s}) in own for s in todo.get("spots", []))
        assert not any(str({"false_alarm": f}) in own for f in todo.get("false_alarms", []))


def test_stable_places_avoid_phrases_the_geocoder_moves():
    """No landmarks, no shop / stop names, no bare "on <street>": those geocode far from the citizen's pin."""
    import random

    risky_vague = [v for v in gc.VAGUE if v and v not in gc.STABLE_VAGUE]
    for issue_id, spot in enumerate(gc.SPOTS, start=1):
        rng = random.Random(issue_id)
        for _ in range(30):
            text = gc.template_text(spot, rng, rng.random() < 0.3, stable_places=True).lower()
            places = " ".join(spot[5][:2]).lower()
            assert not any(m.lower() in text for m in spot[6] if m.lower() not in places), text
            assert not any(v in text for v in risky_vague if v not in places), text
            assert f"on {spot[0].lower()}" not in text, text


def test_stable_places_never_garble_the_place_phrase():
    import random

    spot = gc.SPOTS[1]  # Marszałkowska x Świętokrzyska
    rng = random.Random(3)
    texts = [gc.template_text(spot, rng, False, stable_places=True).lower() for _ in range(200)]
    phrases = [p.lower() for p in spot[5][:2]]
    english = [t for t in texts if " here" in t]
    assert all(any(p in t for p in phrases) for t in texts if t not in english)


def test_default_generator_output_is_unchanged():
    """complaints_synth.json (A's triage evaluation) still comes from the old default path."""
    a = gc.generate(seed=7, now=NOW)
    b = gc.generate(seed=7, now=NOW, spots=dict(enumerate(gc.SPOTS, start=1)), window_days=gc.WINDOW_DAYS)
    assert a == b


@pytest.mark.parametrize("category", ["road_damage", "tram_track", "streetlight", "flooding", "waste", "other"])
def test_generated_photos_are_jpegs(category):
    from PIL import Image

    blob = sw.photo(category, 1)
    assert blob[:3] == b"\xff\xd8\xff" and 5_000 < len(blob) < 400_000
    assert Image.open(io.BytesIO(blob)).size == (640, 480)


def test_samples_are_back_dated_and_drop_missing_lux():
    arr = np.array([[0.0, 0, 0, 9.8, 52.2, 21.0, 20, math.nan], [0.01, 0, 0, 9.8, 52.2, 21.0, 20, 4.5]])
    start = NOW.timestamp() - 86400
    out = sw.samples_at(arr, start)
    assert out[0]["t"] == pytest.approx(start) and "lux" not in out[0] and out[1]["lux"] == 4.5


def test_multipart_body(monkeypatch):
    sent = {}

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout):
        sent.update(data=req.data, ctype=req.headers["Content-type"], auth=req.headers.get("Authorization"))
        return Resp(b'{"ok": true}')

    monkeypatch.setattr(sw.urllib.request, "urlopen", fake_urlopen)
    out = sw.Client("http://x").post("/mobile/reports", token="t", form={"text": "Dziura", "lon": 21.0},
                                     files={"photo": ("a.jpg", b"\xff\xd8JPEG", "image/jpeg")})
    assert out == {"ok": True} and sent["auth"] == "Bearer t"
    boundary = sent["ctype"].split("boundary=")[1]
    assert sent["data"].startswith(f"--{boundary}".encode()) and sent["data"].endswith(f"--{boundary}--\r\n".encode())
    assert b'name="text"\r\n\r\nDziura' in sent["data"] and b"\xff\xd8JPEG" in sent["data"]
