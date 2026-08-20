"""Handlebar entry: bar + collar + grips + levers at the stem top, bike frame."""

from build123d import Compound

import _frontend as B


DISPLAY_NAME = "Motorbike handlebar"


def gen_step():
    built = B.build_handlebar()
    if isinstance(built, list):
        return Compound(children=built, label="handlebar")
    return built
