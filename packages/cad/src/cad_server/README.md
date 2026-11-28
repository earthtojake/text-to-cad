# cad_server

The CAD server and the `cad` command, part of the `cad` distribution: the daemon that builds, keeps and
serves CAD documents, one per computer; the viewer and the CAD app's MCP endpoint on its listener; the
environment the CAD kernel runs in; cad's own update; and the command that runs them all.

Models are written against the library, `cad`, which the server imports without its CAD kernel: the kernel
lives in the environments the server makes, on first need, for models and its own kernel processes,
`cad[build123d]` at the server's own release (the kernel's one, the base). `cad run` runs a program as `uv run` does, with cad pinned at
the server's release and the integrations its imports use; a tool's own command an integration declares
(`cad run kicad-cli …`) gets that integration and runs headless; a script that imports `bpy` gets the
blender integration, its environment made on Python 3.13, the one Blender is built for.

The mechanisms its laws constrain are the engine's pages: [`engine/README.md`](engine/README.md) is their index.

## The shape of the package

```
cad_server/
  engine/                # the engine's server half: the daemon, its supervisor and the services it
                         #   declares (its workers, its render processes), the library and the state
                         #   folder's own (library, state), the live models' book, the verbs as commands
                         #   (cli), and the engine's README and pages (docs/), the mechanisms the laws
                         #   constrain
  cli/                   # the `cad` command: a module per command and per verb (`cad <verb> FILE`:
                         #   verbs, over what each document type does for it, document_types,
                         #   from the library's registry), each a shell over the function or
                         #   parser that does the work; the one table of the spellings it had
  viewer/                # the engine's HTTP application (engine_app), launcher (main), routes
                         #   (http_app: /api/v1, its document kinds in kinds), files by
                         #   absolute path (backend), a file's catalog row (scanner), the folders a person opened as
                         #   projects, each shown a folder at a time (projects), the library's rows
                         #   every CAD view shares (recents), a STEP's and an .xbf's serve
                         #   by the engine and in-process document reads (documents), a DXF's
                         #   payload, drawn in a kernel process (drawings), a KiCad board's or
                         #   schematic's plot (plots), a robot's (robots), a document's view bundle,
                         #   its page's reads written as a folder (bundle)
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
  sharing.py             # `cad share`'s and `cad import`'s client of the share service: a share's names and links,
                         #   a shared file's files (a model's .xbf and its closure's), the cad-share/2 packs of the
                         #   files a share lacks, the service's API (urllib, in the command's own process), a
                         #   share's zip written into a folder, a share's link as the name of this computer's copy
                         #   of it, and what is kept: the agreement, the setting, each share and import in its
                         #   file's entry of the library, and what a share keeps in its file's folder of the cache
  language.py            # the language the person chose for the CAD views
  whats_new.py           # the releases whose What's new the person has seen
  updates.py             # the hourly read of the version feed, and PyPI asked for `cad update`
  notices.py             # the project's notices the feed carries: said after a command, in `cad doctor`
                         #   and to the viewer (`cadNotices`)
  assets.py              # where the bundled runtime is
  _internal/             # the environments models run in (base, extras, scan), cad's own update
                         #   (auto_update, auto_update_helper),
                         #   the plugin kept as new as cad
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

- **The verbs**: `cad <verb> FILE`, the file's type by its suffix as the library's registry names it:
  `cad export SRC DST [--as KIND]` (one destination, as `cp` writes one: a file by its suffix, or of a KiCad
  board or schematic a folder or a `.zip` too, `--as` naming the kind where DST cannot), `cad inspect FILE [REF]`
  (what a document holds; a robot description's conformance check; `--interference`, which parts share volume;
  `--ranges`, each joint's stops), `cad snapshot FILE OUT.png`, `cad dfm FILE` (whether a part can be made) and
  `cad fea FILE` (a stress study). A model is its `.xbf`, the file that is its document and whose id is the
  model's (`cad export arm.xbf arm.glb`). Each check's findings carry a severity, a code and a location
  (`--json`). `cad <verb> --help` gives every form, `cad <verb> FILE --help` that file's type's options, and a
  file whose type lacks the verb is refused in one line naming the types that have it (`cli/verbs.py`, over
  `cli/document_types.py`).
- **Integrations**, a tool's own operations on its files: `cad kicad drc BOARD`, `cad kicad erc SCHEMATIC`
  (KiCad's own checks) and `cad mujoco check MODEL.xml` (`cli/integrations.py`).
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
- **`cad viewer [FILE|FOLDER ...]`** opens a page of the running server: each file's, a folder as a project.
- **`cad doctor`**: one read-only report: this cad's release, its Python, where it runs from (the environment,
  the release installed there and who installed it), its data and cache folders and what `cad cache prune` would free,
  the CAD kernel environment and whether it loads, the integrations, whether the server runs and its release, and
  cad's own update (the switches, whether an update can begin, the feed's newest release, the uv it runs,
  the last attempt with uv's words, why in plain words, a release held back, and its log); on Windows, a uv folder
  in an app's private copy of AppData. Under a line that warns, what to do (`auto_update.advice`); where cad or
  its update is not working, a last check, `fix`, says the one thing to do next. It changes nothing. Exit 1 where
  the kernel is installed and does not load; `--json` gives the report
  as one document.
- **`cad cache dir|prune|clean`**, as `uv cache` treats uv's: `dir` prints the cache folder; `prune`
  removes what no file and no release needs -- environments made for other releases, the release folders
  0.11.11 and earlier left, a file's folder once its file is gone (its note names the file), one whose note
  names none (an earlier build's) once nothing in it was written for 30 days, and, past 1 GiB, the meshes cad
  keeps by geometry (a shared file's part meshes, a part's hulls) used longest ago -- and, where no update is
  underway, cad's own releases in uv's cache (`uv cache clean cad`; nothing of another package) and on Windows
  each `cad.exe` an update moved aside and could not remove then, each said, with what it freed (`--json`: one
  document, by kind -- `environments`, `releases`, `gone`, `unused`, `meshes`, `aside` -- the paths removed and
  the bytes freed, the bytes freed in all, what came of uv's cache, `uv`, and each path kept, of which kind, and
  why); `clean` removes all of the cache, refused while the server runs. `prune` runs beside a server: it keeps
  what is in use (an environment a process runs from, a file's folder while it is being shared) and says so. The
  cap is about what the CAD kernel's environment takes, so meshes never cost more than the kernel; each is made
  again when it is next needed. Only these, cad's update and the server (once, as it starts) delete a past
  release's files; the server removes what `prune` removes of cad's own by `prune`'s rules, quietly (`base.tidy`,
  `releases.tidy`), and never touches uv's cache.
- **`cad update`**: cad, and only cad, updated now to the newest release on PyPI, a new major version too, by the
  server that runs, or by the command itself where none runs (below), even with automatic updates off. It never
  starts a server, and is refused unless
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
- **`cad share FILE [--yes]`**: one file (a CAD file the viewer opens, turned into its canonical path; a model by
  its `.xbf`, a script refused) shared for anyone with its link to open in the
  hosted viewer and to download its files (a model's `.xbf` and the script, modules and files it read, from the build
  closure the `.xbf` holds, none changed since it was made; a file's file), for 7 days after its last share: the
  server writes its view bundle into the file's folder in the cache, over the one it wrote there last, and the command
  uploads the files the share lacks itself, so an agent app's sandbox sees the connection, and sharing it again sends
  only what changed. The first share on a computer is refused without `--yes`, the person's yes, in lines that say
  what goes, where, who can open it, for how long and how to delete it. **`cad share status|on|off`**: whether
  sharing is on and agreed, and this computer's live shares; `off` refuses every share until `on`. **`cad share
  delete FILE|LINK`**: a share deleted, asked first. The agreement, the setting, a share in its file's entry of
  the library and the cache's folders are written by the server that runs, as every change of the library is, else
  by the command (the engine's **Sharing**). **`cad import LINK [FOLDER]`**: a share's files downloaded by the command
  itself into a folder, every entry kept inside it, a model's `.xbf` among them, and the file the share is of added to
  the library with the link it came from; it runs nothing and makes no project, and prints the commands that show it
  and build it. Of a share this computer made, it downloads nothing and says where its files are. A share's link
  names this computer's copy of it wherever cad takes a document, as the library holds them: the file it shared,
  else the file its import wrote.

No command removes cad, and installing it is uv's (`uv tool install cad`, `uv tool uninstall cad`).
One command can install it with uv where a computer has none: `cad mcp` run from uv's cache, which
runs that same `uv tool install`.
A command that destroys asks first (`cad server --rotate-token`: a terminal's `(y/N)`, else `--yes`;
`_internal/consent.py`).

Kept only for releases 0.10.0 to 0.11.11, and deleted with that bridge (`cli/setup.py`): `cad setup
--engine-update`, which those releases' updater runs on the new release; and plain `cad setup`, which a `cad
update` typed on those releases runs, the install command in install mode. On a computer whose apps got
text-to-cad only from a store, the bridge moves cad alone, installs it with uv, and runs no install command.

Run, and never listed by `cad --help`, because programs rather than people use them: `cad requirement
[INTEGRATION ...]`, which prints the exact requirement a Python of a program's own installs this release's cad
by (`cad[build123d]==<release>`); `cad plugin update`, `install` under the name the servers of 0.11.12 and 0.11.13
run; and `cad plugin --refresh`, which the updater of 0.11.10 runs after it moves a computer, and which does
nothing. Nothing another program calls -- an
installer, an earlier release's updater, an agent app's launch -- is removed before its replacement ships.

A command or an option the skills used is replaced, not kept: its old spelling runs nothing and answers in one
line with the spelling the command has now, exit 2 (`usage`), from one table (`cli/__init__.py`'s `_hint`):
`cad xbf export a.xbf a.step` and every other `cad <type> <operation>`, `cad model <operation>` (the skill text
of releases up to 0.12), the short forms `cad status` and `cad stop` (0.11.0 to 0.11.11's skill text), bare
`cad server` and `cad orcaslicer`: `'cad xbf export' is 'cad export SRC DST' now; 'cad export --help' says its
options`.

On Windows, what a command writes to a pipe or a file is UTF-8, and so is what the program `cad run` runs
writes (a console is left as it is, as is every stream elsewhere); Windows PowerShell 5.1 decodes a
program's piped output with the console's code page (`[Console]::OutputEncoding`), so an accent in a
PowerShell pipeline is still wrong there, and that is PowerShell's to set.

## cad's own update

`_internal/auto_update.py` decides when, `_internal/auto_update_helper.py` carries it out. **The rule**: cad installs
by itself the newest release there is, a new major version too: it names no release and bounds none, so what the
person's installer takes for `cad` is what is installed, never a release yanked on PyPI (which is how one is held
back). Only a global install updates itself, one uv made (`uv tool install cad`): it is updated
where it is, by the person's own uv (`base.find_uv`: uv's default install place, then PATH, else a one-line
error saying how to get uv), with the person's settings and
uv's receipt left as it is, a range a person wrote there included; one that only caps the major, as 0.11.18 and
earlier wrote it (`cad<1`, `cad>=X,<1`), is replaced where it is all that keeps the newest release out (cad installed
over uv's record in place, `uv tool install --upgrade cad`: `auto_update.capped`). A cad pipx or pip
installed is updated the way it was installed, and `cad update` says so. One a person pinned (`uv tool install
cad==X`) is left alone (cause `pinned`). Two switches in the person's settings:
`auto_update.on`, whether cad updates itself, on unless turned off (`cad update auto`); and `plugin.auto_update`,
whether the server runs `cad plugin install` once where cad is newer than the release the plugin is up to date for,
off unless turned on (`cad plugin update auto`).

**When** (`due`). cad updates at two moments alone, and nothing runs in the background: a person's ask (`cad update`,
and the viewer's button, which is `cad update`'s), and the server's start, where the switch is on and the feed as last
read names a newer release (`restart`, from `daemon.main`: the start becomes the update; never for
`--foreground` or `--port`), or `cad server start` where the start failed. The server reads PyPI (`updates.py`, at
most once an hour, in the background: its index page for cad, `pypi.org/simple/cad/` as JSON, the newest release that is not yanked: the sign
that there is something to take, never what is installed) and the project's notices (`api.texttocad.dev/v1/notices`), kept together in `releases.json`, and does
nothing else with them. Holding a release back is yanking it on PyPI. A server never restarted, whose person never asks, stays on its
release, the button showing the update. Not due where the environment holds that release already under this older
server (`stale`: `cad server start` replaces the server), nor for a release whose last try ended `start_failed`
(`given_up`; `cad update` still tries it), nor while an attempt is underway. One due that cannot begin (`blocked`:
`pinned`, `no_installer`) is counted once for its release. `CAD_UPDATE_CHECK=0` turns the check off for a process.
A global install behind a release for three days, the switch on, says so at most once a day on stderr
after a command's output (`auto_update.notice`; not after `cad update`, `cad doctor`, `cad run`, `cad plugin`, the
server's commands, help or `--json`), with what to do (`advice`, the line `cad doctor` and a failed `cad update` give).

**The schedule and the record.** A release that does not install is tried again at a later start: an hour after its
first automatic try, then 2, 4, 8 and 16 hours, then a day after each (`next_try`), counted for that release, so a newer
release starts afresh; no automatic update begins where four attempts, of any release, began in the last day; a
person's own (`asked`) counts among them and spends no try. The attempt is kept in `auto-update.json`, begun in one step
under the state folder's lock, so two servers begin one; its worker beats in it every minute, and one silent for 20
minutes is `lost`. It ends `installed`, `current` or `failed`, with `detail`, `restored`, `started` and, where it did
not install what it was for, `cause`, one word of a closed list (`auto_update_helper.CAUSES`), said in plain words by
`auto_update.SAID`, and `worker`, the release whose worker ran. The release that began the attempt reads the record its
worker writes, so the record only gains fields.

**The worker** (`auto_update_helper.py`) runs from the release the update goes to, never from the environment it
replaces: uv builds that release in its cache first (`build`: where it cannot, the attempt fails with uv's cause and
nothing is touched), then the worker starts from it, detached, with no window, outside any Windows app package (by
Task Scheduler, `places.outside_package`) and out of the job of the app that ran cad where that job allows it (an app
closing its job would end the update midway; the server's daemon starts so too): `uv tool run --isolated --managed-python --from "cad==<X>"
python -P -m cad_server._internal.auto_update_helper <told>` (`from_cache`, `helper_command`). That entry is a
contract every later release keeps: an older release starts a newer one's worker by it, and hands it `told`, of which
a worker may use any key and must need none an installed release does not send (a later release may send fewer; the
record's keys, which the older release reads, are never removed). uv deletes the old
files one by one, in the order of the package's `RECORD`, and stops at the first it cannot delete, with nothing put
back; on Windows a file a running process holds cannot be deleted, so the worker makes the upgrade safe and repairs it
where it fails anyway. uv prepares the release before it changes anything, so a download that fails leaves cad as it
was. In order:

1. **Switch** (the record's `phase` is `switching`: a server of the release being left starts none, `leaving`). On
   Windows inside an app package: refused, cause `packaged`. The server that answers is stopped at once, as `cad server
   stop` stops it; a `cad` command it cuts short says cad updated itself while it ran. On Windows, uv's bin `cad.exe` is
   moved aside, then every other process of the environment stopped but those it spares, until none is left (by the
   Win32 API, else PowerShell's `Get-CimInstance Win32_Process`).
   Then `uv tool upgrade cad`: the newest release uv
   takes; the moment it returns a bin `cad` is back.
2. **Check**: `cad server start` where a server ran or one is wanted, which must leave a server of the release, else
   `cad --version` naming it.
3. **Back**, where uv or the check failed: where uv failed and left the environment whole, the release it holds, as
   it is; where the release installed and did not run, the release before, by the same safe `uv tool upgrade
   "cad==<before>"`. Cause `start_failed` where the release did not start
   and the one before runs again; where uv was refused a file and a process of the environment could not be stopped,
   `cad_running`; the detail is uv's first error, never its rollback's after it.
4. **Repair**, in one step, where no cad runs after that (or uv left a `*.dist-info` without its `RECORD`, which every
   later uv run fails on): uv makes the environment anew, as the install command does (`uv tool install
   --force cad`; never one release, which would pin it). The worker runs from uv's
   cache, so nothing of it is in the way. That removes the environment, so the worker does it once nothing of it runs:
   the attempt `repairing` first, on which the processes the switch spared leave (`cad update` says so and ends),
   waited for, then every process of it stopped. Cause `broken` where that leaves no cad that runs either.

No step is tried twice in a run. Each command, its status, time and the end of its output go to `auto-update.log` in the
state folder (the attempt before's, `auto-update.1.log`), which nothing sends. A worker that raises leaves the attempt
underway, `helper_crash`. Forward only: nothing moves to an older release but step 3, at the update itself.

**Notices** (`notices.py`). The version feed can carry the project's notices, one line of text and a link on
texttocad.dev or the project's repository, for every cad older than a release (`updates.parse_notices`, which checks
each again by the feed's rules and drops one that fails; kept with the feed in `releases.json`, where releases before
notices ignore the key). Where this cad reads the feed (`updates.checking`), whatever automatic updates are set to, a
command says each that applies on stderr after its own output, at most once a day by its id (`notices.json` in the
state folder, written before it is said), on the rules of the stayed-behind line; `cad doctor` lists each; and
`GET /api/v1/server`'s `cadNotices` hands them to the viewer. With none, nothing says anything.

**In the MCP channel** (`mcp/server.py`'s `attention`), for an agent that never sees cad's stderr: the stayed-behind
line (at once where the update failed or cannot begin; where automatic updates are off, that the release is out and to
ask before `cad update`) and each notice, under `cad needs attention:`, in the initialize answer's `instructions` and
once a session on the first result of an agent's tool. From the feed as last read and the records; nothing when all is
well.

**The update button** (`auto_update.button`, `GET /api/v1/server`'s `cadUpdate`; `POST /api/v1/local/update`).
Where cad can update itself (a uv global install), whatever the switch says, the viewer and the CAD app show it while
PyPI, as last read, names a newer release: one state, Update (a click updates in place and restarts), working
while an attempt of this release is underway, or, where the last did not install what it was for and cad is still
behind, its `cause` and the worker's log, said in the alert card until another attempt begins or the person puts it away (`dismissed`, `auto_update.dismiss`). A click is
`cad update` (`Daemon.update`): PyPI asked, the attempt underway joined, else one begun at once. The route is
refused where cad cannot update itself, saying why, and sits behind the credentials and guard header of every
route that changes something. It shows nothing of an attempt from another release (the one that installed this
cad), nor a failure to a server older than its environment (`stale`): a click only restarts the server on it.

**The plugin catches up** (`_internal/plugin_catch_up.py`). Where `plugin.auto_update` is on and this cad is
newer than the release the plugin is up to date for, the server runs this cad's own `cad plugin install` once,
detached, its output in `install-command.log` in the data folder, the run named by `CAD_PLUGIN_SERVER_RUN`. It
has 15 minutes: each command it runs is given what is left of them and stopped with all it started, no app is
begun past them, and it exits non-zero (in a Windows session where `taskkill` is refused, only the command's own
process is ended). A hard stop (`plugin_catch_up.HardStop`, a thread of its own) ends a run not ended a minute
past its 15: counted as stopped, its record closed, exit 124, its lock freed. The server asks at
each tending, whatever is in flight, from a minute after its start (`START_SECONDS`: the install command that
just updated cad goes on to the plugin in that minute), never while a run holds the lock, so the rule holds
however cad got newer: its own update, `cad update` or `uv tool upgrade cad`. The release is
kept in `install-command.json` in the data folder: written when `cad plugin install` ends with every app it
found gone well, and when the switch is turned on (`cad plugin update auto on`, the hosted install command's last
step; with `CAD_INSTALL_FAILED=1`, where the plugin's step went badly, none; turned on by hand, "from this
release on"). Only the computer's global install writes it: a cad run from anywhere else (the newest release
from uv's cache) keeps none, since its release may be one the installed cad has not reached. A run of the global install that went badly marks its release as owed a run (`owed`), which the server
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
at its start or any tending, sends one `update` event from the record (the release before, how it ended,
which step failed, where it did not install a newer cad its `cause` -- `already` where the environment held the
release already, `none` where the record names none --, the tries, the installer, whether it was typed, and how
the server's run of `cad plugin install` for a newer cad went) and marks the record `reported`. An attempt whose
worker has been silent for 20 minutes (an hour, for a record of a release before the beat) is counted `lost`. An
automatic update due that cannot begin is counted `blocked`, with its cause, once for each release the feed calls
for (`auto-update-blocked.json` in the data folder). Never uv's words, a path or a setting's value. A failed
update is counted by the next server of the old cad, a successful one by the new cad's; a new attempt counts the
one before it first, whatever begins it, as it stands where its `cad plugin install` run is still underway.

`cad update` asks the server that runs (`{"op": "update"}`, which an agent's sandboxed shell may send with no
permission): it asks PyPI for the newest release that is not yanked (`updates.pypi`, 5 s at
most; `CAD_PYPI_URL` names a stand-in), says `cad X is the newest release` where none is newer, and
otherwise begins the same update at once, with the switch off too and whatever the
schedule says (it spends no automatic try, and counts among the day's four), or joins the one underway, another
process's too. Where PyPI cannot be reached it updates
all the same, to the newest release uv finds. It waits for the end, up
to 30 minutes, saying once on stderr `cad: updating cad Y to X`, then restarting the cad server where one ran. It never runs
`cad plugin`. Where no server runs, the command judges and begins the update itself, and its worker starts no
server: an update typed with none running leaves none running. In a shell whose
sandbox cannot start a server, it says so and updates nothing.

## Folders

The data folder (the state folder, `cad.engine.places.state_dir`) is `cad` in the platform's place for state (`~/Library/Application Support/cad` on macOS,
`~/.local/state/cad` on Linux and Windows) or the folder `CAD_STATE_DIR` names: settings, the library
(`library.json`, which this user alone may read, as it holds the keys of their shares: the project folders, and the
files a person opened, starred, built, shared or imported, a shared file's entry with each share of it and an
imported file's with the link it came from), the page token and port, the telemetry spool and the feed's last answer. The cache
folder is `~/.cache/cad`, on Windows too, or the folder `CAD_CACHE_DIR` names: what the engine derived of a
document (a file's count and picture, `documents/<id>/note.json`, which names the file; a board's plots, kept checks;
a shared file's last view bundle, `documents/<id>/view/`), the environments, bytecode, parts' hulls and the
integrations' private homes, all made again on demand. A file's folder goes with its file, and the meshes are held to
a size, the least recently used first, a read counting as a use (`cad cache prune`). A model's document is its `.xbf`, which the engine keeps no copy of. On Windows neither
is in the local application data, which Windows virtualizes for every process an app package (the Claude
desktop app) starts. A release reads what the release before wrote and migrates it on first touch, once
(`cad_server.engine.library`); nothing in the cache is converted.

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
