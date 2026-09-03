# The store

`~/.cache/cadgen/` — where every model's result lives. Read this before
changing anything under `cadgen/store/`, the build pipeline that writes to it,
or a consumer that reads from it. It is written so that someone who only ran
`pip install cadgen` can act on every sentence.

## 1. Vocabulary

One word per concept; the code uses these words and no others.

| term | meaning |
|---|---|
| **model** | a parameterless `@step` function (with any stacked `@stl/@glb/@3mf`); identity = its resolved script path; one per file |
| **parent / child** | models related by a call inside a body |
| **build** | running a model's function and publishing its result |
| **store** | the whole cache, `~/.cache/cadgen/`: `objects/` + `index/` |
| **object** | an immutable, content-addressed file in `objects/` — a component or a tree |
| **component** | a leaf geometry object: one solid's `.brep` + `.surf` |
| **tree** | a model's result object: its own components + links, with placements, names, colors; its hash is the model's result identity |
| **link** | a tree entry pointing at a child's tree hash, with placement and name |
| **pin** | the child tree hash a parent resolved during a build (noun and verb) |
| **record** | the mutable per-model entry in `index/`: current tree hash, closure, children pins, outputs |
| **index** | the input-addressed side of the store: records, op-memo entries, mesh entries |
| **op memo** | the per-kernel-operation cache (always two words) |
| **closure** | the source files a model's build read |
| **stale / current**, **gate** | the freshness state and the check that decides it |
| **worker / spare / extra**, **job** | daemon vocabulary (the daemon's own documentation) |

Retired words: node, package, descriptor, manifest, ref (as a store concept),
memo (bare), scope, blob. They do not appear in code or documentation.

## 2. Layout

```
~/.cache/cadgen/                      (CADGEN_CACHE_DIR overrides; else the platform cache dir)
  objects/ab/cdef…                    immutable, content-addressed, sharded like git
  index/model/<sha256(script path)>   records (input-addressed, mutable, atomic)
  index/component/<cid>               component entries → {surf, brep} object hashes
  index/op/<sha256(op key)>           op-memo entries → object hash
  index/mesh/<key>                    tessellation entries → object hash
  index/dxf/<sha256(drawing)>         drawing freshness entries (the @dxf pipeline)
  locks/                              advisory build coordination (not store contents)
```

There are exactly two ways a file is named, and that is the only distinction
the store makes:

- **Content-addressed** (`objects/`): the name is `sha256(bytes)`. Two kinds
  of object exist — a **component** (the `.brep` bytes, and separately the
  `.surf` bytes, of one solid) and a **tree** (JSON). Writing an object is
  idempotent; an object is never rewritten or edited. A result is complete
  when its tree object exists, and nothing references a tree until it does,
  so a half-written result cannot exist.
- **Input-addressed** (`index/`): the name is derived from what PRODUCED the
  entry (a script path, a kernel operation's inputs, a surface × tolerance),
  and the entry is a small JSON file pointing at objects or recording facts.
  Entries are mutable and written temp + rename.

No directories per result, no hardlinks, no staging directories, no version
salts. The `.step` document, its sidecar and declared mesh files are
**outputs** in the project, not store contents; the record lists them with shas.

## 3. Tree and record

### Tree

A tree is the JSON a model's build writes. Its hash is the model's result
identity. A real one (`link_arm`: a bar plus two placements of a pin model):

```json
{
  "label": "link_arm",
  "entryKind": "assembly",
  "units": "mm",
  "components": {
    "0c5932ad05ce64a6": {"surf": "c1a8623b…", "brep": "ebe7552f…", "contentHash": "0c5932ad…"}
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
  (`cid`, a content hash of the exact shape); each names the `.surf` and
  `.brep` objects. `occurrences` place components; `links` place children's
  trees. Two placements of one child are two links to one tree. Transforms
  are 16 numbers, row-major, translation in the fourth column, in the
  parent's frame.
- `assembly.root` is the grouping the author's compound expressed; a link
  appears in it as a node of type `link`.
- Consumers that speak the older flat shape (the viewer client, the Node
  exporters) read a **flattened** tree: `cadgen.store.trees.flatten` expands
  links recursively (ids rebased — a child's `o1.2` under link `o1.3` becomes
  `o1.3.2`; a part child's single occurrence takes the link's name),
  composes transforms, and merges components. `cadgen.store.view` lays that
  out as a temporary directory or serves it virtually; nothing of the sort is
  ever written INTO the store.

### Record

The mutable per-model entry, `index/model/<sha256(resolved script path)>`.
A real one (`link_robot`: a base, two placements of `link_arm`, one of
`link_pin`):

```json
{
  "kind": "record",
  "model": "/abs/models/examples/src/link_robot.py",
  "entryKind": "assembly",
  "sourceKind": "python",
  "tree": "64429167…",
  "closure": {"hash": "e341ac84…", "files": ["/abs/models/examples/src/link_robot.py"], "static": false},
  "children": [
    {"model": "/abs/models/examples/src/link_arm.py", "tree": "c161092b…"},
    {"model": "/abs/models/examples/src/link_pin.py", "tree": "265aee57…"}
  ],
  "outputs": {"/abs/models/examples/STEP/link_robot.step": {"sha256": "823699b0…"}},
  "stepHash": "823699b0…"
}
```

- `children` is recorded from the CALLS the body made — every child wrapper
  entered during the body appends `(model, pinned tree)`, whether that child
  ended up linked, inlined, modified or discarded. It is never derived from
  links.
- `closure.files` is the model's static import closure (AST, transitive,
  first-party) **stopping at model files**, plus files executed in its own
  frame and discovered inputs (`read_step` documents, the `.anim.js`). The
  boundary is decided statically by what the importer TAKES from a model
  file: only model functions (`from arm import arm`) → a result edge, file
  excluded, the child tracked by its pin; anything else (`from plate import
  WIDTH`) → a source edge, file included. Hit and miss runs record identical
  closures by construction. `closure.static: true` marks a record whose
  inputs are not files (a document re-emitted by `cadgen step build`); the
  gate's clause 2 does not re-hash files for it.
- A leaf has `children: []`. Roots and leaves have the same record. A record
  for an imported document (`sourceKind: "step"`) has the document's bytes as
  its closure.
- `outputs` may carry per-output facts a door needs (`declared`, the
  tessellation `chord`/`angle`, the baked `pose`); those are the door's, the
  store only keeps them beside the sha.

## 4. The gate

`cadgen.store.gate.stale(model)` — one function for every model. Stale if any
of:

1. **No record.** Protects against reading a result that was never built or
   whose record was collected.
2. **`sha256(closure.files as they are now) != closure.hash`.** Protects
   against a source edit; the hash is a semantic hash of each file's Python
   (comments and formatting do not count), computed at execution time (§5).
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
model only; its children go through the gate as usual.

## 5. Invariants

Each with the failure it prevents.

- **Hash at execution.** A closure file is hashed when the interpreter
  executes it (an audit hook on `exec`), not after the build. Prevents: a file
  edited during a long build being recorded with the bytes that did NOT run,
  which would make a stale result read as current forever.
- **Publish order.** Objects first (components, then the tree), then the
  outputs (`.step` moved into place atomically; sidecar), then the record.
  Prevents: a record pointing at a tree that does not exist yet, or a `.step`
  whose sha the record has not seen.
- **Publish rule.** `cadgen.store.publish.decide`: a build never replaces a
  current record with a stale one — if the record on disk already reflects the
  closure as it is NOW and the build that finished ran against older sources,
  the result is discarded. Prevents: two concurrent builds of one model ending
  with the older source's result on disk.
- **Children from calls, never from links.** Prevents: a modified or discarded
  child dropping out of the dependency edge, so an edit to it would not reach
  the parent.
- **Closure boundary rule.** A model file reached only through its model
  function is a result edge (pin); anything else taken from it is a source
  edge (file in the closure). Prevents both false-current (a constant imported
  from a model file changing unnoticed) and false-stale (a child's internal
  edit rebuilding every parent).
- **Pins and snapshot isolation.** A parent materializes the tree it pinned
  when the child was resolved, even if the child is rebuilt mid-parent-build.
  Prevents: a parent's result mixing two versions of one child.
- **Objects are immutable.** An object is written once under its hash and
  never edited. Prevents: a component changing under every tree that shares
  it.
- **Portability: a moved project is a set of new models over the same
  objects.** Nothing path-dependent enters an object: closure files are
  recorded relative to the script, trees hold geometry, names and placements
  only, and component ids are content hashes — so a moved or copied project
  hashes to the same closures and the same trees. Records ARE keyed by the
  resolved script path, so after a move every model reads as unbuilt (clause
  1); its first build runs the body once, finds every component and tree
  already present (nothing is re-extracted or rewritten; the tree hash comes
  out identical), writes a new record and re-notes its documents in
  `index/document`. Until that first build, a moved GENERATED document has no
  document entry and reads as an import (its own source); an actually imported
  document gets a new record at its new path pointing at the same tree. The
  records at the old path become unreachable and GC collects them. Prevents:
  two projects at different paths sharing one record and one overwriting the
  other's outputs list; and a path or timestamp changing a hash.
- **Outputs are not store contents.** The `.step`, sidecar and meshes live in
  the project; the record validates them by sha (clause 5). Prevents: a
  store wipe destroying a user's documents, and a document pretending to be
  current after a hand edit.
- **No locks are needed for correctness.** Objects are idempotent, entries
  are temp+rename, the publish rule decides concurrent same-model outcomes,
  pins isolate parents. The advisory `locks/` tier remains in this phase for
  progress reporting and to keep two builders of one model from doing the
  same kernel work twice; nothing reads it to decide freshness.

## 6. Link or component

Decided mechanically; there is no error path.

- `cadgen.store.materialize.materialize(tree)` rebuilds a child's geometry as
  a build123d `Compound` and TAGS it with the tree hash and a handle to the
  shape it was built from. The tag is metadata for the build, not part of any
  contract a model author sees.
- When the parent's result is written, every tagged compound found in it whose
  shape is still the one it was materialized with (`IsPartner`: same
  underlying shape, any rigid placement, relabelled or recolored or not)
  becomes a **link**. Everything else — geometry the parent made, a sub-shape
  it extracted, a child it modified (`housing() - holes`), a mirrored child —
  becomes the parent's own **components**. Modifying a child is legitimate and
  fully tracked (the child is still in `children` because it was called); it
  simply makes the parent own that geometry instead of linking.
- Placement that keeps the link: `child.moved(loc)` and `Location * child`
  (the same shape, re-placed). build123d's `child.located(loc)` deep-copies
  the geometry (`BRepBuilderAPI_Copy`), which serializes to different bytes —
  a new component id, so a component rather than a link. That is not new
  cost (the copy never shared a component id either); it is why the skill
  places with `moved()`.
- **The materialize contract.** A parent may rely on: the child's exact
  geometry, its labels, colors and placements, as a compound whose children
  mirror the child's grouping. It receives nothing else — a child's sidecar
  content (kinematics, animation, export declarations) never rides up.
- A `link` in a tree is resolved by hash, so two placements of one child are
  two links to one object, and a child shared by many parents is stored once.

## 7. Concurrency

No serialization, no cancellation, no waiting on another build.

- **Same model twice.** Both builds run. Each publishes objects (idempotent)
  and then consults the publish rule: the one whose closure matches the
  sources as they are now wins the record; the other's result is left as
  unreferenced objects for GC.
- **Edit a child while its parent builds.** The parent already pinned the
  child's tree when it called it; it materializes that pin and publishes a
  record whose pin no longer matches the child's current tree. The parent is
  therefore already stale when it finishes — the next gate says so (clause
  3) and the next run rebuilds it. `cadgen store why` shows the mismatch.
- **Edit a parent while a child builds.** Unrelated: the child's record and
  tree are its own. The parent's next build calls the child, finds it
  current, and pins the new tree.
- In this phase child builds run as subprocesses of the parent's build and
  the parent waits for the child it called (it needs the geometry); it never
  waits for a build it did not start.

## 8. GC

`cadgen store gc [--dry-run] [--grace-hours H]` — mark and sweep. Reachable =
every object referenced (transitively, through links) from a record, plus the
objects component/op/mesh entries point at, plus anything modified within the
grace period (default 1 h — the window in which a build may still hold a pin
to a child's previous tree). No age sweeps, no per-tier rules. When a daemon
is up, GC runs through it and respects live pins (a later phase).

## 9. The daemon

The warm build daemon routes a top-level call by model (script path) and runs
the same pipeline this document describes; it holds no store state of its
own. Pins and extras are described in the daemon's own documentation.

## 10. Debugging

- Which record: `index/model/<sha256(resolved script path)>` —
  `cadgen store why <model.py>` prints it, the gate's verdict clause by
  clause (with each child's pinned vs current tree), the closure files and
  the tree's links.
- Resolve a tree: `cadgen.store.trees.get_tree(hash)`; flattened with
  `flatten(hash)`. Components: `tree["components"]`, each with its `surf` and
  `brep` object hashes under `objects/ab/cdef…`.
- `cadgen store info` sizes the store. `cadgen store gc --dry-run` lists what
  a sweep would remove.
- Clearing the store is always safe: delete `~/.cache/cadgen` (or the
  `CADGEN_CACHE_DIR` directory). Every model reads as stale and rebuilds; no
  project file is touched.

## 11. Never

- Write a file into the store non-atomically (objects: temp + rename under
  the hash; entries: temp + rename).
- Put a path, a timestamp, or anything machine-specific into an object.
- Derive a model's dependencies from its tree's links.
- Add a version salt to a store name.
- Add a lock that a reader consults to decide freshness.
- Add a memory cap or an age-based eviction rule.
