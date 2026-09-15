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

Every run keeps the model's result in the store current — a **tree** of exact
`.brep` + `.surf` components plus links to its children's trees — and writes
every output the model declares from that result. Unchanged sources are a
fast no-op. The default `.step` is the sibling `<stem>.step`; relocate it
durably with `@step(out="path/to/out.step")` (relative to the script). There
is no per-run output override: a model has one set of outputs, declared in its
decorators, and the store's record of it is keyed by the script.

Rules the decorator enforces:

- **The decorator only declares.** Nothing runs at decoration or import time.
  A model file without `if __name__ == "__main__": <model>()` never builds.
- **A top-level call builds.** Calling the decorated name when no build is in
  progress (`__main__`, a REPL) runs the pipeline and returns `None`; a failed
  build exits with the pipeline's code. It takes no arguments.
- **A call inside a build composes.** From another model's body the same name
  returns the shape: the child is built if it is stale (writing ITS outputs
  and record), otherwise loaded from the store, and either way its result is
  linked into the parent's. Composition is ordinary Python; there is nothing
  to cache by hand and no composition API.
- **One model per file is the recommendation, not a rule.** A model's identity
  is `script.py::function`; a file holding one model is named by its path alone
  (`python plate.py`, `store why plate.py`). Several decorated functions in one
  file are allowed — a small variant family — and each is its own record,
  output (a sole model writes `<file>.<fmt>`; models sharing a file write
  `<function>.<fmt>`) and job, built by its
  own call under `__main__`; name one as `plate.py::plate_wide` in `store why`
  and `store forget`. They share the file's closure: editing any of them makes
  all of them stale, so a family that changes independently belongs in
  separate files.
- **Calling a model from plain Python returns its geometry.** Outside a build,
  `plate()` builds (or finds current) and returns the model's tree as a
  `Compound` — what a parent composing it would get — so a script, a notebook
  or a REPL can read bounds, faces or volumes straight off a model. A drawing
  returns `None`.
- **A model takes no parameters.** It is one configuration of one set of
  outputs, so there is nothing for an argument to select; the decorator
  refuses a parameter list. Parametric geometry is a plain factory the model
  calls:

  ```python
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
  single solid as one component. Nothing is declared or inferred about it —
  `inspect` and the run both report `part`/`assembly` off the tree.
- **Outputs are what the decorators declare.** `@step` writes the `.step`.
  Mesh outputs are `@stl`/`@threemf`/`@glb` stacked on the model, tolerances
  on the decorators (`supported-exports.md`). **A model may declare no STEP at
  all**: `@stl`/`@threemf`/`@glb` with no `@step` is a full model — same tree,
  record, build, no-op and composition — that writes its meshes and no
  `.step`, no sidecar. STEP is one output kind, not a requirement.
- Options on `@step`: `out=`, `mesh_tolerance=`, `mesh_angular_tolerance=`,
  `kinematics=` (`kinematics.md`). **No decorator argument changes the
  geometry a model produces**: they decide where the files land, how they are
  written, and what the sidecar declares. No decorator names JavaScript:
  choreography is the render module beside the document
  (`STEP/<name>.step.js`), which the viewer loads by name and no build reads.
  Everything a model declares about itself lives in its decorators, and a
  child's declarations never ride up into a parent.

**Imports:** `from cadgen import build123d as bd` is the canonical import — a
lazy, transparent re-export (same names, same objects on first touch), so a
current model's re-run never pays the ~2.5s kernel import: the freshness gate
and the warm-worker handoff fire before any `bd.` attribute resolves. Raw
`import build123d` still works, just slower on re-runs (the build prints a
one-line hint). Keep `bd.<anything>` out of module-level constants and default
arguments for the same reason.

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

A model that DECLARES something beyond geometry — kinematics, animation, or
mesh exports — gets a sidecar BESIDE THE OUTPUT (`<name>.step.json`) carrying
those sections. A plain model writes NO sidecar: its record in the store is
what makes reruns no-op. Imports write none of it. The written STEP file
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

**Every build is parallel.** A child call returns at once with a lazy shape
and submits the child's build to the pool; the body keeps calling siblings,
each landing on its own worker; the parent waits when it first reads geometry
— normally the closing `bd.Compound(children=[...])`, after every sibling has
been submitted. Placement (`moved`, `Pos/Rot/Location *`), `.label` and
`.color` are deferred; anything that reads geometry (`.faces()`,
`.bounding_box()`, a boolean, `copy.copy`) forces that child there, so
parallelism follows the dependencies the body actually expresses. Nothing is
annotated and nothing is scheduled ahead of time.

**Dependency is pull.** A parent depends on each child by RESULT: its record
pins the child's tree hash, so a child edit that yields identical geometry
leaves the parent current, and an edit that does not reach a child skips that
child's Python and kernel work entirely. **Rebuilding a child does not rebuild
the assemblies that use it** — run the parent to pick up the change
(`python src/robot.py` builds whatever is stale beneath it and links the
rest). A parent finished against a child that changed during its build says so
(`already stale: … rerun`).

**Builds never wait on or cancel one another.** Two runs of one model both
run to completion; each publishes what it built and the store keeps the one
whose sources match the files as they are now. Editing a child while its
parent builds leaves the parent finished against the child it pinned — its
next gate says stale (`store why` shows the pinned vs current tree). There is
no lock anywhere.

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
input. The render module beside the document (`<name>.step.js`) is NOT one —
it is the viewer's, and editing it never makes a model stale.

Every decorator argument is ordinary Python, evaluated when the module is
imported: `out=f"{FOLDER}/{NAME}.step"`, `mesh_tolerance=TOL` with `TOL` from
`lib/`, a path built from a constant — all fine, and nothing is read off the
source text. The values feeding them are tracked like any other input (a
`lib/` module by file, a model-file constant by value), so changing the
constant behind an `out=` makes the model stale. The module top must still stay
kernel-free: what a door pays to learn a model's declarations is one import of
the file.

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

### Mirrored parts are their own models

STEP cannot express a reflection, so a right-hand part is not a mirrored
placement of the left-hand one: give it its own model file that calls the same
factory, and let the assembly place two ordinary children.

```python
# src/lib/bracket_shape.py — the factory (plain module, no decorator)
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

Mirroring a child inside the parent (`bd.mirror(bracket_left(), ...)`) is
legal — the parent then owns the mirrored geometry as its own components — but
the right-hand part has no STEP of its own and no place to declare exports or
mates. Prefer the model.

### Inputs: reading a STEP file the model does not generate

Use `cadgen.read_step`, not `build123d.import_step`. It returns the same
shape, served from the op memo on a warm run, and — the part that matters — it
RECORDS the file's content hash as a build input. Replacing the vendor STEP
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

For structuring multi-part projects (folder layout, shared `src/lib/` code,
commit policy), read `project-layout.md` and `project-template.md`.

## Freshness: `cadgen store why`

`cadgen store why <model>.py` (or a generated `.step`; the store remembers
which script wrote it) is the one freshness door. It prints the gate's verdict
clause by clause and why:

```text
model   /abs/src/frame.py
verdict STALE  (child result moved: standoff.py)
  [ok] 1 record present
  [ok] 2 closure 1 files unchanged
  [x] 3 children (2)
        [ok] /abs/src/plate.py  pinned 51b0eafbbc5f  current 51b0eafbbc5f
        [x] /abs/src/standoff.py  pinned 33df4f5cf2ee  current 91667e73758b  child result moved
  [ok] 4 tree 7dc0cee81f77 complete
  [ok] 5 outputs (1)
        [ok] /abs/STEP/frame.step
closure b99f36c995b8  files: frame.py
tree    components 0  occurrences 0  links 3
        link plate -> 51b0eafbbc5f
        link standoff_left -> 33df4f5cf2ee
        link standoff_right -> 33df4f5cf2ee
```

Here `standoff.py` was edited and rebuilt on its own; the frame still pins
the old tree, so it is stale until `python src/frame.py` runs — the pull
semantics above, made visible. The exit code is 1 for stale, 0 for current;
`--json` gives the same verdict as data. The five clauses: (1) a record
exists; (2) the closure files — and any constant imported by value — hash as
recorded; (3) every child is current and its tree is the one pinned; (4) the
tree and its components exist in the store; (5) every declared output matches
its recorded sha. Mesh tolerances and argv flags are not inputs. Reach for
`store why` whenever a model did or did not rebuild when you expected it to,
before reaching for `--force`.

## Generated assemblies

An assembly is a model whose return places children (a `Compound` of parts
or of other models' results); the tree records that structure and `inspect`
reports it as `assembly`. Passing a generated assembly's exported `.step` to a tool treats it as a document and
loses source-level composition; work with the `.py` source. Prefer
`cadgen.assembly.AssemblyHelper` so native labels, named mate frames, and
source-level relationships are preserved before STEP export (see
`positioning.md`).

## Imported STEP/STP files

An imported STEP/STP file needs no model script and no preparation step. Hand
it straight to `cadgen step inspect`, `cadgen step snapshot`, or a mesh door:
each compiles a tree from the file's bytes on first use (a job in the pool,
shared with the CAD Viewer), and its part/assembly kind is inferred from the
STEP product hierarchy.

```bash
cadgen step inspect refs path/to/imported.step --facts
cadgen stl build path/to/imported.step meshes/imported.stl
```

To produce STL/3MF/native GLB files from an imported STEP, pass it to the
matching format door with an explicit OUT (an imported file declares nothing, so
a bare door has no variants to produce); read `supported-exports.md`.

### Re-emitting a foreign STEP as your own

A STEP written by another kernel round-trips through cadgen with
`cadgen step build IN OUT`: OCCT reads it, the tree is built, and the
canonical writer emits it, so OUT's bytes are deterministic and identical on
every run. The same command ANNOTATES a document that has no model script —
`--kinematics` takes the whole space (`{mates, couplings, poses, at}`, the same
vocabulary the decorator takes, as inline JSON or a `.json` path) and
`--animation` copies a `.js` module's text into OUT's sidecar.

```bash
cadgen step build vendor/hinge.step STEP/hinge.step \
  --kinematics '{"mates": [{"name": "swing", "kind": "revolute",
                            "parent": "#body", "child": "#lever",
                            "axis": "#lever.bore", "limits": [0, 90]}],
                 "poses": {"open": {"swing": 45}}}'
```

Re-running is a no-op; editing only the kinematics refreshes the sidecar without
re-emitting a byte. Vendor metadata (PMI, GD&T) does not survive the round trip.
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
explicitly after adding a part module rather than relying on the gate.

## After generation

- Confirm the process succeeded and each declared output exists and is
  non-empty (the stdout line names the document; `--json` adds the `tree`
  hash).
- Run the baseline inspection and any spec-driven checks per
  `inspection-and-validation.md`:

```bash
cadgen step inspect refs path/to/model.step --facts --planes --positioning
```

## Workers and the daemon

Every build is a job on a worker; every worker has build123d imported. A warm
daemon runs them **by default** — the decorator hands a directly-run script to
it before any kernel import — and `CADGEN_DAEMON=0` uses transient workers
instead:

```bash
python path/to/part.py              # warm: persistent workers
CADGEN_DAEMON=0 python part.py      # transient workers, spawned for this run
```

- **One worker per model.** A request lands on the worker bound to its model
  script; a busy worker means a second one (an *extra*) runs the job now; a
  model with no worker takes a warm spare (`CADGEN_DAEMON_SPARES`, default 2,
  refilled in the background). Nothing waits on another build and no worker
  count is capped.
- **Children build in parallel.** Inside a body, each child call submits that
  child to the pool and returns at once; siblings build on their own workers
  while the body continues, and the parent waits only when it first reads the
  geometry.
- **One running build per core.** `N = os.cpu_count()` jobs run at once
  (`CADGEN_JOBS` overrides); the rest queue in order. A parent waiting on its
  children holds no slot, so a deep tree builds on a single slot. Hitting the
  limit during a fan-out is normal and costs no wall time.
- **Idle workers unbind after 10 minutes** (`CADGEN_DAEMON_IDLE_UNBIND`,
  seconds) and return to the spare set; the daemon exits after an hour with no
  request (`CADGEN_DAEMON_IDLE_TIMEOUT`). Both are about RAM; neither ever
  blocks a build.
- **No memory ceiling and no worker cap.** Unlimited memory is the operating
  assumption. A worker the OS kills mid-job is reported as a dead worker with
  its exit status, the job it held, and the exact `CADGEN_DAEMON=0 ...` rerun;
  nothing is retried silently.
- **`CADGEN_DAEMON=0` is still parallel.** Transient workers are spawned for
  the run (each paying one kernel import, concurrently), inherit the
  environment — so a test's `CADGEN_CACHE_DIR` isolates its store — and exit
  with the run. There is no daemon job ledger in this mode, so the CAD Viewer
  does not see such builds in progress.
- **`cadgen daemon status`** reports each worker's model, whether it is busy,
  its job count and whether it is an extra; the spare count; and `jobs running
  n/N, queued m` — the first place to look when a build seems slow.
- Doors (`inspect`, `snapshot`, the mesh doors) never run a body and take no
  slot; a compile of a document with no tree is the one door operation that
  is a job.
- The daemon runs on Windows too (a named pipe instead of a Unix socket). It
  is per cadgen install; `CADGEN_DAEMON_SOCKET` overrides the address, and a
  `.log` beside it holds lifecycle and C-level OCP noise. When cadgen itself
  changes, the daemon notices the version token mismatch, drains its jobs and
  exits; the next client starts a fresh one.

Cold and warm builds write identical bytes for every format.
