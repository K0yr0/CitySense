"""City health map: 25 m road/tram segments with their vibration health."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from backend.api import serializers as ser
from backend.api.deps import DB
from backend.models import Mode

router = APIRouter(prefix="/segments", tags=["segments"])

DEFAULT_LIMIT = 20_000


def _parse_bbox(bbox: str) -> dict:
    try:
        min_lon, min_lat, max_lon, max_lat = (float(v) for v in bbox.split(","))
    except ValueError as exc:
        raise HTTPException(400, "bbox must be minLon,minLat,maxLon,maxLat") from exc
    if min_lon >= max_lon or min_lat >= max_lat:
        raise HTTPException(400, "bbox min values must be smaller than max values")
    return {"min_lon": min_lon, "min_lat": min_lat, "max_lon": max_lon, "max_lat": max_lat}


@router.get("")
def list_segments(
    conn: DB,
    bbox: str | None = Query(None, description="minLon,minLat,maxLon,maxLat"),
    mode: Mode | None = None,
    measured_only: bool = False,
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=200_000),
) -> dict:
    """Segments as polylines; measured ones first so a truncated result still shows the health map."""
    from backend import db

    where, params = [], {"limit": limit}
    if bbox:
        where.append("s.geom && ST_MakeEnvelope(%(min_lon)s, %(min_lat)s, %(max_lon)s, %(max_lat)s, 4326)")
        params.update(_parse_bbox(bbox))
    if mode is not None:
        where.append("s.mode = %(mode)s")
        params["mode"] = mode.value
    if measured_only:
        where.append("s.health is not null")
    # health / health_rides / health_updated_at are written only by C's sensor code (migration 300).
    sql = ("select s.id, s.mode, s.name, s.health, s.health_rides as rides, s.health_updated_at as updated_at,\n"
           "       ST_AsGeoJSON(s.geom, 6) as geojson\n"
           "from segments s\n"
           + ("where " + " and ".join(where) + "\n" if where else "")
           + "order by (s.health is null), s.id\nlimit %(limit)s")
    return {"segments": [ser.segment_json(r) for r in db.fetch_all(conn, sql, params)]}
