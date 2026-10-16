"""A 40 mm control knob in millimetres: domed top, knurled side, shaft bore.

Exercises the primitive path: Solid primitives (half-extents, half-heights),
an intersection that domes the top, a polar pattern of grooves, and blended
versus sharp booleans.
"""

from cadjoint.construction import Solid
from cadjoint.sdf import PolarPattern
from cadjoint.sdf.boolean import Difference, Intersection

# Cylinder height is a HALF-height: this one spans z = 0 .. 16.
body = Solid.cylinder(radius=20.0, height=8.0, position=(0, 0, 8.0), name="body")

# Dome: intersect with a large sphere whose top sits 2 mm above the body.
# smoothness rounds the rim where the two meet (model units, here mm).
dome = Solid.sphere(radius=30.0, position=(0, 0, -12.0), name="dome")
knob = Intersection(body, dome, smoothness=1.0)

# Knurl: one groove on the side, repeated 24 times about Z.
groove = Solid.cylinder(radius=1.6, height=9.0, position=(20.5, 0, 8.0), name="groove")
knurl = PolarPattern(groove, 24)

# Shaft bore from below, 6 mm diameter, 10 mm deep; sharp (smoothness=0).
bore = Solid.cylinder(radius=3.0, height=5.0, position=(0, 0, 5.0), name="bore")

scene = Difference(Difference(knob, knurl, smoothness=0.5), bore, smoothness=0.0)
