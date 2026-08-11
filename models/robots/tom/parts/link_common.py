#!/usr/bin/env python3
"""
Shared layout for the tom v2 servo-to-servo link brackets.

Link frame convention (millimeters, Z-up):
- +Z is up. The bottom servo's output shaft is coaxial with the link's
  vertical centerline (X = Y = 0) and points down (-Z); its case-bottom
  face is up at Z = 0 and its body runs along +X (rear end at
  X = -10.11, front end at X = +35.11). It uses the rear-horn-less
  variant (parts/imports/sts3250_no_rear_horn.step) so bracket feet seat flat
  on its case-bottom face; only the case's small rear journal/screw stub
  still protrudes there.
- The top servo forms a horizontal pitch joint: it stands on end with
  its horn axis along X at (Y = 0, Z = TOP_PIVOT_Z_MM) and the
  horn-to-horn span centered on the link centerline (output horn face at
  X = +18.3, rear horn face at X = -18.3). Two mounting variations are
  supported:
  - horn mount: the bracket horn plates bolt to both horn faces
    (4x M3-pattern screws per side) and the servo body, which belongs to
    the next link, is flipped to stand above the pivot so it rotates
    freely.
  - case mount: the brackets bolt to the servo case with 2x M2 screws
    per side (flush side into the case-bottom face holes at
    Y = +/-10.25, Z = 102.25; offset side into the case-top face holes
    at Y = +/-10.25, Z = 106.0), the body hangs down into the link, and
    the next link's yoke grabs the free horns.

All brackets are authored directly in this link frame so the bracket
STEP files and the verification assemblies compose with identity
transforms for the brackets.

Servo source geometry (STS3250 local frame, from
parts/imports/sts3250.step):
- body bounds x [-35.61, 9.61], y [-28.2, 9.2], z [-12.36, +12.36]
- output shaft axis at (x, z) = (-25.5, 0), pointing +y; output horn
  face at y = +9.2, rear horn face at y = -27.4, each with four
  diameter-3.2 screw holes on a 7 mm circle plus a center hole; the rear
  journal/screw stub protrudes to y = -28.2
- case-bottom plane y = -25.6 with four M2 holes (r 1.1) at
  x in {-17.2, +7.25}, z = +/-10.25, facing -y
- case-top plane y = +6.4 with four M2 holes (r 1.1) at
  x in {-17.2, +3.5}, z = +/-10.25, facing +y, around the output horn
  boss (radius 11.2)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

TOM_DIR = Path(__file__).resolve().parents[1]
V2_DIR = Path(__file__).resolve().parents[1]
_CACHE_HOME = V2_DIR / ".cache"
_CACHE_HOME.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("XDG_CACHE_HOME", str(_CACHE_HOME))

import build123d

if str(TOM_DIR) not in sys.path:
    sys.path.insert(0, str(TOM_DIR))

from robot_common.booleans import intersection_volume
from robot_common.materials import GRAY_ALUMINUM_COLOR
from robot_common.step_import import import_as_shape


# Plain bare-aluminum tint for the v2 brackets. Without an explicit source
# color the viewer falls back to its dark theme paint, which reads as a
# deliberately colored part.
BRACKET_COLOR = GRAY_ALUMINUM_COLOR

SERVO_STEP = V2_DIR / "parts" / "imports" / "sts3250.step"
SERVO_NO_REAR_HORN_STEP = V2_DIR / "parts" / "imports" / "sts3250_no_rear_horn.step"

def _env_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number, got {value!r}") from exc
    if parsed <= 0.0:
        raise ValueError(f"{name} must be positive, got {parsed!r}")
    return parsed


# Sheet stock for the v2 aluminum brackets (SendCutSend 0.063 in 5052-H32).
SENDCUTSEND_ALU_063_THICKNESS_MM = 25.4 * 0.063
SHEET_THICKNESS_MM = _env_float(
    "TOM_V2_SHEET_THICKNESS_MM",
    SENDCUTSEND_ALU_063_THICKNESS_MM,
)
SCS_EFFECTIVE_BEND_RADIUS_MM = 25.4 * 0.035
SCS_K_FACTOR = 0.42
SCS_BEND_DEDUCTION_90_MM = 25.4 * 0.096
SCS_OUTSIDE_SETBACK_90_MM = SCS_EFFECTIVE_BEND_RADIUS_MM + SHEET_THICKNESS_MM
SCS_BEND_ALLOWANCE_90_MM = (2.0 * SCS_OUTSIDE_SETBACK_90_MM) - SCS_BEND_DEDUCTION_90_MM
MOUNT_PLANE_CLEARANCE_MM = 0.0
SIDE_FACE_CLEARANCE_MM = 0.25
# Gap between a horn mount face and its bracket horn plate, matching the
# v1 servo_horn_yoke convention. Also used for case-face plates.
HORN_FACE_GAP_MM = 0.25
ROTATING_PART_CLEARANCE_MM = 0.5

# STS3250 local-frame facts (verified at build time against the STEP).
SERVO_HALF_WIDTH_MM = 12.360025
SERVO_BODY_X_MIN_MM = -35.610023
SERVO_BODY_X_MAX_MM = 9.610026
SERVO_SHAFT_LOCAL_X_MM = -25.5
SERVO_CASE_BOTTOM_LOCAL_Y_MM = -25.6
SERVO_CASE_TOP_LOCAL_Y_MM = 6.4
SERVO_OUTPUT_HORN_FACE_LOCAL_Y_MM = 9.2
SERVO_REAR_HORN_FACE_LOCAL_Y_MM = -27.4
# The rear journal/screw stub protrudes 0.8 mm past the rear horn face.
SERVO_REAR_EXTREME_LOCAL_Y_MM = -28.2
SERVO_MOUNT_HOLE_LOCAL_X_MM = (-17.2, 7.25)
SERVO_TOP_MOUNT_HOLE_LOCAL_X_MM = (-17.2, 3.5)
SERVO_MOUNT_HOLE_LOCAL_Z_MM = 10.25
SERVO_MOUNT_HOLE_RADIUS_MM = 1.1
SERVO_HORN_SCREW_CIRCLE_RADIUS_MM = 7.0
SERVO_HORN_SCREW_HOLE_RADIUS_MM = 1.6
SERVO_REAR_HORN_DISK_RADIUS_MM = 9.6
SERVO_OUTPUT_HORN_BOSS_RADIUS_MM = 11.2
SERVO_REAR_JOURNAL_RADIUS_MM = 3.05
REAR_JOURNAL_CLEARANCE_RADIUS_MM = 3.75

# Link-frame layout derived from the facts above.
BOTTOM_FACE_Z_MM = 0.0
PLATE_HALF_SPAN_MM = SERVO_HALF_WIDTH_MM
PLATE_INNER_OFFSET_MM = SERVO_HALF_WIDTH_MM + SIDE_FACE_CLEARANCE_MM
PLATE_OUTER_OFFSET_MM = PLATE_INNER_OFFSET_MM + SHEET_THICKNESS_MM
# Servo body extents measured from the shaft axis along the body direction.
BODY_REAR_OVERHANG_MM = -(SERVO_BODY_X_MIN_MM - SERVO_SHAFT_LOCAL_X_MM)  # 10.11
BODY_FRONT_REACH_MM = SERVO_BODY_X_MAX_MM - SERVO_SHAFT_LOCAL_X_MM  # 35.11
# Mount hole columns measured from the shaft axis along the body direction.
HOLE_NEAR_OFFSET_MM = SERVO_MOUNT_HOLE_LOCAL_X_MM[0] - SERVO_SHAFT_LOCAL_X_MM  # 8.3
HOLE_FAR_OFFSET_MM = SERVO_MOUNT_HOLE_LOCAL_X_MM[1] - SERVO_SHAFT_LOCAL_X_MM  # 32.75
HOLE_SIDE_OFFSET_MM = SERVO_MOUNT_HOLE_LOCAL_Z_MM  # 10.25

# The offset-side web sits outboard of the bottom servo's front end face.
# Its position is set by SendCutSend's U/C-channel rule: the jog channel
# base (web inner face to offset-wall outer face) must be at least 2x the
# screw-tab flange height. 39.5 gives a 22.15 mm base vs a 21.62 mm
# requirement.
OUTER_WEB_INNER_X_MM = 39.5
OUTER_WEB_OUTER_X_MM = OUTER_WEB_INNER_X_MM + SHEET_THICKNESS_MM
OUTER_WEB_CLEARANCE_MM = OUTER_WEB_INNER_X_MM - BODY_FRONT_REACH_MM

# Top pitch joint: the horn axis runs along X at this height. For the
# case-mounted link, center the visible case span on the link centerline so
# the top servo body reads centered over the bottom horn axis; the pitch axis
# still intersects that vertical axis at X = Y = 0.
TOP_PIVOT_Z_MM = 180.0
HORN_HALF_SPAN_MM = 0.5 * (
    SERVO_OUTPUT_HORN_FACE_LOCAL_Y_MM - SERVO_REAR_HORN_FACE_LOCAL_Y_MM
)  # 18.3
# Offset that centers the horn span: local y -> X = y + this value.
HORN_SPAN_CENTERING_OFFSET_MM = HORN_HALF_SPAN_MM - SERVO_OUTPUT_HORN_FACE_LOCAL_Y_MM  # 9.1
# Offset that centers the case side faces for the case-mounted top servo.
CASE_SPAN_CENTERING_OFFSET_MM = -0.5 * (
    SERVO_CASE_BOTTOM_LOCAL_Y_MM + SERVO_CASE_TOP_LOCAL_Y_MM
)  # 9.6
# Z mapping constants for the two top-servo orientations.
TOP_BODY_DOWN_Z_OFFSET_MM = TOP_PIVOT_Z_MM + SERVO_SHAFT_LOCAL_X_MM  # Z = 109.5 - x
TOP_BODY_UP_Z_OFFSET_MM = TOP_PIVOT_Z_MM - SERVO_SHAFT_LOCAL_X_MM  # Z = x + 160.5

# Horn-mount plates (horn variation).
HORN_PLATE_INNER_X_MM = HORN_HALF_SPAN_MM + HORN_FACE_GAP_MM
HORN_PLATE_OUTER_X_MM = HORN_PLATE_INNER_X_MM + SHEET_THICKNESS_MM
HORN_PLATE_TOP_Z_MM = TOP_PIVOT_Z_MM + 13.0

# Case-mount plates (case variation). The plates sit against the case
# faces and stop below the rotating horn parts.
CASE_BOTTOM_FACE_X_MM = SERVO_CASE_BOTTOM_LOCAL_Y_MM + CASE_SPAN_CENTERING_OFFSET_MM  # -16.0
CASE_TOP_FACE_X_MM = SERVO_CASE_TOP_LOCAL_Y_MM + CASE_SPAN_CENTERING_OFFSET_MM  # +16.0
CASE_FLUSH_PLATE_INNER_X_MM = -(abs(CASE_BOTTOM_FACE_X_MM) + HORN_FACE_GAP_MM)  # -16.75
CASE_FLUSH_PLATE_OUTER_X_MM = CASE_FLUSH_PLATE_INNER_X_MM - SHEET_THICKNESS_MM
CASE_OFFSET_PLATE_INNER_X_MM = CASE_TOP_FACE_X_MM + HORN_FACE_GAP_MM  # +15.75
CASE_OFFSET_PLATE_OUTER_X_MM = CASE_OFFSET_PLATE_INNER_X_MM + SHEET_THICKNESS_MM
CASE_FLUSH_PLATE_TOP_Z_MM = (
    TOP_PIVOT_Z_MM - SERVO_REAR_HORN_DISK_RADIUS_MM - ROTATING_PART_CLEARANCE_MM
)  # 124.9
CASE_OFFSET_PLATE_TOP_Z_MM = (
    TOP_PIVOT_Z_MM - SERVO_OUTPUT_HORN_BOSS_RADIUS_MM - ROTATING_PART_CLEARANCE_MM
)  # 123.3
# Case-mount screw hole heights (Z = TOP_BODY_DOWN_Z_OFFSET_MM - local x).
CASE_FLUSH_HOLE_Z_MM = TOP_BODY_DOWN_Z_OFFSET_MM - SERVO_MOUNT_HOLE_LOCAL_X_MM[1]  # 102.25
CASE_OFFSET_HOLE_Z_MM = TOP_BODY_DOWN_Z_OFFSET_MM - SERVO_TOP_MOUNT_HOLE_LOCAL_X_MM[1]  # 106.0
# Both case faces carry raised center sections that stand proud of the
# screw-boss planes (measured from the STEP): a 1.9 mm panel within
# Y +/-9.242 starting at Z = 105.3 on the case-bottom side, and a 1.1 mm
# ridge within Y +/-7.0 starting at the body's lower end (Z = 99.89) on
# the case-top side. The case plates get open-top relief notches around
# them and seat on the flat outer margins.
CASE_FLUSH_RELIEF_HALF_WIDTH_MM = 9.242 + ROTATING_PART_CLEARANCE_MM
CASE_FLUSH_RELIEF_BOTTOM_Z_MM = 105.297 - ROTATING_PART_CLEARANCE_MM
CASE_OFFSET_RELIEF_HALF_WIDTH_MM = 7.0 + ROTATING_PART_CLEARANCE_MM
CASE_OFFSET_RELIEF_BOTTOM_Z_MM = 99.894 - ROTATING_PART_CLEARANCE_MM

# Case-mount brackets: two separate formed parts (split per SendCutSend's
# U/C-channel forming rule). The flush wall ends flat below the
# case-bottom raised panel; the offset wall ends just above its M2 screws
# as two short tabs whose bend is split through the middle (the case-top
# holes sit above the center-ridge relief line, so a continuous bend
# there would leave an under-minimum local flange).
CASE_FLUSH_WALL_TOP_Z_MM = CASE_FLUSH_RELIEF_BOTTOM_Z_MM  # 104.797
CASE_OFFSET_TAB_TOP_Z_MM = (
    CASE_OFFSET_HOLE_Z_MM + SERVO_MOUNT_HOLE_RADIUS_MM + 1.5
)  # 108.6
# SendCutSend ALU-063 bend-service rule values for 5052-H32 0.063 in.
SCS_MIN_FLANGE_BEFORE_BEND_MM = 25.4 * 0.255
SCS_MIN_FLANGE_AFTER_BEND_MM = 25.4 * 0.303
SCS_CHANNEL_BASE_TO_FLANGE_RATIO = 2.0
SCS_DIE_WIDTH_MM = 25.4 * 0.472
SCS_HALF_DIE_WIDTH_MM = 0.5 * SCS_DIE_WIDTH_MM
SCS_BEND_RELIEF_DEPTH_MM = 25.4 * 0.118
SCS_MIN_CORNER_RELIEF_DISTANCE_FROM_BEND_LINE_MM = 25.4 * 0.030

# Bottom-servo up-face obstacles (extents measured from the STEP, with
# clearance margins): the cable bay and the raised center zone that runs
# from the bay through the raised panel.
CABLE_BAY_X_MIN_MM = 11.65 - ROTATING_PART_CLEARANCE_MM
CABLE_BAY_X_MAX_MM = 16.25 + ROTATING_PART_CLEARANCE_MM
CABLE_BAY_HALF_WIDTH_MM = 9.1 + ROTATING_PART_CLEARANCE_MM
BOTTOM_PANEL_X_MAX_MM = 24.59 + 0.5 * 9.63 + ROTATING_PART_CLEARANCE_MM  # 29.905

# Bracket bodies are 25.8 mm wide (0.54 mm clear of the servo width per
# side). The flush foot's stiffening lips are protruding tabs folded down
# at the body edge, so each lip bend line terminates at free edges of the
# flat blank and needs no bend relief.
BODY_HALF_WIDTH_MM = 12.9
LIP_OUTER_HALF_WIDTH_MM = BODY_HALF_WIDTH_MM + SHEET_THICKNESS_MM
LIP_X_MIN_MM = -13.8
LIP_X_MAX_MM = 2.0

FOOT_BOTTOM_Z_MM = BOTTOM_FACE_Z_MM + MOUNT_PLANE_CLEARANCE_MM
FOOT_TOP_Z_MM = FOOT_BOTTOM_Z_MM + SHEET_THICKNESS_MM
# Lip legs hang 9.5 mm (formed outside length) below the foot, keeping
# the flat flange 0.5 mm above the before-bend minimum.
LIP_BOTTOM_Z_MM = FOOT_TOP_Z_MM - 9.5
# The shelf tucks 0.5 mm under the hanging top servo's lower end face so
# the screw-tab flange above it stays as short as possible (jog channel
# 2:1 rule).
SHELF_TOP_Z_MM = CASE_OFFSET_RELIEF_BOTTOM_Z_MM  # 99.394
SHELF_BOTTOM_Z_MM = SHELF_TOP_Z_MM - SHEET_THICKNESS_MM  # 97.362

# Feet stop clear of the cable bay (flush side) and the raised panel
# (offset side), so the split feet need no windows.
FLUSH_FOOT_REACH_X_MM = CABLE_BAY_X_MIN_MM  # 11.15
OFFSET_FOOT_REACH_X_MM = BOTTOM_PANEL_X_MAX_MM  # 29.905

# Single-bend offset bracket: the case-top plate descends to the bottom
# servo and one bend turns it outboard across the servo's up-face. The
# foot keeps two side rails seated on the servo's Z=0 rim strips
# (inner rim edges at Y = +/-12.06) and a window around the raised
# center zone (measured at Y <= +/-9.242, proud up to Z = 1.9).
OFFSET_FOOT_END_X_MM = 35.5
OFFSET_WINDOW_HALF_WIDTH_MM = 9.7
# The window also relieves the plate's bottom edge between the rails so
# the interrupted foot bend terminates at free edges, and doubles as the
# bottom servo's cable exit slot over its cable bay. The extra 1.5 mm
# keeps the relief past the published minimum regardless of where the
# flat-pattern bend line lands within the bend allowance.
OFFSET_PLATE_RELIEF_TOP_Z_MM = FOOT_TOP_Z_MM + SCS_BEND_RELIEF_DEPTH_MM + 1.5  # 7.342
# The bend zone and foot flare outboard so each interrupted-bend rail is
# three sheet thicknesses wide instead of the two-thickness rule-of-thumb
# minimum; the flare wings end at free edges above the bend.
OFFSET_FOOT_FLARE_HALF_WIDTH_MM = 14.5
OFFSET_FLARE_TOP_Z_MM = 8.0

INTERFERENCE_VOLUME_LIMIT_MM3 = 1e-3
HOLE_MATCH_TOLERANCE_MM = 0.05

# --- Carbon-tube link variant (RoArm-style) ---------------------------
# Off-the-shelf clamps: SK10 (base-mount shaft support, holds the tube
# against the vertical top plate) and SHF10 (flange-mount shaft support,
# holds the tube on the horizontal bottom plate). step.parts only hosts
# generic envelopes for these SKUs, so the assembly uses true-dimension
# envelopes built from the standard SK10/SHF10 catalog dimensions below.
# Verify against the sourced vendor's datasheet before cutting plates.
# The carbon tube itself is a step.parts catalog miss (recorded
# 2026-06-13); it is generic 3K roll-wrapped 10 x 8 mm stock cut to
# length.
SK10_CENTER_HEIGHT_MM = 20.0
SK10_BOLT_PITCH_MM = 32.0
SK10_BASE_WIDTH_MM = 42.0
SK10_THICKNESS_MM = 14.0
SK10_DEPTH_MM = 27.0
SK10_BASE_SLAB_MM = 8.0
SHF10_BOLT_PITCH_MM = 35.0
SHF10_FLANGE_WIDTH_MM = 46.5
SHF10_FLANGE_THICKNESS_MM = 7.0
SHF10_HUB_RADIUS_MM = 10.0
SHF10_HUB_HEIGHT_MM = 13.0
CLAMP_BOLT_CLEARANCE_RADIUS_MM = 2.9  # M5 clearance
TUBE_OUTER_RADIUS_MM = 5.0
TUBE_INNER_RADIUS_MM = 4.0
TUBE_BORE_CLEARANCE_MM = 0.05

# Tube-link layout. The flat plates are 0.125 in 5052 so the bottom
# servo's rear journal/screw stub (2.6 mm proud) is buried inside the
# bottom plate's through hole.
TUBE_PLATE_THICKNESS_MM = 25.4 * 0.125  # 3.175
TUBE_TOP_PLATE_INNER_X_MM = CASE_TOP_FACE_X_MM + HORN_FACE_GAP_MM  # 15.75
TUBE_TOP_PLATE_OUTER_X_MM = TUBE_TOP_PLATE_INNER_X_MM + TUBE_PLATE_THICKNESS_MM
TUBE_AXIS_X_MM = TUBE_TOP_PLATE_INNER_X_MM - SK10_CENTER_HEIGHT_MM  # -4.25
BOTTOM_PLATE_TOP_Z_MM = FOOT_BOTTOM_Z_MM + TUBE_PLATE_THICKNESS_MM  # 3.425
TUBE_BOTTOM_Z_MM = 5.0
TUBE_TOP_Z_MM = 95.0
SK10_CENTER_Z_MM = 85.0
TUBE_TOP_PLATE_BOTTOM_Z_MM = 70.0
TUBE_TOP_PLATE_FLARE_HALF_WIDTH_MM = 19.5
BOTTOM_PLATE_FLARE_HALF_WIDTH_MM = 21.0
BOTTOM_PLATE_X_MIN_MM = -14.5
BOTTOM_PLATE_X_MAX_MM = 35.5
BOTTOM_PLATE_FLARE_X_MAX_MM = 6.0

# Row-major 4x4 transforms placing the servos in the link frame.
# Horn variation: body up (local x -> +Z), output horn toward +X.
TOP_SERVO_HORN_TRANSFORM = (
    0.0, 1.0, 0.0, HORN_SPAN_CENTERING_OFFSET_MM,
    0.0, 0.0, 1.0, 0.0,
    1.0, 0.0, 0.0, TOP_BODY_UP_Z_OFFSET_MM,
    0.0, 0.0, 0.0, 1.0,
)
def top_servo_case_transform(case_span_centering_offset_mm: float = CASE_SPAN_CENTERING_OFFSET_MM) -> tuple[float, ...]:
    # Case variation: body down (local x -> -Z), output horn toward +X.
    return (
        0.0, 1.0, 0.0, case_span_centering_offset_mm,
        0.0, 0.0, -1.0, 0.0,
        -1.0, 0.0, 0.0, TOP_BODY_DOWN_Z_OFFSET_MM,
        0.0, 0.0, 0.0, 1.0,
    )


TOP_SERVO_CASE_TRANSFORM = top_servo_case_transform()
BOTTOM_SERVO_TRANSFORM = (
    1.0, 0.0, 0.0, -SERVO_SHAFT_LOCAL_X_MM,
    0.0, 0.0, 1.0, 0.0,
    0.0, -1.0, 0.0, SERVO_CASE_BOTTOM_LOCAL_Y_MM,
    0.0, 0.0, 0.0, 1.0,
)

# Expected hole centers in the link frame.
BOTTOM_SERVO_MOUNT_HOLES_XY_MM = tuple(
    (x_offset, side * HOLE_SIDE_OFFSET_MM)
    for x_offset in (HOLE_NEAR_OFFSET_MM, HOLE_FAR_OFFSET_MM)
    for side in (-1.0, 1.0)
)
# Horn screw holes on each horn face, as (y, z) in the link frame.
HORN_SCREW_HOLES_YZ_MM = (
    (0.0, TOP_PIVOT_Z_MM + SERVO_HORN_SCREW_CIRCLE_RADIUS_MM),
    (0.0, TOP_PIVOT_Z_MM - SERVO_HORN_SCREW_CIRCLE_RADIUS_MM),
    (SERVO_HORN_SCREW_CIRCLE_RADIUS_MM, TOP_PIVOT_Z_MM),
    (-SERVO_HORN_SCREW_CIRCLE_RADIUS_MM, TOP_PIVOT_Z_MM),
)
# Case-mount screw holes, as (y, z) in the link frame.
CASE_FLUSH_HOLES_YZ_MM = tuple(
    (side * HOLE_SIDE_OFFSET_MM, CASE_FLUSH_HOLE_Z_MM) for side in (-1.0, 1.0)
)
CASE_OFFSET_HOLES_YZ_MM = tuple(
    (side * HOLE_SIDE_OFFSET_MM, CASE_OFFSET_HOLE_Z_MM) for side in (-1.0, 1.0)
)


def make_box(
    *,
    x_min: float,
    x_max: float,
    y_min: float,
    y_max: float,
    z_min: float,
    z_max: float,
) -> build123d.Solid:
    return build123d.Solid.make_box(
        x_max - x_min,
        y_max - y_min,
        z_max - z_min,
        plane=build123d.Plane(origin=build123d.Vector(x_min, y_min, z_min)),
    )


def make_z_cylinder(
    *,
    x: float,
    y: float,
    radius: float,
    z_min: float,
    z_max: float,
) -> build123d.Solid:
    return build123d.Solid.make_cylinder(
        radius,
        z_max - z_min,
        plane=build123d.Plane(origin=build123d.Vector(x, y, z_min), z_dir=(0.0, 0.0, 1.0)),
    )


def make_x_cylinder(
    *,
    y: float,
    z: float,
    radius: float,
    x_min: float,
    x_max: float,
) -> build123d.Solid:
    return build123d.Solid.make_cylinder(
        radius,
        x_max - x_min,
        plane=build123d.Plane(origin=build123d.Vector(x_min, y, z), z_dir=(1.0, 0.0, 0.0)),
    )


def make_y_cylinder(
    *,
    x: float,
    z: float,
    radius: float,
    y_min: float,
    y_max: float,
) -> build123d.Solid:
    return build123d.Solid.make_cylinder(
        radius,
        y_max - y_min,
        plane=build123d.Plane(origin=build123d.Vector(x, y_min, z), z_dir=(0.0, 1.0, 0.0)),
    )


def _transform_location(transform: tuple[float, ...]) -> build123d.Location:
    return build123d.Location(
        build123d.Plane(
            origin=(transform[3], transform[7], transform[11]),
            x_dir=(transform[0], transform[4], transform[8]),
            z_dir=(transform[2], transform[6], transform[10]),
        )
    )


def _load_servo_shape(step_path: Path) -> build123d.Shape:
    generator_path = step_path.with_name(step_path.name + ".py")
    if generator_path.is_file():
        # A GENERATED servo variant (the no-rear-horn sts3250, derived from the stock servo) builds
        # from its gen_step — a source-level dependency, so no committed STEP is needed. The stock
        # IMPORTED sts3250 (no generator) keeps the cached import. The layout-fact check below
        # validates whichever shape we get.
        import copy

        from robot_common.link_assembly import _generated_child_shape

        shape = copy.deepcopy(_generated_child_shape(str(generator_path)))
    elif step_path.exists():
        shape = import_as_shape(step_path)
    else:
        raise FileNotFoundError(f"Missing STS3250 servo STEP: {step_path}")
    bb = shape.bounding_box()
    for measured, expected in (
        (bb.min.X, SERVO_BODY_X_MIN_MM),
        (bb.max.X, SERVO_BODY_X_MAX_MM),
        (bb.min.Z, -SERVO_HALF_WIDTH_MM),
        (bb.max.Z, SERVO_HALF_WIDTH_MM),
        (bb.min.Y, SERVO_REAR_EXTREME_LOCAL_Y_MM),
        (bb.max.Y, SERVO_OUTPUT_HORN_FACE_LOCAL_Y_MM),
    ):
        if abs(measured - expected) > 0.01:
            raise RuntimeError(
                f"{step_path.name} no longer matches the v2 layout facts: "
                f"measured {measured:.4f}, expected {expected:.4f}"
            )
    return shape


def place_servo(shape: build123d.Shape, transform: tuple[float, ...]) -> build123d.Shape:
    return shape.moved(_transform_location(transform))


def _planar_hole_centers(
    shape: build123d.Shape,
    *,
    axis: str,
    plane_coordinate: float,
) -> list[tuple[float, float, float]]:
    """Inner circular wire centers on planar faces at the given axis plane.

    Returns (a, b, radius) where (a, b) are the in-plane coordinates: (x, y)
    for a Z-normal plane and (y, z) for an X-normal plane.
    """
    centers: list[tuple[float, float, float]] = []
    for face in shape.faces():
        if face.geom_type.name != "PLANE":
            continue
        face_center = face.center()
        coordinate = face_center.Z if axis == "z" else face_center.X
        if abs(coordinate - plane_coordinate) > 0.05:
            continue
        normal = face.normal_at(face_center)
        component = normal.Z if axis == "z" else normal.X
        if abs(abs(component) - 1.0) > 1e-3:
            continue
        wires = list(face.wires())
        if len(wires) < 2:
            continue
        outer = max(wires, key=lambda wire: abs(build123d.Face(wire).area))
        for wire in wires:
            if wire.is_same(outer):
                continue
            circle_edges = [edge for edge in wire.edges() if edge.geom_type.name == "CIRCLE"]
            if not circle_edges:
                continue
            center = build123d.Face(wire).center()
            radius = max(edge.radius for edge in circle_edges)
            if axis == "z":
                centers.append((center.X, center.Y, radius))
            else:
                centers.append((center.Y, center.Z, radius))
    return centers


def _verify_holes(
    found: list[tuple[float, float, float]],
    *,
    expected: tuple[tuple[float, float], ...],
    radius: float,
    label: str,
) -> None:
    for expected_a, expected_b in expected:
        if not any(
            abs(a - expected_a) <= HOLE_MATCH_TOLERANCE_MM
            and abs(b - expected_b) <= HOLE_MATCH_TOLERANCE_MM
            and abs(found_radius - radius) <= HOLE_MATCH_TOLERANCE_MM
            for a, b, found_radius in found
        ):
            raise RuntimeError(
                f"Placed STS3250 is missing an expected {label} hole at "
                f"({expected_a:.3f}, {expected_b:.3f}); found {found!r}"
            )


def verify_bottom_servo_mount_holes(placed_servo: build123d.Shape) -> None:
    _verify_holes(
        _planar_hole_centers(placed_servo, axis="z", plane_coordinate=BOTTOM_FACE_Z_MM),
        expected=BOTTOM_SERVO_MOUNT_HOLES_XY_MM,
        radius=SERVO_MOUNT_HOLE_RADIUS_MM,
        label="bottom-servo case-bottom",
    )


def verify_top_servo_horn_holes(placed_servo: build123d.Shape, *, side: float) -> None:
    _verify_holes(
        _planar_hole_centers(placed_servo, axis="x", plane_coordinate=side * HORN_HALF_SPAN_MM),
        expected=HORN_SCREW_HOLES_YZ_MM,
        radius=SERVO_HORN_SCREW_HOLE_RADIUS_MM,
        label=f"horn-face (side {side:+.0f})",
    )


def verify_top_servo_case_holes(
    placed_servo: build123d.Shape,
    *,
    case_span_centering_offset_mm: float = CASE_SPAN_CENTERING_OFFSET_MM,
) -> None:
    _verify_holes(
        _planar_hole_centers(
            placed_servo,
            axis="x",
            plane_coordinate=SERVO_CASE_BOTTOM_LOCAL_Y_MM + case_span_centering_offset_mm,
        ),
        expected=CASE_FLUSH_HOLES_YZ_MM,
        radius=SERVO_MOUNT_HOLE_RADIUS_MM,
        label="case-bottom-face",
    )
    _verify_holes(
        _planar_hole_centers(
            placed_servo,
            axis="x",
            plane_coordinate=SERVO_CASE_TOP_LOCAL_Y_MM + case_span_centering_offset_mm,
        ),
        expected=CASE_OFFSET_HOLES_YZ_MM,
        radius=SERVO_MOUNT_HOLE_RADIUS_MM,
        label="case-top-face",
    )


def verify_no_interference(
    bracket: build123d.Shape,
    placed_servo: build123d.Shape,
    *,
    label: str,
) -> float:
    volume = intersection_volume(placed_servo, bracket)
    if volume > INTERFERENCE_VOLUME_LIMIT_MM3:
        raise RuntimeError(f"Bracket intersects {label} by {volume:.6f} mm^3")
    return volume


def placed_link_servos_horn() -> tuple[build123d.Shape, build123d.Shape]:
    top = place_servo(_load_servo_shape(SERVO_STEP), TOP_SERVO_HORN_TRANSFORM)
    bottom = place_servo(_load_servo_shape(SERVO_NO_REAR_HORN_STEP), BOTTOM_SERVO_TRANSFORM)
    verify_top_servo_horn_holes(top, side=1.0)
    verify_top_servo_horn_holes(top, side=-1.0)
    verify_bottom_servo_mount_holes(bottom)
    return top, bottom


def placed_link_servos_case(
    *,
    case_span_centering_offset_mm: float = CASE_SPAN_CENTERING_OFFSET_MM,
) -> tuple[build123d.Shape, build123d.Shape]:
    top = place_servo(
        _load_servo_shape(SERVO_STEP),
        top_servo_case_transform(case_span_centering_offset_mm),
    )
    bottom = place_servo(_load_servo_shape(SERVO_NO_REAR_HORN_STEP), BOTTOM_SERVO_TRANSFORM)
    verify_top_servo_case_holes(
        top,
        case_span_centering_offset_mm=case_span_centering_offset_mm,
    )
    verify_bottom_servo_mount_holes(bottom)
    return top, bottom


def horn_plate(*, side: float, z_min: float = SHELF_BOTTOM_Z_MM) -> build123d.Shape:
    """Vertical horn plate for one side: a sheet panel bolted to the horn
    face at X = side * 18.3, carrying the four 7 mm-circle screw holes and
    a center clearance hole on the pitch axis."""
    x_inner = side * HORN_PLATE_INNER_X_MM
    x_outer = side * HORN_PLATE_OUTER_X_MM
    plate: build123d.Shape = make_box(
        x_min=min(x_inner, x_outer),
        x_max=max(x_inner, x_outer),
        y_min=-PLATE_HALF_SPAN_MM,
        y_max=PLATE_HALF_SPAN_MM,
        z_min=z_min,
        z_max=HORN_PLATE_TOP_Z_MM,
    )
    cut_x_min = min(x_inner, x_outer) - 2.0
    cut_x_max = max(x_inner, x_outer) + 2.0
    for hole_y, hole_z in HORN_SCREW_HOLES_YZ_MM:
        plate = plate.cut(
            make_x_cylinder(
                y=hole_y,
                z=hole_z,
                radius=SERVO_HORN_SCREW_HOLE_RADIUS_MM,
                x_min=cut_x_min,
                x_max=cut_x_max,
            )
        )
    # The rear (-X) side needs a larger center hole: the case's rear
    # journal/screw stub protrudes 0.8 mm past the rear horn face, through
    # the plate plane. The output (+X) side only needs access to the horn's
    # center screw.
    center_clearance_radius = (
        REAR_JOURNAL_CLEARANCE_RADIUS_MM if side < 0.0 else SERVO_HORN_SCREW_HOLE_RADIUS_MM
    )
    plate = plate.cut(
        make_x_cylinder(
            y=0.0,
            z=TOP_PIVOT_Z_MM,
            radius=center_clearance_radius,
            x_min=cut_x_min,
            x_max=cut_x_max,
        )
    )
    return plate
