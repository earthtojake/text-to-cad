"""F-14D system: nose_gear — leg, wheels, launch bar, doors, bay.

A stage of the aircraft: the group `lib/nose_gear.py` builds, already on its gear
stance, which `f14d.py` calls in its body. A `@memo` function: an edit that does
not reach its code replays it from the worker's memory instead of running it.
"""

from cadgen import memo

from lib import nose_gear as nose_gear_lib


@memo
def nose_gear():
    group = nose_gear_lib.build()
    return group
