"""W16 system: covers — cam covers, coils, plug wells, breathers.

A stage of the engine: the parts `lib/covers.py` builds, as one labelled group,
which `w16.py` calls in its body. A `@memo` function: an edit that does not
reach its code replays it from the worker's memory instead of running it.
"""

from cadgen import memo

import build123d as bd

from lib import covers as covers_lib
from lib import spec as S


@memo
def covers():
    parts = covers_lib.build(S.SECTIONED)
    if not parts:
        raise RuntimeError("covers.build() produced no parts")
    group = bd.Compound(children=parts, label="covers")
    return group
