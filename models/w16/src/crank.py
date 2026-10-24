"""W16 system: crank — crankshaft, damper, flywheel.

A stage of the engine: the parts `lib/bottom_end.py` builds, as one labelled group,
which `w16.py` calls in its body. A `@memo` function: an edit that does not
reach its code replays it from the worker's memory instead of running it.
"""

from cadgen import memo

import build123d as bd

from lib import bottom_end as bottom_end_lib
from lib import spec as S


@memo
def crank():
    parts = bottom_end_lib.build(S.SECTIONED)
    if not parts:
        raise RuntimeError("bottom_end.build() produced no parts")
    group = bd.Compound(children=parts, label="crank")
    return group
