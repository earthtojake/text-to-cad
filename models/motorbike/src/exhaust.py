"""Exhaust entry: head pipe + oval chrome muffler on the rider right, bike frame."""

from __future__ import annotations

import build123d as bd
from cadgen import model

from lib import drivetrain as B


@model
def exhaust():
    built = B.build_exhaust()
    if isinstance(built, list):
        return bd.Compound(children=built, label="exhaust")
    return built


if __name__ == "__main__":
    exhaust()
