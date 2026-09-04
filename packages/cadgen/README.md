# cadgen

The published distribution: everything that turns CAD source into documents,
documents into derived state, and derived state into pixels and meshes. One
PyPI package carrying both language halves — the Python engine under
`src/cadgen/`, and the built JavaScript it executes under
`src/cadgen/_runtime/` (the cadgen-js runtime and the CAD Viewer's client,
bundled in at build time; the JS *source* lives in its own packages and never
ships as source).

**PURPOSE** — the engine and its command surface: model execution, the
content-keyed cache, document assembly, kinematics, exports, validation,
inspection, snapshots, the warm daemon, and the CAD Viewer (`cadgen viewer`:
a local HTTP server over the built client, one directory per instance).

**MAY DEPEND ON** — the Python ecosystem it declares (OCP/build123d lazily,
never at namespace-import time) and the *built outputs* of `cadgen-js`.
Never app code, never `cadgen-js` source at runtime.

**DEPENDED ON BY** — every skill (as a pinned installed distribution). The
CAD Viewer is not a dependent but a part: `cadgen.viewer` serves the client and
compiles foreign STEP imports in a worker process it owns.

## The design laws

These are LAWS, not conventions: a change that violates them is wrong even
when it works. Each carries a pressure-test to apply before writing code.

### 1. Generated files are totally independent of their source code

A generated file (STEP, DXF, STL, GLB, 3MF) and its sidecar
(`<name>.step.json`) stand alone, forever.

*Pressure-test*: a generated file must be fully renderable — viewer,
snapshot, inspect — by reading ONLY the generated file(s), the sidecar, and
the cache. Never the source. A missing cache regenerates from the generated
file's own bytes (`cadgen step compile` semantics), never from source.
Deleting every `.py` in a project must not change what renders.

- Nothing a renderer reads references the source tree: the sidecar's
  kinematics are resolved numbers and labels, its animation is COPIED
  module text.
- The sidecar's closure fields exist for the source-side no-op gate only.
  Staleness at any door is a teaching error naming `python <script>` —
  nothing auto-rebuilds.
- Source scripts are PROGRAMS: run, never passed to CLIs, never parsed by
  renderers.

### 2. The store contains only derived results

`~/.cache/cadgen` is the store: content-addressed objects (a model's result
tree and the components it is made of) and input-addressed index entries
(the per-model record, op-memo and tessellation entries) — data derivable
from sources and documents, and nothing else. Its layout, formats, gate and
invariants are the contract in [`STORE.md`](STORE.md); read it before
touching anything that writes to or reads from the store.

*Pressure-test*: everything in the store is (a) a pure function of some
source or document, (b) safely deletable at any time, and (c) rebuildable
by running the models again. If losing a store entry would lose information,
that information is in the wrong place.

**The store is what the sources imply; the sidecar is what the author meant.**

There is no automatic GC: `cadgen store gc` is the only sweeper, and every
object is immutable and idempotently written, so deletion never needs
coordination — a racing reader re-misses and rebuilds.

### 3. One sidecar per artifact, and it belongs to that artifact alone

`part.step` gets `part.step.json` — schema-versioned sections (closure,
kinematics, animation, meshExports). New capability = new section + schema
bump, never a second sidecar file. Model-side, beside the artifact, so it
travels with the file it describes.

A sidecar describes the model that declared it — never its parent, never its
children. A parent composing a child receives GEOMETRY (tree, labels, colors,
placements, exact shape) and nothing else: the child's kinematics and
animation are written by the child's own build into the child's own sidecar,
and an assembly that needs a relation declares it on the assembly. This is
what lets a cached child stand in for its function: the cache carries
geometry, and geometry is all a parent may read.
*Pressure-test*: build a child that declares `kinematics=`, then build a parent
that composes it. The parent's sidecar must contain only the parent's own
declarations, and the child's sidecar must be unchanged by the parent's build.

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

`python model.py` is the one source door: it gates, builds, writes the
document + sidecar, and heals declared exports. Every CLI takes documents.

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
(11). Clients render from file + sidecar + cache and never read source or
trigger builds (12). Correctness never depends on a cache hit (13).
Composition: importing links, `cadgen.compose.memo` caches; a model must
never `read_step` its own output (14). The bundled runtime under
`_runtime/` is the JS half of these; the laws' JS statements live with the
cadgen-js source.

### 15. The package ships alone

The installed distribution is the whole world: the Python engine, the
bundled `_runtime/`, and this document. It works with the repository it
was built from gone — and its markdown must read that way, referring to
nothing outside the package.

*Pressure-test*: every sentence in the package's markdown must be true and
actionable for someone who only ran `pip install cadgen`. Naming a bundled
thing ("the cadgen-js runtime bundled at build time") passes; a repo path
to its source, a repo script, or a repo workflow does not.

## The shape of the package

```
src/cadgen/
  <format>.py            # public namespaces: step, stl, threemf, glb, dxf,
                         #   urdf, srdf, sdf — each binds its verbs
  authoring.py           # @step/@dxf/@stl/@glb/@threemf decorators; a model's
                         #   outputs are what they declare — a mesh decorator
                         #   alone is a model that writes no STEP
  kinematics.py          # typed mates vocabulary (revolute/slider/
                         #   cylindrical/fastened, couple, normalize)
  compose.py             # memo — the traced, cached composition scope
  step_scene.py          # read_step and scene loading (recorded inputs)
  assembly.py            # AssemblyHelper — positioning through native joints, labels
  results.py             # the typed Results every verb returns (stdlib-only)
  cli/                   # generated command shells, one per <format> <verb>
  daemon/                # warm worker pool (supervisor never imports OCP)
  _internal/             # the engine: generation pipeline, package builder,
                         #   FK (kinematics_fk/resolve), mesh_export ledger,
                         #   cli_from_function, doors (documents-only gate),
                         #   source_sidecar, step_assemble/step_reemit,
                         #   caches (op memo, scope store, cache_paths)
  viewer/                # the CAD Viewer's server: launcher (main),
                         #   routes (http_app), catalog (scanner), freshness
                         #   authority (artifact_status), compile worker
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
teach it — doors compile missing packages on demand.

Developed in [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad);
that repo's contributor guide carries the development workflow (tests,
bundling, versioning).
