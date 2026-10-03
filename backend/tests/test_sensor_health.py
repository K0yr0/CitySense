"""S3 live segment health (db/functions.sql recompute_segment_health + migration 301) on real PostGIS.

Needs a database: CITYECHO_TEST_DB=1 and DATABASE_URL pointing at a scratch database (everything
runs in one transaction that is rolled back). Without it only the static checks run.
"""
from __future__ import annotations

import os
import re
from datetime import timedelta
from pathlib import Path

import pytest

from backend import db

REPO_ROOT = Path(__file__).resolve().parents[2]
needs_db = pytest.mark.skipif(os.getenv("CITYECHO_TEST_DB") != "1", reason="needs PostGIS: set CITYECHO_TEST_DB=1")


def _flat(path: str) -> str:
    return re.sub(r"\s+", " ", (REPO_ROOT / path).read_text(encoding="utf-8")).lower()


def test_health_function_is_plpgsql_and_weights_recent_passes():
    sql = _flat("db/functions.sql")
    body = sql[sql.index("create or replace function recompute_segment_health()"):]
    assert "language plpgsql" in body[:200]  # may be applied before migrations 300/301
    assert "filter (where recent <= 5)" in body
    assert "health_weight = round(ps.weight::numeric, 3)" in body and "health_updated_at = ps.last_at" in body
    assert "least(" in body and ", 60)" in body  # exponent clamped: no float underflow on very old data


def test_migration_301_adds_health_weight():
    sql = _flat("db/migrations/301_segment_health_weight.sql")
    assert "alter table segments add column if not exists health_weight real not null default 0" in sql
    assert "select recompute_segment_health()" in sql


@pytest.fixture
def conn():
    import importlib.util

    import psycopg
    from psycopg.rows import dict_row

    from backend.config import settings

    spec = importlib.util.spec_from_file_location("init_db", REPO_ROOT / "scripts" / "init_db.py")
    init_db = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(init_db)
    c = psycopg.connect(settings.database_url, row_factory=dict_row)
    try:
        init_db.migrate(c)
        yield c
    finally:
        c.rollback()
        c.close()


def _segment(conn, k: int) -> int:
    lat = 52.10 + k * 0.001  # outside the demo map, one short road segment each
    return db.fetch_one(conn, "insert into segments (geom, mode) values (ST_GeomFromText(%s, 4326), 'road') "
                              "returning id", (f"LINESTRING(20.9000 {lat}, 20.9003 {lat})",))["id"]


def _pass(conn, seg: int, rms: float, at, *, passed: bool = True) -> int:
    ride = db.insert_ride(conn, vehicle_line="T", mode="road", started_at=at)
    db.upsert_ride_segments(conn, ride, [{"segment_id": seg, "rms": rms, "samples": 10,
                                          "passed_at": at if passed else None}])
    return ride


def _row(conn, seg: int) -> dict:
    return db.fetch_one(conn, "select health, health_rides, health_weight, health_updated_at "
                              "from segments where id = %s", (seg,))


@needs_db
def test_new_passes_outvote_old_ones(conn):
    now = db.fetch_one(conn, "select now() as t")["t"]
    repaired, rough = _segment(conn, 1), _segment(conn, 2)
    for d in range(5):                       # rough for a week ...
        _pass(conn, repaired, 2.0, now - timedelta(days=7 - d))
    db.recompute_segment_health(conn)
    before = _row(conn, repaired)["health"]
    for h in (3, 2, 1):                      # ... then repaired: three clean passes today
        _pass(conn, repaired, 0.1, now - timedelta(hours=h))
    for d in range(3):
        _pass(conn, rough, 2.0, now - timedelta(days=d))
    db.recompute_segment_health(conn)
    after, r = _row(conn, repaired), _row(conn, rough)
    assert after["health"] > 0.9 and after["health"] > before + 0.5
    assert r["health"] < 0.1
    assert after["health_rides"] == 8        # raw amount still counts every ride


@needs_db
def test_freshness_and_time_weighted_amount(conn):
    now = db.fetch_one(conn, "select now() as t")["t"]
    fresh, week, old, fallback = (_segment(conn, k) for k in (3, 4, 5, 6))
    _pass(conn, fresh, 0.5, now)
    _pass(conn, week, 0.5, now - timedelta(days=7))
    _pass(conn, old, 0.5, now - timedelta(days=3650))       # exponent clamped, no underflow
    _pass(conn, fallback, 0.5, now - timedelta(days=1), passed=False)  # no passed_at -> ride start
    db.recompute_segment_health(conn)
    assert _row(conn, fresh)["health_weight"] == pytest.approx(1.0, abs=0.01)
    assert _row(conn, week)["health_weight"] == pytest.approx(0.5, abs=0.01)
    assert _row(conn, old)["health_weight"] == pytest.approx(0.0, abs=0.001)
    assert _row(conn, fresh)["health_updated_at"] == now
    assert _row(conn, week)["health_updated_at"] == now - timedelta(days=7)
    assert _row(conn, fallback)["health_updated_at"] == now - timedelta(days=1)


@needs_db
def test_deleted_rides_reset_segment(conn):
    now = db.fetch_one(conn, "select now() as t")["t"]
    seg = _segment(conn, 7)
    ride = _pass(conn, seg, 0.5, now)
    db.recompute_segment_health(conn)
    assert _row(conn, seg)["health_rides"] == 1
    conn.execute("delete from rides where id = %s", (ride,))
    db.recompute_segment_health(conn)
    assert _row(conn, seg) == {"health": None, "health_rides": 0, "health_weight": 0, "health_updated_at": None}
