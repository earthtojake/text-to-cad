"""Hinged-lid box generator: open-top base box + hinged lid (build123d).

Units: millimeters. Origin: center of the base box footprint, Z up.
Artifacts: base.stl, lid.stl, hinged_lid.step beside this source.
"""

from build123d import Box, Cylinder, Pos, Rot, export_step, export_stl

WALL = 2.0
LID_T = 2.0  # lid plate thickness (mm); nominal design value: 2.0

BASE_X, BASE_Y, BASE_Z = 60.0, 40.0, 20.0
LUG_R = 4.0
PIN_R = 2.1
HINGE_Y = BASE_Y / 2  # hinge axis sits on the back top edge, z = BASE_Z
HINGE_Z = BASE_Z

base = Pos(0, 0, BASE_Z / 2) * Box(BASE_X, BASE_Y, BASE_Z)
inner = Pos(0, 0, WALL + (BASE_Z - WALL) / 2) * Box(
    BASE_X - 2 * WALL, BASE_Y - 2 * WALL, BASE_Z - WALL
)
base -= inner

for lug_x in (-22.0, 22.0):
    lug = Pos(lug_x, HINGE_Y, HINGE_Z) * Rot(0, 90, 0) * Cylinder(LUG_R, 8.0)
    bore = Pos(lug_x, HINGE_Y, HINGE_Z) * Rot(0, 90, 0) * Cylinder(PIN_R, 12.0)
    base += lug - bore

lid = Pos(0, 0, HINGE_Z + LID_T / 2) * Box(BASE_X, BASE_Y, LID_T)
knuckle = Pos(0, HINGE_Y, HINGE_Z) * Rot(0, 90, 0) * Cylinder(LUG_R, 28.0)
knuckle_bore = Pos(0, HINGE_Y, HINGE_Z) * Rot(0, 90, 0) * Cylinder(PIN_R, 30.0)
lid += knuckle - knuckle_bore

export_stl(base, "base.stl")
export_stl(lid, "lid.stl")
export_step(base, "base.step")
export_step(lid, "lid.step")
print(f"exported base/lid STL+STEP, LID_T={LID_T}")
