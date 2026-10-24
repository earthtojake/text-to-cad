"""F-14D system: aft — speed brakes, beavertail, tailhook, dump mast.

A stage of the aircraft: the group `lib/aft.py` builds, already on its gear
stance, which `f14d.py` calls in its body. A `@memo` function: an edit that does
not reach its code replays it from the worker's memory instead of running it.
"""

from cadgen import memo

from lib import aft as aft_lib


@memo
def aft():
    group = aft_lib.build()
    return group
