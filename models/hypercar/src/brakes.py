"""Hypercar system: brakes — discs, calipers, hubs.

A stage of the car: the group `lib/brakes.py` builds, which `hypercar.py`
calls in its body. A `@memo` function: an edit that does not reach its code
replays it from the worker's memory instead of running it.
"""

from cadgen import memo

from lib import brakes as brakes_lib


@memo
def brakes():
    built = brakes_lib.build()
    return built
