"""Front fork entry: telescopic fork + chrome axle on the steering axis, bike frame."""

from build123d import Compound

import _frontend as B


DISPLAY_NAME = "Motorbike front fork"


def gen_step():
    built = B.build_front_fork()
    if isinstance(built, list):
        return Compound(children=built, label="front_fork")
    return built
