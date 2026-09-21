"""The STEP fixture the viewer's browser tests open.

Two coloured parts, a bore through the base (so the modeling tree has a cut
feature and the topology a cylindrical face), one revolute mate, one named pose
and one routine.
"""

import cadgen
from cadgen import build123d as bd
from cadgen import srgb, step

KINEMATICS = {
    "mates": [
        cadgen.revolute(
            "hinge",
            parent="#base",
            child="#arm",
            origin=(10, 0, 0),
            direction=(0, 0, 1),
            limits=(0, 90),
        )
    ],
    "poses": {"open": {"hinge": 90}},
}

ANIMATION = r"""
export const clips = {
  swing: {
    label: "Swing",
    duration: 4,
    loop: true,
    update(t, m) {
      const angle = 45 * (1 - Math.cos((2 * Math.PI * t) / 4));
      m.get("arm").rotate([0, 0, 1], angle, [10, 0, 0]);
    },
  },
};
"""


@step(out="../STEP/hinge_block.step", kinematics=KINEMATICS, animation=ANIMATION)
def hinge_block():
    base = bd.Box(20, 20, 10) - bd.Cylinder(3, 20)
    base.label = "base"
    base.color = srgb("#3A6EA5")
    arm = bd.Pos(15, 0, 0) * bd.Box(10, 8, 8)
    arm.label = "arm"
    arm.color = srgb("#D9772B")
    return bd.Compound(children=[base, arm], label="hinge_block")


if __name__ == "__main__":
    hinge_block()
