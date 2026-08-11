"""SpaceX orbital launch mount (OLM) - standalone component entry.

Reuses the exact launch-mount geometry from the shared helper
`starship_mechazilla_parts.py` (same coordinates it occupies in the full
`starship_mechazilla.step.py` assembly): the six-leg steel table with 20
hold-down clamps, the water-cooled flame deflector, the deluge/water supply
system, and the booster quick-disconnect.

Ships with an exploded-view animation (`launch_mount.params.js`) that lifts
the clamp table off the legs, raises the flame deflector, drops the water
system, and slides the booster QD aside to show how the pad hardware stacks.

Child order (sidecar ref contract): 1 legs, 2 table + clamps,
3 flame deflector, 4 water/deluge system, 5 booster QD.
"""

import starship_mechazilla_parts as smz


def gen_step():
    return {
        "shape": smz.build_olm(),
        "params": "launch_mount.params.js",
    }
