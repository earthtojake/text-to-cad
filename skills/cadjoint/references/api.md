# cadjoint authoring reference

Every name below exists at the commit `requirements.txt` pins. A scene file
imports what it uses; nothing is injected.

## Conventions that differ from B-rep CAD

| Quantity | cadjoint |
| --- | --- |
| `Solid.box(size=...)` | **half**-extents: `size=(10, 5, 2)` is 20 x 10 x 4 |
| `Solid.cylinder(height=...)` | **half**-height, axis along local Z |
| `position=` | the centre, in world coordinates |
| `rotation=` on `Solid`, `Rotate(...)` | radians; `Solid` applies X, then Y, then Z |
| `extrude(draft=, twist=)`, `PolygonProfile.regular(start_angle=)` | degrees |
| `extrude(depth=)` | symmetric: spans plus and minus depth/2 about the sketch plane |
| boolean `smoothness` | `k` in model units, default 0.1 (pass 0 for sharp); acts within `4k` of a seam, shifts the surface by up to `k` |

## Primitives

```python
from cadjoint.construction import Solid

Solid.box(size=(hx, hy, hz), position=(x, y, z), rotation=(rx, ry, rz), name="plate")
Solid.sphere(radius=r, position=..., name="ball")
Solid.cylinder(radius=r, height=half_h, position=..., rotation=..., name="boss")
```

`Solid` has only these three. Faces: `box.face("+z")`, `cylinder.face("cap+")`.

Raw primitives, centred at the origin and placed with `Translate`/`Rotate`:

```python
from cadjoint.sdf import Box, RoundBox, Sphere, Cylinder, Capsule, Torus

RoundBox(size=(hx, hy, hz), radius=r)    # grows by r: outer half-extents are hx+r, hy+r, hz+r
Capsule(radius=r, height=half_len)       # Z axis; half-length of the straight part
Torus(major_radius, minor_radius)        # in the XY plane
```

## Booleans

```python
from cadjoint.sdf.boolean import Union, Difference, Intersection

Union(a, b, c, smoothness=0.0)
Difference(base, tool_1, tool_2, smoothness=0.0)   # first argument is the base
Intersection(a, b, smoothness=1.0)
```

Operators `a | b`, `a - b`, `a & b` exist but always blend by 0.1; prefer the
explicit forms. The blend is Quilez's polynomial smooth minimum: it acts
wherever two operands' distances differ by less than `4k`, moves the surface
by up to `k` there and by exactly `k` along faces that coincide, and a chained
`Union(a, b, c, ...)` applies it once per operand, so shifts accumulate. The
rounded profile is a parabola, not a constant-radius fillet. To fillet
several features onto one body, join them sharp and blend that group with
the body once (see `examples/clevis_bracket.py`).

## Transforms and field operations

```python
from cadjoint.sdf import Translate, Rotate, Scale, Mirror, Twist, Shell, Offset
from cadjoint.sdf import LinearPattern, PolarPattern

Translate(sdf, (dx, dy, dz))
Rotate(sdf, "x", angle_radians)      # axis "x", "y", "z" or a 3-vector
Scale(sdf, factor)                   # float or per-axis triple
Mirror(sdf, "x")                     # about the plane x = 0
Shell(sdf, thickness)                # total wall, centred on the surface
Offset(sdf, distance)                # positive grows the solid
LinearPattern(sdf, (1, 0, 0), count, spacing)
PolarPattern(sdf, count)             # about world Z through the origin
```

`Rotate` silently treats an unknown axis string as Z: write `"x"`, `"y"` or
`"z"` exactly. `Shell` of a closed solid is a closed double wall; open it
with an `Intersection` or `Difference`. `PolarPattern` copies about the Z
axis only: build the feature off-axis, pattern it, then rotate the result.

## Sketches

```python
from cadjoint.construction import PolygonProfile, SketchPlane, extrude, revolve, loft

plane = SketchPlane(origin=(0, 0, 0), normal=(0, 0, 1))
profile = PolygonProfile([(x0, y0), (x1, y1), (x2, y2)], plane=plane, name="outline")
PolygonProfile.circle(radius, center=(0, 0), plane=plane, name="disc")
PolygonProfile.rounded_rect(width, height, radius, plane=plane, name="slot")  # full width/height
PolygonProfile.regular(sides, radius, start_angle=0.0, plane=plane, name="hex")

extrude(profile, depth, draft=0.0, twist=0.0)
revolve(profile)                    # about the plane's in-plane Y axis
loft(profile_a, profile_b, height)  # same vertex count; a at -h/2, b at +h/2
```

A profile point `(x, y)` lands at `origin + x*u + y*v`. Without `x_axis`:

| `normal` | `u` | `v` |
| --- | --- | --- |
| +Z | +X | +Y |
| +Y | -X | +Z |
| +X | -Z | +Y |

So a profile on a `normal=(0, 1, 0)` plane revolves about world Z, with
profile x as the radius; a profile may close along the axis (x = 0).

Polygons must be simple, with at least three vertices and no zero-length
edge. Curves are polylines: `circle` uses 32 segments by default; raise
`segments=` when a round edge must be smooth at the export resolution.

Work planes from existing geometry: `SketchPlane.on(solid.cap("+"))`,
`SketchPlane.offset(plane, distance)`, `SketchPlane.midplane(face_a, face_b)`.
`face.hole(radius, depth, at=(u, v), through=1.0)` returns a cylinder to
subtract from the solid the face belongs to.

## Parameters and constraints

```python
from cadjoint.geometry import Scalar, Vector, Vector2
from cadjoint.constraints import DistanceConstraint, FixedConstraint, satisfy_constraints

width = Scalar(40.0, free=True, name="width")
a = Vector2([0.0, 0.0], free=True, name="a")
DistanceConstraint(a, b, width)
satisfy_constraints(scene, steps=8)   # after building scene; edits it in place
```

Parameters are fixed unless `free=True`. A constraint only acts once
`satisfy_constraints` runs. Plain numbers are enough for a part that is only
exported; use parameters when the user wants a named dimension or an
optimization later.

## Not available

No fillet, chamfer, thread, text, cone primitive, gyroid or other TPMS
lattice. Round with blends, `RoundBox` or `rounded_rect`; for the rest, model
in `$cad`.
