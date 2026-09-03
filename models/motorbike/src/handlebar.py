"""Handlebar entry: bar + collar + grips + levers at the stem top, bike frame."""

from __future__ import annotations

from cadgen import build123d as bd
from cadgen import step

from lib import frontend as B


@step(out="../STEP/handlebar.step")
def handlebar():
    built = B.build_handlebar()
    if isinstance(built, list):
        return bd.Compound(children=built, label="handlebar")
    return built


if __name__ == "__main__":
    handlebar()
