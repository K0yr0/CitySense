#!/usr/bin/env python
"""Deterministic synthetic tram ride: 100 Hz accelerometer + 1 Hz GPS (+ night lux), combined CSV.

Writes data/demo/<name>.csv (columns = backend.sensor.ingest.SAMPLE_COLUMNS, readable by
load_sensor_logger) and data/demo/<name>_truth.csv (kind, lon, lat) listing every injected
anomaly: kind "bump" (track defect) and, with --night, kind "dark_gap" (broken streetlight).

The *world* (bump positions/strength, rail joints, lamps, broken lamps) is fixed per line by
WORLD_SEED, so every ride on the same line hits the same defects at the same coordinates (this
is what lets fusion's ">= 2 rides" rule fire). `--seed` only changes the ride itself: phone pose,
vibration noise, cruise speeds, dwell times, red lights, door slams and GPS error.

  .venv/bin/python scripts/synth_ride.py --name tram17_day_01 --seed 1
  .venv/bin/python scripts/synth_ride.py --name tram17_night_01 --seed 2 --night
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.signal import butter, sosfilt

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from backend.sensor.ingest import SAMPLE_COLUMNS, _haversine_m  # noqa: E402

DEMO_DIR = REPO_ROOT / "data" / "demo"
FS = 100                  # Hz
G = 9.81
WORLD_SEED = 1717         # fixed: same defects/lamps for every ride on a line
ACC, DEC = 1.0, 1.2       # tram acceleration / braking, m/s²
BOGIE_M = 9.0             # second bogie hits the same defect this many metres later
LAMP_SPACING_M = 33.0
N_BROKEN_LAMPS = 4

# Tram line 17 along Marszałkowska, Plac Bankowy -> Plac Unii Lubelskiej (southbound).
# "path" follows the OpenStreetMap railway=tram geometry of data/osm/segments_demo.geojson
# (shortest path over the tram tracks, simplified to 0.5 m), so the GPS points map-match onto
# `tram` segments. Stops are snapped onto the path; the first and last stop are its end points.
ROUTES = {
    "17": {
        "mode": "tram",
        "path": [  # (lon, lat)
            (21.002644, 52.243250), (21.003677, 52.242454), (21.003802, 52.242349), (21.003931, 52.242204),
            (21.004159, 52.241844), (21.004277, 52.241690), (21.004441, 52.241521), (21.004681, 52.241306),
            (21.004787, 52.241159), (21.004831, 52.241059), (21.004858, 52.240908), (21.004855, 52.240583),
            (21.004873, 52.240392), (21.004914, 52.240211), (21.004966, 52.240053), (21.005108, 52.239745),
            (21.005339, 52.239422), (21.005614, 52.239135), (21.005820, 52.238962), (21.005995, 52.238837),
            (21.006435, 52.238576), (21.006510, 52.238511), (21.006572, 52.238427), (21.014693, 52.224845),
            (21.015451, 52.223552), (21.015514, 52.223459), (21.015589, 52.223374), (21.015848, 52.223145),
            (21.015984, 52.222986), (21.017879, 52.219775), (21.017978, 52.219686), (21.018095, 52.219493),
            (21.020856, 52.214840), (21.021389, 52.213937), (21.021428, 52.213853), (21.021469, 52.213717),
            (21.021483, 52.213584), (21.021467, 52.213439), (21.021435, 52.213336),
        ],
        "stops": [  # (name, lon, lat), in driving order, on the path
            ("pl. Bankowy", 21.002644, 52.243250),
            ("Królewska", 21.006028, 52.238818),
            ("Świętokrzyska", 21.008437, 52.235308),
            ("Centrum", 21.011621, 52.229982),
            ("Hoża", 21.014213, 52.225648),
            ("pl. Konstytucji", 21.016268, 52.222505),
            ("pl. Zbawiciela", 21.017954, 52.219708),
            ("pl. Unii Lubelskiej", 21.021435, 52.213336),
        ],
        "crossings": ["Centrum", "pl. Zbawiciela"],  # tram-track crossings just after these stops
    },
}
DEFAULT_START = {False: "2026-09-29T07:10:00Z", True: "2026-09-30T19:40:00Z"}  # 09:10 / 21:40 Warsaw


# --------------------------------------------------------------------------- geometry

class Route:
    def __init__(self, line: str):
        if line not in ROUTES:
            raise ValueError(f"unknown line {line!r}; known: {sorted(ROUTES)}")
        cfg = ROUTES[line]
        self.names = [s[0] for s in cfg["stops"]]
        path = cfg.get("path") or [(lon, lat) for _, lon, lat in cfg["stops"]]
        self.lon = np.array([p[0] for p in path], dtype=float)
        self.lat = np.array([p[1] for p in path], dtype=float)
        seg = _haversine_m(self.lat[:-1], self.lon[:-1], self.lat[1:], self.lon[1:])
        self.vertex_s = np.concatenate([[0.0], np.cumsum(seg)])
        self.length = float(self.vertex_s[-1])
        self.stop_s = np.array([self.project(lon, lat) for _, lon, lat in cfg["stops"]])
        if self.stop_s[0] > 0.01 or self.stop_s[-1] < self.length - 0.01 or np.any(np.diff(self.stop_s) <= 0):
            raise ValueError(f"line {line}: stops must run along the path from its first to its last point")
        self.stop_s[0], self.stop_s[-1] = 0.0, self.length  # the ride starts and ends at a stop
        self.crossing_s = [self.stop_s[self.names.index(n)] + 30.0 for n in cfg["crossings"]]

    def project(self, lon: float, lat: float) -> float:
        """Along-route distance (metres) of the path point closest to (lon, lat)."""
        kx = 111_320 * np.cos(np.radians(self.lat.mean()))  # local equirectangular metres
        x, y = (self.lon - lon) * kx, (self.lat - lat) * 110_540
        dx, dy = np.diff(x), np.diff(y)
        seg2 = dx ** 2 + dy ** 2
        t = np.clip(-(x[:-1] * dx + y[:-1] * dy) / np.where(seg2 > 0, seg2, 1.0), 0.0, 1.0)
        d2 = (x[:-1] + t * dx) ** 2 + (y[:-1] + t * dy) ** 2
        i = int(np.argmin(d2))
        return float(self.vertex_s[i] + t[i] * (self.vertex_s[i + 1] - self.vertex_s[i]))

    def at(self, s) -> tuple[np.ndarray, np.ndarray]:
        """(lon, lat) at along-route distance s (metres)."""
        return np.interp(s, self.vertex_s, self.lon), np.interp(s, self.vertex_s, self.lat)


def _world(route: Route, n_bumps: int) -> dict:
    """Fixed physical world of a line. Bumps are drawn sequentially, so the first k bumps are
    identical for any n_bumps >= k; every element uses its own RNG stream."""
    rng = np.random.default_rng([WORLD_SEED, 1])
    bumps: list[tuple[float, float, float]] = []  # (s, amplitude m/s² at 30 km/h, ring freq Hz)
    for _ in range(20000):
        if len(bumps) >= n_bumps:
            break
        s, amp, freq = rng.uniform(80, route.length - 80), rng.uniform(4.5, 9.5), rng.uniform(7, 11)
        if np.min(np.abs(route.stop_s - s)) > 70 and all(abs(s - b[0]) > 120 for b in bumps):
            bumps.append((s, amp, freq))
    if len(bumps) < n_bumps:
        raise ValueError(f"route too short for {n_bumps} bumps (placed {len(bumps)})")

    rng = np.random.default_rng([WORLD_SEED, 2])  # rail joints: small clicks, below detection floor
    joints = np.cumsum(rng.uniform(40, 90, size=int(route.length / 40) + 2))
    joints = joints[joints < route.length]
    joint_amp = rng.uniform(0.4, 0.9, size=joints.size)

    rng = np.random.default_rng([WORLD_SEED, 3])  # streetlights every ~33 m, a few broken
    lamps = np.arange(10.0, route.length, LAMP_SPACING_M)
    lamps = lamps + rng.uniform(-2.0, 2.0, size=lamps.size)
    power = rng.uniform(14, 22, size=lamps.size)  # lux under the lamp, measured inside the tram
    broken: list[int] = []
    while len(broken) < N_BROKEN_LAMPS:
        k = int(rng.integers(3, lamps.size - 3))
        if all(abs(k - b) > 2 for b in broken):
            broken.append(k)
    return {"bumps": bumps, "joints": joints, "joint_amp": joint_amp,
            "lamps": lamps, "lamp_power": power, "broken": sorted(broken)}


# --------------------------------------------------------------------------- ride simulation

def _bandnoise(rng: np.random.Generator, n: int, lo: float, hi: float) -> np.ndarray:
    sos = butter(2, [lo, hi], btype="band", fs=FS, output="sos")
    x = sosfilt(sos, rng.normal(size=n + 2 * FS))[2 * FS:]  # drop filter warm-up
    return x / (x.std() or 1.0)


def _add_pulse(x: np.ndarray, t0: float, amp: float, freq: float, tau: float) -> None:
    """Damped oscillation starting at t0 (impact on the car body)."""
    i0 = int(round(t0 * FS))
    if i0 < 0 or i0 >= x.size:
        return
    tt = np.arange(int(6 * tau * FS)) / FS
    pulse = amp * np.exp(-tt / tau) * np.cos(2 * np.pi * freq * tt)
    m = min(pulse.size, x.size - i0)
    x[i0:i0 + m] += pulse[:m]


def _speed_profile(route: Route, world: dict, rng: np.random.Generator):
    """Distance-based kinematics with stops and red lights -> (t, s(t), v(t), dwell windows)."""
    n_red, red = int(rng.integers(1, 3)), []  # 1-2 red lights, away from stops and defects
    for _ in range(1000):
        if len(red) >= n_red:
            break
        s = rng.uniform(100, route.length - 100)
        if np.min(np.abs(route.stop_s - s)) > 60 and all(abs(s - b[0]) > 80 for b in world["bumps"]):
            red.append(s)
    halts = sorted([(s, "stop") for s in route.stop_s] + [(s, "red") for s in red])

    ds = 0.1
    s_grid = np.arange(0.0, route.length + ds, ds)
    s_grid[-1] = route.length
    v = np.zeros_like(s_grid)
    for (a, _), (b, _) in zip(halts[:-1], halts[1:]):
        m = (s_grid >= a) & (s_grid <= b)
        vmax = rng.uniform(30, 45) / 3.6
        v[m] = np.minimum(vmax, np.minimum(np.sqrt(2 * ACC * (s_grid[m] - a)), np.sqrt(2 * DEC * (b - s_grid[m]))))
    v = np.maximum(v, 0.3)  # creep speed avoids infinite time at the halts
    t_move = np.concatenate([[0.0], np.cumsum(ds / (0.5 * (v[1:] + v[:-1])))])

    shift = np.zeros_like(s_grid)
    knots_t, knots_s, dwells = [], [], []
    for i, (s, kind) in enumerate(halts):
        idx = min(int(np.searchsorted(s_grid, s)), s_grid.size - 1)
        if i == 0:
            d = 8.0
        elif i == len(halts) - 1:
            d = 6.0
        else:
            d = rng.uniform(15, 35) if kind == "stop" else rng.uniform(10, 40)
        arrive = t_move[idx] + shift[idx]
        knots_t += [arrive, arrive + d]
        knots_s += [s_grid[idx], s_grid[idx]]
        dwells.append((arrive, arrive + d, kind))
        shift[idx + 1:] += d
    t_all = np.concatenate([t_move + shift, knots_t])
    s_all = np.concatenate([s_grid, knots_s])
    order = np.lexsort((s_all, t_all))
    t_end = float(t_all.max())
    t = np.arange(0.0, t_end, 1.0 / FS)
    s_t = np.interp(t, t_all[order], s_all[order])
    v_t = np.gradient(s_t, 1.0 / FS)
    return t, s_t, v_t, dwells


def generate_ride(*, line: str = "17", seed: int = 1, night: bool = False, bumps: int = 6,
                  start: str | datetime | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Simulate one ride. Returns (samples with SAMPLE_COLUMNS, truth with kind/lon/lat)."""
    route = Route(line)
    world = _world(route, bumps)
    rng = np.random.default_rng([seed, 17])
    t, s_t, v_t, dwells = _speed_profile(route, world, rng)
    n = t.size
    speed_scale = np.minimum(v_t / 8.33, 2.0)  # vibration grows with speed (1.0 at 30 km/h)

    def t_at(s: float) -> float:
        return float(np.interp(s, s_t, t))

    def hit_scale(tt: float) -> float:
        return float(np.clip(np.interp(tt, t, v_t) / 8.33, 0.5, 2.0))

    # Vertical specific force on the car body (vehicle frame, m/s² on top of gravity).
    vert = _bandnoise(rng, n, 2.0, 25.0) * (0.06 + 0.20 * speed_scale)   # running vibration
    vert += _bandnoise(rng, n, 0.4, 1.4) * 0.25 * speed_scale             # body bounce (< high-pass)
    for s_b, amp, freq in world["bumps"]:                                 # injected defects
        tb = t_at(s_b)
        a = amp * hit_scale(tb)
        _add_pulse(vert, tb, a, freq, 0.08)
        _add_pulse(vert, tb + BOGIE_M / max(np.interp(tb, t, v_t), 1.0), 0.5 * a, freq, 0.08)
    for s_j, amp in zip(world["joints"], world["joint_amp"]):            # rail joints
        _add_pulse(vert, t_at(s_j), amp * hit_scale(t_at(s_j)), 14.0, 0.04)
    for s_c in route.crossing_s:                                          # track crossings: clatter
        for k in range(4):
            tc = t_at(s_c + 2.0 * k)
            _add_pulse(vert, tc, 1.2 * hit_scale(tc), 12.0, 0.05)
    for t0, t1, kind in dwells[1:-1]:                                     # door slams while standing
        if kind == "stop" and t1 - t0 > 4:
            for td in rng.uniform(t0 + 1.0, t1 - 2.0, size=int(rng.integers(1, 4))):
                _add_pulse(vert, td, rng.uniform(2.0, 4.5), 6.0, 0.1)

    v_smooth = np.convolve(v_t, np.ones(FS // 2) / (FS // 2), mode="same")
    a_long = np.gradient(v_smooth, 1.0 / FS) + 0.3 * _bandnoise(rng, n, 1.0, 20.0) * (0.06 + 0.2 * speed_scale)
    a_lat = 0.4 * _bandnoise(rng, n, 0.5, 20.0) * (0.06 + 0.2 * speed_scale)
    f_vehicle = np.column_stack([a_long, a_lat, G + vert])

    yaw, pitch, roll = rng.uniform(0, 2 * np.pi), rng.uniform(-1.0, 1.0), rng.uniform(-0.7, 0.7)
    rz = np.array([[np.cos(yaw), -np.sin(yaw), 0], [np.sin(yaw), np.cos(yaw), 0], [0, 0, 1]])
    ry = np.array([[np.cos(pitch), 0, np.sin(pitch)], [0, 1, 0], [-np.sin(pitch), 0, np.cos(pitch)]])
    rx = np.array([[1, 0, 0], [0, np.cos(roll), -np.sin(roll)], [0, np.sin(roll), np.cos(roll)]])
    acc = f_vehicle @ (rz @ ry @ rx) + rng.normal(0, 0.015, size=(n, 3))  # arbitrary phone pose

    # 1 Hz GPS with correlated (AR(1), sigma ~2.5 m) error, interpolated onto the 100 Hz timeline.
    t_fix = np.arange(rng.uniform(0, 1), t[-1], 1.0)
    lon_f, lat_f = route.at(np.interp(t_fix, t, s_t))
    err = np.zeros((t_fix.size, 2))
    err[0] = rng.normal(0, 2.5, size=2)
    for k in range(1, t_fix.size):
        err[k] = 0.85 * err[k - 1] + rng.normal(0, 2.5 * np.sqrt(1 - 0.85 ** 2), size=2)
    lat_f = lat_f + err[:, 0] / 110_540
    lon_f = lon_f + err[:, 1] / (111_320 * np.cos(np.radians(52.23)))
    spd_f = np.abs(np.interp(t_fix, t, v_t) + rng.normal(0, 0.15, size=t_fix.size)) * 3.6

    truth = [("bump", *route.at(s_b)) for s_b, _, _ in world["bumps"]]
    lux = np.full(n, np.nan)
    if night:  # streetlight saw-tooth: one bell-shaped peak per lamp, broken lamps missing
        lux = 2.0 + 0.8 * _bandnoise(rng, n, 0.02, 0.2)  # shop windows / ambient
        for k, (s_l, p) in enumerate(zip(world["lamps"], world["lamp_power"])):
            if k in world["broken"]:
                truth.append(("dark_gap", *route.at(s_l)))
                continue
            lux += p / (1 + ((s_t - s_l) / 8.0) ** 2) ** 1.5
        lux = np.clip(lux * (1 + rng.normal(0, 0.03, size=n)), 0.1, None)
        lux = np.round(lux[(np.arange(n) // 20) * 20], 1)  # light sensor reports at ~5 Hz

    start_ts = pd.Timestamp(start or DEFAULT_START[night])
    start_ts = start_ts.tz_localize("UTC") if start_ts.tzinfo is None else start_ts.tz_convert("UTC")
    samples = pd.DataFrame({
        "t": np.round(t, 2),
        "ts": start_ts + pd.to_timedelta(np.round(t * 1000).astype("int64"), unit="ms"),
        "ax": np.round(acc[:, 0], 3), "ay": np.round(acc[:, 1], 3), "az": np.round(acc[:, 2], 3),
        "lat": np.round(np.interp(t, t_fix, lat_f), 6), "lon": np.round(np.interp(t, t_fix, lon_f), 6),
        "speed_kmh": np.round(np.interp(t, t_fix, spd_f), 2), "lux": lux,
    })[SAMPLE_COLUMNS]
    truth_df = pd.DataFrame(truth, columns=["kind", "lon", "lat"]).round({"lon": 6, "lat": 6})
    return samples, truth_df


def write_ride(name: str, out_dir: str | Path = DEMO_DIR, **kwargs) -> tuple[Path, Path]:
    """generate_ride(**kwargs) -> <out_dir>/<name>.csv and <name>_truth.csv."""
    samples, truth = generate_ride(**kwargs)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = samples.copy()
    out["ts"] = out["ts"].dt.strftime("%Y-%m-%dT%H:%M:%S.%f").str[:-3] + "Z"
    csv_path, truth_path = out_dir / f"{name}.csv", out_dir / f"{name}_truth.csv"
    out.to_csv(csv_path, index=False, na_rep="")
    truth.to_csv(truth_path, index=False)
    return csv_path, truth_path


def score_detections(found: pd.DataFrame, truth: pd.DataFrame, kind: str = "bump",
                     radius_m: float = 20.0) -> dict:
    """Precision/recall of detections (lon/lat columns) vs truth rows of `kind` within radius_m."""
    tr = truth[truth["kind"] == kind]
    if found.empty or tr.empty:
        return {"precision": 1.0 if found.empty else 0.0, "recall": 1.0 if tr.empty else 0.0,
                "found": len(found), "truth": len(tr)}
    d = _haversine_m(found["lat"].to_numpy()[:, None], found["lon"].to_numpy()[:, None],
                     tr["lat"].to_numpy()[None, :], tr["lon"].to_numpy()[None, :])
    hit = d <= radius_m
    return {"precision": float(hit.any(axis=1).mean()), "recall": float(hit.any(axis=0).mean()),
            "found": len(found), "truth": len(tr)}


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--name", required=True, help="output basename, e.g. tram17_day_01")
    ap.add_argument("--line", default="17", choices=sorted(ROUTES))
    ap.add_argument("--seed", type=int, default=1, help="ride seed (world stays fixed)")
    ap.add_argument("--night", action="store_true", help="add streetlight lux with broken lamps")
    ap.add_argument("--bumps", type=int, default=6, help="number of injected track defects")
    ap.add_argument("--start", default=None, help="ride start, ISO-8601 UTC")
    ap.add_argument("--out-dir", default=str(DEMO_DIR))
    ap.add_argument("--check", action="store_true", help="run bump detection and print precision/recall")
    args = ap.parse_args(argv)

    csv_path, truth_path = write_ride(args.name, args.out_dir, line=args.line, seed=args.seed,
                                      night=args.night, bumps=args.bumps, start=args.start)
    print(f"wrote {csv_path} and {truth_path}")
    if args.check:
        from backend.sensor.detect import detect_bumps
        from backend.sensor.ingest import load_sensor_logger
        found = detect_bumps(load_sensor_logger(csv_path))
        print("bump detection:", score_detections(found, pd.read_csv(truth_path)))


if __name__ == "__main__":
    main()
