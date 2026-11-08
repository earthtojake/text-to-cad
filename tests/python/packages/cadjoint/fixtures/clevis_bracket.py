"""A clevis bracket in millimetres: base plate, twin lugs, ribs, holes, cutouts.

A load-bearing part rather than a shape study. The base is 120 x 60 x 10,
the lugs rise to 52 with a 14 mm pin hole at z = 34 and a 16 mm gap, two
ribs brace the lugs, four 7 mm bolt holes and two rounded triangular
lightening cutouts go through the plate.

What the field does that edge selection does not:

- One blended Union against the plate fillets every root it creates --
  both faces of both lugs, and the ribs -- with no edges to pick and none
  that can fail to round. The blend reaches 4 * ROOT_BLEND from each seam,
  so the lugs and ribs are joined sharp first and only that one blend
  touches the plate: chained blends accumulate.
- The lug's crown is an exact circle (box plus cylinder), not a polyline.
- The cutouts' 3 mm corner radii come from Offset: the triangle shrunk by
  3 mm about its incenter, then offset outward by 3 mm, has the original
  straight edges and exact 3 mm arcs at the corners. (Offsetting the
  original triangle in and back out would not: the two offsets cancel on a
  distance field and give the sharp triangle back.)
- Holes and cutouts are subtracted sharp (smoothness=0), so their edges and
  diameters hold.
"""

import math

from cadjoint.construction import PolygonProfile, SketchPlane, Solid, extrude
from cadjoint.sdf import Offset, RoundBox, Translate
from cadjoint.sdf.boolean import Difference, Union

ROOT_BLEND = 0.6  # smoothness k: the root blend spans about 4k = 2.4 mm

# Base plate: 120 x 60 x 10 on z = 0, every outer edge rounded by 3.
# RoundBox grows by its radius, so the inner box is 3 smaller per side.
base = Translate(RoundBox((57.0, 27.0, 2.0), 3.0), (0.0, 0.0, 5.0))

# Lugs: 36 wide, 18 thick, crown radius 18 centred at z = 34, gap 16.
# Box and crown are joined sharp first: their sides are tangent, and a blend
# where two surfaces coincide pushes outward by its full width.
# The box starts inside the plate (z = 5) so the blended union has overlap.
lugs = []
for side, y in (("pos", 17.0), ("neg", -17.0)):
    stem = Solid.box(size=(18.0, 9.0, 14.5), position=(0.0, y, 19.5), name=f"lug_{side}")
    crown = Solid.cylinder(
        radius=18.0, height=9.0, position=(0.0, y, 34.0),
        rotation=(math.pi / 2, 0.0, 0.0), name=f"crown_{side}",
    )
    lugs.append(Union(stem, crown, smoothness=0.0))

# Ribs: 6 mm gussets on the lugs' outer faces, from the plate edge (y = 30)
# up to z = 38 on the lug. Each starts 4 mm inside its lug so the two
# overlap instead of touching. The foot overhangs the plate's rounded top
# edge, and the blend filling under it reaches 0.15 mm past y = 30 at the
# foot's two top corners; the plate's side face itself stays at 30. A plane with normal +X maps profile (x, y) to
# world (-z, y).
ribs = []
for side, sign in (("pos", 1.0), ("neg", -1.0)):
    inner, outer, foot = 22.0 * sign, 26.0 * sign, 30.0 * sign
    corners = [(-10.0, inner), (-10.0, foot), (-38.0, outer), (-38.0, inner)]
    ribs.append(extrude(
        PolygonProfile(
            corners if sign > 0 else corners[::-1],
            plane=SketchPlane(origin=(0.0, 0.0, 0.0), normal=(1.0, 0.0, 0.0)),
            name=f"rib_{side}",
        ),
        depth=6.0,
    ))

body = Union(base, Union(*lugs, *ribs, smoothness=0.0), smoothness=ROOT_BLEND)

# Pin hole: 14 mm through both lugs along Y.
pin = Solid.cylinder(
    radius=7.0, height=40.0, position=(0.0, 0.0, 34.0),
    rotation=(math.pi / 2, 0.0, 0.0), name="pin_hole",
)

# Bolt holes: 7 mm through the plate.
bolts = [
    Solid.cylinder(radius=3.5, height=8.0, position=(x, y, 5.0), name=f"bolt_{i}")
    for i, (x, y) in enumerate(((-45.0, -20.0), (-45.0, 20.0), (45.0, -20.0), (45.0, 20.0)))
]

# Lightening cutouts: rounded triangles with 3 mm corner radii.
def rounded_triangle(vertices, radius, name):
    """Prism through the plate whose triangle has corners rounded by radius."""
    (ax, ay), (bx, by), (cx, cy) = vertices
    a = math.dist((bx, by), (cx, cy))
    b = math.dist((ax, ay), (cx, cy))
    c = math.dist((ax, ay), (bx, by))
    ix = (a * ax + b * bx + c * cx) / (a + b + c)
    iy = (a * ay + b * by + c * cy) / (a + b + c)
    area = abs((bx - ax) * (cy - ay) - (cx - ax) * (by - ay)) / 2.0
    scale = 1.0 - radius / (2.0 * area / (a + b + c))  # inradius shrinks by radius
    inset = [(ix + (x - ix) * scale, iy + (y - iy) * scale) for x, y in vertices]
    prism = extrude(
        PolygonProfile(inset, plane=SketchPlane(origin=(0.0, 0.0, 5.0)), name=name),
        depth=40.0,
    )
    return Offset(prism, radius)


cutouts = [
    rounded_triangle([(-54.0, -13.0), (-54.0, 13.0), (-25.0, 0.0)], 3.0, "cutout_left"),
    rounded_triangle([(54.0, -13.0), (25.0, 0.0), (54.0, 13.0)], 3.0, "cutout_right"),
]

scene = Difference(body, pin, *bolts, *cutouts, smoothness=0.0)
