# Minimal project starters

Choose the starter that fits the task. Create only the files it needs; rename
parts and change dimensions for the design. Keep an existing project's layout.
For a new project, use the location and conventions in [project layout](project-layout.md).
Commands below run from the CAD project root.

## One part

Create `src/plate.py`:

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
cadgen step snapshot STEP/plate.step tmp/plate.png
```

Review the PNG and check the dimensions needed by the design. A second model
run should report `current`. A one-off part can instead use a flat folder and
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
cadgen step snapshot STEP/assembly.step tmp/assembly.png
```

This is a placement example; add the fastening features the actual design needs.
Running the root builds its stale children. After a child changes, rerun the root.
Placed children use `.moved()` or `Location * shape` to keep their geometry shared.
For mating datums and joint relationships, see [positioning](positioning.md).

## Add capabilities only when needed

| Need | Add |
| --- | --- |
| STL, 3MF or GLB output | A mesh decorator; a mesh-only model omits `@step`. See [exports](supported-exports.md). |
| Shared factory or hole pattern | A plain helper under `src/lib/`, with `src/lib/__init__.py`. |
| Left/right geometry | Mirror inline, or use separate models for independent outputs/reuse; see [mirroring and caching](step-generation.md#mirrored-geometry-and-reusable-models). |
| Subassembly | A model that calls its child models; use folders as the project grows. |
| 2D drawing | A separate drawing model using `$dxf`. |
| Vendor CAD | Preserve the source under the format's `imported/` folder; use `read_step` with an anchored path or a wrapper model. |
| Durable requirement checks | `checks/` or the project's existing test directory; exploratory checks and images go in ignored `tmp/`. |

Only kinematics, intrinsic materials or animation require a STEP sidecar.
Declaring a mesh alongside STEP does not create one.

## Project bookkeeping

Add a short `src/README.md` catalog for a multi-model project:

```markdown
# Models

| Script | Output | Purpose |
| --- | --- | --- |
| plate.py | STEP/plate.step | Base plate |
| standoff.py | STEP/standoff.step | Repeated spacer |
| assembly.py | STEP/assembly.step | Plate with two spacers |

Build the assembly with `python src/assembly.py` from the project root.
```

Follow the repository's version-control policy and the user's commit instructions.
The [layout reference](project-layout.md#version-control) suggests defaults and
ignore patterns for new projects. Create output folders and helpers only as needed.

If the project uses Git LFS for imported sources, scope its `.gitattributes`
entries to the relevant files or formats, for example:

```gitattributes
STEP/imported/** filter=lfs diff=lfs merge=lfs -text
*.step.json text
```

Configure Git LFS before adding files covered by those rules. A file starting with
`version https://git-lfs...` is a pointer: `git lfs checkout STEP/imported`
restores objects already in the local cache; missing objects need fetching from
the project's LFS remote before CAD tools can read them.
