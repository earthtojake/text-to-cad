"""Hypercar system: suspension_rear — the same, rear.

A stage of the car: the group `lib/suspension_rear.py` builds, which `hypercar.py`
calls in its body. A `@memo` function: an edit that does not reach its code
replays it from the worker's memory instead of running it.
"""

from cadgen import memo

from lib import suspension_rear as suspension_rear_lib


@memo
def suspension_rear():
    built = suspension_rear_lib.build()
    return built
