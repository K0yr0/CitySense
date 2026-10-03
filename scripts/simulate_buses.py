#!/usr/bin/env python
"""Virtual bus/tram fleet: drives simulated sensor rides over real Warsaw streets and streams them
to POST /devices/stream exactly like a real on-board device would (docs/ARCHITECTURE.md §8.5).

Everything here is SIMULATED (no real sensors). The world is fixed: potholes, track defects and
broken streetlights sit at known coordinates in data/demo/sim_world.json (the ground truth), so
every vehicle whose route passes over a defect feels it. Lines sharing a street hit the same
potholes; the tram on Marszałkowska never hits the road potholes 20 m beside its tracks.

Fleet = DEVICE_KEYS in .env, ids `<bus|tram>-<line>-<nn>`, e.g. bus-171-01, tram-17-01. Each
vehicle drives its line back and forth (`--rides` trips) in its own thread, sending a chunk
every `--chunk-s` seconds of ride data; `--speed 1` paces chunks in real time, 0 = flat out.
Bus lines are real ZTM lines (171, 159, 107, 160) driven along their real routes, taken from the
Warsaw GTFS feed and cut to the demo map (data/demo/bus_lines.json, rebuilt with --import-gtfs).

  .venv/bin/python scripts/simulate_buses.py --dry-run                 # generate + score, no API
  .venv/bin/python scripts/simulate_buses.py --api http://localhost:8000 --rides 2
  .venv/bin/python scripts/simulate_buses.py --make-world              # rewrite sim_world.json
  .venv/bin/python scripts/simulate_buses.py --import-gtfs             # rebuild bus_lines.json from GTFS
  docker compose --profile sim up simulator
  .venv/bin/python scripts/simulate_buses.py --eval                    # accuracy report (S4), no API
  .venv/bin/python scripts/simulate_buses.py --scenario all            # stage demo scenarios (S5)

Each run appends one JSON line per ride (device, trip, defects passed, API answer) to
data/rides/sim_<UTC time>.jsonl for the accuracy report (S4).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
import synth_ride as synth  # noqa: E402  (scripts/ is on sys.path when run as a script)

GEOJSON = REPO_ROOT / "data" / "osm" / "segments_demo.geojson"
WORLD_FILE = REPO_ROOT / "data" / "demo" / "sim_world.json"
REPORT_FILE = REPO_ROOT / "data" / "demo" / "sim_accuracy.md"
LOG_DIR = REPO_ROOT / "data" / "rides"
WORLD_SEED = 2026
BUS_LINES_FILE = REPO_ROOT / "data" / "demo" / "bus_lines.json"
GTFS_ZIP = REPO_ROOT / "data" / "cache" / "gtfs" / "warsaw.zip"     # gitignored download, only for --import-gtfs
GTFS_URL = "https://mkuran.pl/gtfs/warsaw.zip"
DEMO_BBOX = (20.9646, 52.1974, 21.0375, 52.2546)  # extent of segments_demo.geojson (lon/lat min, max)
KX, KY = 111_320 * math.cos(math.radians(52.23)), 110_540.0  # local metres per degree
STOP_MAX_OFF_M = 30.0      # a GTFS stop farther than this from the line's shape is not on this variant
MIN_STOP_GAP_M = 40.0      # platforms of one stop / loops: keep stops at least this far apart along the line
ON_ROAD_M = 8.0            # simulated defects only where the map has a road segment (so they map-match)

# Real ZTM bus lines, driven along their GTFS shape (direction 0, most frequent variant) inside the demo map,
# and the defects each one gets in the simulated world. Picked for long, many-street paths over the map's
# road network that share streets (Jerozolimskie, Piękna/Myśliwiecka, Solidarności), so lines confirm each other.
BUS_LINES = {
    "171": {"potholes": 5, "dark_lamps": 2},  # Leszno, Solidarności, pl. Bankowy, Marszałkowska, Jerozolimskie
    "159": {"potholes": 4, "dark_lamps": 2},  # Jerozolimskie, Chałubińskiego, Koszykowa, Piękna, Myśliwiecka
    "107": {"potholes": 4, "dark_lamps": 1},  # Nowolipki, Anielewicza, Wierzbowa, Krucza, Piękna, Myśliwiecka
    "160": {"potholes": 3, "dark_lamps": 1},  # Solidarności, Jana Pawła II, rondo ONZ
}

TRAM_LINES = {"17": {"defects": 6}}  # built-in synth_ride routes; their defects come from synth._world

# Defects placed where the synthetic citizen complaints (data/complaints_synth.json, owner A) cluster on a
# simulated line, so sensors and citizens describe the same world (S5). Without issue 2, 40 "tram track"
# complaints at Świętokrzyska met only clean tram passes and their confidence sank to ~45 %.
# Coordinates: the cluster's median point projected onto the line (fusion merges within 40 m).
ANCHORS = [
    {"kind": "bump", "mode": "tram", "line": "17", "street": "Marszałkowska", "lon": 21.008526, "lat": 52.235159,
     "amp": 8.0, "freq": 9.0, "anchor": "complaints issue 2: tram track, Marszałkowska x Świętokrzyska (40 reports)"},
    {"kind": "bump", "mode": "tram", "line": "17", "street": "Marszałkowska", "lon": 21.005973, "lat": 52.238853,
     "amp": 8.5, "freq": 8.5, "anchor": "complaints issue 1: tram track, Marszałkowska x Królewska (12 reports)"},
    {"kind": "bump", "mode": "road", "line": "171", "street": "Marszałkowska", "lon": 21.011257, "lat": 52.230832,
     "amp": 7.5, "freq": 8.0, "anchor": "complaints issue 3: pothole, Marszałkowska near Centrum (22 reports)"},
]
DEMO_RIDES = [("tram17_day_01", 1, False), ("tram17_night_01", 2, True)]  # (name, seed, night) for seed_demo.py


# --------------------------------------------------------------------------- real bus lines (GTFS) on the road map

def _m(lon, lat) -> tuple[float, float]:
    return lon * KX, lat * KY


def _inside(lon: float, lat: float) -> bool:
    return DEMO_BBOX[0] <= lon <= DEMO_BBOX[2] and DEMO_BBOX[1] <= lat <= DEMO_BBOX[3]


@lru_cache(maxsize=1)
def road_index(path: Path = GEOJSON):
    """STRtree over the map's road segments in local metres: (tree, geometries, street names)."""
    from shapely import STRtree
    from shapely.geometry import LineString

    feats = [f for f in json.loads(Path(path).read_text(encoding="utf-8"))["features"]
             if f["properties"]["mode"] == "road"]
    geoms = [LineString([_m(x, y) for x, y in f["geometry"]["coordinates"]]) for f in feats]
    return STRtree(geoms), geoms, [f["properties"]["name"] for f in feats]


def road_distance(lon: float, lat: float) -> float:
    """Metres to the nearest road segment of the map (inf beyond 50 m)."""
    from shapely.geometry import Point

    tree, geoms, _ = road_index()
    p = Point(_m(lon, lat))
    near = tree.query(p.buffer(50))
    return min((geoms[i].distance(p) for i in near), default=math.inf)


def street_at(lon: float, lat: float) -> str | None:
    """Name of the nearest road segment of the map."""
    from shapely.geometry import Point

    tree, geoms, names = road_index()
    p = Point(_m(lon, lat))
    near = list(tree.query(p.buffer(50)))
    return names[min(near, key=lambda i: geoms[i].distance(p))] if near else None


def import_gtfs(zip_path: Path = GTFS_ZIP, lines=tuple(BUS_LINES)) -> dict:
    """Each line's most frequent direction-0 shape, cut to its longest run of stops inside the demo map,
    with those stops projected onto it. Result = data/demo/bus_lines.json (small, committed)."""
    import zipfile

    from shapely.geometry import LineString, Point
    from shapely.ops import substring

    z = zipfile.ZipFile(zip_path)
    feed = pd.read_csv(z.open("feed_info.txt"), dtype=str).iloc[0]
    routes = pd.read_csv(z.open("routes.txt"), dtype=str)
    routes = routes[routes["route_short_name"].isin(lines) & (routes["route_type"] == "3")]
    trips = pd.read_csv(z.open("trips.txt"), dtype=str, usecols=["trip_id", "route_id", "shape_id", "direction_id"])
    trips = trips[trips["route_id"].isin(routes["route_id"]) & (trips["direction_id"] == "0")]
    top = (trips.groupby(["route_id", "shape_id"]).size().reset_index(name="n")
           .sort_values(["n", "shape_id"], ascending=[False, True]).drop_duplicates("route_id"))
    sample = {sid: sorted(trips.loc[trips["shape_id"] == sid, "trip_id"])[0] for sid in top["shape_id"]}
    shapes = pd.read_csv(z.open("shapes.txt"), dtype={"shape_id": str})
    shapes = shapes[shapes["shape_id"].isin(set(top["shape_id"]))]
    stop_times = pd.concat(
        ch[ch["trip_id"].isin(set(sample.values()))]
        for ch in pd.read_csv(z.open("stop_times.txt"), dtype=str, usecols=["trip_id", "stop_id", "stop_sequence"],
                              chunksize=2_000_000))
    stops = pd.read_csv(z.open("stops.txt"), dtype=str, usecols=["stop_id", "stop_name", "stop_lat", "stop_lon"])
    stops = stops.set_index("stop_id")
    out = {"source": "ZTM Warszawa timetable via the GTFS feed of Mikołaj Kuranowski (" + GTFS_URL + "); bus "
                     "shapes based on © OpenStreetMap contributors (ODbL)",
           "feed_version": str(feed.get("feed_version", "")), "lines": {}}
    for row in top.itertuples():
        route = routes[routes["route_id"] == row.route_id].iloc[0]
        pts = shapes[shapes["shape_id"] == row.shape_id].astype({"shape_pt_sequence": int}).sort_values("shape_pt_sequence")
        geom = LineString([_m(lo, la) for lo, la in zip(pts["shape_pt_lon"], pts["shape_pt_lat"])])
        seq = stop_times[stop_times["trip_id"] == sample[row.shape_id]].astype({"stop_sequence": int})
        runs, cur = [], []
        for sid in seq.sort_values("stop_sequence")["stop_id"]:
            st = stops.loc[sid]
            lo, la = float(st["stop_lon"]), float(st["stop_lat"])
            p = Point(_m(lo, la))
            d = geom.project(p)
            if _inside(lo, la) and geom.distance(p) <= STOP_MAX_OFF_M:
                if not cur or d > cur[-1][1] + MIN_STOP_GAP_M:
                    cur.append((str(st["stop_name"]), d))
            elif cur:
                runs.append(cur)
                cur = []
        runs.append(cur)
        run = max(runs, key=lambda r: r[-1][1] - r[0][1] if len(r) > 1 else 0.0)
        part = substring(geom, run[0][1], run[-1][1])
        path = [(round(x / KX, 6), round(y / KY, 6)) for x, y in part.coords]
        path = [p for k, p in enumerate(path) if k == 0 or p != path[k - 1]]
        stop_pts = [(name, *(round(c, 6) for c in (lambda q: (q.x / KX, q.y / KY))(geom.interpolate(d))))
                    for name, d in run]
        stop_pts[0], stop_pts[-1] = (stop_pts[0][0], *path[0]), (stop_pts[-1][0], *path[-1])
        samples = [part.interpolate(t) for t in np.arange(0, part.length, 25.0)]
        on_road = float(np.mean([road_distance(q.x / KX, q.y / KY) <= 20 for q in samples]))
        out["lines"][str(route["route_short_name"])] = {
            "name": str(route["route_long_name"]), "shape_id": row.shape_id, "length_m": round(part.length),
            "on_road_network": round(on_road, 2), "stops": stop_pts, "path": path}
    return out


@lru_cache(maxsize=1)
def bus_lines() -> dict:
    return json.loads(BUS_LINES_FILE.read_text(encoding="utf-8"))["lines"]


@lru_cache(maxsize=None)
def bus_route_cfg(line: str) -> dict:
    """ROUTES-style config (mode, path, stops) of a real bus line, from data/demo/bus_lines.json."""
    spec = bus_lines()[line]
    return {"mode": "road", "path": [tuple(p) for p in spec["path"]],
            "stops": [tuple(s) for s in spec["stops"]], "crossings": []}


def route_for(mode: str, line: str, reverse: bool = False) -> synth.Route:
    """A line's route; `reverse` = the return trip (same path driven backwards)."""
    cfg = bus_route_cfg(line) if mode == "road" else dict(synth.ROUTES[line])
    if not reverse:
        return synth.Route(line, cfg)
    route = synth.Route(line, {**cfg, "crossings": [],
                               "path": list(cfg.get("path") or [(lo, la) for _, lo, la in cfg["stops"]])[::-1],
                               "stops": cfg["stops"][::-1]})
    route.reverse = True
    route.crossing_s = [route.length - c for c in synth.Route(line, cfg).crossing_s]
    return route


def _builtin_world(line: str) -> tuple[synth.Route, dict]:
    """synth._world of a built-in tram line (defects, joints, lamps fixed along its forward path)."""
    route = synth.Route(line)
    return route, synth._world(route, TRAM_LINES.get(line, {}).get("defects", 6))


def _mirror(world: dict, length: float) -> dict:
    """The same physical world seen from the other end of the path (s -> length - s)."""
    return {**world, "bumps": sorted((length - s, a, f) for s, a, f in world["bumps"]),
            "joints": length - world["joints"], "lamps": length - world["lamps"]}


# --------------------------------------------------------------------------- the fixed world (ground truth)

def make_world(seed: int = WORLD_SEED) -> dict:
    """Defects at fixed coordinates: potholes + dark lamps on the bus corridors, the tram lines' track defects."""
    defects = [dict(a) for a in ANCHORS]
    taken = [(a["lon"], a["lat"]) for a in ANCHORS if a["mode"] == "road"]  # road defects of every line so far

    def pick(route, rng, n: int, *, margin: float, stop_gap: float, gap: float) -> list[tuple[float, float]]:
        """n spots on the line: on the map's roads, away from stops and from every road defect placed so far."""
        out = []
        for _ in range(20000):
            if len(out) >= n:
                break
            s = float(rng.uniform(margin, route.length - margin))
            lon, lat = (float(v) for v in route.at(s))
            if (np.min(np.abs(route.stop_s - s)) > stop_gap and road_distance(lon, lat) <= ON_ROAD_M
                    and all(float(synth._haversine_m(lat, lon, q[1], q[0])) > gap for q in taken)):
                out.append((lon, lat))
                taken.append((lon, lat))
        return out

    for line, spec in BUS_LINES.items():
        route = route_for("road", line)
        rng = np.random.default_rng([seed, sum(map(ord, line))])
        for lon, lat in pick(route, rng, spec["potholes"], margin=60, stop_gap=50, gap=120):
            defects.append({"kind": "bump", "mode": "road", "street": street_at(lon, lat), "line": line,
                            "lon": round(lon, 6), "lat": round(lat, 6),
                            "amp": round(float(rng.uniform(5.0, 9.5)), 2),
                            "freq": round(float(rng.uniform(6.0, 10.0)), 2)})
        # lamp detection needs the lit rhythm on both sides: keep broken lamps off the ends and stops
        for lon, lat in pick(route, rng, spec["dark_lamps"], margin=200, stop_gap=60, gap=200):
            defects.append({"kind": "dark_lamp", "mode": "road", "street": street_at(lon, lat), "line": line,
                            "lon": round(lon, 6), "lat": round(lat, 6)})
    for line in TRAM_LINES:  # recorded for the truth; synth._world drives them
        route, world = _builtin_world(line)
        for s, amp, freq in world["bumps"]:
            lon, lat = route.at(s)
            defects.append({"kind": "bump", "mode": "tram", "street": None, "line": line, "builtin": True,
                            "lon": round(float(lon), 6), "lat": round(float(lat), 6),
                            "amp": round(float(amp), 2), "freq": round(float(freq), 2)})
        for k in world["broken"]:
            lon, lat = route.at(world["lamps"][k])
            defects.append({"kind": "dark_lamp", "mode": "tram", "street": None, "line": line, "builtin": True,
                            "lon": round(float(lon), 6), "lat": round(float(lat), 6)})
    for i, d in enumerate(defects, 1):
        d["id"] = f"D{i:03d}"
    return {"seed": seed, "note": "SIMULATED ground truth for scripts/simulate_buses.py", "defects": defects}


def write_demo_rides(defects: list[dict], out_dir: Path = synth.DEMO_DIR) -> list[Path]:
    """Rewrite the tram 17 demo rides (seed_demo.py uploads them) over the full world, anchors included."""
    route = route_for("tram", "17")
    world, _ = vehicle_world(route, defects)
    out = []
    for name, seed, night in DEMO_RIDES:
        out += synth.write_ride(name, out_dir, route=route, world=world, seed=seed, night=night)
    return out


def load_world(path: Path = WORLD_FILE) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8")) if Path(path).exists() else make_world()


def vehicle_world(route: synth.Route, defects: list[dict]) -> tuple[dict, list[dict]]:
    """synth world for one route + the defects it actually drives over (with along-route s)."""
    mine = [d for d in defects if d["mode"] == route.mode]
    if route.line in synth.ROUTES and route.mode == "tram":
        fwd, base = _builtin_world(route.line)
        if getattr(route, "reverse", False):
            base = _mirror(base, fwd.length)
        # added track defects (S5 scenarios); added dark lamps are ignored on built-in tram lines
        extra = synth.world_on_route(route, [d for d in mine if not d.get("builtin")])
        base["bumps"] = sorted(base["bumps"] + extra["bumps"])
        world = base
    else:
        world = synth.world_on_route(route, mine)
    passed = []
    for d in mine:
        s, off = route.locate(d["lon"], d["lat"])
        if off <= synth.ON_ROUTE_M and 0 < s < route.length:
            passed.append({"id": d["id"], "kind": d["kind"], "lon": d["lon"], "lat": d["lat"], "s": round(s, 1)})
    return world, passed


# --------------------------------------------------------------------------- accuracy sweep (S4)

# One factor at a time away from the baseline, plus one combined hard case.
EVAL_CONDITIONS: list[tuple[str, dict]] = [
    ("baseline", {}),
    ("vibration noise x1.5", {"noise": 1.5}),
    ("vibration noise x2", {"noise": 2.0}),
    ("vibration noise x3", {"noise": 3.0}),
    ("slow traffic (speed x0.6)", {"speed": 0.6}),
    ("fast (speed x1.3)", {"speed": 1.3}),
    ("phone lying flat", {"pose": "flat"}),
    ("phone upright (holder/pocket)", {"pose": "upright"}),
    ("GPS error 5 m", {"gps_m": 5.0}),
    ("GPS error 10 m", {"gps_m": 10.0}),
    ("hard: noise x2 + slow + GPS 5 m", {"noise": 2.0, "speed": 0.6, "gps_m": 5.0}),
]
EVAL_VEHICLES = [*((f"bus-{line}-01", "road", line) for line in BUS_LINES), ("tram-17-01", "tram", "17")]
BUMP_RADIUS_M, LAMP_RADIUS_M = 20.0, 25.0


def match_counts(found: pd.DataFrame, truth: list[dict], radius_m: float) -> dict:
    """Counts for micro-averaging: detections near a truth point (tp) or not (fp); truth points hit or missed."""
    nf, nt = len(found), len(truth)
    if nf == 0 or nt == 0:
        return {"tp": 0, "fp": nf, "hit": 0, "miss": nt}
    t_lat = np.array([d["lat"] for d in truth])[None, :]
    t_lon = np.array([d["lon"] for d in truth])[None, :]
    d = synth._haversine_m(found["lat"].to_numpy(float)[:, None], found["lon"].to_numpy(float)[:, None], t_lat, t_lon)
    near = d <= radius_m
    tp = int(near.any(axis=1).sum())
    hit = int(near.any(axis=0).sum())
    return {"tp": tp, "fp": nf - tp, "hit": hit, "miss": nt - hit}


def eval_ride(job: tuple) -> dict:
    """One simulated night ride through the real detectors -> bump and dark-lamp counts."""
    from backend.sensor.detect import detect_bumps
    from backend.sensor.lights import find_dark_gaps

    label, cond, (device_id, mode, line), trip, seed, defects = job
    df, passed, _ = build_ride(device_id, mode, line, trip, seed=seed, night=True, defects=defects, conditions=cond)
    bumps = match_counts(detect_bumps(df), [p for p in passed if p["kind"] == "bump"], BUMP_RADIUS_M)
    lamps = match_counts(find_dark_gaps(df), [p for p in passed if p["kind"] == "dark_lamp"], LAMP_RADIUS_M)
    return {"condition": label, "mode": mode, **{f"bump_{k}": v for k, v in bumps.items()},
            **{f"lamp_{k}": v for k, v in lamps.items()}}


def evaluate(defects: list[dict], *, seeds: int = 10, conditions=EVAL_CONDITIONS, workers: int | None = None) -> pd.DataFrame:
    """Per-ride counts for every condition x vehicle x direction x seed (parallel processes)."""
    from concurrent.futures import ProcessPoolExecutor

    jobs = [(label, cond, veh, trip, 1000 + k, defects)
            for label, cond in conditions for veh in EVAL_VEHICLES for trip in (0, 1) for k in range(seeds)]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        return pd.DataFrame(list(pool.map(eval_ride, jobs, chunksize=2)))


def _ratio(a: int, b: int) -> str:
    return f"{100.0 * a / b:.1f}%" if b else "n/a"


def summarize(rows: pd.DataFrame) -> pd.DataFrame:
    order = {label: i for i, (label, _) in enumerate(EVAL_CONDITIONS)}
    g = rows.groupby("condition", sort=False).sum(numeric_only=True)
    g = g.loc[sorted(g.index, key=lambda c: order.get(c, len(order)))]
    rides = rows.groupby("condition").size()
    return pd.DataFrame({
        "rides": rides.reindex(g.index),
        "pothole/track defects passed": g["bump_hit"] + g["bump_miss"],
        "defect recall": [_ratio(h, h + m) for h, m in zip(g["bump_hit"], g["bump_miss"])],
        "defect precision": [_ratio(t, t + f) for t, f in zip(g["bump_tp"], g["bump_fp"])],
        "broken lamps passed": g["lamp_hit"] + g["lamp_miss"],
        "lamp recall": [_ratio(h, h + m) for h, m in zip(g["lamp_hit"], g["lamp_miss"])],
        "lamp precision": [_ratio(t, t + f) for t, f in zip(g["lamp_tp"], g["lamp_fp"])],
    })


def write_report(rows: pd.DataFrame, path: Path, *, seeds: int) -> str:
    table = summarize(rows)
    header = "| condition | " + " | ".join(table.columns) + " |"
    lines = [header, "|" + "---|" * (len(table.columns) + 1)]
    lines += ["| " + " | ".join([str(idx), *map(str, row)]) + " |" for idx, row in table.iterrows()]
    by_mode = rows[rows["condition"] == "baseline"].groupby("mode").sum(numeric_only=True)
    mode_lines = [f"- **{'bus (road potholes)' if m == 'road' else 'tram (track defects)'}**: recall "
                  f"{_ratio(r.bump_hit, r.bump_hit + r.bump_miss)}, precision {_ratio(r.bump_tp, r.bump_tp + r.bump_fp)}"
                  for m, r in by_mode.iterrows()]
    text = "\n".join([
        "# Sensor detection accuracy: MEASURED IN SIMULATION",
        "",
        "> **All sensor data here is simulated** (scripts/simulate_buses.py, no real hardware). Present these",
        "> numbers as *measured in simulation*, never as field results. Regenerate with",
        "> `.venv/bin/python scripts/simulate_buses.py --eval`.",
        "",
        f"Setup: the real detectors (`backend/sensor/detect.py`, `backend/sensor/lights.py`) run on simulated night "
        f"rides over the fixed ground truth `data/demo/sim_world.json`: {len(EVAL_VEHICLES)} lines "
        f"(bus {', '.join(BUS_LINES)}; tram 17) x 2 directions x {seeds} seeds per condition. A detection counts if it is "
        f"within {BUMP_RADIUS_M:.0f} m (defects) / {LAMP_RADIUS_M:.0f} m (lamps) of a true defect the vehicle drove "
        f"over. Recall = share of passed defects detected; precision = share of detections that are real. One "
        f"factor is changed at a time from the baseline (noise x1, normal speed, phone in a random pose, GPS 2.5 m).",
        "",
        *lines,
        "",
        "Baseline by vehicle type:",
        *mode_lines,
        "",
        "Not measured here: the fusion step (several rides -> one verified incident). In the end-to-end Docker run",
        "of the fleet every ground-truth defect became exactly one incident; that is a single run, not a statistic.",
        "",
    ])
    Path(path).write_text(text, encoding="utf-8")
    return text


# --------------------------------------------------------------------------- fleet + streaming

def parse_device(device_id: str) -> tuple[str, str] | None:
    """`bus-171-01` -> ("road", "171"); `tram-17-02` -> ("tram", "17"); None if not a known line."""
    parts = device_id.split("-")
    if len(parts) < 3:
        return None
    kind, line = parts[0].lower(), "-".join(parts[1:-1])
    if kind == "bus" and line in BUS_LINES:
        return "road", line
    if kind == "tram" and line in synth.ROUTES:
        return "tram", line
    return None


def ride_seed(base: int, device_id: str, trip: int) -> int:
    return int(hashlib.sha256(f"{base}:{device_id}:{trip}".encode()).hexdigest()[:8], 16)


def to_samples(df: pd.DataFrame) -> list[dict]:
    """synth frame -> /devices/stream samples (relative `t`, no NaN lux)."""
    cols = ["t", "ax", "ay", "az", "lat", "lon", "speed_kmh", "lux"]
    out = []
    for row in df[cols].itertuples(index=False):
        s = {"t": row.t, "ax": row.ax, "ay": row.ay, "az": row.az, "lat": row.lat, "lon": row.lon,
             "speed_kmh": row.speed_kmh}
        if not (row.lux is None or (isinstance(row.lux, float) and math.isnan(row.lux))):
            s["lux"] = row.lux
        out.append(s)
    return out


def post_chunk(api: str, key: str, body: dict, timeout: float = 600.0, retries: int = 3) -> dict:
    data = json.dumps(body).encode()
    for attempt in range(retries):
        req = urllib.request.Request(f"{api.rstrip('/')}/devices/stream", data,
                                     {"Content-Type": "application/json", "X-Device-Key": key})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code < 500 or attempt == retries - 1:
                raise RuntimeError(f"/devices/stream {e.code}: {e.read().decode(errors='replace')[:300]}") from e
        except urllib.error.URLError:
            if attempt == retries - 1:
                raise
        time.sleep(2 ** attempt)
    raise RuntimeError("unreachable")


def stream_ride(api: str, key: str, line: str, mode: str, samples: list[dict], *,
                chunk_s: float, speed: float, stop: threading.Event) -> dict | None:
    """Send one ride in chunks of `chunk_s` seconds; the last chunk is `final`. Returns the final answer."""
    n_per = max(1, int(round(chunk_s * synth.FS)))
    for i in range(0, len(samples), n_per):
        if stop.is_set():
            return None
        final = i + n_per >= len(samples)
        t0 = time.monotonic()
        res = post_chunk(api, key, {"vehicle_line": line, "mode": mode, "samples": samples[i:i + n_per],
                                    "final": final})
        if final:
            return res
        if speed > 0:
            time.sleep(max(0.0, chunk_s / speed - (time.monotonic() - t0)))
    return None


def build_ride(device_id: str, mode: str, line: str, trip: int, *, seed: int, night: bool,
               defects: list[dict], conditions: dict | None = None) -> tuple[pd.DataFrame, list[dict], synth.Route]:
    route = route_for(mode, line, reverse=trip % 2 == 1)
    world, passed = vehicle_world(route, defects)
    df, _ = synth.generate_ride(route=route, world=world, seed=ride_seed(seed, device_id, trip), night=night,
                                conditions=conditions)
    if not night:
        passed = [p for p in passed if p["kind"] != "dark_lamp"]  # lamps are only visible at night
    return df, passed, route


def run_vehicle(device_id: str, secret: str, mode: str, line: str, args, defects: list[dict],
                log, lock: threading.Lock, stop: threading.Event) -> None:
    for trip in range(args.rides):
        if stop.is_set():
            return
        df, passed, route = build_ride(device_id, mode, line, trip, seed=args.seed, night=args.night,
                                       defects=defects)
        rec = {"device_id": device_id, "line": line, "mode": mode, "trip": trip,
               "direction": "reverse" if trip % 2 else "forward", "night": args.night,
               "duration_s": round(float(df["t"].iloc[-1]), 1), "length_m": round(route.length),
               "defects_passed": passed}
        if not args.dry_run:
            try:
                rec["result"] = stream_ride(args.api, f"{device_id}:{secret}", line, mode, to_samples(df),
                                            chunk_s=args.chunk_s, speed=args.speed, stop=stop)
            except Exception as exc:  # one vehicle failing must not stop the fleet
                rec["error"] = str(exc)
        with lock:
            log.write(json.dumps(rec, ensure_ascii=False) + "\n")
            log.flush()
            res = rec.get("result") or {}
            status = rec.get("error") or (f"ride {res.get('ride_id')}: {res.get('bumps')} bumps, "
                                          f"{res.get('dark_gaps')} dark gaps, incidents {res.get('incident_ids')}, "
                                          f"verified {res.get('verified_incident_ids')}" if res else "generated")
            print(f"[{device_id}] trip {trip} {rec['direction']}: {len(passed)} defects on route; {status}",
                  flush=True)


def fleet(device_keys: dict[str, str], only: list[str] | None) -> list[tuple[str, str, str, str]]:
    out = []
    for device_id, secret in sorted(device_keys.items()):
        if only and device_id not in only:
            continue
        parsed = parse_device(device_id)
        if parsed is None:
            print(f"skip {device_id}: id must be bus-<{'|'.join(BUS_LINES)}>-NN or tram-<{'|'.join(synth.ROUTES)}>-NN")
            continue
        out.append((device_id, secret, *parsed))
    return out


# --------------------------------------------------------------------------- stage scenarios (S5)

# Fixed spots with no defect and no complaint within 80 m, away from stops (seeded, repeatable).
NEW_POTHOLE = {"id": "S5-NEW", "kind": "bump", "mode": "road", "line": "159", "street": "Aleje Jerozolimskie",
               "lon": 20.972611, "lat": 52.220435, "amp": 8.0, "freq": 8.0}
HIDDEN_POTHOLE = {"id": "S5-REPORTED", "kind": "bump", "mode": "road", "line": "107", "street": "Mordechaja Anielewicza",
                  "lon": 20.981055, "lat": 52.245071, "amp": 7.5, "freq": 8.5}
SCENARIO_SEED = 5000
# App reports carry the phone's position; no street names, which the geocoder could resolve elsewhere.
CITIZEN_TEXTS = [
    "Duża dziura w jezdni, autobusy podskakują. Zgłaszam z miejsca.",
    "Wyrwa w asfalcie na prawym pasie, niebezpiecznie dla rowerzystów.",
]
LATE_REPORT_TEXT = "Nowa dziura w jezdni tutaj, uważajcie!"
SCENARIO_CITIZEN = "scenario.citizen@cityecho.test"  # demo sign-in account of scenario 1's late report


def scenario_buses(spot: dict) -> tuple[str, str]:
    return f"bus-{spot['line']}-01", f"bus-{spot['line']}-02"


class Api:
    """Tiny JSON client for the scenarios (stdlib only, like the devices)."""

    def __init__(self, base: str, token: str | None = None):
        self.base, self.token = base.rstrip("/"), token

    def _req(self, method: str, path: str, data: bytes | None = None, ctype: str | None = None,
             token: str | None = None) -> dict:
        token = token or self.token
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        if ctype:
            headers["Content-Type"] = ctype
        req = urllib.request.Request(self.base + path, data, headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"{method} {path} -> {e.code}: {e.read().decode(errors='replace')[:300]}") from e

    def get(self, path: str) -> dict:
        return self._req("GET", path)

    def post_json(self, path: str, body: dict) -> dict:
        return self._req("POST", path, json.dumps(body).encode(), "application/json")

    def post_form(self, path: str, fields: dict, token: str | None = None) -> dict:
        from urllib.parse import urlencode
        return self._req("POST", path, urlencode(fields).encode(), "application/x-www-form-urlencoded", token)

    def dev_sign_in(self, email: str) -> str:
        """POST /auth/dev (local stack only) -> bearer token."""
        return self.post_json("/auth/dev", {"email": email})["token"]


def admin_token(api: Api) -> str | None:
    """Admin endpoints (/incidents, /reports/bulk) need an admin: sign in as the first ADMIN_EMAILS entry."""
    from backend.config import settings

    if not settings.admin_emails:
        return None
    try:
        return api.dev_sign_in(settings.admin_emails[0])
    except (RuntimeError, OSError):  # dev sign-in off, or the API is unreachable
        return None


def find_incident(api: Api, spot: dict, issue_type: str = "road_damage", radius_m: float = 40.0) -> dict | None:
    """The incident of `issue_type` nearest to the spot (within radius_m), as a full detail."""
    rows = api.get(f"/incidents?type={issue_type}&limit=5000")["incidents"]
    best = min(((float(synth._haversine_m(spot["lat"], spot["lon"], r["lat"], r["lon"])), r) for r in rows),
               key=lambda x: x[0], default=None)
    return api.get(f"/incidents/{best[1]['id']}") if best and best[0] <= radius_m else None


def describe(inc: dict | None) -> str:
    if inc is None:
        return "no incident yet"
    return (f"incident #{inc['id']}: {inc['status'].upper()} (confidence {inc['confidence']:.0%}), "
            f"{inc['report_count']} citizen reports, {inc['sensor_rides']} sensor rides, "
            f"{inc['sensor_misses']} clean passes, found before any report: {'yes' if inc['found_before_report'] else 'no'}")


def segment_health(api: Api, spot: dict, half_m: float = 15.0) -> str:
    dlon, dlat = half_m / (111_320 * math.cos(math.radians(spot["lat"]))), half_m / 110_540
    bbox = f"{spot['lon'] - dlon},{spot['lat'] - dlat},{spot['lon'] + dlon},{spot['lat'] + dlat}"
    segs = [x for x in api.get(f"/segments?bbox={bbox}&mode=road&measured_only=true")["segments"]
            if x.get("health") is not None]
    return f"{min(x['health'] for x in segs):.2f}" if segs else "not measured"


class Scenario:
    def __init__(self, args, keys: dict[str, str], defects: list[dict]):
        self.args, self.keys, self.defects = args, keys, defects
        self.api = Api(args.api, args.token)
        if self.api.token is None:  # the incident detail and bulk reports are admin-only
            self.api.token = admin_token(self.api)
        if self.api.token is None:
            sys.exit("the scenarios read admin-only endpoints: pass --token (or CITYECHO_API_TOKEN), or enable "
                     "dev sign-in (AUTH_DEV_LOGIN=1) with an ADMIN_EMAILS entry in .env")
        self.trip = 0  # alternate directions across the whole show

    def say(self, text: str) -> None:
        print(f"\n>>> {text}", flush=True)

    def drive(self, device_id: str, *, extra: list[dict] = (), removed: set[str] = frozenset(),
              before_send=None) -> dict:
        """One ride with the world changed by the scenario. The API dates a streamed ride so that it
        ends 'now'; `before_send(duration_s)` runs first, e.g. to date reports before the ride started."""
        if device_id not in self.keys:
            sys.exit(f"scenario needs {device_id} in DEVICE_KEYS")
        mode, line = parse_device(device_id)
        world = [d for d in self.defects if d["id"] not in removed] + list(extra)
        trip, self.trip = self.trip, self.trip + 1
        df, passed, _ = build_ride(device_id, mode, line, trip, seed=SCENARIO_SEED, night=False, defects=world)
        if before_send:
            before_send(float(df["t"].iloc[-1]))
        res = stream_ride(self.args.api, f"{device_id}:{self.keys[device_id]}", line, mode, to_samples(df),
                          chunk_s=self.args.chunk_s, speed=self.args.speed, stop=threading.Event())
        print(f"    {device_id} drove line {line} ({'return' if trip % 2 else 'outbound'}): "
              f"{res['bumps']} bumps felt, ride #{res['ride_id']}", flush=True)
        return res

    def new_pothole(self) -> None:
        first, second = scenario_buses(NEW_POTHOLE)
        self.say(f"Scenario 1: a NEW pothole opens on {NEW_POTHOLE['street']} (line {NEW_POTHOLE['line']}). "
                 "Nobody has reported it.")
        print(f"    before: {describe(find_incident(self.api, NEW_POTHOLE))}")
        self.drive(first, extra=[NEW_POTHOLE])
        print(f"    after the first bus: {describe(find_incident(self.api, NEW_POTHOLE))}")
        self.drive(second, extra=[NEW_POTHOLE])
        print(f"    after a second bus:  {describe(find_incident(self.api, NEW_POTHOLE))}")
        citizen = self.api.dev_sign_in(SCENARIO_CITIZEN)
        r = self.api.post_form("/mobile/reports", {"text": LATE_REPORT_TEXT, "lon": NEW_POTHOLE["lon"],
                                                   "lat": NEW_POTHOLE["lat"]}, token=citizen)
        print(f"    a citizen reports it in the app later -> report joins incident #{(r.get('incident') or {}).get('id')}")
        print(f"    now: {describe(find_incident(self.api, NEW_POTHOLE))}")

    def report_then_verify(self) -> None:
        first, second = scenario_buses(HIDDEN_POTHOLE)
        self.say(f"Scenario 2: citizens report a pothole on {HIDDEN_POTHOLE['street']} (line {HIDDEN_POTHOLE['line']}); "
                 "the next bus checks it.")

        def report_first(ride_s: float) -> None:  # the reports come in before the bus sets off
            t0 = datetime.now(timezone.utc).timestamp() - ride_s - 120
            self.api.post_json("/reports/bulk", {"reports": [
                {"text": text, "lon": HIDDEN_POTHOLE["lon"], "lat": HIDDEN_POTHOLE["lat"], "source": "web",
                 "created_at": datetime.fromtimestamp(t0 + 30 * k, timezone.utc).isoformat()}
                for k, text in enumerate(CITIZEN_TEXTS)]})
            print(f"    after {len(CITIZEN_TEXTS)} reports: {describe(find_incident(self.api, HIDDEN_POTHOLE))}")

        self.drive(first, extra=[HIDDEN_POTHOLE], before_send=report_first)
        print(f"    after the next bus:  {describe(find_incident(self.api, HIDDEN_POTHOLE))}")
        self.drive(second, extra=[HIDDEN_POTHOLE])
        print(f"    after another bus:   {describe(find_incident(self.api, HIDDEN_POTHOLE))}")

    def repair(self) -> None:
        first, second = scenario_buses(NEW_POTHOLE)
        self.say(f"Scenario 3: the {NEW_POTHOLE['street']} pothole is REPAIRED; buses keep driving over the spot.")
        if find_incident(self.api, NEW_POTHOLE) is None:
            print("    (scenario 1 has not run on this database yet: running it first)")
            self.new_pothole()
        before = find_incident(self.api, NEW_POTHOLE)
        print(f"    before: {describe(before)}; road health there {segment_health(self.api, NEW_POTHOLE)}")
        for dev in (first, second, first):
            self.drive(dev, removed={NEW_POTHOLE["id"]})
        after = find_incident(self.api, NEW_POTHOLE)
        felt = after["sensor_rides"] - before["sensor_rides"]
        print(f"    after 3 passes: the buses felt {'nothing' if felt == 0 else f'{felt} bumps'} at the spot; road health "
              f"there {segment_health(self.api, NEW_POTHOLE)} (the 5 newest passes count, 1 = smooth)")
        print(f"    {describe(after)}")
        print("    a verified incident stays open until the city marks the job done in the web admin "
              "(work_status = done, owner B); the sensors now back that decision")


SCENARIOS = {"new-pothole": "new_pothole", "report-verify": "report_then_verify", "repair": "repair"}


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--rides", type=int, default=2, help="trips per vehicle (alternating direction)")
    ap.add_argument("--seed", type=int, default=1, help="ride seed base (the world stays fixed)")
    ap.add_argument("--night", action="store_true", help="night rides: lux sensor sees broken streetlights")
    ap.add_argument("--chunk-s", type=float, default=10.0, help="seconds of ride data per request")
    ap.add_argument("--speed", type=float, default=0.0, help="1 = real time, 10 = 10x, 0 = as fast as possible")
    ap.add_argument("--devices", nargs="*", help="only these device ids (default: all DEVICE_KEYS)")
    ap.add_argument("--world", default=str(WORLD_FILE), help="ground-truth defects JSON")
    ap.add_argument("--import-gtfs", nargs="?", const=str(GTFS_ZIP), metavar="ZIP",
                    help=f"rebuild {BUS_LINES_FILE.name} from the Warsaw GTFS zip ({GTFS_URL}) and exit")
    ap.add_argument("--make-world", action="store_true",
                    help="(re)write the world file and the tram 17 demo rides over it, then exit")
    ap.add_argument("--dry-run", action="store_true", help="generate rides and log truth, send nothing")
    ap.add_argument("--eval", action="store_true", help="accuracy sweep over recording conditions (S4), no API")
    ap.add_argument("--eval-seeds", type=int, default=10, help="rides per line, direction and condition")
    ap.add_argument("--report", default=str(REPORT_FILE), help="where --eval writes its markdown report")
    ap.add_argument("--scenario", choices=[*SCENARIOS, "all"], help="run a stage demo scenario (S5) against --api")
    ap.add_argument("--token", default=os.getenv("CITYECHO_API_TOKEN"),
                    help="Bearer token for the scenario's API reads, if they need a login")
    args = ap.parse_args(argv)

    if args.eval:
        t0 = time.monotonic()
        rows = evaluate(load_world(Path(args.world))["defects"], seeds=args.eval_seeds)
        print(write_report(rows, Path(args.report), seeds=args.eval_seeds))
        print(f"{len(rows)} rides in {time.monotonic() - t0:.0f}s -> {args.report}")
        return

    if args.import_gtfs:
        if not Path(args.import_gtfs).exists():
            sys.exit(f"{args.import_gtfs} not found: download {GTFS_URL} there first")
        lines = import_gtfs(Path(args.import_gtfs))
        BUS_LINES_FILE.write_text(json.dumps(lines, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        for line, d in lines["lines"].items():
            print(f"line {line} ({d['name']}): {d['length_m']} m, {len(d['stops'])} stops, "
                  f"{d['on_road_network']:.0%} on the map's roads")
        return

    if args.make_world:
        world = make_world()
        Path(args.world).write_text(json.dumps(world, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"wrote {args.world}: {len(world['defects'])} defects")
        for path in write_demo_rides(world["defects"]):
            print(f"wrote {path.relative_to(REPO_ROOT)}")
        return

    from backend.config import settings

    if args.scenario:
        show = Scenario(args, settings.device_keys, load_world(Path(args.world))["defects"])
        for name in (SCENARIOS if args.scenario == "all" else [args.scenario]):
            getattr(show, SCENARIOS[name])()
        return

    vehicles = fleet(settings.device_keys, args.devices)
    if not vehicles:
        sys.exit("no simulated vehicles: set DEVICE_KEYS in .env, e.g. "
                 "DEVICE_KEYS=bus-171-01:<secret>,tram-17-01:<secret>")
    defects = load_world(Path(args.world))["defects"]
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"sim_{datetime.now(timezone.utc):%Y%m%dT%H%M%S}.jsonl"
    print(f"{len(vehicles)} vehicles, {args.rides} trips each, {'DRY RUN' if args.dry_run else args.api}"
          f" -> {log_path.relative_to(REPO_ROOT)}", flush=True)
    lock, stop = threading.Lock(), threading.Event()
    with log_path.open("w", encoding="utf-8") as log:
        threads = [threading.Thread(target=run_vehicle, args=(*v, args, defects, log, lock, stop),
                                    name=v[0], daemon=True) for v in vehicles]
        for th in threads:
            th.start()
        try:
            for th in threads:
                while th.is_alive():
                    th.join(0.5)
        except KeyboardInterrupt:
            stop.set()
            print("stopping (open rides are dropped by the API after 30 min idle)")


if __name__ == "__main__":
    main()
