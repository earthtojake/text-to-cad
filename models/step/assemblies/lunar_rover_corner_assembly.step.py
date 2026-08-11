from __future__ import annotations

import math
from collections.abc import Iterable, Sequence

from build123d import *
from build123d import Shape
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt, gp_Trsf


DISPLAY_NAME = "Futuristic lunar rover wheel suspension corner"

# Coordinate convention:
# - millimeters
# - wheel axis is global Y
# - visible outside wheel face points toward negative Y
# - wheel center is fixed at X=0, Y=0, Z=80

WHEEL_CENTER = (0.0, 0.0, 80.0)
BASE_CENTER_X = -20.0
BASE_TOP_Z = 8.0

COLORS = {
    "dark_graphite": (0.005, 0.006, 0.007, 1.0),
    "matte_black": (0.002, 0.002, 0.002, 1.0),
    "satin_titanium": (0.42, 0.43, 0.40, 1.0),
    "pale_aluminum": (0.78, 0.80, 0.78, 1.0),
    "brushed_steel": (0.50, 0.52, 0.54, 1.0),
    "anodized_orange": (1.00, 0.34, 0.08, 1.0),
    "spring_orange": (1.00, 0.42, 0.02, 1.0),
    "brushed_aluminum": (0.66, 0.68, 0.66, 1.0),
    "fastener_steel": (0.18, 0.19, 0.20, 1.0),
}


Vector3 = tuple[float, float, float]


def v_add(a: Vector3, b: Vector3) -> Vector3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def v_sub(a: Vector3, b: Vector3) -> Vector3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def v_mul(a: Vector3, scalar: float) -> Vector3:
    return (a[0] * scalar, a[1] * scalar, a[2] * scalar)


def v_dot(a: Vector3, b: Vector3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def v_cross(a: Vector3, b: Vector3) -> Vector3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def v_len(a: Vector3) -> float:
    return math.sqrt(v_dot(a, a))


def v_norm(a: Vector3) -> Vector3:
    length = v_len(a)
    if length <= 1e-9:
        raise ValueError("zero-length vector")
    return (a[0] / length, a[1] / length, a[2] / length)


def style(shape: Shape, label: str, color_name: str) -> Shape:
    shape.label = label
    shape.color = Color(*COLORS[color_name])
    return shape


def group(label: str, children: Sequence[Shape], color_name: str | None = None) -> Compound:
    compound = Compound(obj=list(children), children=list(children), label=label)
    if color_name is not None:
        compound.color = Color(*COLORS[color_name])
    return compound


def transformed(shape: Shape, center: Vector3, axis_x: Vector3, axis_y: Vector3, axis_z: Vector3) -> Shape:
    x_dir = v_norm(axis_x)
    y_dir = v_norm(axis_y)
    z_dir = v_norm(axis_z)
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


def oriented_box(
    label: str,
    center: Vector3,
    size_x: float,
    size_y: float,
    size_z: float,
    axis_x: Vector3 = (1.0, 0.0, 0.0),
    axis_y: Vector3 = (0.0, 1.0, 0.0),
    axis_z: Vector3 = (0.0, 0.0, 1.0),
    color_name: str = "pale_aluminum",
    fillet_radius: float = 0.0,
) -> Shape:
    shape = transformed(Box(size_x, size_y, size_z), center, axis_x, axis_y, axis_z)
    if fillet_radius > 0.0:
        shape = softened(shape, fillet_radius)
    return style(shape, label, color_name)


def cylinder_between(label: str, p1: Vector3, p2: Vector3, radius: float, color_name: str) -> Shape:
    axis = v_sub(p2, p1)
    length = v_len(axis)
    if length <= 1e-6:
        return style(Sphere(radius).moved(Location(p1)), label, color_name)
    direction = v_norm(axis)
    wrapped = BRepPrimAPI_MakeCylinder(
        gp_Ax2(gp_Pnt(*p1), gp_Dir(*direction)),
        radius,
        length,
    ).Shape()
    return style(Shape(obj=wrapped), label, color_name)


def cylinder_x(label: str, center: Vector3, radius: float, length: float, color_name: str) -> Shape:
    return style(Cylinder(radius, length, rotation=(0, 90, 0)).moved(Location(center)), label, color_name)


def cylinder_y(label: str, center: Vector3, radius: float, length: float, color_name: str) -> Shape:
    return style(Cylinder(radius, length, rotation=(90, 0, 0)).moved(Location(center)), label, color_name)


def cylinder_z(label: str, center: Vector3, radius: float, length: float, color_name: str) -> Shape:
    return style(Cylinder(radius, length).moved(Location(center)), label, color_name)


def softened(shape: Shape, radius: float) -> Shape:
    # Small repeated pads, spokes, tubes, and bolts dominate export time if every
    # edge receives a true BREP fillet. Major machined bodies still get rounded
    # edges below; small bodies rely on cylindrical profiles and crisp bevel-like
    # proportions to keep the STEP robust.
    if radius < 0.95:
        return shape
    try:
        return fillet(shape.edges(), radius=radius)
    except Exception:
        try:
            return chamfer(shape.edges(), length=radius * 0.35)
        except Exception:
            return shape


def annular_y(label: str, center: Vector3, outer_radius: float, inner_radius: float, length: float, color_name: str) -> Shape:
    outer = Cylinder(outer_radius, length, rotation=(90, 0, 0)).moved(Location(center))
    inner = Cylinder(inner_radius, length + 4.0, rotation=(90, 0, 0)).moved(Location(center))
    return style(softened(outer - inner, 1.2), label, color_name)


def wheel_lattice() -> Compound:
    center = WHEEL_CENTER
    parts: list[Shape] = [
        annular_y("wheel_outer_rim_ring", center, 65.0, 56.0, 42.0, "dark_graphite"),
        annular_y("wheel_inner_rim_ring", center, 38.0, 25.0, 40.0, "dark_graphite"),
        style(Torus(65.0, 1.8, rotation=(90, 0, 0)).moved(Location((0.0, -21.4, 80.0))), "wheel_outer_bead_visible", "dark_graphite"),
        style(Torus(65.0, 1.8, rotation=(90, 0, 0)).moved(Location((0.0, 21.4, 80.0))), "wheel_outer_bead_inner", "dark_graphite"),
    ]

    for index in range(16):
        theta_inner = (2.0 * math.pi * index) / 16.0
        theta_outer = theta_inner + math.radians(5.0)
        p1 = (
            math.cos(theta_inner) * 19.0,
            -13.5,
            80.0 + math.sin(theta_inner) * 19.0,
        )
        p2 = (
            math.cos(theta_outer) * 56.0,
            13.5,
            80.0 + math.sin(theta_outer) * 56.0,
        )
        spoke = cylinder_between(f"wheel_angular_spoke_{index + 1:02d}", p1, p2, 2.8, "dark_graphite")
        parts.append(style(softened(spoke, 0.6), spoke.label or f"wheel_angular_spoke_{index + 1:02d}", "dark_graphite"))

    return group("wheel", parts, "dark_graphite")


def tread_elements() -> Compound:
    parts: list[Shape] = []
    rim_radius = 65.0
    tread_height = 5.0
    # The diagonal chevron bars have tangent-wise corners, so the pad center is
    # tucked slightly below the nominal 65 mm rim surface to keep the full tread
    # envelope close to the requested 140 mm outside diameter.
    radial_center = rim_radius + tread_height / 2.0 - 1.1
    long_size = math.hypot(18.0, 10.0)

    for index in range(32):
        theta = (2.0 * math.pi * index) / 32.0
        normal = (math.cos(theta), 0.0, math.sin(theta))
        tangent = (-math.sin(theta), 0.0, math.cos(theta))
        chevron_sign = 1.0 if index % 2 == 0 else -1.0
        for side_name, y_sign in (("outside", -1.0), ("inside", 1.0)):
            axis_x = v_norm(v_add(v_mul((0.0, 1.0, 0.0), y_sign * 18.0), v_mul(tangent, chevron_sign * 10.0)))
            axis_z = normal
            axis_y = v_norm(v_cross(axis_z, axis_x))
            center = v_add(
                WHEEL_CENTER,
                v_add(
                    v_mul(normal, radial_center),
                    v_add(v_mul((0.0, 1.0, 0.0), y_sign * 9.0), v_mul(tangent, chevron_sign * 5.0)),
                ),
            )
            pad = oriented_box(
                f"tread_chevron_{index + 1:02d}_{side_name}",
                center,
                long_size,
                5.8,
                tread_height,
                axis_x,
                axis_y,
                axis_z,
                "matte_black",
                fillet_radius=0.75,
            )
            parts.append(pad)
    return group("tire_tread_elements", parts, "matte_black")


def hub_and_axle() -> tuple[Shape, Compound]:
    hub = cylinder_y("central_hub", WHEEL_CENTER, 17.0, 50.0, "pale_aluminum")
    hub = style(softened(hub, 1.2), "central_hub", "pale_aluminum")

    axle_parts: list[Shape] = [
        cylinder_y("axle_stub", (0.0, 8.0, 80.0), 8.0, 78.0, "fastener_steel"),
        cylinder_y("visible_axle_cap", (0.0, -29.0, 80.0), 12.0, 6.0, "fastener_steel"),
    ]
    axle_parts = [style(softened(part, 0.6), part.label or "axle_part", "fastener_steel") for part in axle_parts]
    return hub, group("axle_hardware", axle_parts, "fastener_steel")


def brake_disc() -> Shape:
    disc = Cylinder(41.0, 5.0, rotation=(90, 0, 0)).moved(Location((0.0, 29.0, 80.0)))
    for index in range(24):
        theta = (2.0 * math.pi * index) / 24.0
        hole_center = (
            math.cos(theta) * 31.0,
            29.0,
            80.0 + math.sin(theta) * 31.0,
        )
        disc = disc - Cylinder(2.2, 8.0, rotation=(90, 0, 0)).moved(Location(hole_center))
    disc = softened(disc, 0.4)
    return style(disc, "brake_disc_82mm_vented", "brushed_steel")


def brake_caliper() -> Compound:
    angle = math.radians(42.0)
    radial = (math.cos(angle), 0.0, math.sin(angle))
    tangent = (-math.sin(angle), 0.0, math.cos(angle))
    base = v_add(WHEEL_CENTER, v_mul(radial, 45.0))
    parts = [
        oriented_box(
            "brake_caliper_outer_half",
            v_add(base, (0.0, 20.8, 0.0)),
            30.0,
            7.0,
            17.0,
            tangent,
            (0.0, 1.0, 0.0),
            radial,
            "anodized_orange",
            fillet_radius=2.0,
        ),
        oriented_box(
            "brake_caliper_inner_half",
            v_add(base, (0.0, 37.2, 0.0)),
            30.0,
            7.0,
            17.0,
            tangent,
            (0.0, 1.0, 0.0),
            radial,
            "anodized_orange",
            fillet_radius=2.0,
        ),
        oriented_box(
            "brake_caliper_bridge",
            v_add(WHEEL_CENTER, v_add(v_mul(radial, 53.0), (0.0, 29.0, 0.0))),
            28.0,
            18.0,
            5.5,
            tangent,
            (0.0, 1.0, 0.0),
            radial,
            "anodized_orange",
            fillet_radius=1.3,
        ),
    ]
    return group("brake_caliper", parts, "anodized_orange")


def upright() -> Compound:
    parts: list[Shape] = [
        oriented_box("upright_machined_web", (-18.0, 40.0, 80.0), 15.0, 18.0, 72.0, color_name="pale_aluminum", fillet_radius=1.5),
        oriented_box("upright_upper_fork_lug", (-10.0, 40.0, 111.0), 30.0, 20.0, 17.0, color_name="pale_aluminum", fillet_radius=1.5),
        oriented_box("upright_lower_fork_lug", (-10.0, 40.0, 49.0), 30.0, 20.0, 17.0, color_name="pale_aluminum", fillet_radius=1.5),
        annular_y("upright_central_bearing", (0.0, 40.0, 80.0), 19.0, 9.0, 20.0, "pale_aluminum"),
        cylinder_y("upright_upper_bushing", (-21.0, 40.0, 111.0), 6.5, 24.0, "satin_titanium"),
        cylinder_y("upright_lower_bushing", (-23.0, 40.0, 49.0), 6.5, 24.0, "satin_titanium"),
    ]
    return group("upright", parts, "pale_aluminum")


def bushing(label: str, center: Vector3, length: float = 15.0) -> Shape:
    return style(softened(cylinder_y(label, center, 6.2, length, "satin_titanium"), 0.5), label, "satin_titanium")


def control_arms() -> tuple[Compound, Compound]:
    upper_upright = (-21.0, 40.0, 111.0)
    upper_front = (-94.0, -16.0, 118.0)
    upper_rear = (-94.0, 52.0, 118.0)
    lower_upright = (-23.0, 40.0, 49.0)
    lower_front = (-94.0, -20.0, 45.0)
    lower_rear = (-94.0, 52.0, 45.0)

    upper_parts = [
        cylinder_between("upper_control_arm_front_tube", upper_front, upper_upright, 3.5, "satin_titanium"),
        cylinder_between("upper_control_arm_rear_tube", upper_rear, upper_upright, 3.5, "satin_titanium"),
        cylinder_between("upper_control_arm_cross_tube", upper_front, upper_rear, 2.8, "satin_titanium"),
        bushing("upper_front_chassis_bushing", upper_front),
        bushing("upper_rear_chassis_bushing", upper_rear),
        bushing("upper_upright_outer_bushing", upper_upright, 18.0),
    ]
    upper_parts = [
        style(softened(part, 0.45), part.label or "upper_control_arm_part", "satin_titanium")
        if "tube" in (part.label or "")
        else part
        for part in upper_parts
    ]

    lower_parts = [
        cylinder_between("lower_control_arm_front_tube", lower_front, lower_upright, 3.5, "satin_titanium"),
        cylinder_between("lower_control_arm_rear_tube", lower_rear, lower_upright, 3.5, "satin_titanium"),
        cylinder_between("lower_control_arm_cross_tube", lower_front, lower_rear, 2.8, "satin_titanium"),
        bushing("lower_front_chassis_bushing", lower_front),
        bushing("lower_rear_chassis_bushing", lower_rear),
        bushing("lower_upright_outer_bushing", lower_upright, 18.0),
    ]
    lower_parts = [
        style(softened(part, 0.45), part.label or "lower_control_arm_part", "satin_titanium")
        if "tube" in (part.label or "")
        else part
        for part in lower_parts
    ]

    return (
        group("upper_control_arm", upper_parts, "satin_titanium"),
        group("lower_control_arm", lower_parts, "satin_titanium"),
    )


def spring_along_axis(label: str, start: Vector3, end: Vector3) -> Compound:
    axis = v_sub(end, start)
    length = v_len(axis)
    axis_z = v_norm(axis)
    fallback = (0.0, 0.0, 1.0)
    if abs(v_dot(axis_z, fallback)) > 0.92:
        fallback = (1.0, 0.0, 0.0)
    axis_x = v_norm(v_cross(fallback, axis_z))
    axis_y = v_norm(v_cross(axis_z, axis_x))

    wire_radius = 1.5
    helix_radius = 10.5
    turns = 8
    segments_per_turn = 8
    total_segments = turns * segments_per_turn

    def helix_point(step: int) -> Vector3:
        angle = 2.0 * math.pi * turns * step / total_segments
        local = (
            math.cos(angle) * helix_radius,
            math.sin(angle) * helix_radius,
            length * step / total_segments,
        )
        return v_add(
            start,
            v_add(
                v_mul(axis_x, local[0]),
                v_add(v_mul(axis_y, local[1]), v_mul(axis_z, local[2])),
            ),
        )

    segments: list[Shape] = []
    previous = helix_point(0)
    for index in range(1, total_segments + 1):
        current = helix_point(index)
        segments.append(
            cylinder_between(
                f"{label}_segment_{index:02d}",
                previous,
                current,
                wire_radius,
                "spring_orange",
            )
        )
        previous = current
    return group(label, segments, "spring_orange")


def coilover_shock() -> Compound:
    top = (-90.0, -8.0, 118.0)
    bottom = (-48.0, -24.0, 58.0)
    axis = v_norm(v_sub(top, bottom))
    length = v_len(v_sub(top, bottom))
    damper_start = v_add(bottom, v_mul(axis, 9.0))
    damper_end = v_add(bottom, v_mul(axis, length * 0.62))
    rod_start = v_add(bottom, v_mul(axis, length * 0.52))
    rod_end = v_add(top, v_mul(axis, -7.0))
    spring_start = v_add(bottom, v_mul(axis, 7.0))
    spring_end = v_add(top, v_mul(axis, -7.0))

    parts = [
        cylinder_between("coilover_damper_body", damper_start, damper_end, 5.0, "brushed_steel"),
        cylinder_between("coilover_piston_rod", rod_start, rod_end, 2.5, "fastener_steel"),
        spring_along_axis("coilover_helical_spring_8_turns", spring_start, spring_end),
        cylinder_y("coilover_top_eyelet", top, 6.0, 14.0, "satin_titanium"),
        cylinder_y("coilover_lower_eyelet", bottom, 6.0, 14.0, "satin_titanium"),
    ]
    return group("coilover_shock", parts, "satin_titanium")


def triangular_cutout_tool(label: str, x_center: float, vertices_yz: Sequence[tuple[float, float]]) -> Shape:
    plane = Plane(origin=(x_center, 0.0, 0.0), x_dir=(0.0, 1.0, 0.0), z_dir=(1.0, 0.0, 0.0))
    with BuildPart() as tool:
        with BuildSketch(plane):
            Polygon(*vertices_yz)
        extrude(amount=13.0, both=True)
    tool.part.label = label
    return tool.part


def chassis_bulkhead() -> tuple[Shape, Compound]:
    plate = Box(8.0, 70.0, 95.0).moved(Location((-95.0, 20.0, 80.0)))
    cutouts = [
        triangular_cutout_tool("bulkhead_upper_triangular_cutout", -95.0, [(3.0, 86.0), (37.0, 86.0), (20.0, 117.0)]),
        triangular_cutout_tool("bulkhead_lower_triangular_cutout", -95.0, [(3.0, 74.0), (37.0, 74.0), (20.0, 43.0)]),
    ]
    for tool in cutouts:
        plate = plate - tool
    for y, z in [(3.0, 86.0), (37.0, 86.0), (20.0, 117.0), (3.0, 74.0), (37.0, 74.0), (20.0, 43.0)]:
        plate = plate - cylinder_x("bulkhead_cutout_corner_radius_tool", (-95.0, y, z), 5.0, 13.0, "pale_aluminum")
    plate = style(softened(plate, 1.0), "chassis_bulkhead", "pale_aluminum")

    supports = group(
        "bulkhead_display_support_blocks",
        [
            oriented_box("bulkhead_left_support_block", (-95.0, -8.0, 20.25), 17.0, 12.0, 24.5, color_name="brushed_aluminum", fillet_radius=1.0),
            oriented_box("bulkhead_right_support_block", (-95.0, 48.0, 20.25), 17.0, 12.0, 24.5, color_name="brushed_aluminum", fillet_radius=1.0),
        ],
        "brushed_aluminum",
    )
    return plate, supports


def countersunk_display_base() -> Shape:
    with BuildPart() as part:
        with BuildSketch():
            RectangleRounded(170.0, 110.0, 6.0)
        extrude(amount=8.0)
    base = part.part.moved(Location((BASE_CENTER_X, 0.0, 0.0)))
    hole_positions = [
        (BASE_CENTER_X - 70.0, -43.0),
        (BASE_CENTER_X + 70.0, -43.0),
        (BASE_CENTER_X - 70.0, 43.0),
        (BASE_CENTER_X + 70.0, 43.0),
    ]
    for x, y in hole_positions:
        base = base - Cylinder(3.2, 12.0).moved(Location((x, y, 4.0)))
        base = base - Cone(3.2, 6.4, 5.0).moved(Location((x, y, 6.3)))
    base = softened(base, 1.1)
    return style(base, "display_base_rounded_countersunk", "brushed_aluminum")


def fasteners() -> Compound:
    parts: list[Shape] = []
    for index in range(6):
        theta = (2.0 * math.pi * index) / 6.0
        center = (math.cos(theta) * 22.0, -28.5, 80.0 + math.sin(theta) * 22.0)
        parts.append(style(softened(cylinder_y(f"hub_bolt_{index + 1:02d}", center, 2.6, 5.0, "fastener_steel"), 0.35), f"hub_bolt_{index + 1:02d}", "fastener_steel"))

    caliper_bolt_centers = [
        v_add(WHEEL_CENTER, (23.0, 17.0, 44.0)),
        v_add(WHEEL_CENTER, (43.0, 17.0, 24.0)),
    ]
    for index, center in enumerate(caliper_bolt_centers, start=1):
        parts.append(style(softened(cylinder_y(f"caliper_socket_bolt_{index}", center, 2.2, 4.0, "fastener_steel"), 0.3), f"caliper_socket_bolt_{index}", "fastener_steel"))

    for index, (y, z) in enumerate(
        [
            (-16.0, 118.0),
            (52.0, 118.0),
            (-20.0, 45.0),
            (52.0, 45.0),
            (-8.0, 34.0),
            (48.0, 34.0),
            (-8.0, 126.0),
            (48.0, 126.0),
        ],
        start=1,
    ):
        parts.append(style(softened(cylinder_x(f"bulkhead_bolt_head_{index:02d}", (-89.6, y, z), 2.8, 3.2, "fastener_steel"), 0.25), f"bulkhead_bolt_head_{index:02d}", "fastener_steel"))
    return group("fasteners", parts, "fastener_steel")


def gen_step():
    upper_arm, lower_arm = control_arms()
    chassis_plate, support_blocks = chassis_bulkhead()
    hub, axle = hub_and_axle()
    children: list[Shape] = [
        countersunk_display_base(),
        support_blocks,
        wheel_lattice(),
        tread_elements(),
        hub,
        axle,
        brake_disc(),
        brake_caliper(),
        upright(),
        upper_arm,
        lower_arm,
        coilover_shock(),
        chassis_plate,
        fasteners(),
    ]
    return group("lunar_rover_wheel_suspension_corner", children)
