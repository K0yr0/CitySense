"""Create (or update) the CityEcho database: db/schema.sql, db/functions.sql, then db/migrations/*.sql.

Idempotent: tables/indexes use `if not exists`, functions `create or replace`, and each
migration runs once (its filename is recorded in `schema_migrations`). Migrations run in
numeric order of their prefix: A = 100–199, B = 200–299, C = 300–399 (db/migrations/README.md).
Run it after every `git pull`.

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
MIGRATIONS_DIR = REPO_ROOT / "db" / "migrations"

MIGRATION_NAME = re.compile(r"^(\d+)_[A-Za-z0-9_.-]+\.sql$")
CREATE_TABLE = re.compile(r"create\s+table\s+(?:if\s+not\s+exists\s+)?([A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE)

# Dependants first (cascade would handle the order anyway).
TABLES = ["citizen_responses", "incident_evidence", "incidents", "evidence", "reports", "contributors",
          "ride_segments", "rides", "segments"]
FUNCTIONS_DROP_SQL = (
    "drop function if exists nearest_segment(float8, float8, text, float8);\n"
    "drop function if exists recompute_segment_health();\n"
)
MIGRATIONS_TABLE_SQL = """
create table if not exists schema_migrations (
  filename    text primary key,
  applied_at  timestamptz not null default now()
)
"""


def mask_url(url: str) -> str:
    """Hide the password in a postgres URL for printing."""
    return re.sub(r"(://[^:/@]+:)[^@]*@", r"\1***@", url)


def migration_files(directory: Path = MIGRATIONS_DIR) -> list[Path]:
    """`NNN_name.sql` files sorted by numeric prefix. Bad names and duplicate numbers raise ValueError."""
    if not directory.is_dir():
        return []
    numbered: list[tuple[int, Path]] = []
    for path in directory.glob("*.sql"):
        match = MIGRATION_NAME.match(path.name)
        if not match:
            raise ValueError(f"migration {path.name!r} must be named <number>_<name>.sql")
        numbered.append((int(match.group(1)), path))
    numbered.sort(key=lambda item: (item[0], item[1].name))
    seen: dict[int, str] = {}
    for number, path in numbered:
        if number in seen:
            raise ValueError(f"migrations {seen[number]!r} and {path.name!r} share number {number}")
        seen[number] = path.name
    return [path for _, path in numbered]


def migration_tables(files: list[Path]) -> list[str]:
    """Tables created by the migrations (`create table [if not exists] name`), in creation order."""
    names: list[str] = []
    for path in files:
        for name in CREATE_TABLE.findall(path.read_text(encoding="utf-8")):
            if name.lower() not in names:
                names.append(name.lower())
    return names


def drop_sql(files: list[Path]) -> str:
    """Drop migration tables (newest first), the migrations log, functions and the core tables."""
    tables = [*reversed(migration_tables(files)), "schema_migrations", *TABLES]
    return FUNCTIONS_DROP_SQL + "".join(f"drop table if exists {t} cascade;\n" for t in tables)


def _first(row):
    return row["filename"] if isinstance(row, dict) else row[0]


def apply_migrations(conn, files: list[Path]) -> list[str]:
    """Run every migration not yet in `schema_migrations`, in order, and record it. Returns the names run."""
    conn.execute(MIGRATIONS_TABLE_SQL)
    applied = {_first(r) for r in conn.execute("select filename from schema_migrations").fetchall()}
    done = []
    for path in files:
        if path.name in applied:
            continue
        conn.execute(path.read_text(encoding="utf-8"))  # no params -> sent as one multi-statement script
        conn.execute("insert into schema_migrations (filename) values (%s)", (path.name,))
        done.append(path.name)
    return done


def apply_sql(conn, *, reset: bool = False, migrations_dir: Path = MIGRATIONS_DIR) -> list[str]:
    """Run (optional drop), schema.sql, functions.sql on `conn`. Returns the steps done. No migrations."""
    steps = []
    if reset:
        conn.execute(drop_sql(migration_files(migrations_dir)))
        steps.append("drop")
    for path in (SCHEMA_SQL, FUNCTIONS_SQL):
        # No params -> psycopg sends the whole multi-statement script as-is.
        conn.execute(path.read_text(encoding="utf-8"))
        steps.append(path.name)
    return steps


def migrate(conn, *, reset: bool = False, migrations_dir: Path = MIGRATIONS_DIR) -> list[str]:
    """Everything init_db does: apply_sql, then the pending migrations. Returns the steps done."""
    files = migration_files(migrations_dir)  # validate names before touching the database
    steps = apply_sql(conn, reset=reset, migrations_dir=migrations_dir)
    ran = apply_migrations(conn, files)
    steps.append(f"migrations: {', '.join(ran)}" if ran else "migrations: up to date")
    return steps


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reset", action="store_true", help="drop all CityEcho tables and functions first")
    parser.add_argument("--yes", "-y", action="store_true", help="do not ask for confirmation with --reset")
    args = parser.parse_args(argv)

    import psycopg

    from backend.config import settings

    url = settings.database_url
    try:
        files = migration_files()
    except ValueError as exc:
        print(f"Bad migration: {exc}", file=sys.stderr)
        return 3
    if args.reset and not args.yes:
        tables = [*migration_tables(files), *TABLES]
        answer = input(f"Drop ALL CityEcho tables ({', '.join(tables)}) in {mask_url(url)}? [y/N] ")
        if answer.strip().lower() not in {"y", "yes"}:
            print("Aborted.")
            return 1

    try:
        with psycopg.connect(url, prepare_threshold=None) as conn:  # one transaction, commits on clean exit
            steps = migrate(conn, reset=args.reset)
    except psycopg.OperationalError as exc:
        print(f"Cannot connect to {mask_url(url)}: {exc}\nSet DATABASE_URL in .env.", file=sys.stderr)
        return 2
    print(f"Database ready at {mask_url(url)} ({' -> '.join(steps)}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
