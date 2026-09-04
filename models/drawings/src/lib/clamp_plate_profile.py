"""The clamp plate's 3D geometry (plain module: no @dxf/@step here).

Shared code, not a model — `src/*.py` is the model catalog and everything under
`src/lib/` is a helper. The drawing (`src/clamp_plate.py`) projects this solid's
top face to a cut profile, which is the STEP-projection workflow without a STEP
artifact: this drawings project deliberately emits drawings only.

Prompt: Flat clamp plate with rounded corners, two clamping bolt holes, and a
central adjustment slot.
"""

from __future__ import annotations

from cadgen import build123d as bd

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
