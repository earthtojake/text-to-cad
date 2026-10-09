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
| [8](#8-gc-eviction-and-the-cap) | The sweeper: retired kinds, eviction to the cap, unreachable objects, a store two cadgens share, and why a pass needs no lock | anything that deletes |
| [9](#9-the-daemon) | The build pool, job ledger and slots | daemon, workers, jobs |
| [9a](#9a-lazy-children) | Lazy children: pins at the call, forcing, exact-`Compound` reference preservation | a decorated call's return, parallel child builds |
| [9b](#9b-editing-previews-and-explicit-saves) | Announced preview trees, the build feed, explicit saves | what the viewer says while a build runs |
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
| **index** | the input-addressed side of the store: records, bounds, mesh entries |
| **closure** | what a model's build depended on: the source it reaches, the files it read, the folders it listed, and the files its imports rely on not existing |
| **stale / current**, **gate** | the freshness state and the check that decides it |
| **claim** | what a write does to an object it finds already present: its mtime becomes now, less two ticks of its clock, so the sweeper's grace window covers it and the claiming process keeps what it verified of it (§8) |
| **evict** | drop a derived entry to keep the store under its cap; only the derived kinds are ever evicted (§8) |
| **obsolete** | a surface, selector-table or mesh entry an older extractor, table scheme or mesher of cadgen's wrote, or a record or document entry at a key this cadgen does not own (another schema version's): no reader of this cadgen asks for it again, and the sweeper retires it once it is a week old (§2, §8) |
| **worker / spare / extra**, **job** | daemon vocabulary (the daemon's own documentation) |

Retired words: node, package, manifest, ref (as a store concept), scope, blob.
They name nothing in the store, in its code or in its documentation.

One word is NOT retired, and it has exactly one meaning:

- **descriptor** — a render/export-side word: the owned descriptor an
  appearance is applied to (README law 17), and the bounded pinned-link
  descriptors of [§9a](#9a-lazy-children). It is never a synonym for a tree,
  a component or a record; those three have their own words above.

## 2. Layout

```
~/.cache/cadgen/                      (CADGEN_CACHE_DIR overrides; else the platform cache dir)
  objects/ab/cdef…                    immutable, content-addressed, sharded like git
  index/document/<sha256(file bytes)>-v<schema>  ARTIFACT side: {schemaVersion, tree, kind, surfaceProducer?, meshes?} for a file's bytes
  index/model/<sha256(script::function)>-v<schema>  records (input-addressed, mutable, atomic)
  index/output/<sha256(output path)>  {model}: which script wrote the file at this path
  index/component/<cid>               geometry-input entries → encoded BREP and intrinsic recipe
  index/surface/<surfaceInput>        attested extraction inputs → SURF object hash
  index/selector/<surfaceInput>-s<scheme>  a surface's selector table (refs, facts, chains) → object hash
  index/bounds/<sha256(bounds key)>   bounding boxes of stored geometry, inline
  index/mesh/<key>                    a component's mesh at one tessellation → GLB object hash
  index/drawing/<sha256(scheme + document hash)>  a 2D drawing's render payload → object hash
  index/skin/<sha256(scheme + document + animation + meshes)>  a document's tube skins → object hash
  index/section/<sha256(scheme + BREP + plane)>    one component's exact cut by one plane → object hash
  index/robot/<sha256(scheme + path + description hash + paired URDF hash)>  a robot description resolved for a player → object hash, plus its primitive meshes
```

Nothing else lives under the root. A build's progress is process state, not
content: the daemon's job ledger, read over its socket (§7, §9). Editing
previews use the same immutable objects, with ephemeral request handles in
that ledger (§9b); there is no preview directory or persistent session index.
A **retired kind** is one an older cadgen wrote and nothing reads any more:
`RETIRED_KINDS` in `store/paths.py`, today only `index/op`, the operation
cache of cadgen 0.7.4 and earlier. The sweeper removes it with every object
only it named (§8). Retiring a kind means moving it from `INDEX_KINDS` to
`RETIRED_KINDS`. Any other folder under `index/` belongs to a newer cadgen or
to none, and nothing here touches it.

An **obsolete** entry is the same thing one entry at a time, in a kind still
in use: a surface entry whose producer's extraction scheme and SURF format are
no newer than this cadgen's and not both the same
(`surfaces.obsolete_entry`; an eager-only one, which names no producer, was
keyed under an older SURF format), a mesh entry keyed by an older mesher or
mesh format (`meshes.obsolete_key`), a selector table keyed by an older table
scheme (`selectors.obsolete_key`), or a mesh or table keyed by an obsolete
surface's input. No reader of this cadgen computes those keys again, but an
older cadgen sharing the store still may, and a read never writes. So the
sweeper retires an obsolete entry, with every object only it named, once it
was last written a week ago (`gc.OBSOLETE_RETIRE_AFTER_SECONDS`), and an
obsolete surface with its meshes and table, once the youngest is (§8): an older cadgen
still in use derives each again at most once a week, and an upgrade's
leftovers go within about a week. A newer cadgen's derived entry is never obsolete.
Kernel versions are not ordered here: an entry of another build123d or OCP is
left to the cap.

Records and document entries carry their schema version in their key,
`<key>-v<schema>` (`index.versioned_key`; `RECORD_SCHEMA_VERSION` and
`DOCUMENT_SCHEMA_VERSION` in `store/records.py`). A cadgen reads and writes only
the keys of its own versions (`gc.owned_key`): two cadgens of different schemas
sharing a store -- a plugin pinned to one release, a checkout on the next --
each compile a document and build a model once and then find their own entry,
and neither rewrites the other's (and with it its mesh ledger). A format change
bumps the version and so lands on new keys; nothing reads, recognises or
migrates another version's entry. Any key this cadgen does not own --
another schema version's, or the unversioned key a cadgen before this rule
wrote -- is obsolete here, retired a week after its last write like the others
(§8), and until then the trees it names stay reachable.

`index/bounds` holds bounding boxes of stored geometry (`store/bounds.py`).
A key names what was measured and how: a component's BREP object hash or a
leaf's BinTools digest, the placement it is measured in, the measuring
algorithm, and the loaded kernel's versions (build123d, OCP and its
distribution); the value is six numbers, inline. A box is a pure function of
that key, so a hit can never differ from a measurement, and an unknown kernel
build just measures. Beside the boxes, keyed the same way by a component's
codec and BREP object, it holds that component's **leaf layout** — how many
leaves the encoded shape has and whether every one sits at the prototype's
own placement — which canonical publication records as it measures those
leaves, and which tree composition (§3) reads to name the exact per-leaf box
keys without decoding the shape. For an all-link result past the bounded
capture it holds each link's bounds (§6): the merge of the leaf boxes the link
places, keyed by the child tree it links and its exact placement. Keyed like
the leaf layout, it holds each component's **topology** — its face and edge
counts, how many of each are curved, and its loose box — the facts the
adaptive edge policy classifies a scene's prototypes by
(`step_scene_mesh.prototype_topology`). An all-link parent's build reads them
by the BREP each pin names and decodes a pinned component only when its entry
is missing or invalid, so its edge classes are the ones the decoded prototypes
give; a scene of an authored compound (a parent with geometry of its own)
still measures its prototypes. Nothing in the index holds a value
computed while a model runs (README law 18): a model's own checks and
operations always execute.

### The two sides of the store — a law

`objects/` is the **artifact side**: what geometry exists. `index/model`,
`index/output` are the **code side**: what source produced a result and
what it depended on. `index/bounds`, `index/component`, `index/surface`,
`index/selector`, `index/mesh`, `index/drawing`, `index/skin`,
`index/section` and `index/robot` remember reusable derivations; surface,
selector, mesh, drawing and section jobs consume only immutable artifact
inputs. `index/drawing` is a
2D document's flattened render payload: its key hashes the extraction scheme
(payload shape × the drawing library's release) together with the document's
content hash, so the same bytes are never flattened twice and an upgrade lands
on a new key instead of invalidating an old one in place. `index/robot` is the
same for a robot description (URDF, SDF, or an SRDF with its paired URDF)
resolved into the articulation and visual list a page plays
(`cadgen.robot_payload`): its key hashes the scheme (the payload's shape, its
resolution revision -- raised when the same bytes resolve differently -- the
articulation's format and the display tessellation), the description's path
(the payload names each link mesh by the absolute path it resolved beside the
description) and the content hashes of the description and the paired URDF,
and the entry also names the primitive meshes the payload draws (`meshes`),
which a sweep keeps with it. `index/skin` is the
same for a document's bending tubes as a CAD view plays them
(`_internal/tube_skin_payload.py`): its key hashes the payload's scheme, the
document's content hash, the digest of the sidecar animation that bends them and
the mesh entries they bind, so an edited clip, a new mesher or a new binding rule
lands on a new key. `index/section` is one component's exact section (`store/sections.py`): the
material a plane cuts from its BREP's solids (and the curves it cuts from its
sheets), in its own coordinates, made by a build-pool `sections` job. Its key hashes the section scheme, the BREP's codec and object
hash, and the plane (unit normal and offset, rounded before they key or cut
anything), so every occurrence a plane meets the same way shares one entry,
and a new scheme lands on new keys. `index/document` is the document lookup: `sha256(file bytes)`, under
this cadgen's document schema (above), → the tree describing those bytes (plus a mesh ledger keyed by format × tolerances
× pose × appearance — the bare mesh doors read and write it, and a script run notes its
declared meshes there too, so the two front doors never redo each other's work).
Mesh variants and model output entries also carry their format's final serializer
revision. A change to one format's encoding invalidates that format's final exports
without discarding geometry or tessellation results, or affecting the other formats'
freshness.
Animated exports capture the sidecar's `animation` keyframes once, before mesh preparation;
the animation variant and the clip sampler consume that same immutable text.
Three properties, each enforced by a
test:

1. **No object references source.** No tree or component carries a path, a
   script name, a closure or source hash, or a record key. The same bytes
   anywhere on disk are the same tree.
2. **A reader never consults a record.** A reader (`read_scene`, `snapshot`,
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
   `read_scene` retains verified native bytes and decodes prototypes on demand.
   Its occurrence and selector views stay bound to that captured revision;
   each `shape()` returns privately copied topology. An already open scene
   survives document replacement or deletion of its cached objects.
   A build's preview tree (§9b) is the build's own: a parent may pin a child's,
   and no viewer displays one.
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
  entry (a script path, measured bytes and their placement, a surface × tolerance),
  and the entry is a small JSON file pointing at objects or recording facts.
  Entries are mutable and written temp + rename.

No directories per result, no hardlinks, no staging directories, no version
salts in object addresses. An input-addressed entry's key includes what its
value depends on, its extraction algorithm or schema version along with its
inputs; this does not change the content address of any object it produces.
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
  A saved-document read-back skips that private decode for a parsed prototype
  whose exact bintools-v4 bytes already exist as an object under a component
  entry declaring the same native recipe: the fence was proven for those bytes
  by the build that published them, and the parsed prototype — private to its
  parse, measured but never meshed — stands in as the prepared native input.
  A forced build derives and fences every component again.

  `store.surfaces.request_view` captures a runtime producer separately from the
  tree. The producer contains extraction scheme 20, SURF format 3 and the
  actual loaded build123d/OCP/distribution versions. A format-3 SURF holds what
  its readers -- selection, measurement, feature recognition -- take and no
  tessellation input: loops are edge references, a B-spline surface keeps its
  degrees and pole counts (a bilinear patch its four corners), a swept surface
  its axis or direction, a general curve its range. Format 2 stays readable:
  an older build may have pinned one in an eager-only component's identity.
  The surface input digest includes every geometry/appearance/producer field.
  Unknown versions cannot create a shared persistent namespace. `derive` runs
  in an artifact job, privately decodes only captured inputs, verifies the SURF
  container and writes the immutable object before the surface index.
  Expected output conflicts fail; no source, model record, latest child or live
  authored shape is consulted.
  Geometry reads, STEP re-emits and parent materialization do not derive SURF.
  First display or selector demand pays that work when its disposable result
  is absent; faster native reads do not imply faster first display. A build's
  kinematics are selector demand only where a selector is named: a mate's
  parent and child resolve in the result tree's occurrences, group nodes and
  their labels, with no component read, and an `axis={"ref": ...}` reads the
  SURF of the one component its occurrence places
  (`_internal/kinematics_resolve.py`).

  Every surface is derived with the component's **selector table**
  (`_internal/selector_table.py`, stored by `store/selectors.py` under
  `index/selector/<surfaceInput>-s<scheme>`): the one place a ref's facts are
  minted. From the exact BREP and the SURF it holds, per face, edge and vertex,
  the local id a ref ends in (`f7`, `e3`, `v2`), the exact metrics and
  parameters the SURF carries, the plane normals, whether an entity can be
  referenced, its relevance, every adjacency (face–edge, edge–vertex), each
  edge's chain and each face's tangent group — the sets the viewer's connected
  selection grows a pick to. The CAD Viewer joins the table to the mesh's face
  and edge tables by ordinal and composes `occurrenceId + "." + localId`; the
  CLI (`assembly_lookup`) reads the same table from a view's
  `components/<cid>.selectors.json`. So a ref the page shows resolves in
  `inspect` to the entity it names, and nothing in a browser mints one. The
  table is served by the surface request's ready row (`selectors`) through the
  same store route as the surface, and a surface without its table is not
  ready: the request derives it again, from the stored surface and BREP. The
  scheme is bumped for any change in what the table holds, and an older
  scheme's entry is obsolete (§2).

  Meshes are derived the same way, and by cadgen alone. `derive` with
  `tessellations` meshes each component after its surface
  (`_internal/occt_mesh.py`: OCCT's `BRepMesh_IncrementalMesh` on the exact
  BREP, the chord tolerance a fraction of the component's bounding diagonal, the
  angle in radians; a face OCCT refuses is tessellated over its own parameters by
  `_internal/face_fallback.py`) and writes each body (`store/meshes.py`) before its
  `index/mesh` entry. The key is the surface input, the mesher and format
  versions and the two tolerances' float64 bits, so a mesher fix lands on new
  keys. A body is glTF 2.0 binary (format 6) in the component's own units: ONE
  triangle primitive (positions, normals, u16 indices up to 65,535 vertices,
  else u32), a face table whose rows give each face's ordinal, contiguous index
  range and colour, an edge table giving each edge's ordinal, class and run of
  polyline points, and the points; the JSON chunk is the canonical JSON for the
  body's identity, bounds, scale and colour palette, which every reader rebuilds
  and requires before it views the arrays in place. Any glTF viewer draws it
  (its one node turns Z-up millimetres into Y-up metres); the tables are
  `extras`. A face no mesher covers -- OCCT refused it and the fallback's
  triangles missed its area by more than a quarter -- never fails the component:
  it is meshed without that face, whose range is empty, and the body names it
  (`unmeshedFaces`, only in a body that has one; its record counts them,
  `unmeshedFaceCount`). Every reader says so: a view or a list warns which faces
  of which part it does not draw or count, the CAD Viewer names the parts it
  draws without them, and a mesh export warns that its file has a hole there and
  is not watertight. A face smaller than the mesh resolves
  (area under the deflection squared) may have no triangles and is not named. Any
  other failure -- OCCT raising, a body its encoding refuses -- is the component's
  `MeshProductionError`. A component is ready once its surface and every mesh asked for are
  stored: the CAD Viewer's cold components ask for the standard level in the
  surface request that derives them, a mesh export asks for its tolerances (a
  build's own export derives them in the build's process, §9), and
  the snapshot host has the build pool mesh what its page found missing, from
  the stored surface record alone (`POST /__tess_cache/produce`: `meshes` jobs
  running `produce_meshes`, the keys dealt across the daemon's warm workers, and
  across more only for enough keys to repay starting one), with no tree.
  Tolerances outside the tessellation policy's bounds
  (`tessellation_policy.tolerance_refusal`) are refused, never meshed. No client writes a mesh: every reader probes and reads, and the routes
  refuse a POST to an entry (405).

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

  **Tree composition.** A child's read-back is context-free. The parent's
  STEP places each child's prototypes from the same bytes the child's own save
  emitted, every group at the identity and every leaf at its flattened world
  transform, so the components, hierarchy, names, colours and the linear part
  of every leaf placement the parent's STEP reads back are exactly those in
  the child's own document tree; only each leaf's translation is new, and it
  is the number the parent's descriptor handed the writer, as its STEP text
  round trip (`store/_compose_readback.py`, `written_real`). A saved build of
  a parent whose fresh bytes have no indexed tree therefore composes its
  document tree from its children's document trees instead of parsing the
  STEP it just wrote, when all of this holds, checked exactly: the result is
  links only (no geometry of its own); every link is a pure translation (its
  linear part exactly the identity) with no link colour, and every link and
  group name survives the label round trip; every link's child record still
  pins the tree the parent used, with a complete `documentTree` whose root is
  an assembly, whose components are all native and whose every node is named
  by a name the label round trip keeps;
  every leaf box the canonical bounds path would take is already in
  `index/bounds` from the child's publication, under a leaf layout (§2)
  whose leaves all sit at the prototype's placement; and the writer emulation
  reproduces every translation in each child's own document from that
  child's descriptor. Anything else — a rotated or coloured link, a part
  child, a parent with geometry of its own, a child rebuilt since the parent
  called it, a missing object or box — takes the ordinary read-back of the
  written bytes, as does a composed tree that fails the authored-to-written
  correspondence. The composed tree is published and captured exactly as an
  indexed read-back of already-seen bytes is, so the correspondence check,
  the canonical maps and the restore are the same code, and `index/document`
  receives a tree equal to the cold compile of the bytes. Under `--verbose` a
  composed tree shows as the stage `tree: compose document from children`;
  `CADGEN_VERIFY_READBACK=1` (§10) proves a corpus by parsing as well and
  failing the build on any difference. This adds no staleness class: the gate
  decides whether the parent runs by its sources, and what it publishes for
  its bytes is the same tree either way.

  **Spliced documents.** The same parent's STEP is almost entirely its
  children's: OCCT writes the root's product tree, then every child's products
  and geometry exactly as the child's own save emitted them. A saved build
  therefore writes it from those files instead of exporting its whole document
  (`store/_splice_step.py`). It generates the parent's own records, OCCT's
  layout record for record: the header the children share, renamed for the
  file; the root and group products; one instance block per link. It then
  copies each child's DATA section verbatim, with its entity ids under a
  fixed-width prefix and its literals untouched. NAUO instance ids run 1..N in
  file order. A translated link rewrites its leaf placements' points to the
  text the writer prints for the parent's leaf translations, once the emulation
  reproduces each child's own text.

  It splices only when all of this holds, and exports otherwise:
  - no geometry of its own;
  - uncoloured pure-translation links;
  - each child linked once (OCCT shares a repeated child, a splice would copy
    it);
  - every child's file still has the bytes its record pins;
  - one writer and kernel wrote every child, in the same units;
  - names without a backslash or a control character, which take the
    writer's own escapes;
  - ids below 10^9;
  - OCCT's layout is recognised at every record the splice reads.

  A forced build exports. Under `--verbose` the stage names which ran:
  `tree: splice STEP <file>` or `tree: assemble STEP <file>`. A parent that
  will splice assembles no private document before its callback: its bounds
  merge from its links' (§6), and it assembles a document only for a link
  whose bounds miss (that link's part alone) or once the splice proves
  ineligible, after the callback; a pin deleted meanwhile then fails the build
  before anything is saved.

  The spliced file's cold compile is the exported file's, and the composed
  tree binds to it as to any other bytes; `CADGEN_VERIFY_READBACK=1` proves
  that on a corpus. Its bytes differ from OCCT's:
  - ids are numbered differently;
  - geometry that two children share is written once per child;
  - the root context's uncertainty is the first child's.

  Hence `STEP_WRITER_SCHEME` 2. Those bytes are a function of the children's
  saved bytes. The parent's writer input fixes those, except for the writer
  that saved a child: a child kept from an earlier writer is spliced as saved,
  which is a valid document of the same tree.

  **Kept documents.** A rebuild may keep its saved document instead of writing
  the same bytes again. The record's `writerInput` is the sha256 of everything
  the saved STEP's bytes are a function of
  (`cadgen.store.build.writer_input_digest`): the flattened descriptor the
  writer is given — geometry by BREP object hash with intrinsic face colours,
  placements, names, colours and grouping — the file name,
  `STEP_WRITER_SCHEME`, the cadgen release and the loaded kernel. It leaves
  out only the root's authored name (the root product is named after the file)
  and finishes (README law 16). When a rebuild's writer input equals its
  record's, the STEP on disk when the build started still has the recorded
  `stepHash`, and that document's tree is complete, the build publishes its
  result and writes only the record, and the sidecar if its bytes changed: no
  export, no read-back, no correspondence. An unchanged sidecar keeps its file
  as the document does, because viewers version it by its stamp and a new one
  reloads the model. The recorded `documentTree` and maps carry over, the
  result takes the recorded result's bounds, which the input pins, and the run
  says `kept STEP`. The writer is pure (README law 5), so those bytes are what
  a write would produce. A forced build always
  writes; so does any rebuild whose record lacks `writerInput`. Bump
  `STEP_WRITER_SCHEME` with any change to the bytes cadgen writes for the same
  descriptor.

  Finishes that STEP does not carry persist in the schema-10 sidecar's named
  `appearance.materials` library and `appearance.assignments` map, keyed by
  verified canonical leaf IDs. Resolved
  kinematics are remapped to exact written product nodes, with independent
  descendant validation so nested single-child groups retain their identity.
  Saved readers compose
  appearance into private descriptors; files with identical STEP bytes share
  geometry while retaining their own finishes. Appearance-sensitive exports
  include the normalized appearance digest in their variant, including absence.

  Model records use payload schema 8 (reach slices, import-time slices, absent,
  roots and listing entries). Earlier records are misses: the next source run
  rebuilds outputs whose input hashes may have been captured after a mid-build
  edit, as well as outputs predating distinct occurrence colours.
  This is one source rebuild; existing geometry and surface objects remain reusable.
  A record with no `closure.own` leaves nothing out of its listings, which is
  how it hashed them, so it needs no new schema.
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
  the kernel; its concrete mesh provenance remains valid after SURF deletion.

- Consumers that speak the older flat shape (the viewer client, the mesh
  exports) read a **flattened** tree: `cadgen.store.trees.flatten` expands
  links recursively (ids rebased — a child's `o1.2` under link `o1.3` becomes
  `o1.3.2`; a part child's single occurrence takes the link's name),
  composes transforms, and merges components. `cadgen.store.view` lays that
  out as a temporary directory or serves it virtually; nothing of the sort is
  ever written INTO the store.

### Record

The mutable per-model entry, `index/model/<sha256(model ref)>-v<schema>` (the
record schema below, §2) where the model ref is `<resolved script path>::<function name>` — the script and the decorated
function, because a file may hold several models (each its own record, output
and job). An imported document's record is keyed on its own path (no function).
A real one (`link_robot`: a base, two placements of `link_arm`, one of
`link_pin`):

```json
{
  "kind": "record",
  "schemaVersion": 8,
  "model": "/abs/models/assemblies/src/link_robot/link_robot.py::link_robot",
  "script": "/abs/models/assemblies/src/link_robot/link_robot.py",
  "function": "link_robot",
  "entryKind": "assembly",
  "sourceKind": "python",
  "tree": "64429167…",
  "documentTree": "b291420a…",
  "closure": {"hash": "e341ac84…", "files": ["link_robot.py", "lib/frame.py"], "shas": {"link_robot.py": "ast1:…", "lib/frame.py": "slice4:…"}, "names": {"lib/frame.py": ["WIDTH", "bar"]}, "wholes": {"lib/frame.py": "ast1:…"}, "own": {}, "static": false},
  "children": [
    {"model": "/abs/models/assemblies/src/link_robot/link_arm.py::link_arm", "tree": "c161092b…"},
    {"model": "/abs/models/assemblies/src/link_robot/link_pin.py::link_pin", "tree": "265aee57…"}
  ],
  "outputs": {"/abs/models/assemblies/STEP/link_robot/link_robot.step": {"sha256": "823699b0…"}},
  "stepHash": "823699b0…",
  "writerInput": "5f0c27d1…"
}
```

- `children` is recorded from the CALLS the body made — every child wrapper
  entered during the body appends `(model, pinned tree)`, whether that child
  ended up linked, inlined, modified or discarded. It is never derived from
  links.
- `closure.files` is the model's static reach (AST, transitive,
  first-party, absolute and relative imports alike — a `lib/` package's
  `from .chain import X` counts, and importing `lib.x` executes
  `lib/__init__.py`, so the package is in it) **stopping at model files**, plus files executed in its own
  frame, what importing its children ran in its process (below), and every
  data file the build read, whoever opened it -- Python's `open`, numpy, an
  OCCT reader in C++ (§5, every read is seen). Nothing is declared. A file
  read is not an input when the build wrote it, when it is one of the model's
  own outputs (the documents and meshes its decorators declare, and the
  sidecar beside its STEP), when it is code (Python source is the reach above; a compiled
  library is the environment's), or when it lies in the environment: the
  interpreter and its packages, cadgen, the store, and the folders the
  operating system owns (fonts, time zones). Three kinds of entry are not files: `<folder>/`, a folder
  the model's code listed (a glob of profiles), hashed by its sorted entry
  names, less the ones cadgen keeps only while it writes beside an output
  (a temp file, a STEP stage folder; `is_transient_name` in
  `cadgen._internal.atomic_replace`), so a sibling's build in that folder
  does not stale it; `!<path>`, a file that
  must stay absent — one the imports were resolved past (a package beside a
  module, an `__init__.py` a namespace package lacks, a module an earlier
  search root lacks) and would resolve to if it appeared — hashed `absent`;
  and `<import roots N>`, the digest of the first N search roots when an
  import was found past the script's own folder (a root added before those
  could shadow it). The clips declared by `@step(animation=...)` are code,
  in the closure like the rest of the model's reach; the build bakes them to
  keyframes in the unified sidecar, and they never enter geometry identity. The
  boundary is decided statically by what the importer TAKES from a model
  file: only model functions (`from arm import arm`) → a result edge, file
  excluded, the child tracked by its pin (also when that file declares several
  models); a module-level literal (`from plate
  import WIDTH` where `WIDTH = 40.0` — numbers, str, bool, None, tuples/
  lists/dicts of those) → a value edge, file excluded, the value tracked in
  `constants`; anything else (a helper function, a `bd.` object, an
  expression) → a source edge, file included. **Constants by value,
  functions by reach, models by result.** Hit and miss runs record identical
  closures by construction. `closure.static: true` marks a record whose
  inputs are not files (a document re-emitted by `cadgen step build`); the
  gate's clause 2 does not re-hash files for it.
- **A listing leaves out the model's own outputs** (`closure.own`): each one
  written in the listed folder, and each folder there one was written into,
  recorded per listing, so every re-hash -- gate clause 2, `cadgen store why`,
  the publish rule, the annotation refresh -- leaves out the same names. They
  are never its inputs, as a file it reads back is not: the listing is taken
  when the body returns, before a first build publishes them, and a rebuild
  lists the previous run's. So a model that lists its own folder is current
  after its first build. A sibling model's outputs stay in, since a body may
  list the folder to find them: a model that lists a folder its siblings build
  into reads stale once after their outputs first appear there.
- **Functions by reach** (`cadgen.store.reach`, the walk in
  `cadgen.store.closure`): a non-model file in the closure is hashed by the
  part of it the model can execute, not by its whole text, so editing a helper
  the model never reaches leaves it current. The record keeps the reached
  names per sliced file in `closure.names` and the file's whole-file hash, of
  the same bytes, in `closure.wholes`; a file absent from `names` (the script
  itself, a model file taken as source, a data file the build read, a file
  the fallbacks below made whole) is hashed whole as before. What a slice is, by
  construction:
  - A statement is an optional **definition** only inside a closed grammar:
    an undecorated function with no type parameters and with defaults and
    annotations consisting of closed literals; or a single-name
    assignment of closed literals. Closed literals contain only constants,
    literal containers without unpacking, and signed numeric constants. A
    repeated binding is never optional: replacing an object can run its
    finalizer. Function defaults/annotations referring to an object can also
    change its lifetime, so bare names there are not optional — unless
    annotations are never evaluated at definition time (`from __future__
    import annotations`, Python 3.14+): then annotations do not count, and a
    single-name annotated assignment of a closed literal is a definition too.
    Everything else is **preamble**, always hashed with its reads reached.
    This includes every class, decorator, call, evaluated annotation,
    augmented assignment, alias assignment, unpacking, property/subscript read,
    operator and formatted string. Neither a familiar module name nor the
    absence of a call node proves purity: Python protocols can execute user
    code implicitly. Unknown syntax defaults to preamble. This deliberately
    trades some cache hits for correct invalidation, while ordinary unused
    helper bodies and literal constants remain sliced by reach.
    An unshadowed `if __name__ == "__main__":` block never runs on import: it
    is in no slice, binds and rebinds nothing, and nothing in it makes its
    file dynamic (the script itself is always hashed whole, block included).
  - A **function edge** brings in that function's own source plus everything
    it can reach: every name its body, decorators, defaults and annotations
    load (also inside nested functions, lambdas and comprehensions, and names
    it declares `global`), each resolved to the definitions binding it in the
    same module — transitively — or, through an import binding, to a name in
    another project module, where the same rule continues. A name a
    function writes through `global` is bound by that function. A class edge
    brings in the whole class. A module-scope import executes its module's
    preamble, and every package on the way (`import a.b.c` executes `a`,
    `a.b` and `a.b.c`); a from-import of a name reaches that name whether or
    not it is used. Attribute chains on a module alias (`geo.plane`,
    `lib.geo.plane`) walk submodules and end on a name; a submodule name that
    the package's `__init__.py` also binds reaches that binding too (it wins
    at run time unless the submodule was imported first).
  - **Every file the build executed is a root.** The walk starts at the
    script and then, walked whole from the bytes that ran, at every
    first-party file the build executed that static reach never saw and no
    child owns — a plugin imported for its side effect, a module found through
    a `sys.path` insert — so what IT calls in a sliced file is in that slice.
  - **What importing a child runs is this model's input.** A child's model
    BODY never runs in this process — it runs in the child's own build, or not
    at all — so it is tracked by the pin (models by result). But importing the
    child runs its module body, the module bodies of the helpers it imports,
    and its model definitions' **headers** (decorators, defaults, annotations)
    here, and any of them can change what this body computes (a registry
    filled, a shared table patched). Each such file is in the closure by what
    its import runs: a child model file as an `islice1:` import slice (its
    preamble, each model definition counted by its header, never its body; a
    cadgen model decorator's literal arguments read as one placeholder, since
    evaluating a literal runs nothing), a helper only children import as a
    slice of what import-time code reaches, and whole when that is dynamic or
    the closure reflective. An import-time walk follows what import-time code
    reads; binding a name by `from x import y` runs none of `y`. What that
    code reaches in a file this closure shares is reached too.
  - **A pin is only a call.** A model function taken from a model file is a
    result edge only while the importer calls it: an attribute of it
    (`arm.__wrapped__`, `arm.__cadgen_model__`) can reach its body, so the file
    is taken as source; and a model's wrapper carries no `__wrapped__`. A
    `@dxf` function is not a pin at all: called inside another build it runs
    its body inline, so taking one is taking source.
  - **Anything dynamic falls back to whole files.** Per module, and the walk
    then descends into all of it: a star import (importer and target whole);
    `globals()`, `locals()` or a bare `vars()` (the module, and every module
    it imports: its module objects expose every name of theirs); a
    module-level `__getattr__`/`__dir__`; a module-scope read of a name nothing
    binds and no builtin answers; a name reached in a module that has no
    binding for it. A module alias used bare — `getattr(geo, name)`,
    `vars(geo)`, `geo.__dict__`, `geo` passed along — makes the target whole,
    and every module bound in it; a package alias used bare makes every file
    of that package whole; an attribute write or delete on a module alias
    (`geo.X = 1`, a monkeypatch) makes the target and the writer whole. Per
    closure: when any walked file can reach an arbitrary module's namespace
    by string or introspection — `exec`, `eval`, `compile`, `__import__`,
    `__builtins__`; any binding from `importlib`, `builtins`, `runpy`,
    `pkgutil`, `inspect`, `pydoc`, `gc`, `ctypes`, `pickle` and its kin, or
    another module that resolves names from strings; `sys.modules` or a frame
    through any alias of `sys` or `from sys import`; `__globals__`,
    `f_globals`/`f_locals`/`f_back` or any other frame attribute — every
    file of the closure is hashed whole and `names` is empty. The reach
    through model files is unchanged: a result or value edge stops there; a
    source edge into a model file takes it whole.
  - **Module-level side effects keep file-level tracking**: they are
    preamble, always hashed, their reads always reached — a constant table
    built by a call, a registry filled at import, a conditional definition.
  - **Static and deterministic.** The walk reads the bytes the exec hook
    captured when each module ran (§5, hash at execution) and resolves
    imports against the script's `sys.path` (its folder, then `PYTHONPATH`);
    its only run-time input is which first-party files executed, and those
    are in the closure either way. The gate never re-derives cross-module
    reach: a sliced file whose whole-file hash is still its `closure.wholes`
    keeps its recorded slice without being analysed, and one that moved is
    re-sliced on disk by its recorded names
    (`cadgen.store.closure.sliced_source_hash`: the names closed within the
    module, each marked bound or unbound, then the preamble and the reached
    definitions in source order, a digest of `ast.dump` per statement, so
    comments and formatting do not count). Any edit that would change what
    the walk reaches — a reached body calling something new, a new binding
    shadowing a name, an import added or changed — also changes a hashed
    statement or marker. A sliced file that turns dynamic hashes whole
    (`ast1:` against a recorded `slice4:`) and reads stale. `cadgen store
    why` prints a sliced file as `lib/geo.py[plane, cyl_along, …]`.
  - **Lexical scopes decide what must be bound.** The analysis resolves every
    load with Python's scoping rules, in one pass per module: parameters and
    assignments belong to their function, a comprehension's targets to the
    comprehension, defaults, decorators, bases and a comprehension's first
    iterable to the enclosing scope, and a class body is invisible to every
    scope nested in it (a class-body comprehension reads the module's name).
    That resolution decides which names must be bound at module scope (the
    unresolved-name fallback). As edges, every name a statement loads is
    followed whatever scope binds it, so reach never rests on scoping alone;
    the only cost is reaching a definition whose name a local shares. Import
    aliases retain all candidate bindings across those scopes, so two nested
    imports named `dims` cannot hide one another. A submodule name taken
    through its package (`from lib import geo`) is part of the package
    `__init__.py`'s slice even while the `__init__.py` does not bind it,
    marked unbound, because a binding added there later wins over the
    submodule. Which files declare models is read from their bytes, never
    cached by path, so a warm process sees a decorator added or removed.
    A sliced file's hash starts `slice4:`, a whole file's `ast1:`.
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
  metadata refresh: same-module literal `kinematics=` or `materials=` values
  (including literal constants used exclusively there) can be reapplied to a
  complete cached baseline without executing the model or rewriting STEP. The
  recorded geometry closure is derived from the exact source buffer that
  executed. Computed and imported annotations stay in that geometry
  fingerprint; an unchanged one can coexist with a literal edit by reusing its
  recorded value. Changing its expression or dependency, reflection, constants
  used anywhere else, child-pin changes, incomplete trees, and changed output
  bytes fall back to the ordinary build. `animation=` clips are always computed:
  a refresh writes the record's baked keyframes back unchanged, and an edited
  clip is an ordinary build.
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
   (comments and formatting do not count), computed at execution time (§5) —
   over the whole file for the script and every file `closure.names` does not
   list, over the reached slice for a file it does (§3, functions by reach):
   editing a helper the model never reaches leaves it current; editing one it
   reaches, directly or through other helpers, or a module-level name a
   reached helper reads, makes it stale. A sliced file still at its recorded
   whole-file hash (`closure.wholes`) keeps its recorded slice unanalysed, so
   an unchanged project costs the gate the whole-file hashes and nothing more.
   A literal imported from a model file is compared as a value: a comment,
   a body edit or a new helper in that file leaves the importer current; a
   changed value (or the name no longer bound to a literal) makes it stale.
   A listed folder is re-hashed less the model's own outputs its
   `closure.own` records (§3).
3. **Any recorded child is stale, or its current tree hash differs from the
   pinned hash.** Protects against a child whose RESULT changed — and lets a
   child edit that yields identical geometry leave the parent current.
   Recursion is memoized per request.
4. **The tree object, or any component it (transitively) references, is
   missing.** Protects against a collected or half-copied store.
5. **A declared output does not match `outputs`.** Protects against a deleted,
   hand-edited or foreign `.step`/sidecar/mesh file beside the model.

Clauses 4 and 5 verify each object and each output once per process. One
build evaluates the gate many times over the same closures, and a large
assembly's STEP is hundreds of megabytes. A later evaluation stats each file and
reuses the verdict while the file keeps the identity (device, inode, size, mtime,
ctime) observed around its verified read, under §10's settled-stamp rule.
Deleting, replacing, truncating or rewriting a file verifies that file again,
and for an object every tree above it in the closure, each read again to walk
its links: a component still at its verified identity is taken on that
identity, and a linked tree whose whole closure holds is taken as verified, so
a child another process rebuilt costs the parent's next evaluation that
child's closure and every tree above it, the parent's own among them, and
clause 4 reads nothing clause 3
just verified (§10). A build's own checks of its saved document and sidecar — before the body
runs, before it publishes, after its rename — read through the same memo, and
a document the build renames into place is remembered by the digest its writer
took: a rename keeps the written file's device, inode, size and mtime, so a
path that still shows that identity, settled before the rename, holds those
bytes. Its checks of its result — after it publishes the tree, when it
announces it, when it claims its record's closure, in the already-stale notice
— take the verification the job already holds; the claims keep it (§8). A
publish reads nothing of a closure its job verified.

A job asks the gate once before its body. That verdict answers the no-op check,
the check for a peer that published meanwhile, the annotation refresh and the
reuse check; it is taken again only after the job waited for a slot, or after
another model of the same run was built, either of which can change it. The
already-stale notice after publishing asks anew (§9a).

Mesh tolerances and argv flags are not inputs. A model run's
`--mesh-tolerance` / `--mesh-angular-tolerance` override every declared mesh's
tolerance for that run (flag > declaration > `@step` > default): each mesh's
ledger entry records the pair the file was written at, so the declared meshes
are re-cut from the current tree — the model is never rebuilt for it — and the
next run without the flags restores them, once. Imported STEPs are inputs (a
file the body reads is in the closure), not models. `--force` rebuilds the named
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
  which would make a stale result read as current forever. A first-party
  module is compiled from the bytes on disk, never from a `__pycache__` `.pyc`
  (CPython accepts one by whole-second mtime and size, so two same-length edits
  inside a second would run stale bytecode), and its loader records exactly
  those bytes; a build writes no bytecode for anything it imports.
  A data file is hashed after the body returns, and only while it still has
  the size and mtime it was opened with (the trace takes both at the open):
  one that changed or vanished since is recorded `changed while building`,
  which matches no file, so the next gate rebuilds.
- **Every read is seen.** A build runs inside a capture
  (`cadgen._internal.filetrace`). The tracer, one small native library per
  platform in `_runtime/native`, rewires every library loaded in the build's
  process -- and each one loaded later -- so its calls to the C library's
  file opens (kernel32's on Windows) pass through a wrapper that logs the
  file, its size and its mtime while the capture is open. Every reader ends
  there: Python's `open`, numpy, build123d's importers, OCCT, FreeType.
  Folders come from Python's `os.listdir` / `os.scandir` audit events, by
  frame: the import system's listings and cadgen's own are not the model's,
  and a listing leaves out the model's own outputs (§3).
  The gate's own reading inside a build (a child's files and outputs, hashed
  to decide whether it is current) is paused on its thread: a child is an
  input by its result. Prevents: a model whose data changed reading as
  current because nobody declared the file. Not seen: a data file the model
  looked for and did not find (one that appears later is no change); a `.py`
  file read as text and `exec`'d rather than imported (source counts by reach,
  and reach follows imports); what a separate program the model runs reads; calls made inside the operating
  system's own libraries (the macOS shared cache); a file a third-party
  library caches for the life of a warm worker, after the first build that
  reads it.
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
  the geometry. A spliced STEP (§3) is canonical by construction: its children
  are, it numbers NAUO instances 1..N, adds no styles and prints no `-0.`.
  Prevents: one model writing two documents, so the packages and index
  entries keyed by the other spelling's bytes are orphaned.
- **Names read back.** OCCT's STEP reader ends a string at an escaped quote
  (`''`) followed by spaces and `,` or `)`. A part named `post (6')` or
  `x('',y)` then lost its product or came back renamed, in every OCCT-based
  reader, and failed the build's read-back. The writer spells every quote in
  such a literal as Part 21's `\X\27` instead, which readers decode to the
  same name (`step_export.respell_misread_quotes`, which the splice applies
  to the names it writes). OCCT also writes a non-ASCII name as its UTF-8 read
  as Latin-1 and encoded again, trimming any byte its C library takes for a
  space from either end, so `Bügel_ä` came back `BÃ¼gel_Ã¤` and `à` lost a
  byte, and both failed every build. A non-ASCII name therefore reaches OCCT in
  ASCII, each run of non-ASCII characters as a Part 21 `\X2\` (basic plane)
  or `\X4\` directive (`step_export.ascii_name`); the name pass restores the
  single backslashes OCCT doubles, the splice spells names the same way
  (`step_export.spell_name`), and every reader decodes the directives to the
  same name. A written document is ASCII. Every other literal keeps OCCT's
  spelling, and a file without such a name is never read again
  (`STEP_WRITER_SCHEME` 3). Where a STEP gave a product or a usage no name,
  OCCT writes its label's address instead (`0:1:1:2`, `=>[0:1:1:2]`; a
  single-part document's root is one): that, a blank, the translator's
  default, a shape kind and digits alone read as no name
  (`step_scene_loader._normalize_label_name`). An occurrence with no name of
  its own shows its product's, unless that is another occurrence's own label
  -- a writer names a product its occurrences share after one of them, cadgen's
  after the last (`step_scene_loader._withhold_borrowed_product_names`) -- and
  otherwise the document tree names it by its id. Readers show the tree's
  names as given (`DOCUMENT_SCHEMA_VERSION` 6: a document entry from before
  these rules is at another key, never read here, and its bytes compile again).
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
  (file in the closure). A non-model file is in the closure by the names the
  model reaches in it from the script and from every file the build
  executed (§3, functions by reach), whole when anything dynamic is in the
  way; a file that ran here because a child was imported, by what its import
  runs; a file the imports rely on not existing, as `!<path>`. Constants by
  value, functions by reach, models by result. Prevents both false-current (a
  constant imported from a model file changing unnoticed; a helper edit hidden
  behind a `getattr` on its module; a child's module body patching what this
  body reads; a new `__init__.py` or module changing what an import finds) and
  false-stale (a child's internal edit, a comment beside a shared constant, or
  a helper no reached code calls — rebuilding every parent).
  One process-wide memo of immutable module-syntax recipes keyed by exact
  source bytes, bounded by 32 MiB of accounted inputs/recipes and 2048
  entries, serves the exec hook, every closure walk and every gate: each file
  revision is analysed once per process. Every lookup still reads the file and
  resolves current import availability, model classification and constant
  values; the recipes contain no resolved dependency graph or freshness
  verdict.
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
- **A hit is a read.** No reader writes the store: a mesh probe, a surface
  lookup, a bounds hit, a document lookup, the gate, a materialized pin --
  none refreshes a stamp or an mtime, so "recently used" for eviction means
  recently written (§8). Prevents: a store this user cannot write failing
  every build that only hits it, which the last-use stamps an earlier
  eviction wrote on each hit did.
- **A write claims what it reuses.** Bytes a write finds already present are
  claimed (their mtime becomes now, less two ticks of the clock that stamps
  them, §8) instead of skipped, and a publish claims its record's whole
  closure before it writes the record; the sweeper deletes only by rename,
  then recheck (§8). Prevents: a sweep that began before a publish deleting an
  object the new record reuses, out of a grace window that never saw the
  reuse.
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
- Tight occurrence bounds live in `index/bounds`, keyed by each leaf's BinTools
  digest and its transform with the translation removed. Translation shifts
  those six bounds directly, so translated instances share the expensive
  surface calculation. Rotation still requires its own tight box;
  control-polygon bounds are not substituted. Measured, memory-hit and disk-hit
  boxes come from the same origin-normalized function, and cached numeric
  arrays are never mutated.
- Canonical saved-document publication already owns each verified component's
  encoded BREP and each parsed occurrence's exact native placement. Its tight
  bounds key uses that BREP identity, codec and rotation in `index/bounds`,
  then shifts the six native bounds by translation. A miss measures
  every native leaf with the same optimal extrema operation; it never transforms
  a component AABB. Incomplete private inputs fall back to the ordinary composed
  native document, after the same component validation and closure checks.
- A bounded descriptor composed entirely of pinned links may instead measure
  exact component bounds from verified canonical BREP objects. `index/bounds`
  stores only six finite numbers, keyed by BREP digest, all 16
  placement doubles without rounding, the bounds algorithm and the kernel's
  versions. It uses the same private reconstruction, placement,
  native leaf traversal and final numeric extrema merge as the whole document;
  rotated local AABBs and raw native-box merges are not substitutes. Missing,
  corrupt, unsupported or invalid inputs use the ordinary whole-document path;
  forced builds bypass this reuse.
- An all-link result past that bound takes its bounds from its links. The
  whole document's bounds are its links' leaf boxes merged, and one link's
  merge is a function of the child tree it links and its exact placement
  alone, so it is remembered in `index/bounds` under those two, the algorithm
  and the kernel's versions (`store.build._bbox_from_links`). Links merge in
  the order the document's leaf traversal visits them, keeping the first of
  equal values as it does, so the six numbers, signed zeros included, are the
  whole document's. A link that misses measures its own part of the document;
  any failure measures the whole document; forced builds bypass this.
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
  it is not a native allocator RSS guarantee. No native shape enters a
  cache. A failed optional preparation releases its private owners before
  falling back. Larger, new-own-component and unsupported results keep the
  ordinary preparation/publication order. STEP correspondence checks and the
  separate canonical readback of newly emitted saved bytes are unchanged.

A tree's bounds (`_bbox_from_shape`) walk the native leaves of one composed
document with no Python callback between leaves, so within that call a
prototype's content digest is computed once per TShape encountered and
discarded when the call returns — never retained, never a substitute for the
next call's read. Vertex hashes (`determinism.py`) read their current native
point, including native point or location edits that leave Python coordinate
attributes unchanged.

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
- **A sweep beside a build.** A pass never coordinates with builds: a write
  claims what it reuses, a publish claims its record's closure, and the
  sweeper deletes by rename, then recheck (§5, §8), so no record is written
  naming an object a concurrent pass took. The daemon runs its own passes
  only while it has no request in flight.
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
  phase n/total, the job's declared output paths — for a script that no longer
  imports, what it declared the last time this daemon could read it) and
  serves it with `daemon status`; the CAD Viewer matches jobs to the
  documents it shows by output path — a CLI build, a parent's child build and
  its own compile read alike — and nothing reads any of it to decide freshness. With `CADGEN_DAEMON=0`
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
can leave a missing or mismatched annotation: the sidecar binds annotations to the
STEP's SHA-256, so readers reject that annotation instead of applying old
mates or finishes to new geometry. Material-only saves can retain the same
STEP digest, so refresh and output-pair conflict checks also observe sidecar
content. A stale/missing record does not block saved-byte reads;
missing derived objects are compiled from the bytes that actually exist.
Explicit regeneration repairs the annotation pair. No reader consults locks
or source to recover an artifact.

## 8. GC, eviction and the cap

One sweeper, `cadgen.store.gc`: by hand as `cadgen store gc [--dry-run]
[--grace-hours H] [--max-size [SIZE]]`, and by the daemon when idle (below). A
pass scans the store once (names, sizes, mtimes), marks once, and removes three
kinds of thing:

1. **Retired kinds and obsolete entries.** The folders in `RETIRED_KINDS`
   (`index/op`, §2) go, and so do the obsolete surface, selector-table and
   mesh entries a week old (§2), with every object only those entries named; a younger
   obsolete entry stays, objects and all, like a current one. An entry naming
   an object the grace window still keeps waits for the next pass, so that
   object goes with its entry rather than with the next full sweep, and an
   entry written again since the scan stays. The records and document entries
   at keys this cadgen does not own go on the same rule -- a week after their
   last write, and not if written again since the scan; their trees' objects
   are left to the sweep (3), which takes what nothing else reaches.
2. **Evicted entries**, only under a cap: the derived kinds -- `mesh`,
   `surface`, `selector`, `component`, `bounds`, `drawing`, `skin`, `section`,
   `robot` -- least recently written first, until the store fits 80% of the cap. Sizes
   are deduplicated: an
   object goes only when nothing that stays still needs it, so evicting a
   component entry whose BREP a current tree places frees only the entry.
   When what no pass may remove leaves less room than the fifth of the cap
   above that 80%, the most recently written derived entries keep that fifth:
   a cap the records and documents outgrew never empties every derived cache.
   **Records, document entries and output entries are never evicted.**
3. **Unreachable objects.** Kept: every object in the closure, through links,
   of a current-schema record's `tree` or `documentTree` or a current-schema
   document entry's tree, and of those trees of a record or document entry at
   a key this cadgen does not own while it is younger than a week, as far as
   this cadgen reads their format (the *protected* set); every object a surviving
   derived entry names; anything written or claimed within the grace window
   (default 1 h). Everything else goes, and so do temp files a crashed writer
   or an interrupted pass left, once past the grace window. A saved document
   retains its geometry even after model/output records are forgotten; its
   mesh ledger records hashes of external output files, which root nothing.

**Recently used means recently written.** A hit is a read (§5). An entry's age
is when a build or a derivation last wrote it -- a publish rewrites every
component entry its tree has; a derivation writes the surface, selector, mesh,
bounds, drawing, skin, section or robot entry it computed -- and an object's is when a
publish last wrote or claimed it. A display cache that is only ever read ages, goes when the cap needs
the room, and costs one recomputation when it is next shown. Evicting never
changes an answer: every reader treats a missing entry or object as a miss.

**Deletion is rename, then recheck** (`objects.delete_unclaimed`). A write that
finds its bytes already present claims them (`objects.put_object`,
`objects.claim_object`), and a publish claims its record's whole closure --
its own components, and a child's tree it pinned long before -- right before it
writes the record (`trees.claim_tree`). The sweeper renames an object it means
to delete, then reads the mtime again from the renamed file: a claim made
before the rename shows there, and the object goes back; a claim made after it
finds the object gone and writes the bytes again, or fails the publish when it
holds none -- never writing a record that names a missing object. So a pass may
run beside builds without a lock. The grace window is the whole protection for
a pin a build holds before its publish, so do not sweep with `--grace-hours 0`,
or a window of a few seconds, while anything is building.

**A claim stamps the recent past, and keeps what was verified.** A claim sets
the object's mtime to now less two ticks of the clock its previous stamp shows
(`objects._claim`: 62.5 ms where stamps carry nanoseconds, 2 s on a
whole-second clock, 4 s on FAT) -- within any grace window a sweep may use,
and settled as it is set, since a later write must land in a newer tick. The
publishing process verified most of what it claims moments before (§4), and a
claim is the one write it makes to an object it has verified, so a claim
carries the verified identity (§10) forward instead of losing it: the stamp
before the claim must be the verified one (nothing wrote the file since the
read) and the stamp after it the claim's own, on the same device, inode and
size; otherwise the identity is forgotten and the next reader hashes the
bytes. What a foreign writer could do to the file in the microseconds between
that stat and the claim's own timestamp write is beyond any stamp; cadgen's
own writers never rewrite an object in place (temp + rename, §11), and a
reader that uses an object's bytes hashes them. A publish therefore claims on
identity what its job verified, reading nothing, and holds the bytes only of
what its own capture had to read -- which is what a claim that finds its object
gone writes back. In a store several users share, POSIX lets only an object's
owner set an explicit time, so a claim on another user's object stamps it now,
which needs only write access: the object is claimed all the same, and its
identity is forgotten, since a stamp of now is not settled as it is set.

**A store two cadgens share.** Every cadgen on a machine uses the same store
by default, and a pass can only judge what it can read. A newer cadgen's
records, document entries or trees may be in formats an older one rejects
(each carries a `schemaVersion`, and a format change bumps it, §2), so the
older one cannot tell which objects they still need -- and objects are shared
by content across versions. So a pass that finds a record, document entry or
tree in a newer format than its own, or a folder under `index/` it does not
know, written within the last 30 days (`NEWER_CADGEN_SECONDS`), removes
nothing at all and reports why (`deferred`); the newer cadgen collects the
store. Thirty days after the newer cadgen's last write, it is taken to be
gone, and passes resume: its records and trees are then a format nothing here
reads, like any older cadgen's, and its records and document entries, at keys
this cadgen does not own, are retired. The other way round needs only a week: a newer
cadgen treats an older format as garbage, which is how an upgrade frees the
space the old one used, and an older cadgen still in use rebuilds what it
needs -- an obsolete surface, selector-table or mesh entry, a record or a
document entry, at most once a week (§2). Until then each version keeps its
own record and document entry at its own key, so neither recompiles a
document or rebuilds a model because the other one did. A pass
never touches anything outside its own folders: object shards
named by two hex digits, and the `index/` folders in `INDEX_KINDS` and
`RETIRED_KINDS`. This is why a new field that names objects, in a record, a
document entry or a tree, is a format change and bumps that `schemaVersion`:
an older sweeper cannot see it, and must know to stand down.

The mark reads JSON only: records, document entries, derived entries and each
tree they reach, once each, verified against its address. A leaf object counts
by being there; whoever reads its bytes verifies them and repairs or recompiles
a damaged one, so the sweep never reads a BREP or SURF body.

**The cap** is `CADGEN_STORE_MAX` (`20G`, `500M`, `1.5GiB`, `0` for none;
default 20 GiB) over the apparent bytes of `objects/` and `index/`. `cadgen
store info` shows the size against it.

**The daemon's housekeeping.** When a request against a store finishes and no
request has been in flight for 30 s, the daemon looks at that store once, under
the cap the requesting client had in force (`CADGEN_STORE_MAX` is forwarded
with every request):

- larger than `max(cap, after + cap/5)` -- `after` being where its last pass
  under that cap ended -- gets a full pass with the cap;
- otherwise, a store holding a retired kind, or holding surfaces, selector tables, meshes,
  records or document entries that
  no retiring pass under this cadgen's versions (`gc.producer_versions`: the
  extractor's and the mesher's) has looked at for a day, gets a retiring pass,
  which retires the retired entries and the week-old obsolete ones -- the
  records and document entries at keys this cadgen does not own among them --
  and sweeps only the objects the retired and obsolete derived entries named. Obsolete entries cannot be told from a stat
  walk, so when that pass ran is noted per store and per versions, in a note of
  its own beside `after`'s: a daemon of another release sharing the store keeps
  its own and never moves this one. So a store gets one such pass after an
  upgrade, then at most one a day however often the daemon idles or restarts,
  and an obsolete entry a pass kept for being younger than a week goes within
  a day of turning a week old (`housekeeping.RETIRE_INTERVAL_SECONDS`).

`after` is noted beside the daemon's socket, per store, in its state
directory, so a store whose records and documents alone hold more than the
cap costs one pass per fifth of the cap it grows -- never one per idle moment,
nor one per daemon start; losing the note costs one pass. The look itself is
a stat walk that keeps nothing per file. A pass runs as `python -m
cadgen.store.gc`, a process of its own, so the record it keeps per object and
entry leaves with it rather than staying in the daemon; the daemon closes its
stdin the moment a request arrives or it winds down, and the pass stops at its
next step. Every step leaves a consistent store, so stopping anywhere is safe
and the next idle look picks it up; even a pass killed between a rename and
its recheck leaves the object under a `.swept` name, which the next pass puts
back if it was claimed and deletes if not. With `CADGEN_DAEMON=0` nothing runs
automatically; `cadgen store gc --max-size` runs a pass by hand.

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
  A worker starts in the system temp folder but keeps it off its import path
  (`python -P`, as every process cadgen starts does: the daemon, the store's
  gc, a transient build, the Viewer), so a build imports exactly what
  `python script.py` would (law 7), nothing another program or user left in
  that folder stands in for cadgen, and no import lists it. Other programs fill it and keep
  changing it; on the path, it was listed again by every import that missed it
  once it had changed, tens of thousands of entries a time, by every worker of
  a burst at once.
  Spares: `CADGEN_DAEMON_SPARES` (default 2). Requests that name no
  model (a document compile or artifact derivation) borrow a spare without binding
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
  exits after `CADGEN_DAEMON_IDLE_TIMEOUT` seconds idle (default 3600). The
  first client that needs the daemon starts it, and `cadgen viewer` starts it as
  soon as its URL is announced, so a session's first build finds warm spares.
  Inside a worker, `submit` is the same client call back to the daemon, so a
  parent's children land on their own workers while the parent's body runs.
- **Transient executor (`CADGEN_DAEMON=0`).** A subprocess per job, alive for
  this build only. Each imports build123d once, concurrently with its
  siblings. It inherits the environment, so a test's `CADGEN_CACHE_DIR`
  isolates its store; tests and CI run this way.

**Scratch outlives a killed process.** A process keeps its served views
(`cadgen-views/<pid>/`), an exported view (`cadgen-view-<pid>-*`), a build's
file-trace log (`cadgen-trace-<pid>-*.log`) and the private copy of a STEP
document it parses (`cadgen-step-import-<pid>-*`) in the system temp folder and
removes them as it ends; a killed one cannot, a view copies every component
it shows and an import copy the whole document. A job whose caller left ends
by its worker being killed, so this is routine. A worker sweeps them as it starts, on a thread of its own,
and the daemon sweeps again once it has reaped a worker that died or was killed
(no starting worker sees one that dies after it started): the
scratch of every pid no process holds, and scratch an older cadgen named
without a pid once it is a day old. A live process's is never touched, a pid it
cannot judge counts as live, and nothing in the store is involved
(`_internal/temp_leftovers.py`). A folder is renamed `cadgen-swept-<pid>-…`
before it is deleted, so a sweep killed midway leaves it condemned rather than
half there with a fresh mtime, and the next sweep finishes it once that
sweeper is gone. A build saves its STEP in a staging folder beside the output
(`.cadgen-stage-<pid>-<host>-<stem>-*/`) and publishes it from there; before it
stages, a build removes from that folder the staging folders of this machine's
builds that are gone (and an older cadgen's unnamed ones once a day old). A
live build's stays, and so does another machine's: an output's folder can be
shared, and a pid says nothing about another machine.

**Silence means hung, not busy.** While a job runs, its worker emits a
heartbeat frame every 10 s (carrying the job's last announced phase and its
CPU clock). The supervisor consumes heartbeats; they are never relayed to the
client, never enter the job ledger and never count as progress. A worker that
sends no frame for 120 s is killed as hung, unless its CPU clock, read from
outside the process, advanced meanwhile: a native call that holds the GIL (a
long OCCT boolean) starves the heartbeat thread but is computing. A stopped
process, or a deadlock that holds the GIL, sends nothing and accrues no CPU. A
hang that releases the GIL (a network read with no timeout, a Python-level
deadlock) keeps beating and is not killed. A body's length is therefore
unbounded; the heartbeat stops before the job's exit frame, so none
reaches the next job. A starting worker is judged the same way: it is silent
until it has imported the kernel, a few CPU seconds that a busy machine, or a
burst of starts, spreads over minutes, so it is waited for while its CPU clock
moves and killed only after 120 s with neither its announcement nor CPU
progress. Meanwhile the job it is for is listed `queued`, detail `Starting a
geometry kernel`: nothing the job runs can say so before its worker exists.
Frames leave a worker on a descriptor of their own, never fd 1 itself: a job may
point fd 1 at stderr for a while (a STEP read sends the kernel's diagnostics
there), and a beat written then went to the daemon's log, so a long read was
killed as hung. A beat no one reads ends the worker at once: its supervisor is
gone, and its client is already running the job again in its own process, as
it says (`lost the build service … Running it cold now`). A job whose caller
left is cancelled, not a crash, in the job ledger and in `cadgen daemon
status` alike, though its worker is killed.

**One daemon per address, by lock.** The daemon takes an exclusive lock keyed
by its socket address (`cadgen.daemon.transport.SingletonLock`: `flock` on
POSIX, `msvcrt.locking` on Windows, released by the kernel when the holder
dies) before it binds, and holds it while it serves that address — a private
socket is a private daemon. A daemon that stops serving removes its address and
then releases the lock, before any teardown. A second daemon starting for the
same address waits up to five seconds for the lock — its predecessor may be
between those two steps, or, when an upgrade replaces an earlier version, still
shutting its pool down with the lock held — and otherwise stands down, touching
nothing; the winner is by construction alone, so a socket file it finds is dead
and may be removed. Clients elect one spawner the same way and the rest wait
for the address. The lock holder creates that address's authkey once via a
linked temp file and republishes its in-memory key if an external cleanup
replaces the file. This is the one lock cadgen keeps — a singleton for
the daemon, never a build lock (§7): twenty clients starting at once used to
start twenty daemons that unlinked each other's live sockets.

**The address always binds.** On POSIX the address is a socket in the
daemon's state directory (`CADGEN_DAEMON_STATE_DIR`, else `cadgen-daemon/` in
the system temp folder), which holds its key, its locks and its log. A Unix
socket path has a ceiling (104 bytes on macOS), so when the state directory is
too deep for it the socket alone goes in `/tmp/cadgen-<uid>/`, named by a hash
of the path it would have had: every client of that state directory finds the
same one, whatever its own `TMPDIR`. Anyone can predict that folder's name in a
`/tmp` every user shares, so the daemon makes it mode 0700 and uses it only
while it is a folder of this user's own; one another user made first is never
used, and every door says so and names the remedy (a shorter
`CADGEN_DAEMON_STATE_DIR`). The key stays in the state directory, so a socket
planted in the short folder could not answer the handshake either. On Windows
the address is a pipe name, which has no path to outgrow.

**A client that never answers holds up no one.** Each connection proves the
authkey, and the daemon proves it back, on a thread of its own
(`cadgen.daemon.transport.Server`). Accepting waits a tenth of a second for that
before it takes the next connection; one that finishes later is handed over
then, and one that has not finished in ten seconds is dropped — its client
reads a daemon closing while it connects, and connects again. While one is
pending past its tenth of a second, accepting waits for no new connection, so a
burst of silent ones delays no one. A daemon (or a build's private broker) that
stops drops the connections still proving the key, and waits for their threads
before it exits. The handshake used to run on the accept thread with no
deadline, so one connection whose challenge never reached its reader (another
viewer thread had read it off a reused file descriptor) held every later request
until the viewer exited.

The **store root is a field on every request** (`store_root`), applied per
job in the worker, never inherited from whichever build spawned the daemon:
one daemon serves any number of isolated stores. The daemon holds no store
state of its own beyond where each store's last housekeeping pass ended
(§8). `cadgen daemon status` reports each worker's `model`,
`busy`, `jobs`, `extra`, plus `spares`, `imports` (cold spawns),
`concurrent` (extras bound) and `jobs running n/N, queued m, coalesced k`;
`--json` adds the **job ledger** (`cadgen.daemon.jobs`): every job the
daemon ran in the last 120 s with its state (`submitted` → `queued` →
`building` [phase, done/total] → `done` | `failed`) and the output paths it
declared, parsed statically from the script it names. The ledger is the CAD
Viewer's only progress source, and it is process state, never a file.

The CLI doors (`cadgen step build|compile`, `stl|3mf|glb build`)
are themselves dispatched through the daemon when one is reachable, so they
run on warm kernels; the subject-less commands (`store`, `doctor`, `daemon
status`, all snapshot orchestration) run in-process. STEP snapshots delegate
missing document compilation and surface derivation to the artifact build pool;
their request resolution and browser orchestration never import the CAD kernel.

When the daemon's runtime changes, a request carrying the new version is told
to restart. With nothing running, the old daemon releases its address and lock
before it answers, so the client's respawn binds at once. During a build, it
keeps its listener and singleton lock until active jobs and their dependencies
finish. New top-level requests run cold during that drain — artifact requests,
which have no cold path, keep asking until the successor binds; dependency
requests remain serviceable so a parent cannot deadlock while saving its result.

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
   the build pipeline takes one around a model body and its emit. The artifact
   work a build asks for under its slot — the surfaces and meshes its declared
   mesh exports lack — runs in the build's own process, under that slot,
   whichever executor runs the build (`artifacts.worker_context`): its kernel and
   store are loaded there, where a pool job cost a cold box's export 2.6 s of
   kernel import for 0.03 s of work. The build does the first share itself and
   deals the pool only shares that repay starting a worker (`artifacts.deal`:
   32 components' surfaces each), so a 250-part export spreads and a 40-part one
   does not; the daemon's warm spares get none of it, because the build has
   bound one of them and the next share waited on a kernel import. A door and a
   server hold no slot, so their artifact work is always pool jobs. **Doors take
   none and never run a body**: `snapshot` and the mesh doors
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
   next build rebinds a spare — no import repaid.
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
work, charged when a display or selector first requires them. On the daemon,
an artifact job is never killed when its caller leaves, as the CAD Viewer's do
routinely: the worker stays warm rather than being replaced by a fresh kernel
import. Before each derivation the worker asks its supervisor whether anyone
still wants the job: its caller, or an identical request that attached to it
since. When no one does, the job ends with what it has derived, all of it in
the store, and a later identical request starts its own job, which finds those
there. One that ran to its end instead kept its worker busy for the rest of a
64-component request while the next model's request waited for a kernel
import. A build or a door whose caller leaves is stopped.

**Browser resources.** Disposable decoded meshes, selectors, BVHs, GPU buffers,
textures and worker work may have byte budgets and be reclaimed when unused.
Admission includes replacement overlap and temporary allocations; active
owners must not be invalidated by another scene's release. GPU and worker heap
figures are estimates where browser APIs expose no measurement. Each live
mesh decode worker owns its highest completed-request estimate; terminating
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
deletable, never the only durable copy of an authored change. A build's events
carry what that status reads and no more: the "Saving STEP" preview names the
output and the source result's tree, a saved result the document's tree and
digest, and the ledger keeps nothing else of either. Kinematics, appearance
and animation travel in the sidecar alone.

Only model-run producers advance editing order. Compiling saved bytes and
attaching a coalesced subscriber to an existing producer do not create a new
editing revision or hide the producer's preview. A concurrent child request
adopts its announced job before executing, so a completed build leaves no
orphaned pending status behind in the ledger.

These ephemeral preview handles are not GC roots. The normal grace period
protects newly published objects; explicit GC or cache deletion can expire an
older preview, including one retained after a failed save. The durable source
and saved STEP remain the recovery path.

The viewer shows the saved file, always: the catalog's bytes with the topology
and annotations that belong to them, replaced in place when a build writes new
bytes (the components it already holds are retained: the last paragraph). It reads
this channel (`GET /__cad/preview`) for status alone: whether a build of the file
is queued or running and its phase, and a failure with its message. An answer
carries no geometry; the server does no kernel work and exposes no
source/closure/model record. A finished build whose output is no longer the file
on disk -- the bytes it saved replaced or, if it saved nothing, the file written
after it ended -- is reported `superseded`, and its failure is no longer the news.
The viewer reads the catalog again when a build finishes or is superseded, rather
than at its next poll. It never announces a background file write it did not
perform. A saved-tree identity change clears incompatible selection and
measurement state.

The server reads one more thing off the channel, to save that catalog read its
time: when a build of the watched file has saved its outputs, it starts their
catalog rows on a thread of its own, the watched file first
(`cadgen.viewer.warm`). Law 1 holds for those rows as for every other: a row is
computed from its file's bytes, and its digest from those bytes. The tree the
ledger says the build saved is used only to start that tree's capture while the
bytes are read; a row shows it only if the bytes name it. Warming is best effort:
what it fails at is left to the read, and the channel answers regardless.

An open editing tab holds one request against an opaque ledger cursor scoped
to its output and store. A matching change wakes it immediately; unrelated jobs
do not cause browser updates. The cursor and job snapshot are captured under
the same lock, and a daemon restart changes the cursor's epoch. The daemon
admits at most 32 read-only waiters, separate from build workers and CPU slots;
saturation returns a snapshot without another thread and the client backs off
to 500 ms. A one-second heartbeat
still rechecks whether the file moved past the newest build, even with no build
event. Closing or switching the tab aborts its request; a disconnected feed
retries without starting a daemon or a model. This adds no persistent state.
The CAD app's tunnel (`cadgen.mcp.tunnel`) never holds the request: it drops the
cursor, so the daemon answers with a snapshot at once, and the client paces
itself (a host relays every call through a few slots all its views share).

The preview is the model's final immutable source result. Parents may pin and
materialize that result before the child's STEP save finishes. It becomes
`record.tree` only after the model's publication checks and dependent saves
succeed; it is never replaced by translated STEP geometry and never used as a
document-byte mapping. Successful explicit saves require all declared outputs;
publishing a preview alone is not success. No saved byte hash is mapped to a
preview tree.

An interactive viewer can retain a complete displayed component across a
replacement when its full SURF object hash, component identity, origin and
effective tessellation agree. Tree-specific placements and appearance are
recomposed. This is disposable browser ownership, not a new persistent cache
or source of geometry identity. Superseded or failed staging does not release
the last complete view's ownership. No automatic-save producer exists in this
runtime: all decorated runs have explicit completion obligations, so display
supersession does not cancel their exports.

## 10. Debugging

- Which record: `index/model/<sha256(script::function)>-v<schema>` —
  `cadgen store why <model.py>` prints it (every model of the file; name one
  as `model.py::function`), the gate's verdict clause by
  clause (with each child's pinned vs current tree), the closure files (a
  sliced helper as `lib/geo.py[plane, cyl_along, …]`, its reached names) and
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
  deletion, damage or atomic replacement invalidates that snapshot, and the
  next request verifies again, by hash, what moved and takes on its identity
  what still holds: each object this process hashed to its address is
  remembered under the settled identity it had (`objects.verified_stamp`),
  each tree it verified under its whole closure, and a component entry
  already validated against its object's bytes needs no bytes while the
  object holds. A native capture (`retain_payloads=True`) reads every object,
  since it owns the bytes, and remembers what it verified all the same. A
  claim by this process keeps an identity (§8); any other write moves it. A
  read is only remembered once it is far enough past the write it observed
  that a further write must
  stamp a different mtime — a filesystem times writes by a clock of its own
  resolution (~15.6 ms on Windows, whose `st_ctime` is the creation time and
  never moves for a rewrite; a 100 Hz timer interrupt on Linux before 6.13,
  even where the stamp shows nanoseconds), and a same-size rewrite inside that
  tick is invisible to every stat field. No read settles in less than two
  Windows ticks. The metadata cache is byte-bounded, store-root
  isolated and returns a newly parsed flattened view to every caller. The gate's
  completeness check (`tree_complete`) is such a consumer, and its output
  digests follow the same rule (§4). The CAD Viewer's surface routes are not:
  they verify a tree's component map once and keep it, for the eight trees
  they served last, and per request stat the tree and the objects of the
  components it names, so a deleted one sends the tree back through the
  complete verification.
  Components carry `brep`, `codec` and `faceColors`; display SURF resolves
  separately through `store.surfaces` and `index/surface`.
- `CADGEN_VERIFY_READBACK=1` makes every saved build that reuses a document
  tree — composed from its children's (§3) or taken from the document index
  for already-seen bytes — parse the written STEP as well, and fail with the
  first difference: the tree hashes, the top-level keys that differ, the
  first differing occurrence, the canonical maps. It is for a maintainer's
  manual check over a corpus; it doubles the read-back's cost and nothing in
  cadgen sets it. Like the store root, it travels with each build to the warm
  daemon, so it applies to exactly the builds started with it.
- `cadgen store info` sizes the store against its cap, names any retired
  kind still present and any `index/` folder it does not know, and says when
  a newer cadgen's writes keep passes off the store. `cadgen store gc
  --dry-run [--max-size [SIZE]]` reports what a pass would retire, evict and
  remove, and deletes nothing.
- **Resets, smallest first.** `python model.py --force` rebuilds one model
  now. `cadgen store forget <model.py>` drops that model's record (the next
  run rebuilds it; children untouched, parents see the moved pin then);
  `cadgen store forget <document>` drops this cadgen's `index/document` entry for the
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
- Add a version salt to an object's address, or a global schema number to component
  identity (§2, geometry identity and versions).
- Add a lock that a reader consults to decide freshness — or any build lock
  at all; the publish rule and pins are the whole concurrency story.
- Let a door, the viewer, snapshot or any render path open `index/model` or
  `index/output` (§2, property 2). A reader's one lookup is `sha256(bytes)` →
  `index/document` → objects.
- Make a reader refuse, or a door rebuild from source: a missing tree is a
  compile job from the file's bytes; "behind its script" is `store why`'s.
- Write to the store on a read: no hit refreshes a stamp or an mtime (§5).
- Evict a record, a document entry or an output entry, or delete an object any
  way but rename, then recheck (§8).
- Delete anything from a store a newer cadgen wrote to within the last 30
  days, or touch a folder under `index/` that is neither in `INDEX_KINDS` nor
  in `RETIRED_KINDS` (§8).
- Use process/display eviction as a reason to mutate exact geometry. Disposable
  memory budgets and worker reclamation follow §9 and never determine
  saved-artifact freshness.
- Let a decorator argument change the geometry a model produces: arguments
  place files, tune how they are written, and declare kinematics; the tree
  is the return value as returned (README law 16).
- Write a sidecar for anything but kinematics, or copy into it what only a
  record needs (README law 17): a mesh door tessellates the document's tree
  and never reads a declaration back.
- Use a retired word (§1) in code or documentation.
