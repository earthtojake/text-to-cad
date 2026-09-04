"""Mirror entry: one round bar-end mirror (rider-left instance shown).

The assembly links this model for the left mirror and builds the right one as
its mirror image. The mount point comes from the handlebar model — a source
edge, so an edit to handlebar.py rebuilds this mirror too.
"""

from __future__ import annotations

from cadgen import build123d as bd
from cadgen import step

from handlebar import MIRROR_MOUNT_LEFT
from lib import trim as T


@step(out="../STEP/mirror.step")
def mirror():
    return bd.Compound(children=T.build_mirror(1.0, MIRROR_MOUNT_LEFT), label="mirror")


if __name__ == "__main__":
    mirror()
