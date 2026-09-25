# Runtime API

All geometry helpers are imported from `cadgen.organic`. Heavy dependencies load
on use. Authoring runs in a plain Python recipe with explicit input/output
paths. Inspection reports are dictionaries that can be saved as JSON.

| Helper | Purpose |
| --- | --- |
| `inspect_mesh(path)` | Source hash, instances, bounds, raw/welded topology |
| `load_mesh(path, up=..., height_mm=... OR mm_per_unit=...)` | Placed geometry in mm/Z-up |
| `prepare_mesh(mesh, fill_small_holes=False, simplify_mm=0)` | Working solid and repair audit |
| `split_plane(mesh, origin=..., normal=..., gap_mm=0)` | Closed negative and positive halves |
| `ball_socket(...)` | Built-in ball/socket CAD factory and its Boolean tools; not a general joint selector |
| `from_cad(shape, tolerance_mm=0.03)` | CAD tessellation for mixed Boolean work |
| `boolean(operation, meshes)` | `union`, `difference`, `intersection` |
| `RotationGrid(pivot, x_degrees=..., y_degrees=..., z_degrees=..., step_degrees=10)` | Fixed-pivot XYZ domain |
| `clearance_envelope(obstacle, grid, clearance_mm=..., inverse=False, geometry_error_mm=0, cell_size_mm=None)` | Local convex or partitioned cover and audit |
| `smooth_clearance_envelope(envelope, pitch_mm=..., sigma_mm=..., outset_mm=...)` | Optional VTK distance-field smoothing with a mesh-volume coverage gate |
| `carve_clearance(host, envelope, allowed_region=..., protected=None)` | Restricted cut, effective cutter and audit |
| `check_motion(fixed, moving, grid, clearance_mm=0, volume_tolerance_mm3=1e-6)` | Sampled overlap/gap report |
| `stl_roundtrip(mesh, max_error_mm=0.001)` | Validated STL-precision mesh and export audit; no repair |
| `write_mesh(mesh, path)` | Valid STL or GLB |
| `write_scene({name: mesh, ...}, path)` | Named independent GLB components |

Both writers use cadgen's shared mesh-export builder. GLB preserves named parts,
vertex/face colors and plain PBR base colors. glTF import converts linear
`COLOR_0` to the writer's sRGB input; hand-authored Trimesh `ColorVisuals` keep
their sRGB interpretation. PBR `OPAQUE`, `MASK` (with cutoff), and `BLEND`
alpha modes survive GLB rewriting. For image-free glTF/GLB, imported PBR
base-color factors and `COLOR_0` are combined at float precision; mesh copies
retain those colors. Trimesh may classify a plain PBR material as a texture
visual. Image-textured scenes remain importable for geometry work,
but direct GLB rewriting requires baking those images to vertex colors first.

## Mechanism coverage

`from_cad` and `boolean` accept valid solids for any authored mechanism. There is
no built-in hinge, slider or automatic sizing factory; use the CAD handoff in
[workflow.md](workflow.md). The only supplied joint factory is `ball_socket`.

The motion API above supports a fixed-pivot angular box. For a hinge/swivel, align
the joint frame and activate only its real axis, for example
`RotationGrid((0, 0, 0), z_degrees=(0, 90), step_degrees=5)` for a chosen local-Z
hinge. The angle limits here are illustrative, not defaults for organic joints.
Translation, screw coupling, offset-axis mechanisms and general linkages require
a compatible authored motion checker/envelope; `RotationGrid` has no mm-travel
field and its angular padding bound does not cover those motions.

## Executable ball-socket coupon check

This minimal source exercises CAD-to-mesh geometry, grouping and all 27 poses.
It writes under `models/`. It does not perform segmentation or insertion
simulation. Its defaults exercise the API only. For an organic recipe, first
select the mechanism and derive explicit dimensions with
[joint-design.md](joint-design.md); use this example only for the ball-socket branch.

```python
import json
from pathlib import Path
from cadgen.organic import (
    ball_socket, from_cad, stl_roundtrip, RotationGrid, check_motion, write_mesh, write_scene,
)

out = Path("models/joint_trial")
joint = ball_socket()
male, _ = stl_roundtrip(from_cad(joint.male))
socket, _ = stl_roundtrip(from_cad(joint.socket))
grid = RotationGrid((0, 0, 0), (-10, 10), (-10, 10), (-10, 10), 10)
report = check_motion(male, socket, grid, clearance_mm=0.1)
write_mesh(male, out / "STL/ball.stl")
write_mesh(socket, out / "STL/socket.stl")
write_scene({"ball": male, "socket": socket}, out / "GLB/assembly.glb")
(out / "motion.json").write_text(json.dumps(report, indent=2) + "\n")
assert report["ok"], report["status"]
```

Place joint CAD with `bd.Pos(*pivot) * joint.male` (and the same for the blank
and void), then call `from_cad`. Attach with
`boolean("union", [body, male])` and
`boolean("difference", [boolean("union", [head, blank]), void])`.
Check component counts and the attachment; these expressions alone do not
establish useful joint placement or freedom of movement.

Snapshot the actual written document:

```bash
cadgen glb snapshot models/joint_trial/GLB/assembly.glb models/joint_trial/review.png
```

The organic output remains a mesh. Export authored mechanical features as
STEP using normal CAD source and validation, independently of the mesh recipe.
Scene poses here are static review states; no spherical viewer control or
automatic motion animation is declared.

For curved cutters, see [motion-surfaces.md](motion-surfaces.md). Smoothing
requires the optional `cadgen[organic,organic-smooth]` extra. Its coverage gate does not
replace final-part wall and motion checks; its outset is not a surface-error bound.
