-- 100 (owner A): signed-in users (Google Sign-In, backend/auth).
-- role is re-derived from ADMIN_EMAILS at every login. contributor_id links the anonymous
-- contributor (device token) the user had before signing in, so earned trust carries over;
-- one contributor belongs to at most one account.
create table if not exists users (
  id              bigserial primary key,
  google_sub      text unique,                       -- Google account id; null for AUTH_DEV_LOGIN users
  email           text not null unique,              -- stored lower-case
  name            text,
  role            text not null default 'citizen' check (role in ('citizen', 'admin')),
  contributor_id  bigint unique references contributors(id) on delete set null,
  created_at      timestamptz not null default now()
);
