# CityEcho Roadmap: Mobile + Web Admin + Sensor Simulation (3 people)

Citizens use the **mobile** app, the city uses the **web**; the **simulation** of the bus sensors belongs to a separate person. Three people, each working on their own computer and pushing to the same repo. Tasks are split by file ownership so that they **never overlap**, and the machine checks this rule on every commit (`OWNERS` + git hook). Short rules for Claude are in `CLAUDE.md` at the repo root.

| | Person A: 📱 Mobile | Person B: 🖥️ Web admin | Person C: 📡 Sensor simulation and data |
|---|---|---|---|
| What they build | The app citizens use | The city's panel; incidents and work flow | **Generates and processes** the virtual buses' sensor data |
| Tasks | M0–M7 | W0–W5 | S0–S5 |
| Branch | `mobile/...` | `admin/...` | `sensor/...` |
| Migration numbers | 100–199 | 200–299 | 300–399 |

## Decisions made

| Topic | Decision |
|---|---|
| Platform | Citizens: **mobile app** (React Native + Expo). Admin: **web** (Next.js) |
| Trust earned before sign-in | **Carries over to the account** at Google sign-in |
| Admin access | Sees **all departments** |
| Sensor data | **No real sensors / ESP32, everything is simulated** (person C). The simulator sends data in the same format to the `/devices/stream` endpoint a real device would use. The web `/ride` page is deleted |
| "Is there a pothole around you?" radius | **25 m**; asked only while GPS accuracy is ≤ 25 m |
| Mobile app languages | **English, Polish, Ukrainian** (no Turkish); the backend's citizen messages follow `Accept-Language` |

## Project structure

```
mobile/          → Person A   Citizen app (Expo, iOS + Android)
web-admin/       → Person B   City panel (the old frontend/ moves here)
backend/sensor/  → Person C   Sensor pipeline (detection, map matching, road health)
scripts/simulate_buses.py → Person C   Virtual bus fleet (sensor simulator)
backend/ (the rest) → A and B, but every file has ONE owner
```

## 3 rules that prevent conflicts

1. **Every file has one owner** (the `OWNERS` file). Reading is free; writing belongs to the owner only. A commit touching someone else's file is blocked on the computer.
2. **Shared files are prepared once on Day 0 and then frozen.**
3. **People depend on each other's contracts, not their code.** The contracts are fixed in the table below.

---

## Day 0: shared foundation ✅ DONE (frozen)

All of the following is done and in the repo. Also: Docker setup (`docker-compose.yml`, `docker/`), the map file `data/osm/segments_demo.geojson`, the mobile skeleton `mobile/` (Expo SDK 57). Contract details: `docs/ARCHITECTURE.md` §8.

| Work | Done by |
|---|---|
| `backend/main.py`: every router registered up front (`users`, `responses`, `mobile`, `admin`, `devices`) | A |
| `backend/auth/`: Google token verification, our own session token, `current_user`, `require_admin` | A |
| `db/schema.sql` frozen; `db/migrations/` opened (**A 100–199, B 200–299, C 300–399**); `scripts/init_db.py` applies the migrations in order | A |
| `requirements.txt` and `.env.example`: all new dependencies and variables (google-auth, `GOOGLE_CLIENT_ID`, `ADMIN_EMAILS`, `DEVICE_KEYS`) | A |
| `mobile/` skeleton (`npx create-expo-app`) | A |
| Move `frontend/` → `web-admin/` and update the root directory on Vercel | B |
| **S0:** load the Warsaw map segments into the database (`scripts/load_osm.py --bbox demo`) | C |

**OpenAPI and generated types are not committed to git.** Each app generates its types from the running backend into its own folder.

---

## File ownership

| Area | 📱 **Person A** | 🖥️ **Person B** | 📡 **Person C** |
|---|---|---|---|
| App | `mobile/**` | `web-admin/**` (for now also `frontend/**`) | — |
| Backend API | `auth/`, `api/users.py`, `api/responses.py`, `api/reports.py`, `api/mobile.py` | `api/admin.py`, `api/incidents.py`, `api/serializers.py`, `api/stats.py`, `api/vehicles.py`, `api/segments.py` (display) | `api/devices.py` (new), `api/rides.py` |
| Backend logic | `fusion/trust.py`, `triage/**` | `fusion/incidents.py`, `verify.py`, `confidence.py`, `score.py`, `routing.py` | `sensor/**` (ingest, detect, lights, mapmatch, track_score, pipeline) |
| Database | `migrations/1xx_*` (users, favorite_routes, trust carry-over) | `migrations/2xx_*` (`work_status`) | `migrations/3xx_*` (devices, time weighting of road health), `db/functions.sql` (`nearest_segment`, `recompute_segment_health`) |
| Scripts | `eval_triage.py` | — | `simulate_buses.py`, `synth_ride.py`, `replay_ride.py`, `load_osm.py`, **all mock data:** `seed_world.py` (new, S6), `seed_demo.py`, `gen_complaints.py`, `scripts/mock/**` |
| Tests | `test_auth.py`, `test_mobile_*.py`, `test_triage_*.py`, `test_confidence_trust.py` | `test_admin_*.py`, `test_fusion.py`, `test_api.py` | `test_devices.py`, `test_sensor_*.py`, `test_load_osm.py`, `test_seed_world*.py`, `test_mock*.py` |
| Data | — | `data/demo/ztm_snapshot.json` | `data/demo/*.csv`, `data/osm/`, the simulator's ground-truth files, `data/complaints_synth.json`, `data/mock/**` |

**Reading is always free.** For example, A's `api/mobile.py` may read the `incidents` and `segments` tables; only B's code writes `incidents`, and only C's code writes `segments.health`.

**Shared (SHARED) files** (marked in `OWNERS`): `backend/main.py`, `db/schema.sql`, `backend/config.py`, `backend/models.py`, `backend/db.py`, `requirements*.txt`, `.env.example`, `scripts/init_db.py`, `CLAUDE.md`, `docs/**`, `OWNERS`. The change process is in the "Git workflow" section below.

The complete, authoritative list is the `OWNERS` file; this table is a summary. If the two disagree, `OWNERS` wins.

## Contracts (between people, names fixed)

| Provider → consumer | Contract | Purpose |
|---|---|---|
| A → B | `require_admin` (FastAPI dependency) | Protect the admin endpoints |
| A → B | `trust.settle(conn, incident_id, real=True)` (already exists) | Settle trust scores when "done" is pressed |
| B → A | `incidents.work_status` column (`todo` / `in_progress` / `done`) | Mobile stops the 25 m question for `done` incidents |
| B → A | `incidents.confidence`, `incidents.status` columns | The short incident view on mobile |
| B → C | `fusion.incidents.ingest_evidence(conn, evidence_ids)` and `verify.check_ride_verifications(conn, ride_id)` (already exist) | Link C's sensor evidence to incidents; count passes as verifications |
| C → B and A | `segments.health`, `segments.health_rides`, `segments.health_updated_at` (freshness), `segments.health_weight` (time-weighted amount of data) columns | B's live map, A's road colours. Only C writes them |
| C → B | `/devices/stream` data format (written in `docs/ARCHITECTURE.md`) | The simulator sends in this format, like a real device |
| C → A | `data/complaints_synth.json` record shape stays stable: `text`, `created_at`, `true_issue_id`, `true_category`, `lon`, `lat`, `street` | A's triage evaluation (`eval_triage.py`) and tests read it |
| A, B → C | The public HTTP API (`docs/ARCHITECTURE.md` §6 and §8): `/auth/dev`, `/reports`, `/reports/bulk`, `/incidents/{id}/responses`, `/mobile/*`, `/admin/incidents/{id}/work`, `/devices/stream` | C's mock seeder writes **only through these endpoints**, never straight into other people's tables. If an endpoint is missing or too slow, C asks its owner |
| C → A, B | `data/mock/README.md`: the demo accounts (emails, roles), personas and what the seeded world contains | A and B know which accounts and incidents to show in the apps and on stage |

If a contract must change: announce it in the group, the people involved approve, and the change is written to `docs/` in a separate SHARED commit.

---

## 📱 Person A: mobile tasks

| # | Task | Details |
|---|---|---|
| M0 | Setup | Expo skeleton, connection to the backend, demo mode |
| M1 | Map | **Current location** button (with an accuracy ring); incidents and road health **as colour only** (good / fair / poor / not measured) |
| M2 | Sign-in | One tap with Google; the trust score on the device **carries over** to the account; signing in is required to report and answer, viewing the map is free |
| M3 | Reporting a problem | Text, camera/photo, location; then a short status ("23 other people reported this", "the city is working on it", "fixed") |
| M4 | 25 m question | "Do you see a pothole within 25 m of you? Yes / No". Local GPS, accuracy ≤ 25 m, once per incident, not asked when `work_status = done`, answers weighted by trust |
| M5 | Favourite routes | Start/end or a bus/tram line; road quality along the route as colour, "bad road ahead" warning |
| M6 | Short incident view | Type, address, confidence label, the city's work status. **No sensor data, timeline or facts** |
| M7 | Notifications (optional) | "The pothole you reported was fixed", "new problem on your route" |

## 🖥️ Person B: web admin tasks

| # | Task | Details |
|---|---|---|
| W0 | Move | `frontend/` → `web-admin/`; delete the citizen pages (`/report`, `/ride`, citizen YES/NO); the whole site requires admin sign-in; fix the overlapping visuals on the home page |
| W1 | Incident queue | Filters for department, confidence status and work status; sorted by priority; all departments |
| W2 | Full incident detail | Sensor signal chart, **evidence timeline**, **facts**, confidence breakdown, all reports and photos, citizen answers |
| W3 | Work flow | **Not started → in progress → done**, who changed it and when. A field separate from the confidence status. **Done** → `trust.settle` is called, the question stops |
| W4 | Live map (display) | Shows the `segments.health` and freshness that C writes; live bus/tram positions (the Warsaw API already works) |
| W5 | Statistics | Report → incident → verified → done, average repair time, department load |

## 📡 Person C: sensor simulation and data tasks

There is no real hardware; all sensor data comes from the simulation. The simulation uses the same endpoint and the same format as if a real device existed.

| # | Task | Details |
|---|---|---|
| S0 | Map segments | Load Warsaw's road and rail network into the database (`scripts/load_osm.py --bbox demo`). The Overpass server is slow; run it from a terminal. **First job**, because everyone needs it |
| S1 | Device API | A device key per virtual bus, protected `/devices/stream`; connects incoming data to the existing sensor pipeline (`sensor/pipeline.py`) and to B's `ingest_evidence` function. The data format is written in `docs/ARCHITECTURE.md` |
| S2 | **Sensor simulator** | `scripts/simulate_buses.py`: drives many virtual buses and trams along real routes (OSM segments; optionally live ZTM positions). Generates acceleration, GPS and light data with the `synth_ride.py` logic; places potholes, track defects and dark lamps at fixed, known points; sends to `/devices/stream`; keeps the list of defects it placed (ground truth) |
| S3 | Live road health | `segments.health` is recomputed as data arrives, newer measurements weigh more (time weighting); freshness and data-amount columns |
| S4 | Accuracy measurement | Precision / recall report against the simulator's ground truth (varying noise, speed and phone position); numbers for the presentation, presented as "measured in simulation" |
| S5 | Demo scenarios | Scenarios triggered on stage with one command: "a new pothole appeared → buses found it → found before any complaint", "a citizen reported → the next bus passed → verified", "repaired → the bus no longer feels anything". Repeatable (fixed seed) |
| S6 | **Whole-project mock data** | One command fills the **entire** project with a consistent, realistic world, so every screen of the mobile app and the web admin has something meaningful to show. Details below |

### S6: whole-project mock data (owner C)

**Goal:** after `docker compose up --build` and **one** command, every feature of A's mobile app and B's web admin shows realistic, consistent data. The same seed always produces the same world.

**Commands:**
- Docker: `docker compose --profile mock run --rm mock` (the service already exists in `docker-compose.yml`)
- Without Docker: `.venv/bin/python scripts/seed_world.py --api http://localhost:8000`
- Options: `--seed N` (default fixed), `--fast` (smaller world for quick local tests), `--check` (verify the world is complete and exit non-zero if not)

**Rules:**
- **API only.** `seed_world.py` writes only through the public endpoints (contract table above), never with direct SQL into other people's tables. Dev sign-in (`POST /auth/dev`) creates the demo users and the admin; it is on in the local Docker stack.
- **One world.** Complaint clusters, simulator defects (`data/demo/sim_world.json`) and road health must agree: where citizens report a pothole, the simulated buses feel it (or deliberately don't, for the "dismissed" cases).
- **Idempotent.** Running it twice does not duplicate data (it detects an already seeded world and exits), and `docker compose down -v` gives a clean start.
- **Target time:** under ~3 minutes for the full world; `--fast` under ~1 minute. `seed_demo.py` takes ~8–9 minutes today because every complaint is geocoded at 1 request/second; send coordinates with each complaint and, if that is not enough, ask A for a faster triage path instead of editing A's code.
- **English only** in all files; citizen-facing complaint texts stay realistic Polish (with some English and Ukrainian).

**What the world must contain** (every item is shown somewhere in an app):

| Area | Mock data | Seen in |
|---|---|---|
| Accounts | 1 admin + ~8 citizen personas via `/auth/dev`: a reliable reporter (high trust), a newcomer, an unreliable one (wrong answers, low trust), a commuter with favourite routes, … Written to `data/mock/README.md` | Mobile sign-in, admin |
| Complaints | Several hundred complaints over the last ~14 days, from personas and anonymous 19115 imports, all categories and departments, some with photos (generated, no real people) | Mobile map, admin queue |
| Citizen answers | YES/NO answers to "is it still there?" from the personas, so trust differs between people | Admin incident detail, mobile profile |
| Sensor rides | Simulated bus and tram fleet runs (existing `simulate_buses.py`), so road health covers the main corridors with fresh and stale segments | Mobile road colours, admin live map |
| Full lifecycle | Incidents in every state: candidate, likely, verified, dismissed, found-before-report, awaiting a vehicle | Everywhere |
| City work | `work_status` mix via the admin endpoint: todo, in progress, done (done ones settle trust) | Admin workflow, mobile "fixed by the city" |
| Favourite routes | Several saved routes per commuter persona, some passing bad segments | Mobile routes, "bad road ahead" |
| Stats | Enough volume that the admin statistics and funnel look real | Admin stats |

**Done when:** `--check` passes on a clean Docker stack; A and B confirm every screen shows data; `data/mock/README.md` lists the demo accounts and what to click on stage; tests in `backend/tests/test_seed_world*.py` pass.

---

## Order and dependencies

```
Day 0:  A → backend foundation + sign-in + mobile/ skeleton   [SHARED commits]
        B → frontend/ → web-admin/ move
        C → S0 (map segments)
Then:   A → M0 → M1 → M2 → M3 → M4 → M5 → M6 (→ M7)
        B → W0 → W1 → W2 → W3 → W4 → W5
        C → S1 → S2 → S3 → S4 → S5 → S6
```

- **M4 ↔ W3:** the "don't ask if done" part stays passive until the `work_status` column exists and starts working by itself once it does. A doesn't have to wait.
- **M1/M5 and W4 ↔ S2/S3:** road colours and the live map start filling once C's simulator runs. Until then A and B work with the existing demo data; nobody waits.
- **Day 0:** until A's SHARED commits are pushed, B and C work only in their own folders; conflicts are impossible meanwhile.
- **S1 ↔ B:** C calls B's existing `ingest_evidence` function. It already exists; no need to wait for B.
- **S6 ↔ A, B:** C uses A's and B's existing endpoints. If an endpoint the mock data needs is missing, C writes down exactly what is needed and the owner adds it; C never edits A's or B's files.

## Git workflow (everyone on their own computer, pushing directly to main)

**One-time setup (on each computer):**
```bash
git clone https://github.com/K0yr0/cityecho.git && cd cityecho
git config core.hooksPath .githooks       # the ownership check runs on every commit
git config cityecho.role A                # your role: A, B or C
git config pull.rebase true
python3 scripts/check_owners.py --all     # should say "0 without an owner"
```

**Every day:**
1. `git pull`: before starting work.
2. Work only in your own files.
3. Tests: `.venv/bin/pytest` (B also `npm run build`). No push until they pass.
4. `git commit`: the hook blocks a commit containing someone else's file or a shared file.
5. `git pull` + `.venv/bin/python scripts/init_db.py`: pick up other people's migrations.
6. `git push`: small and frequent.

**Why there are no conflicts:** since two people never write to the same file, `git pull --rebase` never produces a text conflict. A conflict means a rule was broken: ask the file's owner; nobody "resolves" someone else's file themselves.

**Changing a shared (SHARED) file:**
1. Announce it in the group; only one person does it at a time.
2. `git pull`, then a separate commit containing only shared files: `CITYECHO_SHARED=1 git commit -m "..."`
3. Push right away; the others run `git pull`.

**Forbidden:** `git push --force`, `git commit --no-verify`, reverting someone else's commit, editing a pushed migration, committing the `.env` file, adding a Claude / Co-Authored-By line to a commit message.

## Risks

- **Simulation:** all sensor data comes from the simulation. Say so clearly in the presentation; accuracy numbers are presented as "measured in simulation" (S4).
- **Personal data (RODO/GDPR):** Google sign-in and location use mean personal data. Only email and identity are stored, no location history is kept, and a privacy notice is added.
- **Demo access:** after W0 the public Vercel site requires admin sign-in. For the jury, either an admin account is created or the mobile app is shown with Expo Go.
- **Trams and road potholes:** trams can't verify road potholes; C's simulated buses verify road potholes.
- **Pushing directly to main:** every push redeploys Vercel and affects everyone. Never push without running the tests.
