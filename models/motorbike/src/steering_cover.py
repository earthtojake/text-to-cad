"""Steering cover entry: head-tube shroud above the apron, bike frame."""

from __future__ import annotations

from cadgen import build123d as bd
from cadgen import step

from lib import bodywork as B


@step(out="../STEP/steering_cover.step")
def steering_cover():
    built = B.build_steering_cover()
    if isinstance(built, list):
        return bd.Compound(children=built, label="steering_cover")
    return built


if __name__ == "__main__":
    steering_cover()
