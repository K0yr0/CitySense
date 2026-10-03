# Docker setup

`docker compose up --build` (from the repo root) starts:

| Service | Port (host) | What |
|---|---|---|
| `db` | 5433 | PostGIS 17 + PostGIS 3.6 (`imresamu/postgis`, amd64 + arm64). Data in the `pgdata` volume. |
| `api` | 8000 | FastAPI. On start: wait for db, `scripts/init_db.py`, load the map from `data/osm/segments_demo.geojson` (skipped with a message if the file is missing), then `uvicorn --reload`. |
| `web` | 3000 | Next.js web admin (`web-admin/`), production build. |
| `seed` | | Profile `seed`, one-shot: `scripts/seed_demo.py --api http://api:8000`. |
| `simulator` | | Profile `sim`, placeholder: `scripts/simulate_buses.py` (person C, not written yet). |

## Files

- `../docker-compose.yml`: the services above.
- `api.Dockerfile`: Python 3.11 slim + `backend/requirements.txt` only (no osmnx/geopandas/torch). Build context is the repo root, filtered by `../.dockerignore`.
- `api-entrypoint.sh`: start-up steps of the `api` container. Must stay LF; the Dockerfile strips CR anyway.
- `web.Dockerfile`: `npm ci` (its postinstall copies the MapLibre worker), `npm run build`, `next start`. Build context is `web-admin/`, filtered by `web-admin/.dockerignore`.

## Common commands

```bash
docker compose up --build                       # start (or rebuild after dependency changes)
docker compose --profile seed run --rm seed     # demo data
docker compose logs -f api                      # follow API logs
docker compose exec api pytest                  # run the backend tests inside the container
docker compose exec db psql -U cityecho         # SQL shell
docker compose up --build web                   # rebuild the web admin after web-admin/ changes
docker compose down                             # stop (keeps the database)
docker compose down -v                          # stop and delete the database + caches
```

## Notes

- **Environment:** the repo-root `.env` is optional and is passed to the Python containers at runtime (never baked into images). `DATABASE_URL` is always overridden to the `db` container.
- **Web API URL:** `NEXT_PUBLIC_API_URL` is compiled into the browser bundle, so it is a build arg (default `http://localhost:8000`, set it in `.env` to change it, then rebuild `web`). The server-side `/api/*` rewrite uses `BACKEND_URL=http://api:8000`.
- **Live reload:** `backend/`, `db/`, `scripts/` and `data/` are bind-mounted into the API container; uvicorn watches `backend/`. On Windows, if edits are not picked up, add `WATCHFILES_FORCE_POLLING=true` to `.env`.
- **Caches** (`data/cache`: osmnx downloads, uploaded photos) live in the `api-cache` volume, not on your disk.
- **Port clash:** if 3000, 8000 or 5433 is taken, change the left side of the `ports:` mapping locally (do not commit it).
- **Mobile** (Expo) runs outside Docker: `cd mobile && npx expo start`, API at `http://<your-LAN-IP>:8000`.
