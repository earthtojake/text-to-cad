"""W16 system: oil_system — dry-sump pan, windage tray, pumps, filter.

A stage of the engine: the parts `lib/oil_system.py` builds, as one labelled group,
which `w16.py` calls in its body. A `@memo` function: an edit that does not
reach its code replays it from the worker's memory instead of running it.
"""

from cadgen import memo

import build123d as bd

from lib import oil_system as oil_system_lib
from lib import spec as S


@memo
def oil_system():
    parts = oil_system_lib.build(S.SECTIONED)
    if not parts:
        raise RuntimeError("oil_system.build() produced no parts")
    group = bd.Compound(children=parts, label="oil_system")
    return group
