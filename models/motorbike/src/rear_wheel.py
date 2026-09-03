"""Rear wheel entry: tire + five-spoke cast rim + brake drum, bike frame."""

from __future__ import annotations

from cadgen import build123d as bd
from cadgen import step

from lib import wheels as W


@step(out="../STEP/rear_wheel.step")
def rear_wheel():
    return bd.Compound(children=W.build_rear_wheel(), label="rear_wheel")


if __name__ == "__main__":
    rear_wheel()
