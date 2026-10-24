"""Headlight entry: chrome shell + clear dome lens on the apron, bike frame."""

from __future__ import annotations

import build123d as bd
from cadgen import model

from lib import trim as B


@model
def headlight():
    built = B.build_headlight()
    if isinstance(built, list):
        return bd.Compound(children=built, label="headlight")
    return built


if __name__ == "__main__":
    headlight()
