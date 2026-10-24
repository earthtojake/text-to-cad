"""W16 system: block — block casting + main caps + shells + block fasteners.

A stage of the engine: the parts `lib/block.py` builds, as one labelled group,
which `w16.py` calls in its body. A `@memo` function: an edit that does not
reach its code replays it from the worker's memory instead of running it.
"""

from cadgen import memo

import build123d as bd

from lib import block as block_lib
from lib import spec as S


@memo
def block():
    parts = block_lib.build(S.SECTIONED)
    if not parts:
        raise RuntimeError("block.build() produced no parts")
    group = bd.Compound(children=parts, label="block")
    return group
