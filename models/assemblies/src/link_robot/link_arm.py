from __future__ import annotations
# An arm carrying two pins: two placements of one pin, a plain function's result
# moved twice (one prototype, two instances in the document).

import build123d as bd

from link_pin import link_pin


def link_arm():
    bar = bd.Box(40.0, 8.0, 4.0)
    bar.label = "bar"
    pin = link_pin()
    left = pin.moved(bd.Location((-15.0, 0.0, 2.0)))
    left.label = "pin_left"
    right = pin.moved(bd.Location((15.0, 0.0, 2.0)))
    right.label = "pin_right"
    return bd.Compound(children=[bar, left, right], label="link_arm")
