"""A 90 mm planter in millimetres: revolved profile, hollowed, drained, on feet.

Exercises the sketch path: a revolved polygon, a Shell to hollow it, a
rounded-rectangle extrusion patterned around the axis, and raw primitives
placed with Translate and Rotate.
"""

import math

from cadjoint.construction import PolygonProfile, SketchPlane, extrude, revolve
from cadjoint.sdf import PolarPattern, Rotate, Shell, Sphere, Torus, Translate
from cadjoint.sdf.boolean import Difference, Intersection, Union
from cadjoint.construction import Solid

# Revolve: profile x is the radius, profile y runs along the axis. A plane
# with normal +Y has in-plane axes u = -X, v = +Z, so the axis is world Z.
# The profile is mirrored across x = 0: an edge lying on the axis would be
# a false surface in the field, and Shell would wrap a wall around it.
profile = PolygonProfile(
    [(-32.0, 0.0), (32.0, 0.0), (45.0, 70.0), (-45.0, 70.0)],
    plane=SketchPlane(origin=(0, 0, 0), normal=(0, 1, 0)),
    name="planter_profile",
)
solid = revolve(profile)

# Hollow it: a 3 mm wall centred on the surface, then open the top with an
# intersection against a box that stops 2 mm below the rim.
wall = Shell(solid, 3.0)
keep = Solid.box(size=(60, 60, 34), position=(0, 0, 33.5), name="keep")
pot = Union(Intersection(wall, keep, smoothness=0.0), Solid.cylinder(
    radius=32.0, height=1.5, position=(0, 0, 0.0), name="floor"), smoothness=0.5)

# A rolled rim: a torus in the XY plane, lifted to the top edge.
rim = Translate(Torus(44.0, 2.2), (0.0, 0.0, 67.5))

# Drain: one hole through the floor.
drain = Solid.cylinder(radius=5.0, height=5.0, position=(0, 0, 0), name="drain")

# Feet: a rounded rectangle extruded symmetrically about its plane, tilted
# 10 degrees about X (Rotate takes radians), then patterned three times.
foot_profile = PolygonProfile.rounded_rect(14.0, 8.0, 3.0, name="foot")
foot = Translate(Rotate(extrude(foot_profile, depth=6.0), "x", math.radians(10.0)), (24.0, 0.0, -3.0))
feet = PolarPattern(foot, 3)

scene = Difference(Union(pot, rim, feet, smoothness=1.0), drain, smoothness=0.0)
