"""SpaceX Super Heavy booster - standalone component entry.

Reuses the exact booster geometry from the shared helper
`starship_mechazilla_parts.py` (same coordinates it occupies in the full
`starship_mechazilla.step.py` assembly). Ships with an exploded-view animation
(`super_heavy.params.js`) that lifts the vented hot-stage ring off the top,
slides the barrel shell radially outward, fans the four grid fins out, and
drops the 33 Raptor engines down to reveal the internal LOX/CH4 tank domes,
common dome, methane downcomer, and engine manifold.

Child order (sidecar ref contract): 1 shell, 2 interior, 3 hot-stage ring,
4-7 grid fins, 8-40 Raptor engines (3 center, 10 middle, 20 outer).
"""

import starship_mechazilla_parts as smz


def gen_step():
    return {
        "shape": smz.build_booster(),
        "params": "super_heavy.params.js",
    }
