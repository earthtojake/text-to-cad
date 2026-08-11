# Prompt: Flat pattern for a plate with a corner gusset tab: one bend line at 45
# degrees across the top-right corner, so the triangular corner folds up as a
# tab. This is the fixture for arbitrary bend-line ORIENTATION — every other
# bend fixture's lines are vertical, and a fold that only handles constant-X
# axes renders this one wrong (or not at all).

from __future__ import annotations

import ezdxf

PLATE_LENGTH_MM = 100.0
PLATE_WIDTH_MM = 60.0
# The bend runs corner-to-corner across the top-right: from the top edge down
# to the right edge, at 45 degrees.
BEND_TOP_X_MM = 60.0
BEND_RIGHT_Y_MM = 20.0
HOLE_DIAMETER_MM = 6.0


def gen_dxf():
    document = ezdxf.new("R2010", setup=True)
    document.units = ezdxf.units.MM
    modelspace = document.modelspace()
    document.layers.add("CUT", color=1)
    document.layers.add("BEND", linetype="DASHED", color=5)

    modelspace.add_lwpolyline(
        [
            (0.0, 0.0),
            (PLATE_LENGTH_MM, 0.0),
            (PLATE_LENGTH_MM, PLATE_WIDTH_MM),
            (0.0, PLATE_WIDTH_MM),
        ],
        close=True,
        dxfattribs={"layer": "CUT"},
    )

    # A mounting hole in the anchored region and one on the tab that folds.
    modelspace.add_circle((25.0, 30.0), radius=HOLE_DIAMETER_MM / 2.0, dxfattribs={"layer": "CUT"})
    modelspace.add_circle((88.0, 48.0), radius=HOLE_DIAMETER_MM / 2.0, dxfattribs={"layer": "CUT"})

    # The 45-degree bend line, spanning the blank corner to corner so it fully
    # separates the tab from the plate.
    modelspace.add_line(
        (BEND_TOP_X_MM, PLATE_WIDTH_MM),
        (PLATE_LENGTH_MM, BEND_RIGHT_Y_MM),
        dxfattribs={"layer": "BEND"},
    )

    return {"document": document}


if __name__ == "__main__":
    gen_dxf()
