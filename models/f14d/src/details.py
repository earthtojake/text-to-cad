"""F-14D system: details — antennas, probes, lights, wicks, vents, panels.

A stage of the aircraft: the group `lib/details.py` builds, already on its gear
stance, which `f14d.py` calls in its body. A `@memo` function: an edit that does
not reach its code replays it from the worker's memory instead of running it.
"""

from cadgen import memo

from lib import details as details_lib


@memo
def details():
    group = details_lib.build()
    return group
