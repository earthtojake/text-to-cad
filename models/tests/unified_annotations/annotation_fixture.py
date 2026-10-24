from cadgen import Material, materials, model
from cadgen.ap242 import configuration_sequence, mechanism_state

import math

import build123d as bd

# The old sidecar's two finishes. Steel keeps each part's own colour (`color=None`);
# the paint is a colour, so it carries one: blue, at opacity 0.5.
STEEL = materials.steel.but(color=None, metallic=0.8, roughness=0.32, description="Brushed steel")
PAINT = Material(name="Blue paint", family="other", color="#2469ac80", roughness=0.42)
ARM_GREEN = "#37966f99"  # "#37966F", alpha 0.6


def _lift(t):
    return {"lift": 8 * math.sin(math.pi * t / 2)}


@model
def annotation_fixture():
    base = bd.Pos(0, 0, 3) * bd.Box(72, 52, 6)
    shaft = bd.Pos(0, 0, 18) * bd.Cylinder(5, 24)
    arm = bd.Pos(18, 0, 12) * bd.Box(44, 12, 8)
    base.label, shaft.label, arm.label = "base", "shaft", "arm"
    arm.color = ARM_GREEN
    base.material = shaft.material = STEEL
    arm.material = PAINT
    pins = []
    for x in range(4):
        for y in (-18, 18):
            pin = bd.Pos(-27 + 18 * x, y, 9) * bd.Cylinder(2, 6)
            pin.label = f"pin_{x}_{y}"
            pins.append(pin)

    # The mates as joints: the arm swings about the shaft's axis, the shaft lifts.
    bd.RevoluteJoint("swing", base, axis=bd.Axis((0, 0, 10), (0, 0, 1)), angular_range=(-80, 80))
    bd.RigidJoint("swing", arm, bd.Location((0, 0, 10)))
    base.joints["swing"].connect_to(arm.joints["swing"], angle=0)
    bd.LinearJoint("lift", base, axis=bd.Axis((0, 0, 0), (0, 0, 1)), linear_range=(-8, 8))
    bd.RigidJoint("lift", shaft, bd.Location((0, 0, 0)))
    base.joints["lift"].connect_to(shaft.joints["lift"], position=0)

    fixture = bd.Compound(children=[base, shaft, arm, *pins], label="annotation_fixture")
    mechanism_state(fixture, "open", swing=45)
    # Up 8 mm, down 8 mm and home in 4 s: it ends where it starts, so a player repeats it
    # as the old looping clip did (a motion has no loop of its own).
    return configuration_sequence(fixture, "demo", _lift, duration=4)


if __name__ == "__main__":
    annotation_fixture()
