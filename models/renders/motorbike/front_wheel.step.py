"""Front wheel entry: tire + five-spoke cast rim + brake disc, bike frame."""

from build123d import Compound

import _wheels as W


DISPLAY_NAME = "Motorbike front wheel"


def gen_step():
    return Compound(children=W.build_front_wheel(), label="front_wheel")
