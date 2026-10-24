# cadgen.engine

A model is a parameterless function that returns a build123d shape, declared
with `@model` (a document with no file) or one or more file decorators (a document with those
files) -- never both: `@model` stacked with a file decorator is refused. The engine runs it in a warm
worker, holds the result as an XCAF document in memory (`@xbf` explicitly writes its BinXCAF file),
and writes the derived files the model declares, each a translation of that document. A drawing is
a model like any other: its body returns 2D geometry (a sketch, a face, wires or edges), and `@dxf`
declares its DXF.

```python
from cadgen.engine import xbf, step
import build123d as bd

@xbf("XBF/arm.xbf")                      # XBF/arm.xbf beside the script; @xbf(out="path.xbf") to choose
@step("arm.step")         # also @glb, @stl, @threemf, @dxf; stacked or alone; out= is every decorator's only argument
def arm():
    return bd.Box(10, 20, 30)


if __name__ == "__main__":
    arm()
```

A call returns the document's handle, never a bare shape: `arm()` builds it through the engine and
returns a `Document` (`api.Document`) -- `.id`, `.url` (its page), `.name`, `.shape` (the built
result, transferred into the caller and the kernel loaded on first access, never before),
`.export(*paths)` and `.snapshot(out, **picture_options)`, which are `export(handle, ...)` and
`snapshot(handle, ...)`. The decorated function stays the function and its id (`arm.id`);
`arm.build(verify=, profile=)` is the debug seam, a `Report`. Inside another model's body a call
builds the child document as before and returns its handle too, whose `.shape` is the result in
that process: a body composes `peg().shape`, and a child called for its files alone stays a bare
`peg()`.

```python
@model
def peg():
    return bd.Cylinder(2, 10)

@xbf("XBF/base.xbf")
def base():
    return bd.Compound(children=[bd.Box(20, 20, 3), peg().shape.moved(bd.Pos(5, 0, 6))])

if __name__ == "__main__":
    handle = base()               # built; the id and the page are printed
    handle.export("base.step")    # export(handle, "base.step")
    handle.shape.volume           # the shape, transferred now
```

A program that holds a shape -- a script with no model, a REPL, a notebook -- hands it over with
`model(shape, name="plate")` (**Shapes handed over**): a document made of it, held and served by
the engine, exportable, and returned as a handle whose `.shape` is the shape passed.

`import build123d as bd` binds at once: cadgen makes the import of `build123d` and `OCP` lazy
(its `cadgen-lazy-kernel.pth`, run at interpreter start in the environment cadgen is installed
in, and `import cadgen` in a checkout), so the kernel loads on the first attribute anything
reads from it -- in the worker, for a build the daemon runs, and never in a run of the script
the engine finds current. `from build123d import Box` reads the name, and loads the kernel at
that line.

A function worth skipping on a later build is marked `@memo` (**Memo functions**): an
assembly's parts, a stage of a long derivation. It writes no file; the model that calls
it does.

```python
from cadgen.engine import memo, xbf

@memo
def wheel(radius, spokes=5):     # replayed, not run, while what it is made of is unchanged
    ...

@xbf("XBF/bike.xbf")
def bike():
    return bd.Compound(children=[wheel(300), wheel(300).moved(bd.Pos(1200, 0, 0))], label="bike")
```

A part's material is set on the shape, as its colour is: `part.material =
materials.aluminium_6061` (or `materials("6061")`: a catalogue of common engineering
materials, **Materials**), or a `Material(...)` constant of the project's own for any other.
`paint(part, faces, material)` gives faces one. On an assembly, a material is every part's
below it that has none: a whole-model default. Set materials on finished parts, after the
last operation: an edit of one is then no kernel call. Two limits of OCCT's STEP writer show in a STEP export: it names the density
unit gram³·cm² (the exponents wrong, the number right: the reader gives the density back as
written), and it writes materials sharing a name as one entity, so a STEP gives every such
material the first one's description.

An assembly's mechanism is build123d's joints: `RevoluteJoint`,
`LinearJoint`, `CylindricalJoint`, `BallJoint` and `RigidJoint` on its parts, placed with
`connect_to(..., angle=, position=, angles=)`. The values they are connected at are the
as-built state, the pose every file of the model shows. The functions that say more are named
after the AP242 entities they write, and are `cadgen.ap242`'s (the root holds none of them):
`mechanism_state(assembly, name, **values)` names another
state (`mechanism_state_representation`), by joint label, and never moves the build;
`gear_pair`, `rack_and_pinion_pair` and `screw_pair(assembly, name, **joints)` constrain joints to
move together by ratio (**Kinematics**); `configuration_sequence(assembly, name, ...)` names a
sequence of states over time (`interpolated_configuration_sequence`, **Configuration
sequences**), and `cadgen.gltf`'s `animation(assembly, name, duration=)` a GLB's own animation
(**Animations**). Connect parts before putting them in the compound that holds
them; where `connect_to` cannot place them (a nested assembly), give the two joints one label
where the parts stand.

```python
from cadgen.ap242 import mechanism_state
from cadgen.engine import xbf

@xbf("XBF/hinge.xbf")
def hinge():
    base, arm = bd.Box(100, 60, 20), bd.Box(120, 20, 10, align=(bd.Align.MIN, bd.Align.CENTER, bd.Align.MIN))
    base.label, arm.label = "base", "arm"
    bd.RevoluteJoint("elbow", base, axis=bd.Axis((40, 0, 20), (0, 1, 0)), angular_range=(-10, 120))
    bd.RigidJoint("mount", arm)
    base.joints["elbow"].connect_to(arm.joints["mount"], angle=30)   # as built: elbow 30
    return mechanism_state(bd.Compound(children=[base, arm], label="hinge"), "raised", elbow=90)
```

A posed or partial file is a function, never an option (law 22): `export` writes the document
as its code built it. `posed(assembly, state)` (`cadgen.ap242`, beside `mechanism_state`) is a
copy of the assembly, sharing its geometry, with every part where a mechanism state, or
`{joint label or coupling name: value}`, puts it -- each link moved by its placement at those
values over its placement as built, the forward kinematics the viewer and the snapshot pose
by (`mechanism.link_worlds`). The copy keeps the joints, couplings, states and sequences, the
asked values its as-built state, so its viewer Position and motions still work; an unknown
state, joint or coupling, or a value out of range, is refused by name as `--pose` refuses it.
A folded arm's STEP is a model: `@step(out="arm_folded.step") def arm_folded(): return
posed(arm().shape, "folded")`.

## Laws

1. **An xbf carries its build closure as pointers and digests** -- script and
   function, modules, data inputs, versions and the key; never source, never lines on
   elements, never input contents, and nothing of a version control's (the engine calls
   no git); names remain the per-element tie to code (**Build closure**).
2. **Only requested files to disk.** The engine writes the files a model declares -- the xbf
   and the exports its decorators name, nothing beside them -- and the operating
   system's coordination for its warm process: a socket and a lock in
   a folder only the user can make (`daemon.default_state_dir`): `cadgen-engine` in
   `$XDG_RUNTIME_DIR`, else in a `$TMPDIR` that is the user's own (macOS's), else
   `/tmp/cadgen-<uid>`; on Windows in the temporary folder (a socket path past the Unix limit
   lives in the user's own `/tmp/cadgen-<uid>` instead) -- and, in the user's state folder its host names,
   the registry: one record per document it has built, been handed or a page opened, pointing at
   its script or file (**Document lifetime**); never geometry and never source. In the cache folder its host names (the platform's: `~/.cache/cadgen`) it
   keeps, under `documents/` alone, each model document's bytes as it last built them (**The
   cache**): its own file, never a declared or exported xbf, regenerable and wiped at no loss,
   so a restart opens every project at once; the code stays the only source of truth. It
   writes no sidecar, record of a build beside a model, index, memo, mesh or parsed document,
   and no derived file beside an input (a STEP converted to an xbf is an export the author asks
   for). A model whose xbf holds the closure the model has now is not run (**Build closure**). An explicit viewer export names one output in managed
   temporary storage for delivery to the browser; it never saves source, a registry,
   or an intermediate XBF. See **Viewer exports** below.
3. **Standalone.** `cadgen.engine` imports nothing of cadgen outside itself:
   OCP, build123d (and ezdxf, build123d's own DXF library, which the DXF export writes
   and checks a drawing with), numpy, Pillow (the renderer's rasteriser) and the standard
   library only. A test holds it.
4. **XCAF is the document; files are explicit.** A live model holds an XCAF document;
   `@xbf` or `--xbf` serializes it as native BinXCAF. It holds: units in
   millimetres, prototypes and instances with placements, a name on every part
   and instance, colours per part and per painted face, materials per part and
   per face given one (`XCAFDoc_Material`: name, description, density, and one
   `TDataStd_NamedData` beside it for the rest; `XCAFDoc_VisMaterial`: PBR), element names
   on face, edge and vertex sub-shape
   labels, and an assembly's mechanism (links, pairs, ground, configurations: see
   Kinematics); its main label names what wrote it (`cadgen.engine xbf/7 (cadgen
   <release>)`, `document.Loaded.writer`) and holds the model's build records: its build
   closure (**Build closure**) and its compiled animations (**Animations**). No code location
   is on an element. STEP, GLB, STL, 3MF and,
   of a planar document, DXF are translations of it (**Exports**).
   `cadgen export` writes any of them from the xbf alone.
5. **The memo is the only build cache, and it lives in the worker.** Every kernel
   operation a model runs is keyed by its inputs. A hit hands back the objects
   the first run made, and a miss makes everything downstream of it miss. So an
   edit costs what it changed, and an element keeps the name its feature history
   gave it across edits. Tessellations live in the serving process's memory,
   keyed by a part's geometry, under its one memory budget (**Document lifetime**). Across a restart, a model's
   build is cold but for its own xbf, taken whole or not at all (**Build closure**); what a restart
   shows without a build is the document cache (law 2), the last built state.
6. **One document per model, with one id.** Every called model makes one document, and every id
   is one formula, `uuid5(NAMESPACE, canonical(scope) + "::" + name)` (`ids.derived_id`): a
   model's scope is its script and its name its function's (`ids.model_id`), an opened file's its
   path with no name (`ids.file_id`, inside the engine only: its public name stays its path), a
   shape handed over its calling script, or the working folder where there is none, and the name
   it is given. The same in every process, worked out without asking the engine. `key="..."` on
   `@model`, a file decorator or `model(shape, ...)` replaces it with `uuid5(NAMESPACE, "key::" +
   key)` (`ids.key_id`): global and readable, and refused, naming the other, when another
   declaration claims the key in this process or in the engine's records. A key or a shape's name
   holding `::`, the formula's separator, is refused at declaration. The store rule: a
   function in a file is a `pointer` (the registry points at its script), `store="memory"` a
   throwaway (nothing is recorded), and a shape is handed over (`shape`: its bytes held and cached,
   nothing to run again). A function in no file is refused: hand its shape over. File
   decorators imply a model and write only their named outputs. No xbf, mesh, memo,
   provenance or derived file is written for a document beyond what it declares. A document
   lives until the engine exits or memory evicts it; its worker retiring does not end it,
   except a `memory` document's. A document that is not held names the command that builds it
   again; the engine never runs it (**Document lifetime**).
7. **Provenance is served live, never written.** What made an element -- the
   feature, its operation, the function, file and line of its call -- lives in
   the trace of the worker that built the document, and is asked of it while it
   lives (`made_by` on the facts endpoints, `cadgen inspect`). A document
   opened with no such worker has none to give, and says so (`made_by: null`).
8. **Poses and motion definitions, never frames.** The document carries
   kinematics -- the mechanism, its mechanism states (each a pose: where its parts
   stand) and its configuration sequences (each a definition: waypoints and an
   ease) -- and the document holds poses and motion definitions, never baked
   frames or clips. A GLB export is the one place a sequence is baked, into a clip
   of the GLB; the engine plays nothing.
9. **Names are the durable tie to code.** An element's name is spelled from the
   function that made its feature and the author's name for that feature (the
   target its result is assigned to, or a label), never from a line or a file:
   moving code renames nothing, and the file holds no line to go stale. A line
   is what the worker serves, now.
10. **A file decorator requires an explicit output path.** `out` is its only
   argument; omitted paths and `None` are refused. Whenever the model it decorates
   runs in a build -- the build's target, or a child another model's body calls --
   that file is written, once per build, from the model's own document: a declared
   file is what the code that last ran makes, whichever model ran it (**Exports**); a
   GLB's animations are baked from the code when that GLB is written (**Animations**).
   A model with no file decorator writes nothing.
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
   time (`test_kinematics`' conformance test walks the subtree and holds it).

14. **Connected means warm.** A worker is not retired for idleness while any served
    document it built has a version wait outstanding or completed a sync within `serve.LIVE`
    seconds. Heartbeats use the document's id (`ids`): a file's `file_id`, a model's
    `model_id` or `key_id`; they never turn a model into a file path. The worker-count
    cap never retires a worker whose document a page watches; it is exceeded instead. The memory
    cap may retire it. Memory may evict a worker's document only when nothing watches it
    (**Document lifetime**). Closing a page never stops the engine or its worker; once its last
    sync expires, ordinary idle retirement applies.

15. **One HTTP owner per installation.** The daemon serves its one page and document
    reads on one authenticated listener. Both `serve` and `viewer` start or reuse it;
    neither command has a standalone serving mode. A launcher exits after handing its client the
    engine URL; closing a client never stops the engine. Tabs select documents at `/<uuid>`: a
    model's id, or a file's id after a launcher registers it; Python scripts are never documents.
    The home shows the folder of the most recent launch, which each launch replaces; requests read
    files by absolute path. No page replaces or re-executes the engine; stopping it is an explicit
    engine operation.
16. **No kernel in request threads.** Reading XBF/STEP, meshing, topology facts and poses
    run in child processes. The daemon holds structures and buffers, never live kernel objects.

17. **MCP state belongs to the engine.** Each HTTP MCP session owns its tools, views
    and UI resource. Stdio peers hold transport metadata only; deleting a session
    never stops the engine. Sidebar sharing is in memory and never writes a registry.
18. **Host differences stay at the boundary.** The stdio peer translates host capabilities;
    the app page keeps version reads short enough for the host's tool-call slots. Engine
    request handlers act on declared capabilities, never on a host's identity.

21. **Python functions own operations; decorators and CLIs expose them.** Every
    successful server-backed build reports its id and localhost viewer URL,
    including a build with file outputs. A cold `daemon=False` build has no served URL.
22. **A verb's option is about the picture or the path, never the model.** `export`
    takes a document and destinations: what the file holds, its parts and their
    placement, colours and motion, is what the code built, so no option selects a part
    or a state. `snapshot`'s options describe the picture (the camera, the display, the
    size, the state the mechanism is drawn in); `serve`'s and `status`'s the process.
    Anything that changes what a document is, is a function in the model's code: a
    part's own model, or a model returning the assembly in a state (`posed`).

## Architecture

One server per installation owns the worker pool, served documents and HTTP listener.
`cadgen serve` and `cadgen viewer` launch or reuse that server and return its URL.
The background process is implemented in `daemon.py`; warm workers remain separate.
Every successful build registers its document by id and gives it a URL, `/<id>`; registration does not mesh it.
A model's worker is a separate process, holding its memo and live kernel objects.
The distribution injects its HTTP application through `daemon.HTTP_FACTORY`; this
standalone engine imports no application module. The application serves the built
viewer's one page on that listener, every document at `/<id>`; an old page session's link
(`/s/...`) and a document named by query (`/?doc=`, `/?file=`) are answered with the home. Document routes run in
process, with no network relay. Kernel reads, topology, poses and meshes run in
reader/mesh subprocesses; even an inline-mesh request stays outside the daemon.

Every document has one id, a lower-case UUID string ([ids.py](ids.py)), by one formula
(`derived_id`: uuid5 of a scope's canonical path, `::` and a name): a model's scope is its script
and its name its function's (`model_id`), worked out in the script's own process (`Model.id`) as in
the engine; a file's is its canonical path and no name (`file_id`), inside the engine only; a shape
handed over is its calling script's (or the working folder's) and its name. A `key=` replaces the
derived id with `key_id`, uuid5 of `key::` and the key. The canonical path (`ids.canonical`) is `realpath` and, on
macOS, the name as the file system spells it, so a symlink and a case variant of one file are one
document; the viewer's document reads (by id) and its Recents key by the same function, so it
serves one document and keeps one Recents entry for it too, while a page names a file by the path
it was given. The server keys everything by the id: its served documents and
the models registered to be served, their watchers and syncs, their builds, the documents a build
holds; `GET /api/doc/<id>` takes it, and a document served at a pose is `<id>~<digest>`. The
daemon keys by it the worker that built each document (`builders`, from which `connected` asks
the server's watched ids) and the live models' book (`models.py`); a worker keys by it what its
builds named (`build._BUILT`, which `made_by` answers from) and the served documents it patches.
The worker pool alone is keyed otherwise: by the canonical path of the script a worker runs, a
process's key, not a document's.

The daemon maps each built document to its worker. HTTP watcher accounting has its
own lock, independent of document reads and pool admission. Outstanding version
waits and recent syncs preserve that worker from idle retirement and keep the daemon
alive. To admit a new script at the worker-count cap, the least recently used
unwatched idle worker is retired. When every idle worker is watched, the new worker
starts past the cap instead: a build never waits on an open page, and never costs one
its warm worker. The per-worker memory cap remains enforced after each build, watched
or not. A retired worker's documents stay served: the daemon takes them from it first, and
holds them under one memory budget that never evicts a watched one (**Document lifetime**).

The installation's private socket supplies its HTTP token. Page URLs exchange it
for a same-site cookie; programmatic clients use Bearer authentication. All routes
retain the application's Host and cross-site mutation checks. Explicit host/port
requests must match an existing listener. A second installed version has a different
installation identity and therefore a different engine.

The injected application also serves `/mcp`, the Streamable HTTP MCP transport
(2025-11-25 and the previously supported protocol revisions). Initialization returns
an opaque `Mcp-Session-Id`. Every subsequent request identifies that session;
DELETE releases it, and a missing/expired session must initialize again (the stdio shim
does so for its host). JSON replies
are used; GET returns 405 because this server has no unsolicited SSE events.
Each session owns its tool server, view registry and immutable UI resource. `cad_http`
dispatches into the same application in process. It is listed for every host, even
without an open page. Calls without the session's app capability can only GET
`/__cad/analytics` or POST exactly `{"share":false}` there; no other route or
telemetry opt-in is authorized. The tool's base64 body and HTTP reply are the
same for both callers, with readable JSON text added for agents. Launch results
carry the app capability in UI-only `_meta["dev.texttocad/httpToken"]`, never
content, structured content or the resource. The page sends it in `x-cadgen-app`;
the server checks it before dispatch and strips it. Authorization precedes the
range cache. Consent attribution is per request, so a simultaneous app opt-in
and agent opt-out cannot exchange authority. Opt-out removes the installation ID
and schedules deletion of previously sent data; `saved:false` reports a failed
settings write. This is an MCP host/model boundary, not a sandbox against the
local authenticated host, which already has the installation's file authority.
Page protocol 9 requires the capability, on `cad_http` and on the page's own `cad_sync` and
`cad_capture_reply`; older pages must reopen, with no alias
for the removed telemetry tool. Sidebar views alone are shared through
an in-memory registry; thread views remain session-local. The host's stdio process
proxies JSON-RPC and owns no page, tool implementation, catalog or view state.
Active HTTP calls keep the daemon alive; quiet MCP sessions expire after an hour.
A card's `cad_sync` renews its served document's warm-worker lease.

The viewer launcher owns no server, reload watcher or process-reuse probe. It
asks the existing engine for its page: the launch's folder becomes the one the home shows, and
each file it names is registered by its id (the id of its canonical path) and printed as its
page, `/<id>`. Development client reload remains a browser concern; Python changes take effect
when that installation's engine is explicitly restarted. What the page knows by id is memory
only, and a file's id is derived again from its path after a restart.


## Layout

| Module | What it is |
| --- | --- |
| `model.py` | the decorators (`out`, `store=`, `key=`), `@model` or file decorators and never both; `Model` (the function, `.id`, `.build` the debug seam); its id (`ids.model_id` of its script and function, or `ids.key_id` of its key; `claim`: one key per declaration), and a build's report of every model a program's call builds, wherever the model is defined; a call returning the document's handle; a child model called in a body is a sub-assembly built in the same run, its call its handle with the result in the worker, and the models a target's run ran (`BuildContext.children`); `model(shape, name=)` handing a shape over; `@memo` and its calls; a script's module and package (`module_of`); `paint`, `mechanism_state`, `configuration_sequence`; `read_step`, `read_xbf` |
| `api.py` | the verbs as functions, through the daemon: `export`, `snapshot`, `inspect` (the root's `cadgen.export`, ...), and `serve`, `status`, `stop`, `server`, which only the CLI calls (process control is the CLI's alone), and `build_script`, a script's models built by `Model.build()`; `Document`, the handle a model call returns (`.shape` transferred by id on first access: `result`); `hand_over`, a shape made a document in the caller and handed to the daemon; `observers`, told after each build, export and snapshot what it did, as plain facts (kinds, counts, times, the worker's part, an error's type and frames): the engine counts nothing, and cadgen's telemetry is an observer cadgen appends |
| `materials.py` | `Material`, a physical material and its look (OpenPBR's glTF subset), and the catalogue of common ones: the module, called |
| `colors.py` | a colour as the author gives it (sRGB hex, 0-255 integers, a build123d `Color`) held linear, and the way back (**Materials**) |
| `mechanism.py` | kinematics: build123d's joints harvested into AP242's links and pairs, couplings (`gear_pair`, `rack_and_pinion_pair`, `screw_pair`), mechanism states (`mechanism_state`), the document's subtree, the structure's `kinematics`, poses (forward kinematics from the ground; `posed`, an assembly copied at a state), and configuration sequences (`configuration_sequence`, a function's samples, `Timeline`: a sequence's pair values over time) |
| `build.py` | one build: load the script afresh (as Python imports it: a package's module by its dotted name), one memo run, document, element names, files: every model's that ran |
| `previous.py` | the model's build closure on its xbf's main label (`manifest`), the release from the version beside the code, and the closure made again before the body runs (`again`) |
| `document.py` | result to XCAF (prototypes, instances, names, colours, materials, element names; a mesh face refused, `mesh_faces`), a warm build's patch of the document it kept, atomic BinXCAF save, read-back of an xbf or a foreign STEP |
| `reader.py` | what a model imports: an XCAF document described as data and assembled into a build123d tree (`read_step`, `read_xbf`); the reader process a build's STEP files are parsed in; a mesh file as data (`read_mesh`, `Mesh`); a read of a file the build writes refused (`refuse_written`) |
| `refs.py` | references to geometry: the ref grammar, occurrence paths, resolution by name in the latest build, for `inspect` and the viewer (**References**) |
| `export/` | `translate` and the kind registry (`__init__`); STEP through the XCAF writer (`step`); placements and meshes from the one mesh cache (`mesh`); a mesh file read as a document of triangles, no kernel (`mesh_file`); GLB, 3MF, binary STL (`glb`, `threemf`, `stl`); a planar document's drawing through build123d's DXF exporter, with the drawing checks (`dxf`); a motion baked into a glTF clip (`motion`); a view made a document again, for a STEP of a document held without its XCAF document and an xbf written from a STEP (`tree`) |
| `mesh.py`, `mesh_format.py` | per-part tessellation at FreeCAD's default tolerance, element facts; the part buffer, its wire format and edge classes (`mesh_format`, kernel-free) |
| `serve.py`, `page/` | HTTP: structure JSON and one binary buffer per part; a STEP read in a reader process, held by its bytes; a minimal three.js page |
| `access.py` | which pages may read a served document from another origin: loopback ones |
| `snapshot.py` | `cadgen snapshot`: one dispatcher by suffix -- a document, a mesh file, a robot or a DXF drawn by OCCT (`render/`) into a PNG; a script's model drawn from its worker's memory |
| `formats/` | the files the stills draw that are not documents, each read into a structure and part buffers: STL (numpy), 3MF (zip + XML), GLB (OCCT's glTF reader, textures and all; and numpy's, for a conversion: `gltf`), URDF/SDF/SRDF (XML, the viewer's forward kinematics), DXF (group codes, flattened as the viewer's pane draws it) |
| `render/` | the stills drawn by OCCT from the engine's meshes: a document held and drawn, and the daemon's render process per served document and per file (`service.py`); the scene (`occt.py`); a DXF drawn in the 2D look (`drawing.py`); the viewer's Explode, ported (`explode.py`); a part's buffer as OCCT shapes (`shapes.py`); the headless OpenGL context per platform (`context.py`) |
| `daemon.py`, `worker.py`, `client.py` | one daemon per installation, one warm worker per model script, at most one per core alive (`Pool`), connect-or-start; a worker's memory cap |
| `progress.py` | where a build is: the engine's stages heard where they begin, each body a model's body runs by name, the frames, and the terminal's bar |
| `atomic_replace.py` | the one rename every written file is moved into place with: cadgen's bounded Windows retry, kept in the engine |
| `cache.py` | the document cache: each model document's bytes in the cache folder (`documents/<id>/document.xbf`), saved when idle, at its drain and at shutdown, once per revision; the index a restart reads, staleness (`changes`) and the LRU bound (`Cache`) |
| `registry.py` | the registry of documents in the user's state folder (`Registry`: `get`, `put`, `list`, `delete`), and the one owner of every write under that folder (`Folder`); where the folder is, the distribution's (`FACTORY`) |
| `cli.py` | the verbs as commands: `cadgen export`, `snapshot`, `serve`, `inspect`, `status`, `stop`, `server` (`parser_for`, `run`; also `python -m cadgen.engine VERB`) |
| `kernel/` | the memo (`memo.py`), maker history (`history.py`), element naming (`trace.py`), deterministic kernel settings (`determinism.py`) |

## CLI

```
python SCRIPT.py                             the models the script explicitly calls
cadgen export SRC DST [DST ...] [--json]
                                             SRC an .xbf, a .step, a document id, or a mesh
                                             (.glb, .stl, .3mf: to the other two mesh kinds)
cadgen snapshot SRC OUT.png [--display MODE|exploded=A|JSON] [--grid] [--camera C|authored] [--preview]
                [--pose NAME|JSON] [--annotation FILE] [--measurements FILE]
                [--width W --height H | --size-profile P] [--json]
cadgen snapshot --job PACKET [SRC] [the same flags, each over every job]
                                             every picture a Quick Edit packet (or a job file) names
cadgen serve DOC [--port N] [--three DIR]
cadgen inspect DOC [REF]                       the build closure; with REF (**References**): an element's facts and
                                             what made it, or a part's or an assembly's volume and mass
cadgen status [--json] | stop [--json] | server
```

`python -m cadgen.engine VERB ...` takes the same verbs, the engine's own entry.

Every `SRC` and `DOC` is an on-disk CAD file's path or a document's id (`ids`): a model's id is
what `python SCRIPT.py` prints for it (`id:`, beside its page, `view: <engine>/<id>`). A document
id is read as the engine holds it, never built: one it does not hold is refused with the command
that builds it again, `python <the program that built it>`. A script is never a source: `x.py`
and `x.py::fn` are refused as any other file that is no document is.

Every build and every verb goes through the engine: no command runs one in its own process.
`daemon=False` on the Python functions (`Model.build`, `export`, `snapshot`) is a seam for tests
and debugging only: it runs in this process, cold, and no document is served: no page, and
nothing for `inspect` to read by its id.

A verb's `--json` (`export`, `snapshot`, `status`, `stop`) prints its answer as one JSON object
on stdout, and a failure as `{"ok": false, "error": ...}` there too, exit status 1, so a caller
reading stdout always finds an answer (`cli.answered`); without `--json` a failure is its words
on stderr, exit 2 for a request refused by name before anything ran and 1 for one that failed.
A refusal keeps its type across the daemon: the worker answers its kind beside its words
(`worker.refusal`) and the caller raises it as that type (`api._failed`), so a pose a document
lacks is refused the same, exit 2, whether a worker or the caller's own process refused it.

`python SCRIPT.py` executes normal Python. Decoration only registers a model;
imports and definitions build nothing. A call such as `arm()` asks the daemon to
build that model and the children its body calls, prints its report -- its `id:` and its
`view:` -- when the call is the program's (made in `__main__`, wherever the model is defined:
`python caller.py` calling `parts.cube()` reports cube), and returns the document's handle
(`api.Document`), whose `.shape` is transferred only when it is read. A failed build
raises; a successful call resumes the script. Put executable model calls under
`if __name__ == "__main__":` so other models can import their definitions.
`Model.build(verify=, profile=, daemon=)`, the debug seam, explicitly requests a build and returns its report.
No watcher selects, suppresses or introduces calls in a Python script.

A script is plain Python, loaded afresh by each build as Python imports it
(`build.load_script`), its folder first on the module search path as `python SCRIPT` has
it, so a module beside it imports by its own name. A script inside a package -- its folder,
and each above it up to the topmost, holding an `__init__.py` -- is that package's module by
its dotted name (`proj.parts.model`), imported as `python -m proj.parts.model` imports it:
its packages first, from their root, which the search path holds next. So its relative imports
(`from .lib import WIDTH`, `from ..common import dims`) and the package by its name
(`import proj.common.dims`) resolve, in a build, in the warm worker build after build, and
under `python -m`; and `python proj/parts/model.py` takes its package the moment the script
imports the engine (`model.as_package_module`), so a relative import written above that
import fails as Python's own does. A script in a folder with no `__init__.py` is the module
its stem names. An edit to any module the script imports is read on the next build, which
re-runs the bodies that reach it (**Body retention**). The script and every first-party module
it imports are compiled from their bytes on disk, never from a `__pycache__` `.pyc`, and a
build writes no bytecode: CPython takes a `.pyc` as current by the source's whole-second mtime
and its size, so a same-length edit inside the second another tool compiled the file would
otherwise run that tool's code.
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
previous files stay. Builds run in the daemon's warm workers, at most one per core alive
(**The engine server and its workers**). `CADGEN_ENGINE_DIR` moves its socket and lock; the client and the server resolve it alike (`daemon.state_dir`: a `..`, a symlink or a trailing slash names the same folder). On POSIX the folder must be the user's own and closed to writing by anyone else (`daemon.folder_refusal`): whoever owns or can write the folder could take the socket's place, so a client refuses to connect or start there and the daemon refuses to lock there, saying why.
`CADGEN_ENGINE_MEMORY_MB` sets the server's memory budget, and `CADGEN_ENGINE_CACHE_GB` the
document cache's size (`0`: no cache; `CADGEN_ENGINE_CACHE_IDLE`, its idle seconds, is the tests'
seam) (**Document lifetime**).
`CADGEN_ENGINE_MEMO=0` turns memo hits off. `CADGEN_VIEWER_WARM=0` keeps `cadgen viewer`
from warming the engine at its launch (**The viewer and the snapshot**). `CADGEN_ENGINE_MESH=processes|inline`
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
keeps. The read is held by the file's bytes, so the same bytes served again --
the file touched, copied, or put back -- are not parsed again while the daemon
lives, and a part's key is made from those bytes and its label, so its mesh is
not made again either. A STEP is read outside the server's lock (every other
document is served meanwhile), and one rewritten while it is served is read
again in the background: the page keeps the old version until the new one is
in. Its structure says how long the parse took and which process made it
(`read`: `{seconds, process}`).

## Profiling

Request function timings with `arm.build(profile=True)`. The script remains plain Python,
run as `python model.py`; it takes no engine flags, and no command profiles a build.

Profiling measures **actual execution**, preserving normal memo, body and XBF hits.
It does not force a rebuild: a replayed body has no function timings for its earlier
execution, and a kernel memo hit measures lookup/replay, not the skipped operation.
Read the existing `cache`, `memo` and `bodies` fields alongside the timings. `verify=True`
retains its usual verification behavior when combined with profiling; it is not a cold run.

The `profile` field in each top-level `Report.models` entry covers
one entire build request, including script loading, all requested and child models,
document processing and declared exports. For multiple targets those entries carry
the **same request-wide profile**, not separate per-model measurements to add together.
It runs in the worker (or the caller with `daemon=False`), excludes client/daemon startup
and queuing, and includes waits during that worker call. Work in other processes is
not function-profiled.

The JSON profile identifies `scope: "build_request"`, `mode: "actual_execution"`, the
process id, elapsed `seconds`, total `self_seconds`, and `function_count`. Its two
lists hold at most 20 rows each: `project_cumulative` (functions under the script's
folder, excluding installed dependencies) and
`top_self` (all functions by self time). A row names `file`, `line`, `function`, total
`calls`, `primitive_calls` (non-recursive calls), `self_seconds` and
`cumulative_seconds`. `profiling.describe` prints those tables; Python callers receive
these fields without printing or writing a profile file. No profile is saved or
reused by a later build. Failed model reports include the work observed before failure.

`cProfile` slows call-heavy Python code, so compare shares with care. It runs with
`builtins=False`: native OCCT time belongs to the Python function that called it,
which also avoids pybind11's unmatched profile events on Python 3.12 and later.

## The engine server and its workers

One engine server per installation (`daemon.py`: a daemon, which `cadgen server` runs in the
foreground), started on demand by the first command that needs
it and gone after an idle hour (`CADGEN_ENGINE_IDLE` seconds; a page waiting on a served
document keeps it). It holds a pool of warm workers, one per model script (and one for the documents no
worker built), each a process whose memo lives as long as
it does. Its rules are a standard pool's, and nothing else: no admission guess, no refusal;
the operating system does the rest. (What the daemon itself holds, the documents and their
tessellations, is under one memory budget: **Document lifetime**.)

- **A cap.** At most `CADGEN_ENGINE_WORKERS` workers are alive (default: the machine's
  cores). A build for a script whose worker is alive goes to it, waiting while it builds
  something else: one build at a time per worker, builds of different scripts at once.
- **First come, first served.** A build for a script with no worker starts one under the cap.
  At the cap, the least recently used idle worker no page watches is retired first (drained of
  its documents, then its stdin closed, so it exits), and its slot is the new one's. With every worker busy, the build waits
  for the first to come free, and every build that needs a slot after it waits behind it. A
  build that waits for its own script's busy worker takes no slot.
- **The cap never retires a watched worker.** When every idle worker has a document a page
  watches, the new worker starts past the cap. The memory cap may still retire a watched one.
- **Unwatched idle workers go.** A worker idle `CADGEN_ENGINE_WORKER_IDLE` seconds (default:
  the daemon's idle time, an hour) is retired only when none of its served documents has
  an outstanding version wait or a sync within `serve.LIVE` (90 seconds).
- **A memory cap.** A worker whose resident memory is over `CADGEN_ENGINE_WORKER_RSS_MB` after
  a build (default: a quarter of the machine's memory, at least 2 GiB; `0` for no cap) is
  retired: the report says so (`retired`), and once it has answered the daemon drains it and
  closes its stdin.
- **Collected when idle.** A worker builds with Python's cyclic collector off and collects once
  no request has come for half a second, so a script's calls one after another never wait on
  it. A worker over its memory cap collects before it measures again.
- **One load per run.** The calls one `python model.py` process makes of its script are served
  from one load of it while every file the load read stands as it was, the load made no kernel
  call and every call since took its models from their keys. Anything else loads the script
  again: another run, an edit, a body that ran.

The meshing pool starts with the first page or view, never with a build. A build serves its
document, so the daemon's server starts with the first `python model.py`; its meshing pool
waits. It starts on the first mesh, topology or pose a page asks, or on `Server.warm`: sent
by `cadgen viewer` at launch (`CADGEN_VIEWER_WARM=0` skips it), called when an app launches a
view and when a build's `view:` link lands. With no page, the daemon's only child is the
worker. Measured on a 24-part model (5 shapes) on a 10-core machine: 1 child and 0.5 GB with
no page, against 12 and 3.2 GB when the pool started with the server. The pool's start costs
a first page about 0.8 s, less the time the page takes to load after the warm.

A retired script's next build is a fresh worker's: a restart, which takes the xbf whole when
its closure is unchanged (**Build closure**), and else builds the model cold. A render
process (**The viewer and the snapshot**) is no worker and does not count toward the cap; it
is held to the same memory cap after each picture, and retired after the same idle time.

On Windows every process the engine starts -- each worker, STEP reader and render process --
has a console of its own and no window (`daemon.windowless`: `CREATE_NO_WINDOW`), and the daemon
a process group of its own too (`daemon.detached`), never no console at all: a console program
started with none gets a new console, with a window (#597). What they start in turn (the
meshing and reading pools) shares their windowless console.

A worker runs each request in that request's folder (its script's, or the caller's), so a model's
relative reads resolve as they would under `python SCRIPT`, and stands in the temporary folder
between requests: an idle worker holds no project folder (on Windows, one a process stands in
cannot be renamed or deleted). A meshing or reading pool's processes exit with the process that
started them, however it ends.

A worker is an interpreter; a run is the script in its caller's environment. A build goes to its
script's live worker whatever the caller's environment but for what shapes the interpreter's
import system (`daemon.RESTARTS`): `PYTHONPATH`, `PYTHONHOME`, `PYTHONSAFEPATH`,
`PYTHONNOUSERSITE`, `PYTHONUSERBASE` and `PYTHONPLATLIBDIR`. A build with another value of any of
them replaces the worker (retired `environment`), and its memo goes with it. Everything else the
run adopts (`worker.adopt`): before the body runs, the caller's environment replaces the worker's
`os.environ`, keeping only those variables and what the worker set for itself
(`CADGEN_ENGINE_WORKER`, `PYTHONDONTWRITEBYTECODE`). `PATH` and `VIRTUAL_ENV` are adopted, not
restarts: neither changes a running interpreter's `sys.path` (the worker is the daemon's
interpreter, started with `-P`, and `site` finds a virtual environment by the interpreter's own
`pyvenv.cfg`, never by `VIRTUAL_ENV`, which only activation scripts and installers read), and
the kernel reads neither; a model that starts a program finds it on its caller's `PATH`. An
agent's shell may give each turn its own `PATH` (Codex puts a temporary folder of its own on it,
`~/.codex/tmp/arg0/codex-arg0…`, new with each Codex process): one warm worker serves every turn.

`cadgen status` says what the server holds (`--json`: the same as data, `api.status()`):

```
engine server 98307, up 2h10m · workers 2/10 · idle timeout 1h · RSS cap 16.0 GB
  busy  tom.py         98310   12 builds   3.7 GB  building tom.py::tom · Building geometry · 3/7 stages · 41s
  idle  motorbike.py   98410    3 builds   0.6 GB  4m
  waiting  2 builds, first come first served
retired: finger_01.py (LRU) 3m ago · qdd_actuator.py (idle) 41m ago · tom.py (RSS) 2h ago
serving http://127.0.0.1:52811: 3 documents · 2.1 GB of 16.0 GB held
cache /Users/me/.cache/cadgen: 14 documents · 212.4 MB of 4.0 GB
documents:
  live      tom      8c1f5a0e-1d3b-5d6e-9a7f-2b4c6d8e0f12
  held      bracket  3e9b7c21-55aa-5f0e-8d11-6c2a9b4e7d30  memory and disk
  held      lid      0a6f2d94-7c1e-5b38-9e40-1d5c7a2b8f63  disk
  evicted   arm      71d0c4e8-9b2a-5c13-a6f4-0e8d2b5c9a17  run `python /work/assemble.py`
```

A worker's memory is as it measured it after its last build; a busy one's build is where its
last progress frame says (**Progress**); the time is how long it has been busy, or idle. A
retirement's reason is `LRU` (room at the cap), `idle`, `RSS` (over its memory cap),
`environment` (a build asked for the script with another `PYTHONPATH`, or another of the variables
that shape the interpreter's import system: its worker is replaced in its slot) or `exited` (it died). The `documents:` lines are each model
document, its state and, for one not held, the command that builds it again (**Document
lifetime**), and a held one where it is held: in memory, on disk (the cache), or both. The
`cache` line is the cache folder, the documents and bytes in it against its cap, the files evicted
for room and the last save that failed. `--json` lists the documents as `models`, the cache as
`cache`, and `serving.documents` the files served, each `held` or `evicted`, with the bytes it holds.

## Document lifetime

A document outlives the worker that built it, and lives until the engine exits or memory
evicts it ([models.py](models.py), [serve.py](serve.py)). Its state (`models.STATES`, what
`cadgen status` lists):

- `live`: a live worker holds it, with its memo and its trace.
- `held`: no worker holds it and the engine answers it all the same: in memory, on disk (**The
  cache**), or both (`Models.where`). In memory the daemon holds it whole: its served structure and shape bytes,
  and the document as the xbf bytes `@xbf` would write of it, mechanism and every assembly's
  placement included, and its build records with it -- the closure and the compiled animations
  (**Animations**) -- so a GLB of it is the build's own. A page and `cadgen inspect` read the
  served structure; an export or a
  snapshot by its id, and the viewer's export, go to the documents worker with the xbf bytes
  (`Daemon.document`), which reads them as it reads an xbf on disk, so no worker of its script
  starts. What made an element is null (law 7: provenance is the worker's). A document its worker
  exited before draining, but that a page had opened, is held for viewing only: an export of it
  names the command that builds it again.
- `building`, `failed`: its build now, or its last one.
- `evicted`: the daemon holds it no more -- memory evicted its bytes, or its worker crashed
  before it was drained.
- `expired`: a `store="memory"` document whose worker went.
- `detached`: not held, and the script it points at is gone (moved, deleted): listed in Recents,
  saying so, until the person removes it. Nothing removes it on its own. A shape handed over is
  never detached: nothing of it can go missing, and nothing builds it again.

**Store.** The rule: a function in a file is a `pointer`, the default -- the registry points at
its script; `store="memory"` is a throwaway -- `@model(store="memory")`, `@xbf("XBF/a.xbf",
store="memory")` (any file decorator) keeps a document in its worker's memory only: no record, it
is forgotten when the worker goes, and its id answers `expired` from then on; a shape is handed
over (`shape`, **Shapes handed over**). A function in no saved file (a notebook cell, a REPL,
`python -c`) is refused, with the words that hand its shape over instead (`model(shape,
name=...)`). Any other `store=` is refused, naming the two.

**Shapes handed over.** `model(shape, name="plate")` (`api.hand_over`) makes a document of any
build123d shape a program holds, from a script or a REPL. In the caller, the shape is made a
document as a build makes one (`document.collect`, `to_xcaf`) and serialised (`document.to_bytes`),
the declarations on it with it -- its joints, mechanism states, configuration sequences and
couplings -- and its GLB animations, passed as `animations=[...]` (the `animation()` builders, each
on the shape or a part of it), since there is no body to declare them in. The daemon (`{"op":
"shape"}`, `Models.hand_over`) reads the bytes through the documents worker, holds them as a drained
document is held (in memory, whole, and in the cache), registers its page, and records it with
`store: "shape"`, its scope as `home`, an empty `run` and `shown`: the words that a program the
engine did not run showed it, so no command builds it again. `name=` is required; its id is
`ids.derived_id` of the calling script (or the working folder, from a REPL) and the name, or
`ids.key_id` of its `key=`. The handle's `.shape` is the shape passed. Called inside a model's body
it is refused: a body returns its shape.

**The registry.** One record per document the engine built, and per CAD file a page opened,
`documents/<id>/document.json` in the user's state folder ([registry.py](registry.py); the
distribution names the folder, `cadgen.viewer.recents.state_dir`): it points; a document's bytes
are the cache's, in the cache folder (**The cache**).
A model's record holds its store, its script and function (`home`, `entry`), the command that
builds it again (`run`, `["python", program]`), its revision and when it was built, its closure
(modules and inputs, with their digests) and the versions it was built on; a file's its path,
its format, when it was opened and whether it is pinned; either's Recents picture (`preview`, UI
state: the PNG under `recents/thumbnails`), and a model's `cache` once the cache holds it (**The
cache**). Every path in it is relative to its one `root`, so a record moves by one field. It is written synchronously
as a build registers, and only when a field but `changed` differs: an unchanged build rewrites
nothing; each write is then told to `registry.OBSERVERS`, never waited on. It is read on demand,
never at start: an id the engine does not hold (after a restart) is answered from its record,
`evicted` with its command, or `detached`, and nothing runs. The registry is the ids' reverse map,
never their authority: every id is derived from a canonical path and a name, or from a key
(`ids`). A keyed record names the declaration that holds the key (`key`, `home`, `entry`): another
declaration's build or hand-over of that key is refused, naming it, while its script is there
(`Models.claimed`). A record's `revision` is its closure's key (the same code, the same revision, after a
restart too), or a token of the build's own where the closure has none. A served document's
generation (its structure's `version`, which a page waits on and the viewer's export compares)
is a token of its build's own: a rebuild is a new generation, and no generation is a counter that
a restart starts again. Recents is the registry's view (`cadgen.viewer.recents`): pinned
first, then the most recently opened or built.

**The cache.** For every `pointer` and `shape` model document -- never a file's, which is its own
file -- the engine keeps `documents/<id>/document.xbf` in the cache folder its host names
([cache.py](cache.py); `cadgen.viewer.recents.cache_dir`: `CADGEN_CACHE_DIR`, else
`$XDG_CACHE_HOME/cadgen` or `%LOCALAPPDATA%\cadgen`, else `~/.cache/cadgen`, the folder 0.7's store
used), written through a `registry.Folder` with `replace_atomic`, its record staying in the state
folder. The bytes are the hold's (`document.to_bytes`: the document, its closure record and its
compiled animations), the engine's own file always: a declared `@xbf` or an exported xbf is the
author's, never used as the cache nor pointed at by it. The folder is shared with any 0.7 install's
store: the engine reads, writes, sizes and evicts only under `documents/`, and lists, counts and
removes nothing else there. It is written never on the run path:

- after `CACHE_IDLE_SECONDS` (10 s) with no build and no read of the document: the daemon asks the
  worker that holds it to save it (`Worker.save`), which the worker does only when no request waits
  for it; a build arriving during the one serialisation waits for it. Measured on juno (29
  documents, 17.2 MB cached; the assembly's 9.6 MB): its serialisation and the pipe take 80-100 ms,
  the file's write 2-6 ms, and a warm build landing 50 ms into the save took 150-170 ms against
  120-140 ms alone. A document no worker holds is written from the bytes the daemon holds;
- at retirement, from the bytes the drain takes;
- at shutdown (`cadgen stop`, a terminate), best effort within 10 s (`cache.SHUTDOWN_SECONDS`), for
  the documents built or read in the last idle window.

Once per revision: the record gains `cache: {revision, bytes, written_at, read}`, and a document
whose revision is the cache's is never written again. A restart indexes the cache files (a listing
and a stat, nothing read); a document with one is `held` and answers every verb -- page, export,
snapshot, inspect, `cad_show` -- by reading its bytes through the documents worker, as a held
document does; no worker of its script starts and nothing runs. Loaded, it sits in the memory
budget's first tier. The record is authoritative: a cache file missing, or not the size its
record says, is not cached.

**Staleness.** `read` is what the build read, with digests: the script and each module its model
reached (each file's bytes, SHA-256, as the build answered) and each file its bodies read (the
closure's own digests). On a page's open, `cadgen inspect` and `cad_show` of a document no worker
holds, the engine compares them with the files now (`Models.stale`): unchanged, the page shows the
current model; changed, it shows the last built state, with a badge -- "The code changed since this
was built" and the rebuild command -- and `inspect` says the same words (`stale` in its answer, the
sentence on stderr). Nothing reruns. A font is named by a family, not checked.

**The bound.** Past `CADGEN_ENGINE_CACHE_GB` (default 4 GB; `0`: no cache at all), the least
recently used cache files go down to 80 % of it, as 0.7's store did, never one a live worker holds
or a page watches; the record stays, without `cache`. Removing a detached document from the home
removes its cache file with its record. A save that fails is logged and listed by `cadgen status`,
never raised: with the cache folder read-only the engine behaves as with no cache.

**Drain.** Before the pool stops a worker -- idle past `CADGEN_ENGINE_WORKER_IDLE`, the count cap's
least recently used, replaced for another environment, over its memory cap -- the daemon asks it
(the `result` request with `whole`, nothing meshed) for every `pointer` document of it the server
does not hold whole at its version (`Models.drain`), out of the pool, then closes its stdin. The
worker serializes the document in memory (`document.to_bytes`: `TDocStd_Application.SaveAs` to a
stream, the bytes `@xbf` writes), and the documents worker reads them in memory too
(`document.read_bytes`: the application's stream read, overwriting into a document of its own).
Nothing is written to disk. A worker over its
memory cap no longer exits on its own: it answers, is drained, and is stopped. A worker that died
drains nothing: its documents the server lacked are `evicted`.

**One budget.** Everything the daemon holds is counted against one budget: each served
document's structure (as JSON), its shape bytes, the bytes made from live shapes and a held
document's xbf bytes, its records among them (`Served.size`), and every tessellation (`MeshCache`, which has no cap of its
own in the daemon). Evicting a document drops all of it.
Bytes are counted as they are put, never sampled. Workers and render processes are processes of
their own, held to their own memory cap. The budget is `CADGEN_ENGINE_MEMORY_MB`, else a quarter
of the machine's physical memory (`serve.memory_budget`: macOS `hw.memsize`, Linux
`sysconf(SC_PHYS_PAGES)` or the cgroup's `memory.max` when that is less, Windows
`GlobalMemoryStatusEx`). Past it, what is held is evicted down to 80 % of it (`Server.trim`):
tessellations first, least recently used first (a tessellation is made again from its shape);
then documents, in two tiers, least recently used first within each:

1. documents the engine reads again itself: files on disk, and model documents whose cache file
   is at the version held, read again under the same id on their next access (reading runs no
   code);
2. every other: model documents, `pointer`, `shape` and `memory` together.

A document a page watches is never evicted, nor its tessellations (connected means warm), nor
the document being served as it is put. The STEP reads held by their bytes go with the first
document evicted.

**Pressure.** The daemon's server asks the operating system's memory-pressure signal every two
seconds (`serve.Pressure`) and, under pressure, evicts in the same order down to the low-water
mark, half the budget:

- macOS: `sysctlbyname("kern.memorystatus_vm_pressure_level")`, 1 normal, 2 warning, 4 critical;
  warning and critical are pressure. It is the level `DISPATCH_SOURCE_TYPE_MEMORYPRESSURE`
  reports, polled: the dispatch source wants a block callback, which Python cannot hand it.
- Windows: `CreateMemoryResourceNotification(LowMemoryResourceNotification)` once, then
  `QueryMemoryResourceNotification` each time.
- Linux: pressure stall information, the cgroup's `memory.pressure`, else `/proc/pressure/memory`;
  `some avg10` over 10 is pressure.

Where none can be read, the budget alone applies. `Pressure.simulate` is the tests' hook.

**The rebuild command.** A document that is not held -- `evicted`, `expired` -- names the exact
command that builds it again: `python` and the program whose call built it (its `__main__`
file, else the model's script), from the daemon's record of it, or after a
restart the registry's. A shape handed over has none: its words say that a program the engine did
not run showed it, and that only running that program again hands it over again. A child model's is its parent's program, whose run builds it. The page
reads it from its document's 404 (`GET /api/doc/<id>`: `{"error", "state", "rebuild"}`),
`cadgen inspect` and `cad_show` of its id refuse with it, and `cadgen status` lists it. A `memory`
document's words add that it is kept in memory only. The engine never runs it: no access, no start
and no restart runs code to bring a document back.
Asked of the server, a document it does not hold is a refusal (`serve.NotHeld`): the server answers
its type, state and command with its words (`daemon.refused`) and the caller raises it as that
type (`api._failed`), so `cadgen inspect`, `export`, `snapshot` and `serve` of such an id exit 2.

`cadgen stop` stops every server of the installation, whatever protocol it speaks: the socket and
lock names carry the protocol (`daemon._tag`), and `daemon.endpoints()` lists this one's and each
older one's, so a cadgen that bumps `PROTOCOL` still stops the server an earlier one started. Both
`stop` and `status` remove the socket and lock of a dead server (nothing answers and nobody holds
its lock) and say so on stderr; `status` names an older protocol's live server, which `stop` stops.
`stop` prints a line per server it stopped (`stopped the engine server at SOCKET`), or `no engine
server is running`; `--json` prints `{"ok": true, "stopped": [SOCKET, ...]}` instead.

## Progress

A build says where it is (`progress.py`), and nothing in a model says it: the engine reports what
it runs, by name. Its stages are said where the build reaches them (`build.py`, through
`progress.current`): `load` (the script loads), `body` (a model's body runs: "Building
geometry"), `names` (its result collected and its elements named), `document` (its XCAF document
made) and `write` (each file written: its name the detail, counted of the model's files). Inside
`body`, each `@memo` call and each child model the body calls is a body of its own, said where
it begins and where it ends by its function's name (`BuildContext.memo` and `child`, through
`Progress.entering` and `leaving`):

```python
@memo
def finger(name): ...                                     # "Building geometry  finger"

@xbf("XBF/hand.xbf")
def hand():
    fingers = [finger(name) for name in FINGERS]
    return bd.Compound(children=[palm(), *fingers], label="hand")
```

While a body runs the detail is its name, the innermost when they nest; when it ends the detail
goes back to the body around it and `done` counts it, of no `total` (how many there will be is not
known). A body the memo replays begins and ends too; a placement of a result this build already
made says nothing, and a body that raises says no end, so the build's last frame names it.

Each is a frame, the whole of where the build is:

```json
{"model": "hand.py::hand", "outputs": ["/abs/XBF/hand.xbf"], "phase": "body", "label": "Building geometry",
 "detail": "middle", "done": 2, "total": 5, "determinate": true, "elapsedMs": 4120}
```

`model` is as the model's report names it, `outputs` the files its build writes, `done` of
`total` the files written while they are written, and in `body` the bodies done (`total` null,
`determinate` false), and `elapsedMs` counts from the build's start. A phase opens with a frame of
its own; a body's come at least 100 ms apart, the latest held one sent when the interval is up, so
a build of a thousand small bodies sends a frame an interval and the last frame is the build's last
state. The worker sends each on its pipe (`{"id", "progress"}`), and
the daemon:

- passes it to the build's caller as it does the log's lines (`client.request(on_progress=)`):
  `python model.py` draws a bar on stderr when it is a terminal -- each
  phase finished a line with its time, the one in flight repainted in place -- and nothing when
  it is not (`progress.Bar`; `api.build_script(progress=)` takes the frames instead, `False` none);
- keeps a busy worker's last, which `cadgen status` shows (**The engine server and its workers**);
- wakes the pages waiting on a served document among the frame's `outputs` (below).

Each model's report holds its last frame (`progress`), so a failed build
says where it was; a worker that dies during a build fails it with where it was in the words.

**The page's route.** `GET /api/doc/<id>/version?after=V&progress=N&wait=S` answers
`{"version", "patch", "building", "failed", "progress"}` once the version is not `V`, or the
count `progress` is not `N`, or after `S` seconds (60 at most); without `progress=` it waits on
the version alone. `building` is the last frame of the build writing the document now, null when
none is; `failed` is the last build of it that failed, `{"model", "error", "progress"}` -- its
error, and its last frame -- null once another begins or one succeeds; `progress` is a count that
moves whenever either does. A page sends back the last answer's `progress`, so each frame and the
build's end wake it, and nothing polls.

## The viewer and the snapshot

The CAD Viewer and its document reads share the daemon's HTTP listener. The page
reads `/__cad/api/doc/<id>` and waits on its `/version` route; dispatch calls the
engine directly. XBF/STEP loading and geometry facts run in child processes. A
launcher starts or reuses the engine's one page, prints its authenticated URL -- a file's page,
`/<id>`, for each file it names, else the home's -- and exits. The standalone engine's
minimal page (`/<id>`) and snapshot server remain available without the enclosing application.

**The look.** The regular display modes draw a document as OCCT's PBR raster draws it, one frozen
record (`render/look.py`) that the OCCT prototype (`render/occt.py`, its finishes and light in
`render/finish.py`) draws by too: one white directional key at radiance 4 travelling
(-0.35, 0.55, -1), and one environment lighting every surface at 0.5, the viewer's neutral studio
baked as a 512 x 256 Radiance image beside the record (`render/studio.hdr`); no ambient term, fill,
shadow, exposure or tone curve: the sum is clamped and sRGB-encoded. Every surface answers that
light as OCCT's PBR program does (the record's `brdf`, `occt`): single scattering, Schlick-GGX
geometry, OCCT's split-sum table, the roughness as given, no anisotropy, which the viewer draws in
place of three's own physical model (the bundled `@text-to-cad/core`'s `lib/viewer/surfaceBrdf.js`),
its environment prefiltered as OCCT bakes it (`lib/viewer/ggxEnvironment.js`: each roughness the
image convolved with that roughness's GGX lobe, the diffuse light OCCT's nine spherical harmonics
of the irradiance). A part without a material,
and every fill (Parts), wears a plain dielectric finish (roughness 0.5) over its colour, linear,
squared, which keeps the saturated colours of OCCT's old Phong look. A part with a material wears
its finish in Solid and Shaded on both renderers, its colour as authored, reflecting that
environment; X-ray draws it in the plain finish. What OCCT's raster has no term for it
approximates (`render/finish.py`): a clear coat eases the base's roughness toward the coat's,
anisotropy is dropped (and the viewer drops it too), transmission is opacity over the colour tinted
by the transmission colour.
Edges are unlit in their class's ink, 1 px; X-ray's faces are lit at 0.22 opacity, Hidden line's
are the backdrop's colour. The engine serves the record as `GET /api/look` and its image as
`GET /api/look/environment`; the page reads both once per engine, beside the document, and the
document's scene brings them as its own lighting and surface rule (the bundled
`@text-to-cad/core`'s `lib/xbf/xbfLook.js`), which the viewer's viewport and the snapshot page put
up in place of the theme's. Preview is drawn as any file's is.

`cadgen snapshot` draws a document as the viewer does. The engine serves and meshes it (the
daemon's meshes, or with `daemon=False` a server of this process), and OCCT draws it from those meshes
(`render/`, below), in the look the viewer resolves for the same display settings. `--display` takes
a mode (`solid`, `shaded`, `parts`, `xray`, `hidden-line`, `wireframe`), `exploded=A` (the parts
moved apart as the viewer's Explode moves them, by an amount from 0 to 1; with a mode,
`hidden-line,exploded=0.6`), `light` or `dark` (the appearance, all a drawing takes), or the display
object (`mode`, `grid`, `appearance`, `camera`, `clip`, `exploded`: `{"enabled", "amount"}`, 0.5
unless given; `hidden` and `isolated`: lists of part refs, an occurrence's path in the refs
grammar, which every look -- Preview, X-ray, Explode, Clip -- leaves out or alone draws, as the
viewer's hide and isolate do, and which a Quick Edit packet given to `--annotation` carries; a
robot's parts are named by the viewer's visual ids too, `link:v1` (`link:v1/object/0` one object of
it); a ref that names nothing is refused by name); `--json` reports what was drawn
and each stage's milliseconds (`serveMs`, `meshMs`, `sceneMs` when a scene is made, `presentMs`,
`frameMs`, `drawMs`, `renderMs`, `totalMs`; a file no document: `readMs` its reader, `openMs` its
render process opening it). `parts` and `exploded` for a document that places one
part are refused by name before anything renders. `--annotation FILE` draws the viewer's annotation over the
model -- each mark on the part it was drawn on, wherever the picture places that part -- from an
annotation file or the Quick Edit packet that carries one (the `.snapshot.json` the viewer writes),
and `--measurements FILE` Measure's dimensions (`[{start, end, label, color}]`). A mark names the
view it was drawn in by label alone (`"view": "view 1"`); the view itself -- its camera
(`position`, `target`, `up`, `orthographicHalfHeight`, the snapshot's own camera object), size and
projection -- is a job of the packet. `--camera authored` draws the picture from the view of the
last mark, exactly (no fit), at its size and projection unless the flags say otherwise: from the
packet given as `--annotation`, else the newest packet beside the annotation file that draws this
document; with none, it is refused by name. A face the mesher left without triangles is named in a
warning. Nothing is written but OUT. OUT may be a folder -- one that is there, or a path ending in a
separator -- and the picture is then `<SRC's stem>_<UTC time>.png` in it (a model's name for a model,
`snapshot.picture_path`), the path the verb prints and reports (`output`).

**A job.** `--job PACKET` replays a whole Quick Edit packet -- or a job file in its words: a job, a list
of jobs, or `{"input", "jobs": [...], "annotation", "measurements"}` -- in one call
(`snapshot.job_pictures`, `api.snapshot(job=)`), on the machinery above: each job is a view, drawn with
its own `camera` (an output's own `camera` over it), its `display` (its `hidden` and `isolated` parts
among it; the packet's top-level copies are `--annotation`'s), its pose (`jointValues`, as `--pose`
takes it), `preview`, and -- a robot's -- the visuals its `selection.hide` names by the viewer's ids
(`link:v1`, each robot instance carrying its visual's), the packet's ink and dimensions over each
(a job's own `annotation` and `measurements` over the packet's); and each of its `outputs` (`path`,
`width`, `height`, `camera`, `label`) is a picture written at its path (a folder takes
`<stem>[_j<m>][_<n>]_<UTC time>.png`, the job's and the output's place where there are several). A
job's `output` settings finish its pictures: `padding` (0 to 0.15 of the picture each side, 0.04
unless given) and `tightFrame` (true unless given: the fit on every drawn vertex, else on the drawn
parts' box) frame a fitted camera, and a view's own camera -- a position, a target and, orthographic,
a half height -- with `tightFrame` false is drawn exactly, as the viewer writes every view
(`padding` 0, `tightFrame` false); `transparent` draws on nothing (OCCT's backdrop is a fill it draws
whole, so the picture is drawn on black and on white and each pixel's coverage read from the two,
in linear light: `service.matte`; Preview keeps its floor and its shadow, the sweep gone);
`renderScale` (1 to 3) draws the picture that many times its size and brings it down, each pixel
the mean of those it covers (`service.picture`): what the engine draws in pixels -- ink, words,
Measure, the grid -- is as heavy against the picture at any scale, while OCCT's GL lines (edges, a
drawing's hairlines) stay one pixel of the larger frame and read finer: OCCT's core profile draws no
line wider than a pixel, and this is that, not a bug; `sizeProfile` sizes an output that gives no
size. SRC, given, is drawn in place of every job's input, and a flag given overrides every job: the
display, the grid, the camera, Preview, the pose, the ink, the dimensions, the size of every
output; an OUT is refused. Every job is checked before anything renders (an unknown key, a setting
out of range, two outputs at one path, a file that is not there: refused by name, every file left as
it was), and a picture that fails writes none of the job's: every picture is staged beside its
output and moved into place only when all are drawn, and a failed snapshot leaves every existing picture as it was. Through the daemon each picture is a frame
of the file's warm render process; `daemon=False` serves each file once for all its pictures.
`--json` prints `{"ok": true, "pictures": [what each drew]}`.

**The OCCT stills.** A document is drawn by OCCT's own OpenGL renderer from the engine's meshes
(`render/`): one presentation per part and look, each
instance a connected object of it; the modes, the camera fit, clip, grid and Preview are the
page's, Explode is the viewer's layout ported to Python (held to the viewer by one golden its own
scene made), and the annotation's ink and the measurements are drawn over the picture. Through the daemon, a served document a snapshot asks
for gets a render process of its own, started on its first picture and holding the document --
each part's buffer from the daemon's one mesh cache (nothing meshed again), its OCCT shapes, a
scene and its presentations on a hidden OpenGL context: a picture of it is a frame of that
process, answered as PNG bytes that the verb writes to OUT (tom: about a tenth of a second). When
the served document is patched -- a build of it, or its file rewritten -- the process is sent the
new version at once with the buffers of the parts it lacks: the parts it shares with the last keep
their shapes, the new ones are made, and its scene is made again before any picture asks. It goes
with the daemon, and after a picture that leaves it over the workers' memory cap it says so
(`retired`) and exits. `daemon=False`, and a model's own document in its worker, draw in that
process. The context is a hidden window: Cocoa on macOS, an X server's (Xvfb on a machine with no
screen) or OCCT's EGL on Linux, a hidden window on Windows; where none can be made the snapshot
fails saying so. Nothing is written but OUT.

`SRC` may also be a file the viewer opens that is no document, each read by its reader
(`formats/`) and drawn by OCCT in the same look, through the daemon by a render process of its own
per file (read again when a file it read changes) or with `daemon=False` in this process:

- **A mesh file** (`.stl`, `.3mf`, `.glb`) becomes a structure and part buffers as a document's are,
  so the modes, the camera fit, the grid, clip, Explode, Preview and the annotation are a
  document's. Each mesh carries the viewer's normals (creased at 30 degrees up to 10,000
  triangles, else flat) and its feature edges (three's `EdgesGeometry` at 16 degrees: the folds,
  the open rims), which Solid and the line modes draw. An STL is one part in the look's fill, its
  numbers millimetres; a 3MF is its objects placed by its build in its unit, each triangle in its
  colour group's or base material's colour (a slicer's generated default is none), a base
  material's `pbmetallic` its finish; a GLB is read by OCCT's glTF reader into an XCAF document --
  its node tree, its meshes, each primitive's material (with the extensions the engine writes:
  IOR, transmission, clear coat, anisotropy, emissive strength) and its base colour texture,
  drawn on its texture coordinates in the lit looks. `--pose` is refused: a mesh has no
  mechanism.
- **A robot** (`.urdf`, `.sdf`, `.srdf`) is its link visuals' meshes (STL, 3MF and GLB files, a
  `package://NAME/...` one in the ROS package the description is in: the nearest folder above it
  named NAME or holding a `package.xml` that names it, as the viewer finds it too; a
  box, cylinder, sphere or capsule made and meshed by the kernel), each link's in one colour of
  the Parts palette, placed by the viewer's forward kinematics (`lib/urdf/kinematics.js` and
  `fourBarCoupling.js`, ported and held to a golden its own code made: mimic joints and four-bar
  linkages followed) where the viewer opens the robot -- every control at zero, an SRDF's `home`
  group state over that. `--pose` names an SRDF group state (`group/name`, or a name one group
  has) or gives joint values (degrees, metres) over the opening pose; an unknown joint, a joint
  that is no control and a value past its limits are refused by name.
- **A drawing** (`.dxf`) is drawn as the viewer's DXF pane draws it: from above, fitted with its
  16 px margin, lines, arcs, polylines, splines, ellipses, solids, solid hatches, blocks and
  dimensions one pixel wide in their pens (ACI 7 the look's ink), words set in the platform's UI
  face, on the light or dark paper (`display.appearance`, `render/look.py`'s `DRAWING`). Its
  camera is a plan view, the window a Quick Edit view of it names (`render/drawing.py`'s
  `plan_view`: `{position, target, up, orthographicHalfHeight}` looking straight down at the sheet,
  +Y up), drawn as that window -- given as `--camera`, as `authored` (the view the ink was last
  drawn in), or as a job's view; `--annotation`'s ink lies on the sheet in drawing coordinates,
  painted as the pane paints it (`paint_ink`: strokes round-capped as wide as the viewer drew them
  against its height, areas filled, a text mark's words filling its box), and `--measurements`
  Measure's dimensions over it. Every other flag is refused by name; what it does not draw
  (points, hatch patterns, images) is named in a warning.

`SRC` may be a document's id too: it is drawn from the document the worker holding it has,
served by a server of the worker's over its one mesh cache, whether or not the model declares an
xbf, and nothing is built. From Python, `cadgen.snapshot(handle, ...)` and `handle.snapshot(...)`
draw the document a model call returned, by its id, as it is held; `cadgen.snapshot(model, ...)`
with the decorated function itself builds it first, writing what the model declares (law 10), and
the snapshot nothing but OUT. A picture is never a declaration: no
decorator and no build flag draws one.

## Exports

### Viewer exports

The browser's Export action writes the displayed document as its code built it (law 22),
through `export/viewer.py` and the same worker writer as `cadgen export`. Its source is the
displayed document and revision, nothing else (`viewer.exports.specification`: `{doc,
revision}`); no part, no pose, and nothing of the view -- selection, visibility, Clip, Explode,
Preview -- is an input. A posed or partial file is a function in the model's code.

- **A file the engine serves** (a STEP or an xbf) is read where a file's export runs, at the
  version shown: its `mtime_ns-size`, checked again in the worker before anything is written.
- **A held model** (by its id) is read from the worker that holds it, or from the whole
  document the server took when that worker went (**Document lifetime**), at the revision shown
  and its structure's digest; it is never built again, and one no longer held is refused.
- **A mesh file** (GLB, STL, 3MF) is named by its path at the bytes shown (the catalog's hash of
  them), checked before the job and, by its `mtime_ns-size`, again in the worker.

The formats offered are a document's STEP, GLB, STL and 3MF, DXF where it is planar, and an xbf
but of an engine-written xbf, which offers its original bytes instead (a separate download); a
mesh file's are the other two mesh kinds and nothing else. A changed source is refused, saying
to open Export again. There is no source bundle in this interface.

The enclosing distribution owns the HTTP queue, the browser download and temporary
artifact lifetime; the standalone engine owns inspection, revision validation and
translation only. One explicit job names one temporary output, with no intermediate
XBF. Cancellation takes effect between worker operations, discarding an in-flight
result without killing a worker shared with another caller.

### Translation formats

The xbf is the model's result; STEP, GLB, STL, 3MF and DXF are exports of a document, and an
xbf can be one too. One writer, `export.translate(document, kind, path)`,
writes every one, whether a decorator declares the file or `cadgen export` asks for it: the
same document writes the same bytes. The file holds what the code built (law 22). Every file is written beside its
target and moved over it; a DXF only when its bytes change.

- **Sources are documents**: an `.xbf` or a `.step` (read into a document first), or a
  document's id (written from what the engine holds of it -- its worker's document, or the whole
  document the server took from the worker before it went (**Document lifetime**) -- byte for byte
  what it would write however the script has changed since, and nothing is built); from Python, a
  `Model` (built first, in its worker: the program's own call) too. An xbf is written from a
  STEP; never from an xbf, which already is the document. Several destinations read the document
  once, and every destination is checked before any is written; an export
  runs in the worker that built the document while the file is as it left it, else in the
  daemon's documents worker, which reads it.
- **A mesh file is a source of the other mesh kinds**: `cadgen export part.stl part.3mf`, any
  pair of GLB, STL and 3MF either way. It is read as a document of its own kind
  (`export/mesh_file.py`): triangles, with the parts, names, colours and placements its format
  carries, each part's mesh the file's own (never meshed again, never cached); the GLB, STL and
  3MF writers write it as any document. It runs where a file's export runs (the daemon's
  documents worker; in this process with `daemon=False`) and loads no CAD kernel: its readers
  are numpy and the standard library (a GLB through `formats/gltf.py`, not OCCT's reader). A mesh
  has no B-rep, so no xbf, STEP or DXF is made from one (`part.stl is a mesh: it has no B-rep, and
  no STEP export is made from one`), and a mesh file is not written from one of its own kind.
  What the destination cannot hold is left out, as a CAD program's Save As does, and nothing
  warns of it:

  | from \ to | STL | GLB | 3MF |
  | --- | --- | --- | --- |
  | **STL** | -- | one part, its file's name; the viewer's normals (creased at 30 degrees) | one object, welded |
  | **GLB** | every placed triangle, one soup | -- | a part per mesh, a build item per mesh node; colours, names, metallic and roughness; textures, the materials' other extensions, normals and animations are dropped |
  | **3MF** | every placed triangle, one soup | an object a mesh, a build item a node; colours and display properties as materials; the viewer's normals | -- |

  Units are the viewer's for each format: an STL's numbers are millimetres (it says no unit; the
  viewer draws them as they are); a GLB's are glTF's metres, Y up, read as Z-up millimetres
  (times 1000) unless a node declares `extras.cadUpAxis: "z"`, and written in the document's
  millimetres under a root node turning them back; a 3MF's are in its `unit` (millimeter when
  absent; one the 3MF specification does not define is refused, as the viewer refuses it), made
  millimetres, and written `unit="millimeter"`. So a 10 mm cube is 10 mm in each, and 0.01 in a
  GLB's numbers. A part with no colour of its own is written in the writers' default grey, as a
  document's is.
- **STEP** (AP242, `export/step.py`): the assembly with instance and product names, colours per
  part and per painted face, material names and densities, element names on face, edge and
  vertex sub-shape labels. Read back through the engine's own reader, the instance tree, every
  name (on the same elements: the reader numbers edges and vertices in its own order), colours
  and materials' names and densities are the xbf's. OCCT's writer drops the look (metallic,
  roughness, emissive and the rest: a material reads back matte), every physical field but the
  density, a face's material (the face keeps its colour), the mechanism and its configurations,
  and the model's key and provenance. The writer's two run-dependent choices are settled
  before it writes: the header's time stamp is `step.WRITTEN_STAMP` (the xbf's date), and the
  colour presentations, which it keeps in a map keyed by shape, are put in the order of the
  shapes they style, so the same document is the same STEP in any process on any day.
- **GLB**: one mesh per prototype (indexed in 16 bits up to 65,535 vertices, in 32 past them), a
  node per placement named by its path, a PBR material per
  look (a paint is a primitive of its own) with an extension for each part of the look past
  metallic-roughness (`KHR_materials_ior`, `_transmission`, `_volume`, `_clearcoat`,
  `_anisotropy`, `_emissive_strength`; **Materials**), every motion of the document an
  animation of the same name (below), and every `animation()` of its code, from a build or from
  the record an xbf carries (**Animations**); **3MF**: an object per prototype, a build item per
  placement, looks through the materials extension (base materials, `pbmetallic` display
  properties, painted triangles naming their own); **STL**: binary, every placed triangle.
  Their meshes are the process's one mesh cache's (`serve.MESHES`), the viewer's: a part the
  build meshed for the viewer is not meshed again for a GLB, nor the other way round.
- **DXF** (`export/dxf.py`): a planar document -- a model whose body returns a sketch, a face,
  wires or edges -- drawn by build123d's own `ExportDXF` (ezdxf), in millimetres, each edge
  where the document places it one entity, so a curve stays an ARC, CIRCLE, ELLIPSE or SPLINE.
  A document placing one part is the layer `CUT`; any other is a layer per part, named by its
  occurrence's name (`cut.label, bend.label = "CUT", "BEND"` in the compound returned), parts
  of one name sharing it; a layer of several shapes is one part of them all
  (`bd.Compound([a, b], label="ENGRAVE")`). A solid is refused (`tom.xbf is 3D`), and so is an edge with a point
  off z=0, by its element name. Layers are written in name order and edges in an order of
  their content (curve kind, sampled points, length), never the kernel's traversal, and
  ezdxf's provenance is pinned and its classes sorted: the same geometry is the same bytes in
  any process on any day, so a declared DXF is the bytes `cadgen export flat.xbf flat.dxf`
  writes. The drawing checks run on the document before it is written -- units set, no
  zero-length or duplicate entity, every cut profile closed, something drawn; open geometry
  only on a layer its name's whole tokens make a bend, engrave or reference one -- and an
  error refuses the file, saying which. `export.dxf.validate_dxf_file` runs them on any DXF.
- **No option selects a part or a state** (law 22): a file of one part is that part's own
  model (a function returning it), and a posed file a model returning the assembly posed
  (`posed(arm().shape, "folded")`, `cadgen.ap242`). Snapshot's `--pose` is the picture's: ad
  hoc, never cached, never declared.

**Motions in a GLB.** Each motion (**Configuration sequences**) is baked into a glTF animation of its name:
translation and rotation channels for each placement it moves, baked CUBICSPLINE over one set of
key times (`export/motion.py`) and written LINEAR (**GLB keys**). The keys start at the motion's waypoints and the halfway point
between each two; at a key every moving placement is where forward kinematics through the
mechanism (its couplings included) puts it,
its in- and out-tangents the one-sided derivatives there, so a step's speed may jump at a
waypoint. A step is halved while at any eighth of it the Hermite strays from the true forward
kinematics by more than 1e-3 of the model's size (the diagonal of what the GLB places) in a
placement's origin or 1e-3 radian in its rotation, at most 4,097 keys. A moved placement's node
stands by translation and rotation, every other by its matrix; placements whose keys are the
same bytes (the parts of one link, each its own node) share one sampler, so a link's motion is
written once however many parts it carries; the animation's
`extras.cadgen` holds the duration. A clip is the motion once, and a player repeats it. STEP,
STL and 3MF ignore motions, and neither `export` nor `@glb` takes an argument for them. On the
corpus's motorbike (2,053 mm across, so a 2.05 mm tolerance), `steer` (a ±20° sweep of the head
tube and back over 4 s) bakes to 5 keys on 15 placements, within 1.26 mm and 2.1e-4 rad of
forward kinematics at eight points inside every step.

**GLB keys.** A bake keys a track where its curve needs it: a motion's every placement on the keys
its hardest one needs, an animation's eased channel CUBICSPLINE, three values a key. The GLB
writes each track that is not STEP as LINEAR keys, the fewest within `KEY_MM` (0.1 mm) and
`KEY_DEGREES` (0.1°) of the bake (`export/keys.py`), constants rather than options (law 22): a
tenth of a millimetre is under a pixel of a 1 m model filling a 4K screen. The bake's curve is
sampled densely (a CUBICSPLINE step as often as keeps its Hermite within 5% of the tolerance of
the chord between two samples, so a line that holds the samples holds the curve); from each kept
key the farthest candidate (a bake key, or a sample of a step its own two keys' line cannot hold)
whose line, lerped or for a rotation slerped as glTF interpolates LINEAR, holds every sample it
spans is kept, with the first and last keys, both keys of a jump (two keys under a millionth of
the clip apart) and two rotation keys never more than 120 degrees apart. A scale is held to the
millimetres its part moves (its change times the part's farthest point from its origin). A STEP
track (a hide) is written as baked, its jumps at the times it names. Distinct tracks are worked
out once, the same document gives the same bytes, and on the corpus's GLBs, their bakes rewritten
so and read at 240 Hz, every track stays within 0.0995 mm and 0.0997° of its bake while the animation keys shrink to 12-24% of
the bake's: juno 108.7 MB to 6.9, tom 98.5 to 18.7, w16 83.2 to 38.5, radial 78.9 to 44.2 (with the
samplers shared, above). A sparsely keyed eased bake (a small model's) can take more LINEAR keys
than it had CUBICSPLINE ones, each a third the bytes.

**File decorators require `out`.** `@xbf("XBF/arm.xbf")` declares the native document;
`@step("arm.step")`, `@glb("arm.glb")`, `@stl("arm.stl")`, `@threemf("arm.3mf")`
and `@dxf("arm.dxf")` declare translations. Relative paths are relative to the script.
There is no default decorator path. No file decorator takes
anything else: a model's material, colours, joints, the pose its joints connect its parts at, its
configurations, its motions and its animations are written in its body. Every declared file shows the model as
built: where its joints' `connect_to` placed the parts. A model that wants a second pose on
every build is a second model function with other joint values. A model with no `@xbf` writes
its derived files and nothing else.

**Every model that runs writes its files** (law 10). A child model -- one another model's body
calls, in its file or another -- writes the files it declares after its target's are written,
once per build, from its own document: the result its body returned, before its caller placed
or labelled it, its closure the one a build of its own script makes (its folder, the modules its
script imports). So its xbf is the one its own build writes, byte for byte; a later build of it
takes that file (**Build closure**), and a file whose bytes are unchanged is kept. A child called
twice is one model, written once; a child that is also a target of the build writes as the
target; a child run inside a replayed body writes as one its caller ran; one that ran before its
caller raised writes all the same. A child writes what its decorators declare. A model taken from its file ran nothing,
and nor did its children. The target's report holds each child's under its identity
(`child_models`: its files, parts and timings), and a
child whose file cannot be written fails the build. A part is written free
(`document.unchecked`): OCCT marks a shape put in a compound as no longer free, which would
make a child's part, placed in its caller's assembly, other bytes than its own build's.

The xbf is saved first and the viewer woken with it: the worker waits for the daemon to hold
the patch (`{"op": "patched"}` on its pipe) before it writes a derived file.

**Functions** (`api`, also `cadgen.export`, `cadgen.snapshot` and `cadgen.inspect`; `serve`,
`status`, `stop` and `server` only the CLI calls): one per command, each through the daemon. No function builds source text;
a shape made elsewhere is handed over, never built (`model(shape, name=...)`, **Shapes handed over**).
`export(source, *destinations)` a list of `Written`; `snapshot(source, out, ...)` a `Drawn`, and `snapshot(job=PACKET, ...)` (with `source` in place of the packet's input, as `--job PACKET SRC`) a list of them, one verb with two input shapes, anything else refused as Python refuses a call; `where(doc)` the build
closure an xbf holds, `where(doc, ref)` an element's facts. Each takes a handle (what a model call
returns), a document id or a file path; `export` and `snapshot` take the decorated function too,
building it first. A handle exports and draws its document the same way (`.export()`,
`.snapshot()`); a `Model`'s `.build(verify=, profile=, daemon=)` is the debug seam, a `Report`: it
and its children, as declared.

## Kinematics

At document time the engine harvests every joint on every part of the result and pairs them
two ways: by `connect_to` where the author used it, and, for every joint `connect_to` did not
join, by label -- a moving joint and a `RigidJoint` of the same label on another part are its
pair (the nearest in the tree; two alike are refused by name), and two rigid joints of one label,
each the other's nearest, fasten their parts. `connect_to` wins where both would pair a joint.
build123d's `connect_to` composes locations within each part's own compound, so it cannot place
a part in a nested assembly: there the model puts each part where it stands, authors the two
joints there, and the label pairs them. The engine never moves a part: every value, as built
included, is computed from where the two joints' frames stand in the built tree. The pairs make
a mechanism in ISO 10303-105's terms (STEP AP242's kinematics):

- **Links** are occurrences that move as one: two parts whose rigid joints are connected
  are one link. The **ground** is every link no `connect_to` moved (the joint whose
  `connect_to` is called stays put; the other's part moves), and every part no joint places.
  A part below a jointed sub-assembly moves with it.
- **Pairs**: a revolute joint is a `REVOLUTE_PAIR`, a linear one a `PRISMATIC_PAIR`, a
  cylindrical one a `CYLINDRICAL_PAIR`, a ball a `SPHERICAL_PAIR`, each `_WITH_RANGE` where
  its range is finite, named by the moving joint's label (a label two pairs share takes the
  path of the part that holds it: `hand/left:knuckle`). Link 1 holds the moving joint, link 2
  the rigid one. Its frames, `transform_item_1` and `transform_item_2`, are
  AXIS2_PLACEMENT_3Ds in their links' frames (a link's frame: its first occurrence's
  placement as built) that coincide at value 0; link 2 stands at
  `link_1 · item_1 · M(v) · item_2⁻¹`, `M` a turn about Z, a slide along Z, both
  (cylindrical: angle, then distance) or build123d's intrinsic X-Y-Z rotation (spherical).
  Degrees and millimetres.
- **Mechanism states**: the as-built values and each named state (`mechanism_state`), as
  `MECHANISM_STATE_REPRESENTATION`s of pair values (the structure's and the viewer's
  `configurations`).
- **Couplings**: each `gear_pair`, `rack_and_pinion_pair` or `screw_pair`, a constraint among
  pairs, as the AP242 couplers it is named after (below).
- **Configuration sequences**: each `configuration_sequence`, as AP242's
  `INTERPOLATED_CONFIGURATION_SEQUENCE` (the structure's and the viewer's `motions`): its
  segments' times (`t_parameter`), interpolation and states (a mechanism state it names, or pair
  values).

**What AP242 cannot hold is refused or left out, never patched** (law 13). A pair the built
tree contradicts fails the build by name: one whose part stands where it cannot put it (moved
after `connect_to`, connected after its compound was made, a rigid joint off the joint's axis)
or that joins two parts rigid joints make one body has no value the standard can hold. A moving
joint matching two rigid joints alike, a linear joint connected to a revolute one (a pin in a
slot, which no AP242 lower pair is) and a mechanism state's value a pair cannot take are left
out and warned; pairs that close a loop are kept and not posed. The warnings are the build's
report (`kinematics.warnings`), never the document's. The harvest's errors are a mechanism state,
a configuration sequence or a coupling naming a joint its assembly does not hold, a coupling
named as a joint is, a coupling driving a joint its pair does not relate or no coupler can hold
(below), and a joint two couplings drive.

**Couplings.** A coupling is a constraint, made by the function named after the AP242 pair it
is written as:

| Function | Its joints | AP242 |
| --- | --- | --- |
| `gear_pair(assembly, name, **joints)` | revolute joints, a ratio each (degrees per unit of its value) | `KinematicPairWithMotionCoupling`, `Kind` `gear_pair`, from the first-named joint to each other one |
| `rack_and_pinion_pair(assembly, name, **joints)` | the first-named a revolute joint (the pinion) or a prismatic one (the rack), every other of the other kind, a ratio each | `Kind` `rack_and_pinion_pair`, from the first-named joint to each other one |
| `screw_pair(assembly, name, joint=pitch)` | one cylindrical joint and its pitch, the millimetres it travels per 360 degrees of turn; the coupling's value is its turn | Part 105's `SCREW_PAIR` (`pitch`) |

Its joints move together, each by its ratio, and only through it, each named by its label. At
value `c` each joint stands at its as-built value plus its ratio times `c`: `c = 0` is as built,
so a coupling never moves the build. Its range is derived, never given: the tightest interval of
`c` in which every joint stays within its own limits (a joint with no limits bounds nothing; a
side nothing bounds is open). Its name poses wherever a joint's does --
`mechanism_state(..., curl=0.5)`, a configuration sequence's waypoints and sweeps, `--pose
'{"curl": 0.6}'` -- and mechanism states and configuration sequences resolve it to pair values
at document time, so their AP242 states and a GLB's bake are as ever; a pose, a mechanism state
or a configuration sequence setting one of its joints alone is refused (a state's or a
sequence's value left out, and warned).

In the document each coupler holds `s1 · d1 + s2 · d2 = 0` over the two values' displacements
from as built (`CouplingRatios`, with `CouplingTypes` saying which value of each pair), so the
ratios read back as written; a coupling of more than two joints is chained as two-joint couplers
from its first-named joint, never one `three_joint_coupler`. A joint its function does not
relate -- a gear pair's prismatic joint, a rack and pinion's two pinions, a screw's revolute
joint, any coupling's ball joint (no coupler relates a ball's three angles) -- fails the build
by name, as does a coupling of one value alone and one whose joints' limits leave it no range
around as built. A function coupling, a cam or a loop is no part of the mechanism: a
configuration sequence says it.

```python
import build123d as bd
from cadgen.ap242 import configuration_sequence, gear_pair, mechanism_state, screw_pair
from cadgen.engine import xbf

CURL = {"index_mcp_flexion": 90, "index_pip": 100, "index_dip": 70}  # degrees at a full curl
BONES = {"base": 30, "proximal": 40, "middle": 25, "distal": 20}     # lengths along +X

@xbf("XBF/index_finger.xbf")
def index_finger():
    bones, x = [], -BONES["base"]
    for name, length in BONES.items():
        bone = bd.Pos(x, 0, 0) * bd.Box(length, 16, 12, align=(bd.Align.MIN, bd.Align.CENTER, bd.Align.CENTER))
        bone.label, x = name, x + length
        bones.append(bone)
    for joint, parent, child in zip(CURL, bones, bones[1:]):
        knuckle = bd.Axis(child.location.position, (0, 1, 0))
        bd.RevoluteJoint(joint, parent, axis=knuckle, angular_range=(0, CURL[joint]))
        bd.RigidJoint(joint, child, bd.Plane(origin=knuckle.position, z_dir=knuckle.direction).location)
        parent.joints[joint].connect_to(child.joints[joint], angle=0)  # as built: straight
    finger = bd.Compound(children=bones, label="index_finger")
    gear_pair(finger, "index_curl", **CURL)                           # one control: 0 straight, 1 a fist
    return configuration_sequence(finger, "grip", [(0, {"index_curl": 0}), (1.5, {"index_curl": 1}),
                                                   (3, {"index_curl": 0})])

SWEEP, TRAVEL = {"left": -70, "right": 70}, 40                       # a door's turn and travel when open

@xbf("XBF/hypercar.xbf")
def hypercar():
    chassis = bd.Box(4400, 900, 400, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    chassis.label = "chassis"
    doors = []
    for side, y in (("left", 475), ("right", -475)):
        door = bd.Pos(400, y, 500) * bd.Box(1000, 50, 600)
        door.label = f"door_{side}"
        hinge = bd.Axis((800, 450 if side == "left" else -450, 500), (0.3, 0, 1))  # a helical hinge
        bd.CylindricalJoint(f"door_{side}", chassis, axis=hinge, angular_range=tuple(sorted((0, SWEEP[side]))),
                            linear_range=(0, TRAVEL))
        bd.RigidJoint(f"door_{side}", door, bd.Plane(origin=hinge.position, z_dir=hinge.direction).location)
        chassis.joints[f"door_{side}"].connect_to(door.joints[f"door_{side}"], angle=0, position=0)  # shut
        doors.append(door)
    car = bd.Compound(children=[chassis, *doors], label="hypercar")
    for side in SWEEP:                                                # each door's pitch: travel per turn
        screw_pair(car, side, **{f"door_{side}": 360 * TRAVEL / SWEEP[side]})
    return mechanism_state(car, "open", **SWEEP)                      # shut is as built
```

`cadgen snapshot XBF/index_finger.xbf c.png --pose '{"index_curl": 0.6}'` draws the
knuckles at 54, 60 and 42 degrees: the picture of the same finger with no coupling at
`--pose '{"index_mcp_flexion": 54, "index_pip": 60, "index_dip": 42}'`; its range, `[0, 1]`, is
where every knuckle stays within its own. A model returning `posed(car().shape, {"left": -35,
"right": 35})` exports the doors a half turn and a half travel open. A gear train
is a gear pair: `gear_pair(actuator, "drive", rotor_spin=360, output=80, ...)`, a
quasi-direct-drive actuator's, ranged by its joints' limits. A coupling's joint in no pair is
left out of it and warned. A label names the joint in each placement of a
sub-assembly placed several times, and a name two couplings share takes the path of the assembly
holding each (`hand/index:curl`), as a label two pairs share does.

The xbf holds the mechanism as a subtree under `Main():100`, found by the
`TDataStd_UAttribute` of its GUID, of standard attributes only: `TDataStd_Name` on every
label, `TDataStd_NamedData` for an entity's AP242 name (`entity`) and attributes (named as
the standard names them), `TDataStd_ReferenceList` for references, `TDataStd_RealArray` and
`TDataStd_IntegerArray` for a configuration's values, `XCAFDoc_AssemblyItemRef` for an
occurrence (`mechanism.py` draws the tree). A motion's segments say its ease as AP242's
`interpolation` (`linear_interpolation_type`, `synchronous_interpolation_type`; the last
segment's `discontinuous_interpolation_type`), and a coupling is its couplers under
`:6 "couplings"`, a label per coupling holding them. The structure serves couplings as
`kinematics.couplings`: `{name: {range, terms: [[pair, value index, ratio]]}}`, a side of the
range null where nothing bounds it. **STEP carries none of it**: OCCT reads AP242
kinematics but cannot write them, so every STEP, posed or not, is placements only.

`--pose` on `cadgen snapshot` poses the mechanism at a
mechanism state (its name, among the structure's `configurations`) or at joint and coupling values (`'{"elbow": 45}'`, `'{"curl": 0.6}'`,
the rest as built): the engine places each link by composing its pairs from the ground down,
exact forward kinematics, and draws that. No flag is as built. An unknown configuration, joint or
coupling, a value out of range (a joint's, a coupling's, or a joint's a coupling puts it at), a
coupling's joint set alone, a coupling set with one of its joints and a pair of a loop are
refused by name before anything renders.

**The viewer's Position** shows a slider per coupling under the Pose row (0 as built, its range
the coupling's, an open side spanning one turn or 100 mm of its first value): dragging it poses
every joint it drives through the page's forward kinematics (`xbfKinematics.js`), and choosing a
mechanism state puts it where that state stands on it (0 where it is off its line). A
coupling's joints have no slider of their own.

## Configuration sequences

A configuration sequence -- AP242's `interpolated_configuration_sequence`, a **motion** in the
structure and the viewer -- is a definition in the model's code, beside its mechanism states:

```python
from cadgen.ap242 import configuration_sequence, mechanism_state

mechanism_state(arm, "folded", shoulder=0, elbow=0)
mechanism_state(arm, "reach", shoulder=45, elbow=90)
configuration_sequence(arm, "cycle", [(0, "folded"), (2, "reach"), (5, "folded")])  # waypoints, eased
configuration_sequence(arm, "wave", [(0, {"wrist": -30}), (1, {"wrist": 30}), (2, {"wrist": -30})], ease="linear")
configuration_sequence(arm, "nod", lambda t: {"elbow": 45 + 20 * math.sin(t)}, duration=6)  # a function of time
```

`configuration_sequence(assembly, name, waypoints_or_fn=None, *, sweep=None, duration=None,
ease="cubic")` takes one of: waypoints `[(t, pose), ...]` (seconds from 0, increasing; `pose` a
mechanism state's name or `{joint: value}`, the rest as built; the last time is the duration), a sweep
`{joint: (from, to)}` with `duration` (two waypoints), or a callable `t -> {joint: value}` with
`duration`. `ease` is `cubic` (each step eased in and out, every pair arriving together at every
waypoint: AP242's `synchronous_interpolation_type`) or `linear` (constant speed:
`linear_interpolation_type`). A sequence is a finite clip, and a player repeats it: one that
comes back says its way back as waypoints. `loop=` and the `spline` ease are refused by name. A
sequence never moves the build. The viewer plays an `.xbf`'s sequences from its Motion section, each frame the
values the GLB baker keys at that time, posed by the page's forward kinematics.

The document keeps the definition (**Kinematics**), never frames. A callable is stored as its
samples, interpolated linearly: eight equal steps over its duration, each step split while the
samples' line strays from the function by more than half the tolerance at any eighth of it --
the tolerance 1e-3 radian for an angle, 1e-3 of the model's size (its bounding box's diagonal,
from the B-rep's geometry) for a distance -- at most 4,097 samples. A step is split where it
strays most: a kink, where two straight runs meet, is the error's peak between two checks, so
the samples close in on it, and the half tolerance at the checks keeps the line within the whole
one between them (a zigzag with kinks off the grid is held within 0.55 of it, `sin` within 0.44,
where the quarter checks and middle splits let a kink stray to 1.06). The same code
samples at the same times, so the file is a function of the code. A sequence naming a
mechanism state or a joint its assembly lacks fails the build by name; one setting a value its
pair cannot take, or moving a pair that closes a loop, is left out and warned.
A warm build that changes only a sequence rewrites the mechanism's subtree and converts no
prototype; the file is the cold build's bytes.

Every build whose body ran samples its functions again; one that replayed it reuses the samples
its run's harvest made (**Body retention**). The files a function opens while it is
sampled are heard as a body's reads are (`kernel/memo.py`, `listened`), held to their bytes, and
are the model's inputs (**Build closure**): a document is not taken from memory or its file
once one changed, and a replayed body's harvest is not reused. A function reading what is no
regular file, or reading past the engine's readers, leaves the model's closure with no key, as a
body that does, and is sampled on every build.

## Animations

A **configuration sequence** (a motion) is the mechanism's and an **animation** is the GLB's. A
sequence moves pair values over time (**Configuration sequences**): the document keeps it, every
GLB of the document bakes it, and STEP, STL and 3MF carry nothing of it. An animation moves the
nodes a GLB places, in glTF's own terms -- translation, rotation and scale channels, and the
mechanism's forward kinematics at given times -- for what a mechanism does not say: an explode, a
reveal, a showcase, a part hidden. It is baked into every GLB the model declares, when that GLB is
written (law 10), from the build's tree in memory.

The xbf is the model's Save As and holds what its build declared, so it carries the compiled
tracks too: a **build record** on its main label after the closure, as the closure is kept (a
`TDataStd_AsciiString`, `document.ANIMATIONS_GUID`), holding `animations.record` -- each
animation's name, duration and tracks (path, interpolation, keys, the occurrence paths of its
parts, what it says beyond its keys, its label and its order), the build's JSON
(`animations.to_json`), no code. A document with no animation holds no record. It is no part of the
mechanism subtree, which stays AP242's alone (law 13), and only a GLB reads it:
`document.Loaded.animations`, and so `Source.read`, give the tracks back as the harvest made them,
so a GLB exported from the xbf (`cadgen export model.xbf model.glb`), from a held document by its
id (**Document lifetime**) and by the build's own worker are byte for byte one GLB, and a model
taken from its xbf after a restart (**Build closure**) writes that GLB too. Every other reader
ignores it: `read_xbf` imports a part, never a child's record (a parent's GLB bakes its own
animations alone), the viewer's page shows the document's structure, and STEP is AP242 with nothing
of ours. For now a model with an animation declares its GLB beside its xbf, the two decorators
stacked on one function: the xbf records the animation, the GLB bakes it.

```python
import build123d as bd
from cadgen import glb, xbf
from cadgen.ap242 import configuration_sequence, mechanism_state
from cadgen.gltf import animation

@xbf("XBF/box.xbf")
@glb("XBF/box.glb")
def box():
    ...                                                              # a hinged lid, a latch, feet
    mechanism_state(box, "open", hinge=100)
    configuration_sequence(box, "open_close", [(0, {"hinge": 0}), (1.5, "open"), (3, {"hinge": 0})])  # every GLB's
    show = animation(box, "showcase", duration=4)                    # this GLB's alone
    show.pose(at={0: {}, 1.5: "open", 3.5: {}})                     # the mechanism, by its FK
    show.stagger("feet/*", by=(0, 0, -20), step=0.5, start=0.5)
    show.rotation("latch", axis=(0, 0, 1), turns=2, start=1, end=3, interpolation="LINEAR")
    show.channel("latch", path="translation", keys=[(1, (0, 0, 0)), (3, (30, 0, 0))])
    show.hide("latch", at=3)
    return box
```

`animation(assembly, name, duration=)` returns a builder whose calls chain (`animations.py`). Its
primitive is glTF's channel, `.channel(parts, path=, keys=[(t, value), ...], interpolation=)`:
`path` is `translation` (a key an offset from as built, mm), `rotation` (a unit quaternion
`(x, y, z, w)`, the turn about `about=`, default the reference's centre) or `scale` (a uniform
factor, each part about its own origin, as glTF scales a node); `interpolation` is `CUBICSPLINE`
(the default, eased in and out at every key), `LINEAR` or `STEP`, as a sampler spells them.
`.translation(parts, by=|to=)`, `.rotation(parts, axis=, turns=|by=|to=, about=)` and
`.scale(parts, to=)` are channels from `start` (0) to `end` (the duration). The helpers compile to
channels: `.explode(parts, direction=|radial=, distance=)` a translation per reference (along a
direction by its rank, or away from a point), `.stagger(parts, by=, step=)` one per reference in
turn, `.hide(parts, at=)` a `STEP` scale to 0 (glTF has no visibility channel), and
`.pose(at={t: mechanism state or values})` translations and rotations of every part the mechanism
moves, its joint values eased between the keys. The duration is the animation's length, in its
`extras.cadgen.duration` as a motion's is (glTF has no field for it).

Parts are named as a ref's owner names them (**References**: a label, `feet/foot_1`, a path from
the assembly the animation is on) or by a glob (`feet/*`, `wheel?`), its outermost matches each a
reference of its own; a reference's parts move as one body. A reference's translations add, after
its rotations; a part's place is every reference holding it, the largest outermost (a scene
graph's order), after the pose. The build fails by name on a part no occurrence is, a
configuration or joint the mechanism lacks, two channels of one path on one reference overlapping
in time, two poses overlapping, a part one glTF channel would interpolate by `STEP` and by
another interpolation, a time outside the duration, and an animation named as a motion is.

**The bake** (`export/animation.py`). A GLB holds the document's motions, then each animation,
one glTF animation per name, its samplers keyed from 0 to the duration. Each part a channel moves
gets a channel per path it changes, its true place at `t` composed as above; a path's
interpolation is its channels': `STEP` keys at each jump, `LINEAR` and `CUBICSPLINE` keys from the
channels' own key times, each step halved while glTF's interpolation strays from the true place by
more than a motion's tolerance (1e-3 of the model's size in an origin, 1e-3 radian, 1e-3 in a
scale), and two keys never more than 120 degrees apart. A CUBICSPLINE key's tangents are the
true curve's one-sided derivatives there, as a motion's are and as the 0.7 clip baker's central
differences were in the limit. Against that baker, on a hinge eased through 100 degrees, a slide
eased 60 mm and a constant spin (a 127 mm model), the two curves agree within 0.1 mm at every
corner of each part, each within its own tolerance of the motion, the new one in 5 to 7 keys a
path where the old one wrote 6 to 11. The parts of one reference move as one body, so their
channels' keys are the same bytes and share one sampler, as a motion's do. The GLB writes every
channel but a STEP one as LINEAR keys within a tenth of a millimetre and of a degree of this bake
(**GLB keys**).

## Materials

A `Material` (`materials.py`) is frozen and SI, and a field it does not know is `None`, never a
guess. Its physical half: `name` (what the catalogue looks it up by), `family` (`metal`,
`plastic`, `elastomer`, `composite`, `wood`, `glass` or `other`), `standard` (the designation:
`UNS A96061`), `description`, `source` (where its numbers came from), `density` kg/m³,
`young_modulus` Pa, `poisson_ratio`, `yield_strength` and `ultimate_strength` Pa,
`thermal_expansion` 1/K, `thermal_conductivity` W/(m·K), `specific_heat` J/(kg·K), and
`isotropic` (False for a laminate or a ply). Its look is a strict subset of OpenPBR, cut to what
glTF carries: `color` (RGBA, alpha its opacity), `metallic`, `roughness`, `ior` (1.5),
`anisotropy` and `anisotropy_rotation` (radians), `transmission`, `transmission_color` and
`transmission_depth` (metres), `coat` and `coat_roughness`, `emissive` (RGB) and
`emissive_strength` (1). Each look parameter is one glTF field; the module's docstring is the
contract that maps OpenPBR, the `Material`, glTF and Blender's Principled BSDF onto one another.
Every field is checked as it is made, by name (0-1 ranges, positive physical values). `but(**changes)`
is a copy with changes; `mass(volume_m3)` is kilograms, or None without a density.

**Colours.** Every colour a model gives -- `shape.color`, `paint(shape, faces, color)`,
`Material(color=, transmission_color=, emissive=)` -- is what the author sees, in sRGB: a hex
string (`"#e68019"`, `"#e68019cc"` with alpha, `"#e81"`, `"#e81c"`), 0-255 integers (`(230, 128,
25)`, or four with alpha), or a build123d `Color`. The document holds linear RGB, as OCCT's
`Quantity_Color` and glTF's factors do, and the engine converts at the door (`colors.py`), each
channel rounded to six decimals, the precision a colour is read back at. The one assumption, and
its rule: **a build123d `Color`'s channels are sRGB**, as build123d defines them (its constructor
and its iteration are `Quantity_TOC_sRGB`; `Color("#e68019")` is `(0.902, 0.502, 0.098)`), so
the engine reads a shape's colour linear through the `Quantity_Color` it wraps. `shape.color =
bd.Color("#e68019")`, `shape.color = "#e68019"` (build123d's setter makes the `Color`) and
`paint(shape, shape.faces(), "#e68019")` store the same colour, within one 8-bit step.
Floats are no colour of the author's: `Material(color=(0.5, 0.5, 0.5))` and
`paint(..., (0.5, 0.5, 0.5))` are refused by what they take, and `bd.Color(0.5, 0.5, 0.5)` is
sRGB mid grey, `#808080`. A colour read back is the colour written: `Material.color` holds it
linear, and a shape a reader makes (`read_xbf`, `read_step`) is given the `Color` of it.

The catalogue is one object, the module itself: `materials("6061")` looks an entry up in any
case by its name, its attribute or an alias (`"6061-T6"`, `"al 6061"`, `"steel"`, `"delrin"`),
and a miss raises `LookupError` naming the three nearest; `materials.aluminium_6061` is an
entry; `materials.names()` is every name by family and `materials.by(family="metal")` the
entries a field selects. There is nothing to register: a project's own materials are
`Material(...)` constants in its own module, and `materials.steel_1018.but(roughness=0.2)` a
variant. Its 44 entries:

| Family | Entries |
| --- | --- |
| metals | Aluminum 6061-T6, 5052-H32, 6063-T5, 7075-T6; Steel 1018, A36, S235JR, 4140; Spring steel 1095; Stainless 304, 316, 17-4 PH; Brass C360, C260; Copper C110; Titanium Ti-6Al-4V; Zinc ZA-8; Neodymium magnet N42 (a density, nothing structural) |
| printing plastics | PLA, PETG, ABS, ASA, Nylon PA12, Nylon PA6-CF, TPU 95A (an elastomer), Polycarbonate, SLA resin |
| engineering plastics | Acetal (POM), Acrylic (PMMA), PTFE, PEEK, HDPE, UHMW-PE, Nylon PA6, Polypropylene |
| sheet, composites, wood | FR4, Carbon fibre laminate and Birch plywood (both not isotropic), MDF, Hardboard |
| elastomers, other | Silicone 50A, NBR 70A, EPDM foam, Glass (soda-lime) |

`aluminium`, `steel`, `stainless_steel`, `brass`, `copper`, `titanium`, `nylon`, `acrylic`,
`glass`, `abs_plastic` and `acetal` are short names for the common choice. The seed values were
taken once from public material cards (FreeCAD's) and typical datasheets, as a starting point;
each entry's `source` names which. The looks are the engine's own: metals metallic with
roughness by finish (polished 0.2, machined 0.35-0.45, cast 0.6), brushed aluminium and
stainless anisotropic, plastics dielectric, glass and the clear plastics transmissive, rubber
rough.

In the file a material is XCAF's own `XCAFDoc_Material` (name, description, density) and
`XCAFDoc_VisMaterial` (PBR: colour and alpha, metallic, roughness, emissive, IOR), and every
other field in one `TDataStd_NamedData` on the material's label, named as the schema names it
(none for a material of a name and a density). Read back it is the material, its PBR factors as
32-bit floats. A material change converts the prototypes it is on; a cold and a warm build write
the same bytes. The structure serves every field of each part's and each painted face's material;
a GLB writes the look as glTF's extensions (the volume's thickness the part's, the smallest extent
of its box; anisotropy along a tangent the mesh carries for it). The viewer draws the look in
Solid, Shaded and Preview, and a plain finish in X-ray and Parts. In Solid and Shaded a file's
finishes reflect the studio's neutral environment on those surfaces alone, so a part with no
material is drawn as ever; an engine document's reflect its look's environment, which lights every
surface of it, and OCCT's stills draw them the same way (**The look**). A part's chip card and
`cadgen inspect` weigh it: volume by density, summed over an assembly.

## Imports

`read_step(path)` reads a `.step`/`.stp`, `read_xbf(path)` an engine document; both copy the
file's geometry into the model's document (`reader.py`). The result is a compound tree of the
file's assembly: an assembly a `Compound` of its components, a part a handle of its own on its
product's geometry (a move places that occurrence, never its siblings), every node named as the
file names that occurrence (its own name, else its product's), coloured and given its material
as the file has them; an xbf's painted faces and face materials come too, and each element keeps
the name its file gives it (**Element names**). An xbf's joints, configurations and motions are
not imported: a part is a part. Linking between models is done by importing code, never by a
file reference. Both are file reads the memo keys by the file's bytes, so a later build's read
of the same bytes is the same objects, and both are the build closure's inputs.

`read_mesh(path)` reads an `.stl` as data, never a shape: a `Mesh` of `vertices` (N x 3, the
file's numbers as millimetres; a point the triangles share is one vertex), `triangles` (M x 3
rows of indices into them), `name` (an ASCII STL's solid's, else the file's stem) and
`bounding_box()` (build123d's `BoundBox`), its arrays read-only. A mesh has no B-rep -- no
surface under a face, no curve under an edge -- so no document holds one: a model measures it
and builds B-rep from its numbers. Its read is keyed by the file's bytes as the others' are,
the same object again for the same bytes, and the file is one of the closure's inputs:

```python
@xbf("XBF/enclosure.xbf")
def enclosure():
    pcb = read_mesh(HERE / "scans/pcb.stl").bounding_box()   # keyed by the scan's bytes
    return bd.Box(pcb.size.X + 6, pcb.size.Y + 6, pcb.size.Z + 4)
```

A result holding a mesh face -- a triangulation with no surface, as build123d's `import_stl`
makes, or a face a model builds of `read_mesh`'s triangles -- is refused by the occurrence's
path before its document is made (`document.mesh_faces`), and the worker builds on: `kit/scan
is a mesh, not B-rep: face 1 is a triangulation with no surface (as build123d's import_stl
makes), and a document holds B-rep alone. Read the mesh as data with read_mesh(path) ...`. The
kernel's face modifier, which every part passes through (`document.direct`), crashed the
process on one.

build123d's importers (`import_step`, `import_brep`, `import_stl`) are file reads the memo keys
by the file's bytes too: a body that calls one is kept and replayed while the bytes are the same.
build123d's `Mesher.read` and OCCT's readers driven directly read a file past the engine: a
body that calls one runs on every build (**Body retention**).

**The fast input is an xbf.** Reading one is many times faster than parsing a STEP of the same
geometry (tom-sized: seconds against most of a minute) and keeps the engine's names losslessly.
Convert a vendor STEP once, keep the xbf beside it, and read the xbf:

```
cadgen export vendor.step vendor.xbf
```

The conversion is the author's: the engine writes no derived file beside an input of its own.
`read_xbf` of a converted STEP is `read_step` of the STEP: the same geometry, names, colours and
materials.

**A STEP is parsed in a reader process.** OCCT's XCAF reader works in many times the memory of
what it makes (2.3 GB for a 354 MB file) and the allocator keeps most of it, so a worker that
parsed a STEP would hold that for its life. A build starts one reader process on its first STEP
read, reuses it for the build's other reads and closes it when the build ends; the reader
answers with the document described as data (products, names, colours, materials, element
names, components) and one `BinTools` dump of the parts' shapes and the components' locations,
and the worker assembles the tree from them. A shape written and read once is what a saved
document reads back, so the tree is a function of the file. An xbf is read in the worker by the
document's own retrieval driver.

**A STEP is the file it is.** A STEP can name other files as its parts (an external document
reference, `DOCUMENT_FILE`), which the XCAF reader's transfer would open -- beside it, above it or
anywhere by an absolute path -- and add to the document as the STEP's own. Every STEP read
(`read_step`'s reader process, and the read behind the viewer, an export and a snapshot) checks
the parsed file before it transfers it and refuses one that names another file
(`document.refuse_external_files`).

## Placements

A part used ten times is one prototype placed ten times, in the worker's memory as in the
document, as FreeCAD's `App::Link` places one. build123d places a shape by deep-copying it
-- `moved`, `located`, `copy.copy`, and the transforms, which deep-copy before they replace
the copy's geometry -- and its deep copy runs `BRepBuilderAPI_Copy` on every node, so each
placement of a vendor assembly was a whole new B-rep. Under the memo a deep copy makes new
objects of the same classes, each with its own label, colour, material, paints, joints and
children, and each a new handle on the SAME `TShape` (`kernel/memo.py`, `_sharing`); so
does `copy.deepcopy(shape)` in a model. A model that wants a B-rep of its own copies it
with `BRepBuilderAPI_Copy`.

build123d's own operations never change a shape they are given in place. `ShapeFix_Shape`
does (it fixes the sub-shapes it is handed): run by a model on a shape a placement shares,
it is given a copy of that shape first, a `copy` feature of the model's, and the other
placements stay as they were (counted: the memo's `copied_on_write`). A `BRep_Builder` a
model drives itself on a placed shape is not seen: it changes every placement.

A file read again in one build from the same site -- a helper reading a screw for each
place it goes -- is decoded once: the read hands back the first read's tree again, new
objects on the same TShapes. A read from another site is another feature, named apart, and
decoded apart: one B-rep carries one set of names.

The document keys a part by its TShape, orientation, paints and materials
(`document.collect`), then merges parts of one geometry key whose elements are named alike
and which hold the same colour, paints and materials (`document.merge`): a helper building
the same bracket for each place it goes is one prototype too. Placements painted or given
materials apart are prototypes apart, the second its own topology over the same geometry
(`document._apart`: the shape tool holds one label per shape).

## Mesh

One tolerance, FreeCAD's default, configurable nowhere: a linear deflection of
`(Lx + Ly + Lz) / 300 * 0.5` of the part's own bounding box (FreeCAD's
Deviation of 0.5 %) and an angular deflection of 28.5 degrees, both absolute,
with the kernel's face parallelism on, through `IMeshTools_Parameters` with
`EnableControlSurfaceDeflectionAllSurfaces` set (analytic faces held to the
deflection; every other knob stays at its default). `BRepMesh_IncrementalMesh`
is used as it is: no check before it, no second pass, no finer retry, no other
tessellator. A face it leaves without triangles is left out and named: the
part's structure lists it under `unmeshed` (ordinals) with a verdict under
`unmeshedCheck` -- the mesher's own status first (`GetStatusFlags` of the
part's mesh), then `BRepCheck_Analyzer`'s on that face ("BRepMesh:
SelfIntersectingWire; BRepCheck: valid") -- and the rest of the part is drawn.
A part is meshed from its binary shape bytes read into a fresh shape, so its
mesh is a function of those bytes alone. Those are its read-back bytes, the
bytes its document holds of it. A build's live part is written and read once to
get them, as saving its document does. A part read from a document (the served
document, `cadgen export`) is written as it was read. So a worker, the
server and an export all mesh one geometry key from the same bytes.
The geometry key is the digest of those bytes (`document.geometry_key`), so a
reader makes a part's key again from the part it read, and takes the key the file
names for it only when the two agree (`document.Loaded`). Where one part naming a
key does not make it, the parts naming it are keyed apart, by the key and their
own keys together (a placement's look kept apart is such a copy, and keeps one key
with its first). The daemon's caches are shared by every document it serves, so a
file never lends its part another document's key, and never its mesh or facts.

Every edge has a class read from the B-rep: 1 feature (two faces at an angle),
2 tangent (two faces meeting at least G1), 3 seam (a face closing on itself),
5 boundary (one face), 6 non-manifold (more than two). Degenerate edges are left
out.

What the kernel measures of an element is asked for, never extracted ahead:
`GET /api/doc/<id>/part/<key>/face/<ordinal>` is its area, centroid, surface
type, exact bounding box and `BRepCheck` verdict (and a round face's radii);
`.../edge/<ordinal>` its length, curve type, class, faces and endpoints (and a
circle's radius and sweep); `.../vertex/<ordinal>` its position;
`.../groups` how a pick of one face or edge grows, as a STEP's selector table
says: each face's tangent group (faces joined across tangent edges of one
solid) and each edge's chain (edges that run on through a shared vertex). Each also answers `made_by`: the element's name, the feature that made
it (its name's last step), that feature's operation, the function, file and line
of its call, and, for a name that folds its derivation, the derivation spelled
out. It comes from the trace of the worker that built the document, asked over
the worker's pipe (a `where` request, answered by the worker's reading thread,
during a build too) and never from a file: a document served cold, with no live
worker that built it (for example, after a daemon restart), answers
`made_by: null`, and so does an element the served version names otherwise than
that worker's last build. The line is the call's in the run that named the part.
`cadgen inspect DOC REF` serves the document on demand and resolves `REF` (**References**):
an element answers its facts and `made_by`, with its canonical `ref`, its occurrence's `path`
(`hand/finger.2`), its part, key, kind, ordinal and name, its points (centroid, position,
endpoints, box) placed where that occurrence stands; a part or an assembly answers what it
weighs: each part's volume, measured on its solids (`.../part/<key>/volume`), times its material's
density, summed -- `{ref, parts, volume (mm³), mass (kg, null when no part has a material),
unweighed (the parts without one, by path)}`, and for one part its path, material and density.
A ref of several selectors answers a list. A ref that names nothing, or several things where
it names one, is refused by name (exit 2).

## Wire format

`GET /api/doc/<id>` returns the structure as JSON: prototypes (key, name,
colour, `faceNames`, `edgeNames`, `vertexNames`, `faceColors` by ordinal, `material` and
`faceMaterials` by ordinal -- each every field of the `Material`, named in camelCase
(`youngModulus`, `transmissionColor`, ...), its colour the base colour it is drawn in, SI
-- and once meshed `unmeshed`/`unmeshedCheck`), instances (prototype, path, a 4x4 world matrix,
colour), the tree, the document's version, and for an assembly with joints `kinematics`: the
links (name, the instances each moves, its frame as built), the pairs (label, type, the two
links, the two frames as 4x4 matrices in their links' frames, limits and units per value), the
ground link, `asBuilt` and `configurations` (name → joint → value: a number, or a list for a
cylindrical or spherical pair), `couplings` (name → `{range, terms}`), `motions` (name →
`{duration, ease, keys}`, each key `{t, configuration}` or `{t, values}`), `loop` (the pairs
closing a loop, or null) and the build's `warnings`. A page poses the instances from it: each link's
placement at the values over its placement as built, applied to its instances.
`POST /api/doc/<id>/pose` (`{"pose": NAME | {joint: value}}`) answers the id of the
document served at that pose, its `kinematics.pose` the values it stands at.
`GET /api/look` is the look the regular display modes are drawn in (**The viewer and the
snapshot**), the same for every document; `GET /api/look/environment` is its environment, the
Radiance image `render/studio.hdr`.
`GET /api/doc/<id>/version?after=V&wait=S` answers as soon as the version is not
`V` (or after `S` seconds, at most 60): the page waits on it, so a build's patch
reaches it at once. The answer carries the patch's timings.

Between the worker and the daemon a patch is one frame on the worker's pipe: a
JSON line `{"id", "patch": {"path", "structure", "meshes": [[key, size,
unmeshed]], "shapes": [[key, size]], "timings"}, "bytes": N}`, then exactly `N`
bytes: the meshes' buffers, then the shapes' binary shape bytes, in the order
listed.

`GET /api/doc/<id>/part/<key>` returns one part's buffer. A client reads it
with typed-array views, without parsing. The header grew from 64 to 80 bytes in
`XBM2` (the vertex table's count and offset did not fit). The 80-byte
little-endian header is:

| Bytes | Field |
| --- | --- |
| 0-3 | magic `XBM2` |
| 4-7 | format version (2) |
| 8-31 | counts: nodes, indices, faces, edges, edge points, vertices (u32 each) |
| 32-59 | byte offsets of the seven arrays below (u32 each) |
| 60-67 | linear and angular deflection (f32 each) |
| 68-79 | reserved |

Then the arrays, each 4-byte aligned: positions `f32[N*3]`, surface normals
`f32[N*3]`, triangle indices `u32[I]`, the face table `u32[F*3]` (face ordinal,
first index, index count; an unmeshed face's count is 0), the edge table
`u32[E*4]` (edge ordinal, first point, point count, class), the edge polylines
`f32[P*3]`, and the vertex table `f32[X*4]` (vertex ordinal, x, y, z) of every
vertex of the part. Ordinals are the part's `TopExp.MapShapes` ordinals, the
same ones its element names use. Selecting a face reads a range of the index
buffer, an edge a range of the polyline buffer, a vertex a row of the vertex
table.

`POST /api/doc/<id>/mesh?mode=inline|processes[&drop=1]` meshes every part not
held yet (with `drop=1`, every part again), in parallel, and returns the time it
took, the bytes, the triangles and the unmeshed faces.

## Element names

Every face, edge and vertex of a part is named as FreeCAD's topological naming names
it: by the feature history that made it, so it keeps its name unless that history
changed (`kernel/trace.py`). A name is its kind and its derivation: the atom it
starts from, the n-th element of its kind a feature made, and a step per feature that
made it out of another (`f:plate.body.3;M:plate.relief`: face 3 of the box, modified
by the relief cut). A long derivation folds to its last feature and a digest
(`f:plate.relief~5d1e0c2f9a3b`); the worker that built it spells it out. Every name is a
reference the CAD Viewer's ref grammar parses (`cadRefs` in the bundled `@text-to-cad/core` runtime, mirrored as
`kernel/trace.py`'s `ELEMENT_NAME`): a feature name has at most one dot, every segment
is an identifier, and an atom ends in a number or a digest.

A feature is the author's name for its result. A call whose result an assignment
stores is `<function>.<target>` (`relief = body - hole` in `plate` is `plate.relief`;
`self.body = ...` is `body`; each target of `a, b = ...` names its own); the calls the
same statement made on the way are `<function>.<target>_<operation><n>`
(`plate.relief_make_cylinder1`). The first statement in a function to assign a target
names it as it is; a later one -- a reassignment, `plate = plate - hole` -- is identified
by its statement's skeleton, its syntax tree with every literal (number, string)
masked: it is `<target>_<tag>`, the tag six letters of that skeleton
(`plate_cfjpgj`), counted only among the statements of the same skeleton in the
function (`plate_cfjpgj2` for the second, or for a loop's second run). So inserting a
step of another shape renames none of the steps around it, and a dimension edit -- a
literal -- keeps every name. Two statements of one skeleton still count in order:
inserting one before another of its shape renames the later one, and a statement
inserted before a function's first assignment to a target becomes the one named as it
is. A helper that makes a shape in its `return` statement and hands it back unassigned
(`return bd.Pos(x, 0, 0) * bd.Cylinder(r, h)`) makes it for its caller: its calls are
named by the caller's assignment the result flows into, as the calls that statement
made on the way (`plate.plate_cfjpgj_make_cylinder1`), through further helpers that
return it too. A call whose result is assigned nowhere (a return expression of the
model, an expression statement) is `<function>.<operation><count>` (`plate.fuse1`),
counted among the part's unassigned calls. Nothing is counted in an order OCCT picks: calls
given pieces of the same features' results (a loop over a sketch's faces) count by where
their pieces are, a compound's own elements are numbered piece by piece in that order, and
elements still named alike take `;D2`, `;D3` in it -- OCCT hands a boolean's or a text's
pieces back in an order the heap sets, so two cold builds would otherwise name them apart. So inserting a feature renames only what it
touches, and renaming a variable renames that feature's elements and nothing else. An author's `label` on a shape handed to a later construction
names, in what that construction makes, the feature that first made the labelled shape
(back along what each feature was made of, to where the shape stops being one chain):
a cut appended to it after takes nothing over. A shape a model places, copies or fixes past
build123d, with OCCT's `BRepBuilderAPI_Transform`, `_GTransform` or `_Copy`,
`ShapeFix_Shape`, `ShapeUpgrade_UnifySameDomain` or `BRepFilletAPI_MakeFillet`, is a
feature like any other (`kernel/memo.py`, `_MAKER_FEATURES`): its elements are named
from what the maker reports, or, where it reports nothing, from the shape it was given
by ordinal when the two map one-to-one. A placement copies nothing (**Placements**): a
placed part is its prototype and has its prototype's names, whichever placement the
model labelled. A label on one of several shapes a feature made -- one part of a file
read -- names what is made of that shape alone, never what is made of its siblings; and
placements of one shape labelled apart name their occurrences and pin none of those
labels on the shape they share, where one placement's label would rename what is made of
every other.

An element of a shape read from a file (`read_step`, `read_xbf`) is named within its own product,
the part of the file it belongs to, however often the file places it: by the name the
file gives it (`read.stepcaf.subshapes.name`; a STEP this engine wrote names every face,
and those names come back as they were; `NONE`, the schema's empty name, is none),
else by its ordinal in the product
(`f:<feature>.<ordinal>`), never by an ordinal across the file. A placement or a compound
of a shape no name reaches never claims its elements as its own.

A warm build that hands a part back unchanged keeps its names
while the functions they come from assign the same targets; a rename names it again.

A child model or a `@memo` function names what its `return` statement makes in itself
(`stage.cut1`), never by its caller's assignment as a plain helper's return is: the engine
calls it, and a replay cannot follow the caller. So marking a helper that returns a
construction unassigned (`return body - holes`) renames those elements once; marking one
that returns an assigned name (`return body`) renames nothing.

## References

A ref names a part, an assembly or one element of a document in the engine's own names
(`refs.py`), and it is resolved by name in the document as it is now -- the latest build. Nothing
of an earlier build is kept: an element a later build moved or resized resolves to where it is
now; one it deleted fails, naming it; one whose making changed (a feature started or stopped
touching it, so it is named otherwise) fails too, listing what its atom is named now (`plate.body.6
is now f:plate.body.6`), never picking one.

```
REF      = [FILE "#"] SELECTOR ("," SELECTOR)*     a bare ELEMENT after an owner is that owner's
SELECTOR = OWNER | [OWNER "/"] ELEMENT              no OWNER: the document's root
OWNER    = SEGMENT ("/" SEGMENT)*                   an occurrence's path, or its last segments
SEGMENT  = LABEL | LABEL "." N | "QUOTED" ["." N]   N: the N-th of the siblings so labelled
ELEMENT  = NAME | face N | edge N | vertex N        NAME: f:…, e:…, v:… (Element names)
```

An occurrence is named by the labels on the way to it. A label its siblings share takes its
number among them, in component order: `hand/finger.2` is the second component labelled `finger`
of `hand`, and a repeated part is always addressed by such a path, never by a number across the
document. An owner may start at any level (`palm`, `finger.2/face 7`) where what it names is one
occurrence; a path whose first segment names the root is read from the root. A label that names
several occurrences is refused with their paths (`finger names 3 occurrences in hand.xbf:
hand/finger.1, hand/finger.2, hand/finger.3`). A segment is read as a label first and as `LABEL.N`
only where no sibling bears it whole; a label holding `/`, `,` or a quote, or one that would read
as another sibling's, is JSON-quoted. An element of an assembly resolves from it when one part
below holds it, so a document of one part takes its elements by the document's name
(`plate/face 3`). A part's elements are numbered by their `TopExp.MapShapes` ordinals, the ones
its names, `faceNames` and the XBM2 buffer use. `FILE` (everything before the first `#`,
JSON-quoted where it holds one) is an absolute CAD file path, the last segments of the document's
path, or a document's id (a model's, which `python SCRIPT.py` prints, or a file's), and must be the
document resolved in: the same file, the same path's last segments, or the same id. A script is
never a `FILE`: `<uuid>#face 1` names face 1 of the model whose id it is, read as the engine holds
it. A canonical ref -- what `inspect` answers --
spells the element by its name (its ordinal only where it has none) under its part's label where
that label names one occurrence, else under the occurrence's path from the root; in a document of
one part, under the document's name. It is also what the CAD Viewer copies of an `.xbf`'s selection,
the file's path first (`/work/XBF/kit.xbf#kit/hand/finger.2/face 7`), or a model's id first for a
model the engine holds: the viewer's parser and speller
of this grammar (`cadRefs` in the bundled runtime) are held to this module's, case for case, by a
fixture both suites assert.

A ref resolves inside the engine, for `inspect` and the viewer, never in a model:
`cadgen inspect DOC REF` (`cadgen.inspect(source, ref)`) answers what it names, placed where its
occurrence stands -- an element's kind, ordinal, name and canonical ref, the kernel's facts of it,
and `made_by`, the feature and the function, file and line of the call that made it; a part's or
an assembly's volume and mass. A model that changes what a person picked reads that answer and
edits the code `made_by` names, or selects the element from the live shape with build123d
(`base.faces().sort_by(bd.Axis.Z)[-1]`); a check reads the document with `read_xbf` and walks its
tree by labels.

**A model never reads a file its own build writes**: its own xbf or export, a child's, a
sibling's (`reader.refuse_written`: `read_xbf` and `read_step` ask as they read the file). Read,
the file would be an input the build rewrites -- its key moving on every build, so the model would
never be taken from its file -- or, kept out of the key, a model depending on its own past. A
model takes what it makes from the live shape instead: so its own output never invalidates it.

## Body retention

A body -- a model's, or a `@memo` call's (**Memo functions**), whose key also holds its
arguments -- is one coarse entry above its calls, kept in the worker's memory
(`kernel/memo.py`, `body`). Its key is what it is made of:

- the symbols its function reaches (`sources.py`, `Symbols`): the global names
  its code and the code nested in it load, read through module attributes, its
  defaults and closure cells, and from there, transitively, every first-party
  function, class, child model and value. A function counts by its code: its
  instructions with their constants and names, its variables, arguments and
  flags, but not its file, its lines or its docstring. A class counts by its
  bases and its attributes. A value counts by a canonical form: numbers,
  strings, containers, enums, build123d vectors, locations and colours, numpy
  arrays, first-party dataclass and class instances. Each global binding the
  code reads counts as what it is bound to, by the module that holds it, so
  rebinding a name is an edit. The walk stops at what is not first-party (the
  standard library, build123d, OCP, numpy): the engine's own code covers those;
- every file it reads through the engine, by its bytes: `read_step`, `read_xbf`, `read_mesh`,
  and build123d's importers (`import_step`, `import_brep`, `import_stl`), which the memo keys
  as it keys the engine's readers;
- every file it reads itself, observed, by its bytes: an audit hook on `open`
  (`kernel/memo.py`, `_audited`) hears each file the body opens for reading
  (`open`, `json.load`, `Path.read_text`, `np.loadtxt`), Python's own files
  aside (a `.py` or `.pyc`, one of the standard library or an installed
  package). When the body returns, each is held as its size, mtime and blake2b
  digest, or as missing. On the next build a file with the same size and mtime
  is the same; one whose stat moved is hashed again, and the same bytes keep
  the body (and the new stat); other bytes, or a file gone or come, run it. A
  file opened only for writing is an output, not an input. A pipe, a socket or a
  device has no bytes to hold: the body runs on every build, and the report's
  `retention.fallbacks` names the file. `retention.reads` lists, per body, the
  files it read;
- the engine's own code.

A model's inputs are its code, what it reads through the engine, and every file
its body reads, observed, by their bytes. A file read past the engine's readers is read
in C or C++, where the hook on `open` hears nothing, into a shape no key names: build123d's
`Mesher.read` and the OCCT readers a model may drive itself
(`STEPControl_Reader.ReadFile`, `STEPCAFControl_Reader.ReadFile` and `.Perform`, IGES's
readers, `RWStl.ReadFile_s`, `StlAPI`, `BRepTools.Read_s` and `BinTools.Read_s` given a
path, `RWMesh_CafReader.Perform`: glTF's and OBJ's; `kernel/memo.py`, `_READER_TARGETS`).
A body that calls one is never retained, so any edit runs it whole, and `retention.fallbacks`
names the call: `reads ../part.brep through OCCT's BRepTools.Read_s: its body is never retained
(any edit runs it whole); use read_step/read_xbf/read_mesh`. (build123d's `import_step`,
`import_brep` and `import_stl` are not on that list: the memo wraps them as operations keyed by
the file's bytes, as the engine's readers are, so a body that calls one is kept.) The file it named is one of its
inputs all the same, held to its bytes (a read of what is no regular file leaves its closure with no
key): a build with nothing changed takes its document, after a restart too, and one after the file
changed builds it. What the engine
cannot see is the author's: the clock, environment variables, randomness, a file only
tested for (`Path.exists`, `os.stat`: an open is heard, a lookup is not), a folder listed
(`glob`, `os.listdir`: a file added to it is not heard), and a file a C library opens for
a reader not on that list. The engine hears Python's `open`, its own readers and the calls on
that list, and none of the rest: no interposer on the C library's `open` hears every open by
any code (an OCCT reader of any name, a C extension's own reader, FreeType loading a font
outside a text), every folder listing, environment variable or program a model's code used.

A module falls back to its bytes, and those of every first-party module it
imports, wherever the walk cannot follow a reference by its value: a `getattr`,
`setattr`, `hasattr` or `delattr` with a computed name, `globals()`, `locals()`,
`vars()`, `eval`, `exec`, `compile`, `__import__` or `importlib` in a function
the body reaches (that function's module falls back); a `from x import *`; a
first-party module the code holds as a value (stored in a local it uses other
than to read attributes, passed, or put in a container); a module a function
imports when it runs that the script's load does not import (whether it is in
memory would depend on which bodies ran); a value with no canonical form (a
shape made at import, an open file). Where no module holds what cannot be
keyed, the body always runs. The report's `retention` gives the time keys took
and, per body, each fallback with its reason.

When the key is what it was in the body's last run in this worker, the body is
not called. That run is replayed instead: each entry it hit or made is bound to
this run as a hit binds it, and each feature it recorded is recorded again, in
order. The result is the same live objects, as the body returned them. The trace
is the one a run leaves, so names, the xbf and the caller's own calls come out as
if the body had run. A body that ran a call plain, or whose entries are gone, runs.

Beside a model body's run the worker keeps its **harvest** (`kernel/memo.py`, `harvest_of`):
what the build made of the result's joints, mechanism states, configuration sequences (a
function's samples) and animations (`document.Harvest`), with the tree it was made of (each
prototype's TShape, label, colour and placement) and the files the sequences' functions read.
The harvest is a function of the result as the body returned it and of the code that made it,
which the body's key covers: a function of time is code the body reaches, wherever it is
defined. So a build that replays the very run the harvest was made from, to the same tree, and
whose functions' files hold their bytes, hands it back instead of sampling again; the report
says `"harvest": "reused"` (`"run"` where it was made), and `cache.reason` ends `the harvest
reused`. A body that ran makes a record with none, a verifying build harvests afresh, and
functions that read what cannot be held to its bytes are sampled on every build. It is memory
only, gone with the body's record, and what it writes -- the xbf's mechanism, animations record
and closure, the GLB, the served structure -- is a fresh harvest's, byte for byte. On tom, a
no-op's `collect` went from 1.50 s to 0.03 s, and the run from 2.47 s to 1.01 s.

Retained bodies follow the memo's retention: what the last four builds used. An
edit to a constant or a function re-runs the bodies that reach it, and the
bodies that hold their results. A comment, a blank line or a docstring re-runs
nothing. An edit to the root re-runs the root alone. A changed input file
re-runs the body that reads it and the bodies that hold its result. The
report's `memo` counts `bodies_run` and `bodies_skipped`, and `bodies` says of each
body of the model how it went: `run` or `replayed`.
`CADGEN_ENGINE_BODIES=0` turns retention off and nothing else. Otherwise a body
must be a function of its inputs: a body that reads the clock or the environment
is not seen to change, and nor is state one body leaves in a module for another
(a registry it fills). A
replayed body's features keep the `file:line` of the run that recorded them,
so after a line-only edit the provenance the worker serves can name a line that moved.

Keys are worked out once a build, for every body the build asks about, against
the namespaces as they are when the first body asks. A code object is read once
per value of it (a module loaded again makes equal code objects), and a file's
dynamic spots once per digest, in the worker's memory.

Measured on a 60,000-call model whose 14 bodies all ran, the logging added
nothing measurable to the build (body 12.4–12.6 s, against 12.7 s with retention
off). The logs do keep about a million more objects alive (2.6 million against
1.6 million). The worker's cyclic collection after each build has to walk them.
Measured with retention on, that collection takes 2.0–2.2 s on a 987-part model,
about 1.3 s of which it also takes with retention off, and 0.7–0.8 s on a
619-part model. It runs after the answer, so only a build sent while it is still
running waits for it.

The read hook costs nothing measurable: on a small model, built in-process, a
no-op took a median 50–51 ms and an edit 0.89–0.95 s with the hook, against
51 ms and 0.89 s with no hook installed.

## Memo functions

`@memo`, bare, marks a function the engine may replay instead of executing (`model.py`,
`Memo`). A call of one inside a build is a body (**Body retention**), named by the
function and a digest of its arguments (`parts.py::wheel(3f2a…)`, the report's `bodies`):
its code is keyed as a model body's is, its kernel calls are logged, and a later build
with the same key replays it -- the same live objects, its features recorded again, so
names and provenance are what a run leaves. A second call with the same arguments in one
build is a new placement of the first's result, as a child model's is. It declares and
writes no file. Outside a build it is its function. Its contract:

- **Arguments by value**, snapshotted at the call (`memo.call_key`): None, bools,
  numbers, strings and bytes, tuples, lists and dicts of them (in order, at most
  `memo.ARGUMENT_VALUES` values), enums and paths; build123d's value types (`Location`,
  `Vector`, `Axis`, `Plane`, `Color`, `Rotation`) and a `Material`; a shape this process's
  operations made, by its memo key, and a replay needs that very TShape again. A call
  given anything else -- a callable, an arbitrary object, a shape made past the engine,
  too many values -- runs every time, as a plain call of its caller.
- **Geometry back**: a shape, or a tuple, list or dict whose leaves are shapes. A call
  returning anything else runs every time it is called (its log stays, for the bodies
  that called it).
- **OCCT's own makers**: a shape the call made past the engine -- an OCCT maker no key
  names, a hand-built B-spline surface made a face -- is keyed by the call itself
  (`memo.adopt`): when every shape it returns is such a shape, the result is one operation
  of the caller's, keyed by the call's name (its function and arguments) and by which run of
  it made them, and registered, so what the caller makes of them is keyed and kept. A replay
  hands back those very shapes, and the operation is a hit; a run of the call makes others,
  and a miss. Inside the call, a build123d operation on such a shape is unkeyed and keeps
  the call running: it returns them as made.
- **No methods**: `@memo` on a function whose first parameter is `self` or `cls` raises
  at decoration.
- **Pure**, the author's part: it reads only what its key holds -- its arguments, the
  code and values it reaches, the files it opens -- and writes nothing outside itself. A
  module global it sets for another function to read, a cache it fills on a shared
  object, an argument it mutates: none of it is seen, and a replay leaves it undone.

Each call that runs every time is named in the report's `retention.fallbacks` with why.
The restart key (**Build closure**) folds a `@memo` function's code in as it folds a
child model's.

**When to mark a function.** `@memo` saves only the Python cost of the kernel-memo hits a
replayed function avoids, 0.1–0.4 ms per hit, so mark a function only when it holds seconds of
kernel work an edit elsewhere leaves untouched: roughly a thousand kernel calls or more. Never
per part, never on a helper called many times; whole sub-assembly stages are the usual
candidates (tom's six stages, movement's three layers: 1.3–3 s each, and twice as fast on an
edit), while per-part markers measured under 0.1 s. Nested `@xbf` is never needed for caching:
the operation-level memo handles every kernel call in any model, markers or not.

A verifying build (`Model.build(verify=True)`) runs every
body the memo would replay -- a model's and every `@memo` call's -- and compares each fresh
result with the logged one: per shape its class, label, colour, paints, material and
placement, and each leaf's geometry: the same TShape, else the same binary BRep digest, else the
same geometry in another order of the BRep's entries (each face's area and centre, each edge's
length and centre, each vertex, sorted: what an order-only difference leaves alone, see **Known
and accepted**), which is `same`. The report's `verify` gives each body checked
as `same`, `differs: <where>`, or `follows <function>` for one whose result holds a body
that differs. A function whose result differs is marked to run on every call for the
worker's life (`memo.always()`), the bodies that call it with it, and a model that calls it
is not taken from its file. A verifying build does not ask the previous document.

## Known and accepted

Two byte-level drifts are accepted, on one condition: no bug and no major impact. Each is
the same geometry and the same names written in another order.

- **A replayed body's BRep order.** A body the memo replays can write its BRep entries in
  another order than its cold run did (the f1's casing, the f14d, the radial's barrels).
- **Parallel booleans on a cold build.** OCCT's parallel booleans can order one result's
  sub-shapes differently from one cold build to the next (the w16, 3 of 794 parts; tom's
  yokes; the moonwatch's tachymeter).

Why that holds, checked:

- **Nothing keys on a document's bytes.** The restart key is digests of the model's code
  and inputs and the format (**Build closure**); a derived file is translated from the
  document, and the write compares bytes only to leave an identical file untouched. The one
  place a document's bytes count is a document *read as an input* (`read_xbf`, `read_step`
  of another model's file), which is keyed by its bytes like any input: an order-only rewrite
  of that file builds the reading model once more, to the same result.
- **Names and refs resolve alike.** On the moonwatch's case (its tachymeter one of these),
  a cold build, a body re-run whose 2,673 kernel calls all replayed, and a second cold build
  in a new daemon wrote three different files of one size; their 15,646 element names are the
  same set, each on the same geometry (a face's area and centre, an edge's length and
  centre, a vertex's point), and refs resolve to the same elements through `cadgen inspect`.
  `test_memo_marker.py` holds the same for a cold build, a replay and a second cold build.
- **`--verify` reads it as `same`.** A leaf whose BRep differs only in order measures alike
  (**Memo functions**): a verification reports it `same`, never `differs`.

The snapshot's part listing (0.7's `--mode list`) is gone by decision: `read_xbf` and `read_step`
(a document's tree) and `cadgen inspect DOC REF` (what a ref names) are the facts route.

## Build closure

A model's xbf is its cache, as a FreeCAD document is its own: opened, it is what was last
computed, and only what changed is computed again. Its main label holds the model's build
closure (`previous.py`, a `TDataStd_AsciiString` beside the writer's, schema `cadgen.engine
closure/1`), pointers and digests only:

```
schema   "cadgen.engine closure/1"
engine   {"release": "cadgen 0.8.0", "format": "xbf/7", "digest": ...}   the format (keyed); the release and
                                                                    the engine's code digest (information only)
libs     {"build123d": ..., "OCP": ...}                             what decides the geometry
source   {"kind": "script", "path": "../src/tom.py", "function": "tom"}
modules  [["../src/lib/arm_parts.py", "9f3c..."], ...]
inputs   [["file", "../STEP/gripper.step", "c0de..."], ["read", "../src/lib/ids.json", "77ab..."], ...]
bodies   how many bodies the model is
key      one digest over the format, libs, source, modules and inputs; null where the
         closure cannot say all the model is made of
```

Beside it on the main label, a document whose build made an `animation()` holds the compiled
tracks as a second build record (**Animations**); the closure neither counts nor keys them: they
are what the code the key covers made.

Every path is relative to the xbf's folder. `modules` lists each first-party module the
script's load imported or the model reaches, with a digest of what the model reaches in it: its
functions' code objects with no line tables or docstrings, its classes, the values its bindings
hold (a path value inside the script's folder relative to it), and, for a module that falls back
to its bytes (**Body retention**), each file of its import closure by its bytes. A comment or a
blank line changes no digest; a module the model loads and does not reach holds the empty one.
`inputs` lists every file a body read -- through the engine (`file`: `read_step`, `read_xbf`,
`read_mesh`, build123d's importers), itself (`read`, a `null` digest for one it found missing;
a motion's function's reads too, **Configuration sequences**), or a text's font (`font`) -- by its digest; a file read past the engine's readers leaves the key
null (**Body retention**). `cadgen inspect DOC` prints the closure, `cadgen.inspect(doc)` and
`document.Loaded.closure` read it.

**When the format moves.** The key takes the engine's `format` alone (`previous.FORMAT`),
not the release that wrote a document nor a digest of the engine's code: a cadgen release,
or an engine edit, that leaves the written document alone keeps every xbf current. `FORMAT`
is bumped by hand (`xbf/6` to `xbf/7`) when what
an engine writes changes -- the document's structure, the attributes on its labels, the
closure's fields, or what the key covers -- and then every xbf builds once, cleanly: a
document of another format is "written by" another engine (`cache.reason`). The bumps so far:
`xbf/2`, the key left the release, the engine digest and numpy, and the closure its commit;
`xbf/3`, the mechanism subtree took AP242's form (**Kinematics**); `xbf/4`, a function
motion's samples are made for linear interpolation (**Configuration sequences**); `xbf/5`, files read by motion
functions join the closure (**Configuration sequences**); `xbf/6`, the closure counted the build's
animations, and a document with any was not taken; `xbf/7`, the compiled animations are a build
record on the main label, the closure counts none, and an animated document is taken like any
(**Animations**).

Before a body runs or is replayed, the build makes the closure again -- the script loaded,
its modules digested, each input hashed again -- and compares its key with the xbf's. The
same key, in an xbf written by this engine that reads whole, and the body is not run: the
report says `cache: {"used": true, "from": "file"}`, every file `written: false`,
`memo.bodies_loaded` the bodies the document is, `bodies` the root `loaded`, `timings` the key
(`key`) and the read (`read`). A later build in the same worker takes it from memory without
reading it (`"from": "memory"`): one taken, or one this worker built, whether or not the memo
could replay its root, so an unchanged warm build costs what a restart's second build does,
the key alone (the w16: 59 s replaying, against under a second). Its
bodies' memo entries count as used by that build, as a replay's do, so an edit after any number
of them still replays what it leaves alone. The memo replays the root instead only where a
file the worker's last build of the model wrote -- the model's own, or a child model's -- moved
or is gone, which the replay writes again (`cache.reason`: replayed from memory). Anything
else builds as before, and `cache.reason` says why: no file yet, a declared export missing,
written by another engine or program, a file that does not read, no key in it, replayed from
memory, or what changed, by name (`cache.changed`, each change; the CLI prints
`rebuilt: ../src/lib/arm_parts.py changed`): a module changed, is new or is no longer imported,
an input changed or is missing, the format, a library or the source moved.
`CADGEN_ENGINE_MEMO=0` and `CADGEN_ENGINE_BODIES=0` turn it off with the rest of retention.

The document is taken whole or not at all, never one body's part of it. OCCT's BinXCAF
reader does not give back the doubles it was given: it makes each direction and placement
anew, and a direction made again is normalized again, a rotation orthogonalized again,
one unit in the last place apart. Measured on the corpus: an `l_bracket` read and saved
is four doubles apart, and `motorbike` read and saved twice is 3,839 bytes apart from
once (no fixed point). A document holding a body's result read back would drift from the
cold build's bytes, build after build. So what is written is always made from what this
process's bodies made, and a document read is never written or patched: the first edit
after a restart runs the model, and writes the cold build's bytes. A taken document has
no worker that built it: `made_by` is null until a build of it runs.

## In-memory models

`@model` declares a model with no files; `@step`, `@xbf` and the other file decorators declare a
model with those files. A function is declared by one or the other, never both: `@model` stacked
with a file decorator is refused, saying to drop `@model`. A declaration does no work. Call the
function explicitly to build it:

```python
from cadgen import model

@model
def bracket():
    import build123d as bd
    return bd.Box(10, 20, 3)

if __name__ == "__main__":
    handle = bracket()
```

The document's id is `bracket.id` (and `handle.id`): uuid5 of the script's canonical path and the
function's name, the same in every process (**Architecture**), or `@model(key="bracket")`'s
`uuid5(NAMESPACE, "key::bracket")`. Different scripts can use the same function name. Running the
script again with changed code updates the same document and open viewers; `python parts.py`
prints each model's `id:` and `view:` lines (`<engine>/<id>`), and `handle.url` is the page. No list
of ids is saved.

`cadgen serve ID`, `cadgen snapshot ID view.png`, `cadgen export ID part.step`, and `cadgen
inspect ID 'face 1'` take the id; `cadgen inspect 'ID#face 1'` uses the same reference syntax.
Each reads the document the engine holds, as it is: editing the script changes nothing until
Python runs it again, and no verb imports, runs or builds a script. An id the engine no longer
holds (evicted, expired) is refused with its state and the command that builds it again
(`python <the program that built it>`; **Document lifetime**).
`--query build` returns saved-file metadata/closure or live-build metadata; `--query closure` and
`--query geometry` select the other queries explicitly. In the CAD Viewer a model's page is
`/<id>`; it has no file of its own, so no Select File and no file menu.

A shape with no function -- a REPL's, a notebook cell's -- is handed over instead: `model(shape,
name="bracket")` returns the same kind of handle (**Shapes handed over**).

Ids live in [ids.py](ids.py), document names (a CAD file's path or an id) in
[addresses.py](addresses.py); the daemon's transient book of live models, by id, lives in [models.py](models.py).
