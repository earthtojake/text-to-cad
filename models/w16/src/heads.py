"""W16 system: heads — two heads, plugs, core plugs, head bolts.

A stage of the engine: the parts `lib/heads.py` builds, as one labelled group,
which `w16.py` calls in its body. A `@memo` function: an edit that does not
reach its code replays it from the worker's memory instead of running it.
"""

from cadgen import memo

import build123d as bd

from lib import heads as heads_lib
from lib import spec as S


@memo
def heads():
    parts = heads_lib.build(S.SECTIONED)
    if not parts:
        raise RuntimeError("heads.build() produced no parts")
    group = bd.Compound(children=parts, label="heads")
    return group
