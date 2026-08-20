"""Front fender entry: cream arc band over the front tire, bike frame."""

from build123d import Compound

import _frontend as B


DISPLAY_NAME = "Motorbike front fender"


def gen_step():
    built = B.build_front_fender()
    if isinstance(built, list):
        return Compound(children=built, label="front_fender")
    return built
