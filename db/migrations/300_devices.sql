-- 300 (owner C): sensor devices (simulated buses/trams) for POST /devices/stream,
-- and a freshness timestamp for segment health (written only by C's sensor code).
create table if not exists devices (
  id            text primary key,                     -- device_id from DEVICE_KEYS / X-Device-Key
  key_hash      text not null,                        -- hash of the device secret, never the secret
  vehicle_line  text,
  mode          text check (mode in ('road', 'tram')),
  last_seen_at  timestamptz,
  created_at    timestamptz not null default now()
);

alter table segments add column if not exists health_updated_at timestamptz;
