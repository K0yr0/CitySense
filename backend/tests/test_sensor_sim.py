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
