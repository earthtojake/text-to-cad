# cad

The library: CAD models written as Python, imported as `cad`, built by the engine (`cad.engine`) into live XCAF documents and the files those models
declare (XBF, STEP, GLB, STL, 3MF, DXF). The same distribution, `cad`, holds the server (imported as
`cad_server`), the computer's one daemon that builds, keeps and serves the documents, with the CAD
Viewer, the CAD app's MCP endpoint and the `cad` command that runs them all; and the stdio transport
an agent app starts (`cad_mcp`, run as `cad mcp`). The server ships what is not Python: the CAD
Viewer's client and the CAD app page, which it serves, built from their JavaScript packages and
bundled in at build time (the JS *source* never ships). Snapshots are drawn by OCCT (a KiCad board's
flat, with Pillow), never in a browser. This file holds the laws of all three parts.

Install it as a uv tool, which gives the computer its one `cad`:

```bash
uv tool install cad
```

It runs on Python 3.11 and newer. `cad server start` starts the server; cad then updates itself to each
new release of its major version (`cad update auto off` stops that); `cad update` updates it now; a new
major version installs only with `cad update --major`; `cad doctor` reports what is installed. `cad-server`, `cad-mcp` and `cadgen` are empty aliases of this
distribution, kept so older installs keep working.

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
cad viewer XBF/arm.xbf                         # the document on the running server's page
cad xbf inspect XBF/arm.xbf                    # what it holds, then its build closure
```

The same operations are functions of each type: `xbf.export("XBF/arm.xbf", "arm.glb")`,
`xbf.snapshot(...)`, `xbf.inspect(...)`; `model.export(arm(), "arm.glb")` exports the model a call returns,
and `step.read("vendor.step")` reads a file into a model.

## Definitions

These words mean one thing each, in the code, the commands and every document.

- **Document type**: what is in a file. Always called "document type". Each has one lowercase underscore
  id, the same in Python, the CLI, the registry, the server, the viewer and the JavaScript: `model`, `step`,
  `glb`, `stl`, `threemf`, `dxf`, `xbf`, `urdf`, `srdf`, `kicad_pcb`, `kicad_sch`. 3MF's id is `threemf`
  because an id must be a valid Python name. The registry (`cad.registry`) maps file extensions to ids (`.step`
  and `.stp` are `step`). `model` is the one type with no file: a model built from code and held in the
  engine's memory, addressed by its document id or the handle its call returns (`@model` declares one);
  `xbf` is the `.xbf` file the engine writes of one, and takes files alone. A document type is a file cad
  shows: each has a view. A file cad writes or checks and never shows is none, whatever cad does with it: an
  MJCF, MuJoCo's own model file, is an export's destination and the mujoco integration's to check, and
  MuJoCo Studio shows it.
- **Document**: one instance of a document type, either a file read on its own or one built from code.
- **Integration**: our support for one third-party tool, named for the tool's own project (`build123d`,
  `kicad`, `trimesh`, `mujoco`, `coacd`, `netgen`, `calculix`, `blender`), never for a capability. It is
  three things: one extra, `cad[<name>]`, grouping the dependencies our code for it needs; our code for it --
  helpers that take its objects, producers and operations; and a process kind: in-process, separate process,
  or both. An integration has an operation of its own only on a file of its tool's that is no document type:
  `check`, answering findings as a type's check does (`cad mujoco check robot.xml`, `cad.mujoco.check`).
  The `orcaslicer` integration (`cad orcaslicer presets|complete`, `cad.orcaslicer`) is deprecated: it
  completed the presets OrcaSlicer stores, from its own folders, for its command line, and cannot from
  OrcaSlicer 2.5 on, which keeps the built-in ones in binary caches; a project saved from the app slices as
  it is (law 28). It is kept, unlisted, for the 30 days law 14's first tier gives a command the skills used.
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
  (a 3D type's manufacturing check), `interference` (a B-rep type's check that no two parts share volume),
  `solve` (a B-rep type's stress study), `ranges` (a mechanism's joint stops,
  found from its geometry), `drc` (a board's design rule check), `erc` (a schematic's electrical
  rules check), `validate` (a robot description's conformance check). Each type implements those that make
  sense for it.

`python -m cad.registry <type>` prints a type's help, worked out from the registry: the content it carries,
its operations and what writes it.

**PURPOSE** — the engine and its command surface: models built in a warm worker whose memo
makes an edit cost what it changed, documents and their exports, kinematics and configuration sequences,
materials, references to geometry, snapshots drawn by OCCT; the viewer (`cad viewer [FILE]`: a
launcher for the engine’s one page, every document at `/<id>`, every file read by its absolute path); CAD beside an agent's chat (`cad mcp`: a stateless stdio peer of the engine’s
HTTP MCP endpoint, with tools and the app page owned by the engine); the URDF and SRDF checks; a MuJoCo model's
check (`cad.mujoco.check`: an MJCF compiled by MuJoCo's own compiler, what collides as what, its contact excludes); a 3D
document's manufacturing check (`cad.<type>.dfm(source, process="cnc"|"sheet"|"molding"|"printing")`:
exact geometry measured by the build123d integration, a mesh by trimesh, judged against general, cited rules); a
B-rep document's interference check (`cad.<type>.interference(source, poses=..., fits=...)`: every
pair of parts whose boxes meet answered, as built and posed, by the engine: exactly, by the kernel, wherever the
two parts' meshes do not show air between them); a
B-rep document's stress study (`cad.<type>.solve(source, study=..., out=...)`, meshed by netgen and solved by
CalculiX's ccx, its results a folder of standard files); a mechanism's joint stops found from its geometry
(`cad.<type>.ranges(source)`, each joint swept against its parts); and engineering drawings (`@eng_drawing`).

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

**DEPENDED ON BY** — the server and the `cad` command (`cad_server`), in the same distribution, and
through them every skill that runs `cad`; the empty aliases `cad-server`, `cad-mcp` and `cadgen`,
which install it at the same release.
The viewer is the server's: it serves `cad_server.viewer`’s client, HTTP application and
every STEP and `.xbf` a page opens on one authenticated listener, without a relay.

## The rest of the package's documentation

This file holds the laws. The engine's pages hold the mechanisms they constrain; where the two
disagree, the engine's pages are right about what the code does.

| Document | What it is for | Go there when |
|---|---|---|
| The server's README, `src/cad_server/README.md` | The server's shape, its commands, cad's own update and where it keeps things | changing a command, the server's folders or the update |
| The transport's README, `src/cad_mcp/README.md` | What `cad mcp` does between an agent app and the server | changing how an agent app reaches the server |
| The engine's README, `src/cad_server/engine/README.md`, and the pages it indexes in `docs/` beside it | The engine, a page per mechanism: models, the server and its workers, the door, document lifetime, progress, the viewer and the snapshot, exports, kinematics, materials, imports, the mesh, the wire format, element names, references, the memo, the build closure and a model's parameters. Read the index, then the one page | changing anything a build, an export, a snapshot or a served document does |

## The design laws

A law is a rule the package keeps and the reason for it, in a few sentences. How each is carried out is
a mechanism's business, and the mechanisms are in the engine's README and the server's; each law names
where. Where a law and the code disagree, one of them is wrong: fix it in the change that found it.

The laws describe what was built, not a template for what comes next. When adding a feature, a document
type, an integration or a command, think from first principles about what is best for that tool: what
it already does, who looks at its files, and what is missing without us. Where that leads away from a
law, say which and why in the change, and amend the law in the same change. Departing from one without
saying so is the only wrong move.

Each law says what it binds: *every document*; *models* (built from code, held in memory); *file
documents* (a file read as it is: a board, a robot description, a mesh, an opened STEP or xbf); or *the
package*. Code, tests and documents cite a law by its number: a change that adds, merges or removes one
renumbers the list and every citation in the same change.

1. **An xbf carries its build closure as pointers and digests.** *Models.* Script and function,
   modules, data inputs, the toolchain and the key; never source, never lines on elements, never input
   contents, nothing of git's. Names remain the per-element tie to code (the engine's **Build
   closure**).
2. **Only requested files reach the disk.** *Every document.* The engine writes the files a model
   declares, the exports a command or a person asks for, and a model's own script only where a person or an
   agent asks to set a parameter it declares (law 30), and nothing beside a model or an input: no
   sidecar, index, memo, mesh or record of a build. What it keeps for itself lives in three folders of
   the user's own, the same whatever release runs: state (settings and the records of documents, never
   geometry or source), cache (each document's bytes as last built, a file document's views keyed by
   its bytes, bytecode and the environments it installs, every one regenerable) and the engine's folder
   (its door and lock). The code stays the only source of truth: a document is what its last run made,
   and nothing reruns (the server's **Folders**; `cad.engine.places`).
3. **Three sides, by where the code runs.** *The package.* The library (`cad`: what a model imports
   and what runs in a worker) imports nothing of the server's or the transport's, so a model runs where
   only it is installed. The server (`cad_server`: the daemon, the commands, the viewer, telemetry)
   imports the library's kernel-free modules and never the kernel or an integration's code (law 27).
   The transport (`cad_mcp`) is the standard library, the engine's client and the server's MCP
   protocol, and loads no kernel. The server reaches into the library, never the other way: its
   telemetry is an observer the engine calls with plain facts. Inside the server two things are known
   in one place each: the app that hosts cad, in its MCP adapter (`cad_server/mcp/`); and the agent
   apps, the plugin and its skills, in `cad_server/plugin/` (the table of apps, how the plugin is
   installed and updated in each, which older copies are ours to remove), which only the `cad plugin`
   command reaches. Nothing else in cad names an app, a plugin or a skill, or imports either place.
4. **A model's document is XCAF; files are explicit.** *Every document.* A live model holds an XCAF
   document: millimetres, prototypes and instances with placements, a name on every part and instance,
   colours and materials per part and per painted face, element names, an assembly's mechanism, and the
   parameters its script declares (name, value, kind, range, step and unit; never where the code spells
   them: law 30).
   STEP, GLB, STL, 3MF and, of a planar document, DXF are translations of it, which `cad <type> export`
   writes from the xbf alone. A file document is its file, read by its type (law 23).
5. **The memo is the only build cache, and it lives in the worker.** *Models.* Every kernel operation
   a model runs is keyed by its inputs, as is every question it asks of what they made. A hit hands
   back what the first run made, and a miss makes everything downstream of it miss, so an edit costs
   what it changed and an element keeps its name across edits. Across a restart a build is cold but for
   its document in the cache, taken whole by its key or not at all; a declared file is never a source.
6. **One document per model, with one id.** *Every document.* A called model makes one document and
   returns its handle, never a bare shape. Every id is one formula over a scope and a name
   (`ids.derived_id`): a model's script and function, an opened file's path, a handed-over shape's
   calling script and name; the same in every process, worked out without asking the engine. A function
   is declared by `@model` or by its file decorators, never both. A document lives until a person
   deletes it: neither its worker retiring nor memory ends it, and one that is not held names the
   command that builds it again (the engine's **Document lifetime**).
7. **Provenance is served live, never written.** *Models.* What made an element (the feature, its
   operation, the function, file and line of its call) lives in the trace of the worker that built the
   document and is asked of it while it lives (`made_by`). A document opened with no such worker says
   so (`made_by: null`); a file names no model and answers none.
8. **Poses and motion definitions, never frames.** *Models.* The document carries kinematics as poses
   and definitions: the mechanism, its states and its configuration sequences. A GLB export is the one
   place a sequence is baked into a clip; the engine plays nothing.
9. **Names are the durable tie to code.** *Models.* An element's name is spelled from the function
   that made its feature and the author's name for that feature, never from a line or a file: moving
   code renames nothing, and the file holds no line to go stale.
10. **A file decorator requires an explicit output path.** *Models.* `out` is required; an omitted
    path or `None` is refused. Whenever its model runs in a build, or is taken from its key, the file
    is written once, from the model's own document, exactly as an export writes it, and only where it
    differs or is missing. A model with no file decorator writes nothing.
11. **A model script is Python, and decoration only declares.** *Models.* Decorated functions declare
    models, explicit calls build them, and `python script.py` or `cad run script.py` runs the program.
    Importing the library or defining a decorated function builds nothing, writes nothing and starts
    nothing. Python decides which calls run and in what order; no command imports, builds or watches a
    script, and the library consumes no script arguments.
12. **The document's kinematics are AP242's.** *Models.* Every entity and attribute of the mechanism
    subtree is ISO 10303-105's as Part 21 writes it, and the library stores no kinematic fact the
    standard cannot name: what it cannot say is dropped or refused by name, never patched with an
    attribute of our own. The authoring functions are named after the entities they write
    (`mechanism_state`, `configuration_sequence`, `gear_pair`, `rack_and_pinion_pair`, `screw_pair`);
    a conformance test holds the subtree (the engine's **Kinematics**).
13. **The distribution ships alone.** *The package.* An installed distribution is the whole world: its
    Python, what it bundles and its documents. It works with the repository it was built from gone, and
    its markdown reads that way, referring to nothing outside the distribution.
    *Pressure-test*: every sentence of the distribution's markdown is true and actionable for someone
    who only ran `uv tool install cad`. Naming a bundled thing passes; a repository path, script or
    workflow does not.
14. **Compatibility, by who pays for a break.** *The package.* A change is judged by who absorbs it
    and whether they can. cad installs by itself every newer release of the major it is on, and never
    a higher major (`cad update --major`); below 1.0 a break bumps the minor, so a breaking release
    arrives by itself with its migration guide. Four tiers, which hold within a major as across one:

    - **Tier 1, what an agent reads each session**: the skills, the commands' verbs and flags, the CAD
      tools' arguments. Whatever the skills of the last 30 days used keeps working, hidden if need be.
      Past the window it is a hard cutover in any
      release: no alias, no shim, and no error that recognizes the old spelling.
      *Pressure-test*: a removed spelling fails exactly as a name that never existed.
    - **Tier 2, the library's public imports**: what a model script imports. Changed only when a
      release must. The earlier spelling stays an alias of the same object for a release at least and
      warns once per name per process (`CadDeprecationWarning`), naming the new path at the line that
      spelled the old. An alias is kept out of every `__all__` and every document but the migration
      guide; a test pins the table (`cad._internal.aliases`). Its removal is the breaking change.
    - **Tier 3, a person's data**: documents, the state folder and its records, settings. A release
      reads what the previous shipped release wrote, writes the current form and migrates on first
      touch, once. Opening, viewing or exporting a saved document never needs its source or a rebuild
      because cad was upgraded (the engine's **Build closure**).
    - **Tier 4, protocols where two releases meet while both run**: the door, the HTTP API, the CAD
      app's server and page, the version feed, the installation records, the analytics schemas, the
      worker contract. Each is numbered or frozen in a golden, so a break is never silent: a change
      within a number is additive, a breaking change bumps the number, and the side that meets a number
      it does not speak says so in one line, naming which package to update.

    `cadgen` is the library's deprecated alias, published at every release and warning as tier 2's do.
15. **Closed vocabularies.** *The package.* Every declaration surface has a closed set of keys and
    kinds. An unknown key is an error naming the supported set, never silently ignored.
16. **Loud failure or correct output, nothing between.** *The package.* The cardinal sin is
    plausible-wrong output at exit 0. No silent fallbacks, no globs, no guessing; a failed write or
    render leaves no file this run wrote, and an earlier file stays byte for byte.
17. **Nothing waits on the network.** *The package.* Once installed, cad works offline: every command,
    build, snapshot, server and page. Its own requests are telemetry and the hourly version check;
    both run in the background and fail silently, and no start, command, build or tool call waits on
    them. The waits are the ones a person asks for by name (`cad update`; `cad plugin install`, which
    runs each agent app's own command and fetches the plugin from GitHub; `cad telemetry off`) and the
    first fetch of an integration's environment, which says so in a line. The
    pages load nothing from the internet (the server's **cad's own update** and **Telemetry**).
    *Pressure-test*: with every integration's environment made, and every request refused, then
    hanging, start a server, open a view, call each tool, and run a build, a snapshot and each
    integration's operation: each works, and nothing waits on a request.
18. **Connected means warm.** *Models.* A document a page watches keeps its worker. No timer retires
    a worker: memory does, and it retires a watched one only when no other is left; the worker-count
    cap is exceeded rather than retire one. The engine outlives its clients, and a page closing never
    stops a worker (the engine's **The engine server and its workers**).
19. **One engine per computer; a tab selects a document at `/<id>`.** *Every document.* Every process
    reaches the one engine through the one door in the engine folder, whatever release it is. Only
    `cad server start` and `cad mcp` start it: any other client that finds none says so in a line and
    starts none, and no Python function starts, stops or serves it. A newer release's start replaces
    an older engine, and an older one joins a newer engine that runs: forward only. Launchers exit and
    clients closing never stop it; kernel work runs in child processes, never in its request threads;
    there are no page sessions (the engine's **Architecture** and **Starting and updating**).
20. **Operations on documents are Python functions the CLI exposes; process control is the CLI's
    alone.** *Every document.* A type's operations are functions of that type (`cad.model.export`,
    `cad.kicad_pcb.drc`, `cad.urdf.validate`), one to one with the commands that call them (`cad model
    export`, `cad kicad_pcb drc`, `cad urdf validate`). Serving, the engine's status, stopping it and
    deleting a document are commands only, with no function of the library. Every successful
    server-backed build reports its id and its page.
21. **Push, not pull: a model is what its last run told the engine.** *Models.* The engine's knowledge
    of a model comes from a run an agent or a person starts, which pushes the model's code, key and
    document to it. The engine never reads a script to learn what a model is, never watches one, never
    infers a document from a path and never runs code on its own: a script edited and not run changes
    nothing it holds or says. One case reads a script outside a run and starts a build, and only when a
    page asks: its Save of a model's parameters (law 30), and its preview of values before it saves them.
    A file document is the disk by definition and is read again when its bytes change.
    *Pressure-test*: build a model, then edit its script, its modules and the files its bodies read
    without running it: every page, command and tool answers as before the edit, and no process of the
    engine has opened a file of the model's code since its run, but a page's Save and preview, which
    read the script and refuse since it changed (`script_changed`).
22. **One table names every document type and integration.** *The package.* The registry
    (`cad.registry`) is the single source for every layer: each type's id, extensions, MIME type, view,
    content and operations, with the integration each needs; each integration's name, extra, process
    kind and any operation of its own. It is the standard library alone, because the server imports
    it, and the server's, the viewer's and the JavaScript's lists of formats are read or generated from
    it (`python -m cad.registry --js`), never kept by hand.
23. **A document type is one object.** *The package.* `cad.<type>` holds the type's decorator where it
    has one, its reader where it has one, and its operations one to one with the CLI's. Its attributes
    load on first use, so `import cad` imports no kernel. A file of another type is refused by name
    before anything runs. A type's package is neutral about producers: it imports no third-party
    library.
24. **An integration is named for its tool and holds only our code for it.** *The package.*
    `cad.<integration>` holds the helpers we define that take that tool's objects and the producers it
    registers; it re-exports nothing of the tool and imports only its own extra's dependencies. cad
    supports a tool only where cad's own code calls it: a tool only the agent runs, a remote service or
    a desktop app the person uses is no integration, and a skill teaches it directly.
    *The signature rule*: a helper taking only paths, plain values or our own types goes under the
    document type; one taking a third-party library's objects goes under that integration.
25. **A decorator works out its producer from what the function returns.** *The package.* The
    registry's producers (a type, a matcher, the code that writes it, its integration) decide which
    makes the file of the returned value. A matcher reads the value's type names and modules, never
    importing a library to ask. Exactly one producer per return type per document type; a return none
    takes fails loudly, naming what the document is made of.
26. **The CLI is `cad <document_type> <operation> <file>`.** *Every document.* `export` and `snapshot`
    are shared by every type that has them (`inspect` and `read` where a type has them); every other
    operation is named for what it does and means one thing: `dfm`, `interference`, `solve`, `ranges`,
    `drc`, `erc`, `validate`. One result shape per operation: a check returns findings, each with
    a severity, a code and a location (`cad.results.CheckResult`), and `export` says the files it wrote.
    A new shared operation must be code-free, frequently needed and meaningful across types. A file cad
    checks and never shows has no document type, and its check is its tool's integration's (`cad mujoco
    check robot.xml`, the one such operation). A name is a type's or an integration's, never both, and
    an operation lives in one place.
27. **An integration runs where its extra is installed.** *The package.* In the command's own process
    when that environment holds the extra, else in the integration's own environment
    (`cad[<integration>]` at the installation's release, made once on first need), as a subprocess. No
    module of the server imports an integration's code. A command line an extra installs runs the same
    way (`cad run kicad-cli …`), headless in private homes, never one on PATH. cad runs the program its
    extra pins, unless `CAD_CCX` or `CAD_KICAD_CLI` names another copy of it. An integration with no
    extra (`orcaslicer`, the standard library alone) runs in the command's own process.
28. **cad wraps a tool only where it adds something.** *The package.* A helper or a typed command for
    a third-party tool exists only where cad adds what the tool lacks, and says what: one result shape
    for a check (`cad kicad_pcb drc`), a safety guarantee (an edit that saves only when its block
    changed the file), parity with the viewer, or a fact the tool does not report (`cad mujoco
    check`). Everything else is the tool's own, used directly: its Python API in the script that
    imports it, its command line (through `cad run` where an extra installs it), its app in the
    person's hands. So cad has no command that only passes arguments on, no helper that renames a
    tool's function, and no code that rebuilds from a tool's own folders and caches what the tool
    exports: a skill teaches the tool's way instead.
    *Pressure-test*: delete the helper and write what a skill would say in its place. If that is the
    tool's own command or call and nothing is lost, the helper was a wrapper. `flat_pattern` and the
    five helpers beside it were: each gave what build123d's own `Plane.to_local_coords`, `offset` and
    `fuse` give, to the last digit.
29. **A producer regenerates a file from code; an edit changes a native file in place.** *The
    package.* A producer is the engine's (law 25): a file decorator declares a persistent script's
    output, and the file is written again from the model whenever it runs. An edit is a native file's
    own: `with <type>.edit(path) as document:` opens the file in its tool, hands the block the tool's
    live document, and saves at the block's end only when the block changed it, never when it raises.
    A type has a decorator or an edit, never both. A page's Save of parameters (law 30) is neither: it
    opens no tool and makes no declared file; it rewrites numbers in a model's own script, and the engine
    builds the model again from it, as a run does.
30. **A model's parameters are its code's, and the viewer's Save is the one way the engine changes a
    script.** *Models.* A script declares a parameter at a module's top level (`cad.model.param`: a
    lower-case name, a plain number default it returns unchanged, and the closed set `min`, `max`,
    `step`, `unit`); one declared inside a function is refused, since a body can be replayed without
    running. A build records the declarations in the document (law 4); the worker that loaded the
    script keeps where each default is spelled in memory alone, as provenance is (law 7). A value
    changes only in the code: an agent or a person edits it and runs the script, or a person saves new
    values in the viewer's Parameters tab. The Save is a page's request, as its preview is, and no
    operation (law 20): no command or library function writes parameters, and an agent changes one by
    editing the code. The Save writes only a literal of the model's own script, only while the file
    holds the bytes its last run read, and runs that run again in the warm worker; a build the new
    values break puts the bytes back, never over another writer's change. A page's preview of other
    values is built in the same worker for that page alone and becomes nothing else: never a file, the
    document, its record or the cache, never what another page, an export or an agent reads (the
    engine's **Parameters**).
    *Pressure-test*: declare a parameter in a shared module, in a loop and as an expression: each is
    listed read-only and a Save refuses it; edit the script by hand and a Save refuses
    (`script_changed`) until the script runs again.


## Inspection

`cad <type> inspect` and `cad.<type>.inspect()` read existing files or the
documents the engine holds by id (`cad model inspect <id>`, `cad.model.inspect(handle)`). They never execute source to obtain a missing model or write
its declared outputs. An unbuilt or unsaved model requires an explicit build: one
the engine built before names the command (`cad run` and the script that defines it). With no reference,
`cad <type> inspect` prints what the document holds -- its state, parts, bounds, volume (and a part
inside out, a solid's faces pointing inward), materials,
joints, couplings (name, kind, ratio, joints), states, sequences, animations, parameters (each its value, range and
unit, where it is declared, and whether the viewer's Save can write it) and declared files -- then its build closure (`--json`:
both as data; `--query structure`, the same with nothing measured: no bounds, volume or masses;
`--query closure`, and `cad.<type>.inspect()` with no reference, the closure alone).
For an XBF file, the summary and structure include that same saved closure.
With a reference it returns geometry facts. No form meshes a part, and a part's volume and box
are measured once and kept by its geometry, in memory alone.
An inspection of a changed STEP waits for the new file to be read. If it changes between
reading the structure and measuring it, inspect it again.
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
  model/                 # the model, the type with no file: @model, its parameters (param, declared
                         #   in the script), and a model's operations, by its handle or document
                         #   id (a ModelType)
  xbf/, step/, stl/,     # the document types, each a DocumentType (`cad.<type>`): its decorator,
  glb/, threemf/, dxf/   #   its reader and its operations (a 3D type's dfm among them, and a
                         #   B-rep type's solve and ranges: model's, xbf's and step's)
  urdf/, srdf/           # the robot descriptions' types: `validate` and the checks behind it
                         #   (_source.py, _validation.py)
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
                         #   and exports (_schematic), and route, copper for the connections a
                         #   plan names, inside an edit (_route; its search, _routing: numpy)
  trimesh/               # the trimesh integration: a mesh's 3D printing measurements -- printing
                         #   (overhangs, walls, trapped volumes, support), orientations (ranked) -- each
                         #   taking a trimesh.Trimesh and answering its report as data (_printing), the
                         #   mesh read and cleaned (_mesh), and the check every mesh type runs (_check)
  mujoco/                # the mujoco integration, MuJoCo's headless core and Studio (mujoco-core, mujoco-studio): a
                         #   document as a mujoco.MjSpec (_spec), a part's collision chosen on it
                         #   (_parts), the spec saved as a folder that travels (_save), and check, its
                         #   one operation on a MuJoCo model's file, which is no document type: the
                         #   model compiled by MuJoCo's own compiler, what it refuses and warns as
                         #   findings (_compile), the model-health checks (_health), what collides as
                         #   what and the contact excludes as data (_report, _check)
  build123d/             # the build123d integration: memo, paint, the AP242 mechanism
                         #   (mechanism_state, configuration_sequence, gear_pair,
                         #   rack_and_pinion_pair, screw_pair, posed), a GLB's animation,
                         #   measurements of native geometry (_geometry),
                         #   the manufacturing checks of exact geometry (_dfm_brep, the core; _dfm_cnc,
                         #   _dfm_sheet with unfold, _dfm_molding, _dfm_printing; _dfm_dxf, a cut file;
                         #   _dfm_check, the entry), the interference check's measuring
                         #   (_interference), named material looks (materials: solder mask, ENIG,
                         #   anodized, ..., each a native bd_materials FinishedMaterial), and the
                         #   producers it registers (_producers)
  engine/                # the engine's library half: models and the worker every build runs
                         #   in, documents, exports, the mesh, references, the OCCT stills, the
                         #   client every command reaches the server by, and where things are
                         #   on this computer (places)
  coacd/                 # the coacd integration, CoACD's convex decomposition: the process of its own
                         #   that cuts a part's mesh into convex hulls for cad.mujoco.decompose
                         #   (_decomposer), which the engine starts and keeps the hulls of (engine/hulls.py)
  netgen/                # the netgen integration: the mesher, always in a process of its own
                         #   (_mesher: a BREP in, a mesh out, every face kept under its ref)
  blender/               # the blender integration, bpy: a GLB loaded into Blender's scene for a
                         #   render, every node's object found by its place in the file, each node
                         #   a clip moves put back where the file places it, and one clip played at
                         #   a time (load, Model, Clip: _scene)
  calculix/              # the calculix integration, the cad-ccx package's ccx: found, checked and run
                         #   headless (_program, on _internal/programs; `cad run ccx`, _command),
                         #   its input and printed output (_files)
  results.py             # the operations' shared result types: what a check (dfm, interference, solve,
                         #   drc, erc, validate) and a KiCad export return, typed
  eng_drawing.py         # @eng_drawing: Sheets and Views over a part, one PDF (open: a future
                         #   pdf document type)
  _internal/             # DocumentType (document_type), a B-rep type's interference check: its
                         #   options and its result (interference), a 3D type's manufacturing check: its
                         #   signature and options, its integration's measuring imported when it
                         #   runs (manufacturing), each process's options, rules and findings
                         #   (dfm/, its README the mechanism), the numpy geometry the checks measure
                         #   with (meshops_printing, a mesh's, shared by both integrations;
                         #   molding_geometry; sheet_plane), the runner of one operation the server's
                         #   command hands an environment that holds its integration (operation),
                         #   the joint stops a type with a mechanism runs (ranges: its signature
                         #   and options, stdlib only; the sweep is engine/ranges.py),
                         #   the earlier spellings (aliases), the
                         #   external programs our code runs, found and run headless (programs), the
                         #   runner `cad run` starts a program by (program: the program's
                         #   folder last on its path), the lazy kernel (lazy_kernel: `import
                         #   build123d` binds, the kernel loads on first use;
                         #   cad-lazy-kernel.pth, at the root of site-packages, installs it
                         #   at interpreter start), the font guard (font_scan; check_fonts, the
                         #   font that breaks `import build123d`), what the library counts
                         #   (counts), the checks' findings and XML helpers, atomic replace,
                         #   the checks' door, the version, and the stress study a B-rep type
                         #   runs (fea: its signature and options in operation, stdlib only; the
                         #   study file, the mesh, the solve, the checks and the files it writes)
src/cadgen/              # the deprecated import alias: every name and every module of it is cad's
                         #   own (law 14's earlier name)
```

The server and the transport say their own shapes and commands in their own READMEs,
`src/cad_server/README.md` and `src/cad_mcp/README.md`.

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
exported STEP enters the ordinary foreign-file path. A board's GLB holds its copper, mask and silkscreen
as well as the board and its parts, each KiCad's own mesh; its STEP the board and its parts alone.

A `.kicad_sch` is source too, read the same way. `cad.kicad_sch.read` reads the whole
hierarchy from its project's root sheet (whichever of its sheets it is given): its sheets, symbols and
pins, wires, buses, labels and junctions, and the nets they make, resolved as KiCad's connection graph
resolves them -- the names `kicad-cli sch export netlist` gives, which are the board's -- and answers
references in the board's grammar where they mean the same (`#U3`, `#U3.7`, `#net:VBUS`) and its own
(`#sheet:/Power/`, `#wire:<uuid>`). Its plot payload (`engine/formats/kicad/schematic_plot.py`) is the
board's shape, every sheet a page, drawn from the symbols' own drawings the file embeds, its text in
the same stroke font with KiCad's text markup, each page on KiCad's default drawing sheet as the viewer
shows it; `cad kicad_sch snapshot --sheet /Power/` draws one page with its title block. KiCad owns ERC (`cad.kicad_sch.erc`, `cad
kicad_sch erc`; beside KiCad's findings the check lists, from the reader, each pin joined some other way besides
and each wire end that lies on a wire's span with no junction, which KiCad joins and its ERC passes:
`pin_on_wire_span`, `wire_end_on_wire_span`, warnings whose `items` name the pin or wire and the wire; a pin
whose one connection is a wire's span is KiCad's own straight run through a pin, not one) and the exports (`cad.kicad_sch.export(schematic, to, out)`, `cad kicad_sch export --to
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
made is removed. Exports and checks of the edited file are explicit calls after the block. A board's save is
checked for the nets KiCad moved: KiCad gives copper the net of a pad it overlaps on any layer, as it loads
and commits, so each track, via, copper shape and zone saved on another net than the block gave it (else the
file had) is a warning on stderr naming it (`#via:<uuid>`), both nets and the pad it overlaps, and is on the
board after the block, `board.net_changes` (`cad.kicad._drift`).

Inside a board's edit, `cad.kicad.route(board, plan)` writes copper for the connections a plan names, in its
order: each a net or a pair of pads, with the copper layers it may use (required; there is no default plan),
its width and clearance (the net's netclass's by default, never under the board's rules), its via limit (for
the whole entry) and via cost (in mm of track; the search settles for a path within 1.2 times the cheapest, so
the trade is about that, not exact). A plan is a list, in order. The plan is checked whole before anything is
routed; a mistake in it is a `ValueError` naming what to give, and so is a board it cannot route by: an outline
that does not close, a pad drawn with a primitive it cannot read or whose padstack layers share no point, a
TrueType copper text with no outline saved, a net KiCad pairs by name with another (a differential pair, which
it does not route), a region past its memory even at the least margin (route the plan in parts). A region whose
margin round the plan's pads would not fit the router's memory (600 MB for its fields and its largest search)
is narrowed to fit first, and said.

It reads the open board (`get_as_string`) and KiCad's rules for it: each net's netclass, the board's minimums,
the solder-mask clearances, and the custom rules. Each clearance a custom rule names is kept everywhere (the
largest of each); a track width, via diameter, hole size, annular width or via count of a rule with no condition
and no layer is kept as DRC holds it (an entry's width outside it is refused naming the rule, the via the router
places is taken up to its least and refused past its most, and a net's via count, its vias on the board counted,
lowers each entry's via limit); a `disallow` or an `assertion` is refused by name; every other constraint that can
bear on new copper, and every size of a rule with a condition or a layer, is a warning naming the rule and the
fix, for DRC to judge after; a `.kicad_dru` its KiCad cannot read, or cannot give over the API, refuses the
board. It routes round everything on the board: pads (a padstack's every layer; a route ends where every layer
has copper), tracks, vias, holes, keep-outs (their arcs to the true arc), the edge, and every copper graphic,
text (by KiCad's stroke metrics, a TrueType one by the outline KiCad saves), text box, table, barcode and
dimension; new copper keeps out of other nets' solder-mask openings (DRC's `solder_mask_bridge`), and new
untented vias whose openings the clearance cannot hold are refused. It searches each connection on a grid whose
free nodes are worked out from the exact shapes (a move between two free nodes is clear along its whole
length), pulls each path tight in continuous geometry, checks every segment and via once more, exactly, and
writes the tracks and vias in one commit: nothing on the board is moved or deleted, nothing else is written,
and the block's save writes the file; a block that raises saves nothing, so a dry run is a route and a raise.
Octolinear and deterministic: the same board and plan give the same copper, in another process and on another
OS: between the board's text and every decision there is only IEEE-754 arithmetic (its angles are its own, not
the C library's), and the tests hold one board's routed copper to a digest on Linux, macOS and Windows.

The answer, a `Routed`, holds every connection's outcome and the plan entry it came from (`Connection.entry`),
with `.ok`, `.failed`, `.warnings` and `.human_lines()`: one it cannot route is answered by name with what walls
it in and what to do (with no via left, the layers it reaches and the via limit as the cause), on stderr too,
and the rest go on; each warning is on stderr (`route: warning: ...`) before routing. A copper pour is neither
an obstacle nor a connection to it: a pad only a pour joins counts as apart, and `board.refill_zones()` in the
block refills the pours round the new copper. It runs in the script's process. It does not route differential
pairs, keep a length, skew or track-angle rule, or choose what to route or in what order.

## The interference check

A B-rep document's `interference` says which of its parts share volume: `cad.model.interference`,
`cad.xbf.interference` and `cad.step.interference`, one to one with `cad <type> interference SRC`. Every pair of
parts whose boxes meet is answered, as built and at each of `poses`: a mechanism state's name, a
configuration sequence at a time of it (`"walk@0.6"`), or `{joint: value}`, as every command takes a pose. It
checks the poses it is given and chooses none. `fits` names the pairs meant to share volume, listed
apart. A pair with air between its two parts is ruled out on their meshes (the kernel's own proximity test, and
a point of each shell classified against the other's solids, so a part swallowed whole is not missed); every
other pair is measured exactly, on the parts' own solids. The engine measures it and keeps each answer by the
two parts' geometries and how one stands to the other: a document edited is measured again only where a part
that changed is one of the two, and the same check of an unchanged document is answered at once.

```python
from cad import model

found = model.interference(robot(), poses=["crouch", "walk@0.6"], fits=[("bearing*", "housing")])
for finding in found.findings:          # an `overlapping_parts` each: its two occurrences in .refs, mm3 in .value
    print(finding.human_line())
assert found.ok, found.summary          # not ok where a pair shares volume, or could not be measured
```

The result is a `CheckResult`: `failed` where a pair shares volume, `not_checked` (its `reason`
`unmeasured`) where none was found but a pair could not be measured (past its five minutes or the check's
twenty, its process lost, the kernel's refusal: each row's `reason`) -- never a pass, and asked again the check
goes on from what it measured -- and `ok` only with every pair answered and none
sharing. A shared volume of `min_volume` or less (0.001 mm3 by default) is none. `measurements` holds the poses, the pairs counted and how each was answered (`pairs`: `apart`,
`kept`, `measured`), every row of `overlaps`, `fits` and `unmeasured` (each `between` its two parts, with every pose it holds at), and the measurements that took
longest (`slowest`).

## Manufacturing checks

A 3D document's `dfm` says whether a part can be made by a process, and what to change where it cannot:
`cad.model.dfm`, `cad.step.dfm`, `cad.xbf.dfm`, `cad.stl.dfm`, `cad.threemf.dfm` and `cad.glb.dfm`, one to one
with `cad <type> dfm SRC --process cnc|sheet|molding|printing` (a mesh -- STL, 3MF, GLB -- takes `printing`
alone, its default: CNC, sheet and molding are judged on exact geometry, and a mesh asked for one is refused
with the check to run instead, the STEP's or the model's), and a DXF's, `cad dxf dfm FILE`, as a sheet's cut file
(its one process, `sheet`, the default). The source is a file of the type or, for `model`, a model's document the engine
holds (its id, or the handle its call returns), so a check script measures the model it builds:

```python
from cad import model, step
from cad.build123d import dfm
from part import part                                          # a model

model.dfm(part(), process="cnc", material="aluminum", axes=3)  # corners, pockets, holes, walls, setups
step.dfm("bracket.step", process="sheet", material="5052", bend_radius=1.6)
step.dfm("cover.step", process="molding", pull="z", material="abs")   # draft, undercuts, ribs, clamp
step.dfm("housing.step", process="printing", technology="sla")         # walls, pins, trapped resin
found = dfm(shape, process="cnc", tools=[3, 6])                # a live build123d shape, the same result
if found.status != "ok":                                       # "ok", "failed" or "not_checked"
    for finding in found.findings:                             # a rule's verdict: its figure, limit and refs
        print(finding.code, finding.location, finding.value, finding.limit, finding.unit, finding.refs)
```

**Three states.** A check answers one of three (`CheckResult.status`; the command's exit status):

| `status` | exit | what it says |
| --- | --- | --- |
| `ok` | 0 | every part was measured and no finding is an error: the part can be made. Warnings are recommendations: it is made, at a cost or a risk |
| `failed` | 1 | a finding is an error: the part cannot be made by this process as drawn. With `--strict` (`strict=True`), a warning fails it too |
| `not_checked` | 3 | the check did not judge what it was asked to, so it is no verdict and never a pass: a source that does not read or holds nothing to measure (`document_unreadable`, `document_empty`, `not_solid`, a mesh's `mesh_unreadable` or `mesh_empty`, a cut file's `no_cut_geometry`, a file that is not there: `invalid_target`), a family that could not be measured (`measurement_failed`), faces the kernel failed to intersect rays with (`rays_unintersected`), a rule whose features carry no figure that should have been measured (`rule_partly_judged`), rules that judged nothing (`rules_none_evaluated`), a report with a figure that is no finite number (`not_finite`). `reason` is the code of the finding that says so |

`ok` is true for `ok` alone. An error found wins over what was not checked: the part fails whatever else
was not judged, and the line says both. Read the state from `status` (or the exit), never from a finding's
severity: a `not_checked` result carries an `error` finding too, the one whose code is its `reason`, which
says why nothing was judged. The command exits 3 too for a check that did not run to its end --
the engine stopped it (its document changed under every try of it, it went past its time or its memory), lost its process
or stopped itself, its environment gave no answer, it crashed -- where `--json` is the failure's document with `"status": "not_checked"` and a
`reason`, and one line on stderr says `NOT CHECKED (<reason>)` and why; a library call raises those. A check its
caller measures (a mesh's, a cut file's, a file's with no engine to reach) runs in a process of its own held to
the same limits (`CAD_ENGINE_CHECK_SECONDS`, `CAD_ENGINE_CHECK_RSS_MB`): past one its result is `not_checked`,
`over_time` or `over_memory`. Exit 2 stays the command line's mistake (`"status": "usage"` in its `--json`
document): an option refused by name, a file of another type or not there, a document the engine does not hold.

- **CNC machining** (`--axes 3|4|5`, `--turning`, `--tools`, `--stock`): holes (drill sizes, depth, drill
  points, counterbores, threads, a wall that cuts a hole's mouth), pockets and slots, internal corners against
  tool radius and depth, sharp
  internal edges no tool makes, walls and gaps, tool access per setup direction and the setups it needs,
  undercuts, voids, stock; turned parts' axis, diameters, bores, grooves and live-tooling features.
- **Sheet metal** (`--thickness`, `--k-factor`, `--bend-radius`, `--kerf`, `--sheet-size`): constant
  thickness, bends, flanges, reliefs, hems, holes and their distances to edges, holes and bends (in each
  convention), notches, tabs and webs, measured on the part unfolded with its K-factor
  (`cad.build123d.unfold`); a DXF's contours, overlaps, crossings, annotation and small features.
- **Injection molding** (`--pull`, `--cavities`): per-face draft, undercuts and the side action, lifter or
  collapsible core each needs, wall thickness and thick sections, ribs, bosses, internal corners, projected
  area and a clamp-force estimate, the parting, the mold envelope; `--candidates` ranks the pulls.
- **3D printing** (`--technology fdm|sls|sla|mjf|pbf`, `--build-volume`, `--layer-height`, `--nozzle`, `--printer`):
  walls supported and not, gaps, holes, pins, embossed and engraved detail, overhangs, bridges and
  cantilevers, clearances between parts, trapped volumes and their escape holes, build-volume fit, bed
  contact and warping, stair-stepping, support; `--candidates` ranks orientations.

**Facts, then verdicts.** A STEP, an xbf or a model's document is measured exactly on its B-rep (the
`build123d` integration), each finding at a face ref that `cad xbf inspect DOC REF` resolves
(`plate/face 7`) -- in one of the engine's checks processes: a file read once, a model from the bytes the engine
holds of it, the same check of an unchanged document answered from the result the engine kept; a mesh by the `trimesh` integration (`cad[trimesh]`), by its caller, each at `x, y, z` in
millimetres.
The measurements are facts and always reported (`measurements`). The verdicts are general: each process has
one table of rules: general practice from published design guides, each rule citing its guide as the
evidence, and cad's own floors where no guide states a limit, each labelled as its own -- no rule
is a shop's limit, and every result says so (`rules_general`). A shop's own limits are
compared with the measurements; what a person knows of their own shop is a plain option (`--tools`,
`--bend-radius`, `--k-factor`, `--sheet-size`, `--build-volume`, ...). A failing rule is one finding for
each feature that fails it, coded by its id, at the feature's most specific ref (a corner's edge, not one of
its two faces), with the verdict as data -- `rule`, `value`, `limit`, `unit`, `op` (`min` or `max`),
`source` (the guide's publisher and title, or `cad` for a floor of its own) and `refs` (every ref the feature names, `location` first) --
and a hint saying what to change; an error is a limit the part breaks, a warning a recommendation. The
command says a rule once -- its hint, its source and how many places -- then a short line a place, and its
last line leads with the state and the counts, which are the findings': `FAILED part.step: 4 error(s), 2
warning(s); cnc ...; failed: cnc.internal_corner_sharp x4`. Every rule's outcome, its source and every
failure (with the index of its item in its family) are `measurements["rules"]`, and a figure not measured is
never a pass: a rule that could not judge some of its features says which (`rule_partly_judged`, its `refs`) and the
check is not checked. What does not apply is no gap: a figure that cannot exist of a feature (a lone rib's
gap to a neighbour) is named in the feature's `not_applicable`, and what a source does not hold (a mesh's
holes, pins and details; a cut file's bends, reliefs, hems and thickness) is said once as a fact
(`families_not_measured`), its rules not evaluated.

**Every part, as it stands.** An assembly's every part is judged, and a part used several times is judged
each way it stands: the occurrences turned alike are measured once and counted
(`measurements["bodies"][i]`: `occurrences`, `paths`, `placements_mm`), and one turned another way is
measured as it stands, at its own refs -- a bracket that prints clean on its back and needs support on its
side is said at the occurrence on its side. `measurements["document"]` totals every occurrence
(`occurrence_count`, `solid_count`, `volume_mm3`), and so does each process: a print measures every
occurrence where it stands on the plate, and the others' totals count a part once for each time it occurs.
Several parts are said (`several_bodies`); one part of several solids says so in every process
(`several_solids`), and solids that share volume fail every process (`not_sound`).
`--material` picks a material's limits, and without it the material the parts declare is read
(`part.material = metals.aluminum()`, when every part agrees: `material_declared`); without `--process`, an
xbf's or a model's parts' declared process is read too (a STEP keeps no process) (`metals.aluminum(process=machined())`,
`plastics.abs_(process=molded())`, `fdm(layer_height_mm=0.2)`, `sls()`, `mjf()`, `slm()`, `vat()` from
`bd_materials.processes`: cnc, molding, or printing with its technology; `process_declared`), so
`cad model dfm ID` alone checks a part for what it says it is; `units` is an STL's, and a DXF's where it
declares none or the wrong ones (the other types declare their own, and take no such option); an option of another process, a value of another kind
(`axes=3.7`, `turning="no"`) and a value no machine has (an end mill over 100 mm, an FDM layer taller than
its nozzle) are refused by name, never coerced -- by the flag on the command line (`--tools`), by the
parameter in Python (`tools`), where a list of numbers is given as one (`tools=[3, 6]`, `stock=(100, 60,
25)`) and a material by its name (`"Aluminium 6061"`). Every family, its JSON, every rule with its source and
what each check cannot measure: [the manufacturing checks](src/cad/_internal/dfm/README.md).

The trimesh integration's functions measure a mesh a program already holds, answering its report as data:
`cad.trimesh.printing(mesh)` and `cad.trimesh.orientations(mesh)`, each taking a `trimesh.Trimesh` and never changing it. A script run with
`cad run` that imports `trimesh` or `cad.trimesh` gets that integration and one that imports `build123d`
gets the other; one that calls `cad.<type>.dfm` gets the type's -- `cad.stl.dfm`, `cad.threemf.dfm` and
`cad.glb.dfm` trimesh, `cad.step.dfm`, `cad.xbf.dfm`, `cad.model.dfm` and `cad.dxf.dfm` build123d -- found by
`cad run`'s scan of its source, with nothing in its header; a name the scan cannot see (imported by name at
run time) the run says it lacks, in one line.

**Since 0.11.7** a check judges; before, it measured, and a part passed whatever its figures were. What a
script or a prompt written for an earlier release meets now:

- **The exit and `status`.** 0 `ok`, 1 `failed`, 3 `not_checked`, 2 the command line's mistake. Exit 1 used to
  say "could not be measured or read", which is 3 now, and a part that breaks a rule's feasibility limit, a
  warning and a pass before, fails. `--json` gains `status` and `reason`, and every check's result carries
  them (`drc`, `erc`, `validate` and `solve` too: `ok` or `failed`); `strict` is new.
- **Findings.** A rule's verdict is data (`rule`, `value`, `limit`, `unit`, `op`, `source`, `refs`): read
  those, never the message. On exact geometry a finding's `location` is a ref (`plate/face 7`) where it was
  `x, y, z`, and the parts' facts are `measurements["document"]` and `measurements["bodies"]` where they were
  `measurements["mesh"]`; a mesh's are as they were.
- **What fails a part** is every finding of severity `error`, whatever its code: a rule whose `severity` is
  `error` (`measurements["rules"]["outcomes"]`; [the manufacturing checks](src/cad/_internal/dfm/README.md#since-0117)
  lists them as of this release), a process's own error (`sheet.not_sheet`), and the part's soundness:
  `not_watertight`, a warning before, is an error on a mesh and on exact geometry alike, as `not_sound` is.
- **Gone.** A mesh's molding check: `cad stl|threemf|glb dfm --process molding` is refused (exit 2), and
  `cad.trimesh.molding` and `cad.trimesh.pulls` are not there -- molding is judged on exact geometry,
  `cad.build123d.molding(shape)` or `cad.step.dfm(path, process="molding")`. With it went the findings
  `coarse_curved_face`, `mesh_folds` and `probe_resolution`; `sealed_voids` is `internal_void`, one finding for
  each void. Printing's `--candidates` answers the orientations alone, best first: run the check once without
  it for the part's own figures.
- **`units`** is an STL's and a DXF's (`--units`; a DXF that declares none is `not_checked` without it,
  `units_not_set`). `cad.step.dfm`, `cad.xbf.dfm`, `cad.model.dfm`, `cad.threemf.dfm` and `cad.glb.dfm` take
  none, where they took `mm` alone.

## Stress studies

A B-rep document's `solve` is a linear static stress study of a part or of an assembly bonded where its
parts touch: `cad.model.solve`, `cad.xbf.solve` and `cad.step.solve`, one to one with `cad model solve`,
`cad xbf solve` and `cad step solve` (a mesh has no faces a study can hold or load by, so the mesh types
have none). It is a check (law 26): its answer is a `cad.results.FeaResult`, a `CheckResult` whose
findings carry a severity, a code and a location, with two uses of one signature:

```python
from cad import step

setup = step.solve("bracket.step")                          # writes nothing
setup.parts, setup.pairs, setup.faces                       # what a study names, by ref
result = step.solve("bracket.step", study="study.json", out="/tmp/bracket")
result.ok, result.findings, result.measurements["safety_factor"], result.written
```

With no study it is the study's setup: the document's parts, the pairs that touch within the contact
tolerance a study bonds by (an overlapping pair a warning) and one part's faces, each with the engine's
ref (`bracket/face 17`, the one the viewer copies) and a hint (`plane, normal -Z, largest`). With a
study (a JSON file, inline JSON or a dict) and `out`, a folder anywhere (made when missing), the solve,
which writes its results there, each a standard file that stands on its own, and touches nothing else in
the folder:

| File | What it holds |
| --- | --- |
| `result.json` | the `FeaResult`, as `--json` prints it |
| `result.glb` | the deformed surface coloured by stress (a ramp texture, so every glTF viewer and the engine's stills draw it), the raw fields as attributes |
| `result.vtu` | the volume's tetrahedra with displacement and von Mises at their corner nodes, for meshio, PyVista or ParaView |
| `stress.png`, `displacement.png` | the engine's stills of each field with a colour bar under each, where it can draw (else a `solver_note`) |
| `ccx.inp` | with `deck`, the input CalculiX solved |

There is no document type for a result: the answer is the JSON, the pictures are for looking, the GLB
opens in the viewer as any GLB does, and the VTU is for a program's own questions. An option of the
other use is refused by name before anything is read. The study reads a file in its own process, as the
engine reads one (`engine.document.load`), with no worker and no build, and resolves faces in the
document's structure as `cad <type> inspect` does (`engine.refs`); a model is written to an `.xbf` in a
temporary folder first, by the engine that holds it, and its result names it by its document id. The
folder's files are each replaced only once all are written, so a failed run leaves the previous results
as they were. Its `ok` is every check's rule, an error blocks: a part that yields or misses a check is a
correct result of a part unfit to use, so its results are written and the command exits 1, as is a study
stopped before the solve (a part nothing holds), with none. A study whose answer would be wrong is refused
instead, writing nothing: a zero load, a load on a held face, a study no load reaches, reactions that
do not balance. `_internal/fea/` solves one kind of study: linear elastic stress and displacement.

Three integrations run it. The kernel reads the B-rep. The mesher is `netgen` (`cad[netgen]`), installed
only where netgen publishes wheels (macOS, Linux x86_64 and Windows x86_64; elsewhere a solve refuses,
naming the platform) and always run in a process of its own, since its OpenCascade and OCP's cannot
share one. The solver is `calculix` (`cad[calculix]`): CalculiX's own `ccx`, which the `cad-ccx` package
carries for each platform (conda-forge's build, unmodified, pinned exactly), found by the integration's
probe: `CAD_CCX` names another (2.20 or newer), and a `ccx` on PATH is never run. It runs headless, on
one thread, in a private folder with homes of its own, so it reads and writes nothing of the person's,
and the result names the CalculiX version that ran; `cad run ccx ARGS` runs the same program on a deck of
a person's own (`cad.calculix._command`). The operation is the calculix integration's, which names the
kernel and netgen `alongside`, so the `cad` command runs a study where all three are: its own process
when its environment holds them, else the environment of `cad[build123d,calculix,netgen]` (law 27); a
script run with `cad run` that calls `cad.<type>.solve` names the extras in its header, and a solve
without one says so in one line.

## Joint stops

A document with a mechanism -- a model, an xbf, a STEP -- answers `ranges`: `cad.model.ranges`,
`cad.xbf.ranges` and `cad.step.ranges`, one to one with `cad model|xbf|step ranges`. It is a check (law
27): a `CheckResult` whose finding per joint (`joint_stops`, at the joint) says where it stops each way and
which two parts meet past each, every number in `measurements["joints"]`. The document is read in the
calling process, as a study reads one (a model exported by the engine to an `.xbf` in a temporary folder
first), described as a robot (`engine.describe`) and each joint swept alone against its parts' surfaces
(`engine.ranges`: surfaces sampled to a fixed resolution and measured gap by gap, the other joints as
built): its stop is where its child link meets its parent link, and a clash with any other link before it is
said beside; a larger clearance only narrows a range. Every part is tested against every other on its own
surface: where a simulator stops a joint, with the collision shapes a MuJoCo function chose, is a question
for the simulator on its file. It writes nothing and changes nothing: a model is code, and its ranges are
written in it (law 21). Its options describe the sweep: `step` (degrees or
millimetres), `clearance` (millimetres, 0.3 by default and at the least: the surfaces' sampling) and `joint`
(the joints to sweep, every one a person moves by default; a name the document has no such joint by is
refused, naming its joints). The kernel reads and meshes the document, so the `cad` command runs it where the kernel is: its own
process when its environment holds it, else the installation's base (law 27).

## Since 0.11.8

What 0.11.8 adds:

- **A model declares what is true of the machine for a robot description.** `cad.build123d`'s `body`,
  `frame`, `free`, `limits` (a drive's `effort` and `velocity`), `link`, `mass` and `point_mass` are kept
  in the xbf beside the materials. Each is a fact of the machine; how a simulator collides a part, which
  pairs never collide, contact friction and a joint's dynamics are a simulation's choices, made in a MuJoCo
  function.
- **A document exports as a robot description.** `cad model export ID robot.xml` (MJCF) and `robot.urdf`
  write its links, exact inertials, visual meshes and colours, each part's mesh as its collision (MuJoCo
  collides a mesh as its convex hull), sites, drive force bounds, couplings, closed loops (MJCF) and states
  as keys, with a `scene.xml` beside an MJCF; `--zero STATE` counts every joint from a state. Its summary
  says how the parts collide, and that a MuJoCo function is where to choose otherwise.
- **A MuJoCo function makes the simulation's choices** (`cad.mujoco`, `cad[mujoco]`): `spec` makes a
  document a `mujoco.MjSpec`; `parts` lists its parts' label paths; `collisions`, `fit` (a box, sphere, cylinder or capsule fitted to the part's
  exact solid) and `decompose` (CoACD's convex hulls of its mesh, `cad[coacd]`) find and replace a part's
  collision by its label path; everything else is MuJoCo's own API; `save` writes the spec as a folder that
  travels.
- **`cad.mujoco.check` checks a MuJoCo model's file** (`cad mujoco check robot.xml`): MuJoCo's own compile,
  the model-health checks, what the model collides as and its contact excludes, as a check's result. An
  MJCF is no document type: cad writes one and asks MuJoCo about one, and MuJoCo Studio shows it (`cad run
  mujoco-studio --model robot.xml`). `check` is the first operation of an integration's own (law 26).
- **`ranges` finds each joint's stops** from the parts' surfaces (**Joint stops**).

What a model, a script or a check written for 0.11.7 meets now:

- **A child turned about its joint's axis at its zero fails the run.** Where a child was built where it
  stands -- its `RigidJoint` at the joint's origin, its Z on the joint's axis, its X another way (as a
  `bd.Plane` of the axis on a turned part gives) -- and `connect_to` turned it about that axis at the joint's
  zero, 0.11.7 built it turned. The run now fails, naming the joint, the turn and the frame to build the
  `RigidJoint` at: a revolute's own frame, `hinge.location`, or a slide's position in its rail's
  orientation. A `RigidJoint` whose Z is not the axis, or that stands elsewhere, places the child on the
  joint as before.
- **A read STEP's densities are the file's.** OCCT read a density declared in kg/m^3 (what most CAD tools
  write) 1000 times too small; it is now read as declared, so masses from such a file are 1000 times
  larger than 0.11.7 said. A STEP this library wrote (g/cm^3) reads as before.
- **A read STEP's user-defined attributes are no materials.** A part parameter a CAD tool writes (`QTY`,
  a sheet-metal default) was read as a material named for it, with no density; it is now none, and an
  attribute that names a material (`PTC_MATERIAL_NAME`) names the part's material.
- **`cad.urdf.validate` warns `zero_effort` and `zero_velocity`** for a joint limit of 0 that is not a
  mimic's. With `strict`, a URDF that passed in 0.11.7 can fail: give the drive's limits.
- **A snapshot's untriangulated faces are one warning**, naming the first parts and counting the faces,
  where 0.11.7 said a line a part.
