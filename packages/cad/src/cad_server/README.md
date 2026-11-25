# cad_server

The CAD server and the `cad` command, part of the `cad` distribution: the daemon that builds, keeps and
serves CAD documents, one per computer; the viewer and the CAD app's MCP endpoint on its listener; the
environment the CAD kernel runs in; cad's own update; and the command that runs them all.

Models are written against the library, `cad`, which the server imports without its CAD kernel: the kernel
lives in the environments the server makes, on first need, for models and its own kernel processes,
`cad[build123d]` at the server's own release. `cad run` runs a program as `uv run` does, with cad pinned at
the server's release and the integrations its imports use; a tool's own command an integration declares
(`cad run kicad-cli …`) gets that integration and runs headless; a script that imports `bpy` gets the
blender integration, its environment made on Python 3.13, the one Blender is built for.

The mechanisms its laws constrain are the engine's pages: [`engine/README.md`](engine/README.md) is their index.

## The shape of the package

```
cad_server/
  engine/                # the engine's server half: the daemon, its supervisor and the services it
                         #   declares (its workers, its render processes), its registry of documents,
                         #   the live models' book, the document cache, the verbs as commands
                         #   (cli), and the engine's README and pages (docs/), the mechanisms the laws
                         #   constrain
  cli/                   # the `cad` command: a module per command and per document type
                         #   (`cad <type> <operation>`: document_types, from the library's
                         #   registry), each a shell over the function or parser that does the work
  viewer/                # the engine's HTTP application (engine_app), launcher (main), routes
                         #   (http_app: /api/v1, its document kinds in kinds), files by
                         #   absolute path (backend), a file's catalog row (scanner), the explorer's reads (folders), the model library
                         #   every CAD view shares (recents), a STEP's and an .xbf's serve
                         #   by the engine and in-process document reads (documents), a DXF's
                         #   payload (drawings), a KiCad board's or schematic's plot (plots), a robot's
                         #   (robots), Quick Edit's packets (prompt_files)
  plugin/                # the plugin in the agent apps, and the one place that names an app, a plugin or
                         #   a skill: the table of apps (apps), this computer and its files (computer),
                         #   where the plugin comes from and what is ours (source), what a person's
                         #   terminal is shown (terminal), and one run under its lock (run); reached
                         #   only by `cad plugin`
  mcp/                   # the engine's MCP endpoint: its JSON-RPC vocabulary (protocol),
                         #   engine sessions (http), tools and launches (server), which apps are
                         #   offered tools and how (host: the Codex app alone), open views (views),
                         #   sidebar views shared in memory (sidebar), the viewer routes in-process
                         #   (tunnel), the page (ui), and the viewer link for a call that shows no
                         #   view (browser)
  robot_payload.py       # a robot description resolved for the viewer's page
  drawing_payload.py     # a DXF flattened by ezdxf for the viewer's pane
  jobs.py                # the viewer exports' admission, progress, waiting and cancellation
  analytics.py           # telemetry: usage counts and crash reports, on by default once
                         #   a command has said so, never after a no
  settings.py            # the person's settings: settings.json in the data folder
  language.py            # the language the person chose for the CAD views
  whats_new.py           # the releases whose What's new the person has seen
  updates.py             # the hourly read of the version feed, and PyPI asked for `cad update`
  assets.py              # where the bundled runtime is
  _internal/             # the environments models run in (base, extras, scan), cad's own update
                         #   (auto_update, auto_update_helper, store, selftest), the plugin kept as new as cad
                         #   (plugin_catch_up), cad installed globally by a cad run
                         #   from uv's cache (tool_install), the hosted install command as the bridge
                         #   runs it (install_script), the daemon's entry (engine_daemon,
                         #   engine_host), telemetry's sender, file locks, the one parser every command
                         #   reads its options by (cli_parser) and the one failure contract every
                         #   command fails by (cli_errors); and, kept apart for the bridge from
                         #   0.10.0 to 0.11.11 and deleted with it, what reads that layout
                         #   (installations, releases, proxy, arrival)
  _runtime/              # BUILT: the viewer client and the CAD app page -- produced when
                         #   the wheel is packaged, never committed, never edited
```

## Commands

`cad --help` lists them all.

- **Document types**: `cad <document_type> <operation> <file>`, one id per type as the library's registry
  names it: `cad model export <id>`, `cad xbf export`, `cad step snapshot`, `cad glb inspect`,
  `cad urdf validate`. `model` is a model the engine holds, by its document id, with no file. `export`,
  `snapshot` and `inspect` are shared by every type that has them; every other operation is named for
  what it does -- `dfm`, `interference`, `solve`, `ranges`, `drc`, `erc`, `validate` -- each a check whose
  findings carry a severity, a code and a location (`--json`). `cad <type> --help` lists a type's
  operations, `cad <type> <operation> --help` its options, and a file of another type is refused by name
  (`cli/document_types.py`, each type's module `cli/<type>.py`).
- **Integrations**, for a tool's own files that are no document type: `cad mujoco check MODEL.xml`
  (`cli/integrations.py`). `cad orcaslicer presets|complete` are deprecated: unlisted, still run, and say so.
- **The server**: `cad server start` starts it, detached, and says so; `cad server stop` stops it;
  `cad server status` says whether it runs, its release, its workers and what they build.
  `cad server start --foreground` runs it in this process; `cad server --rotate-token` replaces the page
  token. Nothing else starts the server but `cad mcp`. A command that needs it and finds none says so in
  one line (`the cad server is not running: run cad server start`) and exits 1. On Windows, `cad server
  start` names any uv folder in an app's private copy of AppData, and says to delete it in File Explorer
  (a delete from inside that app does not reach it).
- **`cad mcp`**: the CAD app's stdio transport an agent app starts (Codex's plugin line). It starts the
  server once, as `cad server start` does. Run from uv's cache on a computer with no global cad, it
  installs one first (`_internal/tool_install.py`) and uses that cad's server
  ([the transport's README](../cad_mcp/README.md)).
- **`cad run`**: a program exactly as `uv run` runs it, with cad pinned at this release and the
  integrations its imports use (`_internal/extras.py`, `_internal/scan.py`), in an environment the engine
  makes.
- **`cad viewer`** opens a page of the running server; `cad delete` deletes documents.
- **`cad doctor`**: one read-only report: this cad's release, its Python, where it runs from (the environment,
  the release installed there and who installed it, and the stored release it runs), whether the release that
  runs passes its own check (`store.checks`), its data and cache folders and what `cad cache prune` would free,
  the CAD kernel environment and whether it loads, the integrations, whether the server runs and its release, and
  cad's own update (the switches, whether an update can begin, the feed's newest release, the uv it builds with,
  the last attempt with uv's words, why in plain words, a release held back, a release ready and when cad restarts
  on it, and its log); on Windows, a uv folder
  in an app's private copy of AppData. Under a line that warns, what to do (`auto_update.advice`); where cad or
  its update is not working, a last check, `fix`, says the one thing to do next. It changes nothing. Exit 1 where
  the kernel is installed and does not load, or the release that runs fails its check; `--json` gives the report
  as one document.
- **`cad cache dir|prune|clean`**, as `uv cache` treats uv's: `dir` prints the cache folder, `prune`
  removes what this release cannot use (environments made for other releases, the release folders 0.11.11 and
  earlier left, and the stored releases nothing runs or points at but the one cad's update has ready, which it
  leaves alone while an update is underway), `clean` removes all of the cache, refused while the server runs.
  Only these, cad's update and the server's start delete a past release's files.
- **`cad update`**: cad, and only cad, updated now to the newest release of its major version on PyPI, by the
  server that runs, or by the command itself where none runs (below), even with automatic updates off; where a
  release of a higher major is out, one more line names it. **`cad update --major`**: the newest release of all,
  a new major version included, which never installs itself. It never starts a server, and is refused unless
  this cad is a global install. It waits until the update ends and says how in one line: where it failed, why
  in plain words, what to do (`auto_update.advice`) and where the log is.
  **`cad update auto [status|on|off]`**: whether cad updates itself (below), on by
  default. `on` is refused unless this cad is a global install, and `status` says when it is not. Where a
  server runs, it keeps the switch (`{"op": "auto_update"}`), as it does every other command's writing, so a
  shell whose sandbox may not write cad's state folder needs no permission; with none running, the command
  writes it.
- **`cad plugin install`**: for every agent app found on this computer, the plugin installed or updated with
  that app's own command, from the GitHub repository's `latest` branch, then our older copies there removed;
  one line per app (`plugin/`: `apps.py` is the one table of apps). It is the one command that installs the
  plugin, and it installs and nothing else: it never changes `cad plugin update auto` (the hosted install command
  turns that on, below). It keeps this cad as the release the plugin is up to date for only where every app it
  found went well (no app failed; none found counts) and this cad is the computer's global install (a cad run from anywhere else, as the newest release from
  uv's cache, keeps none: below). In a person's
  terminal it builds the CAD logo first and keeps a live line under the apps' lines; anywhere else the plain
  lines. No options. Exit status 0 where it ended well, 1 where every app it found failed, 2 for a command line
  it does not take, 75 where another run was going and a server began this one, 124 where a server's run was
  stopped at its deadline. Where `CAD_PLUGIN_REPORT` names a file, each app's status is written there as it ends
  (`{"schema": "cad plugin install/1", "apps": {...}}`). It is what the server runs after cad got newer (below);
  where this release's server began it (`CAD_PLUGIN_SERVER_RUN`, which no released cad sets), it has 15 minutes:
  each command it runs is stopped with all it started when they are up, no further app is begun, and it exits
  non-zero; one that has not ended a minute past them, because a step of it never came back, is ended whatever it
  is doing (exit status 124). Any other run has no deadline and leaves the server's record of its run alone: the
  name 0.11.12 and 0.11.13 give their server's run, `CAD_INSTALL_ATTEMPT`, is not read. **`cad plugin update`**:
  the same command under the name 0.11.12 and 0.11.13 gave it, run exactly as `install` is, and listed by no
  help. One run at a time: a run holds a lock in the data folder for the whole run, and a second run waits for
  the first, unless a server began it. It runs no install command, no `cad update` and no `cad plugin`. A run a person reads says the telemetry notice first, as every command does (one a person
  typed, or one the hosted install command handed over in a terminal; never one a server began, whose output is
  a log's, nor one reached from an install command cad itself started), and each run is counted as it ends
  (Telemetry, below). **`cad plugin update auto [status|on|off]`**: whether the server runs `cad plugin install`
  once where cad is newer than the release the plugin is up to date for (below), off by default, kept by the
  server as `cad update auto` is; it installs nothing. The hosted install command turns it on as its last step,
  with `CAD_INSTALL_FAILED=1` where the plugin's step ended non-zero or named an app as failed (then it keeps no
  release), as 0.11.12 and 0.11.13 read it too. `cad plugin` is the one command that reaches `plugin/`, and that package the
  one place in cad that names an agent app, a plugin or a skill.
- **`cad telemetry [status|on|off]`**: the person's answer about usage stats and crash reports.

No command removes cad, and installing it is uv's (`uv tool install cad`, `uv tool uninstall cad`).
One command can install it with uv where a computer has none: `cad mcp` run from uv's cache, which
runs that same `uv tool install`.
Every command that destroys asks first (`cad delete`,
`cad server --rotate-token`: a terminal's `(y/N)`, else `--yes`; `_internal/consent.py`).

Kept only for releases 0.10.0 to 0.11.11, and deleted with that bridge (`cli/setup.py`): `cad setup
--engine-update`, which those releases' updater runs on the new release; plain `cad setup`, which a `cad
update` typed on those releases runs, the install command in install mode; and the hidden short forms
`cad status` and `cad stop`, which their skill text uses. On a computer whose apps got text-to-cad only
from a store, the bridge moves cad alone, installs it with uv, and runs no install command.

Run, and never listed by `cad --help`, because programs rather than people use them: `cad serve`, which
serves a document over HTTP and prints its URL, and `cad requirement [INTEGRATION ...]`, which prints the
exact requirement a Python of a program's own installs this release's cad by (`cad[build123d]==<release>`).

A command the skills used keeps working for at least 30 days after the skills stop using it.

On Windows, what a command writes to a pipe or a file is UTF-8, and so is what the program `cad run` runs
writes (a console is left as it is, as is every stream elsewhere); Windows PowerShell 5.1 decodes a
program's piped output with the console's code page (`[Console]::OutputEncoding`), so an accent in a
PowerShell pipeline is still wrong there, and that is PowerShell's to set.

## cad's own update

`_internal/auto_update.py`. **The rule**: cad installs by itself any newer release of its own major version,
and never a release of a higher major, which a person asks for (`cad update --major`). Only a global install
updates itself, one whose environment `uv tool install cad` or `pipx install cad` made, and both the same way,
with uv. Two switches in the person's settings: `auto_update.on`, whether cad updates itself, on unless turned
off (`cad update auto`); and `plugin.auto_update`, whether the server runs `cad plugin install` once where cad
is newer than the release the plugin is up to date for, off unless turned on (`cad plugin update auto`).

**The store** (`_internal/store.py`). No file of an installed cad is ever changed: its environment, its `cad`
command and the installer's record of it stay as they were made. A newer release is installed whole into a
folder of its own in the state folder's `store`, a stored release, named for the release and for what its compiled
files are built for (`store.built_for`), made by `uv pip install --target` for the environment's interpreter, its
files linked from uv's cache where the file system allows, its marker (`cad-store.json`) written last. Then one
small file written whole, the pointer, names it: `store/pointer-<checksum of the environment's folder>.json`. The pointer is in the state folder, never in the
environment: on Windows an environment lies under AppData, where a file made by a process an app package
started (a server an agent app's shell started) lands in a copy only that app sees.

**`_cad_release`**, the one module outside the packages, reads the pointer: the wheel's `cad.pth` imports it as
each interpreter of the environment starts. Where the pointer was written for this very install of cad (the
environment, the interpreter, and the time and size of the installed cad's `RECORD`), it puts the stored release
on the import path in place of the environment's own packages, reads its `.pth` files and holds its marker open
for the life of the process; else the environment runs its own packages. So a process keeps the release it
started with, and installing cad again always runs what was installed. No update replaces this module, so what
it reads never changes: where the state folder is, the pointer's name and keys, the marker's name, and that a
stored release is one folder of the import path.

**In use.** A release is removed only where no process holds its marker: on Windows by renaming its folder,
which the system refuses while a file in it is open; elsewhere by taking the marker's lock, which each process
that runs it shares. The tidying (`store.clean`) keeps what a pointer names and the release it ran before, and
removes pointers that mean nothing (once ten minutes old), builds that died (an hour old) and every other release
no process runs but the one that is ready (`auto_update.kept`, below). The worker tidies as it ends; a server as it
starts, and `cad cache prune`, where no attempt is underway.

**When** (`due`). The server reads the version feed (`updates.py`, at most once an hour, in the background):
`api.texttocad.dev/v1/releases`, `latest` and the newest of each major (`lines`), kept in the state folder's
`releases.json`. The releases before this design read `/v1/versions` into `versions.json`; nothing here reads
either. An update is due where the switch is on, this cad is a global install, no attempt is underway, of any
release, and the feed names a newer release of this cad's major: exactly that release, or, where it names none
of this major and its `latest` is of a higher one, PyPI's newest of this major (`cad>=<this>,<<major + 1>`). Not
where the environment runs it already under this older server (`stale`: `cad server start` replaces the server),
nor for a release whose last automatic try ended `start_failed` (`given_up`: a server restarting for nothing
once a day is worse than waiting; `cad doctor` says it is held back, and `cad update` tries it), nor for the
release that is ready already. The server asks as it tends itself with nothing in flight (no command run for a
minute, or nothing since it started), and `cad server start` asks when its start fails. One due that cannot begin
(`blocked`: `no_switch`, the environment does not read the pointer or its cad is damaged; `no_installer`, no uv)
is counted once for its release.
`CAD_UPDATE_CHECK=0` turns the check off for a process; with no answer from the feed, nothing happens. A global
install behind a release of its major for three days, the switch on, says so at most once a day on stderr after
a command's output (`auto_update.notice`, kept in `auto-update-notice.json`; not after `cad update`, `cad
doctor`, `cad run`, `cad plugin`, the server's commands, help or `--json`): both releases, what to do, and why where an attempt failed or none can begin
(`advice`: the line `cad doctor` and a failed `cad update` give).

**The schedule and the record.** A release that does not install is tried again an hour after its first
automatic try, then 2, 4, 8 and 16 hours, then a day after each (`next_try`), counted for that release in
`tried` in the state folder (the eight tried last), so a newer release starts afresh; no automatic update begins
where four attempts, of any release, began in the last day; a person's own (`cad update`, the button: `asked`)
counts among them and spends no try. The attempt is kept in `auto-update.json`, begun in one step under the state
folder's lock (nothing underway, then this one underway), so two servers begin one; every write of it that another
process may make at the same moment holds that lock (the claim, the worker's beat, its decision to end `ready`,
its last write, `dismiss`, `report`). Its worker beats in it every minute; one silent for 20 minutes is `lost`. It
ends `installed`, `current` or `failed`, with `detail`, `restored`, `started` and, where it did not install what
it was for, `cause`, one word of a closed list (`auto_update_helper.CAUSES`), said in plain words by
`auto_update.SAID` -- or `ready`, below.

**Ready, then the switch.** The server's own update only gets the release ready: its record says `"switch": false`,
and its worker, once the release is built and checked, ends it `ready` (nothing points at it; no event is counted,
and no cause) in one step under the lock, so no server restarts under a viewer page someone is looking at. A release
is ready (`auto_update.ready`) where the last record says so, it began from the release that runs, and its folder is
still a stored release; the tidying keeps it. The switch to it begins by itself, where automatic updates are on, the
check is on and the feed as last read still calls for that release (`auto_update.restart`): as the server starts
(`daemon.main`, before it serves anything: that start stands aside, and its starter waits for the next release's
server; never for `--foreground`, nor a start that names its port, `--port`), once nothing at all has been asked of
the server for an hour (`ALONE_SECONDS`, a page's requests too: `Daemon.last`; a hidden page asks nothing), or, the
release ready a day, at the first minute with no command. A person's ask (`cad update`, the button) switches to it
at once, even where PyPI cannot be reached, and one made during the silent build makes that attempt theirs
(`"switch": true, "asked": true`, in the step that joins it). The switch resumes the attempt: a new record at
`switching`, its tries the ready one's, held by no schedule and counted among none of the day's attempts. A newer
release takes the record's place as any attempt does, and the one that was ready is tidied.

**The worker** (`_internal/auto_update_helper.py`), started detached as `python -P -m
cad_server._internal.auto_update_helper` by the environment's interpreter, so it runs the current release:

1. **Build** (`phase`: `building`, kept as uv builds). A release stored already is run once first
   (`store.sound`) and used where it runs; else it is built (and one that does not run replaced, or, where a
   process still runs it, the attempt ends `in_use`), with the uv the release that runs carries (`carried_uv`, beside its `uv` package; else the
   person's), in a `.building-` folder; run once by the environment's interpreter with that
   folder and the standard library alone on its path (`store.verify`: the release's own check,
   `_internal/selftest.py`, says `cad <release>` last); judged (not older, and but for `--major` of the same
   major; the same release is `current`); named (`store.publish`). Nothing that runs is touched: uv stopped at
   its 15 minutes leaves no release. An attempt that only gets its release ready ends here, `ready`.
2. **Switch** (`switching`, kept first). The pointer read, for the way back. A server that answers is drained:
   asked to stop once nothing is in flight, and waited for ten minutes at most (`client.drain`), after which
   the next start replaces it. The pointer written (`store.point`), then `cad server start` where a server ran
   or one is wanted, which must leave a server of the release, else `cad --version`, which must name it. A `cad`
   command that finds no server meanwhile, or an older one, waits for the next (`client.SWITCHING`, 30 s), and a
   server of the release being left starts none in the next one's place (`auto_update.leaving`): its starter
   launches nothing more meanwhile and waits for the server that answers (`client.LEAVING`), since a daemon
   launched then would run whichever release the pointer names at that instant.
3. **The way back** (`restoring`, kept once the pointer is back). Where that fails: the pointer put back as it was read (`store.restore`), a server of the
   new release that came up late stopped, the release before's server started where one is wanted; cause
   `start_failed` (the server) or `broken` (the command), `restored` where the release before runs. Where the
   pointer could not be written, the cause is the write's.

No step is tried twice in a run. A build's cause is told from uv's words and which of uv's settings are there,
by name (`cause_of`). Each command, its status, time and last 64 KiB of output go to `auto-update.log` in the
state folder (the attempt before's, `auto-update.1.log`), which nothing sends. A worker that raises leaves the
attempt underway, `helper_crash`. Forward only: nothing moves to an older release.

**The update button** (`auto_update.button`, `GET /api/v1/server`'s `cadUpdate`; `POST /api/v1/local/update`).
Where cad can update itself, whatever the switch says, the viewer and the CAD app show it while the feed names a
newer release of this cad's major, with the attempt of this release underway that restarts the server (and its
`phase`; a silent build shows nothing), `ready` and the release where one is ready and the feed calls for it (a
click only restarts the server), or, where the last did not install what it was for and cad is still behind, its
`cause` and the worker's log, said in the alert
card until another attempt begins or the person puts it away (`dismissed`, `auto_update.dismiss`). A click is
`cad update` (`Daemon.update`): PyPI asked, the attempt underway joined, else one begun at once. The route is
refused where cad cannot update itself, saying why, and sits behind the credentials and guard header of every
route that changes something. It shows nothing of an attempt from another release (the one that installed this
cad), nor a failure to a server older than its environment (`stale`): a click restarts the server on it.

**The plugin catches up** (`_internal/plugin_catch_up.py`). Where `plugin.auto_update` is on and this cad is
newer than the release the plugin is up to date for, the server runs this cad's own `cad plugin install` once,
detached, its output in `install-command.log` in the data folder, the run named by `CAD_PLUGIN_SERVER_RUN`. It
has 15 minutes: each command it runs is given what is left of them and stopped with all it started, no app is
begun past them, and it exits non-zero (in a Windows session where `taskkill` is refused, only the command's own
process is ended). A hard stop (`plugin_catch_up.HardStop`, a thread of its own) ends a run not ended a minute
past its 15: counted as stopped, its record closed, exit 124, its lock freed. The server asks at
each tending once nothing is in flight, from a minute after its start (`START_SECONDS`: the install command that
just updated cad goes on to the plugin in that minute), never while a run holds the lock, so the rule holds
however cad got newer: its own update, `cad update`, `uv tool upgrade cad` or `pipx upgrade cad`. The release is
kept in `install-command.json` in the data folder: written when `cad plugin install` ends with every app it
found gone well, and when the switch is turned on (`cad plugin update auto on`, the hosted install command's last
step; with `CAD_INSTALL_FAILED=1`, where the plugin's step went badly, none; turned on by hand, "from this
release on"). Only the computer's global install writes it: a cad run from anywhere else (the newest release
from uv's cache) keeps none, since its release may be of a major the installed cad never reaches. A run of the global install that went badly marks its release as owed a run (`owed`), which the server
makes for that release or a later one. With no record, no mark and the switch on, the record is written for this
release and nothing runs. A run underway, of any release, begun less than an hour ago, is waited for, and the
server asks the record again under the state folder's lock as it begins one. A run that failed, where any app
failed, or that never said how it ended, is tried again an hour later at the earliest: at most three runs for
one release, counted for that release. Never where the update check is off for the process (`CAD_UPDATE_CHECK=0`,
CI, a development build), where `CAD_ENGINE_UPDATE_INSTALLER` is set and empty (a test's way to say the server
runs nothing by itself), for a cad that is no global install, or while the bridge owes its own run of the hosted
install command. The worker and `cad update` run none; `cad doctor` shows the record. One run at a time:
`cad plugin install` holds `install-command.lock` in the data folder from start to end (tried for two seconds
first); a second run waits, but one a server began exits 75 and is tried again an hour later. cad's own update
does not wait for a run: a run keeps the release it started with.

**Each attempt is counted once** (`auto_update.report`), where telemetry is on: the server that runs after it,
at its start or a quiet tending, sends one `update` event from the record (the release before, how it ended,
which step failed, where it did not install a newer cad its `cause` -- `already` where the environment held the
release already, `none` where the record names none --, the tries, the installer, whether it was typed, and how
the server's run of `cad plugin install` for a newer cad went) and marks the record `reported`. An attempt whose
worker has been silent for 20 minutes (an hour, for a record of a release before the beat) is counted `lost`. An
automatic update due that cannot begin is counted `blocked`, with its cause, once for each release the feed calls
for (`auto-update-blocked.json` in the data folder). Never uv's words, a path or a setting's value. A failed
update is counted by the next server of the old cad, a successful one by the new cad's; a new attempt counts the
one before it first, whatever begins it, as it stands where its `cad plugin install` run is still underway.

`cad update` asks the server that runs (`{"op": "update"}`, which an agent's sandboxed shell may send with no
permission): it asks PyPI for the newest release of this cad's major that is not yanked (`updates.pypi`, 5 s at
most; `CAD_PYPI_URL` names a stand-in), says `cad X is the newest release` where none is newer (`the newest 0.x
release` where a higher major is out, with one more line naming it, `cad update --major` and the migration
guides' address), and otherwise begins the same update at once, with the switch off too and whatever the
schedule says (it spends no automatic try, and counts among the day's four), or joins the one underway, another
process's too. `cad update --major` (`{"op": "update", "major": true}`) builds PyPI's newest of all, never below
the release that runs; the next automatic update keeps to the new major. Where uv's own record keeps the install
below the major it then runs (`outgrown`), it says so in one more line, with `uv tool install --force cad`. Where PyPI cannot be reached it builds
all the same, or, where a release is ready and PyPI names it or none, only switches to it. It waits for the end, up
to 30 minutes, saying each step once on stderr (`cad: installing cad X beside cad Y`, then `cad: restarting the cad
server on it, once nothing is running`, or `cad: switching to it` with no server; for a release that was ready,
`cad: restarting the cad server on cad X, installed beside cad Y, once nothing is running` alone). It never runs
`cad plugin`. Where no server runs, the command judges and begins the update itself, and its worker starts no
server: an update typed with none running leaves none running. In a shell whose
sandbox cannot start a server, it says so and updates nothing.

## Folders

The data folder (the state folder, `cad.engine.places.state_dir`) is `cad` in the platform's place for state (`~/Library/Application Support/cad` on macOS,
`~/.local/state/cad` on Linux and Windows) or the folder `CAD_STATE_DIR` names: settings, Recents, the
documents' records, the page token and port, the telemetry spool and the feed's last answer. The cache
folder is `~/.cache/cad`, on Windows too, or the folder `CAD_CACHE_DIR` names: the documents' bytes, the
environments, bytecode and the integrations' private homes, all made again on demand. On Windows neither
is in the local application data, which Windows virtualizes for every process an app package (the Claude
desktop app) starts. A release reads what the release before wrote and migrates it on first touch, once
(`cad.engine.identity.migrate`); nothing in the cache is converted.

Coming from 0.7 or 0.8 (named cadgen): their caches (`~/.cache/cadgen`, `%LOCALAPPDATA%\cadgen`) and the
state files only they wrote are not read or removed by anything here; `cad doctor` says where they are,
with their size, and the person deletes them once no such release is left.

## Telemetry

`analytics.py` describes each batch by the release that counted it and `app`, the agent app that ran it,
detected (the MCP handshake's client name, else the markers an app sets in its shell, else `unknown`). A
no, wherever it is said (`cad telemetry off`, the app menu's switch), is kept in the settings and asks the
receiver to delete what was sent under the install id.

**A run of `cad plugin install` is counted as it ends** (`cli/plugin.py`'s `_count`,
`analytics.install`), where telemetry is on, as every count is. One `install` event: who began the run (a
person, the hosted install command handing over, cad's server), how it ended (`ok`: well; `failed`: every app it
found failed; `stopped`: its deadline stopped it before it was done; `busy`: another run was going and this one
ran nothing), what its terminal showed of the logo and in which colours, its whole seconds, how many agent apps it
found and how many of those failed: counts, never which apps. And one `install_failure` event for each app
where the run failed, and for no other: the app by cad's own key for it in `plugin/apps.py`, why in one word
chosen where it failed (`timeout`, `command`, `network`, `exception`, `other`), and its whole seconds. cad
names an agent app only where its install failed, so which apps a computer has is never sent. Never a path, a
version of an app's, a line an app printed or an error's message. Whether a run that ended ended well is read from its apps where they are counted,
so the two never disagree: it is `failed` exactly where every app it found failed, and `ok` anywhere else. A run
its deadline stopped says what it had found by then, whatever that was.
The run is kept as one line in a file of its own beside the settings (`telemetry-installs.jsonl`, which no
sender of an earlier release takes) and a sender is started at once, detached, as for a version's arrival and
for cad's own update: the run may be the last thing cad does on the computer for a long while. Nothing of it
is kept for a run that began before the person was told, and a crash of the command is reported as any
command's is.

## HTTP

The engine's HTTP API is `/api/v1` (`viewer/http_app.py`, its document kinds `viewer/kinds.py`; the routes
are listed in the engine README's **Wire format**): the pages are at the root, and every route they call
is under it.

The viewer exposes `POST /api/v1/local/clipboard` for explicit viewport PNG copies. It uses the same host
and custom-header gates as other mutation routes, limits images to 20 MiB, and delegates native delivery
to `viewer/clipboard.py`. It never reads the clipboard. Unsupported desktop clipboard environments return
an error.
