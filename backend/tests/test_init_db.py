"""scripts/init_db.py migrations: numeric order, once-only via schema_migrations, --reset drops their tables."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_init_db():
    spec = importlib.util.spec_from_file_location("init_db_under_test", REPO_ROOT / "scripts" / "init_db.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


init_db = _load_init_db()


class FakeConn:
    """Records statements; keeps an in-memory schema_migrations table."""

    def __init__(self, applied=()) -> None:
        self.statements: list[tuple[str, object]] = []
        self.migrations = list(applied)

    def execute(self, sql, params=None):
        self.statements.append((sql, params))
        rows = []
        if sql.startswith("insert into schema_migrations"):
            self.migrations.append(params[0])
        elif sql.startswith("select filename from schema_migrations"):
            rows = [(name,) for name in self.migrations]
        return type("Cursor", (), {"fetchall": lambda self: rows})()

    def scripts(self) -> list[str]:
        """First line of every multi-statement script that ran (migration files start with a comment)."""
        return [sql.splitlines()[0] for sql, params in self.statements if params is None and sql.startswith("--")]


def write(directory: Path, name: str, body: str | None = None) -> Path:
    path = directory / name
    path.write_text(body or f"-- {name}\ncreate table if not exists t_{path.stem.split('_', 1)[1]} (id int);\n")
    return path


def test_files_sorted_by_numeric_prefix(tmp_path):
    for name in ("300_devices.sql", "20_early.sql", "100_users.sql", "200_work_status.sql", "101_routes.sql"):
        write(tmp_path, name)
    (tmp_path / "README.md").write_text("not a migration")
    names = [p.name for p in init_db.migration_files(tmp_path)]
    assert names == ["20_early.sql", "100_users.sql", "101_routes.sql", "200_work_status.sql", "300_devices.sql"]
    assert init_db.migration_files(tmp_path / "missing") == []


@pytest.mark.parametrize("bad", ["users.sql", "1a_x.sql", "100-users.sql", "100_.sql"])
def test_bad_names_are_rejected(tmp_path, bad):
    write(tmp_path, "100_users.sql")
    (tmp_path / bad).write_text("select 1;")
    with pytest.raises(ValueError, match="must be named"):
        init_db.migration_files(tmp_path)


def test_duplicate_numbers_are_rejected(tmp_path):
    write(tmp_path, "200_a.sql")
    write(tmp_path, "200_b.sql")
    with pytest.raises(ValueError, match="share number 200"):
        init_db.migration_files(tmp_path)


def test_migrations_run_once_in_order_and_are_recorded(tmp_path):
    for name in ("300_c.sql", "100_a.sql", "200_b.sql"):
        write(tmp_path, name)
    files = init_db.migration_files(tmp_path)
    conn = FakeConn()
    assert init_db.apply_migrations(conn, files) == ["100_a.sql", "200_b.sql", "300_c.sql"]
    assert "create table if not exists schema_migrations" in conn.statements[0][0]
    assert conn.scripts() == ["-- 100_a.sql", "-- 200_b.sql", "-- 300_c.sql"]
    assert conn.migrations == ["100_a.sql", "200_b.sql", "300_c.sql"]
    inserts = [p for s, p in conn.statements if s.startswith("insert into schema_migrations")]
    assert inserts == [("100_a.sql",), ("200_b.sql",), ("300_c.sql",)]

    # second run: nothing re-applied
    again = FakeConn(applied=conn.migrations)
    assert init_db.apply_migrations(again, files) == []
    assert again.scripts() == []

    # a teammate's lower-numbered migration arrives later: only it runs
    write(tmp_path, "101_late.sql")
    late = FakeConn(applied=conn.migrations)
    assert init_db.apply_migrations(late, init_db.migration_files(tmp_path)) == ["101_late.sql"]


def test_migrate_runs_schema_functions_then_migrations(tmp_path):
    write(tmp_path, "100_a.sql")
    conn = FakeConn()
    steps = init_db.migrate(conn, migrations_dir=tmp_path)
    assert steps == ["schema.sql", "functions.sql", "migrations: 100_a.sql"]
    assert "create table if not exists segments" in conn.statements[0][0]
    assert "recompute_segment_health" in conn.statements[1][0]
    assert init_db.migrate(FakeConn(applied=["100_a.sql"]), migrations_dir=tmp_path)[-1] == "migrations: up to date"

    (tmp_path / "oops.sql").write_text("select 1;")
    untouched = FakeConn()
    with pytest.raises(ValueError):
        init_db.migrate(untouched, migrations_dir=tmp_path)
    assert untouched.statements == []  # names are validated before anything runs


def test_reset_drops_migration_tables_and_log(tmp_path):
    write(tmp_path, "100_users.sql", "create table if not exists users (id int);\n"
                                     "CREATE TABLE favorite_routes (id int);\n")
    write(tmp_path, "300_devices.sql", "create table if not exists devices (id text);\n"
                                       "alter table segments add column if not exists x int;\n")
    conn = FakeConn()
    init_db.migrate(conn, reset=True, migrations_dir=tmp_path)
    drop = conn.statements[0][0]
    order = [line.split()[4] for line in drop.splitlines() if line.startswith("drop table")]
    assert order[:4] == ["devices", "favorite_routes", "users", "schema_migrations"]
    assert {"incidents", "contributors", "segments"} <= set(order)
    assert conn.migrations == ["100_users.sql", "300_devices.sql"]  # applied again after the reset


def test_repo_day0_migrations_exist_and_define_the_contract():
    files = init_db.migration_files()
    names = [p.name for p in files]
    assert {"100_users.sql", "200_work_status.sql", "300_devices.sql"} <= set(names)
    assert names.index("100_users.sql") < names.index("200_work_status.sql")  # work_status_by -> users
    for name in names:  # A = 1xx, B = 2xx, C = 3xx
        assert 100 <= int(name.split("_", 1)[0]) <= 399, name
    sql = {p.name: " ".join(p.read_text().lower().split()) for p in files}
    users = sql["100_users.sql"]
    for col in ("google_sub text unique", "email text not null unique", "name text",
                "role text not null default 'citizen'", "contributor_id bigint unique references contributors(id)",
                "created_at timestamptz"):
        assert col in users, col
    work = sql["200_work_status.sql"]
    assert "add column if not exists work_status text not null default 'todo'" in work
    assert "check (work_status in ('todo', 'in_progress', 'done'))" in work
    assert "work_status_changed_at timestamptz" in work and "work_status_by bigint references users(id)" in work
    devices = sql["300_devices.sql"]
    assert "create table if not exists devices" in devices and "key_hash text not null" in devices
    assert "check (mode in ('road', 'tram'))" in devices
    assert "alter table segments add column if not exists health_updated_at timestamptz" in devices
    tables = init_db.migration_tables(files)  # later migrations (101, 2xx, ...) may add tables in between
    assert {"users", "devices"} <= set(tables) and tables.index("users") < tables.index("devices")
