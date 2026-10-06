-- The cloud server's tables. Applied on every start: every statement is idempotent.
-- Times are timestamptz written from the server's clock; money is US dollars.

create table if not exists users (
  id text primary key,
  issuer text not null,
  subject text not null,
  email text,
  name text,
  created_at timestamptz not null,
  unique (issuer, subject)
);

create table if not exists api_keys (
  id text primary key,
  user_id text not null references users(id) on delete cascade,
  name text not null,
  hash text not null unique,
  prefix text not null,
  created_at timestamptz not null,
  last_used_at timestamptz
);
create index if not exists api_keys_user on api_keys (user_id);

create table if not exists builds (
  id text primary key,
  user_id text not null references users(id),
  parent_id text,
  title text,
  entry jsonb not null,
  pythonpath jsonb not null,
  files jsonb not null,
  dedupe_key text not null,
  status text not null,
  error jsonb,
  outputs jsonb,
  primary_file text,
  export_key text,
  export_error text,
  thumbnail_key text,
  log text,
  progress jsonb,
  cadgen text,
  limits jsonb not null,
  timings jsonb,
  cost jsonb,
  flags jsonb,
  reservation jsonb,
  created_at timestamptz not null,
  started_at timestamptz,
  finished_at timestamptz,
  updated_at timestamptz not null
);
create index if not exists builds_user_created on builds (user_id, created_at desc);
create index if not exists builds_dedupe on builds (user_id, dedupe_key);
-- One build at a time per person, enforced by the database rather than by a race.
create unique index if not exists builds_one_active on builds (user_id) where status in ('queued', 'running');

create table if not exists jobs (
  id text primary key,
  build_id text not null references builds(id),
  user_id text not null references users(id),
  kind text not null,
  status text not null,
  request jsonb not null,
  result jsonb,
  error jsonb,
  progress jsonb,
  limits jsonb not null,
  timings jsonb,
  cost jsonb,
  flags jsonb,
  reservation jsonb,
  created_at timestamptz not null,
  started_at timestamptz,
  finished_at timestamptz,
  updated_at timestamptz not null
);
create index if not exists jobs_user_created on jobs (user_id, created_at desc);
create unique index if not exists jobs_one_active on jobs (user_id) where status in ('queued', 'running');

create table if not exists usage_daily (
  user_id text not null references users(id) on delete cascade,
  day text not null,
  vcpu_seconds double precision not null default 0,
  reserved_vcpu_seconds double precision not null default 0,
  builds integer not null default 0,
  jobs integer not null default 0,
  primary key (user_id, day)
);

create table if not exists budget_daily (
  day text primary key,
  spent_usd double precision not null default 0,
  reserved_usd double precision not null default 0
);
