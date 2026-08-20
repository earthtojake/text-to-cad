# Prompt: One flat pattern that exercises every bend shape the 3D fold preview has to handle, so
# a fold regression shows up on a part instead of only in a unit test.
#
# Each bend is here for a reason, and they are deliberately NOT all alike:
#
#   bend 1  vertical, edge to edge     the ordinary case
#   bend 2  vertical, edge to edge     a second parallel bend, so up/up folds a U and up/down a Z
#   bend 3  HORIZONTAL, across a tab   perpendicular to bends 1-2, and a CHORD: it spans only the
#                                      tab's width, and the same infinite line continues along
#                                      the panel's bottom edge where no bend runs. A fold model
#                                      that cuts by each bend's infinite line slices the whole
#                                      blank here and folds material the bend does not separate.
#   bend 4  DIAGONAL across a corner   45 degrees, to hold the line that bend orientation is not
#                                      restricted to the axes. Inboard of the chamfer, since a
#                                      bend drawn ON a cut edge separates nothing.
#
# Every bend line ends ON the outline, because that is what makes a fold a fold: a brake needs
# the line to reach material's edge at both ends. Holes sit clear of the bend bands, since
# material inside a bend radius becomes the curve and cannot stay flat.
#
# Not covered here, deliberately: a bend whose ends stop short of the edge and rely on relief
# slits. The preview refuses those by design and names the shortfall; tom's link_bracket is the
# fixture for that case.

from __future__ import annotations

import ezdxf
from ezdxf.units import MM

PANEL_WIDTH_MM = 180.0
PANEL_HEIGHT_MM = 90.0

BEND_1_X_MM = 45.0
BEND_2_X_MM = 120.0

# The tab hanging off the bottom edge, folded about the panel's bottom edge line.
TAB_LEFT_X_MM = 70.0
TAB_RIGHT_X_MM = 110.0
TAB_DEPTH_MM = 22.0

# The top-right corner: chamfered at CHAMFER, folded about a 45-degree chord inboard of it.
CHAMFER_MM = 34.0
CORNER_FOLD_MM = 55.0

HOLE_DIAMETER_MM = 5.5


def _outline() -> list[tuple[float, float]]:
    """The blank, walked anticlockwise: bottom edge with the tab hanging below it, then up the
    right edge to the chamfered corner."""
    width = PANEL_WIDTH_MM
    height = PANEL_HEIGHT_MM
    return [
        (0.0, 0.0),
        # bottom edge, interrupted by the tab
        (TAB_LEFT_X_MM, 0.0),
        (TAB_LEFT_X_MM, -TAB_DEPTH_MM),
        (TAB_RIGHT_X_MM, -TAB_DEPTH_MM),
        (TAB_RIGHT_X_MM, 0.0),
        (width, 0.0),
        # up the right edge, stopping short for the chamfer
        (width, height - CHAMFER_MM),
        (width - CHAMFER_MM, height),
        (0.0, height),
    ]


def gen_dxf():
    # setup=True loads the standard linetypes, so BEND can be DASHED as the convention has it.
    document = ezdxf.new("R2010", setup=True)
    document.units = MM
    modelspace = document.modelspace()
    document.layers.add("CUT")
    document.layers.add("BEND", linetype="DASHED")

    modelspace.add_lwpolyline(_outline(), close=True, dxfattribs={"layer": "CUT"})

    # 1 and 2: the parallel pair, bottom edge to top edge.
    for x in (BEND_1_X_MM, BEND_2_X_MM):
        modelspace.add_line(
            (x, 0.0), (x, PANEL_HEIGHT_MM), dxfattribs={"layer": "BEND"}
        )

    # 3: the tab fold, spanning exactly the gap the tab leaves in the bottom edge.
    modelspace.add_line(
        (TAB_LEFT_X_MM, 0.0), (TAB_RIGHT_X_MM, 0.0), dxfattribs={"layer": "BEND"}
    )

    # 4: the corner fold, from the right edge to the top edge, parallel to the chamfer and
    # inboard of it so it cuts the corner tab off the panel rather than tracing the cut.
    modelspace.add_line(
        (PANEL_WIDTH_MM, PANEL_HEIGHT_MM - CORNER_FOLD_MM),
        (PANEL_WIDTH_MM - CORNER_FOLD_MM, PANEL_HEIGHT_MM),
        dxfattribs={"layer": "BEND"},
    )

    # One hole per face, all clear of the bend bands.
    for x, y in (
        (22.0, 45.0),
        (85.0, 45.0),
        (150.0, 25.0),
        (90.0, -13.0),
        (155.0, 70.0),
    ):
        modelspace.add_circle(
            (x, y), radius=HOLE_DIAMETER_MM / 2.0, dxfattribs={"layer": "CUT"}
        )

    return {"document": document}


if __name__ == "__main__":
    gen_dxf()
