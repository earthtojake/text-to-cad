from __future__ import annotations

import math
from collections.abc import Sequence

from build123d import (
    Box,
    Color,
    Compound,
    Cylinder,
    Face,
    Location,
    Plane,
    Polygon,
    Shape,
    Torus,
    Wire,
    BuildPart,
    BuildSketch,
    chamfer,
    extrude,
    fillet,
    loft,
)
from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt


DISPLAY_NAME = "Roadable VTOL flying car concept"

# Units: millimeters.
# Origin: center of the road car cabin footprint.
# +X: forward/nose, +Y: driver-left/port side, +Z: up.

MODEL_LABEL = "roadable_vtol_flying_car_concept"

COLORS = {
    "pearl_body": (0.82, 0.86, 0.84, 1.0),
    "graphite": (0.03, 0.035, 0.04, 1.0),
    "dark_glass": (0.08, 0.16, 0.24, 0.58),
    "warm_lens": (1.0, 0.74, 0.28, 1.0),
    "red_lens": (0.95, 0.08, 0.05, 1.0),
    "titanium": (0.52, 0.56, 0.58, 1.0),
    "brushed_aluminum": (0.72, 0.74, 0.73, 1.0),
    "rotor_blue": (0.24, 0.42, 0.56, 1.0),
    "safety_orange": (1.0, 0.35, 0.06, 1.0),
    "rubber": (0.005, 0.006, 0.007, 1.0),
}

Vector3 = tuple[float, float, float]

BODY_STATIONS = [
    (-182.0, 48.0, 24.0, 43.0),
    (-146.0, 82.0, 39.0, 42.0),
    (-78.0, 102.0, 50.0, 42.0),
    (20.0, 104.0, 54.0, 43.0),
    (105.0, 82.0, 44.0, 43.0),
    (162.0, 42.0, 28.0, 43.0),
    (183.0, 10.0, 10.0, 43.0),
]

CANOPY_STATIONS = [
    (-62.0, 45.0, 10.0, 65.0),
    (-22.0, 56.0, 24.0, 72.0),
    (32.0, 52.0, 25.0, 72.0),
    (74.0, 30.0, 10.0, 65.0),
]

DUCT_OUTER_RADIUS = 48.0
DUCT_INNER_RADIUS = 36.0
DUCT_HEIGHT = 12.0
DUCT_Z = 58.0
DUCT_FRONT_X = 112.0
DUCT_REAR_X = -114.0
DUCT_CENTER_Y = 112.0
ROTOR_Z = DUCT_Z + 0.9


def style(shape: Shape, label: str, color_name: str) -> Shape:
    shape.label = label
    shape.color = Color(*COLORS[color_name])
    return shape


def group(label: str, children: Sequence[Shape], color_name: str | None = None) -> Compound:
    compound = Compound(obj=list(children), children=list(children), label=label)
    if color_name is not None:
        compound.color = Color(*COLORS[color_name])
    return compound


def softened(shape: Shape, radius: float) -> Shape:
    if radius <= 0.0:
        return shape
    try:
        return fillet(shape.edges(), radius=radius)
    except Exception:
        try:
            return chamfer(shape.edges(), length=radius * 0.35)
        except Exception:
            return shape


def superellipse_section(
    x_pos: float,
    width: float,
    height: float,
    z_center: float,
    *,
    exponent: float = 2.65,
    segments: int = 40,
) -> Face:
    points: list[Vector3] = []
    half_width = width / 2.0
    half_height = height / 2.0
    for index in range(segments):
        angle = 2.0 * math.pi * index / segments
        y_pos = math.copysign(abs(math.cos(angle)) ** (2.0 / exponent), math.cos(angle)) * half_width
        z_pos = z_center + math.copysign(abs(math.sin(angle)) ** (2.0 / exponent), math.sin(angle)) * half_height
        points.append((x_pos, y_pos, z_pos))
    return Face.make_surface(Wire.make_polygon(points, close=True))


def lofted_superellipse(label: str, stations: Sequence[tuple[float, float, float, float]], color_name: str) -> Shape:
    faces = [superellipse_section(*station) for station in stations]
    return style(softened(loft(faces, ruled=False), 0.75), label, color_name)


def cylinder_x(label: str, center: Vector3, radius: float, length: float, color_name: str) -> Shape:
    return style(Cylinder(radius, length, rotation=(0.0, 90.0, 0.0)).moved(Location(center)), label, color_name)


def cylinder_y(label: str, center: Vector3, radius: float, length: float, color_name: str) -> Shape:
    return style(Cylinder(radius, length, rotation=(90.0, 0.0, 0.0)).moved(Location(center)), label, color_name)


def cylinder_z(label: str, center: Vector3, radius: float, length: float, color_name: str) -> Shape:
    return style(Cylinder(radius, length).moved(Location(center)), label, color_name)


def cylinder_between(label: str, p1: Vector3, p2: Vector3, radius: float, color_name: str) -> Shape:
    axis = (p2[0] - p1[0], p2[1] - p1[1], p2[2] - p1[2])
    length = math.sqrt(axis[0] ** 2 + axis[1] ** 2 + axis[2] ** 2)
    direction = (axis[0] / length, axis[1] / length, axis[2] / length)
    wrapped = BRepPrimAPI_MakeCylinder(
        gp_Ax2(gp_Pnt(*p1), gp_Dir(*direction)),
        radius,
        length,
    ).Shape()
    return style(Shape(obj=wrapped), label, color_name)


def annular_z(label: str, center: Vector3, outer_radius: float, inner_radius: float, height: float, color_name: str) -> Shape:
    outer = Cylinder(outer_radius, height).moved(Location(center))
    inner = Cylinder(inner_radius, height + 3.0).moved(Location(center))
    return style(softened(outer - inner, 0.65), label, color_name)


def annular_x(label: str, center: Vector3, outer_radius: float, inner_radius: float, length: float, color_name: str) -> Shape:
    outer = Cylinder(outer_radius, length, rotation=(0.0, 90.0, 0.0)).moved(Location(center))
    inner = Cylinder(inner_radius, length + 3.0, rotation=(0.0, 90.0, 0.0)).moved(Location(center))
    return style(softened(outer - inner, 0.65), label, color_name)


def annular_y(label: str, center: Vector3, outer_radius: float, inner_radius: float, length: float, color_name: str) -> Shape:
    outer = Cylinder(outer_radius, length, rotation=(90.0, 0.0, 0.0)).moved(Location(center))
    inner = Cylinder(inner_radius, length + 3.0, rotation=(90.0, 0.0, 0.0)).moved(Location(center))
    return style(softened(outer - inner, 0.55), label, color_name)


def prism_from_xz(label: str, y_center: float, points_xz: Sequence[tuple[float, float]], thickness: float, color_name: str) -> Shape:
    faces = []
    for y_pos in (y_center - thickness / 2.0, y_center + thickness / 2.0):
        points = [(x_pos, y_pos, z_pos) for x_pos, z_pos in points_xz]
        faces.append(Face.make_surface(Wire.make_polygon(points, close=True)))
    return style(softened(loft(faces, ruled=True), 0.45), label, color_name)


def prism_from_yz(label: str, x_center: float, points_yz: Sequence[tuple[float, float]], thickness: float, color_name: str) -> Shape:
    faces = []
    for x_pos in (x_center - thickness / 2.0, x_center + thickness / 2.0):
        points = [(x_pos, y_pos, z_pos) for y_pos, z_pos in points_yz]
        faces.append(Face.make_surface(Wire.make_polygon(points, close=True)))
    return style(softened(loft(faces, ruled=True), 0.35), label, color_name)


def body_shell() -> Compound:
    fuselage = lofted_superellipse("one_piece_aero_road_car_fuselage", BODY_STATIONS, "pearl_body")
    belly = style(
        softened(Box(225.0, 42.0, 8.0).moved(Location((-18.0, 0.0, 18.0))), 1.2),
        "flat_structural_battery_spine",
        "graphite",
    )
    canopy = lofted_superellipse("teardrop_panoramic_canopy", CANOPY_STATIONS, "dark_glass")

    splitter = style(
        softened(Box(42.0, 54.0, 3.6).moved(Location((172.0, 0.0, 32.0))), 0.8),
        "front_aero_splitter_under_nose",
        "graphite",
    )
    rear_diffuser = style(
        softened(Box(58.0, 68.0, 5.0).moved(Location((-167.0, 0.0, 27.0))), 0.8),
        "rear_diffuser_plane",
        "graphite",
    )

    lights = [
        cylinder_x("left_warm_headlamp", (184.0, 17.5, 43.5), 4.2, 3.4, "warm_lens"),
        cylinder_x("right_warm_headlamp", (184.0, -17.5, 43.5), 4.2, 3.4, "warm_lens"),
        cylinder_x("left_rear_marker_lamp", (-184.0, 28.0, 42.0), 3.2, 3.4, "red_lens"),
        cylinder_x("right_rear_marker_lamp", (-184.0, -28.0, 42.0), 3.2, 3.4, "red_lens"),
    ]

    return group(
        "aero_car_body",
        [fuselage, belly, canopy, splitter, rear_diffuser, *lights],
        "pearl_body",
    )


def wing_panel(label: str, side: float) -> Shape:
    base_points = [
        (74.0, 43.0),
        (96.0, 138.0),
        (-92.0, 128.0),
        (-66.0, 43.0),
    ]
    points = [(x_pos, side * y_pos) for x_pos, y_pos in base_points]
    if side < 0:
        points = list(reversed(points))
    with BuildPart() as wing:
        with BuildSketch(Plane.XY):
            Polygon(points, align=None)
        extrude(amount=5.2)
    panel = wing.part.moved(Location((0.0, 0.0, 51.5)))
    return style(softened(panel, 0.7), label, "brushed_aluminum")


def stabilizers() -> Compound:
    fin_profile = [(-174.0, 54.0), (-129.0, 55.0), (-114.0, 108.0), (-166.0, 91.0)]
    return group(
        "twin_rear_vertical_stabilizers",
        [
            prism_from_xz("port_vertical_tail_fin", 36.0, fin_profile, 5.0, "safety_orange"),
            prism_from_xz("starboard_vertical_tail_fin", -36.0, fin_profile, 5.0, "safety_orange"),
        ],
        "safety_orange",
    )


def lifting_wings() -> Compound:
    center_fairing = style(
        softened(Box(120.0, 96.0, 7.0).moved(Location((-2.0, 0.0, 53.0))), 1.0),
        "flush_wing_centerbox_between_ducts",
        "brushed_aluminum",
    )
    return group(
        "folding_lifting_wing_set",
        [
            center_fairing,
            wing_panel("port_deployable_lifting_wing", 1.0),
            wing_panel("starboard_deployable_lifting_wing", -1.0),
            stabilizers(),
        ],
        "brushed_aluminum",
    )


def rotor_blade_z(label: str, center: Vector3, angle_deg: float, color_name: str) -> Shape:
    root_radius = 9.0
    tip_radius = DUCT_INNER_RADIUS - 4.0
    root_width = 9.0
    tip_width = 4.4
    angle = math.radians(angle_deg)
    radial = (math.cos(angle), math.sin(angle))
    tangent = (-math.sin(angle), math.cos(angle))

    corners = []
    for distance, half_width in (
        (root_radius, root_width / 2.0),
        (tip_radius, tip_width / 2.0),
        (tip_radius, -tip_width / 2.0),
        (root_radius, -root_width / 2.0),
    ):
        corners.append(
            (
                center[0] + radial[0] * distance + tangent[0] * half_width,
                center[1] + radial[1] * distance + tangent[1] * half_width,
            )
        )
    with BuildPart() as blade:
        with BuildSketch(Plane.XY):
            Polygon(corners, align=None)
        extrude(amount=1.8)
    return style(blade.part.moved(Location((0.0, 0.0, center[2] - 0.9))), label, color_name)


def lift_duct_module(label: str, center: Vector3, front: bool, side: float) -> Compound:
    duct_label = "front" if front else "rear"
    side_label = "port" if side > 0 else "starboard"
    parts: list[Shape] = [
        annular_z(f"{side_label}_{duct_label}_protective_lift_duct_ring", center, DUCT_OUTER_RADIUS, DUCT_INNER_RADIUS, DUCT_HEIGHT, "graphite"),
        style(
            Torus(DUCT_OUTER_RADIUS - 2.4, 1.3).moved(Location((center[0], center[1], center[2] + DUCT_HEIGHT / 2.0))),
            f"{side_label}_{duct_label}_upper_guard_lip",
            "titanium",
        ),
        cylinder_z(f"{side_label}_{duct_label}_rotor_hub", (center[0], center[1], ROTOR_Z), 8.5, 6.0, "titanium"),
    ]

    for index in range(6):
        parts.append(
            rotor_blade_z(
                f"{side_label}_{duct_label}_lift_rotor_blade_{index + 1}",
                (center[0], center[1], ROTOR_Z + 1.6),
                index * 60.0 + (15.0 if front else -15.0),
                "rotor_blue",
            )
        )

    for index, angle_deg in enumerate((0.0, 90.0, 180.0, 270.0), start=1):
        angle = math.radians(angle_deg)
        p1 = (center[0], center[1], center[2])
        p2 = (
            center[0] + math.cos(angle) * (DUCT_INNER_RADIUS - 2.0),
            center[1] + math.sin(angle) * (DUCT_INNER_RADIUS - 2.0),
            center[2],
        )
        parts.append(cylinder_between(f"{side_label}_{duct_label}_duct_cross_strut_{index}", p1, p2, 1.8, "titanium"))

    body_attach = (center[0] + (-31.0 if front else 31.0), side * 50.0, center[2] - 3.0)
    parts.append(cylinder_between(f"{side_label}_{duct_label}_faired_duct_boom", body_attach, center, 4.8, "brushed_aluminum"))
    return group(label, parts, "graphite")


def lift_system() -> Compound:
    duct_centers = [
        ("port_front_lift_fan_module", (DUCT_FRONT_X, DUCT_CENTER_Y, DUCT_Z), True, 1.0),
        ("starboard_front_lift_fan_module", (DUCT_FRONT_X, -DUCT_CENTER_Y, DUCT_Z), True, -1.0),
        ("port_rear_lift_fan_module", (DUCT_REAR_X, DUCT_CENTER_Y, DUCT_Z), False, 1.0),
        ("starboard_rear_lift_fan_module", (DUCT_REAR_X, -DUCT_CENTER_Y, DUCT_Z), False, -1.0),
    ]
    return group(
        "quad_tilt_lift_duct_system",
        [lift_duct_module(label, center, front, side) for label, center, front, side in duct_centers],
        "graphite",
    )


def rear_blade_x(label: str, center: Vector3, angle_deg: float) -> Shape:
    root_radius = 7.0
    tip_radius = 20.5
    root_width = 6.0
    tip_width = 2.8
    angle = math.radians(angle_deg)
    radial = (math.cos(angle), math.sin(angle))
    tangent = (-math.sin(angle), math.cos(angle))
    points: list[tuple[float, float]] = []
    for distance, half_width in (
        (root_radius, root_width / 2.0),
        (tip_radius, tip_width / 2.0),
        (tip_radius, -tip_width / 2.0),
        (root_radius, -root_width / 2.0),
    ):
        y_pos = center[1] + radial[0] * distance + tangent[0] * half_width
        z_pos = center[2] + radial[1] * distance + tangent[1] * half_width
        points.append((y_pos, z_pos))
    return prism_from_yz(label, center[0], points, 1.8, "rotor_blue")


def rear_thruster() -> Compound:
    center = (-201.0, 0.0, 56.0)
    parts: list[Shape] = [
        annular_x("rear_cruise_thrust_duct", center, 27.0, 20.5, 28.0, "graphite"),
        cylinder_x("rear_cruise_rotor_hub", center, 6.0, 16.0, "titanium"),
        cylinder_between("upper_rear_thruster_pylon", (-174.0, 0.0, 61.0), (-190.0, 0.0, 72.0), 3.4, "brushed_aluminum"),
        cylinder_between("lower_rear_thruster_pylon", (-174.0, 0.0, 39.0), (-190.0, 0.0, 42.0), 3.0, "brushed_aluminum"),
    ]
    for index in range(7):
        parts.append(rear_blade_x(f"rear_cruise_propulsor_blade_{index + 1}", center, index * 360.0 / 7.0 + 8.0))
    return group("rear_cruise_propulsor", parts, "graphite")


def wheel_module(label: str, x_pos: float, side: float) -> Compound:
    y_pos = side * 61.0
    wheel_center = (x_pos, y_pos, 20.0)
    side_label = "port" if side > 0 else "starboard"
    axle_end = (x_pos, side * 45.0, 20.0)
    fairing = style(
        softened(Box(37.0, 17.0, 14.0).moved(Location((x_pos, side * 52.0, 31.0))), 2.0),
        f"{side_label}_{label}_flush_retractable_wheel_fairing",
        "pearl_body",
    )
    parts = [
        fairing,
        cylinder_between(f"{side_label}_{label}_short_axle", axle_end, wheel_center, 3.4, "titanium"),
        annular_y(f"{side_label}_{label}_low_profile_tire", wheel_center, 20.0, 11.0, 12.0, "rubber"),
        cylinder_y(f"{side_label}_{label}_silver_wheel_hub", wheel_center, 7.0, 15.0, "brushed_aluminum"),
    ]
    return group(f"{side_label}_{label}_road_wheel_module", parts, "rubber")


def road_gear() -> Compound:
    return group(
        "retractable_road_wheel_set",
        [
            wheel_module("front", 108.0, 1.0),
            wheel_module("front", 108.0, -1.0),
            wheel_module("rear", -105.0, 1.0),
            wheel_module("rear", -105.0, -1.0),
        ],
        "rubber",
    )


def gen_step():
    return group(
        MODEL_LABEL,
        [
            body_shell(),
            lifting_wings(),
            lift_system(),
            rear_thruster(),
            road_gear(),
        ],
    )
