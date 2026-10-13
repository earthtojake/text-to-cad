# usd-brep-build123d

EXPERIMENTAL. build123d's modeling language on NVIDIA's
[usd-brep](https://github.com/NVIDIA-Omniverse/usd-brep) kernel (SMLib), with no
OpenCascade in the process. A build123d script runs unchanged but for its import, builds
the same solid, and writes exact B-rep to OpenUSD:

```python
import usd_brep_build123d as bd          # instead of: import build123d as bd

with bd.BuildPart() as flange:
    bd.Cylinder(40, 10, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    with bd.Locations((0, 0, 10)):
        with bd.PolarLocations(30, 6):
            bd.CounterBoreHole(3, 5, 2)
    rims = flange.edges().filter_by(bd.GeomType.CIRCLE).sort_by(bd.SortBy.RADIUS)[-2:]
    bd.fillet(rims, radius=1.5)

bd.export_usd(flange.part, "flange.usda")
```

**PURPOSE**: build123d's builders, objects, operations and selectors over usd-brep Breps;
OpenUSD (`BrepArray` prims) in and out.

**MAY DEPEND ON**: `usd-brep==1.0.0` (CPython 3.12 wheels, Linux and Windows) and numpy.
OpenCascade (OCP, from build123d) only in `usd_brep_build123d.occt`, the exact conversion to
OpenCascade, imported by whoever calls it.

**DEPENDED ON BY**: nothing. Its tests compare it with build123d.

## The laws

### 1. build123d's semantics, not usd-brep's

The same script builds the same solid. Where the kernels disagree, the package does what
build123d on OpenCascade does, quirks included, because that is what scripts were written
against:

| OpenCascade / build123d | usd-brep | Here |
| --- | --- | --- |
| Shapes are values | booleans consume their operands; fillets edit in place | every operation copies its operands first |
| A fillet runs along the whole tangent-continuous chain through a selected edge | fillets exactly the edges given | the chain is collected first |
| Seams and edges between tangent faces are skipped in a fillet or chamfer | the whole call fails | they are dropped; a selection of nothing else raises, as build123d does |
| Arcs and their extruded seams are circles and lines | B-splines; some intersections (a torus groove in a cylinder) are 3.6e-6 mm off a circle | an exact (to 1e-6 of its size) line or circle reports `LINE`/`CIRCLE`, `radius`, `arc_center` |
| A chamfer's length is its setback on each face | the linear cross-section sets back `r*cot(theta/2)` | converted per edge from the face angle |
| A sketch inside `Locations` ignores them; an outer builder is a parent only in the same Python scope | n/a | the same |

### 2. Raise rather than approximate

A feature this package does not implement raises `NotImplementedError`. A kernel result
that is not a valid solid raises: usd-brep can return a body with no material from a fillet
OpenCascade refuses, and this package raises `ValueError` as build123d would.

### 3. Parity is proven against build123d

Every feature has a test that builds the same script with build123d and with this package
and requires the two solids to coincide: the volume where they differ is zero. Measure
equality that way, on the exact conversion in `occt.py`, not with `volume`: usd-brep's
integrator does not always meet the accuracy it is asked for (3e-5 off on a NURBS blend at
a requested 1e-6).

### 4. Extensions are named as extensions

usd-brep-only capabilities get their own names (`blend`, `export_usd`, `import_usd`); a
build123d signature is never widened.

## What is covered

- **Builders**: `BuildPart`, `BuildSketch` (modes ADD, SUBTRACT, INTERSECT), `Locations`,
  `GridLocations`, `PolarLocations`, `add`; builder `edges()`, `faces()`, `vertices()`,
  `solids()`, `max_dimension`.
- **Algebra mode**: `Pos`, `Rot`, `Location`, `Plane` (named planes, `offset`, `rotated`,
  `Plane * shape`), `+ - &` (lists too), `moved`, `move`, `located`, `locate`, `location`,
  `rotate`, `translate`, `scale`, `mirror`, `split`, `Compound`, `solids()`.
- **Part objects**: `Box`, `Cylinder` (partial too), `Cone`, `Sphere`, `Torus`, `Hole`,
  `CounterBoreHole`, `CounterSinkHole`, all with `align`, `rotation` and `mode`.
- **Sketch objects**: `Rectangle`, `RectangleRounded`, `Circle`, `Ellipse`, `Polygon`,
  `RegularPolygon`, `SlotOverall`, `SlotCenterToCenter`, `Trapezoid`.
- **Operations**: `extrude` (`amount`, `dir`, `both`), `revolve`, `loft` (one-loop sections;
  ruled is exact, smooth is usd-brep's cubic skin), `fillet`, `chamfer` (symmetric),
  `mirror`, `split` (by a plane), `offset` (solids, with or without openings), `scale`.
- **Selectors**: `filter_by` (`GeomType`, `Axis`, `Plane`, a predicate), `sort_by` and
  `group_by` (`Axis`, `SortBy`, a key), `first`, `last`; edge `radius`, `arc_center`,
  `normal()`, `length`, `position_at`, `tangent_at`, `bounding_box()`, `center()`.
- **usd-brep extensions**: `blend(edges, radius, continuity=2)`, a curvature-continuous
  (G2) or G3 blend where `fillet` is circular; `export_usd`, `import_usd`.

Sketches keep their exact profiles and modes and apply the modes as 3D booleans when
extruded or revolved (the same solid as a 2D boolean first): usd-brep can combine sheets
in 2D, but thickening a `boolean_2d` result crashes the interpreter, and a sheet's trimmed
edges cannot be read back as curves.

## Known differences

- A selection that hinges on the order of ties (`sort_by(Axis.Z)[0]` with several edges at
  the same height) can pick a different edge: the kernels list topology in different orders.
- Faces report `PLANE` or `OTHER` only: usd-brep's Python API does not say which analytic
  surface a face is.
- Face counts can differ where usd-brep splits a face OpenCascade keeps whole; the solid is
  the same.
- `mirror` (and a non-uniform `scale`) turns every face and edge into a B-spline: usd-brep
  reflects by scaling.

## Not yet

STEP (USD is the output), `Text`, `BuildLine` and curve objects (`Line`, `Spline`, arcs),
`sweep`, `make_face`, sketch fillets/chamfers and offsets, `extrude(until=...)` and tapers,
`draft`, joints, partial spheres, cones and tori, hidden-line drawings. Each would raise
today; usd-brep has the kernel operations for most of them.

## Running

usd-brep has wheels for CPython 3.12 on Linux and Windows:

```bash
uv run --python 3.12 --with usd-brep==1.0.0 --with numpy --with-editable . python model.py
```

from this directory, or `pip install -e .` into a 3.12 environment.
