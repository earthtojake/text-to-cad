"""F-14D system: main_gear — legs, wheels, brakes, doors, bays.

A stage of the aircraft: the group `lib/main_gear.py` builds, already on its gear
stance, which `f14d.py` calls in its body. A `@memo` function: an edit that does
not reach its code replays it from the worker's memory instead of running it.
"""

from cadgen import memo

from lib import main_gear as main_gear_lib


@memo
def main_gear():
    group = main_gear_lib.build()
    return group
