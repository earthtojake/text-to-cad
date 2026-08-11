"""SpaceX Starship upper stage - standalone component entry.

Reuses the exact ship geometry from the shared helper
`starship_mechazilla_parts.py` (same coordinates it occupies in the full
`starship_mechazilla.step.py` assembly), so this component is identical to its
counterpart in the stack. Ships with an exploded-view animation
(`starship.params.js`) that separates the nosecone, barrel shell, thermal-tile
shell, aft flaps, and engines to reveal the internal tank domes, common dome,
LOX header tank, and header transfer tube.

Child order (sidecar ref contract): 1 shell, 2 nose, 3 barrel tiles,
4 interior, 5 aft flap port, 6 aft flap starboard, 7-9 sea-level Raptors,
10-12 vacuum Raptors.
"""

import starship_mechazilla_parts as smz


def gen_step():
    return {
        "shape": smz.build_ship(),
        "params": "starship.params.js",
    }
