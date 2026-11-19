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

The mechanisms its laws constrain are [`engine/README.md`](engine/README.md).

## The shape of the package

```
cad_server/
  engine/                # the engine's server half: the daemon, its supervisor and the services it
                         #   declares (its workers, its render processes), its registry of documents,
                         #   the live models' book, the document cache, the verbs as commands
                         #   (cli), and the engine's README, the mechanisms the laws constrain
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
                         #   (auto_update, auto_update_helper), cad installed globally by a cad run
                         #   from uv's cache (tool_install), the hosted install command as cad
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
- **Integrations**, for a tool's own files that are no document type: `cad mujoco check MODEL.xml`,
  `cad orcaslicer presets KIND`, `cad orcaslicer complete` (`cli/integrations.py`).
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
- **`cad plugin update`**: the hosted install command run in the foreground, its output and exit status the
  command's (`_internal/install_script.py`); where the server began the run, the install command and all it
  started are stopped after 15 minutes and the command exits non-zero. **`cad plugin update auto
  [status|on|off]`**: whether the server runs it once where cad is newer than the release it last ended well for
  (below), off by default, kept by the server as `cad update auto` is. That is all cad knows of plugins.
- **`cad telemetry [status|on|off]`**: the person's answer about usage stats and crash reports.

No command removes cad, and installing it is uv's (`uv tool install cad`, `uv tool uninstall cad`).
Two commands can install it with uv where a computer has none: `cad mcp` run from uv's cache, which
runs that same `uv tool install`, and `cad plugin update`, through the install command it runs.
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
and `plugin.auto_update`, whether the server runs the install command once where cad is newer than the
release it last ended well for, off unless turned on (`cad plugin update auto`; the install command turns it
on wherever cad is there, and tells cad when its run is ending badly, so that run keeps no release).

The server reads the version feed (`updates.py`, at most once an hour, in the background; never waited on):
`api.texttocad.dev/v1/releases`, the newest release (`latest`) and the newest of each major version (`lines`,
`updates.newest_of_major`), kept in the state folder's `releases.json` (an answer with `latest` alone is read with
no `lines`). The releases before this design read `/v1/versions` and keep it in `versions.json` in the same
folder, which they read while a computer is carried over; nothing here reads either, so no `latest` of 0.12.0 or
later reaches them. It asks whether to update as it starts, and as it tends itself: the switch on, this cad a
global install whose installer is found, no update underway (of any release, begun within the hour), and the
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
newer than the release the install command last ended well for, the server runs this cad's own `cad plugin
update` once, detached, its output in `install-command.log` in the data folder; that run stops the install
command, with all it started, after 15 minutes, and so fails (`install_script.run`, as the bridge stops its
own); in a Windows session where `taskkill` is refused, only the install command's own process is ended, and what it
started may run on. It asks at its start and at
each tending once nothing is in flight, so it holds however cad got newer: its own update, a typed `cad
update`, `uv tool upgrade cad` or `pipx upgrade cad` by hand. That release is kept in `install-command.json`
in the data folder, beside the update's own record: written when `cad plugin update` ends with exit status 0
and when the switch is turned on (the install command's last step, right after it put the plugin in place,
wherever cad is there, but written only where its run is ending with exit status 0: one ending badly says so,
`CAD_INSTALL_FAILED=1`; turned on by hand, it means "from this release on"); a run that fails writes none. With no record and the switch on, the record is written for this release and nothing
runs, so a fresh install runs nothing again. A run underway, of any release, begun less than an hour ago, is
waited for, and the server that begins a run asks the record again under the state folder's lock as it keeps
it, so two servers never both begin one. A run that failed, or never said how it ended, is tried again an
hour later at the earliest, at a later start or tending: at most three runs for one release, each an hour or
more after the one before. Never where the update check is off for the process
(`CAD_UPDATE_CHECK=0`, CI, a development build), where `CAD_ENGINE_UPDATE_INSTALLER` names no command (a
test's), for a cad that is no global install, or while the bridge owes its own run of the install command.
The helper and `cad update` run none. `cad doctor` shows the record.

**Each attempt is counted once** (`auto_update.report`), where telemetry is on, as every count is: the server
that runs after it, at its start or a quiet tending, sends one `update` event from the record (the release
before, how it ended, which step failed, the tries, the installer, whether it was typed, and how the install
command's run for a newer cad went: a run begun since the attempt began) and marks the record `reported`. A
failed update is counted by the next server of the old cad that runs, a successful one by the new cad's
server; a new attempt counts the one before it first, whatever begins it (a server, or a typed `cad update`
with no server running, in its own process), and counts it as it stands where the install command's run for
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
and says what it got. It updates cad alone: it never runs the install command. Where no server runs, the
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

## HTTP

The engine's HTTP API is `/api/v1` (`viewer/http_app.py`, its document kinds `viewer/kinds.py`; the routes
are listed in the engine README's **Wire format**): the pages are at the root, and every route they call
is under it.

The viewer exposes `POST /api/v1/local/clipboard` for explicit viewport PNG copies. It uses the same host
and custom-header gates as other mutation routes, limits images to 20 MiB, and delegates native delivery
to `viewer/clipboard.py`. It never reads the clipboard. Unsupported desktop clipboard environments return
an error.
