"""Extrude the same dimensioned profiles used by the vector logo generator."""
from __future__ import annotations

import json
from pathlib import Path

from cadgen import build123d as bd
from cadgen import srgb

PROFILE_PATH = Path(__file__).resolve().parents[1] / "profiles.json"


def make_logo(text: str, lighter: tuple[int, ...] = ()) -> bd.Compound:
    profiles = json.loads(PROFILE_PATH.read_text())
    unit = profiles["unitMm"]
    height = profiles["height"]
    thickness = profiles["depth"] * unit
    advance = (profiles["width"] + profiles["gap"]) * unit
    letters = []
    for index, character in enumerate(text):
        loops = profiles["letters"][character]
        wires = []
        for loop in loops:
            # Screen Y points down; CAD Y points up. The bottom edge is Y=0.
            points = [(x * unit, (height - y) * unit, 0) for x, y in loop[:-1]]
            wires.append(bd.Wire.make_polygon(points, close=True))
        face = bd.Face(wires[0], wires[1:])
        # Some profiles include collinear segments; merge coplanar extrusion
        # faces so the STEP has only meaningful model edges.
        solid = bd.Solid.extrude(face, (0, 0, thickness)).clean()
        solid = solid.moved(bd.Location((index * advance, 0, 0)))
        solid.label = f"letter_{index + 1:02d}_{character}"
        solid.color = srgb(profiles["lighterColor" if index in lighter else "color"])
        letters.append(solid)
    return bd.Compound(children=letters, label=f"logo_{text.lower()}")
