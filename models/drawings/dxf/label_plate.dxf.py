# Prompt: A laser-cut label plate that exercises the annotation set: TEXT
# engraving (a serial number), an OPEN polyline on the engrave layer (a score
# that must render as a line on the surface, never a solid), and layer colors
# from the layer table.

from __future__ import annotations

import ezdxf

PLATE_LENGTH_MM = 120.0
PLATE_WIDTH_MM = 50.0
HOLE_DIAMETER_MM = 4.5
HOLE_INSET_MM = 8.0


def gen_dxf():
    document = ezdxf.new("R2010", setup=True)
    document.units = ezdxf.units.MM
    modelspace = document.modelspace()
    document.layers.add("CUT", color=1)
    document.layers.add("ENGRAVE", color=5)

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

    for x in (HOLE_INSET_MM, PLATE_LENGTH_MM - HOLE_INSET_MM):
        for y in (HOLE_INSET_MM, PLATE_WIDTH_MM - HOLE_INSET_MM):
            modelspace.add_circle(
                (x, y),
                radius=HOLE_DIAMETER_MM / 2.0,
                dxfattribs={"layer": "CUT"},
            )

    # The engraved serial number: TEXT with height and rotation, no outlines.
    modelspace.add_text(
        "SN-1042",
        dxfattribs={
            "layer": "ENGRAVE",
            "height": 9.0,
            "insert": (28.0, 21.0),
        },
    )

    # An OPEN score line under the label: a zigzag underline that never closes,
    # so it must survive as a score overlay rather than being dropped.
    modelspace.add_lwpolyline(
        [
            (28.0, 15.0),
            (48.0, 12.0),
            (68.0, 15.0),
            (88.0, 12.0),
        ],
        close=False,
        dxfattribs={"layer": "ENGRAVE"},
    )

    return {"document": document}


if __name__ == "__main__":
    gen_dxf()
