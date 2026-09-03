"""Print-in-place multi-pivot holder with a phone/tablet cradle for FDM printing.

Units: millimeters.
Origin: pivot 1 fold line center — pin axes run along X, the link chain runs
along +Y, and the whole model is authored in its print pose: every plate flat
on the bed (z=0), all three hinges open 180 degrees. The model prints as one
flat job with no supports and articulates after printing; in use the base sits
on (or screws to) the desk and the three pivots set reach and viewing lean.
Stable poses come from the folded chain resting on itself and the cradle's
bottom edge on the desk, helped by the snug pin fit — not from a lock.

Chain: base mounting plate -> lower arm -> upper arm -> phone cradle, joined
by three parallel barrel pivots. Each pivot interleaves two bored end knuckles
on the -Y link with one solid center knuckle plus a captive pin (heads larger
than the bore) on the +Y link — the same joint pattern as
print_in_place_hinge.step.py in this directory.

The cradle backs a phone (80 mm interior width by default) between two side
walls and a bottom lip at the pivot end, which is the downhill end once the
cradle leans back. Set CRADLE_INNER_W near 170 for a small tablet; the source
regenerates at the new width.

Clearances target a tuned 0.4 mm-nozzle FDM printer:
- 0.3 mm diametral pin-to-bore (0.15 mm radial, snug for pose holding;
  raise BORE_R to 2.7 for a free-swinging joint)
- 0.5 mm axial knuckle-to-knuckle gaps, 0.35 mm head-to-stack gaps
- 0.2 mm radial scallop between each knuckle and the opposite plate

Print footprint: 94 x 248 mm, 18 mm tall — fits a 250 mm bed; scale or shorten
the arm links for a 220 mm bed.
"""
from __future__ import annotations
from cadgen import step

from cadgen import build123d as bd
from cadgen import srgb
from cadgen.assembly import AssemblyHelper


# ---- shared joint geometry ----
PLATE_T = 5.0
KNUCKLE_R = 5.0
AXIS_Z = KNUCKLE_R  # barrel tangent to the bed
PIN_R = 2.5
BORE_R = 2.65  # pin radius + 0.15 mm radial clearance, snug
AXIAL_GAP = 0.5
HEAD_R = 3.3  # > bore radius so the heads cannot pass through, < plate edge offset
HEAD_T = 2.0
HEAD_GAP = 0.35
NOTCH_R = 5.2  # knuckle radius + 0.2 mm clearance scalloped into the opposite plate
NOTCH_X_OVERSHOOT = 0.4
PLATE_INNER_Y = 4.0  # plate edge offset from the fold plane; barrel overlaps it
NOTCH_INNER_Y = 3.8  # scallop starts just past the plate edge, into the fold gap

END_KN_LEN = 8.0
CENTER_KN_LEN = 8.0
STACK_HALF = END_KN_LEN + AXIAL_GAP + CENTER_KN_LEN / 2.0  # 12.5
PIN_SPAN_HALF = STACK_HALF + HEAD_GAP + HEAD_T  # 14.85

END_KN_X1 = (-STACK_HALF, -STACK_HALF + END_KN_LEN)  # (-12.5, -4.5)
CENTER_KN_X = (-CENTER_KN_LEN / 2.0, CENTER_KN_LEN / 2.0)  # (-4.0, 4.0)
END_KN_X2 = (STACK_HALF - END_KN_LEN, STACK_HALF)  # (4.5, 12.5)

# ---- chain layout: fold lines along the chain ----
Y_J1 = 0.0
Y_J2 = 60.0
Y_J3 = 120.0

LOWER_LEN = 52.0  # plate spans Y_J1 + PLATE_INNER_Y .. Y_J2 - PLATE_INNER_Y
UPPER_LEN = 52.0
ARM_W = 34.0  # wide enough to cover the pin heads (outboard at +-14.85)
ARM_SLOT_LEN = 32.0
ARM_SLOT_W = 13.0

BASE_LEN = 36.0
BASE_W = 46.0
SCREW_HOLE_D = 5.5  # M5 clearance

CRADLE_INNER_W = 80.0  # phone width incl. case; ~170 for a small tablet
CRADLE_WALL_T = 7.0
CRADLE_W = CRADLE_INNER_W + 2.0 * CRADLE_WALL_T  # 94
CRADLE_LEN = 84.0
CRADLE_WALL_H = 13.0
CRADLE_WALL_LEN = 60.0
LIP_T = 4.0
LIP_H = 9.0
SINK = 2.0  # walls/lip sink into the back plate so every fuse overlaps in volume


def _rounded_plate(width, length, cy, radius):
    """Flat link plate on the bed spanning z in [0, PLATE_T], centered at (0, cy)."""
    return bd.extrude(bd.RectangleRounded(width, length, radius), PLATE_T).moved(
        bd.Location((0.0, cy, 0.0))
    )


def _barrel(y_fold, x_start, x_end, radius=KNUCKLE_R):
    """Solid knuckle segment on a pivot axis at (y_fold, AXIS_Z)."""
    return bd.Cylinder(radius=radius, height=x_end - x_start, rotation=(0, 90, 0)).moved(
        bd.Location(((x_start + x_end) / 2.0, y_fold, AXIS_Z))
    )


def _bore_tool(y_fold, x_start, x_end):
    """Through-bore cutter for a bored end knuckle, overshooting both faces."""
    length = x_end - x_start + 2.0
    return bd.Cylinder(radius=BORE_R, height=length, rotation=(0, 90, 0)).moved(
        bd.Location(((x_start + x_end) / 2.0, y_fold, AXIS_Z))
    )


def _pin(y_fold):
    """Captive pin: shaft across the full stack plus two outboard heads."""
    pin = bd.Cylinder(radius=PIN_R, height=2.0 * PIN_SPAN_HALF, rotation=(0, 90, 0)).moved(
        bd.Location((0.0, y_fold, AXIS_Z))
    )
    heads = [
        bd.Cylinder(radius=HEAD_R, height=HEAD_T, rotation=(0, 90, 0)).moved(
            bd.Location((side * (PIN_SPAN_HALF - HEAD_T / 2.0), y_fold, AXIS_Z))
        )
        for side in (-1.0, 1.0)
    ]
    return pin.fuse(*heads)


def _notch_tool(side, y_fold, x_start, x_end):
    """Scallop cutter clearing the opposite link's knuckle from this link's plate."""
    length = x_end - x_start + 2.0 * NOTCH_X_OVERSHOOT
    cx = (x_start + x_end) / 2.0
    sleeve = bd.Cylinder(radius=NOTCH_R, height=length, rotation=(0, 90, 0)).moved(
        bd.Location((cx, y_fold, AXIS_Z))
    )
    plate_side = bd.Box(length + 4.0, 20.0, 24.0).moved(
        bd.Location((cx, y_fold + side * (NOTCH_INNER_Y + 10.0), 0.0))
    )
    return sleeve & plate_side


def _arm_plate(cy):
    """Shared arm link plate with a lightening slot along the chain."""
    plate = _rounded_plate(ARM_W, LOWER_LEN, cy, 3.0)
    slot = bd.extrude(
        bd.Plane.XY.rotated((0, 0, 90)) * bd.SlotOverall(ARM_SLOT_LEN, ARM_SLOT_W),
        PLATE_T + 2.0,
    ).moved(bd.Location((0.0, cy, -1.0)))
    return plate - slot


def _make_base():
    """Root link: screw-down mounting plate with two bored end knuckles at pivot 1."""
    cy = Y_J1 - PLATE_INNER_Y - BASE_LEN / 2.0
    plate = _rounded_plate(BASE_W, BASE_LEN, cy, 4.0)
    holes = [
        bd.Cylinder(radius=SCREW_HOLE_D / 2.0, height=PLATE_T + 2.0).moved(
            bd.Location((x, y, PLATE_T / 2.0))
        )
        for x in (-15.0, 15.0)
        for y in (cy - 12.0, cy + 12.0)
    ]
    base = plate.fuse(
        _barrel(Y_J1, *END_KN_X1),
        _barrel(Y_J1, *END_KN_X2),
    )
    base = base - holes
    base = base - [_bore_tool(Y_J1, *END_KN_X1), _bore_tool(Y_J1, *END_KN_X2)]
    base = base - _notch_tool(-1.0, Y_J1, *CENTER_KN_X)
    base.label = "base_mount_plate"
    base.color = srgb("#5B6B7A")
    return base


def _make_lower_arm():
    """Link 2: center knuckle + captive pin at pivot 1, bored knuckles at pivot 2."""
    cy = (Y_J1 + Y_J2) / 2.0
    arm = _arm_plate(cy).fuse(
        _barrel(Y_J1, *CENTER_KN_X),
        _pin(Y_J1),
        _barrel(Y_J2, *END_KN_X1),
        _barrel(Y_J2, *END_KN_X2),
    )
    arm = arm - [_bore_tool(Y_J2, *END_KN_X1), _bore_tool(Y_J2, *END_KN_X2)]
    arm = arm - [
        _notch_tool(1.0, Y_J1, *END_KN_X1),
        _notch_tool(1.0, Y_J1, *END_KN_X2),
        _notch_tool(-1.0, Y_J2, *CENTER_KN_X),
    ]
    arm.label = "lower_arm_link"
    arm.color = srgb("#C98056")
    return arm


def _make_upper_arm():
    """Link 3: center knuckle + captive pin at pivot 2, bored knuckles at pivot 3."""
    cy = (Y_J2 + Y_J3) / 2.0
    arm = _arm_plate(cy).fuse(
        _barrel(Y_J2, *CENTER_KN_X),
        _pin(Y_J2),
        _barrel(Y_J3, *END_KN_X1),
        _barrel(Y_J3, *END_KN_X2),
    )
    arm = arm - [_bore_tool(Y_J3, *END_KN_X1), _bore_tool(Y_J3, *END_KN_X2)]
    arm = arm - [
        _notch_tool(1.0, Y_J2, *END_KN_X1),
        _notch_tool(1.0, Y_J2, *END_KN_X2),
        _notch_tool(-1.0, Y_J3, *CENTER_KN_X),
    ]
    arm.label = "upper_arm_link"
    arm.color = srgb("#6E8B6E")
    return arm


def _make_cradle():
    """Link 4: phone cradle back with side walls and bottom lip, pinned at pivot 3."""
    y_near = Y_J3 + PLATE_INNER_Y
    cy = y_near + CRADLE_LEN / 2.0
    plate = _rounded_plate(CRADLE_W, CRADLE_LEN, cy, 6.0)
    walls = [
        bd.Box(CRADLE_WALL_T, CRADLE_WALL_LEN, CRADLE_WALL_H + SINK).moved(
            bd.Location(
                (
                    side * (CRADLE_INNER_W / 2.0 + CRADLE_WALL_T / 2.0),
                    y_near + 16.0 + CRADLE_WALL_LEN / 2.0,
                    PLATE_T - SINK + (CRADLE_WALL_H + SINK) / 2.0,
                )
            )
        )
        for side in (-1.0, 1.0)
    ]
    lip = bd.Box(CRADLE_INNER_W, LIP_T, LIP_H + SINK).moved(
        bd.Location((0.0, y_near + 2.0 + LIP_T / 2.0, PLATE_T - SINK + (LIP_H + SINK) / 2.0))
    )
    cradle = plate.fuse(_barrel(Y_J3, *CENTER_KN_X), _pin(Y_J3), *walls, lip)
    cradle = cradle - [
        _notch_tool(1.0, Y_J3, *END_KN_X1),
        _notch_tool(1.0, Y_J3, *END_KN_X2),
    ]
    cradle.label = "cradle_phone_holder"
    cradle.color = srgb("#A87E93")
    return cradle


def _pin_frame_loc(y_fold):
    """Frame oriented like the revolute frame (local Z along the pin axis +X).

    Modeled parts already sit in the print pose, so an angle=0 connect holds
    that pose instead of re-rotating the pinned link.
    """
    return bd.Location(
        bd.Plane(origin=(0.0, y_fold, AXIS_Z), x_dir=(0.0, 0.0, 1.0), z_dir=(1.0, 0.0, 0.0))
    )


@step(out="../STEP/print_in_place_multi_pivot_phone_holder.step")
def print_in_place_multi_pivot_phone_holder():
    """Return the print-in-place holder as a labeled four-link assembly compound."""
    asm = AssemblyHelper("print_in_place_multi_pivot_phone_holder")

    base = asm.add(_make_base(), "base_mount_plate")
    lower = asm.add(_make_lower_arm(), "lower_arm_link")
    upper = asm.add(_make_upper_arm(), "upper_arm_link")
    cradle = asm.add(_make_cradle(), "cradle_phone_holder")

    j1_bore = asm.revolute_frame(base, "pivot1_bore_axis", bd.Axis((0.0, Y_J1, AXIS_Z), (1.0, 0.0, 0.0)))
    j1_pin = asm.rigid_frame(lower, "pivot1_pin_frame", _pin_frame_loc(Y_J1))
    asm.revolute(j1_bore, j1_pin, angle=0.0, label="base_pivot")

    j2_bore = asm.revolute_frame(lower, "pivot2_bore_axis", bd.Axis((0.0, Y_J2, AXIS_Z), (1.0, 0.0, 0.0)))
    j2_pin = asm.rigid_frame(upper, "pivot2_pin_frame", _pin_frame_loc(Y_J2))
    asm.revolute(j2_bore, j2_pin, angle=0.0, label="elbow_pivot")

    j3_bore = asm.revolute_frame(upper, "pivot3_bore_axis", bd.Axis((0.0, Y_J3, AXIS_Z), (1.0, 0.0, 0.0)))
    j3_pin = asm.rigid_frame(cradle, "pivot3_pin_frame", _pin_frame_loc(Y_J3))
    asm.revolute(j3_bore, j3_pin, angle=0.0, label="wrist_pivot")

    return asm.build()


if __name__ == "__main__":
    print_in_place_multi_pivot_phone_holder()
