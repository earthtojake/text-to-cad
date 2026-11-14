# cad-server

The CAD server for text-to-cad, imported as `cad_server`: the daemon that builds, keeps and serves CAD
documents, one per installed version in use (each reached through its own door; the default channel's also
answers clients of 0.11.10 and earlier); the CAD Viewer and the CAD app's MCP endpoint on its listener; the environment the
CAD kernel runs in; the installations and the one that is current; and the command that runs and
installs them all.

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
                         #   them), how a host
                         #   presents CAD (host), open views (views), sidebar views shared in
                         #   memory (sidebar), the viewer routes in-process (tunnel), the page
                         #   (ui), and the CAD Viewer link for a host that renders no MCP Apps
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
  updates.py             # the hourly version check, for a copy nothing else keeps current,
                         #   and the release an update moves to
  auto_updates.py        # automatic updates: the person's setting (on by default), the
                         #   releases they take by Semantic Versioning (takes: patch below 1.0,
                         #   patch or minor from 1.0), the hour of quiet and the retry rule the
                         #   default version's own update keeps
  assets.py              # where the bundled runtime is
  _internal/             # the environments models run in (base: the installation's base,
                         #   cad[build123d], made by uv on first need; extras: the one a
                         #   program's run asks for, cad pinned with its integrations, its
                         #   packages and uv's options; scan: the integrations a program's
                         #   imports use, read without running it), the launch commands (launch), the
                         #   installations' registry, which one is current, and the `cad` command
                         #   (installations: ~/.local/bin/cad, which the skills run; written by
                         #   `cad doctor`, `cad setup`, `cad setup --add` and a CAD app's first
                         #   registration), a pin's reading by the version it names (pins), the
                         #   module the command of 0.11.10 and earlier ran (proxy), the flat release
                         #   folders of 0.11.10 and earlier (releases), the updater and the contract
                         #   between releases (update), the versions installed in their own folders and the
                         #   one routine that moves a channel between them (versions), the pointer
                         #   per channel (pointers), a version's first-start import (imports), the
                         #   layout of 0.11.10 and earlier (legacy), the plugin folder every agent app is pointed at
                         #   (plugin), the agent apps setup reads and writes (providers),
                         #   what earlier releases left behind (leftovers), the daemon's entry
                         #   (engine_daemon) and what it is composed of (engine_host), the
                         #   server's observer of the engine and the telemetry sender, where
                         #   an event comes from and who has an updater (channel), file locks (the data folder's one lock:
                         #   `file_lock.state`), the CLI derivation, the one parser every
                         #   command reads its options by (cli_parser) and the one failure
                         #   contract every command fails by (cli_errors)
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
(the pinned one, or the default's); `cad doctor` the setup of the version it runs as (the installation
registered, the `cad` command written, whether the CAD kernel environment is made and the integrations' -- never
made there --, the engine started; the current one, the engine's and each app's plugin's: the whole report on
stdout, exit 1 when the kernel is installed and does not load; `--check` the report alone, which registers,
writes and starts nothing, what a bug report wants; `--json` it as one document, each check's name, status and
detail) and the one command that reads every version and channel: each installed version (where it is, which
channels are on it, whether its server runs and on which port, and, where no channel is on it, what becomes of it:
carried into its successor and removed by that version's process; installed and never a channel's; its code removed
by `cad uninstall` and its data kept for a later install; or its data kept, and why), each channel with its version
and when it was last used (a stamp beside its pointer), each pointer that cannot be read (one that names no version
it writes again, naming the newest version a channel has been on; never with `--check`), and what is left of the layout of 0.11.10 and earlier and whether it can go yet. `cad doctor --prune`, a
person's command and never automatic, shows its plan, asks, and does exactly that: it forgets every named channel
unused for 30 days (never the default; its version's data goes to the default channel's version, and where that is
older the version goes whole, its settings and Recents with it, which the plan says), removes every version no channel
is on -- its data carried into its successor first, never one with work in flight -- with the versions installed and
never a channel's, and the layout of 0.11.10 and earlier once that is safe, saying each thing it
did, and what
earlier releases left behind that nothing needs (`_internal/leftovers.py`: engine records of an older format,
the bytecode of installations no longer registered, cache folders no record names, the launchers earlier releases
published beside the `cad` command, 0.8's `cadgen` proxy among them; none written in the last seven days); `cad run` a
program exactly as `uv run` runs it -- uv run's
options, a script's `# /// script` header, a project -- with cad pinned at this release and the
integrations its imports use (`_internal/extras.py`, `_internal/scan.py`, by the library's registry), in an
environment the engine makes, its own folder last on its path, and a command an integration declares
(`kicad-cli`) with that integration, through its `_command` module, headless; `cad requirement [INTEGRATION ...]` the
exact requirement a Python of a program's own installs this release's cad by
(`cad[build123d]==<release>`); `cad viewer` the engine page launcher;
`cad setup`, which the install command `curl -fsSL https://texttocad.dev/install.sh | sh` runs, makes its
release present in its own folder, moves the default channel to it (its data imported, the pointer, the mirror for
0.11.10 and earlier, every version no pointer names removed, the server's port handed to its server -- a server of
0.11.10 or earlier drained first), then sets it up in every agent app it finds, each by its own command
(`_internal/providers.py`), and keeps its receipt, which is what gives the default channel an updater; it leaves a
store's copy, and every named channel, alone; `cad setup --add` makes its release present and writes the `cad`
command, and nothing else (the install command's `--add <version>`, which a skill's setup block names). Only the
default channel has an updater (`_internal/update.py`, whose docstring is the contract between releases: an
updater installs the new release by its own `cad setup --add` and runs its own `cad setup --engine-update`,
nothing else), and only where the install command has run: `cad update` runs the newest release's `cad setup` that
way, as the update button does, and on a device already on the newest release this release's setup again, which
gives an app a run left behind its text (the receipt's `behind`, which `cad doctor` names; the default version's
server does it by itself too, once a day at most while idle) (`--dry-run` reads the version feed, keeping nothing,
and says the release it would install before the plan; with no receipt it says there is no install to update; with a channel's pin, that whoever
delivers the copy updates it); a pinned command newer than the default channel's version runs the same sequence,
whatever the switch says; and `cad update auto on|off` turns automatic updates on or off (on by default: the
default version's server installs a newer release that breaks nothing -- a patch release below 1.0, a patch or
minor release from 1.0 -- in the background and runs its setup once it has handled no command for an hour; one that
may break something waits for the update button or `cad update`);
`cad uninstall` takes out what the install command put here -- our plugin copies, the plugin folder, the default
channel and its version's code unless a store's channel is on it (its data -- settings, Recents, documents' records,
page token and port -- stays for a later install, which finds it), the receipt, and the `cad` command unless a store's
copy still runs it (said, with which) --, and `--purge` everything, that data with it. The channels go before any
server is stopped, so a thread an app still has open finds its channel gone and starts no server again; a version
something still runs from stays, said with what runs and that deleting its folder once that has ended finishes it;
asked first as every command that destroys is (`cad
delete`, `cad doctor --prune`, `cad server --rotate-token`: a terminal's `(y/N)`, else `--yes`;
`_internal/consent.py`);
`cad plugin` writes
the plugin folder and prints its path; and `cad telemetry` the person's answer, whose no, wherever it is said
(`cad telemetry off`, the app menu's switch, `cad setup --no-telemetry`), is said in every version on the device
and in the state folder's settings, where 0.11.10 and earlier read it and where a version installed later takes it
from as it first starts (`analytics.everywhere`, `inherit_no`). The mechanism is the
engine README's **CLI** and **Document types and integrations**.

**Since 0.11.8** `cad <type> inspect`'s text names at most four parts on a line of materials, then the first
three and how many more; its `--json` still names every part, so a program reads that.

The plugin every agent app gets is one folder, `plugin` in the state folder, which the server writes
from its own copy of the plugin (`_runtime/plugin`: each host's manifest, its config for the CAD app's
server, and the skills, byte for byte as they were released) with every version this distribution's
(`_internal/plugin.py`). It is written again in place -- each file renamed over, never a symlink --
by `cad setup` before it points the apps at it -- every update runs the new release's setup --, and by `cad plugin
--refresh`, which the updater of 0.11.10 and earlier runs once the release it moved to serves. Each app takes it
the way it takes a local plugin (`_internal/providers.py`): a local catalog that Claude Code reads in
place and Codex copies, an extension Gemini CLI links, a copy in Cursor's local plugins folder, the
skills copied by the Skills CLI for the agents without a plugin. Claude gets the skills alone: `cad setup`
writes no CAD server into Claude Desktop's config, and takes out the one releases through 0.11.10 wrote
there. A copy an app got from a store (claude.ai's directory, OpenAI's in Codex) is the app's to deliver and update, on
that store's own channel -- every pin in its text carries it (`cad +<version>@claude`, `@codex`), and its CAD
app's launcher is given it as an argument (`cad-mcp --channel codex`); a copy Cursor installed from a marketplace
added in Cursor is the repository, our own text, as Cursor fetched it, which text-to-cad does not update, so it can
be many releases behind, and is on the default channel: every `cad setup` keeps it, adds nothing of ours beside it, and says
how to switch (remove it in the app's own plugin manager, then run the install command again). An update writes the folder for the
new release and brings our copies along, a person's or an automatic one; a store's copy, and the version its
channel is on, are its store's to update. A model builds by running its script: `cad +<version> run model.py`, through
the `cad` command. The CAD app an agent
host starts is `cad-mcp`, of the `cad-mcp` distribution, which reaches this server.

**The `cad` command** (`~/.local/bin/cad`, `cad.exe` on Windows: `_internal/installations.py`) is the one file
every version is run through, written by `cad setup`, `cad setup --add` and `cad doctor`, and never replaced by a
release whose revision of it is older. It reads only its first argument. A pin, `cad +<version>[@<channel>]
<verb> ...` -- every command a skill runs carries its release's, and a copy a store delivers its channel too --
runs that version's own `cad` with the whole command line, and never another version: one not installed is
installed first by its own release (`uvx ... --from cad-server==<version> cad setup --add`), unless the channel's
pointer names a newer version already. That version reads the pin (`_internal/pins.py`): equal to its channel's
version, it runs; newer, or the channel's first use, it moves the channel to itself first (the default channel,
where the install command has run here, by the updater); older, it refuses. With no pin, the command runs the
default channel's version: its pointer; else, where the install command has run here, the installation the layout of
0.11.10 and earlier names current; else the newest version installed that has started, else the newest
installed, whose first command then makes the default channel's first use (its data imported, its pointer) before
anything else, so no version writes data before its first start. The channel a command is on is
`cad.engine.places.channel()` -- `default` for a pin that names none, and for no pin --, which its requests to the
server name and `cad run` hands its program. Each refusal is one line on stderr (from the version, one JSON
document on stdout under `--json`), with its exit status: 2 `bad_pin`, a first word `+...` that is no pin or names
no channel; 3 `cannot_install_here`, a version not installed that this shell could not install, with the line to
run outside the sandbox (`curl -fsSL https://texttocad.dev/install.sh | sh -s -- --add <version>`; in PowerShell
`& ([scriptblock]::Create((irm https://www.texttocad.dev/install.ps1))) --add <version>`), or one whose channel it
could not move; 4 `stale_pin`, a pin older than the version its channel is on now -- the chat's copy of the skill
is older than the one installed: the line says to read the skill again, and, where it still names the same
release, to bring this app's copy up (`cad update` for the default channel, the plugin's update in its app for a
named one), then read it again or start a new chat; 5 `other_version`, a version's own
`cad` given another version's pin. A `cad` command of 0.11.10 or earlier knows no pin: it says `+<version>` is an
unknown command (exit 2).

An installed version keeps everything it reads and writes in its own folder, `versions/<version>` in
the state folder: its data (`data/`: settings, Recents, the documents' records, the page token and
port, the telemetry spool, the version feed's cache, and its caches under `data/cache/`) and its code
(`code/`: its environments, the kernel's and `cad run`'s under `code/base/`, and their bytecode), and
its engine's door in `<version>` in the engine folder; a process with no version (a checkout or a test
under `CAD_STATE_DIR`, `CAD_ENGINE_DIR` and `CAD_CACHE_DIR`, a release of 0.11.10 or earlier) keeps the flat
layout below, in the state and cache folders (`cad.engine.places`). A version is made present whole --
its server and kernel environments, then its code marker -- by `cad setup --add` (`_internal/versions.py`),
which writes the `cad` command where it is missing or of an older revision and changes nothing else; each delivery
channel's pointer (`default`, `channels/<name>` in the state folder:
`_internal/pointers.py`; a pointer that is there and cannot be read, or names no version, is never taken for none:
a pinned command refuses, nothing is removed while one cannot be read, and only `cad setup`, the updater and `cad
doctor` write one again) names its version, moved by one routine that imports the new version's settings, Recents,
records, page token and port from the version it replaces at its first start (`_internal/imports.py`), proves the
version's server starts (its own start sequence, up to ready to serve), carries over what the version it leaves
wrote since, and removes the versions no channel is on that a pointer has named -- a version installed and never
named is no sweep's -- each carrying what it holds that its successor lacks into it first (records, Recents,
settings; never what it kept for telemetry, which moves once, to the next sender), in a process of that successor
alone, which writes them in its own formats; the layout of 0.11.10 and earlier
is imported from and, once the default channel has left it and that is safe, carried over, its code, records and
caches removed (`_internal/legacy.py`).

Each version in use runs its own server, reached through its own door alone, `<version>` in the engine folder,
and only the default channel's also answers the flat door every client of 0.11.10 and earlier and every process
with no version finds (`engine/daemon.py`'s `Bridge`, the only code for earlier releases). What moves each: a
channel's move stops its old version's server once no pointer names that version and nothing is in flight on it
-- a build, a draw, an export, an agent's tool call; never an idle app or an open page --, and the new version's
serves on the old one's port with the page token it imported; where the old one stays (another channel is on its
version, or work is in flight there), the new one takes the next free port, the update ends there, and the page
that asked for it goes to the new server's address (a CAD app card says to start a new thread); a server whose version no pointer names stops
itself once idle, handing the port it served pages on to the server of the version its channel moved to, and that
version's server, or its next move, removes its folder, its data carried in first; where that version is unknown, the
folder stays and `cad doctor` says why.
`cad stop`
and `cad status` act on one version's server: the pinned one, or the default's. Only the default channel's
version, on a device where the install command has run (its receipt), has an updater: every other server's page
and CAD app card show no update notice, no update button and no automatic-updates switch (the settings route
answers its `updates` null, `_internal/channel.py`'s `told`), and neither does a CAD app card whose launcher is on a
named channel, even where that channel shares the default's version.

Telemetry (`analytics.py`) describes each batch with two fields: `channel`, the delivery channel of the
requests or sessions it counted (a pin's or a launcher's, `default` for none, `dev` from a development build),
and `app`, the agent app that ran them, detected (the MCP handshake's client name, else the markers an app sets in
its shell, else `unknown`) -- one batch for each version, channel and app a window counted. A row a command or a
build keeps for sending says the three itself, so what a version had not sent when its folder goes is moved, as
it goes, to the version that sends next (`analytics.hand_on`), with the deletions it still owed. A no is said in
every version's settings, and the deletion it asks for is asked under every install id they hold: at once by
`cad telemetry off`, up to the first request the receiver does not answer, and by whichever version sends next.

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
