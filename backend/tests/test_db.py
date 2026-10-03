"""Tests for backend/db.py, db/functions.sql and scripts/init_db.py with a fake connection.

A real-PostGIS smoke test runs only with CITYECHO_TEST_DB=1 (uses DATABASE_URL, rolls back).
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest
from psycopg.types.json import Jsonb

from backend import db
from backend.models import EvidenceIn, IssueType, Source, TriageResult

REPO_ROOT = Path(__file__).resolve().parents[2]


def _flat(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).strip()


class FakeCursor:
    def __init__(self, conn: "FakeConn"):
        self.conn = conn
        self.rows: list = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self.conn.calls.append((sql, params))
        self.rows = list(self.conn.results.pop(0)) if self.conn.results else []
        return self

    def executemany(self, sql, params_seq):
        self.conn.many.append((sql, list(params_seq)))

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return list(self.rows)


class FakeConn:
    """Records every statement; `results` is a queue of row lists, one per execute()."""

    def __init__(self, results=None):
        self.calls: list[tuple[str, object]] = []
        self.many: list[tuple[str, list]] = []
        self.results = list(results or [])
        self.closed = False
        self.committed = 0
        self.rolled_back = 0

    def cursor(self, row_factory=None):
        return FakeCursor(self)

    def execute(self, sql, params=None):
        return FakeCursor(self).execute(sql, params)

    def commit(self):
        self.committed += 1

    def rollback(self):
        self.rolled_back += 1


def _load_script(name: str):
    spec = importlib.util.spec_from_file_location(f"_cityecho_{name}", REPO_ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------------------- nearest segments

def test_nearest_segments_single_batched_query_in_input_order():
    coords = [(21.01, 52.23), (21.02, 52.24), (21.03, 52.25)]
    # DB answers out of order and the 2nd point is unmatched (left join -> id null).
    conn = FakeConn(results=[[{"ord": 3, "id": 30}, {"ord": 1, "id": 10}, {"ord": 2, "id": None}]])

    out = db.nearest_segments(conn, coords, mode="tram", max_dist_m=20)

    assert out == [10, None, 30]
    assert len(conn.calls) == 1
    sql, params = conn.calls[0]
    flat = _flat(sql).lower()
    assert "unnest(%(lons)s::float8[], %(lats)s::float8[]) with ordinality" in flat
    assert "left join lateral" in flat
    assert "st_dwithin(s.geom::geography, pts.pt::geography, %(max_dist_m)s::float8)" in flat
    assert "st_setsrid(st_makepoint(p.lon, p.lat), 4326)" in flat
    assert "<->" in flat and "limit 1" in flat
    assert flat.endswith("order by pts.ord")
    assert params == {"lons": [21.01, 21.02, 21.03], "lats": [52.23, 52.24, 52.25], "mode": "tram", "max_dist_m": 20.0}


def test_nearest_segments_accepts_numpy_and_none_mode():
    conn = FakeConn(results=[[{"ord": 1, "id": 7}]])
    out = db.nearest_segments(conn, [(np.float64(21.0), np.float32(52.2))], mode=None, max_dist_m=60)
    assert out == [7]
    params = conn.calls[0][1]
    assert params["mode"] is None and params["max_dist_m"] == 60.0
    assert all(type(v) is float for v in params["lons"] + params["lats"])


def test_nearest_segments_empty_input_runs_no_query():
    conn = FakeConn()
    assert db.nearest_segments(conn, []) == []
    assert conn.calls == []


def test_nearest_segment_delegates_to_batched_query():
    conn = FakeConn(results=[[{"ord": 1, "id": 42}]])
    assert db.nearest_segment(conn, 21.0, 52.2, mode="road") == 42
    assert conn.calls[0][1]["lons"] == [21.0]
    conn = FakeConn(results=[[{"ord": 1, "id": None}]])
    assert db.nearest_segment(conn, 21.0, 52.2) is None


# --------------------------------------------------------------------------- inserts

def test_insert_ride():
    conn = FakeConn(results=[[{"id": 5}]])
    ts = datetime(2026, 10, 1, 8, 0, tzinfo=timezone.utc)
    rid = db.insert_ride(conn, vehicle_line="17", mode="tram", started_at=ts, source_file="a.csv")
    assert rid == 5
    sql, params = conn.calls[0]
    assert "insert into rides" in _flat(sql) and "returning id" in sql
    assert params == ("17", "tram", ts, None, None, "a.csv")


def test_insert_report_denormalizes_structured_and_builds_point():
    conn = FakeConn(results=[[{"id": 9}]])
    structured = {"category": IssueType.ROAD_DAMAGE, "urgency": 4, "department": "ZDM", "summary_en": "Pothole"}
    naive = datetime(2026, 10, 1, 12, 0)
    rid = db.insert_report(
        conn, raw_text="Dziura w jezdni", structured=structured, lon=21.0, lat=52.2,
        location_confidence=0.8, embedding=np.array([0.1, 0.2], dtype=np.float32), created_at=naive,
    )
    assert rid == 9
    sql, p = conn.calls[0]
    flat = _flat(sql)
    assert "insert into reports" in flat
    assert "ST_SetSRID(ST_MakePoint(%(lon)s::float8, %(lat)s::float8), 4326)" in flat
    assert "coalesce(%(created_at)s::timestamptz, now())" in flat
    assert (p["category"], p["urgency"], p["department"]) == ("road_damage", 4, "ZDM")
    assert type(p["category"]) is str
    assert isinstance(p["structured"], Jsonb) and p["structured"].obj["summary_en"] == "Pothole"
    assert p["embedding"] == pytest.approx([0.1, 0.2]) and all(type(v) is float for v in p["embedding"])
    assert (p["lon"], p["lat"], p["source"]) == (21.0, 52.2, "web")
    assert p["created_at"].tzinfo is timezone.utc


def test_insert_report_accepts_triage_model_and_missing_location():
    conn = FakeConn(results=[[{"id": 1}]])
    tri = TriageResult(category="tram_track", urgency=5, department="Tramwaje Warszawskie")
    db.insert_report(conn, raw_text="x", structured=tri, lon=None, lat=52.2, location_confidence=None,
                     embedding=None, duplicate_of=3, source="19115")
    p = conn.calls[0][1]
    assert (p["category"], p["urgency"], p["department"]) == ("tram_track", 5, "Tramwaje Warszawskie")
    assert p["lon"] is None and p["lat"] is None  # half a coordinate is no location
    assert p["embedding"] is None and p["duplicate_of"] == 3 and p["source"] == "19115"
    assert p["created_at"] is None  # -> now() in SQL


def test_insert_evidence_casts_and_wraps_details():
    conn = FakeConn(results=[[{"id": 77}]])
    ev = EvidenceIn(
        source=Source.SENSOR, type=IssueType.TRAM_TRACK, lon=21.0, lat=52.23, severity=1.7,
        ts=datetime(2026, 10, 1, tzinfo=timezone.utc), segment_id=np.int64(12), ride_id=np.int64(3),
        details={"kind": "bump", "signal": np.array([0.1, 0.5], dtype=np.float32), "signal_fs": np.int64(100)},
    )
    assert db.insert_evidence(conn, ev) == 77
    sql, p = conn.calls[0]
    assert "insert into evidence" in _flat(sql)
    assert "ST_SetSRID(ST_MakePoint(%(lon)s::float8, %(lat)s::float8), 4326)" in _flat(sql)
    assert (p["source"], p["type"]) == ("sensor", "tram_track")
    assert type(p["source"]) is str and type(p["segment_id"]) is int and type(p["ride_id"]) is int
    assert p["severity"] == 1.0 and p["report_id"] is None
    assert isinstance(p["details"], Jsonb)
    dumped = json.loads(db._dumps(p["details"].obj))
    assert dumped["signal"] == pytest.approx([0.1, 0.5]) and dumped["signal_fs"] == 100


def test_upsert_ride_segments_batches_and_skips_unmatched():
    conn = FakeConn()
    ts = datetime(2026, 10, 1, tzinfo=timezone.utc)
    db.upsert_ride_segments(conn, np.int64(4), [
        {"segment_id": np.int64(1), "rms": np.float32(0.5), "samples": np.int64(30), "passed_at": ts},
        {"segment_id": None, "rms": 0.2, "samples": 3, "passed_at": ts},
        {"segment_id": 2, "rms": 0.9, "samples": 10, "passed_at": None},
    ])
    assert conn.calls == [] and len(conn.many) == 1
    sql, rows = conn.many[0]
    assert "insert into ride_segments" in _flat(sql)
    assert "on conflict (ride_id, segment_id) do update" in _flat(sql)
    assert rows == [(4, 1, 0.5, 30, ts), (4, 2, 0.9, 10, None)]
    assert all(type(v) is int for v in rows[0][:2])

    empty = FakeConn()
    db.upsert_ride_segments(empty, 4, [])
    assert empty.many == [] and empty.calls == []


def test_recompute_segment_health_calls_sql_function():
    conn = FakeConn()
    db.recompute_segment_health(conn)
    assert [_flat(s) for s, _ in conn.calls] == ["select recompute_segment_health()"]


def test_fetch_helpers():
    conn = FakeConn(results=[[{"a": 1}], [{"a": 1}, {"a": 2}], []])
    assert db.fetch_one(conn, "select 1 as a where %s", (True,)) == {"a": 1}
    assert db.fetch_all(conn, "select a from t") == [{"a": 1}, {"a": 2}]
    assert db.fetch_one(conn, "select 1 where false") is None
    assert conn.calls[0][1] == (True,)


# --------------------------------------------------------------------------- get_conn

class FakePool:
    def __init__(self, conn):
        self.conn = conn

    @contextmanager
    def connection(self):
        yield self.conn


def test_get_conn_commits_on_success(monkeypatch):
    conn = FakeConn()
    monkeypatch.setattr(db, "_get_pool", lambda: FakePool(conn))
    with db.get_conn() as c:
        assert c is conn
    assert (conn.committed, conn.rolled_back) == (1, 0)


def test_get_conn_rolls_back_on_error(monkeypatch):
    conn = FakeConn()
    monkeypatch.setattr(db, "_get_pool", lambda: FakePool(conn))
    with pytest.raises(RuntimeError):
        with db.get_conn():
            raise RuntimeError("boom")
    assert (conn.committed, conn.rolled_back) == (0, 1)


# --------------------------------------------------------------------------- SQL files + init_db

def test_functions_sql_defines_contract_functions():
    sql = _flat((REPO_ROOT / "db" / "functions.sql").read_text(encoding="utf-8")).lower()
    assert "create or replace function nearest_segment( lon float8, lat float8, p_mode text default null, " \
           "max_dist_m float8 default 20 ) returns bigint" in sql
    assert "create or replace function recompute_segment_health() returns void" in sql
    assert "percentile_cont(0.5) within group (order by rms)" in sql
    assert "percentile_cont(0.99) within group (order by med_rms)" in sql
    assert "count(distinct ride_id)" in sql
    assert "least(greatest(" in sql  # clamp to 0..1
    assert sql.count("$$") % 2 == 0


def test_init_db_applies_schema_then_functions():
    init_db = _load_script("init_db")
    conn = FakeConn()
    assert init_db.apply_sql(conn) == ["schema.sql", "functions.sql"]
    assert "create table if not exists segments" in conn.calls[0][0]
    assert "recompute_segment_health" in conn.calls[1][0]
    assert all(params is None for _, params in conn.calls)  # multi-statement scripts need no params

    conn = FakeConn()
    assert init_db.apply_sql(conn, reset=True)[0] == "drop"
    drop = conn.calls[0][0]
    for table in ("segments", "rides", "ride_segments", "reports", "evidence", "incidents", "incident_evidence"):
        assert f"drop table if exists {table} cascade" in drop


def test_init_db_reset_requires_confirmation(monkeypatch):
    init_db = _load_script("init_db")
    monkeypatch.setattr("builtins.input", lambda prompt: "n")
    assert init_db.main(["--reset"]) == 1
    assert init_db.mask_url("postgresql://postgres:s3cret@db.x.supabase.co:5432/postgres") == \
        "postgresql://postgres:***@db.x.supabase.co:5432/postgres"


# --------------------------------------------------------------------------- real PostGIS (opt-in)

@pytest.mark.skipif(os.getenv("CITYECHO_TEST_DB") != "1", reason="needs PostGIS: set CITYECHO_TEST_DB=1")
def test_real_db_roundtrip():
    import psycopg
    from psycopg.rows import dict_row

    from backend.config import settings

    init_db = _load_script("init_db")
    conn = psycopg.connect(settings.database_url, row_factory=dict_row)
    try:
        init_db.migrate(conn)  # schema + functions + migrations, like a real database
        ids = [
            db.fetch_one(conn, "insert into segments (geom, mode) values "
                               "(ST_GeomFromText(%s, 4326), %s) returning id", (wkt, mode))["id"]
            for wkt, mode in [
                ("LINESTRING(21.0000 52.2300, 21.0003 52.2300)", "tram"),
                ("LINESTRING(21.0000 52.2302, 21.0003 52.2302)", "road"),
            ]
        ]
        # ~5 m south of the tram line, ~27 m from the road; a point 1 km away; same point again.
        pts = [(21.00015, 52.22995), (21.0150, 52.2300), (21.00015, 52.22995)]
        assert db.nearest_segments(conn, pts, mode="tram") == [ids[0], None, ids[0]]
        assert db.nearest_segment(conn, 21.00015, 52.23021, mode="road") == ids[1]
        assert db.fetch_one(conn, "select nearest_segment(21.00015, 52.22995, 'tram') as id")["id"] == ids[0]

        ride = db.insert_ride(conn, vehicle_line="17", mode="tram", started_at=datetime.now(timezone.utc))
        db.upsert_ride_segments(conn, ride, [{"segment_id": ids[0], "rms": 0.4, "samples": 10, "passed_at": None},
                                             {"segment_id": ids[1], "rms": 0.1, "samples": 10, "passed_at": None}])
        db.recompute_segment_health(conn)
        rows = db.fetch_all(conn, "select id, health, health_rides from segments where id = any(%s) order by id", (ids,))
        assert [r["health_rides"] for r in rows] == [1, 1]
        assert all(0.0 <= r["health"] <= 1.0 for r in rows) and rows[0]["health"] < rows[1]["health"]
    finally:
        conn.rollback()
        conn.close()
