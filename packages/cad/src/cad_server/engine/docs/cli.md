# CLI

A page of [the engine's documentation](../README.md). A name in bold in parentheses, such as (**Kinematics**), is another page or a named paragraph of one: the index says which.

```
cad run [uv run's options] SCRIPT.py | -m MODULE | -c CODE | COMMAND [ARGS...]
                                             uv run, cad pinned at this release with the integrations
                                             the program's imports use: the models the script
                                             explicitly calls (and python SCRIPT.py in an environment
                                             of the library's, with its kernel); a command an
                                             integration declares (kicad-cli) with that integration,
                                             headless; a script that imports bpy with the blender
                                             integration, on Python 3.13, the one bpy is built for
cad run mujoco-studio --model scene.xml      MuJoCo Studio's web viewer on the model, reloaded as it
                                             changes: the person opens the URL it prints
cad requirement [INTEGRATION ...] [--json]   the exact requirement a Python of a program's own installs
                                             this release's cad by: cad[build123d]==<release>
cad model export ID DST [DST ...] [--tolerance MM] [--angle DEG] [--zero STATE] [--json]
                                             a model, by its document id: the document the engine holds
cad xbf|step export FILE DST [DST ...] [--tolerance MM] [--angle DEG] [--zero STATE] [--json]
                                             SRC an .xbf or a .step; --tolerance and --angle (a model's, an
                                             xbf's, a STEP's) mesh a .glb, an .stl or a .3mf to MM and
                                             DEG (Mesh)
                                             DST .step, .glb, .stl, .3mf, .dxf, .xbf, or .xml: an MJCF of the
                                             document (the robot description), its meshes in assets/ beside it,
                                             a scene.xml beside it where none is; .urdf: the same as ROS reads
                                             it, meshes/ beside it; --zero takes either at a mechanism state;
                                             what each holds said on stderr (--json: its row's robot)
cad glb|stl|threemf export SRC DST [DST ...] [--json]
                                             a mesh to the other two mesh kinds
cad TYPE snapshot SRC OUT.png [--display MODE|exploded=A|JSON] [--grid] [--camera C|authored]
                [--preview] [--pose NAME|NAME@SECONDS|JSON] [--annotation FILE] [--measurements FILE]
                [--width W --height H | --size-profile P] [--json]
cad TYPE snapshot --job PACKET [SRC] [the same flags, each over every job]
                                             every picture a Quick Edit packet (or a job file) names
cad serve DOC [--port N]
cad model inspect ID [REF] [--query Q] [--json] | xbf|step|glb inspect FILE [REF] [...]
                                             what the document holds, then its build closure; with REF
                                             (**References**): an element's facts and
                                             what made it, or a part's or an assembly's volume, mass and
                                             world bounds (a part's placement too); of a GLB, its nodes,
                                             meshes and animations (an STL or a 3MF, and a ref into any
                                             mesh, is refused, saying what shows it); Q summary (the default
                                             without REF), structure (the summary with nothing measured),
                                             closure, geometry (the default with REF) or build
cad urdf|srdf validate FILE [--strict] [--json] [the type's own options]
                                             its findings, each a severity, a code and a location
cad mujoco check FILE [--strict] [--json]    a MuJoCo model's file (an MJCF: no document type, an
                                             integration's operation), compiled by MuJoCo: what it
                                             refuses or warns of, the model-health checks, what collides
                                             as what and the contact excludes; in cad[mujoco]'s
                                             environment (made first) where this one holds no mujoco
cad orcaslicer presets KIND [--match TEXT] [--profiles DIR] [--json]
                                             DEPRECATED, with `complete` below: unlisted, and said so
                                             on stderr when run.
                                             the OrcaSlicer presets of one kind (machine, process,
                                             filament) a person can select, by name: an integration's
                                             operation on its tool's own files, found by name
cad orcaslicer complete --printer P --process P --filament F [--out DIR] [--profiles DIR] [--json]
                                             those presets written complete for OrcaSlicer's command
                                             line, and the files it wrote; always in this process
cad model|xbf|step dfm SRC [--process cnc] [--axes 3|4|5] [--turning] [--tools D,D] [--stock XxYxZ]
cad model|xbf|step dfm SRC [--process sheet] [--thickness T] [--k-factor K] [--bend-radius R] [--kerf W]
                [--sheet-size XxY]
cad model|xbf|step dfm SRC [--process molding] [--pull AXIS|X,Y,Z] [--wall-limit DEG] [--zero-tol DEG]
                [--cavities N] [--candidates]
cad model|xbf|step dfm SRC [--process printing] [--technology fdm|sls|sla|mjf|pbf] [--build-volume XxYxZ]
                [--angle-limit DEG] [--layer-height H] [--nozzle D] [--samples N] [--candidates]
cad stl|glb|threemf dfm FILE [--process printing] [printing's options as above] [--units U]
cad dxf dfm FILE [--process sheet] [--thickness T] [--k-factor K] [--bend-radius R] [--kerf W]
                [--sheet-size XxY] [--units U]
      ... [--material M] [--json]
                                             the manufacturing check: SRC a file or a document id;
                                             --process, given none, the parts' declared one (a model,
                                             an xbf; a STEP keeps none) or a DXF's sheet; --units an
                                             STL's, and a DXF's that declares none (not checked
                                             without); exact geometry and a DXF the build123d
                                             integration's (findings at face refs, layers), a mesh the
                                             trimesh integration's (at x, y, z); the general
                                             rules' verdicts (no shop's limits) and
                                             every measurement
cad model|xbf|step interference SRC [--pose NAME|NAME@SECONDS|JSON]...
                [--fit A B]... [--min-volume MM3] [--json]
                                             which parts share volume: every pair whose boxes meet
                                             answered, by the kernel wherever their meshes do not show
                                             air between them, as built and at each pose given; a named fit
                                             listed apart; each pair not measured said, and never passed
cad model|xbf|step solve SRC [--occurrence PART] [--json]
                                             a stress study's setup, the kernel's: the parts, the pairs
                                             that touch and a part's faces by ref; writes nothing
cad model|xbf|step solve SRC --study STUDY --out DIR [--deck] [--verbose] [--json]
                                             the solve, meshed by netgen and solved by CalculiX's ccx
                                             (cad[calculix]): result.json, result.glb, result.vtu and a
                                             picture of each field written into DIR, its findings and
                                             every number; exit 1 when a part yields or misses a check
cad kicad_pcb drc BOARD [--json] | export BOARD --to gerbers|drill|pos|step -o DIR | inspect BOARD
                                             KiCad's DRC and fabrication outputs, by kicad-cli; the board
                                             in one look, by the library's reader
cad kicad_sch erc SCHEMATIC [--json] | export SCHEMATIC --to pdf|svg|netlist|bom -o DIR
                                             KiCad's ERC and the schematic's outputs, by kicad-cli, run on
                                             the project's root sheet whichever sheet is named
cad kicad_sch inspect SCHEMATIC [REF] [--json]
                                             its sheets, parts and nets; with REF (#U3, #U3.7, #net:VBUS,
                                             #sheet:/Power/, #wire:<uuid>), what that names
cad kicad_sch snapshot SCHEMATIC OUT.png [--sheet PATH] [--border] [--display JSON] [...]
                                             one sheet drawn flat (the root unless --sheet names another)
cad server start [--port N] [--foreground] | stop [--json] | status [--json]; cad server --rotate-token [--yes]
cad delete DOC [DOC ...] [--dry-run] [--yes] [--json]
                                             each document deleted: its record, its document in the engine's
                                             cache and what the engine holds of it (**Delete**); never a
                                             file of yours. Asked first; --dry-run says what and how many
```

The rule: `cad <document_type> <operation> <file>`, the type's id as the registry names it
(`cad.registry`); `export` and `snapshot` are shared by every type that has them, `inspect` where a type
has it, and every other operation is named for what it does (`dfm`, `drc`, `erc`, `validate`); `TYPE` is any
type with that operation (`cad <type> --help` lists a type's). A file of another type is refused by name
before anything runs, exit 2 (`part.glb is a glb, not a stl: use cad glb snapshot`; `wrong_type`), as is a
file of no type (`robot.dae is not a urdf file: cad urdf takes .urdf`), and a file of the type that is not
there, by every type's every operation alike (`no such file: part.stl`; `not_found`), as is a file an option
names that is not there (`--urdf robot.urdf: no such file`; `--annotation`, `--measurements`, `--job`, a
schematic's `--display`; the snapshot refuses one as `snapshot.NoSuchFile`, a `SnapshotRefused`). A model's document
is a type of its own, `model`, with no file: `cad model export ID ...` takes its id, a file's type refuses
one (`ID is a model's document id, not a .xbf file: use cad model export`), and `cad model` refuses a file
the same way. The commands are the server's
(`cad_server.cli.document_types`), each type's its own module (`python -m cad_server.cli.xbf export ...`);
`python -m cad_server.engine VERB ...` takes the engine's verbs, its own entry.

Every `SRC` and `DOC` is an on-disk CAD file's path, for the file's type, or a model's document id
(`ids`), for `cad model`: a model's id is what `cad run SCRIPT.py` prints for it (`id:`, beside its page, `view: <engine>/<id>`). A document
id is read as the engine holds it, never built: one it does not hold is refused with the command
that builds it again, `cad run <the script that defines it>`. A script is never a source: `x.py`
and `x.py::fn` are refused as any other file that is no document is.

Every build and every verb goes through the engine: no command runs one in its own process. A
verb that starts the engine to answer says so, `engine started` on stderr, once, and only when the
engine that answers is the one it started (`client.on_started`); `status`, `stop` and `delete` never start
one, nor does an MCP host closing its session.
`daemon=False` on the Python functions (`Model.build`, `export`, `snapshot`) is a seam for tests
and debugging only: it runs in this process, cold, and no document is served: no page, and
nothing for `inspect` to read by its id.

**Help** -- `-h` or `--help` at any depth, or `cad help <command ...>` (`cad help step export`) -- prints
the help on stdout and exits 0, and does nothing else: it moves no earlier release's state, writes nothing
and says no telemetry notice. Nor does a command whose answer is JSON say the notice: it waits for a run a
person reads, and nothing is sent by default until it is said.

**Consent.** A command that destroys -- `cad delete`, `cad server --rotate-token` -- says its plan first, what it removes and how many (`cad delete --dry-run`
says it alone), and then asks: at a terminal, `... (y/N)` on stderr, anything but `y` or `yes` changing
nothing (`declined`, exit 1); where no one can be asked (no terminal, `--json`, CI), it changes nothing
without `-y`/`--yes`, failing `confirmation_required` (exit 2) with the exact command with `--yes`
(`cad_server._internal.consent`). `--yes` answers that question and no other. `cad setup` asks nothing:
installing is what was asked.

**The failure contract**, every command's alike (`cad_server._internal.cli_errors`). A failure's class
sets the exit status, the same with `--json` and without: 2 for the command line and its input -- a
command or an option it does not take, an argument missing or out of range, a file of another type, an
input that is not there, a destructive command where no one can be asked and no `--yes` -- which fails
the same way until the call changes; 1 for a failure of the work (a build, a render, an export, a tool,
the engine out of reach, a mistake of ours, a destructive command the person said no to); 130 for an interrupt
(Ctrl-C). A command's `--json` prints
its answer as one JSON object on stdout, and every failure as one JSON document there too, so a caller
reading stdout always finds an answer, with nothing else on stdout and no traceback (`--verbose`, where
a command takes it, puts one on stderr):

```
{"ok": false, "error": "part.glb is a glb, not a stl: use cad glb snapshot", "reason": "wrong_type"}
```

`reason` is one of a fixed set, added to and never renamed (`cli_errors.REASONS`): `usage` (a command,
option or argument the command line got wrong), `invalid_argument` (a value refused by name before
anything ran: out of range, a pose the document lacks), `wrong_type`, `not_found` (a file that is not
there, a document the engine has no record of or does not hold), `confirmation_required` (with
`"userActionRequired": true` and `"next"`, the command with `--yes`), exit 2; `declined`, `not_running`,
`other_release`, `engine_unavailable`, `failed`, `internal_error`, exit 1; `canceled`, exit 130. Without `--json` a
failure is its words on stderr. A
command line no parser can read is the parser's own usage error (`cli_parser`: every command's options are
read by the one parser, which takes no abbreviation of an option -- `--js` is no `--json` -- and suggests
at most one option, choice or command it is closest to, never running it). A refusal keeps its type
across the daemon: the worker answers its kind beside its words (`worker.refusal`) and the caller raises
it as that type (`api._failed`), so a pose a document lacks is refused the same, exit 2, whether a worker
or the caller's own process refused it.

`python SCRIPT.py` executes normal Python. Decoration only registers a model;
imports and definitions build nothing. A call such as `arm()` asks the daemon to
build that model and the children its body calls, prints its report -- its `id:` and its
`view:` -- when the call is the program's (made in `__main__`, wherever the model is defined:
`python caller.py` calling `parts.cube()` reports cube), and returns the document's handle
(`api.Document`), whose `.shape` is transferred only when it is read. The run line (`built …`,
or `took …` for a model taken from its key) is followed by the model's delta against its build
before, which the daemon says from the facts the worker's tree held (`delta`): `parts 21 (+2) ·
bounds 461.4 × 152 × 709.3 mm (was 504.9 × 152 × 709.3) · joints 1 · sequences 1`, with `warnings
N` where there are or were some, what a changed value was beside it, then `changed 2` when that
many parts have a geometry the build before had none of (by the geometry keys the build already
has, so an edit that keeps the bounds -- a hole, a thickness, a fillet -- is still seen) or
`materials changed` when only colours or materials did, nothing to compare on a first
build and no line for a failed one, and the report carries it as data (`delta`). Its bounds are
`inspect`'s, each part's box placed where it stands, to within each part's mesh tolerance: every
part starts from the kernel's quick box, and only the parts that could hold the model's extremes
are measured, their outermost faces exactly (a cold walk of tom lists 5 of its 221 parts and
measures no face exactly; juno's, 41 of 246 and 12 faces; measuring every part took 5.5 s and
8.2 s), and a tree whose signature is its last build's is not walked again, so a warm no-op pays
nothing measurable for it. A failed build
raises; a successful call resumes the script. A failed run's line says when the model's previous
good build is still served (`failed parts.py::bad; serving its previous good build`), and, the
error left uncaught, that the program stopped there: `the run stopped at bad`, and, where its code
calls a model after that line, `: a model it calls after this one is not built` (`model._calls_after`,
read from the program's source). Nothing builds those models for it: Python decides which calls run
(law 11), so each keeps the document of its last run until the program runs again. A body that fails in a kernel call with an OCCT exception (often bare: `Standard_Failure`,
`Standard_DomainError`, by OCCT build) has that call named on its failure line, as the memo saw it --
`failed plate.py::plate at Solid.make_box(0, 60, 5): the kernel refused it` -- and in its report
(`failedAt`; `memo.refused_call`). Put executable model calls under
`if __name__ == "__main__":` so other models can import their definitions.
`Model.build(verify=, profile=, daemon=)`, the debug seam, explicitly requests a build and returns its report.
No watcher selects, suppresses or introduces calls in a Python script.

A script is plain Python, loaded afresh by each build as Python imports it
(`build.load_script`), its folder on the module search path -- last, after everything
installed, where `python SCRIPT` puts it first, so a project's `cad.py` never stands in for the
library (`cad run` runs a program so too, `cad._internal.program`) -- so a module beside it
imports by its own name. A script whose module would bear the library's name or its earlier one
(`cad.py`, `cadgen.py`, or a package folder of either name) is refused. A script inside a package -- its folder,
and each above it up to the topmost, holding an `__init__.py` -- is that package's module by
its dotted name (`proj.parts.model`), imported as `python -m proj.parts.model` imports it:
its packages first, from their root, which the search path holds after it. So its relative imports
(`from .lib import WIDTH`, `from ..common import dims`) and the package by its name
(`import proj.common.dims`) resolve, in a build, in the warm worker build after build, and
under `python -m`; and `python proj/parts/model.py` takes its package the moment the script
imports the engine (`model.as_package_module`), so a relative import written above that
import fails as Python's own does. A script in a folder with no `__init__.py` is the module
its stem names. An edit to any module the script imports is read on the next build, which
re-runs the bodies that reach it (**Body retention**). The script and every first-party module
it imports are compiled from their bytes on disk, never from a `__pycache__` `.pyc`, and a
build writes no bytecode of them: CPython takes a `.pyc` as current by the source's whole-second
mtime and its size, so a same-length edit inside the second another tool compiled the file would
otherwise run that tool's code. The libraries a worker loads are another matter: the daemon and
its workers cache their bytecode under `pycache/<installation>` in the cache folder (`places.bytecode`, `PYTHONPYCACHEPREFIX`; one given is honoured, a caller's
`PYTHONDONTWRITEBYTECODE` is not, as the daemon serves every later client), never beside a
library or a model. A uv installation compiles nothing on install, so without it every worker's
start compiled build123d and the pure-Python libraries it loads: measured on a fresh
environment of the wheel, a fresh daemon's first build of a one-body model took 5.2-6.2 s with
none cached and 2.4-2.9 s cached. A folder no daemon started in 30 days goes (`PYCACHE_UNUSED_DAYS`). With no cache folder that is this user's alone, nothing is written.
The daemon's standby (**The engine server and its workers**) loads the kernel once the base exists:
the first load of a fresh installation on macOS also waits on the system's first look at each native
library, 43 s measured, which the standby pays while nobody waits. A build that waits
on such a load -- one arriving before the standby is ready, or the first of a worker whose kernel is
not loaded -- says so once, on stderr, when it has waited `worker.KERNEL_PATIENCE` (5 s): `loading
the CAD kernel for the first time in this environment, up to a minute`. A warm worker says nothing. An
environment without the build123d integration (**Running a model**) loads none.
A warm build does not make the document again: the worker holds the XCAF
document it last wrote and patches it (`document.Kept`). A prototype whose label
holds what a cold build would make of it keeps that label untouched; one that
changed or went is cleared at its place in the order and made again at the tag a
cold build gives it, with the assemblies that place it, and the references a cold
build orders by label (a colour's, a material's, a part's placements) are put back
in that order. The mechanism is written again only when a joint, a configuration
or an occurrence it names changed. So the file a patch writes is the cold build's,
byte for byte, and the document the worker serves is the one it wrote.
Nor does the day: the creation date the BinXCAF driver writes in the file's
header is always `01/01/2000` (`document.WRITTEN_DATE`, put over the driver's in
place), so two cold builds of the same code are the same bytes on any day.
If a body raises, the error is reported with the model's frames and the
previous files stay. The report also keeps the error's whole traceback as facts (`raised`,
`build._raised`: its type and every frame, the library's included), and the daemon decides
from them whether the failure is a mistake in cad's own code (`reportable`,
`daemon._reportable`) by the rule telemetry counts a build's crash by
(`analytics.told_signature`), so the tracker hears of what telemetry would: an error Python
raised in cad's code at a line that is no `raise`, past the memo's and the history's wrappers
of build123d's calls. The model's own code, a library it called, the kernel refusing a call and
the library refusing what it was given are the model's to correct. The page's record of the failed
build carries `reportable`, and the card offers Report Issue only where it is not `false`; a
worker that died under the build is reportable. The program's own call prints those frames once on stderr, then `failed
<script>::<model>`, and nothing else; the call still raises (`EngineError`), so a caller may catch
it, and left uncaught it ends the program with status 1 without its traceback again
(`model._told`). A call the engine never served -- none runs and this shell's sandbox cannot
start one, a folder refused, its port held -- raises its `ConnectionError` or `EngineError` the
same way: left uncaught, its one line on stderr (`cad: <why>`, as a `cad` verb says it) and
status 1, no traceback; caught, nothing said. Builds run in the daemon's warm workers, at most one per core alive
(**The engine server and its workers**). `CAD_ENGINE_DIR` moves its door and lock; the client and the server resolve it alike (`places.engine_dir`: a `..`, a symlink or a trailing slash names the same folder). On POSIX the folder must be the user's own and closed to writing by anyone else (`places.folder_refusal`): whoever owns or can write the folder could take the door's place, so a client refuses to connect or start there and the daemon refuses to lock there, saying why.
`CAD_ENGINE_MEMORY_MB` sets the server's memory budget (**Document lifetime**); the document
cache has no size to set, keeping every document until a person deletes it
(`CAD_ENGINE_CACHE_IDLE`, its idle seconds, is the tests' seam).
`CAD_ENGINE_DEFAULT_PORT` stands in for 3245 as the default port (`daemon.default_port`): the
tests' seam, so a suite holds or frees a default of its own and never touches the machine's 3245.
`CAD_ENGINE_MEMO=0` turns memo hits off. `CAD_VIEWER_WARM=0` keeps `cad viewer`
from warming the engine at its launch (**The viewer and the snapshot**). `CAD_ENGINE_MESH=processes|inline`
picks how parts are meshed. The default, `processes`, uses a warm pool of
processes started with the first page or view, each handed one part's shape as bytes,
largest first, a large part meshed with the kernel's face parallelism too.
`inline` meshes one part at a time over the kernel's own threads. Python
threads add nothing, because the kernel's mesher holds the interpreter's lock.

A served document stays in memory. `serve` reads its file once; from then on
the script's worker sends each build's document to the daemon the moment the
xbf is in place, before the exports are written: its structure, made from the
build's tree, the meshes of the parts that are new to it and to the daemon,
meshed in the worker, and the shapes the daemon lacks. The daemon puts it in
place of the one it serves and answers the waiting page. The file is read
again only when another process rewrote it.

A served STEP is read in a reader process of the server's, never in the daemon
(the XCAF reader's working memory is many times its result's, and its allocator
keeps it): one read per process, the next process started and warm meanwhile,
answering the structure and each part's shape bytes, which are all the daemon
keeps. Reads that come while one is under way (a board's part models: 22 files at once on
KiCad's "video" demo) are read beside it by up to three helper processes (`serve.READERS`: four
reads at once at most, and never every core), each reading up to 16 files before it goes: only
files of at most 8 MB (what such a parse leaves in a process is about 100 MB), never under memory
pressure, and the helpers go once no read has been under way for 10 seconds, so with no page
reading the daemon's children are what they were. A larger file waits for the one reader. Measured
on a 10-core Mac, that board's 22 models: 19.0 s to read one at a time in fresh processes, 3.0 s
so. The read is held by the file's bytes, so the same bytes served again --
the file touched, copied, or put back -- are not parsed again while the daemon
lives, and a part's key is made from those bytes and its label, so its mesh is
not made again either. A STEP is read outside the server's lock (every other
document is served meanwhile), and one rewritten while it is served is read
again in the background: the page keeps the old version until the new one is
in. Its structure says how long the parse took and which process made it
(`read`: `{seconds, process}`).
