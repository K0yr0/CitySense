"""Tests for the sensor-geo modules: dark gaps (lights), map matching, ride pipeline."""
from __future__ import annotations

import json
from datetime import datetime
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from backend import db
from backend.models import EvidenceIn, IssueType, Mode, Source
from backend.sensor import lights, mapmatch, pipeline
from backend.sensor.mapmatch import haversine_m

LON0, LAT0 = 21.0, 52.23
M_PER_DEG_LAT = 111_320.0
M_PER_DEG_LON = M_PER_DEG_LAT * np.cos(np.radians(LAT0))
BEARING = np.radians(60)
T0 = pd.Timestamp("2026-10-01T22:00:00Z")
TRAM_BASE, ROAD_BASE = 1, 10_000  # fake segment ids: base + 25 m slot along the test line
CONN = object()


# ----------------------------------------------------------------------------- helpers

def _to_lonlat(dist_m, offset_m=0.0):
    """Point `dist_m` along a straight test line, `offset_m` to its left."""
    dist_m, offset_m = np.asarray(dist_m, float), np.asarray(offset_m, float)
    east = dist_m * np.sin(BEARING) - offset_m * np.cos(BEARING)
    north = dist_m * np.cos(BEARING) + offset_m * np.sin(BEARING)
    return LON0 + east / M_PER_DEG_LON, LAT0 + north / M_PER_DEG_LAT


def _segment_for(lon, lat, mode, max_dist_m):
    """Fake PostGIS: one 25 m segment per slot along the line, separate ids for tram/road."""
    east, north = (lon - LON0) * M_PER_DEG_LON, (lat - LAT0) * M_PER_DEG_LAT
    along = east * np.sin(BEARING) + north * np.cos(BEARING)
    cross = -east * np.cos(BEARING) + north * np.sin(BEARING)
    if abs(cross) > max_dist_m or along < 0:
        return None
    return (TRAM_BASE if mode == "tram" else ROAD_BASE) + int(along // 25)


def _night_ride(*, n_lamps=80, spacing=30.0, missing=(), dim=(), fs=20, seed=0,
                gps_sd=1.5, bumps_m=()) -> tuple[pd.DataFrame, np.ndarray]:
    """SAMPLE_COLUMNS ride under a lamp row (lamp profile ~ cos^3 law, 6 m above the sensor).

    Speed varies 17-47 km/h with a 10 s stop; GPS = noisy 1 Hz fixes interpolated onto the
    samples, like ingest does. Returns (df, lon/lat of every removed or dimmed lamp).
    """
    rng = np.random.default_rng(seed)
    lamps = 20 + np.arange(n_lamps) * spacing + rng.uniform(-2, 2, n_lamps)
    amp = rng.uniform(30, 50, n_lamps)
    amp[list(missing)] = 0.0
    amp[list(dim)] *= 0.15
    total = lamps[-1] + 30
    t = np.arange(0, 3 * total, 1 / fs)
    speed = 32 + 15 * np.sin(2 * np.pi * t / 40)
    speed[(t > 30) & (t < 40)] = 0.0
    dist = np.cumsum(speed / 3.6 / fs)
    keep = dist <= total
    t, speed, dist = t[keep], speed[keep], dist[keep]
    lux = 2.0 + (amp * (36 / (36 + (dist[:, None] - lamps) ** 2)) ** 1.5).sum(axis=1)
    lux += rng.normal(0, 0.4, len(t))

    fix_t = np.arange(0, t[-1] + 1)
    fix_lon, fix_lat = _to_lonlat(np.interp(fix_t, t, dist))
    fix_lon = fix_lon + rng.normal(0, gps_sd, len(fix_t)) / M_PER_DEG_LON
    fix_lat = fix_lat + rng.normal(0, gps_sd, len(fix_t)) / M_PER_DEG_LAT

    az = 9.81 + rng.normal(0, 0.05, len(t))
    width = max(2, int(0.04 * fs))
    for b in bumps_m:  # 40 ms half-sine kicks of 8 m/s²
        i = int(np.argmin(np.abs(dist - b)))
        az[i:i + width] += 8 * np.sin(np.pi * np.arange(width) / width)
    df = pd.DataFrame({
        "t": t, "ts": T0 + pd.to_timedelta(t, unit="s"),
        "ax": rng.normal(0, 0.05, len(t)), "ay": rng.normal(0, 0.05, len(t)), "az": az,
        "lat": np.interp(t, fix_t, fix_lat), "lon": np.interp(t, fix_t, fix_lon),
        "speed_kmh": speed, "lux": lux,
    })
    gone = sorted(set(missing) | set(dim))
    return df, np.column_stack(_to_lonlat(lamps[gone]))


def _nearest_dist(gaps: pd.DataFrame, truth: np.ndarray) -> np.ndarray:
    """Matrix of distances (m): detected gap x true position."""
    return haversine_m(gaps["lon"].to_numpy()[:, None], gaps["lat"].to_numpy()[:, None],
                       truth[None, :, 0], truth[None, :, 1])


@pytest.fixture
def fake_db(monkeypatch):
    """Replace every backend.db function the pipeline touches; record the calls."""
    rec = SimpleNamespace(calls=[], rides=[], nearest=[], ride_segments=[], evidence=[])

    def insert_ride(conn, **kw):
        rec.calls.append("insert_ride")
        rec.rides.append(kw)
        return 7

    def nearest_segments(conn, coords, mode=None, max_dist_m=20):
        rec.calls.append("nearest_segments")
        rec.nearest.append({"coords": list(coords), "mode": mode, "max_dist_m": max_dist_m})
        return [_segment_for(lon, lat, mode, max_dist_m) for lon, lat in coords]

    def upsert_ride_segments(conn, ride_id, rows):
        rec.calls.append("upsert_ride_segments")
        rec.ride_segments.append((ride_id, rows))

    def insert_evidence(conn, ev):
        rec.calls.append("insert_evidence")
        rec.evidence.append(ev)
        return len(rec.evidence)

    def recompute_segment_health(conn):
        rec.calls.append("recompute_segment_health")

    for fn in (insert_ride, nearest_segments, upsert_ride_segments, insert_evidence, recompute_segment_health):
        monkeypatch.setattr(db, fn.__name__, fn)
    return rec


# ----------------------------------------------------------------------------- lights

@pytest.mark.parametrize("spacing,seed", [(25, 0), (32, 1), (40, 2), (30, 3)])
def test_dark_gaps_precision_recall_on_saw_tooth(spacing, seed):
    missing, dim = (10, 25, 40, 41, 60), (52,)  # 40+41: two dead lamps in a row; 52: 15 % brightness
    df, truth = _night_ride(spacing=spacing, missing=missing, dim=dim, seed=seed)
    gaps = lights.find_dark_gaps(df)

    assert list(gaps.columns) == lights.GAP_COLUMNS
    dist = _nearest_dist(gaps, truth)
    precision = (dist.min(axis=1) <= 8).mean()
    recall = (dist.min(axis=0) <= 8).mean()
    assert precision >= 0.9 and recall >= 0.8, (precision, recall)

    assert gaps["severity"].between(0, 1).all()
    assert (gaps["observed_lux"] < 0.3 * gaps["expected_lux"]).all()
    assert gaps["ts"].between(df["ts"].min(), df["ts"].max()).all()
    assert gaps["ts"].dt.tz is not None
    # two consecutive dead lamps are worse than a single one
    sev_at = lambda j: gaps["severity"].to_numpy()[np.argmin(dist[:, j])]  # noqa: E731
    order = sorted(set(missing) | set(dim))
    assert sev_at(order.index(40)) > sev_at(order.index(10))


def test_dark_gaps_ignores_long_unlit_stretch():
    """10 lamps missing in a row is a park or junction, not broken lamps; lamp 10 still counts."""
    df, truth = _night_ride(missing=(10, *range(30, 40)), seed=4)
    gaps = lights.find_dark_gaps(df)
    assert len(gaps) == 1
    assert _nearest_dist(gaps, truth[:1]).min() <= 8


@pytest.mark.parametrize("case", ["daytime", "no_lux_column", "nan_lux", "unlit_street", "random_noise"])
def test_dark_gaps_empty_without_regular_night_rhythm(case):
    df, _ = _night_ride(missing=(10, 25), seed=5)
    rng = np.random.default_rng(5)
    if case == "daytime":
        df["lux"] += 5000.0
    elif case == "no_lux_column":
        df = df.drop(columns="lux")
    elif case == "nan_lux":
        df["lux"] = np.nan
    elif case == "unlit_street":
        df["lux"] = 2.0 + rng.normal(0, 0.4, len(df))
    else:
        df["lux"] = np.convolve(rng.gamma(2, 3, len(df)), np.ones(40) / 40, mode="same")
    gaps = lights.find_dark_gaps(df)
    assert gaps.empty and list(gaps.columns) == lights.GAP_COLUMNS


def test_dark_gaps_handles_empty_frame():
    assert lights.find_dark_gaps(pd.DataFrame(columns=["t", "ts", "lat", "lon", "speed_kmh", "lux"])).empty


# ----------------------------------------------------------------------------- mapmatch

def test_match_points_dedupes_and_maps_back(fake_db):
    base_lon, base_lat = _to_lonlat([10.0, 60.0, 110.0])
    far_lon, far_lat = _to_lonlat(60.0, offset_m=200.0)  # off the network
    lons = np.r_[np.repeat(base_lon, 40), far_lon, np.nan, base_lon[0]]
    lats = np.r_[np.repeat(base_lat, 40), far_lat, 52.0, np.nan]
    lons[:120] += np.random.default_rng(0).uniform(-2e-6, 2e-6, 120)  # sub-1e-5° jitter

    seg = mapmatch.match_points(CONN, lons, lats, Mode.TRAM, max_dist_m=15)

    assert fake_db.calls == ["nearest_segments"]
    call = fake_db.nearest[0]
    assert call["mode"] == "tram" and call["max_dist_m"] == 15
    assert len(call["coords"]) == 4  # 3 track points + the far one; NaNs never reach the DB
    assert seg.dtype == object and len(seg) == len(lons)
    expected = [_segment_for(lon, lat, "tram", 15) for lon, lat in zip(base_lon, base_lat)]
    assert list(seg[:120]) == list(np.repeat(expected, 40))
    assert seg[120] is None and seg[121] is None and seg[122] is None
    assert all(isinstance(s, int) for s in seg[:120])


def test_match_points_without_valid_coords_skips_db(fake_db):
    seg = mapmatch.match_points(CONN, [np.nan, np.nan], [52.2, np.nan], "road")
    assert list(seg) == [None, None] and fake_db.calls == []


# ----------------------------------------------------------------------------- pipeline

def _straight_ride(n=400, fs=10) -> pd.DataFrame:
    """36 km/h along the test line: sample i is i metres from the start."""
    t = np.arange(n) / fs
    lon, lat = _to_lonlat(np.arange(n, dtype=float))
    df = pd.DataFrame({"t": t, "ts": T0 + pd.to_timedelta(t, unit="s"), "ax": 0.0, "ay": 0.0, "az": 9.81,
                       "lat": lat, "lon": lon, "speed_kmh": 36.0, "lux": np.nan})
    df.loc[100, ["lon", "lat"]] = _to_lonlat(100.0, offset_m=25.0)   # off the 20 m match radius, near track
    df.loc[150, ["lon", "lat"]] = _to_lonlat(150.0, offset_m=300.0)  # GPS glitch
    return df


@pytest.mark.parametrize("mode,issue", [("tram", IssueType.TRAM_TRACK), (Mode.ROAD, IssueType.ROAD_DAMAGE)])
def test_process_ride_contract(fake_db, monkeypatch, mode, issue):
    df = _straight_ride()
    seen = {}

    def highpass(frame, fs=None, cutoff_hz=1.5):
        seen["hp_len"] = len(frame)
        return np.zeros(len(frame))

    def segment_pass_stats(frame, hp, seg_ids):
        seen["seg_ids"] = seg_ids
        return [{"segment_id": s, "rms": 0.1, "samples": 10, "passed_at": T0.to_pydatetime()}
                for s in dict.fromkeys(x for x in seg_ids if x is not None)]

    def detect_bumps(frame, fs=None):
        rows = [frame.iloc[i] for i in (50, 100, 150)]
        return pd.DataFrame({
            "t": [r.t + 0.02 for r in rows], "ts": [r.ts for r in rows],
            "lat": [r.lat for r in rows], "lon": [r.lon for r in rows],
            "speed_kmh": [36.0, np.nan, 36.0], "raw_peak": [3.2, 2.0, 9.0], "severity": [0.6, 0.4, 1.3],
            "signal": [[0.0, 1.5, np.nan, -0.5]] * 3, "signal_fs": [100] * 3, "peak_index": [1] * 3,
        })

    def find_dark_gaps(frame, min_spacing_m=20, max_spacing_m=60):
        lon, lat = _to_lonlat([210.0, 235.0], offset_m=12.0)
        return pd.DataFrame({"lon": lon, "lat": lat, "ts": [T0 + pd.Timedelta(seconds=20)] * 2,
                             "expected_lux": [40.0, 38.5], "observed_lux": [3.0, 2.5], "severity": [0.7, 0.7]})

    monkeypatch.setattr(pipeline.detect, "highpass", highpass)
    monkeypatch.setattr(pipeline.detect, "detect_bumps", detect_bumps)
    monkeypatch.setattr(pipeline.track_score, "segment_pass_stats", segment_pass_stats)
    monkeypatch.setattr(pipeline.lights, "find_dark_gaps", find_dark_gaps)

    out = pipeline.process_ride(CONN, df, vehicle_line="17", mode=mode, device_hash="abc", source_file="r.csv")

    # orchestration order and the ride row
    assert fake_db.calls[0] == "insert_ride" and fake_db.calls[-1] == "recompute_segment_health"
    assert fake_db.calls.count("recompute_segment_health") == 1
    ride = fake_db.rides[0]
    assert ride == {"vehicle_line": "17", "mode": str(mode), "started_at": T0.to_pydatetime(),
                    "ended_at": df["ts"].iloc[-1].to_pydatetime(), "device_hash": "abc", "source_file": "r.csv"}
    assert seen["hp_len"] == len(df)
    seg_ids = seen["seg_ids"]
    assert seg_ids.dtype == object and len(seg_ids) == len(df)
    base = TRAM_BASE if str(mode) == "tram" else ROAD_BASE
    assert base <= seg_ids[50] < base + 16 and seg_ids[100] is None and seg_ids[150] is None
    assert fake_db.nearest[0]["mode"] == str(mode) and 300 < len(fake_db.nearest[0]["coords"]) <= len(df)
    ride_id, rows = fake_db.ride_segments[0]
    assert ride_id == 7 and len(rows) == out["segments_covered"] == 16

    # evidence: bump at 50 (matched), bump at 100 (unmatched but near track), glitch at 150 dropped
    ev = fake_db.evidence
    assert all(isinstance(e, EvidenceIn) and e.source == Source.SENSOR and e.ride_id == 7 for e in ev)
    bumps = [e for e in ev if e.type == issue]
    lamps = [e for e in ev if e.type == IssueType.STREETLIGHT]
    assert len(bumps) == 2 and len(lamps) == 2 and len(ev) == 4
    assert bumps[0].segment_id == seg_ids[50] and bumps[1].segment_id is None
    assert [b.severity for b in bumps] == [0.6, 0.4]
    for b in bumps:
        assert set(b.details) == {"kind", "speed_kmh", "raw_peak", "signal", "signal_fs", "peak_index"}
        assert b.details["kind"] == "bump" and b.details["signal"] == [0.0, 1.5, 0.0, -0.5]
        assert isinstance(b.ts, datetime) and b.ts.tzinfo is not None
        json.dumps(b.details, allow_nan=False)
    assert bumps[1].details["speed_kmh"] is None  # NaN must not reach jsonb

    # streetlights are matched against road segments, whatever the vehicle mode
    light_call = fake_db.nearest[-1]
    assert light_call["mode"] == "road" and light_call["max_dist_m"] == pipeline.LIGHT_MATCH_DIST_M
    assert [e.segment_id for e in lamps] == [ROAD_BASE + 8, ROAD_BASE + 9]
    assert lamps[0].details == {"kind": "dark_gap", "expected_lux": 40.0, "observed_lux": 3.0}
    assert lamps[0].ts == (T0 + pd.Timedelta(seconds=20)).to_pydatetime()

    assert out == {"ride_id": 7, "evidence_ids": [1, 2, 3, 4], "bumps": 2, "dark_gaps": 2, "segments_covered": 16}


def test_process_ride_end_to_end_with_real_signal_modules(fake_db):
    """Real detect/track_score/lights on a synthetic 100 Hz night tram ride; only the DB is faked."""
    bump_m = (150.0, 450.0)
    df, truth = _night_ride(n_lamps=22, spacing=30, missing=(12,), fs=100, seed=6, gps_sd=1.0, bumps_m=bump_m)

    out = pipeline.process_ride(CONN, df, vehicle_line="17", mode="tram")

    assert out["ride_id"] == 7 and out["segments_covered"] > 15
    assert fake_db.ride_segments[0][1] and fake_db.calls[-1] == "recompute_segment_health"
    bumps = [e for e in fake_db.evidence if e.type == IssueType.TRAM_TRACK]
    lamps = [e for e in fake_db.evidence if e.type == IssueType.STREETLIGHT]
    assert out["bumps"] == len(bumps) >= 2 and out["dark_gaps"] == len(lamps) >= 1
    assert out["evidence_ids"] == list(range(1, len(fake_db.evidence) + 1))

    bump_lon, bump_lat = _to_lonlat(np.array(bump_m))
    for lon, lat in zip(bump_lon, bump_lat):  # every injected bump found within 15 m, on a tram segment
        near = [b for b in bumps if haversine_m(b.lon, b.lat, lon, lat) < 15]
        assert near and all(b.segment_id is not None and b.segment_id < ROAD_BASE for b in near)
    for b in bumps:
        assert b.details["kind"] == "bump" and 0 <= b.severity <= 1 and len(b.details["signal"]) <= 200
        json.dumps(b.details, allow_nan=False)

    assert any(haversine_m(e.lon, e.lat, *truth[0]) < 8 for e in lamps)
    assert all(e.segment_id is None or e.segment_id >= ROAD_BASE for e in lamps)
    assert all(e.details["kind"] == "dark_gap" for e in lamps)


def test_process_ride_rejects_unknown_mode(fake_db):
    with pytest.raises(ValueError):
        pipeline.process_ride(CONN, _straight_ride(), vehicle_line=None, mode="bike")
