"""Rear shock entry: coilover between the frame lug and engine boss, bike frame."""

from __future__ import annotations

import build123d as bd
from cadgen import model

from lib import drivetrain as B


@model
def rear_shock():
    built = B.build_rear_shock()
    if isinstance(built, list):
        return bd.Compound(children=built, label="rear_shock")
    return built


if __name__ == "__main__":
    rear_shock()
