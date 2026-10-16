---
name: cadjoint
description: Implicit (signed-distance) CAD with cadjoint, a differentiable JAX kernel - smooth blended booleans, shells, patterns, sketches extruded, revolved or lofted, constrained parameters - meshed to a watertight STL, OBJ or faceted STEP. Signed distance fields here are geometry, not the SDFormat robot files of $sdf. Use when the user wants organic or blended forms, smooth unions and fillet-like blends, hollow shells, radial or linear patterns of features, implicit or signed-distance-field modeling, or a part whose parameters will later be optimized by gradient. For prismatic parts that need exact B-rep faces, threads or chamfers, use $cad.
license: MIT
---

# cadjoint

Provenance: maintained in [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad).
Use the installed local skill files as the runtime source of truth.

A cadjoint model is a field, not a boundary: every solid is a signed distance
function, booleans are pointwise min/max (or their smooth blends), and a mesh
exists only once the field is sampled. Blends, shells and patterns are
therefore cheap and robust; exact analytic faces are not available. Choose
this skill for the first kind of part and `$cad` for the second.

## Setup

cadjoint needs Python 3.11 or newer, and macOS's `python3` is 3.9, where
the install is refused. Create the environment with uv, which fetches a
managed interpreter, and install the skill's `requirements.txt` into it
once. The file pins cadjoint to a commit because
cadjoint's API is not yet stable:

```bash
uv venv --managed-python --python 3.12 cadjoint-env
uv pip install --python cadjoint-env -r <skill-dir>/requirements.txt
```

`<skill-dir>` is the directory holding this file. Run every command below
with that environment's interpreter, `cadjoint-env/bin/python` (on Windows
`cadjoint-env\Scripts\python.exe`).

## Workflow

1. **Write a scene file**, e.g. `src/bracket.py`: plain Python that builds the
   part and binds it to a module-level name `scene`. Model in millimetres.
   Read [references/api.md](references/api.md) before writing the first
   line; its conventions (half-extents, half-heights, radians, default blend)
   differ from build123d's. Start from the closer of the two examples in
   [references/examples/](references/examples/): `clevis_bracket.py`, a
   machined bracket with blended roots, sharp holes and rounded cutouts, or
   `space_frame_node.py`, six tubes blended into a hub and hollowed to a
   constant wall.
2. **Export:**

   ```bash
   python <skill-dir>/scripts/cadjoint_export.py src/bracket.py STL/bracket.stl --resolution 160
   ```

   The suffix selects STL, OBJ or STEP. The script fits the meshing grid to
   the part, so any scale works. It prints one JSON object.
3. **Read the report.** `ok` and `watertight` must be true, `clipped` false
   and `warnings` empty, or each warning explained. `clipped` means part of the solid lies
   on or beyond the grid boundary and the mesh is cut open there. `size` is
   the mesh's extent in millimetres and `bodies` its count of separate
   pieces: check both against the request. A part meant as one piece that
   reports several has a wall or bridge thinner than about two cells.
   `spacing` is the cell size: raise `--resolution` until the thinnest wall
   spans at least four cells, and report the spacing with the file.
4. **Look inside the field when a dimension matters.** A mesh shows where
   the surface is; a slice of the field shows how far every point is from
   it:

   ```bash
   python <skill-dir>/scripts/cadjoint_slice.py src/bracket.py tmp/bracket-x0.png --axis x --at 0 --step 1
   ```

   Inside is blue, outside orange, the surface is the black line and the
   thin lines are contours every `--step` millimetres. The report's
   `field_range` gives the deepest point inside: twice that is the
   thickness of the thickest wall the slice cuts. Use it to confirm a wall
   or a blend's reach before exporting at high resolution.
5. **Review an image** with `$cad`'s snapshot workflow on the exported STL,
   and compare it with the request before showing anything. Fix the scene
   and export again rather than describing a defect.
6. **Show the model** with `$cad`'s viewer workflow, given the absolute path
   from the report's `path`.

## Outputs

| Output | Use | Limits |
| --- | --- | --- |
| STL (binary) | printing: `$dfam-check`, `$gcode` | none beyond the mesh spacing |
| OBJ | rendering, other mesh tools | coplanar triangles merged into polygons |
| STEP (`.step`) | handing a solid to B-rep tools | faceted: one planar face per triangle, 500-900 bytes each, so about 140 MB at 160,000 triangles; no cylinder or plane can be selected as such, and radius measurements read chords. Export STEP at a lower `--resolution` than STL |

A 3MF or GLB comes from the STL through `$cad`. Never hand a faceted STEP to
a check that needs exact radii (`$dfm`, `$sendcutsend`) without saying it is
faceted.

## Rules

- **Scale.** Model in millimetres; the field has no units, the export keeps
  the numbers, and the viewer and slicers read millimetres.
- **Blends are in model units and change the size.** Every boolean blends by
  default (`smoothness=0.1`). Pass `smoothness=0` for a sharp edge. A blend
  of `k` acts wherever two operands come within `4k` of each other and pushes
  the surface out (union) or in (difference) by up to `k` there, by exactly
  `k` along faces that coincide, and chained blends add up. Join parts sharp
  and blend once; keep other faces more than `4k` from a blended seam when
  their position matters; never blend two coincident faces.
- **Give every `Solid` a unique name.** Its parameters are named after it,
  and two solids with the same name collide when parameters are extracted.
- **Holes and pockets are tools.** `face.hole(...)` and `face.pocket(...)`
  return a solid to subtract; overlap a subtracted tool past the face it
  cuts (or use `through=`), never flush with it.
- **No infinite solids in a scene.** `Plane` and an unbounded intersection
  make the scan fail; the error says to pass `--bounds`.
- **Thin walls need cells.** `--resolution` counts cells along the longest
  axis and stops at 512, so the spacing is at least the part's length / 512:
  0.6 mm for a 300 mm part. A 1 mm wall there still meshes closed but its
  thickness is only good to about one spacing. When the four-cell rule above
  cannot be met, say so and report the spacing; `--bounds X0 Y0 Z0 X1 Y1 Z1`
  meshes a smaller box at the same cell count when only part of a large
  object matters.
- **No fillet, chamfer, thread or text operations exist.** Rounding comes from
  blends, `RoundBox` or `PolygonProfile.rounded_rect`; for the rest use `$cad`.

## Beyond geometry

Parameters declared with `free=True` stay differentiable through the field,
the mesh, and cadjoint's FEM studies, so `jax.grad` of a mass, a compliance
or a peak temperature with respect to a sketch vertex is one call. That
workflow and cadjoint's interactive editor are documented at
https://andrinr.github.io/cadjoint/ and are outside this skill's scope;
offer them when the user asks to optimize a shape, not by default.
