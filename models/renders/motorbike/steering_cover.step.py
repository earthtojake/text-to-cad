"""Steering cover entry: head-tube shroud above the apron, bike frame."""

from build123d import Compound

import _bodywork as B


DISPLAY_NAME = "Motorbike steering cover"


def gen_step():
    built = B.build_steering_cover()
    if isinstance(built, list):
        return Compound(children=built, label="steering_cover")
    return built
