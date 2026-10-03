# CityEcho — Architecture & Module Contracts

This file is the **single source of truth** for how the modules fit together.
Every module codes against the signatures below. If you own a module, implement
exactly these names and shapes; if you consume one, call only these names.

Source spec: `CityEcho_vs.md` (Turkish roadmap). Target: a demoable hackathon
system for Warsaw, built around four core parts — **sensor pipeline + text
triage + fusion + map**. Everything else is optional polish.

## 1. Big picture

```
 phone / ESP32 ─► sensor pipeline ─┐                        ┌─► /segments  (health map)
   (CSV / PWA)    ingest→detect→    │                        │
                  mapmatch→evidence ├─► evidence ─► FUSION ──┼─► /incidents (queue, detail)
 citizen form ──► triage pipeline ──┘   (PostGIS)  incidents │
 19115 / synth    structure→geocode→                score    ├─► /stats
                  embed→dedup→evidence              routing  │
                                                    verify ◄─┴── ZTM live vehicles
                                                      │
                     "next tram through segment" ─────┘ (verification loop)
```

* **Evidence** is the common currency: a sensor peak and a citizen complaint are
  the same kind of row, anchored to a point (+ nearest segment).
* **Fusion** clusters evidence into **incidents** (location + time), scores their
  priority, routes them to a department, flags *found-before-report* (sensor-only,
  ≥ 2 rides) and asks the **verification loop** to check report-only incidents with
  the next vehicle.
* The **confidence engine** combines *sensor confidence* (detecting rides minus
  clean passes) with *citizen confidence* (YES/NO answers weighted by each
  contributor's trust) into one confidence that sets the status:
  **candidate → likely → verified** (or **dismissed**).
* **Contributor trust** is the feedback loop: when an incident resolves, everyone
  who answered is scored right/wrong and their trust, and so the weight of their
  future answers, is updated.

```
 Vehicle sensors ─► Sensor event ─┐
                                  ├─► Incident clustering (location + time) ─► Incident
 Citizen YES/NO (reports + answers)┘                                            │
        ▲                                     ┌──────────────┬────────────────────┘
        │                             Sensor confidence   Citizen confidence (× trust)
        │                                     └──────► Confidence engine ◄──────┘
        │                                                     │
        │                         Status: candidate · likely · verified (· dismissed)
        │                                     ┌───────────────┴───────────────┐
        └── affects future answer weight ── Contributor trust update   Municipal dashboard
```
* Pipelines never call fusion. The **API layer orchestrates**:
  `pipeline → fusion.ingest_evidence → (verify)`.

## 2. Repository layout and ownership

```
.env.example  .gitignore  pytest.ini  README.md          (foundation)
db/schema.sql                                             (foundation)
db/functions.sql                                          (DB agent)
backend/config.py  backend/models.py                      (foundation — read only)
backend/db.py                                             (DB agent)
backend/sensor/ingest.py detect.py track_score.py         (sensor-signal agent)
backend/sensor/lights.py mapmatch.py pipeline.py          (sensor-geo agent)
backend/triage/structure.py vision.py                     (triage-LLM agent)
backend/triage/geocode.py dedup.py pipeline.py            (triage-geo agent)
backend/fusion/incidents.py score.py routing.py verify.py (fusion agent)
backend/main.py backend/api/*.py                          (API agent)
frontend/**                                               (frontend agent)
scripts/load_osm.py                                       (DB agent)
scripts/synth_ride.py                                     (sensor-signal agent)
scripts/gen_complaints.py                                 (triage-LLM agent)
scripts/eval_triage.py                                    (triage-geo agent)
scripts/replay_ride.py scripts/seed_demo.py               (API agent)
backend/tests/test_<module>.py                            (owner of <module>)
data/cache/  data/demo/  data/rides/  data/osm/           (runtime data)
```

Rules for every module:
* Python 3.11, `from __future__ import annotations`, type hints, short docstrings.
* Import shared things from `backend.config` (`settings`) and `backend.models`.
* Heavy/optional deps (`sentence_transformers`, `osmnx`, `geopandas`) are imported
  **lazily inside functions** with a working fallback or a clear error.
* Network/LLM calls must degrade gracefully (no key / offline → fallback, never crash the API).
* DB functions take an open `conn` (psycopg 3 connection, `dict_row`) as the first
  argument and **do not commit** — the caller's `get_conn()` block commits.
* Coordinates: always `(lon, lat)` order in function arguments, WGS84 / SRID 4326.
* Timestamps: timezone-aware UTC `datetime`.
* Tests: pytest in `backend/tests/`, run with `.venv/bin/pytest`. No PostGIS is
  available locally, so DB code is tested with fakes/monkeypatching; tests that
  need a real DB must `pytest.skip` unless `CITYECHO_TEST_DB=1`.

## 3. Shared vocabulary (`backend/models.py`)

| Enum | Values (stored verbatim in DB) |
|---|---|
| `IssueType` | `road_damage`, `tram_track`, `streetlight`, `flooding`, `waste`, `other` |
| `Source` | `sensor`, `report` |
| `Mode` | `road`, `tram` |
| `Department` | `ZDM`, `Tramwaje Warszawskie`, `MPWiK`, `Straż Miejska`, `inne` |
| `IncidentStatus` | `candidate`, `likely`, `verified`, `dismissed`, `closed` (confidence-driven; verified/dismissed/closed are terminal) |

`EvidenceIn` dataclass: `source, type, lon, lat, severity(0–1), ts, segment_id?, ride_id?, report_id?, details{}`.
`TriageResult` pydantic model: `category, location_text, urgency(1–5), hazard_to_people, department, summary_en, summary_tr, needs_clarification`.

### `evidence.details` (jsonb) shapes

* sensor bump: `{"kind": "bump", "speed_kmh": float, "raw_peak": float, "signal": [float, ...], "signal_fs": int, "peak_index": int}`
  — `signal` is the high-passed magnitude ±1 s around the peak, downsampled to ≤ 200 points.
* sensor dark gap: `{"kind": "dark_gap", "expected_lux": float, "observed_lux": float}`
* report: `{"kind": "report", "urgency": int, "summary_en": str, "hazard_to_people": bool, "location_confidence": float, "location_text": str|null}`

## 4. Database (`db/schema.sql`, `db/functions.sql`)

Tables: `segments, rides, ride_segments, contributors, reports, evidence, incidents, incident_evidence, citizen_responses`
(`contributors` = anonymous hashed browser tokens with `correct/incorrect/trust`; `citizen_responses` = one
YES/NO per contributor per incident, plus one implicit YES per located report)
(see schema.sql for every column). `db/functions.sql` (DB agent) adds:

* `nearest_segment(lon float8, lat float8, p_mode text default null, max_dist_m float8 default 20) returns bigint`
* `recompute_segment_health() returns void` (plpgsql) — for each segment with `ride_segments`
  rows: `health = 1 - clamp(median(rms of the 5 newest passes) / p99(median rms over all segments), 0, 1)`,
  `health_rides = count(distinct ride_id)`, `health_updated_at`, `health_weight` (see §8.3).

## 5. Python module contracts

### 5.1 `backend/db.py` (DB agent)
```python
def get_conn() -> ContextManager[psycopg.Connection]   # dict_row; commit on success, rollback on error
def nearest_segment(conn, lon: float, lat: float, mode: str | None = None, max_dist_m: float = 20) -> int | None
def nearest_segments(conn, coords: list[tuple[float, float]], mode: str | None = None, max_dist_m: float = 20) -> list[int | None]  # one batched query (unnest + lateral)
def insert_ride(conn, *, vehicle_line: str | None, mode: str, started_at: datetime | None, ended_at: datetime | None = None, device_hash: str | None = None, source_file: str | None = None) -> int
def insert_report(conn, *, raw_text: str, structured: dict, lon: float | None, lat: float | None, location_confidence: float | None, embedding: list[float] | None, duplicate_of: int | None = None, photo_url: str | None = None, source: str = "web", created_at: datetime | None = None) -> int
    # also fills reports.category / urgency / department from `structured`
def insert_evidence(conn, ev: EvidenceIn) -> int
def upsert_ride_segments(conn, ride_id: int, rows: list[dict]) -> None   # dict keys: segment_id, rms, samples, passed_at
def recompute_segment_health(conn) -> None                               # select recompute_segment_health()
def fetch_one(conn, sql: str, params: dict | tuple | None = None) -> dict | None
def fetch_all(conn, sql: str, params: dict | tuple | None = None) -> list[dict]
```

### 5.2 Sensor signal — `backend/sensor/ingest.py`, `detect.py`, `track_score.py`
```python
# ingest.py
SAMPLE_COLUMNS = ["t", "ts", "ax", "ay", "az", "lat", "lon", "speed_kmh", "lux"]
def load_sensor_logger(path: str | Path) -> pd.DataFrame
    # Accepts: Sensor Logger export folder or .zip (Accelerometer.csv/TotalAcceleration.csv,
    # Location.csv, Light.csv) OR a single combined CSV with the SAMPLE_COLUMNS.
    # Returns one row per accelerometer sample with GPS (lat/lon/speed_kmh) interpolated
    # onto it; t = seconds since start (float), ts = tz-aware UTC datetime, accel in m/s²,
    # lux NaN when absent. Sorted by t.
def from_samples(samples: list[dict]) -> pd.DataFrame        # PWA stream chunks -> same columns
def estimate_fs(df: pd.DataFrame) -> int                      # sampling rate in Hz

# detect.py
def highpass(df: pd.DataFrame, fs: int | None = None, cutoff_hz: float = 1.5) -> np.ndarray
    # |a| minus median (gravity), 4th-order Butterworth high-pass, filtfilt
def detect_bumps(df: pd.DataFrame, fs: int | None = None) -> pd.DataFrame
    # columns: t, ts, lat, lon, speed_kmh, raw_peak, severity (0–1), signal (list[float]),
    # signal_fs (int), peak_index (int). Drops speed < 5 km/h, speed-normalizes severity.

# track_score.py
def segment_rms(hp: np.ndarray, seg_ids: Sequence[int | None]) -> pd.Series     # index segment_id -> rms
def segment_pass_stats(df: pd.DataFrame, hp: np.ndarray, seg_ids) -> list[dict] # rows for db.upsert_ride_segments
def health_from_rms(rms_all: pd.DataFrame) -> pd.DataFrame   # columns: health (0–1), confidence (#rides)
```
Plus `scripts/synth_ride.py`: generates a realistic combined CSV (100 Hz accel +
GPS along a real Warsaw tram line, injected bumps at known coords, optional night
lux saw-tooth with missing peaks) into `data/demo/` with a matching
`*_truth.csv` of injected anomalies. Used for tests and the offline demo.

### 5.3 Sensor geo — `backend/sensor/lights.py`, `mapmatch.py`, `pipeline.py`
```python
# lights.py
def find_dark_gaps(df: pd.DataFrame, min_spacing_m: float = 20, max_spacing_m: float = 60) -> pd.DataFrame
    # columns: lon, lat, ts, expected_lux, observed_lux, severity (0–1). Empty if no lux / daytime.

# mapmatch.py
def match_points(conn, lons, lats, mode: str | None, max_dist_m: float = 20) -> np.ndarray
    # segment id per point (object array, None when unmatched). Dedupes coords rounded to
    # 1e-5 deg and uses db.nearest_segments in one batched query.

# pipeline.py
def process_ride(conn, df: pd.DataFrame, *, vehicle_line: str | None, mode: str,
                 device_hash: str | None = None, source_file: str | None = None) -> dict
    # insert ride -> highpass -> mapmatch -> ride_segments (track_score.segment_pass_stats)
    # -> detect_bumps -> evidence (tram mode => tram_track, road => road_damage)
    # -> find_dark_gaps -> evidence (streetlight) -> db.recompute_segment_health
    # returns {"ride_id", "evidence_ids", "bumps", "dark_gaps", "segments_covered"}
```

### 5.4 Triage LLM — `backend/triage/structure.py`, `vision.py`
```python
# structure.py
def structure(text: str) -> TriageResult
    # Claude API, temperature 0, strict JSON (validate with TriageResult); retry once.
    # No API key / failure -> keyword heuristic fallback (Polish + English keywords),
    # never raises. Department follows routing rules in §5.6.
def summarize_reports(texts: list[str]) -> str     # 1–2 sentence English summary; fallback: first text truncated

# vision.py
def anonymize(image_bytes: bytes) -> bytes          # strip EXIF (Pillow), blur faces + plates (OpenCV Haar), JPEG out
def check_photo(image_bytes: bytes, claimed: IssueType | None = None) -> dict
    # {"category": IssueType, "severity": float 0–1, "matches_claim": bool | None, "notes": str}
    # Claude vision; fallback {"category": claimed or "other", "severity": 0.5, "matches_claim": None, "notes": "vision unavailable"}
```
Plus `scripts/gen_complaints.py` → `data/complaints_synth.json`: list of
`{"text", "created_at", "true_issue_id", "true_category", "lon", "lat", "street"}`
(300–500 Polish complaints, 40 real Warsaw issue spots, 1–40 reports each, 20 % vague
locations). Uses Claude when a key exists, otherwise a deterministic template generator.

### 5.5 Triage geo + dedup — `backend/triage/geocode.py`, `dedup.py`, `pipeline.py`
```python
# geocode.py
WARSAW_VIEWBOX = "20.85,52.37,21.27,52.10"
def geocode(location_text: str) -> tuple[float, float, float] | None   # (lon, lat, confidence 0–1)
    # Nominatim bounded to Warsaw, JSON file cache in data/cache/geocode.json,
    # ≤ 1 req/s, User-Agent from settings; offline -> cache only.

# dedup.py
def embed(texts: list[str]) -> np.ndarray      # L2-normalized; multilingual-e5 ("query: " prefix) or hashing fallback
def same_incident(a: dict, b: dict) -> bool    # same category, < 50 m, < 72 h, cosine > threshold
def find_duplicate(conn, *, category: str, lon: float, lat: float, created_at: datetime, embedding: np.ndarray) -> int | None
    # candidate reports within 50 m / 72 h / same category from DB, best cosine above threshold,
    # returns the canonical id (candidate.duplicate_of or candidate.id)
def greedy_cluster(records: list[dict]) -> list[int]   # offline clustering for evaluation

# pipeline.py
def process_report(conn, text: str, *, pin: tuple[float, float] | None = None,
                   photo_bytes: bytes | None = None, created_at: datetime | None = None,
                   source: str = "web", structured: TriageResult | None = None) -> dict
    # structure -> (vision.anonymize + check_photo) -> geocode (fallback to pin) -> embed
    # -> find_duplicate -> db.insert_report -> nearest segment (tram_track => 'tram', else 'road', 60 m)
    # -> db.insert_evidence(source=report) if located
    # returns {"report_id", "evidence_id" (None if no location), "structured" (dict),
    #          "duplicate_of", "lon", "lat", "photo_url"}
```
Photos: anonymized JPEG saved to `data/cache/photos/<uuid>.jpg`; `photo_url` = `/photos/<uuid>.jpg`.
Plus `scripts/eval_triage.py`: category accuracy, routing accuracy, dedup purity/ARI vs `true_issue_id`.

### 5.6 Fusion — `backend/fusion/incidents.py`, `confidence.py`, `trust.py`, `score.py`, `routing.py`, `verify.py`
```python
# routing.py
def department_for(issue_type: str) -> str
    # road_damage, streetlight -> ZDM; tram_track -> Tramwaje Warszawskie;
    # flooding -> MPWiK; waste -> Straż Miejska; other -> inne

# score.py
def priority_score(*, sensor_severity: float, report_count: int, max_urgency: int,
                   vulnerability: float, both_sources: bool) -> float
    # (0.35*sev + 0.25*log(1+n)/log(51) + 0.20*urg/5 + 0.20*vuln) * (1.5 if both_sources)

# incidents.py
MATCH_RADIUS_M = 40; MATCH_WINDOW_DAYS = 7; PROACTIVE_MIN_RIDES = 2
def ingest_evidence(conn, evidence_ids: list[int]) -> list[int]
    # for each evidence: report evidence whose report has duplicate_of -> join that report's incident;
    # else nearest open incident of same type within 40 m seen in last 7 days; else new incident.
    # Link incident_evidence, then refresh_incident. Returns touched incident ids (unique, ordered).
    # A located report also becomes its author's YES (trust.record_report_yes).
def refresh_incident(conn, incident_id: int) -> dict
    # recompute counts, max severity/urgency, sensor_confirmed, found_before_report
    # (sensor evidence from >= 2 distinct rides and no report evidence older than the 2nd ride),
    # confidence.assess(per-ride severities, sensor_misses, trust-weighted votes) -> confidence,
    # sensor/citizen confidence, status (sets verified_at); reaching verified/dismissed -> trust.settle.
    # department, address (segment name or report location_text), score. Returns the incident row.

# confidence.py (pure)
PRIOR = 0.25; SENSOR_HIT = 1.2; SENSOR_MISS = 0.8; CITIZEN_VOTE = 0.6; CITIZEN_CAP = 2.5
LIKELY_AT = 0.60; VERIFIED_AT = 0.85; DISMISSED_BELOW = 0.10
def assess(ride_severities, misses, votes: [(answer, trust)]) -> Assessment
    # confidence = σ(logit(PRIOR) + Σ hits·(0.5+0.5·sev) − misses·0.8 + clamp(Σ ±0.6·2·trust, ±2.5))
def status_for(confidence, current) -> str      # terminal statuses are sticky

# trust.py
DEFAULT_TRUST = 0.6                              # Beta(3, 2) prior; trust = (correct+3)/(correct+incorrect+5)
def contributor_for(conn, token) -> dict | None  # salted SHA-256 of the browser token, created on first use
def record_vote(conn, incident_id, contributor_id, answer, *, resolved=False)
def record_report_yes(conn, incident_id, report_id)
def votes_for(conn, incident_id) -> [(answer, trust)]
def settle(conn, incident_id, real: bool) -> [contributor_id]   # score unsettled answers, update trust

# verify.py
def live_vehicles(kind: str = "tram") -> list[dict]
    # [{"id", "line", "lon", "lat", "ts", "kind"}]; ZTM busestrams_get (type 1=bus, 2=tram),
    # 30 s in-memory cache; DEMO_MODE / no key / error -> data/demo/ztm_snapshot.json
def next_vehicle_for(lon: float, lat: float, mode: str) -> dict | None
    # {"vehicle": "tram 17", "line": "17", "eta_min": int, "distance_m": float}
def request_verification(conn, incident_id: int) -> dict | None
    # only for candidate/likely incidents without sensor evidence; sets
    # verify_vehicle, verify_eta_min, verify_requested_at (status stays confidence-driven)
def check_ride_verifications(conn, ride_id: int) -> list[int]
    # for candidate/likely/verified incidents this ride passed (segment or within 40 m):
    # detected -> hit (re-assess); a capable vehicle (bus for road_damage, tram for tram_track)
    # that felt nothing -> sensor_misses += 1 (re-assess, confidence drops).
    # Returns the ids this ride detected that are now verified.
```

### 5.7 API — `backend/main.py`, `backend/api/*.py`
FastAPI app `backend.main:app`, CORS from `settings.cors_origins`, static
`/photos` from `data/cache/photos`. Routers: `rides, reports, segments, incidents, responses, stats, vehicles` + Day 0 `auth, users, mobile, admin, devices` (§8).
Orchestration:
* `/rides/upload`, `/rides/stream` (final chunk): `process_ride → ingest_evidence → check_ride_verifications`
* `/reports`: `process_report → ingest_evidence →` if incident has no sensor evidence, is candidate/likely and has no pending request → `request_verification`
* `/incidents/{id}/responses`: `trust.contributor_for → record_vote → refresh_incident`
* `/reports/bulk`: same without verification requests (fast import)

## 6. HTTP API (JSON shapes — the frontend codes against these)

```
GET  /health -> {"ok": true}

GET  /segments?bbox=minLon,minLat,maxLon,maxLat&mode=tram|road&measured_only=true
  -> {"segments": [{"id": 1, "mode": "tram", "health": 0.82 | null, "rides": 3,
                    "path": [[21.01, 52.23], [21.0103, 52.2302]]}]}

GET  /incidents?department=ZDM&status=candidate,likely&limit=200
  -> {"incidents": [IncidentSummary]}            # sorted by score desc
IncidentSummary = {
  "id", "type", "status", "score", "department", "lon", "lat", "address",
  "report_count", "sensor_count", "sensor_rides", "sensor_confirmed", "found_before_report",
  "has_sensor", "has_report", "max_severity", "max_urgency",
  "first_seen", "last_seen", "verify_vehicle", "verify_eta_min",
  "confidence",            # 0–1, confidence engine
  "sensor_confidence" | null, "citizen_confidence" | null,   # null = no data from that source yet
  "yes_count", "no_count", "sensor_misses",
  "awaiting_verification"  # a vehicle was asked and has not passed yet
}

GET  /incidents/{id}
  -> IncidentSummary + {
       "summary": str | null,
       "reports":  [{"id", "raw_text", "summary_en", "urgency", "created_at", "photo_url"}],
       "evidence": [{"id", "source", "type", "severity", "ts", "ride_id", "report_id", "details"}],
       "timeline": [{"ts", "kind", "label"}],
         # kind ∈ first_report | report | sensor | proactive | verification_requested
         #        | sensor_miss | response | verified | dismissed
       "signal": {"fs": int, "values": [float], "peak_index": int} | null   # strongest sensor bump
     }

POST /incidents/{id}/verify -> {"incident_id", "status", "vehicle", "eta_min"}

POST /incidents/{id}/responses  {"answer": "yes" | "no", "contributor": "<browser token, 8–200 chars>"}
  -> {"incident_id", "status", "confidence", "sensor_confidence", "citizen_confidence",
      "yes_count", "no_count", "contributor_trust"}        # 404 unknown, 409 dismissed/closed

POST /reports   (multipart/form-data: text (req), lon?, lat?, photo? file, contributor? token)
  -> ReportStatus
GET  /reports/{id}/status -> ReportStatus
ReportStatus = {
  "report_id", "incident_id" | null, "status" | null, "category", "department",
  "others_count",          # other reports merged into the same incident
  "sensor_confirmed", "verify_vehicle", "verify_eta_min",
  "confidence" | null, "contributor_trust" | null,
  "message"                # e.g. "23 others reported this. Tram 17 will verify in ~6 min.
                           #       Status: likely (80% confidence). Sent to ZDM."
}
POST /reports/bulk  {"reports": [{"text", "created_at"?, "lon"?, "lat"?, "source"?}]}
  -> {"processed": int, "report_ids": [int], "incident_ids": [int]}

POST /rides/upload  (multipart: file (CSV or Sensor Logger .zip), vehicle_line, mode=tram|road)
  -> {"ride_id", "bumps", "dark_gaps", "segments_covered", "evidence_ids", "incident_ids", "verified_incident_ids"}
POST /rides/stream  {"session_id", "vehicle_line", "mode", "samples": [{"t","ax","ay","az","lat","lon","speed_kmh","lux"?}], "final": bool}
  -> {"session_id", "buffered": int} | (final) same as /rides/upload

GET  /stats
  -> {"reports_total", "incidents_total", "found_before_report", "candidate_total", "likely_total",
      "verified_total", "awaiting_verification", "contributors_total",
      "avg_verification_min" | null, "rides_total", "segments_measured"}

GET  /vehicles/live?kind=tram|bus -> {"vehicles": [{"id", "line", "lon", "lat", "ts", "kind"}]}
```
Timestamps are ISO-8601 strings. Scores are floats (≈ 0–1.5).

## 7. Frontend (`frontend/`)

Next.js (App Router, TypeScript, Tailwind) + MapLibre GL + deck.gl + recharts.
`NEXT_PUBLIC_API_URL` (default `http://localhost:8000`); `NEXT_PUBLIC_USE_MOCK=1`
serves fixtures from `lib/mock.ts` (shapes identical to §6) so the UI works with no backend.

* `/` — city health map: `PathLayer` segments green→red by health, `ScatterplotLayer`
  incidents (size = score, colour: blue = report only, green = sensor only, orange = both),
  live ZTM vehicles, layer toggles, stats bar on top.
* `/incidents` — queue sorted by score, department + status (candidate/likely/verified/dismissed/closed) filters,
  status chip with confidence %, badges (found before report, verified by, vehicle verifying, clean passes).
* `/incidents/[id]` — confidence breakdown (sensor → citizen → engine → status), "Is this problem still there?"
  YES/NO (`/incidents/{id}/responses`, anonymous token from `lib/contributor.ts`), merged reports + summary,
  photo, sensor signal chart (recharts, peak marked), evidence timeline. `lib/confidence.ts` mirrors the engine.
* `/report` — mobile citizen form (text, photo, location pin / geolocation) → status message.
* `/ride` — PWA-style recorder: DeviceMotion + Geolocation → `/rides/stream` chunks.

## 8. Day 0 contracts

Frozen on Day 0 so A (mobile), B (web admin) and C (sensor simulation) never need to touch
shared files. Changing anything here = announce in the group + separate SHARED commit.

### 8.1 Auth and roles (`backend/auth/`, owner A)

```
client (Expo / web admin) ── Google Sign-In ──► Google ID token
        POST /auth/google {id_token, contributor?} ──► verify (google-auth, aud ∈ GOOGLE_CLIENT_IDS)
        ──► upsert users row (role from ADMIN_EMAILS) ──► link contributor (trust carry-over)
        ◄── {token, user}        then every call:  Authorization: Bearer <token>
```

* **Token:** HS256 JWT signed with `AUTH_SECRET`, valid `AUTH_TOKEN_DAYS` (30). Claims `sub` (user id),
  `email`, `name`, `role`, `iat`, `exp`, `iss="cityecho"`. Stateless: no DB lookup per request.
* **Roles** (`backend.models.Role`): `citizen` | `admin`. `admin` iff the email is in `ADMIN_EMAILS`
  (re-derived at every login; `require_admin` also re-checks the list, so removal is instant).
* **Trust carry-over:** `contributor` is the anonymous device token the app already sends to
  `/reports` and `/incidents/{id}/responses`. At login, if the user has no contributor yet, that
  token's contributor (`trust.contributor_for`) is linked (`users.contributor_id`, unique) so earned trust stays.
* **Dependencies** (`from backend.auth import ...`):
  `current_user` / `CurrentUser` → `{id, email, name, role}` or **401**;
  `optional_user` / `OptionalUser` → user or `None` (missing *or* invalid token);
  `require_admin` / `AdminUser` → admin or **403** (401 without token).
  `/admin/*` has `require_admin` on the whole router: every B endpoint there is admin-only.
* Settings (`.env`): `GOOGLE_CLIENT_IDS` (comma list: web, iOS, Android), `AUTH_SECRET`,
  `AUTH_TOKEN_DAYS`, `ADMIN_EMAILS` (comma list), `AUTH_DEV_LOGIN` (0/1), `DEVICE_KEYS` (comma list of `device_id:secret`).

### 8.2 New endpoints

```
User = {"id": int, "email": str, "name": str | null, "role": "citizen" | "admin"}

POST /auth/google  {"id_token": str, "contributor"?: str (8–200 chars)}
  -> {"token": str, "user": User}      # 401 bad/unverified token, 503 GOOGLE_CLIENT_IDS empty
POST /auth/dev     {"email": str, "contributor"?: str}
  -> {"token": str, "user": User}      # only with AUTH_DEV_LOGIN=1, else 404. Local testing only.
GET  /users/me     (Bearer) -> User    # fresh from the DB; 401 without token or deleted account
GET  /mobile/ping  -> {"ok": true}                      # A's router; more mobile routes go here
GET  /admin/ping   (Bearer, admin) -> {"ok": true, "user": User}   # B's router
POST /devices/stream  (X-Device-Key) -> buffered ride per device, 401 without a valid key (8.5)
POST /incidents/{id}/responses       # unchanged (§6), moved to backend/api/responses.py (owner A)
```

### 8.3 Database (`db/migrations/`)

`scripts/init_db.py` applies `schema.sql`, `functions.sql`, then each `db/migrations/NNN_name.sql`
**once**, in numeric order, recording it in `schema_migrations(filename, applied_at)`. `--reset` also
drops migration tables. Numbering: **A = 100–199, B = 200–299, C = 300–399**; never edit a pushed
migration, add a new one (see `db/migrations/README.md`). Day 0 migrations:

| File | Adds |
|---|---|
| `100_users.sql` | `users(id, google_sub unique, email unique, name, role default 'citizen', contributor_id unique → contributors, created_at)` |
| `200_work_status.sql` | `incidents.work_status text not null default 'todo'` check `todo`/`in_progress`/`done`, `work_status_changed_at`, `work_status_by → users` |
| `300_devices.sql` | `devices(id text pk, key_hash, vehicle_line, mode road/tram, last_seen_at, created_at)`, `segments.health_updated_at` |
| `301_segment_health_weight.sql` (S3) | `segments.health_weight real not null default 0` |

* **`work_status`** (`backend.models.WorkStatus`): `todo` → `in_progress` → `done`. Written **only by B**
  (web admin workflow, sets `work_status_changed_at` / `work_status_by`; on `done` B calls
  `trust.settle(conn, id, real=True)`). Independent of the confidence `status`. A reads it: no
  "is it still there?" question when `done`.
* **`segments.health`, `health_rides`, `health_updated_at`, `health_weight`**: written **only by C** (sensor pipeline /
  `recompute_segment_health`). A and B only read them. `health` = median vibration of the 5 newest passes
  (so repairs show after ~3 clean passes); `health_updated_at` = newest measurement (freshness);
  `health_weight` = sum of 0.5^(age / 7 days) per pass (1.0 ≈ one fresh ride, 0 = never measured / stale).

### 8.4 Public (citizen) incident view, for A

The mobile app never shows sensor data, evidence, timeline or facts (those are admin-only, §6 detail).
A's `backend/api/mobile.py` returns at most:

```
PublicIncident = {
  "id", "type", "lon", "lat", "address", "department",
  "status",          # candidate | likely | verified | dismissed | closed (confidence label)
  "confidence",      # 0–1
  "work_status",     # todo | in_progress | done (city's work)
  "report_count", "first_seen", "last_seen"
}
```
No `signal`, `evidence`, `timeline`, `reports` (raw texts), `sensor_*`, `verify_*` or per-contributor data.
Road health is shown only as a colour class derived from `segments.health`.

### 8.5 `/devices/stream` (owner C; the simulator talks to it like a real device)

```
POST /devices/stream
  X-Device-Key: <device_id>:<secret>      # pair from DEVICE_KEYS (settings.device_keys); 401 otherwise
  {"vehicle_line": "17", "mode": "road" | "tram",
   "samples": [{"t", "ax", "ay", "az", "lat", "lon", "speed_kmh", "lux"?}],   # same fields as /rides/stream
   "final"?: bool}                        # default false; true = ride ends, process it
  -> {"device_id", "buffered": int} | (final) same as /rides/upload
```
One open ride per device (buffered like `/rides/stream`); the final chunk runs
`process_ride → ingest_evidence → check_ride_verifications`. `devices.key_hash` stores a hash, never the secret.
