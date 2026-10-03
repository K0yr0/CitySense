"""`users` table access (db/migrations/100_users.sql) and the login upsert.

Trust carry-over: the mobile app keeps an anonymous contributor token before login
(the same token `/incidents/{id}/responses` and `/reports` take). At login that token's
contributor row (backend.fusion.trust.contributor_for) is linked to the user, once,
so trust earned anonymously stays with the account.
"""
from __future__ import annotations

from typing import Any

from backend import config
from backend.models import Role

USER_COLS = "id, google_sub, email, name, role, contributor_id, created_at"

SQL_BY_SUB = f"select {USER_COLS} from users where google_sub = %(sub)s"

SQL_BY_ID = f"select {USER_COLS} from users where id = %(id)s"

SQL_UPDATE_BY_ID = f"""
update users set email = %(email)s, name = coalesce(%(name)s, name), role = %(role)s
where id = %(id)s
returning {USER_COLS}
"""

# New user, or an existing one found by email (e.g. a dev-login user who now signs in with Google).
SQL_UPSERT_BY_EMAIL = f"""
insert into users (google_sub, email, name, role)
values (%(sub)s, %(email)s, %(name)s, %(role)s)
on conflict (email) do update
set google_sub = coalesce(users.google_sub, excluded.google_sub),
    name = coalesce(excluded.name, users.name),
    role = excluded.role
returning {USER_COLS}
"""

# Link only when the user has none yet and no other account already owns that contributor.
SQL_LINK_CONTRIBUTOR = """
update users set contributor_id = %(contributor_id)s
where id = %(user_id)s and contributor_id is null
  and not exists (select 1 from users other where other.contributor_id = %(contributor_id)s)
returning contributor_id
"""


def role_for(email: str) -> str:
    """admin if the email is listed in ADMIN_EMAILS (case-insensitive), else citizen."""
    return Role.ADMIN.value if email.strip().lower() in config.settings.admin_emails else Role.CITIZEN.value


def public_user(row: dict[str, Any]) -> dict[str, Any]:
    """The user shape every endpoint returns: {id, email, name, role}."""
    return {"id": int(row["id"]), "email": row.get("email"), "name": row.get("name"), "role": row.get("role")}


def get_user(conn, user_id: int) -> dict[str, Any] | None:
    from backend import db

    return db.fetch_one(conn, SQL_BY_ID, {"id": user_id})


def upsert_user(conn, *, email: str, name: str | None, google_sub: str | None) -> dict[str, Any]:
    """Create or update the user (matched by Google subject first, then email). Role is re-derived."""
    from backend import db

    email = email.strip().lower()
    params = {"sub": google_sub, "email": email, "name": name, "role": role_for(email)}
    existing = db.fetch_one(conn, SQL_BY_SUB, params) if google_sub else None
    if existing:
        return db.fetch_one(conn, SQL_UPDATE_BY_ID, {**params, "id": existing["id"]}) or existing
    return db.fetch_one(conn, SQL_UPSERT_BY_EMAIL, params)


def link_contributor(conn, user: dict[str, Any], contributor_token: str | None) -> dict[str, Any]:
    """Carry anonymous trust over: link the token's contributor if the user has none yet."""
    if not contributor_token or user.get("contributor_id") is not None:
        return user
    from backend import db
    from backend.fusion import trust

    contributor = trust.contributor_for(conn, contributor_token)
    if not contributor:
        return user
    row = db.fetch_one(conn, SQL_LINK_CONTRIBUTOR, {"user_id": user["id"], "contributor_id": contributor["id"]})
    return {**user, "contributor_id": row["contributor_id"]} if row else user


def login(conn, *, email: str, name: str | None, google_sub: str | None = None,
          contributor: str | None = None) -> dict[str, Any]:
    """Upsert the user and link their anonymous contributor. Returns the full users row."""
    user = upsert_user(conn, email=email, name=name, google_sub=google_sub)
    return link_contributor(conn, user, contributor)
