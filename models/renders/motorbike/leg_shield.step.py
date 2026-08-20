"""Leg shield entry: cream step-through apron, bike frame."""

from build123d import Compound

import _bodywork as B


DISPLAY_NAME = "Motorbike leg shield"


def gen_step():
    built = B.build_leg_shield()
    if isinstance(built, list):
        return Compound(children=built, label="leg_shield")
    return built
