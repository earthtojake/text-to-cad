from __future__ import annotations

import math
from collections.abc import Sequence

from build123d import (
    Box,
    Color,
    Compound,
    Cone,
    Cylinder,
    Location,
    Shape,
    Sphere,
    Torus,
    chamfer,
    fillet,
    scale,
)
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt, gp_Trsf


DISPLAY_NAME = "Pelican riding a bicycle"

# Units: millimeters.
# Origin: halfway between the wheel hubs on the bicycle center plane.
# X: rear-to-front bicycle direction, Y: wheel axle direction, +Z: up.

COLORS = {
    "rubber_black": (0.003, 0.003, 0.003, 1.0),
    "rim_silver": (0.70, 0.72, 0.70, 1.0),
    "spoke_steel": (0.82, 0.84, 0.82, 1.0),
    "frame_blue": (0.05, 0.28, 0.75, 1.0),
    "seat_brown": (0.28, 0.12, 0.05, 1.0),
    "pelican_white": (0.96, 0.95, 0.88, 1.0),
    "wing_gray": (0.66, 0.68, 0.64, 1.0),
    "feather_dark": (0.08, 0.08, 0.075, 1.0),
    "bill_yellow": (1.00, 0.78, 0.26, 1.0),
    "pouch_orange": (0.95, 0.45, 0.12, 1.0),
    "leg_orange": (0.98, 0.50, 0.12, 1.0),
    "eye_black": (0.0, 0.0, 0.0, 1.0),
}

Vector3 = tuple[float, float, float]


def _v_add(a: Vector3, b: Vector3) -> Vector3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _v_sub(a: Vector3, b: Vector3) -> Vector3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _v_mul(a: Vector3, scalar: float) -> Vector3:
    return (a[0] * scalar, a[1] * scalar, a[2] * scalar)


def _v_dot(a: Vector3, b: Vector3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _v_cross(a: Vector3, b: Vector3) -> Vector3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _v_len(a: Vector3) -> float:
    return math.sqrt(_v_dot(a, a))


def _v_norm(a: Vector3) -> Vector3:
    length = _v_len(a)
    if length <= 1e-9:
        raise ValueError("zero-length vector")
    return (a[0] / length, a[1] / length, a[2] / length)


def _style(shape: Shape, label: str, color_name: str) -> Shape:
    shape.label = label
    shape.color = Color(*COLORS[color_name])
    return shape


def _group(label: str, children: Sequence[Shape], color_name: str | None = None) -> Compound:
    compound = Compound(obj=list(children), children=list(children), label=label)
    if color_name is not None:
        compound.color = Color(*COLORS[color_name])
    return compound


def _softened(shape: Shape, radius: float) -> Shape:
    try:
        return fillet(shape.edges(), radius=radius)
    except Exception:
        try:
            return chamfer(shape.edges(), length=radius * 0.45)
        except Exception:
            return shape


def _transformed(shape: Shape, center: Vector3, axis_x: Vector3, axis_y: Vector3, axis_z: Vector3) -> Shape:
    x_dir = _v_norm(axis_x)
    y_dir = _v_norm(axis_y)
    z_dir = _v_norm(axis_z)
    trsf = gp_Trsf()
    trsf.SetValues(
        x_dir[0],
        y_dir[0],
        z_dir[0],
        center[0],
        x_dir[1],
        y_dir[1],
        z_dir[1],
        center[1],
        x_dir[2],
        y_dir[2],
        z_dir[2],
        center[2],
    )
    return Shape(obj=BRepBuilderAPI_Transform(shape.wrapped, trsf, True).Shape())


def _oriented_box(
    label: str,
    center: Vector3,
    size_x: float,
    size_y: float,
    size_z: float,
    axis_x: Vector3,
    axis_y: Vector3,
    axis_z: Vector3,
    color_name: str,
    *,
    radius: float = 0.0,
) -> Shape:
    shape = _transformed(Box(size_x, size_y, size_z), center, axis_x, axis_y, axis_z)
    if radius > 0.0:
        shape = _softened(shape, radius)
    return _style(shape, label, color_name)


def _cylinder_between(label: str, p1: Vector3, p2: Vector3, radius: float, color_name: str) -> Shape:
    axis = _v_sub(p2, p1)
    length = _v_len(axis)
    if length <= 1e-6:
        return _style(Sphere(radius).moved(Location(p1)), label, color_name)
    direction = _v_norm(axis)
    wrapped = BRepPrimAPI_MakeCylinder(
        gp_Ax2(gp_Pnt(*p1), gp_Dir(*direction)),
        radius,
        length,
    ).Shape()
    return _style(Shape(obj=wrapped), label, color_name)


def _cylinder_y(label: str, center: Vector3, radius: float, length: float, color_name: str) -> Shape:
    return _style(Cylinder(radius, length, rotation=(90, 0, 0)).moved(Location(center)), label, color_name)


def _cylinder_x(label: str, center: Vector3, radius: float, length: float, color_name: str) -> Shape:
    return _style(Cylinder(radius, length, rotation=(0, 90, 0)).moved(Location(center)), label, color_name)


def _ellipsoid(label: str, center: Vector3, radii: Vector3, color_name: str) -> Shape:
    shape = scale(Sphere(1.0), by=radii).moved(Location(center))
    return _style(shape, label, color_name)


def _flat_cone_x(
    label: str,
    center: Vector3,
    length: float,
    base_radius: float,
    tip_radius: float,
    y_scale: float,
    z_scale: float,
    color_name: str,
) -> Shape:
    cone = Cone(base_radius, tip_radius, length, rotation=(0, 90, 0))
    shape = scale(cone, by=(1.0, y_scale, z_scale)).moved(Location(center))
    return _style(shape, label, color_name)


def _make_wheel(label: str, center: Vector3) -> Compound:
    cx, cy, cz = center
    tire_major_radius = 40.0
    tire_minor_radius = 4.0
    rim_radius = 31.0
    spoke_radius = 0.72
    hub_radius = 4.2
    spoke_count = 20

    parts: list[Shape] = [
        _style(
            Torus(tire_major_radius, tire_minor_radius, rotation=(90, 0, 0)).moved(Location(center)),
            f"{label}_continuous_black_tire",
            "rubber_black",
        ),
        _style(
            Torus(rim_radius, 1.45, rotation=(90, 0, 0)).moved(Location(center)),
            f"{label}_silver_rim",
            "rim_silver",
        ),
        _cylinder_y(f"{label}_hub_barrel", center, hub_radius, 14.0, "rim_silver"),
        _cylinder_y(f"{label}_hub_axle_pin", center, 1.8, 24.0, "spoke_steel"),
    ]

    for index in range(spoke_count):
        theta = index * math.tau / spoke_count
        rim_point = (cx + math.cos(theta) * (rim_radius - 1.8), cy, cz + math.sin(theta) * (rim_radius - 1.8))
        opposite_offset = -0.9 if index % 2 == 0 else 0.9
        hub_point = (cx, cy + opposite_offset, cz)
        parts.append(_cylinder_between(f"{label}_radial_spoke_{index + 1:02d}", hub_point, rim_point, spoke_radius, "spoke_steel"))

    return _group(label, parts)


def _make_bicycle() -> Compound:
    rear = (-55.0, 0.0, 44.0)
    front = (55.0, 0.0, 44.0)
    bottom = (0.0, 0.0, 49.0)
    seat_lug = (-15.0, 0.0, 86.0)
    head_low = (43.0, 0.0, 66.0)
    head_high = (38.0, 0.0, 88.0)
    handle_stem = (57.0, 0.0, 99.0)

    parts: list[Shape] = [
        _make_wheel("rear_wheel", rear),
        _make_wheel("front_wheel", front),
        _cylinder_between("frame_seat_tube", bottom, seat_lug, 2.3, "frame_blue"),
        _cylinder_between("frame_top_tube", seat_lug, head_high, 2.2, "frame_blue"),
        _cylinder_between("frame_down_tube", bottom, head_low, 2.5, "frame_blue"),
        _cylinder_between("frame_head_tube", head_low, head_high, 2.6, "frame_blue"),
        _cylinder_between("frame_left_chain_stay", (bottom[0], -4.2, bottom[2]), (rear[0], -4.2, rear[2]), 1.7, "frame_blue"),
        _cylinder_between("frame_right_chain_stay", (bottom[0], 4.2, bottom[2]), (rear[0], 4.2, rear[2]), 1.7, "frame_blue"),
        _cylinder_between("frame_left_seat_stay", (seat_lug[0], -3.8, seat_lug[2]), (rear[0], -3.8, rear[2]), 1.55, "frame_blue"),
        _cylinder_between("frame_right_seat_stay", (seat_lug[0], 3.8, seat_lug[2]), (rear[0], 3.8, rear[2]), 1.55, "frame_blue"),
        _cylinder_between("front_left_fork_blade", (head_low[0], -4.0, head_low[2]), (front[0], -4.0, front[2]), 1.7, "frame_blue"),
        _cylinder_between("front_right_fork_blade", (head_low[0], 4.0, head_low[2]), (front[0], 4.0, front[2]), 1.7, "frame_blue"),
        _cylinder_between("handlebar_stem", head_high, handle_stem, 1.8, "frame_blue"),
        _cylinder_y("handlebar_crossbar", (64.0, 0.0, 101.0), 1.6, 38.0, "frame_blue"),
        _cylinder_y("left_black_grip", (64.0, -22.5, 101.0), 2.2, 8.0, "rubber_black"),
        _cylinder_y("right_black_grip", (64.0, 22.5, 101.0), 2.2, 8.0, "rubber_black"),
        _cylinder_between("seat_post", seat_lug, (-17.0, 0.0, 95.0), 1.75, "spoke_steel"),
        _style(_softened(Box(24.0, 17.0, 5.0).moved(Location((-20.0, 0.0, 97.0))), 1.2), "brown_saddle", "seat_brown"),
        _style(Torus(7.5, 0.9, rotation=(90, 0, 0)).moved(Location(bottom)), "crank_ring", "spoke_steel"),
        _cylinder_y("bottom_bracket_axle", bottom, 3.3, 20.0, "rim_silver"),
    ]

    pedal_front = (12.5, -11.0, 38.5)
    pedal_back = (-12.5, 11.0, 60.5)
    parts.extend(
        [
            _cylinder_between("front_crank_arm", bottom, pedal_front, 1.0, "spoke_steel"),
            _cylinder_between("rear_crank_arm", bottom, pedal_back, 1.0, "spoke_steel"),
            _style(_softened(Box(15.0, 4.0, 2.5).moved(Location(pedal_front)), 0.7), "front_pedal_flat", "rubber_black"),
            _style(_softened(Box(15.0, 4.0, 2.5).moved(Location(pedal_back)), 0.7), "rear_pedal_flat", "rubber_black"),
        ]
    )

    return _group("bicycle", parts, "frame_blue")


def _make_pelican() -> Compound:
    parts: list[Shape] = [
        _ellipsoid("pelican_round_body", (-12.0, 0.0, 120.0), (24.0, 15.0, 29.0), "pelican_white"),
        _ellipsoid("pelican_chest_belly_highlight", (1.0, 0.0, 112.0), (18.0, 13.0, 20.0), "pelican_white"),
        _ellipsoid("left_folded_wing", (-22.0, -13.0, 120.0), (19.0, 3.2, 25.0), "wing_gray"),
        _ellipsoid("right_folded_wing", (-22.0, 13.0, 120.0), (19.0, 3.2, 25.0), "wing_gray"),
        _ellipsoid("left_dark_wing_tip", (-33.0, -15.7, 104.0), (12.0, 2.2, 10.0), "feather_dark"),
        _ellipsoid("right_dark_wing_tip", (-33.0, 15.7, 104.0), (12.0, 2.2, 10.0), "feather_dark"),
        _cylinder_between("curved_neck_lower_segment", (-1.0, 0.0, 139.0), (12.0, 0.0, 151.0), 5.0, "pelican_white"),
        _cylinder_between("curved_neck_upper_segment", (12.0, 0.0, 151.0), (24.0, 0.0, 157.0), 4.4, "pelican_white"),
        _ellipsoid("pelican_head", (28.0, 0.0, 160.0), (10.5, 8.1, 9.5), "pelican_white"),
        _flat_cone_x("long_upper_bill", (52.0, 0.0, 160.5), 48.0, 5.2, 1.1, 1.45, 0.55, "bill_yellow"),
        _ellipsoid("rounded_lower_bill_pouch", (49.0, 0.0, 151.5), (23.0, 7.0, 7.2), "pouch_orange"),
        _cylinder_between("dark_bill_seam_left", (31.0, -7.3, 156.2), (70.0, -2.7, 157.0), 0.45, "feather_dark"),
        _cylinder_between("dark_bill_seam_right", (31.0, 7.3, 156.2), (70.0, 2.7, 157.0), 0.45, "feather_dark"),
        _ellipsoid("left_eye", (31.5, -7.4, 162.8), (1.45, 0.75, 1.45), "eye_black"),
        _ellipsoid("right_eye", (31.5, 7.4, 162.8), (1.45, 0.75, 1.45), "eye_black"),
        _ellipsoid("soft_head_crest", (19.0, 0.0, 168.0), (4.0, 4.0, 5.0), "pelican_white"),
    ]

    tail_roots = [(-34.0, -4.5, 108.0), (-38.0, 0.0, 110.0), (-34.0, 4.5, 108.0)]
    for index, center in enumerate(tail_roots, start=1):
        parts.append(_ellipsoid(f"short_tail_feather_{index}", center, (11.0, 2.0, 5.2), "feather_dark"))

    # Bent orange legs and webbed feet make the bird visibly seated on the cycle.
    left_hip = (-8.0, -5.7, 96.0)
    left_knee = (2.5, -7.5, 74.0)
    left_pedal = (12.5, -11.0, 38.5)
    right_hip = (-13.0, 5.7, 96.0)
    right_knee = (-19.0, 8.4, 74.0)
    right_pedal = (-12.5, 11.0, 60.5)
    parts.extend(
        [
            _cylinder_between("left_upper_leg", left_hip, left_knee, 1.8, "leg_orange"),
            _cylinder_between("left_lower_leg", left_knee, left_pedal, 1.6, "leg_orange"),
            _cylinder_between("right_upper_leg", right_hip, right_knee, 1.8, "leg_orange"),
            _cylinder_between("right_lower_leg", right_knee, right_pedal, 1.6, "leg_orange"),
            _ellipsoid("left_webbed_foot_on_forward_pedal", _v_add(left_pedal, (1.5, 0.0, 2.0)), (8.5, 3.5, 2.2), "leg_orange"),
            _ellipsoid("right_webbed_foot_on_rear_pedal", _v_add(right_pedal, (-1.5, 0.0, 2.0)), (8.5, 3.5, 2.2), "leg_orange"),
        ]
    )

    feather_line_specs = [
        ("left_wing_feather_line_1", (-17.0, -16.2, 136.0), (-33.0, -16.2, 112.0)),
        ("left_wing_feather_line_2", (-11.0, -16.4, 126.0), (-34.0, -16.4, 101.0)),
        ("right_wing_feather_line_1", (-17.0, 16.2, 136.0), (-33.0, 16.2, 112.0)),
        ("right_wing_feather_line_2", (-11.0, 16.4, 126.0), (-34.0, 16.4, 101.0)),
    ]
    for label, p1, p2 in feather_line_specs:
        parts.append(_cylinder_between(label, p1, p2, 0.55, "feather_dark"))

    return _group("pelican", parts, "pelican_white")


def _make_ground_shadow() -> Compound:
    # Thin reference pads give the model a stable visual base without merging
    # into the wheels.
    front_pad = _style(_softened(Box(92.0, 28.0, 1.0).moved(Location((55.0, 0.0, -2.0))), 1.0), "front_wheel_ground_shadow", "rubber_black")
    rear_pad = _style(_softened(Box(92.0, 28.0, 1.0).moved(Location((-55.0, 0.0, -2.0))), 1.0), "rear_wheel_ground_shadow", "rubber_black")
    return _group("subtle_ground_shadow", [front_pad, rear_pad])


def gen_step() -> Compound:
    bicycle = _make_bicycle()
    pelican = _make_pelican()
    ground = _make_ground_shadow()
    assembly = _group("pelican_riding_bicycle", [bicycle, pelican, ground])
    assembly.label = "pelican_riding_bicycle"
    return assembly
