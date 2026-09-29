# Questions on the field

Read this when a request asks *how thick*, *how far apart*, *do they touch*,
*how much*, or *what is at this point*. Because every shape is a distance,
these are evaluations of the same fields the part is made of, not topology
walks — and every answer is sampled, so it states the resolution it was taken
at and is exact only to that.

## In Python, on any field

```python
from cadgen import implicit as im

part = ...                                   # a Field (call the decorated part inside another, or build one)
part.distance([(0, 0, 0), (14, 14, 0)])      # signed distance per point, negative inside
part.contains(points)                        # inside test
part.normal(points)                          # unit outward normal
part.bounds                                  # conservative axis-aligned bounds

im.probe(part, [(0, 0, 0)])                  # distance, inside, owning leaf, normal per point
im.thickness(part, resolution=0.25)          # min/p05/median wall thickness (inward rays) and max (largest inscribed sphere), with locations
im.clearance(a, b, resolution=0.25)          # least distance from a's surface to b; negative = they interpenetrate by that much
im.interference(a, b, resolution=0.25)       # shared volume and its bounds; 0 when apart
im.contour(part, resolution=0.25).volume()   # enclosed volume of the mesh; .area(), .centroid()
```

Write these checks in the project's `tmp/` or `checks/`, as `$cad` does. A
check that fails to compute is not a pass.

## On a saved tape, from the shell

```bash
cadgen implicit measure GLB/housing.implicit.json
cadgen implicit measure GLB/housing.implicit.json --walls
cadgen implicit measure GLB/housing.implicit.json --at 0,0,0 --at 14,14,0 --resolution 0.25
cadgen implicit measure GLB/housing.implicit.json --json
```

The report gives the tight bounds, volume, surface area and centroid, one
line per leaf with its surface share, the thinnest and thickest walls with
`--walls`, and one line per `--at` probe: distance, inside or outside, and
which leaf's surface is nearest. `--json` is the same as one object.

## Faces

A face the user picks in the viewer arrives as a selector, `part.step#o1.f7`.
The tape knows which leaf's surface every face lies on:

```bash
cadgen implicit faces src/housing.step --ref housing.step#o1.f7
cadgen implicit faces src/housing.step --json          # every face, with its leaf and source line
```

Each line is the selector, the surface type and area, the centre, and the
leaf: its label and the `file:line` that wrote it. Edit that line, rerun the
script, and the face changes. A face on a fillet belongs to whichever operand
is nearer at its centre.

## Reading the numbers

- **Thickness** comes from rays cast into the solid from surface vertices
  along their inward normals until they exit. `min_thickness` is the shortest
  ray with `min_at` its start: a thin plate, a thin shell, the wall between a
  hole and an edge — or a knife edge, which reads near zero and is real (a
  plane cut through a sloping wall makes one; look at `min_at`). `p05_thickness`
  and `median_thickness` say what the walls are like away from such an edge;
  quote the 5th percentile as "the walls" and the minimum as "the thinnest
  point". `max_thickness` is the largest sphere that fits inside. All are
  exact to a cell.
- **Clearance** is sampled at `a`'s mesh vertices, so a gap narrower than a
  cell may read as touching; measure at a finer resolution when the answer
  is near zero. `touching` is true when the gap is under one cell.
- **Interference** counts grid cells inside both solids; small overlaps need
  a fine resolution to register.
- **Volume** comes from the same mesh the file holds, so it agrees with what
  a slicer sees. It is within about half a percent at the default resolution.

Always report the resolution beside a measurement, and refine once (halve
the resolution) when a number is close to a limit the user cares about.
