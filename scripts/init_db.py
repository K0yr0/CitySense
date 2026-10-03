"""Create (or update) the CityEcho database: db/schema.sql, then db/functions.sql.

Idempotent: tables/indexes use `if not exists`, functions `create or replace`.

    .venv/bin/python scripts/init_db.py                 # apply to $DATABASE_URL
    .venv/bin/python scripts/init_db.py --reset         # drop CityEcho tables first (asks)
    .venv/bin/python scripts/init_db.py --reset --yes   # ... without asking
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

SCHEMA_SQL = REPO_ROOT / "db" / "schema.sql"
FUNCTIONS_SQL = REPO_ROOT / "db" / "functions.sql"

# Dependants first (cascade would handle the order anyway).
TABLES = ["incident_evidence", "incidents", "evidence", "reports", "ride_segments", "rides", "segments"]
DROP_SQL = (
    "drop function if exists nearest_segment(float8, float8, text, float8);\n"
    "drop function if exists recompute_segment_health();\n"
    + "".join(f"drop table if exists {t} cascade;\n" for t in TABLES)
)


def mask_url(url: str) -> str:
    """Hide the password in a postgres URL for printing."""
    return re.sub(r"(://[^:/@]+:)[^@]*@", r"\1***@", url)


def apply_sql(conn, *, reset: bool = False) -> list[str]:
    """Run (optional drop), schema.sql, functions.sql on `conn`. Returns the steps done."""
    steps = []
    if reset:
        conn.execute(DROP_SQL)
        steps.append("drop")
    for path in (SCHEMA_SQL, FUNCTIONS_SQL):
        # No params -> psycopg sends the whole multi-statement script as-is.
        conn.execute(path.read_text(encoding="utf-8"))
        steps.append(path.name)
    return steps


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reset", action="store_true", help="drop all CityEcho tables and functions first")
    parser.add_argument("--yes", "-y", action="store_true", help="do not ask for confirmation with --reset")
    args = parser.parse_args(argv)

    import psycopg

    from backend.config import settings

    url = settings.database_url
    if args.reset and not args.yes:
        answer = input(f"Drop ALL CityEcho tables ({', '.join(TABLES)}) in {mask_url(url)}? [y/N] ")
        if answer.strip().lower() not in {"y", "yes"}:
            print("Aborted.")
            return 1

    try:
        with psycopg.connect(url, prepare_threshold=None) as conn:  # commits on clean exit
            steps = apply_sql(conn, reset=args.reset)
    except psycopg.OperationalError as exc:
        print(f"Cannot connect to {mask_url(url)}: {exc}\nSet DATABASE_URL in .env.", file=sys.stderr)
        return 2
    print(f"Database ready at {mask_url(url)} ({' -> '.join(steps)}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
