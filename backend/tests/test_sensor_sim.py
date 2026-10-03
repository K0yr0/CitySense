"""Sensor simulator (scripts/simulate_buses.py): routes, fixed world, per-vehicle worlds, streaming.

No PostGIS or API needed: routes come from data/osm/segments_demo.geojson, streaming uses a fake post.
"""
from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.append(str(SCRIPTS))
import simulate_buses as sim  # noqa: E402
import synth_ride as synth  # noqa: E402

from backend.sensor.detect import detect_bumps  # noqa: E402


@pytest.fixture(scope="module")
def world():
    return sim.load_world()["defects"]


@pytest.mark.parametrize("line", sorted(sim.BUS_LINES))
def test_bus_routes_follow_their_street(line):
    route = sim.route_for("road", line)
    spec = sim.BUS_LINES[line]
    assert route.mode == "road" and route.names == [s[0] for s in spec["stops"]]
    assert 1000 < route.length < 5000
    # every stop is on the route (stops are graph nodes of the street, rounded to ~10 m)
    for _, lon, lat in spec["stops"]:
        assert route.locate(lon, lat)[1] < 15


def test_reverse_route_is_the_same_path_backwards():
    fwd, rev = sim.route_for("road", "MAR"), sim.route_for("road", "MAR", reverse=True)
    assert rev.length == pytest.approx(fwd.length)
    assert rev.names == fwd.names[::-1]
    assert (rev.lon[0], rev.lat[0]) == (fwd.lon[-1], fwd.lat[-1])


def test_world_file_is_current(world):
    """data/demo/sim_world.json is the ground truth; it must match make_world() (run --make-world)."""
    assert world == sim.make_world()["defects"]
    ids = [d["id"] for d in world]
    assert len(ids) == len(set(ids))
    assert {(d["mode"], d["kind"]) for d in world} == {("road", "bump"), ("road", "dark_lamp"),
                                                       ("tram", "bump"), ("tram", "dark_lamp")}


def test_vehicles_only_feel_defects_of_their_mode_and_street(world):
    _, tram = sim.vehicle_world(sim.route_for("tram", "17"), world)
    _, mar = sim.vehicle_world(sim.route_for("road", "MAR"), world)
    by_id = {d["id"]: d for d in world}
    assert tram and all(by_id[p["id"]]["mode"] == "tram" for p in tram)
    assert mar and all(by_id[p["id"]]["line"] == "MAR" for p in mar)
    # Marszałkowska potholes sit ~20 m beside the tram tracks: the tram never drives over them
    assert not {p["id"] for p in tram} & {p["id"] for p in mar}


def test_shared_world_across_lines_on_the_same_street():
    route = sim.route_for("road", "MAR")
    lon, lat = route.at(route.length / 2)
    pothole = {"id": "X1", "kind": "bump", "mode": "road", "lon": float(lon), "lat": float(lat), "amp": 7, "freq": 8}
    far = {**pothole, "id": "X2", "lat": float(lat) + 0.001}  # ~110 m off the street
    w, passed = sim.vehicle_world(route, [pothole, far])
    assert [p["id"] for p in passed] == ["X1"]
    assert len(w["bumps"]) == 1 and w["bumps"][0][0] == pytest.approx(route.length / 2, abs=1.0)


@pytest.mark.parametrize("mode,line", [("tram", "17"), ("road", "SWI")])
def test_return_trip_hits_the_same_places(world, mode, line):
    fwd_world, fwd = sim.vehicle_world(sim.route_for(mode, line), world)
    rev_route = sim.route_for(mode, line, reverse=True)
    rev_world, rev = sim.vehicle_world(rev_route, world)
    assert sorted(p["id"] for p in fwd) == sorted(p["id"] for p in rev)
    fwd_route = sim.route_for(mode, line)
    fwd_pts = sorted(tuple(map(float, fwd_route.at(s))) for s, _, _ in fwd_world["bumps"])
    rev_pts = sorted(tuple(map(float, rev_route.at(s))) for s, _, _ in rev_world["bumps"])
    np.testing.assert_allclose(fwd_pts, rev_pts, atol=2e-5)  # same coordinates, ~2 m


def test_tram_17_forward_world_is_the_demo_world():
    route = synth.Route("17")
    w, _ = sim.vehicle_world(sim.route_for("tram", "17"), [])
    assert w["bumps"] == sorted(synth._world(route, 6)["bumps"])


def test_parse_device():
    assert sim.parse_device("bus-MAR-01") == ("road", "MAR")
    assert sim.parse_device("tram-17-02") == ("tram", "17")
    assert sim.parse_device("bus-999-01") is None
    assert sim.parse_device("tram-MAR-01") is None
    assert sim.parse_device("bus") is None
    vehicles = sim.fleet({"bus-SWI-01": "a", "nope": "b", "tram-17-01": "c"}, None)
    assert [v[:4] for v in vehicles] == [("bus-SWI-01", "a", "road", "SWI"), ("tram-17-01", "c", "tram", "17")]
    assert sim.fleet({"bus-SWI-01": "a", "tram-17-01": "c"}, ["tram-17-01"])[0][0] == "tram-17-01"


def test_ride_seeds_differ_per_device_and_trip():
    seeds = {sim.ride_seed(1, d, t) for d in ("bus-MAR-01", "bus-MAR-02") for t in range(3)}
    assert len(seeds) == 6 and sim.ride_seed(1, "bus-MAR-01", 0) == sim.ride_seed(1, "bus-MAR-01", 0)


def test_bus_ride_detects_the_potholes_it_passed(world):
    df, passed, _ = sim.build_ride("bus-SWI-01", "road", "SWI", 1, seed=3, night=False, defects=world)
    truth = pd.DataFrame([p for p in passed if p["kind"] == "bump"]).assign(kind="bump")
    assert len(truth) == 3 and not any(p["kind"] == "dark_lamp" for p in passed)  # lamps: night only
    score = synth.score_detections(detect_bumps(df), truth)
    assert score["recall"] == 1.0 and score["precision"] == 1.0


def test_stream_ride_chunks_and_final(monkeypatch):
    sent = []

    def fake_post(api, key, body, **kw):
        sent.append((key, body["vehicle_line"], body["mode"], len(body["samples"]), body["final"]))
        return {"ride_id": 1} if body["final"] else {"buffered": 0}

    monkeypatch.setattr(sim, "post_chunk", fake_post)
    samples = [{"t": i / 100} for i in range(2500)]
    res = sim.stream_ride("http://x", "bus-SWI-01:k", "SWI", "road", samples,
                          chunk_s=10, speed=0, stop=threading.Event())
    assert res == {"ride_id": 1}
    assert [s[3:] for s in sent] == [(1000, False), (1000, False), (500, True)]
    assert {s[:3] for s in sent} == {("bus-SWI-01:k", "SWI", "road")}


def test_to_samples_drops_nan_lux():
    df = pd.DataFrame({"t": [0.0, 0.01], "ax": [0, 0], "ay": [0, 0], "az": [9.8, 9.8], "lat": [52.2, 52.2],
                       "lon": [21.0, 21.0], "speed_kmh": [20, 20], "lux": [np.nan, 5.0]})
    out = sim.to_samples(df)
    assert "lux" not in out[0] and out[1]["lux"] == 5.0
    json.dumps(out)  # JSON-serializable


def test_world_on_route_ignores_off_route_and_keeps_lamps_regular():
    route = synth.Route("17")
    lon, lat = route.at(500.0)
    w = synth.world_on_route(route, [{"kind": "dark_lamp", "lon": lon, "lat": lat},
                                     {"kind": "bump", "lon": lon + 0.01, "lat": lat, "amp": 5, "freq": 8}])
    assert w["bumps"] == [] and len(w["broken"]) == 1
    k = w["broken"][0]
    assert w["lamps"][k] == pytest.approx(500.0, abs=0.5)
    assert np.all(np.diff(np.sort(w["lamps"])) > 15)  # the broken lamp replaced its neighbour, no doubling


# --------------------------------------------------------------------------- S4: recording conditions + accuracy sweep

def test_default_conditions_reproduce_the_demo_ride():
    a, _ = synth.generate_ride(seed=4, bumps=2)
    b, _ = synth.generate_ride(seed=4, bumps=2, conditions={"noise": 1.0, "speed": 1.0, "pose": "random", "gps_m": 2.5})
    pd.testing.assert_frame_equal(a, b)


def test_pose_conditions():
    flat, _ = synth.generate_ride(seed=4, bumps=0, conditions={"pose": "flat"})
    upright, _ = synth.generate_ride(seed=4, bumps=0, conditions={"pose": "upright"})
    assert abs(flat["az"].mean()) == pytest.approx(9.81, abs=0.1)        # gravity on the screen normal
    assert abs(upright["ay"].mean()) == pytest.approx(9.81, abs=0.1)     # gravity along the long side
    assert abs(upright["az"].mean()) < 0.5
    with pytest.raises(ValueError):
        synth.generate_ride(seed=4, bumps=0, conditions={"pose": "sideways"})


def test_noise_and_gps_conditions_change_the_signal():
    base, _ = synth.generate_ride(seed=4, bumps=0)
    noisy, _ = synth.generate_ride(seed=4, bumps=0, conditions={"noise": 3.0})
    gps, _ = synth.generate_ride(seed=4, bumps=0, conditions={"gps_m": 10.0})
    assert noisy["az"].std() > 1.5 * base["az"].std()
    route = synth.Route("17")
    off = lambda df: np.median([route.locate(lo, la)[1] for lo, la in zip(df["lon"][::500], df["lat"][::500])])
    assert off(gps) > 2 * off(base)


def test_match_counts():
    truth = [{"lon": 21.0, "lat": 52.2}, {"lon": 21.01, "lat": 52.2}]
    found = pd.DataFrame({"lon": [21.0, 21.0001, 21.02], "lat": [52.2, 52.2, 52.2]})  # two near truth[0], one far
    assert sim.match_counts(found, truth, 20) == {"tp": 2, "fp": 1, "hit": 1, "miss": 1}
    assert sim.match_counts(found.iloc[:0], truth, 20) == {"tp": 0, "fp": 0, "hit": 0, "miss": 2}
    assert sim.match_counts(found, [], 20) == {"tp": 0, "fp": 3, "hit": 0, "miss": 0}


def test_eval_ride_and_report(world, tmp_path):
    row = sim.eval_ride(("baseline", {}, ("bus-SWI-01", "road", "SWI"), 0, 1000, world))
    assert row["condition"] == "baseline" and row["mode"] == "road"
    assert row["bump_hit"] + row["bump_miss"] == 3 and row["lamp_hit"] + row["lamp_miss"] == 1
    rows = pd.DataFrame([row, {**row, "condition": "GPS error 10 m", "bump_hit": 1, "bump_miss": 2}])
    text = sim.write_report(rows, tmp_path / "acc.md", seeds=1)
    assert "MEASURED IN SIMULATION" in text and (tmp_path / "acc.md").read_text() == text
    assert "| baseline | 1 | 3 | 100.0% |" in text and "| GPS error 10 m | 1 | 3 | 33.3% |" in text


def test_committed_report_is_labelled_as_simulation():
    text = sim.REPORT_FILE.read_text()
    assert text.startswith("# Sensor detection accuracy: MEASURED IN SIMULATION")
    assert all(label in text for label, _ in sim.EVAL_CONDITIONS)


# --------------------------------------------------------------------------- S5: complaint anchors, demo rides, scenarios

def test_complaint_anchors_are_in_the_world_and_on_their_line(world):
    by_anchor = {d.get("anchor"): d for d in world if d.get("anchor")}
    assert len(by_anchor) == len(sim.ANCHORS)
    for a in sim.ANCHORS:
        route = sim.route_for(a["mode"], a["line"])
        assert route.locate(a["lon"], a["lat"])[1] < 1.0
        _, passed = sim.vehicle_world(route, world)
        assert by_anchor[a["anchor"]]["id"] in {p["id"] for p in passed}


def test_demo_rides_are_current(world, tmp_path):
    """data/demo/tram17_*.csv (uploaded by seed_demo.py) are the world's rides: rerun --make-world after changes."""
    for path in sim.write_demo_rides(world, tmp_path):
        assert path.read_bytes() == (synth.DEMO_DIR / path.name).read_bytes(), path.name
    truth = pd.read_csv(synth.DEMO_DIR / "tram17_day_01_truth.csv")
    for a in (a for a in sim.ANCHORS if a["mode"] == "tram"):
        d = synth._haversine_m(truth["lat"], truth["lon"], a["lat"], a["lon"])
        assert d.min() < 1.0  # every tram anchor is a defect of the demo rides


def test_scenario_spots_are_clean_and_on_their_line(world):
    for spot in (sim.NEW_POTHOLE, sim.HIDDEN_POTHOLE):
        route = sim.route_for("road", spot["line"])
        assert route.locate(spot["lon"], spot["lat"])[1] < 1.0
        near = [d for d in world if synth._haversine_m(d["lat"], d["lon"], spot["lat"], spot["lon"]) < 150]
        assert near == []


class FakeApi:
    def __init__(self, incidents):
        self.incidents, self.posts = incidents, []

    def get(self, path):
        if path.startswith("/incidents?"):
            return {"incidents": self.incidents}
        return next(i for i in self.incidents if path == f"/incidents/{i['id']}")

    def post_json(self, path, body):
        self.posts.append((path, body))
        return {}


def test_find_incident_nearest_within_radius():
    spot = {"lon": 21.0, "lat": 52.2}
    api = FakeApi([{"id": 1, "lon": 21.0003, "lat": 52.2}, {"id": 2, "lon": 21.0001, "lat": 52.2},
                   {"id": 3, "lon": 21.01, "lat": 52.2}])
    assert sim.find_incident(api, spot)["id"] == 2
    assert sim.find_incident(FakeApi([{"id": 3, "lon": 21.01, "lat": 52.2}]), spot) is None
    assert sim.describe(None) == "no incident yet"


def test_scenario_reports_are_dated_before_the_ride(monkeypatch, world):
    from datetime import datetime, timezone

    sent = []
    monkeypatch.setattr(sim, "stream_ride", lambda *a, **k: sent.append(a) or {"bumps": 4, "ride_id": 9})
    monkeypatch.setattr(sim, "find_incident", lambda api, spot, *a, **k: None)
    args = types_ns(api="http://x", token=None, chunk_s=10, speed=0)
    show = sim.Scenario(args, {"bus-SWI-01": "k1", "bus-SWI-02": "k2"}, world)
    show.api = FakeApi([])
    show.report_then_verify()
    (path, body), = show.api.posts
    assert path == "/reports/bulk" and len(body["reports"]) == len(sim.CITIZEN_TEXTS)
    ride_s = sent[0][4][-1]["t"]  # samples of the first ride, relative seconds
    newest = max(datetime.fromisoformat(r["created_at"]) for r in body["reports"])
    assert (datetime.now(timezone.utc) - newest).total_seconds() > ride_s  # before the ride started
    assert [a[1] for a in sent] == ["bus-SWI-01:k1", "bus-SWI-02:k2"]


def types_ns(**kw):
    from types import SimpleNamespace
    return SimpleNamespace(**kw)
