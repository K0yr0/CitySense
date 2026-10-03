"""Citizen responses and contributor trust: the chart's feedback loop.

* Every located report is an implicit YES on its incident; the "Is this problem still there?"
  prompt adds explicit YES/NO answers (one per contributor per incident, latest wins).
* The confidence engine weighs each answer by its contributor's trust.
* When an incident resolves (verified = real, dismissed = not real), each contributor's
  unsettled answers are scored right/wrong and their trust is updated, which changes how
  much their *future* answers weigh. Trust is the mean of a Beta(3, 2) prior:
  (correct + 3) / (correct + incorrect + 5), so newcomers start at 0.6.

Contributors are anonymous: a salted SHA-256 of a random token the browser keeps.
"""
from __future__ import annotations

import hashlib

from backend.db import fetch_all, fetch_one

PRIOR_CORRECT = 3
PRIOR_INCORRECT = 2
DEFAULT_TRUST = PRIOR_CORRECT / (PRIOR_CORRECT + PRIOR_INCORRECT)  # 0.6, also for anonymous 19115 reports
HASH_SALT = "cityecho-contributor:"
MAX_TOKEN_LEN = 200

SQL_CONTRIBUTOR = """
insert into contributors (contributor_hash, trust) values (%(hash)s, %(trust)s)
on conflict (contributor_hash) do update set contributor_hash = excluded.contributor_hash
returning id, trust, correct, incorrect
"""

SQL_VOTE = """
insert into citizen_responses (incident_id, contributor_id, answer, settled)
values (%(incident_id)s, %(contributor_id)s, %(answer)s, %(settled)s)
on conflict (incident_id, contributor_id) where contributor_id is not null
do update set answer = excluded.answer, settled = excluded.settled or citizen_responses.settled,
              created_at = now()
"""

SQL_REPORT_CONTRIBUTOR = "select contributor_id from reports where id = %(report_id)s"

SQL_REPORT_YES_ANON = """
insert into citizen_responses (incident_id, report_id, answer)
values (%(incident_id)s, %(report_id)s, true)
on conflict (report_id) where report_id is not null do nothing
"""

# A contributor's new report on an incident they already answered turns their answer into YES.
SQL_REPORT_YES_KNOWN = """
insert into citizen_responses (incident_id, contributor_id, report_id, answer)
values (%(incident_id)s, %(contributor_id)s, %(report_id)s, true)
on conflict (incident_id, contributor_id) where contributor_id is not null
do update set answer = true, report_id = coalesce(citizen_responses.report_id, excluded.report_id)
"""

SQL_VOTES = """
select cr.answer, coalesce(c.trust, %(default_trust)s) as trust
from citizen_responses cr
left join contributors c on c.id = cr.contributor_id
where cr.incident_id = %(incident_id)s
"""

# Score every unsettled answer against the outcome and update those contributors' trust.
SQL_SETTLE = """
with pending as (
    update citizen_responses set settled = true
    where incident_id = %(incident_id)s and not settled
    returning contributor_id, answer
), tally as (
    select contributor_id,
           count(*) filter (where answer = %(real)s)  as ok,
           count(*) filter (where answer <> %(real)s) as bad
    from pending
    where contributor_id is not null
    group by contributor_id
)
update contributors c
set correct   = c.correct + t.ok,
    incorrect = c.incorrect + t.bad,
    trust     = (c.correct + t.ok + %(prior_correct)s)::real
                / (c.correct + t.ok + c.incorrect + t.bad + %(prior_correct)s + %(prior_incorrect)s)
from tally t
where c.id = t.contributor_id
returning c.id
"""


def trust_from_counts(correct: int, incorrect: int) -> float:
    """Beta(3, 2) posterior mean: 0.6 for a newcomer, -> 1 when right, -> 0 when wrong."""
    return (correct + PRIOR_CORRECT) / (correct + incorrect + PRIOR_CORRECT + PRIOR_INCORRECT)


def contributor_hash(token: str) -> str:
    return hashlib.sha256((HASH_SALT + token.strip()).encode()).hexdigest()


def contributor_for(conn, token: str | None) -> dict | None:
    """Contributor row {id, trust, correct, incorrect} for a browser token (created on first use)."""
    token = (token or "").strip()
    if not token:
        return None
    if len(token) > MAX_TOKEN_LEN:
        raise ValueError("contributor token too long")
    return fetch_one(conn, SQL_CONTRIBUTOR, {"hash": contributor_hash(token), "trust": DEFAULT_TRUST})


def record_vote(conn, incident_id: int, contributor_id: int, answer: bool, *, resolved: bool = False) -> None:
    """Explicit YES/NO. Answers on an already-resolved incident never move trust (no free points)."""
    conn.execute(SQL_VOTE, {"incident_id": incident_id, "contributor_id": contributor_id,
                            "answer": bool(answer), "settled": bool(resolved)})


def record_report_yes(conn, incident_id: int, report_id: int) -> None:
    """A located report joined `incident_id`: count it as its author's YES (idempotent)."""
    row = fetch_one(conn, SQL_REPORT_CONTRIBUTOR, {"report_id": report_id}) or {}
    params = {"incident_id": incident_id, "report_id": report_id, "contributor_id": row.get("contributor_id")}
    conn.execute(SQL_REPORT_YES_KNOWN if params["contributor_id"] else SQL_REPORT_YES_ANON, params)


def votes_for(conn, incident_id: int) -> list[tuple[bool, float]]:
    """[(answer, trust)] for the confidence engine; anonymous answers use DEFAULT_TRUST."""
    rows = fetch_all(conn, SQL_VOTES, {"incident_id": incident_id, "default_trust": DEFAULT_TRUST})
    return [(bool(r["answer"]), float(r["trust"])) for r in rows]


def settle(conn, incident_id: int, real: bool) -> list[int]:
    """Incident resolved (real = verified, not real = dismissed): update contributor trust.

    Returns the ids of contributors whose trust changed.
    """
    rows = fetch_all(conn, SQL_SETTLE, {"incident_id": incident_id, "real": bool(real),
                                        "prior_correct": PRIOR_CORRECT, "prior_incorrect": PRIOR_INCORRECT})
    return [int(r["id"]) for r in rows]
