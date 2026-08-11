# Prompt: Flat pattern for a sheet-metal U-channel bracket: a rectangular blank
# with TWO parallel bend lines, so the web stays flat and both flanges fold the
# same way. The two-bend case is what an L-bracket cannot exercise — bend
# ordering, and a segment that is bounded by a bend on both sides rather than by
# a bend and a free edge.

from __future__ import annotations

import ezdxf

BLANK_WIDTH_MM = 70.0
FLANGE_LENGTH_MM = 30.0
WEB_LENGTH_MM = 80.0
HOLE_DIAMETER_MM = 5.5
HOLE_EDGE_INSET_MM = 12.0
SLOT_WIDTH_MM = 24.0
SLOT_HEIGHT_MM = 10.0


def gen_dxf():
    # setup=True loads the standard linetypes (DASHED) for the bend lines.
    document = ezdxf.new("R2010", setup=True)
    document.units = ezdxf.units.MM
    modelspace = document.modelspace()
    document.layers.add("CUT")
    document.layers.add("BEND", linetype="DASHED")

    blank_length = FLANGE_LENGTH_MM + WEB_LENGTH_MM + FLANGE_LENGTH_MM
    modelspace.add_lwpolyline(
        [
            (0.0, 0.0),
            (blank_length, 0.0),
            (blank_length, BLANK_WIDTH_MM),
            (0.0, BLANK_WIDTH_MM),
        ],
        close=True,
        dxfattribs={"layer": "CUT"},
    )

    # A mounting hole near each corner of both flanges — the parts that end up
    # vertical once the blank is folded.
    flange_hole_xs = (
        HOLE_EDGE_INSET_MM,
        blank_length - HOLE_EDGE_INSET_MM,
    )
    hole_ys = (HOLE_EDGE_INSET_MM, BLANK_WIDTH_MM - HOLE_EDGE_INSET_MM)
    for x in flange_hole_xs:
        for y in hole_ys:
            modelspace.add_circle(
                (x, y),
                radius=HOLE_DIAMETER_MM / 2.0,
                dxfattribs={"layer": "CUT"},
            )

    # A slot through the web, so the flat pattern has an interior cutout that is
    # not a circle and sits clear of both bend lines.
    web_centre_x = FLANGE_LENGTH_MM + WEB_LENGTH_MM / 2.0
    web_centre_y = BLANK_WIDTH_MM / 2.0
    modelspace.add_lwpolyline(
        [
            (web_centre_x - SLOT_WIDTH_MM / 2.0, web_centre_y - SLOT_HEIGHT_MM / 2.0),
            (web_centre_x + SLOT_WIDTH_MM / 2.0, web_centre_y - SLOT_HEIGHT_MM / 2.0),
            (web_centre_x + SLOT_WIDTH_MM / 2.0, web_centre_y + SLOT_HEIGHT_MM / 2.0),
            (web_centre_x - SLOT_WIDTH_MM / 2.0, web_centre_y + SLOT_HEIGHT_MM / 2.0),
        ],
        close=True,
        dxfattribs={"layer": "CUT"},
    )

    # The two bend lines. Vertical and full-height, which is what the preview
    # mesher requires to split the blank into foldable strips.
    for x in (FLANGE_LENGTH_MM, FLANGE_LENGTH_MM + WEB_LENGTH_MM):
        modelspace.add_line(
            (x, 0.0),
            (x, BLANK_WIDTH_MM),
            dxfattribs={"layer": "BEND"},
        )

    return {"document": document}


if __name__ == "__main__":
    gen_dxf()
