-- CAD's anonymous analytics: one row per event of a batch (src/lib/analytics/events.mjs), and where
-- installs are, as totals. No IP address, nothing that names a person, a file or a model. Safe to
-- run again: it creates what is missing and adds the columns a later schema introduced.
create table if not exists events (
  id             bigint generated always as identity primary key,
  received_at    timestamptz not null default now(),  -- the row's one time: when its batch arrived
  install_id     uuid        not null,  -- random, made on the person's machine; deleted there on opt-out
  session_id     uuid        not null,  -- random, one per `cadgen mcp` or `cadgen viewer` process
  event          text        not null,  -- tool | view | file
  tool           text,                  -- event = tool: cad_show, cad_view, ...
  file           text,                  -- event = file: 16 hex characters, an HMAC of the path under the install's own salt
  kind           text,                  -- event = file: step | stl | 3mf | glb | dxf | urdf | srdf | sdf
  calls          integer     not null,  -- tool: calls; view: touches; file: 1
  errors         integer     not null,  -- tool: failed calls
  version        text        not null,  -- cadgen's
  source         text        not null,  -- store (a plugin directory install) | manual
  platform       text        not null,  -- darwin | linux | win32 | other
  arch           text,
  client         text,                  -- the agent app: codex-mcp-client, claude-ai, ...
  client_version text,
  presentation   text                   -- tabs | inline | text (the CAD app), browser (`cadgen viewer`)
);
alter table events add column if not exists file text;
alter table events add column if not exists kind text;
create index if not exists events_received_at on events (received_at);
-- An install's rows, in time: what it forgets, and whether it has sent anything this week or month.
create index if not exists events_install on events (install_id, received_at);
drop index if exists events_install_id;

-- How many installs sent analytics from each country, each week and each month: totals only, never
-- an install. The country is the host's (Vercel's `x-vercel-ip-country`, from the request's IP
-- address, which is not kept); an install counts once a period, where its first batch of the
-- period came from. Nothing here names an install, and nothing in `events` names a country. Kept
-- indefinitely, and an opt-out leaves them: no total can be traced to anyone.
create table if not exists countries (
  period   text    not null check (period in ('week', 'month')),
  starts   date    not null,  -- the period's first day in UTC: a Monday (ISO week) or the 1st
  country  text    not null,  -- ISO 3166-1 alpha-2; ZZ where the host could not tell
  installs integer not null,
  primary key (period, starts, country)
);
