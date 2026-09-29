# Modeling with fields

Read this when writing or editing an implicit part. `im` is
`from cadgen import implicit as im`. Every call returns a new immutable
`Field`; nothing is evaluated until the part is meshed or measured.

## Primitives (leaves)

All are centred at the origin unless a point is given; all are exact
distances (the value *is* the distance to the surface).

| Call | Shape |
| --- | --- |
| `im.sphere(r)` | sphere |
| `im.box((x, y, z), radius=0)` or `im.box(s)` | box; `radius` rounds every edge and corner (must be ≤ half the smallest side) |
| `im.cylinder(radius, height, radius_edge=0)` | along Z; `radius_edge` rounds both rims |
| `im.capsule(a, b, radius)` | a sphere swept from point `a` to point `b` |
| `im.cone(radius_bottom, radius_top, height)` | along Z; `radius_top=0` is a point |
| `im.torus(radius, tube)` | in the XY plane |
| `im.half_space(normal, origin)` | the half of space the normal points into, from the plane through `origin`: `part - im.half_space((0, 0, 1), (0, 0, 10))` removes everything above z = 10. Unbounded: only ever a cutting tool inside `&` or `-` |
| `im.extrude(profile, height)` | a 2D profile along Z |
| `im.revolve(profile)` | a 2D profile drawn in the (radius, z) half-plane, turned about Z |
| `im.custom(fn, bounds)` | your own `fn(points (N,3)) -> (N,)` with declared bounds; cannot be saved to a tape |
| `im.from_step(path)` | an existing STEP as a leaf: the way a B-rep enters the field. Its B-rep is kept, so sharp booleans with it leave as an exact STEP; the tape records the file relative to itself |
| `im.from_shape(shape)` | a build123d shape (a `$cad` model's result) as a leaf; not tapeable |

2D profiles for extrude and revolve: `im.circle(r)`, `im.rect(w, h, radius=0)`,
`im.polygon([(x, y), ...])` (any simple polygon, either winding),
`im.regular_polygon(sides, radius)` (a hex socket is `regular_polygon(6, r)`).
A revolve profile must stay at radius ≥ 0; a `rect` centred on the axis will not.

Give a leaf a name with `.named("bore")`. The name is what the viewer shows
and what `measure` lists; a leaf without one is listed as `<kind>@<file:line>`.

## Booleans

```python
a | b                       # union            min(a, b)
a & b                       # intersection     max(a, b)
a - b                       # subtraction      max(a, -b)
im.union(a, b, c, round=2)  # fillet the joins by ~2 (smooth min)
im.union(a, b, chamfer=2)   # bevel the joins
im.intersect(a, b, round=1)
im.subtract(body, tool, round=1)   # fillet the cut edges
```

`round` and `chamfer` blend over a band about that wide at the join and leave
the rest of the field exact. A blend of `k` fills at most `k/4` into a gap, so
to bridge two solids a distance `g` apart use `round > 4 g`. Concave fillets
(inside corners) come from the boolean's `round`; convex rounds (outside
edges) come from a primitive's own `radius` or from `.round(r)` below.

## Placement

```python
f.translate(x, y, z)            # or f.translate((x, y, z))
f.rotate(deg, axis=(0, 0, 1))   # about an axis through the origin, right-hand rule
f.scale(k)                      # uniform only; distances stay exact
f.mirror("x")                   # the field AND its reflection across x = 0
f.repeat((dx, dy, dz), (nx, ny, nz))  # a finite grid of copies, centred on the original
f.elongate(x=0, y=0, z=0)       # stretch by a flat section along each axis
```

Build a feature at the origin, then place it. Rotations are about the origin,
so rotate before translating. `mirror` is the cheap way to make symmetric
hole patterns: one hole, mirrored twice, is four.

## Offsets, shells, rounds

```python
f.offset(r)      # grow (r > 0) or shrink the solid by a metric distance
f.shell(t)       # the skin: a wall t thick centred on the surface (hollowing)
f.round(r)       # round every convex edge by r (shrink then grow)
```

A shell of a closed solid is a closed hollow part with no opening. Cut the
opening afterwards: `f.shell(2) - im.half_space((0, 0, 1), (0, 0, top - 0.1))` (the half space pointing up from just under the top).
A wall of thickness `t` you can print is `f.shell(t)`; a *cavity* is
`f - f.offset(-t)`.

## Patterns

**A bracket with a filleted web**

```python
base = im.box((60, 40, 6)).named("base")
upright = im.box((6, 40, 40)).translate(-27, 0, 20).named("upright")
bracket = im.union(base, upright, round=4)
holes = im.cylinder(2.2, 20).translate(15, 12, 0).mirror("y").named("holes")
return bracket - holes
```

**A hex socket cap**

```python
head = im.cylinder(6, 5, radius_edge=0.5).named("head")
socket = im.extrude(im.regular_polygon(6, 2.5), 6).translate(0, 0, 2).named("socket")
return head - socket
```

**A lattice-like grid**

```python
cell = im.box(8).shell(1.2)
return cell.repeat((8, 8, 8), (5, 5, 3)) & im.sphere(22)
```

**A revolved knob with a hollow**

```python
outline = im.polygon([(0, 0), (12, 0), (14, 6), (9, 20), (0, 20)])
knob = im.revolve(outline).named("knob")
return knob.shell(1.6) - im.half_space((0, 0, -1), (0, 0, 0.1))   # open the bottom: remove what is below z = 0.1
```

**Composing parts**

```python
from housing import housing        # another script's @im.part

@im.part(out="GLB/assembly.glb")
def assembly():
    return housing() | im.sphere(4).translate(0, 0, 14).named("cap")
```

## Starting from a B-rep

Any STEP can enter the field, be operated on there, and leave as a STEP:

```python
base = im.from_step("STEP/bracket.step").named("bracket")
ribbed = im.union(base, im.box((40, 3, 12)).translate(0, 0, 8).named("rib"), round=2)
hollow = ribbed.shell(1.6) - im.half_space((0, 0, -1), (0, 0, 0.2)).named("opening")
return hollow - im.cylinder(1.7, 30).translate(15, 0, 0).mirror("x").named("holes")
```

Use this when a B-rep operation keeps failing (a shell, a blend between
bodies), when a lattice or organic feature must be added to a machined
part, or when the question is metric (clearance of two STEPs: `im.clearance(a, b)`).
The distance of a B-rep leaf comes from its surface and is exact to a small
fraction of the grid cell; contouring costs more than a primitive (a few
seconds for a part like the housing at 0.4 mm). A sharp boolean with a
B-rep leaf leaves in the STEP with the original faces intact; a shell or
blend leaves only if OpenCascade agrees, as for any tree.

## Limits to state in the report

- The STEP is the kernel's rebuild of the field: a join OpenCascade refuses to
  fillet is left sharp and named in the warnings, and `elongate` or a custom
  field has no STEP at all (the part writes a mesh instead). Say so when it
  happens.
- Smooth blends (`round`, `chamfer`) make the field a *bound* near the join,
  not an exact distance; offsets through a blend are approximate there.
- Non-uniform scale is not offered because it breaks the distance property.
- Resolution decides fidelity: a feature smaller than about two cells is lost.
