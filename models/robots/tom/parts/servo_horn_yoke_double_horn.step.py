from __future__ import annotations

import sys
from pathlib import Path

import build123d

V2_DIR = Path(__file__).resolve().parents[1]
PARTS_DIR = V2_DIR / "parts"
for path in (V2_DIR, PARTS_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import link_common as lc
from robot_common.step_entry import load_step_entry

servo_horn_yoke = load_step_entry("servo_horn_yoke")


PART_NAME = Path(__file__).stem
DISPLAY_NAME = "Double Servo Horn Yoke Horn"

SIDE_BY_SIDE_CLEARANCE_MM = 2.0
SERVO_CENTER_SPACING_Y_MM = (2.0 * abs(lc.SERVO_REAR_EXTREME_LOCAL_Y_MM)) + SIDE_BY_SIDE_CLEARANCE_MM
SERVO_CENTER_OFFSET_Y_MM = 0.5 * SERVO_CENTER_SPACING_Y_MM
YOKE_SINGLE_HALF_WIDTH_Z_MM = 10.5

SHEET_THICKNESS_MM = lc.SHEET_THICKNESS_MM
CUT_EXTENSION_MM = 2.0
M3_CLEARANCE_RADIUS_MM = servo_horn_yoke.M3_CLEARANCE_RADIUS_MM
HORN_CENTER_CLEARANCE_RADIUS_MM = servo_horn_yoke.HORN_CENTER_CLEARANCE_RADIUS_MM
HORN_SCREW_CIRCLE_RADIUS_MM = lc.SERVO_HORN_SCREW_CIRCLE_RADIUS_MM
BOTTOM_FACE_SLOT_WIDTH_MM = servo_horn_yoke.BOTTOM_FACE_SLOT_WIDTH_MM
BOTTOM_FACE_SLOT_BEND_EDGE_CLEARANCE_MM = servo_horn_yoke.BOTTOM_FACE_SLOT_BEND_EDGE_CLEARANCE_MM
BOTTOM_FACE_SLOT_END_GAP_MM = servo_horn_yoke.BOTTOM_FACE_SLOT_END_GAP_MM

WEB_OUTER_X_MM = (
    lc.SERVO_SHAFT_LOCAL_X_MM
    - servo_horn_yoke.YOKE_HORN_AXIS_TO_WEB_OUTER_LENGTH_MM
)
WEB_INNER_X_MM = WEB_OUTER_X_MM + SHEET_THICKNESS_MM
HORN_AXIS_X_MM = lc.SERVO_SHAFT_LOCAL_X_MM
HORN_FLANGE_END_X_MM = HORN_AXIS_X_MM + servo_horn_yoke.HORN_CAP_FLANGE_RADIUS_MM

OUTPUT_HORN_FACE_Y_MM = lc.SERVO_OUTPUT_HORN_FACE_LOCAL_Y_MM

REAR_SERVO_CENTER_Y_MM = -SERVO_CENTER_OFFSET_Y_MM
FRONT_SERVO_CENTER_Y_MM = SERVO_CENTER_OFFSET_Y_MM
REAR_OUTER_HORN_FACE_Y_MM = REAR_SERVO_CENTER_Y_MM - OUTPUT_HORN_FACE_Y_MM
FRONT_OUTER_HORN_FACE_Y_MM = FRONT_SERVO_CENTER_Y_MM + OUTPUT_HORN_FACE_Y_MM
WEB_PATTERN_CENTER_Y_MM = 0.5 * (REAR_OUTER_HORN_FACE_Y_MM + FRONT_OUTER_HORN_FACE_Y_MM)

Z_MIN_MM = -YOKE_SINGLE_HALF_WIDTH_Z_MM
Z_MAX_MM = YOKE_SINGLE_HALF_WIDTH_Z_MM
HORN_PATTERN_CENTER_Z_MM = 0.0


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


def _make_box(*, x_min: float, x_max: float, y_min: float, y_max: float, z_min: float, z_max: float) -> build123d.Solid:
    return build123d.Solid.make_box(
        x_max - x_min,
        y_max - y_min,
        z_max - z_min,
        plane=build123d.Plane(origin=build123d.Vector(x_min, y_min, z_min)),
    )


def _face_from_wire(wire: build123d.Wire) -> build123d.Face:
    return build123d.Face(wire)


def _assemble_wire(edges: list[build123d.Edge]) -> build123d.Wire:
    wires = list(build123d.Wire.combine(edges))
    if len(wires) != 1:
        raise RuntimeError(f"Expected a single assembled wire, found {len(wires)}")
    return wires[0]


def _make_channel_body() -> build123d.Shape:
    rear_outer_y = REAR_OUTER_HORN_FACE_Y_MM - SHEET_THICKNESS_MM
    output_outer_y = FRONT_OUTER_HORN_FACE_Y_MM + SHEET_THICKNESS_MM

    body: build123d.Shape = _make_box(
        x_min=WEB_OUTER_X_MM,
        x_max=WEB_INNER_X_MM,
        y_min=rear_outer_y,
        y_max=output_outer_y,
        z_min=Z_MIN_MM,
        z_max=Z_MAX_MM,
    )
    body = body.fuse(
        _make_capped_horn_flange(
            y_min=rear_outer_y,
            y_max=REAR_OUTER_HORN_FACE_Y_MM,
        )
    )
    body = body.fuse(
        _make_capped_horn_flange(
            y_min=FRONT_OUTER_HORN_FACE_Y_MM,
            y_max=output_outer_y,
        )
    )
    return body


def _make_capped_horn_flange(*, y_min: float, y_max: float) -> build123d.Shape:
    cap_radius = servo_horn_yoke.HORN_CAP_FLANGE_RADIUS_MM
    slot_radius = servo_horn_yoke.HORN_FORK_SLOT_RADIUS_MM
    cap_z_min = HORN_PATTERN_CENTER_Z_MM - HORN_SCREW_CIRCLE_RADIUS_MM - cap_radius
    cap_z_max = HORN_PATTERN_CENTER_Z_MM + HORN_SCREW_CIRCLE_RADIUS_MM + cap_radius

    flange: build123d.Shape = _make_box(
        x_min=WEB_INNER_X_MM,
        x_max=HORN_AXIS_X_MM,
        y_min=y_min,
        y_max=y_max,
        z_min=cap_z_min,
        z_max=cap_z_max,
    )
    for cap_z in (
        HORN_PATTERN_CENTER_Z_MM - HORN_SCREW_CIRCLE_RADIUS_MM,
        HORN_PATTERN_CENTER_Z_MM + HORN_SCREW_CIRCLE_RADIUS_MM,
    ):
        cap = _make_cylinder_along(
            radius=cap_radius,
            height=y_max - y_min,
            origin=build123d.Vector(HORN_AXIS_X_MM, y_min, cap_z),
            direction=build123d.Vector(0.0, 1.0, 0.0),
        )
        flange = flange.fuse(cap)

    fork_slot = _make_cylinder_along(
        radius=slot_radius,
        height=(y_max - y_min) + (2.0 * CUT_EXTENSION_MM),
        origin=build123d.Vector(
            HORN_AXIS_X_MM,
            y_min - CUT_EXTENSION_MM,
            HORN_PATTERN_CENTER_Z_MM,
        ),
        direction=build123d.Vector(0.0, 1.0, 0.0),
    )
    return flange.cut(fork_slot)


def _horn_face_m3_holes() -> tuple[tuple[float, float, float], ...]:
    return (
        (
            HORN_AXIS_X_MM - HORN_SCREW_CIRCLE_RADIUS_MM,
            HORN_PATTERN_CENTER_Z_MM,
            M3_CLEARANCE_RADIUS_MM,
        ),
        (
            HORN_AXIS_X_MM,
            HORN_PATTERN_CENTER_Z_MM - HORN_SCREW_CIRCLE_RADIUS_MM,
            M3_CLEARANCE_RADIUS_MM,
        ),
        (
            HORN_AXIS_X_MM,
            HORN_PATTERN_CENTER_Z_MM + HORN_SCREW_CIRCLE_RADIUS_MM,
            M3_CLEARANCE_RADIUS_MM,
        ),
    )


def _web_holes(center_y: float) -> tuple[tuple[float, float, float], ...]:
    circle = HORN_SCREW_CIRCLE_RADIUS_MM
    return (
        (
            center_y,
            HORN_PATTERN_CENTER_Z_MM,
            HORN_CENTER_CLEARANCE_RADIUS_MM,
        ),
        (
            center_y - circle,
            HORN_PATTERN_CENTER_Z_MM,
            M3_CLEARANCE_RADIUS_MM,
        ),
        (
            center_y + circle,
            HORN_PATTERN_CENTER_Z_MM,
            M3_CLEARANCE_RADIUS_MM,
        ),
        (
            center_y,
            HORN_PATTERN_CENTER_Z_MM - circle,
            M3_CLEARANCE_RADIUS_MM,
        ),
        (
            center_y,
            HORN_PATTERN_CENTER_Z_MM + circle,
            M3_CLEARANCE_RADIUS_MM,
        ),
    )


def _double_horn_mount_holes(face_y: float) -> tuple[tuple[build123d.Vector, float], ...]:
    circle = HORN_SCREW_CIRCLE_RADIUS_MM
    return (
        (
            build123d.Vector(HORN_AXIS_X_MM - circle, face_y, HORN_PATTERN_CENTER_Z_MM),
            M3_CLEARANCE_RADIUS_MM,
        ),
        (
            build123d.Vector(HORN_AXIS_X_MM + circle, face_y, HORN_PATTERN_CENTER_Z_MM),
            M3_CLEARANCE_RADIUS_MM,
        ),
        (
            build123d.Vector(HORN_AXIS_X_MM, face_y, HORN_PATTERN_CENTER_Z_MM - circle),
            M3_CLEARANCE_RADIUS_MM,
        ),
        (
            build123d.Vector(HORN_AXIS_X_MM, face_y, HORN_PATTERN_CENTER_Z_MM + circle),
            M3_CLEARANCE_RADIUS_MM,
        ),
    )


def _horn_mount_spec(name: str, face_y: float) -> servo_horn_yoke.HornMountSpec:
    bbox = _make_box(
        x_min=WEB_OUTER_X_MM,
        x_max=HORN_FLANGE_END_X_MM,
        y_min=face_y,
        y_max=face_y + SHEET_THICKNESS_MM,
        z_min=Z_MIN_MM,
        z_max=Z_MAX_MM,
    ).bounding_box()
    return servo_horn_yoke.HornMountSpec(
        name=name,
        mount_face_y=face_y,
        mount_face_center=build123d.Vector(HORN_AXIS_X_MM, face_y, HORN_PATTERN_CENTER_Z_MM),
        mount_face_bbox=bbox,
        half_width_z=YOKE_SINGLE_HALF_WIDTH_Z_MM,
        center_clearance_radius=HORN_CENTER_CLEARANCE_RADIUS_MM,
        mount_holes=_double_horn_mount_holes(face_y),
    )


def _bottom_face_slot() -> tuple[float, float, float, float]:
    center_x = (
        WEB_INNER_X_MM
        + BOTTOM_FACE_SLOT_BEND_EDGE_CLEARANCE_MM
        + (0.5 * BOTTOM_FACE_SLOT_WIDTH_MM)
    )
    slot_z_min = Z_MIN_MM + BOTTOM_FACE_SLOT_END_GAP_MM
    slot_z_max = Z_MAX_MM - BOTTOM_FACE_SLOT_END_GAP_MM
    slot_length = slot_z_max - slot_z_min
    if slot_length <= BOTTOM_FACE_SLOT_WIDTH_MM:
        raise ValueError(
            "Double yoke bottom-face slot does not have enough length across "
            "the flange width after applying the flange-end gaps"
        )
    return (
        center_x,
        0.5 * (slot_z_min + slot_z_max),
        slot_length,
        BOTTOM_FACE_SLOT_WIDTH_MM,
    )


def _make_y_slot_cut(
    *,
    center_x: float,
    center_z: float,
    length: float,
    width: float,
    y_min: float,
    y_max: float,
) -> build123d.Shape:
    radius = 0.5 * width
    half_straight = 0.5 * length - radius
    y_start = y_min - CUT_EXTENSION_MM
    y_height = (y_max - y_min) + (2.0 * CUT_EXTENSION_MM)
    body: build123d.Shape = _make_box(
        x_min=center_x - radius,
        x_max=center_x + radius,
        y_min=y_start,
        y_max=y_start + y_height,
        z_min=center_z - half_straight,
        z_max=center_z + half_straight,
    )
    for end_z in (center_z - half_straight, center_z + half_straight):
        cap = _make_cylinder_along(
            radius=radius,
            height=y_height,
            origin=build123d.Vector(center_x, y_start, end_z),
            direction=build123d.Vector(0.0, 1.0, 0.0),
        )
        body = body.fuse(cap)
    return body


def _cut_horn_face_holes(shape: build123d.Shape) -> build123d.Shape:
    cut_height = SHEET_THICKNESS_MM + (2.0 * CUT_EXTENSION_MM)
    for face_y, direction_y in (
        (REAR_OUTER_HORN_FACE_Y_MM - SHEET_THICKNESS_MM - CUT_EXTENSION_MM, 1.0),
        (FRONT_OUTER_HORN_FACE_Y_MM - CUT_EXTENSION_MM, 1.0),
    ):
        for center_x, center_z, radius in _horn_face_m3_holes():
            cutter = _make_cylinder_along(
                radius=radius,
                height=cut_height,
                origin=build123d.Vector(center_x, face_y, center_z),
                direction=build123d.Vector(0.0, direction_y, 0.0),
            )
            shape = shape.cut(cutter)
    return shape


def _cut_outer_horn_slots(shape: build123d.Shape) -> build123d.Shape:
    center_x, center_z, length, width = _bottom_face_slot()
    for y_min, y_max in (
        (
            REAR_OUTER_HORN_FACE_Y_MM - SHEET_THICKNESS_MM,
            REAR_OUTER_HORN_FACE_Y_MM,
        ),
        (
            FRONT_OUTER_HORN_FACE_Y_MM,
            FRONT_OUTER_HORN_FACE_Y_MM + SHEET_THICKNESS_MM,
        ),
    ):
        shape = shape.cut(
            _make_y_slot_cut(
                center_x=center_x,
                center_z=center_z,
                length=length,
                width=width,
                y_min=y_min,
                y_max=y_max,
            )
        )
    return shape


def _cut_web_holes(shape: build123d.Shape) -> build123d.Shape:
    cut_height = SHEET_THICKNESS_MM + (2.0 * CUT_EXTENSION_MM)
    start_x = WEB_OUTER_X_MM - CUT_EXTENSION_MM
    for center_y, center_z, radius in _web_holes(WEB_PATTERN_CENTER_Y_MM):
        cutter = _make_cylinder_along(
            radius=radius,
            height=cut_height,
            origin=build123d.Vector(start_x, center_y, center_z),
            direction=build123d.Vector(1.0, 0.0, 0.0),
        )
        shape = shape.cut(cutter)
    return shape


def build_step() -> build123d.Shape:
    horn = _make_channel_body()
    horn = _cut_horn_face_holes(horn)
    horn = _cut_outer_horn_slots(horn)
    horn = _cut_web_holes(horn)

    solids = horn.solids()
    if len(solids) != 1:
        raise RuntimeError(f"Expected one connected double horn solid, found {len(solids)}")

    horn.label = PART_NAME
    horn.color = lc.BRACKET_COLOR

    bb = horn.bounding_box()
    _slot_center_x, _slot_center_z, slot_length, slot_width = _bottom_face_slot()
    print(
        f"{DISPLAY_NAME}: "
        f"servo_center_spacing_y={SERVO_CENTER_SPACING_Y_MM:.3f} mm, "
        f"span_y={bb.size.Y:.3f} mm, "
        f"span_z={bb.size.Z:.3f} mm, "
        f"web_face_x={WEB_INNER_X_MM:.4f} mm, "
        f"thickness={SHEET_THICKNESS_MM:.4f} mm, "
        f"horn_patterns=2, "
        f"outer_horn_slots=2x{slot_length:.3f}x{slot_width:.3f} mm"
    )
    return horn


def build_dxf():
    front_horn = _horn_mount_spec("double_front_horn", FRONT_OUTER_HORN_FACE_Y_MM)
    rear_horn = _horn_mount_spec("double_rear_horn", REAR_OUTER_HORN_FACE_Y_MM)
    layout, _cap_radius = servo_horn_yoke._build_layout(
        WEB_INNER_X_MM,
        sheet_half_width_z=YOKE_SINGLE_HALF_WIDTH_Z_MM,
        upper_horn=front_horn,
        lower_horn=rear_horn,
        rule=servo_horn_yoke.SHEET_RULE,
    )
    flat_pattern, metrics = servo_horn_yoke.build_flat_pattern(
        WEB_INNER_X_MM,
        sheet_half_width_z=YOKE_SINGLE_HALF_WIDTH_Z_MM,
        upper_horn=front_horn,
        lower_horn=rear_horn,
        rule=servo_horn_yoke.SHEET_RULE,
    )
    doc = servo_horn_yoke._topology_flat_pattern_dxf(
        build_step(),
        layout,
        flat_pattern,
        upper_horn=front_horn,
        lower_horn=rear_horn,
        rule=servo_horn_yoke.SHEET_RULE,
    )
    print(
        f"{DISPLAY_NAME} DXF: "
        f"length={flat_pattern.total_length_mm:.3f} mm, "
        f"width={flat_pattern.width_mm:.3f} mm, "
        f"bend_lines=({flat_pattern.bend_line_positions_mm[0]:.3f}, "
        f"{flat_pattern.bend_line_positions_mm[1]:.3f}) mm, "
        f"round_holes={len(flat_pattern.round_hole_profiles)}, "
        f"slots={len(flat_pattern.slot_profiles)}, "
        f"flange_flat_min={metrics.min_flange_flat_length_mm:.3f} mm, "
        f"slot_edge_to_bend_min={metrics.min_slot_edge_to_bend_mm:.3f} mm"
    )
    return doc


def gen_step() -> dict[str, object]:
    return {
        "shape": build_step(),
    }


if __name__ == "__main__":
    gen_step()
