# Prompt: Flat pattern for a 90-degree sheet-metal L-bracket: rectangular
# blank, two mounting holes per leg, and a dashed bend line between the legs.

from __future__ import annotations

import ezdxf

BLANK_WIDTH_MM = 60.0
LEG_A_LENGTH_MM = 50.0
LEG_B_LENGTH_MM = 40.0
HOLE_DIAMETER_MM = 6.0
HOLE_EDGE_INSET_MM = 12.0


def gen_dxf():
    # setup=True loads the standard linetypes (DASHED) for the bend line.
    document = ezdxf.new("R2010", setup=True)
    document.units = ezdxf.units.MM
    modelspace = document.modelspace()
    document.layers.add("CUT")
    document.layers.add("BEND", linetype="DASHED")

    blank_length = LEG_A_LENGTH_MM + LEG_B_LENGTH_MM
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

    hole_ys = (HOLE_EDGE_INSET_MM, BLANK_WIDTH_MM - HOLE_EDGE_INSET_MM)
    hole_xs = (
        HOLE_EDGE_INSET_MM,
        blank_length - HOLE_EDGE_INSET_MM,
    )
    for x in hole_xs:
        for y in hole_ys:
            modelspace.add_circle(
                (x, y),
                HOLE_DIAMETER_MM / 2.0,
                dxfattribs={"layer": "CUT"},
            )

    modelspace.add_line(
        (LEG_A_LENGTH_MM, 0.0),
        (LEG_A_LENGTH_MM, BLANK_WIDTH_MM),
        dxfattribs={"layer": "BEND"},
    )
    return {"document": document}


if __name__ == "__main__":
    gen_dxf()
