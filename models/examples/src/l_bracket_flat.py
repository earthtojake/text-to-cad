# Prompt: Flat pattern for a 90-degree sheet-metal L-bracket: rectangular
# blank, two mounting holes per leg, and a bend line between the legs.

from __future__ import annotations

from cadgen import build123d as bd
from cadgen import dxf

BLANK_WIDTH_MM = 60.0
LEG_A_LENGTH_MM = 50.0
LEG_B_LENGTH_MM = 40.0
HOLE_DIAMETER_MM = 6.0
HOLE_EDGE_INSET_MM = 12.0

BLANK_LENGTH_MM = LEG_A_LENGTH_MM + LEG_B_LENGTH_MM


@dxf(out="../DXF/l_bracket_flat.dxf")
def l_bracket_flat():
    # The blank is drawn in its own first-quadrant coordinates (0,0 at the
    # bottom-left corner), which is how a flat pattern is dimensioned on the
    # shop floor; BuildSketch centres its primitives, so shift by half.
    with bd.BuildSketch() as cut:
        with bd.Locations((BLANK_LENGTH_MM / 2.0, BLANK_WIDTH_MM / 2.0)):
            bd.Rectangle(BLANK_LENGTH_MM, BLANK_WIDTH_MM)
        hole_xs = (HOLE_EDGE_INSET_MM, BLANK_LENGTH_MM - HOLE_EDGE_INSET_MM)
        hole_ys = (HOLE_EDGE_INSET_MM, BLANK_WIDTH_MM - HOLE_EDGE_INSET_MM)
        with bd.Locations(*[(x, y) for x in hole_xs for y in hole_ys]):
            bd.Circle(HOLE_DIAMETER_MM / 2.0, mode=bd.Mode.SUBTRACT)

    # Open geometry: allowed only because the layer name carries bend intent.
    bend = bd.Line((LEG_A_LENGTH_MM, 0.0), (LEG_A_LENGTH_MM, BLANK_WIDTH_MM))

    return {"CUT": cut.sketch, "BEND": bend}


if __name__ == "__main__":
    l_bracket_flat()
