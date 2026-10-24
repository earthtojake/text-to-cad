"""F-14D system: inlets — ramps, splitters, bleed slots, ducts.

A stage of the aircraft: the group `lib/inlets.py` builds, already on its gear
stance, which `f14d.py` calls in its body. A `@memo` function: an edit that does
not reach its code replays it from the worker's memory instead of running it.
"""

from cadgen import memo

from lib import inlets as inlets_lib


@memo
def inlets():
    group = inlets_lib.build()
    return group
