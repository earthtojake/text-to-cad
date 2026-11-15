# cad-server

The CAD server, imported as `cad_server`: the daemon that builds, keeps and serves CAD
documents, one per installed version in use (each reached through its own door; the one `installations/current`
names also answers clients of 0.11.10 and earlier); the CAD Viewer and the CAD app's MCP endpoint on its listener; the
environment the CAD kernel runs in; the versions installed side by side; and the command that runs them all.

Models are written against the library, `cad`, which the server imports without
its CAD kernel: the kernel lives in the environments the server makes, on first need, for models and
its own kernel processes, `cad[build123d]` at the server's own release. `cad run` runs a program as
`uv run` does, with cad pinned at the server's release and the integrations its imports use; a tool's
own command an integration declares (`cad run kicad-cli …`) gets that integration and runs headless; a
script that imports `bpy` gets the blender integration, its environment made on Python 3.13, the one
Blender is built for.

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
                         #   engine sessions (http), tools and launches (server: the tools
                         #   0.11.10 removed answer by name with the `cad` command that replaced
                         #   them), which apps are offered tools and how (host: the Codex app
                         #   alone), open views (views), sidebar views
                         #   shared in memory (sidebar), the viewer routes in-process (tunnel), the
                         #   page (ui), and the CAD Viewer link for a call that shows no view
                         #   (browser)
  robot_payload.py       # a robot description resolved for the viewer's page: its
                         #   articulation, its visuals in rest space, the facts a person
                         #   reads off it; held in memory
  drawing_payload.py     # a DXF flattened by ezdxf for the viewer's pane
  kicad/                 # a KiCad schematic's electrical rules check and exports (`cad kicad_sch
                         #   erc|export`: schematic), by the kicad integration's kicad-cli, headless
                         #   in private homes
  jobs.py                # the viewer exports' admission, progress, waiting and cancellation
  analytics.py           # telemetry: usage counts and crash reports, on by default once
                         #   a command has said so, never after a no
  settings.py            # the person's settings: settings.json in the data folder
  language.py            # the language the person chose for the CAD views
  whats_new.py           # the releases whose What's new the person has seen (settings'
                         #   whats_new), and whether a device was updated or is new
  updates.py             # the hourly version check: the latest release the feed names, and
                         #   whether it is newer than this one
  assets.py              # where the bundled runtime is
  _internal/             # the environments models run in (base: the installation's base,
                         #   cad[build123d], made by uv on first need; extras: the one a
                         #   program's run asks for, cad pinned with its integrations, its
                         #   packages and uv's options; scan: the integrations a program's
                         #   imports use, read without running it), the launch commands (launch), the
                         #   `cad` command and the installation records clients of 0.11.10 and earlier
                         #   read (installations: ~/.local/bin/cad; written by `cad setup` and `cad doctor`),
                         #   a pin's reading by the version it names (pins), the
                         #   module the command of 0.11.10 and earlier ran (proxy), the flat release
                         #   folders of 0.11.10 and earlier (releases), the versions installed in their own
                         #   folders, their use and their cleanup (versions), a version's data copied in
                         #   once (imports), the layout of 0.11.10 and earlier (legacy), what earlier
                         #   releases left behind (leftovers), the daemon's entry
                         #   (engine_daemon) and what it is composed of (engine_host), the
                         #   server's observer of the engine and the telemetry sender, where
                         #   an event comes from and who is told of a new release (channel), file locks (the data folder's one lock:
                         #   `file_lock.state`), the CLI derivation, the one parser every
                         #   command reads its options by (cli_parser) and the one failure
                         #   contract every command fails by (cli_errors)
  _runtime/              # BUILT: the CAD Viewer client and the CAD app page -- produced when
                         #   the wheel is packaged, never committed, never edited
```

## Commands

A document type's commands are `cad <document_type> <operation> <file>`, one id per type as the
library's registry names it (`cad.registry`): `cad model export <id>`, `cad xbf export`, `cad step snapshot`,
`cad glb inspect`, `cad urdf validate`, and the rest `cad --help` lists, grouped by type. `model` is a model
the engine holds, by its document id, with no file; every other type takes a file of its own. `export`,
`snapshot` and `inspect` are the engine's verbs, shared by every type that has them (`snapshot` draws every
file the viewer opens, a DXF or a robot among them); every other operation is named for what it does --
`dfm`, `solve`, `ranges`, `drc`, `erc`, `validate` -- each a check (its findings, each a severity, a code and a location;
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
KiCad is never run for this work, the server never starts KiCad's app by itself, Open in hands a `.kicad_*` file
to a person's KiCad only at their click and never to its default handler (on Linux it asks that KiCad's
`kicad-cli` its version, headless, and nothing else), and
viewing a board needs no KiCad installed: its first plot fetches kicode, the `kicad` integration's, to refill its pours on a copy, unless `CAD_KICAD_REFILL=0` in the server's environment, which draws them as the file saved them, as a failed fetch does. A KiCad schematic's are the same integration's, run the same way, on its project's root sheet whichever sheet is named: `cad kicad_sch erc` is KiCad's electrical rules check (it fails on errors and says the warnings, each with its sheet and where; the library checks a headless `kicad-cli` cannot make, the person's global libraries being out of its reach, are one note) and `cad kicad_sch export SCHEMATIC --to pdf|svg|netlist|bom -o DIR` its outputs; `cad kicad_sch snapshot --sheet /Power/` draws one sheet, and `cad kicad_sch inspect SCHEMATIC [REF]` says what it holds and what a reference names, the library's, with no KiCad.
A B-rep type's `solve` (`cad model|xbf|step solve SRC`, the setup: the parts, the pairs that touch and a part's
faces; `--study STUDY --out DIR`, the solve, which writes `result.json`, `result.glb`, `result.vtu` and a picture of
each field into DIR, `--deck` adding CalculiX's input) is the stress study,
meshed by the `netgen` integration and solved by the `calculix` integration's ccx (the cad-ccx package), run in this
process where its environment holds the kernel, netgen and ccx, else in the environment of
`cad[build123d,calculix,netgen]` the engine makes once. `cad run ccx ARGS` runs the same ccx on a deck of the
person's own.
`cad model|xbf|step ranges SRC [--step S] [--clearance MM] [--joint NAME]` sweeps each joint of the
document's mechanism alone against its parts and says where each stops and which parts meet, writing nothing (the
library's `cad.<type>.ranges`), run in this process where its environment holds the kernel, else in the
installation's base.
A 3D type's `dfm` (`cad model|xbf|step|stl|glb|threemf
dfm SRC --process cnc|sheet|molding|printing`, and `cad dxf dfm FILE --process sheet` of a cut file) is
the manufacturing check: CNC machining, sheet metal, injection molding or 3D printing, measured exactly on a
STEP's or an xbf's B-rep by the `build123d` integration (findings at face refs) or on a mesh by the
`trimesh` integration, and judged against general rules, each cited (no shop's limits), every measurement
and every rule's outcome under `--json`. A B-rep's (a model, a STEP, an xbf) is the engine's: measured in one
of its checks processes -- a file read once, a model from the bytes the engine holds, never in the model's worker
-- and kept by the document's version, beside the engine's cache, so the same check of an unchanged
document measures nothing, after a restart too. Where the
engine measures nothing (none to reach, another release's), and for a mesh and a DXF, it runs in this process where
its environment holds the type's integration, else in that integration's environment (the base for build123d, `cad[trimesh]` made once by the engine, as `cad
run` makes a program's: `_internal/integration_env.py`).
An MJCF, a MuJoCo model's file, is no document type: cad writes one (an export's `.xml`) and never shows
one. `cad mujoco check MODEL.xml [--strict]` is the `mujoco` integration's operation on it (`cad
<integration> <operation> FILE`, `cli/integrations.py`): MuJoCo's own compiler, what it refuses or warns
of, the model-health checks, what the model collides as and its contact excludes, run in this process where
its environment holds mujoco, else in the environment of `cad[mujoco]` the engine makes once; `cad run
mujoco-studio --model MODEL.xml` shows the person the model in MuJoCo Studio. OrcaSlicer's presets are no
document type either: `cad orcaslicer presets KIND [--match TEXT]` lists those a person can select, and `cad
orcaslicer complete --printer P --process P --filament F [--out DIR]` writes them complete, every parent merged
in and the printer named as compatible, for OrcaSlicer's own command line (the `orcaslicer` integration's two
operations, which take preset names and no FILE). Its code is the library's, the standard library alone, so
they always run in this process: no engine, no environment made. `cad serve`,
`status`, `stop`, `delete` and `server` are the engine's process control, each acting on one version's server
(the pinned one, or the newest's); `cad doctor` the health of the version it runs as and its repair (the `cad`
command written where it is missing or older, the installation registered where none is current, whether the CAD
kernel environment is made and the integrations' -- never made there --, the engine started: the whole report on
stdout, exit 1 when the kernel is installed and does not load; `--check` the report alone, which registers, writes
and starts nothing, what a bug report wants; `--json` it as one document, each check's name, status and detail) and
the one command that reads every version installed: where each is, whether its server runs and on which port, when
an agent last used it, and when the newest one's cleanup removes it; what is left of the layout of 0.11.10 and earlier
and whether it can go yet; and what earlier releases left behind that nothing of this one uses (`_internal/leftovers.py`: engine records of an older
format, the bytecode of installations no longer registered, cache folders no record names, the launchers earlier
releases published beside the `cad` command, 0.8's `cadgen` proxy among them), which nothing removes but the person;
`cad run` a
program exactly as `uv run` runs it -- uv run's
options, a script's `# /// script` header, a project -- with cad pinned at this release and the
integrations its imports use (`_internal/extras.py`, `_internal/scan.py`, by the library's registry), in an
environment the engine makes, its own folder last on its path, and a command an integration declares
(`kicad-cli`) with that integration, through its `_command` module, headless; `cad requirement [INTEGRATION ...]` the
exact requirement a Python of a program's own installs this release's cad by
(`cad[build123d]==<release>`); `cad viewer` the engine page launcher;
`cad setup` installs the version that runs it on this computer, and nothing else: its folder
(`versions/<version>` in the state folder), its server, a check that it runs, the CAD kernel, its complete marker
(`_internal/versions.py`'s `make_present`), and the `cad` command where it is missing or older; its first setup copies
its settings and store in once, from the newest older version installed, or from the layout of 0.11.10 and earlier,
what 0.7 and 0.8 kept in their own state folder taken into it first (`_internal/imports.py`); and on a computer an
earlier release ran on it hands over what that release left running, its own processes and records alone
(`_internal/legacy.py`): 0.8's server stopped by 0.8's own `cadgen stop`, and a server of 0.11.10 or earlier asked to
stop once idle, with the records its clients start a server by naming this version. Last, it starts the version's own
server, detached, where none runs, and says in a line that it is running (or why not, which never fails the setup):
setup always runs outside a sandbox, where an agent's sandboxed shell cannot start one, so every later session finds
it running. It starts none where a server of 0.11.10 or earlier was just asked to stop once idle: that server still
holds its pages' port, and the next command starts this version's. Run again it is quick and changes nothing. It is
run as `uvx --no-config --managed-python --python 3.14 --from cad-server==<version> cad
setup`. It has one hidden option, `--engine-update`, which no person runs: the updaters of 0.10.0 to 0.11.10, frozen
on computers, update by running a newer release's `cad setup --engine-update` from a flat folder they made, so it
does the same, but for starting the server (their switch starts it), then the hand-over from their layout (the
records their switch reads written: `installations/current` and the installation record naming the version's server),
then starts the hosted install script once, detached and never waited on, by a program that first waits, up to
about an hour, until the site's `install.py` names this release (`_internal/install_script.py`; the site is deployed
after the version feed names a release); a command file of another's at `~/.local/bin/cad` is said and the run goes
on (`CAD_ENGINE_UPDATE_INSTALLER` names a command to run instead, for a test, and `CAD_ENGINE_UPDATE_INSTALL_PY` the
`install.py` to wait for). cad has no updater: the version check (`updates.py`) only knows the
latest release, and says so (**The update notice**). `cad uninstall` removes cad from this computer: every version,
each one's server stopped first (and, on Windows, waited for until its processes have ended), the state folder and
the cache folder of 0.11.10 and earlier where they hold a mark only cad writes, what its servers kept in the engines'
folder (cad's entries alone), and the `cad` command; nothing is kept and nothing else is touched. It asks first, as every command that destroys does (`cad
delete`, `cad server --rotate-token`: a terminal's `(y/N)`, else `--yes`;
`_internal/consent.py`); and `cad telemetry` the person's answer, whose no, wherever it is said
(`cad telemetry off`, the app menu's switch), is said in every version on the device
and in the state folder's settings, where 0.11.10 and earlier read it and where a version installed later takes it
from as it first starts (`analytics.everywhere`, `inherit_no`). The mechanism is the
engine README's **CLI** and **Document types and integrations**.

**Since 0.11.8** `cad <type> inspect`'s text names at most four parts on a line of materials, then the first
three and how many more; its `--json` still names every part, so a program reads that.

A model builds by running its script: `cad +<version> run model.py`, through
the `cad` command. The CAD app an agent
host starts is `cad-mcp`, of the `cad-mcp` distribution, which reaches this server.

**The `cad` command** (`~/.local/bin/cad`, `cad.exe` on Windows: `_internal/installations.py`) is the one file
every version is run through, written by `cad setup` and `cad doctor` where it is missing or of an older revision,
and never replaced by a release whose revision of it is older. It reads only its first argument and what every
version keeps where every version keeps it, so a command written by one release runs every later one by the same
rules. A pin, `cad +<version>[@<name>] <verb> ...`, runs exactly that version's own `cad` with the whole command line,
and never another version. A version that is not installed is said to be so, `cad: cad <version> is not
installed on this computer.`, exit 3: nothing is installed, no install command is named and no network is used (the
line that installs a version is that version's own, `uvx ... --from cad-server==<version> cad setup`). With no pin,
the command runs the newest version installed (the highest version number: a release is always `X.Y.Z`, never a
pre-release, and a development build `X.Y.Z-dev.<stamp>` sorts after its release; the command orders those two
forms alone as the server does, and a name of another form may sort otherwise there); with none installed it says `cad:
cad is not installed on this computer.`, exit 3. The version reads the pin (`_internal/pins.py`): its
`@name` is a label alone -- the channel its requests to the server name (`cad.engine.places.channel()`, `default`
for none) and `cad run` hands its program, which telemetry reports, and which turns the update notice off. Each
refusal is one line on stderr (from the version, one JSON document on stdout under `--json`), with its exit status:
2 `bad_pin`, a first word `+...` that is no pin or names no channel; 3, a version not installed (the command's
own); 5 `other_version`, a version's own `cad` given another version's pin. A `cad` command of 0.11.10 or earlier
knows no pin: it says `+<version>` is an unknown command (exit 2).

**The update notice.** cad updates nothing by itself. Each version's server reads the version feed in the
background at most once an hour (`updates.py`; never waited on; `CAD_UPDATE_CHECK=0` turns it off), and where the
last read names a newer release, a command says so on stderr after its own output, at most once every 24 hours on
the computer (a stamp in the state folder, `update-notice`), and never for a command that names a channel:

```
A new version of cad is available: X -> Y
```

One line, naming no command and no link: cad says only that a version exists. How to install it is for whatever
installed this one to say, and cad cannot know what that was. `cad --version` prints `cad X`, and then the same line
on stderr whenever a newer release is known. Nothing on stdout changes.

**Versions side by side.** An installed version keeps everything it reads and writes in its own folder,
`versions/<version>` in the state folder: its data (`data/`: settings, Recents, the documents' records, the page
token and port, the telemetry spool, the version feed's cache, and its caches under `data/cache/`), its code (`code/`:
its environments, the kernel's and `cad run`'s under `code/base/`, and their bytecode), and its last use (`used`, the
file's time), and its engine's door in `<version>` in the engine folder; a process with no version (a checkout or a
test under `CAD_STATE_DIR`, `CAD_ENGINE_DIR` and `CAD_CACHE_DIR`, a release of 0.11.10 or earlier) keeps the flat
layout below, in the state and cache folders (`cad.engine.places`). A version is made present whole -- its server and
kernel environments, then its code marker -- by `cad setup` (`_internal/versions.py`), and is installed while that
marker is there. Its settings and store are copied in ONCE, at its first setup (or first start), from the newest older
installed version, or, on a computer coming from 0.11.10 and earlier, from that layout (`_internal/imports.py`); after
that nothing moves between versions, and no version refuses another's commands.

Each version in use runs its own server, reached through its own door alone, `<version>` in the engine folder, and
only the one `installations/current` names (written by the hand-over from a shipped release, `cad setup
--engine-update`, by a plain `cad setup` where it names nothing, a version not installed or an older one, and by a
registration where none is current) also answers the flat door every client of 0.11.10
and earlier and every process with no version finds (`engine/daemon.py`'s `Bridge`, the only code for earlier
releases). Each version records its own last use by an agent: a `cad` command run for it, a request its server takes,
an MCP tool call other than the page's own. **The cleanup**: the server of the newest installed version, as it starts
and then every 24 hours, removes every older installed version no agent has used for 2 days (never used: 2 days from
its install) -- its server stopped where nothing is in flight there, then its folder deleted -- and, once it is safe,
what is left of the layout of 0.11.10 and earlier (`_internal/legacy.py`, what that layout wrote after the import
carried in first). A version that is not the newest cleans nothing. `cad stop` and `cad status` act on one version's
server: the pinned one, or the newest's.

Telemetry (`analytics.py`) describes each batch with two fields: `channel`, the delivery channel of the
requests or sessions it counted (a pin's or a launcher's, `default` for none, `dev` from a development build),
and `app`, the agent app that ran them, detected (the MCP handshake's client name, else the markers an app sets in
its shell, else `unknown`) -- one batch for each version, channel and app a window counted. A row a command or a
build keeps for sending says the three itself; what a version had not sent when the cleanup removes its folder
goes with it. A no is said in
every version's settings, and the deletion it asks for is asked under every install id they hold: at once by
`cad telemetry off`, up to the first request the receiver does not answer, and by whichever version sends next.

The state folder is `cad` in the platform's place for state, the cache folder `cad` in its
place for caches; on Windows they are where Linux keeps them, `~\.local\state\cad` and
`~\.cache\cad`, never in the local application data, which Windows virtualizes for every process
an app package (the Claude desktop app) starts. Where 0.10.0 kept them there (`cad-state` and `cad`
in `%LOCALAPPDATA%`), the same commands move the settings, the documents' records and their bytes,
Recents, the receipt, the page token and the port the engine remembers once; `cad doctor` reports the rest, which
nothing removes but the person. On a computer an earlier release (0.8, named
cadgen) set up, a version's first setup (its import), `cad doctor` and a registration move what this release keeps of
the earlier state folder into the layout of 0.11.10 and earlier, which the version imports, each thing once and only where this one has none of it: the
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
the agent apps' plugin configs), so nothing here removes them: `cad doctor` looks for them in the
folders 0.7 used (or the ones `CAD_STATE_DIR` and `CAD_CACHE_DIR` name) and says they are there, with
their size and when they were last written; the person deletes them once no 0.7 is left.

The engine's HTTP API is `/api/v1` (`viewer/http_app.py`, its document kinds `viewer/kinds.py`; the
routes are listed in the engine README's **Wire format**): the pages are at the root, and every
route they call is under it.

The viewer exposes `POST /api/v1/local/clipboard` for explicit viewport PNG copies. It
uses the same host and custom-header gates as other mutation routes, limits
images to 20 MiB, and delegates native delivery to `viewer/clipboard.py`. It never
reads the clipboard. Unsupported desktop clipboard environments return an error.
