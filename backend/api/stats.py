"""Headline numbers for the dashboard stats bar."""
from __future__ import annotations

from fastapi import APIRouter

from backend.api.deps import DB

router = APIRouter(prefix="/stats", tags=["stats"])

STATS_SQL = """
select
  (select count(*) from reports)                                              as reports_total,
  (select count(*) from incidents)                                            as incidents_total,
  (select count(*) from incidents where found_before_report)                  as found_before_report,
  (select count(*) from incidents where status = 'candidate')                 as candidate_total,
  (select count(*) from incidents where status = 'likely')                    as likely_total,
  (select count(*) from incidents where status = 'verified')                  as verified_total,
  (select count(*) from incidents
    where status in ('candidate', 'likely') and sensor_count = 0 and verify_requested_at is not null
      and (last_miss_at is null or last_miss_at < verify_requested_at))       as awaiting_verification,
  (select avg(extract(epoch from verified_at - verify_requested_at)) / 60.0
     from incidents
    where verified_at is not null and verify_requested_at is not null
      and verified_at >= verify_requested_at)                                 as avg_verification_min,
  (select count(*) from contributors)                                         as contributors_total,
  (select count(*) from rides)                                                as rides_total,
  (select count(*) from segments where health is not null)                    as segments_measured
"""

COUNT_KEYS = ("reports_total", "incidents_total", "found_before_report", "candidate_total", "likely_total",
              "verified_total", "awaiting_verification", "contributors_total", "rides_total", "segments_measured")


@router.get("")
def get_stats(conn: DB) -> dict:
    """Counts per status plus avg(verified_at - verify_requested_at) in minutes (null until something is verified)."""
    from backend import db

    row = db.fetch_one(conn, STATS_SQL) or {}
    out: dict = {k: int(row.get(k) or 0) for k in COUNT_KEYS}
    avg = row.get("avg_verification_min")
    out["avg_verification_min"] = None if avg is None else round(float(avg), 1)
    return out
