"""Track / road health from continuous vibration: RMS per 25 m segment per ride.

health = 1 - normalize(median RMS across rides), confidence = number of rides.
`health_from_rms` mirrors the SQL `recompute_segment_health()` so offline analysis and
the database agree.
"""
from __future__ import annotations

from typing import Sequence

import numpy as np
import pandas as pd

from backend.sensor.detect import MIN_SPEED_KMH, speed_factor


def _clean_ids(seg_ids, n: int) -> pd.Series:
    ids = pd.Series(list(seg_ids), dtype=object)
    if len(ids) != n:
        raise ValueError(f"seg_ids has {len(ids)} entries for {n} samples")
    return ids.where(ids.notna(), None)


def segment_rms(hp: np.ndarray, seg_ids: Sequence[int | None]) -> pd.Series:
    """RMS of `hp` per segment (unmatched None/NaN samples skipped). Index: segment_id."""
    hp = np.asarray(hp, float)
    ids = _clean_ids(seg_ids, len(hp))
    mask = ids.notna().to_numpy()
    if not mask.any():
        return pd.Series(dtype=float, name="rms").rename_axis("segment_id")
    sq = pd.Series(hp[mask] ** 2, index=ids[mask].astype("int64").to_numpy())
    return np.sqrt(sq.groupby(level=0).mean()).rename("rms").rename_axis("segment_id")


def segment_pass_stats(df: pd.DataFrame, hp: np.ndarray, seg_ids) -> list[dict]:
    """Rows `{segment_id, rms, samples, passed_at}` for db.upsert_ride_segments, in ride order.

    RMS is speed-normalized (hp / clip(speed/30, 0.5, 2), i.e. m/s² at a 30 km/h equivalent)
    so rides at different speeds are comparable, and uses only samples >= 5 km/h. A segment
    the vehicle only crawled/stood on still gets a row (all its samples), because the
    verification loop needs to know the ride passed it.
    """
    hp = np.asarray(hp, float)
    ids = _clean_ids(seg_ids, len(df))
    speed = df["speed_kmh"].to_numpy(float)
    frame = pd.DataFrame({
        "segment_id": ids,
        "sq": (hp / speed_factor(speed)) ** 2,
        "moving": np.nan_to_num(speed) >= MIN_SPEED_KMH,
        "ts": pd.to_datetime(df["ts"], utc=True).reset_index(drop=True),
    })[ids.notna().to_numpy()]
    rows = []
    for seg, g in frame.groupby("segment_id", sort=False):
        use = g[g["moving"]] if g["moving"].any() else g
        rows.append({
            "segment_id": int(seg),
            "rms": round(float(np.sqrt(use["sq"].mean())), 4),
            "samples": int(len(use)),
            "passed_at": g["ts"].iloc[len(g) // 2].to_pydatetime(),
        })
    return rows


def health_from_rms(rms_all: pd.DataFrame, ref: float | None = None) -> pd.DataFrame:
    """Per-segment health from long-format rows `segment_id, rms[, ride_id]` (e.g. ride_segments).

    health = 1 - clip(median_rms / ref, 0, 1) with ref = p99 of the per-segment medians
    (as in SQL) unless an absolute `ref` (m/s²) is given. confidence = distinct rides.
    Returns a DataFrame indexed by segment_id: median_rms, health (0–1), confidence (int).
    """
    df = rms_all if "segment_id" in rms_all else rms_all.reset_index()
    df = df.dropna(subset=["segment_id", "rms"])
    if df.empty:
        return pd.DataFrame(columns=["median_rms", "health", "confidence"]).rename_axis("segment_id")
    g = df.groupby("segment_id")
    med = g["rms"].median()
    conf = g["ride_id"].nunique() if "ride_id" in df else g.size()
    ref = float(ref if ref is not None else med.quantile(0.99))
    health = 1.0 - (med / ref).clip(0, 1) if ref > 0 else pd.Series(1.0, index=med.index)
    return pd.DataFrame({"median_rms": med, "health": health.round(4), "confidence": conf.astype(int)})
