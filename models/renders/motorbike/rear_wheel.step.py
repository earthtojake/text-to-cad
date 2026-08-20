"""Rear wheel entry: tire + five-spoke cast rim + brake drum, bike frame."""

from build123d import Compound

import _wheels as W


DISPLAY_NAME = "Motorbike rear wheel"


def gen_step():
    return Compound(children=W.build_rear_wheel(), label="rear_wheel")
