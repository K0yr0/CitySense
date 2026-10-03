# CityEcho

**Warsaw's buses verify its citizens, and its citizens verify its buses.**

CityEcho brings together two channels that never talk to each other: what vehicles *sense* (cheap accelerometer/GPS/light sensors on trams and buses) and what people *report* (19115-style complaints). Both become one kind of **evidence** row anchored to a 25 m road/tram segment. A **fusion engine** clusters evidence into incidents, scores them, routes them to the right department, and flags problems the sensors found **before any citizen reported them**. For complaints that no sensor has seen yet, it asks the **next tram passing that spot** to verify (the verification loop).

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
frontend/           Next.js dashboard: city health map, incident queue/detail, citizen form, ride recorder
data/               demo rides, synthetic complaints, ZTM sample snapshot, caches
```

## Quick start

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

### 4. Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run dev            # live backend at NEXT_PUBLIC_API_URL
npm run dev:mock       # no backend needed: built-in Warsaw fixtures
```

Pages: `/` city health map + stats bar · `/incidents` queue · `/incidents/[id]` detail with sensor signal + timeline · `/report` citizen form · `/ride` phone sensor recorder (needs HTTPS on phones: `npm run dev:https`).

## Demo flow (3 minutes)

1. **Sensors:** the map shows tram 17's rides; click a red segment or sensor incident to see the vibration peak.
2. **Citizens:** paste a vague Polish complaint into `/report`. It gets structured, geocoded and merged into an existing incident ("23 others reported this").
3. **Fusion moment:** a report-only incident shows "Tram 17 will verify in ~6 min". Replay the ride and the incident turns *confirmed*:
   ```bash
   .venv/bin/python scripts/replay_ride.py --incident <id> --line 17 --wait 3
   ```
4. **Numbers:** the stats bar shows reports → incidents → found before any report → average verification time.

## Useful scripts

| Script | Purpose |
|---|---|
| `scripts/synth_ride.py --name X [--night] --check` | Deterministic synthetic tram ride with ground truth |
| `scripts/gen_complaints.py [--llm]` | Synthetic 19115-style Polish complaints → `data/complaints_synth.json` |
| `scripts/eval_triage.py` | Measured category/routing accuracy and dedup quality (pitch numbers) |
| `scripts/replay_ride.py` | Upload a recorded ride; with `--incident` it plays out the verification loop |
| `scripts/seed_demo.py` | Fill a demo database through the API |
