"""Complete movement: base (plate/train/escapement/balance) + keyless and
motion works + chronograph works, all authored in the shared MOVEMENT local
frame (see `lib/spec.py`), so composition is identity — no re-posing here.
"""

import chrono_works
import keyless_works
import movement_base
from cadgen import build123d as bd
from cadgen import step
from cadgen.compose import memo

# Composition is by FUNCTION: importing a sibling model links it (import never
# builds), and `memo` caches each child's geometry as a traced SCOPE keyed by
# its own source closure — an edit that does not reach a child's files skips
# that child's Python and kernel work entirely.
_BASE = memo(movement_base.movement_base)
_KEYLESS = memo(keyless_works.keyless_works)
_CHRONO = memo(chrono_works.chrono_works)


@step(out="../STEP/movement.step")
def movement():
    children = []

    base = _BASE()
    base.label = "movement_base"
    children.append(base)

    keyless = _KEYLESS()
    keyless.label = "keyless_works"
    children.append(keyless)

    chrono = _CHRONO()
    chrono.label = "chronograph_works"
    children.append(chrono)

    return bd.Compound(children=children, label="movement")


if __name__ == "__main__":
    movement()
