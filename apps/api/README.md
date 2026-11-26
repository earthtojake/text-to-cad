# API

`api.texttocad.dev`: text-to-cad's version feed and its telemetry receiver, a Vercel
project of its own (`texttocad-api`, Root Directory `apps/api`).

**PURPOSE** — the one service text-to-cad talks to (`cad_server/_internal/api.py` in
`packages/cad`). Every release, 0.7.7 on (cadgen before 0.10), calls its routes, so their
paths, methods, statuses, bodies and headers are a contract that never breaks.

**MAY DEPEND ON** — Node's standard library and the web platform's `fetch`,
`Request` and `Response`: no npm dependencies, so there is nothing to install. It is
not one of the root npm workspaces and has no lockfile.

**DEPENDED ON BY** — nothing in the repo imports it. text-to-cad reaches it over HTTPS: the
engine, for the CAD app's and the browser viewer's counts (`app`, `viewer`), the sender a
`cad` command starts (`cli`; a `cadgen` command's before 0.10), and 0.7's `cadgen mcp`, viewer and build daemon; and
the install command (`scripts/install/`), for one report of a run that failed with no working cad to count it.

## Build and deploy

```
api/v1.js       # the one Vercel Function: web-standard GET and POST, every /v1 path
src/            # the handler, the receiver (events.mjs), a failed install's report (install.mjs), the drop list (noise.mjs), PostHog's store, the feed; their tests
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

Its `/v1` routes serve the version feed text-to-cad's hourly check reads (`cad_server/updates.py` in
`packages/cad`; releases 0.7.12 to 0.11.11 read its frozen address), and receive its telemetry (`cad_server/analytics.py`): the usage
counts the CAD app, the browser viewer and a `cad` command's sender (and 0.7's build
daemon) send, which it checks and passes on to PostHog, and the one report the install command
(`scripts/install/`) sends where a run of it failed. Clients know only
`api.texttocad.dev`, so the service behind it can change without a release of text-to-cad.

| Route | What it does |
| --- | --- |
| `GET /v1/releases` | The version feed, the same for everyone: `{latest, lines}` → `200` (`src/versions.mjs`), for example `{"latest": "1.2.0", "lines": {"0": "0.12.3", "1": "1.2.0"}}`. cad 0.11.12 and later read it (`cad_server/updates.py`). `latest` is the newest release. `lines` names the newest release of each major version that has one, keyed by the major as a string, and says when cad updates itself: an update begins when it names a release of the installed major newer than the one installed (or where it names none of that major and `latest` is of a higher major), and then installs PyPI's newest of the installed major; a higher major never installs itself. Every release it names follows the rules below. |
| `GET /v1/versions` | The frozen version feed of releases 0.7.12 to 0.11.11 (they send `User-Agent: cadgen`; nothing newer reads it): `{latest}` alone → `200`, under the same rules, the same caching and the same `503`, naming the newest release **below 0.12.0** (`OLD_BELOW`). 0.11.0 to 0.11.11 install by themselves exactly the release it names, as `cad-server==X`, but only a patch of their own minor, and 0.10.0 to 0.10.4 install it on a click: were it to name 0.12.0 or later, every 0.11.x computer would stop updating by itself, while the newest 0.11.x carries the bridge to the design that updates itself freely ([decisions](../../docs/contributing/decisions.md), "Old releases are carried through the newest 0.11"). Until a release 0.12.0 exists it answers exactly what `/v1/releases`'s `latest` does. |
| `POST /v1/events` | One batch: `{schema: 12, batch, at, install, session, process, version, app, platform, arch, client: {name, version}, presentation, events: [...]}` → `204`, once PostHog has taken it. `batch` is the batch's own random id, and `at` when it was made (whole seconds, the sender's clock): a sender that never heard back sends the batch again as it was, and each of its rows takes an id made of the two (`id`: a UUIDv5 of `batch` and the row's key), the same every time, which PostHog is given as the event's `uuid`. `process` is the sender: `app` (the CAD app), `viewer` (the browser viewer), `daemon` (0.7's build daemon, which names no `client` or `presentation`; 0.8's engine sends as `app` and `viewer`) or `cli` (what `cad` commands counted, `cadgen` commands before 0.10 and model scripts through 0.8, and from schema 10 the engine's daemon of the model builds it answers -- builds, the engine's health, their crashes -- which names neither: a batch of its own from whichever process sends it, the CAD app's, the viewer's, or the sender a `cad` command or the daemon starts when neither has sent it for five minutes; 0.10 and 0.11 sent no model build). `app` is the agent app running it, detected rather than told: the MCP client's name where there is one (`codex-mcp-client` is `codex`, `cursor-vscode` `cursor`, `claude-code` `claude-code`, `claude-ai` `claude-desktop`, any other its own name made a token), else the app whose markers are set in the command's shell, else `unknown`. It is an open set, checked by its shape (up to 40 lower-case letters, digits and `._-`), never against a list. A schema 11 or 12 batch names no channel; one that does (a development build's, before the field was dropped; no release sent one) is `400`, as any field its schema lacks. Each event counts what the process saw since its last batch, one event per thing counted (`FIELDS` in `src/events.mjs`): `tool` `{tool, calls, errors}`; `tool_failure` `{tool, reason, count}`, a tool's failed calls for one reason, a word the client chose where the call failed (`no_path`, `relative_path`, `no_file`, `not_cad`, `no_view`, `wrong_view`, `bad_request`, `timeout`, `view_error`, `too_large`, `no_viewer`, `bug` or `other`; schema 10 adds `no_kernel`), never what the failure said; `view` `{calls}`; `files` `{kind, count}`, distinct models or files of a format shown for the first time that day; `build` `{kind, via, count, failed, crashed, cancelled, cached, seconds, longest}`, model builds or file exports by who asked (`script` or `command`) -- a model build's `failed` from schema 10 counts only the failures the system or the machine caused (`bug`, `no_kernel`, `export_error`, `outdated`, `memory`, `io_error`), a build the person's own script failed (it raised, the kernel refused it, it did not compile) being in its `count` alone, which is every build the daemon answered, and none `cancelled`; schemas 5 to 9 from 0.8 counted every failure; `build_failure` `{kind, via, reason, count}`, the failed builds of a format and asker for one reason, a word the client chose where the build failed from the error's kind and whose code raised it (`model_error`, `kernel_error`, `refused`, `script_error`, `arguments`, `child_failed`, `missing_module`, `missing_file`, `io_error`, `timeout`, `memory`, `export_error`, `bug` or `other`), never what it said, its counts adding up to the build's `failed` (schema 9 adds `no_kernel`: the engine could not start the kernel process the build runs in, which earlier schemas counted as `refused`; schema 10 adds `outdated`: the CAD server running is of a release before an option the library asked of it, which earlier schemas counted as `export_error`); `snapshot` `{kind, count, failed, seconds}`; `snapshot_failure` `{kind, reason, part, count}` likewise (`bad_request`, `no_file`, `input_error`, `browser`, `timeout`, `memory`, `render_error`, `bug` or `other`; schema 9 adds `no_gl`, no OpenGL context to draw in -- no X display, no GLX, a GDI 1.1 -- which earlier schemas counted as `render_error`, and `no_kernel`), and from schema 9 which part of the request a refusal (`bad_request`) named, a word the client chose where it refused, never the value given (`source`, `out`, `display`, `display.mode`, `display.exploded`, `display.clip`, `display.grid`, `display.visibility`, `camera`, `pose`, `size`, `annotation`, `measurements`, `references`, `job` or `other`), and `none` for any other reason; `feature` `{feature, count}` (`assembly`, `declared_mesh`, `kinematics`, `animation`, `drawing`, `quick_edit`; from 0.10 a model build's `assembly`, `declared_mesh` and `drawing` are not counted: usage, where the daemon counts CAD failing); `control` `{control, count, seconds}`, one of a CAD view's controls a person used, from the CAD app and the browser viewer alike (`process` tells them apart): a name from a closed list the page chose (`CONTROLS`: the strip's tools and Preview, Select's and Measure's filters, Pencil's and Shapes' tools, Explode's and Clip's controls, Display's modes and Grid, Projection, Preview's settings, the routines and Position, the sidebar's sections and trees, a part's menu, Look at, the view cube, Quick Edit's Copy, Queue and Send, the navbar's and app menu's items, Export by format and the home's), how many times it was used, and for a tool that stays on (the tool in hand, Preview) the whole seconds it was on while its page was shown -- either may be 0 (a tool on all that window, taken up in an earlier one; a button), never both -- never a value typed or chosen, unless the value is itself a name of the list (`display_xray`, `clip_axis_z`); `health` `{workers, crashes, recycles, refusals}`, the daemon's build workers (from schema 10 counted by the daemon with each build it answers; 0.10 and 0.11 sent none); `exception` `{where, tool?, type, handled, status?, cause?, frames: [{file, function, line?, column?, chunk_id?}], count}`, one crash and how many times it happened: where (`tool`, `route`, `request`, `build`, `command` or `page`), the error's type, whether the process went on, and up to 30 innermost frames, each a file inside text-to-cad (`cad/<path>` or `cad_server/<path>`; `cadgen/<path>` before 0.10), the standard library, a dependency or the page's assets (never an absolute path, `..` or a drive), with the person's own code `<user>`, and a page's frame in one of its own chunks that chunk's debug id (`chunk_id`), under which the release uploaded its source map; a dead worker's exit status in `status`; from schema 10, on the engine's crash of no kernel process (`cad.engine.serve.KernelProcessesUnavailable`) alone, which failure it was in `cause`, a word the client chose where it classified the failure (`pool`: the system refused the process pool; else the kernel environment could not be made: `network`, `denied`, `killed`, `python`, `resolve`, `install`, `files`, `uv`, `probe` or `other`), sent once per failure however many calls it failed; from schema 11, `arrival` `{step, route, from, outcome, reason?, attempts?, count}`, one step of how a computer got to the sending version, so one stuck on its way is counted: `step` `setup` (its `cad setup`: `ok` or `failed`), `serving` (its server serving for the first time: `ok`) or `handover` (the hand-over that server runs after it: `done`, `failed`, `gave_up` or `superseded`, with how many `attempts` it took, 0 to 1000), `route` `updater` (an earlier release's updater ran it) or `setup` (`cad setup` itself, the install command's), `from` the version installed before it (a version's name, at most 32 characters, starting with a digit) or `none`, and on a `failed` step alone why, a word the client chose where it failed (a setup's `uv`, `network`, `denied` or `other`; a hand-over's `no_report`, `setup`, `app` or `other`); the client keeps each and starts a sender for it at once, every time, so a step counted by a version that never runs again still reaches the receiver; from schema 11 too, `update` `{from, outcome, reason?, tries, installer, asked, plugin, count}`, one attempt of cad's own update of itself that ended, counted once by the server that runs after it (a failed update by the old cad's, a successful one by the new cad's; where a new attempt begins first, by whatever begins it, a typed `cad update` with no server running among them) and sent as an `arrival` is: `from` the version before it (as `arrival`'s), `outcome` `installed` (a newer cad), `current` (nothing newer), `failed`, or `restored` (failed, and the version before put back), on a `failed` or `restored` attempt alone which step failed, a word the client chose (`upgrade`: the installer's upgrade never ended well, or, for `cad update --major`, ended well without crossing to the higher major asked for; `older`: it ended well on a version it may not end on, older than the one before or, but for `--major`, of another major; and on `failed` alone `put_back`: the version before could not be put back either; a `--major` that crossed is `installed`), `tries` 1 to 1000, `installer` `uv` or `pipx`, `asked` true for a typed `cad update` and false for an automatic one, and `plugin` how the install command's run for the newer cad ended, a run begun since the attempt began (`ok`, `failed`, `underway` where a new attempt began before it ended, or `none` where none ran for it; `none` on every outcome but `installed`); from schema 12, `install` `{by, outcome, logo, colour, seconds, found, failed, count}`, one run of the plugin's install in the agent apps, which cad runs itself (`cad plugin install`), kept and sent as an `arrival` is: `by` who began it (`person`: the command typed; `script`: the install command handing over; `server`: cad's server, after an update), `outcome` `ok`, `failed` (every app found failed), `stopped` (its deadline passed before it was done: a run the server began has one) or `busy` (another run held the lock, and this one left at once), `logo` what the terminal showed of the logo (`played`, `still`, `none` or `failed`) and `colour` in which colours (`24bit`, `256` or `none`), `seconds` the whole seconds the run took (0 to 100000), and `found` and `failed` how many apps it found and how many of those failed (0 to 64 each, never more failed than found, counts and never which apps; of a run that ended, `failed` is the outcome where at least one was found and every one failed, and `ok` otherwise; a `stopped` run says what it had found by then, whatever that was; a `busy` run found none); and from schema 12 too, `install_failure` `{app, reason, seconds, count}`, one app where such a run failed, and only such an app -- cad never names an app it installed in, updated, cleaned up or skipped, so which agent apps a computer has is never sent: `app` the install's own key for it (`claude`, `codex`, `cursor`, ...: an open set, checked by the same shape as the batch's `app`), why it failed, a word the client chose where it failed (`timeout`, `command`, `network`, `exception` or `other`; always there), and the whole seconds it took (0 to 100000). Its row, and its PostHog event, name the app `plugin_app`: `app` there is the batch's, the agent app running cad. Never a message. A kind is `model` for a live model, or an actual file format: `step`, `stl`, `3mf`, `glb`, `dxf`, `urdf`, `srdf`, `sdf`, `xbf`, `kicad_pcb` or `kicad_sch` (the last two schema 8's alone). A schema 7, 8, 9, 10, 11 or 12 batch holds up to 256 events, one per control a window used beside the rest; schemas 1–6 hold 64. Schema 11 is read too: the same without `install` or `install_failure`. Schema 10 is read too: schema 11 without `app`, with a `channel` from the old list below, translated. Schema 9 is read too: the same without a tool's `no_kernel`, a build's `outdated` or a crash's `cause`. Schema 8 is read too: the same without `part`, `no_gl` or `no_kernel`, each of its `snapshot_failure` rows keyed (and so its `id`) as ever. Schema 7 is read too: the same without `model`, `kicad_pcb` or `kicad_sch`. Schema 6 (development builds of cadgen 0.8, before the controls; no release sent it) is read too: the same without `control`. Schema 5 (cadgen 0.7.20 to 0.7.26) is read too: schema 6 without `xbf` or `cli`. Schema 4 (cadgen 0.7.19) is read too: no `batch`, `at`, `build_failure` or `snapshot_failure`, and its rows no `id`, so PostHog stamps its events as they arrive. Schema 3 (cadgen 0.7.16 to 0.7.18) likewise, and without `tool_failure`. Schemas 1 and 2 (cadgen 0.7.7 to 0.7.15) are read too: they name no `process` (the browser viewer's `presentation` was `browser`; anything else was the CAD app), a schema 1 batch says how the install was made (`source`: `store` or `manual`) in place of `channel`, and their `file` event named one distinct file by a salted code, of which the receiver passes on the format alone, as `files`. A batch whose `schema` is a whole number newer than the receiver reads is `503` with `Retry-After`, passing nothing on: a release whose schema reached people before the receiver that reads it was deployed, whose sender keeps the batch and sends it again (`Later` in `src/events.mjs`). Anything else is `400` and passes nothing on. |
| `POST /v1/forget` | `{install}`: deletes the install's person in PostHog and every event sent under its id → `204` once PostHog has queued it (it deletes in the background). `cad telemetry off` calls it (`cadgen telemetry off` before 0.10); the random id is the only authority needed. The id rides in the body because Vercel's request logs keep each path beside the caller's IP. Each deletion spends the personal key, so each instance allows 5 in 10 minutes per client address (`x-vercel-forwarded-for`, else the first hop of `x-forwarded-for`) and per install id, in memory, the address only as a salted hash, in a map of at most 1000 keys with the oldest evicted (`src/limit.mjs`); past that it is `429` with `Retry-After`, nothing queued, which a client takes as a deletion it still owes. |
| `POST /v1/install` | One report of a run of the install command that failed with no working cad to count it (`src/install.mjs`): `{schema: 1, run, at, stage, outcome, code, platform, arch, by, uv, type?, frames?}` → `204`, once PostHog has taken it. A run that ends with a cad that works sends nothing here: that cad counts the plugin's install itself (`install`, `install_failure` above). `run` is a random UUID made for that run alone and kept nowhere on the computer (read in either case, kept in lower case), and `at` when the report was made (whole seconds, the sender's clock). `stage` is where the run failed: `uv` (uv could not be installed, or is too old), `fetch` (`install.py` could not be downloaded), `python` (uv could not run it), `cad` (cad could not be installed), `plugin` (no cad could run the plugin's step) or `script` (`install.py` crashed). `outcome` is `failed` or `crashed`, `code` an exit status (0 to 255), `platform` one of `darwin`, `linux`, `win32`, `other`, `arch` a short token as a batch's (at most 16 characters), `by` who ran the command (`person` or `cad`), and `uv` uv's version (`X.Y.Z`) or `none`. A `crashed` report alone says more: `type`, the error type's name (as an `exception` row's), which it always names, and `frames`, up to 10 of `{function, line?}` in `install.py`, never a file's name, a path or a message. Anything else is `400` and passes nothing on: an unknown field, a word outside a vocabulary, a `type` or `frames` on a report that is no crash, or a body past 4 KiB. It becomes one PostHog event, `install_failed`, with the run's id as its distinct id and no person made of it (`$process_person_profile: false`), the report's own fields as properties, the country as for a batch and PostHog's own location lookup off; under an id made of the run and the stage and at the report's own time, so a report sent again is the same event. It is captured in the same project as the counts. Nothing is kept under an id that lasts, so there is nothing for `/v1/forget` to delete. Each instance allows 30 in 10 minutes per client address, counted as `/v1/forget`'s are and apart from them (`INSTALL_LIMIT` in `src/limit.mjs`); past that it is `429` with `Retry-After`, nothing passed on. The install command sends a report once and never again, whatever the answer. |
| `GET /v1/health` | → `200`, or `503` naming a missing or malformed setting (`POSTHOG_REGION`, `POSTHOG_PROJECT_KEY`, `POSTHOG_PERSONAL_KEY`, `POSTHOG_PROJECT_ID`), or PostHog's status when it will not take the personal key for the project, or `posthog_project_key` when `POSTHOG_PROJECT_KEY` is another project's. `Deploy API` checks it, so a deploy verifies all four settings. PostHog's answer, failure or not, is kept a minute per instance (`READY_TTL_MS`), so a burst of checks spends the personal key once. |

Each address names the newest `X.Y.Z` release of the PyPI project `cadgen` (the library's deprecated alias, which a release uploads last, after `cad`, `cad-server` and `cad-mcp`) that PyPI's simple index (PEP 691 JSON, what uv resolves every pin through) has an unyanked file of, every unyanked file of it uploaded at least an hour ago by PyPI's own `upload-time` (a file with none makes its release too new), and that the project does not hold back (`CAD_HELD_RELEASES`, [Holding a release](#holding-a-release)): never a pre-release, a release whose every file is yanked is none, and a release too new or held is passed over for the newest one that qualifies, never answered as nothing (and `/v1/versions`, the newest below 0.12.0 that qualifies). Both come from one read of PyPI. Each instance keeps what it read for five minutes, and keeps answering it while PyPI fails. A failed read waits the same five minutes before retrying, even when no feed has been read yet; Vercel's edge keeps a reply five minutes, serves it one minute more while it fetches a new one, and serves it on for a week while the function fails (`public, s-maxage=300, stale-while-revalidate=60, stale-if-error=604800`): so a changed answer reaches everyone within about six minutes of the function reading it, and at most about eleven minutes after PyPI or the hold list changed. With nothing read and PyPI unreachable (3 s at most) it is `503`, kept nowhere, which a client takes as a check that failed: silently, keeping the feed it last read, trying again an hour later. Every running cad server reads it at most once an hour (never in CI, never a development build, never with `CAD_UPDATE_CHECK=0`), and an automatic update begins when it names a newer release of the installed major; the install command and `cad update` read no feed (the install command takes PyPI's newest, `cad update` PyPI's newest of the installed major). It asks no telemetry service.

Schema 8 separates live models from files without adding identities or free-text fields. A model build,
a shown model document and a snapshot sourced from a model use `kind: model`. An explicit export still
counts under its destination format, and an opened or snapshotted `.xbf` file stays `xbf`. The existing
`build` and `files` event names remain. Schemas 6–7 used `xbf` for both live models and actual XBF files;
those rows remain as sent and cannot be split retrospectively. Earlier schemas and queued batches keep
their original meanings. Deploy this receiver before releasing a schema 8 sender.

Schema 9 tells a snapshot's refusals apart by the part of the request they named (`part`), and names two
failures that are the machine's, not the request's: `no_gl` (no OpenGL context: a Linux with no X display or
GLX, a Windows with no GPU driver) and `no_kernel` (the engine could not start its kernel process). Before it,
a refusal said nothing of what it refused, `no_gl` was `render_error` and `no_kernel` was a refusal
(`bad_request`, `refused`). A row of schema 8 or earlier keeps its key, so a batch sent again keeps its ids.
Deploy this receiver before releasing a schema 9 sender: a `cad-server` release with `SCHEMA = 9` is cut only
after `Deploy API` has run on `main` with it.

Schema 10 is schema 9 with one more reason a CAD tool's call failed (`tool_failure`), the machine's: `no_kernel`,
the engine could start no kernel process for it (no kernel environment, or a process pool the system refused),
which before it was `other`; and that failure's crash (`exception`, type `cad.engine.serve.KernelProcessesUnavailable`)
says which failure it was (`cause`), and is sent once per failure, where before it every call sent one. A crash
without a `cause` is keyed, and so given its row id, as in schema 9. It adds one reason a build failed, the system's:
`outdated`, the CAD server running is of a release before an option the library asked of it, which before it was
`export_error`. And the engine's daemon counts the model builds it answers again, under the same rows 0.8's model
scripts sent: a model build's `failed`, and its `build_failure` rows, from schema 10 count only what the system or
the machine caused, where schemas 5 to 9 from 0.8 counted every failure; a build the person's own script failed is
in `count` alone. Deploy this receiver before releasing a schema 10 sender, as for schema 9: a schema 9 receiver
refuses a schema 10 batch whole.

Schema 11 (from 0.11.12) is schema 10 with the install described by one field, `app`, the agent app
running it (the table above), where schema 10 and earlier sent a combined `channel` (`codex-install`,
`claude-directory`, ...). A schema 11 batch sends no channel, and its rows carry none: PostHog is given no `channel`
for them, and none is made up. The older batches are translated as they arrive, as
before, and keep the value as sent in `legacy_channel`: `claude-directory` is channel `claude`,
`openai-directory` is `codex`, `dev` and `unknown` stay as they are, and every other value (`*-install`, `*-github`,
`claude-desktop`, `agent-plugins`, `cursor-marketplace`) is `default`. The app comes from the batch's MCP client name
by the rule above; where it has none (the browser viewer's page names itself, `cad-viewer`, which is no app), from
the old channel: `claude-desktop` is `claude-desktop`, any other `claude-*` `claude-code`, `codex-*` and
`openai-directory` `codex`, `cursor-*` `cursor`, `gemini-*` `gemini`; else `unknown`. A schema 1 batch named no
channel: its `channel` and `legacy_channel` are `unknown`, and it keeps `source`. Older batches are still checked
against the old list exactly as before, and their rows keep their ids. Events PostHog already stored keep the values
they were stored with: a chart by `channel` counts the releases up to 0.11.11, and a chart by `app` every release.
Schema 11 also adds `arrival` and `update` (the table above), which no earlier schema sends: either in a batch of
schema 10 or earlier is refused. Deploy this receiver before a schema 11 sender reaches anyone: the merge that releases one deploys it. A batch of a schema newer than the deployed receiver reads is answered `503` rather than refused, so a sender that reaches people first keeps its batches until the deploy is live; check that `Deploy API` succeeded after the merge all the same.

Schema 12 is schema 11 with two more events, `install` and `install_failure` (the table above), which no earlier
schema sends: either in a batch of schema 11 or earlier is refused. cad installs the plugin in the agent apps itself
from the release that sends it (`cad plugin install`, which cad's server and the install command run), so each
run is counted, where before the install command did that work and counted nothing. A run says how many apps it found
and how many failed, never which: cad names an agent app only where its install failed (`install_failure`), and an
app it installed in, updated or skipped is never named, so what a computer has installed is not sent. A run that never
reaches a cad that works has no cad to count it: the install command reports where it failed itself, once
(`/v1/install`). An `install_failure` names the app by the install's own key (`claude`, `claude-desktop`, `codex`,
...), which is not the batch's `app` (the app running cad, by another list: `claude-code`): its row and its PostHog
event carry it as `plugin_app`, and `app` stays what it is on every other event. Everything
else is schema 11's, and a row of schema 11 or earlier keeps its key, so a batch sent again keeps its ids. Deploy this
receiver before releasing a schema 12 sender: the merge that releases one deploys it, a schema 11 receiver answers a
schema 12 batch `503` so its sender keeps it until then, and `Deploy API` is checked after the merge all the same.
The `/v1/install` route is deployed before the install command that posts to it, too: until it is, a report gets a
`404` and is lost, as any report the receiver does not take.

Each event of a batch becomes one PostHog event (`src/posthog.mjs`): `tool_used`, `tool_failed`,
`view_used`, `files_shown`, `models_built`, `build_failed`, `snapshots_rendered`, `snapshot_failed`,
`feature_used`, `control_used`, `daemon_health`, `version_arrival`, `cad_updated`, `plugin_installed` (`install`), `plugin_app_failed` (`install_failure`) or, for a crash, `$exception`, which PostHog's error tracking groups into
issues (`$exception_list`: the type, a value that is only ever a dead worker's exit
status, `mechanism.handled`, and raw frames, only text-to-cad's own or the page's own -- never a `vendor-` chunk's -- `in_app`),
with the install id as its distinct id, the batch's context (`session`,
`process`, `version`, `channel` (none for schema 11), `app`, `legacy_channel`, `source`, `platform`, `arch`, `client`, `client_version`,
`presentation`) and the event's own counts as properties, and `country`: the ISO code
Vercel places the request in (`x-vercel-ip-country`), left out where it cannot tell.
PostHog's own location lookup is off for every event (`$geoip_disable`): the receiver
posts from Vercel's servers, and nothing finer than the country is wanted. An event is a
window's counts, so a question adds up a property (`calls`, `count`, `seconds`): it never
counts events. A report of a failed install is no batch's event: it is `install_failed`, under its run's id, one event
a run (`/v1/install` in the table above), so that one is counted.

**A batch sent again counts once.** A schema 5, 6, 7, 8, 9, 10, 11 or 12 row's event carries its row id as PostHog's `uuid`
and its batch's `at` as its `timestamp`, both the same however often the batch comes. PostHog takes
events with the same `uuid`, event name, `timestamp` and distinct id as one
([its docs](https://posthog.com/docs/cdp/common-questions): sent with a uuid, duplicates "are eventually
de-duplicated"), collapsing them as its tables merge, so a query may see both copies until then. The
`timestamp` is always the batch's own, by the sender's clock, so a copy sent however long after keeps the
same key; a clock that is off places its counts where it says. Every earlier schema's event is stamped as
it arrives.

- **Every release keeps counting.** The receiver reads every schema a release
  sends, for as long as that release can still be running: a copy nobody
  updates is counted like a current one. A new schema adds a reader beside the old
  ones in `events.mjs`.
- **Nothing outside the contract is passed on**: unknown fields, tool names that are
  not `cad_*`, names outside an event's vocabulary, free-text strings are refused, in a report of a failed install as
  in a batch. The receiver keeps no IP address, and sends PostHog none.
- **A refusal is logged, and says why.** Every released client is accepted, so a 400 is
  garbage or a bug losing a real person's counts (a newer schema is `503`, logged as
  `telemetry /v1/events deferred 503: ...`, never a refusal), and Vercel's per-status counts are a paid
  feature. Each refusal is one `console.warn` line: `telemetry /v1/events refused 400:
  <rule> (schema N, cadgen X.Y.Z)`, where the rule is a field's path or a vocabulary and
  the release is logged only when it reads as one. Never a value, an install id or a
  service's message (`handler.mjs`: `reasonOf`); an error that is ours is logged by its
  name or string code alone (`TimeoutError`, `posthog_503`). A refused report of a failed install is logged the same
  way, by its rule alone: `telemetry /v1/install refused 400: <rule>`.
- **Never text-to-cad's bug: dropped.** A crash row that matches the drop list
  (`NEVER_OURS` in `src/noise.mjs`) goes no further than the receiver: released clients
  keep sending what a later one learned to leave out, and each would be an issue in
  PostHog with no fix in text-to-cad. A signature goes on the list only when it can never
  be a mistake in text-to-cad's code, never because it is frequent, and in the same change
  the client stops sending it (`failed_output` and `signature` in `cad_server/analytics.py`). Each
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
- **No browser posts.** Every POST must be `application/json` (`415` otherwise) and
  carry no `Origin` header (`403`): text-to-cad posts from Python, and its install command from curl, wget or
  PowerShell too, none of which sends one, and a
  browser sends one with every POST, a form's, `sendBeacon`'s and a no-cors fetch's included.
  There are no CORS headers.
- **The privacy policy describes these events.** A new field, of a batch or of a failed install's report, is a
  change to the docs site's `apps/docs/src/app/privacy-policy/page.tsx` in the same PR.
- **Portable.** `src/handler.mjs` is a plain `fetch(Request) → Response` handler
  over a store (`insert`, `report`, `forget`, `ready`) and a feed (`versions`); `posthog.mjs` is
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
`POSTHOG_PROJECT_ID`. The failed installs (`install_failed`) go to that same project, under the same key. Nothing
in GitHub holds them. A changed value takes effect with
the next deploy, and `Deploy API` checks `api.texttocad.dev/v1/health`, which answers
`503` while any is missing, PostHog refuses the personal key, or the project key is
another project's: the deploy is where the settings are checked, since Vercel keeps
Sensitive values write-only and nothing else can read them back.

Retention is PostHog's: events go after the period its plan keeps them (a year on the
free plan), and the privacy policy says so.

The feed moves an hour after PyPI does: no release deploys anything here, and `latest` never
names a release that cannot be installed yet, or one PyPI took less than an hour ago. A new release is named
between 60 and about 71 minutes after its last file reached PyPI (the hour, then up to five minutes for an
instance to read PyPI again and six for the edge to let go of its last answer). Every installed version's server reads it
(never a development build).
A Vercel Firewall rate-limit rule on `/v1/*` (answering `429`) is recommended: a
real client sends at most once every five minutes per running process, and once more
as it exits, and a computer installing or updating sends one more for each step it
counts (`arrival`, sent at once: its setup, its server's first serve, each hand-over
attempt), and one for each of cad's own updates (`update`), so a per-IP limit well above that turns a flood away at no cost to real
clients. A computer whose install fails posts one report more (`/v1/install`), once. The in-memory limits above
are the first layer and hold per
instance only, so a flood spread over many instances or addresses passes them: the
Vercel Firewall rules on `/v1/forget` and `/v1/health` are the second layer, and `/v1/install`, open to anyone
as they are, wants one beside them.

A client keeps a batch it could not send (offline, a `5xx` while the receiver or
PostHog is down or before it reads the batch's schema, a `404` before it is deployed, a
firewall's `403` or a `429`) and sends
it again, whole and before anything newer, for as long as its process runs, and past that by
the next process that sends; what it counts meanwhile waits for a later batch. A deletion an
opt-out owes is asked for again the same way. It drops only a batch the receiver read and refused
(`400`, `413`, `415` or `422`): that batch would be refused again. A report of a failed install is the exception:
the install command has no cad to keep it, so it is sent once, and lost where it is not taken.

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
warm workers), which computers are stuck on their way to a release and where (`version_arrival` by `version`,
`from`, `route`, `step`, `outcome` and `reason`, installs counted: a setup that failed, a setup with no first serving
after it, a hand-over failed or given up), how cad's own updates go and where they fail (`cad_updated`: installs by
`outcome`, `reason` and `installer`, the failures against the attempts; `plugin` for the install command's run after
one), how the plugin's install goes in the agent apps (`plugin_installed`: installs by `outcome` and `by`, the logo by
`logo` and `colour`, and `seconds`; `plugin_app_failed`: failures by `plugin_app` and `reason`), where the
install command fails before any cad works (`install_failed`: events by `stage`, `outcome`, `code`, `platform`, `uv`
and `by`, each a run and no person; a crash by `type` and `frames`), and where (installs by `country`). A process
nobody used sends nothing.

## Holding a release

The feed's `latest` is what starts every automatic update within the hour, so a release can be held back: the feed
then never names it, and goes on naming the newest release that is not held. A hold is a brake, not a wall: on
releases after 0.11.11 an update the feed starts installs PyPI's newest, so a computer behind the feed's release gets
a held release too, and the install command, `cad update` and `uv tool install cad` read no feed at all. Holding is a
setting of the Vercel project, not a change to the code: `CAD_HELD_RELEASES`, a production environment variable
(plain, not Sensitive, so it can be read back), listing versions separated by commas or spaces, for example
`0.12.0, 0.12.1`. Anything in it that is not a version `X.Y.Z` is ignored, and the function's log says so.

A release is named no sooner than an hour after its last file reached PyPI, and `cadgen` is uploaded last, a
minute or two after the merge's `Publish Release` run reaches PyPI: that hour is the time to hold it. A hold
takes effect at most about six minutes after its redeploy finishes (the new deployment reads PyPI afresh; the
edge lets go of an answer within six minutes), and computers see it at their next check. Better,
hold it before merging the release pull request, and let it go once it is checked.

To hold a release:

1. In the Vercel dashboard, open the project `texttocad-api`, then Settings, Environment Variables.
2. Add `CAD_HELD_RELEASES` for Production (or edit it if it is there) and put the version in it, for example
   `0.12.0`. Save.
3. Redeploy, since a function reads its variables when it is deployed: in GitHub, Actions, `Deploy API`,
   Run workflow on `main` (or `gh workflow run deploy-api.yml --ref main`). The same code is deployed again,
   with the new setting; a new production deployment also clears Vercel's edge cache of the old answer.
4. Check: `curl -s https://api.texttocad.dev/v1/releases` names a release that is not held, in `latest` and in
   `lines` (and `/v1/versions`, which names nothing from 0.12.0 on, likewise).

To let it go: remove the version from `CAD_HELD_RELEASES` (or delete the variable when it is the only one),
save, and redeploy as in step 3. If it is the newest release and an hour old, the feed names it within about six minutes of the redeploy.

What a hold cannot do: take back a release from a computer that has already installed it, since nothing moves
back to an older version; or keep it from a computer that installs or updates by PyPI (above). To pull a release
from everyone, yank it on PyPI as well: uv skips a yanked release unless it is asked for by name. A hold that leaves no release to name (every release held) leaves a new
deployment with no feed, answering `503`, which `Deploy API`'s check refuses: an older release must always be
left unheld.
