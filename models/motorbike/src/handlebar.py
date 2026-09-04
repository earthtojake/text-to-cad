"""Handlebar entry: bar + collar + grips + levers at the stem top, bike frame."""

from __future__ import annotations

from cadgen import build123d as bd
from cadgen import step

from lib import frontend as B
from lib import spec as S

# Where a bar-end mirror's stalk meets the bar, rider-left and rider-right. The
# handlebar owns these points; mirror.py and motorbike.py read them. Reading a
# constant from a model file is a SOURCE edge: the readers depend on this whole
# file, so any edit here (not only to these lines) makes them stale.
_TOP = S.steer_point(S.STEM_TOP_T)
MIRROR_MOUNT_LEFT = (_TOP[0] - 16.0, 235.0, _TOP[2] + 6.0)
MIRROR_MOUNT_RIGHT = (MIRROR_MOUNT_LEFT[0], -MIRROR_MOUNT_LEFT[1], MIRROR_MOUNT_LEFT[2])


@step(out="../STEP/handlebar.step")
def handlebar():
    built = B.build_handlebar()
    if isinstance(built, list):
        return bd.Compound(children=built, label="handlebar")
    return built


if __name__ == "__main__":
    handlebar()
