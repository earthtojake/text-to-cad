-- CAD's anonymous analytics: one row per event of a batch (src/lib/analytics/events.mjs). No IP
-- address, no request header, nothing that names a person, a file or a model. Safe to run again:
-- it creates what is missing and adds the columns a later schema introduced.
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
create index if not exists events_install_id on events (install_id);
