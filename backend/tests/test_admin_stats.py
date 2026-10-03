"""W5 statistics tests: GET /admin/stats shape, rounding, empty database and admin-only access (fake DB)."""
from __future__ import annotations

import importlib
import sys
import types
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend import config
from backend.api import admin, deps
from backend.auth import tokens
from backend.main import app

ADMIN = {"id": 5, "email": "boss@city.pl", "name": "Boss", "role": "admin"}


def install(monkeypatch, name: str, **attrs) -> types.ModuleType:
    mod = types.ModuleType(name)
    mod.__dict__.update(attrs)
    monkeypatch.setitem(sys.modules, name, mod)
    parent, _, child = name.rpartition(".")
    monkeypatch.setattr(importlib.import_module(parent), child, mod, raising=False)
    return mod


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setattr(config, "settings", replace(config.settings, auth_secret="test-secret-" + "x" * 32,
                                                    admin_emails=[ADMIN["email"]]))
    answers: dict = {}
    calls: list = []

    def fetch_one(conn, sql, params=None):
        calls.append((sql, params))
        return answers.get(sql)

    def fetch_all(conn, sql, params=None):
        calls.append((sql, params))
        return answers.get(sql) or []

    install(monkeypatch, "backend.db", fetch_one=fetch_one, fetch_all=fetch_all)
    app.dependency_overrides[deps.get_db] = lambda: SimpleNamespace()
    headers = {"Authorization": f"Bearer {tokens.issue_token(ADMIN)}"}
    yield SimpleNamespace(answers=answers, calls=calls, client=TestClient(app), headers=headers)
    app.dependency_overrides.clear()


def test_stats_shape_and_rounding(env):
    env.answers[admin.SQL_STATS] = {
        "reports_total": 412, "incidents_total": 63, "verified_total": 21, "in_progress_total": 4, "done_total": 9,
        "found_before_report": 7, "avg_repair_hours": Decimal("30.456"), "median_repair_hours": 22.04,
        "avg_verification_min": Decimal("7.26")}
    env.answers[admin.SQL_STATS_DEPARTMENTS] = [
        {"department": "ZDM", "total": 40, "todo": 25, "in_progress": 3, "done": 8, "verified": 15,
         "avg_repair_hours": Decimal("28.91")},
        {"department": "MPWiK", "total": 5, "todo": 4, "in_progress": 1, "done": 0, "verified": 1, "avg_repair_hours": None},
    ]
    days = [date(2026, 10, 3) - timedelta(days=n) for n in range(admin.TREND_DAYS - 1, -1, -1)]
    env.answers[admin.SQL_STATS_DAILY] = [{"day": d, "new": n % 3, "done": n % 2} for n, d in enumerate(days)]

    r = env.client.get("/admin/stats", headers=env.headers)
    assert r.status_code == 200
    body = r.json()
    assert {k: body[k] for k in ("reports_total", "incidents_total", "verified_total", "in_progress_total",
                                 "done_total", "found_before_report")} == {
        "reports_total": 412, "incidents_total": 63, "verified_total": 21, "in_progress_total": 4,
        "done_total": 9, "found_before_report": 7}
    assert body["avg_repair_hours"] == 30.5 and body["median_repair_hours"] == 22.0
    assert body["avg_verification_min"] == 7.3
    assert body["departments"][0] == {"department": "ZDM", "total": 40, "todo": 25, "in_progress": 3, "done": 8,
                                      "verified": 15, "avg_repair_hours": 28.9}
    assert body["departments"][1]["avg_repair_hours"] is None
    assert len(body["daily"]) == admin.TREND_DAYS
    assert body["daily"][-1] == {"day": "2026-10-03", "new": 13 % 3, "done": 13 % 2}
    (_, params), = [c for c in env.calls if c[0] is admin.SQL_STATS_DAILY]
    assert params == {"days": admin.TREND_DAYS}


def test_stats_empty_database(env):
    body = env.client.get("/admin/stats", headers=env.headers).json()
    assert body["incidents_total"] == 0 and body["done_total"] == 0
    assert body["avg_repair_hours"] is None and body["median_repair_hours"] is None and body["avg_verification_min"] is None
    assert body["departments"] == [] and body["daily"] == []


def test_stats_is_admin_only(env):
    assert env.client.get("/admin/stats").status_code == 401
    citizen = tokens.issue_token({**ADMIN, "id": 9, "email": "ala@example.com", "role": "citizen"})
    assert env.client.get("/admin/stats", headers={"Authorization": f"Bearer {citizen}"}).status_code == 403


def test_repair_time_only_counts_done_incidents():
    for sql in (admin.SQL_STATS, admin.SQL_STATS_DEPARTMENTS):
        flat = " ".join(sql.split())
        assert "work_status = 'done' and work_status_changed_at >= first_seen" in flat
    assert "generate_series" in admin.SQL_STATS_DAILY and "%(days)s" in admin.SQL_STATS_DAILY
