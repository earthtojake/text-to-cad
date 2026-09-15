# cadgen

The published distribution: everything that turns CAD source into documents,
documents into derived state, and derived state into pixels and meshes. One
PyPI package carrying both language halves — the Python engine under
`src/cadgen/`, and the built JavaScript it executes under
`src/cadgen/_runtime/` (the cadgen-js runtime and the CAD Viewer's client,
bundled in at build time; the JS *source* lives in its own packages and never
ships as source).

**PURPOSE** — the engine and its command surface: model execution, the
store, document assembly, kinematics, exports, validation, inspection,
snapshots, the warm daemon and its build pool, and the CAD Viewer
(`cadgen viewer`: a local HTTP server over the built client, one directory per
instance).

Snapshot `--debug --json` reports artifact resolution and measured browser
stages; see [snapshot diagnostics](SNAPSHOTS.md) for timing boundaries.

**MAY DEPEND ON** — the Python ecosystem it declares (OCP/build123d lazily,
never at namespace-import time) and the *built outputs* of `cadgen-js`.
Never app code, never `cadgen-js` source at runtime.

Expensive pure parameterized geometry helpers may opt into [`@memo`](MEMO.md).
The decorator uses the existing object/index store and requires no author-owned
cache utilities. It is separate from the parameterless models that declare files.

**DEPENDED ON BY** — every skill (as a pinned installed distribution). The
CAD Viewer is not a dependent but a part: `cadgen.viewer` serves the client and
submits a document's compile as a job to the same build pool every door uses.

## The design laws

These are LAWS, not conventions: a change that violates them is wrong even
when it works. Each carries a pressure-test to apply before writing code.

### 1. Generated files are totally independent of their source code

A generated file (STEP, DXF, STL, GLB, 3MF) and its sidecar
(`<name>.step.json`) stand alone, forever.

*Pressure-test*: a generated file must be fully renderable — viewer,
snapshot, inspect — by reading ONLY the generated file(s), the sidecar, and
the store's artifact side. Never the source. A file whose bytes have no tree
in the store is compiled from those bytes (`cadgen step compile` semantics),
never from source. Deleting every `.py` in a project must not change what
renders.

The viewer automatically follows an active build's immutable preview tree
before STEP persistence ([`STORE.md`](STORE.md) §9b). This is a separate
runtime input: it does not change saved-artifact read-back or allow artifact
readers to inspect source or model records. Concurrent child requests adopt their
announced jobs before execution, so completed builds leave no orphaned pending status.
Following edits keeps the authored preview after a successful STEP save.
The viewer reports incomplete or failed updates without announcing background file writes. Without an available editing preview,
the viewer resolves the saved bytes and corresponding topology and annotations.
Native geometry completeness is separate from display-surface readiness.
Canonical trees pin encoded BREP and effective intrinsic face colors; surface
extraction is an artifact-only build-pool job selected by an attested producer.
`read_step`, STEP re-emits and parent materialization do not wait for SURF.
A first display or selector request still pays missing surface derivation.
The exact input, codec and recovery boundaries are in [`STORE.md`](STORE.md).

The authored tree is also the final result returned by decorated calls when the
caller consumes that result. A conventional real-file `__main__` bare call
finishes the checked source result and every declared output, then avoids
materializing geometry that Python immediately discards; assigned, nested,
interactive and instrumented calls retain the geometry return. A parent can
consume a child's complete source result before that child's STEP save, but
waits for every called child's declared outputs before saving itself.
The child's job carries the exact immutable pin; asynchronous consumers never
look up a newer model record to resolve it.
For a small result made entirely of pinned child links, the build runtime
captures verified geometry and appearance and validates private native shapes
before publication. It can then assemble the private STEP document after the
source event. Ordinary model code, child-output waiting and saved-byte readback
keep their existing semantics; unsupported or forced builds use the ordinary
order. The bounds and ownership limits are specified in [`STORE.md`](STORE.md) §6.
An exact `Compound(children=[...])` of eligible lazy children preserves their
pins through composition instead of reconstructing them at attachment. Native
access or hierarchy mutation restores ordinary private geometry. Until then
the root is an internal Compound subclass, so exact-type introspection differs;
`isinstance(root, Compound)` stays true. See [`STORE.md`](STORE.md) §9a for the
eligibility and escape boundaries.

- Nothing a renderer reads references the source tree: the sidecar's
  kinematics are resolved numbers and labels, its appearance uses canonical
  leaf occurrence IDs, and its animation is an embedded self-contained ES
  module; a tree and its
  components carry no path, script or record key
  ([`STORE.md`](STORE.md) §2, the two-sides law).
- A door never refuses a document and never auto-rebuilds: whether a
  document is behind its script is the model's record's question, answered
  by `cadgen store why` and the build tree, never by a render path.
- Source scripts are PROGRAMS: run, never passed to CLIs, never parsed by
  renderers.

### 2. The store contains only derived results

`~/.cache/cadgen` is the store: content-addressed objects (a model's result
tree and the components it is made of) and input-addressed index entries
(the per-model record, the document → tree map, op-memo and tessellation
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

There is no automatic GC: `cadgen store gc` is the only sweeper, and every
object is immutable and idempotently written, so deletion never needs
coordination — a racing reader re-misses and rebuilds. Store correctness needs
no lock protocol: atomic writes, pins and the publish rule (`STORE.md` §5, §7)
decide concurrent outcomes. Saved-file readers never wait for a source model
to finish; missing derived artifacts are resolved through the build pool.

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

### 5. Byte determinism

Same inputs, same bytes, every format — STEP (canonicalized NAUO ids and
presentation-style ordering), meshes (one deterministic tessellator), DXF
(geometry-ordered emitter). Content-addressing and every freshness ledger
depend on it.

### 6. One surface, three faces

The DECORATOR declares a capability on a model, the PUBLIC FUNCTION
(`cadgen.<format>.<verb>`) performs it, and the CLI (`cadgen <format>
<verb>`) is GENERATED from the function's signature
(`_internal/cli_from_function.py`) — never hand-written, structurally
sync-tested.

*Pressure-test*: for any option, "what is this called on the other two
surfaces?" must answer with the same name and a role-determined payload —
`kinematics` everywhere: on DECLARING surfaces (decorators, `step build`)
it is the space (`{mates, couplings, poses, at}`); on CONSUMING surfaces
(snapshot, mesh `build`) it is a point in that space (a preset name or
`{dof: value}`). One name, one validator, no synonyms.

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

### 8. No backwards compatibility

Hard cutovers only. Every retired surface fails loudly with a teaching
error naming its replacement — never an alias, never a shim.

### 9. Closed vocabularies

Every declaration surface has a closed key/kind set. Unknown keys are
teaching errors, never silently ignored.

### 10. Loud failure or correct output, nothing between

The cardinal sin is plausible-wrong output at exit 0. No silent fallbacks,
no globs, no guessing; a failed render leaves NO file at the requested
path.

### 11–14. Runtime laws (shared with cadgen-js)

Kinematics is pure data and choreography is pure JS, fully independent
(11). Clients render from file + sidecar + the store's artifact side and never
read source, a record, or trigger source builds (12). An explicit editing
session may consume runtime-announced preview trees as specified in STORE §9b.
Correctness never depends on a
store hit (13). Composition: importing binds, calling links — a parent
depends on a child by its RESULT (the pinned tree), on a constant by its
VALUE, on a helper by its FILE — and a model must never `read_step` its own
output (14). The bundled runtime under `_runtime/` is the JS half of these;
the laws' JS statements live with the cadgen-js source.

### 15. The package ships alone

The installed distribution is the whole world: the Python engine, the
bundled `_runtime/`, and this document. It works with the repository it
was built from gone — and its markdown must read that way, referring to
nothing outside the package.

*Pressure-test*: every sentence in the package's markdown must be true and
actionable for someone who only ran `pip install cadgen`. Naming a bundled
thing ("the cadgen-js runtime bundled at build time") passes; a repo path
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

A source fast path may refresh literal `kinematics=`, `materials=`, and
`animation=` annotations from the model module without executing geometry.
It requires an exact executed-byte closure attestation, unchanged dependencies
and child pins, complete cached baseline/document trees, and same-module
literals used only by those decorator arguments. A computed or imported
annotation may coexist: its expression remains in the geometry fingerprint and
its recorded value is reused only while that expression and its dependencies
are unchanged. Reflection, another use of a stripped literal constant, or a
change to computed annotation code falls back to the ordinary model build.

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

Schema 9 sidecars contain only `schemaVersion`, the saved STEP's `documentHash`,
and optional `kinematics`, `appearance`, and `animation` sections. Appearance
stores named material definitions plus canonical leaf occurrence assignments;
animation stores a self-contained JavaScript ES module. Appearance is applied to an owned
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
  kinematics.py          # typed mates vocabulary (revolute/slider/
                         #   cylindrical/fastened, couple, normalize)
  step_scene.py          # read_step and scene loading (recorded inputs)
  inputs.py              # declare_input: a data file the model reads and
                         #   cadgen has no reader for (a JSON atlas, a CSV
                         #   table) is a freshness input once it says so
  assembly.py            # AssemblyHelper — positioning through native joints, labels
  results.py             # the typed Results every verb returns (stdlib-only)
  store/                 # the store (STORE.md): objects, index, records, trees,
                         #   closure, gate, materialize, publish, lazy, gc, view
  cli/                   # generated command shells, one per <format> <verb>
  cli_tree.py            # the build tree on stderr / JSONL events
  daemon/                # the build pool: executors (daemon + transient),
                         #   broker (job slots, coalescing), pool (workers,
                         #   spares, extras), jobs (the ledger), server,
                         #   worker, client, transport
  _internal/             # the engine: generation pipeline, tree builder,
                         #   FK (kinematics_fk/resolve), mesh_export ledger,
                         #   cli_from_function, doors (documents by bytes),
                         #   source_sidecar, step_assemble/step_reemit
  viewer/                # the CAD Viewer's server: launcher (main),
                         #   routes (http_app), catalog (scanner), status
                         #   (artifact_status: not compiled / compiling /
                         #   compiled / failed), build_progress (the daemon's
                         #   job ledger, read over its socket)
  _runtime/              # BUILT JS (browser snapshot renderer, node
                         #   builders, the viewer client) — generated, never
                         #   edited here
```

Verbs by format: `step` compile · build · snapshot · inspect;
`stl`/`3mf`/`glb` build · snapshot; `dxf` snapshot; `urdf`/`sdf`
validate · snapshot; `srdf` validate. `cadgen snapshot` routes any suffix.
`cadgen store|daemon|doctor` are status commands, and `cadgen viewer
[list|stop]` the CAD Viewer's launcher and instance manager — all deliberately
outside the mirror pattern. `cadgen step compile` is internal tooling: skills never
teach it — doors compile a document's missing tree on demand.

Developed in [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad);
that repo's contributor guide carries the development workflow (tests,
bundling, versioning).
