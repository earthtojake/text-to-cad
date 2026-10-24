"""The clamp plate's 3D geometry (plain module: no model here).

Shared code, not a model: the drawing (`clamp_plate.py`) lays this solid's top
face into the XY plane as its cut profile, from live geometry, never a file a
build wrote.

Prompt: Flat clamp plate with rounded corners, two clamping bolt holes, and a
central adjustment slot.
"""

from __future__ import annotations

import build123d as bd

LENGTH_MM = 70.0
WIDTH_MM = 40.0
THICKNESS_MM = 6.0
CORNER_RADIUS_MM = 6.0
BOLT_HOLE_DIAMETER_MM = 6.5
BOLT_SPACING_MM = 52.0
SLOT_LENGTH_MM = 24.0
SLOT_WIDTH_MM = 8.0


def plate():
    """The clamp plate as a solid, sitting on Z=0 up to THICKNESS_MM."""
    with bd.BuildPart() as part:
        with bd.BuildSketch():
            bd.RectangleRounded(LENGTH_MM, WIDTH_MM, CORNER_RADIUS_MM)
            with bd.Locations(
                (-BOLT_SPACING_MM / 2.0, 0.0), (BOLT_SPACING_MM / 2.0, 0.0)
            ):
                bd.Circle(BOLT_HOLE_DIAMETER_MM / 2.0, mode=bd.Mode.SUBTRACT)
            bd.SlotOverall(SLOT_LENGTH_MM, SLOT_WIDTH_MM, mode=bd.Mode.SUBTRACT)
        bd.extrude(amount=THICKNESS_MM)
    return part.part
