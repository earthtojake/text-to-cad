from __future__ import annotations
from cadgen import step
# A pin: the leaf every link_* example composes. Small on purpose — these three
# models exercise the store's link/component decision, not modelling.

from cadgen import build123d as bd


@step(out="../STEP/link_pin.step")
def link_pin():
    return bd.Cylinder(radius=2.0, height=12.0)


if __name__ == "__main__":
    link_pin()
