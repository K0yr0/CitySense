-- CityEcho SQL functions. Apply after db/schema.sql (scripts/init_db.py does both).
-- Idempotent: every function uses `create or replace`.

-- Nearest segment to a WGS84 point within `max_dist_m` metres (exact geography
-- distance), optionally restricted to one mode ('road' | 'tram'). NULL when none.
-- The `&&` box (degrees, widened by cos(lat) for longitude) lets the GiST index on
-- segments.geom do the coarse filtering; ST_DWithin on geography is the exact check.
-- Same logic as backend.db.nearest_segments (which batches many points).
create or replace function nearest_segment(
  lon        float8,
  lat        float8,
  p_mode     text   default null,
  max_dist_m float8 default 20
) returns bigint
language sql
stable
as $$
  select s.id
  from segments s
  cross join (select ST_SetSRID(ST_MakePoint(lon, lat), 4326) as pt) p
  where (p_mode is null or s.mode = p_mode)
    and s.geom && ST_Expand(p.pt,
                            max_dist_m / (111320.0 * greatest(cos(radians(lat)), 0.01)),
                            max_dist_m / 110540.0)
    and ST_DWithin(s.geom::geography, p.pt::geography, max_dist_m)
  order by s.geom::geography <-> p.pt::geography, s.id
  limit 1
$$;


-- Segment health from per-ride vibration RMS:
--   med_s  = median(rms) over the rides that covered segment s
--   health = 1 - clamp(med_s / p99(med over all measured segments), 0, 1)
--   health_rides = number of distinct rides that covered s
-- Segments whose ride_segments rows all disappeared (rides deleted) go back to
-- "never measured" (health null, health_rides 0).
create or replace function recompute_segment_health() returns void
language sql
as $$
  with per_segment as (
    select segment_id,
           percentile_cont(0.5) within group (order by rms) as med_rms,
           count(distinct ride_id)                          as rides
    from ride_segments
    group by segment_id
  ),
  norm as (
    select percentile_cont(0.99) within group (order by med_rms) as p99
    from per_segment
  )
  update segments s
     set health = 1.0 - least(greatest(coalesce(ps.med_rms / nullif(n.p99, 0), 0), 0.0), 1.0),
         health_rides = ps.rides
    from per_segment ps
    cross join norm n
   where s.id = ps.segment_id;

  update segments s
     set health = null,
         health_rides = 0
   where (s.health is not null or s.health_rides > 0)
     and not exists (select 1 from ride_segments rs where rs.segment_id = s.id);
$$;
