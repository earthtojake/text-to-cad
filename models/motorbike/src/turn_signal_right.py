"""Right turn signal: the left signal's mirror image, authored at the
front-right position.

The assembly places this part twice — front-right as returned, rear-right
placed with `Pos` — exactly as it links `turn_signal_left.py`.
"""

from __future__ import annotations

import build123d as bd
from cadgen import model

from lib import spec as S
from lib import trim as T


@model
def turn_signal_right():
    x, y, z = S.FRONT_SIGNAL_POS
    return bd.Compound(children=T.build_turn_signal((x, -y, z), -1.0), label="turn_signal")


if __name__ == "__main__":
    turn_signal_right()
