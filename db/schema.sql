-- CityEcho database schema (PostgreSQL + PostGIS, e.g. Supabase).
-- Run once on a fresh database, then db/functions.sql.
-- Everything is anchored to a road/tram segment; sensor peaks and citizen
-- reports both become rows in `evidence`, which the fusion engine clusters
-- into `incidents`.

create extension if not exists postgis;

-- 25 m pieces of the OSM road and tram network.
create table if not exists segments (
  id            bigserial primary key,
  geom          geometry(LineString, 4326) not null,
  mode          text not null check (mode in ('road', 'tram')),
  osm_way_id    bigint,
  name          text,                         -- street name from OSM, used as incident address
  length_m      real,
  vulnerability real not null default 0,      -- 0–1: school/hospital/stop/cycleway within 100 m
  health        real,                         -- 0 = bad .. 1 = healthy; null = never measured
  health_rides  int  not null default 0       -- how many rides contributed to `health`
);
create index if not exists segments_geom_gix on segments using gist (geom);
create index if not exists segments_mode_idx on segments (mode);

-- One recorded trip of one vehicle (phone or ESP32 kit).
create table if not exists rides (
  id            bigserial primary key,
  vehicle_line  text,                         -- e.g. '17'
  mode          text check (mode in ('road', 'tram')),
  started_at    timestamptz,
  ended_at      timestamptz,
  device_hash   text,                         -- hashed device id, never a personal identifier
  source_file   text,
  created_at    timestamptz not null default now()
);

-- Per-ride vibration RMS for every segment the ride covered.
-- Feeds segment health (median over rides) and tells the verification loop
-- which segments a ride actually passed.
create table if not exists ride_segments (
  ride_id     bigint not null references rides(id) on delete cascade,
  segment_id  bigint not null references segments(id) on delete cascade,
  rms         real   not null,
  samples     int,
  passed_at   timestamptz,
  primary key (ride_id, segment_id)
);
create index if not exists ride_segments_segment_idx on ride_segments (segment_id);

-- Anonymous citizens who report or answer YES/NO, with their earned trust.
-- Identity is a salted hash of a random browser token: never a name, email or phone.
create table if not exists contributors (
  id                bigserial primary key,
  contributor_hash  text not null unique,
  correct           int  not null default 0,          -- answers that matched the final outcome
  incorrect         int  not null default 0,
  trust             real not null default 0.6,        -- (correct + 3) / (correct + incorrect + 5)
  created_at        timestamptz not null default now()
);

-- Citizen complaints (web form, 19115 import, synthetic data).
create table if not exists reports (
  id                  bigserial primary key,
  contributor_id      bigint references contributors(id),  -- null for 19115 / synthetic imports
  raw_text            text not null,
  photo_url           text,                   -- anonymized photo only (EXIF stripped, faces/plates blurred)
  structured          jsonb,                  -- full LLM triage output (TriageResult)
  category            text,                   -- denormalized from structured.category
  urgency             int,
  department          text,
  embedding           real[],                 -- normalized text embedding (dimension depends on model)
  geom                geometry(Point, 4326),  -- null when location could not be resolved
  location_confidence real,
  duplicate_of        bigint references reports(id),  -- canonical report this one duplicates
  source              text not null default 'web' check (source in ('web', '19115', 'synthetic')),
  created_at          timestamptz not null default now()
);
create index if not exists reports_geom_gix on reports using gist (geom);
create index if not exists reports_created_idx on reports (created_at);

-- The common currency: one row per sensor anomaly or per located report.
create table if not exists evidence (
  id          bigserial primary key,
  segment_id  bigint references segments(id),
  source      text not null check (source in ('sensor', 'report')),
  type        text not null,                  -- IssueType: road_damage, tram_track, streetlight, flooding, waste, other
  severity    real not null default 0,        -- 0–1
  ts          timestamptz not null,
  ride_id     bigint references rides(id) on delete cascade,
  report_id   bigint references reports(id) on delete cascade,
  geom        geometry(Point, 4326) not null,
  details     jsonb not null default '{}'::jsonb,  -- see docs/ARCHITECTURE.md "evidence.details"
  created_at  timestamptz not null default now(),
  check ((source = 'sensor' and ride_id is not null) or (source = 'report' and report_id is not null))
);
create index if not exists evidence_geom_gix on evidence using gist (geom);
create index if not exists evidence_segment_idx on evidence (segment_id);
create index if not exists evidence_ride_idx on evidence (ride_id);
create index if not exists evidence_report_idx on evidence (report_id);

-- A real-world problem backed by one or more pieces of evidence.
create table if not exists incidents (
  id                   bigserial primary key,
  segment_id           bigint references segments(id),
  type                 text not null,
  geom                 geometry(Point, 4326) not null,   -- location of the first evidence
  address              text,
  summary              text,                             -- LLM summary of merged reports (cached)
  score                real not null default 0,             -- priority (urgency, vulnerability, ...)
  status               text not null default 'candidate'    -- driven by `confidence`, see fusion/confidence.py
                       check (status in ('candidate', 'likely', 'verified', 'dismissed', 'closed')),
  confidence           real not null default 0,             -- 0–1, sensor + trust-weighted citizen evidence
  sensor_confidence    real,                                -- null = no sensor data yet
  citizen_confidence   real,                                -- null = no citizen responses yet
  yes_count            int  not null default 0,             -- citizen YES (reports + explicit answers)
  no_count             int  not null default 0,             -- citizen NO answers
  department           text,
  first_seen           timestamptz not null,
  last_seen            timestamptz not null,
  sensor_confirmed     boolean not null default false,   -- at least one sensor evidence attached
  found_before_report  boolean not null default false,   -- sensors found it (>= 2 rides) before any citizen report
  report_count         int  not null default 0,
  sensor_count         int  not null default 0,
  sensor_rides         int  not null default 0,          -- distinct rides that detected it
  max_severity         real not null default 0,
  max_urgency          int  not null default 0,
  verify_vehicle       text,                             -- e.g. 'tram 17'
  verify_eta_min       int,
  verify_requested_at  timestamptz,
  verified_at          timestamptz,                      -- when status became 'verified'
  sensor_misses        int  not null default 0,          -- capable rides that passed without detecting anything
  last_miss_at         timestamptz
);
create index if not exists incidents_geom_gix on incidents using gist (geom);
create index if not exists incidents_status_score_idx on incidents (status, score desc);
create index if not exists incidents_department_idx on incidents (department);

create table if not exists incident_evidence (
  incident_id bigint not null references incidents(id) on delete cascade,
  evidence_id bigint not null references evidence(id) on delete cascade,
  primary key (incident_id, evidence_id)
);
create index if not exists incident_evidence_evidence_idx on incident_evidence (evidence_id);

-- Citizen YES/NO on an incident. Every located report is an implicit YES (report_id set);
-- explicit answers come from the "Is this problem still there?" prompt.
create table if not exists citizen_responses (
  id              bigserial primary key,
  incident_id     bigint  not null references incidents(id) on delete cascade,
  contributor_id  bigint  references contributors(id),      -- null = anonymous (19115 import)
  report_id       bigint  references reports(id) on delete cascade,
  answer          boolean not null,                         -- true = YES, the problem is there
  settled         boolean not null default false,           -- already counted in contributor trust
  created_at      timestamptz not null default now()
);
create index if not exists citizen_responses_incident_idx on citizen_responses (incident_id);
-- one answer per contributor per incident (latest wins) and one YES per report
create unique index if not exists citizen_responses_once_idx
  on citizen_responses (incident_id, contributor_id) where contributor_id is not null;
create unique index if not exists citizen_responses_report_idx
  on citizen_responses (report_id) where report_id is not null;
