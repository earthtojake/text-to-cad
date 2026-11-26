"""Rear wheel entry: tire + five-spoke cast rim + brake drum, bike frame."""

from __future__ import annotations

import build123d as bd
from cad import xbf

from lib import wheels as W


@xbf
def rear_wheel():
    return bd.Compound(children=W.build_rear_wheel(), label="rear_wheel")


if __name__ == "__main__":
    rear_wheel()
