# cadgen

The published distribution: CAD models written as Python, built by cadgen's engine
(`cadgen.engine`) into live XCAF documents and the files those models declare (XBF, STEP, GLB, STL,
3MF, DXF), and the tools that show and check them. One PyPI package carrying the Python under
`src/cadgen/` and what it ships that is not Python under `src/cadgen/_runtime/`: the CAD
Viewer's client and the CAD app page, which it serves, built from their JavaScript packages
and bundled in at build time (the JS *source* never ships). Its snapshots are drawn by OCCT,
never in a browser.

```python
from cadgen import step, xbf
import build123d as bd

@xbf("XBF/arm.xbf")                      # XBF/arm.xbf beside the script
@step("arm.step")         # and its STEP, a translation of that document
def arm():
    return bd.Box(10, 20, 30)


if __name__ == "__main__":
    arm()
```

`cadgen run` builds a model in its project's environment -- the project's dependencies and
the engine's own cadgen, made by uv once -- starting the selected engine when none runs; the
other commands attach to the running engine (which `cadgen server` in another terminal, or the
MCP bootstrap, starts too).

```bash
cadgen run arm.py                             # builds it in the engine's warm worker
cadgen export XBF/arm.xbf arm.glb arm.stl     # more translations of the document it wrote
cadgen snapshot XBF/arm.xbf arm.png           # a still of it, drawn by OCCT
cadgen serve XBF/arm.xbf                      # the document on a local page
cadgen inspect XBF/arm.xbf                    # what it holds, then its build closure
```

**PURPOSE** — the engine and its command surface: models built in a warm worker whose memo
makes an edit cost what it changed, documents and their exports, kinematics and configuration sequences,
materials, references to geometry, snapshots drawn by OCCT; the CAD Viewer (`cadgen viewer [FILE]`: a
launcher for the selected engine's one page, every document at `/<id>`, every file read by its absolute path); CAD beside an agent's chat (`cadgen mcp`: a stateless stdio peer of the engine’s
HTTP MCP endpoint, with tools and the app page owned by the engine); the URDF, SDF and SRDF validators; and
engineering drawings (`@eng_drawing`).

**MAY DEPEND ON** — the Python ecosystem it declares (OCP/build123d lazily, never at
`import cadgen`) and the bundled runtime. Never app code, never JavaScript source at runtime.

**DEPENDED ON BY** — every skill (as a pinned installed distribution). The CAD Viewer is not a
dependent but a part: the engine serves `cadgen.viewer`’s client, HTTP application and
every STEP and `.xbf` a page opens on one authenticated listener, without a relay.

## The rest of the package's documentation

This file holds the LAWS. The engine's own README holds the mechanisms they constrain; where
the two disagree, the engine's README is right.

| Document | What it is for | Go there when |
|---|---|---|
| [`src/cadgen/engine/README.md`](src/cadgen/engine/README.md) | The engine: models and decorators, running a model in its project's environment, the engine server and its workers, the door, progress, the viewer and the snapshot, exports, kinematics, couplings and configuration sequences, materials, imports, placements, the mesh and its wire format, element names, references, body retention, queries, memo functions and the build closure | changing anything a build, an export, a snapshot or a served document does |

## The design laws

These are LAWS, not conventions: a change that violates them is wrong even when it works.
Laws 1 to 13 and 19 to 23 are the engine's; 14 to 18 hold for the whole package.

1. **An xbf carries its build closure as pointers and digests** -- script and function,
   modules, data inputs, the toolchain (versions, the Python and the machine) and the key; never
   source, never lines on elements, never input contents, nothing of git's; names remain the
   per-element tie to code (the engine's **Build closure**).
2. **Only requested files to disk.** The engine writes the files a model declares -- the xbf and the exports
   its decorators name, nothing beside them -- and the operating system's coordination for its
   warm process: a door (a named pipe; on Windows a port file), a lock and its connections' pipes, in
   a folder only the user can make: `cadgen-engine` in `$XDG_RUNTIME_DIR`, else in the user's own
   temporary folder (on macOS the one the system names, whatever `$TMPDIR` a sandbox sets; else
   `$TMPDIR`), else `/tmp/cadgen-<uid>` -- and cadgen's own
   state in the user's state folder: settings, Recents' small previews, and the registry of the
   documents it has built, been handed or opened, one record each that points at its script or
   file, the user's one page token, each engine's connection metadata (keyed by its selected port; this user's alone), and each registered installation's record
   (`installations/<version>.json`: its python, its console script, its environment), and the
   release the device runs (`current`).
   Document records, Recents, thumbnails and cached document bytes are shared across
   ports, as are preferences, the page token and installation registry. State stores
   neither geometry nor source. In the platform's cache folder (`~/.cache/cadgen`, by
   0.7's rule), under `documents/`, it keeps each model document's last-built bytes: its own file, never a
   declared or exported xbf (the same bytes), kept until a person deletes it -- nothing evicts it
   -- and made again by a run of its script (a shape's by the program that handed it over), so a
   restart opens saved documents; and under `pycache/` the bytecode its own processes compile of the libraries they load
   (`PYTHONPYCACHEPREFIX`, with worker bytecode separated by its startup dependency snapshot), regenerable too, so nothing is written
   beside a library or a model. The code stays the only source of truth: a document is what its
   last run made, the engine never checks the code on disk against it, and nothing reruns -- when
   to run the code again is the agent's call. It writes no
   sidecar, record of a build beside a model, index, memo, mesh or parsed document, and no derived file
   beside an input. A model whose document -- in its warm worker, else the cache -- holds the closure the
   model has now is not run, whatever files it declares: they are exports of the document, written
   after it. Explicit viewer exports write only the requested
   artifact to managed temporary storage for delivery; no source or intermediate XBF
   is written (the engine's **Viewer exports**).
3. **Standalone.** `cadgen.engine` imports nothing of cadgen outside itself: OCP, build123d, bd_materials, threejs_materials (and
   ezdxf, build123d's own DXF library), numpy, Pillow and the standard library only. cadgen
   reaches into it, never the other way: its telemetry is an observer the engine calls with
   plain facts (`engine.api.observers`).
4. **XCAF is the document; files are explicit.** A live model holds an XCAF document;
   `@xbf` or `--xbf` serializes it as native BinXCAF. It holds: units in millimetres,
   prototypes and instances with placements, a name on every part and instance, colours and
   materials per part and per painted face, element names on face, edge and vertex labels, and
   an assembly's mechanism. STEP, GLB, STL, 3MF and, of a planar document, DXF are translations
   of it; `cadgen export` writes any of them from the xbf alone.
5. **The memo is the only build cache, and it lives in the worker.** Every kernel operation a model
   runs is keyed by its inputs, and so is every question it asks of what they made: a validity
   check, a volume, a distance. A hit hands back the objects the first run made, or the answer it
   gave, and a miss makes everything downstream of it miss. So an edit costs what it changed, and an element
   keeps the name its feature history gave it across edits. Across a restart, a model's build
   is cold but for its document in the cache -- every model's alike, taken whole by its key or not
   at all; a declared file, its xbf too, is never a source -- and what a restart shows without a build
   is the engine's document cache (law 2): the last built state, never a step of a build.
6. **One document per model, with one id.** Every called model makes one document, and a call
   returns its handle (`.id`, `.url`, `.name`, `.shape`, `.export`, `.snapshot`), never a bare
   shape. Every id is one formula, `uuid5(NAMESPACE, canonical(scope) + "::" + name)`
   (`ids.derived_id`): a model's script and function (`ids.model_id`), an opened file's path and
   no name (`ids.file_id`, inside the engine only: its public name stays its path), a shape handed
   over its calling script, or the working folder, and its name -- the same in every process,
   worked out without asking the engine. Identity is namespace plus name: in 0.8 the namespace is
   the script's folder, with no project detection. A model's name is its identity within its
   namespace, the function's name by default, `name=` gives it another. An explicit name uses the
   folder as the formula's scope; one that another file of the folder declared at its last run is
   refused, naming both declaration locations, until that file is gone or runs again without it. Unnamed functions in different files keep their script/function ids. A
   function in a file is a model (the registry points at its script), and a shape is handed over
   (`model(shape, name=...)`: held and kept, never rebuilt); every one is recorded and kept in
   the engine's document cache alike. A function is declared by `@model` (no file) or by its file
   decorators (those files), never both; file decorators write only their named outputs. No xbf,
   mesh, memo, provenance or derived file is written for a document beyond what it declares. A
   document lives until a person deletes it (`cadgen delete`, the home's Delete); its worker
   retiring does not end it, nor does memory, which reads it again from the cache. A document
   that is not held names the command that builds it again; the engine never runs it (the
   engine's **Document lifetime**).
7. **Provenance is served live, never written.** What made an element -- the feature, its
   operation, the function, file and line of its call -- lives in the trace of the worker that
   built the document, and is asked of it while it lives (`made_by`, `cadgen inspect`). A model's
   document opened with no such worker has none to give, and says so (`made_by: null`); a file --
   a model's declared xbf among them -- names no model and answers none.
8. **Poses and motion definitions, never frames.** The document carries kinematics -- the
   mechanism, its mechanism states and its configuration sequences -- as poses and definitions,
   never baked frames or clips. A GLB export is the one place a sequence is baked, into a clip of
   the GLB; the engine plays nothing.
9. **Names are the durable tie to code.** An element's name is spelled from the function that
   made its feature and the author's name for that feature, never from a line or a file: moving
   code renames nothing, and the file holds no line to go stale.
10. **A file decorator requires an explicit output path.** `out` is required; `name=` optionally names the model;
    omitted paths and `None` are refused. Whenever the model it decorates runs in a
    build -- the build's target, or a child another model's body calls -- or is taken from its
    key, that file is written, once per build, from the model's own document, exactly as an export
    of it writes it: translated, compared, and written only where it differs or is missing; a
    GLB's animations are baked from the code when that GLB is written. A model with no file
    decorator writes nothing.
11. **Decoration only declares; a model script is Python.** A script runs only when Python
    runs it; no verb imports or builds a script. Importing cadgen or
    defining a decorated function never builds a model, writes its outputs, starts a
    worker, or exits the caller. An explicit call builds the model and writes its
    declared files, then returns to the caller. Python controls which calls run and
    in what order, including its `__main__` block and conditions; watchers never
    change that control flow. cadgen consumes no script arguments. Engine switches
    are environment variables.
12. **A model is a Python script.** Decorated functions declare models; explicit calls
    build them; `python script.py` runs the program. No command builds source text.
13. **The document's kinematics are AP242's, and cadgen stores no kinematic fact the
    standard cannot name.** Every entity and attribute of the mechanism subtree is ISO
    10303-105's as Part 21 writes it (edition 4's domain model's where Part 21 has none);
    only the root says the schema and the units. What the standard cannot say is not
    patched with an attribute of cadgen's own: it is dropped, or refused by name at document
    time (the engine's **Kinematics**; a conformance test walks the subtree and holds it). The
    authoring functions are named after the entities they write: `mechanism_state`
    (`mechanism_state_representation`), `configuration_sequence`
    (`interpolated_configuration_sequence`), and `gear_pair`, `rack_and_pinion_pair` and
    `screw_pair`, each refusing a joint its pair does not relate.
14. **The package ships alone.** The installed distribution is the whole world: the Python, the
    bundled `_runtime/`, and this document. It works with the repository it was built from gone
    -- and its markdown must read that way, referring to nothing outside the package.
    *Pressure-test*: every sentence in the package's markdown must be true and actionable for
    someone who only ran `pip install cadgen`. Naming a bundled thing ("the JavaScript runtime
    bundled at build time") passes; a repository path to its source, a repository script, or a
    repository workflow does not.
15. **No backwards compatibility for authoring and runtime APIs.** Hard cutovers only.
    A retired surface does not exist: no
    alias, no shim, and no error that recognizes its old spelling to explain what replaced it. A
    removed command, flag, argument, key, module or name gets what the current contract's
    ordinary validation says -- an unknown command, an unrecognized argument, an unknown key, an
    `ImportError`, an `AttributeError`.
    *Pressure-test*: use a removed spelling; the error must read exactly as it would for a name
    that never existed.

    Read-only diagnostics may identify an older engine through its status protocol.
    This restores no authoring API and never admits builds against that engine.

    **Persisted-document exception.** Saved documents have a separate compatibility contract:
    opening, viewing, importing and exporting supported formats must not require their source or
    a rebuild just because cadgen was upgraded. The engine reads `xbf/8`, `xbf/9` and `xbf/10`; it converts
    `xbf/8` material metadata in memory, without executing model code or changing source or cache
    bytes. A separate migration record identifies the conversion while the original build closure
    and toolchain provenance remain unchanged. Explicit export to a different XBF path can save
    the upgraded document atomically; opening it does not rewrite it. Unsupported formats and
    failed conversions preserve the original bytes and cache record and give a clear error.
    Build-cache reuse is separate: explicitly running a model compares the current key and may
    rebuild it. This exception retains no retired authoring APIs or classes. The engine's
    [Build closure](src/cadgen/engine/README.md#build-closure) describes the supported conversion
    and export behavior.

16. **Closed vocabularies.** Every declaration surface has a closed key/kind set. An unknown key
    is an error naming the supported set, never silently ignored.
17. **Loud failure or correct output, nothing between.** The cardinal sin is plausible-wrong
    output at exit 0. No silent fallbacks, no globs, no guessing; a failed write or render leaves
    no file this run wrote; an earlier file stays byte for byte.
18. **Nothing waits on the network.** Once installed, cadgen works offline: every command,
    build, snapshot, server and page. Its own requests are two: telemetry (`analytics.py`, usage
    counts under a random id, sent by default once a `cadgen` command has said so, and never
    after the person's no) and the hourly version check (`updates.py`), with the download of a
    newer release the engine's self-update makes where the install command set the computer up
    (`_internal/auto_update.py`). They run in the background and fail silently: no start,
    command, build, request or tool call waits on them.
    A command sends nothing itself: what it counted -- an engine verb's build, export or
    snapshot (`_internal/engine_telemetry.py`, cadgen's observer of the engine), a drawing, a
    crash -- is kept in a small file beside the settings (`analytics.spool`), which the CAD app's
    and the viewer's background sends take, and a command that finds it has waited more than a
    window, with no other process sending, starts a sender detached that sends it and exits
    (`_internal/telemetry_send.py`). A process that exits sends nothing either: its last batch is
    kept beside the settings, and the next process that sends sends it, in the background. One
    wait remains, bounded: `cadgen telemetry off`, which waits for the deletion it asks for.
    The pages load nothing from the internet: everything they show ships in the wheel.
    *Pressure-test*: with an installed cadgen and every request refused (a proxy on a closed
    port), and again with every request hanging, start a server, open a view, call each tool,
    and run a build and a snapshot: each works, and nothing waits on a request beyond the one
    wait above.

19. **Connected means warm.** A served document's outstanding version wait or recent
    sync marks it watched; a watched model document keeps its worker, and a watched file -- a
    model's declared xbf among them -- none. No timer retires a worker: memory does, and it
    retires one whose document a page watches only when no other is left. The engine outlives its clients; a page
    closing never stops a worker. The worker-count cap never retires a worker whose document a
    page watches; it is exceeded instead. The memory cap may retire it (the
    engine's **Architecture** and **The engine server and its workers**). Memory may take a
    document out of memory, for the engine's cache to give back, only when nothing watches it (the
    engine's **Document lifetime**).

20. **The port selects the engine; tabs select documents at `/<uuid>`.** The
    default is 3245; `CADGEN_PORT` or CLI `--port` selects another. Clients from
    different Python environments attach to that port's private authenticated
    transport. `cadgen server` starts the engine explicitly, and MCP bootstrap and
    `cadgen run` start or attach to it; a start first retires an older cadgen release's engine on
    the port once it is idle, and brings up the engine of the release the device runs
    (`<state>/current`) where that is newer than its own. An engine of an older release than the
    current one is superseded and steps aside by itself once nothing holds it, nothing runs and
    nothing has been asked of it for a while, first starting its successor when pages watch it, so
    they reload on it; nothing asks it to. An engine in
    use is never displaced, and no release retires a newer one's. An agent app's pinned server line is a floor, written once at install and never rewritten
    for a release: the `cadgen mcp` it names is a proxy that owns no tools and starts or attaches to
    the current release's engine, meeting it by protocol. Ordinary model calls,
    `serve`, `viewer` and document operations only attach: a missing engine, a conflicting
    listener or an engine they do not meet fails, with no automatic start, local fallback,
    rollover or retirement. A client, a project's worker and the engine meet by protocol,
    document format and native line (system, architecture, OCP major.minor), never by
    release: a project of another cadgen release that meets the engine is served, and told
    once. Model workers run in the calling project's interpreter, with that environment's
    dependencies and its own cadgen: the environment `cadgen run` makes holds the engine's cadgen,
    and that rule is for one where cadgen was installed by hand.
    The persistent document library, cache, Recents and thumbnails are shared across ports.
    No decorator selects a port and no Python connection API selects an engine.
    A tab names a model's id, or a registered file's id; scripts are never documents.
    A page never replaces or re-executes the engine. Its page and document reads
    share one authenticated HTTP listener. Launchers exit; clients closing never
    stop the engine. Kernel operations run in child processes, never request threads.
    There are no page sessions: the explorer opens where it was last, else home;
    each MCP session owns its views and resource, and a launch's folder resolves only the
    relative files it names. The stdio shim owns only connection metadata, and the one act a
    text host's `cad_show` asks of the person's machine: it opens their browser, in the
    environment its host gave it, and the engine, which runs in whatever environment started
    it, never does. The shim tells the engine, on its session, whether the page opened before
    its host has the answer, and keeps nothing of it after; the engine counts a page as open in
    a browser only once told it opened. Sidebar sharing stays in memory, and host quirks stay
    in the shim and page. The viewer's routes are the page's alone (`cad_http`), behind the
    session capability delivered in UI-only launch metadata. Only the person answers
    telemetry, through a page or the telemetry CLI. See the engine's **Architecture**.

21. **Operations on documents are Python functions the CLI exposes; process control is the
    CLI's alone.** `export`, `snapshot` and `inspect` are functions of the root
    (`cadgen.export`, ...) and commands that call them; serving, the engine's status, stopping it
    and running it (`cadgen serve`, `status`, `stop`, `server`), and deleting a document (`cadgen
    delete`, which the home's Delete is too), are commands only, with no function of the root. Every successful server-backed build reports its id and localhost
    viewer URL, including a build with file outputs. Explicit offline `Model.build(daemon=False)`, `export(..., daemon=False)` and
    `snapshot(..., daemon=False)` run cold in the caller, with no server required,
    no live document and no served URL. Failure to attach never selects this mode.

22. **A verb's option is about the picture or the path, never the model.** `export` takes a
    document and destinations: what the file holds, its parts and their placement, colours and
    motion, is what the code built, so no option selects a part or a state. `snapshot`'s
    options describe the picture (the camera, the display, the size, the state the mechanism
    is drawn in); `serve`'s and `status`'s the process. Anything that changes what a document
    is, is a function in the model's code: a part's own model, or a model returning the
    assembly in a state (`cadgen.ap242.posed`).

23. **Push, not pull: a model is what its last run told the engine.** The engine's knowledge of a
    model comes from a run an agent or a person starts (`cadgen run model.py`),
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
    read, without running it: every page, the home, every verb and tool and `cadgen status` answer
    as they did before the edit, and no process of the engine has opened a file of the model's code
    since its run.


## Agent operations

Every MCP presentation exposes `cad_export`, `cad_snapshot`, `cad_inspect` and `cad_run`,
independently of the viewer. They call the Python operations through the engine's
workers. No tool builds or imports a script: a model is built by its script, run by Python
(laws 11, 12), and `cad_run` is that run -- the engine runs `cadgen run SCRIPT.py` with its own
command, in the project's environment, and answers with the run's output and the script's
documents; a script given as text with a name is written first, as `<state>/scripts/<name>/<name>.py`,
and run as any script is. A source is an absolute CAD file path or a document id; a document id is read as
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
`jobs.py` owns admission, progress, waiting and cancellation for both agent
operations and viewer exports. Viewer exports additionally own temporary artifact
expiry, revision checks and download delivery; running cancellation discards that
temporary artifact. Browser downloads choose the viewer user's local destination
before starting. An agent's explicit host path is a different destination contract.

`cadgen inspect`, `cadgen.inspect()` and `cad_inspect` read existing files or the
documents the engine holds by id. They never execute source to obtain a missing model or write
its declared outputs. An unbuilt or unsaved model requires an explicit build: one
the engine built before names the command (`cadgen run` and the script that defines it). With no reference,
`cadgen inspect` prints what the document holds -- its state, parts, bounds, volume, materials,
joints, couplings (name, kind, ratio, joints), states, sequences, animations and declared files -- then its build closure (`--json`:
both as data; `--query structure`, the same with nothing measured: no bounds, volume or masses;
`--query closure`, and `cadgen.inspect()` with no reference, the closure alone);
with a reference it returns geometry facts. No form meshes a part, and a part's volume and box
are measured once and kept by its geometry, in memory alone.
`query="build"` (`--query build`) returns saved-file metadata and closure or live
build metadata. File metadata does not imply a live worker.

## The shape of the package

```
src/cadgen/
  __init__.py            # the root, exactly: model, the decorators (xbf, step, glb, stl,
                         #   threemf, dxf), memo, paint, read_step,
                         #   read_xbf, read_mesh, and the operations on documents (export,
                         #   snapshot, inspect), and __version__, loaded on first use; the font
                         #   guard and the lazy kernel, first
  ap242.py               # the mechanism's AP242 names: mechanism_state,
                         #   configuration_sequence, gear_pair, rack_and_pinion_pair,
                         #   screw_pair (product and manufacturing information to join them)
  gltf.py                # animation: the document records its compiled tracks, and only a
                         #   GLB reads them (an exported GLB's clips)
  engine/                # the engine: models, the server and its workers, documents,
                         #   exports, the mesh, references, the OCCT stills (its README)
  cli/                   # the `cadgen` command: a module per command, each a shell over
                         #   the function or parser that does the work
  viewer/                # engine HTTP application (engine_app), launcher (main), routes (http_app),
                         #   files by absolute path (backend), a file's catalog row
                         #   (scanner), the explorer's reads (folders), the model library
                         #   every CAD view shares (recents), a STEP's and an .xbf's serve
                         #   by the engine and in-process document reads (documents), a DXF's
                         #   payload (drawings), a robot's (robots), Quick Edit's packets
                         #   (prompt_files)
  mcp/                   # stateless stdio proxy (shim) and its JSON-RPC transport
                         #   (protocol), engine sessions (http), tools and launches
                         #   (server), the agent operations (operations), which host started
                         #   the shim and how it presents CAD (host), open views (views),
                         #   sidebar views shared in memory (sidebar), the viewer routes
                         #   in-process (tunnel), the page (ui), and the CAD Viewer link for
                         #   a host that renders no MCP Apps, which the shim opens (browser)
  urdf.py, sdf.py,       # the robot validators: one public namespace per format, its
  srdf.py                #   `validate` verb, and the checks behind it (*_source.py,
                         #   *_validation.py, sdf_external.py, findings.py, xml_common.py)
  results.py             # what a `validate` verb returns: the JSON line protocol, typed
  robot_payload.py       # a robot description resolved for the viewer's page: its
                         #   articulation, its visuals in rest space, the facts a person
                         #   reads off it; held in memory
  drawing_payload.py     # a DXF flattened by ezdxf for the viewer's pane
  eng_drawing.py         # @eng_drawing: Sheets and Views over a part, one PDF
  flatten.py             # flat patterns: exact 2D geometry from a solid's planar faces
  geometry.py            # measurements of native geometry: closest points, overlap,
                         #   soundness, mass properties
  analytics.py           # telemetry: usage counts and crash reports, on by default once
                         #   a command has said so, never after a no
  settings.py            # the person's settings: settings.json in the state directory
  language.py            # the language the person chose for the CAD views
  updates.py             # the hourly version check, and the notice of a newer release
  assets.py              # where the bundled runtime is
  check_fonts.py         # `python -m cadgen.check_fonts`: the font that breaks
                         #   `import build123d`
  _internal/             # the launch command, the installations' registry, the release
                         #   the device runs (<state>/current, which the engine's
                         #   start follows) and the proxy
                         #   it writes (installations: ~/.local/bin/cadgen, which the
                         #   skills run as `cadgen +<version>`; written as `cadgen mcp`
                         #   or `cadgen server` starts and by `cadgen doctor`, never by
                         #   another command), the
                         #   proxy's resolver (proxy), the project environments `cadgen run`
                         #   makes with uv (projects), the font guard,
                         #   the lazy kernel (lazy_kernel: `import build123d` binds, the
                         #   kernel loads on first use; cadgen-lazy-kernel.pth, at the root
                         #   of site-packages, installs it at interpreter start),
                         #   the engine observer and the telemetry sender, the install
                         #   channel, the self-update (auto_update), atomic replace,
                         #   file locks (the state folder's one
                         #   lock: `file_lock.state`), the CLI derivation
  _runtime/              # BUILT: the CAD Viewer client and the CAD app page -- produced
                         #   when the wheel is packaged, never committed, never edited
```

Start a standalone server explicitly, or let the MCP bootstrap or `cadgen run` start it:

```bash
uvx --no-config --managed-python --python 3.13 --from cadgen==0.8.3 cadgen server
```

`cadgen run model.py` builds a model: the engine's installation runs it in the project's
environment, which holds the project's dependencies (its `requirements.txt`, the project
itself, the script's inline `# /// script` metadata) and the engine's own cadgen, created with
uv once and kept under the cache folder's `envs/` -- so the script, its worker and the engine
run one cadgen by construction, and a dependency change or an engine upgrade makes a new
environment. Its Python is the project's `.python-version` or `requires-python`, else the
engine's; `--refresh` makes the environment again, `--show-env` prints its folder (the
engine's **Running a model**). `python model.py` from an environment where cadgen was
installed by hand attaches too: client, engine and worker meet by protocol, document format
and native line, never by release (law 20), and an older project cadgen is served and nudged
once to update. Either way the builds run in warm workers of the project's interpreter, on the
selected engine; set `CADGEN_PORT` in both environments when using another port.

Commands: `cadgen run` builds a model script in its project's environment, starting the
selected engine when none runs; `cadgen export`, `snapshot`, `serve`, `inspect`, `status`,
`stop`, `delete` and `server` are the engine's verbs (`snapshot` draws every file the viewer
opens, a DXF or a robot among them); `cadgen urdf|sdf|srdf validate` validates robot descriptions;
`cadgen viewer` launches the selected engine's page; `cadgen mcp` is the stdio peer
an agent host starts; and `cadgen telemetry` records the person's answer.
`cadgen doctor` checks setup, registers the installation (the release the device runs from then
on, when it is one past the current one) and writes the global
`cadgen` command without starting an engine. Its `--prune` removes records and
caches nothing needs, as reported by `_internal/leftovers.py`. `cadgen setup`
(also `cadgen update`), which the install command `curl -fsSL https://texttocad.dev/install.sh | sh`
runs, sets up or updates text-to-cad in every agent app it finds, each by its own
command (Claude Desktop's config merged where it has no CAD server, a `.bak` beside it; one it has
is kept, whatever release it names), gives the agents without a
plugin the skills alone through the Skills CLI (`npx skills add`), removes second copies,
retires an older engine on the selected port once it is idle, then does what `doctor`
does, makes its release the one the device runs (`<state>/current`, when it is past the current
one), and keeps a receipt that `cadgen uninstall` takes back (with `--purge`, cadgen's
state and cache folders too); `--dry-run` prints either one's plan alone. An app's server line
is written once and is a floor: the server it names is a proxy that starts or attaches to the
current release's engine (`_internal/installations.py`, `engine/client.py`), so the next session
an app starts meets it, with nothing to restart. From then on the
engine on that port runs a newer release's `cadgen setup` itself, within the hour of the
release (`_internal/auto_update.py`), or at once when the update card asks; `CADGEN_UPDATE_CHECK=0`
turns that and the version check off.
For a version or connection conflict, `cadgen doctor --json` reports the current CLI,
registered installations, known engines and discoverable agent configuration, and with
`--python <python>` an environment where cadgen was installed by hand (one `cadgen run` makes
holds the engine's own cadgen). Omit `--json` to read the report as text.
These diagnostic modes inspect without registering an installation, changing
configuration, or starting or stopping an engine. Discovery covers supported local
provider configuration and registered or cached plugins; it does not scan every
virtual environment or establish what a running agent host has loaded. The report
states these limits. Remedies are suggestions to apply explicitly, including
updating a project's cadgen or the engine, or configuring distinct ports. JSON includes a schema
version, findings and remedies. Diagnostic exit codes are `0` for no required
failures (warnings may remain, a release apart among them), `3` for an incompatible
project or engine (another protocol, a document format it cannot read, or another OCP
line, the finding naming which), and `5` for an unavailable or invalid required
interpreter, skill, engine or port; invalid arguments return `2`.
The registered proxy accepts `~/.local/bin/cadgen +<version> <verb>` to select a
CLI installation; use `cadgen.cmd` on Windows, or its `CADGEN_LAUNCHER_DIR` path.
Use the explicit proxy path when a virtual environment with a cadgen of its own is active, so
that its ordinary `cadgen` console script cannot shadow the dispatcher. A model script runs with
`cadgen run`; in an environment where cadgen was installed by hand, with that environment's
actual `python`, never the proxy.

Coming from 0.7: cadgen 0.7.x kept a cache store, which can hold gigabytes, at
`~/.cache/cadgen` (macOS and Linux; `$XDG_CACHE_HOME/cadgen` when that is set),
`%LOCALAPPDATA%\cadgen` (Windows) or the folder `CADGEN_CACHE_DIR` named: its `objects/` and
`index/`. 0.8 keeps the shared document cache in that folder's `documents/`
and the engine's bytecode under `pycache/`, and neither reads nor writes 0.7's store beside it, nor the state files only 0.7 writes
(its sidebar views, its snapshot browser's lock, its viewer's log, its Recents log). Whether a 0.7
is still installed cannot be told from here (0.7 never registered itself; it lives in uv's
environments and the agent apps' plugin configs), so they retire themselves: `cadgen doctor` says
they are there, with their size and when they were last written, and `cadgen doctor --prune`
removes them once nothing has written them for seven days -- a 0.7 in use writes its store at
every build -- or at once with `--all-versions`, once no 0.7 is left in any agent app. 0.8 loses
nothing by it. Settings, the telemetry answer and recents live in the state directory, and stay.

The viewer exposes `POST /__cad/clipboard` for explicit viewport PNG copies. It
uses the same host and custom-header POST gates as other mutation routes, limits
images to 20 MiB, and delegates native delivery to `viewer/clipboard.py`. It never
reads the clipboard. Unsupported desktop clipboard environments return an error.
