"""Front wheel entry: tire + five-spoke cast rim + brake disc, bike frame."""

from __future__ import annotations

from cadgen import build123d as bd
from cadgen import step

from lib import wheels as W


@step(out="../STEP/front_wheel.step")
def front_wheel():
    return bd.Compound(children=W.build_front_wheel(), label="front_wheel")


if __name__ == "__main__":
    front_wheel()
