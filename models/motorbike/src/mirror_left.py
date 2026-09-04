"""Left bar-end mirror: one round mirror on the rider-left bar end.

`mirror_right.py` is its mirror image — a separate model built from the same
`lib/trim.py` factory, because STEP cannot express a reflection. The mount
point comes from the handlebar model: a constant imported from a model file,
tracked by value, so only a changed mount moves this mirror.
"""

from __future__ import annotations

from cadgen import build123d as bd
from cadgen import step

from handlebar import MIRROR_MOUNT_LEFT
from lib import trim as T


@step(out="../STEP/mirror_left.step")
def mirror_left():
    return bd.Compound(children=T.build_mirror(1.0, MIRROR_MOUNT_LEFT), label="mirror")


if __name__ == "__main__":
    mirror_left()
