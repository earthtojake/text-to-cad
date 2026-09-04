"""Complete movement: base (plate/train/escapement/balance) + keyless and
motion works + chronograph works, all authored in the shared MOVEMENT local
frame (see `lib/spec.py`), so composition is identity — no re-posing here.
"""

import chrono_works
import keyless_works
import movement_base
from cadgen import build123d as bd
from cadgen import step

# Composition is by FUNCTION: importing a sibling model links it (import never
# builds), and calling it inside this body builds it if stale — on its own
# worker, in parallel with its siblings — or loads it. An edit that does not
# reach a child's files skips that child's Python and kernel work entirely.


@step(out="../STEP/movement.step")
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
