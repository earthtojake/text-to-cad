"""Hypercar system: suspension_front — wishbones, uprights, pushrods, rockers, coilovers.

A stage of the car: the group `lib/suspension_front.py` builds, which `hypercar.py`
calls in its body. A `@memo` function: an edit that does not reach its code
replays it from the worker's memory instead of running it.
"""

from cadgen import memo

from lib import suspension_front as suspension_front_lib


@memo
def suspension_front():
    built = suspension_front_lib.build()
    return built
