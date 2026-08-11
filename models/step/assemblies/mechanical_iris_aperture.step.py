from __future__ import annotations

from math import cos, degrees, radians, sin, tau
from typing import Iterable

from build123d import (
    Align,
    Box,
    BuildPart,
    BuildSketch,
    Color,
    Compound,
    Cone,
    Cylinder,
    Location,
    Locations,
    Mode,
    Plane,
    Polygon,
    RegularPolygon,
    chamfer,
    extrude,
    fillet,
)


# Units: millimeters.
# Origin: center of the aperture on the Z axis.
# XY: ring/blade plane viewed from above. +Z: stack direction upward.

MODEL_LABEL = "mechanical_iris_aperture_assembly"

BRUSHED_STEEL = Color(0.64, 0.67, 0.68, 1.0)
STEEL_HIGHLIGHT = Color(0.76, 0.78, 0.78, 1.0)
GRAPHITE = Color(0.0, 0.0, 0.0, 1.0)
BRASS = Color(0.95, 0.68, 0.25, 1.0)
GUNMETAL = Color(0.13, 0.15, 0.17, 1.0)
DARK_GRAY = Color(0.06, 0.065, 0.07, 1.0)
APERTURE_BLACK = Color(0.0, 0.0, 0.0, 1.0)

BASE_OD = 160.0
BASE_ID = 52.0
BASE_THICKNESS = 8.0
BASE_TOP_Z = BASE_THICKNESS
BASE_MOUNT_HOLE_COUNT = 6
BASE_MOUNT_HOLE_DIAMETER = 5.0
BASE_MOUNT_BCD = 130.0
BASE_COUNTERSINK_TOP_DIAMETER = 10.5
BASE_COUNTERSINK_DEPTH = 2.4

RETAINING_ROOT_OD = 150.0
RETAINING_TOOTH_TIP_OD = 154.0
RETAINING_ID = 70.0
RETAINING_Z_BOTTOM = 8.0
RETAINING_Z_TOP = 13.0
RETAINING_HEIGHT = RETAINING_Z_TOP - RETAINING_Z_BOTTOM
RETAINING_TEETH = 120

BLADE_COUNT = 12
BLADE_THICKNESS = 1.2
BLADE_Z_BOTTOM = 13.05
BLADE_Z_STAGGER = 0.15
BLADE_INNER_NOSE_RADIUS = 18.0
BLADE_NOMINAL_INNER_RADIUS = 24.0
BLADE_OUTER_RADIUS = 68.0
BLADE_SPAN_DEGREES = 38.0
BLADE_PIVOT_RADIUS = 62.0
BLADE_PIVOT_LOCAL_ANGLE = radians(13.0)
BLADE_PIVOT_HOLE_DIAMETER = 3.0
BLADE_DRIVE_PIN_RADIUS = 46.0
BLADE_DRIVE_PIN_LOCAL_ANGLE = radians(-8.0)

ACTUATING_OD = 138.0
ACTUATING_ID = 86.0
ACTUATING_Z_BOTTOM = 14.0
ACTUATING_Z_TOP = 17.0
ACTUATING_HEIGHT = ACTUATING_Z_TOP - ACTUATING_Z_BOTTOM
CAM_SLOT_RADIUS = BLADE_DRIVE_PIN_RADIUS
CAM_SLOT_LENGTH = 18.0
CAM_SLOT_WIDTH = 4.0

FRONT_SCREW_COUNT = 6
FRONT_SCREW_BCD = 120.0
FRONT_SCREW_HEAD_DIAMETER = 7.0
FRONT_SCREW_HEAD_HEIGHT = 3.0


def _polar_point(radius: float, angle: float) -> tuple[float, float]:
    return (radius * cos(angle), radius * sin(angle))


def _offset_point(
    radius: float,
    angle: float,
    tangent_offset: float,
) -> tuple[float, float]:
    radial_x, radial_y = cos(angle), sin(angle)
    tangent_x, tangent_y = -sin(angle), cos(angle)
    return (
        radius * radial_x + tangent_offset * tangent_x,
        radius * radial_y + tangent_offset * tangent_y,
    )


def _set_metadata(part, label: str, color: Color):
    part.label = label
    part.color = color
    return part


def _safe_chamfer(part, edges: Iterable, length: float):
    selected = list(edges)
    if not selected:
        return part
    try:
        return chamfer(selected, length=length)
    except Exception:
        return part


def _safe_fillet(part, edges: Iterable, radius: float):
    selected = list(edges)
    if not selected:
        return part
    try:
        return fillet(selected, radius=radius)
    except Exception:
        return part


def _circular_edges(
    part,
    *,
    radius: float | None = None,
    coordinate: float | None = None,
    axis: str = "z",
    tolerance: float = 0.06,
):
    edges = []
    for edge in part.edges():
        try:
            edge_radius = edge.radius
            edge_center = edge.arc_center
            edge_normal = edge.normal()
        except Exception:
            continue

        if radius is not None and abs(edge_radius - radius) > tolerance:
            continue

        components = {"x": abs(edge_normal.X), "y": abs(edge_normal.Y), "z": abs(edge_normal.Z)}
        if components[axis] < 1.0 - 1e-4:
            continue

        if coordinate is not None:
            coord = {"x": edge_center.X, "y": edge_center.Y, "z": edge_center.Z}[axis]
            if abs(coord - coordinate) > tolerance:
                continue

        edges.append(edge)

    return edges


def _edges_at_z(part, z_value: float, *, tolerance: float = 0.04):
    edges = []
    for edge in part.edges():
        bbox = edge.bounding_box()
        if abs(bbox.min.Z - z_value) <= tolerance and abs(bbox.max.Z - z_value) <= tolerance:
            edges.append(edge)
    return edges


def _tooth_profile(
    *,
    teeth: int,
    root_radius: float,
    tip_radius: float,
    phase: float = 0.0,
    root_span_fraction: float = 0.72,
    tip_span_fraction: float = 0.34,
) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    pitch_angle = tau / teeth

    for tooth_index in range(teeth):
        center_angle = phase + tooth_index * pitch_angle
        points.extend(
            (
                _polar_point(root_radius, center_angle - root_span_fraction * pitch_angle / 2.0),
                _polar_point(tip_radius, center_angle - tip_span_fraction * pitch_angle / 2.0),
                _polar_point(tip_radius, center_angle + tip_span_fraction * pitch_angle / 2.0),
                _polar_point(root_radius, center_angle + root_span_fraction * pitch_angle / 2.0),
            )
        )

    return points


def _tick_rectangle_points(angle: float, inner_radius: float, outer_radius: float, width: float):
    tangent_x, tangent_y = -sin(angle), cos(angle)
    p1 = _polar_point(inner_radius, angle)
    p2 = _polar_point(outer_radius, angle)
    half_width = width / 2.0
    return [
        (p1[0] - tangent_x * half_width, p1[1] - tangent_y * half_width),
        (p2[0] - tangent_x * half_width, p2[1] - tangent_y * half_width),
        (p2[0] + tangent_x * half_width, p2[1] + tangent_y * half_width),
        (p1[0] + tangent_x * half_width, p1[1] + tangent_y * half_width),
    ]


def _make_base_ring():
    with BuildPart() as base:
        Cylinder(
            radius=BASE_OD / 2.0,
            height=BASE_THICKNESS,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
        )

        with Locations(Location((0.0, 0.0, -0.75))):
            Cylinder(
                radius=BASE_ID / 2.0,
                height=BASE_THICKNESS + 1.5,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
                mode=Mode.SUBTRACT,
            )

        for index in range(BASE_MOUNT_HOLE_COUNT):
            x_pos, y_pos = _polar_point(BASE_MOUNT_BCD / 2.0, tau * index / BASE_MOUNT_HOLE_COUNT)
            with Locations(Location((x_pos, y_pos, -0.75))):
                Cylinder(
                    radius=BASE_MOUNT_HOLE_DIAMETER / 2.0,
                    height=BASE_THICKNESS + 1.5,
                    align=(Align.CENTER, Align.CENTER, Align.MIN),
                    mode=Mode.SUBTRACT,
                )
            with Locations(Location((x_pos, y_pos, BASE_TOP_Z - BASE_COUNTERSINK_DEPTH))):
                Cone(
                    bottom_radius=BASE_MOUNT_HOLE_DIAMETER / 2.0,
                    top_radius=BASE_COUNTERSINK_TOP_DIAMETER / 2.0,
                    height=BASE_COUNTERSINK_DEPTH + 0.2,
                    align=(Align.CENTER, Align.CENTER, Align.MIN),
                    mode=Mode.SUBTRACT,
                )

        with BuildSketch(Plane.XY.offset(BASE_TOP_Z - 0.22)):
            for index in range(72):
                angle = tau * index / 72
                major = index % 6 == 0
                inner_radius = 76.0 if major else 77.2
                outer_radius = 79.35
                width = 0.72 if major else 0.44
                Polygon(_tick_rectangle_points(angle, inner_radius, outer_radius, width), align=None)
        extrude(amount=0.36, mode=Mode.SUBTRACT)

    part = base.part
    chamfer_edges = []
    for radius in (BASE_OD / 2.0, BASE_ID / 2.0):
        chamfer_edges.extend(_circular_edges(part, radius=radius, coordinate=0.0))
        chamfer_edges.extend(_circular_edges(part, radius=radius, coordinate=BASE_THICKNESS))
    part = _safe_chamfer(part, chamfer_edges, 1.0)
    return _set_metadata(part, "base_ring_annular_disk_160od_52id_countersunk", BRUSHED_STEEL)


def _make_tick_marks() -> list[object]:
    ticks = []
    for index in range(72):
        angle = tau * index / 72
        major = index % 6 == 0
        inner_radius = 76.0 if major else 77.2
        outer_radius = 79.35
        width = 0.72 if major else 0.44
        with BuildPart() as tick:
            with BuildSketch(Plane.XY.offset(BASE_TOP_Z - 0.18)):
                Polygon(_tick_rectangle_points(angle, inner_radius, outer_radius, width), align=None)
            extrude(amount=0.12)
        ticks.append(_set_metadata(tick.part, f"dark_engraved_radial_tick_{index + 1:02d}", DARK_GRAY))
    return ticks


def _make_retaining_ring():
    root_radius = RETAINING_ROOT_OD / 2.0
    tip_radius = RETAINING_TOOTH_TIP_OD / 2.0

    with BuildPart() as retaining:
        with BuildSketch(Plane.XY.offset(RETAINING_Z_BOTTOM)):
            Polygon(
                _tooth_profile(
                    teeth=RETAINING_TEETH,
                    root_radius=root_radius,
                    tip_radius=tip_radius,
                    phase=-tau / RETAINING_TEETH / 2.0,
                    root_span_fraction=0.72,
                    tip_span_fraction=0.34,
                ),
                align=None,
            )
        extrude(amount=RETAINING_HEIGHT)

        with Locations(Location((0.0, 0.0, RETAINING_Z_BOTTOM - 0.5))):
            Cylinder(
                radius=RETAINING_ID / 2.0,
                height=RETAINING_HEIGHT + 1.0,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
                mode=Mode.SUBTRACT,
            )

    part = retaining.part
    outer_chamfers = []
    outer_chamfers.extend(_edges_at_z(part, RETAINING_Z_BOTTOM))
    outer_chamfers.extend(_edges_at_z(part, RETAINING_Z_TOP))
    part = _safe_chamfer(part, outer_chamfers, 0.45)
    return _set_metadata(part, "front_retaining_ring_120_external_teeth_150od_70id", STEEL_HIGHLIGHT)


def _blade_outline_points(center_angle: float) -> list[tuple[float, float]]:
    local_points: list[tuple[float, float]] = []

    for step in range(10):
        local_angle = radians(-BLADE_SPAN_DEGREES / 2.0) + radians(BLADE_SPAN_DEGREES) * step / 9
        local_points.append((BLADE_OUTER_RADIUS, local_angle))

    local_points.extend(
        (
            (54.0, radians(18.8)),
            (36.0, radians(18.2)),
            (BLADE_NOMINAL_INNER_RADIUS, radians(18.0)),
            (20.0, radians(17.5)),
            (BLADE_INNER_NOSE_RADIUS, radians(14.5)),
            (BLADE_INNER_NOSE_RADIUS, radians(10.5)),
            (BLADE_INNER_NOSE_RADIUS, radians(6.5)),
            (BLADE_INNER_NOSE_RADIUS, radians(2.5)),
            (BLADE_INNER_NOSE_RADIUS, radians(-1.5)),
            (BLADE_INNER_NOSE_RADIUS, radians(-5.5)),
            (BLADE_INNER_NOSE_RADIUS, radians(-9.5)),
            (BLADE_INNER_NOSE_RADIUS, radians(-13.5)),
            (20.0, radians(-16.8)),
            (BLADE_NOMINAL_INNER_RADIUS, radians(-18.0)),
            (38.0, radians(-18.4)),
            (56.0, radians(-18.8)),
        )
    )

    return [_polar_point(radius, center_angle + local_angle) for radius, local_angle in local_points]


def _blade_pivot_center(blade_angle: float) -> tuple[float, float]:
    return _polar_point(BLADE_PIVOT_RADIUS, blade_angle + BLADE_PIVOT_LOCAL_ANGLE)


def _blade_drive_pin_center(blade_angle: float) -> tuple[float, float]:
    return _polar_point(BLADE_DRIVE_PIN_RADIUS, blade_angle + BLADE_DRIVE_PIN_LOCAL_ANGLE)


def _make_iris_blade(index: int):
    blade_angle = tau * index / BLADE_COUNT
    z_bottom = BLADE_Z_BOTTOM + index * BLADE_Z_STAGGER
    pivot_x, pivot_y = _blade_pivot_center(blade_angle)

    with BuildPart() as blade:
        with BuildSketch(Plane.XY.offset(z_bottom)):
            Polygon(_blade_outline_points(blade_angle), align=None)
        extrude(amount=BLADE_THICKNESS)

        with Locations(Location((pivot_x, pivot_y, z_bottom - 0.2))):
            Cylinder(
                radius=BLADE_PIVOT_HOLE_DIAMETER / 2.0,
                height=BLADE_THICKNESS + 0.4,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
                mode=Mode.SUBTRACT,
            )

    part = blade.part
    part = _safe_chamfer(part, part.edges(), 0.28)
    return _set_metadata(part, f"iris_blade_{index + 1:02d}_matte_black_graphite", GRAPHITE)


def _curved_slot_points(center_angle: float) -> list[tuple[float, float]]:
    half_angle = (CAM_SLOT_LENGTH / CAM_SLOT_RADIUS) / 2.0
    inner_radius = CAM_SLOT_RADIUS - CAM_SLOT_WIDTH / 2.0
    outer_radius = CAM_SLOT_RADIUS + CAM_SLOT_WIDTH / 2.0
    start_angle = center_angle - half_angle
    end_angle = center_angle + half_angle

    points = []
    for step in range(8):
        angle = start_angle + (end_angle - start_angle) * step / 7
        points.append(_polar_point(outer_radius, angle))
    for step in range(7, -1, -1):
        angle = start_angle + (end_angle - start_angle) * step / 7
        points.append(_polar_point(inner_radius, angle))
    return points


def _make_actuating_ring():
    with BuildPart() as actuator:
        with Locations(Location((0.0, 0.0, ACTUATING_Z_BOTTOM))):
            Cylinder(
                radius=ACTUATING_OD / 2.0,
                height=ACTUATING_HEIGHT,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
            )
        with Locations(Location((0.0, 0.0, ACTUATING_Z_BOTTOM - 0.5))):
            Cylinder(
                radius=ACTUATING_ID / 2.0,
                height=ACTUATING_HEIGHT + 1.0,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
                mode=Mode.SUBTRACT,
            )

        with BuildSketch(Plane.XY.offset(ACTUATING_Z_BOTTOM - 0.2)):
            for index in range(BLADE_COUNT):
                blade_angle = tau * index / BLADE_COUNT
                slot_angle = blade_angle + BLADE_DRIVE_PIN_LOCAL_ANGLE
                Polygon(_curved_slot_points(slot_angle), align=None)
        extrude(amount=ACTUATING_HEIGHT + 0.4, mode=Mode.SUBTRACT)

    part = actuator.part
    chamfer_edges = []
    for radius in (ACTUATING_OD / 2.0, ACTUATING_ID / 2.0):
        chamfer_edges.extend(_circular_edges(part, radius=radius, coordinate=ACTUATING_Z_BOTTOM))
        chamfer_edges.extend(_circular_edges(part, radius=radius, coordinate=ACTUATING_Z_TOP))
    part = _safe_chamfer(part, chamfer_edges, 0.8)
    return _set_metadata(part, "actuating_ring_12_curved_cam_slots_138od_86id", BRUSHED_STEEL)


def _make_pivot_screw(index: int):
    blade_angle = tau * index / BLADE_COUNT
    x_pos, y_pos = _blade_pivot_center(blade_angle)
    shaft_height = ACTUATING_Z_TOP - BLADE_Z_BOTTOM + 0.2
    head_height = 1.6

    with BuildPart() as screw:
        Cylinder(
            radius=1.25,
            height=shaft_height,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
        )
        with Locations(Location((0.0, 0.0, shaft_height))):
            Cylinder(
                radius=2.5,
                height=head_height,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
            )
        with BuildSketch(Plane.XY.offset(shaft_height + head_height - 0.72)):
            RegularPolygon(radius=1.35, side_count=6, major_radius=True, rotation=30.0)
        extrude(amount=0.82, mode=Mode.SUBTRACT)

    part = screw.part
    head_edges = []
    head_edges.extend(_circular_edges(part, radius=2.5, coordinate=shaft_height))
    head_edges.extend(_circular_edges(part, radius=2.5, coordinate=shaft_height + head_height))
    part = _safe_fillet(part, head_edges, 0.35)
    part = part.moved(Location((x_pos, y_pos, BLADE_Z_BOTTOM - 0.1)))
    return _set_metadata(part, f"pivot_screw_{index + 1:02d}_brass_head_and_shaft", BRASS)


def _make_drive_pin(index: int):
    blade_angle = tau * index / BLADE_COUNT
    x_pos, y_pos = _blade_drive_pin_center(blade_angle)

    with BuildPart() as pin:
        Cylinder(
            radius=1.3,
            height=ACTUATING_Z_TOP - BLADE_Z_BOTTOM + 0.75,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
        )

    part = pin.part
    part = _safe_fillet(part, _circular_edges(part, radius=1.3, coordinate=ACTUATING_Z_TOP - BLADE_Z_BOTTOM + 0.75), 0.45)
    part = part.moved(Location((x_pos, y_pos, BLADE_Z_BOTTOM - 0.05)))
    return _set_metadata(part, f"drive_pin_{index + 1:02d}_brass_cam_follower", BRASS)


def _make_front_socket_screw(index: int):
    angle = tau * index / FRONT_SCREW_COUNT + radians(30.0)
    x_pos, y_pos = _polar_point(FRONT_SCREW_BCD / 2.0, angle)
    shaft_radius = 2.5
    shaft_height = ACTUATING_Z_TOP - RETAINING_Z_BOTTOM + 0.2
    head_radius = FRONT_SCREW_HEAD_DIAMETER / 2.0
    socket_depth = 1.45

    with BuildPart() as screw:
        Cylinder(
            radius=shaft_radius,
            height=shaft_height,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
        )
        with Locations(Location((0.0, 0.0, shaft_height))):
            Cylinder(
                radius=head_radius,
                height=FRONT_SCREW_HEAD_HEIGHT,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
            )
        with BuildSketch(Plane.XY.offset(shaft_height + FRONT_SCREW_HEAD_HEIGHT - socket_depth)):
            RegularPolygon(radius=2.05, side_count=6, major_radius=True, rotation=30.0)
        extrude(amount=socket_depth + 0.15, mode=Mode.SUBTRACT)

    part = screw.part
    head_edges = []
    head_edges.extend(_circular_edges(part, radius=head_radius, coordinate=shaft_height))
    head_edges.extend(_circular_edges(part, radius=head_radius, coordinate=shaft_height + FRONT_SCREW_HEAD_HEIGHT))
    part = _safe_fillet(part, head_edges, 0.5)
    part = part.moved(Location((x_pos, y_pos, RETAINING_Z_BOTTOM - 0.1)))
    return _set_metadata(part, f"front_socket_head_cap_screw_{index + 1:02d}_gunmetal", GUNMETAL)


def _make_aperture_shadow():
    with BuildPart() as shadow:
        with Locations(Location((0.0, 0.0, BLADE_Z_BOTTOM - 0.22))):
            Cylinder(
                radius=18.0,
                height=0.12,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
            )
    return _set_metadata(shadow.part, "dark_central_aperture_void_36mm_visual_shadow", APERTURE_BLACK)


def gen_step():
    """Return a labeled mechanical iris aperture assembly in millimeters."""
    parts = [
        _make_aperture_shadow(),
        _make_base_ring(),
        *_make_tick_marks(),
        _make_retaining_ring(),
    ]

    for index in range(BLADE_COUNT):
        parts.append(_make_iris_blade(index))

    parts.append(_make_actuating_ring())

    for index in range(BLADE_COUNT):
        parts.append(_make_drive_pin(index))
        parts.append(_make_pivot_screw(index))

    for index in range(FRONT_SCREW_COUNT):
        parts.append(_make_front_socket_screw(index))

    assembly = Compound(
        obj=parts,
        children=parts,
        label=MODEL_LABEL,
    )
    return assembly
