# cad

The library: CAD models written as Python, imported as `cad` (and as `cadgen`, its earlier name, an
alias of it), built by the engine (`cad.engine`) into live XCAF documents and the files those models
declare (XBF, STEP, GLB, STL, 3MF, DXF). It is one of three distributions released together, at one
version: the library; the server, `cad-server` (imported as `cad_server`), the computer's one
daemon that builds, keeps and serves the documents, with the CAD Viewer, the CAD app's MCP endpoint
and the command that runs them all; and the shim, `cad-mcp` (`cad_mcp`), the stdio transport
an agent app starts. The server ships what is not Python: the CAD Viewer's client and the CAD app
page, which it serves, built from their JavaScript packages and bundled in at build time (the JS
*source* never ships). Snapshots are drawn by OCCT (a KiCad board's flat, with Pillow), never in a
browser. This file holds the laws of
all three.

A **document** is what a person reviews: one instance of a **document type** (below), either a file read on
its own or one built from code -- a model, built by the engine. Documents exist so that a person can review the
subjective output of an agent, a design, and answer it through the viewer's tools: annotate, select, quick edit.
The laws below say how they are made, named, kept and served.

```python
from cad import step, xbf
import build123d as bd

@xbf("XBF/arm.xbf")                      # XBF/arm.xbf beside the script
@step("arm.step")         # and its STEP, a translation of that document
def arm():
    return bd.Box(10, 20, 30)


if __name__ == "__main__":
    arm()
```

```bash
cad run arm.py                                 # builds it in the engine's warm worker, printing its id
cad model export <id> arm.3mf --tolerance 0.01 # the model as the engine holds it, by that id
cad xbf export XBF/arm.xbf arm.glb arm.stl     # more translations of the document it wrote
cad xbf snapshot XBF/arm.xbf arm.png           # a still of it, drawn by OCCT
cad serve XBF/arm.xbf                          # the document on a local page
cad xbf inspect XBF/arm.xbf                    # what it holds, then its build closure
```

The same operations are functions of each type: `xbf.export("XBF/arm.xbf", "arm.glb")`,
`xbf.snapshot(...)`, `xbf.inspect(...)`; `model.export(arm(), "arm.glb")` exports the model a call returns,
and `step.read("vendor.step")` reads a file into a model.

## Definitions

These words mean one thing each, in the code, the commands and every document.

- **Document type**: what is in a file. Always called "document type". Each has one lowercase underscore
  id, the same in Python, the CLI, the registry, the server, the viewer and the JavaScript: `model`, `step`,
  `glb`, `stl`, `threemf`, `dxf`, `xbf`, `urdf`, `sdf`, `srdf`, `kicad_pcb`, `kicad_sch`. 3MF's id is `threemf`
  because an id must be a valid Python name. The registry (`cad.registry`) maps file extensions to ids (`.step`
  and `.stp` are `step`). `model` is the one type with no file: a model built from code and held in the
  engine's memory, addressed by its document id or the handle its call returns (`@model` declares one);
  `xbf` is the `.xbf` file the engine writes of one, and takes files alone.
- **Document**: one instance of a document type, either a file read on its own or one built from code.
- **Integration**: our support for one third-party tool, named for the tool's own project (`build123d`,
  `kicad`, `trimesh`),
  never for a capability. It is three things: one extra, `cad[<name>]`, grouping the dependencies our code
  for it needs; our code for it -- helpers that take its objects, producers and operations; and a process
  kind: in-process, separate process, or both.
- **Dependency**: one installable package or binary, named only in the distribution's metadata and lock
  files, never in the API, the CLI or the docs. It becomes an integration only when we write code for that
  tool: OCP is a dependency of `build123d`, not an integration.
- **Producer**: code that makes a document type from some input. Many integrations can produce one type.
  Each type documents the content it carries, and each producer states which parts of it it provides.
- **Edit**: code that changes a native file of a type in place, in the caller's process, rather than
  making it: `kicad_pcb.edit` and `kicad_sch.edit`, a `with` block over the open document. An edit is no
  producer and no operation.
- **Operation**: one of a closed set. `export` and `snapshot` are shared by every type that has them, and
  `inspect` and `read` are where a type has them; every other operation is named for what it does: `dfm`
  (a 3D type's manufacturing check), `drc` (a board's design rule check), `erc` (a schematic's electrical
  rules check), `validate` (a robot description's conformance check). Each type implements those that make
  sense for it.

`python -m cad.registry <type>` prints a type's help, worked out from the registry: the content it carries,
its operations and what writes it.

**PURPOSE** — the engine and its command surface: models built in a warm worker whose memo
makes an edit cost what it changed, documents and their exports, kinematics and configuration sequences,
materials, references to geometry, snapshots drawn by OCCT; the CAD Viewer (`cad viewer [FILE]`: a
launcher for the engine’s one page, every document at `/<id>`, every file read by its absolute path); CAD beside an agent's chat (`cad-mcp`: a stateless stdio peer of the engine’s
HTTP MCP endpoint, with tools and the app page owned by the engine); the URDF, SDF and SRDF checks; a 3D
document's manufacturing check (`cad.<type>.dfm(source, process="molding"|"printing")`, measured with
trimesh); engineering drawings (`@eng_drawing`); and semantic PMI with the model-based definition around
it (`cad.build123d`: datums, dimensions and tolerances on a part's faces, kept in its xbf and exported as
AP242's; notes, named views and their presentation, kept in the xbf alone).

**MAY DEPEND ON** — the Python ecosystem it declares (OCP/build123d lazily, never at
`import cad`), and nothing of the server's or the shim's. Never app code, never JavaScript.
Its one required dependency is numpy, the meshes' arrays: what the server imports of it -- the
document model, the protocol a client speaks, the build's words -- imports no CAD kernel. The
kernel (OCP, build123d, bd_materials, threejs-materials, matplotlib, shapely) is its `build123d`
extra, which the server installs, on first need, into the environment its own kernel processes run in
(the engine's **Running a model**). `cad run` runs a program as `uv run` does, in an environment the
server makes for it: the library pinned at the server's release with the integrations the program's
imports use (worked out without running it, from the library's table of integrations,
`cad._internal.integrations`; a script's header that names `cad[...]` chooses them), and the packages
the program names itself -- its script's inline metadata (a `# /// script` block's `dependencies`),
`cad run --with`, or its uv project's. A header or project never pins the library to another release:
the device decides it. A person who runs models with a Python of their own gives it the library at the
server's release (`cad requirement build123d` prints it: `cad[build123d]==<release>`): a script run
with that Python is built by a worker of that Python, the environment's own packages importable
there. The library's layer over that kernel -- the
model API and the engine's `kernel/` (the memo, element naming, the determinism settings) -- is the
build123d integration: a
third-party technology and the application layer over it are an integration, named for the
technology, and its extra carries the same name.

**DEPENDED ON BY** — the server, `cad-server`, which pins it at its own release, and through
the server every skill that runs `cad`; the alias `cadgen`, which installs it.
The CAD Viewer is the server's: it serves `cad_server.viewer`’s client, HTTP application and
every STEP and `.xbf` a page opens on one authenticated listener, without a relay.

## The rest of the package's documentation

This file holds the LAWS. The engine's own README holds the mechanisms they constrain; where
the two disagree, the engine's README is right.

| Document | What it is for | Go there when |
|---|---|---|
| The engine's README, `cad_server/engine/README.md` in the server's distribution (`cad-server`) | The engine: models and decorators, the engine server and its workers, the door, progress, the viewer and the snapshot, exports, kinematics, couplings and configuration sequences, materials, imports, placements, the mesh and its wire format, element names, references, body retention, queries, memo functions and the build closure | changing anything a build, an export, a snapshot or a served document does |

## The design laws

These are LAWS, not conventions: a change that violates them is wrong even when it works.
Each of the 31 says, after its title, what it binds: *every document*; *models* (a model's document,
built from code, in memory, no file of its own); *file documents* (a document that is a file read as
it is: a board, a schematic, a robot description, a mesh, an opened STEP or xbf); or *the package*
(the distributions alike).

1. **An xbf carries its build closure as pointers and digests.** *Models.* Script and function,
   modules, data inputs, the toolchain (versions, the Python and the machine) and the key; never
   source, never lines on elements, never input contents, nothing of git's; names remain the
   per-element tie to code (the engine's **Build closure**).
2. **Only requested files to disk.** *Every document.* The engine writes the files a model declares -- the xbf and the exports
   its decorators name, nothing beside them -- and the operating system's coordination for its
   warm process: a door (a named pipe; on Windows a port file), a lock and its connections' pipes, in
   a folder only the user can make: `cad-engine` in `$XDG_RUNTIME_DIR`, else in the user's own
   temporary folder (on macOS the one the system names, whatever `$TMPDIR` a sandbox sets; else
   `$TMPDIR`), else `/tmp/cad-<uid>`; on Windows `~\.local\state\cad-engine`, out of the local
   application data an app package virtualizes (0.8's was `cadgen-engine`: neither release finds the
   other's door) -- and the server's own
   state in the user's state folder (`cad`): settings, Recents' small previews, and the registry of the
   documents it has built, been handed or opened, one record each that points at its script or
   file, the user's one page token, the engine's record (the port it rolled to while 3245 is another
   program's; both this user's alone), each registered installation's record
   (`installations/<version>.json`: its python, its console script, its environment) and which one
   is current (`installations/current`: the release whose engine the device runs), and the
   releases an update installed (`releases/<version>`: each one's environment, made by uv from its
   cache; the one before the current kept as the way back);
   never geometry and never source. In the
   platform's cache folder (`~/.cache/cad`, on Windows too) it keeps, under `documents/`, the
   engine's cache for documents, and nowhere else there: each model document's bytes as it last
   built them, its own file, never a declared or exported xbf (the same bytes), made again by a run
   of its script (a shape's by the program that handed it over), so a restart opens every project
   at once; and, for a file document, the views derived from its bytes under that document, keyed by
   those bytes (a KiCad board's plot, its refilled pours, its DRC and its kept exports:
   `documents/<id>/kicad/<key>/`), so a changed file is a new entry and nothing stale is served --
   every one regenerable, kept until the document is deleted (`cad delete`, the home's Delete), which
   deletes it with them -- nothing evicts it; under `pycache/` the bytecode its own processes compile of the libraries they load
   (`PYTHONPYCACHEPREFIX`, a folder per installation), regenerable too, so nothing is written
   beside a library or a model; and under `base/` the environment the engine's kernel processes run in, an
   installation's base, `cad[build123d]` at its release, made by uv from its cache on first need, and
   beside it each environment a program's run made (`cad run`: the library pinned with the integrations
   its imports use, and the packages it names), regenerable as well, those of the release before the
   current kept as the way back (the engine's **Running a model**). The code stays the only source of truth: a document is what its
   last run made, the engine never checks the code on disk against it, and nothing reruns -- when
   to run the code again is the agent's call. It writes no
   sidecar, record of a build beside a model, index, memo, mesh or parsed document (but the file
   documents' derived views above, in the document cache), and no derived file beside an input. A model whose document -- in its warm worker, else the cache -- holds the closure the
   model has now is not run, whatever files it declares: they are exports of the document, written
   after it. Explicit viewer exports write only the requested
   artifact to managed temporary storage for delivery; no source or intermediate XBF
   is written (the engine's **Viewer exports**).
3. **Three sides, by where the code runs.** *The package.* The library -- what a model imports and what runs in
   a worker: the model API, the kernel side of the engine, the document model and the protocol a
   client speaks -- imports nothing of the server's or the shim's, so a model runs where only it is
   installed; it imports nothing outside itself but its own dependencies, the standard library and
   each integration's extra, that extra only in that integration's environment (law 26; the kernel is
   the `build123d` extra's, which the engine's workers run in). The server -- what runs in the daemon
   or a `cad` command: the daemon, the registry, the CAD Viewer's and the CAD app's servers, every
   verb, the environment makers, telemetry -- imports the library's kernel-free modules, and never
   the kernel or an integration's code (law 29). The shim (`cad_mcp`), the stdio transport
   an agent app starts, is the standard library alone. The server reaches into the library, never the
   other way: its telemetry is an observer the engine calls with plain facts (`engine.api.observers`),
   which the server's commands append.
4. **A model's document is XCAF; files are explicit.** *Every document.* A model's document is
   XCAF: a live model holds an XCAF document; `@xbf` or `--xbf` serializes it as native BinXCAF.
   It holds: units in millimetres,
   prototypes and instances with placements, a name on every part and instance, colours and
   materials per part and per painted face, element names on face, edge and vertex labels, an
   assembly's mechanism, and each part's semantic PMI as XCAF's own GD&T objects, notes and views
   (the engine's **PMI**). STEP, GLB, STL, 3MF and, of a planar document, DXF are translations
   of it; `cad <type> export` writes any of them from the xbf alone. A file document -- a board, a
   schematic, a robot description, a mesh -- is its file, read by its type (law 25).
5. **The memo is the only build cache, and it lives in the worker.** *Models.* Every kernel operation a model
   runs is keyed by its inputs, and so is every question it asks of what they made: a validity
   check, a volume, a distance. A hit hands back the objects the first run made, or the answer it
   gave, and a miss makes everything downstream of it miss. So an edit costs what it changed, and an element
   keeps the name its feature history gave it across edits. Across a restart, a model's build
   is cold but for its document in the cache -- every model's alike, taken whole by its key or not
   at all; a declared file, its xbf too, is never a source -- and what a restart shows without a build
   is the engine's document cache (law 2): the last built state, never a step of a build. A file
   document's derived views kept under law 2 are views of its bytes, not a build cache.
6. **One document per model, with one id.** *Every document.* Every called model makes one document, and a call
   returns its handle (`.id`, `.url`, `.name`, `.shape`, `.export`, `.snapshot`), never a bare
   shape. Every id is one formula, `uuid5(NAMESPACE, canonical(scope) + "::" + name)`
   (`ids.derived_id`): a model's script and function (`ids.model_id`), an opened file's path and
   no name (`ids.file_id`, inside the engine only: its public name stays its path), a shape handed
   over its calling script, or the working folder, and its name -- the same in every process,
   worked out without asking the engine. Identity is namespace plus name: the namespace is
   the script's folder, with no project detection. A model's name is its identity within its
   namespace, the function's name by default, `name=` gives it another. An explicit name uses the
   folder as the formula's scope; one that another file of the folder declared at its last run is
   refused, naming both declaration locations, until that file is gone or runs again without it. Unnamed functions in different files keep their script/function ids. A
   function in a file is a model (the registry points at its script), and a shape is handed over
   (`model(shape, name=...)`: held and kept, never rebuilt); every one is recorded and kept in
   the engine's document cache alike. A function is declared by `@model` (no file) or by its file
   decorators (those files), never both; file decorators write only their named outputs. No xbf,
   mesh, memo, provenance or derived file is written for a document beyond what it declares. A
   document lives until a person deletes it (`cad delete`, the home's Delete); its worker
   retiring does not end it, nor does memory, which reads it again from the cache. A document
   that is not held names the command that builds it again; the engine never runs it (the
   engine's **Document lifetime**).
7. **Provenance is served live, never written.** *Models.* What made an element -- the feature, its
   operation, the function, file and line of its call -- lives in the trace of the worker that
   built the document, and is asked of it while it lives (`made_by`, `cad <type> inspect`). A model's
   document opened with no such worker has none to give, and says so (`made_by: null`); a file --
   a model's declared xbf among them -- names no model and answers none.
8. **Poses and motion definitions, never frames.** *Models.* The document carries kinematics -- the
   mechanism, its mechanism states and its configuration sequences -- as poses and definitions,
   never baked frames or clips. A GLB export is the one place a sequence is baked, into a clip of
   the GLB; the engine plays nothing.
9. **Names are the durable tie to code.** *Models.* An element's name is spelled from the function that
   made its feature and the author's name for that feature, never from a line or a file: moving
   code renames nothing, and the file holds no line to go stale.
10. **A file decorator requires an explicit output path.** *Models.* `out` is required; `name=` optionally names the model;
    omitted paths and `None` are refused. Whenever the model it decorates runs in a
    build -- the build's target, or a child another model's body calls -- or is taken from its
    key, that file is written, once per build, from the model's own document, exactly as an export
    of it writes it: translated, compared, and written only where it differs or is missing; a
    GLB's animations are baked from the code when that GLB is written. A model with no file
    decorator writes nothing.
11. **Decoration only declares; a model script is Python.** *Models.* A script runs only when Python
    runs it; no verb imports or builds a script. Importing the library or
    defining a decorated function never builds a model, writes its outputs, starts a
    worker, or exits the caller. An explicit call builds the model and writes its
    declared files, then returns to the caller. Python controls which calls run and
    in what order, including its `__main__` block and conditions; watchers never
    change that control flow. The library consumes no script arguments. Engine switches
    are environment variables.
12. **A model is a Python script.** *Models.* Decorated functions declare models; explicit calls
    build them; `python script.py` runs the program. No command builds source text.
13. **The document's kinematics are AP242's, and the library stores no kinematic fact the
    standard cannot name.** *Models.* Every entity and attribute of the mechanism subtree is ISO
    10303-105's as Part 21 writes it (edition 4's domain model's where Part 21 has none);
    only the root says the schema and the units. What the standard cannot say is not
    patched with an attribute of its own: it is dropped, or refused by name at document
    time (the engine's **Kinematics**; a conformance test walks the subtree and holds it). The
    authoring functions are named after the entities they write: `mechanism_state`
    (`mechanism_state_representation`), `configuration_sequence`
    (`interpolated_configuration_sequence`), and `gear_pair`, `rack_and_pinion_pair` and
    `screw_pair`, each refusing a joint its pair does not relate.
14. **Each distribution ships alone.** *The package.* An installed distribution is the whole world: its Python,
    what it bundles (the server's `_runtime/`), and its documents. It works with the repository it
    was built from gone -- and its markdown must read that way, referring to nothing outside its
    own distribution, another one's files included.
    *Pressure-test*: every sentence in a distribution's markdown must be true and actionable for
    someone who only ran `pip install cad==<release>` (or `cad-server`, or `cad-mcp`). Naming a bundled thing ("the JavaScript runtime
    bundled at build time") passes; a repository path to its source, a repository script, or a
    repository workflow does not. This README also holds the laws of all three distributions, so a
    law may name another distribution's file, said as that distribution's ("the server's
    `updates.py`").
15. **Compatibility, by who pays for a break.** *The package.* A change is judged by who absorbs it and whether
    they can. Four tiers:

    **Tier 1: what an agent reads each session** -- the skills, the `cad` command's verbs and flags,
    the CAD tools' arguments, the wording of docs. Hard cutovers only, release over release. A retired
    surface does not exist: no alias, no shim, and no error that recognizes its old spelling to
    explain what replaced it. A removed command, flag, argument, key, module or name gets what the
    current contract's ordinary validation says -- an unknown command, an unrecognized argument, an
    unknown key, an `ImportError`, an `AttributeError`.
    *Pressure-test*: use a removed spelling; the error must read exactly as it would for a name that
    never existed.

    **Tier 2: the library's public imports** -- `from cad import model` and the rest of what a model
    script imports: the document types, the integrations' helpers, the model contract. These are changed
    only when a release must: a change breaks scripts a person already has, which an agent then has
    to find out about and rewrite. When one is unavoidable, the earlier spelling stays an alias of the
    SAME object for a release at least: it warns once per name per process, with `CadDeprecationWarning`
    (a `FutureWarning`, which Python shows by default), naming the new path ("cad.read_step is deprecated;
    use cad.step.read"), from the lookup itself, so the warning names the line of the program that spelled
    it, as the person named the file. A run says each once: the program's own process says what its import
    spells, and the worker that imports the same script to build its models does not say it again. An
    alias needs what its new path needs, so `cad run` gives a 0.10 script the integration its 0.11 spelling
    gets. An alias is kept out of every `__all__` and every document but the migration guide; a test pins the
    table of them (`cad._internal.aliases`). An agent migrates a project on first touch.

    **Tier 3: a person's data** -- documents, the state folder and its records, Recents, settings,
    receipts, the plugin folder. A release reads what the previous shipped release wrote, writes the
    current form, and migrates on first touch, once: never the old form written, never a downgrade.
    Opening, viewing, importing and exporting a saved document never requires its source or a rebuild
    because text-to-cad was upgraded: the engine reads `xbf/8`, `xbf/9` and `xbf/10` and converts `xbf/8` in
    memory, without executing model code or changing source or cache bytes, under a migration record
    that leaves the original build closure and toolchain provenance unchanged; an explicit export to
    another XBF path saves the upgraded document atomically, and opening one does not rewrite it;
    an unsupported format or a failed conversion keeps the original bytes and record and says why.
    Build-cache reuse is separate: running a model compares the current key and may rebuild. This tier
    retains no retired authoring API. The engine's README's **Build closure** describes the conversion.

    **Tier 4: protocols where two releases meet while both run** -- the door, the CAD app's server and
    its page, the update handshake, the HTTP API (`/api/v1`), a page's reload probe, the version feed,
    the installation and release records, the analytics schemas, and the PyPI names old pins resolve
    through. Each is numbered or frozen in a golden, so a break is never silent: a change within a
    number is additive, and unknown keys and ops are ignored; a breaking change bumps the number.
    Whether the newer side keeps answering the previous number is decided case by case, by what a
    mismatch would strand and whether the stranded side can say what to do. Where it does not, the
    side that meets a number it does not speak says so in one line and names which package to update,
    and to what release, never how to install it: the person or the agent has their own way -- but
    for the server, whose one way the line names (`cad update`): installing `cad-server` into a
    project's environment neither registers nor moves the device's server. The analytics receiver
    keeps every schema a released client sends. The worker contract (`cad.engine.contract`: the worker
    protocol's number, the document format, the kernel), by which a script run with a Python of its
    own and the server meet, is decided so: a contract the server does not speak is refused before any
    worker starts, in that one line, with no window; one contract of two releases builds, and the
    script says once which package to update. 0.8's door had no number, and 0.10
    meets 0.8 by stopping it, never by answering it: 0.8's engines keep their own folder, no process
    of 0.10's speaks to one of 0.8's, and `cad setup` stops 0.8's server with 0.8's own `cadgen stop`.

    **The earlier name.** `cadgen` is the library under its earlier name, not a retired surface:
    the `cadgen` import is the library itself, every name and every module of it `cad`'s own
    object (one copy, and nothing said of it), and the `cadgen` distribution
    installs the library at its own release. Nothing else of 0.8's names is kept: the `cadgen`
    command, the `CADGEN_*` variables and `cadgen mcp` are gone, as this law says.


16. **Closed vocabularies.** *The package.* Every declaration surface has a closed key/kind set. An unknown key
    is an error naming the supported set, never silently ignored.
17. **Loud failure or correct output, nothing between.** *The package.* The cardinal sin is plausible-wrong
    output at exit 0. No silent fallbacks, no globs, no guessing; a failed write or render leaves
    no file this run wrote; an earlier file stays byte for byte.
18. **Nothing waits on the network.** *The package.* Once installed, text-to-cad works offline: every command,
    build, snapshot, server and page. Its own requests are two: telemetry (the server's `analytics.py`, usage
    counts under a random id, sent by default once a `cad` command has said so -- never its help, nor an
    answer in JSON, which no person reads --, and never
    after the person's no) and the hourly version check (the server's `updates.py`). Both run in the
    background and fail silently: no start, command, build, request or tool call waits on them.
    An update waits on the network because a person asked for it -- the update button, `cad
    update`, the install command run again --: it reads the feed then, and uv installs the release
    from its cache and the network for what that lacks; one that cannot reach it says so in a line
    and leaves everything as it was. `cad update --dry-run`, asked what an update would do, reads the
    feed the same bounded way and keeps nothing of it, saying so in a line when it cannot reach it. An automatic update (on by default, `cad update auto off` to
    leave every update to the person) waits on nothing: the server installs the release in the
    background and switches only once it has been idle for a minute. It takes a release that breaks
    nothing, as Semantic Versioning numbers it -- a patch release below 1.0, a patch or minor release
    from 1.0 --; one that may (a minor or major release below 1.0, a major one from 1.0) waits for the
    person's click.
    An integration's environment (`cad[kicad]`'s, with kicode; `cad[trimesh]`'s) is fetched once, the
    first time a command needs it, from uv's cache and the network, and works offline after that; a
    first-need fetch that cannot reach the network says so in a line, and nothing else waits on it.
    A command sends nothing itself: what it counted -- an engine verb's build, export or
    snapshot (`_internal/engine_telemetry.py`, the server's observer of the engine), a drawing, a
    crash; a model's own process, where only the library is installed, counts nothing -- is kept
    in a small file beside the settings (`analytics.spool`), which the CAD app's
    and the viewer's background sends take, and a command that finds it has waited more than a
    window, with no other process sending, starts a sender detached that sends it and exits
    (the server's `_internal/telemetry_send.py`). A process that exits sends nothing either: its last batch is
    kept beside the settings, and the next process that sends sends it, in the background. One
    wait remains, bounded: `cad telemetry off`, which waits for the deletion it asks for.
    The pages load nothing from the internet: everything they show ships in the wheel.
    *Pressure-test*: with an installed server, each integration's environment made by its first
    need, and every request refused (a proxy on a closed port), and again with every request
    hanging, start a server, open a view, call each tool, and run a build, a snapshot and each
    integration's operation: each works, and nothing waits on a request beyond the one wait above.

19. **Connected means warm.** *Models.* A served document's outstanding version wait or recent
    sync marks it watched; a watched model document keeps its worker, and a watched file -- a
    model's declared xbf among them -- none. No timer retires a worker: memory does, and it
    retires one whose document a page watches only when no other is left. The engine outlives its clients; a page
    closing never stops a worker. The worker-count cap never retires a worker whose document a
    page watches; it is exceeded instead. The memory cap may retire it (the
    engine's **Architecture** and **The engine server and its workers**). Memory may take a
    document out of memory, for the engine's cache to give back, only when nothing watches it (the
    engine's **Document lifetime**).

20. **One engine serves the device; tabs select documents at `/<uuid>`.** *Every document.* It is the current
    installation's: every client, whatever its release, attaches to it or starts it -- a client with
    no installation registered starts none: the library never starts a server of its own environment
    -- and only an
    update moves it to another release -- one the person asks for, or an automatic patch update once
    the engine is idle (law 18) -- on the same port with the same token (the engine's **Starting and
    updating**). A tab names a model's id, or a file's id after a launcher
    registers it; Python scripts are never documents. A page never replaces or re-executes the engine. Its one page and document reads
    share its authenticated HTTP listener. `serve` and `viewer` always start or reuse it, with no
    standalone serving mode, and no Python function starts, stops or serves it (law 21). Launchers
    exit; clients closing never stop it. Kernel operations run in child processes, never in the
    engine's request threads. There are no page sessions: the explorer opens where it was last, else
    the person's home folder, and a launch's folder resolves only the relative files it names; each
    MCP session owns its views and resource. The
    stdio shim owns only connection metadata, and the one act a text host's `cad_show` asks of
    the person's machine: it opens their browser, in the environment its host gave it, and the
    engine, which runs in whatever environment started it, never does. The shim tells the engine,
    on its session, whether the page opened before its host has the answer, and keeps nothing of
    it after; the engine counts a page as open in a browser only once told it opened. Sidebar
    sharing stays in memory, and host quirks stay in the shim and page. The viewer's routes are
    the page's alone (`cad_http`), behind the session capability delivered in UI-only launch
    metadata. Only the person answers telemetry, through a page or the telemetry CLI. See the
    engine's **Architecture**.

21. **Operations on documents are Python functions the CLI exposes; process control is the
    CLI's alone.** *Every document.* A type's operations -- `export` and `snapshot`, `inspect`, and those named for what
    they do (`dfm`, `drc`, `erc`, `validate`) -- are functions of each document type (`cad.model.export`,
    `cad.xbf.export`, `cad.kicad_pcb.drc`, `cad.urdf.validate`, ...), one to one with the commands that
    call them (`cad model export`, `cad xbf export`, `cad kicad_pcb drc`, `cad urdf validate`); serving, the engine's status, stopping it and running it (`cad serve`,
    `status`, `stop`, `server`), and deleting a document (`cad delete`, which the home's Delete is too),
    are commands only, with no function of the library. Every successful server-backed build reports its id and localhost
    viewer URL, including a build with file outputs. A cold `daemon=False` build has no served
    URL.

22. **A verb's option is about the picture or the path, never the model.** *Every document.* `export` takes a
    document and destinations: what the file holds, its parts and their placement, colours and
    motion, is what the code built, so no option selects a part or a state; its one option, an
    STL's or a 3MF's mesh tolerance, is how finely the file's triangles follow that, not what it holds. `snapshot`'s
    options describe the picture (the camera, the display, the size, the state the mechanism
    is drawn in); `serve`'s and `status`'s the process. Anything that changes what a document
    is, is a function in the model's code: a part's own model, or a model returning the
    assembly in a state (`cad.build123d.posed`).

23. **Push, not pull: a model is what its last run told the engine.** *Models.* The engine's knowledge of a
    model comes from a run an agent or a person starts (`python model.py`, `cad run model.py`),
    which pushes the model's code, its key and its document to the engine. The engine never reads a
    script to learn what a model is, never watches one, never infers a document from a path on
    disk, and never runs code on its own: a script edited and not run changes nothing the engine
    holds or says, until the next run tells it. What it reads at a run is what that run executes
    and declares -- the script and the modules its program imports, the files its bodies read,
    their digests for the build closure, and the files its decorators declare (law 10) -- and none
    of it again once the run is over. Two reads are not the engine reading code: a file document,
    which is the disk by definition and is read again when its bytes change; and the registry's
    record, which a run wrote. An existence check that only words a state reads no code (a model
    whose script is gone is `detached`, the engine's **Document lifetime**).
    The one startup exception is the JSON identity migration (the engine's README, **Identity
    migration**): it hashes existing scripts once for older records, without importing them or
    reading or writing an XBF.
    *Pressure-test*: build a model, then edit its script, its modules and the files its bodies
    read, without running it: every page, the home, every verb and tool and `cad status` answer
    as they did before the edit, and no process of the engine has opened a file of the model's code
    since its run.


24. **One table names every document type and integration.** *The package.* The registry (`cad.registry`) is the
    single source of every layer: each type's id, extensions, MIME type, how it is viewed (an engine
    document, a mesh, a drawing, a robot, a plot), the content it carries, its operations and the
    integration each needs, and whether it has a decorator or an edit; each integration's name, extra,
    process kind and, for an external program, its probe (the program, the oldest version our code supports, the
    install hint -- for a program that comes with an extra, as kicad-cli comes with `cad[kicad]`, that
    extra -- and the variable that names a program outright, as `CAD_KICAD_CLI` does). A document type
    either has files (its extensions) or has none (`model`, a document in memory, named by its id): a
    document is known by its id either way, and nothing in the engine assumes a file behind a
    document. It is kernel-free, the standard library alone, because the server imports it; the
    server's, the viewer's and the JavaScript's lists of formats are read from it, the JavaScript's
    generated (`python -m cad.registry --js`), never kept by hand. Where a released protocol spells a type
    otherwise -- the HTTP API's document kinds and the analytics schemas say `3mf` -- the entry names that
    spelling (`wire`); nothing else does.

25. **A document type is one object.** *The package.* `cad.<type>` is a `DocumentType`: the type's decorator where it
    has one (`@step("arm.step")`), its reader where it has one (`step.read`), its operations one to one
    with the CLI's, and the vocabulary the type's own standard defines where it takes no third-party
    objects (`sdf.GZ_CHECK_MODES`). Its attributes load on first use: `import cad` imports no kernel. A
    file of another type is refused by name before anything runs (`part.glb is a glb, not a stl`). A
    type's package (`cad/<type>/`) holds its reader, its operations' dispatch and its checks, and is
    neutral about producers: it imports no third-party library.

26. **An integration is named for its tool and holds only our code for it.** *The package.* `cad.<integration>` (code in
    `cad/<integration>/`) holds the helpers WE define that take that tool's objects and the producers it
    registers for the types they make; it re-exports nothing of the tool (`import build123d as bd` stays
    build123d's), and imports only its own extra's dependencies. Every extra, every `cad.<name>` namespace
    and every `cad/<name>/` package is a registered integration or document type. cad supports a tool only
    where cad's own code calls it: a tool only the agent runs, a remote service, or a desktop app the person
    uses is no integration.
    *The signature rule* decides where a helper goes: one taking only paths, plain values or our own types
    goes under the document type; one taking a third-party library's objects goes under that integration.

27. **A decorator works out its producer from what the function returns.** *The package.* A file decorator declares a
    persistent script's output; the registry's producers -- each a type, a matcher, the code that writes
    it and its integration -- decide which makes the file of the returned value. A matcher reads the
    value's type names and modules, never importing a library to ask. Exactly one producer per return
    type per document type; a return none takes fails loudly, naming the types the document is made of and
    the integration that would add more.

28. **The CLI is `cad <document_type> <operation> <file>`.** *Every document.* `export` and `snapshot` are shared by every
    type that has them (and `inspect` and `read` where a type has them); every other operation is named
    for what it does -- `dfm` a 3D type's manufacturing check, `drc` a board's design rule check, `erc` a
    schematic's electrical rules check, `validate` a robot description's conformance check -- never a
    shared word that means something different per type. Each type implements those that make sense; a
    `model`, which has no file, is named by its document id (`cad model export <id> arm.step`). A new
    shared operation must be code-free, frequently needed and meaningful across types. One result shape
    per operation: a check (`dfm`, `drc`, `erc`, `validate`) returns findings, each with a severity, a code
    and a location (`--json`: `cad.results.CheckResult`); `export` says the files it wrote. A type's own
    options live with the type (`cad srdf validate robot.srdf --urdf robot.urdf`).
    `cad <type> --help` lists the type's operations, `cad <type> <operation> --help` its options, and `cad
    --help` groups the commands by type. The commands that are no document's -- setup, update,
    uninstall, doctor, plugin, viewer, status, stop, server, telemetry, run, serve and delete -- stay
    top-level.

29. **An integration runs where its extra is installed.** *The package.* An integration's code runs
    in the command's own process when that environment holds the integration's extra, else in that
    integration's environment -- `cad[<integration>]` at the installation's release, made once per
    installation on first need, as `cad run` makes a program's -- run as a subprocess, the library's
    runner of one operation (`cad._internal.operation`; the server's `_internal/integration_env.py`).
    No module of the server imports an integration's code: the runner does, in whichever process
    runs it. A function of the library called where its integration is missing says which extra to
    add, or to run the script with `cad run`. A command line an integration's extra installs
    (`kicad-cli`, the registry's `commands`) runs the same way: `cad run kicad-cli …` adds the extra,
    and the integration's `_command` module runs the environment's own command there, headless in
    private homes, never one on PATH.

30. **A typed command wraps a tool only where it adds something.** *The package.* `cad <type>
    <operation>` runs a tool's command for a reason the tool's own line lacks: one result shape (law 28's
    findings, the files an export wrote), a safety guarantee (a board's folder left as found, a refused
    output path), or parity with the viewer (the same check, the same export). Everything else of the
    tool is its own command line, run through `cad run` (`cad run kicad-cli pcb render …`), which the
    skill documents with the tool's own flags at the pinned version; no typed command is added to
    rename one.

31. **A producer regenerates a file from code; an edit changes a native file in place.** *The package.*
    A producer is the engine's (law 27): a file decorator (`@model`, `@xbf`, `@step`, `@glb`, `@stl`,
    `@threemf`, `@dxf`) declares a persistent script's output, the function is a model the engine builds,
    and the file is written again from the model whenever it runs. An edit is a native file's own: the file
    is the source, and `with <type>.edit(path) as document:` opens it in its tool, in the caller's process,
    hands the block the tool's live document, and saves it where it is at the block's end only when the
    block changed it, and not at all when the block raises (a KiCad board's and schematic's,
    `kicad_pcb.edit` and `kicad_sch.edit`, through KiCad's IPC API, one KiCad per project for both). An
    edit declares nothing, writes no other file and is never a model: what is made from an edited file (a
    STEP, Gerbers, a check) is an explicit call after the block (`kicad_pcb.export`, `kicad_pcb.drc`). A
    type has a decorator or an edit, never both; the registry says which (`Producer`, `Edit`).


## Agent operations

Every MCP presentation exposes `cad_export`, `cad_snapshot` and `cad_inspect`,
independently of the viewer. They call the Python operations through the engine's
workers. No tool builds or imports a script: a model is built by its script, run by Python
(laws 11, 12). A source is an absolute CAD file path or a document id; a document id is read as
the engine holds it. Export names absolute server-host destinations; snapshot names a PNG or a
Quick Edit packet.

Start with a unique `requestId` (16–100 letters, digits, underscores or hyphens).
A start is checked whole before anything is queued: a refusal names every argument
missing and every one the tool does not take, and the shape it takes, in one line.
The result carries `id`, `epoch`, `state`, `sequence`, `stage` and `progress` -- the engine's
latest progress event for the operation, the one shape every job the engine runs says where it is
in (the engine's **Progress**: `{kind, stage, job, outputs, detail, done, total, elapsedMs}`), and
its stage's words -- and, when done, `result` or `error`. Use the same tool with `action: "status"`, `operationId` and
`epoch`; `waitMs` (up to 25000) waits for the result, on a start or a status, or with
`afterSequence` for the next change. A retry
with the same request ID joins the identical operation; changed arguments are
refused. `action: "cancel"` cancels queued work. Running operations can write
explicit destinations and are not cancellable. Disconnecting does not cancel. File outputs are not a multi-file transaction: a
failed operation may have written earlier outputs or a called model's declarations.
Failure results state this explicitly (`outputsMayHaveBeenWritten`, false when it failed before
anything was asked to write); reports over 2 MiB are explicitly marked
truncated and can be obtained through the Python API or CLI.
There is no separate job tool or generic HTTP jobs API.

Status is in session memory for up to 24 hours: the 64 most recent finished operations
(32 MiB of reports at most) and the 2048 most recent request identities, the oldest
dropped rather than new work refused; a restart loses it. A remembered identity whose
operation was dropped answers 410 and never replays writes.
The server's `jobs.py` owns admission, progress, waiting and cancellation for both agent
operations and viewer exports. Viewer exports additionally own temporary artifact
expiry, revision checks and download delivery; running cancellation discards that
temporary artifact. Browser downloads choose the viewer user's local destination
before starting. An agent's explicit host path is a different destination contract.

`cad <type> inspect`, `cad.<type>.inspect()` and `cad_inspect` read existing files or the
documents the engine holds by id (`cad model inspect <id>`, `cad.model.inspect(handle)`). They never execute source to obtain a missing model or write
its declared outputs. An unbuilt or unsaved model requires an explicit build: one
the engine built before names the command (`cad run` and the script that defines it). With no reference,
`cad <type> inspect` prints what the document holds -- its state, parts, bounds, volume (and a part
inside out, a solid's faces pointing inward), materials,
joints, couplings (name, kind, ratio, joints), states, sequences, animations and declared files -- then its build closure (`--json`:
both as data; `--query structure`, the same with nothing measured: no bounds, volume or masses;
`--query closure`, and `cad.<type>.inspect()` with no reference, the closure alone);
with a reference it returns geometry facts. No form meshes a part, and a part's volume and box
are measured once and kept by its geometry, in memory alone.
`query="build"` (`--query build`) returns saved-file metadata and closure or live
build metadata. File metadata does not imply a live worker.

## The shape of the package

```
src/cad/
  __init__.py            # the root, exactly: __version__, CadDeprecationWarning and the
                         #   document types (model among them), loaded on first use; the font guard, the lazy
                         #   kernel and the earlier spellings' aliases, first
  registry.py            # the document types and the integrations: the one table every layer
                         #   reads, kernel-free (`python -m cad.registry --js` writes the JS)
  model/                 # the model, the type with no file: @model and a model's operations, by
                         #   its handle or document id (a ModelType)
  xbf/, step/, stl/,     # the document types, each a DocumentType (`cad.<type>`): its decorator,
  glb/, threemf/, dxf/   #   its reader and its operations (a 3D type's dfm among them); a
                         #   STEP's AP242 PMI records read and checked in step/_ap242.py
  urdf/, sdf/, srdf/     # the robot descriptions' types: `validate` and the checks behind it
                         #   (_source.py, _validation.py, sdf's _external.py, gz sdf --check)
  kicad_pcb/             # a saved KiCad board: read, inside and inspect (the reader is
                         #   engine/formats/kicad, the standard library alone, and its flat
                         #   still engine/render/board.py); drc, export and edit (a with
                         #   block), the kicad integration's
  kicad_sch/             # a saved KiCad schematic: read (its hierarchy, its nets and
                         #   references; engine/formats/kicad/schematic, the standard library
                         #   alone) and inspect; its flat still engine/render/schematic.py;
                         #   erc, export and edit, the kicad integration's
  kicad/                 # the kicad integration, kicode: its kicad-cli found and run (_program,
                         #   on _internal/programs), `cad run kicad-cli` (_command), an edit of
                         #   a board or a schematic through its headless api-server and KiPy
                         #   (_session), DRC (_check), its exports (_export), a schematic's ERC
                         #   and exports (_schematic)
  trimesh/               # the trimesh integration: a mesh's manufacturing measurements -- molding
                         #   (draft, undercuts, projection along a pull), pulls (the pulls ranked),
                         #   printing (overhangs, walls, support), orientations (ranked) -- each
                         #   taking a trimesh.Trimesh and answering its report as data (_molding,
                         #   _printing), and the dfm every 3D type runs with them (_check)
  build123d/             # the build123d integration: memo, paint, the AP242 mechanism
                         #   (mechanism_state, configuration_sequence, gear_pair,
                         #   rack_and_pinion_pair, screw_pair, posed), the semantic PMI model
                         #   code writes on a part's faces (annotate, datum, ...: engine/pmi.py),
                         #   a GLB's animation, measurements of native geometry (_geometry),
                         #   flat patterns (_flatten), and the producers it registers (_producers)
  engine/                # the engine's library half: models and the worker every build runs
                         #   in, documents, exports, the mesh, references, the OCCT stills, the
                         #   client every command reaches the server by, and where things are
                         #   on this computer (places)
  results.py             # the operations' shared result types: what a check (dfm, drc, erc,
                         #   validate) and a KiCad export return, typed
  eng_drawing.py         # @eng_drawing: Sheets and Views over a part, one PDF (open: a future
                         #   pdf document type)
  _internal/             # DocumentType (document_type), a 3D type's manufacturing check: its
                         #   signature and options, the trimesh integration's measuring imported
                         #   when it runs (manufacturing), the runner of one operation the server's
                         #   command hands an environment that holds its integration (operation),
                         #   the earlier spellings (aliases), the
                         #   external programs our code runs, found and run headless (programs), the
                         #   runner `cad run` starts a program by (program: the program's
                         #   folder last on its path), the lazy kernel (lazy_kernel: `import
                         #   build123d` binds, the kernel loads on first use;
                         #   cad-lazy-kernel.pth, at the root of site-packages, installs it
                         #   at interpreter start), the font guard (font_scan; check_fonts, the
                         #   font that breaks `import build123d`), what the library counts
                         #   (counts), the checks' findings and XML helpers, atomic replace,
                         #   the checks' door, the version
src/cadgen/              # the earlier import name: every name and every module of it is cad's
                         #   own (law 15's earlier name)
```

The server, `cad-server`, and the shim, `cad-mcp`, say their own shapes and commands in
their own READMEs.

## Native KiCad files

A `.kicad_pcb` is source, edited in KiCad or as text and read directly for each plot or snapshot:
the library never builds, caches or writes back an XCAF model of a board. The parser and read-only
board index live under `src/cad/engine/formats/kicad/`, the standard library alone, so the server
and a script run with `cad run` import them without the CAD kernel; the flat renderer is
`src/cad/engine/render/board.py`, which imports Pillow only when it draws. `cad.kicad_pcb` is
the document type: `kicad_pcb.read` exposes the inspection index, `inside` the even-odd test a check measures
with, and `inspect` the board in one look. KiCad owns authoring, DRC (`cad.kicad_pcb.drc`, `cad
kicad_pcb drc`) and the fabrication, assembly and 3D exports (`cad.kicad_pcb.export(board, to, out)`,
`cad kicad_pcb export --to gerbers|drill|pos|bom|step|glb|odb|ipc2581|pdf|dxf -o DIR`), the `kicad`
integration's, run by kicode's `kicad-cli` (`cad[kicad]`; a person's own KiCad is never run). A script
run with `cad run` that calls them gets the extra; the command runs them in the extra's environment. An
exported STEP enters the ordinary foreign-file path.

A `.kicad_sch` is source too, read the same way. `cad.kicad_sch.read` reads the whole
hierarchy from its project's root sheet (whichever of its sheets it is given): its sheets, symbols and
pins, wires, buses, labels and junctions, and the nets they make, resolved as KiCad's connection graph
resolves them -- the names `kicad-cli sch export netlist` gives, which are the board's -- and answers
references in the board's grammar where they mean the same (`#U3`, `#U3.7`, `#net:VBUS`) and its own
(`#sheet:/Power/`, `#wire:<uuid>`). Its plot payload (`engine/formats/kicad/schematic_plot.py`) is the
board's shape, every sheet a page, drawn from the symbols' own drawings the file embeds, its text in
the same stroke font; `cad kicad_sch snapshot --sheet /Power/` draws one page. KiCad owns ERC (`cad.kicad_sch.erc`, `cad
kicad_sch erc`) and the exports (`cad.kicad_sch.export(schematic, to, out)`, `cad kicad_sch export --to
pdf|svg|netlist|bom -o DIR`), the `kicad` integration's, run where the board's are.

A board or a schematic is changed in place through KiCad's IPC API by an edit of it, a `with` block:
`with kicad_pcb.edit("board.kicad_pcb") as board:` or `with kicad_sch.edit("design.kicad_sch") as schematic:`
hands the block the open document (KiPy's, kicode's), through kicode's headless `kicad-cli api-server` on
the file, in private KiCad homes (a person's own KiCad settings and library tables are never read or
written; `cad.kicad._session`). A file not there yet is made by KiCad, with its project, and saved; an
existing one is saved at the block's end only when the block changed it (KiCad's own modified state), so a
block that changes nothing leaves it byte for byte, in its own format; nothing is saved when the block
raises, and the exception goes on; a save KiCad cannot finish puts back every file it wrote and says why.
One KiCad serves a project: the board's and the schematic's edits of one
project, one inside the other, share it, each saved at its own block's end. A schematic's symbol libraries
are its project's own `sym-lib-table`'s, loaded before the block runs; a placement from one the project
lacks is refused in one line naming it. The library writes no other file of KiCad's: a `.kicad_prl` an edit
made is removed. Exports and checks of the edited file are explicit calls after the block.

## Manufacturing checks

A 3D document's `dfm` measures it for a manufacturing process, with the `trimesh` integration
(`cad[trimesh]`): `cad.model.dfm`, `cad.xbf.dfm`, `cad.step.dfm`, `cad.stl.dfm`, `cad.threemf.dfm` and
`cad.glb.dfm`, one to one with `cad <type> dfm --process molding|printing`. The source is a file of
the type or, for `model`, a document the engine holds (its id, or the handle a model's call returns), so a
check script measures the model it builds:

```python
from cad import model, stl
from part import part                  # a model

result = model.dfm(part(), process="molding", pull="-z")    # draft, undercuts, projected area
stl.dfm("part.stl", process="printing", angle_limit=40)  # overhangs, walls, support
stl.dfm("part.stl", process="molding", candidates=True)  # the pulls ranked: x, y, z, principal axes
result.ok, result.findings, result.measurements["draft"]["min_wall_draft"]
```

The figures are facts, never verdicts: nothing compares them against a resin's, a printer's or a tool's
limit. The answer is a `cad.results.CheckResult`: `measurements` every family measured, its findings
what they show -- warnings (`zero_draft_walls`, `undercut_candidates`, `overhangs`, `units_suspect`,
`not_watertight`, `several_bodies`, `coarse_curved_face`), each at the place it was measured (`x, y, z`
in millimetres), and errors for what could not be measured (`measurement_failed`, `mesh_unreadable`,
`not_finite`, `invalid_target`), which alone fail it. Each option belongs to a process: molding's
`pull` (`z`, `-y`, `x,y,z`; default `z`), `wall_limit` (45 degrees) and `zero_tol` (0.05); printing's
`angle_limit` (45) and `samples` (2000); `units` (`mm`, `cm`, `m`, `in`, `ft`) an STL's alone, the
other types declaring their own; `candidates` either's. An option of the other process is refused by
name. A mesh is measured as the viewer reads it: an STL as it is, a 3MF's or a GLB's objects placed in
millimetres, Z up, and a model, a STEP or an xbf as the engine tessellates it.

Measured as a mesh, a curved face's draft is read from its facets, which are chords: the report says how
far its facets disagree (`spread_deg`) and when to export finer. The trimesh integration's functions
measure a mesh a program already holds, answering the same report as data:
`cad.trimesh.molding(mesh, pull="z")`, `cad.trimesh.pulls(mesh)`, `cad.trimesh.printing(mesh)` and
`cad.trimesh.orientations(mesh)`, each taking a `trimesh.Trimesh` (any file trimesh reads, an `.obj`
or a `.ply` among them) and never changing it. A script run with `cad run` that imports `trimesh` or
`cad.trimesh` gets the integration; one that only calls `cad.<type>.dfm` names it in its header
(`cad[trimesh]`), and a check without it says so in one line.
