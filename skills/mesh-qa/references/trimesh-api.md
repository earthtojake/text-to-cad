# trimesh API for Mesh QA

Long-form notes and copyable snippets for programmatic geometry and
printability checks with trimesh. This is an API guide, not a checklist:
pick what serves the part you are validating.

## Loading

```python
import trimesh

mesh = trimesh.load("path/to/part.stl", force="mesh")
```

- `force="mesh"` collapses scenes into a single `Trimesh` when you expect
  one part. Without it, multi-body files return a `Scene`.
- Supported inputs include STL, OBJ, PLY, GLB/GLTF, and 3MF. STEP is not a
  mesh format; export STL/3MF from the CAD skill first, then validate the
  mesh.
- Units follow the source file. STL has no units; the CAD skill works in
  millimeters, so exported meshes are normally millimeters. Confirm before
  asserting dimensions.

## Structural sanity

```python
mesh.is_watertight          # every edge shared by exactly two faces
mesh.is_winding_consistent  # face normals oriented consistently
mesh.volume                 # signed volume; > 0 for a valid solid
mesh.euler_number           # topological invariant; 2 for a simple solid
```

Splitting into connected bodies:

```python
bodies = mesh.split(only_watertight=False)
len(bodies)  # 1 for a single-component part
```

Use `split()` to detect unintended floating fragments (support leftovers,
duplicated shells, detached features).

## Dimensions and bounds

```python
mesh.bounding_box.extents   # (dx, dy, dz) of the axis-aligned bounds
mesh.bounds                 # [[minx, miny, minz], [maxx, maxy, maxz]]
mesh.center_mass
mesh.area                   # surface area
```

For feature-level measurements (hole diameters, slot widths, boss heights),
slice or section the mesh rather than inferring from the global bounds:

```python
section = mesh.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1])
planar, _ = section.to_2D()
```

## Self-intersection

trimesh has no first-class built-in self-intersection test. Practical
approaches, in increasing order of strength:

- Watertight + winding-consistent + positive volume already rules out most
  degenerate exports.
- `trimesh.collision.CollisionManager` with an FCL backend (if installed)
  can register the mesh against itself; reported contacts indicate
  self-overlap.
- For thin self-touching shells, ray-based checks (below) at suspect
  locations usually surface the problem as near-zero local thickness.

## Local wall thickness via ray casting

Estimate local thickness by casting rays from sampled surface points along
the inward normal and measuring the distance to the next hit:

```python
import numpy as np
import trimesh

points, face_index = trimesh.sample.sample_surface(mesh, 2000)
normals = mesh.face_normals[face_index]

rays = trimesh.ray.ray_triangle.RayMeshIntersector(mesh)
thickness = []
for p, n in zip(points, normals):
    origin = p + n * 1e-3          # nudge outward to avoid self-hit
    direction = -n
    hits, _, _ = rays.intersects_location([origin], [direction])
    if len(hits):
        thickness.append(np.linalg.norm(hits[0] - origin))

thickness = np.array(thickness)
thickness.min(), np.percentile(thickness, 5)
```

Notes:

- Sample more points for large or feature-dense parts; 2000 is a light
  first pass.
- The outward nudge avoids the ray immediately re-hitting its origin face.
- Percentiles are more robust than the raw minimum: a single sliver hit
  between two nearly-touching surfaces may be intentional geometry.
- With `pyembree` installed, `trimesh.ray.ray_pyembree.RayMeshIntersector`
  is much faster and supports batched queries.

## Proximity and containment (needs rtree)

```python
nearest, distance, _ = trimesh.proximity.signed_distance(mesh, points)
```

`signed_distance` reports per-point distance to the surface, negative
inside. Useful for clearance checks between a part and a mating envelope,
or for verifying that a hole actually passes through.

## Turning slicer output into assertions

The gcode skill slices meshes with real slicer CLIs and can validate the
resulting G-code. Evidence worth converting into assertions, when the part
warrants it:

- Support structures required for geometry the design expected to print
  unsupported.
- Overhang warnings on faces the design intended to be self-supporting.
- Out-of-bounds toolhead motion (part does not fit the bed).
- Layer-time or travel anomalies indicating unintended thin features.

Treat slicer output as one more data source: read the validate/dry-run
report, decide which findings contradict the design intent, and assert
those specific findings. See the gcode skill for its command surface.

## Test hygiene

- Load the mesh once per module with a `scope="module"` fixture; loading
  dominates runtime for large meshes.
- Use `pytest.approx` with an explicit `abs=` tolerance for every
  dimensional assertion; state the tolerance basis in a comment.
- Name tests after the requirement they verify
  (`test_mounting_hole_clears_m3_screw`), not the API call they make.
