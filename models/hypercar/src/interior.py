"""Hypercar system: interior — seats, wheel, dash, console, pedals, door cards.

A stage of the car: the group `lib/interior.py` builds, which `hypercar.py`
calls in its body. A `@memo` function: an edit that does not reach its code
replays it from the worker's memory instead of running it.
"""

from cadgen import memo

from lib import interior as interior_lib


@memo
def interior():
    built = interior_lib.build()
    return built
