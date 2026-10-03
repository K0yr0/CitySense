"""Tests for scripts/load_osm.py: pure parts and the CLI with a fake connection (no osmnx / network / DB)."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
from shapely.geometry import LineString, MultiLineString, Point, Polygon

REPO_ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("_cityecho_load_osm", REPO_ROOT / "scripts" / "load_osm.py")
lo = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lo)


# --------------------------------------------------------------------------- splitting

def _assert_contiguous(line, pieces):
    assert pieces[0].coords[0] == pytest.approx(line.coords[0])
    assert pieces[-1].coords[-1] == pytest.approx(line.coords[-1])
    for a, b in zip(pieces, pieces[1:]):
        assert a.coords[-1] == pytest.approx(b.coords[0])
    assert sum(p.length for p in pieces) == pytest.approx(line.length)


def test_split_straight_line_into_equal_25m_pieces():
    line = LineString([(0, 0), (100, 0)])
    pieces = lo.split_line_metric(line, 25)
    assert [p.length for p in pieces] == pytest.approx([25, 25, 25, 25])
    _assert_contiguous(line, pieces)


def test_split_rounds_piece_count_instead_of_leaving_a_sliver():
    line = LineString([(0, 0), (110, 0)])  # 4.4 steps -> 4 pieces of 27.5 m, no 10 m leftover
    assert [p.length for p in lo.split_line_metric(line, 25)] == pytest.approx([27.5] * 4)
    line = LineString([(0, 0), (40, 0)])  # 1.6 steps -> 2 pieces of 20 m
    assert [p.length for p in lo.split_line_metric(line, 25)] == pytest.approx([20, 20])


def test_split_short_line_kept_whole():
    line = LineString([(0, 0), (10, 0)])
    assert lo.split_line_metric(line, 25) == [line]
    line = LineString([(0, 0), (37, 0)])  # 1.48 steps -> still one piece
    assert lo.split_line_metric(line, 25) == [line]


def test_split_keeps_vertices_of_curved_line():
    line = LineString([(0, 0), (30, 0), (30, 30)])  # 60 m with a corner at 30 m
    pieces = lo.split_line_metric(line, 25)
    assert [p.length for p in pieces] == pytest.approx([30, 30])
    assert list(pieces[0].coords) == [(0, 0), (30, 0)]
    assert list(pieces[1].coords) == [(30, 0), (30, 30)]

    line = LineString([(0, 0), (20, 0), (20, 30)])  # corner inside the first 25 m piece
    first = lo.split_line_metric(line, 25)[0]
    assert (20.0, 0.0) in list(first.coords) and first.length == pytest.approx(25)
    _assert_contiguous(line, lo.split_line_metric(line, 25))


def test_split_multilinestring_and_degenerate_input():
    multi = MultiLineString([[(0, 0), (50, 0)], [(0, 10), (25, 10)]])
    assert [p.length for p in lo.split_line_metric(multi, 25)] == pytest.approx([25, 25, 25])
    assert lo.split_line_metric(LineString(), 25) == []
    assert lo.split_line_metric(LineString([(1, 1), (1, 1)]), 25) == []
    assert lo.split_line_metric(Point(0, 0), 25) == []
    assert lo.split_line_metric(None, 25) == []


def test_build_segments_carries_attributes_and_drops_slivers():
    lines = [
        {"geometry": LineString([(0, 0), (50, 0)]), "mode": "tram", "osm_way_id": 11, "name": None},
        {"geometry": LineString([(0, 5), (0.4, 5)]), "mode": "road", "osm_way_id": 12, "name": "Tiny"},
        {"geometry": LineString([(0, 9), (12, 9)]), "mode": "road", "osm_way_id": 13, "name": "Marszałkowska"},
    ]
    segs = lo.build_segments(lines, 25)
    assert [(s["mode"], s["osm_way_id"], s["name"], s["length_m"]) for s in segs] == [
        ("tram", 11, None, 25.0), ("tram", 11, None, 25.0), ("road", 13, "Marszałkowska", 12.0),
    ]
    assert all(s["vulnerability"] == 0.0 for s in segs)


# --------------------------------------------------------------------------- vulnerability

SEG = LineString([(0, 0), (25, 0)])


def test_vulnerability_weights_within_radius():
    w = lo.VULNERABILITY_WEIGHTS
    pois = {
        "school": [Point(10, 50)],                 # 50 m away -> counts
        "hospital": [Point(10, 150)],              # 150 m away -> ignored
        "platform": [Point(124, 0)],               # 99 m past the segment end -> counts
        "cycleway": [LineString([(0, 101), (25, 101)])],  # 101 m -> ignored
    }
    assert lo.compute_vulnerability([SEG], pois) == [pytest.approx(w["school"] + w["platform"])]


def test_vulnerability_is_presence_based_and_clamped():
    near = Point(5, 5)
    one_kind = {"school": [near, Point(6, 6), Point(7, 7)]}
    assert lo.compute_vulnerability([SEG], one_kind) == [lo.VULNERABILITY_WEIGHTS["school"]]
    all_kinds = {k: [near] for k in lo.VULNERABILITY_WEIGHTS}
    assert sum(lo.VULNERABILITY_WEIGHTS.values()) > 1
    assert lo.compute_vulnerability([SEG], all_kinds) == [1.0]


def test_vulnerability_polygons_unknown_kinds_and_empty_input():
    school_grounds = Polygon([(0, 80), (40, 80), (40, 120), (0, 120)])  # edge 80 m away
    segs = [SEG, LineString([(0, 500), (25, 500)])]
    out = lo.compute_vulnerability(segs, {"school": [school_grounds], "zoo": [Point(0, 0)], "hospital": []})
    assert out == [lo.VULNERABILITY_WEIGHTS["school"], 0.0]
    assert lo.compute_vulnerability([], {"school": [Point(0, 0)]}) == []
    assert lo.compute_vulnerability(segs, {}) == [0.0, 0.0]


def test_fill_missing_names_from_nearest_named_road():
    tram = [LineString([(0, 3), (25, 3)]), LineString([(0, 200), (25, 200)]), LineString([(0, -2), (25, -2)])]
    roads = [LineString([(0, 0), (25, 0)]), LineString([(0, 20), (25, 20)]), LineString([(0, 1), (25, 1)])]
    out = lo.fill_missing_names(tram, [None, None, "Al. Jerozolimskie"], roads, ["Marszałkowska", "Złota", None])
    assert out == ["Marszałkowska", None, "Al. Jerozolimskie"]
    assert lo.fill_missing_names(tram, [None] * 3, [], []) == [None] * 3


# --------------------------------------------------------------------------- helpers, cache, COPY

def test_bbox_modes_and_slug_helpers():
    assert lo.parse_bbox("20.975,52.22,21.02,52.24") == (20.975, 52.22, 21.02, 52.24)
    assert lo.parse_bbox("demo") == lo.DEMO_BBOX
    with pytest.raises(ValueError):
        lo.parse_bbox("52.24,21.02,52.22,20.975")
    with pytest.raises(ValueError):
        lo.parse_bbox("1,2,3")
    assert lo.parse_modes("road, tram") == ["road", "tram"]
    with pytest.raises(ValueError):
        lo.parse_modes("tram,metro")
    assert lo.area_slug("Warszawa, Poland", None) == "warszawa_poland"
    assert lo.area_slug("Łódź", None) == "lodz"
    assert lo.area_slug(None, lo.DEMO_BBOX) == "demo"
    assert lo.cache_path(None, lo.DEMO_BBOX).name == "segments_demo.geojson"
    assert lo.area_slug(None, (20.975, 52.22, 21.02, 52.24)) == "bbox_20.9750_52.2200_21.0200_52.2400"
    grown = lo.expand_bbox(lo.DEMO_BBOX, 150)
    assert grown[1] == pytest.approx(lo.DEMO_BBOX[1] - 150 / 110540)
    assert grown[2] - lo.DEMO_BBOX[2] == pytest.approx(150 / (111320 * 0.6122), rel=1e-2)


def test_clean_name_and_osm_id():
    assert lo.clean_name(["", "Marszałkowska", "Złota"]) == "Marszałkowska"
    assert lo.clean_name(float("nan")) is None and lo.clean_name("  ") is None
    assert lo.osm_id(("way", 123)) == 123 and lo.osm_id([5, 6]) == 5 and lo.osm_id(None) is None


def test_feature_collection_roundtrip():
    segs = [{"geometry": LineString([(21.0123456789, 52.23), (21.0126, 52.2301)]), "mode": "tram",
             "osm_way_id": 99, "name": "Marszałkowska", "length_m": 25.1, "vulnerability": 0.55}]
    fc = json.loads(json.dumps(lo.to_feature_collection(segs, {"modes": ["tram"], "step_m": 25.0})))
    assert fc["type"] == "FeatureCollection" and fc["cityecho"]["step_m"] == 25.0
    assert fc["features"][0]["geometry"]["coordinates"][0] == [21.012346, 52.23]  # 6 decimals (~0.1 m)
    back = lo.from_feature_collection(fc)[0]
    assert {k: back[k] for k in lo.SEGMENT_PROPS} == {k: segs[0][k] for k in lo.SEGMENT_PROPS}
    assert back["geometry"].equals_exact(segs[0]["geometry"], 1e-6)


class _FakeCopy:
    def __init__(self, sink):
        self.sink = sink

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def write_row(self, row):
        self.sink.append(row)


class _FakeCursor:
    def __init__(self, existing):
        self.sql, self.rows, self.existing = [], [], existing

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self.sql.append(sql)

    def fetchone(self):
        return (self.existing,)

    def copy(self, sql):
        self.sql.append(sql)
        return _FakeCopy(self.rows)


class _FakeConn:
    def __init__(self, existing=0):
        self.cur = _FakeCursor(existing)
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.closed = True
        return False

    def cursor(self):
        return self.cur


SEGS = [{"geometry": LineString([(21.0, 52.23), (21.0003, 52.23)]), "mode": "tram",
         "osm_way_id": 7, "name": None, "length_m": 20.5, "vulnerability": 0.2}]


def test_load_segments_copies_ewkb_rows():
    conn = _FakeConn(existing=0)
    assert lo.load_segments(conn, SEGS, modes=["tram"], truncate=False) == 1
    assert conn.cur.sql[1] == lo.COPY_SQL and conn.cur.sql[-1] == "analyze segments"
    geom, *rest = conn.cur.rows[0]
    assert geom.upper().startswith("0102000020E6100000")  # little-endian LineString with SRID 4326
    assert rest == ["tram", 7, None, 20.5, 0.2]


def test_load_segments_truncate_and_duplicate_guard():
    conn = _FakeConn(existing=5)
    with pytest.raises(SystemExit):
        lo.load_segments(conn, SEGS, modes=["tram"], truncate=False)
    assert conn.cur.rows == []
    conn = _FakeConn(existing=5)
    lo.load_segments(conn, SEGS, modes=["tram"], truncate=True)
    assert conn.cur.sql[0] == "truncate segments restart identity cascade"
    assert len(conn.cur.rows) == 1


def test_dry_run_uses_cache_without_osmnx(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(lo, "OSM_DIR", tmp_path)
    path = lo.cache_path(None, lo.DEMO_BBOX)
    path.write_text(json.dumps(lo.to_feature_collection(SEGS, {"modes": ["tram"], "step_m": 25.0})))
    monkeypatch.setattr(lo, "build_network", lambda *a, **k: pytest.fail("should use the cache"))
    monkeypatch.setattr(lo, "REPO_ROOT", tmp_path)
    assert lo.main(["--bbox", "demo", "--modes", "tram", "--dry-run"]) == 0
    assert "tram: 1 segments" in capsys.readouterr().out


# --------------------------------------------------------------------------- --from-geojson / --skip-if-loaded

SEGS2 = SEGS + [{"geometry": LineString([(21.01, 52.23), (21.0103, 52.2301)]), "mode": "road",
                 "osm_way_id": 8, "name": "Marszałkowska", "length_m": 22.0, "vulnerability": 0.0}]


def _write_geojson(path, segs=SEGS2, meta=None):
    path.write_text(json.dumps(lo.to_feature_collection(segs, meta or {"modes": ["road", "tram"], "pois": "ok"})))
    return path


def _no_network(monkeypatch):
    monkeypatch.setattr(lo, "build_network", lambda *a, **k: pytest.fail("must not download"))
    monkeypatch.setattr(lo, "_require_geo", lambda: pytest.fail("must not import osmnx / geopandas"))


def test_from_geojson_loads_all_rows(tmp_path, monkeypatch, capsys):
    _no_network(monkeypatch)
    conn = _FakeConn(existing=0)
    monkeypatch.setattr(lo, "_connect", lambda: conn)
    path = _write_geojson(tmp_path / "segs.geojson")
    assert lo.main(["--from-geojson", str(path)]) == 0
    assert [r[1:] for r in conn.cur.rows] == [("tram", 7, None, 20.5, 0.2), ("road", 8, "Marszałkowska", 22.0, 0.0)]
    assert conn.cur.rows[0][0].upper().startswith("0102000020E6100000")
    assert conn.closed
    assert "Loaded 2 segments" in capsys.readouterr().out


def test_from_geojson_mode_filter_and_dry_run(tmp_path, monkeypatch):
    _no_network(monkeypatch)
    conn = _FakeConn(existing=0)
    monkeypatch.setattr(lo, "_connect", lambda: conn)
    path = _write_geojson(tmp_path / "segs.geojson")
    assert lo.main(["--from-geojson", str(path), "--modes", "road"]) == 0
    assert [r[1] for r in conn.cur.rows] == ["road"]

    monkeypatch.setattr(lo, "_connect", lambda: pytest.fail("dry run must not touch the database"))
    assert lo.main(["--from-geojson", str(path), "--dry-run", "--skip-if-loaded"]) == 0


def test_skip_if_loaded_exits_zero_without_changes(tmp_path, monkeypatch, capsys):
    _no_network(monkeypatch)
    conn = _FakeConn(existing=12)
    monkeypatch.setattr(lo, "_connect", lambda: conn)
    path = _write_geojson(tmp_path / "segs.geojson")
    assert lo.main(["--from-geojson", str(path), "--skip-if-loaded"]) == 0
    assert conn.cur.sql == ["select count(*) as n from segments"]  # only the check, no copy / truncate
    assert conn.cur.rows == []
    assert "nothing to do" in capsys.readouterr().out


def test_skip_if_loaded_loads_into_empty_table(tmp_path, monkeypatch):
    _no_network(monkeypatch)
    conn = _FakeConn(existing=0)
    monkeypatch.setattr(lo, "_connect", lambda: conn)
    path = _write_geojson(tmp_path / "segs.geojson")
    assert lo.main(["--from-geojson", str(path), "--skip-if-loaded"]) == 0
    assert conn.cur.sql[0] == "select count(*) as n from segments"
    assert lo.COPY_SQL in conn.cur.sql and len(conn.cur.rows) == 2


def test_from_geojson_without_skip_refuses_duplicates(tmp_path, monkeypatch):
    _no_network(monkeypatch)
    monkeypatch.setattr(lo, "_connect", lambda: _FakeConn(existing=3))
    path = _write_geojson(tmp_path / "segs.geojson")
    with pytest.raises(SystemExit, match="--truncate"):
        lo.main(["--from-geojson", str(path)])


def test_from_geojson_bad_input(tmp_path, monkeypatch, capsys):
    _no_network(monkeypatch)
    monkeypatch.setattr(lo, "_connect", lambda: pytest.fail("no database for bad input"))
    assert lo.main(["--from-geojson", str(tmp_path / "missing.geojson")]) == 2
    bad = tmp_path / "bad.geojson"
    bad.write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[21, 52], [21.001, 52]]},
         "properties": {"mode": "metro"}}]}))
    assert lo.main(["--from-geojson", str(bad)]) == 2
    assert "unknown mode" in capsys.readouterr().err


def test_from_geojson_needs_no_osmnx_or_geopandas(tmp_path):
    """The Docker image has no osmnx / geopandas: importing them must not be needed."""
    path = _write_geojson(tmp_path / "segs.geojson")
    code = (
        "import sys, runpy\n"
        "sys.modules['osmnx'] = None; sys.modules['geopandas'] = None  # any import now fails\n"
        f"sys.argv = ['load_osm.py', '--from-geojson', {str(path)!r}, '--dry-run']\n"
        f"runpy.run_path({str(REPO_ROOT / 'scripts' / 'load_osm.py')!r}, run_name='__main__')\n"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert "Read" in out.stdout and "2 segments" in out.stdout


def test_committed_demo_geojson_is_valid():
    path = REPO_ROOT / "data" / "osm" / "segments_demo.geojson"
    if not path.exists():
        pytest.skip("data/osm/segments_demo.geojson not generated yet")
    assert path.stat().st_size < 25e6
    segs, meta = lo.read_geojson(path)
    assert {s["mode"] for s in segs} == {"tram", "road"}
    assert meta["step_m"] == 25.0 and meta["bbox"] == list(lo.DEMO_BBOX)
    assert all(0.0 <= s["vulnerability"] <= 1.0 for s in segs)
    assert all(s["geometry"].geom_type == "LineString" for s in segs)


def test_call_with_deadline_and_mirror_fallback(monkeypatch):
    import threading
    import types

    assert lo.call_with_deadline(lambda: 42, 1.0) == 42
    release = threading.Event()
    with pytest.raises(TimeoutError):
        lo.call_with_deadline(lambda: release.wait(5), 0.1)  # a hung call is abandoned, not awaited
    release.set()
    with pytest.raises(KeyError):
        lo.call_with_deadline(lambda: {}["x"], 1.0)

    ox = types.SimpleNamespace(settings=types.SimpleNamespace(overpass_url=None))
    tried = []

    def fetch():
        tried.append(ox.settings.overpass_url)
        if ox.settings.overpass_url != "m3":
            raise ConnectionError("down")
        return "data"

    assert lo.with_mirrors(ox, "pois", fetch, 10, mirrors=("m1", "m2", "m3")) == "data"
    assert tried == ["m1", "m2", "m3"]
    with pytest.raises(RuntimeError, match="every Overpass mirror failed"):
        lo.with_mirrors(ox, "pois", lambda: (_ for _ in ()).throw(ConnectionError("x")), 10, mirrors=("m1",))
