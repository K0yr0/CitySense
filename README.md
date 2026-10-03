# CityEcho

**Warsaw's buses verify its citizens, and its citizens verify its buses.**

CityEcho brings together two channels that never talk to each other: what vehicles *sense* (cheap accelerometer/GPS/light sensors on trams and buses) and what people *report* (19115-style complaints). Both become one kind of **evidence** row anchored to a 25 m road/tram segment. A **fusion engine** clusters evidence into incidents, scores them, routes them to the right department, and flags problems the sensors found **before any citizen reported them**. A **confidence engine** combines sensor confidence with citizen YES/NO answers weighted by **contributor trust**, moving each incident from *candidate* to *likely* to *verified*; trust is updated when an incident resolves, so reliable citizens count for more next time. For complaints that no sensor has seen yet, it asks the **next tram passing that spot** to verify (the verification loop).

- Architecture and module contracts: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- What has been built and verified so far: [BUILD_REPORT.md](BUILD_REPORT.md)

## Repository map

```
backend/            FastAPI app + Python modules
  config.py         settings from .env          models.py   shared enums/types
  db.py             PostGIS access helpers
  sensor/           ingest → detect bumps → track health → dark gaps → map-match → evidence
  triage/           LLM structuring → photo anonymize/check → geocode → embed → dedup → evidence
  fusion/           evidence → incidents, priority score, department routing, verification loop
  api/              HTTP routers (rides, reports, segments, incidents, stats, vehicles)
  tests/            pytest suite (no database needed)
db/                 schema.sql + functions.sql (PostgreSQL + PostGIS)
scripts/            init_db, load_osm, synth_ride, gen_complaints, eval_triage, seed_demo, replay_ride
web-admin/          Next.js admin dashboard: city health map, incident queue/detail, citizen form, ride recorder
docker/             Dockerfiles + API entrypoint for docker-compose.yml (see docker/README.md)
data/               demo rides, synthetic complaints, ZTM sample snapshot, caches
```

## Run with Docker (recommended)

Runs the database (PostGIS), the API and the web admin with one command. Works on macOS (Apple Silicon and Intel), Windows and Linux.

1. Install [Docker Desktop](https://www.docker.com/products/docker-desktop/) and start it.
2. Optional: `cp .env.example .env` and fill in the API keys you have (`ANTHROPIC_API_KEY`, `WARSAW_API_KEY`, `NOMINATIM_USER_AGENT`). Without a `.env` everything still runs with offline fallbacks. `DATABASE_URL` from `.env` is ignored: the API always uses the `db` container.
3. Start everything:
   ```bash
   docker compose up --build
   ```
4. Open http://localhost:3000 (web admin) and http://localhost:8000/docs (API).
5. Fill the database with demo data (in a second terminal, while the stack runs):
   ```bash
   docker compose --profile seed run --rm seed
   ```
6. Stop with `Ctrl+C` or `docker compose down`. Reset everything, database included: `docker compose down -v`.

The database is also reachable from your computer at `postgresql://cityecho:cityecho@localhost:5433/cityecho` (port 5433, so it does not clash with a local Postgres). Backend code under `backend/` reloads automatically; after changing `web-admin/`, run `docker compose up --build web`. Details and troubleshooting: [docker/README.md](docker/README.md).

**Mobile** runs outside Docker with Expo: `cd mobile && npx expo start`, with the API URL set to `http://<your-LAN-IP>:8000` (your computer's Wi-Fi IP, not `localhost`, because the phone is a different device).

**Türkçe kısa not:** Docker Desktop'ı kur ve aç. İsteğe bağlı: `cp .env.example .env` (API anahtarları). Sonra `docker compose up --build` çalıştır; web http://localhost:3000, API http://localhost:8000/docs adresinde açılır. Demo verisi için `docker compose --profile seed run --rm seed`. Durdurmak: `docker compose down`; veritabanı dahil her şeyi silmek: `docker compose down -v`. Mobil uygulama Docker dışında çalışır: `cd mobile && npx expo start`, API adresi `http://<bilgisayarının-LAN-IP'si>:8000`.

## Quick start (without Docker)

### 1. Backend

```bash
python3.11 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt        # core
.venv/bin/pip install -r backend/requirements-ml.txt     # optional: real embeddings + OSM download
cp .env.example .env                                     # fill in DATABASE_URL, API keys
.venv/bin/pytest                                         # 172 tests, no DB required
```

Without `ANTHROPIC_API_KEY`, triage uses a Polish/English keyword fallback. Without `sentence-transformers`, dedup uses a hashing embedding. Without `WARSAW_API_KEY`, or with `DEMO_MODE=1`, live vehicles come from `data/demo/ztm_snapshot.json`, which is sample data.

### 2. Database (Supabase or any Postgres with PostGIS)

```bash
.venv/bin/python scripts/init_db.py                          # schema.sql + functions.sql
.venv/bin/python scripts/load_osm.py --bbox demo             # city-centre road + tram segments (needs ML extras)
```

### 3. Run and seed

```bash
.venv/bin/uvicorn backend.main:app --reload                  # http://localhost:8000/docs
.venv/bin/python scripts/seed_demo.py                        # 367 synthetic complaints + 2 demo tram rides
```

### 4. Web admin

```bash
cd web-admin
npm install
cp .env.local.example .env.local
npm run dev            # live backend at NEXT_PUBLIC_API_URL
npm run dev:mock       # no backend needed: built-in Warsaw fixtures
```

Pages: `/` city health map + stats bar · `/incidents` queue · `/incidents/[id]` detail with sensor signal + timeline · `/report` citizen form · `/ride` phone sensor recorder (needs HTTPS on phones: `npm run dev:https`).

## Demo flow (3 minutes)

1. **Sensors:** the map shows tram 17's rides; click a red segment or sensor incident to see the vibration peak.
2. **Citizens:** paste a vague Polish complaint into `/report`. It gets structured, geocoded and merged into an existing incident ("23 others reported this. Status: likely (80% confidence)").
3. **Fusion moment:** citizens alone stop at *likely*. A report-only incident shows "Tram 17 will verify in ~6 min". Replay the ride and the confidence engine moves it to *verified*, updating the trust of everyone who answered:
   ```bash
   .venv/bin/python scripts/replay_ride.py --incident <id> --line 17 --wait 3
   ```
4. **Citizen check:** on any incident, answer "Is this problem still there? YES / NO". The answer is weighted by your trust, and your trust grows when your answers match the final outcome.
5. **Numbers:** the stats bar shows reports → incidents → verified → found before any report → average verification time.

## Useful scripts

| Script | Purpose |
|---|---|
| `scripts/synth_ride.py --name X [--night] --check` | Deterministic synthetic tram ride with ground truth |
| `scripts/gen_complaints.py [--llm]` | Synthetic 19115-style Polish complaints → `data/complaints_synth.json` |
| `scripts/eval_triage.py` | Measured category/routing accuracy and dedup quality (pitch numbers) |
| `scripts/replay_ride.py` | Upload a recorded ride; with `--incident` it plays out the verification loop |
| `scripts/seed_demo.py` | Fill a demo database through the API |
