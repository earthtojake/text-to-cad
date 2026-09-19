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
- **Use one decorated model per entrypoint file.** Match the script's stem in
  its declared outputs: `plate.py` → `STEP/plate.step`, `STL/plate.stl`, etc.
  Stack output decorators on that one function; put shared factories in helper
  modules and independently exported configurations in separate entrypoints.
  The model is addressed by its script path (`python plate.py`,
  `cadgen store why plate.py`). This is the skill's project convention;
  helpers and package `__init__.py` files are not model entrypoints.
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
  written, and what the sidecar declares. `animation=` is a self-contained
  JavaScript ES module string embedded in that sidecar. `materials=` is
  `{"definitions": {id: material}, "assignments": [{"targets": ["#label", "#group"], "material": id}]}`;
  definitions remain available even when unassigned, and every target must
  resolve exactly. See `build123d-modeling.md` for the material channels.
  Everything a model declares about itself lives in its decorators, and a
  child's intrinsic materials inherit through its pinned tree. Kinematics and
  animation are document-scoped and never inherit into a parent.

**Imports:** use `from cadgen import build123d as bd`, a lazy re-export,
so a current model can finish before loading the CAD kernel. Keep geometry,
CAD file reads and `bd` attributes out of module-level constants/defaults.
Use `from __future__ import annotations` for annotations such as `-> bd.Shape`.
Raw `import build123d` works but pays the import cost on every rerun.

**A model runs like `python script.py`.** Its folder is on `sys.path` for the
whole build, plus your `PYTHONPATH` — cadgen adds nothing else and infers no
project root — so an import inside the body, or inside a helper the body calls,
resolves exactly like one at module top — and the file it loads is hashed when
it executes, so it is in the closure either way. Prefer module-top imports for
readability and so the static scan sees the graph up front; a lazy import is
not an error.

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

A model that builds on another part wires it in one of two modes. Choose
deliberately:

- **A CHILD (the default)** — the other part is a model in this project:
  import its function and call it. A child edit flows into the parent on the
  parent's next rebuild; there are no exported bytes to keep in sync. Never
  route a generated child through its exported `.step`.
- **An INPUT** — the other part is a document, not source: a purchased or
  downloaded part, or a generated part the user has EXPLICITLY asked to
  decouple (export it once, then treat the export like any other document).
  Read it with `cadgen.read_step`, below.

### Memoizing expensive geometry helpers

`from cadgen import memo` adds an optional `@memo` to a parameterized
geometry helper. The model still takes no arguments and declares all files;
the helper returns a shape and creates no files. Use it for expensive repeated
booleans or builders, returning an ordinary `Solid` or a builder's `.part`.
Place reusable factories in a helper module so changing the parent's placement
or configuration leaves their source unchanged. Keys include each helper's
whole captured source file, so editing another function in that file also
invalidates it.

The decorator declares a **pure function under an unmodified CAD/math runtime**:
geometry depends only on immutable arguments, defaults, globals and deterministic
helpers. No I/O, random/time/environment inputs, progress reporting, child model
calls, callbacks, identity-dependent logic or dependency monkeypatches. This is
an author precondition, not an automatically proven Python sandbox. Supported
finite scalars/tuples and a bounded CAD/math vocabulary can reuse results;
unsupported code, mutable inputs and calls within an already-open builder keep
ordinary execution. Cheap primitives often cost less to execute than to verify
and reconstruct, so do not decorate every function.

Normal warm workers and transient child workers support reuse. Generic embedded
calls execute the body. Eligible misses, hits and `CADGEN_MEMO_CACHE=0` use
the same private canonical return codec; native handle identity is not an input
or an output contract. Missing objects recover by running the factory. No
additional caching, ownership or invalidation helpers belong in authored code.
`MEMO.md` in the installed cadgen package specifies the complete contract.

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
dependency is tracked either way. **Never `located()`** for placement: it
deep-copies the geometry, which makes it the parent's own component instead
of a link (`positioning.md`). Put geometry changes that belong to the child in
the child's file or its factory.

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

### What a rebuild tracks — models by result, constants by value, functions by file

What an importer TAKES from a model file decides how that file counts:

- **`from widget import widget`** (the model function) → tracked by RESULT:
  the parent pins the child's tree; `widget.py` is not in the parent's source.
- **`from widget import WIDTH`** (a module-level literal: a number, string,
  bool, `None`, or tuples/lists/dicts of those) → tracked by VALUE: a
  comment or body edit in `widget.py` leaves the importer current; only a
  changed value rebuilds it.
- **Anything else** from a model file (a helper function, a `bd.` object, an
  expression) → tracked by FILE: the whole file joins the importer's source
  closure, and any edit to it rebuilds the importer. Shared helpers therefore
  belong in `lib/` (a plain module, in the closure of every model that
  reaches it), and shared constants may live in a model file or in `lib/`.

Inputs join the closure too: a `read_step` document is hashed as a build
input, and so is any other data file the model declares with
`cadgen.declare_input` (below). Embedded `animation=` source and named
`materials=` are decorator annotations. Imported values and helper calls
remain ordinary source dependencies.

Every decorator argument is ordinary Python, evaluated when the module is
imported: `out=f"{FOLDER}/{NAME}.step"`, `mesh_tolerance=TOL` with `TOL` from
`lib/`, a path built from a constant — all fine, and nothing is read off the
source text. The values feeding them are tracked like any other input (a
`lib/` module by file, a model-file constant by value), so changing the
constant behind an `out=` makes the model stale. The module top must still stay
kernel-free so checking the model's declarations stays cheap.

### Annotation caching

Annotation-only edits may reuse cached geometry; computed or imported
annotations remain tracked dependencies and may require a rebuild.

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
like any other child. Eligible factory/operation caches may also reuse inline
work; separate models add a model-level cache boundary, not basic cache safety.

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

Use `cadgen.read_step`, not `build123d.import_step`. It returns the same
native shape, reuses cached geometry when available, and records the file's
content hash as a build input. Replacing the vendor STEP
then makes the model stale on its own, with no `--force`; read through
build123d and the model stays "current" against a file that changed
underneath it.

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

`read_step` records the STEP it reads because cadgen reads it for you. For any
other file a model reads — a JSON routing atlas, a CSV of tap sizes, a table of
solved offsets — cadgen has no reader, so declare it with
`cadgen.declare_input`. It returns the resolved path and puts the file's content
hash in the model's closure; the model does its own parsing.

```python
import json
from pathlib import Path

from cadgen import build123d as bd
from cadgen import declare_input, step

_HERE = Path(__file__).resolve().parent


@step
def plate():
    atlas = json.loads(declare_input(_HERE / "atlas.json").read_text(encoding="utf-8"))
    return bd.Box(atlas["width"], 20, 4)
```

Wrap the path, not the read, so there is no way to declare one file and read
another. Edit `atlas.json` and the model is stale on its own; rewrite it with
identical bytes and it stays current, because the input is the content and not
the mtime. Without the declaration the model reports itself current forever
after the data changes, and only `--force` gets the truth back. A missing file
raises before the model's parser sees it. The rule about a model's own output
applies here too: never declare a file the model writes.

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
directory, time or randomness. Put configurations in source/factory arguments
and declare file inputs explicitly. After a runtime fix, force affected models
if their cached results still reflect the old behavior.

## Generated assemblies

An assembly is a model whose return places children (a `Compound` of parts
or of other models' results); `read_scene` exposes the saved hierarchy.
Edit the `.py` source to change an assembly; inspect or export its saved STEP
to check what was actually written. Use native labels and choose transforms
or native joints to express placement; see [positioning](positioning.md).

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
vocabulary the decorator takes, as inline JSON or a `.json` path);
`--materials` takes the named declaration as inline JSON or a `.json` path;
and `--animation` takes a JavaScript module file or its source text. All
three resolve into OUT's unified schema-9 sidecar.

```bash
cadgen step build vendor/hinge.step STEP/hinge.step \
  --kinematics '{"mates": [{"name": "swing", "kind": "revolute",
                            "parent": "#body", "child": "#lever",
                            "axis": "#lever.f2", "limits": [0, 90]}],
                 "poses": {"open": {"swing": 45}}}'
```

Re-running is a no-op; editing only these annotations refreshes the sidecar
without re-emitting a byte. Vendor metadata (PMI, GD&T) does not survive the round trip.
**Choose the door by how the model will evolve**: a shape you will keep changing
belongs in a model script (a thin wrapper that reads the foreign STEP), while
a one-shot canonicalization or annotation of a file you do not own is exactly
what `step build` is for.

## Optional-module assemblies

A model that imports several part modules and SKIPS the ones that do not exist
yet is a useful pattern for parallel work — the assembly stays renderable while
individual parts are still being written. It has one sharp edge.

The model's closure is computed from the modules it ACTUALLY IMPORTED at build
time. A module that did not exist during the build was never in the closure,
so its later appearance cannot make the model stale, and every door keeps
reading the old document's tree — no error, no warning. Run the model script
with `--force` after adding a previously absent part module.

## After generation

- Confirm the process succeeded and each declared output exists and is
  non-empty (the stdout line names the document; `--json` adds the `tree`
  hash).
- Run the Python geometry checks selected for this design per
  `inspection-and-validation.md`:

```bash
python tmp/check_model.py
```

## Progress and runtime diagnostics

The warm daemon is on by default. `cadgen daemon status` shows running and
queued work. Jobs may wait for CPU or memory admission; concurrency and worker
lifetimes are runtime details, specified in the installed package's `STORE.md`.
For diagnosis, `CADGEN_DAEMON=0 python part.py` uses transient workers with the
same geometry/output contract.

Results go to stdout; progress and errors go to stderr. Model runs accept
`--json` for machine-readable results and `--verbose` for timings/full tracebacks.
For long model bodies, optional `report` and `track` calls expose progress:

```python
from cadgen import report, track

# Inside a model body:
report("ribs")
for rib in track(ribs, label=lambda r: r.name):
    ...
```

Use one cache store for normal project work. A separate `CADGEN_CACHE_DIR`
is useful for isolated tests, but two stores writing the same project outputs
can cause repeated freshness misses. The store holds derived results only.
Prefer a targeted `--force` or `cadgen store forget <model>.py` when diagnosing
one stale result; `cadgen store gc` removes unreachable cache data.
