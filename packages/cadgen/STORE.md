# The store

`~/.cache/cadgen/` — where every model's result lives. Read this before
changing anything under `cadgen/store/`, the build pipeline that writes to it,
or a consumer that reads from it. It is written so that someone who only ran
`pip install cadgen` can act on every sentence.

Long on purpose, so jump to the section your change touches. The laws it
serves are in [`README.md`](README.md); where the two disagree, this file is
right.

| § | What it settles | Read it before |
|---|---|---|
| [1](#1-vocabulary) | The one word per concept, and the retired ones | naming anything |
| [2](#2-layout) | What lives under the root, **the two sides law**, and geometry identity versions | adding an entry or a reader, bumping any version |
| [3](#3-tree-and-record) | Tree and record shapes, annotation edges | changing what a build writes |
| [4](#4-the-gate) | The freshness clauses, in order | touching stale/current |
| [5](#5-invariants) | Each invariant with the failure it prevents | any store write |
| [6](#6-link-or-component) | Whether a child becomes a link or the parent's geometry | composition, materialize, packaging |
| [7](#7-concurrency) | Why there is no lock | concurrent builds, publish races |
| [8](#8-gc) | The only sweeper | anything that deletes |
| [9](#9-the-daemon) | The build pool, job ledger and slots | daemon, workers, jobs |
| [9a](#9a-lazy-children) | Lazy children: pins at the call, forcing, exact-`Compound` reference preservation | a decorated call's return, parallel child builds |
| [9b](#9b-editing-previews-and-explicit-saves) | Announced preview trees, the feed, explicit saves | the viewer's live-edit path |
| [9c](#9c-pure-parameterized-features) | `@memo`'s store side (author contract: [`MEMO.md`](MEMO.md)) | operation reuse |
| [10](#10-debugging) | `store why`, resolving a tree, resets smallest first | diagnosing staleness |
| [11](#11-never) | The explicit prohibitions | before proposing any of them |

## 1. Vocabulary

One word per concept; the code uses these words and no others.

| term | meaning |
|---|---|
| **model** | a parameterless decorated function — `@step` (with any stacked `@stl/@glb/@threemf`), `@stl/@glb/@threemf` alone (mesh-only), or `@dxf` (a drawing); identity = its resolved script path plus the function's name, spelled `script.py::function`; a file usually holds one (then the bare path names it and its default output is `<file>.<fmt>`) and may hold several (each writing `<function>.<fmt>`), which share the file's closure; its outputs are what its decorators declare |
| **parent / child** | models related by a call inside a body |
| **build** | running a model's function and publishing its result |
| **store** | the whole cache, `~/.cache/cadgen/`: `objects/` + `index/` |
| **object** | an immutable, content-addressed file in `objects/` — a component or a tree |
| **component** | exact encoded BREP plus an immutable effective face-color recipe; display surfaces are derived separately |
| **tree** | a model's result object: its own components + links, with placements, names, colors; its hash is the model's result identity |
| **link** | a tree entry pointing at a child's tree hash, with placement and name |
| **pin** | the child tree hash a parent resolved during a build (noun and verb) |
| **record** | the mutable per-model entry in `index/`: current tree hash, closure, children pins, outputs |
| **index** | the input-addressed side of the store: records, op-memo entries, mesh entries |
| **op memo** | the per-kernel-operation cache (always two words) |
| **closure** | the source files a model's build read |
| **stale / current**, **gate** | the freshness state and the check that decides it |
| **worker / spare / extra**, **job** | daemon vocabulary (the daemon's own documentation) |

Retired words: node, package, manifest, ref (as a store concept), scope, blob.
They name nothing in the store, in its code or in its documentation.

Two words are NOT retired, and each has exactly one meaning:

- **op memo** — the per-operation cache above, always two words. `@memo` is
  its one author-facing surface: the decorator's contract is
  [`MEMO.md`](MEMO.md) and its store side is [§9c](#9c-pure-parameterized-features).
  A bare "memo" for any other cache is still wrong.
- **descriptor** — a render/export-side word: the owned descriptor an
  appearance is applied to (README law 17), and the bounded pinned-link
  descriptors of [§9a](#9a-lazy-children). It is never a synonym for a tree,
  a component or a record; those three have their own words above.

## 2. Layout

```
~/.cache/cadgen/                      (CADGEN_CACHE_DIR overrides; else the platform cache dir)
  objects/ab/cdef…                    immutable, content-addressed, sharded like git
  index/document/<sha256(file bytes)> ARTIFACT side: {schemaVersion, tree, kind, surfaceProducer?, meshes?} for a file's bytes
  index/model/<sha256(script::function)>  records (input-addressed, mutable, atomic)
  index/output/<sha256(output path)>  {model}: which script wrote the file at this path
  index/component/<cid>               geometry-input entries → encoded BREP and intrinsic recipe
  index/surface/<surfaceInput>        attested extraction inputs → SURF object hash
  index/op/<sha256(op key)>           op-memo entries → object hash, or an inline value
  index/mesh/<key>                    tessellation entries → object hash
```

Nothing else lives under the root. A build's progress is process state, not
content: the daemon's job ledger, read over its socket (§7, §9). Editing
previews use the same immutable objects, with ephemeral request handles in
that ledger (§9b); there is no preview directory or persistent session index.

Operation-index keys include the operation scheme, build123d version, loaded
OCP binding version and cadquery-ocp-novtk provider distribution version.
Unknown runtime versions disable persistent op reuse; normal computation remains available.
These are input-index compatibility fields, never tree/component content or
salts on document-byte keys. Computed results and disk hits share the same
process LRU limit; dropping a RAM entry does not delete its persistent entry or
invalidate a consumer's private geometry.

### The two sides of the store — a law

`objects/` is the **artifact side**: what geometry exists. `index/model`,
`index/output` are the **code side**: what source produced a result and
what it depended on. `index/op`, `index/component`, `index/surface` and
`index/mesh` remember reusable derivations; surface and mesh jobs consume only
immutable artifact inputs. `index/document` is the document lookup: `sha256(file bytes)` → the
tree describing those bytes (plus a mesh ledger keyed by format × tolerances
× pose × appearance — the bare mesh doors read and write it, and a script run notes its
declared meshes there too, so the two front doors never redo each other's work).
GLB variants and model output entries also carry the final serializer revision.
A change to GLB encoding invalidates final GLB exports without discarding
geometry or tessellation results, or affecting STL/3MF freshness.
Animated exports capture the sidecar's embedded animation source before mesh preparation;
the animation variant and the Node builder consume that same immutable text.
Three properties, each enforced by a
test:

1. **No object references source.** No tree or component carries a path, a
   script name, a closure or source hash, or a record key. The same bytes
   anywhere on disk are the same tree.
2. **A reader never consults a record.** A door (`inspect`, `snapshot`,
   `stl|3mf|glb build`, `step build` on a document), the viewer's catalog and
   render, and the mesh ledger find a tree in ONE lookup — hash the file's
   bytes, read `index/document`, read objects — and never open `index/model`
   or `index/output`. A miss is a compile job, never a refusal. The viewer
   reads no record at all — no exception: its status is artifact-side (not
   compiled / compiling / failed) and it never learns which model
   wrote a document. "Is this document behind its source" is `cadgen store
   why`'s and the build tree's question.
   Once selected, the tree and its document digest travel together. A reader
   must not select geometry, then hash a possibly replaced file to bind its
   annotations or export ledger. A snapshot rejects a topology manifest from
   a different selected document instead of combining revisions.
   An explicitly attached editing session has a different input: a complete
   preview tree announced by the build runtime (§9b). It still reads no
   model/output records and never runs source. This input is not a saved file.
3. **Records are deletable.** `rm -rf index/model index/output` loses no
   artifact: every reader still works from objects; a rebuild re-creates the
   records without rebuilding a tree whose objects exist.

`index/document` is written whenever a tree is published for a document — by
a model's build for its `.step`, by a compile job for the file it compiled.
`index/output` is written beside it for `store why` and provenance;
nothing in the viewer or on a render path reads it.

There are exactly two ways a file is named, and that is the only distinction
the store makes:

- **Content-addressed** (`objects/`): the name is `sha256(bytes)`. Two kinds
  of object exist — a **component** (the `.brep` bytes, and separately the
  `.surf` bytes, of one solid) and a **tree** (JSON). Writing an object is
  idempotent; valid bytes are never changed. Geometry completeness requires
  the entire verified required closure before publication. Display readiness
  is separate and disposable. A repair may restore bytes at their exact hash.
- **Input-addressed** (`index/`): the name is derived from what PRODUCED the
  entry (a script path, a kernel operation's inputs, a surface × tolerance),
  and the entry is a small JSON file pointing at objects or recording facts.
  Entries are mutable and written temp + rename.

No directories per result, no hardlinks, no staging directories, no version
salts in object addresses or document-byte keys. An input-addressed derivation
includes its extraction algorithm/schema along with the inputs that affect its
output; this does not change the content address of any object it produces.
The `.step` document, its sidecar and declared mesh files are
**outputs** in the project, not store contents; the record lists them with shas.

### Geometry identity and versions

A component's id (cid) is a hash of exactly three inputs: its BREP bytes, its
intrinsic face colours, and the string `GEOMETRY_SCHEME` (currently
`cadgen-geometry-input-v3`, in `_internal/component_package.py`). That
string is the **only** version on geometry identity. Everything derived from
a component — surfaces (`SURF_VERSION`), tessellations (the tessellation
scheme), index payloads (their `schemaVersion`) — carries its own version and
validates its own compatibility, so a fix in a producer retires that layer's
entries alone and never moves a cid.

- Bump `GEOMETRY_SCHEME` only when the same bytes must map to a different
  tree: a codec or interpretation change. It re-keys every user's store, so
  it is rare and deliberate, and the reason goes in the commit and here.
- Bump the derived artifact's own version for an extractor, mesher or surface
  fix. Never reach for geometry identity to invalidate a derived layer.
- Wiping a store is an operator action (`cadgen store gc`, `store forget`),
  never a hash side effect.

Until cadgen 0.5.1 a global `CACHE_SCHEMA_VERSION` number salted the cid and
was bumped for producer fixes as well as geometry changes (17: mesh section
removed from `assembly.json`; 18: periodic spline domains; 19: components are
the re-read STEP bytes, not the script's shapes; 20: distinct occurrence
colours on a shared TShape). It stopped being hashed when geometry and
derived display assets were separated, and it is retired; do not reintroduce
a salt of that kind.

## 3. Tree and record

### Tree

A tree is the JSON a model's build writes. Its hash is the model's result
identity. A real one (`link_arm`: a bar plus two placements of a pin model):

```json
{
  "kind": "geometry-tree",
  "schemaVersion": 2,
  "label": "link_arm",
  "entryKind": "assembly",
  "units": "mm",
  "components": {
    "0c5932ad05ce64a6": {"kind": "native", "codec": "bintools-v4", "brep": "ebe7552f…", "faceColors": {}, "contentHash": "0c5932ad…"}
  },
  "occurrences": [
    {"id": "o1.1", "name": "bar", "component": "0c5932ad05ce64a6", "transform": [1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1]}
  ],
  "links": [
    {"id": "o1.2", "name": "pin_left",  "tree": "265aee57…", "transform": [1,0,0,-15, 0,1,0,0, 0,0,1,2, 0,0,0,1]},
    {"id": "o1.3", "name": "pin_right", "tree": "265aee57…", "transform": [1,0,0,15,  0,1,0,0, 0,0,1,2, 0,0,0,1]}
  ],
  "assembly": {"root": {"id": "o1", "name": "link_arm", "nodeType": "assembly", "children": [
    {"id": "o1.1", "name": "bar", "nodeType": "part", "leafPartIds": ["o1.1"], "children": []},
    {"id": "o1.2", "name": "pin_left", "nodeType": "link", "tree": "265aee57…", "children": []},
    {"id": "o1.3", "name": "pin_right", "nodeType": "link", "tree": "265aee57…", "children": []}
  ]}},
  "bbox": {"min": [-20, -4, 0], "max": [20, 4, 14]},
  "stats": {"occurrenceCount": 1, "linkCount": 2}
}
```

- `components` are geometry this model created itself, keyed by component id
  (`cid`, the first 16 hexadecimal characters of the complete geometry-input
  hash); each names its encoded `.brep`, declared codec and intrinsic recipe. A model result contains the exact authored source geometry,
  reconstructed from canonical BREP bytes. It is the same result on a miss,
  RAM/disk reuse, a top-level return, and a child call, independent of STEP
  declarations or an attached UI. OCCT's STEP translation can change geometry,
  so a saved document always has a separate tree read back from its bytes
  (`cadgen.store.build.build_tree_through_step`). `occurrences`
  place components; `links` place children's
  trees. Two placements of one child are two links to one tree. Transforms
  are 16 numbers, row-major, translation in the fourth column, in the
  parent's frame.
  Geometry input v3 hashes the closed component kind, declared codec, exact
  unlocated BREP bytes and effective positive face-ordinal RGBA recipe. Absent
  native face ordinals are removed before hashing. JSON ordinal keys are
  converted to strings before canonical sorting, so round trips past ordinal9
  preserve the same identity. Uniform color remains occurrence metadata.
  Named PBR definitions and leaf assignments live in the authored tree's
  top-level `appearance`.
  Extractor, native runtime and surface readiness never enter a native component
  or geometry tree identity.

  Native components are privately decoded before publication. BinTools v4
  retains the existing decoded native semantics and original payload while
  checking exact point-bearing vertex records and referenced placements. Known
  point-parameter loss falls back to pinned BinTools v3, then BRepTools ASCIIv3;
  both alternates require full original native bytes and their own byte fixed
  point. Declared headers are checked before decoding. This is a specific
  known-hazard fence, not an equivalence claim for every possible native state.
  If no codec passes, an explicit `eager-only` component pins the required
  `eagerSurface` in its geometry identity. Native access raises
  `NativeUnavailable`; a saved-file reader may privately reparse its exact
  selected STEP bytes. Authored child pins never substitute a saved document.

  `store.surfaces.request_view` captures a runtime producer separately from the
  tree. The producer contains extraction scheme19, SURF format2 and the actual
  loaded build123d/OCP/distribution versions. Its full input digest includes
  every geometry/appearance/producer field. Unknown versions cannot create a
  shared persistent namespace. `derive` runs in an artifact job, privately
  decodes only captured inputs, verifies the SURF container and writes the
  immutable object before the surface index. Expected output conflicts fail;
  no source, model record, latest child or live authored shape is consulted.
  Geometry reads, STEP re-emits and parent materialization do not derive SURF.
  First display or selector demand pays that work when its disposable result
  is absent; faster native reads do not imply faster first display.

- `assembly.root` is the grouping the author's compound expressed; a link
  appears in it as a node of type `link`.

  The model result and saved document are separate trees. `record.tree` keeps
  authored grouping and intrinsic appearance for exact child pins. A generated
  save also records `documentTree`, built by the same canonical parsed-scene
  path as a cold import, using only hierarchy, names, colors and geometry in
  the STEP bytes. Only this tree is entered in `index/document`.

  Raw-document compilation does not discover neighboring model sources. It
  passes the parsed scene directly to this canonical builder, whose fixed edge
  classes also govern saved readback; it does not construct a discarded Python
  compound or calculate source-only adaptive metadata. Generated models,
  annotated re-emits and public `read_step` geometry retain their existing
  preparation paths. Compilation leaves the STEP and its sidecar untouched;
  declaration consumers retain their normal binding and schema checks.

  Saved readback may reconstruct a private scene from that document index
  when the freshly emitted STEP has an already-seen exact digest. It verifies
  one snapshot of the root tree and every required BREP/eager-surface object against
  its content address; document trees containing source links are rejected.
  Missing, unreadable or damaged objects cause a raw STEP parse. New output
  bytes and forced builds also use the raw parser. Both paths retain the same
  placement, face-color and complete authored-to-written correspondence checks.
  The internal saved-build call retains the selected immutable object bytes
  beside its independently decoded scene until correspondence succeeds. It
  then reuses that exact canonical tree and component identities: native
  decode/re-encode is not assumed to preserve BREP byte identity. Publication
  verifies existing objects and atomically restores missing or damaged bytes
  from this captured closure, required components before the tree. No native
  object or capture survives the call or is attached to a public scene; generic
  scene publication always derives the current mutable geometry and metadata,
  regardless of scene hashes or attributes. Eager-only readback parses the
  selected STEP bytes and uses ordinary canonical publication. Raw publication
  verifies indexed component objects before reuse and derives failed entries
  again; known damaged closures and forced builds derive all canonical
  components. Current authored PBR is rebound after readback, without consulting
  source records, output indexes or staged sidecars.

  Finishes that STEP does not carry persist in the schema-9 sidecar's named
  `appearance.materials` library and `appearance.assignments` map, keyed by
  verified canonical leaf IDs. Resolved
  kinematics are remapped to exact written product nodes, with independent
  descendant validation so nested single-child groups retain their identity.
  Saved readers compose
  appearance into private descriptors; files with identical STEP bytes share
  geometry while retaining their own finishes. Appearance-sensitive exports
  include the normalized appearance digest in their variant, including absence.

  Model records use payload schema7. Earlier records are misses: the next
  source run rebuilds outputs whose input hashes may have been captured after
  a mid-build edit, as well as outputs predating distinct occurrence colours.
  This is one source rebuild; existing geometry and surface objects remain reusable.
  Document mappings remain payload schema4: saved bytes stay
  authoritative and are reparsed without guessing colours that the document
  does not contain. There are no directory or document-byte-key salts. Trees
  use only geometry schema2; there is no optional old-tree decoder. Schema2
  admits resolved named intrinsic appearance on authored trees. Document indexes may carry an
  optional exact loaded `surfaceProducer` hint outside the tree. A same-tree
  rewrite preserves a valid hint and external mesh ledger; a tree replacement
  drops both unless an attested producer is supplied. A reader selects tree and
  hint from one atomic record snapshot. Geometry ignores absent or invalid
  hints. A prepared warm view can use a valid prior producer without importing
  the kernel; its concrete TESS provenance remains valid after SURF deletion.

- Consumers that speak the older flat shape (the viewer client, the Node
  exporters) read a **flattened** tree: `cadgen.store.trees.flatten` expands
  links recursively (ids rebased — a child's `o1.2` under link `o1.3` becomes
  `o1.3.2`; a part child's single occurrence takes the link's name),
  composes transforms, and merges components. `cadgen.store.view` lays that
  out as a temporary directory or serves it virtually; nothing of the sort is
  ever written INTO the store.

### Record

The mutable per-model entry, `index/model/<sha256(model ref)>` where the model
ref is `<resolved script path>::<function name>` — the script and the decorated
function, because a file may hold several models (each its own record, output
and job). An imported document's record is keyed on its own path (no function).
A real one (`link_robot`: a base, two placements of `link_arm`, one of
`link_pin`):

```json
{
  "kind": "record",
  "schemaVersion": 7,
  "model": "/abs/models/assemblies/src/link_robot/link_robot.py::link_robot",
  "script": "/abs/models/assemblies/src/link_robot/link_robot.py",
  "function": "link_robot",
  "entryKind": "assembly",
  "sourceKind": "python",
  "tree": "64429167…",
  "documentTree": "b291420a…",
  "closure": {"hash": "e341ac84…", "files": ["/abs/models/assemblies/src/link_robot/link_robot.py"], "static": false},
  "children": [
    {"model": "/abs/models/assemblies/src/link_robot/link_arm.py::link_arm", "tree": "c161092b…"},
    {"model": "/abs/models/assemblies/src/link_robot/link_pin.py::link_pin", "tree": "265aee57…"}
  ],
  "outputs": {"/abs/models/assemblies/STEP/link_robot/link_robot.step": {"sha256": "823699b0…"}},
  "stepHash": "823699b0…"
}
```

- `children` is recorded from the CALLS the body made — every child wrapper
  entered during the body appends `(model, pinned tree)`, whether that child
  ended up linked, inlined, modified or discarded. It is never derived from
  links.
- `closure.files` is the model's static import closure (AST, transitive,
  first-party, absolute and relative imports alike — a `lib/` package's
  `from .chain import X` counts) **stopping at model files**, plus files executed in its own
  frame and discovered inputs (`read_step` documents). The animation module
  declared by `@step(animation=...)` is source annotation;
  it is embedded in the unified sidecar and never enters geometry identity. The
  boundary is decided statically by what the importer TAKES from a model
  file: only model functions (`from arm import arm`) → a result edge, file
  excluded, the child tracked by its pin (also when that file declares several
  models); a module-level literal (`from plate
  import WIDTH` where `WIDTH = 40.0` — numbers, str, bool, None, tuples/
  lists/dicts of those) → a value edge, file excluded, the value tracked in
  `constants`; anything else (a helper function, a `bd.` object, an
  expression) → a source edge, file included. **Constants by value,
  functions by file, models by result.** Hit and miss runs record identical
  closures by construction. `closure.static: true` marks a record whose
  inputs are not files (a document re-emitted by `cadgen step build`); the
  gate's clause 2 does not re-hash files for it.
- `constants` is `{"<model file, relative to the script>": {"<NAME>":
  "<sha256 of the literal's canonical repr>"}}` — every literal the model
  took from a model file by value. Empty for most models. The gate's clause
  2 re-hashes each value by importing the model file under a **kernel-guarded
  loader** (`cadgen.store.closure.module_constant_hashes`: the script's folder
  and the caller's `PYTHONPATH` on `sys.path`, a private module name, the bytes on disk compiled
  fresh) — a model file whose import pulls the kernel, or fails, reads as
  stale rather than as unchanged. This is why a model file's top level must
  stay kernel-free (`from cadgen import build123d as bd`, no `bd.` in module
  constants): the gate runs it.
- Python records may also carry `unannotatedTree`, exact document occurrence
  and node maps, and `geometryClosure`. Together they permit one narrow
  metadata refresh: same-module literal `kinematics=`, `materials=`, or
  `animation=` values (including literal constants used exclusively there)
  can be reapplied to a complete cached baseline without executing the model
  or rewriting STEP. The recorded geometry closure is derived from the exact
  source buffer that executed. Computed and imported annotations stay in that
  geometry fingerprint; an unchanged one can coexist with a literal edit by
  reusing its recorded value. Changing its expression or dependency, reflection,
  constants used anywhere else, child-pin changes, incomplete trees, and
  changed output bytes fall back to the ordinary build.
- A leaf has `children: []`. Roots and leaves have the same record. A record
  for an imported document (`sourceKind: "step"`) has the document's bytes as
  its closure. Cold compilation does not read earlier model/output records
  or preserve their declared exports when writing this bookkeeping.
- A **drawing** (`@dxf`) is a model like any other: the same wrapper, record,
  gate and job. `entryKind: "drawing"`, `tree: null` (gate clause 4 is
  vacuous), its `.dxf` as the one output, and `children` pinned from the
  models its body called — a flat pattern of `bracket()` goes stale when
  bracket's geometry changes. The viewer and `dxf snapshot` read the `.dxf`
  file directly; there is no drawing-specific freshness anywhere.
- A model's **outputs are whatever its decorators declare**. STEP is one
  output kind, not the primary: a model declared by `@stl`/`@glb`/`@threemf`
  alone has the same tree and record as any model, every stale declared mesh
  is (re)generated from that tree, and no `.step` (and no sidecar) is written
  — `outputs` simply lists no document and `stepHash` is empty.
- `outputs` may carry per-output facts a door needs (`declared`, the
  tessellation `chord`/`angle`); those are the door's, the store only keeps
  them beside the sha.

## 4. The gate

`cadgen.store.gate.stale(model)` — one function for every model. Stale if any
of:

1. **No record.** Protects against reading a result that was never built or
   whose record was collected.
2. **`sha256(closure.files as they are now) != closure.hash`, or a constant
   in `constants` no longer hashes to its recorded value.** Protects against
   a source edit; the hash is a semantic hash of each file's Python
   (comments and formatting do not count), computed at execution time (§5).
   A literal imported from a model file is compared as a value: a comment,
   a body edit or a new helper in that file leaves the importer current; a
   changed value (or the name no longer bound to a literal) makes it stale.
3. **Any recorded child is stale, or its current tree hash differs from the
   pinned hash.** Protects against a child whose RESULT changed — and lets a
   child edit that yields identical geometry leave the parent current.
   Recursion is memoized per request.
4. **The tree object, or any component it (transitively) references, is
   missing.** Protects against a collected or half-copied store.
5. **A declared output does not match `outputs`.** Protects against a deleted,
   hand-edited or foreign `.step`/sidecar/mesh file beside the model.

Mesh tolerances and argv flags are not inputs. Imported STEPs are inputs (a
`read_step` file is in the closure), not models. `--force` rebuilds the named
model only; its children go through the gate as usual. `cadgen store forget
<model.py>` drops the record instead, so the next run — not this one — rebuilds
it (§10, Resets).

## 5. Invariants

Each with the failure it prevents.

- **Hash at execution.** A closure file is hashed when the interpreter
  executes it (an audit hook on `exec`), not after the build. The execution
  window includes module initialization. The model loader records the semantic
  hash of the exact buffer it compiled before executing it, so a replacement
  during module loading cannot substitute a later file's identity. Prevents: a file
  edited during a long build being recorded with the bytes that did NOT run,
  which would make a stale result read as current forever.
  Declared data inputs retain their first declaration-time hash for both STEP
  and DXF builds; an edit later in the body therefore leaves the result stale.
  Since `declare_input` returns a path for the author's own reader, the author
  must keep the file stable between declaration and that read. CAD readers
  that own their input bytes record the exact consumed digest instead.
- **Publish order.** Objects first (components, then the complete tree), the
  document-byte mapping, the outputs (`.step` moved into place atomically;
  digest-bound sidecar), output mappings, then the record. STEP export and
  read-back use a private sibling staging directory outside the store.
  Prevents: a record pointing at a tree that does not exist yet, or a `.step`
  whose sha the record has not seen.
- **Canonical STEP bytes.** Before a written STEP is published, the writer
  canonicalizes what OCCT emitted: NAUO instance ids, presentation-style
  order, and the sign of zero — `-0.` is rewritten `0.`, because which IEEE
  zero a coordinate lands on follows the operation path that produced it, not
  the geometry. Prevents: one model writing two documents, so the packages and
  index entries keyed by the other spelling's bytes are orphaned.
- **Publish rule.** `cadgen.store.publish.decide`: a build rejects replacing a
  current record with a stale one — if the record on disk already reflects the
  closure as it is NOW and the build that finished ran against older sources,
  the result is discarded and an explicit save fails. The expected document
  and annotation digests also detect a competing edit during the build.
  These checks narrow conflicting publication; they are not atomic exclusion
  against another process's rename (§7).
- **Children from calls, never from links.** Prevents: a modified or discarded
  child dropping out of the dependency edge, so an edit to it would not reach
  the parent.
- **Closure boundary rule.** A model file reached only through its model
  function is a result edge (pin); a module-level literal taken from it is a
  value edge (`constants`); anything else taken from it is a source edge
  (file in the closure). Constants by value, functions by file, models by
  result. Prevents both false-current (a constant imported from a model file
  changing unnoticed) and false-stale (a child's internal edit — or a comment
  beside a shared constant — rebuilding every parent).
  One closure calculation may share immutable import-syntax recipes keyed by
  exact source bytes, bounded by 8 MiB of accounted inputs/recipes and 256
  entries. Every lookup still reads the file and resolves current import
  availability, model classification and constant values; the recipes contain
  no resolved dependency graph or freshness verdict and do not outlive the call.
- **The two sides (§2, the law).** No object references source; no reader
  consults a record; records are deletable. Prevents: a moved or copied
  document rendering differently from its twin, a render path going stale or
  refusing because of a record's state, and a store-side cleanup destroying
  anything a user can see.
- **Pins and snapshot isolation.** A parent materializes the tree it pinned
  when the child was resolved, even if the child is rebuilt mid-parent-build.
  Prevents: a parent's result mixing two versions of one child.
- **Objects are immutable.** An object is written once under its hash and
  never edited. Prevents: a component changing under every tree that shares
  it. Saved-document recovery may replace missing bytes or bytes that no
  longer match their address, using newly derived bytes verified against that
  address. This is explicit atomic repair, never deletion after a failed read.
  A writer that finds valid bytes leaves them untouched; racing repair writers
  publish the same content, so no reader sees an intermediate missing object.
- **Portability: a moved project is a set of new models over the same
  objects.** Nothing path-dependent enters an object: closure files are
  recorded relative to the script, trees hold geometry, names and placements
  only, and component ids are content hashes — so a moved or copied project
  hashes to the same closures and the same trees. Records ARE keyed by the
  resolved script path (and function), so after a move every model reads as unbuilt (clause
  1); its first build runs the body once, finds every component and tree
  already present (nothing is re-extracted or rewritten; the tree hash comes
  out identical), writes a new record and re-notes its outputs in
  `index/output`. The moved documents themselves never stopped rendering:
  `index/document` is keyed by their bytes, so every door and the viewer
  find the same tree at the new path before any rebuild; only `store why`
  reads the moved model as unbuilt until then. The
  records at the old path become unreachable and GC collects them. Prevents:
  two projects at different paths sharing one record and one overwriting the
  other's outputs list; and a path or timestamp changing a hash.
- **Outputs are not store contents.** The `.step`, sidecar and meshes live in
  the project; the record validates them by sha (clause 5). Prevents: a
  store wipe destroying a user's documents, and a document pretending to be
  current after a hand edit.
- **No locks are needed for correctness.** Objects are idempotent, entries
  are temp+rename, the publish rule decides concurrent same-model outcomes,
  pins isolate parents. There is no lock layer (§7); two builders of one
  model may do the same kernel work twice, and the publish rule keeps one.

## 6. Link or component

Decided mechanically from the returned geometry and occurrence metadata.

- `cadgen.store.materialize.materialize(tree)` rebuilds a child's geometry as
  a build123d `Compound` and TAGS it with the tree hash and a handle to the
  shape it was built from, together with a private immutable baseline of its
  geometry and descendant metadata. The tag is internal; model authors need
  no additional imports or ownership helpers.
- Its process cache retains at most 64 MiB of immutable canonical BREP bytes.
  Each independent materialization reconstructs fresh kernel shapes; repeated
  occurrences of one component within that materialization share their
  prototype. Different face-color components sharing BREP bytes receive
  private topology, preventing XCAF from overwriting another variant's styles.
  Every occurrence owns its face-color and PBR maps. New byte-cache entries
  require a matching content digest; a hit still requires the object to exist
  on disk. Complete tree capture verifies every required object on each new
  materialization. Intrinsic recipes live in the immutable geometry tree;
  no SURF read or surface-recipe cache is needed. Each exposure receives a
  private dictionary. Clearing the byte memo leaves active consumers' shapes
  and appearance maps valid.
- When the parent's result is written, every tagged child whose native
  partner, geometry and descendant metadata still match its original baseline
  becomes a **link**. Everything else — geometry the parent made, a sub-shape
  it extracted, a child it modified (`housing() - holes`), a mirrored child —
  becomes the parent's own **components**. Modifying a child is legitimate and
  fully tracked (the child is still in `children` because it was called); it
  simply makes the parent own that geometry instead of linking.
  Native identity alone is insufficient: OCCT can mutate an existing TShape,
  and a nested label, color or placement can change independently. Verification
  reads private topology without altering caller geometry or meshing flags.
  Copying a modified child cannot establish a clean baseline for the old tree.
  Root placement, label and color remain link overrides. A part's root color
  replaces its previous color; an assembly's root color inherits into otherwise
  uncolored descendants, preserving explicit descendant colors.
  Native additions/removals are reconciled with surviving wrapper metadata.
  Conflicting native/wrapper hierarchy edits or ambiguous removal of identical
  occurrences fail explicitly instead of discarding geometry or guessing labels.
- A directly returned materialized root carries its component addresses through
  clean placement after that same full integrity check. Packaging reuses the
  pinned encoded BREP and intrinsic recipe instead of deriving their identity a second time.
  Forced extraction uses the pinned canonical bytes; deleted pinned assets
  cause an ordinary identity derivation from the owned geometry. No pointer-only
  shortcut bypasses the native mutation check.
- Placement that keeps the link: `child.moved(loc)` and `Location * child`
  (the same shape, re-placed). build123d's `child.located(loc)` deep-copies
  the geometry (`BRepBuilderAPI_Copy`), which serializes to different bytes —
  a new component id, so a component rather than a link. That is not new
  cost (the copy never shared a component id either); it is why the skill
  places with `moved()`.
- **The materialize contract.** A parent may rely on: the child's exact
  geometry, its labels, colors, owned intrinsic PBR values and placements, as a compound whose children
  mirror the child's grouping. It receives nothing else — a child's sidecar
  content (kinematics, animation, export declarations) never rides up.
- A `link` in a tree is resolved by hash, so two placements of one child are
  two links to one object, and a child shared by many parents is stored once.
  Materialization requires the complete transitive object graph. A missing pin
  is an error, never an empty subtree or a request for the child's newer record.
- Tight occurrence bounds use the existing `op` index, keyed by current native
  geometry and its full linear transform. Translation shifts those six bounds
  directly, so translated instances share the expensive surface calculation.
  Rotation still requires its own tight box; control-polygon bounds are not
  substituted. Disabled, memory-hit and disk-hit paths evaluate the same
  origin-normalized function, and cached numeric arrays are never mutated.
- Canonical saved-document publication already owns each verified component's
  encoded BREP and each parsed occurrence's exact native placement. Its tight
  bounds key uses that BREP identity, codec and rotation in the runtime-scoped
  `op` index, then shifts the six native bounds by translation. A miss measures
  every native leaf with the same optimal extrema operation; it never transforms
  a component AABB. Incomplete private inputs fall back to the ordinary composed
  native document, after the same component validation and closure checks.
- A bounded descriptor composed entirely of pinned links may instead measure
  exact component bounds from verified canonical BREP objects. The existing
  `op` index stores only six finite numbers, keyed by BREP digest, all 16
  placement doubles without rounding, the bounds algorithm and the actual
  native/binding identity. It uses the same private reconstruction, placement,
  native leaf traversal and final numeric extrema merge as the whole document;
  rotated local AABBs and raw native-box merges are not substitutes. Missing,
  corrupt, unsupported or invalid inputs use the ordinary whole-document path;
  forced builds bypass this reuse.
- The internal source publisher may capture that complete descriptor and its
  verified tree/BREP bytes plus normalized intrinsic face-color recipes before its
  callback. Every unique BREP and exact native placement is validated privately
  before publication even when numeric bounds hit; scalar cache entries never
  certify native validity. These same owned prototypes supply bounds misses and
  the later ordinary occurrence/group assembly. Geometry, names, placement,
  grouping, face colors and occurrence PBR remain the captured values; no live
  authored shape, latest child record or store object is read after the callback
  to construct that private document. The normal prepublication disk-closure
  check and declared-child output waits remain in place. Already captured
  ownership survives subsequent cache deletion just as an already materialized
  document does. Arbitrary direct preview callbacks retain the ordinary order.
- Admission allows at most 64 occurrences, 16 components, 32 trees and depth 32;
  aggregate tree bytes and the flattened descriptor each have a 64 KiB limit.
  BREP bytes are limited to 768 KiB, required eager-only SURF bytes to 4 MiB, and retained appearance
  recipes to 256 KiB. This bounds additional encoded payload/recipe retention to
  5.125 MiB, plus bounded Python structures and invocation-owned native shapes;
  it is not a native allocator RSS guarantee. No native shape enters an op
  cache. A failed optional preparation releases its private owners before
  falling back. Larger, new-own-component and unsupported results keep the
  ordinary preparation/publication order. STEP correspondence checks and the
  separate canonical readback of newly emitted saved bytes are unchanged.

Operation keys serialize current geometry from private topology, normalizing
only non-geometric `Free`/`Checked` flags. Native mutations must change the key.
Each input is read again: Python properties can mutate geometry even during key
construction. No TShape-to-content mapping replaces those reads. Shape hashes
use a cheaper subset of the full equality signature, so collisions still require
the complete equality check. Vertex hashes read their current native point at
that same precision, including native point or location edits that leave Python
coordinate attributes unchanged. The bounded rounding memo stores numeric inputs
and outputs, never shapes or geometric signatures.
Input protection and shape-attribute recipes accept actual topology shapes,
including subclasses; geometry values such as vectors remain value arguments
even when they also contain a private native wrapper.

## 7. Concurrency

No persistent build locks. CPU admission and identical child coalescing may
wait; memory admission waits on builds in flight and fails only when nothing
running could make room (§9). Explicit builds
are not cancelled merely because a newer editing request exists.

- **Same model twice.** Both builds run. Each publishes objects (idempotent)
  and then consults the publish rule: the one whose closure matches the
  sources as they are now wins the record; the other's result is left as
  unreferenced objects for GC. A rejected explicit save reports failure.
- **Edit a child while its parent builds.** The parent already pinned the
  child's tree when it called it; it materializes that pin and publishes a
  record whose pin no longer matches the child's current tree. The parent is
  therefore already stale when it finishes — the next gate says so (clause
  3) and the next run rebuilds it. `cadgen store why` shows the mismatch.
- **Edit a parent while a child builds.** Unrelated: the child's record and
  tree are its own. The parent's next build calls the child, finds it
  current, and pins the new tree.
- **Dependency waits** release the parent's CPU slot but retain its geometry
  and memory reservation. A coalesced child may have been started by another
  consumer; it must remain alive while any required consumer uses it.
  The daemon tracks the producer and attached consumers separately. A lost
  producer connection does not cancel work an attached caller still needs.
  The last disconnect retires that particular in-flight entry before its
  worker is stopped; late completion cannot finish a replacement request.
- **No locks.** There is no lock layer: every store write is atomic
  (temp + rename) and idempotent, the document is written to a temp file and
  moved into place, the record cross-validates the outputs by sha (gate
  clause 5), and the publish rule decides same-model outcomes. Progress is
  not on disk at all: the daemon keeps a ledger of every job it runs (state,
  phase n/total, the job's declared output paths) and serves it with `daemon
  status`; the CAD Viewer matches jobs to the documents it shows by output
  path — a CLI build, a parent's child build and its own compile read alike —
  and nothing reads any of it to decide freshness. With `CADGEN_DAEMON=0`
  there is no ledger, and concurrent builds are unbrokered
  — safe by the two invariants above, wasteful, and a debugging mode.

Before a generated body runs, the build captures its target STEP and sidecar
digests (absence counts too). It prepares the result once, exports and reads
back a private STEP, publishes complete immutable objects, and checks source
freshness and the expected output pair. A concurrently written byte-identical
pair is idempotent; a different pair makes the save fail. After the final
renames it verifies the written digests before recording success. A STEP
re-emission has an explicit immutable input/annotation digest, not a Python
closure; its output-pair check still applies.

Each rename is atomic; the group is not a transaction or compare-and-swap.
There is a check-to-rename race with independent CLI or external writers, and
an external writer can replace a successfully saved document later. A failure
before publication preserves the previous pair. A crash after the STEP rename
can leave a missing or mismatched annotation: schema 9 binds annotations to the
STEP's SHA-256, so readers reject that annotation instead of applying old
mates or finishes to new geometry. Material-only saves can retain the same
STEP digest, so refresh and output-pair conflict checks also observe sidecar
content. A stale/missing record does not block saved-byte reads;
missing derived objects are compiled from the bytes that actually exist.
Explicit regeneration repairs the annotation pair. No reader consults locks
or source to recover an artifact.

## 8. GC

`cadgen store gc [--dry-run] [--grace-hours H]` — mark and sweep. Reachable =
every object referenced (transitively, through links) from a record's result
and document trees or a current-schema document index, plus the
objects component/op/mesh entries point at, plus anything modified within the
grace period (default 1 h — the window in which a build may still hold a pin
to a child's previous tree). A saved document retains its geometry even after
model/output records are forgotten. Its mesh ledger records hashes of external
output files; those hashes do not root store objects. No age sweeps, no per-tier rules. GC does not
consult the daemon: the grace period is the whole protection for a build in
flight, so do not sweep with `--grace-hours 0` while anything is building.
Nothing runs GC automatically.

## 9. The daemon

Every build goes through one interface, `cadgen.daemon.executors.submit(model)
-> job`, with two executors that behave identically:

- **Daemon executor (default).** Workers are persistent and warm. The routing
  key is the model (`script::function` — two models in one file are two
  subjects, two workers): a request for a model whose worker is
  idle takes it; whose worker is busy binds a spare as an **extra** for that
  one job (the extra returns to the spare set after); a model with no worker
  binds a spare and a replacement starts in the background; no spare means a
  spawn. Spares load build123d/OCP as well as the lazy tool parsers before
  announcing readiness; importing the supervisor never loads the kernel.
  Spares: `CADGEN_DAEMON_SPARES` (default 2). Requests that name no
  model (`inspect` on a document or an artifact derivation) borrow a spare without binding
  it. Borrowed workers count toward spare capacity while busy, so a stream of
  artifact jobs reuses warm kernels instead of starting a replacement import
  for every request. A subject-less burst may briefly retain already-admitted
  surplus workers so an asynchronous client's next poll can reuse them; after
  two idle seconds the periodic sweep returns the set to the configured spare
  count. An explicit zero-spare pool retires every returning borrowed worker.
  A returning borrowed worker fills an available spare slot rather than counting
  itself as an existing replacement. Worker admission accounts for
  resident memory and pending reservations,
  and may reclaim idle workers or refuse work (§9 below). A worker is recycled after
  `CADGEN_DAEMON_RECYCLE` jobs (default 1000) as a leak hedge, and the daemon
  exits after `CADGEN_DAEMON_IDLE_TIMEOUT` seconds idle (default 3600).
  Inside a worker, `submit` is the same client call back to the daemon, so a
  parent's children land on their own workers while the parent's body runs.
- **Transient executor (`CADGEN_DAEMON=0`).** A subprocess per job, alive for
  this build only. Each imports build123d once, concurrently with its
  siblings. It inherits the environment, so a test's `CADGEN_CACHE_DIR`
  isolates its store; tests and CI run this way.

**One daemon per address, by lock.** The daemon takes a process-lifetime
exclusive lock keyed by its socket address (`cadgen.daemon.transport.
SingletonLock`: `flock` on POSIX, `msvcrt.locking` on Windows, released by the
kernel when the holder dies) before it binds — a private socket is a private
daemon; a second daemon starting for the same address stands down at
once, touching nothing; the winner is by construction alone, so a socket file it
finds is dead and may be removed. Clients elect one spawner the same way and
the rest wait for the address. The lock holder creates that address's authkey
once via a linked temp file and republishes its in-memory key if an external
cleanup replaces the file. This is the one lock cadgen keeps — a singleton for
the daemon, never a build lock (§7): twenty clients starting at once used to
start twenty daemons that unlinked each other's live sockets.

The **store root is a field on every request** (`store_root`), applied per
job in the worker, never inherited from whichever build spawned the daemon:
one daemon serves any number of isolated stores. The daemon holds no store
state of its own. `cadgen daemon status` reports each worker's `model`,
`busy`, `jobs`, `extra`, plus `spares`, `imports` (cold spawns),
`concurrent` (extras bound) and `jobs running n/N, queued m, coalesced k`;
`--json` adds the **job ledger** (`cadgen.daemon.jobs`): every job the
daemon ran in the last 120 s with its state (`submitted` → `queued` →
`building` [phase, done/total] → `done` | `failed`) and the output paths it
declared, parsed statically from the script it names. The ledger is the CAD
Viewer's only progress source, and it is process state, never a file.

The CLI doors (`cadgen step inspect|build|compile`, `stl|3mf|glb build`)
are themselves dispatched through the daemon when one is reachable, so they
run on warm kernels; the subject-less commands (`store`, `doctor`, `daemon
status`, all snapshot orchestration) run in-process. STEP snapshots delegate
missing document compilation and surface derivation to the artifact build pool;
their request resolution and browser orchestration never import the CAD kernel.

When the daemon's runtime changes during a build, the old daemon keeps its
listener and singleton lock until active jobs and their dependencies finish.
New top-level requests run cold during that drain; dependency requests remain
serviceable so a parent cannot deadlock while saving its result.

CPU scheduling and reuse remain independent of memory admission:

1. **Job slots — one running build per core.** A FIFO counting semaphore of
   `N = os.cpu_count()` slots per executor (`CADGEN_JOBS` overrides; daemon-wide
   for the daemon executor, per top-level build for the transient one, whose
   root process runs a private broker its workers inherit). A job takes a slot
   before its body runs and holds it through its emit; it **yields the slot
   while it waits for a child's source result or declared outputs** and reacquires
   — queuing if it must — when that wait ends. A waiting parent holds no CPU slot, which is
   why a 1-slot pool still builds a 3-level tree. It retains its geometry and
   memory reservation. Slots count kernel work only:
   the build pipeline takes one around a model body and its emit. **Doors take
   none and never run a body**: `inspect`, `snapshot` and the mesh doors
   (`stl|3mf|glb build`) ask one question of a document — does the store have a
   tree for this file's bytes (`doors.document_tree`: `sha256(bytes)` →
   `index/document` → tree; no record is opened, §2 the law)? Yes → read it; a
   source that has moved on is the model's record's business, not the door's,
   so no document is ever refused. No → the door (or the CAD Viewer) submits a
   **compile job** to the pool (`executors.submit_compile`) that builds a tree
   from the bytes, generated or imported alike — the one door operation that is
   a job: it runs on a spare, holds a slot through its read and emit, coalesces
   on the document's bytes and shows in the tree. The tree shows `queued` when a
   slot did not come at once.
2. **In-flight coalescing.** A child submit carries its source's closure hash;
   a submit for `(store, model, closure)` matching a job already in flight attaches to
   that job instead of starting another. In flight only, identical source only,
   never a lookup into the past — and never the model a top-level request named
   (a second `python a.py` still runs, on an extra). Two parents needing one
   stale child build it once.
3. **Idle unbind — 10 minutes** (`CADGEN_DAEMON_IDLE_UNBIND`). A bound worker
   idle that long returns to the spare set (spares beyond K exit); its model's
   next build rebinds a spare — no import repaid — with a cold RAM op-memo tier.
   Purely RAM: idle workers hold no slot and never block a new model.

**Memory admission.** The daemon sums worker RSS including extraction
descendants, pending spawn reservations, and retiring workers until they exit.
Idle workers are reclaimed oldest first. Busy/suspended workers retain at
least a worker reservation. That reservation is calibrated, not configured: it
starts at a 512 MiB seed and, on every accounting pass, becomes the lowest RSS
among workers that are idle and have served no job — what a worker costs once
it has imported the kernel and before it holds any geometry — never below the
seed. A worker that has run a body is excluded, so retained geometry cannot
inflate the reservation that keeps it resident; the dependency headroom is
derived from the same number. Ordinary root requests preserve dependency
headroom; nested requests can spend it. A known oversized root reservation or
retained worker may use that headroom only as the sole worker charge, and
only within the total allowance. A request that cannot fit waits while builds
hold run slots or spawns are still starting, since each hands its charge back
when it finishes; a parent fanning out its children submits them all at once
and only a core's worth run. It fails explicitly, with the parent's geometry
still owned, only when nothing is in flight that could release memory, so a
tree of parents all waiting on children they cannot admit errors instead of
hanging.
Reclamation drops process state only; it never runs persistent-store GC.
Reservations and sampled RSS form a soft operating budget. Arbitrary future
native allocations cannot be predicted or stopped by this admission check;
active shared work is not killed merely to recover budget.

| Setting | Default |
|---|---|
| `CADGEN_MEMORY_MB` | 70% of discovered physical/cgroup RAM; `0` disables |
| `CADGEN_COMPONENT_MEMORY_MB` | 384 MiB per extraction subprocess |

The per-worker reservation and the dependency headroom have no settings; the
pool calibrates both. Setting the removed `CADGEN_WORKER_MEMORY_MB` or
`CADGEN_DEPENDENCY_MEMORY_MB` is an error at policy construction rather than a
value silently ignored.

This is a soft admission envelope, not a native allocator limit. A single
OCCT operation may grow between RSS samples. Where RSS cannot be enumerated,
reservations still apply. Transient execution receives extraction-pool sizing,
but has no daemon-wide aggregate process budget. CPU slot counts remain upper
bounds, and extraction concurrency also fits a per-worker extraction ceiling
(a third of the budget, capped at 2048 MiB), which is not the admission
reservation and is likewise unconfigurable.
Geometry publication no longer starts extraction subprocesses for native
components. Surface requests use the shared artifact-job admission and one
private derivation per requested component; they have no model binding,
declared output or editing-producer order. Their time and memory remain real
work, charged when a display or selector first requires them.

**Browser resources.** Disposable decoded meshes, selectors, BVHs, GPU buffers,
textures and worker work may have byte budgets and be reclaimed when unused.
Admission includes replacement overlap and temporary allocations; active
owners must not be invalidated by another scene's release. GPU and worker heap
figures are estimates where browser APIs expose no measurement. Each live
tessellation worker owns its highest completed-request estimate; terminating
that slot releases its charge. Queued temporary reservations and live-slot
ownership are process state, never persistent geometry or cache identity. Such budgets
do not change exact objects, canonical tree hashes or export tolerances, do
not delete the disk cache, and must preserve a usable view on denied work.

## 9a. Lazy children

Inside a body, a child call returns at once with a `LazyCompound`
(`cadgen.store.lazy`) — a `build123d.Compound` whose `.wrapped` is a property.
The gate runs at the call: a stale child is submitted to the pool and the
promise carries the job; a current child is a promise with no job. Geometry
arrives on the first read of `.wrapped` or of the child list — usually at the closing
`Compound(children=[...])`, after every sibling has been submitted — so
siblings build in parallel and the parent waits only for children it
submitted itself. Deferred without forcing: `Pos/Rot/Location * child`,
`.moved()`, `.label =`, `.color =`. Everything else (`.faces()`,
`.bounding_box()`, `.children` and the node views over it, booleans,
`copy.copy`) forces. Most compound constructors
also force; the exact-reference case below postpones native reconstruction:
a body that reads a child before placing the next forces it there, and
parallelism follows the dependencies the author wrote. Forcing waits for the
job's complete final source result, materializes the pinned tree (§6), applies the deferred placement, label
and color, and tags the result exactly as an eager materialize would, so the
link/component decision is unchanged. **Pins are taken at the call**: a
current child's record is read when the parent calls it and its tree is pinned
then, so a rebuild of that child between the call and the force cannot change
what this build composes; a stale child's pin is its job's result, fixed when
that particular job produces it. A `sourceResult` event carries the exact model
reference and tree hash. The job captures it directly; forcing never rereads
the mutable model record. Daemon and transient coalesced consumers receive the
same event, including subscribers attaching after source publication.
Coalescing is scoped by store, model and source closure. The same stale child
called twice shares one job. A failed child without a result raises `ChildBuildError` at the forcing site,
naming the call site in the parent and carrying the worker's output.

Within a model body, an exact `Compound(obj=list_or_tuple)` of lazy children can
prepare later already-pinned inputs before the first pending input yields its
execution slot. This constructs fresh private geometry from a verified tree
snapshot; it does not force another job, publish a wrapper, or apply authored
placement or metadata early. Ordinary forcing still checks the exact pin and
rereads/verifies every prepared object before consuming its own private result.
Preparation errors are retried in the original force order at the same pin.
The constructor hook installs once, and active state belongs to that constructor
and build frame on its thread; exit or failure releases unused preparations.
A plain `Compound(children=list_or_tuple)` also qualifies when `obj` and `parent`
are absent or `None`, and the exact lazy inputs are distinct and unparented.
The original attachment-triggered force starts preparation; anytree still
performs its own validation, attachment and error rollback. Nested constructors,
arbitrary iterators, subclasses and child reparenting keep ordinary forcing.
Admission permits at most eight small unlinked trees,
with 768 KiB of verified BREP bytes and 4 MiB of required eager-only SURF bytes in total;
tree size and component/occurrence counts are also bounded. These limit extra
work and retention, not native allocator RSS. No native cache or thread is added.

An exact plain `Compound(children=list_or_tuple)` with absent/None `obj` and
`parent` can instead preserve references through source publication. It accepts
2–64 distinct, unparented, unforced exact `LazyCompound` inputs from one active
build frame, with ordinary `Location`, `Pos` or `Rot` placements, string labels
and ordinary colors. Custom material, face or tree overrides, mixed inputs and
nested constructors use ordinary forcing. The original constructor validates
arguments and performs attachment and rollback; queued pins resolve in that
same attachment order. Each unique tree is verified once within that private
constructor snapshot. Labels, inherited colors and placement values are captured
when attachment ordinarily consumed them.

The root temporarily has an internal `_ReferenceCompound` subtype. It remains
an `isinstance(..., Compound)`, but exact `type(...) is Compound` introspection
changes until native access. Reading, writing or deleting its native wrapper,
copying, native operations and hierarchy edits install the ordinary native
container and restore its plain Compound class. A child's native escape or
hierarchy edit forces the parent first, preserving the difference between
wrapper replacement and in-place shared-topology mutation. Unexposed inputs
may be packaged as exact links after their frame exits; a different active
frame cannot adopt them. A later packaging/native consumer verifies its pin
again, and final publication still validates the entire required disk closure.

The internal source publisher can read these links through a private scene
adapter without constructing the initial XCAF document. It decodes each distinct
geometry once for that scene and retains separate occurrence/prototype keys so
adaptive topology counts stay unchanged. Ordinary STEP preparation owns its
own private native document. No native object is retained across builds or
shared with an independent authored consumer, and saved STEP read-back remains
separate from the source tree. This is a constructor optimization within the
existing object/index model, not a second assembly store.

Every called child still owes all declared outputs, including a call whose
geometry was discarded. A parent publishes its complete source result and
preview, then waits for all child outputs before its own save. The run retains
these handles and drains every child even if the parent's body or packaging
fails. A child save failure leaves the parent's previous saved document intact;
the attempted source preview may remain visible with failure status. Waiting
for source or saves yields the CPU slot and reacquires it before kernel work;
a one-slot nested build progresses, although it cannot overlap persistence.
Missing pinned objects fail the request rather than substituting a newer tree.

The top-level call renders the graph these calls reveal as a build tree on
stderr (`cadgen.cli_tree`): a TTY gets one refreshed block — `submitted`,
`building · <phase> n/total`, `current`, `✓ <time>`, finished subtrees folded
to one line, current children counted on the parent's line; `--json` or a
non-TTY gets one JSON line per model transition. Child events reach the root
through the pool, tagged with the root request's id, identically for both
executors. After publishing, the root runs its gate once more and says
`already stale: …; rerun` if a child changed during the build.

After a successful top-level build, the caller waits for the checked source
result before returning. A proven discarded bare call in the actual real-file
`__main__` module then returns without materializing that tree into native
geometry. Any caller that consumes the result, any interactive or instrumented
execution, and any uncertain bytecode keeps the materialized return. This does
not shorten source publication, declared-output completion or failure paths.

## 9b. Editing previews and explicit saves

Running existing decorated code publishes a complete preview before the root's
own STEP export/read-back, then continues that same build until its declared
outputs finish. No model author imports a session, cache or ownership helper.
Source files remain the durable authored inputs. The active worker owns the
prepared geometry and frozen child pins for the pending save; a worker crash
fails that request. There is no crash-resumable save queue hidden in the cache.

The daemon identifies each accepted request by an epoch and monotonic ordinal,
records its store root and declared output paths, and attaches producer IDs to
events. An editing session selects the newest request for its output and store;
late older events cannot replace it. It may retain the previous visible model
while the newer request builds. A daemon restart expires request ordering; a
disconnected preview is labelled as such. The ledger is short-lived and
deletable, never the only durable copy of an authored change.

Only model-run producers advance editing order. Compiling saved bytes and
attaching a coalesced subscriber to an existing producer do not create a new
editing revision or hide the producer's preview. A concurrent child request
adopts its announced job before executing, so a completed build leaves no
orphaned pending status behind in the ledger.

These ephemeral preview handles are not GC roots. The normal grace period
protects newly published objects; explicit GC or cache deletion can expire an
older preview, including one retained after a failed save. The feed then
reports that its geometry is unavailable. Already displayed browser resources
remain owned until replaced or closed, but reopening requires a new build.
The durable source and saved STEP remain the recovery path.

The viewer automatically follows active edits for STEP entries. It reads this
channel via `GET /__cad/preview`, validates transitive object availability, and
fetches geometry from the existing object routes. The server
does no kernel work and exposes no source/closure/model record. Without an
available preview, the viewer resolves the saved bytes with the topology and
annotations that belong to them. It reports an incomplete or failed update as
such, and never announces a background file write it did not perform. Preview kinematics are
resolved against the preview tree; the saved sidecar is resolved separately against the read-back
tree and bound to the saved bytes. Within one build, successful authored-tree
kinematics resolution may be reused for that exact tree hash, with independent
copies for preview and saved-document remapping. No resolution survives the
build or substitutes for the read-back remap. Preview and saved events carry
their independently pinned appearance and embedded animation. A saved-tree identity change clears incompatible selection and
measurement state.

An open editing tab holds one request against an opaque ledger cursor scoped
to its output and store. A matching change wakes it immediately; unrelated jobs
do not cause browser updates. The cursor and job snapshot are captured under
the same lock, and a daemon restart changes the cursor's epoch. The daemon
admits at most 32 read-only waiters, separate from build workers and CPU slots;
saturation returns a snapshot without another thread and the client backs off
to 500 ms. A one-second heartbeat
still rechecks actual saved bytes and object completeness even with no build
event. Each heartbeat verifies each unique tree once without retaining its
BREP payloads. Closing or switching the tab aborts its request; a disconnected feed
retries without starting a daemon or a model. This adds no persistent state.

The preview is the model's final immutable source result. Parents may pin and
materialize that result before the child's STEP save finishes. It becomes
`record.tree` only after the model's publication checks and dependent saves
succeed; it is never replaced by translated STEP geometry and never used as a
document-byte mapping. Successful explicit saves require all declared outputs;
publishing a preview alone is not success. In **Follow
edits**, a successful save keeps that revision's authored preview on screen:
the status confirms the STEP save, while the viewport remains explicitly a
preview with its own topology and kinematics. This avoids replacing every
component just because STEP translation changed its canonical encoding.
Choosing **Saved file** displays the validated saved representation instead.
A successful no-op request without a new preview, or an expired preview with
a separately validated saved result, also falls back to that saved input.
No saved byte hash is mapped to a preview tree to obtain this reuse.

An interactive viewer can retain a complete displayed component across a
replacement when its full SURF object hash, component identity, origin and
effective tessellation agree. Tree-specific placements and appearance are
recomposed. This is disposable browser ownership, not a new persistent cache
or source of geometry identity. Superseded or failed staging does not release
the last complete view's ownership. No automatic-save producer exists in this
runtime: all decorated runs have explicit completion obligations, so display
supersession does not cancel their exports.

## 9c. Pure parameterized features

The optional `@memo` decorator declares a pure intermediate geometry
factory, with the author preconditions and execution limits in
[`MEMO.md`](MEMO.md). It declares no output, model record or job. The
existing `index/op` maps its scheme/runtime/code/source/helper/global/default/
closure/argument key to a canonical BREP object and attribute recipe. Objects
contain no source paths. Hits verify disk content and reconstruct a private
shape; misses, disabled reuse and hits apply the same eligible return codec.
No native shape is retained between calls. Missing or corrupt objects re-miss
and repair through the ordinary atomic object/index writes.

Only a worker bootstrap preceding authored module loading can establish reuse
trust. Generic embedded execution runs the body, and cannot upgrade an earlier
untrusted snapshot. Guards are defensive checks within the declared pure-factory,
unmodified-dependency contract, not a complete proof about arbitrary Python
monkeypatches. Unsupported code or inputs execute normally. Code recipes are
bounded to 256 entries and 1 MiB; no persistent trace or hidden dependency graph
is added. Captured helper files stay in the model's closure on a hit, and full
source-file digests conservatively invalidate other features in that file.
Explicit model saves still obey every child/output/publication requirement.

## 10. Debugging

- Which record: `index/model/<sha256(script::function)>` —
  `cadgen store why <model.py>` prints it (every model of the file; name one
  as `model.py::function`), the gate's verdict clause by
  clause (with each child's pinned vs current tree), the closure files and
  the tree's links. The verdict line names the first stale clause as a
  phrase: `no record`, `closure changed: <file>` (the record keeps each
  closure file's hash under `closure.shas`), `constant changed: <NAME> in
  <file>`, `child stale: <child.py>`, `child result moved: <child.py>`,
  `tree or components missing`, `never written: <path>`, `output missing:
  <path>`, `output changed: <path>`.
- Resolve a tree: `cadgen.store.trees.get_tree(hash)`; flattened with
  `capture_tree(hash)` for an owned verified flattened view and byte closure.
  Metadata-only consumers use `capture_tree(hash, retain_payloads=False)` to
  perform the same complete verification while releasing each raw object after
  reading it. Compact process-local metadata may be reused while every required
  immutable object retains the file identity observed around its verified read;
  deletion, damage or atomic replacement invalidates that snapshot and makes the
  next request verify the complete byte closure again. A read is only remembered
  once it is far enough past the write it observed that a further write must
  stamp a different mtime — a filesystem times writes by a clock of its own
  resolution (~15.6 ms on Windows, whose `st_ctime` is the creation time and
  never moves for a rewrite), and a same-size rewrite inside that tick is
  invisible to every stat field. The metadata cache is byte-bounded, store-root
  isolated and returns a newly parsed flattened view to every caller.
  Components carry `brep`, `codec` and `faceColors`; display SURF resolves
  separately through `store.surfaces` and `index/surface`.
- `cadgen store info` sizes the store. `cadgen store gc --dry-run` lists what
  a sweep would remove.
- **Resets, smallest first.** `python model.py --force` rebuilds one model
  now. `cadgen store forget <model.py>` drops that model's record (the next
  run rebuilds it; children untouched, parents see the moved pin then);
  `cadgen store forget <document>` drops the `index/document` entry for the
  file's bytes and the record that wrote it, so the next open or door call
  compiles it again. `forget` never deletes objects — `cadgen store gc` does,
  for whatever no record reaches any more. Clearing the store is always safe:
  delete `~/.cache/cadgen` (or the `CADGEN_CACHE_DIR` directory); every model
  reads as stale and rebuilds; no project file is touched.
- The gate has no cadgen-version clause: a record built by a cadgen with a
  bug stays current after the fix, and so does every parent tree that linked
  what it built. Recover with `forget` on the affected models (or the parents
  that link them), or clear the store.

## 11. Never

- Write a file into the store non-atomically (objects: temp + rename under
  the hash; entries: temp + rename).
- Put a path, a timestamp, or anything machine-specific into an object.
- Derive a model's dependencies from its tree's links.
- Add a version salt to a store name, or a global schema number to component
  identity (§2, geometry identity and versions).
- Add a lock that a reader consults to decide freshness — or any build lock
  at all; the publish rule and pins are the whole concurrency story.
- Let a door, the viewer, snapshot or any render path open `index/model` or
  `index/output` (§2, property 2). A reader's one lookup is `sha256(bytes)` →
  `index/document` → objects.
- Make a reader refuse, or a door rebuild from source: a missing tree is a
  compile job from the file's bytes; "behind its script" is `store why`'s.
- Run automatic persistent-store GC or use process/display eviction as a
  reason to mutate exact geometry. Disposable memory budgets and worker
  reclamation follow §9 and never determine saved-artifact freshness.
- Let a decorator argument change the geometry a model produces: arguments
  place files, tune how they are written, and declare kinematics; the tree
  is the return value as returned (README law 16).
- Write a sidecar for anything but kinematics, or copy into it what only a
  record needs (README law 17): a mesh door tessellates the document's tree
  and never reads a declaration back.
- Use a retired word (§1) in code or documentation.
