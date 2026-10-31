from __future__ import annotations
# A pin: the leaf every link_* part composes. Small on purpose: the three files
# exercise one B-rep placed several times through two levels, not modelling.

import build123d as bd


def link_pin():
    return bd.Cylinder(radius=2.0, height=12.0)
