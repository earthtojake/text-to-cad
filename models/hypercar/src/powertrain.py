"""Hypercar system: powertrain — engine, intake, exhaust, transaxle, driveshafts.

A stage of the car: the group `lib/powertrain.py` builds, which `hypercar.py`
calls in its body. A `@memo` function: an edit that does not reach its code
replays it from the worker's memory instead of running it.
"""

from cadgen import memo

from lib import powertrain as powertrain_lib


@memo
def powertrain():
    built = powertrain_lib.build()
    return built
