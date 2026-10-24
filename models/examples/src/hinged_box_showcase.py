"""A hinged box with a lid, a latch and two feet: kinematics and an animation on one model.

The lid's hinge is the mechanism (a revolute joint, two configurations, one motion): the xbf
keeps it, and every GLB of the box carries the motion `open_close` as a clip. The showcase is the
GLB's own (`animation`): the lid opens through the mechanism's forward kinematics, the feet drop
out one after the other, the latch spins off and is hidden. The document never holds it; a GLB
exported while the model is live bakes it (`cadgen export <id> GLB/hinged_box_showcase.glb`, the
id its run prints); one exported from a saved xbf carries the motion alone.
"""

import build123d as bd

from cadgen import model
from cadgen.ap242 import configuration_sequence, mechanism_state
from cadgen.gltf import animation

HINGE = ((-40, 0, 30), (0, -1, 0))  # the hinge axis, point and direction: +angle lifts the lid


@model
def hinged_box_showcase():
    body = bd.Box(80, 50, 30, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    lid = bd.Pos(0, 0, 30) * bd.Box(80, 50, 6, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    latch = bd.Pos(42, 0, 30) * bd.Cylinder(4, 8)
    feet = [bd.Pos(x, 0, -4) * bd.Box(10, 40, 4, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
            for x in (-30, 30)]
    body.label, lid.label, latch.label = "body", "lid", "latch"
    for at, foot in enumerate(feet, 1):
        foot.label = f"foot_{at}"
    hinge = bd.Axis(*HINGE)
    bd.RevoluteJoint("hinge", body, axis=hinge, angular_range=(0, 110))
    bd.RigidJoint("hinge", lid, bd.Plane(origin=hinge.position, z_dir=hinge.direction).location)
    body.joints["hinge"].connect_to(lid.joints["hinge"], angle=0)  # as built: shut
    box = bd.Compound(children=[body, lid, latch, bd.Compound(children=feet, label="feet")],
                      label="hinged_box_showcase")
    mechanism_state(box, "shut", hinge=0)
    mechanism_state(box, "open", hinge=100)
    configuration_sequence(box, "open_close", [(0, "shut"), (1.5, "open"), (3, "shut")])

    show = animation(box, "showcase", duration=4)
    show.pose(at={0: "shut", 1.5: "open", 3.5: "shut"})
    show.stagger("feet/*", by=(0, 0, -20), step=0.5, start=0.5)
    show.rotation("latch", axis=(0, 0, 1), turns=2, start=1, end=3, interpolation="LINEAR")
    show.translation("latch", by=(30, 0, 0), start=1, end=3)
    show.hide("latch", at=3)
    return box


if __name__ == "__main__":
    hinged_box_showcase()
