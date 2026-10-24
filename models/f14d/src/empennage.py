"""F-14D system: empennage — fins, rudders, stabilators, ventral fins.

A stage of the aircraft: the group `lib/empennage.py` builds, already on its gear
stance, which `f14d.py` calls in its body. A `@memo` function: an edit that does
not reach its code replays it from the worker's memory instead of running it.
"""

from cadgen import memo

from lib import empennage as empennage_lib


@memo
def empennage():
    group = empennage_lib.build()
    return group
