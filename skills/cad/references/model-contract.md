# Models

Read this file when writing or editing a model script, composing models into
assemblies, choosing what to mark `@memo`, reading files into a model, or working out
why a run ran what it ran.

## Contents

- [A model is a function](#a-model-is-a-function)
- [Assemblies call their parts](#assemblies-call-their-parts)
- [What a run runs](#what-a-run-runs)
- [`@memo` marks stages](#memo-marks-stages)
- [Inputs](#inputs)
- [Documents and the server](#documents-and-the-server)

## A model is a function

- **Only a call builds.** Decorating a function and importing its script build nothing,
  so a script's `__main__` chooses, in plain Python (an argument, a loop), which models
  its run builds.
- **The handle a call returns** has `.name` and `.report` (how it built) beside its id,
  page, shape and export. `.shape` is brought into the calling process, and the kernel
  loaded there, when it is first read and never before, so a script that only builds
  pays nothing for it. In a plain script (a check, a drawing) it is the tree a calling
  body reads, every part placed, named, coloured and given its material, without its
  joints. Verbs take the handle (`model.export(handle, ...)`, `posed(handle, state)`).
- **A file decorator takes `@model`'s place, never beside it**: `@step("part.step")`,
  and `@xbf`, `@glb`, `@stl`, `@threemf` and `@dxf` likewise with a path, declare a model
  whose run also writes those files
  ([model page or file page](exports.md#model-page-or-file-page)).
- **Kernel objects belong in bodies.** `import build123d as bd` loads no kernel until an
  attribute is read from `bd`, which in a body happens in the server. Read at module
  level (`from build123d import Box`, an `Axis`, a `Location`, a colour palette, a
  shape, a `bd.Align.CENTER` default argument) it loads the kernel in the script's own
  process, 2 to 3 s on every run, a run that rebuilds nothing included. Keep numbers and
  tuples at module level.
- **A body that raises fails its model**: the run prints the model's frames and exits 1,
  and the model's page says the run failed.
- How a script's imports resolve is in
  [imports and shared code](project-layout.md#imports-and-shared-code).

## Assemblies call their parts

```python
# src/assembly.py
import build123d as bd
from cad import model

from plate import THICKNESS, plate      # src/plate.py: a part model and a constant of its script
from standoff import standoff_m3        # src/standoff.py: one configuration of a part

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

- **A child builds in the same run** and keeps its own document and id, which every
  command answers. Its `.shape` is what its body returned, before the caller placed or
  labelled it. Called twice it is built once, each call a new placement of the one
  result; called only for the files it declares, it is a bare call.
- **A jointed child brings its mechanism**: its joints, states and sequences are in the
  assembly's document too. The joints between children are written in the assembly's
  body ([kinematics](kinematics.md#joints-place-parts-and-make-the-mechanism)).
- Placing a part and what a placement shares are in [positioning](positioning.md); how
  labels name occurrences, in [references](inspection-and-validation.md#references).

## What a run runs

A run replays what an edit did not reach, at two levels. Each kernel operation is kept
by its inputs and the body that ran it, so after an edit only what is downstream of the
change runs. Above that a whole body (a model's, or a `@memo` call's) is replayed, not
run, while what it is made of is unchanged: the code it reaches through every
first-party module it imports (functions by their code, not their lines, comments or
docstrings; the constants and defaults they read) and every file it reads, by its bytes
([inputs](#inputs)). The run's lines say which:

```text
built src/assembly.py::assembly warm in 0.09s: bodies 2 run, 1 replayed; 3 misses, 2 hits; body 0.02s, names 0.00s, document 0.00s
  parts 3 · bounds 60 × 44 × 16 mm (was 60 × 40 × 16) · joints 0 · sequences 0 · changed 1
  rebuilt: plate.py: DEPTH changed
  src/plate.py::plate, a child
  src/standoff.py::standoff_m3, a child
```

That run followed an edit of the plate's depth: the plate's body and the assembly's ran,
the standoff's replayed, and of the kernel's five operations two were hits. `warm` is a
worker that built the script before. `cold` is a fresh one with nothing kept, so what it
builds it builds whole: after a server restart, or once the server retired the script's
worker, which a `cold: ...` line under the run's explains. A run of an unchanged model
says `took ...: nothing ran`.

What makes a body run on every build is counted on the run's line (`2 misses, 0 hits, 2
uncached`) and named under it (`not retained: ...`):

- **A shape made past build123d.** One made by calling `OCP` directly (a
  `BRepOffsetAPI_MakeFilling`, a sewing) has no key, so every operation downstream of it
  runs on every build and its body is never replayed. Reach for `OCP` to ask a question;
  to make a shape, use build123d's operation (`Face.make_surface_patch` for a filled
  cap), or make it in a `@memo` function of values that returns it as made.
- **An attribute of your own on a shape** (`shape._stood = location`) is part of that
  shape's key while its value is plain data: a number, a string, a `Location`, a tuple or
  a dict of them. A function or an object of your own cannot be compared, so every
  operation on that shape runs on every build (the line says `uncached`, and blames a
  shape no keyed call made): keep such data beside the shape, in a dict by label.
- **A file read past the server's readers**: [inputs](#inputs).

What the server cannot see is yours to keep out of a body. Beside the clock, environment
variables and randomness, that is a file only tested for (`Path.exists`), a folder
listed (`glob`, `os.listdir`) and state one body leaves in a module for another.
`bracket.build(verify=True)` tests it: it runs every body the server would replay and
compares each fresh result with the kept one (`.models[0]["verify"]`).

`bracket.build()` returns the run's report as data, a dict per model in `.models`: `id`,
`memo`, `bodies` (each `run`, `replayed` or `loaded`), `retention` (each body's
`fallbacks`, the reasons it runs on every build, and the files it `reads`), `timings` and
`children`; `build(profile=True)` adds function timings.

```bash
cad run -c "import bracket; print(bracket.bracket.build().models[0]['retention'])"
```

## `@memo` marks stages

`@memo` (`from cad.build123d import memo`) marks a function the server may replay whole
instead of running. A call of it in a run is keyed by its code and its arguments, and a
second call with the same arguments in one run is a new placement of the first one's
result. Outside a run it is its function.

- **Mark rarely.** The server already replays every kernel operation of any model, so a
  memo hit saves only the Python cost of those calls (0.1 to 0.4 ms each). Mark a function
  that holds seconds of kernel work an edit elsewhere leaves alone, roughly a thousand
  kernel calls or more: whole sub-assembly stages (measured: 1.3 to 3 s each, twice as
  fast on an edit). Never mark per part, or a helper called many times: those measured
  under 0.1 s.
- **Mark the body several models share.** A kernel operation is kept for the body that ran
  it (a model's, or a `@memo` call's), never shared between two models, so nine models
  that pose one robot each build the robot again (each run's line says `0 hits`) unless
  its builder is marked: then it runs once and the others replay it
  (`bodies 1 run, 1 replayed`).
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

A run's progress (a bar on a terminal, the same on the model's page) names each `@memo`
call and each child model as it begins, so a long body split into stages shows where its
time goes.

## Inputs

What a body reads is an input of its run, by the file's bytes, and a changed file
re-runs the body that read it. Anchor paths on the script, so a run reads the same file
from any working folder:

```python
from pathlib import Path

import build123d as bd
from cad import model, stl, xbf

HERE = Path(__file__).resolve().parent


@model
def rig():
    motor = xbf.read(HERE / "../vendor/motor.xbf")
    motor.label = "motor"
    pcb = stl.read(HERE / "../scans/pcb.stl").bounding_box()   # an input, by the scan's bytes
    tray = bd.Box(pcb.size.X + 6, pcb.size.Y + 6, 6)
    tray.label = "tray"
    return bd.Compound(children=[tray, bd.Pos(0, 0, 20) * motor], label="rig")
```

- **`step.read(path)` and `xbf.read(path)`** copy a document's geometry into the model as
  a build123d compound tree: each assembly a `Compound`, each part named, coloured and
  given its material as the file has them, each element keeping the name the file gives
  it. An xbf's joints, mechanism states, sequences and animations are not imported: a
  part is a part. Take the tree's parts placed with `leaves(tree)` (`cad.build123d`),
  never `located` or `moved` on a node of it, which copies the whole assembly
  ([opening geometry](inspection-and-validation.md#opening-geometry)).
- **A vendor STEP is converted once**: `cad step export vendor.step vendor.xbf` writes an
  xbf of it, which `xbf.read` reads many times faster than `step.read` parses the STEP
  (seconds against most of a minute for a large assembly), with the same names. Keep the
  xbf beside the STEP and read the xbf.
- **A STEP that names other files as its parts** (an external reference, written by a
  CAD tool's multi-file export) is refused by name, here and in the viewer and
  `cad <type> export`: export it again from its CAD tool as one file.
- **`stl.read(path)`** reads an `.stl` as data, never a shape: `vertices`, `triangles`,
  `name` and `bounding_box()`. A document holds B-rep alone, so a mesh is measured and
  built from, never placed in a model.
- **Every file the body's Python opens** for reading is an input too: `open`,
  `json.load`, `Path.read_text`, `np.loadtxt`. A file opened only for writing is not.
- **build123d's `import_step`, `import_brep` and `import_stl`** are inputs by the file's
  bytes as the server's readers are. Prefer `step.read` (names, colours, materials, the
  assembly tree) and `xbf.read` (fastest); `import_stl` makes a mesh, which no model
  holds.
- **A read past the server runs the body on every run**: OCCT's readers driven directly
  (`BRepTools.Read_s`, `STEPControl_Reader`, ...) read files where the server cannot hear
  them.

## Documents and the server

- **The id names the model, not a state of it.** It comes from the script's path and the
  function's name (`bracket.id`, without a call), so two scripts may use one function
  name, and a renamed function is a new document. `@model(name="bracket")` takes the id
  from the script's folder and that name instead, whichever file of the folder declares
  it; one name declared twice in a folder is refused, naming both declarations and the
  way out.
- **What names the state** is the key of the code and inputs the document was built
  from, `handle.report["closure"]["key"]` (`cad model inspect "$ID" --query closure`
  prints the closure). A file derived from a document (a simulator's description, a GLB
  beside a film) that records the key can tell whether the document has been built from
  other sources since. The key is `None` where the model's code cannot be keyed.
- **A document is kept until it is deleted**, across server restarts: its id answers
  every command as last built, and one the server has lost is refused with the `cad run`
  that brings it back. `cad delete <id>` (or a script's path, for every document of it)
  removes the record and the kept document, never a file of yours. Delete only what the
  person asked to delete, with `--yes`.
- **A shape with no script** (a notebook cell, a REPL, a script that only holds a
  shape) is handed over: `model(shape, name="plate")` makes a document of it, served on
  its page and exported like any other, and returns its handle. Joints, mechanism states
  and sequences on the shape go with it; a GLB's animations are passed as
  `animations=[...]`. Nothing builds it again but the program that handed it over. A
  decorated function in no saved file is refused, with these words.
- `cad server status` lists each document as `live` (its worker holds it), `held` (the
  server answers it without one, and a ref's `made_by` is null), `unsaved` (lost: run
  its script) or `detached` (its script is gone).
- **A build that runs away on memory is stopped.** A worker past
  `CAD_ENGINE_WORKER_CEILING_MB` (default: half the machine's memory) at two of the server's
  checks, half a minute apart, is stopped, and the build's error says so. The server reads
  the setting when it starts.
