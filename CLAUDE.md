# CityEcho: project rules for Claude

This file is read automatically at the start of every Claude Code session. Everyone's Claude on the team follows the same rules.

**Project:** a Warsaw smart-city project. Data from bus and tram sensors (**entirely simulated**) and citizen complaints become the same kind of "evidence". A fusion engine turns them into incidents, and the confidence engine sets their status: candidate → likely → verified.

Details:
- Full plan and task split: [docs/ROADMAP.md](docs/ROADMAP.md)
- File ownership (enforced by the machine): [OWNERS](OWNERS)
- Architecture and API contracts: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- What has been built and tested: [BUILD_REPORT.md](BUILD_REPORT.md)
- **Open security findings, person by person:** [docs/SECURITY.md](docs/SECURITY.md). Fix only your own; mark ✅ when done.

## 1. At the start of a session: who are you working with?

Three people, each working **on their own computer** and pushing to the same repo. Tasks **must never overlap**.

| | Person A: 📱 Mobile (citizens) | Person B: 🖥️ Web admin (city) | Person C: 📡 Sensor simulation and data |
|---|---|---|---|
| Main folders | `mobile/` (code in `mobile/src/`) | `web-admin/` | `backend/sensor/`, sensor scripts |
| Task codes | M0–M7 | W0–W5 | S0–S6 |
| Migration numbers | 100–199 | 200–299 | 300–399 |

**First thing:** run `git config --get cityecho.role`.
- If it is empty: ask the user whether they are A, B or C and do the setup (section 3).
- If it is set: write only to that role's files.

## 2. Hard rules (never break them)

1. **Every file has exactly one owner.** Ownership is in the `OWNERS` file. Only the owner writes to a file; reading is free.
2. **If someone else's file needs a change:** don't change the code yourself. Tell the user exactly what is needed (file, function, why); they pass it on to the owner.
3. **Shared (SHARED) files are frozen.** They are marked `SHARED` in `OWNERS`: `backend/main.py`, `db/schema.sql`, `backend/config.py`, `backend/models.py`, `backend/db.py`, `requirements*.txt`, `.env.example`, `scripts/init_db.py`, `CLAUDE.md`, `docs/**`, `OWNERS`. If one must change:
   1. Announce it in the group first; one person does it.
   2. Update with `git pull --rebase`.
   3. Make a separate commit containing **only** shared files: `CITYECHO_SHARED=1 git commit -m "..."`
   4. Push right away, and don't move on to the next one until everyone has said "pulled".
4. **Database changes** go to `db/migrations/`, not `db/schema.sql`: A `1xx_*.sql`, B `2xx_*.sql`, C `3xx_*.sql`. A pushed migration is **never edited** again; fixes go in a new migration.
5. **A new file** that matches no pattern in `OWNERS` is blocked at commit. Add it to `OWNERS` first (in a SHARED commit).
6. **Contracts** (function, column and endpoint names between people) are fixed in `docs/ROADMAP.md` → "Contracts". They are never changed by one side alone.
7. **OpenAPI and generated types are not committed.**
8. **Secrets:** only in the `.env` file (gitignored). Never commit them, never print them.
9. **Commit messages** must **not** contain a `Co-Authored-By: Claude` or "Generated with Claude Code" line.
10. **Don't skip the hook.** Don't use `--no-verify`; if the hook blocks something, fix the cause.

## 3. Setup (once per computer)

```bash
git clone https://github.com/K0yr0/cityecho.git && cd cityecho
git config core.hooksPath .githooks       # the ownership check runs on every commit
git config cityecho.role A                # your role: A, B or C
git config pull.rebase true               # pull always rebases
python3 scripts/check_owners.py --all     # should say "0 without an owner"
```

Then the backend setup (section 7).

## 4. Daily git flow (everyone pushes directly to main)

```bash
git pull                                  # 1. before starting work
# ... work only in your own files ...
.venv/bin/pytest                          # 2. no push until the tests pass
git add <your files> && git commit        # 3. the hook blocks other people's files
git pull && .venv/bin/python scripts/init_db.py   # 4. pick up other people's migrations
git push                                  # 5. small, frequent pushes
```

- **Never** `git push --force`, never revert someone else's commit.
- Because everyone writes only to their own files, `git pull` (rebase) produces no conflicts. A conflict means a rule was broken: ask the file's owner, don't resolve it yourself.
- Every push to `main` redeploys Vercel. A push that breaks the web app affects everyone, so B runs the web build (`npm run build`) before pushing.

## 5. Decisions already made (don't reopen them)

- The citizen side is a **mobile app** (Expo), the admin side is the **web** (Next.js).
- **No real sensors / ESP32. Everything is simulated.** Person C generates the virtual buses' sensor data (`scripts/simulate_buses.py`) and sends it to the `/devices/stream` endpoint like a real device. The presentation says clearly that the data is simulated.
- The web `/ride` phone recording page **will be deleted**.
- Trust earned before signing in **carries over to the account** at Google sign-in.
- The admin sees **all departments** (ZDM, Tramwaje Warszawskie, MPWiK, Straż Miejska).
- The automatic "is there a pothole here?" **pop-up appears within 25 m**. A Yes/No answer (pop-up or a tapped problem on the map) **counts within 100 m**. Both need the phone's GPS accuracy ≤ 25 m and sign-in; one answer per person per problem.
- There are two separate status fields; never mix them: the **confidence status** (candidate / likely / verified / dismissed, set by the engine) and the **work status** `work_status` (not started / in progress / done, set by the city).
- **When "done" is set:** the question stops, trust scores are settled, and NO answers that arrive after the repair don't count against anyone.
- Citizens **don't see** sensor data, the evidence timeline or facts; those are admin-only. Citizens see road health **only as a colour**.
- The mobile app is in **English, Polish and Ukrainian** (no Turkish); the backend's citizen messages follow `Accept-Language`.

## 6. Order of work

**Day 0 is done** (shared foundation, sign-in skeleton, migrations, Docker, map data, mobile skeleton, `web-admin/` move). All three start at the same time:

```
A → M0 → M1 → M2 → M3 → M4 → M5 → M6 (→ M7)
B → W0 → W1 → W2 → W3 → W4 → W5
C → S1 → S2 → S3 → S4 → S5 → S6  (S0 map: done)
```

Task contents: `docs/ROADMAP.md`. Day 0 contracts (sign-in, roles, `work_status`, `/devices/stream` format, short incident view): `docs/ARCHITECTURE.md` §8.

## 7. Running

**Easy way: Docker** (Docker Desktop must be installed; details: `docker/README.md`):
```bash
cp .env.example .env                              # optional keys
docker compose up --build                         # database + backend + web admin
# http://localhost:3000  (web admin)   http://localhost:8000/docs  (API)
docker compose --profile seed run --rm seed       # load the demo complaints and rides (old, slow)
docker compose --profile mock run --rm mock       # S6: the whole-project mock world (once C has built it)
docker compose down -v                            # reset everything
```
✅ Docker verified (Apple Silicon Mac, Colima): database, migrations, map loading (seconds), API, live vehicles, web admin and demo data (367 complaints → 74 incidents) work end to end.

Free command-line alternative to Docker Desktop (Mac): `brew install colima docker docker-compose && colima start --cpu 4 --memory 6`. Windows/Linux: Docker Desktop or Docker Engine.

**Why test locally:** on Vercel's free plan, only the repo owner's (A's) commits are deployed for a private repo. B's and C's pushes land in the repo but don't reach the site. Everyone tests their changes on their own computer with Docker.

**Without Docker:**
```bash
python3.11 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt
cp .env.example .env
brew install postgresql@18 postgis && createdb cityecho
.venv/bin/python scripts/init_db.py                                                   # after every git pull
.venv/bin/python scripts/load_osm.py --from-geojson data/osm/segments_demo.geojson --skip-if-loaded   # map, seconds
.venv/bin/uvicorn backend.main:app --reload                                           # http://localhost:8000/docs
cd web-admin && npm install && npm run dev                                            # http://localhost:3000
```

**Mobile** (A; outside Docker): `cd mobile && npm install && npx expo start`, Expo Go on the phone. For the phone, set `EXPO_PUBLIC_API_URL=http://<your-computer's-LAN-IP>:8000` in `mobile/.env`. Node 22 or 24 recommended (23 prints a warning).

`.env` contents (everyone has their own `.env`; it is not shared):
- `DATABASE_URL=postgresql://localhost:5432/cityecho`
- `WARSAW_API_KEY`: the long `eyJ...` token from your api.um.warszawa.pl account (everyone uses their own account)
- `NOMINATIM_USER_AGENT`: a real email address
- `ANTHROPIC_API_KEY`: optional; without it the keyword fallback runs
- `GOOGLE_CLIENT_IDS`, `AUTH_SECRET`, `ADMIN_EMAILS`: Google sign-in (set up by A). To try it locally without Google: `AUTH_DEV_LOGIN=1` → `POST /auth/dev {"email": ...}`
- `DEVICE_KEYS`: the virtual buses' device keys (C)

## 8. Current status (keep this file up to date)

- ✅ Backend: sensor pipeline, complaint triage, fusion, confidence engine, contributor trust, verification loop. 278 tests pass (`.venv/bin/pytest`; PostGIS tests with `CITYECHO_TEST_DB=1`).
- ✅ Day 0: all routers registered; sign-in skeleton (`backend/auth/`: `current_user`, `require_admin`, Google + dev sign-in, trust carry-over); migration system and the 100/200/300 migrations (`users`, `work_status`, `devices`); Docker; mobile skeleton (Expo SDK 57).
- ✅ The web interface is in `web-admin/`. The citizen pages are still in it; B deletes them in W0.
- ✅ Public demo site: https://cityecho-gules.vercel.app (with demo data). Updated only by A's pushes (section 7).
- ✅ Docker verified end to end (section 7).
- ✅ Live Warsaw vehicle positions work (new API, see below).
- ✅ Ownership check: `OWNERS` + `.githooks/pre-commit` + `scripts/check_owners.py`.
- ✅ Map (S0): 11,833 segments (9,057 road, 2,776 rail) with real vulnerability data; `data/osm/segments_demo.geojson` is in the repo, loading takes seconds. Demo tram rides are aligned with the real rails (100%).
- ✅ Mobile app (A, M0–M6): map with current location and road health as colour only, Google + demo sign-in with trust carry-over, reporting with photo and location, the 25 m question, favourite routes with "bad road ahead" warnings, short incident view. `/mobile/*` endpoints in `backend/api/mobile.py`, migration `101_favorite_routes.sql`. Languages: English, Polish, Ukrainian (`mobile/src/i18n/`). M7 (notifications) not started.
- ✅ Sensor simulation (C, S1–S5): `/devices/stream` (`X-Device-Key`, one buffer per device); `scripts/simulate_buses.py` virtual fleet: buses drive the real routes of ZTM lines 171, 159, 107 and 160 (Warsaw GTFS, `data/demo/bus_lines.json`), tram 17 drives Marszałkowska (device names `bus-171|159|107|160-NN`, `tram-17-NN`; `docker compose --profile sim up simulator`); fixed ground truth `data/demo/sim_world.json`; road health = median of the last 5 passes + `health_updated_at` (freshness) + `health_weight` (301); accuracy report `data/demo/sim_accuracy.md` (`--eval`, measured in simulation); stage scenarios `--scenario all` (~15 s on a clean database).
- ✅ **S6, whole-project mock data (C):** `docker compose --profile mock run --rm mock` (or `scripts/seed_world.py`; `--fast`, `--check`) fills every feature of the mobile app and the web admin with one consistent world through the API only, in ~90 s (`--fast` ~50 s): 14 days of complaints and back-dated rides along the real bus lines (~1,300 measured road segments), 8 demo citizens + admin (`admin@cityecho.test`, dev sign-in), photos, answers with diverging trust, routes, work status, dismissed false alarms. Accounts and stage walkthrough: `data/mock/README.md`. Waiting for A and B to confirm their screens. C also owns `seed_demo.py` (old, slow), `gen_complaints.py` and `data/complaints_synth.json`.
- ✅ Trams can't verify road potholes (by design); simulated buses verify road potholes (line 171 runs along Marszałkowska next to tram 17).
- ❌ Known gap (B and C): a tram line consists of two parallel rails; a ride's GPS jumps between them. Fusion's "≥ 2 rides on the same segment" rule must count the two rails as one.
- ✅ Demo data aligned (S5): defects placed at the complaint clusters (`ANCHORS`); the 40 "track defect" complaints on Świętokrzyska are verified at 97% after `seed_demo`. A verified incident is not closed by clean passes; the repair is closed by B's `work_status = done` flow.
- ℹ️ `nearest_segment(...)` finds the nearest road at ~16 m and the nearest rail at ~24 m on Marszałkowska; a 50 m radius may be needed when searching rails only.

## 9. Pitfalls

- **Warsaw's live vehicle API changed.** Address: `POST https://dane.um.warszawa.pl/api/action/get_ztm_lokalizacja_pojazdow`, body `{"type": 1|2}` (1 = bus, 2 = tram), token in the `Authorization` header. The old `busestrams_get` + `apikey=` no longer works. The code uses the new one (`backend/fusion/verify.py`).
- **With Docker + Colima, `--reload` doesn't see file changes:** after code changes run `docker compose restart api`; after `.env` changes run `docker compose up -d --force-recreate api`.
- **`seed_demo` takes ~8–9 minutes** (triage of 367 complaints). Prepare it before the presentation.
- **Overpass (OpenStreetMap) is slow** and often times out. Downloads are cached in `data/cache/osmnx`.
- `frontend/AGENTS.md`: APIs may have changed in this Next.js version. Read the docs in `node_modules/next/dist/docs/` before writing a new Next feature.
- Accuracy numbers (category 97% etc.) come from **synthetic data**. Present them as "measured in simulation".
