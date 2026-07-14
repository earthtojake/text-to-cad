from __future__ import annotations

import ezdxf
from build123d import Box, BuildPart, Hole, Locations


LENGTH = 120.0
WIDTH = 60.0
THICKNESS = 5.0
HOLE_DIAMETER = 6.0
EDGE_OFFSET = 10.0

HOLE_CENTERS = (
    (LENGTH / 2 - EDGE_OFFSET, WIDTH / 2 - EDGE_OFFSET, 0.0),
    (-(LENGTH / 2 - EDGE_OFFSET), WIDTH / 2 - EDGE_OFFSET, 0.0),
    (LENGTH / 2 - EDGE_OFFSET, -(WIDTH / 2 - EDGE_OFFSET), 0.0),
    (-(LENGTH / 2 - EDGE_OFFSET), -(WIDTH / 2 - EDGE_OFFSET), 0.0),
)


def gen_step():
    with BuildPart() as plate:
        Box(LENGTH, WIDTH, THICKNESS)
        with Locations(*HOLE_CENTERS):
            Hole(radius=HOLE_DIAMETER / 2)

    plate.part.label = "four_hole_plate"
    return plate.part


def gen_dxf():
    doc = ezdxf.new("R2010")
    doc.units = ezdxf.units.MM

    doc.layers.add("outline", color=7)
    doc.layers.add("holes", color=1)
    doc.layers.add("centerlines", color=3)
    doc.layers.add("notes", color=2)

    msp = doc.modelspace()
    x0, x1 = -LENGTH / 2, LENGTH / 2
    y0, y1 = -WIDTH / 2, WIDTH / 2

    msp.add_lwpolyline(
        [(x0, y0), (x1, y0), (x1, y1), (x0, y1)],
        close=True,
        dxfattribs={"layer": "outline"},
    )

    for x, y, _ in HOLE_CENTERS:
        msp.add_circle((x, y), HOLE_DIAMETER / 2, dxfattribs={"layer": "holes"})
        msp.add_line((x - 5, y), (x + 5, y), dxfattribs={"layer": "centerlines"})
        msp.add_line((x, y - 5), (x, y + 5), dxfattribs={"layer": "centerlines"})

    msp.add_text(
        "FOUR HOLE PLATE 120 x 60 x 5, 4x DIA 6 THRU, hole centers 10 from edges",
        height=3,
        dxfattribs={"layer": "notes"},
    ).set_placement((x0, y0 - 10))

    return doc
