"""Seat entry: brown saddle on the under-seat body, bike frame."""

from build123d import Compound

import _bodywork as B


DISPLAY_NAME = "Motorbike seat"


def gen_step():
    built = B.build_seat()
    if isinstance(built, list):
        return Compound(children=built, label="seat")
    return built
