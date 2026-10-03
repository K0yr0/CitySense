"""POST /devices/stream (docs/ARCHITECTURE.md §8.5): device auth, per-device buffering, final processing.

No PostGIS needed: backend.db, the sensor pipeline and fusion are fake modules, so these tests
check auth, buffering, the `devices` upsert and the orchestration contract only.
"""
from __future__ import annotations

import importlib
import sys
import types
from contextlib import contextmanager
from types import SimpleNamespace

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.api import deps
from backend.api import devices as devices_api
from backend.api import rides as rides_api
from backend.main import app

KEYS = {"bus-175-01": "s3cret-a", "tram-17-01": "s3cret-b"}
RIDE_KEYS = {"ride_id", "bumps", "dark_gaps", "segments_covered", "evidence_ids", "incident_ids",
             "verified_incident_ids"}


def install(monkeypatch, name: str, **attrs) -> types.ModuleType:
    """Put a fake module at `name` (sys.modules + attribute on the parent package)."""
    mod = types.ModuleType(name)
    mod.__dict__.update(attrs)
    monkeypatch.setitem(sys.modules, name, mod)
    parent, _, child = name.rpartition(".")
    monkeypatch.setattr(importlib.import_module(parent), child, mod, raising=False)
    return mod


class FakeConn:
    @contextmanager
    def transaction(self):
        yield


@pytest.fixture
def env(monkeypatch, tmp_path):
    conn, calls, db_sql, db_opened = FakeConn(), [], [], []

    def fetch_one(conn, sql, params=None):
        db_sql.append((" ".join(sql.split()), params))
        return {"id": params[0]} if params else None

    def fake_get_db():
        db_opened.append(1)
        yield conn

    state = SimpleNamespace(fail=False, ride_id=5)

    def from_samples(samples):
        calls.append(("from_samples", len(samples)))
        return pd.DataFrame(samples)

    def process_ride(conn, df, *, vehicle_line, mode, device_hash=None, source_file=None):
        calls.append(("process_ride", {"n": len(df), "vehicle_line": vehicle_line, "mode": mode,
                                       "device_hash": device_hash, "source_file": source_file}))
        if state.fail:
            raise RuntimeError("mapmatch failed")
        return {"ride_id": state.ride_id, "evidence_ids": [21], "bumps": 1, "dark_gaps": 0, "segments_covered": 12}

    def ingest_evidence(conn, ids):
        calls.append(("ingest_evidence", list(ids)))
        return [70]

    def check_ride_verifications(conn, ride_id):
        calls.append(("check_ride_verifications", ride_id))
        return [70]

    install(monkeypatch, "backend.db", fetch_one=fetch_one, fetch_all=lambda *a, **k: [])
    install(monkeypatch, "backend.sensor.ingest", from_samples=from_samples)
    install(monkeypatch, "backend.sensor.pipeline", process_ride=process_ride)
    install(monkeypatch, "backend.fusion.incidents", ingest_evidence=ingest_evidence)
    install(monkeypatch, "backend.fusion.verify", check_ride_verifications=check_ride_verifications)
    monkeypatch.setattr(devices_api, "settings", SimpleNamespace(device_keys=dict(KEYS)))
    monkeypatch.setattr(rides_api, "RIDES_DIR", tmp_path / "rides")
    app.dependency_overrides[deps.get_db] = fake_get_db
    devices_api._buffers.clear()
    yield SimpleNamespace(client=TestClient(app), calls=calls, db_sql=db_sql, db_opened=db_opened,
                          state=state, mp=monkeypatch, tmp=tmp_path)
    app.dependency_overrides.clear()
    devices_api._buffers.clear()


def _key(device_id="bus-175-01"):
    return {"X-Device-Key": f"{device_id}:{KEYS[device_id]}"}


def _chunk(n, *, start=0, final=False, line="175", mode="road"):
    samples = [{"t": (start + i) / 100, "ax": 0.1, "ay": 0.2, "az": 9.8, "lat": 52.2, "lon": 21.0, "speed_kmh": 30}
               for i in range(n)]
    return {"vehicle_line": line, "mode": mode, "samples": samples, "final": final}


def _upserts(env):
    return [p for sql, p in env.db_sql if sql.startswith("insert into devices")]


@pytest.mark.parametrize("header", [
    None, "", "bus-175-01", "bus-175-01:", "bus-175-01:wrong", "unknown:s3cret-a", ":s3cret-a",
    "tram-17-01:s3cret-a",  # another device's secret
])
def test_rejects_missing_or_bad_key(env, header):
    headers = {} if header is None else {"X-Device-Key": header}
    r = env.client.post("/devices/stream", json=_chunk(3), headers=headers)
    assert r.status_code == 401
    assert env.db_opened == [] and devices_api._buffers == {}


def test_rejects_everything_when_no_keys_configured(env):
    env.mp.setattr(devices_api, "settings", SimpleNamespace(device_keys={}))
    assert env.client.post("/devices/stream", json=_chunk(3), headers=_key()).status_code == 401


def test_missing_key_wins_over_bad_body(env):
    assert env.client.post("/devices/stream", json={}).status_code == 401
    assert env.client.post("/devices/stream", json={"mode": "metro"}, headers=_key()).status_code == 422


def test_buffers_per_device_and_records_device(env):
    r1 = env.client.post("/devices/stream", json=_chunk(3), headers=_key())
    r2 = env.client.post("/devices/stream", json=_chunk(2, start=3, line=None), headers=_key())
    other = env.client.post("/devices/stream", json=_chunk(4, line="17", mode="tram"), headers=_key("tram-17-01"))
    assert r1.status_code == 200 and r1.json() == {"device_id": "bus-175-01", "buffered": 3}
    assert r2.json() == {"device_id": "bus-175-01", "buffered": 5}
    assert other.json() == {"device_id": "tram-17-01", "buffered": 4}
    assert env.calls == []  # buffering never runs the pipeline

    ups = _upserts(env)
    assert [u[0] for u in ups] == ["bus-175-01", "bus-175-01", "tram-17-01"]
    assert ups[0][2:] == ("175", "road") and ups[1][2] is None  # vehicle_line kept by coalesce in SQL
    assert ups[2][2:] == ("17", "tram")
    assert ups[0][1] == devices_api.key_hash("bus-175-01", KEYS["bus-175-01"])
    assert all(KEYS["bus-175-01"] not in str(p) for p in ups)  # the secret itself is never stored
    assert devices_api._buffers["bus-175-01"]["vehicle_line"] == "175"


def test_final_processes_whole_ride(env):
    env.client.post("/devices/stream", json=_chunk(3), headers=_key())
    r = env.client.post("/devices/stream", json=_chunk(2, start=3, final=True), headers=_key())
    assert r.status_code == 200
    body = r.json()
    assert set(body) == RIDE_KEYS
    assert body == {"ride_id": 5, "bumps": 1, "dark_gaps": 0, "segments_covered": 12, "evidence_ids": [21],
                    "incident_ids": [70], "verified_incident_ids": [70]}
    assert env.calls[0] == ("from_samples", 5)
    meta = env.calls[1][1]
    assert meta["n"] == 5 and meta["vehicle_line"] == "175" and meta["mode"] == "road"
    assert meta["device_hash"] == devices_api.device_hash("bus-175-01") and len(meta["device_hash"]) == 16
    assert meta["source_file"] == "device:bus-175-01"
    assert not (env.tmp / "rides").exists()  # no CSV copy of device rides (they fill the disk)
    assert env.calls[2:] == [("ingest_evidence", [21]), ("check_ride_verifications", 5)]
    assert len(_upserts(env)) == 2  # first chunk + final
    assert "bus-175-01" not in devices_api._buffers


def test_single_final_chunk_is_a_whole_ride(env):
    r = env.client.post("/devices/stream", json=_chunk(4, final=True), headers=_key())
    assert r.status_code == 200 and env.calls[0] == ("from_samples", 4)


def test_failed_final_can_be_retried(env):
    env.client.post("/devices/stream", json=_chunk(4), headers=_key())
    env.state.fail = True
    r = env.client.post("/devices/stream", json=_chunk(2, start=4, final=True), headers=_key())
    assert r.status_code == 500
    assert len(devices_api._buffers["bus-175-01"]["samples"]) == 4  # final chunk removed, buffer kept

    env.state.fail = False
    env.calls.clear()
    r = env.client.post("/devices/stream", json=_chunk(2, start=4, final=True), headers=_key())
    assert r.status_code == 200 and env.calls[0] == ("from_samples", 6)
    assert "bus-175-01" not in devices_api._buffers


def test_empty_final_size_cap_and_expiry(env):
    r = env.client.post("/devices/stream", json={"mode": "road", "samples": [], "final": True}, headers=_key())
    assert r.status_code == 400 and "bus-175-01" not in devices_api._buffers

    env.mp.setattr(rides_api, "MAX_STREAM_SAMPLES", 3)
    assert env.client.post("/devices/stream", json=_chunk(4), headers=_key()).status_code == 413
    devices_api._buffers["stale"] = {"samples": [{}], "vehicle_line": None, "mode": "road", "touched": -1e9}
    assert env.client.post("/devices/stream", json=_chunk(1), headers=_key("tram-17-01")).status_code == 200
    assert "stale" not in devices_api._buffers
