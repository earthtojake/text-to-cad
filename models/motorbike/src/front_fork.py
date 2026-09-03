"""Front fork entry: telescopic fork + chrome axle on the steering axis, bike frame."""

from __future__ import annotations

from cadgen import build123d as bd
from cadgen import step

from lib import frontend as B


@step(out="../STEP/front_fork.step")
def front_fork():
    built = B.build_front_fork()
    if isinstance(built, list):
        return bd.Compound(children=built, label="front_fork")
    return built


if __name__ == "__main__":
    front_fork()
