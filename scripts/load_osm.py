"""Load the Warsaw tram + drivable road network from OpenStreetMap into `segments`.

Every OSM line is cut into ~25 m pieces in a metric CRS (EPSG:2180, Poland CS92),
tagged with mode / osm_way_id / name / length_m / vulnerability, converted back to
WGS84, cached as data/osm/segments_<area>.geojson and bulk-loaded with COPY.

    # FAST, OFFLINE (what everyone and Docker use): load the committed city-centre file.
    # Needs only shapely + psycopg (no osmnx / geopandas, no network). Idempotent with --skip-if-loaded.
    python scripts/load_osm.py --from-geojson data/osm/segments_demo.geojson --skip-if-loaded

    # Rebuild from OpenStreetMap (slow Overpass servers; needs backend/requirements-ml.txt):
    .venv/bin/python scripts/load_osm.py --bbox demo --dry-run        # -> data/osm/segments_demo.geojson
    .venv/bin/python scripts/load_osm.py --bbox 20.975,52.208,21.030,52.248 --truncate
    # whole city (several minutes, a few hundred thousand segments)
    .venv/bin/python scripts/load_osm.py --place "Warszawa, Poland" --truncate

Overpass mirrors are tried in order (OVERPASS_MIRRORS) under a hard wall-clock budget per
download, because osmnx's own timeout does not stop a server that trickles bytes. If the
school / hospital / platform / cycleway query fails, segments are written with
vulnerability 0 and the GeoJSON metadata says "pois": "unavailable".

Vulnerability (0–1) = min(1, sum of the weights of the feature kinds present
within 100 m of the segment) — presence, not counts:
    amenity=school 0.35 · amenity=hospital 0.35 · public_transport=platform 0.20 · highway=cycleway 0.15
e.g. a segment next to a school and a tram stop scores 0.55.

Segments without an OSM name borrow the name of the nearest named road piece
within 30 m (tram tracks rarely carry a name), so incidents get a street address.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import threading
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

import numpy as np
import shapely
from shapely import STRtree
from shapely.geometry import LineString, MultiLineString, shape
from shapely.ops import substring

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

OSM_DIR = REPO_ROOT / "data" / "osm"
METRIC_CRS = 2180
DEFAULT_PLACE = "Warszawa, Poland"
# City centre: Rondo Daszyńskiego (W) .. Marszałkowska / Nowy Świat (E), Plac Zbawiciela (S) .. Plac Bankowy (N)
DEMO_BBOX = (20.975, 52.208, 21.030, 52.248)  # covers the synthetic tram 17 ride (data/demo)
MODES = ("tram", "road")

MIN_PIECE_M = 1.0                # drop slivers from tiny OSM connector edges
VULNERABILITY_RADIUS_M = 100.0
VULNERABILITY_WEIGHTS = {"school": 0.35, "hospital": 0.35, "platform": 0.20, "cycleway": 0.15}
POI_TAGS = {"amenity": ["school", "hospital"], "public_transport": "platform", "highway": "cycleway"}
NAME_FILL_DIST_M = 30.0
SKIP_TRAM_SERVICE = {"yard", "siding"}   # depot tracks: no passenger service, only noise for map matching
SEGMENT_PROPS = ("mode", "osm_way_id", "name", "length_m", "vulnerability")
COPY_SQL = "copy segments (geom, mode, osm_way_id, name, length_m, vulnerability) from stdin"
COORD_DECIMALS = 6               # ~0.1 m: plenty for 25 m segments, keeps the committed file small

# Public Overpass mirrors, tried in order. The osmnx cache key (data/cache/osmnx) is a hash of
# mirror URL + query, so a cached answer is only found under the mirror that fetched it.
OVERPASS_MIRRORS = (
    "https://overpass-api.de/api",
    "https://overpass.kumi.systems/api",
    "https://overpass.private.coffee/api",
)
OVERPASS_QUERY_TIMEOUT_S = 300   # sent to Overpass as [timeout:..]; part of the osmnx cache key, keep it fixed
NETWORK_BUDGET_S = 600.0         # hard wall-clock limit for the tram / road downloads (all mirrors)
POI_BUDGET_S = 240.0             # hard wall-clock limit for the POI download (all mirrors)


# =========================================================================== pure geometry

def split_line_metric(line, step_m: float = 25.0) -> list[LineString]:
    """Cut a metric (Multi)LineString into equal consecutive pieces of about `step_m`.

    Uses n = round(length / step_m) pieces (at least one), so every piece is
    0.75–1.5 × step_m long; lines shorter than that are returned whole.
    Original vertices are kept, so curves stay curved.
    """
    if line is None or line.is_empty:
        return []
    if isinstance(line, MultiLineString):
        return [piece for part in line.geoms for piece in split_line_metric(part, step_m)]
    if not isinstance(line, LineString) or step_m <= 0:
        return []
    length = line.length
    if length <= 0:
        return []
    n = max(1, int(length / step_m + 0.5))
    if n == 1:
        return [line]
    size = length / n
    pieces = []
    for i in range(n):
        piece = substring(line, i * size, length if i == n - 1 else (i + 1) * size)
        if isinstance(piece, LineString) and piece.length > 0:
            pieces.append(piece)
    return pieces


def build_segments(lines: Iterable[Mapping[str, Any]], step_m: float = 25.0) -> list[dict]:
    """Split metric lines ({geometry, mode, osm_way_id, name}) into segment dicts with length_m."""
    out = []
    for line in lines:
        for piece in split_line_metric(line["geometry"], step_m):
            if piece.length < MIN_PIECE_M:
                continue
            out.append({
                "geometry": piece,
                "mode": line["mode"],
                "osm_way_id": line.get("osm_way_id"),
                "name": line.get("name"),
                "length_m": round(piece.length, 2),
                "vulnerability": 0.0,
            })
    return out


def compute_vulnerability(
    segments: Sequence,
    pois: Mapping[str, Sequence],
    radius_m: float = VULNERABILITY_RADIUS_M,
    weights: Mapping[str, float] = VULNERABILITY_WEIGHTS,
) -> list[float]:
    """0–1 vulnerability per metric segment from metric POI geometries grouped by kind.

    score = min(1, Σ weight[kind] for every kind with at least one feature within radius_m).
    """
    if len(segments) == 0:
        return []
    segs = np.asarray(segments, dtype=object)
    total = np.zeros(len(segs))
    for kind, geoms in pois.items():
        weight = weights.get(kind, 0.0)
        geoms = [g for g in geoms if g is not None and not g.is_empty]
        if not weight or not geoms:
            continue
        seg_idx, _ = STRtree(geoms).query(segs, predicate="dwithin", distance=radius_m)
        hit = np.zeros(len(segs), dtype=bool)
        hit[seg_idx] = True
        total += weight * hit
    return [round(float(min(1.0, v)), 3) for v in total]


def fill_missing_names(
    geoms: Sequence,
    names: Sequence[str | None],
    ref_geoms: Sequence,
    ref_names: Sequence[str | None],
    max_dist_m: float = NAME_FILL_DIST_M,
) -> list[str | None]:
    """Give unnamed geometries the name of the nearest named reference line within max_dist_m."""
    out = list(names)
    ref = [(g, n) for g, n in zip(ref_geoms, ref_names) if n]
    missing = [i for i, n in enumerate(out) if not n]
    if not ref or not missing:
        return out
    tree = STRtree([g for g, _ in ref])
    src_idx, ref_idx = tree.query_nearest([geoms[i] for i in missing], max_distance=max_dist_m)
    for a, b in zip(src_idx, ref_idx):
        i = missing[int(a)]
        if not out[i]:  # ties return several matches: keep the first
            out[i] = ref[int(b)][1]
    return out


# =========================================================================== pure helpers

def parse_bbox(text: str) -> tuple[float, float, float, float]:
    """'minLon,minLat,maxLon,maxLat' (or 'demo') -> tuple."""
    if text.strip().lower() == "demo":
        return DEMO_BBOX
    parts = [float(p) for p in text.split(",")]
    if len(parts) != 4:
        raise ValueError("bbox must be minLon,minLat,maxLon,maxLat")
    min_lon, min_lat, max_lon, max_lat = parts
    if not (min_lon < max_lon and min_lat < max_lat and -90 <= min_lat and max_lat <= 90):
        raise ValueError(f"invalid bbox {text!r}: expected minLon,minLat,maxLon,maxLat")
    return min_lon, min_lat, max_lon, max_lat


def parse_modes(text: str) -> list[str]:
    modes = sorted({m.strip() for m in text.split(",") if m.strip()})
    bad = [m for m in modes if m not in MODES]
    if bad or not modes:
        raise ValueError(f"modes must be a comma list of {MODES}, got {text!r}")
    return modes


def expand_bbox(bbox: tuple[float, float, float, float], meters: float) -> tuple[float, float, float, float]:
    """Grow a WGS84 bbox by `meters` on every side (so POIs just outside still count)."""
    min_lon, min_lat, max_lon, max_lat = bbox
    dlat = meters / 110540.0
    dlon = meters / (111320.0 * math.cos(math.radians((min_lat + max_lat) / 2)))
    return min_lon - dlon, min_lat - dlat, max_lon + dlon, max_lat + dlat


def area_slug(place: str | None, bbox: tuple[float, float, float, float] | None) -> str:
    """File-name-safe area id: 'demo', 'bbox_20.9750_52.2200_21.0200_52.2400' or 'warszawa_poland'."""
    if bbox and tuple(bbox) == DEMO_BBOX:
        return "demo"
    if bbox:
        return "bbox_" + "_".join(f"{v:.4f}" for v in bbox)
    text = unicodedata.normalize("NFKD", (place or "area").replace("ł", "l").replace("Ł", "L"))
    text = text.encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_") or "area"


def cache_path(place: str | None, bbox: tuple[float, float, float, float] | None) -> Path:
    return OSM_DIR / f"segments_{area_slug(place, bbox)}.geojson"


def clean_name(value: Any) -> str | None:
    """OSM name value -> str or None (lists from merged edges -> first non-empty, NaN -> None)."""
    if isinstance(value, (list, tuple)):
        return next((n for n in (clean_name(v) for v in value) if n), None)
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    text = str(value).strip()
    return text or None


def osm_id(value: Any) -> int | None:
    """OSM id from a features index tuple ('way', 123), a list of ids, or a scalar."""
    if isinstance(value, tuple):
        value = value[-1]
    if isinstance(value, list):
        value = value[0] if value else None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def to_feature_collection(
    segments: Sequence[Mapping[str, Any]], meta: Mapping[str, Any] | None = None, decimals: int = COORD_DECIMALS
) -> dict:
    """WGS84 segment dicts -> GeoJSON FeatureCollection (meta stored under 'cityecho')."""
    features = []
    for s in segments:
        coords = [[round(x, decimals), round(y, decimals)] for x, y, *_ in s["geometry"].coords]
        features.append({
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": coords},
            "properties": {k: s.get(k) for k in SEGMENT_PROPS},
        })
    return {"type": "FeatureCollection", "cityecho": dict(meta or {}), "features": features}


def from_feature_collection(fc: Mapping[str, Any]) -> list[dict]:
    """GeoJSON FeatureCollection -> WGS84 segment dicts."""
    out = []
    for f in fc.get("features", []):
        props = f.get("properties") or {}
        seg = {k: props.get(k) for k in SEGMENT_PROPS}
        seg["geometry"] = shape(f["geometry"])
        seg["vulnerability"] = float(seg["vulnerability"] or 0.0)
        out.append(seg)
    return out


# =========================================================================== OSM download

def _require_geo():
    """Import osmnx + geopandas lazily (they live in backend/requirements-ml.txt)."""
    try:
        import geopandas as gpd
        import osmnx as ox
    except ImportError as exc:
        raise SystemExit(
            f"load_osm.py needs osmnx and geopandas ({exc.name or exc} is missing).\n"
            "Install the extras: .venv/bin/pip install -r backend/requirements-ml.txt\n"
            "(or use a cached data/osm/segments_<area>.geojson)"
        ) from None
    ox.settings.use_cache = True
    ox.settings.cache_folder = str(REPO_ROOT / "data" / "cache" / "osmnx")
    ox.settings.requests_timeout = OVERPASS_QUERY_TIMEOUT_S
    ox.settings.overpass_rate_limit = False  # mirrors' /status pauses were one source of the hangs
    ox.settings.log_console = False
    return ox, gpd


def call_with_deadline(fn, timeout_s: float):
    """Run fn() in a daemon thread; return its result or raise TimeoutError after timeout_s.

    A stuck HTTP read cannot be interrupted from outside, so on timeout the worker thread is
    abandoned (daemon: it dies with the process) and the caller moves on.
    """
    box: dict[str, Any] = {}

    def run():
        try:
            box["value"] = fn()
        except BaseException as exc:  # noqa: BLE001 - re-raised in the caller's thread
            box["error"] = exc

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    worker.join(max(0.0, timeout_s))
    if worker.is_alive():
        raise TimeoutError(f"no answer within {timeout_s:.0f} s")
    if "error" in box:
        raise box["error"]
    return box.get("value")


def with_mirrors(ox, label: str, fn, budget_s: float, mirrors: Sequence[str] = OVERPASS_MIRRORS):
    """fn() against each Overpass mirror in turn, all within budget_s seconds of wall clock.

    Each attempt gets an equal share of the remaining budget (a mirror that fails fast leaves
    more time for the next). Raises RuntimeError listing every failure when all mirrors fail.
    """
    deadline = time.monotonic() + budget_s
    errors = []
    for i, url in enumerate(mirrors):
        remaining = deadline - time.monotonic()
        if remaining <= 1:
            errors.append(f"{url}: budget exhausted")
            break
        share = remaining / (len(mirrors) - i)
        ox.settings.overpass_url = url
        started = time.monotonic()
        try:
            result = call_with_deadline(fn, share)
            print(f"  {label}: {url} answered in {time.monotonic() - started:.1f} s")
            return result
        except Exception as exc:  # noqa: BLE001 - try the next mirror
            msg = f"{type(exc).__name__}: {exc}"[:200]
            print(f"  {label}: {url} failed after {time.monotonic() - started:.0f} s ({msg})")
            errors.append(f"{url}: {msg}")
    raise RuntimeError(f"{label}: every Overpass mirror failed within {budget_s:.0f} s: " + "; ".join(errors))


def _is_empty_response(exc: Exception) -> bool:
    return type(exc).__name__ in {"InsufficientResponseError", "EmptyOverpassResponse"}


def _features(ox, place: str | None, bbox, tags: dict):
    """osmnx features for a bbox (left, bottom, right, top) or a place; None when nothing matches."""
    try:
        if bbox:
            return ox.features_from_bbox(bbox, tags=tags)
        return ox.features_from_place(place, tags=tags)
    except Exception as exc:  # noqa: BLE001 - osmnx raises its own error type for "no data"
        if _is_empty_response(exc):
            return None
        raise


def _column(gdf, name: str) -> list:
    return list(gdf[name]) if name in gdf.columns else [None] * len(gdf)


def fetch_tram_lines(ox, place: str | None, bbox) -> list[dict]:
    """railway=tram ways as metric line dicts."""
    gdf = _features(ox, place, bbox, {"railway": "tram"})
    if gdf is None or gdf.empty:
        return []
    gdf = gdf[gdf.geometry.geom_type.isin(["LineString", "MultiLineString"])]
    if "service" in gdf.columns:
        gdf = gdf[~gdf["service"].isin(SKIP_TRAM_SERVICE)]
    gdf = gdf.to_crs(METRIC_CRS)
    return [
        {"geometry": geom, "mode": "tram", "osm_way_id": osm_id(idx), "name": clean_name(name)}
        for idx, geom, name in zip(gdf.index, gdf.geometry, _column(gdf, "name"))
    ]


def fetch_road_lines(ox, place: str | None, bbox) -> list[dict]:
    """Drivable road edges (network_type='drive') as metric line dicts, one per physical road."""
    try:
        if bbox:
            graph = ox.graph_from_bbox(bbox, network_type="drive", retain_all=True, truncate_by_edge=True)
        else:
            graph = ox.graph_from_place(place, network_type="drive", retain_all=True)
    except Exception as exc:  # noqa: BLE001
        if _is_empty_response(exc) or isinstance(exc, ValueError):
            print(f"  no drivable roads found ({exc})")
            return []
        raise
    edges = ox.graph_to_gdfs(graph, nodes=False, fill_edge_geometry=True)
    # Two-way streets appear as u->v and v->u: keep one copy per (orientation-free) geometry.
    keys = shapely.to_wkb(shapely.normalize(np.asarray(edges.geometry.values, dtype=object)))
    seen: set[bytes] = set()
    keep = []
    for key in keys:
        keep.append(key not in seen)
        seen.add(key)
    edges = edges[np.asarray(keep)].to_crs(METRIC_CRS)
    return [
        {"geometry": geom, "mode": "road", "osm_way_id": osm_id(oid), "name": clean_name(name) or clean_name(ref)}
        for geom, oid, name, ref in zip(
            edges.geometry, _column(edges, "osmid"), _column(edges, "name"), _column(edges, "ref")
        )
    ]


def fetch_pois(ox, place: str | None, bbox) -> dict[str, list]:
    """Metric geometries of school / hospital / platform / cycleway features around the area."""
    query_bbox = expand_bbox(bbox, VULNERABILITY_RADIUS_M * 1.5) if bbox else None
    gdf = _features(ox, place, query_bbox, POI_TAGS)
    if gdf is None or gdf.empty:
        return {}
    gdf = gdf.to_crs(METRIC_CRS)
    geoms = list(gdf.geometry)
    amenity = _column(gdf, "amenity")
    columns = {
        "school": [a == "school" for a in amenity],
        "hospital": [a == "hospital" for a in amenity],
        "platform": [v == "platform" for v in _column(gdf, "public_transport")],
        "cycleway": [v == "cycleway" for v in _column(gdf, "highway")],
    }
    return {kind: [g for g, m in zip(geoms, mask) if m] for kind, mask in columns.items()}


def build_network(
    place: str | None, bbox, modes: Sequence[str], step_m: float,
    poi_budget_s: float = POI_BUDGET_S, info: dict | None = None,
) -> list[dict]:
    """Download OSM data and return WGS84 segment dicts ready for GeoJSON / COPY.

    `info` (if given) receives "pois": "ok" | "none" | "unavailable" for the GeoJSON metadata.
    """
    ox, gpd = _require_geo()
    info = info if info is not None else {}
    area = f"bbox {bbox}" if bbox else repr(place)
    lines: list[dict] = []
    try:
        if "tram" in modes:
            print(f"Downloading railway=tram for {area} ...")
            tram = with_mirrors(ox, "tram", lambda: fetch_tram_lines(ox, place, bbox), NETWORK_BUDGET_S)
            print(f"  {len(tram)} tram ways")
            lines += tram
        if "road" in modes:
            print(f"Downloading drive network for {area} ...")
            road = with_mirrors(ox, "road", lambda: fetch_road_lines(ox, place, bbox), NETWORK_BUDGET_S)
            print(f"  {len(road)} road edges")
            lines += road
    except RuntimeError as exc:
        raise SystemExit(f"{exc}\nTry again later, or load the committed data/osm/segments_demo.geojson "
                         "with --from-geojson.") from None

    segments = build_segments(lines, step_m)
    if not segments:
        return []
    print(f"Split into {len(segments)} segments of ~{step_m:g} m")

    print(f"Downloading schools / hospitals / platforms / cycleways (hard limit {poi_budget_s:.0f} s) ...")
    try:
        pois = with_mirrors(ox, "pois", lambda: fetch_pois(ox, place, bbox), poi_budget_s)
        info["pois"] = "ok" if pois else "none"
        print("  " + ", ".join(f"{k}: {len(v)}" for k, v in pois.items()) if pois else "  none found")
    except RuntimeError as exc:
        pois = {}
        info["pois"] = "unavailable"
        print(f"WARNING: {exc}\nWARNING: POIs unavailable, every segment gets vulnerability 0.", file=sys.stderr)
    metric = [s["geometry"] for s in segments]
    vulnerability = compute_vulnerability(metric, pois)

    roads = [s for s in segments if s["mode"] == "road"]
    names = fill_missing_names(
        metric, [s["name"] for s in segments], [r["geometry"] for r in roads], [r["name"] for r in roads]
    )

    wgs84 = list(gpd.GeoSeries(metric, crs=METRIC_CRS).to_crs(4326))
    for seg, geom, vul, name in zip(segments, wgs84, vulnerability, names):
        seg.update(geometry=geom, vulnerability=vul, name=name)
    return segments


# =========================================================================== database

def segment_rows(segments: Iterable[Mapping[str, Any]]) -> Iterator[tuple]:
    """COPY rows: (hex EWKB geom with SRID 4326, mode, osm_way_id, name, length_m, vulnerability)."""
    for s in segments:
        geom = shapely.to_wkb(shapely.set_srid(s["geometry"], 4326), hex=True, include_srid=True)
        yield (
            geom,
            s["mode"],
            osm_id(s.get("osm_way_id")),
            s.get("name"),
            float(s["length_m"]) if s.get("length_m") is not None else None,
            float(s.get("vulnerability") or 0.0),
        )


def _scalar(row) -> int:
    return int(row["n"] if isinstance(row, dict) else row[0])


def count_segments(conn, modes: Sequence[str] | None = None) -> int:
    """Rows in `segments` (optionally only these modes)."""
    with conn.cursor() as cur:
        if modes:
            cur.execute("select count(*) as n from segments where mode = any(%s)", (list(modes),))
        else:
            cur.execute("select count(*) as n from segments")
        return _scalar(cur.fetchone())


def load_segments(conn, segments: Sequence[Mapping[str, Any]], *, modes: Sequence[str], truncate: bool) -> int:
    """Bulk-load segments with COPY. Refuses to duplicate already loaded modes unless truncate."""
    with conn.cursor() as cur:
        if truncate:
            # Cascades to ride_segments / evidence / incidents: their segment ids would be stale anyway.
            cur.execute("truncate segments restart identity cascade")
        else:
            cur.execute("select count(*) as n from segments where mode = any(%s)", (list(modes),))
            existing = _scalar(cur.fetchone())
            if existing:
                raise SystemExit(
                    f"segments already holds {existing} rows for modes {list(modes)}; "
                    "re-run with --truncate to replace the network (or --skip-if-loaded to keep it)."
                )
        with cur.copy(COPY_SQL) as copy:
            for row in segment_rows(segments):
                copy.write_row(row)
        cur.execute("analyze segments")
    return len(segments)


def _connect():
    """psycopg connection to settings.database_url (commits when the `with` block exits cleanly)."""
    import psycopg

    from backend.config import settings

    return psycopg.connect(settings.database_url, prepare_threshold=None)


# =========================================================================== CLI

def resolve_path(text: str) -> Path:
    """A user path: as given (relative to the cwd), else relative to the repo root."""
    path = Path(text).expanduser()
    if not path.is_absolute() and not path.exists() and (REPO_ROOT / path).exists():
        return REPO_ROOT / path
    return path


def _display(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def read_geojson(path: Path) -> tuple[list[dict], dict]:
    """(segments, cityecho metadata) from a segments GeoJSON written by this script."""
    fc = json.loads(path.read_text(encoding="utf-8"))
    if fc.get("type") != "FeatureCollection":
        raise ValueError(f"{path} is not a GeoJSON FeatureCollection")
    segments = from_feature_collection(fc)
    bad = sorted({str(s["mode"]) for s in segments if s["mode"] not in MODES})
    if bad:
        raise ValueError(f"{path}: unknown mode(s) {bad}; expected {MODES}")
    return segments, dict(fc.get("cityecho") or {})


def print_summary(segments: Sequence[Mapping[str, Any]], modes: Sequence[str]) -> None:
    for mode in modes:
        sel = [s for s in segments if s["mode"] == mode]
        if sel:
            km = sum(s["length_m"] or 0 for s in sel) / 1000
            vul = sum(s["vulnerability"] for s in sel) / len(sel)
            print(f"  {mode}: {len(sel)} segments, {km:.1f} km, mean vulnerability {vul:.2f}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--from-geojson", metavar="PATH",
                        help="load this segments GeoJSON instead of downloading (no osmnx / network needed)")
    parser.add_argument("--skip-if-loaded", action="store_true",
                        help="exit 0 without changes when `segments` already has rows (any mode)")
    parser.add_argument("--place", default=DEFAULT_PLACE, help=f"OSM place name (default {DEFAULT_PLACE!r})")
    parser.add_argument("--bbox", help="minLon,minLat,maxLon,maxLat, or 'demo' for the city centre; overrides --place")
    parser.add_argument("--modes", default="tram,road", help="comma list of tram,road (default both)")
    parser.add_argument("--step-m", type=float, default=25.0, help="target segment length in metres (default 25)")
    parser.add_argument("--dry-run", action="store_true", help="only write / read the GeoJSON, no database")
    parser.add_argument("--truncate", action="store_true",
                        help="empty `segments` first (all modes; cascades to ride_segments/evidence/incidents)")
    parser.add_argument("--refresh", action="store_true", help="ignore the GeoJSON cache and re-download")
    parser.add_argument("--poi-timeout", type=float, default=POI_BUDGET_S,
                        help=f"hard wall-clock limit (s) for the POI download over all mirrors (default {POI_BUDGET_S:g})")
    args = parser.parse_args(argv)

    try:
        bbox = parse_bbox(args.bbox) if args.bbox else None
        modes = parse_modes(args.modes)
    except ValueError as exc:
        parser.error(str(exc))

    source = resolve_path(args.from_geojson) if args.from_geojson else None
    if source is not None and not source.is_file():
        print(f"GeoJSON not found: {args.from_geojson}", file=sys.stderr)
        return 2

    if args.skip_if_loaded and not args.dry_run:
        with _connect() as conn:
            existing = count_segments(conn)
        if existing:
            print(f"segments already has {existing} rows: nothing to do (--skip-if-loaded).")
            return 0

    if source is not None:
        try:
            segments, meta = read_geojson(source)
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            print(f"Cannot read {args.from_geojson}: {exc}", file=sys.stderr)
            return 2
        segments = [s for s in segments if s["mode"] in modes]
        print(f"Read {_display(source)}: {len(segments)} segments (pois: {meta.get('pois', 'unknown')})")
        if not segments:
            print(f"No {modes} segments in {args.from_geojson}.", file=sys.stderr)
            return 1
    else:
        place = None if bbox else args.place
        path = cache_path(place, bbox)
        segments = None
        if path.exists() and not args.refresh:
            fc = json.loads(path.read_text(encoding="utf-8"))
            meta = fc.get("cityecho", {})
            if meta.get("modes") == modes and meta.get("step_m") == args.step_m:
                segments = from_feature_collection(fc)
                print(f"Using cached {_display(path)} ({len(segments)} segments; --refresh to re-download)")
        if segments is None:
            info: dict = {}
            segments = build_network(place, bbox, modes, args.step_m, poi_budget_s=args.poi_timeout, info=info)
            if not segments:
                print("No segments found for this area.", file=sys.stderr)
                return 1
            meta = {
                "place": place, "bbox": list(bbox) if bbox else None, "modes": modes, "step_m": args.step_m,
                "vulnerability_radius_m": VULNERABILITY_RADIUS_M, "vulnerability_weights": VULNERABILITY_WEIGHTS,
                "pois": info.get("pois", "unknown"),
                "source": "OpenStreetMap contributors (ODbL), via Overpass",
                "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(to_feature_collection(segments, meta), ensure_ascii=False,
                                       separators=(",", ":")), encoding="utf-8")
            print(f"Wrote {_display(path)} ({path.stat().st_size / 1e6:.1f} MB)")

    print_summary(segments, modes)

    if args.dry_run:
        print("Dry run: database untouched.")
        return 0

    with _connect() as conn:  # commits on clean exit
        n = load_segments(conn, segments, modes=modes, truncate=args.truncate)
    print(f"Loaded {n} segments into the database.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
