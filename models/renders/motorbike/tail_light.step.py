"""Tail light entry: housing + red lens on the tail, bike frame."""

from build123d import Compound

import _trim as B


DISPLAY_NAME = "Motorbike tail light"


def gen_step():
    built = B.build_tail_light()
    if isinstance(built, list):
        return Compound(children=built, label="tail_light")
    return built
