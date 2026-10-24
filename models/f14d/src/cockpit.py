"""F-14D system: cockpit — tub, panels, seats, HUD, canopy, windscreen.

A stage of the aircraft: the group `lib/cockpit.py` builds, already on its gear
stance, which `f14d.py` calls in its body. A `@memo` function: an edit that does
not reach its code replays it from the worker's memory instead of running it.
"""

from cadgen import memo

from lib import cockpit as cockpit_lib


@memo
def cockpit():
    group = cockpit_lib.build()
    return group
