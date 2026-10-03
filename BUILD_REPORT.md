# CityEcho: Build Report

*Ground architecture built from the `CityEcho_vs.md` roadmap · 2026-10-03 · updated to match the algorithm chart*

## What exists now

The four core parts of the roadmap's 24-hour plan are implemented end to end as real code (not stubs): **sensor pipeline + text triage + fusion + map**. The API, demo scripts, synthetic data and a frontend dashboard tie them together.

The verification loop, photo anonymization, streetlight detection and the live ride recorder are also in. ESP32 firmware and air quality are not (both are optional in the roadmap).

| | |
|---|---|
| Backend tests | **198 passed, 1 skipped** (the skip needs a real PostGIS database) |
| SQL statements | **42 / 42 parse** with the real Postgres parser (pglast) |
| Frontend | `npm run build` passes, lint clean, 6 routes |
| API | Starts, serves all 12 routes from §6 of the contract |

## How it was built

First, a shared foundation: `db/schema.sql`, `backend/config.py`, `backend/models.py`, and a written contract (`docs/ARCHITECTURE.md`) fixing every function signature and JSON shape. Then 8 agents worked in parallel, each owning a separate set of files.

| # | Agent | Files | Tests | Key result |
|---|---|---|---|---|
| 1 | Database + OSM | `backend/db.py`, `db/functions.sql`, `scripts/init_db.py`, `scripts/load_osm.py` | 32 + 1 skip | Batched nearest-segment matching; OSM split into 25 m segments with a vulnerability score |
| 2 | Sensor signal | `sensor/ingest.py`, `detect.py`, `track_score.py`, `scripts/synth_ride.py` | 14 | Reads Sensor Logger exports; 2 demo tram 17 rides (day + night) |
| 3 | Sensor geo | `sensor/lights.py`, `mapmatch.py`, `sensor/pipeline.py` | 17 | Broken-streetlight detection on distance-resampled lux; full ride → evidence pipeline |
| 4 | LLM triage | `triage/structure.py`, `vision.py`, `scripts/gen_complaints.py` | 16 | Claude call checked against a JSON schema, with a keyword fallback; EXIF strip + face/plate blur; 367 synthetic Polish complaints |
| 5 | Geocode + dedup | `triage/geocode.py`, `dedup.py`, `triage/pipeline.py`, `scripts/eval_triage.py` | 19 | Nominatim with cache and rate limit; merge rule of 50 m / 72 h / text similarity |
| 6 | Fusion | `fusion/incidents.py`, `score.py`, `routing.py`, `verify.py` | 47 | Evidence → incident matching, explainable score, "found before report" flag, ZTM verification loop |
| 7 | API | `backend/main.py`, `backend/api/*`, `scripts/seed_demo.py`, `scripts/replay_ride.py` | 26 | 12 endpoints; per-record savepoints in bulk import; stage replay of the verification loop |
| 8 | Frontend | `frontend/**` | build + lint | Health map (MapLibre + deck.gl), queue, detail with signal chart, citizen form, phone ride recorder; mock mode |

## Measured results (synthetic data, offline)

| Metric | Result | Roadmap target |
|---|---|---|
| Bump detection (2 demo rides) | 6/6 found, 0 false; within 1–4 m | precision ≥ 70 %, recall ≥ 60 % |
| Bump detection (30 extra seeded rides) | 240/240, 0 false; 0 false on 30 smooth rides | — |
| Dark gaps (night ride) | 4/4 broken lamps, 0 on the day ride | — |
| Category accuracy (keyword fallback, 367 complaints) | 97.3 % | ≥ 85 % |
| Routing accuracy | 97.3 % | ≥ 90 % |
| Dedup (purity / ARI) | 1.000 / 0.952 | ≥ 80 % |
| Compression | 367 complaints → 55 clusters (true: 40) | show the number |

**Honesty note for the pitch:** these numbers come from synthetic data that the same system generated. They are not real-world accuracy. The synthetic issues are far apart, and the keyword fallback and the complaint generator were written together. Present them as "pipeline works end to end", and replace them with numbers from real rides and real complaints.

## Fixes made during integration

1. **OpenCV pinned below 5.** OpenCV 5.0 removed the face/plate detector (`CascadeClassifier`), so photos were only metadata-stripped and never blurred. It is now pinned to `>=4.9,<5` (4.14 installed); blurring works and the test passes.
2. **Photos that can't be blurred are not stored.** The report pipeline now drops a photo if blurring is unavailable, so the GDPR promise in the pitch holds.
3. **Stale incident summaries.** The cached LLM summary is now cleared whenever new reports merge into an incident.
4. **Demo map area.** The `--bbox demo` area of `load_osm.py` cut off both ends of the synthetic tram 17 ride. It is widened to `20.975,52.208,21.030,52.248`.

## Update: aligned with the algorithm chart

The algorithm chart (vehicle sensors and citizen YES/NO → clustering → sensor confidence + trust-weighted
citizen confidence → confidence engine → candidate / likely / verified → dashboard + contributor trust
update → future answer weight) was compared with the code. Six boxes were missing or partial:

| Chart box | Before | Now |
|---|---|---|
| Citizen Response YES / NO | Only new complaints, no NO | `POST /incidents/{id}/responses`; each report is also an implicit YES |
| Sensor Confidence | Raw counts; clean passes only changed a label | Hits per ride (by severity) minus clean passes by a vehicle that could have felt it |
| Citizen Confidence × User Trust | No identity; every report weighed 1 | Anonymous contributors (salted hash of a browser token); answers weighted 2 × trust |
| Confidence Engine | Only a priority score; fixed status rules | `backend/fusion/confidence.py`: log-odds sum → one confidence |
| Status Candidate · Likely · Verified | open / awaiting / confirmed / no_anomaly | candidate < 60 % ≤ likely < 85 % ≤ verified; plus dismissed < 10 % |
| Contributor Trust Update → future weight | Missing | `backend/fusion/trust.py`: answers scored when an incident resolves; trust = (correct+3)/(correct+incorrect+5) |

Two design choices go beyond the chart:
- **`dismissed` status.** Without a negative outcome, people who correctly answer NO could never gain trust.
- **Cap on the crowd.** Citizen answers alone cannot reach *verified* (the citizen points are capped), because 30 people repeating one complaint are not 30 independent witnesses. A vehicle sensor pass, or several sensor rides, verifies.

The frontend shows the chart directly. The incident page has a confidence breakdown (sensor → citizen → engine → status) and the "Is this problem still there? YES / NO" prompt. The map panel has the same prompt in compact form. Queue chips show status with confidence. The public demo data derives every status from the same engine (`frontend/lib/confidence.ts` mirrors the Python one).

## Not verified yet

- **No SQL has run against a real PostGIS database.** It was syntax-checked and tested with fake connections only (local Postgres has no PostGIS, and there is no Docker). This is the biggest remaining risk.
- **`load_osm.py` has never downloaded OSM data** (osmnx/geopandas are in `requirements-ml.txt`, which is not installed).
- **Claude API path not exercised.** There is no key here, so only the keyword fallback and a mocked client were tested.
- **ZTM live API not called.** `data/demo/ztm_snapshot.json` is a hand-made **sample**, labelled as such.
- **Frontend not tested against the live backend.** It was checked in headless Chrome against its own fixtures.
- **The new confidence and trust SQL is untested against PostGIS too:** `citizen_responses` upserts, `contributors`, and the trust-settlement query (42 statements parse; none has run).
- **A tram cannot verify a road pothole.** Tram detections are typed `tram_track` and only cluster with `tram_track` incidents, and tram clean passes don't count against road damage. The roadmap's "tram 17 verifies a pothole" story (demo incident #102) needs a bus, or a track-related incident.
- **Synthetic geography is approximate.** The tram 17 route and the complaint coordinates are estimates. If they are more than 20 m from the real OSM tracks, map matching will drop points.

## Next steps (in order)

1. Create the Supabase project, set `DATABASE_URL`, run `scripts/init_db.py`, and fix any SQL errors.
2. `pip install -r backend/requirements-ml.txt`, then `scripts/load_osm.py --bbox demo`.
3. Check that the synthetic ride (`ROUTES` in `scripts/synth_ride.py`) lies on the loaded tram segments; adjust and regenerate if not.
4. Start the API, run `scripts/seed_demo.py`, open the frontend with `npm run dev`, and rehearse the demo with `scripts/replay_ride.py --incident <id>`.
5. Add the keys (`ANTHROPIC_API_KEY`, `WARSAW_API_KEY`) and test the live paths once.
6. Record real tram rides with Sensor Logger (at least one at night), mark ground-truth potholes, and re-tune `MIN_PEAK_MS2`, `SEVERITY_REF_MS2` and the lux thresholds.
7. Optional: put ZTM GTFS in `data/gtfs/`. This stops the verification loop from picking a tram on a crossing street. At Marszałkowska × Jerozolimskie the sample snapshot currently picks tram 9 instead of 17.

## Tuning notes

| Setting | Value | Where |
|---|---|---|
| Bump minimum peak | 3.0 m/s² | `detect.MIN_PEAK_MS2` |
| Severity reference | 10.0 m/s² | `detect.SEVERITY_REF_MS2` |
| Peak merge distance | 15 m | `detect.py` |
| Dedup threshold, hashing fallback | 0.20 | `dedup.py` |
| Dedup threshold, multilingual-e5 | 0.80 | `dedup.py` |
| Fusion match radius / window | 40 m / 7 days | `incidents.py` |
| "Found before report" | ≥ 2 rides | `incidents.py` |
| Vulnerability weights (within 100 m) | school 0.35, hospital 0.35, platform 0.20, cycleway 0.15 | `load_osm.py` |
| Score | (0.35·severity + 0.25·log(1+n)/log 51 + 0.20·urgency/5 + 0.20·vulnerability) × 1.5 when both sources agree | `score.py` |
| Default Claude model | `claude-opus-5-5` | override with `ANTHROPIC_MODEL` |
| Confidence prior | 0.25 | `confidence.PRIOR` |
| Points per detecting ride / per clean pass | +1.2 × (0.5 + 0.5·severity) / −0.8 | `confidence.py` |
| Points per citizen answer, cap | ±0.6 × 2·trust, capped at ±2.5 | `confidence.py` |
| Likely / verified / dismissed | ≥ 60 % / ≥ 85 % / < 10 % | `confidence.py` (mirrored in `frontend/lib/confidence.ts`) |
| Trust | Beta(3, 2): newcomers 0.6 | `trust.py` |
