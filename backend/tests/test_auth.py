"""Auth tests: Google login (fake verifier, no network), session JWTs, roles, dev login, trust carry-over."""
from __future__ import annotations

import importlib
import sys
import types
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import jwt
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient

from backend import config
from backend.api import deps
from backend.auth import google, tokens
from backend.auth import deps as auth_deps
from backend.fusion import trust as trust_mod
from backend.main import app

SECRET = "test-secret-" + "x" * 40
USER_KEYS = {"id", "email", "name", "role"}


# --------------------------------------------------------------------------- fakes

class FakeUsersDB:
    """In-memory `users` + `contributors` answering the SQL of backend.auth.store and trust.contributor_for."""

    def __init__(self) -> None:
        self.users: dict[int, dict] = {}
        self.contributors: dict[str, dict] = {}  # contributor_hash -> row
        self.calls: list[tuple[str, dict]] = []

    def _by(self, key, value):
        return next((dict(u) for u in self.users.values() if u[key] == value and value is not None), None)

    def fetch_one(self, conn, sql, params=None):
        self.calls.append((sql, params))
        p = params or {}
        if "insert into contributors" in sql:
            row = self.contributors.setdefault(p["hash"], {"id": len(self.contributors) + 1, "trust": 0.85,
                                                           "correct": 4, "incorrect": 0})
            return dict(row)
        if "update users set contributor_id" in sql:
            user = self.users[p["user_id"]]
            taken = any(u["contributor_id"] == p["contributor_id"] for u in self.users.values())
            if user["contributor_id"] is not None or taken:
                return None
            user["contributor_id"] = p["contributor_id"]
            return {"contributor_id": p["contributor_id"]}
        if "update users set email" in sql:
            user = self.users[p["id"]]
            user.update(email=p["email"], role=p["role"], name=p["name"] or user["name"])
            return dict(user)
        if "insert into users" in sql:
            user = self.users.get((self._by("email", p["email"]) or {}).get("id"))
            if user is None:
                uid = len(self.users) + 1
                user = self.users[uid] = {"id": uid, "google_sub": p["sub"], "email": p["email"], "name": p["name"],
                                          "role": p["role"], "contributor_id": None, "created_at": None}
            else:
                user.update(google_sub=user["google_sub"] or p["sub"], name=p["name"] or user["name"], role=p["role"])
            return dict(user)
        if "where google_sub" in sql:
            return self._by("google_sub", p["sub"])
        if "from users where id" in sql:
            return self._by("id", p["id"])
        raise AssertionError(f"unexpected SQL: {sql}")


def install(monkeypatch, name: str, **attrs) -> types.ModuleType:
    mod = types.ModuleType(name)
    mod.__dict__.update(attrs)
    monkeypatch.setitem(sys.modules, name, mod)
    parent, _, child = name.rpartition(".")
    monkeypatch.setattr(importlib.import_module(parent), child, mod, raising=False)
    return mod


GOOGLE_ACCOUNTS = {
    "good-token-ala": {"sub": "g-ala", "email": "Ala@Example.com", "email_verified": True, "name": "Ala"},
    "good-token-boss": {"sub": "g-boss", "email": "boss@city.pl", "email_verified": True, "name": "Boss"},
    "good-token-unverified": {"sub": "g-x", "email": "x@example.com", "email_verified": False},
}


@pytest.fixture
def env(monkeypatch):
    def configure(**kw):
        base = dict(auth_secret=SECRET, auth_token_days=30, admin_emails=["boss@city.pl"],
                    google_client_ids=["web-id", "ios-id", "android-id"], auth_dev_login=False)
        monkeypatch.setattr(config, "settings", replace(config.settings, **{**base, **kw}))

    configure()
    fdb = FakeUsersDB()
    install(monkeypatch, "backend.db", fetch_one=fdb.fetch_one, fetch_all=lambda *a, **k: [])
    monkeypatch.setattr(trust_mod, "fetch_one", fdb.fetch_one)  # real trust.contributor_for, fake DB
    audiences = []

    def fake_google_verify(token, audience):  # stands in for google.oauth2.id_token.verify_oauth2_token
        audiences.append(audience)
        if token not in GOOGLE_ACCOUNTS:
            raise ValueError("Wrong number of segments in token")
        return dict(GOOGLE_ACCOUNTS[token])

    monkeypatch.setattr(google, "_google_verify", fake_google_verify)
    app.dependency_overrides[deps.get_db] = lambda: SimpleNamespace()
    yield SimpleNamespace(db=fdb, client=TestClient(app), configure=configure, audiences=audiences)
    app.dependency_overrides.clear()


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def login(env, id_token="good-token-ala", **body):
    return env.client.post("/auth/google", json={"id_token": id_token, **body})


# --------------------------------------------------------------------------- Google login

def test_google_login_creates_citizen_and_returns_session(env):
    r = login(env)
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"token", "user"} and set(body["user"]) == USER_KEYS
    assert body["user"] == {"id": 1, "email": "ala@example.com", "name": "Ala", "role": "citizen"}
    assert env.audiences == [["web-id", "ios-id", "android-id"]]  # any of the configured client ids
    claims = tokens.decode_token(body["token"])
    assert claims["sub"] == "1" and claims["role"] == "citizen" and claims["iss"] == "cityecho"
    assert claims["exp"] - claims["iat"] == 30 * 86400

    again = login(env).json()  # same Google subject -> same user
    assert again["user"]["id"] == 1 and len(env.db.users) == 1


def test_google_login_admin_role_from_admin_emails(env):
    body = login(env, "good-token-boss").json()
    assert body["user"]["role"] == "admin"
    assert env.client.get("/admin/ping", headers=bearer(body["token"])).json() == {"ok": True, "user": body["user"]}


def test_google_login_rejections(env):
    assert login(env, "forged-token-123").status_code == 401
    assert login(env, "good-token-unverified").status_code == 401
    assert env.client.post("/auth/google", json={}).status_code == 422
    env.configure(google_client_ids=[])
    assert login(env).status_code == 503
    assert env.db.users == {}


def test_verify_google_id_token_uses_google_auth(monkeypatch):
    """The real _google_verify calls google.oauth2.id_token.verify_oauth2_token (patched: no network)."""
    seen = {}

    def verify_oauth2_token(token, request, audience=None, clock_skew_in_seconds=0):
        seen.update(token=token, audience=audience)
        return {"sub": "123", "email": "A@B.PL", "name": "A"}

    monkeypatch.setattr(config, "settings", replace(config.settings,
                                                    google_client_ids=["web-id", "ios-id", "android-id"]))
    from google.oauth2 import id_token

    monkeypatch.setattr(id_token, "verify_oauth2_token", verify_oauth2_token)
    assert google.verify_google_id_token("abc") == {"sub": "123", "email": "a@b.pl", "name": "A"}
    assert seen == {"token": "abc", "audience": ["web-id", "ios-id", "android-id"]}


# --------------------------------------------------------------------------- trust carry-over

def test_contributor_token_is_linked_once(env):
    body = login(env, contributor="device-token-1").json()
    user = env.db.users[body["user"]["id"]]
    assert user["contributor_id"] == 1
    assert list(env.db.contributors) == [trust_mod.contributor_hash("device-token-1")]  # hashed, never raw

    login(env, contributor="device-token-2")  # already linked: keeps the first contributor
    assert user["contributor_id"] == 1

    boss = login(env, "good-token-boss", contributor="device-token-1").json()  # owned by Ala: not shared
    assert env.db.users[boss["user"]["id"]]["contributor_id"] is None


def test_login_without_contributor_links_nothing(env):
    body = login(env).json()
    assert env.db.users[body["user"]["id"]]["contributor_id"] is None
    assert env.db.contributors == {}
    assert login(env, contributor="short").status_code == 422  # same 8–200 char rule as /responses


# --------------------------------------------------------------------------- session tokens

def test_users_me_and_bad_tokens(env):
    token = login(env).json()["token"]
    me = env.client.get("/users/me", headers=bearer(token))
    assert me.status_code == 200 and me.json() == {"id": 1, "email": "ala@example.com", "name": "Ala",
                                                   "role": "citizen"}

    assert env.client.get("/users/me").status_code == 401
    assert env.client.get("/users/me").headers["www-authenticate"] == "Bearer"
    assert env.client.get("/users/me", headers={"Authorization": f"Basic {token}"}).status_code == 401
    head, payload, sig = token.split(".")
    tampered = f"{head}.{payload[:-2]}{'A' if payload[-2] != 'A' else 'B'}{payload[-1]}.{sig}"
    assert env.client.get("/users/me", headers=bearer(tampered)).status_code == 401
    other = jwt.encode(jwt.decode(token, options={"verify_signature": False}), "another-secret-" + "y" * 40,
                       algorithm="HS256")
    assert env.client.get("/users/me", headers=bearer(other)).status_code == 401
    unsigned = jwt.encode({"sub": "1", "role": "admin", "iss": "cityecho", "iat": 0, "exp": 2**40}, None,
                          algorithm="none")
    assert env.client.get("/users/me", headers=bearer(unsigned)).status_code == 401

    env.db.users.clear()  # account deleted -> token no longer opens /users/me
    assert env.client.get("/users/me", headers=bearer(token)).status_code == 401


def test_token_expiry(env):
    user = {"id": 5, "email": "a@b.pl", "name": "A", "role": "citizen"}
    old = tokens.issue_token(user, now=datetime.now(timezone.utc) - timedelta(days=31))
    with pytest.raises(tokens.InvalidToken):
        tokens.decode_token(old)
    fresh = tokens.issue_token(user, now=datetime.now(timezone.utc) - timedelta(days=29))
    assert tokens.user_from_claims(tokens.decode_token(fresh)) == user
    env.configure(auth_token_days=1)
    with pytest.raises(tokens.InvalidToken):
        tokens.decode_token(tokens.issue_token(user, now=datetime.now(timezone.utc) - timedelta(days=2)))


def test_empty_auth_secret_uses_ephemeral_key(env):
    env.configure(auth_secret="")
    token = tokens.issue_token({"id": 1, "email": "a@b.pl", "name": None, "role": "citizen"})
    assert tokens.decode_token(token)["sub"] == "1"
    env.configure(auth_secret=SECRET)
    with pytest.raises(tokens.InvalidToken):
        tokens.decode_token(token)


def test_optional_user(env):
    token = tokens.issue_token({"id": 3, "email": "a@b.pl", "name": "A", "role": "citizen"})
    creds = lambda t: HTTPAuthorizationCredentials(scheme="Bearer", credentials=t)  # noqa: E731
    assert auth_deps.optional_user(None) is None
    assert auth_deps.optional_user(creds("not.a.jwt")) is None  # stale token: public routes keep working
    assert auth_deps.optional_user(creds(token))["id"] == 3
    with pytest.raises(HTTPException) as exc:
        auth_deps.current_user(creds("not.a.jwt"))
    assert exc.value.status_code == 401


# --------------------------------------------------------------------------- require_admin

def test_require_admin(env):
    citizen = login(env).json()["token"]
    admin = login(env, "good-token-boss").json()["token"]
    assert env.client.get("/admin/ping").status_code == 401
    assert env.client.get("/admin/ping", headers=bearer(citizen)).status_code == 403
    assert env.client.get("/admin/ping", headers=bearer(admin)).status_code == 200

    env.configure(admin_emails=[])  # removed from ADMIN_EMAILS -> admin token stops working at once
    assert env.client.get("/admin/ping", headers=bearer(admin)).status_code == 403

    forged = tokens.issue_token({"id": 1, "email": "ala@example.com", "name": "Ala", "role": "admin"})
    assert env.client.get("/admin/ping", headers=bearer(forged)).status_code == 403


# --------------------------------------------------------------------------- dev login

def test_dev_login_is_gated_by_flag(env):
    assert env.client.post("/auth/dev", json={"email": "boss@city.pl"}).status_code == 404
    assert env.db.users == {}

    env.configure(auth_dev_login=True)
    r = env.client.post("/auth/dev", json={"email": "Boss@City.pl", "contributor": "device-token-1"})
    assert r.status_code == 200
    body = r.json()
    assert body["user"] == {"id": 1, "email": "boss@city.pl", "name": "boss", "role": "admin"}
    assert env.db.users[1]["google_sub"] is None and env.db.users[1]["contributor_id"] == 1
    assert env.client.get("/admin/ping", headers=bearer(body["token"])).status_code == 200
    assert env.client.post("/auth/dev", json={"email": "not-an-email"}).status_code == 422

    login(env, "good-token-boss")  # the same person later signs in with Google: same account, sub filled in
    assert len(env.db.users) == 1 and env.db.users[1]["google_sub"] == "g-boss"


# --------------------------------------------------------------------------- settings parsing

def test_auth_settings_parsing(monkeypatch):
    monkeypatch.setenv("DEVICE_KEYS", " bus-17-01:s3cret , tram-4-01:abc:def, broken, :nokey, empty: ")
    assert config._device_keys("DEVICE_KEYS") == {"bus-17-01": "s3cret", "tram-4-01": "abc:def"}
    monkeypatch.setenv("AUTH_TOKEN_DAYS", " ")
    assert config._int("AUTH_TOKEN_DAYS", 30) == 30
    monkeypatch.setenv("AUTH_TOKEN_DAYS", "7")
    assert config._int("AUTH_TOKEN_DAYS", 30) == 7
    defaults = config.Settings()
    assert isinstance(defaults.google_client_ids, list) and isinstance(defaults.device_keys, dict)
