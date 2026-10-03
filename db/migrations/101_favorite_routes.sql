-- 101 (owner A): a signed-in user's favourite routes for the mobile app (M5).
-- kind 'points' = start/end pins (routed via OSRM, straight-line fallback);
-- kind 'line'   = a bus/tram line (segments covered by rides with that vehicle_line).
-- start_geom / end_geom ("end" is a reserved word) are null for kind 'line'.
create table if not exists favorite_routes (
  id          bigserial primary key,
  user_id     bigint not null references users(id) on delete cascade,
  name        text not null,
  kind        text not null check (kind in ('points', 'line')),
  start_geom  geometry(Point, 4326),
  end_geom    geometry(Point, 4326),
  line        text,
  mode        text check (mode in ('road', 'tram')),
  created_at  timestamptz not null default now()
);
create index if not exists favorite_routes_user_idx on favorite_routes (user_id);
