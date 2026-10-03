"""W3 work flow tests: GET/POST /admin/incidents/{id}/work against a fake DB (no PostGIS).

Checks admin-only access, the update + history log, trust settling exactly once when an
incident becomes done, and that a no-op change writes nothing.
"""
from __future__ import annotations

import importlib
import json
import sys
import types
from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend import config
from backend.api import admin, deps
from backend.auth import tokens
from backend.fusion import trust as trust_mod
from backend.main import app

T0 = datetime(2026, 10, 3, 9, 30, tzinfo=timezone.utc)
ADMIN = {"id": 5, "email": "boss@city.pl", "name": "Boss", "role": "admin"}


class FakeDB:
    """Keeps one incident's work status and jsonb work_log, answering the admin SQL by constant."""

    def __init__(self, work_status: str = "todo") -> None:
        self.incident = {"id": 7, "work_status": work_status, "work_status_changed_at": None,
                         "work_status_by": None, "work_log": []}
        self.calls: list[tuple[str, dict]] = []

    def fetch_one(self, conn, sql, params=None):
        self.calls.append((sql, params))
        p = params or {}
        if sql in (admin.SQL_WORK_LOCK, admin.SQL_WORK_CURRENT):
            if p["id"] != self.incident["id"]:
                return None
            by = ADMIN if self.incident["work_status_by"] == ADMIN["id"] else None
            log = self.incident["work_log"]
            ever_done = any(e["to_status"] == "done" for e in (json.loads(log) if isinstance(log, str) else log))
            return {**self.incident, "ever_done": ever_done,
                    "by_id": by and by["id"], "by_email": by and by["email"], "by_name": by and by["name"]}
        if sql is admin.SQL_WORK_UPDATE:  # mirrors the SQL: note-only keeps since-when / by-whom
            inc = self.incident
            inc["work_log"] = inc["work_log"] + [{"from_status": inc["work_status"], "to_status": p["status"],
                                                  "by_email": p["email"], "by_name": p["name"], "note": p["note"],
                                                  "at": T0.isoformat()}]
            if inc["work_status"] != p["status"]:
                inc.update(work_status=p["status"], work_status_changed_at=T0, work_status_by=p["user_id"])
            return {"id": p["id"]}
        raise AssertionError(f"unexpected SQL: {sql}")

    def fetch_all(self, conn, sql, params=None):
        raise AssertionError(f"unexpected SQL: {sql}")

    def ran(self, sql) -> int:
        return sum(1 for s, _ in self.calls if s is sql)


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
    fdb = FakeDB()
    install(monkeypatch, "backend.db", fetch_one=fdb.fetch_one, fetch_all=fdb.fetch_all)
    settled: list[tuple[int, bool]] = []

    def fake_settle(conn, incident_id, real):
        settled.append((incident_id, real))
        return [11, 12, 13]

    monkeypatch.setattr(trust_mod, "settle", fake_settle)
    app.dependency_overrides[deps.get_db] = lambda: SimpleNamespace()
    headers = {"Authorization": f"Bearer {tokens.issue_token(ADMIN)}"}
    yield SimpleNamespace(db=fdb, client=TestClient(app), headers=headers, settled=settled)
    app.dependency_overrides.clear()


def test_work_endpoints_are_admin_only(env):
    assert env.client.get("/admin/incidents/7/work").status_code == 401
    citizen = tokens.issue_token({**ADMIN, "id": 9, "email": "ala@example.com", "role": "citizen"})
    r = env.client.post("/admin/incidents/7/work", json={"status": "done"},
                        headers={"Authorization": f"Bearer {citizen}"})
    assert r.status_code == 403
    assert env.db.ran(admin.SQL_WORK_UPDATE) == 0 and env.settled == []


def test_get_work_initial_state_and_404(env):
    r = env.client.get("/admin/incidents/7/work", headers=env.headers)
    assert r.status_code == 200
    assert r.json() == {"incident_id": 7, "work_status": "todo", "changed_at": None, "changed_by": None, "history": []}
    assert env.client.get("/admin/incidents/404/work", headers=env.headers).status_code == 404
    assert env.client.post("/admin/incidents/404/work", json={"status": "done"}, headers=env.headers).status_code == 404


def test_flow_logs_who_and_when_and_settles_trust_once(env):
    r = env.client.post("/admin/incidents/7/work", json={"status": "in_progress", "note": "  crew 4  "},
                        headers=env.headers)
    assert r.status_code == 200
    body = r.json()
    assert body["work_status"] == "in_progress" and body["settled_contributors"] == 0
    assert body["changed_at"] == "2026-10-03T09:30:00+00:00"
    assert body["changed_by"] == {"id": 5, "email": "boss@city.pl", "name": "Boss"}
    assert body["history"] == [{"from_status": "todo", "to_status": "in_progress", "by_email": "boss@city.pl",
                                "by_name": "Boss", "note": "crew 4", "at": "2026-10-03T09:30:00+00:00"}]
    assert env.settled == []

    done = env.client.post("/admin/incidents/7/work", json={"status": "done"}, headers=env.headers).json()
    assert done["work_status"] == "done" and done["settled_contributors"] == 3
    assert env.settled == [(7, True)]                                  # trust.settle(real=True)
    assert [h["to_status"] for h in done["history"]] == ["done", "in_progress"]

    again = env.client.post("/admin/incidents/7/work", json={"status": "done"}, headers=env.headers).json()
    assert again["settled_contributors"] == 0 and env.settled == [(7, True)]   # no-op: nothing written
    assert env.db.ran(admin.SQL_WORK_UPDATE) == 2 and len(env.db.incident["work_log"]) == 2

    noted = env.client.post("/admin/incidents/7/work", json={"status": "done", "note": "photo of the repair"},
                            headers=env.headers).json()
    assert noted["history"][0] == {"from_status": "done", "to_status": "done", "by_email": "boss@city.pl",
                                   "by_name": "Boss", "note": "photo of the repair", "at": "2026-10-03T09:30:00+00:00"}
    assert noted["settled_contributors"] == 0 and env.settled == [(7, True)]

    reopened = env.client.post("/admin/incidents/7/work", json={"status": "todo", "note": "came back"},
                               headers=env.headers).json()
    assert reopened["work_status"] == "todo" and env.settled == [(7, True)]
    assert reopened["history"][0]["from_status"] == "done"

    # Done again after a reopen: answers given about the repaired spot are never scored.
    redone = env.client.post("/admin/incidents/7/work", json={"status": "done"}, headers=env.headers).json()
    assert redone["work_status"] == "done" and redone["settled_contributors"] == 0
    assert env.settled == [(7, True)]


def test_bad_status_is_rejected(env):
    r = env.client.post("/admin/incidents/7/work", json={"status": "fixed"}, headers=env.headers)
    assert r.status_code == 422
    assert env.db.ran(admin.SQL_WORK_UPDATE) == 0


def test_sql_shape():
    sql = " ".join(admin.SQL_WORK_UPDATE.split())
    assert "(select id from users where id = %(user_id)s)" in sql          # stale token id -> null, not an FK error
    assert "when work_status = %(status)s then work_status_changed_at" in sql  # note-only keeps "since"
    assert "work_log = coalesce(work_log, '[]'::jsonb) || jsonb_build_array(" in sql
    assert "for update" in admin.SQL_WORK_LOCK
    assert """@> '[{"to_status": "done"}]'::jsonb as ever_done""" in admin.SQL_WORK_LOCK


def test_history_is_newest_first_and_tolerates_a_json_string(env):
    env.db.incident["work_log"] = (
        '[{"from_status": "todo", "to_status": "in_progress", "by_email": "a@city.pl", "by_name": null, '
        '"note": null, "at": "2026-10-01T08:00:00+00:00"}, {"from_status": "in_progress", "to_status": "done", '
        '"by_email": "b@city.pl", "by_name": "B", "note": "ok", "at": "2026-10-02T08:00:00+00:00"}]')
    hist = env.client.get("/admin/incidents/7/work", headers=env.headers).json()["history"]
    assert [h["by_email"] for h in hist] == ["b@city.pl", "a@city.pl"]
