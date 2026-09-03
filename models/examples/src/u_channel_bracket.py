# Prompt: Flat pattern for a sheet-metal U-channel bracket: a rectangular blank
# with TWO parallel bend lines, so the web stays flat and both flanges fold the
# same way. The two-bend case is what an L-bracket cannot exercise — bend
# ordering, and a segment that is bounded by a bend on both sides rather than by
# a bend and a free edge.

from __future__ import annotations

from cadgen import build123d as bd
from cadgen import dxf

BLANK_WIDTH_MM = 70.0
FLANGE_LENGTH_MM = 30.0
WEB_LENGTH_MM = 80.0
HOLE_DIAMETER_MM = 5.5
HOLE_EDGE_INSET_MM = 12.0
SLOT_WIDTH_MM = 24.0
SLOT_HEIGHT_MM = 10.0

BLANK_LENGTH_MM = FLANGE_LENGTH_MM + WEB_LENGTH_MM + FLANGE_LENGTH_MM
BEND_XS_MM = (FLANGE_LENGTH_MM, FLANGE_LENGTH_MM + WEB_LENGTH_MM)


@dxf(out="../DXF/u_channel_bracket.dxf")
def u_channel_bracket():
    with bd.BuildSketch() as cut:
        with bd.Locations((BLANK_LENGTH_MM / 2.0, BLANK_WIDTH_MM / 2.0)):
            bd.Rectangle(BLANK_LENGTH_MM, BLANK_WIDTH_MM)

        # A mounting hole near each corner of both flanges — the parts that end
        # up vertical once the blank is folded.
        hole_xs = (HOLE_EDGE_INSET_MM, BLANK_LENGTH_MM - HOLE_EDGE_INSET_MM)
        hole_ys = (HOLE_EDGE_INSET_MM, BLANK_WIDTH_MM - HOLE_EDGE_INSET_MM)
        with bd.Locations(*[(x, y) for x in hole_xs for y in hole_ys]):
            bd.Circle(HOLE_DIAMETER_MM / 2.0, mode=bd.Mode.SUBTRACT)

        # A slot through the web, so the flat pattern has an interior cutout
        # that is not a circle and sits clear of both bend lines.
        with bd.Locations((BLANK_LENGTH_MM / 2.0, BLANK_WIDTH_MM / 2.0)):
            bd.Rectangle(SLOT_WIDTH_MM, SLOT_HEIGHT_MM, mode=bd.Mode.SUBTRACT)

    # The two bend lines: vertical and full-height, which is what the preview
    # mesher requires to split the blank into foldable strips.
    bends = [bd.Line((x, 0.0), (x, BLANK_WIDTH_MM)) for x in BEND_XS_MM]

    return {"CUT": cut.sketch, "BEND": bends}


if __name__ == "__main__":
    u_channel_bracket()
