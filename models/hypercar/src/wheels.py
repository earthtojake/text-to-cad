"""Hypercar system: wheels — rims, tyres.

A stage of the car: the group `lib/wheels.py` builds, which `hypercar.py`
calls in its body. A `@memo` function: an edit that does not reach its code
replays it from the worker's memory instead of running it.
"""

from cadgen import memo

from lib import wheels as wheels_lib


@memo
def wheels():
    built = wheels_lib.build()
    return built
