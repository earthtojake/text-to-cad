from __future__ import annotations
from cadgen import step
# An arm carrying two pins. Calling ``link_pin()`` inside the build makes it a
# CHILD: built (or loaded) through the store and LINKED into this tree twice,
# once per placement.

from cadgen import build123d as bd

from link_pin import link_pin


@step(out="../STEP/link_arm.step")
def link_arm():
    bar = bd.Box(40.0, 8.0, 4.0)
    bar.label = "bar"
    pin = link_pin()
    left = pin.moved(bd.Location((-15.0, 0.0, 2.0)))
    left.label = "pin_left"
    right = pin.moved(bd.Location((15.0, 0.0, 2.0)))
    right.label = "pin_right"
    return bd.Compound(children=[bar, left, right], label="link_arm")


if __name__ == "__main__":
    link_arm()
