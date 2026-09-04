# Migrating a CAD project from cadgen 0.4 to 0.5

This is a hand-migration playbook. Work through it top to bottom with a v0.4
project open and you will end with a working v0.5 project. Nothing else is
required — no other document, no tool.

## Read this first: there is no compatibility layer

v0.5 ships **zero** backwards compatibility. Deliberately:

- No shims, no aliases, no deprecated keyword arguments.
- No codemod. Nothing rewrites your sources.
- **No teaching errors.** A v0.5 tool handed a v0.4-shaped call reports only
  what its *current* contract requires. A retired flag is an unrecognized
  argument. A retired job key is an unknown key. A `gen_step()` file is a file
  that declares no model. None of those errors will mention 0.4, migration, or
  what the thing used to be called.

So: when something fails during this migration, the error tells you what v0.5
wants, not what you did. Read it as a spec, not as a diagnosis. That is the
design — every entry point teaches exactly one contract, the current one.

The corollary is that a **half-migrated project fails confusingly**. A model
script converted to `@step` whose stale v0.4 sidecar is still on disk fails at
the sidecar, not at the script. Do the deletion step (step 5) before you start
debugging anything.

### The one-paragraph summary

A v0.5 **model** is a plain `.py` file that decorates one **parameterless**
function with `@step`, `@dxf`, or a mesh decorator, and you build it by
**calling it**: the file ends with `if __name__ == "__main__": model()` and you
run `python model.py`. There is no generation CLI. A model's outputs are exactly
what its decorators declare — a STEP, a DXF, an STL, any mix — written where
`out=` says; everything derived lands in a content-addressed **store** under
`~/.cache/cadgen`. An assembly is a model that imports its part models and calls
them; the children build in parallel and the parent **links** their results.
Generated files carry no trace of their source.

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
   cadgen doctor            # prints the installed cadgen and checks a pin
   ```

   v0.4 installed one console script, `cadgen-step-artifact`. v0.5 installs
   `cadgen`. If `cadgen` is missing, the install did not take.

3. **Commit your work.** This migration deletes generated files.

4. **Keep a v0.4 build around if you care about geometry equivalence.** Note
   the occurrence, face and edge counts and the bounds of each primary STEP
   (`inspect refs --facts`, see step 7) so you can compare after. If you do not
   care, skip it — snapshots are usually enough.

## Migration checklist

Do these in order. Later steps assume earlier ones.

- [ ] 1. Rewrite imports
- [ ] 2. Convert the generator into a model
- [ ] 3. Convert composition: children are models you call
- [ ] 4. Move articulation to kinematics + `.anim.js`
- [ ] 5. Reshape the project layout, then delete v0.4 leftovers
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
body must stay cheap so the call can run the freshness gate and hand off to the
warm daemon *before* anything pays the ~2.5 s kernel import. A current model's
re-run then never wakes the kernel at all.

Raw `import build123d` still works and is not an error — it just costs ~2.5 s
on every re-run, and the call prints a hint on stderr when it sees the kernel
already imported. The same goes for `bd.<anything>` in a module-level constant
or a default argument: each one resolves the attribute at import.

Use **attribute style**. `from cadgen.build123d import Box` works but is eager:
a from-import must bind the object, which forces the real import immediately.

**Imports: module top by preference, not by rule.** A model runs like
`python script.py` — its folder stays on `sys.path` for the whole build — so an
import inside the body or a helper resolves the same way, and the file it loads
is hashed when it executes, so it is tracked either way. Module-top imports keep
the graph visible up front; that is the only reason to prefer them.

**Reading a vendor STEP.** Use `cadgen.read_step`, never
`build123d.import_step`:

```python
# before (0.4)                              # after (0.5)
from build123d import import_step           from cadgen import read_step, step

motor = import_step("imported/motor.step")  motor = read_step(_HERE / "imported" / "motor.step")
```

The returned shape is identical (the root itself, not a wrapper, with
per-occurrence and prototype STEP colors applied), and it is served from the
store, so a warm read costs tens of milliseconds instead of a full text-STEP
re-parse. `read_step` also **declares the file**: its content hash joins the
model's closure, so replacing the vendor STEP makes the model stale. A file
read as data by `import_step` announces nothing, and in v0.4 such a model kept
reporting itself current.

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
selection + flatten + union + optional kerf offset. It selects the planar faces
at ONE coordinate, so it unfolds a flat plate but **not a folded bracket**.
Unfolding a multi-panel part is the caller's job: select each panel's faces with
`flatten.planar_faces(...)` per plane, flatten each with its own placement, and
fuse with `flatten.union_faces(...)`. A worked multi-plane example lives in the
dxf skill's `references/generator-templates.md`.

### 2. Convert the generator into a model

This is the structural change. A v0.4 source had a magic `gen_step()` /
`gen_dxf()` function and usually a `<name>.step.py` / `<name>.dxf.py` filename.
v0.5 reads neither.

```python
# bracket.step.py (0.4)              # bracket.py (0.5)
from build123d import Box            from cadgen import build123d as bd
                                     from cadgen import step

def gen_step():                      @step(out="../STEP/bracket.step")
    return Box(10, 10, 10)           def bracket():
                                         return bd.Box(10, 10, 10)


                                     if __name__ == "__main__":
                                         bracket()
```

Mechanically:

1. **Rename the file to a plain `.py`.** `bracket.step.py` → `bracket.py`.
2. **Name the function after the file and decorate it** with `@step` (or
   `@dxf`, or a mesh decorator). Both bare (`@step`) and configured
   (`@step(...)`) forms work.
3. **Remove every parameter.** A model takes **no arguments** — a parameter of
   any kind, defaulted or not, is rejected. Parametric geometry is a plain
   factory function the model calls; another configuration is another model
   (another file). See "Mirrored parts" in step 3.
4. **Return the bare shape.** The v0.4 envelope dict (`{"shape": ..., "stl":
   ...}`) is gone; a `@step` function returns one build123d `Shape`. Mesh
   outputs are decorators (below).
5. **End the file with the call.** `if __name__ == "__main__": bracket()`.
   Decorating no longer runs anything; **calling the model is the build.**
   Without the guard, `python bracket.py` does nothing.
6. **One model per file.** A source defining two must be split. A model's
   identity — its record, its freshness, its worker — is the script path.

#### Decorator arguments

`@step` takes, all keyword-only:

| Argument | Meaning |
| --- | --- |
| `out=` | Output path. **Script-relative** (see the path note below). Default: sibling `<stem>.step`. |
| `kind=` | `"part"` or `"assembly"`. Inferred from the return when omitted. |
| `kinematics=` | The typed-mates dict. See step 4. |
| `animation=` | Name of a `.anim.js` choreography module beside the script. See step 4. |
| `mesh_tolerance=` | Chord tolerance for the tree's tessellation. Relative — see step 6. |
| `mesh_angular_tolerance=` | Angular tolerance, radians. |

`@dxf` takes **only `out=`**. It has no `kind=` (a drawing is 2D geometry), no
`kinematics=` and no `animation=`; passing any of them is an error.

Two decorator arguments are read **statically**, before the module runs, and
must be literals: `out=` (a string) and the two tolerances (numbers) — plus
`kind=` when you write it. A tolerance therefore cannot come from a constants
module; write the number in each decorator (a project README can name the
shared value). `kinematics=` and `animation=` are ordinary Python evaluated
when the module loads — a dict built at import, or loaded from a file, is fine
and is what the kinematics reference shows. Unknown keyword arguments are
rejected outright on every decorator.

#### The one path-semantics exception

Every CLI and function path argument in v0.5 is **native**: a relative path
resolves against the process's current working directory, an absolute path
works anywhere, and `~` expands. v0.4's cwd-gated and repo-gated behaviours are
gone.

The single deliberate exception is the **decorator's `out=`** — on `@step`,
`@dxf`, `@stl`, `@glb` and `@threemf` alike — which resolves relative to the
**script**. That is what makes a project relocatable: the declaration travels
with the model and produces the same layout whatever directory you run from.
`animation=` is likewise a name beside the script. There is **no per-run output
override**: `-o`/`--output` does not exist. Where a file lands is a property of
the model, not of a run.

```python
@step(out="../STEP/bracket.step")   # ../STEP relative to THIS FILE
def bracket(): ...
```

#### What the function returns

A `@step` function returns a build123d `Shape` — nothing else. A `@dxf` function
returns build123d 2D geometry: a bare shape goes to the `CUT` layer, or a
`{layer: shape}` dict gives named layers (`CUT` / `ENGRAVE` / `SCORE`). The
engine writes the file; you never call an exporter.

#### Mesh exports are decorators — and STEP is optional

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


if __name__ == "__main__":
    bracket()
```

- The 3MF decorator is spelled `@threemf` (identifiers cannot start with a
  digit); the CLI door is `3mf`.
- Stacking order is behaviour-neutral.
- Bare (`@glb`) means the sibling default. Declare the same format more than
  once at *distinct* `out=` targets for draft/print variants; two bare
  declarations of one format collide, as do two identical `out=` targets.
- `@stl`/`@glb`/`@threemf` accept `out=`, `mesh_tolerance=`,
  `mesh_angular_tolerance=` and their own `kinematics=`. They do **not** accept
  `animation=` — mesh exports are static bakes.
- Mesh decorators on a `@dxf` drawing are an error.
- **A model needs no `@step` at all.** `@stl`/`@glb`/`@threemf` alone make a
  **mesh-only model**: same tree, same record, same freshness; its outputs are
  the meshes. A model's outputs are exactly what its decorators declare.

`python bracket.py` writes every declared output and heals any that were
deleted. No separate export step.

#### Running the model

```bash
python bracket.py
```

Flags ride the script's argv:

| Flag | Effect |
| --- | --- |
| `--force` | Rebuild even when the gate says current. |
| `--mesh-tolerance FLOAT` | Override chord tolerance for this run. |
| `--mesh-angular-tolerance FLOAT` | Override angular tolerance, radians. |
| `--verbose` | Stage timing and full tracebacks on stderr. |
| `--json` | One JSON result line on stdout. |

There is no `-o`, no `--write`, no `--lock-timeout`.

What a run says: **stdout** carries one result line — `built STEP/bracket.step`
or `current STEP/bracket.step` (a mesh-only model prints its tree hash; a
drawing prints its `.dxf`). With `--json` that line carries `outcome`
(`built` | `current`), `document` (the written STEP's path, `null` for a
mesh-only model) and `tree` (the result's hash in the store). `packagePath` is
gone. **stderr** carries the build tree — every model
the run touched, collapsing as each finishes — and the `[cadgen] wrote ...`
lines.

Behaviours that differ from v0.4 and will bite:

- **A run always writes its outputs.** There is no `--write`, and no way to
  build "just the render package": running the model produces the files.
- **Importing a model module never builds.** Only the call does. Inside another
  model's body, a call composes (next step); at top level, it builds.
- **Every build is parallel.** Children build on a pool of warm workers; a
  build never waits on or cancels another build, and two runs of the same model
  can overlap — the store's publish rule decides what lands.

### 3. Convert composition: children are models you call

In v0.4 an assembly built its parts inline, through `lib/` helpers, or with
`cadgen.compose.memo`. In v0.5 **a child is a model**: a sibling file with its
own decorator and outputs. The parent imports it and **calls** it:

```python
# frame.py
from cadgen import build123d as bd
from cadgen import step

from plate import plate          # importing links; never builds
from standoff import standoff


@step(out="../STEP/frame.step")
def frame():
    p = plate()                                  # submits plate's build, returns at once
    left = bd.Pos(-30, 0, 5) * standoff()        # placements are deferred too
    right = bd.Pos(30, 0, 5) * standoff()        # a second call: same result, one build
    return bd.Compound(children=[p, left, right], label="frame")


if __name__ == "__main__":
    frame()
```

- **`compose.memo` is deleted.** `cadgen.compose` does not exist. Every
  `memo(helper, ...)` call site becomes a model file for that child, imported
  and called. The cache it provided is the store: a current child is served
  from its tree in milliseconds.
- **Calls are lazy and parallel.** Inside a body a call submits the child's
  build to the pool and returns a compound whose geometry is read on first use;
  `Pos * child`, `Rot * child`, `Location * child`, `.moved()`, `.label` and
  `.color` are deferred. Anything else forces it. Children therefore build in
  parallel, and the parent **links** each child's tree instead of copying its
  geometry — an intact child costs the parent no components.
- **Place with `Pos/Rot/Location *` or `.moved(loc)`, never `.located(loc)`.**
  `located()` deep-copies the geometry, which turns a link into the parent's
  own components (still correct, just no longer shared).
- **A rebuilt part does not update its assemblies until they are rebuilt.**
  `python src/plate.py` publishes plate's new tree; `frame` still pins the old
  one and reads as stale until `python src/frame.py` runs. Pull semantics.
  `cadgen store why src/frame.py` shows the pinned-vs-current pair.
- **Models by result, constants by value, functions by file.** Importing a
  sibling's *model* is a result edge (its tree hash); importing a *constant*
  from a model file is tracked by value; importing a *function* or any name
  from a non-model file (`lib/`) puts that file in the closure — any edit
  rebuilds. Shared constants can live in a model file or in `lib/`.
- **Mirrored parts are their own model.** STEP cannot express a reflection, so
  a right-hand part built by mirroring a left-hand model becomes the parent's
  own geometry. Write a factory in `lib/` and two one-line models:

  ```python
  # lib/bracket_shape.py                 # bracket_left.py            # bracket_right.py
  def build(side: str):                  @step(out="../STEP/bracket_left.step")
      sign = 1 if side == "left" else -1 def bracket_left():
      ...                                    return bracket_shape.build("left")
  ```

- **Sub-assemblies are models** with their own file and outputs; a
  `lib/*.build()` helper that assembled a system becomes `src/<system>.py`.
- **Sidecar boundary.** A child's kinematics, animation and mesh declarations
  belong to that child alone. A parent receives geometry (tree, labels, colors,
  placements) and nothing else; **mates never propagate up**. The v0.4
  `assembly_mates` promotion plumbing is deleted, and so is
  `AssemblyHelper.relations`.
- **Dynamic imports** (`__import__`, `importlib`, and loading a sibling model
  file by path with `importlib.util.spec_from_file_location`) of model modules
  are not tracked. Import children explicitly. Two v0.4 habits hide here: a
  script that loaded a sibling model file **to read one constant** becomes
  `from sibling import CONSTANT` (tracked by value); a script that loaded a
  sibling model module **to rebuild it under different constants** (re-exec,
  environment variables, monkeypatched globals) becomes a factory in `lib/`
  that takes those values as arguments, called by two ordinary models.

### 4. Move articulation to kinematics + `.anim.js`

v0.4's `.params.js` sidecar — FK scripts, pose functions, demo modes — is gone,
and so is GIF export. v0.5 splits what `.params.js` conflated into three
systems with different lifecycles:

| System | Where it lives | Lifecycle |
| --- | --- | --- |
| Geometry | The model function's body and the factories it calls | Changing one rebuilds the model |
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
- **`fastened` mates contribute no DOF.** They take no `limits` and no axis.
- **Limits are required** on every non-`fastened` mate: `(lo, hi)` for
  single-DOF kinds, a `{"turn": ..., "travel": ...}` dict for `cylindrical`.
- **`parent`/`child` are occurrence refs** — `#`-prefixed labels (canonical;
  label parts with `cadgen.label_shape`) or occurrence ids. A ref may name a
  subassembly, which carries every part beneath it.
- **`axis`** is a selector ref (`axis="#forearm.pivot_bore"`) *or* literals
  (`origin=(x,y,z), direction=(x,y,z)`) — never both. Refs resolve once at
  build into world numbers; the viewer does arithmetic, never topology.
- **The mate graph is a tree**: one parent mate per occurrence, no cycles.
  Closed-loop linkages are out of scope by design.
- **Couplings gear real mate DOFs**, not other couplings. No chaining.
- **`pose=` does not exist.** The bake point is the dict's own `"at"` key:
  `kinematics={**KINEMATICS, "at": "closed"}`. It takes a preset name or a
  `{dof: value}` dict, and never survives into the sidecar block — the written
  artifact is its own q=0.
- **Mates stay with the model that declares them.** A parent that links an
  articulated child gets its geometry, not its mates (step 3).

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
  silently animates nothing.
- Handles: `.rotate(axis, degrees, origin=[0,0,0])`, `.translate(vec)`,
  `.opacity(0..1)`, `.visible(bool)`. Successive transforms **premultiply**.
- Every frame starts from rest and `update(t)` rebuilds the state — a pure
  function of `t`, so scrub, loop and seek are free. No wall-clock, no state.
- Animation is deliberately ignorant of mates. That independence is what
  guarantees a choreography edit can never invalidate a build.
- The declared file must exist. A missing `animation=` target fails the build.

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
required and is never `IN`. To make an import a first-class model instead, wrap
it: a `@step` whose body is `return read_step(...)` gives the vendor file a
record, a tree and a place in your assemblies.

### 5. Reshape the project layout, then delete v0.4 leftovers

v0.5 is unopinionated in *code* — `out=` puts an artifact anywhere. The
convention below is what the tooling's examples assume.

```
<project>/
  src/                    # authored code — the only thing you edit
    README.md             #   model catalog
    plate.py              #   one model per file
    plate_drawing.py
    frame.py              #   an assembly: calls plate() and standoff()
    plate.anim.js         #   choreography sits beside its model
    lib/
      __init__.py         #   a regular package, never a namespace one
      holes.py            #   helpers, factories, shared constants
  STEP/                   # raw outputs only (plus source sidecars)
    plate.step
    plate.step.json
    imported/             #   vendor files keep their upstream names
  DXF/  STL/  GLB/  3MF/  # same shape: outputs + imported/
  tmp/                    # scratch
```

- **`imported/` is a subfolder of each format folder**, not a top-level
  directory.
- **Every `.py` directly under `src/` is a model.** Shared code goes in
  `src/lib/`. So `ls src/*.py` is the catalog. A model may share its stem with
  the `lib/` module it wraps — alias the import.
- **Model script stem = artifact stem = a Python identifier.** Part numbers,
  revisions and spaces go on the artifact via `out=`, never in the stem.
- **Build a project with a per-script loop.** There is no Makefile, no
  directory sweep and no `cadgen build`: `for m in src/*.py; do python $m;
  done`, or run the root assembly, which pulls everything beneath it.

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

**Now delete the v0.4 leftovers — before debugging anything.** Stale droppings
produce failures that point at the wrong thing.

1. **In-tree package directories.** v0.4 kept render packages beside the
   sources in a per-folder `__cadgen__/models/<entry>/` directory. v0.5 keeps
   nothing in the tree:

   ```bash
   find . -type d -name __cadgen__ -prune -print   # look first
   find . -type d -name __cadgen__ -prune -exec rm -rf {} +
   ```

2. **v0.4 sidecars.** Delete `<name>.step.js` / `<name>.stp.js` step-module
   sidecars, every `<name>.params.js`, and any `<name>.step.source.json` left
   over from an intermediate 0.5 snapshot. v0.5 writes exactly one sidecar
   shape, `<name>.step.json` at schema 5, and refuses anything else at that
   name (see the schema section below).

3. **The old cache.** v0.4's `~/.cache/cadgen` layout (`packages/`,
   `components/`, `opmemo/`, `records/`) is simply abandoned — nothing reads it
   and nothing migrates it. Delete the directory; v0.5 creates its store on the
   first build:

   ```bash
   rm -rf ~/.cache/cadgen          # or $CADGEN_CACHE_DIR if you set one
   ```

   Clearing the store is always safe, in any version: every model reads as
   stale and rebuilds; no project file is touched.

Also delete the **generated STEP/mesh files themselves** if you want a clean
comparison. A v0.4-generated `.step` has cadgen provenance properties embedded
*inside* the STEP text — v0.5 writes none, so an old artifact is never
byte-comparable with a new one even when the geometry is identical.

### 6. Rebuild

```bash
python src/plate.py
python src/frame.py        # builds plate and standoff too, in parallel, then links them
```

Run each model script explicitly, or the roots. A second run of a current model
prints `current ...` and never touches the kernel.

#### Rethink your tolerance flags — do not copy them

This is the easiest thing to get silently wrong.

| | v0.4 | v0.5 |
| --- | --- | --- |
| `--mesh-tolerance` | **absolute** linear deflection, mm; default `0.02` | **relative** chord tolerance, fraction of each component's bounding diagonal; default `1.5e-3` |
| `--mesh-angular-tolerance` | radians; default `0.6` | radians; default `0.35` |

A v0.4 value carried over unchanged means something entirely different. On a
200 mm part, `--mesh-tolerance 0.02` used to mean 0.02 mm; in v0.5 it means
0.02 × 200 = 4 mm — vastly coarser. Drop your old numbers and start from the
new defaults, tightening only where a curved part visibly needs it. Tolerances
declared on a root do not reach its children; declare them on every model that
needs them.

There is now **one** JS tessellator for both render and export; the OCCT mesh
path is deleted. An exported STL/3MF/GLB is the same tessellation the viewer
draws, watertight, colored, and byte-deterministic across repeated exports.

#### The daemon and the pool

Every build runs on a pool of warm worker processes, one bound per model, with
a job limit of one per core (`CADGEN_JOBS` overrides). You start nothing — the
first call spawns the daemon. `cadgen daemon status` shows its workers and the
jobs in flight. There are **no locks**: `--lock-timeout`, "contended" and
"skipped" outcomes are gone; a build never waits on another and never cancels
one. `CADGEN_DAEMON=0` runs the same parallel build on transient workers that
exit with the run (useful for tests; those builds are invisible to a running
viewer). Do not mix the two modes on one model.

### 7. Verify

**Freshness.** `cadgen store why <model.py>` is the one freshness door. It
prints the gate's verdict clause by clause and why — which closure file
changed, which child's result moved, which output is missing — and exits 1
when stale. Reach for it whenever a model did or did not rebuild when you
expected, before reaching for `--force`.

```bash
cadgen store why src/frame.py
cadgen store info                # what the store holds, by kind
cadgen store gc --dry-run        # what a sweep would remove
```

**Inspect.** The baseline check, then targeted questions:

```bash
cadgen step inspect refs STEP/plate.step --facts --planes --positioning
cadgen step inspect validate STEP/plate.step
cadgen step inspect measure STEP/frame.step --from '#o1.2' --to '#o1.3' --axis x
```

`refs --facts` reports counts and bounds, and its `ok` field covers ref
resolution only — an open shell and an inverted solid both pass it. Use
`validate` for geometry soundness.

**Snapshot.** Mandatory after any visible change:

```bash
cadgen step snapshot STEP/plate.step tmp/review.png
```

The path you name is the path you get, cleared before the render and written
atomically after it, so a missing file is the failure signal.

**Verify the geometry did not move.** Compare `inspect refs --facts` of the
v0.4 build you kept with the new one: identical occurrence, face and edge
counts and bounds mean the migration moved nothing. Between two v0.5 builds the
check is sharper — `python src/plate.py --json` prints the `tree` hash, and an
identical tree is identical geometry.

**View.** The CAD Viewer is `cadgen viewer`, run from the directory to serve:

```bash
cd /absolute/path/to/project && cadgen viewer
cadgen viewer list      # every running viewer and what it serves
cadgen viewer stop --port 3245
```

The client build ships in the wheel; there is no separate viewer install or
launcher. A document's badge shows compile state only — **not compiled**,
**compiling**, **rendered**, **failed** — and a document with no tree is
compiled when you open it. The viewer never reads your source and never says
"stale": whether a document is behind its script is `store why`'s question.

---

## CLI cross-reference

v0.4's user-facing commands were skill scripts run as `python scripts/<tool>`.
v0.5 has a single console script, `cadgen`, plus running model scripts
directly. Every subcommand is also reachable as `python -m cadgen.cli <verb>`.

| v0.4 | v0.5 |
| --- | --- |
| `python scripts/gen MODEL.step.py` | `python model.py` |
| `python scripts/gen MODEL.step.py --write` | `python model.py` (a run always writes) |
| `python scripts/gen ... --write PATH` | `out=` on the decorator (there is no per-run override) |
| `python scripts/gen ... --force` | `python model.py --force` |
| `python scripts/gen ... --json` / `--verbose` | `python model.py --json` / `--verbose` |
| `python scripts/gen ... --mesh-tolerance` | same flag — **but the units changed**, see step 6 |
| `python scripts/export TARGET --stl/--3mf/--glb` | `@stl`/`@threemf`/`@glb` on the model, or `cadgen stl\|3mf\|glb build DOC [OUT]` |
| `cadgen.compose.memo(helper, ...)` | a child model, imported and called |
| `python scripts/inspect refs\|measure\|align\|frame\|diff\|validate` | `cadgen step inspect <inspection> ...` |
| `python scripts/snapshot ...` | `cadgen step snapshot`, `cadgen stl\|3mf\|glb snapshot`, `cadgen dxf snapshot`, `cadgen urdf\|sdf snapshot`, or polymorphic `cadgen snapshot` |
| `python scripts/artifact ...` / `cadgen-step-artifact` | `cadgen step compile` (internal; every door compiles on demand) |
| `python skills/cad/scripts/cadgen_daemon ...` | `cadgen daemon status` |
| the viewer launcher (`npm run start --dir`, `server/main.py`) | `cadgen viewer`, `cadgen viewer list`, `cadgen viewer stop` |
| `cadgen cache info\|gc` (intermediate 0.5) | `cadgen store info\|why\|gc` |
| DXF: `python skills/dxf/scripts/gen ...` | `python drawing.py` |
| — | `cadgen step build IN OUT` (re-emit/annotate a document) |
| — | `cadgen store why <model.py>` |
| — | `cadgen doctor` |

The full v0.5 command set is `cadgen --help`:

```
3mf|glb|stl build      write a model's mesh output(s)
3mf|glb|stl snapshot   render a mesh to an image
daemon status          show the warm daemon's workers
doctor                 print installed cadgen and verify a skill's pin
dxf snapshot           render a DXF to an image
sdf|urdf snapshot      render a robot description to an image
sdf|urdf|srdf validate validate a robot description
snapshot               render any supported input to an image
step build             write a new STEP from one, with kinematics
step compile           make a STEP's tree current (internal)
step inspect           inspect selector references in a STEP
step snapshot          render a STEP model to an image
store                  the store: info, why <model> (gate verdict), gc
viewer [list|stop]     serve the current directory in the CAD Viewer
```

Notable absences: there is no `cadgen gen`, no `cadgen export`, no `cadgen
build`, and no `cadgen dxf build` — a drawing's file *is* the product, made by
running its script.

### Doors take documents; scripts are run

Every `cadgen` verb above takes a `.step` / `.stl` / `.dxf` **file** — a
document. `python <script>` is the only source door. A door finds a document's
tree by the hash of the file's bytes; when there is none (a vendor STEP, a file
copied in from elsewhere, a store you just cleared) it **compiles the file** as
a pool job and proceeds. A door never refuses a document and never runs a
script: it does not know, or ask, whether the file is behind its source. That
question belongs to `cadgen store why`.

## Selector refs

**Good news: the ref grammar only widened.** No ref a v0.4 project wrote stops
parsing in v0.5. You do not have to rewrite refs — this section is here so you
know what is now *available*.

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

- **Comma lists inherit context.** Whichever naming scheme came last seeds the
  bare entities after it: `#o1.2,f3,f4` means `o1.2`, `o1.2.f3`, `o1.2.f4`.
- **Duplicate labels never resolve bare.** A label matching two occurrences
  raises and lists the numbered aliases (`_1`, `_2`, in occurrence-tree order).
- **Numeric forms win.** A part named `f12` or `o1.4` gets no alias and is
  reachable only by its numeric id.
- **Occurrence-group refs have no special syntax.** A group is an occurrence
  ref naming an interior node of the instance tree — `#o1.4`. In v0.4 that was
  an error; in v0.5 it expands to its subtree leaves in tree order.

**File prefixes are a guard, not a resolver.** An empty prefix (`#o1.2`) is
accepted everywhere. A *non-empty* prefix must name the file the command was
already pointed at, or it is an error; it never selects a different file.

```bash
cadgen step inspect refs STEP/bracket.step '#o1.2.f19'      # always fine
cadgen step inspect refs STEP/bracket.step 'bracket#o1.2'   # fine: names the target
cadgen step inspect refs STEP/bracket.step 'other#o1.2'     # error
```

**What is emitted.** The toolchain accepts many spellings and prints exactly
one: numeric, leading `#`, no file prefix. On a single-occurrence document the
occurrence prefix is dropped from the display form (`#f45`), while an assembly
prints the full path (`#o1.12.f19`). The CAD Viewer is the one place that emits
file-prefixed refs.

**Surfaces differ slightly.** `inspect refs`/`frame`/`measure`/`align` require
the leading `#`; `inspect validate`/`interfere --refs` and snapshot's
`--focus`/`--hide` accept it optionally. `inspect diff` takes no refs at all.
Snapshot selection accepts **occurrence refs only**.

**Stop writing `.step.py` targets.** `path/to/entry.step.py` was a documented
target form in v0.4 and is no longer part of the contract.

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

Also removed: the `params` key (it is `kinematics` now), and `workspaceRoot` /
`rootDir` (pass a relative or absolute `input` path instead). `.gif` output
paths are refused.

- `mode` is `view` (default), `section` or `list`. Mesh inputs allow only
  `view` and `list`.
- `selection.focus`/`selection.refs` and `selection.hide` are mutually
  exclusive within one job. Selection requires STEP topology, so mesh, robot
  and DXF inputs refuse it.
- `outputs` entries are a bare string or an object with `path`, `width`,
  `height`, `sizeProfile`, `camera`, `label`, `viewLabel`, `dataUrl`, `text`.
- A packet may be a single job object, a bare array of jobs, or
  `{"jobs": [...]}`.
- `--job PATH` reads a JSON file; `--job -` reads stdin. The rich option flags
  (`--camera`, `--theme`, `--display`, `--kinematics`, `--animation`) each
  take a name, inline JSON, or a path; `--time SECONDS` is the moment for
  `--animation` and is refused without it.

### Themes and display are two separate options

- **`--theme`** selects the visual world: `materials`, `background`, `floor`,
  `environment`, `lighting`, `colorMode`, `projection`, `modeColors`. Ids:
  `workbench-light`, `workbench-dark`, `cinematic`, `vibrant`, `blue`, `pink`,
  `clay-sunrise`, `terminal`, plus the render-only `snapshot`.
- **`--display`** controls how geometry is drawn: `projection`, `mode`, `clip`,
  `exploded`, `edges`.

The snapshot default theme is `snapshot` — Workbench Light with the ground grid
and origin axis removed. Pass `--theme workbench-light` for the viewer's own
look. Display `mode` has seven canonical values: `solid`, `rendered`,
`transparent`, `hidden_edges`, `hidden_lines_removed`, `unshaded`,
`wireframe`; the two topology modes need CAD topology, so mesh inputs refuse
them.

## Artifact and schema reference

### What lands where

| Thing | v0.4 | v0.5 |
| --- | --- | --- |
| Model source | `<name>.step.py` / `<name>.dxf.py` with `gen_step()`/`gen_dxf()` | `<name>.py` with one parameterless decorated function, called under `__main__` |
| Primary artifact | Written only with `--write` | Whatever the decorators declare, always written by a run; STEP is not required |
| Derived geometry | In-tree `__cadgen__/models/<entry>/` render packages | `~/.cache/cadgen/objects/` — content-addressed components and trees |
| Freshness | Provenance embedded in the STEP text, later a `records/` tier | `~/.cache/cadgen/index/model/<sha256(script path)>` — the model's record |
| Children | Inline geometry, `lib/` helpers, `compose.memo` | Sibling models, called; the parent's tree **links** their trees |
| Declarations sidecar | `<name>.step.js` (a JS module) | `<name>.step.json`, schema 5, JSON |
| Pose/FK script | `<name>.params.js` | `kinematics=` on the decorator (data, in the sidecar) |
| Animation | `.params.js` demo modes; GIF export | `<name>.anim.js`, text copied into the sidecar; PNG stills only |
| Mesh outputs | `scripts/export --stl/--3mf/--glb` | `@stl`/`@threemf`/`@glb` decorators, or the format doors |

### The sidecar: `<name>.step.json`, schema 5

A sidecar carries **declarations only**, and exists **only when the model needs
one** — when it declares kinematics, animation, or mesh exports. A plain model
that is geometry and nothing else writes no sidecar at all.

```
schemaVersion   5
kinematics      typed mates with axes resolved to world numbers, couplings, pose presets
animation       the .anim.js choreography TEXT, copied
meshExports     what the @stl/@glb/@threemf declarations resolved to
```

There is **no** `sourceKind`, `sourcePath`, `sourceHash`, `sourceClosure`, or
timestamp — a generated file carries no tie back to its source. A model that
*drops* its kinematics loses the file. A sidecar belongs to the model that
declares it: a parent's sidecar never carries a child's mates.

**A v0.4 sidecar is not read.** A sidecar that is present must declare schema 5;
anything else is an error naming the schema found and the fix — rebuild the
model, or re-annotate the document with `cadgen step build`. A *missing*
sidecar is fine. The migration for sidecars is exactly: **delete the old ones
and rebuild from source.**

### The store

Everything derived lives in one root — `$CADGEN_CACHE_DIR` if set, else the
platform cache dir (`~/.cache/cadgen` on Linux and macOS) — with two sides:

```
objects/ab/cdef…                    immutable, content-addressed: components and trees
index/document/<sha256(file bytes)> a file's bytes → its tree (what every door reads)
index/model/<sha256(script path)>   the model's record: tree, closure, children pins, outputs
index/output/<sha256(output path)>  which script wrote the file at this path
index/component | op | mesh         component entries, the op memo, tessellations
```

`objects/` and `index/document` are the **artifact side**: no object references
a source file, and a reader (door, viewer, snapshot) never opens a record.
`index/model` and friends are the **code side**: what source produced what and
what it depended on. Records are deletable without corrupting anything; a
rebuild re-creates them. `cadgen store info` sizes it, `cadgen store gc`
sweeps unreachable objects, and deleting the whole root is always safe. Nothing
else is written anywhere — a build's progress is process state, read from the
daemon.

## Troubleshooting a half-migrated project

Remember: these errors describe the v0.5 contract. None of them will mention
0.4.

**"declares no CAD model" / "decorate one function with `@step` or `@dxf`"**
You ran a file that still has a bare `gen_step()`/`gen_dxf()` function, or you
renamed the file but forgot the decorator. → Step 2.

**Running the script prints nothing and writes nothing**
The file has no `if __name__ == "__main__": model()`. Decorating declares; the
call builds. → Step 2.

**"takes no parameters"**
A converted `gen_step()` kept parameters — with or without defaults. A model
takes no arguments; parametric geometry is a factory the model calls, another
configuration is another model. → Step 2, and "Mirrored parts" in step 3.

**"takes no arguments"** at a call site
Something calls a model with arguments. Models are called bare; the factory
takes the arguments. → Step 3.

**A dict came back from the model / "bare shape"**
The v0.4 envelope. Return the shape; declare meshes as decorators. → Step 2.

**`ModuleNotFoundError: cadgen.compose`**
`memo` is gone. Each memoized helper becomes a child model, imported and
called. → Step 3.

**`AttributeError: ... has no attribute 'relations'` / `assembly_mates`**
The mates-promotion plumbing is deleted; a parent never receives a child's
mates. Declare the mates on the model that owns the parts, or on the parent for
its own occurrences. → Step 3.

**"unsupported sidecar schema … (expected 5)"**
A v0.4 sidecar (or an intermediate `.step.source.json`) is still sitting next to
the artifact. → Delete it and rebuild. Step 5.

**Unexpected keyword argument on a decorator, or "must be a numeric literal"**
You passed a retired name — `write=` instead of `out=`, `pose=` instead of the
kinematics dict's `"at"` key, `kinematics=`/`animation=` on `@dxf` — or a
tolerance that is not a literal. → The decorator table in step 2.

**"kinematics has unknown key(s) … the vocabulary is closed"**
Your kinematics dict has something other than `mates`, `couplings`, `poses`,
`at`. → Step 4.

**Unrecognized argument `-o` / `--output` / `--lock-timeout` on a model run**
There is no per-run output override and no lock layer. `out=` on the decorator
places the file. → Step 2.

**Unrecognized argument on a `cadgen` command**
A retired snapshot flag. `--input`/`-i` and `--output`/`-o` became the two
positionals `TARGET OUT`; `--params` became `--kinematics`. → `cadgen <verb>
--help` is always the current interface.

**`cadgen cache` is not a command**
The intermediate 0.5 name. → `cadgen store info|why|gc`.

**A model did not rebuild after I edited a child**
Expected: a parent pulls its children only when it is built. `cadgen store why
<parent.py>` shows the child pinned at the old tree. → Rebuild the parent.

**An assembly copied a part's geometry instead of linking it**
The part was reflected, `located()`, or otherwise modified after the call.
→ Place with `Pos/Rot/Location *` or `.moved()`; make a mirrored part its own
model. Step 3.

**Mesh export fails with `ERR_MODULE_NOT_FOUND 'three'`** (source checkouts only)
The checkout's `packages/cadgen-js/node_modules` is missing; cadgen names the
fix. Installed wheels never see this.

**Meshes came out far coarser (or finer) than in v0.4**
You carried a tolerance number across. `--mesh-tolerance` is relative now.
→ Step 6.

**The viewer shows a document as "not compiled" after a build**
The build ran with `CADGEN_DAEMON=0`, which the viewer cannot see, or the
viewer was opened on a different store root. Open the file: the viewer compiles
it from its bytes.

## Migration complete when

- [ ] Every model is a plain `.py` with exactly one parameterless decorated
      function, ending in `if __name__ == "__main__": model()`.
- [ ] No `gen_step`/`gen_dxf` remains; no `.step.py`/`.dxf.py` filenames
      remain; no `compose.memo`, `-o`, or envelope dict remains.
- [ ] All build123d access goes through `from cadgen import build123d as bd`.
- [ ] All vendor STEP reads go through `cadgen.read_step`.
- [ ] Every assembly imports and calls its part models; mirrored parts are their
      own models; placement uses `Pos/Rot/Location *` or `.moved()`.
- [ ] No `__cadgen__` directory, `.step.js`, `.params.js`, or
      `.step.source.json` remains anywhere in the project; the old cache root
      is gone.
- [ ] Every model script runs clean, a second run prints `current`, and
      `cadgen store why` agrees.
- [ ] `cadgen step inspect validate` passes on each STEP you author. Purchased
      and vendor solids brought in with `read_step` are inputs, not your
      geometry: validate them once to know what you have, and expect an
      assembly that contains them to report their defects, not yours.
- [ ] A snapshot of each primary STEP has been rendered and reviewed.
- [ ] Tolerance flags have been re-derived from the new relative defaults, not
      copied.
