"""Front fender entry: cream arc band over the front tire, bike frame."""

from __future__ import annotations

import build123d as bd
from cadgen import model

from lib import frontend as B


@model
def front_fender():
    built = B.build_front_fender()
    if isinstance(built, list):
        return bd.Compound(children=built, label="front_fender")
    return built


if __name__ == "__main__":
    front_fender()
