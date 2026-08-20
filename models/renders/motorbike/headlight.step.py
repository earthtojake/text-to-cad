"""Headlight entry: chrome shell + clear dome lens on the apron, bike frame."""

from build123d import Compound

import _trim as B


DISPLAY_NAME = "Motorbike headlight"


def gen_step():
    built = B.build_headlight()
    if isinstance(built, list):
        return Compound(children=built, label="headlight")
    return built
