"""Hypercar system: chassis — monocoque tub, subframes, crash structures.

A stage of the car: the group `lib/chassis.py` builds, which `hypercar.py`
calls in its body. A `@memo` function: an edit that does not reach its code
replays it from the worker's memory instead of running it.
"""

from cadgen import memo

from lib import chassis as chassis_lib


@memo
def chassis():
    built = chassis_lib.build()
    return built
