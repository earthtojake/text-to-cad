# Migrating a CAD project from cadgen 0.4 to 0.5

This is a hand-migration playbook. Work through it top to bottom with a v0.4
project open and you will end with a working v0.5 project. Nothing else is
required — no other document, no tool.

## Read this first: there is no compatibility layer

v0.5 ships **zero** backwards compatibility. Deliberately:

- No shims, no aliases, no deprecated keyword arguments.
- No codemod. `cadgen.migrate` was deleted; nothing rewrites your sources.
- **No teaching errors.** This is the part that surprises people. A v0.5 tool
  handed a v0.4-shaped call reports only what its *current* contract requires.
  A retired flag is an unrecognized argument. A retired job key is an unknown
  key. A `gen_step()` file is a file that declares no model. None of those
  errors will mention 0.4, migration, or what the thing used to be called.

So: when something fails during this migration, the error tells you what v0.5
wants, not what you did. Read it as a spec, not as a diagnosis. That is the
design — every entry point teaches exactly one contract, the current one.

The corollary is that a **half-migrated project fails confusingly**. A model
script converted to `@step` whose stale v0.4 sidecar is still on disk fails at
the sidecar, not at the script. Do the deletion step (step 5) before you start
debugging anything.

### The one-paragraph summary

A v0.5 model is a plain `.py` file that decorates one function with `@step` or
`@dxf`, and you build it by running it: `python model.py`. There is no
generation CLI. Artifacts land beside the script (or wherever `out=` says);
everything derived lands in `~/.cache/cadgen`, keyed by content. A model that
declares kinematics, animation, or mesh exports also writes one JSON sidecar
next to its artifact. Generated files carry no trace of their source.

## Prerequisites

1. **Python 3.11+ and a working v0.5 install.**

   ```bash
   python -m pip install -r requirements.txt   # from your project
   python -m playwright install chromium       # only if you render snapshots
   ```

   A project's `requirements.txt` names the distribution, with the snapshot
   extra if you render:

   ```
   cadgen[snapshot]
   ```

   In v0.4 a skill vendored cadgen through an editable path
   (`--editable ./scripts/packages/cadgen`) and named `playwright` separately.
   Replace that line.

2. **Confirm what you actually have.**

   ```bash
   cadgen doctor            # prints the installed cadgen
   ```

   v0.4 installed one console script, `cadgen-step-artifact`. v0.5 installs
   `cadgen`. If `cadgen` is missing, the install did not take.

3. **Commit or stash your work.** This migration deletes generated files.

4. **Keep a v0.4 build around if you care about geometry equivalence.** Before
   you delete anything, note the component content hashes of the old package so
   you can compare after (see "Verify the geometry did not move", below). If
   you do not care, skip it — snapshots are usually enough.

## Migration checklist

Do these in order. Later steps assume earlier ones.

- [ ] 1. Rewrite imports
- [ ] 2. Convert the generator into a decorated model
- [ ] 3. Move articulation to kinematics + `.anim.js`
- [ ] 4. Reshape the project layout
- [ ] 5. Delete v0.4 artifacts, sidecars, and caches
- [ ] 6. Rebuild
- [ ] 7. Verify

---

### 1. Rewrite imports

**Canonical import.** Every model script imports build123d through cadgen:

```python
# before (0.4)                      # after (0.5)
from build123d import Box, Cylinder from cadgen import build123d as bd
import build123d as bd              from cadgen import step
```

`cadgen.build123d` is a lazy, transparent re-export: `bd.Box` **is**
build123d's `Box` — same object, so `isinstance`, subclassing and `except`
clauses behave identically. The laziness is the point. A model script's module
body must stay cheap so the decorator can run the freshness gate and hand off
to the warm daemon *before* anything pays the ~2.5s kernel import. A current
model's re-run then never wakes the kernel at all.

Raw `import build123d` still works and is not an error — it just costs ~2.5s on
every re-run, and the decorator prints a hint on stderr when it sees the kernel
already imported.

Use **attribute style**. `from cadgen.build123d import Box` works but is eager:
a from-import must bind the object, which forces the real import immediately.

**Imports go at module top.** `sys.path` does not survive into the model
function — the pipeline restores it after loading the module. Import at module
level; only *call* the imported code inside the function.

**Reading a vendor STEP.** Use `cadgen.read_step`, never
`build123d.import_step`:

```python
# before (0.4)                              # after (0.5)
from build123d import import_step           from cadgen import read_step, step

motor = import_step("imported/motor.step")  motor = read_step(_HERE / "imported" / "motor.step")
```

The returned shape is identical (the root itself, not a wrapper, with
per-occurrence and prototype STEP colors applied), and it is served from the
content-keyed package store, so a warm read costs tens of milliseconds instead
of a full text-STEP re-parse.

**The recording is the real reason.** Freshness used to follow a model's Python
import reach, which is observable — modules announce themselves. A file read as
*data* announces nothing, so in v0.4 a model built from a vendor STEP kept
reporting itself current after that STEP was replaced, and only `--force` got
the truth back. `read_step` declares the file: its path and content hash join
the model's closure, and the next run's gate re-hashes it.

**The flatten projection helpers are gone.** v0.4's `cadgen.flatten` sampled
wires into point lists, unioned polygons in shapely, and emitted polylines.
v0.5 replaced that pipeline with exact OCC operations on the real faces, and
the sampling-era helpers were removed with it — a drawing built on them fails
with `AttributeError` at the point of emission:

| Removed (0.4) | Replacement (0.5) |
| --- | --- |
| `flatten.union_projected_faces` | `flatten.union_faces(flatten.flatten_faces(faces))` — exact OCC union of flattened faces |
| `flatten.project_face_polygon` | `flatten.flatten_face(face)` — lays the real face into XY; arcs stay arcs |
| `flatten.project_wire_points` | None. Nothing samples wires any more; return the flattened face itself |
| `flatten.add_shapely_geometry` | None. A `@dxf` function returns build123d 2D geometry; the engine writes the DXF |
| `flatten.add_ring` | Model the ring as geometry: an outer face with the inner contour as a hole |
| `flatten.add_circle_polyline` | Model the circle: `bd.Circle(r)` exports as a DXF `CIRCLE`, not a chord run |
| `cadgen.step_scene.import_step` | `cadgen.read_step` (see above) |

`flatten.flat_pattern(part, coordinate=..., kerf=...)` is the one-call form:
selection + flatten + union + optional kerf offset. Know its limit — it selects
the planar faces at ONE coordinate, so it unfolds a flat plate but **not a
folded bracket**. Unfolding a multi-panel part is now the caller's job: select
each panel's faces with `flatten.planar_faces(...)` per plane, flatten each
with its own placement (distributing that bend's allowance yourself), and fuse
with `flatten.union_faces(...)`. A worked multi-plane example lives in the dxf
skill's `references/generator-templates.md`.

### 2. Convert the generator into a decorated model

This is the structural change. A v0.4 source had a magic `gen_step()` /
`gen_dxf()` function and usually a `<name>.step.py` / `<name>.dxf.py` filename.
v0.5 reads neither.

```python
# bracket.step.py (0.4)              # bracket.py (0.5)
from build123d import Box            from cadgen import build123d as bd
                                     from cadgen import step
def gen_step():
    return Box(10, 10, 10)           @step()
                                     def bracket(width: float = 10.0):
                                         return bd.Box(width, 10, 10)
```

Mechanically:

1. **Rename the file to a plain `.py`.** `bracket.step.py` → `bracket.py`. The
   artifact still defaults to the sibling `<stem>.step`, so the STEP path does
   not move.
2. **Name the function after the file and decorate it** with `@step()` (or
   `@dxf()`). Both work bare (`@step`) or configured (`@step(...)`).
3. **Give every parameter a default.** The pipeline calls the function with no
   arguments; a parameter without a default is rejected at decoration. Promote
   module-level constants to defaulted parameters when you want them tunable.
4. **Move everything the model needs ABOVE the decorated function.** Decoration
   is what runs the build, so anything below it never executes.
5. **One `@step` or `@dxf` model per file.** A source defining two must be
   split. Entry identity — refs, packages, closures — is keyed by the source
   file everywhere in the pipeline.

#### Decorator arguments

`@step` takes, all keyword-only:

| Argument | Meaning |
| --- | --- |
| `out=` | Output path. **Script-relative** (see the path note below). Default: sibling `<stem>.step`. |
| `kind=` | `"part"` or `"assembly"`. Inferred from the return when omitted. |
| `kinematics=` | The typed-mates dict. See step 3. |
| `animation=` | Name of a `.js` choreography module beside the script. See step 3. |
| `mesh_tolerance=` | Chord tolerance for the render package. Relative — see step 6. |
| `mesh_angular_tolerance=` | Angular tolerance, radians. |

`@dxf` takes **only `out=`**. It has no `kind=` (a drawing is 2D geometry), no
`kinematics=` and no `animation=`; passing any of them is an error.

Unknown keyword arguments are rejected outright on both decorators.

> **`write=` is now `out=`.** If your sources came off an intermediate 0.5
> development snapshot that used `write=`, rename it. There is no alias.

#### The one path-semantics exception

Every CLI and function path argument in v0.5 is **native**: a relative path
resolves against the process's current working directory, an absolute path
works anywhere, and `~` expands. v0.4's cwd-gated and repo-gated behaviours are
gone.

The single deliberate exception is the **decorator's `out=`** — on `@step`,
`@dxf`, `@stl`, `@glb` and `@threemf` alike — which resolves relative to the
**script**. That is what makes a project relocatable: the declaration travels
with the model and produces the same layout whatever directory you run from.
`animation=` is likewise a name beside the script. Ad-hoc `OUT` arguments on
the CLI doors are cwd-relative, because they are one-shot and never persisted.

```python
@step(out="../STEP/bracket.step")   # ../STEP relative to THIS FILE
def bracket(): ...
```

#### What the function returns

A `@step` function returns a build123d `Shape`, or an envelope dict whose only
fields are `shape`, `stl`, `3mf`, `mesh_tolerance` and `mesh_angular_tolerance`.
Prefer returning the bare shape and declaring mesh outputs as decorators
(below) — that is the shape the rest of the toolchain reads.

A `@dxf` function returns build123d 2D geometry: a bare shape goes to the `CUT`
layer, or a `{layer: shape}` dict gives named layers (`CUT` / `ENGRAVE` /
`SCORE`). The engine writes the DXF bytes; you never call an exporter.

#### Mesh exports become stacked decorators

v0.4 produced meshes with a separate `scripts/export` run. v0.5 declares them
on the model, and every build produces them:

```python
# before (0.4)
#   python scripts/gen models/bracket.step.py --write
#   python scripts/export models/bracket.step.py --stl --3mf

# after (0.5)
from cadgen import build123d as bd
from cadgen import glb, step, stl, threemf


@step(out="../STEP/bracket.step")
@stl(out="../STL/bracket.stl")
@threemf
@glb
def bracket():
    return bd.Box(40, 20, 6)
```

- The 3MF decorator is spelled `@threemf` (identifiers cannot start with a
  digit); the CLI door is `3mf`.
- Stacking order above or below `@step` is behaviour-neutral.
- Bare (`@glb`) means the sibling default. Declare the same format more than
  once at *distinct* `out=` targets for draft/print variants; two bare
  declarations of one format collide, as do two identical `out=` targets.
- `@stl`/`@glb`/`@threemf` accept `out=`, `mesh_tolerance=`,
  `mesh_angular_tolerance=` and their own `kinematics=`. They do **not** accept
  `animation=` — mesh exports are static bakes.
- Mesh decorators on a `@dxf` drawing are an error.

`python bracket.py` now writes the STEP **and** the declared meshes, and heals
any of them that were deleted. No separate export step.

#### Running the model

```bash
python bracket.py
```

Flags ride the script's argv:

| Flag | Effect |
| --- | --- |
| `-o`, `--output PATH` | Override the model's output path for this run. |
| `--force` | Rebuild even when the gate says current. |
| `--mesh-tolerance FLOAT` | Override chord tolerance for this run. |
| `--mesh-angular-tolerance FLOAT` | Override angular tolerance, radians. |
| `--verbose` | Stage timing and full tracebacks on stderr. |
| `--json` | One JSON result line on stdout. |

Two behaviours that differ from v0.4 and will bite:

- **A run always writes the artifact.** In v0.4, `scripts/gen` built only the
  render package unless you passed `--write`. There is no `--write` in v0.5 and
  no way to build "just the package" from a script — running the model produces
  the file.
- **A direct run ends the process.** Decoration raises `SystemExit` with the
  pipeline's exit code, so trailing module code after the decorated function
  does not run. This is true on both the warm and cold paths, deliberately, so
  the two never disagree.
- **Importing a model module never builds.** Composition imports the module and
  calls the function to get the shape:

  ```python
  from widget import widget as build_widget   # importing links; never builds
  ```

  For an expensive child, wrap it with `cadgen.compose.memo` — importing links,
  `memo` caches.

### 3. Move articulation to kinematics + `.anim.js`

v0.4's `.params.js` sidecar — FK scripts, pose functions, demo modes — is gone,
and so is GIF export. v0.5 splits what `.params.js` conflated into three
systems with different lifecycles:

| System | Where it lives | Lifecycle |
| --- | --- | --- |
| Geometry parameters | The model function's signature | Changing one re-runs Python and rebuilds the artifact |
| Kinematics | `kinematics=` on the decorator, pure data | Drives viewer sliders and posed exports; no rebuild, no Python at render time |
| Animation | A plain `.anim.js` module named by `animation=` | Text copied into the sidecar; never invalidates a build |

#### Typed mates

One dict, closed key vocabulary `mates` / `couplings` / `poses` / `at`:

```python
import cadgen
from cadgen import build123d as bd
from cadgen import step

KINEMATICS = {
    "mates": [
        cadgen.revolute("elbow", parent="#upper_arm", child="#forearm",
                        axis="#forearm.pivot_bore", limits=(0, 150)),
        cadgen.slider("extend", parent="#rail", child="#carriage",
                      axis="#rail.f2", limits=(0, 80)),
        cadgen.cylindrical("lead", parent="#housing", child="#screw",
                           axis="#screw.f1",
                           limits={"turn": (0, 3600), "travel": (0, 40)}),
        cadgen.fastened("mount", parent="#carriage", child="#bracket"),
    ],
    "couplings": [cadgen.couple("curl", {"mcp": 50, "pip": 70, "dip": 40})],
    "poses": {"open": {"jaw": 40}, "closed": {"jaw": 0}},
}


@step(out="../STEP/arm.step", kinematics=KINEMATICS, animation="arm.anim.js")
def arm(): ...
```

Rules that catch v0.4 conversions:

- **Authored placement is q=0.** Every DOF's rest value is 0 — the placement
  you built. There is no `default=` on a mate; passing one is an error. A
  presentation pose is a `poses` preset or a bake.
- **Mate kinds** are `revolute` (degrees), `slider` (model units),
  `cylindrical` (sub-DOFs `<name>.turn` and `<name>.travel` about one axis),
  and `fastened` (0-DOF rigid attachment). `fastened` is needed exactly when
  occurrences are *siblings* in the instance tree — a pin that must orbit with
  its carrier. Instance-tree children ride for free.
- **`fastened` mates contribute no DOF.** They are excluded from the DOF list,
  take no `limits`, and take no axis.
- **Limits are required** on every non-`fastened` mate: `(lo, hi)` for
  single-DOF kinds, a `{"turn": ..., "travel": ...}` dict for `cylindrical`.
- **`parent`/`child` are occurrence refs** — `#`-prefixed labels (canonical;
  label parts with `cadgen.label_shape`) or occurrence ids. A ref may name a
  subassembly, which carries every part beneath it.
- **`axis`** is a selector ref (`axis="#forearm.pivot_bore"`) *or* literals
  (`origin=(x,y,z), direction=(x,y,z)`) — never both. Refs resolve once at
  build into world numbers; the viewer does arithmetic, never topology.
- **The mate graph is a tree**: one parent mate per occurrence, no cycles.
  Closed-loop linkages are out of scope by design — they need a solver, and
  cadgen evaluates pure forward kinematics.
- **Couplings gear real mate DOFs**, not other couplings. No chaining.
- **`pose=` does not exist.** The bake point is the dict's own `"at"` key:
  `kinematics={**KINEMATICS, "at": "closed"}`. It takes a preset name or a
  `{dof: value}` dict, and never survives into the sidecar block — the written
  artifact is its own q=0.

#### The `.anim.js` contract

Choreography moves out of Python entirely, into a plain ES module beside the
script:

```js
// arm.anim.js
export const clips = {
  demo: {
    label: "Demo",
    duration: 8,          // seconds
    loop: true,           // default
    update(t, m) {        // called every frame; t in seconds
      m.get("forearm").rotate([0, 0, 1], 120 * (t / 8), [0, 0, 25]);
      m.get("#o1.3.1,o1.3.2").translate([0, 0, 40 * Math.min(t / 2, 1)]);
      m.get("lid").opacity(t < 5 ? 1 : 1 - (t - 5) / 2);
    },
  },
};
```

- `m.get(target)` takes a label (canonical) or occurrence-id refs, comma-listed;
  each id covers its whole subtree. Unknown targets **throw** — a typo never
  silently animates nothing. Labels here match rendered parts only, unlike a
  mate ref; to animate a whole group, name its occurrence id.
- Handles: `.rotate(axis, degrees, origin=[0,0,0])`, `.translate(vec)`,
  `.opacity(0..1)`, `.visible(bool)`. Successive transforms **premultiply**.
- Every frame starts from rest and `update(t)` rebuilds the state — a pure
  function of `t`, so scrub, loop and seek are free. No wall-clock, no state.
- Animation is deliberately ignorant of mates. Animating a jointed part
  re-describes the motion in ratio math. That independence is what guarantees a
  choreography edit can never invalidate a build.
- The declared file must exist. There is no convention discovery; a missing
  `animation=` target fails the build.

**GIF export is deleted.** Snapshot writes PNG stills only, and a `.gif` output
path is refused. Motion review is interactive in the CAD Viewer. For still
evidence of a configuration, render at DOF values:

```bash
cadgen step snapshot STEP/arm.step tmp/open.png --kinematics '{"jaw": 40}'
cadgen step snapshot STEP/arm.step tmp/open.png --kinematics open   # a declared preset
```

#### Annotating a STEP you did not generate

A document with no model script gets kinematics from `cadgen step build IN OUT`,
whose `--kinematics` takes the whole space as inline JSON or a `.json` path, and
whose `--animation` copies a `.js` module's text into OUT's sidecar. `OUT` is
required, and is what distinguishes `build` from the internal `compile`.

### 4. Reshape the project layout

v0.5 is unopinionated in *code* — `out=` puts an artifact anywhere. The
convention below is the recommended shape for a project with more than a couple
of models, and it is what the rest of the tooling's examples assume.

```
<project>/
  src/                    # authored code — the only thing you edit
    README.md             #   model catalog
    plate.py              #   one @step/@dxf model per file
    plate_drawing.py
    plate.anim.js         #   choreography sits beside its model
    lib/
      __init__.py         #   a regular package, never a namespace one
      holes.py
  STEP/                   # raw outputs only (plus source sidecars)
    plate.step
    plate.step.json
    imported/             #   vendor files keep their upstream names
  DXF/  STL/  GLB/  3MF/  # same shape: outputs + imported/
  tmp/                    # scratch
```

- **`imported/` is a subfolder of each format folder** — `STEP/imported/`,
  `DXF/imported/` — not a top-level directory.
- **Every `.py` directly under `src/` is a runnable model.** Shared code goes in
  `src/lib/`. So `ls src/*.py` is the catalog. Imports need no setup, because
  Python puts the script's own directory on `sys.path`.
- **Model script stem = artifact stem = a Python identifier.** `plate.py` →
  `STEP/plate.step`. Part numbers, revisions and spaces go on the artifact via
  `out="../STEP/PN-10432_revB.step"`, never in the stem. Never distinguish two
  files by case alone.
- **Where the project sits:** in a workspace that is more than CAD, put the
  project inside the directory that holds the workspace's models (`models/`, for
  example), never loose at the root. In an empty or bare workspace, the CAD
  project *is* the workspace — lay `src/` and the format folders out at the root.

**Commit policy.** Authored `src/` is always committed. Format folders are not,
with two deliberate exceptions: `imported/` sources, and pinned byte-for-byte
fixtures (`git add -f`).

```gitignore
/STEP/*
!/STEP/imported/
/DXF/*
!/DXF/imported/
/STL/*
!/STL/imported/
/GLB/*
!/GLB/imported/
/3MF/*
!/3MF/imported/
/tmp/
__pycache__/
```

The `*` forms are load-bearing. Ignoring `/STEP/` outright would make the
`imported/` negation dead, because git never descends into an ignored directory.

### 5. Delete v0.4 artifacts, sidecars, and caches

**Do this before debugging anything.** Stale v0.4 droppings produce failures
that point at the wrong thing.

Three kinds of leftovers:

1. **In-tree package directories.** v0.4 kept render packages beside the
   sources in a per-folder `__cadgen__/models/<entry>/` directory. v0.5 has no
   in-tree packages at all. Delete every `__cadgen__` directory in the project:

   ```bash
   find . -type d -name __cadgen__ -prune -print   # look first
   find . -type d -name __cadgen__ -prune -exec rm -rf {} +
   ```

2. **v0.4 sidecars.** Delete `<name>.step.js` / `<name>.stp.js` step-module
   sidecars, every `<name>.params.js`, and any `<name>.step.source.json` left
   over from an intermediate 0.5 snapshot. v0.5 writes exactly one sidecar
   shape, `<name>.step.json` at schema 5, and refuses anything else it finds at
   that name (see the schema section below).

3. **The old cache.** v0.5's store is `~/.cache/cadgen`, content-hash keyed and
   store-primary. Everything in it is derived; deleting any of it costs a
   rebuild, never correctness.

   ```bash
   cadgen cache info                 # per-tier sizes; prints the cache root
   cadgen cache gc --dry-run         # what a sweep would free
   cadgen cache gc                   # sweep entries older than 30 days + dead generations
   cadgen cache gc --all             # delete everything, current generations included
   ```

   `--all` is the clean-slate option for a migration. There is no automatic or
   background GC; this command is the only sweeper.

Also delete the **generated STEP/mesh files themselves** if you want a clean
comparison. They will be rewritten in step 6. Note that a v0.4-generated
`.step` file has cadgen provenance properties (`cadgen:sourcePath`,
`cadgen:sourceHash`) embedded *inside* the STEP text — v0.5 writes none, so an
old artifact is not byte-comparable with a new one even when the geometry is
identical.

### 6. Rebuild

```bash
python src/plate.py
python src/plate_drawing.py
```

Run each model script explicitly. Do not sweep directories — there is no
directory-wide generation in v0.5.

#### Rethink your tolerance flags — do not copy them

This is the easiest thing to get silently wrong.

| | v0.4 | v0.5 |
| --- | --- | --- |
| `--mesh-tolerance` | **absolute** linear deflection, mm; default `0.02` | **relative** chord tolerance, fraction of each component's bounding diagonal; default `1.5e-3` |
| `--mesh-angular-tolerance` | radians; default `0.6` | radians; default `0.35` |

A v0.4 value carried over unchanged means something entirely different. On a
200 mm part, `--mesh-tolerance 0.02` used to mean 0.02 mm; in v0.5 it means
0.02 × 200 = 4 mm — vastly coarser. Drop your old numbers and start from the
new defaults, tightening only where a curved part visibly needs it.

The upside of the change: there is now **one** JS tessellator for both render
and export. The OCCT mesh path is deleted. An exported STL/3MF/GLB is the same
tessellation the viewer draws, watertight, colored, with boundary vertices on
the exact STEP edge curves, and byte-deterministic across repeated exports.
Because the tolerance is relative, it is scale-free: one number behaves the
same on a 5 mm screw and a 2 m frame.

#### Warm builds (optional)

`cadgen daemon status` shows the warm build daemon's workers. You do not need
to start it — the client starts it for you, and `cadgen daemon` takes no
arguments by design. Workers have **project affinity**: a worker is bound to
one project (the directory holding the model script) for its whole life, so two
builds of the same project serialize while different projects fan out in
parallel. That is a correctness property, not just a performance one — all
projects share top-level module names like `lib`, so a worker reused across
projects could build one against another's helpers.

Set `CADGEN_DAEMON=0` to keep builds cold. Nothing in this migration requires
the daemon.

### 7. Verify

**Inspect.** The baseline check, then targeted questions:

```bash
cadgen step inspect refs STEP/plate.step --facts --planes --positioning
cadgen step inspect validate STEP/plate.step
cadgen step inspect measure STEP/plate.step --from '#o1.1' --to '#o1.2'
```

`refs --facts` reports counts and bounds, and its `ok` field covers ref
resolution only — an open shell and an inverted solid both pass it. Use
`validate` for geometry soundness.

**Snapshot.** Mandatory after any visible change:

```bash
cadgen step snapshot STEP/plate.step tmp/review.png
```

The path you name is the path you get, cleared before the render and written
atomically after it, so a missing file is the failure signal — there is never a
stale image to mistake for output. A directory argument gets a generated
timestamped name inside it.

**Verify the geometry did not move.** Content addressing makes "same geometry"
checkable. Compare component content hashes against the pre-migration package:

```bash
python src/plate.py --force
python - <<'EOF'
import json, pathlib
from cadgen.catalog import render_package_dir
d = json.loads((render_package_dir(pathlib.Path("STEP/plate.step")) / "assembly.json").read_text())
print(sorted(e["contentHash"] for e in d["components"].values()))
EOF
```

Identical hash lists mean identical geometry. Written DXF bytes are pure
drawing content with no identity comments, so a rename changes nothing there.

**View.** The CAD Viewer's backend is stdlib-only Python. Launch the bundled
server from the directory to serve — there is no directory flag, the cwd IS
the served directory:

```bash
cd /absolute/path/to/project && python <viewer>/server/main.py --host 127.0.0.1 --json
```

It serves one directory, fixed at start, and reuses a live instance already
serving the same directory at the same version rather than starting a second.
cadgen is a **soft** dependency: importing a foreign STEP spawns a cadgen
build, but viewing works without cadgen installed. Everything renders from
three inputs — the artifact file, its `.step.json` sidecar, and the cache. The
viewer never reads your source and never rebuilds on source changes.

Coupled DOFs get **driven sliders**: when exactly one coupling gears a DOF with
a nonzero ratio, that DOF's Pose slider reads the effective value, is labelled
as driven by the coupling, and dragging it moves the coupling — so sliding one
gear turns the whole train. A DOF geared by two couplings stays independent;
that inverse is underdetermined and the viewer refuses to guess a split.

---

## CLI cross-reference

v0.4's user-facing commands were skill scripts run as `python scripts/<tool>`.
v0.5 has a single console script, `cadgen`, plus running model scripts
directly. Every subcommand is also reachable as `python -m cadgen.cli <verb>`.

| v0.4 | v0.5 |
| --- | --- |
| `python scripts/gen MODEL.step.py` | `python model.py` |
| `python scripts/gen MODEL.step.py --write` | `python model.py` (a run always writes) |
| `python scripts/gen ... --write PATH` | `python model.py -o PATH`, or `out=` on the decorator |
| `python scripts/gen ... --force` | `python model.py --force` |
| `python scripts/gen ... --json` / `--verbose` | `python model.py --json` / `--verbose` |
| `python scripts/gen ... --mesh-tolerance` | same flag — **but the units changed**, see step 6 |
| `python scripts/export TARGET --stl/--3mf/--glb` | `@stl`/`@threemf`/`@glb` on the model, or `cadgen stl\|3mf\|glb build DOC [OUT]` |
| `python scripts/inspect refs\|measure\|align\|frame\|diff\|validate` | `cadgen step inspect <inspection> ...` |
| `python scripts/snapshot ...` | `cadgen step snapshot`, `cadgen stl\|3mf\|glb snapshot`, `cadgen dxf snapshot`, `cadgen urdf\|sdf snapshot`, or polymorphic `cadgen snapshot` |
| `python scripts/artifact ...` | `cadgen step compile` (internal; every door compiles on demand) |
| `cadgen-step-artifact` | `cadgen step compile` |
| `python skills/cad/scripts/cadgen_daemon ...` | `cadgen daemon`, `cadgen daemon status` |
| DXF: `python skills/dxf/scripts/gen ...` | `python drawing.py` |
| — | `cadgen step build IN OUT` (re-emit/annotate a document) |
| — | `cadgen cache info` / `cadgen cache gc` |
| — | `cadgen doctor` |

The full v0.5 command set:

```
step build      write a new STEP from one, with kinematics
step compile    make a STEP's render package current (internal)
step inspect    inspect selector references in a STEP
step snapshot   render a STEP model to an image
stl|3mf|glb build      write a model's mesh output(s)
stl|3mf|glb snapshot   render a mesh to an image
dxf snapshot    render a DXF to an image
urdf|sdf|srdf validate  validate a robot description
urdf|sdf snapshot       render a robot description to an image
snapshot        render any supported input to an image
cache           inspect or gc the user-level caches (info/gc)
doctor          print installed cadgen and verify a skill's pin
daemon          run the warm build daemon
daemon status   show the warm daemon's workers
```

Notable absences: there is no `cadgen gen`, no `cadgen export`, and no
`cadgen dxf build` — a drawing's file *is* the product, made by running its
script.

### Doors take documents; scripts are run

Every `cadgen` verb above takes a `.step` / `.stl` / `.dxf` **file**. Hand one a
`.py` and it refuses by name. This is the inverse of v0.4, where `scripts/gen`,
`scripts/export` and `scripts/inspect` all accepted a `.step.py` generator and
would build it for you. In v0.5:

- `python <script>` is the only source door.
- A document that has drifted from its script is **refused**, not silently
  rebuilt. Rerun the script.
- Nothing needs a separate cache or import step — each door makes what it needs
  on demand.

## Selector refs

**Good news: the ref grammar only widened.** No ref a v0.4 project wrote stops
parsing in v0.5. Unrecognized text still falls through as opaque rather than
raising. You do not have to rewrite refs — this section is here so you know what
is now *available*, and so two refs that used to error and now work do not
surprise you.

A ref is one token: `[<file-prefix>]#<selector>[,<selector>...]`. No spaces —
the token stops at whitespace.

| Form | Spelling |
| --- | --- |
| Occurrence | `#o1`, `#o1.2`, `#o1.2.3` |
| Occurrence + entity | `#o1.12.f19`, `#o1.2.e7`, `#o1.2.s3`, `#o1.2.v4` |
| Bare entity | `#f45`, `#e12`, `#s2`, `#v4` (single-occurrence documents, or inheriting context in a comma list) |
| Label | `#eye_shank`, `#mounting_eye:lower` |
| Label + entity | `#servo_end_plate.f45` |
| Numbered alias for a duplicate label | `#cast_rim:5spoke_1`, `#cast_rim:5spoke_2` |
| Mate | `#m1` |
| Whole file | `mounting_plate.stl#` |

Entity kinds are exactly `s` (shape), `f` (face), `e` (edge), `v` (vertex).

> A label ref is `#<the build123d part name>.<kind><n>` — the literal word
> `label` never appears. `#servo_end_plate.f45` names face 45 of the part
> labelled `servo_end_plate`.

Points worth knowing:

- **Comma lists inherit context.** Whichever naming scheme came last seeds the
  bare entities after it: `#o1.2,f3,f4` means `o1.2`, `o1.2.f3`, `o1.2.f4`.
- **Duplicate labels never resolve bare.** A label matching two occurrences
  raises and lists the numbered aliases (`_1`, `_2`, in occurrence-tree order)
  to use instead.
- **Numeric forms win.** A part named `f12` or `o1.4` gets no alias and is
  reachable only by its numeric id.
- **Occurrence-group refs have no special syntax.** A group is just an
  occurrence ref naming an interior node of the instance tree — `#o1.4`. This
  is the one behavioural change: in v0.4 an interior node was an error
  ("unknown part/subassembly occurrence selector"); in v0.5 it expands to its
  subtree leaves in tree order. Same spelling, previously rejected, now works.
  An unknown group ref raises with a near-miss hint naming the deepest real
  ancestor and its children.

**File prefixes are a guard, not a resolver.** An empty prefix (`#o1.2`) is
accepted everywhere unconditionally — the file is whatever the separate target
argument says. A *non-empty* prefix must name the file the command was already
pointed at, or it is an error; it never selects a different file. And you cannot
fold the file into the target: a target argument containing `#` is refused,
because selector refs require an explicit target argument.

```bash
cadgen step inspect refs STEP/bracket.step '#o1.2.f19'      # always fine
cadgen step inspect refs STEP/bracket.step 'bracket#o1.2'   # fine: names the target
cadgen step inspect refs STEP/bracket.step 'other#o1.2'     # error
```

**What is emitted.** The toolchain accepts many spellings and prints exactly
one: numeric, leading `#`, no file prefix. Labels are resolved to numeric ids
before any selector reaches a render job or JSON output; `inspect --detail`
reports a label only as a separate `labelRef` field. On a single-occurrence
document the occurrence prefix is dropped from the display form (`#f45`), while
an assembly prints the full path (`#o1.12.f19`). The CAD Viewer is the one
place that emits file-prefixed refs.

**Surfaces differ slightly.** `inspect refs`/`frame`/`measure`/`align` require
the leading `#`; `inspect validate`/`interfere --refs` and snapshot's
`--focus`/`--hide` accept it optionally. `inspect diff` takes no refs at all.
Snapshot selection accepts **occurrence refs only** — a face or edge selector is
refused there.

**Stop writing `.step.py` targets.** `path/to/entry.step.py` was a documented
target form in v0.4 and is no longer part of the contract. Path-shaped targets
still often resolve to the sibling `.step` in practice, so this may not fail
loudly — treat it as something to clean up rather than something that will
announce itself.

## Snapshot job schema

If your v0.4 project drove snapshots from job JSON, the schema changed.

**Top-level `focus`, `hide` and `refs` are retired.** They live inside a nested
`selection` object now:

```json
// before (0.4)                    // after (0.5)
{ "input": "arm.step",             { "input": "arm.step",
  "focus": ["#o1.2"],                "selection": { "focus": ["#o1.2"] },
  "params": { "jaw": 40 },           "kinematics": { "jaw": 40 },
  "outputs": ["out.png"] }           "outputs": ["out.png"] }
```

The accepted job keys are: `input` (required), `mode`, `outputs`, `theme`,
`display`, `render`, `camera`, `selection`, `kinematics`, `animation`
(`{"clip": name, "time": seconds}` — one still frame of a STEP model's clip,
layered over `kinematics`), `jointValues`, `sizeProfile`, `width`, `height`,
`scale`, `sceneScale`, `debug`, `timeoutSeconds`.

Also removed: the `params` key (it is `kinematics` now — `params` is reserved
and rejected), and `workspaceRoot` / `rootDir` (pass a relative or absolute
`input` path instead). `.gif` output paths are refused.

Other behaviour worth knowing:

- `mode` is `view` (default), `section` or `list`. Mesh inputs allow only
  `view` and `list`.
- `selection.focus`/`selection.refs` and `selection.hide` are mutually
  exclusive within one job. Selection requires STEP topology, so mesh, robot
  and DXF inputs refuse it.
- `outputs` entries are a bare string or an object with `path`, `width`,
  `height`, `sizeProfile`, `camera`, `label`, `viewLabel`, `dataUrl`, `text`.
- A packet may be a single job object, a bare array of jobs, or
  `{"jobs": [...]}`.
- `--job PATH` reads a JSON file; `--job -` reads stdin. `--job` does **not**
  accept inline JSON. The rich option flags (`--camera`, `--theme`,
  `--display`, `--kinematics`, `--animation`, `--joint-values`) each take a
  name, inline JSON, or a path; `--time SECONDS` is the moment for
  `--animation` and is refused without it.

### Themes and display are two separate options

v0.5 splits what v0.4 mixed, mirroring the viewer's two tabs:

- **`--theme`** selects the visual world: `materials`, `background`, `floor`,
  `environment`, `lighting`, `colorMode`, `projection`, `modeColors`. Ids:
  `workbench-light`, `workbench-dark`, `cinematic`, `vibrant`, `blue`, `pink`,
  `clay-sunrise`, `terminal`, plus the render-only `snapshot`.
- **`--display`** controls how geometry is drawn: `projection`, `mode`, `clip`,
  `exploded`, `edges`.

The snapshot default theme is `snapshot` — Workbench Light with the ground grid
and origin axis removed, because in a still image those read as geometry rather
than as orientation. Pass `--theme workbench-light` for the viewer's own look.
Projection is a theme trait honoured by every format, so a snapshot frames the
way the viewport does.

Display `mode` collapses a large alias table to seven canonical values:
`solid`, `rendered`, `transparent`, `hidden_edges`, `hidden_lines_removed`,
`unshaded`, `wireframe`. The two topology modes (`hidden_edges`,
`hidden_lines_removed`) need CAD topology, so mesh inputs refuse them.

Mesh, DXF and robot snapshot doors do not *have* `--focus`, `--hide`,
`--display`, `--kinematics` or `--mode section` — a mesh has no occurrences,
CAD edges or kinematics, so those options are absent from the command rather
than refused by it.

## Artifact and schema reference

### What lands where

| Thing | v0.4 | v0.5 |
| --- | --- | --- |
| Model source | `<name>.step.py` / `<name>.dxf.py` with `gen_step()`/`gen_dxf()` | `<name>.py` with one `@step`/`@dxf` function |
| Primary artifact | Written only with `--write` | Always written by a run; sibling `<stem>.step` or `out=` |
| Render package | In-tree `__cadgen__/models/<entry>/` | `~/.cache/cadgen/packages/<stepHash>-v<N>/` |
| Declarations sidecar | `<name>.step.js` (a JS module) | `<name>.step.json`, schema 5, JSON |
| Pose/FK script | `<name>.params.js` | `kinematics=` on the decorator (data, in the sidecar) |
| Animation | `.params.js` demo modes; GIF export | `<name>.anim.js`, text copied into the sidecar; PNG stills only |
| Provenance | Embedded in the STEP text as `cadgen:sourcePath` / `cadgen:sourceHash` | `~/.cache/cadgen/records/<key>.source.json` |
| Mesh outputs | `scripts/export --stl/--3mf/--glb` | `@stl`/`@threemf`/`@glb` decorators, or the format doors |

### The sidecar: `<name>.step.json`, schema 5

A sidecar carries **declarations only**, and exists **only when the model needs
one** — that is, when it declares kinematics, animation, or mesh exports. A
plain model that is geometry and nothing else writes no sidecar at all.

Its complete section list:

```
schemaVersion   5
kinematics      typed mates with axes resolved to world numbers, couplings, pose presets
animation       the .anim.js choreography TEXT, copied
meshExports     what the @stl/@glb/@threemf declarations resolved to
```

That is the whole file. There is **no** `sourceKind`, `sourcePath`,
`sourceHash`, `sourceClosure`, or timestamp — nothing source-derived-as-identity.
That is a design law: a generated file carries no tie back to its source. The
sidecar sits beside the artifact because declarations cannot be re-derived from
the STEP bytes; evicting the store must never lose your kinematics.

A model that *drops* its kinematics loses the file — the writer removes a
sidecar that is no longer warranted.

**A v0.4 sidecar is not read.** A sidecar that is present must declare schema 5;
anything else is an error naming the schema found, the schema expected, and the
fix — rebuild the model, or re-annotate the document with `cadgen step build`.
A *missing* sidecar is fine and means "an import, or a plain model". So the
migration for sidecars is exactly: **delete the old ones and rebuild from
source.** There is nothing to convert by hand.

### Provenance moved to the records tier

Everything source-derived — `sourceKind`, `sourcePath`, `sourceHash`,
`sourceClosureFiles`, `sourceClosureHash`, `annotationHash`, `generatedAt` —
lives in an evictable record:

```
~/.cache/cadgen/records/<sha256(resolved artifact path)[:24]>.source.json
```

Every generated build writes one; every freshness gate reads one. It exists so
a *plain* model with no sidecar still no-ops on rerun and is still refused by
the doors when it drifts from its script. Eviction costs one rebuild, never
correctness — an evicted record simply reads as an import until the next build
re-records it. Imports write neither a sidecar nor a record.

### Storage layout

The cache root, one rule, honoured by both Python and JS:

1. `$CADGEN_CACHE_DIR` if set.
2. `$XDG_CACHE_HOME/cadgen` on POSIX if set; `%LOCALAPPDATA%\cadgen` on Windows
   if set.
3. `~/.cache/cadgen` otherwise.

| Tier | Contents |
| --- | --- |
| `packages/` | One self-contained render package per document, keyed by the document's content hash |
| `components/` | Exact-geometry component store; components hardlink in from packages |
| `opmemo/` | Kernel-op memo, one subdirectory per salt generation |
| `meshes/` | Shared tessellation cache |
| `records/` | Per-model provenance/freshness records |

Everything under the root is content-addressed and best-effort. Deleting any
entry, or the whole root, costs a rebuild and never correctness.

## Troubleshooting a half-migrated project

Remember: these errors describe the v0.5 contract. None of them will mention
0.4. Below is what each one means *for a migration*.

**"declares no CAD model" / "decorate one function with `@step` or `@dxf`"**
You ran a file that still has a bare `gen_step()`/`gen_dxf()` function, or you
renamed the file but forgot the decorator. cadgen no longer detects the magic
function names at all — they are ordinary functions to it. → Step 2.

**"defines more than one CAD model"**
The file has two decorated functions. One model per file is a hard rule, because
entry identity is keyed by the source file. → Split it into two files.

**"parameters must all have defaults"**
A converted `gen_step()` gained parameters without defaults. The pipeline calls
the model function with no arguments. → Give every parameter a default.

**"unsupported sidecar schema … (expected 5)"**
A v0.4 sidecar (or an intermediate `.step.source.json`) is still sitting next to
the artifact. Nothing reads it. → Delete it and rebuild. Step 5.

**Unexpected keyword argument on a decorator**
You passed a v0.4-era or intermediate name — `write=` instead of `out=`,
`pose=` instead of the kinematics dict's `"at"` key, `params=`, or `kinematics=`
/ `animation=` on `@dxf`. The decorators reject unknown kwargs outright rather
than ignoring them. → Check the decorator argument table in step 2.

**"kinematics has unknown key(s) … the vocabulary is closed"**
Your kinematics dict has something other than `mates`, `couplings`, `poses`,
`at`. Note `animation` is its own `@step` kwarg, never a kinematics key. → Step 3.

**"`default=` was dropped"**
A mate carried a rest value. Zero is always the artifact as written. → Declare a
`poses` preset, or bake with `{..., "at": <preset>}`.

**Unrecognized argument on a `cadgen` command**
A retired snapshot flag. `--input`/`-i` and `--output`/`-o` became the two
positionals `TARGET OUT`; `--params` became `--kinematics`; `--params-path` went
away with the `.params.js` mechanism. These now fail as ordinary unknown
arguments with no migration hint. → Consult `cadgen <verb> --help`, which is
always the current interface.

**Unknown job key, or "move it into `selection`"**
Top-level `focus`/`hide`/`refs`, or `params`, or `workspaceRoot`/`rootDir` in a
snapshot job. → See the snapshot job schema section.

**A `.py` handed to a door is refused by name**
Correct and intended. Doors take documents. → `python <script>` first, then run
the door on the file it wrote.

**"has drifted from its script"**
The `.step` on disk no longer matches what its model script would produce. v0.5
refuses rather than silently rebuilding under you. → Rerun `python <script>`.

**A model reports itself current after you replaced a vendor STEP**
You are still using `build123d.import_step`, which reads the file as data and
announces nothing to the freshness gate. → Switch to `cadgen.read_step`, which
records the file's path and content hash into the model's closure. Step 1.

**Meshes came out far coarser (or finer) than in v0.4**
You carried a tolerance number across. `--mesh-tolerance` is relative now. →
Step 6.

**A model builds but the trailing code in the file never runs**
Expected. A direct run ends the process at decoration with the pipeline's exit
code. → Move the work above the decorated function, or into it.

**`sys.path` manipulation inside the model function has no effect**
The pipeline restores `sys.path` after loading the module. → Import at module
top; only *call* the imported code inside the function.

**Two builds of the same project seem to serialize**
Daemon worker affinity: one worker per project, for correctness — projects share
top-level module names like `lib`. → Expected. `CADGEN_DAEMON=0` disables warm
builds entirely.

## Migration complete when

- [ ] Every model is a plain `.py` with exactly one `@step`/`@dxf` function.
- [ ] No `gen_step`/`gen_dxf` remains; no `.step.py`/`.dxf.py` filenames remain.
- [ ] All build123d access goes through `from cadgen import build123d as bd`.
- [ ] All vendor STEP reads go through `cadgen.read_step`.
- [ ] No `__cadgen__` directory, `.step.js`, `.params.js`, or
      `.step.source.json` remains anywhere in the project.
- [ ] Every model script runs clean, and a second run is a fast no-op.
- [ ] `cadgen step inspect validate` passes on each primary STEP.
- [ ] A snapshot of each primary STEP has been rendered and reviewed.
- [ ] Tolerance flags have been re-derived from the new relative defaults, not
      copied.
