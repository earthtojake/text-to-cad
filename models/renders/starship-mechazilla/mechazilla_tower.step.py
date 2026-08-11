"""SpaceX Mechazilla launch tower + arms - standalone component entry.

Reuses the exact tower geometry from the shared helper
`starship_mechazilla_parts.py` (same coordinates it occupies in the full
`starship_mechazilla.step.py` assembly): the ~146 m lattice tower with
platforms/cabling/standpipes, the rail-guided carriage, the two chopstick
catch arms, and the ship quick-disconnect arm.

Ships with a chopstick catch/close animation (`mechazilla_tower.params.js`)
that swings the arms from the wide catch-ready pose down to closed capture,
retracts the QD arm clear, and lets the carriage ride the rails.

Child order (sidecar ref contract): 1 static tower, 2 carriage,
3 chopstick arm port (+Y), 4 chopstick arm starboard (-Y), 5 QD arm.
"""

import starship_mechazilla_parts as smz


def gen_step():
    return {
        "shape": smz.build_tower_group(),
        "params": "mechazilla_tower.params.js",
    }
