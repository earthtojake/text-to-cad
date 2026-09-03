"""Tail light entry: housing + red lens on the tail, bike frame."""

from __future__ import annotations

from cadgen import build123d as bd
from cadgen import step

from lib import trim as B


@step(out="../STEP/tail_light.step")
def tail_light():
    built = B.build_tail_light()
    if isinstance(built, list):
        return bd.Compound(children=built, label="tail_light")
    return built


if __name__ == "__main__":
    tail_light()
