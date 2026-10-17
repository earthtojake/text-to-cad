# cadgen

The published distribution: everything that turns CAD source into documents,
documents into derived state, and derived state into pixels and meshes. One
PyPI package carrying the Python engine under `src/cadgen/` and what it executes
that is not Python under `src/cadgen/_runtime/`: the shared JavaScript runtime and
the CAD Viewer's client, bundled in at build time (the JS *source* lives in its own
packages and never ships as source), and one native library, one build per
platform: the file tracer (its C source is `native/`).

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
| [`STORE.md`](STORE.md) | The store's contract: layout, the two-sides law, tree/record shapes, the gate, invariants, link-vs-component, concurrency, GC, the daemon, children, editing previews, debugging. Sectioned, with a table of contents | changing anything that writes to or reads from `~/.cache/cadgen`, or any build, door or reader that depends on it |
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

Four mechanisms live under this law rather than beside it, and each is
specified where it is implemented — change one by reading that section, not
this one:

| Mechanism | What it must not break | Specified in |
|---|---|---|
| Build status and preview: the viewer's feed says whether a build of a file is running or failed and, as soon as the build has its result, names the **preview revision** -- the result tree and the parts it draws with, artifact-side objects -- which the viewer draws labelled as a preview until the saved file replaces it in place; the file is exported from that very tree, and its bytes map to it once written, so the saved file's parts are the preview's and nothing is fetched twice | no reader reaches source, closure or a model record; a preview never stands in for a saved file, and no bytes map to a tree before they are written from it | [`STORE.md`](STORE.md) §9b |
| Composition: what a decorated call returns -- the child's stored result, decoded, or built there and then -- and how a parent records it | the link/component decision, the child's key | [`STORE.md`](STORE.md) §6, §9a |
| Display data: canonical trees pin encoded BREP and effective intrinsic face colors; each part's display data — ONE record naming two objects, OCCT's mesh at the one display tolerance and the selector table, both made from the component's topology facts, extracted in memory under an attested producer — is derived by the build pool, never on the build's thread (a daemon worker, or with no daemon a thread of the build's process): the jobs a build asks for the moment its result exists -- one, or a pool slot's share each of a large batch -- and waits for before it reports done (a parent's children's builds had theirs derived); views only read, and a part missing from the store is derived by one build-pool job; cadgen is the only mesher — every client draws the store's meshes and holds no tolerance | geometry stays separate from display data — a part that fails to derive is a warning and never makes the geometry rebuild; `read_step` never waits for a part | [`STORE.md`](STORE.md) §3 |
| Exports: a model's STEP written from its stored result by the build pool, its sidecar from its record, and every exported file verified against the tree it was written from | the file's bytes map to its result, pending a parse that verifies them, which a door waits for; a file that does not verify is its own content, and the build says so | [`STORE.md`](STORE.md) §3 |

### 2. The store contains only derived results

`~/.cache/cadgen` is the store: content-addressed objects (a model's result
tree and the components it is made of) and input-addressed index entries
(the per-model record, the document → tree map, bounds and part entries)
— data derivable from sources and documents, and nothing else. Its
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
daemon, when idle, evicts derived entries (part, component, bounds, drawing,
skin, robot, result) least recently written first and sweeps what nothing reaches, and retires on
sight the index kinds an older cadgen left (`index/op`, and `index/surface`,
`index/selector` and `index/mesh`). A record,
a document entry, an output entry or a provenance entry is never evicted. `cadgen store gc` does
the same by hand (`STORE.md` §8). A cadgen never judges what it cannot read:
a store a newer cadgen wrote to within 30 days is left to that cadgen, and a
folder it does not know is never touched. A read never writes the store, and a write
that finds its bytes already present claims them, so deletion needs no
coordination: a sweep keeps whatever a publish has claimed, and a racing
reader re-misses and rebuilds. Store correctness needs
no lock protocol: atomic writes, keys and the publish rule (`STORE.md` §5, §7)
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
Intrinsic finishes travel with the child's stored geometry and are rebound to
the parent document's occurrences when it is saved.

### 4. A written artifact carries its identity, never its context

A STEP or DXF is geometry, and a STEP written named also carries what
names it (law 20): each part's key as its product's description, and each
face's and edge's name as the name of the entity written for it
(`_internal/step_names.py`), so any reader of the file gets the names from
the file alone. Those are ordinary STEP names and descriptions, and a STEP
written plain carries none. Provenance, kinematics, and context ride the
sidecar; the artifact separated from everything else is a plain importable
file.

### 5. Byte determinism is the writers' promise, not the kernel's

cadgen's writers are pure: the same shapes give the same bytes, in every
format — STEP (canonicalized NAUO ids and presentation-style ordering), meshes
(the store's mesh of each component, serialized by one deterministic writer), DXF
(geometry-ordered emitter). The geometry kernel, the mesher included, makes no
such promise. Two runs of one model can differ in a last digit
or in the order of the pieces a boolean returns, and cadgen neither hides that
nor depends on it. Equal bytes mean reuse; different bytes cost a
recomputation (a re-mesh, a parent recompose) and never a wrong answer. A
rebuild whose result tree and writer are unchanged keeps its saved STEP instead
of writing the same bytes again ([`STORE.md`](STORE.md) §3, the kept rule).
Content addresses stay byte hashes; whether a model runs is decided by its
sources (`STORE.md` §4), never by its outputs being reproducible. Compare two
builds by geometry within a tolerance, never by file hash. One identity is
deliberately not a byte hash: a **part** -- a component's display data -- is
keyed by the **construction** that made its component (law 20), so a body the
kernel writes a little differently from one run to the next is one part with
one mesh, and a file that holds its result maps to that result and draws with
the build's parts.
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
script. The contracts live in [`step_scene.py`](src/cadgen/step_scene.py) and
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
Its flags (`--force`, `--json`, `--verbose`, `--profile`)
apply to every model it builds: no flag names, selects or configures one of them. A command
that addresses one model, such as `cadgen store why`, names it
`script.py::function`; a bare `script.py` names its sole model, and a file that
declares several must be named. *Pressure-test*: put two models in one file and
call both from `__main__`; every flag must mean the same thing for each.

### 8. No backwards compatibility

Hard cutovers only. A retired surface does not exist: no alias, no shim, and
no error that recognizes its old spelling to explain what replaced it. A
removed command, flag, argument, key, module or name gets what the current
contract's ordinary validation says — an unknown command, an unrecognized
argument, an unknown key, an `ImportError`. A version-gated refusal (a sidecar
written to another schema) states what is required and the remedy, never what
changed.
*Pressure-test*: use a removed spelling; the error must read exactly as it
would for a name that never existed.

The explicit exception is `cadgen.assembly.AssemblyHelper`: it is softly
deprecated and still works. Construction emits a visible `FutureWarning`
pointing to native build123d compounds, labels, transforms and joints.
Importing it is quiet; a current model that skips its body emits no warning.
This does not change geometry, model freshness or child sharing.

### 9. Closed vocabularies

Every declaration surface has a closed key/kind set. An unknown key is an
error naming the supported set, never silently ignored.

### 10. Loud failure or correct output, nothing between

The cardinal sin is plausible-wrong output at exit 0. No silent fallbacks,
no globs, no guessing; a failed render leaves NO file at the requested
path.

### 11–14. Runtime laws (shared with the bundled JavaScript runtime)

Kinematics and choreography are both pure data, fully independent: resolved
mates, and keyframes the build samples from Python clips (11). Clients render
from file + sidecar + the store's artifact side and never
read source, a record, or trigger source builds (12). A build's status
(STORE §9b) carries no geometry of its own: it names a preview revision --
artifact-side objects a client reads like any other -- and clients render
the saved file, or that preview labelled as one until the file replaces it.
Correctness never depends on a store hit, and a door confirms an unverified
document entry before it answers with it (13). Composition: importing binds, calling links — a parent
depends on a child by its KEY (the child and everything it was built from: its
sources, data, children and producer, as its record keeps them -- so a child
source edit rebuilds its parent, which relinks the child's stored result) and
on what importing it runs in the parent's process (its module body and model
headers, never a model body), on a constant by its VALUE, on a helper by its REACH (the part of
the helper the script and every file the build executed can run, closed
statically; the whole file — or the whole closure — wherever the analysis
cannot see), on a data file by its BYTES (every file the build opened,
whoever opened it: STORE.md §5, every read is seen), on an environment
variable its own code reads by its VALUE (a daemon job runs in its caller's
environment), and on every file whose appearance would change what an import
finds, a module an import looked for and did not find included
([`STORE.md`](STORE.md) §3) — and a model must never `read_step` its own
output (14). What a program the model starts reads is no input; the build
says so when it starts one. The bundled runtime
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
how they are written (a mesh decorator's tolerances), and what the sidecar declares
(`kinematics=`, `materials=`, `animation=`). The geometry is the function's return value and nothing
else: a `Compound` placing children is packaged as occurrences, a single
solid as one component, and `part`/`assembly` is read off the resulting tree.
A posed or differently configured export is authored geometry, or another
model. Intrinsic appearance participates in the authored tree identity so it
inherits through composed children, while component identities and STEP bytes
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

A sidecar declares nothing about meshes: a door tessellates the document's
tree and writes the file it was asked for.
*Pressure-test*: build a part that declares meshes but no kinematics,
materials, or animation; no
`.step.json` may appear beside it.

### 18. Caches sit around a model run; inside it, only the kernel memo

The gate decides whether a model runs at all (`STORE.md` §4), and the store
derives everything render-side from the bytes the run wrote (law 2). Inside a
run, every modeling operation executes once per distinct input, and never
twice: the **kernel memo** (`_internal/kernel_memo.py`) is one interception
layer at build123d's topology layer, installed in the warm worker beside
`determinism.py`, that sees every kernel construction the model's code calls
-- primitives, booleans, fillets and chamfers, extrusions, sweeps and lofts,
the faces, wires, shells and solids the constructors make, copies and moves,
cleaning, validity, file imports -- and remembers, in the worker's memory for
the life of the process, the live result of each under a key made of the
operation, its parameters by value and the keys of the shapes it was given (a
result by the operation that made it, a face or an edge by the shape it was
taken from and its index there, a file by its bytes), so a second run of the
same code hands back **the same live objects** the first run made, restored
to the state the operation returned them in, down to the point where an input
changed, and executes everything from there. A hit is the previous run's
object itself: nothing is reconstructed from bytes, no copy stands in for what
an operation returned, and what build123d's `==` and `is_same` answer is what
they would answer in a run that happened to make those objects -- pointer
identity is preserved along every chain of hits, a hit needs the very input
objects the first run was given (a shape no operation of this process made
runs its call uncached), and every miss makes its downstream miss, which is
why the memo is correct where the operation cache cadgen once kept
(`index/op`, retired, `STORE.md` §8) was not: that one replayed bytes into
fresh shapes, and model code that held an edge across an operation found
nothing. Every boolean the layer sees runs non-destructive, so it leaves its
inputs as it was given them and its result shares every sub-shape it did not
change; what another operation does to its inputs (an extrusion clears its
profile's `Free` flag and appends representations to the profile's edges) is
captured as each sub-shape's state before and after -- tolerance, flags, how
many representations it holds -- replayed on a hit and undone when a later
run no longer runs the operation, so a cold run and a hot run write the same
bytes; a change that state does not express makes the input's maker forget it.
The memo never reaches the store and
never outlives the worker: a cold run computes everything, and
`CADGEN_KERNEL_MEMO=0` turns hits off and nothing else -- every call runs and is
keyed and traced as ever. The memo's key for the construction that made a
component -- every setting the call ran with, the output of it the component
is, the effects later calls had on it -- restated stably (`construction_key`),
is that component's identity (law 20), the same in a cold worker, a warm one
and with hits off. The same layer records each call from the
model's own code as a **feature** (`_internal/kernel_trace.py`), whose lineage
names the faces, edges and vertices of what the run made, and whose trace is
what provenance keeps (law 20, `STORE.md` §3). The hooks that
remain change no result: `determinism.py` fixes the iteration order of
build123d's de-duplications (an order-keeping set, and a `Vertex` hash by
point that leaves equality alone), a child call hands back the child's
stored result decoded (`STORE.md` §9a), and the file trace only watches what
the run opens (`STORE.md` §5). An expensive part may still be its own model; it
no longer has to be.
*Pressure-test*: call a model's function under plain Python, then inside a
cadgen build with the memo cold, then again with it hot; the geometry each
returns, the bytes of every component it writes, and the answer to every `==`
and `is_same` along the way, are the same all three times, and the hot run
counts a hit for every miss of the cold one.

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

### 20. A thing is named by what made it; bytes name objects

cadgen names a thing by what the question is about, and never answers one
question with another's name.

- **Bytes name objects.** A component, a tree and a document are their bytes
  (`sha256`): the content address, the publish rule, the sweeper and the gate
  all stand on equal bytes meaning the same thing and different bytes costing
  a recomputation, never a wrong answer (laws 2 and 5).
- **Construction names parts and elements.** What the eye and the hand touch
  is named by what made it, not by which bytes happened to carry it or where
  it sat in a list. A **part** is the construction that made its component:
  the kernel memo's key for it (law 18: the operation, every setting it ran
  with, its parameters by value, the keys of the shapes it was given and the
  output of it the component is, restated stably with cadgen's release) with
  the producer that derives its display data -- so one body is one mesh
  however its bytes come out, a file that holds its result maps to that
  result, and a preview's parts are the file's. A
  face, edge or vertex is its **lineage** (`_internal/kernel_trace.py`): the
  feature that made it -- `<function>.<operation><count>`, counted among the
  features the part descends from so an edit elsewhere renames nothing, or the
  label an author gave the shape, which pins it in what is made of that shape
  once labelled (a label set after a construction used the shape renames
  nothing it made; on a part placed as it is, a label names the occurrence:
  parts made alike and labelled apart are one part) -- and its number among the elements of its
  kind that feature made, `f:bracket.extrude1.3`, with a piece's number after a
  later split. A ref is the occurrence's **token** (`o:`, from its place in
  the tree: parent token, name, rounded placement) and the element's name:
  `#o:4b1f9e2a7c03/f:bracket.extrude1.3`. So a ref survives a STEP round trip, a
  sibling's insertion, a dimension change and code that moves, and a name
  copied from the viewer resolves in `inspect` to the same face. Nothing on
  the way from a run to its record measures geometry to name anything: the
  key and the lineage are what the run's memo and trace already hold.
- **Geometry is the fallback.** What no construction of a run made -- a file
  read, a shape built outside the patched kernel surface -- is keyed by its
  bytes, and its elements are named by **geometric tokens**
  (`_internal/geometric_tokens.py`, `f:` and twelve hex characters, a hash of
  the element's geometry within its body), measured on demand: where a part's
  display data is derived, in the build pool, and where a ref in that form is
  resolved against a body named by lineage (`refs.py`, the one resolver every
  ref goes through), remembered by content either way. A geometric name
  tolerates what a byte name cannot and must not
  pretend to exactness; nothing that decides whether a model is current or
  whether bytes were written reads one (laws 2, 5). Names are in the file
  (law 4), but what they stand for lives in the store of the build that wrote
  it: read with a store that never held that build, a saved file is compiled
  like any other, named by its geometry, so a ref by name resolves where that
  store is and a ref by token everywhere (`STORE.md` §3).
- **Provenance is the run's trace, on the code side only.** Which line of
  which file ran a feature is a build's knowledge about its code, and lives
  where that knowledge belongs: in a per-model entry beside the record,
  `index/provenance` (`STORE.md` §3), on the store's code side with
  `index/model` and `index/output`, reached from a saved document only through
  those by the two commands that may ask about code, `cadgen store why` and
  `cadgen store where`. No object, part, document entry, sidecar or written
  file carries a frame or a line (law 1); a feature's name is a function's
  name, an operation and a count, and deleting the code side loses no
  geometry and renames nothing.

Versions follow the names (`STORE.md` §2): `GEOMETRY_SCHEME` is the only
version on a component's identity, the construction key carries cadgen's
release, and `GEOMETRIC_TOKEN_SCHEME` is the only version on a geometric
token; a fix to what is derived from a name bumps that layer's version.
*Pressure-test*: build a model and compile the STEP it wrote in an empty
store: the compile names every occurrence as the result does, every part's
faces and edges where the result has them within the display tolerance, drawn
alike -- what the build's verify checks -- so the file maps to the result,
its parts the build's; a file the translation changed is its own content,
named by its geometry, and the build says so, then writes it plain. Then change a
dimension and rebuild: every face the change left in place keeps its name.
Then insert a new sibling before an occurrence and rebuild: every token and
name the untouched occurrences had is unchanged. Throughout, nothing outside
the model's own code measures a surface while it builds. Then `rm -rf
index/model index/output index/provenance`: every view and every ref still
resolves; only `store where` says it no longer knows.

## The shape of the package

```
src/cadgen/
  <format>.py            # public namespaces: step, stl, threemf, glb, dxf,
                         #   urdf, srdf, sdf — each binds its verbs
  authoring.py           # @step/@dxf/@stl/@glb/@threemf decorators; a call
                         #   builds at top level and composes (a child: its
                         #   stored result decoded, or built here, serially)
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
                         #   store), the facts a person reads off it; refused
                         #   at the door in the validators' words, joint
                         #   values held to the articulation
  kinematics.py          # typed mates vocabulary (revolute/slider/
                         #   cylindrical/fastened, couple, normalize)
  animation.py           # animation clips (cadgen.clip) for @step's
                         #   animation=, baked to sidecar keyframes at build
  step_scene.py          # read_step and read_scene
  refs.py                # the one resolver: every ref (read_scene, store
                         #   where, a mate's ends and axis, a snapshot's
                         #   focus and hide, a clip's targets, a material's
                         #   assignments) to its node and element, the
                         #   fallback matcher in it
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
                         #   results (a model's result under the key of
                         #   everything it was built from, §3), closure, gate,
                         #   materialize, publish, gc, view, exports (a model's
                         #   STEP written from its result and verified against
                         #   it, §3), provenance (the build's account of its
                         #   code, §3)
  cli/                   # generated command shells, one per <format> <verb>
  cli_tree.py            # the build tree on stderr / JSONL events, and each
                         #   built model's time line (model code vs cadgen)
  daemon/                # the build pool: executors (daemon + transient),
                         #   broker (job slots, coalescing), pool (workers,
                         #   spares, extras), jobs (the ledger), server,
                         #   worker, client, transport, telemetry (what it
                         #   builds and how that goes, counted)
  _internal/             # the engine: generation pipeline, tree builder,
                         #   kernel_memo (law 18: the memo at the kernel
                         #   boundary, whose keys are parts' identities),
                         #   kernel_trace (its features, and the lineage
                         #   that names elements),
                         #   filetrace (every file a build opens),
                         #   tessellate (every display mesh: OCCT's
                         #   triangulation of the exact BREP, each face checked
                         #   against its surface and meshed again where it
                         #   strays),
                         #   geometric_tokens (the fallback matcher: an
                         #   element's name from its geometry, for elements
                         #   no construction names, measured on demand),
                         #   tree_tokens (an occurrence's token, from its
                         #   place in the tree),
                         #   step_names (the names a STEP carries, law 4:
                         #   each part's key and each face's and edge's
                         #   name, written and read from the file),
                         #   step_verify (whether a written STEP holds the
                         #   result it was written from, law 20),
                         #   step_placements (a placement a reader rebuilds
                         #   as the result places it),
                         #   step_reals (how a real reads in a STEP file),
                         #   preview_revision (a build's preview: its parts
                         #   announced as the pool stores them, its
                         #   annotations as one object, STORE.md §9b),
                         #   kinematics_resolve (mate axes to numbers),
                         #   animation_bake
                         #   (clips to keyframes), mesh_export (the mesh
                         #   writers, a clip's keys in a GLB, their ledger),
                         #   cli_from_function, doors (documents by bytes),
                         #   build_timing (where a build's time went;
                         #   --profile),
                         #   source_sidecar, step_reemit
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
                         #   the wheel is packaged, never committed, never edited
native/                  # the native library's C source: filetrace.c
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
