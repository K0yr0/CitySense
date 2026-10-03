-- 201 (owner B): history of the city work status (W3): who moved an incident to
-- todo / in_progress / done, when, and an optional note. Written only by backend/api/admin.py.
-- A jsonb array on the incident (oldest first) rather than a table: the history is only ever read
-- per incident, and the names/emails are snapshots, so it stays readable if an account is deleted.
-- Entry: {"from_status", "to_status", "by_email", "by_name", "note", "at"}.
alter table incidents add column if not exists work_log jsonb not null default '[]'::jsonb;
