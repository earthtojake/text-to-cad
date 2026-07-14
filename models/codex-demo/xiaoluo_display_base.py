from __future__ import annotations

import ezdxf
from build123d import Box, BuildPart, Cylinder, Hole, Locations


BASE_LENGTH = 110.0
BASE_WIDTH = 70.0
BASE_THICKNESS = 8.0
PEDESTAL_DIAMETER = 44.0
PEDESTAL_HEIGHT = 18.0
SOCKET_DIAMETER = 12.0
MOUNT_HOLE_DIAMETER = 4.5
ACCESSORY_HOLE_DIAMETER = 5.0
MOUNT_EDGE_OFFSET_X = 12.0
MOUNT_EDGE_OFFSET_Y = 12.0
ACCESSORY_SPACING = 28.0
ACCESSORY_Y = -18.0

MOUNT_HOLE_CENTERS = (
    (BASE_LENGTH / 2 - MOUNT_EDGE_OFFSET_X, BASE_WIDTH / 2 - MOUNT_EDGE_OFFSET_Y, 0.0),
    (-(BASE_LENGTH / 2 - MOUNT_EDGE_OFFSET_X), BASE_WIDTH / 2 - MOUNT_EDGE_OFFSET_Y, 0.0),
    (BASE_LENGTH / 2 - MOUNT_EDGE_OFFSET_X, -(BASE_WIDTH / 2 - MOUNT_EDGE_OFFSET_Y), 0.0),
    (-(BASE_LENGTH / 2 - MOUNT_EDGE_OFFSET_X), -(BASE_WIDTH / 2 - MOUNT_EDGE_OFFSET_Y), 0.0),
)

ACCESSORY_HOLE_CENTERS = (
    (-ACCESSORY_SPACING / 2, ACCESSORY_Y, 0.0),
    (ACCESSORY_SPACING / 2, ACCESSORY_Y, 0.0),
)


def gen_step():
    with BuildPart() as base:
        Box(BASE_LENGTH, BASE_WIDTH, BASE_THICKNESS)
        with Locations((0.0, 0.0, BASE_THICKNESS / 2 + PEDESTAL_HEIGHT / 2)):
            Cylinder(radius=PEDESTAL_DIAMETER / 2, height=PEDESTAL_HEIGHT)

        with Locations((0.0, 0.0, 0.0)):
            Hole(radius=SOCKET_DIAMETER / 2)

        with Locations(*MOUNT_HOLE_CENTERS):
            Hole(radius=MOUNT_HOLE_DIAMETER / 2)

        with Locations(*ACCESSORY_HOLE_CENTERS):
            Hole(radius=ACCESSORY_HOLE_DIAMETER / 2)

    base.part.label = "xiaoluo_display_base"
    return base.part


def gen_dxf():
    doc = ezdxf.new("R2010")
    doc.units = ezdxf.units.MM

    doc.layers.add("base_outline", color=7)
    doc.layers.add("pedestal_projection", color=5)
    doc.layers.add("holes", color=1)
    doc.layers.add("centerlines", color=3)
    doc.layers.add("notes", color=2)

    msp = doc.modelspace()
    x0, x1 = -BASE_LENGTH / 2, BASE_LENGTH / 2
    y0, y1 = -BASE_WIDTH / 2, BASE_WIDTH / 2

    msp.add_lwpolyline(
        [(x0, y0), (x1, y0), (x1, y1), (x0, y1)],
        close=True,
        dxfattribs={"layer": "base_outline"},
    )

    msp.add_circle(
        (0.0, 0.0),
        PEDESTAL_DIAMETER / 2,
        dxfattribs={"layer": "pedestal_projection"},
    )
    msp.add_circle((0.0, 0.0), SOCKET_DIAMETER / 2, dxfattribs={"layer": "holes"})

    for x, y, _ in MOUNT_HOLE_CENTERS:
        msp.add_circle((x, y), MOUNT_HOLE_DIAMETER / 2, dxfattribs={"layer": "holes"})
        msp.add_line((x - 5, y), (x + 5, y), dxfattribs={"layer": "centerlines"})
        msp.add_line((x, y - 5), (x, y + 5), dxfattribs={"layer": "centerlines"})

    for x, y, _ in ACCESSORY_HOLE_CENTERS:
        msp.add_circle((x, y), ACCESSORY_HOLE_DIAMETER / 2, dxfattribs={"layer": "holes"})
        msp.add_line((x - 5, y), (x + 5, y), dxfattribs={"layer": "centerlines"})
        msp.add_line((x, y - 5), (x, y + 5), dxfattribs={"layer": "centerlines"})

    msp.add_line((-8, 0), (8, 0), dxfattribs={"layer": "centerlines"})
    msp.add_line((0, -8), (0, 8), dxfattribs={"layer": "centerlines"})
    msp.add_text(
        "XIAOLUO DISPLAY BASE 110 x 70 x 26, D44 PEDESTAL, D12 SOCKET, 4x D4.5, 2x D5",
        height=3,
        dxfattribs={"layer": "notes"},
    ).set_placement((x0, y0 - 10))

    return doc
