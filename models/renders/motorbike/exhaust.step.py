"""Exhaust entry: head pipe + oval chrome muffler on the rider right, bike frame."""

from build123d import Compound

import _drivetrain as B


DISPLAY_NAME = "Motorbike exhaust"


def gen_step():
    built = B.build_exhaust()
    if isinstance(built, list):
        return Compound(children=built, label="exhaust")
    return built
