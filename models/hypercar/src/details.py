"""Hypercar system: details — mirrors, badges, filler, vents, fasteners.

A stage of the car: the group `lib/details.py` builds, which `hypercar.py`
calls in its body. A `@memo` function: an edit that does not reach its code
replays it from the worker's memory instead of running it.
"""

from cadgen import memo

from lib import details as details_lib


@memo
def details():
    built = details_lib.build()
    return built
