#!/usr/bin/env python
"""Virtual bus/tram fleet: drives simulated sensor rides over real Warsaw streets and streams them
to POST /devices/stream exactly like a real on-board device would (docs/ARCHITECTURE.md §8.5).

Everything here is SIMULATED (no real sensors). The world is fixed: potholes, track defects and
broken streetlights sit at known coordinates in data/demo/sim_world.json (the ground truth), so
every vehicle whose route passes over a defect feels it. Lines sharing a street hit the same
potholes; the tram on Marszałkowska never hits the road potholes 20 m beside its tracks.

Fleet = DEVICE_KEYS in .env, ids `<bus|tram>-<line>-<nn>`, e.g. bus-MAR-01, tram-17-01. Each
vehicle drives its line back and forth (`--rides` trips) in its own thread, sending a chunk
every `--chunk-s` seconds of ride data; `--speed 1` paces chunks in real time, 0 = flat out.
Line labels (MAR, JER, SWI) are simulation corridors, not ZTM timetable lines.

  .venv/bin/python scripts/simulate_buses.py --dry-run                 # generate + score, no API
  .venv/bin/python scripts/simulate_buses.py --api http://localhost:8000 --rides 2
  .venv/bin/python scripts/simulate_buses.py --make-world              # rewrite sim_world.json
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
OFF_STREET_PENALTY = 3.0   # path search: edges of other streets cost 3x, so buses stay on their corridor

# Simulated bus corridors: stops in driving order, each snapped to the named street.
BUS_LINES = {
    "MAR": {"street": "Marszałkowska", "potholes": 5, "dark_lamps": 2, "stops": [
        ("pl. Bankowy", 21.0036, 52.2423), ("Królewska", 21.0065, 52.2384),
        ("Świętokrzyska", 21.0086, 52.2352), ("Centrum", 21.0120, 52.2301),
        ("Hoża", 21.0144, 52.2256), ("pl. Konstytucji", 21.0166, 52.2223),
        ("pl. Zbawiciela", 21.0182, 52.2196), ("pl. Unii Lubelskiej", 21.0215, 52.2139)]},
    "JER": {"street": "Aleje Jerozolimskie", "potholes": 5, "dark_lamps": 2, "stops": [
        ("pl. Zawiszy", 20.9857, 52.2241), ("Dw. Centralny", 21.0036, 52.2282),
        ("Centrum", 21.0120, 52.2301), ("rondo de Gaulle'a", 21.0218, 52.2319),
        ("Muzeum Narodowe", 21.0259, 52.2328), ("Most Poniatowskiego", 21.0322, 52.2341)]},
    "SWI": {"street": "Świętokrzyska", "potholes": 3, "dark_lamps": 1, "stops": [
        ("rondo ONZ", 20.9988, 52.2330), ("Emilii Plater", 21.0040, 52.2342),
        ("Marszałkowska", 21.0094, 52.2354), ("Mazowiecka", 21.0128, 52.2360),
        ("Nowy Świat", 21.0187, 52.2371)]},
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
    {"kind": "bump", "mode": "road", "line": "MAR", "street": "Marszałkowska", "lon": 21.011257, "lat": 52.230832,
     "amp": 7.5, "freq": 8.0, "anchor": "complaints issue 3: pothole, Marszałkowska near Centrum (22 reports)"},
]
DEMO_RIDES = [("tram17_day_01", 1, False), ("tram17_night_01", 2, True)]  # (name, seed, night) for seed_demo.py


# --------------------------------------------------------------------------- routes over the OSM road graph

@lru_cache(maxsize=1)
def road_graph(path: Path = GEOJSON):
    """Undirected graph of `road` segments: (node lon/lat, edge list, csr builder inputs)."""
    feats = [f for f in json.loads(Path(path).read_text(encoding="utf-8"))["features"] if f["properties"]["mode"] == "road"]
    nodes: dict[tuple[float, float], int] = {}

    def nid(c) -> int:
        return nodes.setdefault((round(c[0], 7), round(c[1], 7)), len(nodes))

    edges = []  # (a, b, length_m, street name, coords a->b)
    for f in feats:
        cs = [tuple(c) for c in f["geometry"]["coordinates"]]
        edges.append((nid(cs[0]), nid(cs[-1]), float(f["properties"]["length_m"]), f["properties"]["name"], cs))
    xy = np.array(list(nodes), dtype=float)
    return xy, edges


def _shortest(street: str, a: int, b: int) -> list[tuple[float, float]]:
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import dijkstra

    xy, edges = road_graph()
    n = len(xy)
    rows, cols, w = [], [], []
    for i, j, length, name, _ in edges:
        cost = max(length, 0.01) * (1.0 if name == street else OFF_STREET_PENALTY)
        rows += [i, j]
        cols += [j, i]
        w += [cost, cost]
    graph = coo_matrix((w, (rows, cols)), shape=(n, n)).tocsr()  # duplicates summed: fine, parallel edges rare
    _, pred = dijkstra(graph, indices=a, return_predecessors=True)
    if pred[b] < 0 and a != b:
        raise ValueError(f"{street}: no road path between nodes {a} and {b}")
    by_pair = {}
    for i, j, length, _, cs in edges:
        for key, coords in (((i, j), cs), ((j, i), cs[::-1])):
            if key not in by_pair or length < by_pair[key][0]:
                by_pair[key] = (length, coords)
    chain = [b]
    while chain[-1] != a:
        chain.append(int(pred[chain[-1]]))
    chain.reverse()
    out: list[tuple[float, float]] = [tuple(xy[a])]
    for i, j in zip(chain[:-1], chain[1:]):
        out += by_pair[(i, j)][1][1:]
    return out


def _snap(street: str, lon: float, lat: float) -> int:
    """Nearest graph node that is an end of a segment of `street`."""
    xy, edges = road_graph()
    cand = sorted({i for e in edges if e[3] == street for i in e[:2]})
    if not cand:
        raise ValueError(f"street {street!r} not in {GEOJSON.name}")
    kx = 111_320 * math.cos(math.radians(lat))
    d = ((xy[cand, 0] - lon) * kx) ** 2 + ((xy[cand, 1] - lat) * 110_540) ** 2
    return cand[int(np.argmin(d))]


def _dedupe(path: list[tuple[float, float]], min_m: float = 0.5) -> list[tuple[float, float]]:
    out = [path[0]]
    for p in path[1:]:
        if float(synth._haversine_m(out[-1][1], out[-1][0], p[1], p[0])) >= min_m:
            out.append(p)
    return out


@lru_cache(maxsize=None)
def bus_route_cfg(line: str) -> dict:
    """ROUTES-style config (mode, path, stops) for a simulated bus corridor."""
    spec = BUS_LINES[line]
    nodes = [_snap(spec["street"], lon, lat) for _, lon, lat in spec["stops"]]
    xy, _ = road_graph()
    path: list[tuple[float, float]] = [tuple(xy[nodes[0]])]
    for a, b in zip(nodes[:-1], nodes[1:]):
        path += _shortest(spec["street"], a, b)[1:]
    path = _dedupe(path)
    stops = [(name, *path_point(path, xy[n])) for (name, _, _), n in zip(spec["stops"], nodes)]
    stops[0], stops[-1] = (stops[0][0], *path[0]), (stops[-1][0], *path[-1])
    return {"mode": "road", "path": path, "stops": stops, "crossings": []}


def path_point(path, p) -> tuple[float, float]:
    """The path vertex closest to p (stops must lie on the path)."""
    arr = np.asarray(path)
    return tuple(arr[int(np.argmin(((arr - np.asarray(p)) ** 2).sum(axis=1)))])


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
    for line, spec in BUS_LINES.items():
        route = route_for("road", line)
        rng = np.random.default_rng([seed, sum(map(ord, line))])
        anchored = [route.locate(a["lon"], a["lat"])[0] for a in ANCHORS if a["mode"] == "road" and a["line"] == line]
        placed: list[float] = []
        for _ in range(20000):
            if len(placed) >= spec["potholes"]:
                break
            s = float(rng.uniform(60, route.length - 60))
            if np.min(np.abs(route.stop_s - s)) > 50 and all(abs(s - p) > 120 for p in placed + anchored):
                placed.append(s)
                lon, lat = route.at(s)
                defects.append({"kind": "bump", "mode": "road", "street": spec["street"], "line": line,
                                "lon": round(float(lon), 6), "lat": round(float(lat), 6),
                                "amp": round(float(rng.uniform(5.0, 9.5)), 2),
                                "freq": round(float(rng.uniform(6.0, 10.0)), 2)})
        # lamp detection needs the lit rhythm on both sides: keep broken lamps off the ends and stops
        lamps: list[float] = []
        for _ in range(20000):
            if len(lamps) >= spec["dark_lamps"]:
                break
            s = float(rng.uniform(200, route.length - 200))
            if np.min(np.abs(route.stop_s - s)) > 60 and all(abs(s - x) > 200 for x in lamps + placed + anchored):
                lamps.append(s)
        for s in lamps:
            lon, lat = route.at(s)
            defects.append({"kind": "dark_lamp", "mode": "road", "street": spec["street"], "line": line,
                            "lon": round(float(lon), 6), "lat": round(float(lat), 6)})
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
EVAL_VEHICLES = [("bus-MAR-01", "road", "MAR"), ("bus-JER-01", "road", "JER"),
                 ("bus-SWI-01", "road", "SWI"), ("tram-17-01", "tram", "17")]
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
        f"(bus MAR, JER, SWI; tram 17) x 2 directions x {seeds} seeds per condition. A detection counts if it is "
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
    """`bus-MAR-01` -> ("road", "MAR"); `tram-17-02` -> ("tram", "17"); None if not a known line."""
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
NEW_POTHOLE = {"id": "S5-NEW", "kind": "bump", "mode": "road", "line": "JER", "street": "Aleje Jerozolimskie",
               "lon": 21.015902, "lat": 52.230809, "amp": 8.0, "freq": 8.0}
HIDDEN_POTHOLE = {"id": "S5-REPORTED", "kind": "bump", "mode": "road", "line": "SWI", "street": "Świętokrzyska",
                  "lon": 21.016533, "lat": 52.236764, "amp": 7.5, "freq": 8.5}
SCENARIO_SEED = 5000
CITIZEN_TEXTS = [
    "Duża dziura w jezdni na Świętokrzyskiej przy Nowym Świecie, autobusy podskakują.",
    "Świętokrzyska koło Nowego Światu: wyrwa w asfalcie, niebezpiecznie dla rowerzystów.",
]


class Api:
    """Tiny JSON client for the scenarios (stdlib only, like the devices)."""

    def __init__(self, base: str, token: str | None = None):
        self.base, self.token = base.rstrip("/"), token

    def _req(self, method: str, path: str, data: bytes | None = None, ctype: str | None = None) -> dict:
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
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

    def post_form(self, path: str, fields: dict) -> dict:
        from urllib.parse import urlencode
        return self._req("POST", path, urlencode(fields).encode(), "application/x-www-form-urlencoded")


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
        self.say("Scenario 1: a NEW pothole opens on Aleje Jerozolimskie. Nobody has reported it.")
        print(f"    before: {describe(find_incident(self.api, NEW_POTHOLE))}")
        self.drive("bus-JER-01", extra=[NEW_POTHOLE])
        print(f"    after the first bus: {describe(find_incident(self.api, NEW_POTHOLE))}")
        self.drive("bus-JER-02", extra=[NEW_POTHOLE])
        print(f"    after a second bus:  {describe(find_incident(self.api, NEW_POTHOLE))}")
        r = self.api.post_form("/reports", {"text": "Nowa dziura na Alejach Jerozolimskich, uważajcie!",
                                            "lon": NEW_POTHOLE["lon"], "lat": NEW_POTHOLE["lat"],
                                            "contributor": "scenario-citizen-1"})
        print(f"    a citizen reports it later -> report joins incident #{r.get('incident_id')}")
        print(f"    now: {describe(find_incident(self.api, NEW_POTHOLE))}")

    def report_then_verify(self) -> None:
        self.say("Scenario 2: citizens report a pothole on Świętokrzyska; the next bus checks it.")

        def report_first(ride_s: float) -> None:  # the reports come in before the bus sets off
            t0 = datetime.now(timezone.utc).timestamp() - ride_s - 120
            self.api.post_json("/reports/bulk", {"reports": [
                {"text": text, "lon": HIDDEN_POTHOLE["lon"], "lat": HIDDEN_POTHOLE["lat"], "source": "web",
                 "created_at": datetime.fromtimestamp(t0 + 30 * k, timezone.utc).isoformat()}
                for k, text in enumerate(CITIZEN_TEXTS)]})
            print(f"    after {len(CITIZEN_TEXTS)} reports: {describe(find_incident(self.api, HIDDEN_POTHOLE))}")

        self.drive("bus-SWI-01", extra=[HIDDEN_POTHOLE], before_send=report_first)
        print(f"    after the next bus:  {describe(find_incident(self.api, HIDDEN_POTHOLE))}")
        self.drive("bus-SWI-02", extra=[HIDDEN_POTHOLE])
        print(f"    after another bus:   {describe(find_incident(self.api, HIDDEN_POTHOLE))}")

    def repair(self) -> None:
        self.say("Scenario 3: the Jerozolimskie pothole is REPAIRED; buses keep driving over the spot.")
        if find_incident(self.api, NEW_POTHOLE) is None:
            print("    (scenario 1 has not run on this database yet: running it first)")
            self.new_pothole()
        before = find_incident(self.api, NEW_POTHOLE)
        print(f"    before: {describe(before)}; road health there {segment_health(self.api, NEW_POTHOLE)}")
        for dev in ("bus-JER-01", "bus-JER-02", "bus-JER-01"):
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
                 "DEVICE_KEYS=bus-MAR-01:<secret>,tram-17-01:<secret>")
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
