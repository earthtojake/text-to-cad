#!/usr/bin/env python3
"""
Generate the tom v2 wrap link plate: one sheet part with two bend lines
connecting the two servos along the +Y side of the link.

Geometry per the side-view draft and the referenced features:
- foot: lies on the bottom servo's case-bottom (up-facing) plane,
  connecting the two +Y mount holes at (X = 8.3 | 32.75, Y = 10.25),
  its inner edge wrapping around the cable bay with a 0.4 mm overhang
  and clearing the raised center zone,
- bend 1 (axis X): split into two segments over the hole zones, each
  with a 7.7 mm formed flange,
- riser leg: lies flat against the top servo's +Y side face (the
  referenced face spans X 7.9..15.2, Z 102.1..129.3), full foot width
  at the bottom and cut partway up to the face's width ("finishing
  width"), with a corner extension past the servo's case-top corner,
- bend 2 (axis Z, full length): wraps onto the case-top face plane and
  connects to its two +Y screw holes at (Y = 10.25, Z = 106 | 126.7).
  The flange stands 1.5 mm off the face on spacers (5x M2 washers or a
  1.5 mm spacer per screw) so it clears the case-top center ridge
  (1.1 mm proud) and the output horn boss (1.3 mm proud), allowing a
  full-depth rectangular flange that meets the published minimum
  flange length.

Advisory (not in SendCutSend's published ruleset): the servo's holes
sit 2.1 mm from its case corners, so both bends run 2.7-3.2 mm from
screw holes - inside the press-brake die span. Expect minor hole
distortion; ream after forming if screws bind.

Usage:
  python v2/link_bracket.py
"""

from __future__ import annotations

import math
import os
import sys
from dataclasses import dataclass
from pathlib import Path

V2_DIR = Path(__file__).resolve().parent
if str(V2_DIR) not in sys.path:
    sys.path.insert(0, str(V2_DIR))

import build123d

from cadgen import flatten as dxf_topology
import link_common as lc


PART_NAME = Path(__file__).stem

CUT_EXTENSION_MM = 2.0


@dataclass(frozen=True)
class FlatPattern:
    outside_setback_mm: float
    bend_allowance_mm: float
    bend_deduction_mm: float
    panel_join_shift_mm: float
    foot_bend_line_y_mm: float
    wrap_bend_line_x_mm: float


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a floating point number, got {raw!r}") from exc


def _env_float_any(names: tuple[str, ...], default: float) -> float:
    for name in names:
        raw = os.environ.get(name)
        if raw is None:
            continue
        try:
            return float(raw)
        except ValueError as exc:
            raise ValueError(f"{name} must be a floating point number, got {raw!r}") from exc
    return default

# Plate planes. The paired brackets are spaced to accept off-the-shelf
# female-female M3 cross standoffs. The flange seats close to the case-top
# face (0.25 mm) so it bolts down flush rather than floating; its inner edge
# stays outboard of the case-top center ridge (proud only over Y 5-7). The
# bend position follows FLANGE_INNER_X parametrically.
CASE_SPAN_CENTERING_OFFSET_MM = _env_float(
    "TOM_V2_CASE_SPAN_CENTERING_OFFSET_MM",
    lc.CASE_SPAN_CENTERING_OFFSET_MM,
)
BASELINE_LINK_BRACKET_OVERALL_HEIGHT_MM = lc.TOP_PIVOT_Z_MM - lc.FOOT_BOTTOM_Z_MM
DEFAULT_LINK_BRACKET_OVERALL_HEIGHT_MM = 150.0
LINK_BRACKET_OVERALL_HEIGHT_MM = _env_float_any(
    (
        "TOM_V2_LINK_BRACKET_OVERALL_HEIGHT_MM",
        "TOM_V2_LINK_BRACKET_HEIGHT_MM",
    ),
    DEFAULT_LINK_BRACKET_OVERALL_HEIGHT_MM,
)
if LINK_BRACKET_OVERALL_HEIGHT_MM < 100.0:
    raise ValueError(
        "TOM_V2_LINK_BRACKET_OVERALL_HEIGHT_MM must be at least 100 mm "
        "to keep the top servo mount above the sloped web"
    )
HEIGHT_SCALE = LINK_BRACKET_OVERALL_HEIGHT_MM / BASELINE_LINK_BRACKET_OVERALL_HEIGHT_MM
TOP_PIVOT_Z_MM = lc.FOOT_BOTTOM_Z_MM + LINK_BRACKET_OVERALL_HEIGHT_MM
TOP_BODY_DOWN_Z_OFFSET_MM = TOP_PIVOT_Z_MM + lc.SERVO_SHAFT_LOCAL_X_MM
CASE_FLUSH_HOLE_Z_MM = TOP_BODY_DOWN_Z_OFFSET_MM - lc.SERVO_MOUNT_HOLE_LOCAL_X_MM[1]
CASE_OFFSET_HOLE_Z_MM = TOP_BODY_DOWN_Z_OFFSET_MM - lc.SERVO_TOP_MOUNT_HOLE_LOCAL_X_MM[1]
LINK_STANDOFF_LENGTH_MM = _env_float("TOM_V2_LINK_STANDOFF_LENGTH_MM", 35.0)
LEG_INNER_Y_MM = 0.5 * LINK_STANDOFF_LENGTH_MM
LEG_FACE_CLEARANCE_MM = LEG_INNER_Y_MM - lc.SERVO_HALF_WIDTH_MM
if LEG_FACE_CLEARANCE_MM < 1.5:
    raise ValueError(
        "TOM_V2_LINK_STANDOFF_LENGTH_MM leaves too little side clearance around the servo body"
    )
FLANGE_FACE_CLEARANCE_MM = 0.25
LEG_OUTER_Y_MM = LEG_INNER_Y_MM + lc.SHEET_THICKNESS_MM
CASE_TOP_FACE_X_MM = lc.SERVO_CASE_TOP_LOCAL_Y_MM + CASE_SPAN_CENTERING_OFFSET_MM
FLANGE_INNER_X_MM = CASE_TOP_FACE_X_MM + FLANGE_FACE_CLEARANCE_MM
FLANGE_OUTER_X_MM = FLANGE_INNER_X_MM + lc.SHEET_THICKNESS_MM
# Output-horn relief: concentric with the servo's output horn boss on the pitch
# axis, so the flange's curved cut is inline with the horn and symmetric.
# Keep this tunable because this gap is a tight tradeoff: reducing the relief
# radius gives the top flange screw more web, while increasing it gives the horn
# more radial clearance.
OUTPUT_HORN_RADIUS_MM = lc.SERVO_OUTPUT_HORN_BOSS_RADIUS_MM
DEFAULT_OUTPUT_HORN_RELIEF_RADIUS_MM = 11.0
OUTPUT_HORN_RELIEF_RADIUS_MM = _env_float(
    "TOM_V2_OUTPUT_HORN_RELIEF_RADIUS_MM",
    DEFAULT_OUTPUT_HORN_RELIEF_RADIUS_MM,
)

# Foot outline. The foot keeps a short Y=7.5 tab around each servo screw
# (left X 6.0-10.6, right X 30.4-35.0 - matching widths) and is set back to
# Y=9.6 everywhere between them, clearing both the cable hole and the
# raised center panel. The left tab is sized to match the right tab.
FOOT_X_MIN_MM = 6.0
FOOT_X_MAX_MM = 35.0
FOOT_EDGE_DEFAULT_Y_MM = 7.5
FOOT_EDGE_RAISED_Y_MM = 9.6
LEFT_TAB_RIGHT_X_MM = 10.6  # 4.6 mm tab (X 6.0-10.6) around the left screw at 8.3
RAISED_ZONE_X_MM = (LEFT_TAB_RIGHT_X_MM, 30.4)

# Leg profile (in the X-Z plane). The side-view layout is three constant-width
# bands from the bottom-servo mounting plane to the 180 mm top pitch axis:
# lower vertical section, centered sloped transition, and upper vertical
# section that carries the top-servo face features. A local 2t rectangular web
# ear gives the interrupted wrap bend room before the one-thickness flange turns
# onto the servo case face.
SECTION_WIDTH_MM = FOOT_X_MAX_MM - FOOT_X_MIN_MM
TOP_FLANGE_BEND_LEEWAY_MM = 2.0 * lc.SHEET_THICKNESS_MM
# Keep the top servo body vertically in line with the yoke-mounted servo body:
# both servos use the same local orientation, so matching the case transform's
# X translation makes their body centers share the same world X coordinate.
TOP_SERVO_ALIGNED_CASE_SPAN_CENTERING_OFFSET_MM = lc.HORN_SPAN_CENTERING_OFFSET_MM
FLANGE_WRAP_INNER_X_MM = (
    TOP_SERVO_ALIGNED_CASE_SPAN_CENTERING_OFFSET_MM + lc.SERVO_CASE_TOP_LOCAL_Y_MM
)
FLANGE_WRAP_OUTER_X_MM = FLANGE_WRAP_INNER_X_MM + lc.SHEET_THICKNESS_MM
TOP_FLANGE_EAR_X_MAX_MM = FLANGE_WRAP_INNER_X_MM
TOP_FLANGE_EAR_X_MIN_MM = TOP_FLANGE_EAR_X_MAX_MM - TOP_FLANGE_BEND_LEEWAY_MM
UPPER_X_MAX_MM = TOP_FLANGE_EAR_X_MIN_MM
UPPER_X_MIN_MM = UPPER_X_MAX_MM - SECTION_WIDTH_MM
TOP_SERVO_MATED_CASE_SPAN_CENTERING_OFFSET_MM = (
    FLANGE_WRAP_INNER_X_MM - lc.SERVO_CASE_TOP_LOCAL_Y_MM
)
TOP_SERVO_FACE_TO_FLANGE_X_OFFSET_MM = (
    TOP_SERVO_MATED_CASE_SPAN_CENTERING_OFFSET_MM - CASE_SPAN_CENTERING_OFFSET_MM
)
RIGHT_SLOPE_BOTTOM_Z_MM = lc.FOOT_BOTTOM_Z_MM + (60.0 - lc.FOOT_BOTTOM_Z_MM) * HEIGHT_SCALE
RIGHT_SLOPE_TOP_Z_MM = lc.FOOT_BOTTOM_Z_MM + (120.0 - lc.FOOT_BOTTOM_Z_MM) * HEIGHT_SCALE
SLOPE_SECTION_HEIGHT_MM = RIGHT_SLOPE_TOP_Z_MM - RIGHT_SLOPE_BOTTOM_Z_MM
SLOPE_RUN_X_MM = abs(FOOT_X_MAX_MM - UPPER_X_MAX_MM)
LOW_X_SLOPE_Z_SHIFT_DOWN_MM = SECTION_WIDTH_MM * (
    math.hypot(SLOPE_RUN_X_MM, SLOPE_SECTION_HEIGHT_MM) - SLOPE_SECTION_HEIGHT_MM
) / SLOPE_RUN_X_MM
LEFT_SLOPE_BOTTOM_Z_MM = RIGHT_SLOPE_BOTTOM_Z_MM - LOW_X_SLOPE_Z_SHIFT_DOWN_MM
LEFT_SLOPE_TOP_Z_MM = RIGHT_SLOPE_TOP_Z_MM - LOW_X_SLOPE_Z_SHIFT_DOWN_MM
SLOPE_DX_PER_Z_MM = (UPPER_X_MAX_MM - FOOT_X_MAX_MM) / SLOPE_SECTION_HEIGHT_MM
SLOPE_HIGH_X_INTERCEPT_MM = FOOT_X_MAX_MM - SLOPE_DX_PER_Z_MM * RIGHT_SLOPE_BOTTOM_Z_MM
SLOPE_LOW_X_INTERCEPT_MM = FOOT_X_MIN_MM - SLOPE_DX_PER_Z_MM * LEFT_SLOPE_BOTTOM_Z_MM
SLOPED_BAND_NORMAL_WIDTH_MM = abs(
    SLOPE_HIGH_X_INTERCEPT_MM - SLOPE_LOW_X_INTERCEPT_MM
) / math.hypot(1.0, SLOPE_DX_PER_Z_MM)
SLOPE_SECTION_CENTER_Z_MM = 0.25 * (
    LEFT_SLOPE_BOTTOM_Z_MM
    + RIGHT_SLOPE_BOTTOM_Z_MM
    + LEFT_SLOPE_TOP_Z_MM
    + RIGHT_SLOPE_TOP_Z_MM
)
# The local bend ear carries the wrap lead-in; the flange box itself remains
# one sheet thickness.
LEG_RUN_X_MM = (
    min(FOOT_X_MIN_MM, UPPER_X_MIN_MM),
    max(FOOT_X_MAX_MM, FLANGE_WRAP_OUTER_X_MM),
)
# Servo face #o1.1.1.1.f19 in link_assembly, expressed in STS3250 local X.
# Keeping this in local coordinates makes the bracket top track height changes.
TOP_SERVO_INLINE_FACE_LOCAL_X_MM = -20.038516
LEG_TOP_Z_MM = TOP_BODY_DOWN_Z_OFFSET_MM - TOP_SERVO_INLINE_FACE_LOCAL_X_MM
OUTPUT_HORN_TOP_EDGE_GAP_MM = TOP_PIVOT_Z_MM - LEG_TOP_Z_MM
FLANGE_BOTTOM_Z_MM = CASE_OFFSET_HOLE_Z_MM - 4.0
BASELINE_TRANSITION_CORNER_FILLET_RADIUS_MM = 24.0
DEFAULT_TRANSITION_CORNER_FILLET_RADIUS_MM = 0.5 * BASELINE_TRANSITION_CORNER_FILLET_RADIUS_MM
TRANSITION_CORNER_FILLET_RADIUS_MM = _env_float(
    "TOM_V2_TRANSITION_CORNER_FILLET_RADIUS_MM",
    DEFAULT_TRANSITION_CORNER_FILLET_RADIUS_MM,
)
FORMED_FLANGE_CORNER_FILLET_RADIUS_MM = 0.8
# Uniform flange inner edge. Place it at the case-top ridge clearance datum
# (ridge half-width 7.0 mm plus 0.5 mm tolerance clearance) so the wrap flange
# reaches closer to the servo face while leaving the horn relief, not the free
# edge, as the limiting boundary near the top screw hole.
FLANGE_EDGE_Y_MM = lc.CASE_OFFSET_RELIEF_HALF_WIDTH_MM
TOP_FLANGE_UPPER_HOLE_Z_MM = TOP_BODY_DOWN_Z_OFFSET_MM + 17.2
TOP_FLANGE_HOLE_TO_RELIEF_EDGE_GAP_MM = (
    math.hypot(lc.HOLE_SIDE_OFFSET_MM, TOP_PIVOT_Z_MM - TOP_FLANGE_UPPER_HOLE_Z_MM)
    - lc.SERVO_MOUNT_HOLE_RADIUS_MM
    - OUTPUT_HORN_RELIEF_RADIUS_MM
)

# Side-web lightening slots, paired per sketch in the lower, sloped, and
# upper bands. Slots cut through the sheet along Y and are kept away from
# the bend reliefs and servo screw holes.
SLOT_CUT_Y_OFFSET_MM = LEG_OUTER_Y_MM + CUT_EXTENSION_MM
SLOT_CUT_Y_SPAN_MM = lc.SHEET_THICKNESS_MM + 2.0 * CUT_EXTENSION_MM
SLOT_WIDTH_MM = 4.0
TOP_SLOT_WIDTH_MM = 4.0
BASELINE_LOWER_SLOT_LENGTH_MM = 38.0
BASELINE_MIDDLE_SLOT_LENGTH_MM = 38.0
BASELINE_TOP_SLOT_LENGTH_MM = 34.0
LOWER_SLOT_LENGTH_MM = BASELINE_LOWER_SLOT_LENGTH_MM * HEIGHT_SCALE
MIDDLE_SLOT_LENGTH_MM = BASELINE_MIDDLE_SLOT_LENGTH_MM * HEIGHT_SCALE
TOP_SLOT_LENGTH_MM = BASELINE_TOP_SLOT_LENGTH_MM * HEIGHT_SCALE
LOWER_SLOT_CENTER_Z_MM = 0.5 * (lc.FOOT_BOTTOM_Z_MM + RIGHT_SLOPE_BOTTOM_Z_MM)
MIDDLE_SLOT_CENTER_Z_MM = SLOPE_SECTION_CENTER_Z_MM
TOP_SLOT_CENTER_Z_MM = 0.5 * (RIGHT_SLOPE_TOP_Z_MM + LEG_TOP_Z_MM)
LOWER_SLOT_CENTER_X_MM = (14.0, 27.0)
MIDDLE_SLOT_CENTER_SPACING_X_MM = 13.0
MIDDLE_SLOT_PAIR_CENTER_X_MM = 0.5 * (
    (SLOPE_DX_PER_Z_MM * MIDDLE_SLOT_CENTER_Z_MM + SLOPE_LOW_X_INTERCEPT_MM)
    + (SLOPE_DX_PER_Z_MM * MIDDLE_SLOT_CENTER_Z_MM + SLOPE_HIGH_X_INTERCEPT_MM)
)
MIDDLE_SLOT_CENTER_X_MM = (
    MIDDLE_SLOT_PAIR_CENTER_X_MM - 0.5 * MIDDLE_SLOT_CENTER_SPACING_X_MM,
    MIDDLE_SLOT_PAIR_CENTER_X_MM + 0.5 * MIDDLE_SLOT_CENTER_SPACING_X_MM,
)
MIDDLE_SLOT_CENTER_XZ_MM = tuple(
    (slot_x, MIDDLE_SLOT_CENTER_Z_MM) for slot_x in MIDDLE_SLOT_CENTER_X_MM
)
MIDDLE_SLOT_CENTER_NORMAL_MM = tuple(
    (slot_x - SLOPE_DX_PER_Z_MM * MIDDLE_SLOT_CENTER_Z_MM - SLOPE_LOW_X_INTERCEPT_MM)
    / math.hypot(1.0, SLOPE_DX_PER_Z_MM)
    for slot_x in MIDDLE_SLOT_CENTER_X_MM
)
MIDDLE_SLOT_LOW_EDGE_MARGIN_MM = MIDDLE_SLOT_CENTER_NORMAL_MM[0] - 0.5 * SLOT_WIDTH_MM
MIDDLE_SLOT_HIGH_EDGE_MARGIN_MM = (
    SLOPED_BAND_NORMAL_WIDTH_MM - MIDDLE_SLOT_CENTER_NORMAL_MM[1] - 0.5 * SLOT_WIDTH_MM
)
MIDDLE_SLOT_ROTATION_DEG = math.degrees(
    math.atan2(
        0.5 * (LEFT_SLOPE_TOP_Z_MM + RIGHT_SLOPE_TOP_Z_MM)
        - 0.5 * (LEFT_SLOPE_BOTTOM_Z_MM + RIGHT_SLOPE_BOTTOM_Z_MM),
        UPPER_X_MAX_MM - FOOT_X_MAX_MM,
    )
)
VERTICAL_SLOT_ROTATION_DEG = 90.0
TOP_SLOT_PAIR_CENTER_X_MM = 0.5 * (UPPER_X_MIN_MM + UPPER_X_MAX_MM)
TOP_SLOT_CENTER_SPACING_X_MM = 13.0
TOP_SLOT_CENTER_X_MM = (
    TOP_SLOT_PAIR_CENTER_X_MM - 0.5 * TOP_SLOT_CENTER_SPACING_X_MM,
    TOP_SLOT_PAIR_CENTER_X_MM + 0.5 * TOP_SLOT_CENTER_SPACING_X_MM,
)
M3_STANDOFF_CLEARANCE_RADIUS_MM = 1.7
MIDDLE_SLOT_HALF_DX_MM = (
    math.cos(math.radians(MIDDLE_SLOT_ROTATION_DEG)) * 0.5 * MIDDLE_SLOT_LENGTH_MM
)
MIDDLE_SLOT_HALF_DZ_MM = (
    math.sin(math.radians(MIDDLE_SLOT_ROTATION_DEG)) * 0.5 * MIDDLE_SLOT_LENGTH_MM
)
LOWER_SLOT_TOP_Z_MM = LOWER_SLOT_CENTER_Z_MM + 0.5 * LOWER_SLOT_LENGTH_MM
MIDDLE_SLOT_LOWER_END_X_MM = tuple(
    slot_x - MIDDLE_SLOT_HALF_DX_MM for slot_x in MIDDLE_SLOT_CENTER_X_MM
)
MIDDLE_SLOT_LOWER_END_Z_MM = MIDDLE_SLOT_CENTER_Z_MM - MIDDLE_SLOT_HALF_DZ_MM
MIDDLE_SLOT_UPPER_END_X_MM = tuple(
    slot_x + MIDDLE_SLOT_HALF_DX_MM for slot_x in MIDDLE_SLOT_CENTER_X_MM
)
MIDDLE_SLOT_UPPER_END_Z_MM = MIDDLE_SLOT_CENTER_Z_MM + MIDDLE_SLOT_HALF_DZ_MM
TOP_SLOT_BOTTOM_Z_MM = TOP_SLOT_CENTER_Z_MM - 0.5 * TOP_SLOT_LENGTH_MM


def _side_profile_x_bounds_at_z(z_mm: float) -> tuple[float, float]:
    if z_mm < LEFT_SLOPE_BOTTOM_Z_MM:
        left_x = FOOT_X_MIN_MM
    elif z_mm <= LEFT_SLOPE_TOP_Z_MM:
        left_x = SLOPE_DX_PER_Z_MM * z_mm + SLOPE_LOW_X_INTERCEPT_MM
    else:
        left_x = UPPER_X_MIN_MM

    if z_mm < RIGHT_SLOPE_BOTTOM_Z_MM:
        right_x = FOOT_X_MAX_MM
    elif z_mm <= RIGHT_SLOPE_TOP_Z_MM:
        right_x = SLOPE_DX_PER_Z_MM * z_mm + SLOPE_HIGH_X_INTERCEPT_MM
    else:
        right_x = UPPER_X_MAX_MM

    return left_x, right_x


def _centered_pair_x_at_z(z_mm: float) -> tuple[float, float]:
    left_x, right_x = _side_profile_x_bounds_at_z(z_mm)
    width = right_x - left_x
    return left_x + 0.25 * width, left_x + 0.75 * width


LOWER_INTER_SLOT_STANDOFF_CENTER_Z_MM = 0.5 * (
    LOWER_SLOT_TOP_Z_MM + MIDDLE_SLOT_LOWER_END_Z_MM
)
LOWER_INTER_SLOT_STANDOFF_CENTER_X_MM = _centered_pair_x_at_z(
    LOWER_INTER_SLOT_STANDOFF_CENTER_Z_MM
)
UPPER_INTER_SLOT_STANDOFF_CENTER_Z_MM = 0.5 * (
    MIDDLE_SLOT_UPPER_END_Z_MM + TOP_SLOT_BOTTOM_Z_MM
)
UPPER_INTER_SLOT_STANDOFF_CENTER_X_MM = _centered_pair_x_at_z(
    UPPER_INTER_SLOT_STANDOFF_CENTER_Z_MM
)
STANDOFF_CENTER_XZ_MM = (
    ("lower_left", LOWER_INTER_SLOT_STANDOFF_CENTER_X_MM[0], LOWER_INTER_SLOT_STANDOFF_CENTER_Z_MM),
    ("lower_right", LOWER_INTER_SLOT_STANDOFF_CENTER_X_MM[1], LOWER_INTER_SLOT_STANDOFF_CENTER_Z_MM),
    ("upper_left", UPPER_INTER_SLOT_STANDOFF_CENTER_X_MM[0], UPPER_INTER_SLOT_STANDOFF_CENTER_Z_MM),
    ("upper_right", UPPER_INTER_SLOT_STANDOFF_CENTER_X_MM[1], UPPER_INTER_SLOT_STANDOFF_CENTER_Z_MM),
)


def top_servo_case_transform(
    case_span_centering_offset_mm: float = CASE_SPAN_CENTERING_OFFSET_MM,
) -> tuple[float, ...]:
    return (
        0.0, 1.0, 0.0, case_span_centering_offset_mm,
        0.0, 0.0, -1.0, 0.0,
        -1.0, 0.0, 0.0, TOP_BODY_DOWN_Z_OFFSET_MM,
        0.0, 0.0, 0.0, 1.0,
    )


def _verify_top_servo_case_holes(
    placed_servo: build123d.Shape,
    *,
    case_span_centering_offset_mm: float,
) -> None:
    lc._verify_holes(
        lc._planar_hole_centers(
            placed_servo,
            axis="x",
            plane_coordinate=lc.SERVO_CASE_BOTTOM_LOCAL_Y_MM + case_span_centering_offset_mm,
        ),
        expected=tuple(
            (side * lc.HOLE_SIDE_OFFSET_MM, CASE_FLUSH_HOLE_Z_MM)
            for side in (-1.0, 1.0)
        ),
        radius=lc.SERVO_MOUNT_HOLE_RADIUS_MM,
        label="case-bottom-face",
    )
    lc._verify_holes(
        lc._planar_hole_centers(
            placed_servo,
            axis="x",
            plane_coordinate=lc.SERVO_CASE_TOP_LOCAL_Y_MM + case_span_centering_offset_mm,
        ),
        expected=tuple(
            (side * lc.HOLE_SIDE_OFFSET_MM, CASE_OFFSET_HOLE_Z_MM)
            for side in (-1.0, 1.0)
        ),
        radius=lc.SERVO_MOUNT_HOLE_RADIUS_MM,
        label="case-top-face",
    )


def _placed_link_servos_case() -> tuple[build123d.Shape, build123d.Shape]:
    top = lc.place_servo(
        lc._load_servo_shape(lc.SERVO_STEP),
        top_servo_case_transform(TOP_SERVO_MATED_CASE_SPAN_CENTERING_OFFSET_MM),
    )
    bottom = lc.place_servo(
        lc._load_servo_shape(lc.SERVO_NO_REAR_HORN_STEP),
        lc.BOTTOM_SERVO_TRANSFORM,
    )
    _verify_top_servo_case_holes(
        top,
        case_span_centering_offset_mm=TOP_SERVO_MATED_CASE_SPAN_CENTERING_OFFSET_MM,
    )
    lc.verify_bottom_servo_mount_holes(bottom)
    return top, bottom


def _xz_unit(vector: tuple[float, float]) -> tuple[float, float]:
    length = math.hypot(vector[0], vector[1])
    if length <= 1e-9:
        raise ValueError("Cannot normalize a zero-length X-Z vector")
    return (vector[0] / length, vector[1] / length)


def _xz_add(
    left: tuple[float, float],
    right: tuple[float, float],
) -> tuple[float, float]:
    return (left[0] + right[0], left[1] + right[1])


def _xz_scale(vector: tuple[float, float], scale: float) -> tuple[float, float]:
    return (vector[0] * scale, vector[1] * scale)


def _profile_point(point: tuple[float, float]) -> tuple[float, float, float]:
    return (point[0], LEG_INNER_Y_MM, point[1])


def _rounded_profile_edges(
    points: list[tuple[float, float]],
    *,
    rounded_indices: set[int],
    radius: float,
) -> list[build123d.Edge]:
    if radius < 0.0:
        raise ValueError("TRANSITION_CORNER_FILLET_RADIUS_MM must be >= 0")

    corner_data: list[tuple[tuple[float, float], tuple[float, float], tuple[float, float] | None]] = []
    for index, corner in enumerate(points):
        if index not in rounded_indices or radius <= 0.0:
            corner_data.append((corner, corner, None))
            continue

        previous = points[index - 1]
        next_point = points[(index + 1) % len(points)]
        toward_previous = _xz_unit((previous[0] - corner[0], previous[1] - corner[1]))
        toward_next = _xz_unit((next_point[0] - corner[0], next_point[1] - corner[1]))
        dot = max(
            -1.0,
            min(1.0, toward_previous[0] * toward_next[0] + toward_previous[1] * toward_next[1]),
        )
        angle = math.acos(dot)
        tangent = radius / math.tan(0.5 * angle)
        previous_length = math.dist(previous, corner)
        next_length = math.dist(next_point, corner)
        if tangent >= min(previous_length, next_length):
            raise ValueError(
                "TRANSITION_CORNER_FILLET_RADIUS_MM is too large for the current "
                f"profile: radius={radius:.3f} mm at point {corner}"
            )

        start = _xz_add(corner, _xz_scale(toward_previous, tangent))
        end = _xz_add(corner, _xz_scale(toward_next, tangent))
        bisector = _xz_unit(_xz_add(toward_previous, toward_next))
        center_distance = radius / math.sin(0.5 * angle)
        center = _xz_add(corner, _xz_scale(bisector, center_distance))
        start_radius = (start[0] - center[0], start[1] - center[1])
        end_radius = (end[0] - center[0], end[1] - center[1])
        mid_radius = _xz_unit(_xz_add(start_radius, end_radius))
        midpoint = _xz_add(center, _xz_scale(mid_radius, radius))
        corner_data.append((start, end, midpoint))

    edges: list[build123d.Edge] = []
    for index, (_start, end, _midpoint) in enumerate(corner_data):
        next_start, next_end, next_midpoint = corner_data[(index + 1) % len(corner_data)]
        if math.dist(end, next_start) > 1e-6:
            edges.append(build123d.Edge.make_line(_profile_point(end), _profile_point(next_start)))
        if next_midpoint is not None:
            edges.append(
                build123d.Edge.make_three_point_arc(
                    _profile_point(next_start),
                    _profile_point(next_midpoint),
                    _profile_point(next_end),
                )
            )
    return edges


def _leg_profile() -> build123d.Face:
    points = [
        (FOOT_X_MIN_MM, lc.FOOT_BOTTOM_Z_MM),
        (FOOT_X_MAX_MM, lc.FOOT_BOTTOM_Z_MM),
        (FOOT_X_MAX_MM, RIGHT_SLOPE_BOTTOM_Z_MM),
        (UPPER_X_MAX_MM, RIGHT_SLOPE_TOP_Z_MM),
        (UPPER_X_MAX_MM, LEG_TOP_Z_MM),
        (UPPER_X_MIN_MM, LEG_TOP_Z_MM),
        (UPPER_X_MIN_MM, LEFT_SLOPE_TOP_Z_MM),
        (FOOT_X_MIN_MM, LEFT_SLOPE_BOTTOM_Z_MM),
    ]
    profile_edges = _rounded_profile_edges(
        points,
        rounded_indices={2, 3, 6, 7},
        radius=TRANSITION_CORNER_FILLET_RADIUS_MM,
    )
    wires = list(build123d.Wire.combine(profile_edges))
    if len(wires) != 1:
        raise RuntimeError(f"Leg profile produced {len(wires)} wires")
    return build123d.Face(wires[0])


def _slot_cut(
    *,
    x: float,
    z: float,
    length: float,
    width: float,
    rotation: float,
) -> build123d.Shape:
    with build123d.BuildPart() as slot:
        with build123d.BuildSketch(build123d.Plane.XZ):
            with build123d.Locations((x, z)):
                build123d.SlotOverall(width=length, height=width, rotation=rotation)
        build123d.extrude(amount=SLOT_CUT_Y_SPAN_MM)

    return slot.part.moved(build123d.Location((0.0, SLOT_CUT_Y_OFFSET_MM, 0.0)))


def _slot_cuts() -> list[build123d.Shape]:
    slots: list[build123d.Shape] = []
    for slot_x in LOWER_SLOT_CENTER_X_MM:
        slots.append(
            _slot_cut(
                x=slot_x,
                z=LOWER_SLOT_CENTER_Z_MM,
                length=LOWER_SLOT_LENGTH_MM,
                width=SLOT_WIDTH_MM,
                rotation=VERTICAL_SLOT_ROTATION_DEG,
            )
        )
    for slot_x, slot_z in MIDDLE_SLOT_CENTER_XZ_MM:
        slots.append(
            _slot_cut(
                x=slot_x,
                z=slot_z,
                length=MIDDLE_SLOT_LENGTH_MM,
                width=SLOT_WIDTH_MM,
                rotation=MIDDLE_SLOT_ROTATION_DEG,
            )
        )
    for slot_x in TOP_SLOT_CENTER_X_MM:
        slots.append(
            _slot_cut(
                x=slot_x,
                z=TOP_SLOT_CENTER_Z_MM,
                length=TOP_SLOT_LENGTH_MM,
                width=TOP_SLOT_WIDTH_MM,
                rotation=VERTICAL_SLOT_ROTATION_DEG,
            )
        )
    return slots


def _transition_corner_edges(bracket: build123d.Shape) -> list[build123d.Edge]:
    corner_points = (
        (FOOT_X_MAX_MM, RIGHT_SLOPE_BOTTOM_Z_MM),
        (UPPER_X_MAX_MM, RIGHT_SLOPE_TOP_Z_MM),
        (UPPER_X_MIN_MM, LEFT_SLOPE_TOP_Z_MM),
        (FOOT_X_MIN_MM, LEFT_SLOPE_BOTTOM_Z_MM),
    )
    return list(
        bracket.edges().filter_by(build123d.Axis.Y).filter_by(
            lambda e: any(
                abs(e.center().X - x) < 0.05
                and abs(e.center().Z - z) < 0.05
                and abs(e.length - lc.SHEET_THICKNESS_MM) < 0.05
                for x, z in corner_points
            )
        )
    )


def build_bracket() -> build123d.Shape:
    leg = build123d.Solid.extrude(
        _leg_profile(), build123d.Vector(0.0, lc.SHEET_THICKNESS_MM, 0.0)
    )
    foot = lc.make_box(
        x_min=FOOT_X_MIN_MM,
        x_max=FOOT_X_MAX_MM,
        y_min=FOOT_EDGE_DEFAULT_Y_MM,
        y_max=LEG_OUTER_Y_MM,
        z_min=lc.FOOT_BOTTOM_Z_MM,
        z_max=lc.FOOT_TOP_Z_MM,
    )
    bend_ear = lc.make_box(
        x_min=TOP_FLANGE_EAR_X_MIN_MM,
        x_max=TOP_FLANGE_EAR_X_MAX_MM,
        y_min=LEG_INNER_Y_MM,
        y_max=LEG_OUTER_Y_MM,
        z_min=FLANGE_BOTTOM_Z_MM,
        z_max=LEG_TOP_Z_MM,
    )
    flange = lc.make_box(
        x_min=FLANGE_WRAP_INNER_X_MM,
        x_max=FLANGE_WRAP_OUTER_X_MM,
        y_min=FLANGE_EDGE_Y_MM,
        y_max=LEG_OUTER_Y_MM,
        z_min=FLANGE_BOTTOM_Z_MM,
        z_max=LEG_TOP_Z_MM,
    )
    bracket: build123d.Shape = leg.fuse(foot).fuse(bend_ear).fuse(flange)

    # Raised-panel clearance: the only setback in the otherwise straight,
    # flush foot inner edge. The servo's raised center panel protrudes to
    # Z=1.9 over this X-span, so the foot edge steps out to clear it. The
    # bay is a recess, so the foot covers it flush with no setback.
    bracket = bracket.cut(
        lc.make_box(
            x_min=RAISED_ZONE_X_MM[0],
            x_max=RAISED_ZONE_X_MM[1],
            y_min=FOOT_EDGE_DEFAULT_Y_MM - CUT_EXTENSION_MM,
            y_max=FOOT_EDGE_RAISED_Y_MM,
            z_min=lc.FOOT_BOTTOM_Z_MM - CUT_EXTENSION_MM,
            z_max=lc.FOOT_TOP_Z_MM + CUT_EXTENSION_MM,
        )
    )
    for slot in _slot_cuts():
        bracket = bracket.cut(slot)

    # M3 cross-standoff holes. These bridge the left/right plates with
    # 35 mm female-female standoffs, turning the pair into a ladder frame.
    for _label, standoff_x, standoff_z in STANDOFF_CENTER_XZ_MM:
        bracket = bracket.cut(
            lc.make_y_cylinder(
                x=standoff_x,
                z=standoff_z,
                radius=M3_STANDOFF_CLEARANCE_RADIUS_MM,
                y_min=LEG_INNER_Y_MM - CUT_EXTENSION_MM,
                y_max=LEG_OUTER_Y_MM + CUT_EXTENSION_MM,
            )
        )

    # Foot servo holes.
    for hole_x in (lc.HOLE_NEAR_OFFSET_MM, lc.HOLE_FAR_OFFSET_MM):
        bracket = bracket.cut(
            lc.make_z_cylinder(
                x=hole_x,
                y=lc.HOLE_SIDE_OFFSET_MM,
                radius=lc.SERVO_MOUNT_HOLE_RADIUS_MM,
                z_min=lc.FOOT_BOTTOM_Z_MM - CUT_EXTENSION_MM,
                z_max=lc.FOOT_TOP_Z_MM + CUT_EXTENSION_MM,
            )
        )
    # Horn clearance: the output horn boss sits on the pitch axis and reaches
    # toward the wrap flange. The relief arc stays concentric with the horn so
    # the remaining screw web can be measured directly from that axis.
    bracket = bracket.cut(
        lc.make_x_cylinder(
            y=0.0,
            z=TOP_PIVOT_Z_MM,
            radius=OUTPUT_HORN_RELIEF_RADIUS_MM,
            x_min=FLANGE_WRAP_INNER_X_MM - CUT_EXTENSION_MM,
            x_max=FLANGE_WRAP_OUTER_X_MM + CUT_EXTENSION_MM,
        )
    )
    # Flange servo holes (the case-top +Y pair).
    for hole_z in (CASE_OFFSET_HOLE_Z_MM, TOP_FLANGE_UPPER_HOLE_Z_MM):
        bracket = bracket.cut(
            lc.make_x_cylinder(
                y=lc.HOLE_SIDE_OFFSET_MM,
                z=hole_z,
                radius=lc.SERVO_MOUNT_HOLE_RADIUS_MM,
                x_min=FLANGE_WRAP_INNER_X_MM - CUT_EXTENSION_MM,
                x_max=FLANGE_WRAP_OUTER_X_MM + CUT_EXTENSION_MM,
            )
        )

    # Round the foot-tab inside corners (Z-direction edges at Y=7.5 where
    # the tabs meet the setback) and the leg top corner.
    foot_tab_x = (FOOT_X_MIN_MM, LEFT_TAB_RIGHT_X_MM, RAISED_ZONE_X_MM[1], FOOT_X_MAX_MM)
    leg_x = LEG_RUN_X_MM[0]
    foot_tab_corners = bracket.edges().filter_by(build123d.Axis.Z).filter_by(
        lambda e: abs(e.center().Y - FOOT_EDGE_DEFAULT_Y_MM) < 0.05
        and any(abs(e.center().X - x) < 0.05 for x in foot_tab_x)
        and abs(e.length - lc.SHEET_THICKNESS_MM) < 0.05
    )
    bracket = bracket.fillet(FORMED_FLANGE_CORNER_FILLET_RADIUS_MM, foot_tab_corners)

    wrap_flange_bottom_free_edges = bracket.edges().filter_by(build123d.Axis.X).filter_by(
        lambda e: abs(e.center().Y - FLANGE_EDGE_Y_MM) < 0.05
        and abs(e.center().Z - FLANGE_BOTTOM_Z_MM) < 0.05
        and abs(e.length - lc.SHEET_THICKNESS_MM) < 0.05
    )
    if len(wrap_flange_bottom_free_edges) != 1:
        raise RuntimeError(
            "Expected one wrap flange bottom free corner to fillet, "
            f"found {len(wrap_flange_bottom_free_edges)}"
        )
    bracket = bracket.fillet(
        FORMED_FLANGE_CORNER_FILLET_RADIUS_MM,
        wrap_flange_bottom_free_edges,
    )

    leg_top_corners = bracket.edges().filter_by(build123d.Axis.Y).filter_by(
        lambda e: abs(e.center().X - leg_x) < 0.05
        and abs(e.center().Z - LEG_TOP_Z_MM) < 0.05
        and abs(e.length - lc.SHEET_THICKNESS_MM) < 0.05
    )
    bracket = bracket.fillet(1.5, leg_top_corners)

    return bracket


def build_step() -> build123d.Shape:
    bracket = build_bracket()

    solids = bracket.solids()
    if len(solids) != 1:
        raise RuntimeError(f"Expected one connected plate solid, found {len(solids)}")

    top_servo, bottom_servo = _placed_link_servos_case()
    top_volume = lc.verify_no_interference(bracket, top_servo, label="the top servo")
    bottom_volume = lc.verify_no_interference(bracket, bottom_servo, label="the bottom servo")

    bracket.label = PART_NAME
    bracket.color = lc.BRACKET_COLOR

    bb = bracket.bounding_box()
    foot_flange = LEG_OUTER_Y_MM - FOOT_EDGE_DEFAULT_Y_MM
    foot_flange_raised = LEG_OUTER_Y_MM - FOOT_EDGE_RAISED_Y_MM
    wrap_flange = LEG_OUTER_Y_MM - FLANGE_EDGE_Y_MM
    # Worst-case wrap-flange depth at the horn-relief intrusion (top of flange).
    horn_intrusion_y = (
        OUTPUT_HORN_RELIEF_RADIUS_MM**2 - (TOP_PIVOT_Z_MM - LEG_TOP_Z_MM) ** 2
    ) ** 0.5
    wrap_flange_at_horn = LEG_OUTER_Y_MM - horn_intrusion_y
    hole_to_bend = LEG_OUTER_Y_MM - lc.HOLE_SIDE_OFFSET_MM
    half_die = lc.SCS_HALF_DIE_WIDTH_MM
    min_flange = lc.SCS_MIN_FLANGE_AFTER_BEND_MM
    flange_check_status = (
        "PASS"
        if min(foot_flange, foot_flange_raised, wrap_flange, wrap_flange_at_horn)
        + 1e-6
        >= min_flange
        else "CHECK"
    )
    hole_to_bend_status = "PASS" if hole_to_bend + 1e-6 >= half_die else "CHECK"
    print(
        "Wrap plate envelope "
        f"X={bb.size.X:.3f} mm, Y={bb.size.Y:.3f} mm, Z={bb.size.Z:.3f} mm"
    )
    print(
        f"Height parameter: overall={LINK_BRACKET_OVERALL_HEIGHT_MM:.3f} mm "
        f"(scale {HEIGHT_SCALE:.4f} from the 180 mm baseline)"
    )
    print(
        "Top case centering offset "
        f"{TOP_SERVO_MATED_CASE_SPAN_CENTERING_OFFSET_MM:.3f} mm "
        f"(face-to-flange shift {TOP_SERVO_FACE_TO_FLANGE_X_OFFSET_MM:.3f} mm); "
        f"case-top face X={FLANGE_WRAP_INNER_X_MM:.3f} mm"
    )
    print(
        f"Side profile bands: lower to low/high-X Z="
        f"{LEFT_SLOPE_BOTTOM_Z_MM:.1f}/{RIGHT_SLOPE_BOTTOM_Z_MM:.1f} mm, "
        f"steeper slope to low/high-X Z="
        f"{LEFT_SLOPE_TOP_Z_MM:.1f}/{RIGHT_SLOPE_TOP_Z_MM:.1f} mm, "
        f"upper to axis Z={TOP_PIVOT_Z_MM:.1f} mm; "
        f"top servo pitch axis Z={TOP_PIVOT_Z_MM:.1f} mm"
    )
    print(
        f"Web width check: lower/upper bands {SECTION_WIDTH_MM:.3f} mm, "
        f"local flange bend leeway {TOP_FLANGE_BEND_LEEWAY_MM:.3f} mm, "
        f"sloped band normal width {SLOPED_BAND_NORMAL_WIDTH_MM:.3f} mm, "
        f"low-X transition shift {LOW_X_SLOPE_Z_SHIFT_DOWN_MM:.3f} mm down"
    )
    print(
        "Transition corner radius: "
        + (
            "disabled"
            if TRANSITION_CORNER_FILLET_RADIUS_MM == 0.0
            else f"{TRANSITION_CORNER_FILLET_RADIUS_MM:.1f} mm"
        )
    )
    print(
        "Slots: 2x lower vertical, 2x sloped transition, 2x upper vertical "
        f"(lengths {LOWER_SLOT_LENGTH_MM:.1f}/{MIDDLE_SLOT_LENGTH_MM:.1f}/"
        f"{TOP_SLOT_LENGTH_MM:.1f} mm, widths {SLOT_WIDTH_MM:.1f}/{TOP_SLOT_WIDTH_MM:.1f} mm)"
    )
    print(
        "Cross standoffs: "
        f"{len(STANDOFF_CENTER_XZ_MM)}x M3 female-female, length={LINK_STANDOFF_LENGTH_MM:.3f} mm, "
        f"inner bracket gap={2.0 * LEG_INNER_Y_MM:.3f} mm, "
        f"clearance per servo side={LEG_FACE_CLEARANCE_MM:.3f} mm"
    )
    print(
        f"Sloped slot margins: low edge {MIDDLE_SLOT_LOW_EDGE_MARGIN_MM:.3f} mm, "
        f"high edge {MIDDLE_SLOT_HIGH_EDGE_MARGIN_MM:.3f} mm"
    )
    print(
        "Sheet setup "
        f"material=5052-H32 (ALU-063), thickness={lc.SHEET_THICKNESS_MM:.4f} mm, "
        "bends=2 (continuous foot bend, full-length wrap bend)"
    )
    print(
        "SendCutSend flange checks (min after-bend "
        f"{min_flange:.3f} mm): "
        f"foot default {foot_flange:.2f} mm, "
        f"foot raised-zone setback {foot_flange_raised:.2f} mm, "
        f"wrap main {wrap_flange:.2f} mm, "
        f"wrap at horn-relief Z={LEG_TOP_Z_MM:.1f} {wrap_flange_at_horn:.2f} mm "
        f"-- {flange_check_status}"
    )
    print(
        f"SendCutSend hole-to-bend checks (half die {half_die:.3f} mm): "
        f"foot screws {hole_to_bend:.2f} mm, wrap-flange screws {hole_to_bend:.2f} mm "
        f"-- {hole_to_bend_status}"
    )
    print(
        "Top flange hole-to-horn-relief web: "
        f"{TOP_FLANGE_HOLE_TO_RELIEF_EDGE_GAP_MM:.3f} mm "
        f"(relief radius {OUTPUT_HORN_RELIEF_RADIUS_MM:.3f} mm)"
    )
    print(
        f"Clearances: leg gap {LEG_FACE_CLEARANCE_MM:.1f} mm off the servo side face; "
        f"bend-ear gives {TOP_FLANGE_BEND_LEEWAY_MM:.3f} mm of flat lead-in; "
        "flange inner face seats on the aligned top servo case face; "
        f"flange inner edge at Y={FLANGE_EDGE_Y_MM} clears the case-top ridge"
    )
    print(f"Top servo interference volume (mm^3): {top_volume:.6f}")
    print(f"Bottom servo interference volume (mm^3): {bottom_volume:.6f}")
    return bracket


def _polyline_points_from_ring(ring) -> list[tuple[float, float]]:
    points = [(float(x), float(y)) for x, y in ring.coords]
    if points and points[0] == points[-1]:
        points.pop()
    return points


def _add_closed_polyline(msp, points: list[tuple[float, float]], *, layer: str) -> None:
    if len(points) < 3:
        return
    msp.add_lwpolyline(points, close=True, dxfattribs={"layer": layer})


def _axis_value(vector: build123d.Vector, axis: str) -> float:
    return {"x": vector.X, "y": vector.Y, "z": vector.Z}[axis]


def _select_planar_face(
    shape: build123d.Shape,
    *,
    normal_axis: str,
    normal_sign: float,
    coordinate_axis: str,
    coordinate: float,
) -> build123d.Face:
    candidates = []
    for face in shape.faces():
        if face.geom_type != build123d.GeomType.PLANE:
            continue
        normal = face.normal_at()
        center = face.center()
        if abs(_axis_value(normal, normal_axis) - normal_sign) > 0.01:
            continue
        if abs(_axis_value(center, coordinate_axis) - coordinate) > 0.05:
            continue
        candidates.append(face)
    if not candidates:
        raise RuntimeError(
            "Could not find topology face for DXF unfolding: "
            f"normal {normal_sign:+.0f}{normal_axis}, {coordinate_axis}={coordinate:.3f}"
        )
    return max(candidates, key=lambda face: face.area)


def _project_wire_points(
    wire: build123d.Wire,
    project,
    *,
    max_segment_mm: float = 0.25,
) -> list[tuple[float, float]]:
    sample_count = max(16, int(math.ceil(wire.length / max_segment_mm)))
    points: list[tuple[float, float]] = []
    for index in range(sample_count):
        point = project(wire.position_at(index / sample_count))
        if not points or math.dist(points[-1], point) > 1e-6:
            points.append(point)
    if len(points) >= 2 and math.dist(points[0], points[-1]) < 1e-6:
        points.pop()
    return points


def _project_face_polygon(face: build123d.Face, project):
    from shapely.geometry import Polygon

    outer = _project_wire_points(face.outer_wire(), project)
    holes = [
        _project_wire_points(wire, project)
        for wire in face.inner_wires()
        if wire.length > 1e-6
    ]
    polygon = Polygon(outer, holes)
    if not polygon.is_valid:
        polygon = polygon.buffer(0)
    if polygon.is_empty:
        raise RuntimeError("Projected STEP topology face produced an empty flat-pattern polygon")
    return polygon


def _validate_sendcutsend_bend_rule() -> None:
    expected_bend_allowance = (
        2.0 * lc.SCS_OUTSIDE_SETBACK_90_MM
    ) - lc.SCS_BEND_DEDUCTION_90_MM
    if abs(expected_bend_allowance - lc.SCS_BEND_ALLOWANCE_90_MM) > 0.01:
        raise RuntimeError(
            "Inconsistent SendCutSend bend rule constants: "
            f"outside_setback={lc.SCS_OUTSIDE_SETBACK_90_MM:.3f} mm, "
            f"bend_deduction={lc.SCS_BEND_DEDUCTION_90_MM:.3f} mm, "
            f"bend_allowance={lc.SCS_BEND_ALLOWANCE_90_MM:.3f} mm, "
            f"expected={expected_bend_allowance:.3f} mm"
        )


def _build_flat_pattern() -> FlatPattern:
    _validate_sendcutsend_bend_rule()

    outside_setback = lc.SCS_OUTSIDE_SETBACK_90_MM
    bend_allowance = lc.SCS_BEND_ALLOWANCE_90_MM
    panel_join_shift = bend_allowance - outside_setback
    return FlatPattern(
        outside_setback_mm=outside_setback,
        bend_allowance_mm=bend_allowance,
        bend_deduction_mm=lc.SCS_BEND_DEDUCTION_90_MM,
        panel_join_shift_mm=panel_join_shift,
        foot_bend_line_y_mm=lc.FOOT_BOTTOM_Z_MM + (0.5 * bend_allowance),
        wrap_bend_line_x_mm=(
            FLANGE_WRAP_INNER_X_MM + panel_join_shift + (0.5 * bend_allowance)
        ),
    )


def _flat_pattern_geometry_from_step_topology():
    from shapely.ops import unary_union

    flat_pattern = _build_flat_pattern()
    outside_setback = flat_pattern.outside_setback_mm
    panel_join_shift = flat_pattern.panel_join_shift_mm

    bracket = build_bracket()
    leg_face = _select_planar_face(
        bracket,
        normal_axis="y",
        normal_sign=1.0,
        coordinate_axis="y",
        coordinate=LEG_OUTER_Y_MM,
    )
    foot_face = _select_planar_face(
        bracket,
        normal_axis="z",
        normal_sign=-1.0,
        coordinate_axis="z",
        coordinate=lc.FOOT_BOTTOM_Z_MM,
    )
    wrap_flange_face = _select_planar_face(
        bracket,
        normal_axis="x",
        normal_sign=1.0,
        coordinate_axis="x",
        coordinate=FLANGE_WRAP_OUTER_X_MM,
    )

    def project_leg(point: build123d.Vector) -> tuple[float, float]:
        flat_x = point.X
        flat_z = point.Z
        if abs(point.X - FLANGE_WRAP_INNER_X_MM) <= 1e-3:
            flat_x = FLANGE_WRAP_INNER_X_MM + panel_join_shift
        if abs(point.Z - lc.FOOT_BOTTOM_Z_MM) <= 1e-3:
            flat_z = lc.FOOT_BOTTOM_Z_MM
        elif point.Z > lc.FOOT_BOTTOM_Z_MM:
            flat_z = point.Z + panel_join_shift
        return (flat_x, flat_z)

    def project_foot(point: build123d.Vector) -> tuple[float, float]:
        if abs(point.Y - LEG_OUTER_Y_MM) <= 1e-3:
            flat_y = lc.FOOT_BOTTOM_Z_MM
        else:
            flat_y = point.Y - LEG_OUTER_Y_MM + outside_setback
        return (point.X, flat_y)

    def project_wrap_flange(point: build123d.Vector) -> tuple[float, float]:
        if abs(point.Y - LEG_OUTER_Y_MM) <= 1e-3:
            flat_x = FLANGE_WRAP_INNER_X_MM + panel_join_shift
        else:
            flat_x = (
                FLANGE_WRAP_INNER_X_MM
                + panel_join_shift
                + (LEG_OUTER_Y_MM - point.Y)
                - outside_setback
                + flat_pattern.bend_allowance_mm
            )
        flat_z = point.Z + panel_join_shift if point.Z > lc.FOOT_BOTTOM_Z_MM else point.Z
        return (flat_x, flat_z)

    leg = _project_face_polygon(leg_face, project_leg)
    foot = _project_face_polygon(
        foot_face,
        project_foot,
    )
    wrap_flange = _project_face_polygon(
        wrap_flange_face,
        project_wrap_flange,
    )
    _validate_projected_flange_depths(foot, wrap_flange, flat_pattern)

    flat_geometry = unary_union([leg, foot, wrap_flange]).buffer(0)
    if not flat_geometry.is_valid:
        flat_geometry = flat_geometry.buffer(0)
    # Keep the linework compact while preserving the sampled STEP curves within
    # a few microns. The samples still originate from the formed solid topology.
    flat_geometry = flat_geometry.simplify(0.002, preserve_topology=True)

    from shapely.geometry import LineString

    foot_bounds = foot_face.bounding_box()
    wrap_bounds = wrap_flange_face.bounding_box()
    bend_lines = (
        LineString(
            [
                (foot_bounds.min.X, lc.FOOT_BOTTOM_Z_MM),
                (foot_bounds.max.X, lc.FOOT_BOTTOM_Z_MM),
            ]
        ),
        LineString(
            [
                (
                    flat_pattern.wrap_bend_line_x_mm,
                    wrap_bounds.min.Z + panel_join_shift,
                ),
                (
                    flat_pattern.wrap_bend_line_x_mm,
                    wrap_bounds.max.Z + panel_join_shift,
                ),
            ]
        ),
    )
    bend_lines = (
        LineString(
            [
                (foot_bounds.min.X, flat_pattern.foot_bend_line_y_mm),
                (foot_bounds.max.X, flat_pattern.foot_bend_line_y_mm),
            ]
        ),
        bend_lines[1],
    )
    return flat_geometry, bend_lines, flat_pattern


def _validate_projected_flange_depths(
    foot,
    wrap_flange,
    flat_pattern: FlatPattern,
) -> None:
    foot_formed_depth = LEG_OUTER_Y_MM - FOOT_EDGE_DEFAULT_Y_MM
    wrap_formed_depth = LEG_OUTER_Y_MM - FLANGE_EDGE_Y_MM
    foot_expected = (
        foot_formed_depth
        - flat_pattern.outside_setback_mm
        + (0.5 * flat_pattern.bend_allowance_mm)
    )
    wrap_expected = (
        wrap_formed_depth
        - flat_pattern.outside_setback_mm
        + (0.5 * flat_pattern.bend_allowance_mm)
    )
    foot_actual = flat_pattern.foot_bend_line_y_mm - foot.bounds[1]
    wrap_actual = wrap_flange.bounds[2] - flat_pattern.wrap_bend_line_x_mm

    checks = (
        ("bottom flange", foot_actual, foot_expected),
        ("top wrap flange", wrap_actual, wrap_expected),
    )
    for name, actual, expected in checks:
        if abs(actual - expected) > 0.01:
            raise RuntimeError(
                f"Projected {name} DXF depth is inconsistent with bend math: "
                f"actual={actual:.3f} mm, expected={expected:.3f} mm"
            )

    if abs(foot_formed_depth - wrap_formed_depth) <= 0.01 and abs(foot_actual - wrap_actual) > 0.01:
        raise RuntimeError(
            "Projected link bracket flange depths are not equal despite equal formed depths: "
            f"bottom={foot_actual:.3f} mm, top={wrap_actual:.3f} mm"
        )


def _add_flat_pattern_entities(msp, flat_geometry, bend_lines) -> None:
    polygons = [flat_geometry] if flat_geometry.geom_type == "Polygon" else list(flat_geometry.geoms)
    for polygon in polygons:
        dxf_topology.add_ring(msp, polygon.exterior, layer="CUT")
        for interior in polygon.interiors:
            dxf_topology.add_ring(msp, interior, layer="CUT", prefer_circle=True)

    for line in bend_lines:
        coords = list(line.coords)
        msp.add_line(
            coords[0],
            coords[-1],
            dxfattribs={"layer": "BEND", "linetype": "DASHED"},
        )


def build_dxf(*, part_name: str = PART_NAME):
    import ezdxf
    from ezdxf.units import MM as DXF_UNIT_MM

    doc = ezdxf.new("R2010", setup=True)
    doc.units = DXF_UNIT_MM
    if "CUT" not in doc.layers:
        doc.layers.add("CUT")
    if "BEND" not in doc.layers:
        doc.layers.add("BEND", linetype="DASHED")
    flat_geometry, bend_lines, flat_pattern = _flat_pattern_geometry_from_step_topology()
    _add_flat_pattern_entities(doc.modelspace(), flat_geometry, bend_lines)

    min_x, min_y, max_x, max_y = flat_geometry.bounds
    print(
        f"{part_name} flat DXF "
        f"overall_height={LINK_BRACKET_OVERALL_HEIGHT_MM:.3f} mm, "
        f"bounds=({max_x - min_x:.3f} x {max_y - min_y:.3f}) mm, "
        f"topology_unfold_faces=3, bend_deduction_90={flat_pattern.bend_deduction_mm:.3f} mm, "
        f"bend_allowance_90={flat_pattern.bend_allowance_mm:.3f} mm, "
        f"bend_lines={len(bend_lines)}, layers=CUT/BEND"
    )
    return doc


def gen_step() -> dict[str, object]:
    return {
        "shape": build_step(),
    }


if __name__ == "__main__":
    gen_step()
