# Prompt: Flat pattern for a plate with a corner gusset tab: one bend line at 45
# degrees across the top-right corner, so the triangular corner folds up as a
# tab. This is the fixture for arbitrary bend-line ORIENTATION — every other
# bend fixture's lines are vertical, and a fold that only handles constant-X
# axes renders this one wrong (or not at all).

from __future__ import annotations

from cadgen import build123d as bd
from cadgen import dxf

PLATE_LENGTH_MM = 100.0
PLATE_WIDTH_MM = 60.0
# The bend runs corner-to-corner across the top-right: from the top edge down
# to the right edge, at 45 degrees.
BEND_TOP_X_MM = 60.0
BEND_RIGHT_Y_MM = 20.0
HOLE_DIAMETER_MM = 6.0

# One mounting hole in the anchored region and one on the tab that folds.
HOLE_CENTRES_MM = ((25.0, 30.0), (88.0, 48.0))


@dxf(out="../DXF/angled_tab.dxf")
def angled_tab():
    with bd.BuildSketch() as cut:
        with bd.Locations((PLATE_LENGTH_MM / 2.0, PLATE_WIDTH_MM / 2.0)):
            bd.Rectangle(PLATE_LENGTH_MM, PLATE_WIDTH_MM)
        with bd.Locations(*HOLE_CENTRES_MM):
            bd.Circle(HOLE_DIAMETER_MM / 2.0, mode=bd.Mode.SUBTRACT)

    # The 45-degree bend, spanning the blank corner to corner so it fully
    # separates the tab from the plate.
    bend = bd.Line(
        (BEND_TOP_X_MM, PLATE_WIDTH_MM),
        (PLATE_LENGTH_MM, BEND_RIGHT_Y_MM),
    )

    return {"CUT": cut.sketch, "BEND": bend}


if __name__ == "__main__":
    angled_tab()
