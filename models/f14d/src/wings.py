"""F-14D system: wings — panels, slats, flaps, spoilers, tip lights.

A stage of the aircraft: the group `lib/wings.py` builds, already on its gear
stance, which `f14d.py` calls in its body. A `@memo` function: an edit that does
not reach its code replays it from the worker's memory instead of running it.
"""

from cadgen import memo

from lib import wings as wings_lib


@memo
def wings():
    group = wings_lib.build()
    return group
