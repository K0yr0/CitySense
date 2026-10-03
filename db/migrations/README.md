# Database migrations

`scripts/init_db.py` applies `db/schema.sql`, then `db/functions.sql`, then every
`db/migrations/<number>_<name>.sql` in numeric order. Each migration runs **once**:
its filename is recorded in the `schema_migrations` table. Run it after every `git pull`:

    .venv/bin/python scripts/init_db.py

| Range | Owner |
|---|---|
| `100–199` | A (mobile, users) |
| `200–299` | B (web admin, `work_status`) |
| `300–399` | C (sensors, devices, segment health) |

Rules:
* Take the next free number in **your** range, e.g. `101_favorite_routes.sql`. Numbers are unique.
* Never edit a migration that has been pushed; fix it with a new one.
* Write them defensively (`if not exists`, `add column if not exists`): a teammate may
  apply yours after a later one of their own, so only depend on lower numbers that are already pushed.
* New tables created with `create table if not exists <name>` are dropped by `init_db.py --reset`.
* `db/schema.sql` is frozen; schema changes go here.
