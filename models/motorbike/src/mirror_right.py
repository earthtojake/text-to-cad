"""Right bar-end mirror: the left mirror's mirror image, as its own part.

Same `lib/trim.py` factory as `mirror_left.py`, handed the rider-right side
and mount. A reflection is new geometry, not a placement, so the right mirror
has its own geometry and its own place in the assembly.
"""

from __future__ import annotations

import build123d as bd
from cadgen import model

from handlebar import MIRROR_MOUNT_RIGHT
from lib import trim as T


@model
def mirror_right():
    return bd.Compound(children=T.build_mirror(-1.0, MIRROR_MOUNT_RIGHT), label="mirror")


if __name__ == "__main__":
    mirror_right()
