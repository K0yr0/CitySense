#!/bin/sh
# CityEcho API container start-up. Keep this file LF-only (the Dockerfile also strips CR).
#   1. wait until Postgres accepts connections ($DATABASE_URL)
#   2. python scripts/init_db.py                      (idempotent: schema + functions)
#   3. python scripts/load_osm.py --from-geojson ...  (map segments; skipped if the file is missing)
#   4. exec the CMD (uvicorn by default)
set -e
cd /app

log() { echo "[cityecho-entrypoint] $*"; }

log "waiting for the database ..."
python - <<'PY'
import os, sys, time
import psycopg

url = os.environ.get("DATABASE_URL", "")
deadline = time.monotonic() + 90
while True:
    try:
        with psycopg.connect(url, connect_timeout=3) as conn:
            conn.execute("select 1")
        break
    except Exception as exc:  # noqa: BLE001
        if time.monotonic() > deadline:
            print(f"[cityecho-entrypoint] database not reachable after 90 s: {exc}", file=sys.stderr)
            sys.exit(1)
        time.sleep(2)
print("[cityecho-entrypoint] database is up")
PY

log "applying schema (scripts/init_db.py)"
python scripts/init_db.py

MAP_FILE="data/osm/segments_demo.geojson"
if [ -f "$MAP_FILE" ]; then
    log "loading map segments from $MAP_FILE"
    if ! python scripts/load_osm.py --from-geojson "$MAP_FILE" --skip-if-loaded; then
        log "WARNING: map load failed (see above). The API still starts, but road health and"
        log "         map matching need segments. Retry: docker compose exec api python scripts/load_osm.py --from-geojson $MAP_FILE --skip-if-loaded"
    fi
else
    log "NOTE: $MAP_FILE not found, skipping the map load. The API still starts, but the map"
    log "      has no road/tram segments until that file exists (person C, task S0). Then run"
    log "      docker compose restart api"
fi

log "starting: $*"
exec "$@"
