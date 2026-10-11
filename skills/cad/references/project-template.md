# Minimal project starters

A single part and a small assembly, in the [project layout](project-layout.md)'s
default structure. Commands below run from the CAD project root.

## One part

`src/plate.py`:

```python
# src/plate.py
from cadgen import build123d as bd
from cadgen import step

WIDTH = 60.0
DEPTH = 40.0
THICKNESS = 4.0


@step(out="../STEP/plate.step")
def plate():
    body = bd.Box(WIDTH, DEPTH, THICKNESS)
    body.label = "plate"
    return body


if __name__ == "__main__":
    plate()
```

```bash
python src/plate.py
```

A second run reports `current`. A one-off part can instead use a flat folder and
`@step` with its default sibling output.

## An assembly

Start with the plate above and add `src/standoff.py`:

```python
# src/standoff.py
from cadgen import build123d as bd
from cadgen import step

HEIGHT = 12.0
OUTER_D = 8.0
BORE_D = 3.4


@step(out="../STEP/standoff.step")
def standoff():
    return bd.Cylinder(OUTER_D / 2, HEIGHT) - bd.Cylinder(BORE_D / 2, HEIGHT)


if __name__ == "__main__":
    standoff()
```

Then `src/assembly.py` places two instances on the top of the centered plate:

```python
# src/assembly.py
from cadgen import build123d as bd
from cadgen import step

from plate import THICKNESS, plate
from standoff import HEIGHT, standoff

PITCH = 30.0


@step(out="../STEP/assembly.step")
def assembly():
    base = plate()
    base.label = "plate"
    post = standoff()
    z = (THICKNESS + HEIGHT) / 2
    left = bd.Pos(-PITCH / 2, 0, z) * post
    left.label = "standoff_left"
    right = bd.Pos(PITCH / 2, 0, z) * post
    right.label = "standoff_right"
    return bd.Compound(children=[base, left, right], label="assembly")


if __name__ == "__main__":
    assembly()
```

```bash
python src/assembly.py
cadgen store why src/assembly.py
```

Running the root builds its stale children; running a child alone leaves the
root stale until the root runs. For mating datums and joint relationships, see
[positioning](positioning.md).

## Adding capabilities

| Need | Add |
| --- | --- |
| STL, 3MF or GLB output | A mesh decorator; a mesh-only model omits `@step`. See [exports](supported-exports.md). |
| Shared factory or hole pattern | A plain helper under `src/lib/`, with `src/lib/__init__.py`. |
| Left/right geometry | Mirror inline, or separate models for independent outputs/reuse; see [mirroring and caching](step-generation.md#mirrored-geometry-and-reusable-models). |
| Subassembly | A model that calls its child models. |
| 2D drawing | A separate drawing model using `$dxf`. |
| Vendor CAD | The source file under the format's `imported/` folder, read with `read_step` (an anchored path) or a wrapper model. |

Only kinematics, intrinsic materials or animation write a STEP sidecar;
declaring a mesh alongside STEP does not create one.
