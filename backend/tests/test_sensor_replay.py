"""scripts/replay_ride.py: the incident endpoints are admin-only (B1), so the replay sends an admin token."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import httpx
import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "replay_ride.py"
INCIDENT = {"id": 7, "type": "tram_track", "address": "Marszałkowska", "lat": 52.23, "lon": 21.01, "status": "likely",
            "confidence": 0.7, "report_count": 3, "sensor_rides": 0, "score": 0.5, "has_sensor": False}
RIDE = {"ride_id": 1, "bumps": 2, "dark_gaps": 0, "segments_covered": 40, "evidence_ids": [5],
        "incident_ids": [7], "verified_incident_ids": [7]}


@pytest.fixture
def replay(monkeypatch):
    spec = importlib.util.spec_from_file_location("replay_ride", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run(replay, monkeypatch, tmp_path, argv, *, admin_email="admin@cityecho.test"):
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path, request.headers.get("authorization")))
        path = request.url.path
        if path == "/health":
            return httpx.Response(200, json={"ok": True})
        if path == "/auth/dev":
            return httpx.Response(200, json={"token": "dev-admin", "user": {"role": "admin"}})
        if path.startswith("/incidents/"):
            if request.headers.get("authorization") is None:
                return httpx.Response(401, json={"detail": "not signed in"})
            if path.endswith("/verify"):
                return httpx.Response(200, json={"vehicle": "tram 17", "eta_min": 3})
            return httpx.Response(200, json={**INCIDENT, "status": "verified"} if any(m == "POST" and p == "/rides/upload" for m, p, _ in seen) else INCIDENT)
        if path == "/rides/upload":
            return httpx.Response(200, json=RIDE)
        return httpx.Response(404)

    real_client = httpx.Client
    monkeypatch.setattr(replay.httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))
    from backend.config import settings
    monkeypatch.setattr(type(settings), "admin_emails", property(lambda self: [admin_email] if admin_email else []),
                        raising=False)
    ride = tmp_path / "ride.csv"
    ride.write_text("t,ax\n0,1\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["replay_ride.py", "--file", str(ride), *argv])
    replay.main()
    return seen


def test_incident_calls_carry_the_admin_token(replay, monkeypatch, tmp_path, capsys):
    seen = run(replay, monkeypatch, tmp_path, ["--incident", "7"])
    incident_calls = [(m, p, a) for m, p, a in seen if p.startswith("/incidents/")]
    assert incident_calls and all(a == "Bearer dev-admin" for _, _, a in incident_calls)
    assert ("POST", "/incidents/7/verify", "Bearer dev-admin") in incident_calls
    assert "VERIFIED" in capsys.readouterr().out


def test_explicit_token_wins(replay, monkeypatch, tmp_path):
    seen = run(replay, monkeypatch, tmp_path, ["--incident", "7", "--token", "given"])
    assert not any(p == "/auth/dev" for _, p, _ in seen)
    assert all(a == "Bearer given" for _, p, a in seen if p.startswith("/incidents/"))


def test_without_an_admin_it_stops_with_a_clear_message(replay, monkeypatch, tmp_path):
    with pytest.raises(SystemExit, match="admin-only"):
        run(replay, monkeypatch, tmp_path, ["--incident", "7"], admin_email=None)


def test_plain_upload_needs_no_token(replay, monkeypatch, tmp_path):
    seen = run(replay, monkeypatch, tmp_path, [], admin_email=None)
    assert [p for _, p, _ in seen] == ["/health", "/rides/upload"]
