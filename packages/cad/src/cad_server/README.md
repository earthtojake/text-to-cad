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
                         #   payload, drawn in a kernel process (drawings), a KiCad board's or schematic's plot (plots), a robot's
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
  jobs.py                # the viewer exports' admission, progress, waiting and cancellation
  analytics.py           # telemetry: usage counts and crash reports, on by default once
                         #   a command has said so, never after a no
  settings.py            # the person's settings: settings.json in the data folder
  language.py            # the language the person chose for the CAD views
  whats_new.py           # the releases whose What's new the person has seen
  updates.py             # the hourly read of the version feed, and PyPI asked for `cad update`
  assets.py              # where the bundled runtime is
  _internal/             # the environments models run in (base, extras, scan), cad's own update
                         #   (auto_update, auto_update_helper), the plugin kept as new as cad
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
- **`cad doctor`**: one read-only report: this cad's release, its Python and where it is installed, its
  data and cache folders and what `cad cache prune` would free, the CAD kernel environment and whether it
  loads, the integrations, whether the server runs and its release, and cad's own update (the switches,
  whether this cad is a global install and by which installer, whether that installer is found, the last
  attempt; on Windows, a uv folder in an app's private copy of AppData). It changes nothing. Exit 1 when the
  kernel is installed and does not load; `--json` gives the report as one document.
- **`cad cache dir|prune|clean`**, as `uv cache` treats uv's: `dir` prints the cache folder, `prune`
  removes what this release cannot use (environments made for other releases, and the release folders
  0.11.11 and earlier left), `clean` removes all of it, refused while the server runs. Nothing else of cad
  deletes a past release's files.
- **`cad update`**: cad, and only cad, updated now to the newest release of its major version on PyPI, by the
  server that runs, or by the command itself where none runs (below), even with automatic updates off; where a
  release of a higher major is out, one more line names it. **`cad update --major`**: the newest release of all,
  a new major version included, which never installs itself. It never starts a server, and is refused unless
  this cad is a global install. It waits until the update ends and says how, in one line, on Windows too.
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
updates itself: a cad whose environment an installer made (`uv tool install cad`: uv's receipt in its
environment). Each installer is one entry (`INSTALLERS`): its upgrade command inside the major, its command
to the newest of all, the command that puts a release back, and where its launchers are. Two switches in the
person's settings: `auto_update.on`, whether cad updates itself, on unless turned off (`cad update auto`);
and `plugin.auto_update`, whether the server runs `cad plugin install` once where cad is newer than the
release the plugin is up to date for, off unless turned on (`cad plugin update auto`, which the hosted install
command runs as its last step).

The server reads the version feed (`updates.py`, at most once an hour, in the background; never waited on):
`api.texttocad.dev/v1/releases`, the newest release (`latest`) and the newest of each major version (`lines`,
`updates.newest_of_major`), kept in the state folder's `releases.json` (an answer with `latest` alone is read with
no `lines`). The releases before this design read `/v1/versions` and keep it in `versions.json` in the same
folder, which they read while a computer is carried over; nothing here reads either, so no `latest` of 0.12.0 or
later reaches them. It asks whether to update as it starts, and as it tends itself: the switch on, this cad a
global install whose installer is found, no update underway (of any release, begun within the hour), no run of
`cad plugin install` going (its lock held: an update would replace the environment's
files under it), and the
feed's newest release of this cad's major newer than this one. Where the feed names none of this major, its
`latest` where that is of this major; where `latest` is of a higher major, the bounded upgrade runs all the same,
tried at most twice for one `latest`. Then, once nothing is in flight (at a start, at once; otherwise once
nothing has run for a minute), the update begins in one step across processes (under the state folder's lock:
nothing underway, then the attempt kept as underway, so two servers that start at once begin one), and a
detached helper that is neither the `cad` executable nor run from cad's environment
(`_internal/auto_update_helper.py`) stops the server, runs the installer's upgrade inside the major, `uv tool
install --upgrade "cad>=<this release>,<<its major + 1>"` (pipx: `pipx upgrade cad --pip-args=...`, the same
range), worked out from the release that runs each time (no Python flags: the environment keeps its
interpreter; tried again on failure, and the previous release put back where a failed install left no `cad`),
and starts the server with whatever cad is there. uv keeps the range, so a person's own `uv tool upgrade cad`
stays inside the major too. The helper takes the result only where it is of the same major and not older:
newer is `installed`, the same release `current`; anything else is a failure. The record keeps the release the
upgrade got. On
Windows uv cannot remove a `cad.exe` that is running, but it can rename one, so the helper renames each
`cad.exe` of the tool aside before uv runs and puts a copy back. For that to work, cad takes its launcher
off `sys.path` as it starts (`__init__.py`), so it never holds the file open. One release is tried at most
twice, never twice within an hour. `cad server start` asks too when the start fails, so a release whose
server cannot start still updates. Forward only: nothing moves to an older release, and a start joins a
running server of a newer release rather than replacing it. With no answer from the feed, nothing happens.
`CAD_UPDATE_CHECK=0` in a process's environment turns the check off for it.

**The plugin catches up** (`_internal/plugin_catch_up.py`). Where `plugin.auto_update` is on and this cad is
newer than the release the plugin is up to date for, the server runs this cad's own `cad plugin
install` once, detached, its output in `install-command.log` in the data folder, the run named by
`CAD_PLUGIN_SERVER_RUN`; that run has 15 minutes: each
command it runs is given what is left of them and stopped with all it started, no app is begun past them, and
it exits non-zero (in a Windows session where `taskkill` is refused, only the command's own process is ended,
and what it started may run on). That deadline is asked between the run's steps, so the command carries a hard
stop too (`plugin_catch_up.HardStop`, a thread of its own): a run that has not ended a minute past its 15,
because a step never came back, has its record closed as a stopped run's, is counted as stopped, and its
process exits with 124 there and then, waiting on nothing, which frees the lock it held for cad's own update
and for every run that waits. The server asks at each tending once nothing is in flight, from a minute
after its start (`plugin_catch_up.START_SECONDS`: the install command that just updated cad, restarting the
server, goes on to the plugin in that minute) and never while a run holds the lock (no try spent), so the
rule holds however cad got newer: its own update, a typed `cad update`, `uv tool upgrade cad` or `pipx upgrade
cad` by hand. That release is kept in `install-command.json`
in the data folder, beside the update's own record: written when `cad plugin install` ends with every app it
found gone well (exit status 0 and no app failed) and when the switch is turned on (`cad plugin update auto on`,
the hosted install command's last step, right after the plugin is in place, but written only where every app
went well: otherwise that command says so with `CAD_INSTALL_FAILED=1` and writes none; turned on by hand, it
means "from this release on"); a run that fails, or where any app failed, writes none: the plugin is up to date
for a release only where every app found went well. Only the computer's global install of cad writes it: a cad run from anywhere else (the newest
release from uv's cache, which the hosted install command runs for an installed cad that has no `cad plugin
install`) does the work and keeps no release, since its own may
be of a major the installed cad never reaches, and this cad's server would then never catch up again. A run of the
global install that did not go well marks its release as owed a run (`owed`, dropped by one that goes well),
which the server makes for that release or a later one, `for` or none. With no record and no such mark and the
switch on (turned on by hand, or no run ever made), the record is written for this release and nothing runs. A run underway, of any release, begun less than an hour ago, is
waited for, and the server that begins a run asks the record again under the state folder's lock as it keeps
it, so two servers never both begin one. A run that failed, where any app failed (its exit status 0 all the
same), or that never said how it ended, is tried again an hour later at the earliest, at a later tending: at
most three runs for one release, each an hour or more after the one before, counted for that release (a server
of another release beside it, left running in another engine folder, never sets the count back), so an app
broken for good costs at most three runs in the background for each release. Never where the update check is
off for the process (`CAD_UPDATE_CHECK=0`, CI, a development build), where `CAD_ENGINE_UPDATE_INSTALLER` is set and empty (a
test's way to say the server runs nothing by itself; `cad plugin install` reads no such variable), for a cad
that is no global install, or while the bridge owes its own run of the hosted install command: until a run of it
installs cad, which ends it whatever the apps did, an app that failed there left to this rule.
The helper and `cad update` run none. `cad doctor` shows the record. One run at a time: `cad plugin install`
holds `install-command.lock` in the data folder from start to end; a second run waits for it, but one a server
began, which exits 75 and is tried again an hour later. A run tries for the lock for
two seconds first: whether a run is going can only be asked by trying for the lock, so a server that asks holds
it for an instant, which is no run. While it is held,
cad's own update is not due, and a typed `cad update` is refused in one line.

**Each attempt is counted once** (`auto_update.report`), where telemetry is on, as every count is: the server
that runs after it, at its start or a quiet tending, sends one `update` event from the record (the release
before, how it ended, which step failed, the tries, the installer, whether it was typed, and how the server's
run of `cad plugin install` for a newer cad went: a run begun since the attempt began) and marks the record `reported`. A
failed update is counted by the next server of the old cad that runs, a successful one by the new cad's
server; a new attempt counts the one before it first, whatever begins it (a server, or a typed `cad update`
with no server running, in its own process), and counts it as it stands where the `cad plugin install` run for
it is still underway (`underway`).

`cad update` asks the server that runs (`{"op": "update"}`, which an agent's sandboxed shell may send with no
permission): it asks PyPI for the newest release of this cad's major that is not yanked (`updates.pypi`, 5 s
at most; `CAD_PYPI_URL` names a stand-in), says `cad X is the newest release` where none is newer (`the newest
0.x release` where a higher major is out), and otherwise begins the same update as soon as nothing is in
flight, with the switch off too and past the limits on automatic tries (it counts as a try all the same), or
joins the one underway, another process's too. Where a release of a higher major is out it adds one line
naming it and `cad update --major`, with the migration guides' address; `cad doctor` says the same, and `cad
update auto` with no argument. `cad update --major` (`{"op": "update", "major": true}`) begins the update to
PyPI's newest of all, never below the release that runs, by `uv tool install --upgrade "cad>=<installed>"` (pipx:
`pipx upgrade cad --pip-args=cad>=<installed>`), the floor alone in place of the range uv or pipx kept;
the next automatic update keeps the new major's. Where PyPI cannot be reached it runs the upgrade all the same
and says what it got. It updates cad alone: it never runs `cad plugin`, and is refused in one line
while a run of `cad plugin install` is going. Where no server runs, the
command judges and begins the update itself, in its own process, and the helper starts no server after it:
an update typed with none running leaves none running. In a shell whose sandbox cannot start a server, it
says so and updates nothing.

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
