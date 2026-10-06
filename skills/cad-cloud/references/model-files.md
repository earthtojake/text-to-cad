# Model files

A build runs each `entry` in order as `python <entry>` from the build root, with
the released cadgen; the first failure stops the build. This file is the contract
those scripts follow. The `cad` skill's `step-generation.md`, `positioning.md`
and `build123d-modeling.md` go deeper when that skill is installed.

## The contract

- **The decorator only declares.** Nothing runs at decoration or import time.
  End the entry with `if __name__ == "__main__": <model>()`: calling the
  decorated name when no build is in progress builds it.
- **A call inside a build composes.** From another model's body the same name
  returns the shape: the child is built, writing its own outputs, and its
  result is linked into the parent. Composition is ordinary Python.
- **One decorated model per entry script.** The script and its declared outputs
  share a stem: `plate.py` writes `STEP/plate.step`, `STL/plate.stl` and so on.
  Stack the output decorators on that one function. Shared factories live in
  helper modules (`src/lib/`), which are not entries.
- **A model takes no parameters.** It is one configuration of one set of
  outputs. Parametric geometry is a plain factory the model calls; a second
  configuration is a second model with its own outputs (`plate_wide.py`).
- **The return is a bare build123d shape.** A `Compound` that places children is
  saved as occurrences, a single solid as one component. The decorator refuses
  a dict.
- **No decorator argument changes geometry.** `out=`, `mesh_tolerance=` and
  `mesh_angular_tolerance=` decide where files land and how they are written.
- **Imports.** Use `from cadgen import build123d as bd`, a lazy re-export, so
  the CAD kernel loads only when geometry is built. Keep geometry, file reads and
  `bd` attributes out of module-level constants and defaults, and add
  `from __future__ import annotations` when annotations mention `bd` types.
  Imports resolve as for `python script.py`: the script's folder is on
  `sys.path`, plus the build's `pythonpath`.

```python
# src/plate.py
from __future__ import annotations

from cadgen import build123d as bd
from cadgen import step


def _plate(width: float, thickness: float) -> bd.Shape:
    return bd.Box(width, 20, thickness)


@step(out="../STEP/plate.step")
def plate():
    return _plate(width=40.0, thickness=6.0)


if __name__ == "__main__":
    plate()
```

## Outputs

`out=` is relative to the script, so `src/plate.py` with
`out="../STEP/plate.step"` writes `STEP/plate.step`. Without `out`, the file
lands beside the script. A build's outputs are the files its scripts write. Each
viewable one (STEP, STL, 3MF, GLB, DXF, URDF, SRDF, SDF) opens at its own link,
and the main file is the STEP named for the first entry, which is why a script
and its outputs share a stem. A file the build only reads, such as a sent vendor
STEP, is an input with no link; a file with an unrelated suffix, or under a
top-level `tmp/`, is dropped.

Stack mesh decorators for STL, 3MF or GLB:

```python
# src/spacer.py
from cadgen import build123d as bd
from cadgen import glb, step, stl, threemf


@step(out="../STEP/spacer.step")
@stl(out="../STL/spacer.stl")
@threemf(out="../3MF/spacer.3mf")
@glb(out="../GLB/spacer.glb")
def spacer():
    return bd.Cylinder(6, 3) - bd.Cylinder(2.5, 3)


if __name__ == "__main__":
    spacer()
```

- A model may declare no `@step`: `@stl`, `@threemf` or `@glb` alone is a full
  model that writes its meshes and no `.step`. Selection and measurement need a
  STEP, so keep `@step` when either matters.
- `mesh_tolerance=` is a chord tolerance relative to each component's bounding
  diagonal (default 1.5e-3, at most 0.05); `mesh_angular_tolerance=` is in
  radians (default 0.35). The defaults suit most parts.
- A GLB is a Y-up glTF file for other tools.
- For a 2D drawing, `$dxf` covers `@dxf` scripts; a drawing is its own entry,
  never in the same script as a `@step` model.

## Assemblies

A child is just an import: `from pin import pin` binds the model and never
builds it. Calling `pin()` inside the assembly's body builds the child and
returns its shape.

```python
# src/pin.py
from cadgen import build123d as bd
from cadgen import step


@step(out="../STEP/pin.step")
def pin():
    return bd.Cylinder(3, 20)


if __name__ == "__main__":
    pin()
```

```python
# src/assembly.py
from cadgen import build123d as bd
from cadgen import step

from pin import pin


@step(out="../STEP/assembly.step")
def assembly():
    plate = bd.Box(40, 20, 6)
    plate.label = "plate"
    left = pin().moved(bd.Location((-12, 0, 13)))
    left.label = "pin_left"
    right = pin().moved(bd.Location((12, 0, 13)))
    right.label = "pin_right"
    return bd.Compound(children=[plate, left, right], label="assembly")


if __name__ == "__main__":
    assembly()
```

Send both scripts with `entry` set to `src/assembly.py`; the build also writes
the child's output, `STEP/pin.step`.

- Place a child's shape as it came back: `moved()`, `Pos/Rot/Location * child`,
  relabelled or recolored. The parent then links to the child's tree, stored
  once and shared by every placement. Modify it (a boolean, a mirror) and the
  parent owns that geometry instead.
- Never use `located()` for placement: it deep-copies the geometry, which makes
  it the parent's own component instead of a link, and it replaces a rotation
  applied earlier.
- A child's mates, kinematics and animation do not ride up into the parent;
  declare what the assembly needs on the assembly.
- Mirror inline when the geometry belongs to the current model:
  `bd.mirror(left, about=bd.Plane.YZ)`. Use a separate model when the mirrored
  part needs its own outputs.
- Native build123d joints (`RigidJoint`, `RevoluteJoint`, `LinearJoint`,
  `connect_to()`) place parts from reusable datums. They position geometry in
  the source; they are not stored STEP constraints.
- Label occurrences by role (`pin_left`, `m3_screw:front_left`) so references and
  checks can name them. A feature fused into or cut from a body keeps no label.

## Inputs

Every file a build reads must be in `files`: the sandbox has no network, and
only the standard library, build123d (through `cadgen`) and what cadgen installs
with it (numpy, shapely, ezdxf, Pillow, matplotlib) are available. Read a vendor
or downloaded STEP with `cadgen.read_step`, which returns native geometry
with the document's colors, and anchor the path on `__file__` so the script runs
from any directory:

```python
from pathlib import Path

from cadgen import read_step, step

_HERE = Path(__file__).resolve().parent


@step(out="../STEP/servo.step")
def servo():
    return read_step(_HERE / ".." / "imported" / "sg90_servo.step")
```

Data files (a JSON table, a CSV) are read the same way and sent the same way.
Never `read_step` a model's own output: a model whose input changes on every run
has geometry that depends on what the last run left behind. To reuse geometry the
project already builds, call that model.

## Appearance

Native `Color` channels are linear RGB; `cadgen.srgb` converts a display hex
value. Set color on leaf occurrences: a color on a group compound does not
propagate to its leaves.

```python
from cadgen import srgb

body.color = srgb("#2E3742")
glass.color = srgb("#38414D", 0.42)
```

Named materials (`@step(materials=...)`) and kinematics (`@step(kinematics=...)`,
joints and poses) are declared on the model; the `cad` skill's
`build123d-modeling.md` and `kinematics.md` document them when it is installed.

## Construction notes

- `.moved(loc)` and `Location * shape` compose a placement; `.located(loc)`
  replaces it.
- Primitives start at their own datum: set `align=` deliberately when placement
  depends on it.
- Select a fillet's or chamfer's edges from the solid after its last operation.
  An edge held from before it may not be the solid's own: a fillet skips it
  silently and fails when none is left; a chamfer fails on it.
- A valid shape can still have negative volume. Check each solid's signed volume;
  aggregate volumes can cancel.
- Apply finishing features late, and batch independent cuts when that avoids
  rebuilding the same intersection network.
- Do not drop or approximate a requested feature silently. Report what cannot
  be built.

## Speed

Every build starts cold in a fresh sandbox, so a build takes as long each time.
Independent child models build in parallel within the sandbox's CPUs. Give a
part that dominates the build time its own model script, check it with its own
`entry`, then call it from the assembly.
