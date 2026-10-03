"""Sensor ingest: Sensor Logger exports, combined CSVs and PWA chunks -> one tidy DataFrame.

Every loader returns one row per accelerometer sample with the columns SAMPLE_COLUMNS:
`t` (s since first sample), `ts` (tz-aware UTC), `ax/ay/az` (m/s², incl. gravity when the
source has it), `lat/lon` (WGS84, linearly interpolated from GPS fixes), `speed_kmh`
(GPS speed, or derived from GPS displacement when missing) and `lux` (NaN when absent).
"""
from __future__ import annotations

import re
import time
import zipfile
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

SAMPLE_COLUMNS = ["t", "ts", "ax", "ay", "az", "lat", "lon", "speed_kmh", "lux"]

G = 9.80665
DEFAULT_FS = 100            # Hz, returned by estimate_fs when the timeline is unusable
GPS_TOLERANCE_S = 2.0       # samples further outside the GPS fix time range get NaN lat/lon/speed
SPEED_WINDOW_S = 3.0        # half-window for GPS-displacement speed (suppresses fix jitter at stops)
MAX_GPS_ACCURACY_M = 50.0   # drop Sensor Logger fixes with a worse horizontalAccuracy
EARTH_R_M = 6_371_000.0

_ALIASES = {
    "x": "ax", "y": "ay", "z": "az", "acc_x": "ax", "acc_y": "ay", "acc_z": "az",
    "latitude": "lat", "longitude": "lon", "lng": "lon",
    "illuminance": "lux", "light": "lux",
    "timestamp": "ts", "datetime": "ts",
    "speed": "speed_ms", "speed_mps": "speed_ms", "speed_m_s": "speed_ms", "speed_kph": "speed_kmh",
    "horizontalaccuracy": "accuracy",
}


# --------------------------------------------------------------------------- public API

def load_sensor_logger(path: str | Path) -> pd.DataFrame:
    """Load a Sensor Logger export (folder or .zip) or a single combined CSV with SAMPLE_COLUMNS."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    if path.is_dir():
        tables: dict[str, Callable[[], pd.DataFrame]] = {}
        for p in sorted(path.rglob("*.csv"), key=lambda p: len(p.parts)):  # shallowest file wins
            tables.setdefault(p.name.lower(), lambda p=p: pd.read_csv(p))
        return _load_export(tables)
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as zf:
            tables = {}
            for name in sorted(zf.namelist(), key=lambda n: n.count("/")):
                if name.lower().endswith(".csv") and "__macosx" not in name.lower():
                    tables.setdefault(Path(name).name.lower(), lambda n=name: pd.read_csv(zf.open(n)))
            return _load_export(tables)
    return _from_frame(pd.read_csv(path))


def from_samples(samples: list[dict]) -> pd.DataFrame:
    """PWA stream chunks (`{"t","ax","ay","az","lat","lon","speed_kmh","lux"?}`) -> SAMPLE_COLUMNS.

    `t` may be epoch (s/ms) or seconds since recording start; a relative clock is anchored so
    the last sample is "now". Sparse GPS (lat/lon only on some samples) is interpolated.
    """
    if not samples:
        return _empty()
    return _from_frame(pd.DataFrame(samples))


def estimate_fs(df: pd.DataFrame) -> int:
    """Sampling rate in Hz from the median positive time step of `t`."""
    if "t" not in df or len(df) < 2:
        return DEFAULT_FS
    dt = np.diff(df["t"].to_numpy(float))
    dt = dt[np.isfinite(dt) & (dt > 0)]
    return max(1, int(round(1.0 / float(np.median(dt))))) if dt.size else DEFAULT_FS


# --------------------------------------------------------------------------- loaders

def _load_export(tables: dict[str, Callable[[], pd.DataFrame]]) -> pd.DataFrame:
    """Combine Sensor Logger per-sensor CSVs (lower-case basename -> reader)."""
    def get(name: str) -> pd.DataFrame | None:
        return _norm_cols(tables[name]()) if name in tables else None

    acc = get("totalacceleration.csv")
    grav = None
    if acc is None:
        acc = get("accelerometer.csv")  # user acceleration (gravity removed)
        grav = get("gravity.csv")
    if acc is None:
        if len(tables) == 1:  # a lone combined CSV inside a folder/zip
            return _from_frame(next(iter(tables.values()))())
        raise ValueError("no TotalAcceleration.csv / Accelerometer.csv in Sensor Logger export")

    sec, absolute = _epoch_seconds(acc)
    offset = 0.0 if absolute else time.time() - float(np.nanmax(sec))
    frame = pd.DataFrame({"epoch": sec + offset, **{c: _num(acc, c) for c in ("ax", "ay", "az")}})
    if grav is not None and {"ax", "ay", "az"} <= set(grav.columns):
        gsec = _epoch_seconds(grav)[0] + offset
        for c in ("ax", "ay", "az"):  # user accel + gravity = total acceleration
            frame[c] = frame[c] + np.nan_to_num(_interp(frame["epoch"].to_numpy(), gsec, _num(grav, c)))

    fixes = None
    loc = get("location.csv")
    if loc is not None:
        fixes = _fix_table(loc, _epoch_seconds(loc)[0] + offset)
        if "accuracy" in loc:
            acc_m = _num(loc, "accuracy")
            fixes = fixes[~(acc_m > MAX_GPS_ACCURACY_M)]
    lux = None
    light = get("light.csv")
    if light is not None and "lux" in light:
        lux = pd.DataFrame({"epoch": _epoch_seconds(light)[0] + offset, "lux": _num(light, "lux")})
    return _finish(frame, fixes, lux)


def _from_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Combined CSV / PWA samples: accel, GPS and lux already share one timeline."""
    df = _norm_cols(df)
    missing = {"ax", "ay", "az"} - set(df.columns)
    if missing:
        raise ValueError(f"sensor CSV is missing accelerometer columns {sorted(missing)}; got {list(df.columns)}")
    sec, absolute = _epoch_seconds(df)
    if not absolute:
        steps = np.diff(sec[np.isfinite(sec)])
        if steps.size and np.median(steps[steps > 0] if (steps > 0).any() else steps) >= 2.0:
            sec = sec / 1000.0  # relative milliseconds (e.g. performance.now()); accel is never < 1 Hz
        sec = sec + (time.time() - float(np.nanmax(sec)))
    frame = pd.DataFrame({"epoch": sec, **{c: _num(df, c) for c in ("ax", "ay", "az")}})
    lux = pd.DataFrame({"epoch": sec, "lux": _num(df, "lux")})
    return _finish(frame, _fix_table(df, sec), lux)


def _finish(acc: pd.DataFrame, fixes: pd.DataFrame | None, lux: pd.DataFrame | None) -> pd.DataFrame:
    acc = acc.dropna().sort_values("epoch").drop_duplicates("epoch")
    if acc.empty:
        return _empty()
    xyz = acc[["ax", "ay", "az"]].to_numpy(float)
    if 0.5 < float(np.median(np.linalg.norm(xyz, axis=1))) < 2.0:  # export in g, not m/s²
        xyz = xyz * G
    x = acc["epoch"].to_numpy(float)
    lat, lon, speed = _gps_onto(x, fixes)
    lux_v = _interp(x, lux["epoch"].to_numpy(float), lux["lux"].to_numpy(float)) if lux is not None else np.nan
    out = pd.DataFrame({
        "t": x - x[0],
        "ts": pd.to_datetime(np.round(x * 1e6).astype("int64"), unit="us", utc=True),
        "ax": xyz[:, 0], "ay": xyz[:, 1], "az": xyz[:, 2],
        "lat": lat, "lon": lon, "speed_kmh": speed, "lux": lux_v,
    })
    return out[SAMPLE_COLUMNS].reset_index(drop=True)


# --------------------------------------------------------------------------- helpers

def _empty() -> pd.DataFrame:
    df = pd.DataFrame({c: pd.Series(dtype=float) for c in SAMPLE_COLUMNS})
    df["ts"] = pd.Series(dtype="datetime64[us, UTC]")
    return df


def _clean(col: object) -> str:
    c = re.sub(r"\s*[\(\[].*?[\)\]]", "", str(col)).strip().lower()  # "speed (m/s)" -> "speed"
    return re.sub(r"[\s\-]+", "_", c)


def _norm_cols(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns=lambda c: _ALIASES.get(_clean(c), _clean(c)))
    return df.loc[:, ~df.columns.duplicated()]


def _num(df: pd.DataFrame, col: str) -> np.ndarray:
    if col not in df:
        return np.full(len(df), np.nan)
    return pd.to_numeric(df[col], errors="coerce").to_numpy(float)


def _epoch_seconds(df: pd.DataFrame) -> tuple[np.ndarray, bool]:
    """UNIX seconds per row and whether the clock was absolute (else relative to recording start)."""
    for col in ("ts", "time", "t", "seconds_elapsed"):
        if col not in df:
            continue
        num = pd.to_numeric(df[col], errors="coerce")
        if num.notna().mean() > 0.5:
            v = num.to_numpy(float)
            med = float(np.nanmedian(np.abs(v)))
            for scale, lim in ((1e9, 1e17), (1e6, 1e14), (1e3, 1e11)):  # ns, us, ms epoch
                if med > lim:
                    return v / scale, True
            return v, med > 1e8  # epoch seconds vs seconds since start
        parsed = pd.to_datetime(df[col], utc=True, errors="coerce", format="ISO8601")
        if parsed.notna().mean() > 0.5:
            return (parsed - pd.Timestamp(0, tz="UTC")).dt.total_seconds().to_numpy(float), True
    raise ValueError(f"no usable time column (ts/time/t/seconds_elapsed) in {list(df.columns)}")


def _fix_table(df: pd.DataFrame, sec: np.ndarray) -> pd.DataFrame:
    speed = _num(df, "speed_kmh")
    if np.isnan(speed).all():
        speed = _num(df, "speed_ms") * 3.6
    return pd.DataFrame({"epoch": sec, "lat": _num(df, "lat"), "lon": _num(df, "lon"), "speed_kmh": speed})


def _interp(x: np.ndarray, xp: np.ndarray, fp: np.ndarray, tol: float = GPS_TOLERANCE_S) -> np.ndarray:
    """Linear interpolation that returns NaN beyond `tol` seconds outside the known range."""
    xp, fp = np.asarray(xp, float), np.asarray(fp, float)
    ok = np.isfinite(xp) & np.isfinite(fp)
    if not ok.any():
        return np.full(len(x), np.nan)
    order = np.argsort(xp[ok], kind="stable")
    xp, fp = xp[ok][order], fp[ok][order]
    y = np.interp(x, xp, fp)
    y[(x < xp[0] - tol) | (x > xp[-1] + tol)] = np.nan
    return y


def _haversine_m(lat1, lon1, lat2, lon2) -> np.ndarray:
    p1, p2 = np.radians(lat1), np.radians(lat2)
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(np.radians(lon2 - lon1) / 2) ** 2
    return 2 * EARTH_R_M * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def _speed_from_track(t: np.ndarray, lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    """km/h from net displacement over ±SPEED_WINDOW_S (robust to GPS jitter while standing)."""
    j1 = np.searchsorted(t, t - SPEED_WINDOW_S, side="left")
    j2 = np.searchsorted(t, t + SPEED_WINDOW_S, side="right") - 1
    dt = t[j2] - t[j1]
    d = _haversine_m(lat[j1], lon[j1], lat[j2], lon[j2])
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(dt > 0, d / dt * 3.6, 0.0)


def _gps_onto(x: np.ndarray, fixes: pd.DataFrame | None) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    nan = np.full(len(x), np.nan)
    if fixes is None:
        return nan, nan, nan
    f = fixes.dropna(subset=["epoch", "lat", "lon"])
    f = f[(f["lat"] != 0) | (f["lon"] != 0)].sort_values("epoch").drop_duplicates("epoch")
    if f.empty:
        return nan, nan, nan
    t, lat, lon = (f[c].to_numpy(float) for c in ("epoch", "lat", "lon"))
    speed = f["speed_kmh"].to_numpy(float)
    bad = ~np.isfinite(speed) | (speed < 0)  # iOS reports -1 for "unknown"
    if bad.any():
        speed = np.where(bad, _speed_from_track(t, lat, lon), speed)
    return _interp(x, t, lat), _interp(x, t, lon), _interp(x, t, speed)
