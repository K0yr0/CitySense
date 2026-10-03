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


-- Segment health from per-ride vibration RMS, newest measurements first (S3):
--   med_s  = median(rms) over the RECENT 5 passes of segment s (newest passed_at first), so new
--            rides push old ones out: after a repair, 3 clean passes make the segment healthy
--   health = 1 - clamp(med_s / p99(med over all measured segments), 0, 1)
--   health_rides      = number of distinct rides that ever covered s (raw data amount)
--   health_weight     = sum over passes of 0.5 ^ (age / 7 days): time-weighted data amount
--                       (1.0 ~ one fresh ride; old data fades towards 0)
--   health_updated_at = time of the newest measurement of s (freshness)
-- Segments whose ride_segments rows all disappeared (rides deleted) go back to
-- "never measured" (health null, health_rides 0).
-- plpgsql: the body is checked when it runs, so this file can be applied before the migrations
-- that add health_weight (301) and health_updated_at (300).
create or replace function recompute_segment_health() returns void
language plpgsql
as $$
begin
  with passes as (
    select rs.segment_id, rs.ride_id, rs.rms,
           coalesce(rs.passed_at, r.started_at, r.created_at) as at,
           row_number() over (partition by rs.segment_id
                              order by coalesce(rs.passed_at, r.started_at, r.created_at) desc, rs.ride_id desc) as recent
    from ride_segments rs
    join rides r on r.id = rs.ride_id
  ),
  per_segment as (
    select segment_id,
           percentile_cont(0.5) within group (order by rms) filter (where recent <= 5) as med_rms,
           count(distinct ride_id)                          as rides,
           sum(exp(-ln(2.0) * least(greatest(extract(epoch from (now() - at))::float8, 0) / (7 * 86400.0), 60)))
                                                            as weight,
           max(at)                                          as last_at
    from passes
    group by segment_id
  ),
  norm as (
    select percentile_cont(0.99) within group (order by med_rms) as p99
    from per_segment
  )
  update segments s
     set health = 1.0 - least(greatest(coalesce(ps.med_rms / nullif(n.p99, 0), 0), 0.0), 1.0),
         health_rides = ps.rides,
         health_weight = round(ps.weight::numeric, 3),
         health_updated_at = ps.last_at
    from per_segment ps
    cross join norm n
   where s.id = ps.segment_id;

  update segments s
     set health = null,
         health_rides = 0,
         health_weight = 0,
         health_updated_at = null
   where (s.health is not null or s.health_rides > 0)
     and not exists (select 1 from ride_segments rs where rs.segment_id = s.id);
end
$$;
