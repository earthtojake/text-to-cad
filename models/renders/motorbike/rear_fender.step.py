"""Rear fender entry: cream arc over the rear tire, bike frame."""

from build123d import Compound

import _bodywork as B


DISPLAY_NAME = "Motorbike rear fender"


def gen_step():
    built = B.build_rear_fender()
    if isinstance(built, list):
        return Compound(children=built, label="rear_fender")
    return built
