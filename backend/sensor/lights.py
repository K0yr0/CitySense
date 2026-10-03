"""Broken-streetlight detection from night-time lux readings ("dark gaps").

A lit street seen from a moving vehicle gives a regular saw-tooth of lux peaks,
one per lamp (Warsaw: usually every 25-40 m). Working in the *distance* domain
instead of time cancels speed changes and stops. Where the rhythm says a lamp
should be but the light there is < 30 % of its neighbours, the lamp is probably
broken: that spot is a dark gap.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.signal import find_peaks

from backend.sensor.mapmatch import haversine_m

GAP_COLUMNS = ["lon", "lat", "ts", "expected_lux", "observed_lux", "severity"]

STEP_M = 1.0                 # distance-resampling resolution
SMOOTH_M = 3                 # moving-average window (m) against sensor noise
DAYTIME_MEDIAN_LUX = 300.0   # median above this = daylight, lamps are invisible
MIN_RANGE_LUX = 3.0          # lamp peaks must rise this far above the dark floor
MIN_PERIODICITY = 0.2        # autocorrelation at a lamp-spacing lag needed to trust the rhythm
DARK_RATIO = 0.3             # light at an expected lamp < 30 % of its neighbours -> dark
MIN_LAMPS = 5                # need at least this many lit lamps to see a rhythm
NEIGHBOUR_SPACINGS = 4       # spacings looked at on each side to get the local rhythm
SPACING_TOL = 0.2            # a regular spacing is within +-20 % of the local typical one
MAX_MISSING_RUN = 3          # longer unlit stretches are parks/junctions, not broken lamps
MIN_SPEED_KMH = 3.0          # GPS jitter while standing still would invent distance
GPS_SMOOTH_S = 3.0           # rolling-mean window for positions before measuring distance


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=GAP_COLUMNS)


def _time_axis(df: pd.DataFrame) -> tuple[pd.Timestamp | None, np.ndarray]:
    """(t0, seconds since t0) from `ts` (preferred) or `t`."""
    if "ts" in df:
        ts = pd.to_datetime(df["ts"], utc=True, errors="coerce")
        if ts.notna().any():
            t0 = ts.min()
            return t0, (ts - t0).dt.total_seconds().to_numpy(dtype=float)
    if "t" in df:
        return None, pd.to_numeric(df["t"], errors="coerce").to_numpy(dtype=float)
    return None, np.arange(len(df), dtype=float)


def _distance_track(df: pd.DataFrame) -> tuple[pd.DataFrame | None, pd.Timestamp | None]:
    """(moving samples indexed by cumulative distance in m, strictly increasing; t0)."""
    if df is None or len(df) == 0 or not {"lon", "lat", "lux"} <= set(df.columns):
        return None, None
    lon = pd.to_numeric(df["lon"], errors="coerce").to_numpy(dtype=float)
    lat = pd.to_numeric(df["lat"], errors="coerce").to_numpy(dtype=float)
    lux = pd.to_numeric(df["lux"], errors="coerce").to_numpy(dtype=float)
    t0, secs = _time_axis(df)
    ok = np.isfinite(lon) & np.isfinite(lat) & np.isfinite(lux) & np.isfinite(secs)
    if "speed_kmh" in df:
        speed = pd.to_numeric(df["speed_kmh"], errors="coerce").to_numpy(dtype=float)
        ok &= ~(speed < MIN_SPEED_KMH)  # unknown speed -> keep
    if ok.sum() < 10:
        return None, None
    lon, lat, lux, secs = lon[ok], lat[ok], lux[ok], secs[ok]
    # GPS jitter adds fake path length (~10 % at tram speeds); a ~3 s rolling mean removes most of it.
    dt = float(np.median(np.diff(secs))) if len(secs) > 1 else 1.0
    window = int(np.clip(round(GPS_SMOOTH_S / dt), 1, len(lon))) if dt > 0 else 1
    lon, lat = (pd.Series(v).rolling(window, center=True, min_periods=1).mean().to_numpy() for v in (lon, lat))
    d = np.concatenate([[0.0], np.cumsum(haversine_m(lon[:-1], lat[:-1], lon[1:], lat[1:]))])
    track = pd.DataFrame({"d": np.round(d, 2), "lon": lon, "lat": lat, "lux": lux, "secs": secs})
    return track.groupby("d", sort=True).mean(), t0


def _periodicity(sig: np.ndarray, lo_lag: int, hi_lag: int) -> float:
    """Best normalised autocorrelation over the plausible lamp-spacing lags."""
    x = sig - sig.mean()
    denom = float(np.dot(x, x))
    hi_lag = min(hi_lag, len(x) // 2)
    if denom <= 0 or hi_lag < lo_lag:
        return 0.0
    return max(float(np.dot(x[:-lag], x[lag:])) / denom for lag in range(lo_lag, hi_lag + 1))


def _drop_dim_peaks(peaks: np.ndarray, lift: np.ndarray) -> np.ndarray:
    """Iteratively remove the dimmest peak while it is < DARK_RATIO of its 2+2 neighbours.

    What survives are the lit lamps; noise wiggles and dim lamps are removed and
    later re-checked as 'expected but dark' positions.
    """
    keep = list(peaks)
    while len(keep) > 2:
        h = lift[keep]
        ratios = np.array([
            h[i] / max(np.median(np.r_[h[max(0, i - 2):i], h[i + 1:i + 3]]), 1e-9)
            for i in range(len(keep))
        ])
        worst = int(np.argmin(ratios))
        if ratios[worst] >= DARK_RATIO:
            break
        keep.pop(worst)
    return np.asarray(keep, dtype=int)


def _local_spacing(spacings: np.ndarray, i: int, lo: float, hi: float) -> float | None:
    """Typical lamp spacing around gap i from its neighbours, or None if the rhythm is irregular."""
    around = np.r_[spacings[max(0, i - NEIGHBOUR_SPACINGS):i], spacings[i + 1:i + 1 + NEIGHBOUR_SPACINGS]]
    around = around[(around >= lo) & (around <= hi)]
    if len(around) < 3:
        return None
    s = float(np.median(around))
    regular = around[np.abs(around / s - 1) <= SPACING_TOL]
    return float(np.median(regular)) if len(regular) >= 3 else None


def find_dark_gaps(df: pd.DataFrame, min_spacing_m: float = 20, max_spacing_m: float = 60) -> pd.DataFrame:
    """Positions where a streetlamp is expected from the lux rhythm but it is dark.

    Returns columns lon, lat, ts, expected_lux, observed_lux, severity (0-1), one row per
    missing lamp. Empty when there is no lux, it is daytime, or no regular rhythm is found.
    Severity grows with darkness and with the number of consecutive missing lamps.
    """
    track, t0 = _distance_track(df)
    if track is None or float(np.median(track["lux"])) > DAYTIME_MEDIAN_LUX:
        return _empty()
    d = track.index.to_numpy(dtype=float)
    grid = np.arange(d[0], d[-1], STEP_M)
    if len(grid) < MIN_LAMPS * min_spacing_m / STEP_M:
        return _empty()

    sig = np.interp(grid, d, track["lux"].to_numpy())
    sig = np.convolve(sig, np.ones(SMOOTH_M) / SMOOTH_M, mode="same")
    floor = float(np.percentile(sig, 5))
    lift = sig - floor
    dyn_range = float(np.percentile(lift, 95))
    if dyn_range < MIN_RANGE_LUX:
        return _empty()
    lo_lag, hi_lag = int(min_spacing_m / STEP_M), int(max_spacing_m / STEP_M)
    if _periodicity(sig, lo_lag, hi_lag) < MIN_PERIODICITY:
        return _empty()

    peaks, _ = find_peaks(lift, distance=max(1, int(0.6 * lo_lag)), prominence=0.08 * dyn_range)
    lamps = _drop_dim_peaks(peaks, lift)
    if len(lamps) < MIN_LAMPS:
        return _empty()

    pos = grid[lamps]
    spacings = np.diff(pos)
    found: list[tuple[float, float, float, int]] = []  # (x, expected_lift, observed_lift, run)
    for i, gap in enumerate(spacings):
        s = _local_spacing(spacings, i, min_spacing_m, max_spacing_m)
        if s is None:
            continue
        n = int(round(gap / s))
        if n < 2 or n - 1 > MAX_MISSING_RUN or abs(gap / s - n) > 0.15 * n:  # error grows with n
            continue
        expected = 0.5 * (lift[lamps[i]] + lift[lamps[i + 1]])
        dark = []
        for k in range(1, n):
            x = pos[i] + k * gap / n
            window = np.abs(grid - x) <= 0.25 * s
            observed = float(lift[window].max())
            if observed < DARK_RATIO * expected:
                dark.append((x, expected, max(observed, 0.0)))
        found += [(x, e, o, len(dark)) for x, e, o in dark]

    if not found:
        return _empty()
    x, expected, observed, run = (np.array(col) for col in zip(*found))
    darkness = np.clip(1 - observed / expected, 0, 1)
    secs = np.round(np.interp(x, d, track["secs"].to_numpy()), 3)  # ms: avoids ns -> datetime warnings
    return pd.DataFrame({
        "lon": np.interp(x, d, track["lon"].to_numpy()),
        "lat": np.interp(x, d, track["lat"].to_numpy()),
        "ts": t0 + pd.to_timedelta(secs, unit="s") if t0 is not None else pd.NaT,
        "expected_lux": np.round(floor + expected, 2),
        "observed_lux": np.round(floor + observed, 2),
        "severity": np.round(np.clip(0.7 * darkness + 0.15 * (run - 1), 0, 1), 3),
    })
