from __future__ import annotations
from cadgen import model
# A base with two arms and a spare pin: the one model of the group. link_arm and
# link_pin are plain functions it calls; the arm is placed twice and holds two
# placements of the pin, so the pin's B-rep is one prototype placed five times,
# two levels deep.

import build123d as bd

from link_arm import link_arm
from link_pin import link_pin


@model
def link_robot():
    base = bd.Box(60.0, 30.0, 6.0)
    base.label = "base"
    arm = link_arm()
    front = arm.moved(bd.Location((0.0, 10.0, 5.0)))
    front.label = "arm_front"
    back = arm.moved(bd.Location((0.0, -10.0, 5.0), (0.0, 0.0, 180.0)))
    back.label = "arm_back"
    spare = link_pin().moved(bd.Location((25.0, 0.0, 9.0)))
    spare.label = "pin_spare"
    return bd.Compound(children=[base, front, back, spare], label="link_robot")


if __name__ == "__main__":
    link_robot()
