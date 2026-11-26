"""Front wheel entry: tire + five-spoke cast rim + brake disc, bike frame."""

from __future__ import annotations

import build123d as bd
from cad import xbf

from lib import wheels as W


@xbf
def front_wheel():
    return bd.Compound(children=W.build_front_wheel(), label="front_wheel")


if __name__ == "__main__":
    front_wheel()
