# API

`api.texttocad.dev`: cadgen's version feed and its telemetry receiver, a Vercel
project of its own (`texttocad-api`, Root Directory `apps/api`).

**PURPOSE** — the one service cadgen talks to (`cadgen/_internal/api.py` in
`packages/cadgen`). Every released cadgen, 0.7.7 on, calls its four routes, so their
paths, methods, statuses, bodies and headers are a contract that never breaks.

**MAY DEPEND ON** — Node's standard library and the web platform's `fetch`,
`Request` and `Response`: no npm dependencies, so there is nothing to install. It is
not one of the root npm workspaces and has no lockfile.

**DEPENDED ON BY** — nothing in the repo imports it. cadgen reaches it over HTTPS: the
engine, for the CAD app's and the browser viewer's counts (`app`, `viewer`), the sender a
`cadgen` command starts (`cli`), and 0.7's `cadgen mcp`, viewer and build daemon.

## Build and deploy

```
api/v1.js       # the one Vercel Function: web-standard GET and POST, every /v1 path
src/            # the handler, the receiver (events.mjs), the drop list (noise.mjs), PostHog's store, the feed; their tests
public/         # what Vercel serves besides the function: robots.txt alone
vercel.json     # /v1/(.*) -> /api/v1; no framework, no build, no deploy on push
```

```bash
npm --prefix apps/api test          # or scripts/test/test-api.sh, which CI runs
```

`vercel.json` rewrites every `/v1/...` path to the function, which keeps the path it
was asked for; the handler routes it, with or without a trailing slash. With no
framework and no build, Vercel would serve the project's files as they are, so
`public/` is the output and holds only `robots.txt`.

Deployment is the `Deploy API` workflow only (`.github/workflows/deploy-api.yml`): a
push to `main` that changes `apps/api` deploys it, after its tests, and a dispatch
redeploys. Nothing about it follows a release.

## Routes

Its `/v1` routes serve the version feed cadgen's daily check reads (`cadgen/updates.py` in
`packages/cadgen`), and receive cadgen's telemetry (`cadgen/analytics.py`): the usage
counts the CAD app, the browser viewer and a `cadgen` command's sender (and 0.7's build
daemon) send, which it checks and passes on to PostHog. Clients know only
`api.texttocad.dev`, so the service behind it can change without a release of cadgen.

| Route | What it does |
| --- | --- |
| `GET /v1/versions` | The version feed, the same for everyone: `{latest}` → `200` (`src/versions.mjs`). `latest` is the newest `X.Y.Z` release of cadgen that PyPI's simple index (PEP 691 JSON, what uv resolves every pin through) has an unyanked file of: never a pre-release, and a release whose every file is yanked is none. Each instance keeps what it read for five minutes, and keeps answering it while PyPI fails; Vercel's edge keeps a reply an hour, refreshes it in the background for a day after, and serves it on for a week while the function fails (`public, s-maxage=3600, stale-while-revalidate=86400, stale-if-error=604800`). With nothing read and PyPI unreachable (3 s at most) it is `503`, kept nowhere, which a released cadgen takes as a check that failed: silently, keeping the feed it last read, trying again the next day. Only a copy installed by hand reads it; a store's copy never checks. It asks no telemetry service. |
| `POST /v1/events` | One batch: `{schema: 8, batch, at, install, session, process, version, channel, platform, arch, client: {name, version}, presentation, events: [...]}` → `204`, once PostHog has taken it. `batch` is the batch's own random id, and `at` when it was made (whole seconds, the sender's clock): a sender that never heard back sends the batch again as it was, and each of its rows takes an id made of the two (`id`: a UUIDv5 of `batch` and the row's key), the same every time, which PostHog is given as the event's `uuid`. `process` is the sender: `app` (the CAD app), `viewer` (the browser viewer), `daemon` (0.7's build daemon, which names no `client` or `presentation`; 0.8's engine sends as `app` and `viewer`) or `cli` (what `cadgen` commands and model scripts counted -- builds, the engine's health, their crashes -- which names neither: a batch of its own from whichever process sends it, the CAD app's, the viewer's, or the sender a `cadgen` command starts when neither has sent it for five minutes). `channel` is where the install came from, as its package named it: `claude-github`, `codex-github`, `cursor-github`, `gemini-github`, `claude-desktop`, `claude-directory`, `openai-directory`, `cursor-marketplace`, `agent-plugins`, `dev` or `unknown`. Only the CAD app is told it, by its plugin's startup config; from the release after cadgen 0.7.19 it notes it for its uv installation, and a `viewer` or `daemon` that was not told one itself sends the one last noted there, so theirs is `unknown` only where no plugin's CAD app ever ran from that installation (a skills-only install, or cadgen run by hand) -- through 0.7.19 it was `unknown` unless the CAD app started that process. Each event counts what the process saw since its last batch, one event per thing counted (`FIELDS` in `src/events.mjs`): `tool` `{tool, calls, errors}`; `tool_failure` `{tool, reason, count}`, a tool's failed calls for one reason, a word cadgen chose where the call failed (`no_path`, `relative_path`, `no_file`, `not_cad`, `no_view`, `wrong_view`, `bad_request`, `timeout`, `view_error`, `too_large`, `no_viewer`, `bug` or `other`), never what the failure said; `view` `{calls}`; `files` `{kind, count}`, distinct models or files of a format shown for the first time that day; `build` `{kind, via, count, failed, crashed, cancelled, cached, seconds, longest}`, model builds or file exports by who asked (`script` or `command`); `build_failure` `{kind, via, reason, count}`, the failed builds of a format and asker for one reason, a word cadgen chose where the build failed from the error's kind and whose code raised it (`model_error`, `kernel_error`, `refused`, `script_error`, `arguments`, `child_failed`, `missing_module`, `missing_file`, `io_error`, `timeout`, `memory`, `export_error`, `bug` or `other`), never what it said, its counts adding up to the build's `failed`; `snapshot` `{kind, count, failed, seconds}`; `snapshot_failure` `{kind, reason, count}` likewise (`bad_request`, `no_file`, `input_error`, `browser`, `timeout`, `memory`, `render_error`, `bug` or `other`); `feature` `{feature, count}` (`assembly`, `declared_mesh`, `kinematics`, `animation`, `drawing`, `quick_edit`); `control` `{control, count, seconds}`, one of a CAD view's controls a person used, from the CAD app and the browser viewer alike (`process` tells them apart): a name from a closed list the page chose (`CONTROLS`: the strip's tools and Preview, Select's and Measure's filters, Pencil's and Shapes' tools, Explode's and Clip's controls, Display's modes and Grid, Projection, Preview's settings, the routines and Position, the sidebar's sections and trees, a part's menu, Look at, the view cube, Quick Edit's Copy, Queue and Send, the navbar's and app menu's items, Export by format and the home's), how many times it was used, and for a tool that stays on (the tool in hand, Preview) the whole seconds it was on while its page was shown -- either may be 0 (a tool on all that window, taken up in an earlier one; a button), never both -- never a value typed or chosen, unless the value is itself a name of the list (`display_xray`, `clip_axis_z`); `health` `{workers, crashes, recycles, refusals}`, the daemon's build workers; `exception` `{where, tool?, type, handled, status?, frames: [{file, function, line?, column?, chunk_id?}], count}`, one crash and how many times it happened: where (`tool`, `route`, `request`, `build`, `command` or `page`), the error's type, whether the process went on, and up to 30 innermost frames, each a file inside cadgen, the standard library, a dependency or the page's assets (never an absolute path, `..` or a drive), with the person's own code `<user>`, and a page's frame in one of its own chunks that chunk's debug id (`chunk_id`), under which the release uploaded its source map; a dead worker's exit status in `status`. Never a message. A kind is `model` for a live model, or an actual file format: `step`, `stl`, `3mf`, `glb`, `dxf`, `urdf`, `srdf`, `sdf` or `xbf`. A schema 7 or 8 batch holds up to 256 events, one per control a window used beside the rest; schemas 1–6 hold 64. Schema 7 is read too: the same without `model`. Schema 6 (development builds of cadgen 0.8, before the controls; no release sent it) is read too: the same without `control`. Schema 5 (cadgen 0.7.20 to 0.7.26) is read too: schema 6 without `xbf` or `cli`. Schema 4 (cadgen 0.7.19) is read too: no `batch`, `at`, `build_failure` or `snapshot_failure`, and its rows no `id`, so PostHog stamps its events as they arrive. Schema 3 (cadgen 0.7.16 to 0.7.18) likewise, and without `tool_failure`. Schemas 1 and 2 (cadgen 0.7.7 to 0.7.15) are read too: they name no `process` (the browser viewer's `presentation` was `browser`; anything else was the CAD app), a schema 1 batch says how the install was made (`source`: `store` or `manual`) in place of `channel`, and their `file` event named one distinct file by a salted code, of which the receiver passes on the format alone, as `files`. Anything else is `400` and passes nothing on. |
| `POST /v1/forget` | `{install}`: deletes the install's person in PostHog and every event sent under its id → `204` once PostHog has queued it (it deletes in the background). `cadgen telemetry off` calls it; the random id is the only authority needed. The id rides in the body because Vercel's request logs keep each path beside the caller's IP. Each deletion spends the personal key, so each instance allows 5 in 10 minutes per client address (`x-vercel-forwarded-for`, else the first hop of `x-forwarded-for`) and per install id, in memory, the address only as a salted hash, in a map of at most 1000 keys with the oldest evicted (`src/limit.mjs`); past that it is `429` with `Retry-After`, nothing queued, which a client takes as a deletion it still owes. |
| `GET /v1/health` | → `200`, or `503` naming a missing or malformed setting (`POSTHOG_REGION`, `POSTHOG_PROJECT_KEY`, `POSTHOG_PERSONAL_KEY`, `POSTHOG_PROJECT_ID`), or PostHog's status when it will not take the personal key for the project, or `posthog_project_key` when `POSTHOG_PROJECT_KEY` is another project's. `Deploy API` checks it, so a deploy verifies all four settings. PostHog's answer, failure or not, is kept a minute per instance (`READY_TTL_MS`), so a burst of checks spends the personal key once. |

Schema 8 separates live models from files without adding identities or free-text fields. A model build,
a shown model document and a snapshot sourced from a model use `kind: model`. An explicit export still
counts under its destination format, and an opened or snapshotted `.xbf` file stays `xbf`. The existing
`build` and `files` event names remain. Schemas 6–7 used `xbf` for both live models and actual XBF files;
those rows remain as sent and cannot be split retrospectively. Earlier schemas and queued batches keep
their original meanings. Deploy this receiver before releasing a schema 8 sender.

Each event of a batch becomes one PostHog event (`src/posthog.mjs`): `tool_used`, `tool_failed`,
`view_used`, `files_shown`, `models_built`, `build_failed`, `snapshots_rendered`, `snapshot_failed`,
`feature_used`, `control_used`, `daemon_health` or, for a crash, `$exception`, which PostHog's error tracking groups into
issues (`$exception_list`: the type, a value that is only ever a dead worker's exit
status, `mechanism.handled`, and raw frames, only cadgen's own or the page's own -- never a `vendor-` chunk's -- `in_app`),
with the install id as its distinct id, the batch's context (`session`,
`process`, `version`, `channel`, `source`, `platform`, `arch`, `client`, `client_version`,
`presentation`) and the event's own counts as properties, and `country`: the ISO code
Vercel places the request in (`x-vercel-ip-country`), left out where it cannot tell.
PostHog's own location lookup is off for every event (`$geoip_disable`): the receiver
posts from Vercel's servers, and nothing finer than the country is wanted. An event is a
window's counts, so a question adds up a property (`calls`, `count`, `seconds`): it never
counts events.

**A batch sent again counts once.** A schema 5, 6, 7 or 8 row's event carries its row id as PostHog's `uuid`
and its batch's `at` as its `timestamp`, both the same however often the batch comes. PostHog takes
events with the same `uuid`, event name, `timestamp` and distinct id as one
([its docs](https://posthog.com/docs/cdp/common-questions): sent with a uuid, duplicates "are eventually
de-duplicated"), collapsing them as its tables merge, so a query may see both copies until then. The
`timestamp` is always the batch's own, by the sender's clock, so a copy sent however long after keeps the
same key; a clock that is off places its counts where it says. Every earlier schema's event is stamped as
it arrives.

- **Every release keeps counting.** The receiver reads every schema a released
  cadgen sends, for as long as that release can still be running: a copy nobody
  updates is counted like a current one. A new schema adds a reader beside the old
  ones in `events.mjs`.
- **Nothing outside the contract is passed on**: unknown fields, tool names that are
  not `cad_*`, names outside an event's vocabulary, free-text strings are refused. The receiver keeps no IP address, and
  sends PostHog none.
- **A refusal is logged, and says why.** Every released client is accepted, so a 400 is
  garbage or a bug losing a real person's counts, and Vercel's per-status counts are a paid
  feature. Each refusal is one `console.warn` line: `telemetry /v1/events refused 400:
  <rule> (schema N, cadgen X.Y.Z)`, where the rule is a field's path or a vocabulary and
  the release is logged only when it reads as one. Never a value, an install id or a
  service's message (`handler.mjs`: `reasonOf`); an error that is ours is logged by its
  name or string code alone (`TimeoutError`, `posthog_503`).
- **Never cadgen's bug: dropped.** A crash row that matches the drop list
  (`NEVER_OURS` in `src/noise.mjs`) goes no further than the receiver: released clients
  keep sending what a later one learned to leave out, and each would be an issue in
  PostHog with no fix in cadgen. A signature goes on the list only when it can never
  be a mistake in cadgen's code, never because it is frequent, and in the same change
  the client stops sending it (`stdout_closed` and `signature` in `cadgen/analytics.py`). Each
  entry matches on `where`, `type`, `status` and frames alone: any `ConnectionError` at a
  `route` (a page that left mid-reply); a `BrokenPipeError` at a `command` (its output's
  reader closed it, `| head`); an `AttributeError` whose innermost frame is
  `cadgen/build123d.py` `__getattr__` or `cadgen/color.py` `_parse_hex` with the
  person's code above it (a model asking for a build123d name that does not exist, or
  a colour that is not a string); a `WorkerDied` with status `-15`, `-2` or `-1` (a
  worker stopped by SIGTERM, SIGINT or SIGHUP); a `RecursionError` with `<user>`
  among its frames (the person's code is in the cycle); an `AbortError` at a `page`
  (a cancellation the page or the browser asked for, `crashOf` in core's `client/crash.js`);
  and a `page` crash none of whose frames is in a script of the page's, every one `<?>` (an
  extension's script, or an automation's, run in the page).
  Only `exception` rows are ever
  dropped, and dropping one is not a refusal: the batch is answered `204` and its other
  rows are stored. Each batch that had any logs one `console.info` line counting them
  by name: `telemetry dropped page_left 4, worker_stopped 1 (schema 3, cadgen 0.7.17)`.
- **No browser posts.** Both POSTs must be `application/json` (`415` otherwise) and
  carry no `Origin` header (`403`): cadgen posts from Python, which sends none, and a
  browser sends one with every POST, a form's, `sendBeacon`'s and a no-cors fetch's included.
  There are no CORS headers.
- **The privacy policy describes these events.** A new field is a change to the docs
  site's `apps/docs/src/app/privacy-policy/page.tsx` in the same PR.
- **Portable.** `src/handler.mjs` is a plain `fetch(Request) → Response` handler
  over a store (`insert`, `forget`, `ready`) and a feed (`versions`); `posthog.mjs` is
  PostHog's, `versions.mjs` reads PyPI, and `api/v1.js` with `vercel.json` is all that
  ties it to Vercel (one function for every `/v1` path, and the country header). The
  tests (`npm test`, which `scripts/test/test-api.sh` runs) hand the store and the feed a
  `fetch` of their own, so they need no network.

Setup, once: a PostHog project; the domain `api.texttocad.dev` on this Vercel
project (a DNS-only CNAME at Cloudflare); and four of the project's own
production environment variables, set as Sensitive in the Vercel dashboard:
`POSTHOG_REGION` (`us` or `eu`, where the PostHog project lives),
`POSTHOG_PROJECT_KEY` (the project's API key, which captures), `POSTHOG_PERSONAL_KEY`
(a personal API key with `person:write`, which deletes, and `project:read`, which health
checks the project with; scope it to this project alone), and
`POSTHOG_PROJECT_ID`. Nothing in GitHub holds them. A changed value takes effect with
the next deploy, and `Deploy API` checks `api.texttocad.dev/v1/health`, which answers
`503` while any is missing, PostHog refuses the personal key, or the project key is
another project's: the deploy is where the settings are checked, since Vercel keeps
Sensitive values write-only and nothing else can read them back.

Retention is PostHog's: events go after the period its plan keeps them (a year on the
free plan), and the privacy policy says so.

The feed moves when PyPI does: no release deploys anything here, and `latest` never
names a release that cannot be installed yet. Only a copy installed by hand reads it: a
store's copy (`claude-directory`, `openai-directory`, `cursor-marketplace`) never checks
and is never told, since its store updates it.
A Vercel Firewall rate-limit rule on `/v1/*` (answering `429`) is recommended: a
real client sends at most once every five minutes per running process, and once more
as it exits, so a per-IP limit well above that turns a flood away at no cost to real
clients. The in-memory limits above are the first layer and hold per
instance only, so a flood spread over many instances or addresses passes them: the
Vercel Firewall rules on `/v1/forget` and `/v1/health` are the second layer.

A client keeps a batch it could not send (offline, a `5xx` while the receiver or
PostHog is down, a `404` before it is deployed, a firewall's `403` or a `429`) and sends
it again, whole and before anything newer, for as long as its process runs, and past that by
the next process that sends; what it counts meanwhile waits for a later batch. A deletion an
opt-out owes is asked for again the same way. It drops only a batch the receiver read and refused
(`400`, `413`, `415` or `422`): that batch would be refused again.

What it answers, in PostHog: how many people use CAD (installs: one per machine and OS
user, a new one after an opt-out and back), how often (active days, from when each batch was
made -- before schema 5, when it arrived: a process sends at most every five minutes, and only when used), which CAD tools
are used and how often they fail (`tool_used`: sum of `calls` and `errors` by `tool`), on
how many files (`files_shown`: sum of `count` by `kind`, each file once a day per
process), how many models are built and how that goes (`models_built`: sums of `count`,
`failed`, `crashed`, `cancelled`, `cached` and `seconds` by `kind` and `via`, and the
largest `longest`), why builds fail (`build_failed`: sum of `count` by `reason`, `kind` and
`via`), snapshots likewise (`snapshots_rendered`, `snapshot_failed`), which features are used
(`feature_used`), which of a CAD view's tools and settings people use, how often and for how long, in
the CAD app and the browser viewer (`control_used`: sums of `count` and `seconds` by `control` and `process`,
and installs by `control`), how the build workers fare (`daemon_health`: the build daemon's, and the engine's
warm workers), and where (installs by
`country`). A process nobody used sends nothing.
