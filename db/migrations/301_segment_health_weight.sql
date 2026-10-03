-- 301 (owner C, S3): time-weighted amount of health data per segment, written only by
-- recompute_segment_health() (db/functions.sql) together with health_updated_at (300).
--   health_weight = sum over passes of 0.5 ^ (age / 7 days); 0 = never measured or long stale.
alter table segments add column if not exists health_weight real not null default 0;

-- Fill health_weight / health_updated_at for rides recorded before this migration.
select recompute_segment_health();
