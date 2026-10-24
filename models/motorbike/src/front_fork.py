"""Front fork entry: telescopic fork + chrome axle on the steering axis, bike frame."""

from __future__ import annotations

import build123d as bd
from cadgen import model

from lib import frontend as B


@model
def front_fork():
    built = B.build_front_fork()
    if isinstance(built, list):
        return bd.Compound(children=built, label="front_fork")
    return built


if __name__ == "__main__":
    front_fork()
