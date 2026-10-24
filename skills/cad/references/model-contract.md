# Models

Read this file when writing or editing a model script, composing models into
assemblies, choosing what to mark `@memo`, reading files into a model, or working out
why a run ran what it ran.

## Contents

- [A model is a function](#a-model-is-a-function)
- [Parameters and configurations](#parameters-and-configurations)
- [`@memo` marks stages](#memo-marks-stages)
- [Assemblies call their parts](#assemblies-call-their-parts)
- [What a run runs](#what-a-run-runs)
- [Inputs](#inputs)
- [Documents and the engine](#documents-and-the-engine)
- [Progress and the report](#progress-and-the-report)

## A model is a function

```python
# src/plate.py
import build123d as bd
from cadgen import model

WIDTH, DEPTH, THICKNESS = 60.0, 40.0, 4.0


@model
def plate():
    body = bd.Box(WIDTH, DEPTH, THICKNESS)
    body.label = "plate"
    return body


if __name__ == "__main__":
    plate()
```

- **`@model` declares, a call builds.** Importing the script or defining the function
  builds nothing. A call the script's `__main__` makes builds the model in the engine
  and prints its `id:` and `view:`; a call another model's body makes builds it as a
  child, in the same run. Python decides which calls run; cadgen reads no script
  arguments.
- **A call returns the document, not the shape**: a handle with `.id`, `.url` (its
  page), `.name`, `.shape` and `.export(...)`. `.shape` is the built shape, brought into
  the calling process when it is first read (a check, a drawing) and never before, so a
  script that only builds pays nothing for it. Inside another model's body, `.shape` is
  the child's result itself: compose `plate().shape`.
- **One declaration per function**: bare `@model` (a document with no file) or its file
  decorators (`@xbf`, `@step`, ...: a document with those files), never both; stacking
  `@model` on a file decorator is refused. The function's name is the model's name:
  rename the function to rename it.
- **A model takes no parameters and returns a build123d shape**: a part, or a
  `Compound` of labelled children (an assembly). A 2D drawing returns 2D geometry and
  belongs to `$dxf`.
- **A script is plain Python, loaded afresh by each run.** Its folder is first on the
  module search path, so a module beside it imports by its own name. A script inside a
  package (its folder holds an `__init__.py`) is that package's module, so its relative
  imports (`from ..lib.dims import WIDTH`) work under `python proj/parts/block.py` and
  `python -m proj.parts.block` alike. An edit to any module it imports is read on the
  next run.
- **`import build123d as bd` costs nothing until it is used.** cadgen makes the import of
  `build123d` (and `OCP`) lazy: the module binds at once and the kernel loads on the
  first attribute anything reads from it, in the worker that builds the model. `from
  build123d import Box` reads the name, so it loads the kernel at that line; so does a
  kernel object made at module level (an `Axis`, a `Location`, a shape, a `bd.Color`
  palette, a `bd.Align.CENTER` default), on every run of the script, a run that rebuilds
  nothing included. Keep numbers (tuples) at module level and make kernel objects inside
  bodies. Write build123d attribute-style.
- **A body that raises fails its model**: the run prints the model's frames, exits 1,
  and the page says the run failed.
- **Called from a plain script** (a check, a drawing), a model is built in the engine
  and its call's `.shape` is the result as a build123d tree: every assembly a `Compound`,
  every part placed, named, coloured and given its material (its joints stay in the
  document: measure a pose by its posed model).

## Parameters and configurations

A model has no parameters, so a part's dimensions are the arguments of a plain helper
function, and each set of values is a model of its own: a configuration, with its own
id and page.

```python
# src/standoff.py
import build123d as bd
from cadgen import model


def standoff_body(height, outer_d, bore_d):
    post = bd.Cylinder(outer_d / 2, height) - bd.Cylinder(bore_d / 2, height)
    post.label = "standoff"
    return post


@model
def standoff_m3():
    return standoff_body(12, 8, 3.4)


@model
def standoff_m4():
    return standoff_body(16, 10, 4.5)
```

The helper needs no marking: the engine keeps every kernel operation it runs, keyed by
its inputs, so a run after an edit elsewhere replays it.

## `@memo` marks stages

`@memo` marks a function the engine may replay whole instead of running. A call of it in
a run is keyed by its code and its arguments, and a later run with the same key replays
it, names and all; a second call with the same arguments in one run is a new placement
of the first one's result. Outside a run it is its function.

- **Mark rarely.** The engine already replays every kernel call of any model, so a memo
  hit saves only the Python cost of those calls (0.1 to 0.4 ms each). Mark a function
  that holds seconds of kernel work an edit elsewhere leaves alone, roughly a thousand
  kernel calls or more: whole sub-assembly stages (measured: 1.3 to 3 s each, twice as
  fast on an edit). Never mark per part, or a helper called many times: those measured
  under 0.1 s.
- **Arguments by value**: numbers, strings, bools, `None`, tuples, lists and dicts of
  them, enums and paths; build123d's `Location`, `Vector`, `Axis`, `Plane`, `Color`
  and `Rotation`; a `Material`; a shape this run made. A call given anything else (a
  callable, an arbitrary object) runs every time.
- **Geometry back**: a shape, or a tuple, list or dict of shapes. A call returning
  anything else runs every time. Shapes it made with OCCT's own makers, returned as made,
  are keyed by the call: the way to keep a construction build123d has no operation for.
- **No methods**, and **pure**: it reads only what its key holds and changes nothing
  outside itself. A global it sets for another function, or an argument it mutates, is
  not seen, and a replay leaves it undone.
- **Return an assigned name.** A `@memo` function names what its `return` statement makes
  in itself, so marking a helper that returns `body - holes` renames those elements
  once; marking one that returns `body` renames nothing.

```python
from cadgen import memo, model


@memo
def drivetrain():                       # seconds of kernel work: a whole stage
    ...


@model
def rover():
    ...
```

Each call that runs every time is named, with why, in the report's
`retention.fallbacks` ([progress and the report](#progress-and-the-report)).

## Assemblies call their parts

```python
# src/assembly.py
import build123d as bd
from cadgen import model

from plate import THICKNESS, plate
from standoff import standoff_m3

PITCH = 30.0


@model
def assembly():
    base = plate().shape
    post = standoff_m3().shape
    z = (THICKNESS + post.bounding_box().size.Z) / 2
    left = bd.Pos(-PITCH / 2, 0, z) * post
    right = bd.Pos(PITCH / 2, 0, z) * post
    left.label, right.label = "standoff_left", "standoff_right"
    return bd.Compound(children=[base, left, right], label="assembly")


if __name__ == "__main__":
    assembly()
```

- **A child builds in the same run**, in the caller's worker, and its call returns its
  document's handle, whose `.shape` is what its body returned, before the caller placed or
  labelled it. A child called only for its own files is a bare call. It keeps its own document and id,
  which every command answers; its rebuild command is the parent's script. A child called
  twice is one model, built once.
- **Running a child's script alone builds the child** and leaves the assemblies that use
  it as they were: run the assembly to update them.
- **A placement shares its shape.** `Pos(...) * part`, `part.moved(...)` and
  `part.located(...)` place the same geometry again, so a part used ten times is one
  part placed ten times, in memory and in every file. A model that needs a B-rep of its
  own copies it with `BRepBuilderAPI_Copy`.
- **Label every placement**: the label names the occurrence in refs, the viewer's tree,
  a STEP's instances and a GLB's nodes. Siblings sharing a label are numbered among them
  (`finger.2`).
- **A child's mechanism stays in its own document.** An assembly's joints are written in
  the assembly's body, on the parts it places ([kinematics](kinematics.md)).

## What a run runs

Each script has a warm worker in the engine, and the worker keeps every kernel
operation its models ran, keyed by its inputs. A hit hands back the objects the first
run made; a miss makes everything downstream of it miss. So an edit costs what it
changed, and an element keeps the name its feature history gave it.

Above that, a body (a model's, or a `@memo` call's) is replayed, not run, while what it
is made of is unchanged:

- the code it reaches: the functions it calls, by their code (not their lines or
  docstrings), and the values it reads (module constants, defaults, data classes),
  through every first-party module it imports;
- every file it reads, by its bytes ([inputs](#inputs));
- the engine's own code and versions.

A comment, a blank line or a docstring re-runs nothing. An edit to a constant re-runs
the bodies that read it and the bodies that hold their results. A changed input file
re-runs the body that reads it. What the engine cannot see is yours to keep out of a
body: the clock, environment variables, randomness, a file only tested for
(`Path.exists`), a folder listed (`glob`, `os.listdir`), and state one body leaves in a
module for another. A body must be a function of its inputs.

A run after the engine restarted, or after the script's worker retired, starts a fresh
worker and builds cold. Every run says how each body went: `bodies 2 run, 1 replayed`.

`bracket.build(verify=True)` runs every body the engine would replay and compares each
fresh result with the logged one (`.models[0]["verify"]`); a body whose result differs
runs on every call for the worker's life. `bracket.build(profile=True)` adds function
timings of the run as it happened. `CADGEN_ENGINE_BODIES=0` turns replay off, and
`CADGEN_ENGINE_MEMO=0` every memo hit.

## Inputs

What a body reads is an input of its run, by the file's bytes, and a changed file
re-runs the body that read it:

- **`read_step(path)` and `read_xbf(path)`** copy a document's geometry into the model as
  a build123d compound tree: each assembly a `Compound`, each part named, coloured and
  given its material as the file has them, each element keeping the name the file gives
  it. An xbf's joints, mechanism states, sequences and animations are not imported: a part is a
  part. A STEP that names other files as its parts (an external reference, written by a
  CAD tool's multi-file export) is refused by name, here and in the CAD Viewer and
  `cadgen export`: export it again from its CAD tool as one file.
- **A vendor STEP is converted once**: `cadgen export vendor.step vendor.xbf` writes an
  xbf of it, which `read_xbf` reads many times faster than `read_step` parses the STEP
  (seconds against most of a minute for a large assembly), with the same names. Keep the
  xbf beside the STEP and read the xbf.
- **`read_mesh(path)`** reads an `.stl` as data, never a shape: `vertices`, `triangles`,
  `name` and `bounding_box()`. A document holds B-rep alone, so a mesh is measured and
  built from, never placed in a model.
- **Every file the body's Python opens** for reading is an input too: `open`,
  `json.load`, `Path.read_text`, `np.loadtxt`. A file opened only for writing is not.
- **build123d's `import_step`, `import_brep` and `import_stl`** are inputs by the file's
  bytes as the engine's readers are. Prefer `read_step` (names, colours, materials, the
  assembly tree) and `read_xbf` (fastest); `import_stl` makes a mesh, which no model
  holds: measure it with `read_mesh`.
- **A read past the engine runs the body on every run**: OCCT's readers driven directly
  (`BRepTools.Read_s`, `STEPControl_Reader`, ...) read files where the engine cannot hear
  them. Use `read_step`, `read_xbf`, `read_mesh` or build123d's importers.
- **Compose project models by calling them.** A file the project exported is a
  deliverable, not an input: reading it ties a model to an export's moment.

Anchor paths on the script, so a run reads the same file from any working folder:

```python
from pathlib import Path

import build123d as bd
from cadgen import model, read_mesh, read_xbf

HERE = Path(__file__).resolve().parent


@model
def rig():
    motor = read_xbf(HERE / "../vendor/motor.xbf")
    motor.label = "motor"
    pcb = read_mesh(HERE / "../scans/pcb.stl").bounding_box()   # an input, by the scan's bytes
    tray = bd.Box(pcb.size.X + 6, pcb.size.Y + 6, 6)
    tray.label = "tray"
    return bd.Compound(children=[tray, bd.Pos(0, 0, 20) * motor], label="rig")
```

## Documents and the engine

Every model a run builds is one document in the engine, with one id: a UUID derived
from the script's path and the function's name, the same in every process
(`bracket.id` in Python, and the handle's `.id`). Two scripts may use the same function
name. `@model(key="bracket")` (or `key=` on a file decorator) gives the document an id of
its key's instead, the same wherever the script moves; two declarations claiming one key
are refused, naming the other. The page is
`/<id>` on the engine's address; `cadgen export`, `snapshot` and `inspect`, and the
CAD app's tools, take the id and read the document as the engine holds it. No command
imports, runs or builds a script: editing the script changes nothing until Python runs
it again.

- **Documents outlive their workers.** A document stays held after its script's worker
  retires (`cadgen status`: `live` with its worker, `held` without one, where `made_by`
  is null), under one memory budget (`CADGEN_ENGINE_MEMORY_MB`, default a quarter of the
  machine's) that never drops a document a page watches.
- **The engine never reruns code.** A document it no longer holds (the engine restarted,
  or it dropped the document under its memory budget) is refused with the command that
  brings it back, `python <the program that built it>`, by the page, `cadgen inspect`
  and `cad_show` alike (`cadgen status`: `evicted`, `expired`, or `detached` once its
  script is gone). Running it updates the same document and its open pages.
- **Each document has a record** in cadgen's state folder (`documents/<uuid>/document.json`:
  the script and function that build it, its store, the rebuild command; never
  geometry). The home's Recents lists the records, most recent first. A record whose
  script is gone is detached: listed, saying so, with no rebuild command. Nothing else is
  written beside your files: no cache folder, and no record of a run.
- **A restart reopens what was built.** The engine keeps each model document's bytes in
  the platform's cache folder (`~/.cache/cadgen/documents/`), once it is idle, so after a
  restart its id answers every verb as last built (`cadgen status`: `held`, on `disk`).
  When a file its build read changed since, the page, `cadgen inspect` and `cad_show`
  say "the code changed since this was built" with the rebuild command; nothing reruns.
  The cache is bounded (`CADGEN_ENGINE_CACHE_GB`, default 4) and safe to delete.
- **`@model(store="memory")`** keeps a document in its worker's memory alone: no record,
  no Recents entry, gone when its worker retires or the engine exits. It suits a
  throwaway probe, and needs a saved script.
- **A shape with no script** (a notebook cell, a REPL, a script that only holds a
  shape) is handed over: `model(shape, name="plate")` makes a document of it, held,
  cached, served on its page and exported like any other, and returns the same handle,
  whose `.shape` is the shape passed. Its id comes from the calling script (or the working
  folder) and the name, or from `key=`. Joints, mechanism states and sequences on the
  shape go with it; a GLB's animations are passed as `animations=[...]`. Nothing builds
  it again: its record says a program the engine did not run showed it, so run that
  program again. A decorated function in no saved file is refused, with these words.
- `cadgen status` lists the workers and the documents the engine holds (`--json` as
  data); `cadgen stop` stops the engine and any older one still running. At most
  `CADGEN_ENGINE_WORKERS` workers live (default: the machine's cores); a worker idle for
  `CADGEN_ENGINE_WORKER_IDLE` seconds, or over `CADGEN_ENGINE_WORKER_RSS_MB` after a run,
  is retired, and its script's next run starts cold. `CADGEN_ENGINE_DIR` moves the
  engine's socket and lock (one engine per folder).

## Progress and the report

A run says where it is: on a terminal, `python model.py` draws a bar on stderr, and the
viewer's page shows the same. Nothing in the model says it: while a body runs, the bar
names each `@memo` call and each child model it calls, by its function's name, as it
begins, and counts it when it ends. A long body split into `@memo` stages (`finger`,
`palm_loft`) shows each:

```text
src/hand.py::hand
    building geometry  finger
```

Each model's report says how it built, then its children:

```text
built src/assembly.py::assembly warm in 0.03s: bodies 2 run, 1 replayed; 3 misses, 2 hits; body 0.00s, ...
  src/plate.py::plate, a child
  src/standoff.py::standoff_m3, a child
  id: 7a9724e8-f676-5676-acaa-160d7c6cc5fa
  view: http://127.0.0.1:54360/7a9724e8-f676-5676-acaa-160d7c6cc5fa?token=...
```

That run followed an edit of the plate's depth: the plate's body and the assembly's ran,
the standoff's replayed, and of the kernel's five operations two were hits.

`cold` is a fresh worker, `warm` one that built the script before; `bodies` counts
those run or replayed, and `misses` and `hits` the kernel's memo. `assembly.build()`
returns the same report as data, a dict per model in `.models`: `id`, `memo`, `bodies`
(each `run` or `replayed`), `retention` (each body's
`fallbacks`, the reasons it runs on every run, and the files it `reads`), `timings` and
`child_models`:

```bash
python -c "import bracket; print(bracket.bracket.build().models[0]['retention'])"
```
