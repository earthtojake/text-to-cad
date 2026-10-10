# The model contract and STEP generation

Read this file when authoring or rebuilding a model script, composing models
into assemblies, deciding what a rebuild tracks, or working with imported
STEP/STP files.

## The model script is the tool

Generation has no CLI. A model is a plain Python script whose `__main__` calls
the decorated function; that call builds it:

```python
from cadgen import build123d as bd
from cadgen import step

WIDTH = 10.0


@step
def bracket():
    return bd.Box(WIDTH, 10, 10)


if __name__ == "__main__":
    bracket()
```

```bash
python bracket.py                 # builds bracket.step (and the result tree in the store)
python bracket.py --force --json  # per-run flags ride the script's argv
```

Every run updates the cached native geometry and writes the outputs declared
by the model. Display data is derived on demand. Unchanged sources are a
fast no-op. The default `.step` is the sibling `<stem>.step`; relocate it
durably with `@step(out="path/to/out.step")` (relative to the script). There
is no per-run output override: a model has one set of outputs, declared in its
decorators, and the store's record of it is keyed by the script.

Rules the decorator enforces:

- **The decorator only declares.** Nothing runs at decoration or import time.
  To build by running the file directly, end it with
  `if __name__ == "__main__": <model>()`. Imported models build when called.
- **A top-level call builds.** Calling the decorated name when no build is in
  progress (`__main__`, a REPL) runs the pipeline; a failed build exits with
  the pipeline's code. A conventional real-file `__main__` bare call such as
  `plate()` finishes every output without loading its discarded geometry back
  into that process. It takes no arguments.
- **A call inside a build composes.** From another model's body the same name
  returns the shape: the child is built if it is stale (writing ITS outputs
  and record), otherwise loaded from the store, and either way its result is
  linked into the parent's. Composition is ordinary Python; there is nothing
  to cache by hand and no composition API.
- **A model is addressed by its script path** (`python plate.py`,
  `cadgen store why plate.py`), and every model in a file is stale when any
  line of the file changes, so a file usually holds one model, with its output
  decorators stacked on that one function. Helpers and package `__init__.py`
  files are not model entrypoints.
- **Calling a model from plain Python returns its geometry.** Outside a build,
  `plate()` builds (or finds current) and returns the model's tree as a
  `Compound` — what a parent composing it would get — so a script, a notebook
  or a REPL can read bounds, faces or volumes straight off a model. Assign or
  otherwise consume the call when using that return. Only a proven discarded
  real-file `__main__` bare call skips this materialization; instrumented,
  interactive and ambiguous calls keep returning geometry. A drawing returns
  `None`.
- **A model takes no parameters.** It is one configuration of one set of
  outputs, so there is nothing for an argument to select; the decorator
  refuses a parameter list. Parametric geometry is a plain factory the model
  calls:

  ```python
  from __future__ import annotations   # keeps `-> bd.Shape` a string, not an import

  from cadgen import build123d as bd
  from cadgen import step


  def _bracket(width: float, thickness: float) -> bd.Shape:
      return bd.Box(width, 10, thickness)


  @step
  def bracket():
      return _bracket(width=40.0, thickness=6.0)


  if __name__ == "__main__":
      bracket()
  ```

  A second configuration is a second model (`bracket_wide.py`), with its own
  outputs — the way two part numbers are two parts. Values a model shares with
  its drawing or its assembly live in module constants (`WIDTH = 40.0`) that
  the siblings import.
- **The return is a bare build123d `Shape` and nothing else** — a dict return
  is refused. The return IS the geometry: a `Compound` placing children is
  packaged as occurrences (linked where a child is another model's result), a
  single solid as one component. `read_scene` exposes that saved occurrence
  hierarchy; manufacturing intent is not inferred from it.
- **Outputs are what the decorators declare.** `@step` writes the `.step`.
  Mesh outputs are `@stl`/`@threemf`/`@glb` stacked on the model, tolerances
  on the decorators (`supported-exports.md`). **A model may declare no STEP at
  all**: `@stl`/`@threemf`/`@glb` with no `@step` is a full model — same tree,
  record, build, no-op and composition — that writes its meshes and no
  `.step`, no sidecar. STEP is one output kind, not a requirement.
- Options on `@step`: `out=`, `mesh_tolerance=`, `mesh_angular_tolerance=`,
  `kinematics=`, `materials=`, and `animation=` (`kinematics.md`). **No decorator argument changes the
  geometry a model produces**: they decide where the files land, how they are
  written, and what the sidecar declares. `animation=` is a dict of clip id →
  `cadgen.clip(update, duration=...)`, Python functions the build samples into
  keyframes in that sidecar. `materials=` is
  `{"definitions": {id: material}, "assignments": [{"targets": ["#label", "#group"], "material": id}]}`;
  definitions remain available even when unassigned, and every target must
  resolve exactly. See `build123d-modeling.md` for the material channels.
  Everything a model declares about itself lives in its decorators, and a
  child's intrinsic materials inherit through its pinned tree. Kinematics and
  animation are document-scoped and never inherit into a parent.

**Imports:** `from cadgen import build123d as bd` is a lazy re-export, so a
current model can finish before loading the CAD kernel. Geometry, CAD file reads
or `bd` attributes in module-level constants or defaults load it anyway, as does
an annotation such as `-> bd.Shape` without `from __future__ import annotations`.
Raw `import build123d` works but pays the import cost on every rerun.

**A model runs like `python script.py`.** Its folder is on `sys.path` for the
whole build, plus your `PYTHONPATH` — cadgen adds nothing else and infers no
project root — so an import inside the body, or inside a helper the body calls,
resolves exactly like one at module top — and the file it loads is hashed when
it executes, so it is in the closure either way. Module-top imports let the
static scan see the graph up front; a lazy import is not an error.

## Generated vs imported STEP

These two terms classify a STEP file by what its source is:

- A **generated STEP file** has a model script as its source. The STEP is a
  *derived output*; the script is what you edit and re-run.
- An **imported STEP file** is its own source: authored or downloaded
  elsewhere. There is nothing upstream to regenerate.

A STEP model with `kinematics=`, `materials=`, or `animation=` writes a sidecar
beside its output (`<name>.step.json`) containing the corresponding resolved
sections, bound to the saved STEP's byte hash. A model with none writes no
sidecar; its store record makes reruns no-op. Mesh declarations stay in that record.
Compiling an imported STEP preserves any authored sidecar. The written STEP file
itself carries NO cadgen metadata and no link back to source code, ever — a
bare artifact copied anywhere is a plain importable file, and every door
resolves it by its bytes, so a moved or copied document renders identically to
its twin.

## Composing on other parts: children and inputs

A model that builds on another part wires it in one of two modes:

- **A CHILD (the default)** — the other part is a model in this project:
  import its function and call it. A child edit flows into the parent on the
  parent's next rebuild; there are no exported bytes to keep in sync. A
  generated child read back through its exported `.step` becomes an input
  instead: nothing rebuilds it, and the parent copies it rather than linking it.
- **An INPUT** — the other part is a document, not source: a purchased or
  downloaded part, or a generated part the user has EXPLICITLY asked to
  decouple (export it once, then treat the export like any other document).
  Read it with `cadgen.read_step`, below.

### Children

A child is just an import: model scripts are real modules, and
`from widget import widget` binds the model with no build side effects.
Calling `widget()` inside the parent's body builds the child when it is stale
(writing the child's own outputs) or loads its result from the store, and
returns the shape. What comes back is GEOMETRY only — tree, labels, colors,
placements. A child's sidecar content (its mates, kinematics, animation) never
rides up into the parent: declare what the assembly needs on the assembly.

```python
from cadgen import build123d as bd
from cadgen import step

from link_pin import link_pin   # importing binds; never builds


@step(out="../STEP/link_arm.step")
def link_arm():
    bar = bd.Box(40.0, 8.0, 4.0)
    bar.label = "bar"
    pin = link_pin()                                   # built if stale, else loaded
    left = pin.moved(bd.Location((-15.0, 0.0, 2.0)))   # placed: the parent LINKS to the pin
    left.label = "pin_left"
    right = pin.moved(bd.Location((15.0, 0.0, 2.0)))   # placed again: a second link, one tree
    right.label = "pin_right"
    return bd.Compound(children=[bar, left, right], label="link_arm")


if __name__ == "__main__":
    link_arm()
```

**Link or component.** Place a child's shape as it came back — `moved()`,
`Pos/Rot/Location * child`, relabelled, recolored — and the parent's result
LINKS to the child's tree (stored once, shared by every parent; two placements
are two links to one tree). Modify it (a boolean, a mirror, extracting a
sub-shape) and the parent owns that geometry as its own components; the
dependency is tracked either way. `located()` replaces the placement, and its
copy becomes the parent's own component, not a link (`positioning.md`). Each
`moved()` copies the shape and all under it. Geometry changes that belong to the
child go in the child's file or its factory.

Child calls submit work and return lazy shapes. Placements, labels and colours
can be set before geometry is ready; geometry queries wait for the child.
Independent children can build in parallel, subject to runtime admission.
No scheduling code is needed in the model.

**Dependency is pull.** A parent depends on each child by RESULT: its record
pins the child's tree hash, so a child edit that yields identical geometry
leaves the parent current, and an edit that does not reach a child skips that
child's Python and kernel work entirely. **Rebuilding a child does not rebuild
the assemblies that use it** — run the parent to pick up the change
(`python src/robot.py` builds whatever is stale beneath it and links the
rest). A parent finished against a child that changed during its build says so
(`already stale: … rerun`).

### What a rebuild tracks — models by result, constants by value, functions by reach

What an importer TAKES from a model file decides how that file counts:

- **`from widget import widget`** (the model function), called → tracked by
  RESULT: the parent pins the child's tree, so an edit inside `widget()`'s body
  rebuilds the parent only when the child's geometry changes. Importing
  `widget.py` still runs its top level in the parent's process — its imports,
  module-level code and any decorator argument that is not a literal — so an
  edit there rebuilds the parent too (a literal such as `out="..."` does not).
  Keep a model file's top level to imports, constants and definitions.
- **`from widget import WIDTH`** (a module-level literal: a number, string,
  bool, `None`, or tuples/lists/dicts of those) → tracked by VALUE: a
  comment or body edit in `widget.py` leaves the importer current; only a
  changed value rebuilds it. A value computed by module-level code is
  import-time code: editing that expression rebuilds the importer too.
- **Anything else** from a model file (a helper function, a `bd.` object, an
  expression) → tracked by FILE: the whole file joins the importer's source
  closure, and any edit to it rebuilds the importer. Shared helpers therefore
  belong in `lib/` (a plain module, in the closure of every model that
  reaches it — by the functions and constants the model can actually run, so
  editing a helper no model calls rebuilds nothing), and shared constants may
  live in a model file or in `lib/`.

Inputs join the closure too: every data file the build opens is hashed as a
build input, whatever opens it (below). A new
file that changes what an import finds — an `__init__.py` added to a folder, a
package beside a module, a same-named module earlier on the path — also makes
the model stale. Literal `kinematics=` and named `materials=` are decorator
annotations; `animation=` clips are code, tracked like the model body. Imported
values and helper calls remain ordinary source dependencies.

Every decorator argument is ordinary Python, evaluated when the module is
imported: `out=f"{FOLDER}/{NAME}.step"`, `mesh_tolerance=TOL` with `TOL` from
`lib/`, a path built from a constant — all fine, and nothing is read off the
source text. The values feeding them are tracked like any other input (a
`lib/` helper by reach, a model-file constant by value), so changing the
constant behind an `out=` makes the model stale. The module top must still stay
kernel-free so checking the model's declarations stays cheap.

### Splitting for rebuild speed

cadgen never caches work inside a model: a model whose inputs changed runs
from scratch, and one whose inputs did not is skipped whole. Rebuild speed
therefore comes from how the project is split:

- A part in its own model (a thin entry file whose `@step` function calls a
  factory in `lib/`, placed by its parent like any child) rebuilds alone: an
  edit to it relinks the parent, its siblings stay current, and stale children
  build in parallel. One heavy casing or shell inside a model of many light
  parts is the case that gains most: edits to the light parts stop paying for it.
- A model reruns only when code it reaches changes, so an edit to one `lib/`
  factory leaves the models that never call it current.
- Every `@step` function in a file is stale when any line of that file changes.

A part that builds in a second or two gains nothing from its own file; each
model's time line (below) shows where a split pays.

### Annotation caching

Annotation-only edits may reuse cached geometry; computed or imported
annotations remain tracked dependencies and may require a rebuild. Animation
clips are always code: editing one reruns the model, which rewrites the
sidecar's keyframes and keeps the STEP's bytes.

### Models inside a package

A model file may live inside a Python package (folders with `__init__.py`).
cadgen runs it under its dotted name, so relative imports (`from .parts.washer
import washer`) resolve whenever cadgen loads the model: as a child of another
model, or when you run it as a module (`python -m pkg.stack`). Running the file
by path (`python pkg/stack.py`) is Python's own limit, not cadgen's: Python
executes it as `__main__` with no package, so a relative import fails before
cadgen is involved; use `-m` or absolute imports for a file you run directly.
`PYTHONPATH` still declares any import root beyond the script's own folder;
cadgen adds nothing of its own.

### Mirrored geometry and reusable models

Mirror geometry inline when it belongs to the current model. For example,
`right = bd.mirror(left, about=bd.Plane.YZ)` needs no separate model file.
In cadgen, reflection creates geometry rather than a rigid placement of the
original child: a mirrored child becomes parent-owned components, while its
source model remains a tracked dependency. The parent's complete result is
still cached, and an unchanged parent remains a no-op.

Use a separate model when the mirrored part needs independent outputs or reuse
across assemblies or parent rebuilds. Its result can then be linked and placed
like any other child. A separate model is also the unit of reuse: cadgen
never caches work inside a model, so an unchanged model is skipped whole and
a changed one runs whole (see [Splitting for rebuild speed](#splitting-for-rebuild-speed)).

For independently exported left/right variants, a shared factory is one option:

```python
# src/lib/bracket_shape.py — the factory (plain module, no decorator)
from __future__ import annotations

from cadgen import build123d as bd


def side_bracket(mirrored: bool = False) -> bd.Shape:
    body = bd.Box(40.0, 10.0, 6.0) - bd.Pos(12.0, 0.0, 0.0) * bd.Cylinder(2.5, 6.0)
    return bd.mirror(body, about=bd.Plane.YZ) if mirrored else body
```

```python
# src/bracket_left.py
from cadgen import step

from lib.bracket_shape import side_bracket


@step(out="../STEP/bracket_left.step")
def bracket_left():
    return side_bracket()


if __name__ == "__main__":
    bracket_left()
```

```python
# src/bracket_right.py
from cadgen import step

from lib.bracket_shape import side_bracket


@step(out="../STEP/bracket_right.step")
def bracket_right():
    return side_bracket(mirrored=True)


if __name__ == "__main__":
    bracket_right()
```

Choose between inline geometry and separate models from the outputs and reuse
the project needs. Either can participate in the containing assembly's kinematics.

### Inputs: reading a STEP file the model does not generate

Prefer `cadgen.read_step` to `build123d.import_step`: it returns the same
native shape with the document's colours, and reads warm from the store when it
already holds the file's tree. Either way the file is a build input: replacing
the vendor STEP makes the model stale on its own, with no `--force`.

```python
from pathlib import Path

from cadgen import read_step, step

_HERE = Path(__file__).resolve().parent


@step
def rig():
    motor = read_step(_HERE / "imported" / "vendor_motor.step")   # recorded input
    ...
```

An imported part is an INPUT, not a model: nothing links to it and it has no
record. To make it first-class — so assemblies link to it, so it has its own
outputs and declarations — wrap it in a model of its own:

```python
from pathlib import Path

from cadgen import read_step, step

_HERE = Path(__file__).resolve().parent


@step(out="../STEP/servo.step")
def servo():
    return read_step(_HERE / ".." / "STEP" / "imported" / "sg90_servo.step")


if __name__ == "__main__":
    servo()
```

**Never `read_step` your own output.** A model that reads the `.step` it is
about to write is not a loop — it is a model whose input changes every time it
runs, so the gate can never say "current", every build is a full rebuild, and
the geometry depends on what the last run happened to leave on disk. Keep
source documents where the model cannot write them — placement policy belongs
to `project-layout.md` (`imported/`). Input path and output path being different
files is the whole rule. If the geometry you want is something the project
already builds, call that model instead of reading the artifact.

### Inputs: a data file the model reads

Every file the build opens is recorded as it reads it, whatever reads it: a
JSON routing atlas through `json.load`, a CSV of tap sizes, a table through
`np.load`, a BREP `bd.import_brep` opens in C++, a project font `bd.Text` loads. Edit
`atlas.json` and the model is stale on its own; rewrite it with identical bytes
and it stays current, because the input is the content and not the mtime. A
folder the model globs is recorded too, so adding or removing a profile there
rebuilds it. The model's own outputs in that folder do not count; another
model's do, so a model that globs the folder its siblings build into reads stale
once after their first build. Nothing is declared.

Not inputs: a file the build writes, the model's own outputs, the Python
environment, and system files (fonts, time zones). A program the model starts
as a separate process reads files on its own, unseen: keep that step outside
the model and read its result.

For structuring multi-part projects (folder layout, shared `src/lib/` code,
commit policy), read `project-layout.md` and `project-template.md`.

## Freshness: `cadgen store why`

`cadgen store why <model>.py` explains whether the model is current and which
sources, imported constants, child results, cached objects or declared outputs
changed. It also accepts a generated STEP when the store knows its source.
Exit status is 0 for current, 1 for stale; `--json` returns the verdict as data.

```bash
cadgen store why src/frame.py
python src/frame.py                 # rebuild the parent after a child changes
python src/frame.py --force         # force this model's body to run
```

The gate cannot track geometry selected by environment variables, the working
directory, time or randomness; configurations in source or factory arguments,
and the files a model reads, are tracked. A cadgen fix does not invalidate
results cached before it: `--force` rebuilds a model whose cached result still
reflects the old behaviour.

## Generated assemblies

An assembly is a model whose return places children (a `Compound` of parts
or of other models' results); `read_scene` exposes the saved hierarchy.
Transforms or native joints express placement; see [positioning](positioning.md).

## Imported STEP/STP files

An imported STEP/STP file needs no model script and no preparation step. Hand
it straight to `read_scene`, `cadgen step snapshot`, or a mesh door:
each compiles a tree from the file's bytes on first use (a job in the pool,
shared with the CAD Viewer), and its part/assembly kind is inferred from the
STEP product hierarchy.

```bash
python tmp/check_imported.py  # read_scene("path/to/imported.step")
cadgen stl build path/to/imported.step meshes/imported.stl
```

To produce STL/3MF/native GLB files from an imported STEP, pass it to the
matching format command. OUT is optional and defaults to a sibling with the
requested extension; read [mesh exports](supported-exports.md).

### Re-emitting a foreign STEP as your own

A STEP written by another kernel round-trips through cadgen with
`cadgen step build IN OUT`: OCCT reads it, the tree is built, and the
canonical writer emits it, so OUT's bytes are deterministic and identical on
every run. The same command ANNOTATES a document that has no model script —
`--kinematics` takes the whole space (`{mates, couplings, poses}`, the same
vocabulary the decorator takes, as inline JSON or a `.json` path) and
`--materials` takes the named declaration as inline JSON or a `.json` path.
Both resolve into OUT's unified sidecar. Animation is not an annotation
`step build` takes: clips need a model script, such as a thin wrapper that
reads the foreign STEP.

```bash
cadgen step build vendor/hinge.step STEP/hinge.step \
  --kinematics '{"mates": [{"name": "swing", "kind": "revolute",
                            "parent": "#body", "child": "#lever",
                            "axis": "#lever.f2", "limits": [0, 90]}],
                 "poses": {"open": {"swing": 45}}}'
```

Re-running is a no-op; editing only these annotations refreshes the sidecar
without re-emitting a byte. Vendor metadata (PMI, GD&T) does not survive the round trip.
OUT's root is named after OUT: the root `PRODUCT` and the header's `FILE_NAME`
take OUT's file stem (`STEP/hinge.step` → `hinge`), exactly as a model script's
document is named after the file it writes — so the same input re-emitted to two
paths yields two differently named documents. Names below the root are kept, so
`#label` references to the parts keep resolving; do not address the root by the
name IN carried.
A shape that will keep changing suits a model script (a thin wrapper that reads
the foreign STEP); `step build` canonicalizes or annotates a file you do not own,
once.

## Optional-module assemblies

A model that imports several part modules and SKIPS the ones that do not exist
yet is a useful pattern for parallel work — the assembly stays renderable while
individual parts are still being written. It has one sharp edge.

The model's closure is computed from the modules it ACTUALLY IMPORTED at build
time. A module that did not exist during the build was never in the closure,
so its later appearance cannot make the model stale, and every door keeps
reading the old document's tree — no error, no warning, until `--force` rebuilds
the model with the new module.

## Progress and runtime diagnostics

The warm daemon is on by default. `cadgen daemon status` shows running and
queued work. Jobs may wait for CPU or memory admission; concurrency and worker
lifetimes are runtime details, specified in the installed package's `STORE.md`.
For diagnosis, `CADGEN_DAEMON=0 python part.py` uses transient workers with the
same geometry/output contract.

Results go to stdout; progress and errors go to stderr. Model runs accept
`--json` for machine-readable results and `--verbose` for timings/full tracebacks.
A `--json` result names its `document` by absolute path, and a `--json` failure
is one `{"ok": false, "error": "..."}` line on stdout with exit status 1 — the
same envelope every `cadgen` command prints. `python part.py --help` lists the
per-run flags. A script builds the models its `__main__` block calls; no flag
selects one.

Every model a run builds, its children included, prints where its time went:

```text
[cadgen] built STEP/arm.step in 9m42s: model code 8m20s, cadgen 1m22s
```

Model code is the decorated function's call, less its waits for child builds
(named on the line when they happened); cadgen is loading the script, storing
parts and writing outputs. A `--json` result carries the same numbers in
`timings` (`seconds`, `modelSeconds`, `cadgenSeconds`, `childrenSeconds`,
`queuedSeconds`; `null` for a current model). A model whose code took more
than twice its last build's, and 30 s more, gets a warning: the time is in the
script. `python part.py --profile` rebuilds that model with its own code under
cProfile and prints, after the build, the project's functions by cumulative
time and the busiest functions anywhere by own time, with `file:line` and
calls. OCCT calls count in the Python function that made them; children are
not profiled (run a child's script to profile it); nothing is written to the
project. cProfile slows typical build123d code about 2x and code made of many
tiny Python calls up to 10x, so read shares, not seconds.
For long model bodies, optional `report` and `track` calls expose progress:

```python
from cadgen import report, track

# Inside a model body:
report("ribs")
for rib in track(ribs, label=lambda r: r.name):
    ...
```

Two stores (a separate `CADGEN_CACHE_DIR`) writing the same project's outputs
cause repeated freshness misses. The store holds derived results only:
`--force` or `cadgen store forget <model>.py` drops one model's result, and
`cadgen store gc` removes unreachable cache data. The store
keeps itself under `CADGEN_STORE_MAX` (default 20 GB) by evicting its least
recently written derived entries; `cadgen store info` shows its size.
