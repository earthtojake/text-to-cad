"""W16 system: camdrive — sprockets, chains, guides, tensioners.

A stage of the engine: the parts `lib/camdrive.py` builds, as one labelled group,
which `w16.py` calls in its body. A `@memo` function: an edit that does not
reach its code replays it from the worker's memory instead of running it.
"""

from cadgen import memo

import build123d as bd

from lib import camdrive as camdrive_lib
from lib import spec as S


@memo
def camdrive():
    parts = camdrive_lib.build(S.SECTIONED)
    if not parts:
        raise RuntimeError("camdrive.build() produced no parts")
    group = bd.Compound(children=parts, label="camdrive")
    return group
