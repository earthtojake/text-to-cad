"""Complete movement: base (plate/train/escapement/balance) + keyless and
motion works + chronograph works, all authored in the shared MOVEMENT local
frame (see `lib/spec.py`), so composition is identity — no re-posing here.
"""

from cadgen import model

import chrono_works
import keyless_works
import movement_base
import build123d as bd

# Composition is by FUNCTION: each layer is a `@memo` function of a sibling file,
# and calling it inside this body runs it in the same build as a sub-assembly.
# An edit that does not reach a layer's code replays it from the worker's memory;
# inside a layer the groups of parts (`lib/mvt_*.py`, `_*_parts`) are plain
# functions: a marker per group saved nothing beyond the layers. Only this model
# and `case.py` write a file.


@model
def movement():
    children = []

    base = movement_base.movement_base()
    base.label = "movement_base"
    children.append(base)

    keyless = keyless_works.keyless_works()
    keyless.label = "keyless_works"
    children.append(keyless)

    chrono = chrono_works.chrono_works()
    chrono.label = "chronograph_works"
    children.append(chrono)

    return bd.Compound(children=children, label="movement")


if __name__ == "__main__":
    movement()
