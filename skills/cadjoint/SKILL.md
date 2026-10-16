---
name: cadjoint
description: Implicit (signed-distance) CAD with cadjoint, a differentiable JAX kernel - smooth blended booleans, shells, patterns, sketches extruded, revolved or lofted, constrained parameters - meshed to a watertight STL, OBJ or faceted STEP. Use when the user wants organic or blended forms, smooth unions and fillet-like blends, hollow shells, radial or linear patterns of features, implicit or SDF modeling, or a part whose parameters will later be optimized by gradient. For prismatic parts that need exact B-rep faces, threads or chamfers, use $cad.
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

Python 3.11 or newer. Install the skill's `requirements.txt` into its own
environment once; it pins cadjoint to a commit because cadjoint's API is not
yet stable:

```bash
python3 -m venv cadjoint-env
cadjoint-env/bin/python -m pip install -r <skill-dir>/requirements.txt
```

`<skill-dir>` is the directory holding this file. Run every command below
with that environment's `python`.

## Workflow

1. **Write a scene file**, e.g. `src/knob.py`: plain Python that builds the
   part and binds it to a module-level name `scene`. Model in millimetres.
   Read [references/api.md](references/api.md) before writing the first
   line; its conventions (half-extents, half-heights, radians, default blend)
   differ from build123d's. Start from the closest example in
   [references/examples/](references/examples/).
2. **Export:**

   ```bash
   python <skill-dir>/scripts/cadjoint_export.py src/knob.py STL/knob.stl --resolution 160
   ```

   The suffix selects STL, OBJ or STEP. The script fits the meshing grid to
   the part, so any scale works. It prints one JSON object.
3. **Read the report.** `ok` must be true and `clipped` false; `clipped`
   means part of the solid lies on or beyond the grid boundary and the mesh
   is cut open there.
   `spacing` is the cell size: a feature thinner than about two cells is
   lost or thickened, so raise `--resolution` until the thinnest wall spans
   at least four. Report the spacing to the user alongside the file.
4. **Review an image** with `$cad`'s snapshot workflow on the exported STL,
   and compare it with the request before showing anything. Fix the scene
   and export again rather than describing a defect.
5. **Show the model** with `$cad`'s viewer workflow, given the absolute path
   from the report's `path`.

## Outputs

| Output | Use | Limits |
| --- | --- | --- |
| STL (binary) | printing: `$dfam-check`, `$gcode` | none beyond the mesh spacing |
| OBJ | rendering, other mesh tools | coplanar triangles merged into polygons |
| STEP (`.step`) | handing a solid to B-rep tools | faceted: one planar face per triangle; no cylinder or plane can be selected as such, and radius measurements read chords |

A 3MF or GLB comes from the STL through `$cad`. Never hand a faceted STEP to
a check that needs exact radii (`$dfm`, `$sendcutsend`) without saying it is
faceted.

## Rules

- **Scale.** Model in millimetres; the field has no units, the export keeps
  the numbers, and the viewer and slicers read millimetres.
- **Blends are in model units and change the size.** Every boolean blends by
  default (`smoothness=0.1`). Pass `smoothness=0` for a sharp edge. A blend of
  `k` moves the surface by up to `k` where operands meet, so a dimension that
  must hold exactly may not sit inside a blend.
- **Give every `Solid` a unique name.** Its parameters are named after it,
  and two solids with the same name collide when parameters are extracted.
- **Holes and pockets are tools.** `face.hole(...)` and `face.pocket(...)`
  return a solid to subtract; overlap a subtracted tool past the face it
  cuts (or use `through=`), never flush with it.
- **No infinite solids in a scene.** `Plane` and an unbounded intersection
  make the scan fail; the error says to pass `--bounds`.
- **Revolve profiles must not touch the axis.** An edge on the axis is a
  false surface in the field; mirror the profile across x = 0 instead (see
  `references/examples/planter.py`).
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
