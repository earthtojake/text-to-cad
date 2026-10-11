# The model contract and STEP generation

Read this file when authoring or rebuilding a model script, composing models
into assemblies, deciding what a rebuild tracks, or working with imported
STEP/STP files.

## The model script is the tool

Generation has no CLI: running a model script builds it, and per-run flags ride
its argv (`python bracket.py --force --json`). The default `.step` is the
sibling `<stem>.step`; `@step(out="path/to/out.step")` (relative to the script)
moves it. A model has one set of outputs, declared in its decorators; there is
no per-run output override.

- **The decorator only declares.** Nothing runs at decoration or import time;
  `if __name__ == "__main__": <model>()` is what builds a file run directly.
- **A top-level call builds.** Calling the decorated name outside a build runs
  the pipeline; a failed build exits nonzero.
- **A call inside a build composes.** From another model's body the same name
  returns the shape: the child is built if stale (writing its own outputs) or
  loaded from the store, and its result is linked into the parent's. There is
  nothing to cache by hand and no composition API.
- **A model is addressed by its script path** (`python plate.py`,
  `cadgen store why plate.py`), and every model in a file is stale when any
  line of the file changes, so a file usually holds one model, with its output
  decorators stacked on that one function. Helpers and package `__init__.py`
  files are not model entrypoints.
- **Calling a model from plain Python returns its geometry**: outside a build,
  `plate()` builds (or finds current) and returns the model's tree as a
  `Compound`, so a script or REPL can read bounds, faces or volumes off it. A
  drawing returns `None`.
- **A model takes no parameters**; the decorator refuses a parameter list.
  Parametric geometry is a plain factory the model calls:

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

  A second configuration is a second model (`bracket_wide.py`) with its own
  outputs. Values shared with a drawing or an assembly live in module constants
  (`WIDTH = 40.0`) that the siblings import.
- **The return is a bare build123d `Shape`**; a dict return is refused. A
  `Compound` placing children is packaged as occurrences (linked where a child is
  another model's result), a single solid as one component.
- **Outputs are what the decorators declare**: `@step` writes the `.step`, and
  `@stl`/`@threemf`/`@glb` write meshes ([mesh exports](supported-exports.md));
  a model may declare meshes and no STEP.
- Options on `@step`: `out=`, `mesh_tolerance=`, `mesh_angular_tolerance=`,
  `kinematics=`, `materials=` and `animation=` ([kinematics](kinematics.md)). No
  decorator argument changes the geometry a model produces. `materials=` is
  `{"definitions": {id: material}, "assignments": [{"targets": ["#label", "#group"], "material": id}]}`;
  every target must resolve exactly ([material channels](build123d-modeling.md#colour-and-finish)).
  A child's materials inherit into its parents; kinematics and animation never do.

**Imports:** `from cadgen import build123d as bd` is a lazy re-export, so a
current model can finish before loading the CAD kernel. Geometry, CAD file reads
or `bd` attributes in module-level constants or defaults load it anyway, as does
an annotation such as `-> bd.Shape` without `from __future__ import annotations`.
Raw `import build123d` pays the import cost on every rerun.

**A model runs like `python script.py`.** Its folder is on `sys.path` for the
whole build, plus your `PYTHONPATH`; cadgen adds nothing else and infers no
project root. An import inside the body resolves like one at module top, and
the file it loads joins the closure either way.

## Generated vs imported STEP

A **generated** STEP has a model script as its source: edit and rerun the
script. An **imported** STEP is its own source, authored or downloaded
elsewhere. The written STEP carries no cadgen metadata and no link back to its
source; every door resolves a document by its bytes, so a copied file renders
like its original. A STEP model with `kinematics=`, `materials=` or `animation=`
writes a sidecar (`<name>.step.json`) bound to the STEP's byte hash; compiling
an imported STEP keeps any sidecar beside it.

## Composing on other parts: children and inputs

- **A CHILD (the default)**: the other part is a model in this project; import
  its function and call it. A child edit reaches the parent on the parent's next
  rebuild. A generated child read back through its exported `.step` becomes an
  input instead: nothing rebuilds it, and the parent copies it rather than
  linking it.
- **An INPUT**: the other part is a document (a purchased part, or a generated
  part the user asked to decouple). Read it with `cadgen.read_step`, below.

### Children

`from widget import widget` binds the model with no build side effects; calling
`widget()` inside the parent's body builds or loads it and returns its shape.
What comes back is geometry only (tree, labels, colours, placements): a child's
mates, kinematics and animation never ride up, so declare what the assembly
needs on the assembly.

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

**Link or component.** A child placed as it came back (`moved()`,
`Pos/Rot/Location * child`, relabelled, recoloured) is a LINK to the child's tree,
stored once and shared by every parent. A modified child (a boolean, a mirror, a
sub-shape) becomes the parent's own components. `located()` replaces the
placement and also makes a copy the parent owns. Each `moved()` copies the shape
and all under it.

Child calls return lazy shapes: placements, labels and colours can be set
before the geometry is ready, geometry queries wait for it, and independent
children build in parallel.

**Dependency is pull.** A parent's record pins each child's tree hash, so a
child edit that yields identical geometry leaves the parent current. A parent
that finished against a child changed during its build says it is already
stale.

### What a rebuild tracks — models by result, constants by value, functions by reach

What an importer TAKES from a model file decides how that file counts:

- **`from widget import widget`** (the model), called → tracked by RESULT: an
  edit inside `widget()`'s body rebuilds the parent only when the child's
  geometry changes. Importing `widget.py` still runs its top level in the
  parent's process, so an edit to its imports, module-level code or a non-literal
  decorator argument rebuilds the parent too.
- **`from widget import WIDTH`** (a module-level literal: number, string, bool,
  `None`, or tuples/lists/dicts of those) → tracked by VALUE: only a changed
  value rebuilds the importer. A value computed at module level is import-time
  code and is tracked as code.
- **Anything else** from a model file (a helper, a `bd.` object, an expression)
  → tracked by FILE: any edit to the file rebuilds the importer. Shared helpers
  belong in `lib/`, a plain module tracked by reach: editing a helper no model
  calls rebuilds nothing.

Every data file the build opens is an input too (below). A new file that changes
what an import finds (an `__init__.py`, a package beside a module, a same-named
module earlier on the path) also makes the model stale. Decorator arguments are
ordinary Python evaluated at import (`out=f"{FOLDER}/{NAME}.step"`, a tolerance
from `lib/`), and the values feeding them are tracked like any other input.

### Splitting for rebuild speed

cadgen never caches work inside a model: a model whose inputs changed runs from
scratch, and one whose inputs did not is skipped whole.

- A part in its own model (a thin entry file whose `@step` function calls a
  factory in `lib/`) rebuilds alone: its parent relinks, its siblings stay
  current, and stale children build in parallel. One heavy casing among many
  light parts gains most.
- A model reruns only when code it reaches changes, so an edit to one `lib/`
  factory leaves the models that never call it current.

A part that builds in a second or two gains nothing from its own file; each
model's time line (below) shows where a split pays.

### Annotation caching

Annotation-only edits may reuse cached geometry; computed or imported
annotations remain tracked dependencies and may require a rebuild. Animation
clips are code: editing one reruns the model, which rewrites the sidecar's
keyframes and keeps the STEP's bytes.

### Models inside a package

A model inside a Python package runs under its dotted name, so relative imports
(`from .parts.washer import washer`) resolve when cadgen loads it as a child or
when it runs as a module (`python -m pkg.stack`). Run by path
(`python pkg/stack.py`), Python itself gives it no package and the relative
import fails: use `-m` or absolute imports there.

### Mirrored geometry and reusable models

`right = bd.mirror(left, about=bd.Plane.YZ)` inline needs no separate model
file. Reflection creates geometry rather than a placement, so a mirrored child
becomes parent-owned components (its source model stays a tracked dependency).
A separate model suits a mirrored part that needs its own outputs or reuse
across assemblies; a shared factory serves both hands:

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

### Inputs: reading a STEP file the model does not generate

`cadgen.read_step` returns the same native shape as `build123d.import_step`,
with the document's colours, and reads warm from the store when it can. Either
way the file is a build input: replacing it makes the model stale.

```python
from pathlib import Path

from cadgen import read_step, step

_HERE = Path(__file__).resolve().parent


@step
def rig():
    motor = read_step(_HERE / "imported" / "vendor_motor.step")   # recorded input
    ...
```

An imported part is an input, not a model: nothing links to it and it has no
record. Wrapping it in a model of its own gives it outputs, declarations and
links:

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

`read_step` refuses a model's own output: an input that changes on every run
never settles. If the project already builds the geometry, call that model.

### Inputs: a data file the model reads

Every file the build opens is recorded as it reads it, whatever opens it:
`json.load`, `np.load`, a BREP `bd.import_brep` opens in C++, a font `bd.Text`
loads. The input is the content, not the mtime, and a globbed folder is recorded
too, so adding or removing a file there rebuilds the model. A model's own outputs
do not count; another model's outputs in a globbed folder do. An environment
variable the model's own code reads is an input by its value. Not inputs:
installed packages, system files, and anything a program the model starts reads;
the build warns when it starts one.

## Freshness: `cadgen store why`

`cadgen store why <model>.py` explains whether the model is current and which
sources, imported constants, child results, cached objects or declared outputs
changed; it also accepts a generated STEP. Exit status is 0 for current, 1 for
stale; `--json` returns the verdict as data. A cadgen fix does not invalidate
results cached before it: `--force` rebuilds a model whose cached result still
reflects the old behaviour.

## Imported STEP/STP files

An imported STEP/STP needs no model script and no preparation: `read_scene`,
`cadgen step snapshot` and the mesh `build` commands each compile its tree from
the file's bytes on first use, inferring part or assembly from its product
hierarchy.

### Re-emitting a foreign STEP as your own

`cadgen step build IN OUT` reads a STEP written by another kernel and emits it
through cadgen's canonical writer, so OUT's bytes are deterministic; rerunning is
a no-op. The same command annotates a document that has no model script with
`--kinematics` and `--materials` ([kinematics](kinematics.md#annotating-a-step-you-did-not-generate));
clips need a model script. Vendor metadata (PMI, GD&T) does not survive; names
do, so `#label` references keep resolving. A shape that will keep changing suits
a thin wrapper model that reads the foreign STEP instead.

## Optional-module assemblies

A model that skips part modules that do not exist yet stays renderable while
parts are written in parallel; a module that appears rebuilds it like an edit.

## Progress and runtime diagnostics

The warm daemon is on by default; `cadgen daemon status` shows running and
queued work, and `CADGEN_DAEMON=0 python part.py` builds with transient workers
under the same contract. Results go to stdout, errors to stderr. Model runs
accept `--json` (one result line; a failure is `{"ok": false, "error": "..."}`
with exit status 1) and `--verbose` (full tracebacks); `python part.py --help`
lists the flags. A script builds the models its `__main__` block calls; no flag
selects one.

Every model a run builds, its children included, prints where its time went:

```text
[cadgen] built STEP/arm.step in 9m42s: model code 8m20s, cadgen 1m22s
```

Model code is the decorated function's call, less its waits for child builds;
cadgen is loading the script, storing parts and writing outputs. A `--json`
result carries the same numbers in `timings` (`null` for a current model). A
model whose code took more than twice its last build's, and 30 s more, gets a
warning. `python part.py --profile` rebuilds that model with its own code under
cProfile and prints the project's functions by cumulative time and the busiest
functions anywhere by own time, with `file:line`; OCCT calls count in the Python
function that made them, children are not profiled, and cProfile slows the code
2-10x, so read shares, not seconds. On a terminal, optional `report` and `track`
calls label progress inside a long model body:

```python
from cadgen import report, track

# Inside a model body:
report("ribs")
for rib in track(ribs, label=lambda r: r.name):
    ...
```

Two stores (a separate `CADGEN_CACHE_DIR`) writing the same project's outputs
cause repeated freshness misses. `cadgen store forget <model>.py` drops one
model's result, `cadgen store gc` removes unreachable data, and
`cadgen store info` shows the store's size; it keeps itself under
`CADGEN_STORE_MAX` (default 20 GB) by evicting least recently written entries.
