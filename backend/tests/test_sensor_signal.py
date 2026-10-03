"""Sensor signal processing: ingest, bump detection, track score and the synthetic ride generator."""
from __future__ import annotations

import importlib.util
import time
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backend.sensor import detect
from backend.sensor.detect import BUMP_COLUMNS, MAX_SIGNAL_POINTS, detect_bumps, highpass
from backend.sensor.ingest import SAMPLE_COLUMNS, estimate_fs, from_samples, load_sensor_logger
from backend.sensor.track_score import health_from_rms, segment_pass_stats, segment_rms

_spec = importlib.util.spec_from_file_location(
    "synth_ride", Path(__file__).resolve().parents[2] / "scripts" / "synth_ride.py")
synth = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(synth)


# --------------------------------------------------------------------------- helpers

def _flat_ride(seconds: float = 60.0, fs: int = 100, speed_kmh: float = 30.0, seed: int = 0) -> pd.DataFrame:
    """Phone lying still in a vehicle on a smooth road: gravity + small vibration, GPS heading north."""
    rng = np.random.default_rng(seed)
    t = np.arange(0, seconds, 1 / fs)
    n = t.size
    speed = np.full(n, speed_kmh)
    lat = 52.23 + np.cumsum(speed / 3.6 / fs) / 111_000
    return pd.DataFrame({
        "t": t, "ts": pd.Timestamp("2026-09-29T07:00:00Z") + pd.to_timedelta(t, unit="s"),
        "ax": 0.2 + rng.normal(0, 0.1, n), "ay": rng.normal(0, 0.1, n), "az": 9.79 + rng.normal(0, 0.15, n),
        "lat": lat, "lon": np.full(n, 21.01), "speed_kmh": speed, "lux": np.nan,
    })


def _kick(df: pd.DataFrame, at_s: float, amp: float, fs: int = 100) -> None:
    """Add a damped 9 Hz vertical jolt (pothole) at time at_s."""
    i0 = int(at_s * fs)
    tt = np.arange(int(0.5 * fs)) / fs
    df.loc[i0:i0 + tt.size - 1, "az"] += amp * np.exp(-tt / 0.08) * np.cos(2 * np.pi * 9 * tt)


def _write_sensor_logger(folder: Path, *, in_g: bool = False, user_accel: bool = False,
                         with_speed: bool = True, with_light: bool = True) -> dict:
    """Fake Sensor Logger export: 40 s at 100 Hz, 1 Hz GPS driving north at 10 m/s."""
    folder.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(1)
    t0_ns = 1_790_000_000_000_000_000
    sec = np.arange(0, 40, 0.01)
    unit = 1.0 / 9.80665 if in_g else 1.0
    tilt = np.array([0.0, 0.6, 0.8]) * 9.80665  # phone tilted: gravity split over y/z
    noise = rng.normal(0, 0.05, (sec.size, 3))
    grav = np.tile(tilt, (sec.size, 1))
    xyz = (noise if user_accel else noise + grav) * unit
    acc = pd.DataFrame({"time": t0_ns + (sec * 1e9).astype("int64"), "seconds_elapsed": sec,
                        "z": xyz[:, 2], "y": xyz[:, 1], "x": xyz[:, 0]})
    acc.to_csv(folder / ("Accelerometer.csv" if user_accel else "TotalAcceleration.csv"), index=False)
    if user_accel:
        g = grav * unit
        pd.DataFrame({"time": acc["time"], "seconds_elapsed": sec, "z": g[:, 2], "y": g[:, 1], "x": g[:, 0]}) \
            .to_csv(folder / "Gravity.csv", index=False)
    gsec = np.arange(0.5, 40, 1.0)
    loc = pd.DataFrame({
        "time": t0_ns + (gsec * 1e9).astype("int64"), "seconds_elapsed": gsec,
        "bearingAccuracy": 5.0, "speedAccuracy": 0.5, "verticalAccuracy": 3.0, "horizontalAccuracy": 4.0,
        "speed": 10.0 if with_speed else -1.0, "bearing": 0.0, "altitude": 110.0,
        "longitude": 21.01, "latitude": 52.23 + gsec * 10.0 / 111_195,
    })
    loc.to_csv(folder / "Location.csv", index=False)
    if with_light:
        lsec = np.arange(0, 40, 0.2)
        pd.DataFrame({"time": t0_ns + (lsec * 1e9).astype("int64"), "seconds_elapsed": lsec, "lux": 5 + lsec}) \
            .to_csv(folder / "Light.csv", index=False)
    return {"t0": pd.Timestamp(t0_ns, unit="ns", tz="UTC")}


# --------------------------------------------------------------------------- detection on synthetic rides

@pytest.mark.parametrize("seed,night", [(1, False), (2, True), (7, False)])
def test_bumps_found_on_synthetic_ride(tmp_path, seed, night):
    csv_path, truth_path = synth.write_ride(f"ride_{seed}", tmp_path, seed=seed, night=night, bumps=6)
    df = load_sensor_logger(csv_path)  # exercises the combined-CSV ingest path
    bumps = detect_bumps(df)
    score = synth.score_detections(bumps, pd.read_csv(truth_path), radius_m=20)
    assert score["recall"] >= 0.9 and score["precision"] >= 0.9, score

    assert list(bumps.columns) == BUMP_COLUMNS
    assert bumps["severity"].between(0, 1).all() and (bumps["speed_kmh"] >= detect.MIN_SPEED_KMH).all()
    for b in bumps.itertuples():
        assert len(b.signal) <= MAX_SIGNAL_POINTS and b.signal_fs == 100
        assert abs(abs(b.signal[b.peak_index]) - b.raw_peak) < 1e-2  # snippet is centred on the peak
        assert str(b.ts.tz) == "UTC"


def test_same_world_across_rides():
    """Day and night rides hit the same defects -> fusion's '>= 2 rides' rule can fire."""
    _, day = synth.generate_ride(seed=1, night=False)
    _, night = synth.generate_ride(seed=2, night=True)
    pd.testing.assert_frame_equal(day, night[night["kind"] == "bump"].reset_index(drop=True))
    assert (night["kind"] == "dark_gap").sum() == synth.N_BROKEN_LAMPS
    _, three = synth.generate_ride(seed=3, bumps=3)
    pd.testing.assert_frame_equal(three, day.iloc[:3])  # first k bumps independent of --bumps


def test_generator_is_deterministic():
    a, _ = synth.generate_ride(seed=4, bumps=2)
    b, _ = synth.generate_ride(seed=4, bumps=2)
    pd.testing.assert_frame_equal(a, b)
    assert list(a.columns) == SAMPLE_COLUMNS and a["lux"].isna().all()


def test_smooth_ride_yields_no_bumps():
    df, _ = synth.generate_ride(seed=5, bumps=0)  # rail joints, crossings and door slams only
    assert len(detect_bumps(df)) == 0
    assert len(detect_bumps(_flat_ride())) == 0


def test_low_speed_samples_are_dropped():
    df = _flat_ride(seconds=60)
    df.loc[df["t"].between(15, 25), "speed_kmh"] = 2.0  # standing at a stop: doors, passengers
    _kick(df, 20.0, 8.0)
    _kick(df, 40.0, 8.0)
    bumps = detect_bumps(df)
    assert len(bumps) == 1 and abs(bumps["t"].iloc[0] - 40.0) < 0.1


def test_severity_is_speed_normalized_and_absolute():
    slow, fast = _flat_ride(speed_kmh=15), _flat_ride(speed_kmh=60)
    _kick(slow, 30.0, 6.0)
    _kick(fast, 30.0, 6.0)
    s_slow, s_fast = detect_bumps(slow)["severity"].iloc[0], detect_bumps(fast)["severity"].iloc[0]
    assert s_slow > 2 * s_fast  # same jolt at 15 km/h means a worse defect than at 60 km/h
    weak = _flat_ride()
    _kick(weak, 30.0, 4.0)
    assert detect_bumps(weak)["severity"].iloc[0] < 0.6  # no self-normalization to 1.0


def test_highpass_removes_gravity_and_tilt():
    df = _flat_ride(seconds=30)
    df["az"] += np.where(df["t"] > 15, -0.5, 0.0) * np.clip(df["t"] - 15, 0, 1)  # slow re-tilt
    hp = highpass(df, 100)
    assert hp.shape == (len(df),) and abs(np.median(hp)) < 0.05 and np.std(hp) < 0.3


# --------------------------------------------------------------------------- ingest

def test_ingest_sensor_logger_folder(tmp_path):
    meta = _write_sensor_logger(tmp_path / "export")
    df = load_sensor_logger(tmp_path / "export")
    assert list(df.columns) == SAMPLE_COLUMNS and len(df) == 4000
    assert df["t"].iloc[0] == 0 and df["t"].is_monotonic_increasing
    assert str(df["ts"].dt.tz) == "UTC" and df["ts"].iloc[0] == meta["t0"]
    mag = np.linalg.norm(df[["ax", "ay", "az"]].to_numpy(), axis=1)
    assert abs(np.median(mag) - 9.80665) < 0.05
    assert np.allclose(df["speed_kmh"].dropna(), 36.0)
    mid = df[df["t"].between(5, 35)]
    assert np.allclose(mid["lat"], 52.23 + mid["t"] * 10.0 / 111_195, atol=1e-6) and (mid["lon"] == 21.01).all()
    assert np.allclose(mid["lux"], 5 + mid["t"], atol=0.01)
    assert estimate_fs(df) == 100


def test_ingest_zip_in_g_with_user_accel_and_missing_speed(tmp_path):
    _write_sensor_logger(tmp_path / "Ride 1", in_g=True, user_accel=True, with_speed=False, with_light=False)
    zpath = tmp_path / "ride.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        for f in (tmp_path / "Ride 1").iterdir():
            zf.write(f, f"Ride 1/{f.name}")
    df = load_sensor_logger(zpath)
    mag = np.linalg.norm(df[["ax", "ay", "az"]].to_numpy(), axis=1)
    assert abs(np.median(mag) - 9.80665) < 0.1  # Accelerometer + Gravity, converted from g
    assert df["lux"].isna().all()
    moving = df[df["t"].between(5, 35)]["speed_kmh"]
    assert np.allclose(moving, 36.0, atol=1.0)  # derived from GPS displacement


def test_from_samples_sparse_gps_relative_clock():
    n = 500
    samples = [{"t": i / 50, "ax": 0.1, "ay": 0.2, "az": 9.8} for i in range(n)]
    for i in range(0, n, 50):
        samples[i].update(lat=52.23 + i * 1e-6, lon=21.01, speed_kmh=20.0)
    df = from_samples(samples)
    assert list(df.columns) == SAMPLE_COLUMNS and len(df) == n and estimate_fs(df) == 50
    assert df["lat"].notna().sum() >= n - 50 and np.isclose(df["lat"].iloc[25], 52.23 + 25e-6)
    assert abs((pd.Timestamp.now(tz="UTC") - df["ts"].iloc[-1]).total_seconds()) < 5
    assert df["lux"].isna().all()
    assert from_samples([]).columns.tolist() == SAMPLE_COLUMNS


def test_from_samples_epoch_ms():
    t0 = time.time() * 1000
    df = from_samples([{"t": t0 + 10 * i, "ax": 0, "ay": 0, "az": 1.0} for i in range(300)])  # g units
    assert estimate_fs(df) == 100 and np.isclose(df["az"].iloc[0], 9.80665)
    assert abs(df["ts"].iloc[0].timestamp() * 1000 - t0) < 1


# --------------------------------------------------------------------------- track score

def test_segment_pass_stats_and_health():
    df = _flat_ride(seconds=30)
    _kick(df, 27.0, 8.0)
    hp = highpass(df, 100)
    seg = np.array([None] * 500 + [1] * 1000 + [2] * 1000 + [3] * 500, dtype=object)  # 3 = has the bump
    df.loc[500:1499, "speed_kmh"] = 0.0  # segment 1: standing only -> still reported (verification)
    rows = segment_pass_stats(df, hp, seg)
    assert [r["segment_id"] for r in rows] == [1, 2, 3]
    assert set(rows[0]) == {"segment_id", "rms", "samples", "passed_at"}
    assert rows[0]["samples"] == 1000 and rows[1]["samples"] == 1000
    assert rows[0]["passed_at"].tzinfo is not None
    assert rows[2]["rms"] > 3 * rows[1]["rms"]

    rms = segment_rms(hp, seg)
    assert list(rms.index) == [1, 2, 3] and rms[3] > rms[2]

    long = pd.DataFrame([{**r, "ride_id": rid} for rid in (1, 2) for r in rows] + [{"segment_id": 4, "rms": 0.1, "ride_id": 1}])
    h = health_from_rms(long)
    assert h.loc[3, "health"] < h.loc[2, "health"] and h["health"].between(0, 1).all()
    assert h.loc[2, "confidence"] == 2 and h.loc[4, "confidence"] == 1
    assert health_from_rms(long, ref=100.0)["health"].min() > 0.9  # absolute reference
