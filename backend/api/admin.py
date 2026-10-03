"""Municipal web admin endpoints (owner B). Every route here requires an admin (router-level dependency).

W3 work flow: the city's work status (`incidents.work_status`: todo -> in_progress -> done, migration 200)
is separate from the confidence `status`. Every change is appended to `incidents.work_log` (migration 201).
Marking an incident done settles the trust of everyone who answered on it (`trust.settle(real=True)`),
and the mobile app stops asking "is it still there?" (it reads `work_status`).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.api import serializers as ser
from backend.api.deps import DB
from backend.auth import AdminUser, require_admin
from backend.models import WorkStatus

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])

HISTORY_LIMIT = 50

SQL_WORK_CURRENT = """
select i.id, i.work_status, i.work_status_changed_at, i.work_log,
       u.id as by_id, u.email as by_email, u.name as by_name
from incidents i
left join users u on u.id = i.work_status_by
where i.id = %(id)s
"""

SQL_WORK_LOCK = "select id, work_status from incidents where id = %(id)s for update"

# One statement: new status + who/when + a history entry (`work_status` on the right is the old value).
# A note-only change keeps "since when / by whom". The token's user id may be stale (e.g. after a
# DB reset): store null rather than break the users FK.
SQL_WORK_UPDATE = """
update incidents
set work_status = %(status)s,
    work_status_changed_at = case when work_status = %(status)s then work_status_changed_at else now() end,
    work_status_by = case when work_status = %(status)s then work_status_by
                          else (select id from users where id = %(user_id)s) end,
    work_log = coalesce(work_log, '[]'::jsonb) || jsonb_build_array(jsonb_build_object(
        'from_status', work_status, 'to_status', %(status)s::text, 'by_email', %(email)s::text,
        'by_name', %(name)s::text, 'note', %(note)s::text, 'at', now()))
where id = %(id)s
returning id
"""


class WorkStatusIn(BaseModel):
    status: WorkStatus
    note: str | None = Field(None, max_length=500, description="optional, e.g. crew or work order number")


@router.get("/ping")
def ping(user: AdminUser) -> dict:
    return {"ok": True, "user": user}


def work_json(conn, incident_id: int) -> dict:
    """{incident_id, work_status, changed_at, changed_by, history} or 404."""
    from backend import db

    row = db.fetch_one(conn, SQL_WORK_CURRENT, {"id": incident_id})
    if row is None:
        raise HTTPException(404, f"incident {incident_id} not found")
    log = ser._json(row.get("work_log")) or []
    history = list(reversed(log))[:HISTORY_LIMIT] if isinstance(log, list) else []
    by = None
    if row.get("by_id") is not None:
        by = {"id": int(row["by_id"]), "email": row.get("by_email"), "name": row.get("by_name")}
    return {
        "incident_id": incident_id,
        "work_status": row.get("work_status") or WorkStatus.TODO.value,
        "changed_at": ser.iso(row.get("work_status_changed_at")),
        "changed_by": by,
        "history": [
            {
                "from_status": h.get("from_status"),
                "to_status": h.get("to_status"),
                "by_email": h.get("by_email"),
                "by_name": h.get("by_name"),
                "note": h.get("note"),
                "at": ser.iso(h.get("at")),
            }
            for h in history
        ],
    }


@router.get("/incidents/{incident_id}/work")
def get_work(incident_id: int, conn: DB) -> dict:
    """Current city work status of an incident and who changed it, newest change first."""
    return work_json(conn, incident_id)


@router.post("/incidents/{incident_id}/work")
def set_work(incident_id: int, body: WorkStatusIn, conn: DB, user: AdminUser) -> dict:
    """Move an incident to todo / in_progress / done (any direction, so a mistake can be undone).

    Reaching `done` settles contributor trust once (`trust.settle(real=True)`); answers given later
    are never scored against anyone (see fusion.incidents.refresh_incident).
    """
    from backend import db
    from backend.fusion import trust

    row = db.fetch_one(conn, SQL_WORK_LOCK, {"id": incident_id})
    if row is None:
        raise HTTPException(404, f"incident {incident_id} not found")
    previous = row.get("work_status") or WorkStatus.TODO.value
    status = body.status.value
    note = (body.note or "").strip() or None
    settled: list[int] = []
    if status != previous or note:
        db.fetch_one(conn, SQL_WORK_UPDATE, {"id": incident_id, "status": status, "user_id": user.get("id"),
                                             "email": user.get("email"), "name": user.get("name"), "note": note})
        if status == WorkStatus.DONE and previous != WorkStatus.DONE:
            settled = trust.settle(conn, incident_id, real=True)
    return {**work_json(conn, incident_id), "settled_contributors": len(settled)}
