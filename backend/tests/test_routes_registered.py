"""Every router is registered in backend/main.py on Day 0, so nobody has to edit that shared file later."""
from __future__ import annotations

from fastapi.testclient import TestClient

from backend.api import incidents as incidents_api, responses as responses_api
from backend.main import ROUTERS, app

EXPECTED = {
    ("GET", "/health"),
    # existing (docs/ARCHITECTURE.md §6)
    ("GET", "/segments"),
    ("GET", "/incidents"), ("GET", "/incidents/{incident_id}"), ("POST", "/incidents/{incident_id}/verify"),
    ("POST", "/incidents/{incident_id}/responses"),
    ("POST", "/reports"), ("GET", "/reports/{report_id}/status"), ("POST", "/reports/bulk"),
    ("POST", "/rides/upload"), ("POST", "/rides/stream"),
    ("GET", "/stats"), ("GET", "/vehicles/live"),
    # Day 0 (§8)
    ("POST", "/auth/google"), ("POST", "/auth/dev"), ("GET", "/users/me"),
    ("GET", "/mobile/ping"), ("GET", "/admin/ping"), ("POST", "/devices/stream"),
}


def routes() -> set[tuple[str, str]]:
    """(METHOD, path) of everything the app serves (OpenAPI: FastAPI includes routers lazily)."""
    return {(method.upper(), path) for path, ops in app.openapi()["paths"].items() for method in ops}


def test_all_routes_registered():
    assert EXPECTED <= routes()


def test_every_router_module_is_included():
    names = {m.__name__ for m in ROUTERS}
    assert {f"backend.api.{n}" for n in ("rides", "reports", "segments", "incidents", "responses", "stats",
                                         "vehicles", "users", "mobile", "admin", "devices")} <= names
    assert "backend.auth.routes" in names


def test_responses_endpoint_moved_out_of_incidents():
    incident_paths = {route.path for route in incidents_api.router.routes}
    assert not any(path.endswith("/responses") for path in incident_paths)
    assert not hasattr(incidents_api, "CitizenResponseIn")
    assert [(r.path, r.methods) for r in responses_api.router.routes] == \
        [("/incidents/{incident_id}/responses", {"POST"})]


def test_stub_routers():
    client = TestClient(app)
    assert client.get("/mobile/ping").json() == {"ok": True}
    r = client.post("/devices/stream", json={})
    assert r.status_code == 501 and r.json() == {"detail": "not implemented yet (owner: C)"}
    assert client.get("/admin/ping").status_code == 401  # require_admin on the whole /admin router
    assert client.get("/users/me").status_code == 401
