"""Map matching: snap GPS samples to 25 m road/tram segments, plus small geo helpers."""
from __future__ import annotations

import numpy as np

from backend import db
from backend.models import Mode

EARTH_RADIUS_M = 6_371_008.8
COORD_DECIMALS = 5  # 1e-5 deg ~ 1.1 m (lat) / 0.7 m (lon in Warsaw): plenty for 25 m segments


def haversine_m(lon1, lat1, lon2, lat2) -> np.ndarray:
    """Great-circle distance in metres; broadcasts over numpy arrays."""
    lon1, lat1, lon2, lat2 = (np.radians(np.asarray(v, dtype=float)) for v in (lon1, lat1, lon2, lat2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_M * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def match_points(conn, lons, lats, mode: str | Mode | None, max_dist_m: float = 20) -> np.ndarray:
    """Segment id per point (object array, None when unmatched or coordinates are missing).

    A 100 Hz ride repeats almost every GPS position many times, so coordinates are
    rounded to 1e-5 deg, deduplicated and sent to `db.nearest_segments` in one batch.
    """
    lons = np.asarray(lons, dtype=float).ravel()
    lats = np.asarray(lats, dtype=float).ravel()
    out = np.full(len(lons), None, dtype=object)
    valid = np.isfinite(lons) & np.isfinite(lats)
    if not valid.any():
        return out

    keys = np.round(np.column_stack([lons[valid], lats[valid]]), COORD_DECIMALS)
    uniq, inverse = np.unique(keys, axis=0, return_inverse=True)
    ids = db.nearest_segments(
        conn,
        [(float(lon), float(lat)) for lon, lat in uniq],
        mode=str(mode) if mode is not None else None,
        max_dist_m=max_dist_m,
    )
    ids_arr = np.empty(len(uniq), dtype=object)
    ids_arr[:] = [None if i is None else int(i) for i in ids]
    out[valid] = ids_arr[inverse.reshape(-1)]
    return out
