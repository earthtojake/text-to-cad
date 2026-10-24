"""W16 system: cams — four camshafts + caps.

A stage of the engine: the parts `lib/cams.py` builds, as one labelled group,
which `w16.py` calls in its body. A `@memo` function: an edit that does not
reach its code replays it from the worker's memory instead of running it.
"""

from cadgen import memo

import build123d as bd

from lib import cams as cams_lib
from lib import spec as S


@memo
def cams():
    parts = cams_lib.build(S.SECTIONED)
    if not parts:
        raise RuntimeError("cams.build() produced no parts")
    group = bd.Compound(children=parts, label="cams")
    return group
