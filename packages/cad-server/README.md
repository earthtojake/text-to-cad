# cad-server

The CAD server for text-to-cad, imported as `cad_server`: the computer's one daemon that builds, keeps and
serves CAD documents; the CAD Viewer and the CAD app's MCP endpoint on its listener; the environment the
CAD kernel runs in; the installations and the one that is current; and the command that runs and
installs them all.

Models are written against the library, `cad`, which the server imports without
its CAD kernel: the kernel lives in the environments the server makes, on first need, for models and
its own kernel processes, `cad[build123d]` at the server's own release. `cad run` runs a program as
`uv run` does, with cad pinned at the server's release and the integrations its imports use.

The mechanisms its laws constrain are [`src/cad_server/engine/README.md`](src/cad_server/engine/README.md).

## The shape of the package

```
src/cad_server/
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
                         #   engine sessions (http), tools and launches (server), the agent
                         #   operations (operations), how a host presents CAD (host), open
                         #   views (views), sidebar views shared in memory (sidebar), the
                         #   viewer routes in-process (tunnel), the page (ui), and the CAD
                         #   Viewer link for a host that renders no MCP Apps (browser)
  robot_payload.py       # a robot description resolved for the viewer's page: its
                         #   articulation, its visuals in rest space, the facts a person
                         #   reads off it; held in memory
  drawing_payload.py     # a DXF flattened by ezdxf for the viewer's pane
  kicad/                 # a KiCad schematic's electrical rules check and exports (`cad kicad_sch
                         #   check|export`: schematic), by the kicad integration's kicad-cli, headless
                         #   in private homes
  jobs.py                # the agent operations' and the viewer exports' admission, progress,
                         #   waiting and cancellation
  analytics.py           # telemetry: usage counts and crash reports, on by default once
                         #   a command has said so, never after a no
  settings.py            # the person's settings: settings.json in the state directory
  language.py            # the language the person chose for the CAD views
  whats_new.py           # the releases whose What's new the person has seen (settings'
                         #   whats_new), and whether a device was updated or is new
  updates.py             # the hourly version check, for a copy nothing else keeps current,
                         #   and the release an update moves to
  assets.py              # where the bundled runtime is
  _internal/             # the environments models run in (base: the installation's base,
                         #   cad[build123d], made by uv on first need; extras: the one a
                         #   program's run asks for, cad pinned with its integrations, its
                         #   packages and uv's options; scan: the integrations a program's
                         #   imports use, read without running it), the launch commands (launch), the
                         #   installations' registry, which one is current, and the proxy it
                         #   writes (installations: ~/.local/bin/cad, which the skills run;
                         #   written by `cad doctor`, `cad setup` and a CAD app's first
                         #   registration), the proxy (proxy), the releases an update
                         #   installs (releases), the update the button starts (update) and its
                         #   switch (switch), the plugin folder every agent app is pointed at
                         #   (plugin), the agent apps setup reads and writes (providers),
                         #   what earlier releases left behind (leftovers), the daemon's entry
                         #   (engine_daemon) and what it is composed of (engine_host), the
                         #   server's observer of the engine and the telemetry sender, the
                         #   install channel, file locks (the state folder's one lock:
                         #   `file_lock.state`), the CLI derivation
  _runtime/              # BUILT: the CAD Viewer client, the CAD app page and the agent-app
                         #   plugin (its manifests and skills) -- produced when the wheel is
                         #   packaged, never committed, never edited
```

## Commands

A document type's commands are `cad <document_type> <operation> <file>`, one id per type as the
library's registry names it (`cad.registry`): `cad model export <id>`, `cad xbf export`, `cad step snapshot`,
`cad glb inspect`, `cad urdf validate`, and the rest `cad --help` lists, grouped by type. `model` is a model
the engine holds, by its document id, with no file; every other type takes a file of its own. `export`,
`snapshot` and `inspect` are the engine's verbs, shared by every type that has them (`snapshot` draws every
file the viewer opens, a DXF or a robot among them); every other operation is named for what it does --
`dfm`, `drc`, `erc`, `validate` -- each a check (its findings, each a severity, a code and a location;
`--json`); `cad <type>
--help` lists a type's operations, `cad <type> <operation> --help` its options, and a file of another
type is refused by name (`cli/document_types.py`, each type's module `cli/<type>.py`). A KiCad board's
`drc` and `export` are the `kicad` integration's: `cad kicad_pcb drc` is KiCad's design rule check
(it fails on errors or unconnected items, says the warnings, and answers `kicad_failed` when KiCad refuses
the board) and `cad kicad_pcb export BOARD --to gerbers|drill|pos|bom|step|glb|odb|ipc2581|pdf|dxf -o DIR`
its fabrication, assembly and 3D outputs, each the library's function (`cad.kicad_pcb.drc`, `export`)
run by kicode's `kicad-cli`: in this process where it runs KiCad itself (`CAD_KICAD_CLI` names a
`kicad-cli`, or kicode is installed here), else in the environment of `cad[kicad]` the engine makes once,
as it makes the trimesh integration's. It runs headless with no display and private homes; a person's own
KiCad is never run, the server never starts KiCad's app, Open in never opens a `.kicad_*` file, and
viewing a board needs no KiCad. A KiCad schematic's are the same integration's, run the same way, on its project's root sheet whichever sheet is named: `cad kicad_sch erc` is KiCad's electrical rules check (it fails on errors and says the warnings, each with its sheet and where; the library checks a headless `kicad-cli` cannot make, the person's global libraries being out of its reach, are one note) and `cad kicad_sch export SCHEMATIC --to pdf|svg|netlist|bom -o DIR` its outputs; `cad kicad_sch snapshot --sheet /Power/` draws one sheet, and `cad kicad_sch inspect SCHEMATIC [REF]` says what it holds and what a reference names, the library's, with no KiCad.
A 3D type's `dfm` (`cad model|xbf|step|stl|glb|threemf dfm SRC --process molding|printing`) is the `trimesh` integration's manufacturing check: injection
molding's draft, undercuts and projected area along `--pull`, or 3D printing's overhangs, walls and
support, `--candidates` ranking the pulls or the orientations, every measurement under `--json`; it runs
in this process where its environment holds trimesh, else in the environment of `cad[trimesh]` the
engine makes once, as `cad run` makes a program's (`_internal/integration_env.py`). `cad serve`,
`status`, `stop`, `delete` and `server` are the engine's process control; `cad doctor` the setup (the
installation registered, the `cad` command written, whether the CAD kernel environment is made, the engine started;
the releases on disk, the current one, the engine's and each app's plugin's) and what earlier releases
left behind that nothing needs, which `cad doctor --prune` removes (`_internal/leftovers.py`: engine
records of an older format, the bytecode of installations no longer registered, cache folders no record
names, the launchers earlier releases published beside the `cad` command, 0.8's `cadgen` proxy among
them; none written in the last seven days); `cad run` a program exactly as `uv run` runs it -- uv run's
options, a script's `# /// script` header, a project -- with cad pinned at this release and the
integrations its imports use (`_internal/extras.py`, `_internal/scan.py`, by the library's registry), in an
environment the engine makes, its own folder last on its path; `cad requirement [INTEGRATION ...]` the
exact requirement a Python of a program's own installs this release's cad by
(`cad[build123d]==<release>`); `cad viewer` the engine page launcher;
`cad setup`, which the install command `curl -fsSL https://texttocad.dev/install.sh | sh` runs, sets
up or updates text-to-cad in every agent app it finds, each by its own command
(`_internal/providers.py`), installs its release's folder -- and no environment for models: each is
made on first need -- and moves the device's engine to its release; `cad update` runs the newest release's
`cad setup`, as the update button does; `cad uninstall` takes text-to-cad out; `cad plugin` writes
the plugin folder and prints its path; and `cad telemetry` the person's answer. The mechanism is the
engine README's **CLI** and **Document types and integrations**.

The plugin every agent app gets is one folder, `plugin` in the state folder, which the server writes
from its own copy of the plugin (`_runtime/plugin`: each host's manifest, its config for the CAD app's
server, and the skills, byte for byte as they were released) with every version this distribution's
(`_internal/plugin.py`). It is written again in place -- each file renamed over, never a symlink --
at a registration of the current installation, by `cad setup` before it points the apps at it, and by
the release left current after every switch of the engine (`cad plugin --refresh`). Each app takes it
the way it takes a local plugin (`_internal/providers.py`): a local catalog that Claude Code reads in
place and Codex copies, an extension Gemini CLI links, a copy in Cursor's local plugins folder, the
skills copied by the Skills CLI for the agents without a plugin. An update writes the folder for the
new release and brings the copies along; nothing updates by itself. A model builds by running its script: `cad run model.py`, through
the `cad` command, which runs the current installation, else the one registered last
(`_internal/proxy.py`). The CAD app an agent
host starts is `cad-mcp`, of the `cad-mcp` distribution, which reaches this server.

The state folder is `cad` in the platform's place for state, the cache folder `cad` in its
place for caches; on Windows they are where Linux keeps them, `~\.local\state\cad` and
`~\.cache\cad`, never in the local application data, which Windows virtualizes for every process
an app package (the Claude desktop app) starts. Where 0.10.0 kept them there (`cad-state` and `cad`
in `%LOCALAPPDATA%`), the same commands move the settings, the documents' records and their bytes,
Recents, the receipt, the page token and the port the engine remembers once, `cad setup` stops 0.10.0's
engine by its own `cad stop`, and `cad doctor --prune` removes the rest a week after its last write. On a computer an earlier release (0.8, named
cadgen) set up, `cad setup`, `cad doctor` and a registration move what this release keeps of the
earlier state folder into this one, each thing once and only where this one has none of it: the
settings, the documents' records, Recents and the setup receipt (`cad.engine.places.adopt`); the
person's telemetry no stays in the earlier folder too, for the earlier release while it is installed.
0.8's installations' records, engine records and page token stay where 0.8 keeps them: no 0.10 engine
serves a link 0.8 printed.

Coming from 0.7: cadgen 0.7.x kept a cache store, which can hold gigabytes, in its cache folder,
`~/.cache/cadgen` (macOS and Linux; `$XDG_CACHE_HOME/cadgen` when that is set),
`%LOCALAPPDATA%\cadgen` (Windows) or the folder `CAD_CACHE_DIR` named: its `objects/` and `index/`;
and state files only 0.7 writes in its state folder (its sidebar views, its snapshot browser's lock,
its viewer's log, its Recents log). No later release reads or writes them. Whether a 0.7 is still
installed cannot be told from here (0.7 never registered itself; it lives in uv's environments and
the agent apps' plugin configs), so they retire themselves: `cad doctor` looks for them in the
folders 0.7 used (or the ones `CAD_STATE_DIR` and `CAD_CACHE_DIR` name) and says they are there, with
their size and when they were last written, and `cad doctor --prune` removes them once nothing has
written them for seven days -- a 0.7 in use writes its store at every build -- or at once with
`--all-versions`, once no 0.7 is left in any agent app.

The engine's HTTP API is `/api/v1` (`viewer/http_app.py`, its document kinds `viewer/kinds.py`; the
routes are listed in the engine README's **Wire format**): the pages are at the root, and every
route they call is under it.

The viewer exposes `POST /api/v1/local/clipboard` for explicit viewport PNG copies. It
uses the same host and custom-header gates as other mutation routes, limits
images to 20 MiB, and delegates native delivery to `viewer/clipboard.py`. It never
reads the clipboard. Unsupported desktop clipboard environments return an error.
