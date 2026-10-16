"""A hollow space-frame node in millimetres: six tubes blended into one hub.

The kind of part fields are for. Six 20 mm tubes leave a hub at different
angles, every junction is blended, and the whole node is hollowed to a 2 mm
wall that follows the blends, with every tube open at its end for a strut
to slide in. In B-rep each step is fragile: filleting six intersecting
cylinders, then shelling the filleted solid, is where OpenCascade most
often refuses. Here it is three field operations:

1. `Union(..., smoothness=k)` blends every junction at once.
2. `Shell(solid, t)` turns the blended solid into a wall of thickness t,
   centred on its surface, so the wall stays 2 mm through every blend.
3. `Intersection` with a ball cuts every tube at the same distance from
   the centre at once, opening the shell (each end is a slightly domed
   ring, since the cut is a sphere).

A strut socket that needs a tighter fit than the wall gives is one more
operation: `Offset` grows or shrinks a field by a uniform distance.
"""

import math

from cadjoint.construction import Solid
from cadjoint.sdf import Rotate, Shell
from cadjoint.sdf.boolean import Intersection, Union

TUBE_RADIUS = 10.0
TUBE_REACH = 44.0     # hub centre to tube end
WALL = 2.0
BLEND = 4.0           # smoothness k: the blend spans about 4k = 16 mm

hub = Solid.sphere(radius=15.0, name="hub")

# Tube directions as (tilt from +Z, turn about Z), in degrees: one straight
# up, three splayed downward like a tripod, two raking sideways.
DIRECTIONS = [(0, 0), (115, 0), (115, 120), (115, 240), (70, 60), (70, 300)]
tubes = []
for i, (tilt, turn) in enumerate(DIRECTIONS):
    tube = Solid.cylinder(
        radius=TUBE_RADIUS, height=TUBE_REACH / 2, position=(0.0, 0.0, TUBE_REACH / 2),
        name=f"tube_{i}",
    )
    tube = Rotate(Rotate(tube, "y", math.radians(tilt)), "z", math.radians(turn))
    tubes.append(tube)

solid = Union(hub, *tubes, smoothness=BLEND)
wall = Shell(solid, WALL)

# Open every tube: keep only what lies within TUBE_REACH - 4 of the centre.
# The cut is sharp, so each opening is a clean ring.
reach = Solid.sphere(radius=TUBE_REACH - 4.0, name="reach")
scene = Intersection(wall, reach, smoothness=0.0)
