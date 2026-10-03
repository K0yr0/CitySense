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

# ever_done: trust is settled only the first time an incident is marked done; after a reopen the
# answers given about the repaired spot must never be scored (CLAUDE.md).
SQL_WORK_LOCK = """
select id, work_status, coalesce(work_log, '[]'::jsonb) @> '[{"to_status": "done"}]'::jsonb as ever_done
from incidents where id = %(id)s for update
"""

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


# --- W5 statistics ---------------------------------------------------------------------------
# Repair time = first_seen -> the moment the city marked it done (work_status_changed_at while done).

TREND_DAYS = 14

SQL_STATS = """
select
  (select count(*) from reports)                                            as reports_total,
  (select count(*) from incidents)                                          as incidents_total,
  (select count(*) from incidents where status = 'verified')                as verified_total,
  (select count(*) from incidents where work_status = 'in_progress')        as in_progress_total,
  (select count(*) from incidents where work_status = 'done')               as done_total,
  (select count(*) from incidents where found_before_report)                as found_before_report,
  (select avg(extract(epoch from work_status_changed_at - first_seen)) / 3600.0
     from incidents where work_status = 'done' and work_status_changed_at >= first_seen) as avg_repair_hours,
  (select percentile_cont(0.5) within group (order by extract(epoch from work_status_changed_at - first_seen)) / 3600.0
     from incidents where work_status = 'done' and work_status_changed_at >= first_seen) as median_repair_hours,
  (select avg(extract(epoch from verified_at - verify_requested_at)) / 60.0
     from incidents where verified_at is not null and verify_requested_at is not null
      and verified_at >= verify_requested_at)                               as avg_verification_min
"""

# Open = still to do and not dismissed/closed by the confidence engine.
SQL_STATS_DEPARTMENTS = """
select coalesce(department, 'inne') as department,
       count(*)                                                                as total,
       count(*) filter (where work_status = 'todo' and status not in ('dismissed', 'closed')) as todo,
       count(*) filter (where work_status = 'in_progress')                     as in_progress,
       count(*) filter (where work_status = 'done')                            as done,
       count(*) filter (where status = 'verified')                             as verified,
       avg(extract(epoch from work_status_changed_at - first_seen)) filter (
           where work_status = 'done' and work_status_changed_at >= first_seen) / 3600.0 as avg_repair_hours
from incidents
group by 1
order by total desc, 1
"""

# Per UTC day for the last N days: incidents first seen, incidents marked done.
SQL_STATS_DAILY = """
select d.day,
       (select count(*) from incidents i
         where (i.first_seen at time zone 'UTC')::date = d.day)                               as new,
       (select count(*) from incidents i
         where i.work_status = 'done' and (i.work_status_changed_at at time zone 'UTC')::date = d.day) as done
from (select generate_series((now() at time zone 'UTC')::date - (%(days)s - 1),
                             (now() at time zone 'UTC')::date, interval '1 day')::date as day) d
order by d.day
"""


def _hours(value) -> float | None:
    return None if value is None else round(float(value), 1)


@router.get("/stats")
def stats(conn: DB) -> dict:
    """Report -> incident -> verified -> done funnel, repair times, load per department, 14-day trend."""
    from backend import db

    row = db.fetch_one(conn, SQL_STATS) or {}
    counts = ("reports_total", "incidents_total", "verified_total", "in_progress_total", "done_total", "found_before_report")
    out: dict = {k: int(row.get(k) or 0) for k in counts}
    out["avg_repair_hours"] = _hours(row.get("avg_repair_hours"))
    out["median_repair_hours"] = _hours(row.get("median_repair_hours"))
    avg_ver = row.get("avg_verification_min")
    out["avg_verification_min"] = None if avg_ver is None else round(float(avg_ver), 1)
    out["departments"] = [
        {"department": d["department"], "total": int(d.get("total") or 0), "todo": int(d.get("todo") or 0),
         "in_progress": int(d.get("in_progress") or 0), "done": int(d.get("done") or 0),
         "verified": int(d.get("verified") or 0), "avg_repair_hours": _hours(d.get("avg_repair_hours"))}
        for d in db.fetch_all(conn, SQL_STATS_DEPARTMENTS)
    ]
    out["daily"] = [
        {"day": ser.iso(d["day"]), "new": int(d.get("new") or 0), "done": int(d.get("done") or 0)}
        for d in db.fetch_all(conn, SQL_STATS_DAILY, {"days": TREND_DAYS})
    ]
    return out


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

    The first time an incident reaches `done` contributor trust is settled (`trust.settle(real=True)`);
    a reopen + done again settles nothing, and answers given later are never scored against anyone
    (see fusion.incidents.refresh_incident).
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
        if status == WorkStatus.DONE and previous != WorkStatus.DONE and not row.get("ever_done"):
            settled = trust.settle(conn, incident_id, real=True)
    return {**work_json(conn, incident_id), "settled_contributors": len(settled)}
