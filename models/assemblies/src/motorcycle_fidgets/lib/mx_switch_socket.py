"""Shared Cherry MX plate-mount socket geometry for switch fidget toys.

All dimensions in millimeters, following the Cherry MX data sheet plate
interface:

* 14.0 mm square plate hole (plus a per-side print clearance), centered on
  x = y = 0
* 1.5 mm plate thickness, the snap-tab engagement depth
* four side relief grooves so the housing snap tabs clear in any orientation
* a square pocket below the plate for the switch body and solder pins
  (switch body below the flange is ~8.5 mm, pins add ~2.3 mm)
* a 45 degree lead-in chamfer around the top of the hole to funnel the
  switch in

``mx_socket_cutter`` returns a boolean SUBTRACTION tool oriented so the plate
top face sits at ``plate_top_z``; the pocket floor lands at
``plate_top_z - MX_PLATE - pocket_depth``.
"""

from __future__ import annotations

from cadgen import build123d as bd


MX_HOLE = 14.0            # nominal Cherry MX plate hole, per side
MX_CLEARANCE = 0.15       # per-side clearance for FDM printing
MX_PLATE = 1.5            # plate thickness (snap-tab engagement)
MX_POCKET_SIDE = 16.8     # switch body pocket, per side (15.6 body + clearance)
MX_POCKET_DEPTH = 12.5    # switch body + pins below the plate
MX_RELIEF_RADIUS = 1.7    # snap-tab relief groove radius
MX_RELIEF_DEPTH = 1.0     # relief groove depth past the hole wall
MX_LEAD_IN = 0.8          # top funnel chamfer width

HOLE_SIDE = MX_HOLE + 2.0 * MX_CLEARANCE


def mx_socket_cutter(plate_top_z: float = 0.0, pocket_depth: float = MX_POCKET_DEPTH):
    """Boolean tool cutting one MX plate socket; plate top at ``plate_top_z``."""

    plate_bottom_z = plate_top_z - MX_PLATE

    # switch body pocket; exact floor, no overshoot into the part below
    pocket = bd.Box(
        MX_POCKET_SIDE, MX_POCKET_SIDE, pocket_depth
    ).moved(bd.Location((0.0, 0.0, plate_bottom_z - pocket_depth / 2.0)))

    # square plate hole, overshooting 1 mm down into the pocket so the two
    # always join into one cavity
    hole = bd.Box(
        HOLE_SIDE, HOLE_SIDE, MX_PLATE + 1.0
    ).moved(bd.Location((0.0, 0.0, plate_top_z - MX_PLATE / 2.0 - 0.5)))

    # 45 degree funnel above the plate top (negative taper widens upward)
    lead = bd.extrude(bd.Rectangle(HOLE_SIDE, HOLE_SIDE), MX_LEAD_IN, taper=-45.0).moved(
        bd.Location((0.0, 0.0, plate_top_z))
    )

    # snap-tab relief grooves at the midpoint of each hole wall, running the
    # full plate height (slightly overshooting in Z only)
    groove_offset = HOLE_SIDE / 2.0 + MX_RELIEF_DEPTH - MX_RELIEF_RADIUS
    groove_height = MX_PLATE + 0.6
    groove_center_z = plate_top_z - MX_PLATE / 2.0
    grooves = [
        bd.Cylinder(MX_RELIEF_RADIUS, groove_height).moved(
            bd.Location((offset_x, offset_y, groove_center_z))
        )
        for offset_x, offset_y in (
            (groove_offset, 0.0),
            (-groove_offset, 0.0),
            (0.0, groove_offset),
            (0.0, -groove_offset),
        )
    ]

    tools = [pocket, hole, lead, *grooves]
    return tools[0].fuse(*tools[1:])


def mx_removal_hole_diameter() -> float:
    """Diameter of a finger/tool access hole to push the switch out (10 mm)."""

    return 10.0
