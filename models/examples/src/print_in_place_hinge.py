"""Print-in-place barrel hinge for FDM printing.

Units: millimeters.
Origin: hinge pin axis center — X along the pin/knuckle axis, Y across the two
leaves (fold plane at y=0), Z up with z=0 at the print bed. The model is
authored in its print pose: both leaves flat on the bed, hinge open 180
degrees, knuckle barrel tangent to the bed. Printing as modeled requires no
supports; the two leaves are separate solids that articulate after printing.

Leaf A: mounting plate with two bored end knuckles.
Leaf B: mounting plate with one solid center knuckle and a full-length captive
pin whose two outboard heads (larger than the bore) lock the hinge together.

Clearances target a tuned 0.4 mm-nozzle FDM printer:
- 0.4 mm diametral pin-to-bore (0.2 mm radial)
- 0.6 mm axial knuckle-to-knuckle and head-to-stack gaps
- 0.2 mm radial scallop between each knuckle and the opposite plate
"""
from __future__ import annotations
from cadgen import step

from cadgen import build123d as bd
from cadgen import srgb
from cadgen.assembly import AssemblyHelper


HINGE_LENGTH = 40.0
PLATE_WIDTH = 20.0
PLATE_THICKNESS = 5.0
PLATE_INNER_Y = 4.0  # plate edge offset from the fold plane; barrel (r=5) overlaps it

KNUCKLE_RADIUS = 5.0
PIN_RADIUS = 2.5
BORE_RADIUS = 2.7  # pin radius + 0.2 mm radial clearance
AXIAL_GAP = 0.6

HEAD_RADIUS = 3.5  # > bore radius so the heads cannot pass through, < plate edge
HEAD_THICKNESS = 2.5
HEAD_AXIAL_GAP = 0.4

NOTCH_RADIUS = 5.2  # knuckle radius + 0.2 mm clearance scalloped into the opposite plate
NOTCH_INNER_Y = 3.85  # scallop starts inside the plate edge, stays clear of the pin (r=2.5)
NOTCH_X_OVERSHOOT = 0.4

SCREW_HOLE_DIAMETER = 5.5  # M5 clearance
SCREW_HOLE_OFFSET_X = 13.0
SCREW_HOLE_Y_INNER = PLATE_INNER_Y + 5.0
SCREW_HOLE_Y_OUTER = PLATE_INNER_Y + PLATE_WIDTH - 5.0

AXIS_Z = KNUCKLE_RADIUS  # barrel tangent to the bed, axis one plate-thickness up

HALF_LENGTH = HINGE_LENGTH / 2.0
KNUCKLE_A_LENGTH = 13.2
KNUCKLE_B_LENGTH = HINGE_LENGTH - 2.0 * KNUCKLE_A_LENGTH - 2.0 * AXIAL_GAP
KNUCKLE_A1 = (-HALF_LENGTH, -HALF_LENGTH + KNUCKLE_A_LENGTH)
KNUCKLE_B = (-KNUCKLE_B_LENGTH / 2.0, KNUCKLE_B_LENGTH / 2.0)
KNUCKLE_A2 = (HALF_LENGTH - KNUCKLE_A_LENGTH, HALF_LENGTH)
PIN_SPAN_HALF = HALF_LENGTH + HEAD_AXIAL_GAP + HEAD_THICKNESS

HINGE_AXIS_ORIGIN = (0.0, 0.0, AXIS_Z)  # bd.Axis is built at the use site, not at import
HINGE_AXIS_DIRECTION = (1.0, 0.0, 0.0)


def _plate(sign: float):
    """Mounting plate on one side of the fold plane with four M5 clearance holes."""
    plate = bd.Box(HINGE_LENGTH, PLATE_WIDTH, PLATE_THICKNESS).moved(
        bd.Location((0.0, sign * (PLATE_INNER_Y + PLATE_WIDTH / 2.0), PLATE_THICKNESS / 2.0))
    )
    hole_tools = [
        bd.Cylinder(radius=SCREW_HOLE_DIAMETER / 2.0, height=PLATE_THICKNESS + 2.0).moved(
            bd.Location((x, sign * y, PLATE_THICKNESS / 2.0))
        )
        for x in (-SCREW_HOLE_OFFSET_X, SCREW_HOLE_OFFSET_X)
        for y in (SCREW_HOLE_Y_INNER, SCREW_HOLE_Y_OUTER)
    ]
    return plate - hole_tools


def _barrel_segment(x_start: float, x_end: float):
    """Solid knuckle segment on the hinge axis."""
    return bd.Cylinder(radius=KNUCKLE_RADIUS, height=x_end - x_start, rotation=(0, 90, 0)).moved(
        bd.Location(((x_start + x_end) / 2.0, 0.0, AXIS_Z))
    )


def _bore_tool(x_start: float, x_end: float):
    """Through-bore cutter for a leaf A knuckle, overshooting both end faces."""
    return bd.Cylinder(radius=BORE_RADIUS, height=x_end - x_start + 2.0, rotation=(0, 90, 0)).moved(
        bd.Location(((x_start + x_end) / 2.0, 0.0, AXIS_Z))
    )


def _pin_with_heads():
    """Captive pin: full-length shaft plus two outboard heads."""
    span = 2.0 * PIN_SPAN_HALF
    pin = bd.Cylinder(radius=PIN_RADIUS, height=span, rotation=(0, 90, 0)).moved(
        bd.Location((0.0, 0.0, AXIS_Z))
    )
    heads = [
        bd.Cylinder(radius=HEAD_RADIUS, height=HEAD_THICKNESS, rotation=(0, 90, 0)).moved(
            bd.Location((x_side * (PIN_SPAN_HALF - HEAD_THICKNESS / 2.0), 0.0, AXIS_Z))
        )
        for x_side in (-1.0, 1.0)
    ]
    return pin.fuse(*heads)


def _notch_tool(sign: float, x_start: float, x_end: float):
    """Scallop cutter clearing the opposite leaf's knuckle from this leaf's plate."""
    length = x_end - x_start + 2.0 * NOTCH_X_OVERSHOOT
    sleeve = bd.Cylinder(radius=NOTCH_RADIUS, height=length, rotation=(0, 90, 0)).moved(
        bd.Location(((x_start + x_end) / 2.0, 0.0, AXIS_Z))
    )
    plate_side = bd.Box(length + 4.0, 20.0, 24.0).moved(
        bd.Location(((x_start + x_end) / 2.0, sign * (NOTCH_INNER_Y + 10.0), 0.0))
    )
    return sleeve & plate_side


def _make_leaf_a():
    leaf = _plate(-1.0).fuse(
        _barrel_segment(*KNUCKLE_A1),
        _barrel_segment(*KNUCKLE_A2),
    )
    leaf = leaf - [_bore_tool(*KNUCKLE_A1), _bore_tool(*KNUCKLE_A2), _notch_tool(-1.0, *KNUCKLE_B)]
    leaf.label = "leaf_a_barrel_bores"
    leaf.color = srgb("#5B6B7A")
    return leaf


def _make_leaf_b():
    leaf = _plate(1.0).fuse(
        _barrel_segment(*KNUCKLE_B),
        _pin_with_heads(),
    )
    leaf = leaf - [_notch_tool(1.0, *KNUCKLE_A1), _notch_tool(1.0, *KNUCKLE_A2)]
    leaf.label = "leaf_b_captive_pin"
    leaf.color = srgb("#C98056")
    return leaf


@step(out="../STEP/print_in_place_hinge.step")
def print_in_place_hinge():
    """Return the print-in-place hinge as a labeled two-leaf assembly compound."""
    asm = AssemblyHelper("print_in_place_hinge")

    leaf_a = asm.add(_make_leaf_a(), "leaf_a_barrel_bores")
    leaf_b = asm.add(_make_leaf_b(), "leaf_b_captive_pin")

    bore_axis = asm.revolute_frame(leaf_a, "bore_axis", bd.Axis(HINGE_AXIS_ORIGIN, HINGE_AXIS_DIRECTION))
    # Same orientation as the revolute frame (local Z along the hinge axis) so the
    # angle=0 connect holds the as-printed pose instead of re-rotating leaf B.
    pin_axis = asm.rigid_frame(
        leaf_b,
        "pin_axis",
        bd.Location(bd.Plane(origin=(0.0, 0.0, AXIS_Z), x_dir=(0.0, 0.0, 1.0), z_dir=(1.0, 0.0, 0.0))),
    )
    asm.revolute(bore_axis, pin_axis, angle=0.0, label="hinge_articulation")

    return asm.build()


if __name__ == "__main__":
    print_in_place_hinge()
