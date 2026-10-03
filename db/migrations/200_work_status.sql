-- 200 (owner B): municipal work status, separate from the confidence status.
-- todo -> in_progress -> done; written only by the web admin (B). The mobile app reads it
-- (no "is it still there?" question once done).
alter table incidents add column if not exists work_status text not null default 'todo';
alter table incidents add column if not exists work_status_changed_at timestamptz;
alter table incidents add column if not exists work_status_by bigint references users(id) on delete set null;

do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'incidents_work_status_check') then
    alter table incidents add constraint incidents_work_status_check
      check (work_status in ('todo', 'in_progress', 'done'));
  end if;
end $$;

create index if not exists incidents_work_status_idx on incidents (work_status);
