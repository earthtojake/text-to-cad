#!/usr/bin/env python3
"""
Generate a bent base clamp that wraps under the base servo footprint.

The upper plate stays in the servo base frame, a side wall rises from the
positive-x side, and a lower return closes the U so the part can clamp to a
desk or fixture from below.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import os
import sys
from pathlib import Path

from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet

TOM_DIR = Path(__file__).resolve().parents[2]
V2_DIR = Path(__file__).resolve().parents[2]
PARTS_DIR = V2_DIR / "parts"
REPO_ROOT = TOM_DIR
_CACHE_HOME = V2_DIR / ".cache"
_CACHE_HOME.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("XDG_CACHE_HOME", str(_CACHE_HOME))
os.environ.setdefault("EZDXF_CACHE_HOME", str(_CACHE_HOME / "ezdxf"))

import build123d
import ezdxf
from ezdxf.units import MM as DXF_UNIT_MM

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(PARTS_DIR) not in sys.path:
    sys.path.insert(0, str(PARTS_DIR))

from robot_common.materials import GRAY_ALUMINUM_COLOR
from cadgen import flatten as dxf_topology


DISPLAY_NAME = "Base Clamp"
INCLUDE_BOTTOM_SURFACE_MOUNT_FEATURES = False
INCLUDE_RETURN_SURFACE_MOUNT_FEATURES = True
PLATE_THICKNESS_MM = 25.4 * 0.125
STANDARD_DESK_CLAMP_CLEARANCE_MM = 65.0
STANDARD_DESK_CLAMP_CONTACT_WIDTH_MM = 33.5
SADDLE_FOOTPRINT_X_BUFFER_MM = 2.0
SIDE_WALL_THICKNESS_MM = PLATE_THICKNESS_MM
BOOLEAN_OVERLAP_MM = 0.05
CUT_EXTENSION_MM = 0.5
CORNER_RADIUS_MM = 3.0
RETURN_FACE_LENGTH_RATIO = 2.0 / 3.0
M3_CLEARANCE_RADIUS_MM = 1.6
BASE_CENTER_HORN_FACE_RADIUS_MM = 2.8
BASE_CENTER_HORN_FACE_CLEARANCE_BUFFER_MM = 0.25
BASE_CENTER_HORN_FACE_CLEARANCE_RADIUS_MM = (
    BASE_CENTER_HORN_FACE_RADIUS_MM + BASE_CENTER_HORN_FACE_CLEARANCE_BUFFER_MM
)
M8_CLEARANCE_DIAMETER_MM = 8.5
M8_CLEARANCE_RADIUS_MM = 0.5 * M8_CLEARANCE_DIAMETER_MM
SENDCUTSEND_EFFECTIVE_BEND_RADIUS_MM = 25.4 * 0.125
SENDCUTSEND_K_FACTOR = 0.44
SENDCUTSEND_BEND_DEDUCTION_90_MM = 25.4 * 0.216
SENDCUTSEND_HALF_DIE_WIDTH_MM = 0.5 * (25.4 * 0.630)
SENDCUTSEND_MIN_FLANGE_FORMED_MM = 25.4 * 0.476
SENDCUTSEND_BEND_RELIEF_DEPTH_MM = 25.4 * 0.270
SENDCUTSEND_MIN_CORNER_RELIEF_FROM_BEND_MM = 25.4 * 0.032
SENDCUTSEND_COUNTERSINK_CENTER_TO_EDGE_MIN_MM = 25.4 * 0.246
SENDCUTSEND_COUNTERSINK_CENTER_TO_BEND_MIN_MM = 25.4 * 0.517
SENDCUTSEND_COUNTERSINK_CENTER_TO_EDGE_BUFFER_MM = 0.5
SENDCUTSEND_MOUNT_HOLE_TO_BEND_BUFFER_MM = 0.5
BEND_INNER_RADIUS_MM = 0.0
BEND_OUTER_RADIUS_MM = 0.0

# Base servo footprint bounds in robot-arm local coordinates.
SADDLE_BASE_FACE_Y_MM = -29.8002
SADDLE_BASE_X_MIN_MM = -35.61
SADDLE_BASE_X_MAX_MM = 6.338516
SADDLE_BASE_Z_MIN_MM = -15.960226
SADDLE_BASE_Z_MAX_MM = 15.960224

BASE_SERVO_FOOTPRINT_X_MIN_MM = SADDLE_BASE_X_MIN_MM - SADDLE_FOOTPRINT_X_BUFFER_MM
BASE_SERVO_FOOTPRINT_X_MAX_MM = SADDLE_BASE_X_MAX_MM + SADDLE_FOOTPRINT_X_BUFFER_MM
BASE_SERVO_SIDE_X_MIN_MM = BASE_SERVO_FOOTPRINT_X_MAX_MM - BOOLEAN_OVERLAP_MM
BASE_SERVO_SIDE_X_MAX_MM = BASE_SERVO_SIDE_X_MIN_MM + SIDE_WALL_THICKNESS_MM
BASE_SERVO_END_FOR_END_PIVOT_LOCAL_X_MM = 0.5 * (
    BASE_SERVO_FOOTPRINT_X_MIN_MM + BASE_SERVO_SIDE_X_MAX_MM
)
BASE_SERVO_END_FOR_END_PIVOT_LOCAL_Z_MM = 0.5 * (SADDLE_BASE_Z_MIN_MM + SADDLE_BASE_Z_MAX_MM)

SERVO_STANDOFF_HEIGHT_MM = 10.0
SERVO_STANDOFF_BODY_DIAMETER_MM = 3.2
SERVO_MOUNT_X_SHIFT_FOR_UNDER_ACCESS_MM = BASE_SERVO_FOOTPRINT_X_MIN_MM
BASE_PLATE_SERVO_MOUNT_HOLE_EDGE_BUFFER_MM = 3.0
BASE_PLATE_UNDER_ACCESS_CLEARANCE_MM = 5.0

# 5x M3 lower-horn clearance pattern on the base plate.
BASE_HORN_CONNECTION_HOLE_SPECS_MM: tuple[tuple[float, float, float], ...] = (
    (-32.5, 0.0, M3_CLEARANCE_RADIUS_MM),
    (-25.5, -7.0, M3_CLEARANCE_RADIUS_MM),
    (-25.5, 0.0, BASE_CENTER_HORN_FACE_CLEARANCE_RADIUS_MM),
    (-25.5, 7.0, M3_CLEARANCE_RADIUS_MM),
    (-18.5, 0.0, M3_CLEARANCE_RADIUS_MM),
)
BASE_SERVO_HORN_LOCAL_X_MM = -25.5

# Resolved from:
# @cad[STEP/imports/sts3250#o1.2.e920,o1.2.e922]
# @cad[STEP/imports/sts3250#o1.2.e921,o1.2.e923]
M2_CLEARANCE_RADIUS_MM = 1.1
M2_FLAT_HEAD_COUNTERSINK_MAJOR_RADIUS_MM = 2.15
M2_UNDERSIDE_COUNTERSINK_DEPTH_MM = 1.05
M2_5_CLEARANCE_RADIUS_MM = 0.5 * 2.7
M2_5_FLAT_HEAD_COUNTERSINK_MAJOR_RADIUS_MM = 2.5
M2_5_UNDERSIDE_COUNTERSINK_DEPTH_MM = 1.15
SERVO_BUS_STANDOFF_HEIGHT_MM = 6.0
SERVO_BUS_STANDOFF_HEX_ACROSS_FLATS_MM = 5.0
BASE_SERVO_M2_HOLE_SPECS_MM: tuple[tuple[float, float, float], ...] = (
    (-17.2, -10.25, M2_CLEARANCE_RADIUS_MM),
    (7.25, -10.25, M2_CLEARANCE_RADIUS_MM),
    (-17.2, 10.25, M2_CLEARANCE_RADIUS_MM),
    (7.25, 10.25, M2_CLEARANCE_RADIUS_MM),
)
BASE_SERVO_STANDOFF_MOUNT_HOLES_MM: tuple[tuple[float, float, float], ...] = tuple(
    (
        (2.0 * BASE_SERVO_END_FOR_END_PIVOT_LOCAL_X_MM)
        - x
        + SERVO_MOUNT_X_SHIFT_FOR_UNDER_ACCESS_MM,
        (2.0 * BASE_SERVO_END_FOR_END_PIVOT_LOCAL_Z_MM) - z,
        M2_CLEARANCE_RADIUS_MM,
    )
    for x, z, _radius in BASE_SERVO_M2_HOLE_SPECS_MM
)
BASE_SERVO_MOUNTED_FOOTPRINT_X_MIN_MM = (
    (2.0 * BASE_SERVO_END_FOR_END_PIVOT_LOCAL_X_MM)
    + SERVO_MOUNT_X_SHIFT_FOR_UNDER_ACCESS_MM
    - SADDLE_BASE_X_MAX_MM
    - SADDLE_FOOTPRINT_X_BUFFER_MM
)
BASE_SERVO_MOUNTED_FOOTPRINT_X_MAX_MM = BASE_SERVO_MOUNTED_FOOTPRINT_X_MIN_MM + (
    BASE_SERVO_FOOTPRINT_X_MAX_MM - BASE_SERVO_FOOTPRINT_X_MIN_MM
)
BASE_SERVO_MOUNTED_HORN_CENTER_X_MM = (
    (2.0 * BASE_SERVO_END_FOR_END_PIVOT_LOCAL_X_MM)
    + SERVO_MOUNT_X_SHIFT_FOR_UNDER_ACCESS_MM
    - BASE_SERVO_HORN_LOCAL_X_MM
)
BASE_ATTACHMENT_HOLES_MM: tuple[tuple[float, float, float], ...] = (
    BASE_SERVO_STANDOFF_MOUNT_HOLES_MM
    + (
        BASE_HORN_CONNECTION_HOLE_SPECS_MM + BASE_SERVO_M2_HOLE_SPECS_MM
        if INCLUDE_BOTTOM_SURFACE_MOUNT_FEATURES
        else ()
    )
)

# Resolved from the four PCB spacer hole centers in the original SO-101 bus board.
SERVO_BUS_BOARD_SPACER_CENTERS_XY_MM: tuple[tuple[float, float], ...] = (
    (2.4930065, 2.4999875),
    (2.4930065, 30.4999925),
    (39.493009, 2.4999875),
    (39.505008000000004, 30.4999925),
)
SERVO_BUS_PLATE_CLEARANCE_RADIUS_MM = M2_5_CLEARANCE_RADIUS_MM
SERVO_BUS_MOUNT_LOCAL_X_MIN_MM = min(x for x, _y in SERVO_BUS_BOARD_SPACER_CENTERS_XY_MM)
SERVO_BUS_MOUNT_LOCAL_X_MAX_MM = max(x for x, _y in SERVO_BUS_BOARD_SPACER_CENTERS_XY_MM)
SERVO_BUS_MOUNT_LOCAL_X_CENTER_MM = 0.5 * (SERVO_BUS_MOUNT_LOCAL_X_MIN_MM + SERVO_BUS_MOUNT_LOCAL_X_MAX_MM)
SERVO_BUS_MOUNT_LOCAL_Y_MIN_MM = min(y for _x, y in SERVO_BUS_BOARD_SPACER_CENTERS_XY_MM)
SERVO_BUS_MOUNT_LOCAL_Y_MAX_MM = max(y for _x, y in SERVO_BUS_BOARD_SPACER_CENTERS_XY_MM)
SERVO_BUS_MOUNT_LOCAL_Y_CENTER_MM = 0.5 * (SERVO_BUS_MOUNT_LOCAL_Y_MIN_MM + SERVO_BUS_MOUNT_LOCAL_Y_MAX_MM)
SENDCUTSEND_MIN_HOLE_TO_EDGE_QUOTE_MM = 0.97
BASE_CLAMP_HOLE_TO_EDGE_BUFFER_MM = 0.53
BASE_CLAMP_HOLE_TO_EDGE_TARGET_MM = (
    SENDCUTSEND_MIN_HOLE_TO_EDGE_QUOTE_MM + BASE_CLAMP_HOLE_TO_EDGE_BUFFER_MM
)
BASE_CLAMP_SERVO_BUS_SPACER_WIDTH_MM = (
    (SERVO_BUS_MOUNT_LOCAL_Y_MAX_MM - SERVO_BUS_MOUNT_LOCAL_Y_MIN_MM)
    + (2.0 * (SERVO_BUS_PLATE_CLEARANCE_RADIUS_MM + BASE_CLAMP_HOLE_TO_EDGE_TARGET_MM))
)

# SendCutSend's current .125" 5052 guideline uses a 0.630" die width for
# bending; cut features should stay outside half of that die width from the
# bend line. We size the wall from the mount-hole span plus that offset.
SENDCUTSEND_5052_125_DIE_WIDTH_MM = 0.630 * 25.4
SENDCUTSEND_FEATURE_TO_BEND_MIN_MM = (0.5 * SENDCUTSEND_5052_125_DIE_WIDTH_MM) + SERVO_BUS_PLATE_CLEARANCE_RADIUS_MM
U_BRACKET_CLEARANCE_MM = (
    max(
        STANDARD_DESK_CLAMP_CLEARANCE_MM,
        (SERVO_BUS_MOUNT_LOCAL_X_MAX_MM - SERVO_BUS_MOUNT_LOCAL_X_MIN_MM)
        + (2.0 * SENDCUTSEND_FEATURE_TO_BEND_MIN_MM)
        - (2.0 * PLATE_THICKNESS_MM),
    )
)

# Resolved from @cad[STEP/imports/servo_bus].
SERVO_BUS_LOCAL_X_MIN_MM = -0.390013
SERVO_BUS_LOCAL_X_MAX_MM = 42.401989
SERVO_BUS_LOCAL_Y_MIN_MM = -0.012095
SERVO_BUS_LOCAL_Y_MAX_MM = 33.012075
SERVO_BUS_LOCAL_Z_MIN_MM = -6.0
SERVO_BUS_LOCAL_Z_MAX_MM = 1.599999
SERVO_BUS_HOLE_CENTER_TO_BOARD_X_EDGE_MIN_MM = min(
    min(bus_x - SERVO_BUS_LOCAL_X_MIN_MM, SERVO_BUS_LOCAL_X_MAX_MM - bus_x)
    for bus_x, _bus_y in SERVO_BUS_BOARD_SPACER_CENTERS_XY_MM
)
SERVO_BUS_TOP_EDGE_BUFFER_MM = max(
    2.0,
    SENDCUTSEND_COUNTERSINK_CENTER_TO_EDGE_MIN_MM
    + SENDCUTSEND_COUNTERSINK_CENTER_TO_EDGE_BUFFER_MM
    - SERVO_BUS_HOLE_CENTER_TO_BOARD_X_EDGE_MIN_MM,
)
SERVO_BUS_TO_SERVO_CLEARANCE_MM = 2.0
SERVO_BUS_TOP_BOARD_X_MIN_MM = (
    BASE_SERVO_MOUNTED_FOOTPRINT_X_MIN_MM
    + (BASE_SERVO_FOOTPRINT_X_MAX_MM - BASE_SERVO_FOOTPRINT_X_MIN_MM)
    + SERVO_BUS_TO_SERVO_CLEARANCE_MM
)
SERVO_BUS_TOP_BOARD_X_MAX_MM = SERVO_BUS_TOP_BOARD_X_MIN_MM + (
    SERVO_BUS_LOCAL_Y_MAX_MM - SERVO_BUS_LOCAL_Y_MIN_MM
)
TOP_PLATE_NECK_CLEARANCE_AFTER_BUS_MM = 2.0
TOP_PLATE_NECK_START_X_MM = SERVO_BUS_TOP_BOARD_X_MAX_MM + TOP_PLATE_NECK_CLEARANCE_AFTER_BUS_MM
TOP_PLATE_NECK_TO_BEND_MIN_MM = SENDCUTSEND_BEND_RELIEF_DEPTH_MM + 2.0
TOP_PLATE_SHOULDER_WIDTH_MM = TOP_PLATE_NECK_TO_BEND_MIN_MM + SIDE_WALL_THICKNESS_MM
SERVO_BUS_TOP_TO_BASE_CLAMP_X_OFFSET_MM = SERVO_BUS_TOP_BOARD_X_MIN_MM - SERVO_BUS_LOCAL_Y_MIN_MM
SERVO_BUS_TOP_TO_BASE_CLAMP_Z_OFFSET_MM = -SERVO_BUS_MOUNT_LOCAL_X_CENTER_MM
SERVO_BUS_TOP_MOUNT_HOLES_MM: tuple[tuple[float, float, float], ...] = tuple(
    (
        bus_y + SERVO_BUS_TOP_TO_BASE_CLAMP_X_OFFSET_MM,
        bus_x + SERVO_BUS_TOP_TO_BASE_CLAMP_Z_OFFSET_MM,
        SERVO_BUS_PLATE_CLEARANCE_RADIUS_MM,
    )
    for bus_x, bus_y in SERVO_BUS_BOARD_SPACER_CENTERS_XY_MM
)
BASE_ATTACHMENT_HOLES_MM = BASE_ATTACHMENT_HOLES_MM + SERVO_BUS_TOP_MOUNT_HOLES_MM
BASE_PLATE_CASE_MIN_WIDTH_MM = 68.0
BASE_PLATE_Z_WIDTH_MM = max(
    SERVO_BUS_LOCAL_Y_MAX_MM - SERVO_BUS_LOCAL_Y_MIN_MM,
    BASE_CLAMP_SERVO_BUS_SPACER_WIDTH_MM,
    (SERVO_BUS_LOCAL_X_MAX_MM - SERVO_BUS_LOCAL_X_MIN_MM)
    + (2.0 * SERVO_BUS_TOP_EDGE_BUFFER_MM),
    STANDARD_DESK_CLAMP_CONTACT_WIDTH_MM + (2.0 * TOP_PLATE_SHOULDER_WIDTH_MM),
    STANDARD_DESK_CLAMP_CONTACT_WIDTH_MM,
    BASE_PLATE_CASE_MIN_WIDTH_MM,
)
BASE_PLATE_HUB_SLOT_LENGTH_MM = 26.0
BASE_PLATE_HUB_SLOT_WIDTH_MM = 4.0
BASE_PLATE_HUB_SLOT_EDGE_INSET_MM = 5.5
BASE_PLATE_HUB_END_SLOT_X_INSET_MM = 6.0
BASE_PLATE_HUB_SIDE_SLOT_COUNT = 2
BASE_PLATE_OCTAGON_LEFT_CHAMFER_X_MM = 10.0
BASE_PLATE_OCTAGON_LEFT_CHAMFER_Z_MM = 10.0
BASE_PLATE_MAIN_SURFACE_CENTER_X_MM = BASE_SERVO_MOUNTED_HORN_CENTER_X_MM
BASE_PLATE_LEFT_EDGE_EXTRA_INSET_MM = 0.0
BASE_PLATE_SHARP_NECK_CORNER_INDICES = (2, 5)


@dataclass(frozen=True)
class BracketLayout:
    x_min: float
    x_max: float
    y_min: float
    y_max: float
    z_min: float
    z_max: float
    clamp_z_min: float
    clamp_z_max: float
    neck_start_x: float
    width: float
    height: float
    clamp_height: float
    return_width: float
    return_x_min: float
    return_y_min: float
    return_y_max: float
    side_x_min: float
    side_x_max: float
    overall_y_min: float
    face_y: float
    attachment_holes: tuple[tuple[float, float, float], ...]
    return_mount_holes: tuple[tuple[float, float, float], ...]
    servo_bus_mount_holes_xzr: tuple[tuple[float, float, float], ...]


@dataclass(frozen=True)
class FlatPattern:
    total_length_mm: float
    width_mm: float
    top_flange_flat_length_mm: float
    return_flange_flat_length_mm: float
    web_flat_start_mm: float
    web_flat_end_mm: float
    bend_line_positions_mm: tuple[float, float]
    cut_circles: tuple[tuple[float, float, float], ...]
    cut_slots: tuple[tuple[float, float, float, float, float], ...]
    rounded_corner_radius_mm: float
    min_feature_to_bend_mm: float


def _make_box(
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


def _make_xz_outline_solid(
    points_xz: tuple[tuple[float, float], ...],
    *,
    y_min: float,
    y_max: float,
) -> build123d.Shape:
    points_xyz = tuple((x, y_min, z) for x, z in points_xz)
    face = build123d.make_face(build123d.Polyline(*points_xyz, close=True))
    return build123d.extrude(face, amount=y_max - y_min, dir=(0.0, 1.0, 0.0))


def _make_cylinder_along(
    *,
    radius: float,
    height: float,
    origin: build123d.Vector,
    direction: build123d.Vector,
) -> build123d.Solid:
    return build123d.Solid.make_cylinder(
        radius,
        height,
        plane=build123d.Plane(origin=origin, z_dir=direction),
    )


def _make_cone_along(
    *,
    base_radius: float,
    top_radius: float,
    height: float,
    origin: build123d.Vector,
    direction: build123d.Vector,
) -> build123d.Solid:
    return build123d.Solid.make_cone(
        base_radius,
        top_radius,
        height,
        plane=build123d.Plane(origin=origin, z_dir=direction),
    )


def _sendcutsend_outside_setback_90_mm() -> float:
    return SENDCUTSEND_EFFECTIVE_BEND_RADIUS_MM + PLATE_THICKNESS_MM


def _sendcutsend_bend_allowance_90_mm() -> float:
    return (2.0 * _sendcutsend_outside_setback_90_mm()) - SENDCUTSEND_BEND_DEDUCTION_90_MM


def _validate_sendcutsend_bend_rule() -> None:
    bend_deduction_error = abs(
        SENDCUTSEND_BEND_DEDUCTION_90_MM
        - ((2.0 * _sendcutsend_outside_setback_90_mm()) - _sendcutsend_bend_allowance_90_mm())
    )
    if bend_deduction_error > 0.05:
        raise RuntimeError(
            "SendCutSend bend-rule constants are inconsistent: "
            f"bend deduction error {bend_deduction_error:.3f} mm is too large"
        )


def _cast_shape(obj: object) -> build123d.Shape:
    from build123d.topology import downcast
    from build123d.topology.shape_core import shapetype

    occt_shape = downcast(obj)
    shape_name = build123d.Shape.shape_LUT[shapetype(occt_shape)]
    shape_type = getattr(build123d, shape_name)
    return shape_type.cast(occt_shape)


def _geom_type_name(shape: build123d.Shape) -> str:
    geom_type = shape.geom_type
    return geom_type.name if hasattr(geom_type, "name") else str(geom_type)


def _build_bracket_layout() -> BracketLayout:
    x_min = min(
        BASE_SERVO_FOOTPRINT_X_MIN_MM,
        BASE_SERVO_MOUNTED_FOOTPRINT_X_MIN_MM,
        min(
            x - radius - BASE_PLATE_SERVO_MOUNT_HOLE_EDGE_BUFFER_MM
            for x, _z, radius in BASE_SERVO_STANDOFF_MOUNT_HOLES_MM
        ),
    )
    x_max = BASE_SERVO_FOOTPRINT_X_MAX_MM
    if BASE_ATTACHMENT_HOLES_MM:
        required_x_max_for_mount_holes = max(
            x
            + SENDCUTSEND_COUNTERSINK_CENTER_TO_BEND_MIN_MM
            + SENDCUTSEND_MOUNT_HOLE_TO_BEND_BUFFER_MM
            for x, _z, _radius in BASE_ATTACHMENT_HOLES_MM
        )
        x_max = max(x_max, required_x_max_for_mount_holes)
    x_max = max(x_max, TOP_PLATE_NECK_START_X_MM + TOP_PLATE_NECK_TO_BEND_MIN_MM)
    required_x_min = x_min
    x_min = (
        (2.0 * BASE_PLATE_MAIN_SURFACE_CENTER_X_MM)
        - TOP_PLATE_NECK_START_X_MM
        + BASE_PLATE_LEFT_EDGE_EXTRA_INSET_MM
    )
    if x_min > required_x_min:
        raise RuntimeError(
            "Base plate main-surface centering would clip required geometry: "
            f"x_min={x_min:.3f} mm > required_x_min={required_x_min:.3f} mm"
        )
    z_center = 0.5 * (SADDLE_BASE_Z_MIN_MM + SADDLE_BASE_Z_MAX_MM)
    z_min = z_center - (0.5 * BASE_PLATE_Z_WIDTH_MM)
    z_max = z_center + (0.5 * BASE_PLATE_Z_WIDTH_MM)
    clamp_z_min = z_center - (0.5 * STANDARD_DESK_CLAMP_CONTACT_WIDTH_MM)
    clamp_z_max = z_center + (0.5 * STANDARD_DESK_CLAMP_CONTACT_WIDTH_MM)
    y_min = SADDLE_BASE_FACE_Y_MM - PLATE_THICKNESS_MM
    y_max = SADDLE_BASE_FACE_Y_MM
    return_y_max = y_min - U_BRACKET_CLEARANCE_MM
    return_y_min = return_y_max - PLATE_THICKNESS_MM
    side_x_max = x_max
    side_x_min = side_x_max - SIDE_WALL_THICKNESS_MM
    return_x_min = side_x_min - (
        RETURN_FACE_LENGTH_RATIO * (side_x_max - BASE_SERVO_FOOTPRINT_X_MIN_MM)
    )
    standoff_under_access_clearance = return_x_min - max(
        x for x, _z, _radius in BASE_SERVO_STANDOFF_MOUNT_HOLES_MM
    )
    if standoff_under_access_clearance < BASE_PLATE_UNDER_ACCESS_CLEARANCE_MM:
        raise RuntimeError(
            "Base servo standoff holes are too close to the lower return face for "
            "driver access: "
            f"{standoff_under_access_clearance:.3f} mm < "
            f"{BASE_PLATE_UNDER_ACCESS_CLEARANCE_MM:.3f} mm"
        )
    return_mount_holes = (
        (
            0.5 * (return_x_min + side_x_min),
            0.5 * (clamp_z_min + clamp_z_max),
            M8_CLEARANCE_RADIUS_MM,
        ),
    ) if INCLUDE_RETURN_SURFACE_MOUNT_FEATURES else ()

    return BracketLayout(
        x_min=x_min,
        x_max=x_max,
        y_min=y_min,
        y_max=y_max,
        z_min=z_min,
        z_max=z_max,
        clamp_z_min=clamp_z_min,
        clamp_z_max=clamp_z_max,
        neck_start_x=TOP_PLATE_NECK_START_X_MM,
        width=x_max - x_min,
        height=z_max - z_min,
        clamp_height=clamp_z_max - clamp_z_min,
        return_width=side_x_max - return_x_min,
        return_x_min=return_x_min,
        return_y_min=return_y_min,
        return_y_max=return_y_max,
        side_x_min=side_x_min,
        side_x_max=side_x_max,
        overall_y_min=return_y_min,
        face_y=y_max,
        attachment_holes=BASE_ATTACHMENT_HOLES_MM,
        return_mount_holes=return_mount_holes,
        servo_bus_mount_holes_xzr=SERVO_BUS_TOP_MOUNT_HOLES_MM,
    )


def _min_servo_bus_hole_center_to_plate_edge(layout: BracketLayout) -> float:
    if not SERVO_BUS_TOP_MOUNT_HOLES_MM:
        return math.inf
    return min(
        min(z - layout.z_min, layout.z_max - z)
        for _x, z, _radius in SERVO_BUS_TOP_MOUNT_HOLES_MM
    )


def _fillet_plan_corners(
    plate: build123d.Solid,
    *,
    x_min: float,
    x_max: float,
    y_min: float,
    y_max: float,
    z_min: float,
    z_max: float,
    include_min_x: bool = True,
    include_max_x: bool = True,
) -> build123d.Shape:
    matches: list[build123d.Edge] = []
    for edge in plate.edges():
        if _geom_type_name(edge) != "LINE":
            continue
        bb = edge.bounding_box()
        if abs((bb.max.Y - bb.min.Y) - (y_max - y_min)) > 1e-3:
            continue
        if (bb.max.X - bb.min.X) > 1e-3 or (bb.max.Z - bb.min.Z) > 1e-3:
            continue
        center = edge.center()
        if abs(abs(center.X - ((x_min + x_max) * 0.5)) - ((x_max - x_min) * 0.5)) > 1e-3:
            continue
        if abs(abs(center.Z - ((z_min + z_max) * 0.5)) - ((z_max - z_min) * 0.5)) > 1e-3:
            continue
        at_min_x = abs(center.X - x_min) <= 1e-3
        at_max_x = abs(center.X - x_max) <= 1e-3
        if at_min_x and not include_min_x:
            continue
        if at_max_x and not include_max_x:
            continue
        matches.append(edge)

    expected_count = (2 if include_min_x else 0) + (2 if include_max_x else 0)
    if len(matches) != expected_count:
        raise RuntimeError(f"Expected {expected_count} plan-view corner edges to fillet, found {len(matches)}")

    mk = BRepFilletAPI_MakeFillet(plate.wrapped)
    for edge in matches:
        mk.Add(CORNER_RADIUS_MM, edge.wrapped)
    mk.Build()
    if not mk.IsDone():
        raise RuntimeError("Failed to round U-bracket plate corners")
    return _cast_shape(mk.Shape())


def _fillet_vertical_plan_edges(
    plate: build123d.Shape,
    *,
    x: float,
    z_values: tuple[float, ...],
    y_min: float,
    y_max: float,
    radius: float,
) -> build123d.Shape:
    matches: list[build123d.Edge] = []
    for edge in plate.edges():
        if _geom_type_name(edge) != "LINE":
            continue
        bb = edge.bounding_box()
        if abs((bb.max.Y - bb.min.Y) - (y_max - y_min)) > 1e-3:
            continue
        if (bb.max.X - bb.min.X) > 1e-3 or (bb.max.Z - bb.min.Z) > 1e-3:
            continue
        center = edge.center()
        if abs(center.X - x) > 1e-3:
            continue
        if not any(abs(center.Z - z) <= 1e-3 for z in z_values):
            continue
        matches.append(edge)

    if len(matches) != len(z_values):
        raise RuntimeError(
            f"Expected {len(z_values)} vertical plan edges to fillet, found {len(matches)}"
        )

    mk = BRepFilletAPI_MakeFillet(plate.wrapped)
    for edge in matches:
        mk.Add(radius, edge.wrapped)
    mk.Build()
    if not mk.IsDone():
        raise RuntimeError("Failed to round selected vertical plan edges")
    return _cast_shape(mk.Shape())


def _fillet_plan_outline_vertices(
    plate: build123d.Shape,
    *,
    points_xz: tuple[tuple[float, float], ...],
    y_min: float,
    y_max: float,
    radius: float,
) -> build123d.Shape:
    matches: list[build123d.Edge] = []
    for edge in plate.edges():
        if _geom_type_name(edge) != "LINE":
            continue
        bb = edge.bounding_box()
        if abs((bb.max.Y - bb.min.Y) - (y_max - y_min)) > 1e-3:
            continue
        if (bb.max.X - bb.min.X) > 1e-3 or (bb.max.Z - bb.min.Z) > 1e-3:
            continue
        center = edge.center()
        if not any(
            abs(center.X - point_x) <= 1e-3 and abs(center.Z - point_z) <= 1e-3
            for point_x, point_z in points_xz
        ):
            continue
        matches.append(edge)

    if len(matches) != len(points_xz):
        raise RuntimeError(
            f"Expected {len(points_xz)} outline vertex edges to fillet, found {len(matches)}"
        )

    mk = BRepFilletAPI_MakeFillet(plate.wrapped)
    for edge in matches:
        mk.Add(radius, edge.wrapped)
    mk.Build()
    if not mk.IsDone():
        raise RuntimeError("Failed to round top-plate outline")
    return _cast_shape(mk.Shape())


def _cut_y_holes(
    plate: build123d.Shape,
    *,
    holes_xzr: tuple[tuple[float, float, float], ...],
    x_min: float,
    x_max: float,
    y_min: float,
    y_max: float,
    z_min: float,
    z_max: float,
) -> build123d.Shape:
    hole_depth = (y_max - y_min) + (2.0 * CUT_EXTENSION_MM)
    for x, z, radius in holes_xzr:
        if not (x_min + radius <= x <= x_max - radius):
            raise RuntimeError(f"Hole at x={x:.3f} mm does not fit within the bracket x span")
        if not (z_min + radius <= z <= z_max - radius):
            raise RuntimeError(f"Hole at z={z:.3f} mm does not fit within the bracket z span")
        plate = plate.cut(
            _make_cylinder_along(
                radius=radius,
                height=hole_depth,
                origin=build123d.Vector(x, y_min - CUT_EXTENSION_MM, z),
                direction=build123d.Vector(0.0, 1.0, 0.0),
            )
        )
    return plate


def _cut_y_slots(
    plate: build123d.Shape,
    *,
    slots_xzlw: tuple[tuple[float, float, float, float], ...],
    x_min: float,
    x_max: float,
    y_min: float,
    y_max: float,
    z_min: float,
    z_max: float,
) -> build123d.Shape:
    slot_depth = (y_max - y_min) + (2.0 * CUT_EXTENSION_MM)
    for x, z, length, width in slots_xzlw:
        if length <= width:
            raise RuntimeError(
                f"Slot length must exceed slot width, got {length:.3f} x {width:.3f} mm"
            )
        if not (x_min + (0.5 * length) <= x <= x_max - (0.5 * length)):
            raise RuntimeError(f"Slot at x={x:.3f} mm does not fit within the bracket x span")
        if not (z_min + (0.5 * width) <= z <= z_max - (0.5 * width)):
            raise RuntimeError(f"Slot at z={z:.3f} mm does not fit within the bracket z span")

        radius = 0.5 * width
        half_straight = 0.5 * (length - width)
        plate = plate.cut(
            _make_box(
                x_min=x - half_straight,
                x_max=x + half_straight,
                y_min=y_min - CUT_EXTENSION_MM,
                y_max=y_min - CUT_EXTENSION_MM + slot_depth,
                z_min=z - radius,
                z_max=z + radius,
            )
        )
        for end_x in (x - half_straight, x + half_straight):
            plate = plate.cut(
                _make_cylinder_along(
                    radius=radius,
                    height=slot_depth,
                    origin=build123d.Vector(end_x, y_min - CUT_EXTENSION_MM, z),
                    direction=build123d.Vector(0.0, 1.0, 0.0),
                )
            )
    return plate


def _cut_y_oriented_slots(
    plate: build123d.Shape,
    *,
    slots_xzlwr: tuple[tuple[float, float, float, float, float], ...],
    x_min: float,
    x_max: float,
    y_min: float,
    y_max: float,
    z_min: float,
    z_max: float,
) -> build123d.Shape:
    slot_depth = (y_max - y_min) + (2.0 * CUT_EXTENSION_MM)
    for x, z, length, width, rotation_deg in slots_xzlwr:
        if length <= width:
            raise RuntimeError(
                f"Slot length must exceed slot width, got {length:.3f} x {width:.3f} mm"
            )
        angle = math.radians(rotation_deg)
        unit_x = math.cos(angle)
        unit_z = math.sin(angle)
        perp_x = -unit_z
        perp_z = unit_x
        radius = 0.5 * width
        half_straight = 0.5 * (length - width)
        half_length = 0.5 * length
        projected_half_x = abs(unit_x) * half_length + abs(perp_x) * radius
        projected_half_z = abs(unit_z) * half_length + abs(perp_z) * radius
        if not (x_min + projected_half_x <= x <= x_max - projected_half_x):
            raise RuntimeError(f"Oriented slot at x={x:.3f} mm does not fit within the bracket x span")
        if not (z_min + projected_half_z <= z <= z_max - projected_half_z):
            raise RuntimeError(f"Oriented slot at z={z:.3f} mm does not fit within the bracket z span")

        rect_points = (
            (
                x - (half_straight * unit_x) - (radius * perp_x),
                z - (half_straight * unit_z) - (radius * perp_z),
            ),
            (
                x + (half_straight * unit_x) - (radius * perp_x),
                z + (half_straight * unit_z) - (radius * perp_z),
            ),
            (
                x + (half_straight * unit_x) + (radius * perp_x),
                z + (half_straight * unit_z) + (radius * perp_z),
            ),
            (
                x - (half_straight * unit_x) + (radius * perp_x),
                z - (half_straight * unit_z) + (radius * perp_z),
            ),
        )
        plate = plate.cut(
            _make_xz_outline_solid(
                rect_points,
                y_min=y_min - CUT_EXTENSION_MM,
                y_max=y_min - CUT_EXTENSION_MM + slot_depth,
            )
        )
        for sign in (-1.0, 1.0):
            plate = plate.cut(
                _make_cylinder_along(
                    radius=radius,
                    height=slot_depth,
                    origin=build123d.Vector(
                        x + (sign * half_straight * unit_x),
                        y_min - CUT_EXTENSION_MM,
                        z + (sign * half_straight * unit_z),
                    ),
                    direction=build123d.Vector(0.0, 1.0, 0.0),
                )
            )
    return plate


def _cut_x_holes(
    bracket: build123d.Shape,
    *,
    holes_yzr: tuple[tuple[float, float, float], ...],
    x_min: float,
    x_max: float,
    y_min: float,
    y_max: float,
    z_min: float,
    z_max: float,
) -> build123d.Shape:
    hole_depth = (x_max - x_min) + (2.0 * CUT_EXTENSION_MM)
    for y, z, radius in holes_yzr:
        if not (y_min + radius <= y <= y_max - radius):
            raise RuntimeError(f"Hole at y={y:.3f} mm does not fit within the bracket y span")
        if not (z_min + radius <= z <= z_max - radius):
            raise RuntimeError(f"Hole at z={z:.3f} mm does not fit within the bracket z span")
        bracket = bracket.cut(
            _make_cylinder_along(
                radius=radius,
                height=hole_depth,
                origin=build123d.Vector(x_min - CUT_EXTENSION_MM, y, z),
                direction=build123d.Vector(1.0, 0.0, 0.0),
            )
        )
    return bracket


def _cut_base_plate_mount_features(
    plate: build123d.Shape,
    *,
    holes_xzr: tuple[tuple[float, float, float], ...],
    x_min: float,
    x_max: float,
    y_min: float,
    y_max: float,
    z_min: float,
    z_max: float,
) -> build123d.Shape:
    return _cut_y_holes(
        plate,
        holes_xzr=holes_xzr,
        x_min=x_min,
        x_max=x_max,
        y_min=y_min,
        y_max=y_max,
        z_min=z_min,
        z_max=z_max,
    )


def _cut_underside_countersinks(
    plate: build123d.Shape,
    *,
    holes_xzr: tuple[tuple[float, float, float], ...],
    y_min: float,
    clearance_radius: float,
    countersink_major_radius: float,
    countersink_depth: float,
) -> build123d.Shape:
    for x, z, radius in holes_xzr:
        if abs(radius - clearance_radius) > 1e-6:
            continue
        plate = plate.cut(
            _make_cone_along(
                base_radius=countersink_major_radius,
                top_radius=radius,
                height=countersink_depth,
                origin=build123d.Vector(x, y_min, z),
                direction=build123d.Vector(0.0, 1.0, 0.0),
            )
        )
    return plate


def _as_single_solid(shape: build123d.Shape) -> build123d.Solid:
    solids = list(shape.solids())
    if len(solids) != 1:
        raise RuntimeError(f"Expected a single solid, found {len(solids)}")
    return solids[0]


def _top_plate_outline_points(layout: BracketLayout) -> tuple[tuple[float, float], ...]:
    left_flat_x = min(
        layout.x_min + BASE_PLATE_OCTAGON_LEFT_CHAMFER_X_MM,
        layout.neck_start_x - BASE_PLATE_HUB_SLOT_LENGTH_MM,
    )
    left_lower_z = min(
        layout.z_min + BASE_PLATE_OCTAGON_LEFT_CHAMFER_Z_MM,
        layout.clamp_z_min - BASE_PLATE_HUB_SLOT_WIDTH_MM,
    )
    left_upper_z = max(
        layout.z_max - BASE_PLATE_OCTAGON_LEFT_CHAMFER_Z_MM,
        layout.clamp_z_max + BASE_PLATE_HUB_SLOT_WIDTH_MM,
    )
    return (
        (left_flat_x, layout.z_min),
        (layout.neck_start_x, layout.z_min),
        (layout.neck_start_x, layout.clamp_z_min),
        (layout.x_max, layout.clamp_z_min),
        (layout.x_max, layout.clamp_z_max),
        (layout.neck_start_x, layout.clamp_z_max),
        (layout.neck_start_x, layout.z_max),
        (left_flat_x, layout.z_max),
        (layout.x_min, left_upper_z),
        (layout.x_min, left_lower_z),
    )


def _top_plate_hub_slot_specs(layout: BracketLayout) -> tuple[tuple[float, float, float, float, float], ...]:
    outline_points = _top_plate_outline_points(layout)
    side_start_x = outline_points[0][0]
    side_end_x = layout.neck_start_x
    side_span = side_end_x - side_start_x
    side_slot_gap = (
        side_span - (BASE_PLATE_HUB_SIDE_SLOT_COUNT * BASE_PLATE_HUB_SLOT_LENGTH_MM)
    ) / (BASE_PLATE_HUB_SIDE_SLOT_COUNT + 1)
    if side_slot_gap <= BASE_PLATE_HUB_SLOT_WIDTH_MM:
        raise RuntimeError(
            "Side case-retention slots cannot be evenly spaced with the current "
            f"edge span: {side_span:.3f} mm"
        )
    slot_z_abs = (0.5 * layout.height) - BASE_PLATE_HUB_SLOT_EDGE_INSET_MM
    side_slot_xs = tuple(
        side_start_x
        + side_slot_gap
        + (0.5 * BASE_PLATE_HUB_SLOT_LENGTH_MM)
        + (index * (BASE_PLATE_HUB_SLOT_LENGTH_MM + side_slot_gap))
        for index in range(BASE_PLATE_HUB_SIDE_SLOT_COUNT)
    )
    slots: list[tuple[float, float, float, float, float]] = []
    for slot_x in side_slot_xs:
        for slot_z in (-slot_z_abs, slot_z_abs):
            slots.append(
                (
                    slot_x,
                    slot_z,
                    BASE_PLATE_HUB_SLOT_LENGTH_MM,
                    BASE_PLATE_HUB_SLOT_WIDTH_MM,
                    0.0,
                )
            )
    slots.append(
        (
            layout.x_min + BASE_PLATE_HUB_END_SLOT_X_INSET_MM,
            0.5 * (layout.z_min + layout.z_max),
            BASE_PLATE_HUB_SLOT_LENGTH_MM,
            BASE_PLATE_HUB_SLOT_WIDTH_MM,
            90.0,
        )
    )
    return tuple(slots)


def _make_lower_plate(layout: BracketLayout) -> build123d.Shape:
    outline_points = _top_plate_outline_points(layout)
    plate = _make_xz_outline_solid(
        outline_points,
        y_min=layout.y_min,
        y_max=layout.y_max,
    )
    rounded_outline_points = tuple(
        point
        for index, point in enumerate(outline_points)
        if index not in BASE_PLATE_SHARP_NECK_CORNER_INDICES
    )
    plate = _fillet_plan_outline_vertices(
        plate,
        points_xz=rounded_outline_points,
        y_min=layout.y_min,
        y_max=layout.y_max,
        radius=CORNER_RADIUS_MM,
    )
    plate = _cut_base_plate_mount_features(
        plate,
        holes_xzr=layout.attachment_holes,
        x_min=layout.x_min,
        x_max=layout.x_max,
        y_min=layout.y_min,
        y_max=layout.y_max,
        z_min=layout.z_min,
        z_max=layout.z_max,
    )
    plate = _cut_y_oriented_slots(
        plate,
        slots_xzlwr=_top_plate_hub_slot_specs(layout),
        x_min=layout.x_min,
        x_max=layout.x_max,
        y_min=layout.y_min,
        y_max=layout.y_max,
        z_min=layout.z_min,
        z_max=layout.z_max,
    )
    plate = _cut_underside_countersinks(
        plate,
        holes_xzr=BASE_SERVO_STANDOFF_MOUNT_HOLES_MM,
        y_min=layout.y_min,
        clearance_radius=M2_CLEARANCE_RADIUS_MM,
        countersink_major_radius=M2_FLAT_HEAD_COUNTERSINK_MAJOR_RADIUS_MM,
        countersink_depth=M2_UNDERSIDE_COUNTERSINK_DEPTH_MM,
    )
    plate = _cut_underside_countersinks(
        plate,
        holes_xzr=layout.servo_bus_mount_holes_xzr,
        y_min=layout.y_min,
        clearance_radius=SERVO_BUS_PLATE_CLEARANCE_RADIUS_MM,
        countersink_major_radius=M2_5_FLAT_HEAD_COUNTERSINK_MAJOR_RADIUS_MM,
        countersink_depth=M2_5_UNDERSIDE_COUNTERSINK_DEPTH_MM,
    )
    return _as_single_solid(plate)


def _make_return_plate(layout: BracketLayout) -> build123d.Shape:
    plate = _make_box(
        x_min=layout.return_x_min,
        x_max=layout.side_x_max,
        y_min=layout.return_y_min,
        y_max=layout.return_y_max,
        z_min=layout.clamp_z_min,
        z_max=layout.clamp_z_max,
    )
    plate = _fillet_plan_corners(
        plate,
        x_min=layout.return_x_min,
        x_max=layout.side_x_max,
        y_min=layout.return_y_min,
        y_max=layout.return_y_max,
        z_min=layout.clamp_z_min,
        z_max=layout.clamp_z_max,
        include_min_x=True,
        include_max_x=False,
    )
    plate = _cut_y_holes(
        plate,
        holes_xzr=layout.return_mount_holes,
        x_min=layout.return_x_min,
        x_max=layout.side_x_max,
        y_min=layout.return_y_min,
        y_max=layout.return_y_max,
        z_min=layout.clamp_z_min,
        z_max=layout.clamp_z_max,
    )
    return _as_single_solid(plate)


def _make_side_wall(layout: BracketLayout) -> build123d.Shape:
    return _make_box(
        x_min=layout.side_x_min,
        x_max=layout.side_x_max,
        y_min=layout.return_y_min,
        y_max=layout.y_max,
        z_min=layout.clamp_z_min,
        z_max=layout.clamp_z_max,
    )


def _long_z_edges_near(
    shape: build123d.Shape,
    *,
    x: float,
    y: float,
    z_min: float,
    z_max: float,
    tolerance: float = 0.08,
) -> build123d.ShapeList:
    matches = build123d.ShapeList()
    min_length = 0.8 * (z_max - z_min)
    for edge in shape.edges():
        if _geom_type_name(edge) != "LINE":
            continue
        bb = edge.bounding_box()
        if (bb.max.X - bb.min.X) > 1e-3 or (bb.max.Y - bb.min.Y) > 1e-3:
            continue
        if (bb.max.Z - bb.min.Z) < min_length:
            continue
        center = edge.center()
        if abs(center.X - x) > tolerance or abs(center.Y - y) > tolerance:
            continue
        matches.append(edge)
    return matches


def _apply_sendcutsend_bend_radii(
    bracket: build123d.Shape,
    *,
    layout: BracketLayout,
) -> build123d.Shape:
    if BEND_INNER_RADIUS_MM < 0.0 or BEND_OUTER_RADIUS_MM < 0.0:
        raise ValueError("Bend radii must be >= 0")
    if BEND_INNER_RADIUS_MM == 0.0 and BEND_OUTER_RADIUS_MM == 0.0:
        return bracket

    inner_bend_edges = build123d.ShapeList()
    for bend_y in (layout.y_min, layout.return_y_max):
        inner_bend_edges.extend(
            _long_z_edges_near(
                bracket,
                x=layout.side_x_min,
                y=bend_y,
                z_min=layout.clamp_z_min,
                z_max=layout.clamp_z_max,
            )
        )
    if len(inner_bend_edges) != 2:
        raise RuntimeError(f"Expected two inside bend edges to fillet, found {len(inner_bend_edges)}")

    if BEND_INNER_RADIUS_MM > 0.0:
        bracket = bracket.fillet(BEND_INNER_RADIUS_MM, inner_bend_edges)

    outer_bend_edges = build123d.ShapeList()
    for bend_y in (layout.y_max, layout.return_y_min):
        outer_bend_edges.extend(
            _long_z_edges_near(
                bracket,
                x=layout.side_x_max,
                y=bend_y,
                z_min=layout.clamp_z_min,
                z_max=layout.clamp_z_max,
                tolerance=0.25,
            )
        )
    if len(outer_bend_edges) != 2:
        raise RuntimeError(f"Expected two outside bend edges to fillet, found {len(outer_bend_edges)}")

    if BEND_OUTER_RADIUS_MM > 0.0:
        bracket = bracket.fillet(BEND_OUTER_RADIUS_MM, outer_bend_edges)

    return bracket


def build_bracket() -> build123d.Solid:
    layout = _build_bracket_layout()
    hub_slot_specs = _top_plate_hub_slot_specs(layout)
    standoff_under_access_clearance = layout.return_x_min - max(
        x for x, _z, _radius in BASE_SERVO_STANDOFF_MOUNT_HOLES_MM
    )
    servo_bus_countersink_edge_clearance = _min_servo_bus_hole_center_to_plate_edge(layout)
    if servo_bus_countersink_edge_clearance < SENDCUTSEND_COUNTERSINK_CENTER_TO_EDGE_MIN_MM:
        raise RuntimeError(
            "Servo bus countersunk holes are too close to the plate edge: "
            f"{servo_bus_countersink_edge_clearance:.3f} mm < "
            f"{SENDCUTSEND_COUNTERSINK_CENTER_TO_EDGE_MIN_MM:.3f} mm"
        )

    bracket = _make_lower_plate(layout)
    bracket = _as_single_solid(bracket.fuse(_make_side_wall(layout)))
    bracket = _as_single_solid(bracket.fuse(_make_return_plate(layout)))
    bracket = _as_single_solid(_apply_sendcutsend_bend_radii(bracket, layout=layout))

    print(
        f"{DISPLAY_NAME}: "
        f"lower_width={layout.width:.3f} mm, "
        f"return_width={layout.return_width:.3f} mm, "
        f"lower_height={layout.height:.3f} mm, "
        f"plate_thickness={PLATE_THICKNESS_MM:.3f} mm, "
        f"clearance={U_BRACKET_CLEARANCE_MM:.3f} mm, "
        f"overall_y_min={layout.overall_y_min:.4f} mm, "
        f"top_surface_holes={len(layout.attachment_holes)}, "
        f"bottom_surface_holes={len(layout.return_mount_holes)}, "
        f"horn_m3_holes={len(BASE_HORN_CONNECTION_HOLE_SPECS_MM) if INCLUDE_BOTTOM_SURFACE_MOUNT_FEATURES else 0}, "
        f"m2_mount_holes={len(BASE_SERVO_M2_HOLE_SPECS_MM) if INCLUDE_BOTTOM_SURFACE_MOUNT_FEATURES else 0}, "
        f"m2_standoff_mount_holes={len(BASE_SERVO_STANDOFF_MOUNT_HOLES_MM)}, "
        f"m2_standoff_height={SERVO_STANDOFF_HEIGHT_MM:.3f} mm, "
        f"m2_plate_clearance_diameter={2.0 * M2_CLEARANCE_RADIUS_MM:.3f} mm, "
        f"m2_countersink_major_diameter={2.0 * M2_FLAT_HEAD_COUNTERSINK_MAJOR_RADIUS_MM:.3f} mm, "
        f"m2_under_access_clearance={standoff_under_access_clearance:.3f} mm, "
        f"return_mount_holes={len(layout.return_mount_holes)}, "
        f"servo_bus_top_holes={len(layout.servo_bus_mount_holes_xzr)}, "
        f"case_retention_slots={len(hub_slot_specs)}x"
        f"{BASE_PLATE_HUB_SLOT_LENGTH_MM:.3f}x{BASE_PLATE_HUB_SLOT_WIDTH_MM:.3f} mm, "
        f"case_retention_slot_centers={[(round(slot[0], 3), round(slot[1], 3)) for slot in hub_slot_specs]}, "
        f"servo_bus_standoff_height={SERVO_BUS_STANDOFF_HEIGHT_MM:.3f} mm, "
        f"servo_bus_plate_clearance_diameter={2.0 * SERVO_BUS_PLATE_CLEARANCE_RADIUS_MM:.3f} mm, "
        f"servo_bus_countersink_major_diameter={2.0 * M2_5_FLAT_HEAD_COUNTERSINK_MAJOR_RADIUS_MM:.3f} mm, "
        f"servo_bus_countersink_center_to_edge={servo_bus_countersink_edge_clearance:.3f} mm, "
        f"servo_bus_countersink_center_to_bend_min={SENDCUTSEND_COUNTERSINK_CENTER_TO_BEND_MIN_MM:.3f} mm, "
        f"neck_to_bend_min={TOP_PLATE_NECK_TO_BEND_MIN_MM:.3f} mm, "
        f"bend_radii_inner_outer=({BEND_INNER_RADIUS_MM:.3f}, {BEND_OUTER_RADIUS_MM:.3f}) mm, "
        f"horn_center_x={BASE_SERVO_MOUNTED_HORN_CENTER_X_MM:.3f} mm, "
        f"flush_y={layout.face_y:.4f} mm"
    )
    bracket.color = GRAY_ALUMINUM_COLOR
    return bracket


def _build_flat_pattern(layout: BracketLayout) -> FlatPattern:
    _validate_sendcutsend_bend_rule()

    outside_setback = _sendcutsend_outside_setback_90_mm()
    bend_allowance = _sendcutsend_bend_allowance_90_mm()
    top_flange_outside_length = layout.side_x_max - layout.x_min
    return_flange_outside_length = layout.return_width
    top_flange_flat_length = top_flange_outside_length - outside_setback
    return_flange_flat_length = return_flange_outside_length - outside_setback
    min_flange_outside_length = min(top_flange_outside_length, return_flange_outside_length)
    min_flange_flat_length = min(top_flange_flat_length, return_flange_flat_length)
    if min_flange_outside_length < SENDCUTSEND_MIN_FLANGE_FORMED_MM:
        raise RuntimeError(
            "Flange length is below the configured bend-rule minimum: "
            f"{min_flange_outside_length:.3f} mm < {SENDCUTSEND_MIN_FLANGE_FORMED_MM:.3f} mm"
        )
    if min_flange_flat_length <= 0.0:
        raise RuntimeError(
            "Flat flange length implied by the bend rule is too short: "
            f"{min_flange_flat_length:.3f} mm"
        )

    web_outside_length = layout.y_max - layout.return_y_min
    web_flat_length = web_outside_length - (2.0 * SENDCUTSEND_EFFECTIVE_BEND_RADIUS_MM)
    if web_flat_length <= 0.0:
        raise RuntimeError(
            f"Web flat length implied by the bend rule is too short: {web_flat_length:.3f} mm"
        )

    web_flat_start = top_flange_flat_length + bend_allowance
    web_flat_end = web_flat_start + web_flat_length
    total_length = web_flat_end + bend_allowance + return_flange_flat_length
    flat_width = layout.z_max - layout.z_min
    bend_line_positions = (
        top_flange_flat_length + (0.5 * bend_allowance),
        web_flat_end + (0.5 * bend_allowance),
    )

    feature_extents: list[tuple[float, float]] = []
    cut_circles: list[tuple[float, float, float]] = []
    cut_slots: list[tuple[float, float, float, float, float]] = []
    for x, z, radius in layout.attachment_holes:
        circle = (x - layout.x_min, z - layout.z_min, radius)
        cut_circles.append(circle)
        feature_extents.append((circle[0], radius))
    for x, z, length, slot_width, rotation_deg in _top_plate_hub_slot_specs(layout):
        slot = (x - layout.x_min, z - layout.z_min, length, slot_width, rotation_deg)
        cut_slots.append(slot)
        feature_extents.append((slot[0], 0.5 * (length if abs(rotation_deg) < 45.0 else slot_width)))
    for x, z, radius in layout.return_mount_holes:
        circle = (total_length - (x - layout.return_x_min), z - layout.z_min, radius)
        cut_circles.append(circle)
        feature_extents.append((circle[0], radius))

    min_feature_to_bend = min(
        min(abs(center_u - bend_u) - feature_radius for bend_u in bend_line_positions)
        for center_u, feature_radius in feature_extents
    )

    return FlatPattern(
        total_length_mm=total_length,
        width_mm=flat_width,
        top_flange_flat_length_mm=top_flange_flat_length,
        return_flange_flat_length_mm=return_flange_flat_length,
        web_flat_start_mm=web_flat_start,
        web_flat_end_mm=web_flat_end,
        bend_line_positions_mm=bend_line_positions,
        cut_circles=tuple(cut_circles),
        cut_slots=tuple(cut_slots),
        rounded_corner_radius_mm=CORNER_RADIUS_MM,
        min_feature_to_bend_mm=min_feature_to_bend,
    )


def _add_rounded_rect_outline(
    msp: ezdxf.layouts.Modelspace,
    *,
    length: float,
    width: float,
    radius: float,
) -> None:
    if radius <= 0.0:
        raise RuntimeError(f"Corner radius must be positive, got {radius:.3f} mm")
    if width <= (2.0 * radius):
        raise RuntimeError(
            "Corner radius is too large for the base clamp flat-pattern width: "
            f"{radius:.3f} mm"
        )
    if length <= (2.0 * radius):
        raise RuntimeError(
            "Corner radius is too large for the base clamp flat-pattern length: "
            f"{radius:.3f} mm"
        )

    msp.add_line((radius, 0.0), (length - radius, 0.0), dxfattribs={"layer": "CUT"})
    msp.add_arc(
        center=(length - radius, radius),
        radius=radius,
        start_angle=-90.0,
        end_angle=0.0,
        dxfattribs={"layer": "CUT"},
    )
    msp.add_line((length, radius), (length, width - radius), dxfattribs={"layer": "CUT"})
    msp.add_arc(
        center=(length - radius, width - radius),
        radius=radius,
        start_angle=0.0,
        end_angle=90.0,
        dxfattribs={"layer": "CUT"},
    )
    msp.add_line((length - radius, width), (radius, width), dxfattribs={"layer": "CUT"})
    msp.add_arc(
        center=(radius, width - radius),
        radius=radius,
        start_angle=90.0,
        end_angle=180.0,
        dxfattribs={"layer": "CUT"},
    )
    msp.add_line((0.0, width - radius), (0.0, radius), dxfattribs={"layer": "CUT"})
    msp.add_arc(
        center=(radius, radius),
        radius=radius,
        start_angle=180.0,
        end_angle=270.0,
        dxfattribs={"layer": "CUT"},
    )


def _add_horizontal_slot_outline(
    msp: ezdxf.layouts.Modelspace,
    *,
    center_u: float,
    center_v: float,
    length: float,
    width: float,
) -> None:
    if length <= width:
        raise RuntimeError(f"Slot length must exceed slot width, got {length:.3f} x {width:.3f} mm")
    radius = 0.5 * width
    half_straight = 0.5 * (length - width)
    left_u = center_u - half_straight
    right_u = center_u + half_straight

    msp.add_line((left_u, center_v - radius), (right_u, center_v - radius), dxfattribs={"layer": "CUT"})
    msp.add_arc(
        center=(right_u, center_v),
        radius=radius,
        start_angle=-90.0,
        end_angle=90.0,
        dxfattribs={"layer": "CUT"},
    )
    msp.add_line((right_u, center_v + radius), (left_u, center_v + radius), dxfattribs={"layer": "CUT"})
    msp.add_arc(
        center=(left_u, center_v),
        radius=radius,
        start_angle=90.0,
        end_angle=270.0,
        dxfattribs={"layer": "CUT"},
    )


def _add_oriented_slot_outline(
    msp: ezdxf.layouts.Modelspace,
    *,
    center_u: float,
    center_v: float,
    length: float,
    width: float,
    rotation_deg: float,
) -> None:
    if abs(rotation_deg) <= 1e-6:
        _add_horizontal_slot_outline(
            msp,
            center_u=center_u,
            center_v=center_v,
            length=length,
            width=width,
        )
        return

    if length <= width:
        raise RuntimeError(f"Slot length must exceed slot width, got {length:.3f} x {width:.3f} mm")
    angle = math.radians(rotation_deg)
    unit_u = math.cos(angle)
    unit_v = math.sin(angle)
    perp_u = -unit_v
    perp_v = unit_u
    radius = 0.5 * width
    half_straight = 0.5 * (length - width)
    start_u = center_u - (half_straight * unit_u)
    start_v = center_v - (half_straight * unit_v)
    end_u = center_u + (half_straight * unit_u)
    end_v = center_v + (half_straight * unit_v)

    line_a_start = (start_u + (radius * perp_u), start_v + (radius * perp_v))
    line_a_end = (end_u + (radius * perp_u), end_v + (radius * perp_v))
    line_b_start = (start_u - (radius * perp_u), start_v - (radius * perp_v))
    line_b_end = (end_u - (radius * perp_u), end_v - (radius * perp_v))
    msp.add_line(line_a_start, line_a_end, dxfattribs={"layer": "CUT"})
    msp.add_line(line_b_end, line_b_start, dxfattribs={"layer": "CUT"})

    perp_angle = math.degrees(math.atan2(perp_v, perp_u))
    msp.add_arc(
        center=(end_u, end_v),
        radius=radius,
        start_angle=perp_angle,
        end_angle=perp_angle + 180.0,
        dxfattribs={"layer": "CUT"},
    )
    msp.add_arc(
        center=(start_u, start_v),
        radius=radius,
        start_angle=perp_angle + 180.0,
        end_angle=perp_angle + 360.0,
        dxfattribs={"layer": "CUT"},
    )


def _slot_profile_points(
    *,
    center_u: float,
    center_v: float,
    length: float,
    width: float,
    rotation_deg: float,
) -> list[tuple[float, float]]:
    if length <= width:
        raise RuntimeError(f"Slot length must exceed slot width, got {length:.3f} x {width:.3f} mm")
    from shapely.geometry import LineString

    angle = math.radians(rotation_deg)
    half_straight = 0.5 * (length - width)
    start = (
        center_u - (half_straight * math.cos(angle)),
        center_v - (half_straight * math.sin(angle)),
    )
    end = (
        center_u + (half_straight * math.cos(angle)),
        center_v + (half_straight * math.sin(angle)),
    )
    profile = LineString([start, end]).buffer(0.5 * width, cap_style=1, resolution=16)
    points = [(float(x), float(y)) for x, y in profile.exterior.coords]
    if points and points[0] == points[-1]:
        points.pop()
    return points


def _strip_cutout_interiors_from_geometry(geometry):
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    polygons = [geometry] if geometry.geom_type == "Polygon" else list(geometry.geoms)
    stripped = [Polygon(polygon.exterior) for polygon in polygons]
    result = unary_union(stripped).buffer(0)
    if not result.is_valid:
        result = result.buffer(0)
    if result.is_empty:
        raise RuntimeError("Base clamp topology DXF produced empty exterior geometry")
    return result


def _add_flat_pattern_service_cutouts(
    msp: ezdxf.layouts.Modelspace,
    flat_pattern: FlatPattern,
) -> None:
    # SendCutSend's secondary-service detector is much happier when round
    # service holes are exact circular contours rather than sampled polylines.
    # Use arc-bulge LWPOLYLINEs to avoid extra entity types in the upload.
    for center_u, center_v, radius in flat_pattern.cut_circles:
        dxf_topology.add_circle_polyline(
            msp,
            (center_u, center_v),
            radius,
            layer="CUT",
        )
    for center_u, center_v, length, width, rotation_deg in flat_pattern.cut_slots:
        msp.add_lwpolyline(
            _slot_profile_points(
                center_u=center_u,
                center_v=center_v,
                length=length,
                width=width,
                rotation_deg=rotation_deg,
            ),
            close=True,
            dxfattribs={"layer": "CUT"},
        )


def _flat_u_from_step_x(
    x: float,
    *,
    layout: BracketLayout,
    flat_pattern: FlatPattern,
) -> float:
    if abs(x - layout.side_x_max) <= 1e-3:
        return flat_pattern.top_flange_flat_length_mm
    return x - layout.x_min


def _flat_v_from_step_z(z: float, *, layout: BracketLayout) -> float:
    return z - layout.z_min


def _flat_point_from_step_vector(
    point: build123d.Vector,
    *,
    layout: BracketLayout,
    flat_pattern: FlatPattern,
) -> tuple[float, float]:
    return (
        _flat_u_from_step_x(point.X, layout=layout, flat_pattern=flat_pattern),
        _flat_v_from_step_z(point.Z, layout=layout),
    )


def _is_top_bend_edge(edge: build123d.Edge, *, layout: BracketLayout) -> bool:
    if _geom_type_name(edge) != "LINE":
        return False
    bb = edge.bounding_box()
    return (
        abs(bb.min.X - layout.side_x_max) <= 1e-3
        and abs(bb.max.X - layout.side_x_max) <= 1e-3
        and abs(bb.min.Z - layout.clamp_z_min) <= 1e-3
        and abs(bb.max.Z - layout.clamp_z_max) <= 1e-3
    )


def _angle_deg(point: tuple[float, float], center: tuple[float, float]) -> float:
    return math.degrees(math.atan2(point[1] - center[1], point[0] - center[0]))


def _ccw_delta_deg(start: float, end: float) -> float:
    return (end - start) % 360.0


def _add_step_projected_edge(
    msp: ezdxf.layouts.Modelspace,
    edge: build123d.Edge,
    *,
    layout: BracketLayout,
    flat_pattern: FlatPattern,
) -> None:
    edge_type = _geom_type_name(edge)
    vertices = list(edge.vertices())
    if edge_type == "LINE":
        if len(vertices) < 2:
            raise RuntimeError("STEP line edge is missing vertices for DXF projection")
        msp.add_line(
            _flat_point_from_step_vector(vertices[0].center(), layout=layout, flat_pattern=flat_pattern),
            _flat_point_from_step_vector(vertices[1].center(), layout=layout, flat_pattern=flat_pattern),
            dxfattribs={"layer": "CUT"},
        )
        return

    if edge_type != "CIRCLE":
        raise RuntimeError(f"Unsupported STEP top-face edge type for DXF projection: {edge_type}")

    center_point = edge.arc_center
    center = _flat_point_from_step_vector(center_point, layout=layout, flat_pattern=flat_pattern)
    radius = float(edge.radius)
    if len(vertices) < 2 or abs(edge.length - (2.0 * math.pi * radius)) <= 1e-3:
        msp.add_circle(center, radius, dxfattribs={"layer": "CUT"})
        return

    start = _flat_point_from_step_vector(vertices[0].center(), layout=layout, flat_pattern=flat_pattern)
    end = _flat_point_from_step_vector(vertices[1].center(), layout=layout, flat_pattern=flat_pattern)
    mid = _flat_point_from_step_vector(edge.center(), layout=layout, flat_pattern=flat_pattern)
    start_angle = _angle_deg(start, center)
    end_angle = _angle_deg(end, center)
    mid_angle = _angle_deg(mid, center)
    ccw_span = _ccw_delta_deg(start_angle, end_angle)
    mid_span = _ccw_delta_deg(start_angle, mid_angle)
    if mid_span > ccw_span + 1e-3:
        start_angle, end_angle = end_angle, start_angle
    msp.add_arc(
        center=center,
        radius=radius,
        start_angle=start_angle,
        end_angle=end_angle,
        dxfattribs={"layer": "CUT"},
    )


def _step_top_face(shape: build123d.Shape, *, layout: BracketLayout) -> build123d.Face:
    matches = []
    for face in shape.faces():
        bb = face.bounding_box()
        if abs(bb.min.Y - layout.y_max) <= 1e-3 and abs(bb.max.Y - layout.y_max) <= 1e-3:
            matches.append(face)
    if not matches:
        raise RuntimeError("Could not find the base clamp top face in the generated STEP file")
    return max(matches, key=lambda face: face.area)


def _add_step_projected_top_flange(
    msp: ezdxf.layouts.Modelspace,
    *,
    layout: BracketLayout,
    flat_pattern: FlatPattern,
) -> Path:
    step_path = Path(__file__).with_suffix(".step")
    if not step_path.exists():
        raise RuntimeError(f"STEP-derived DXF requires the generated STEP file: {step_path}")
    shape = build123d.import_step(step_path)
    top_face = _step_top_face(shape, layout=layout)
    projected_edges = 0
    for edge in top_face.edges():
        if _is_top_bend_edge(edge, layout=layout):
            continue
        _add_step_projected_edge(
            msp,
            edge,
            layout=layout,
            flat_pattern=flat_pattern,
        )
        projected_edges += 1
    if projected_edges <= 0:
        raise RuntimeError("No STEP top-face edges were projected into the DXF")
    return step_path


def _add_web_and_return_flat_outline(
    msp: ezdxf.layouts.Modelspace,
    *,
    layout: BracketLayout,
    flat_pattern: FlatPattern,
) -> None:
    start_u = flat_pattern.top_flange_flat_length_mm
    end_u = flat_pattern.total_length_mm
    min_v = layout.clamp_z_min - layout.z_min
    max_v = layout.clamp_z_max - layout.z_min
    radius = min(CORNER_RADIUS_MM, 0.5 * (max_v - min_v), flat_pattern.return_flange_flat_length_mm)

    if radius <= 0.0:
        msp.add_line((start_u, min_v), (end_u, min_v), dxfattribs={"layer": "CUT"})
        msp.add_line((end_u, min_v), (end_u, max_v), dxfattribs={"layer": "CUT"})
        msp.add_line((end_u, max_v), (start_u, max_v), dxfattribs={"layer": "CUT"})
        return

    msp.add_line((start_u, min_v), (end_u - radius, min_v), dxfattribs={"layer": "CUT"})
    msp.add_arc(
        center=(end_u - radius, min_v + radius),
        radius=radius,
        start_angle=-90.0,
        end_angle=0.0,
        dxfattribs={"layer": "CUT"},
    )
    msp.add_line((end_u, min_v + radius), (end_u, max_v - radius), dxfattribs={"layer": "CUT"})
    msp.add_arc(
        center=(end_u - radius, max_v - radius),
        radius=radius,
        start_angle=0.0,
        end_angle=90.0,
        dxfattribs={"layer": "CUT"},
    )
    msp.add_line((end_u - radius, max_v), (start_u, max_v), dxfattribs={"layer": "CUT"})


def _topology_flat_pattern_dxf(
    bracket: build123d.Shape,
    layout: BracketLayout,
    flat_pattern: FlatPattern,
) -> ezdxf.document.Drawing:
    doc = ezdxf.new("R2010", setup=True)
    doc.units = DXF_UNIT_MM
    if "CUT" not in doc.layers:
        doc.layers.add("CUT")
    if "BEND" not in doc.layers:
        doc.layers.add("BEND", linetype="DASHED")

    return_start_u = flat_pattern.total_length_mm - flat_pattern.return_flange_flat_length_mm
    web_source_span = layout.y_max - layout.return_y_min
    web_flat_span = return_start_u - flat_pattern.top_flange_flat_length_mm
    if web_source_span <= 0.0 or web_flat_span <= 0.0:
        raise RuntimeError("Base clamp topology DXF has invalid web span")

    def project_top(point: build123d.Vector) -> tuple[float, float]:
        return (
            _flat_u_from_step_x(point.X, layout=layout, flat_pattern=flat_pattern),
            _flat_v_from_step_z(point.Z, layout=layout),
        )

    def project_web(point: build123d.Vector) -> tuple[float, float]:
        t = (layout.y_max - point.Y) / web_source_span
        return (
            flat_pattern.top_flange_flat_length_mm + (t * web_flat_span),
            _flat_v_from_step_z(point.Z, layout=layout),
        )

    def project_return(point: build123d.Vector) -> tuple[float, float]:
        if abs(point.X - layout.side_x_max) <= 1e-3:
            u = return_start_u
        else:
            u = flat_pattern.total_length_mm - (point.X - layout.return_x_min)
        return (u, _flat_v_from_step_z(point.Z, layout=layout))

    top_faces = dxf_topology.planar_faces(
        bracket,
        normal_axis="y",
        normal_sign=1.0,
        coordinate_axis="y",
        coordinate=layout.y_max,
    )
    web_faces = dxf_topology.planar_faces(
        bracket,
        normal_axis="x",
        normal_sign=1.0,
        coordinate_axis="x",
        coordinate=layout.side_x_max,
    )
    return_faces = dxf_topology.planar_faces(
        bracket,
        normal_axis="y",
        normal_sign=-1.0,
        coordinate_axis="y",
        coordinate=layout.return_y_min,
    )
    geometry = dxf_topology.union_projected_faces(
        (
            (top_faces, project_top),
            (web_faces, project_web),
            (return_faces, project_return),
        )
    )
    geometry = _strip_cutout_interiors_from_geometry(geometry)
    dxf_topology.add_shapely_geometry(doc.modelspace(), geometry, layer="CUT")
    _add_flat_pattern_service_cutouts(doc.modelspace(), flat_pattern)

    for bend_line_u in flat_pattern.bend_line_positions_mm:
        doc.modelspace().add_line(
            (bend_line_u, layout.clamp_z_min - layout.z_min),
            (bend_line_u, layout.clamp_z_max - layout.z_min),
            dxfattribs={"layer": "BEND", "linetype": "DASHED"},
        )
    return doc


def build_dxf() -> ezdxf.document.Drawing:
    layout = _build_bracket_layout()
    flat_pattern = _build_flat_pattern(layout)
    doc = _topology_flat_pattern_dxf(build_bracket(), layout, flat_pattern)

    print(
        f"{DISPLAY_NAME} DXF: "
        f"stock_thickness={PLATE_THICKNESS_MM:.3f} mm, "
        f"flat_length={flat_pattern.total_length_mm:.3f} mm, "
        f"flat_width={flat_pattern.width_mm:.3f} mm, "
        f"bend_lines=({flat_pattern.bend_line_positions_mm[0]:.3f}, {flat_pattern.bend_line_positions_mm[1]:.3f}) mm, "
        "derived_from_topology=build_bracket()"
    )
    print(
        "DXF bend checks "
        f"top_flange_flat={flat_pattern.top_flange_flat_length_mm:.3f} mm, "
        f"return_flange_flat={flat_pattern.return_flange_flat_length_mm:.3f} mm, "
        f"feature_to_bend_min={flat_pattern.min_feature_to_bend_mm:.3f} mm, "
        f"feature_to_bend_required={SENDCUTSEND_HALF_DIE_WIDTH_MM:.3f} mm"
    )
    if flat_pattern.min_feature_to_bend_mm < SENDCUTSEND_HALF_DIE_WIDTH_MM:
        print(
            "Warning: flat-pattern features enter the bend die region by "
            f"{SENDCUTSEND_HALF_DIE_WIDTH_MM - flat_pattern.min_feature_to_bend_mm:.3f} mm"
        )
    return doc


def gen_step() -> dict[str, object]:
    return {
        "shape": build_bracket(),
    }


if __name__ == "__main__":
    gen_step()
