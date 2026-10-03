"""Bump / pothole / track-defect detection on vehicle accelerometer data.

Orientation-free: works on |a| (so the phone can lie in any pose), removes gravity with
the median, high-passes at 1.5 Hz (kills braking, body sway, slow tilt) and picks peaks
that stand out from the local vibration level. Severity is speed-normalized against an
absolute reference, so a perfectly smooth ride yields no bumps at all (the roadmap's
reference code normalized by the ride's own 0.99 quantile, which always invents bumps).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.signal import butter, find_peaks, sosfiltfilt

from backend.sensor.ingest import estimate_fs

FILTER_ORDER = 4
STD_WINDOW_S = 5.0          # rolling window for the local vibration level
STD_FACTOR = 2.5            # a peak must exceed 2.5 x local rolling std ...
MIN_PEAK_MS2 = 3.0          # ... AND this absolute floor (|hp| in m/s², ~0.3 g). Normal tram/bus
                            # vibration, rail joints and track crossings stay below ~2.5 m/s² after
                            # the 1.5 Hz high-pass; potholes / broken joints hit 4-15 m/s².
SEVERITY_REF_MS2 = 10.0     # speed-normalized peak that maps to severity 1.0 (~1 g extra jolt at
                            # 30 km/h: phone lifts off the seat). severity = min(1, norm_peak / REF).
REF_SPEED_KMH = 30.0        # speed at which raw and normalized peaks are equal
MIN_SPEED_KMH = 5.0         # below this (stops, doors, passengers walking) samples are ignored
MERGE_DIST_M = 15.0         # peaks closer than this along the ride (axles/bogies) -> one bump
SIGNAL_HALF_WINDOW_S = 1.0  # stored hp snippet: ±1 s around the peak
MAX_SIGNAL_POINTS = 200

BUMP_COLUMNS = ["t", "ts", "lat", "lon", "speed_kmh", "raw_peak", "severity",
                "signal", "signal_fs", "peak_index"]


def speed_factor(speed_kmh) -> np.ndarray:
    """Hit strength grows with speed: divide raw peaks by clip(speed/30, 0.5, 2.0)."""
    v = np.nan_to_num(np.asarray(speed_kmh, float), nan=0.0)
    return np.clip(v / REF_SPEED_KMH, 0.5, 2.0)


def highpass(df: pd.DataFrame, fs: int | None = None, cutoff_hz: float = 1.5) -> np.ndarray:
    """|a| minus its median (gravity), 4th-order Butterworth high-pass, zero-phase.

    Uses `sosfiltfilt` (filtfilt on second-order sections: same zero-phase forward-backward
    filtering, numerically stable). Returns one value per row of `df` (m/s²).
    """
    a = df[["ax", "ay", "az"]].to_numpy(float)
    if len(a) == 0:
        return np.zeros(0)
    mag = np.sqrt((a ** 2).sum(axis=1))
    x = np.nan_to_num(mag - np.nanmedian(mag)) if np.isfinite(mag).any() else np.zeros(len(mag))
    fs = int(fs or estimate_fs(df))
    if cutoff_hz >= 0.45 * fs or len(x) <= 3 * (2 * (FILTER_ORDER // 2) + 1):
        return x - x.mean()  # too short / too slow to filter meaningfully
    sos = butter(FILTER_ORDER, cutoff_hz, btype="highpass", fs=fs, output="sos")
    return sosfiltfilt(sos, x)


def detect_bumps(df: pd.DataFrame, fs: int | None = None) -> pd.DataFrame:
    """Speed-normalized bumps with location and a ±1 s signal snippet (columns BUMP_COLUMNS)."""
    if len(df) < 3:
        return pd.DataFrame(columns=BUMP_COLUMNS)
    fs = int(fs or estimate_fs(df))
    hp = highpass(df, fs)
    speed = df["speed_kmh"].to_numpy(float)
    moving = (np.nan_to_num(speed) >= MIN_SPEED_KMH) & df["lat"].notna().to_numpy() & df["lon"].notna().to_numpy()

    win = max(3, int(STD_WINDOW_S * fs))
    local_std = pd.Series(hp).rolling(win, center=True, min_periods=max(2, win // 4)).std().to_numpy()
    height = np.maximum(STD_FACTOR * np.nan_to_num(local_std), MIN_PEAK_MS2)
    env = np.where(moving, np.abs(hp), 0.0)  # low-speed samples can never be peaks
    peaks, props = find_peaks(env, height=height, distance=max(1, fs // 2))
    if peaks.size == 0:
        return pd.DataFrame(columns=BUMP_COLUMNS)

    # One physical defect is hit by several axles/bogies: keep the strongest peak per MERGE_DIST_M.
    t = df["t"].to_numpy(float)
    dist = np.concatenate([[0.0], np.cumsum(np.diff(t) * np.nan_to_num(speed[1:]) / 3.6)])
    kept: list[int] = []
    for p in peaks[np.argsort(-props["peak_heights"])]:
        if all(abs(dist[p] - dist[k]) >= MERGE_DIST_M for k in kept):
            kept.append(int(p))
    kept.sort()

    rows = []
    for p in kept:
        raw = float(env[p])
        norm = raw / float(speed_factor(speed[p]))
        signal, signal_fs, peak_index = _snippet(hp, p, fs)
        rows.append({
            "t": float(t[p]), "ts": df["ts"].iloc[p], "lat": float(df["lat"].iloc[p]),
            "lon": float(df["lon"].iloc[p]), "speed_kmh": round(float(speed[p]), 2),
            "raw_peak": round(raw, 3), "severity": round(min(1.0, norm / SEVERITY_REF_MS2), 3),
            "signal": signal, "signal_fs": signal_fs, "peak_index": peak_index,
        })
    return pd.DataFrame(rows, columns=BUMP_COLUMNS)


def _snippet(hp: np.ndarray, p: int, fs: int) -> tuple[list[float], int, int]:
    """hp ±1 s around index p, decimated (peak sample always kept) to <= MAX_SIGNAL_POINTS."""
    half = int(round(SIGNAL_HALF_WINDOW_S * fs))
    step = max(1, int(np.ceil(2 * half / MAX_SIGNAL_POINTS)))
    k = half // step
    idx = p + step * np.arange(-k, k)  # 2k <= MAX_SIGNAL_POINTS points, peak at position k
    idx = idx[(idx >= 0) & (idx < len(hp))]
    return [round(float(v), 3) for v in hp[idx]], max(1, int(round(fs / step))), int((idx < p).sum())
