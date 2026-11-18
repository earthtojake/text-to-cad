from __future__ import annotations
from cad import model
# A three-axis gantry router as a machine's twin: a joint per machine axis, each named for its
# letter, so the viewer's Position > Machine row poses it where a controller says the machine is
# (`cad_server/machines`). The gantry slides along Y on the bed, the carriage along X on the gantry and
# the spindle along Z on the carriage. Each joint is at 0 at the machine's zero, the corner it homes
# to, and its range is the machine's travel: change `TRAVEL` to the machine being watched.

import build123d as bd

# Each axis's travel in millimetres, from machine zero: X and Y forward from the front-left corner,
# Z down from the top of its stroke.
TRAVEL = {"x": (0.0, 800.0), "y": (0.0, 800.0), "z": (-100.0, 0.0)}
BED = (900.0, 900.0, 40.0)


def _slide(fixed: bd.Shape, moving: bd.Shape, label: str, origin, direction, limits) -> None:
    """``moving`` slides along the axis on ``fixed``: build123d's linear joint, the moving side's
    rigid joint on the joint's frame, connected at 0 where the parts stand."""
    bd.LinearJoint(label, fixed, axis=bd.Axis(origin, direction), linear_range=limits)
    bd.RigidJoint(label, moving, fixed.location * fixed.joints[label].relative_axis.location)
    fixed.joints[label].connect_to(moving.joints[label], position=0.0)


@model
def cnc_router():
    width, depth, height = BED
    bed = bd.Box(width, depth, height, align=(bd.Align.MIN, bd.Align.MIN, bd.Align.MIN))
    bed.label = "bed"
    # The gantry at Y = 0: two side plates and a beam across X, standing over the bed's front edge.
    side = bd.Box(30.0, 120.0, 220.0, align=(bd.Align.MIN, bd.Align.MIN, bd.Align.MIN))
    beam = bd.Pos(0.0, 40.0, 220.0) * bd.Box(width, 60.0, 80.0, align=(bd.Align.MIN, bd.Align.MIN, bd.Align.MIN))
    gantry = bd.Pos(-30.0, 0.0, height) * side + bd.Pos(width, 0.0, height) * side + bd.Pos(0.0, 0.0, height) * beam
    gantry.label = "gantry"
    # The carriage at X = 50 (where the spindle's centre is at machine X = 0), on the beam's front face.
    carriage = bd.Pos(20.0, 0.0, height + 180.0) * bd.Box(60.0, 40.0, 160.0, align=(bd.Align.MIN, bd.Align.MIN, bd.Align.MIN))
    carriage.label = "carriage"
    # The spindle at the top of its stroke (Z = 0), in front of the carriage.
    spindle = (bd.Pos(50.0, -30.0, height + 120.0) * bd.Cylinder(30.0, 160.0, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
               + bd.Pos(50.0, -30.0, height + 80.0) * bd.Cylinder(4.0, 40.0, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)))
    spindle.label = "spindle"
    _slide(bed, gantry, "y", (0.0, 0.0, height), (0.0, 1.0, 0.0), TRAVEL["y"])
    _slide(gantry, carriage, "x", (0.0, 0.0, height + 220.0), (1.0, 0.0, 0.0), TRAVEL["x"])
    _slide(carriage, spindle, "z", (50.0, -30.0, height + 120.0), (0.0, 0.0, 1.0), TRAVEL["z"])
    return bd.Compound(children=[bed, gantry, carriage, spindle], label="cnc_router")


if __name__ == "__main__":
    cnc_router()
