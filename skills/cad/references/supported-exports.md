# Supported exports

Read this file when the user requests STL, 3MF, or native GLB output files from
CAD geometry. A `.step` comes from running the model script
([model contract](step-generation.md)); 2D DXF belongs to the `$dxf` skill.
Native GLB exports are ordinary glTF 2.0 binary for external tools: Y-up, one
material per distinct part or face colour.

## Declare the exports the model always has

Stack `@stl`, `@glb` or `@threemf` on the model for maintained mesh outputs. For
example, a project-root `bracket.py`:

```python
from cadgen import build123d as bd
from cadgen import glb, step, stl


@step(out="STEP/bracket.step")
@stl(out="STL/bracket.stl")
@glb(out="GLB/bracket.glb")
def bracket():
    return bd.Box(40, 20, 6)


if __name__ == "__main__":
    bracket()
```

Every run writes the STEP and the declared meshes, and restores declared outputs
that were deleted or edited. Mesh declarations alone create no sidecar, and the
export commands below never read them. Stacking order does not matter.

## A model with no STEP

A function with `@stl`, `@glb` or `@threemf` and no `@step` is a full model (same
tree, record, no-op and composition: `spacer()` inside another model links like
any child) that writes its meshes and no `.step` or sidecar. Its format's
`snapshot` renders it, and `cadgen store why spacer.py` explains its freshness.

```python
from cadgen import build123d as bd
from cadgen import stl


@stl(out="STL/spacer.stl", mesh_tolerance=4e-4)
def spacer():
    return bd.Cylinder(6, 3) - bd.Cylinder(2.5, 3)


if __name__ == "__main__":
    spacer()
```

Maintained draft/print variants can keep the model's stem in separate subfolders:

```python
@stl(out="STL/draft/bracket.stl", mesh_tolerance=8e-3)
@stl(out="STL/print/bracket.stl", mesh_tolerance=4e-4)
```

## Tool

One door per format (`cadgen stl build`, `cadgen 3mf build`, `cadgen glb build`),
each taking a saved STEP/STP and an optional OUT (default: a sibling with the
format's extension; an explicit OUT is relative to the working directory):

```bash
cadgen stl build STEP/model.step                     # writes STEP/model.stl
cadgen stl build STEP/model.step meshes/model.stl    # one ad-hoc export
```

An unchanged export reports `current`; `--force` re-exports without rebuilding
the source model. A mesh door never writes a `.step`. `cadgen glb build
--animation CLIP` writes a clip into the GLB as glTF animation
([exporting the clip inside a GLB](kinematics.md#exporting-the-clip-inside-a-glb)).

## Rendering a mesh file

Each mesh format has a `snapshot` verb with `cadgen step snapshot`'s grammar:

```bash
cadgen stl snapshot STL/bracket.stl tmp/bracket_mesh.png
cadgen 3mf snapshot 3MF/bracket.3mf tmp/bracket_3mf.png
cadgen glb snapshot meshes/bracket.glb tmp/bracket_glb.png
```

A mesh has no CAD topology: its door takes `--display solid` (default) or
`render`, and refuses the STEP-only options by name (`edges`, `clip`, `exploded`,
section mode, `--focus`/`--hide`, `--kinematics`, `--animation`). A GLB renders as
its own glTF scene, with its authored materials, at rest.

## Mesh tolerance

Mesh exports write the meshes the CAD Viewer draws: OCCT's mesh of each
component's exact surfaces. Faces that meet share their boundary vertices, and
identical inputs produce identical bytes.

```bash
--mesh-tolerance FLOAT           # chord tolerance RELATIVE to each component's
                                 # bounding diagonal (default 1.5e-3)
--mesh-angular-tolerance FLOAT   # max normal spread across a triangle edge,
                                 # radians (default 0.35)
```

On an export command these set that export's tolerances (defaults otherwise; the
model's declarations are not read). On a model-script run they override every
declared mesh's tolerances for that run only. `--json` results report the
effective pair.

Linear tolerance is relative, not millimetres: for a chord deviation of X mm on a
part whose bounding diagonal is D mm, pass X/D (0.1 mm on a 200 mm part is
`5e-4`). Linear tolerance must be from `5e-5` to `0.05` and angular tolerance
from `0.05` to `1.5708` radians, on flags and decorators alike; finer settings
take minutes per curved face without visible gain. A value outside is refused
before anything builds.

A face no mesher can cover (typically a sliver a boolean left, narrower than the
chord tolerance) never fails the export: the part is written without it, and the
result's `warnings` name it, for example `#o1.2 pin: 1 face (f3) could not be
meshed, so pin.stl has a hole in place of it: it is not watertight`. Repairing
the face in the model, or a finer `--mesh-tolerance`, closes the hole.
