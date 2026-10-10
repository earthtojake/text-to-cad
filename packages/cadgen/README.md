# cadgen

The published distribution: everything that turns CAD source into documents,
documents into derived state, and derived state into pixels and meshes. One
PyPI package carrying the Python engine under `src/cadgen/` and what it executes
that is not Python under `src/cadgen/_runtime/`: the shared JavaScript runtime and
the CAD Viewer's client, bundled in at build time (the JS *source* lives in its own
packages and never ships as source), and the native file tracer, one library per
platform.

**PURPOSE** — the engine and its command surface: model execution, the
store, document assembly, kinematics, exports, validation, inspection,
snapshots, the warm daemon and its build pool, the CAD Viewer
(`cadgen viewer`: a local HTTP server over the built client, on port 3245 or the
port `--port` names, serving every CAD file by its absolute path), and CAD beside an agent's chat (`cadgen mcp`: an MCP App server that
an agent host starts, over the viewer's own routes: tabs in Codex, viewer cards
in the chat for every other MCP Apps host).

**MAY DEPEND ON** — the Python ecosystem it declares (OCP/build123d lazily,
never at namespace-import time) and the bundled runtime.
Never app code, never JavaScript source at runtime.

**DEPENDED ON BY** — every skill (as a pinned installed distribution). The
CAD Viewer is not a dependent but a part: `cadgen.viewer` serves the client and
submits a document's compile as a job to the same build pool every door uses.

## The rest of the package's documentation

This file holds the LAWS. Two documents beside it hold the mechanisms the
laws constrain; a law that governs one links to it, and where a mechanism
document and this one disagree, the mechanism document is right.

| Document | What it is for | Go there when |
|---|---|---|
| [`STORE.md`](STORE.md) | The store's contract: layout, the two-sides law, tree/record shapes, the gate, invariants, link-vs-component, concurrency, GC, the daemon, lazy children, editing previews, debugging. Sectioned, with a table of contents | changing anything that writes to or reads from `~/.cache/cadgen`, or any build, door or reader that depends on it |
| [`SNAPSHOTS.md`](SNAPSHOTS.md) | Snapshots: display presets, what a mesh, robot or drawing snapshot draws (the CAD Viewer's own scene for it), requests and OUT, sizes, and `--debug --json` — every measured browser stage, what each one covers, and which durations must not be added together | changing what a snapshot draws or accepts, or reading snapshot timings |

## The design laws

These are LAWS, not conventions: a change that violates them is wrong even
when it works. Each carries a pressure-test to apply before writing code.

### 1. Generated files are totally independent of their source code

A generated file (STEP, DXF, STL, GLB, 3MF) and its sidecar
(`<name>.step.json`) stand alone, forever.

*Pressure-test*: a generated file must be fully readable — viewer,
snapshot, `read_scene` — by reading ONLY the generated file(s), the sidecar, and
the store's artifact side. Never the source. A file whose bytes have no tree
in the store is compiled from those bytes (`cadgen step compile` semantics),
never from source. Deleting every `.py` in a project must not change what
renders.

- Nothing a renderer reads references the source tree: the sidecar's
  kinematics are resolved numbers and labels, its appearance uses canonical
  leaf occurrence IDs, and its animation is keyframes over those IDs, sampled
  from the model's clips when it built — data, never code; a tree and its
  components carry no path, script or record key
  ([`STORE.md`](STORE.md) §2, the two-sides law).
- A door never refuses a document and never auto-rebuilds: whether a
  document is behind its script is the model's record's question, answered
  by `cadgen store why` and the build tree, never by a render path.
- Source scripts are PROGRAMS: run, never passed to CLIs, never parsed by
  renderers.

Three mechanisms live under this law rather than beside it, and each is
specified where it is implemented — change one by reading that section, not
this one:

| Mechanism | What it must not break | Specified in |
|---|---|---|
| Build status: the viewer's feed says whether a build of a file is running or failed, never what it previews; the viewer shows the saved file | saved-artifact read-back; no reader reaches source, closure or a model record | [`STORE.md`](STORE.md) §9b |
| Composition: what a decorated call returns, what a parent may consume before a child's save, and when an exact `Compound(children=[...])` keeps its children's pins | the link/component decision, declared-output completion, `isinstance(root, Compound)` | [`STORE.md`](STORE.md) §6, §9a |
| Display surfaces and meshes: canonical trees pin encoded BREP and effective intrinsic face colors; SURF extraction and OCCT meshing are artifact-only build-pool jobs under an attested producer, and cadgen is the only mesher — every client draws the store's meshes | geometry completeness stays separate from display readiness — `read_step`, STEP re-emits and parent materialization never wait for SURF or a mesh | [`STORE.md`](STORE.md) §2 |
| Tree composition: an all-link parent's saved-document tree composed from its children's document trees instead of parsed from the STEP it just wrote | `index/document` holds the cold compile of the written bytes, the same tree either way; every ineligible case parses | [`STORE.md`](STORE.md) §3 |
| STEP splicing: the same parent's STEP written from its children's saved STEP files instead of exported through OCCT | the cold compile of the spliced file is the exported file's; every ineligible case exports | [`STORE.md`](STORE.md) §3 |

### 2. The store contains only derived results

`~/.cache/cadgen` is the store: content-addressed objects (a model's result
tree and the components it is made of) and input-addressed index entries
(the per-model record, the document → tree map, bounds and tessellation
entries) — data derivable from sources and documents, and nothing else. Its
layout, formats, gate, two-sides law and invariants are the contract in
[`STORE.md`](STORE.md); read it before touching anything that writes to or
reads from the store. Where this document and `STORE.md` disagree, `STORE.md`
is right and this one is stale.

*Pressure-test*: everything in the store is (a) a pure function of some
source or document, (b) safely deletable at any time, and (c) rebuildable
by running the models again. If losing a store entry would lose information,
that information is in the wrong place.

**The store is what the sources imply; the sidecar is what the author meant.**

The store holds itself to a size cap (`CADGEN_STORE_MAX`, default 20 GB): the
daemon, when idle, evicts derived entries (mesh, surface, component, bounds,
drawing) least recently written first and sweeps what nothing reaches, and
retires on sight the index kinds an older cadgen left (`index/op`). A record,
a document entry or an output entry is never evicted. `cadgen store gc` does
the same by hand (`STORE.md` §8). A cadgen never judges what it cannot read:
a store a newer cadgen wrote to within 30 days is left to that cadgen, and a
folder it does not know is never touched. A read never writes the store, and a write
that finds its bytes already present claims them, so deletion needs no
coordination: a sweep keeps whatever a publish has claimed, and a racing
reader re-misses and rebuilds. Store correctness needs
no lock protocol: atomic writes, pins and the publish rule (`STORE.md` §5, §7)
decide concurrent outcomes. Saved-file readers never wait for a source model
to finish; missing derived artifacts are resolved through the build pool.
*Pressure-test*: build a model and snapshot it, make the store read-only, then
do both again: each succeeds and nothing under the store changes.

### 3. One sidecar per artifact, and it belongs to that artifact alone

`part.step` gets `part.step.json` — schema-versioned sections (kinematics,
appearance, animation). New capability = new section + schema bump, never a second sidecar
file. Model-side, beside the artifact, so it travels with the file it
describes — and it exists only when law 17 says it must.

A sidecar describes the model that declared it — never its parent, never its
children. A parent composing a child receives geometry and intrinsic appearance
(tree, labels, colors, PBR values, placements, exact shape). The child's
kinematics belong to the child's own sidecar,
and an assembly that needs a relation declares it on the assembly. This is
what lets a cached child stand in for its function: the cache carries
geometry and intrinsic appearance; a parent never reads the child's sidecar.
*Pressure-test*: build a child that declares `kinematics=`, then build a parent
that composes it. The parent's kinematics section contains only its own
declarations, and the child's sidecar is unchanged by the parent's build.
Intrinsic finishes travel with the pinned geometry and are rebound to the
parent document's occurrences when it is saved.

### 4. Zero metadata in written artifacts

A STEP or DXF is pure geometry. Provenance, kinematics, and context ride
the sidecar; the artifact separated from everything else is a plain
importable file.

### 5. Byte determinism is the writers' promise, not the kernel's

cadgen's writers are pure: the same shapes give the same bytes, in every
format — STEP (canonicalized NAUO ids and presentation-style ordering), meshes
(the store's mesh of each component, serialized by one deterministic writer), DXF
(geometry-ordered emitter). The geometry kernel, the mesher included, makes no
such promise. Two runs of one model can differ in a last digit
or in the order of the pieces a boolean returns, and cadgen neither hides that
nor depends on it. Equal bytes mean reuse; different bytes cost a
recomputation (a re-mesh, a parent recompose) and never a wrong answer. A
rebuild whose writer input is unchanged keeps its saved STEP instead of writing
the same bytes again ([`STORE.md`](STORE.md) §3, `writerInput`).
Content addresses stay byte hashes; whether a model runs is decided by its
sources (`STORE.md` §4), never by its outputs being reproducible. Compare two
builds by geometry within a tolerance, never by file hash.
*Pressure-test*: build one model twice, each from an empty store. If the bytes
differ, nothing fails, and the second build's outputs are as correct as the
first's.

### 6. One surface, three faces

The DECORATOR declares a capability on a model, the PUBLIC FUNCTION
(`cadgen.<format>.<verb>`) performs it, and the CLI (`cadgen <format>
<verb>`) is GENERATED from the function's signature
(`_internal/cli_from_function.py`) — never hand-written, structurally
sync-tested.

*Pressure-test*: for any option, "what is this called on the other two
surfaces?" must answer with the same name and a role-determined payload —
`kinematics` everywhere: on DECLARING surfaces (decorators, `step build`)
it is the space (`{mates, couplings, poses}`); on the CONSUMING surface
(snapshot) it is a point in that space (a preset name or `{dof: value}`).
The mesh `build` doors take no `kinematics`: a mesh is the document's tree,
tessellated as stored. One name, one validator, no synonyms.

Geometry queries are a Python library surface, separate from document-format
verbs. `read_step(path)` returns build123d geometry; `read_scene(path)` returns
revision-scoped occurrence/selector views with caller-owned world geometry.
`cadgen.geometry` provides `closest_points`, `overlap_volume`, `is_sound`,
`topology_errors`, `boundary_edges`, `self_intersections` and
`mass_properties`. These operations accept native geometry and return facts;
selection, units, thresholds, exclusions and verdicts belong to the caller's
script. The inspect
CLI and `step.inspect` are removed, with an immediate migration error.
The contracts live in [`step_scene.py`](src/cadgen/step_scene.py) and
[`geometry.py`](src/cadgen/geometry.py). They import no kernel at namespace
load and require no display artifacts.

**The one exception: `@eng_drawing` has no public function and no CLI.**
`cadgen.eng_drawing` declares a capability on a DOCUMENT OVER a part, not on a
model: what it consumes is a `Sheet` the author composed in Python — views,
their placement, and dimensions between points on the part's geometry — and no
argument list can carry that. There is nothing for a generated CLI to take but
a script path, which law 7 forbids, and nothing for a public function to add
over the decorator. The decorator is the whole surface; the script is the
program; the output is one PDF. Adding a `cadgen eng-drawing` verb would mean
passing a script to a CLI, so it stays absent by design.

### 7. Documents-only CLIs; scripts are programs

`python model.py` is the one source door: it gates, builds, writes every
output the decorators declare (`.step`, meshes, sidecar — STEP is one output
kind, not a required one), and rewrites declared exports that drifted. Every
CLI takes documents, resolves them by their bytes, and compiles a missing
tree from those bytes as a job in the build pool — never from a script.

A script is a program, and cadgen runs it wherever it lives. The import path
inside a build is exactly `python script.py`'s — the script's own folder, then
the caller's `PYTHONPATH` — and nothing cadgen adds or infers from directory
names. Project layout (`src/`, `lib/`, format folders) is a convention of the
skills, never a fact cadgen knows; a project that wants an import root beyond
the script's folder declares it the standard Python way (`PYTHONPATH=src`).
*Pressure-test*: move a project's folders around and rebuild; cadgen must not
care, only the project's imports may.

A script may declare several models, and builds the ones its `__main__` calls.
Its flags (`--force`, `--json`, `--verbose`, `--profile`, the mesh tolerances)
apply to every model it builds: no flag names, selects or configures one of them. A command
that addresses one model, such as `cadgen store why`, names it
`script.py::function`; a bare `script.py` names its sole model, and a file that
declares several must be named. *Pressure-test*: put two models in one file and
call both from `__main__`; every flag must mean the same thing for each.

### 8. No backwards compatibility

Hard cutovers only. Every retired surface fails loudly with a teaching
error naming its replacement — never an alias, never a shim.

The explicit exception is `cadgen.assembly.AssemblyHelper`: it is softly
deprecated and still works. Construction emits a visible `FutureWarning`
pointing to native build123d compounds, labels, transforms and joints.
Importing it is quiet; a current model that skips its body emits no warning.
This does not change geometry, model freshness or child sharing.

### 9. Closed vocabularies

Every declaration surface has a closed key/kind set. Unknown keys are
teaching errors, never silently ignored.

### 10. Loud failure or correct output, nothing between

The cardinal sin is plausible-wrong output at exit 0. No silent fallbacks,
no globs, no guessing; a failed render leaves NO file at the requested
path.

### 11–14. Runtime laws (shared with the bundled JavaScript runtime)

Kinematics and choreography are both pure data, fully independent: resolved
mates, and keyframes the build samples from Python clips (11). Clients render
from file + sidecar + the store's artifact side and never
read source, a record, or trigger source builds (12). A build's status
(STORE §9b) carries no geometry: clients render the saved file.
Correctness never depends on a
store hit (13). Composition: importing binds, calling links — a parent
depends on a child by its RESULT (the pinned tree) and on what importing it
runs in the parent's process (its module body and model headers, never a
model body), on a constant by its VALUE, on a helper by its REACH (the part of
the helper the script and every file the build executed can run, closed
statically; the whole file — or the whole closure — wherever the analysis
cannot see), on a data file by its BYTES (every file the build opened,
whoever opened it: STORE.md §5, every read is seen),
and on every file whose appearance would change what an import finds
([`STORE.md`](STORE.md) §3) — and a model must never `read_step` its own
output (14). The bundled runtime
under `_runtime/` is the JS half of these; the laws' JS statements live in that
runtime. It is built
when the wheel is packaged and travels only inside it: the source tree never
carries a built copy, so an installed cadgen and the sources that produced it
cannot disagree.

### 15. The package ships alone

The installed distribution is the whole world: the Python engine, the
bundled `_runtime/`, and this document. It works with the repository it
was built from gone — and its markdown must read that way, referring to
nothing outside the package.

*Pressure-test*: every sentence in the package's markdown must be true and
actionable for someone who only ran `pip install cadgen`. Naming a bundled
thing ("the JavaScript runtime bundled at build time") passes; a repo path
to its source, a repo script, or a repo workflow does not.

### 16. Decorator inputs never change the geometry

A `@step`/`@dxf`/`@stl`/`@glb`/`@threemf` decorator's arguments never change
the geometry a model produces. They decide where the files land (`out=`),
how they are written (the mesh tolerances), and what the sidecar declares
(`kinematics=`, `materials=`, `animation=`). The geometry is the function's return value and nothing
else: a `Compound` placing children is packaged as occurrences, a single
solid as one component, and `part`/`assembly` is read off the resulting tree.
A posed or differently configured export is authored geometry, or another
model. Intrinsic appearance participates in the authored tree identity so it
inherits through pinned children, while component identities and STEP bytes
remain unchanged.

Because they cannot change geometry, literal `kinematics=` and `materials=`
values can be refreshed onto a cached baseline without executing the model — a
narrow fast path whose preconditions and fallbacks are
[`STORE.md`](STORE.md) §3 (the record's `unannotatedTree` and
`geometryClosure`). It is an optimization the law permits, never a second
way to build. `animation=` clips are code, never literals: an edited clip is an
ordinary build, which bakes new keyframes and keeps the STEP's bytes.

Two features were deleted for violating this: the kinematics bake point
(`kinematics={..., "at": pose}`), which transformed the tree through its mates
before writing it, and `kind="part"|"assembly"`, whose only effect was to steer
whether the build packaged the return as one component or as occurrences.
*Pressure-test*: change only `materials=` or `animation=` and rebuild; component
identities and STEP bytes must not change.

### 17. A sidecar only when strictly necessary

Never write a JSON sidecar unless something beside the artifact has to read
it. Kinematics, named intrinsic materials, and animation need durable artifact annotations;
a model with none writes no sidecar. A rebuild removes sections the model
no longer declares and deletes an empty sidecar. Metadata with no reader
beside the artifact — what a model declares about its own outputs, where a
build came from, when it ran — belongs in the store record, never in a
file next to the geometry.

Schema 10 sidecars contain only `schemaVersion`, the saved STEP's `documentHash`,
and optional `kinematics`, `appearance`, and `animation` sections. Appearance
stores named material definitions plus canonical leaf occurrence assignments;
animation stores keyframes baked from the model's Python clips when it built —
an ordered list of clips, each a set of tracks over canonical leaf occurrences —
so the sidecar carries data, never code. Appearance is applied to an owned
render/export descriptor, never to the byte-derived tree. Appearance-sensitive
export variants include its digest, including the absence of overrides.
The document digest binds those declarations to the artifact; it is
not provenance. An old schema or a mismatched digest must be rebuilt or
re-annotated, never silently applied. Compiling an imported STEP preserves
its authored sidecar bytes.

The retired `meshExports` section copied mesh decorator declarations that only
a door read back; a door now tessellates the document's tree and writes the
file it was asked for.
*Pressure-test*: build a part that declares meshes but no kinematics,
materials, or animation; no
`.step.json` may appear beside it.

### 18. Caches sit around a model run, never inside it

The gate decides whether a model runs at all (`STORE.md` §4), and the store
derives everything render-side from the bytes the run wrote (law 2). Inside a
run, every modeling operation executes: cadgen never replays a stored result,
never substitutes a copy for what an operation returned, and never changes
what build123d's `==` and `is_same` answer. A script therefore behaves the
same inside cadgen as under plain Python. The hooks that remain change no
result: `determinism.py` fixes the iteration order of build123d's
de-duplications (an order-keeping set, and a `Vertex` hash by point that
leaves equality alone), lazy children defer a child's geometry until it is
read (`STORE.md` §9a), and the file trace only watches what the run opens
(`STORE.md` §5). An expensive or independently edited part gets its
speed by being its own model, never from a cache inside one. What an older
cadgen cached inside a run (`index/op`, the operation cache) is never read,
and is retired with every object only it named (`STORE.md` §8).
*Pressure-test*: call a model's function under plain Python and inside a
cadgen build; the geometry it returns, and the answer to every `==` and
`is_same` along the way, are the same.

### 19. Nothing waits on the network

Once installed, cadgen works offline: every command, build, snapshot, server
and page. Its own requests are two: telemetry
(`analytics.py`, usage counts under a random id, sent by default once a `cadgen`
command has said so, and never after the person's no) and the daily version check
(`updates.py`). Both run in the background and fail silently: no start,
command, build, request or tool call waits on them, and one that fails changes
nothing but what is counted or offered. A command sends nothing itself: it hands
what it counted -- a build it made with no daemon to ask, a snapshot, a drawing, a
crash -- to a running build daemon over its local socket, never starting one, and
gives up after a moment (`daemon.client.HAND_OVER_SECONDS`); with no daemon to take
it, it keeps it in a small file beside the settings for the next process that sends
(`analytics.spool`). A process that exits sends nothing either: its last batch --
a server's, or the build daemon's -- is kept in a file beside the settings, and the
next process that sends sends it in the background, a moment after it starts
(`analytics.KEPT`). One wait remains, bounded, for something only the network can
do: `cadgen telemetry off`, which waits for the deletion it asks for (still owed,
and asked again, when nobody answers). The
pages load nothing from the internet: everything they show ships in the wheel.
Installing needs the network (cadgen itself, and the headless browser the first
snapshot fetches), and nothing after it does. The law is the package's, not the
launcher's: a launcher that checks a package index before it starts anything
(`uvx`, once its cache is stale) has its own needs.
*Pressure-test*: with an installed cadgen and every request refused (a proxy on
a closed port), and again with every request hanging, start a server, open a
view, call each tool, and run a build and a snapshot: each works, and nothing
waits on a request beyond the two waits above.

## The shape of the package

```
src/cadgen/
  <format>.py            # public namespaces: step, stl, threemf, glb, dxf,
                         #   urdf, srdf, sdf — each binds its verbs
  authoring.py           # @step/@dxf/@stl/@glb/@threemf decorators; a call
                         #   builds at top level and composes (a lazy child)
                         #   inside a body; a model's outputs are what they
                         #   declare — a mesh decorator alone is a model that
                         #   writes no STEP
  articulation.py        # a model's kinematics resolved for a player:
                         #   controls, joints as affine rows (plus a sampled
                         #   curve where a joint follows its driver
                         #   nonlinearly), carries, handles, poses; the
                         #   reference evaluator
  robot_payload.py       # a robot description (URDF, SDF, SRDF with its
                         #   URDF) resolved for the page: the articulation
                         #   above (a tcad:four_bar linkage closed here into
                         #   a curve), the visuals in rest space (a box,
                         #   cylinder, sphere or capsule meshed into the
                         #   store), the facts a person reads back; refused
                         #   at the door in the validators' words, joint
                         #   values held to the articulation
  kinematics.py          # typed mates vocabulary (revolute/slider/
                         #   cylindrical/fastened, couple, normalize)
  animation.py           # animation clips (cadgen.clip) for @step's
                         #   animation=, baked to sidecar keyframes at build
  step_scene.py          # read_step and read_scene
  assembly.py            # label utilities and softly deprecated AssemblyHelper
  results.py             # the typed Results every verb returns (stdlib-only)
  settings.py            # the person's settings: settings.json in the state
                         #   directory, a section per feature, shared by
                         #   every app and version of cadgen
  analytics.py           # telemetry: usage counts and crash reports (a
                         #   crash's type and frames, never its message) from
                         #   the CAD apps and the build daemon, on by default
                         #   once a command has said so, never after a no (its
                         #   answer: settings.json's `telemetry` section)
  features.py            # the CAD views' features a person can turn off
                         #   (Quick edit: settings.json's `features` section)
  updates.py             # the daily version check: whether a newer release is
                         #   out, for a copy nothing else keeps up to date
                         #   (_internal/channel.py)
  store/                 # the store (STORE.md): objects, index, records, trees,
                         #   closure, gate, materialize, publish, lazy, gc, view
  cli/                   # generated command shells, one per <format> <verb>
  cli_tree.py            # the build tree on stderr / JSONL events, and each
                         #   built model's time line (model code vs cadgen)
  daemon/                # the build pool: executors (daemon + transient),
                         #   broker (job slots, coalescing), pool (workers,
                         #   spares, extras), jobs (the ledger), server,
                         #   worker, client, transport, telemetry (what it
                         #   builds and how that goes, counted)
  _internal/             # the engine: generation pipeline, tree builder,
                         #   filetrace (every file a build opens),
                         #   kinematics_resolve (mate axes to numbers),
                         #   animation_bake
                         #   (clips to keyframes), mesh_export (the mesh
                         #   writers, a clip's GLB sampling, their ledger),
                         #   cli_from_function, doors (documents by bytes),
                         #   build_timing (where a build's time went;
                         #   --profile),
                         #   source_sidecar, step_assemble/step_reemit
  viewer/                # the CAD Viewer's server: launcher (main),
                         #   routes (http_app), files by absolute path
                         #   (backend), a file's catalog row (scanner; started
                         #   when a watched build saves: warm), the explorer's
                         #   reads (folders), the model library every CAD view
                         #   shares (recents), status
                         #   (artifact_status: not compiled / compiling /
                         #   compiled / failed), build_progress (the daemon's
                         #   job ledger, read over its socket)
  mcp/                   # CAD for agent hosts: stdio JSON-RPC (protocol), the
                         #   tools and launches (server), open views (views),
                         #   the viewer routes in-process (tunnel), roots,
                         #   the page (ui), and the CAD Viewer link for
                         #   a host that renders no MCP Apps (browser)
  _runtime/              # BUILT JS (browser snapshot renderer, the viewer
                         #   client, the MCP app page) and the native file
                         #   tracer, one library per platform — produced when
                         #   the wheel is packaged, never committed, never
                         #   edited
```

Verbs by format: `step` compile · build · snapshot;
`stl`/`3mf`/`glb` build · snapshot; `dxf` snapshot; `urdf`/`sdf`
validate · snapshot; `srdf` validate. `cadgen snapshot` routes any suffix.
`cadgen store|daemon|doctor` are status commands, `cadgen viewer
[stop]` the CAD Viewer's launcher, and `cadgen mcp`
the server an agent host starts — all deliberately outside the mirror pattern. `cadgen step compile` is internal tooling: skills never
teach it — doors compile a document's missing tree on demand.

Developed in [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad);
that repo's contributor guide carries the development workflow (tests,
bundling, versioning).

The viewer exposes `POST /__cad/clipboard` for explicit viewport PNG copies. It
uses the same host and custom-header POST gates as other mutation routes, limits
images to 20 MiB, and delegates native delivery to `viewer/clipboard.py`. It never
reads the clipboard. Unsupported desktop clipboard environments return an error.

It exposes `POST /__cad/sketches?name=` for a picture a copied prompt names by path:
the view with a person's sketch drawn over it. It takes a PNG of at most 20 MiB under
the same gates and saves it in the system's temporary directory as
`cadgen-sketches/<name-stem>-<sha256[:12]>.png` (the same picture saved twice is one
file, and saving it again makes it the newest), keeps only the newest 64
(`viewer/sketches.py`), and answers `{"ok": true, "path": "<absolute path>"}`. It is
scratch, not state.
