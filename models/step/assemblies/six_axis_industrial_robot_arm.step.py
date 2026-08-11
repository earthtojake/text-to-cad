from math import atan2, cos, degrees, radians, sin, tau

from build123d import (
    Align,
    Box,
    BuildPart,
    BuildSketch,
    Circle,
    Color,
    Compound,
    Cone,
    Cylinder,
    Edge,
    Location,
    Locations,
    Mode,
    Plane,
    Polygon,
    RectangleRounded,
    add,
    extrude,
    fillet,
    sweep,
)


# Units: millimeters.
# Origin: axis 1/base yaw center at X=0, Y=0. XY is the floor/display plane, +Z is up.
# Static display pose: raised shoulder, bent elbow, compact 3-axis wrist reaching mostly +X.

DISPLAY_BASE_LENGTH = 180.0
DISPLAY_BASE_WIDTH = 140.0
DISPLAY_BASE_THICKNESS = 12.0
DISPLAY_BASE_CENTER = (60.0, 0.0, 0.0)

FIXED_BASE_DIAMETER = 82.0
FIXED_BASE_BOTTOM_Z = 12.0
FIXED_BASE_TOP_Z = 42.0

TURNTABLE_DIAMETER = 72.0
TURNTABLE_BOTTOM_Z = 42.0
TURNTABLE_TOP_Z = 58.0

SHOULDER_CENTER = (0.0, 0.0, 90.0)
ELBOW_CENTER = (74.0, 0.0, 142.0)
WRIST_ROLL_CENTER = (154.0, 0.0, 128.0)
WRIST_PITCH_CENTER = (174.0, 0.0, 128.0)
TOOL_ROLL_CENTER = (196.0, 0.0, 128.0)
TOOL_FLANGE_CENTER = (216.0, 0.0, 128.0)

MATTE_WHITE = Color(0.91, 0.92, 0.90, 1.0)
LIGHT_GRAY = Color(0.73, 0.76, 0.76, 1.0)
DARK_GRAPHITE = Color(0.10, 0.11, 0.12, 1.0)
DEEP_GRAPHITE = Color(0.045, 0.048, 0.052, 1.0)
BRUSHED_STEEL = Color(0.74, 0.76, 0.76, 1.0)
DARK_STEEL = Color(0.24, 0.25, 0.26, 1.0)
BLUE_ACCENT = Color(0.02, 0.30, 0.82, 1.0)
ORANGE_ACCENT = Color(1.0, 0.46, 0.10, 1.0)
MATTE_BLACK = Color(0.005, 0.006, 0.007, 1.0)


def _set_metadata(part, label: str, color: Color):
    part.label = label
    part.color = color
    return part


def _safe_fillet(edges, radius: float) -> None:
    selected = list(edges)
    if not selected:
        return
    try:
        fillet(selected, radius=radius)
    except Exception:
        pass


def _axis_rotation(axis: str) -> tuple[float, float, float]:
    if axis == "x":
        return (0.0, 90.0, 0.0)
    if axis == "y":
        return (90.0, 0.0, 0.0)
    return (0.0, 0.0, 0.0)


def _make_axis_cylinder(
    label: str,
    axis: str,
    center: tuple[float, float, float],
    radius: float,
    length: float,
    color: Color,
    fillet_radius: float = 0.0,
):
    with BuildPart() as cyl:
        Cylinder(
            radius=radius,
            height=length,
            align=(Align.CENTER, Align.CENTER, Align.CENTER),
        )
        if fillet_radius > 0.0:
            _safe_fillet(cyl.edges(), fillet_radius)
    part = cyl.part.moved(Location(center, _axis_rotation(axis)))
    return _set_metadata(part, label, color)


def _make_axis_ring(
    label: str,
    axis: str,
    center: tuple[float, float, float],
    outer_radius: float,
    inner_radius: float,
    thickness: float,
    color: Color,
):
    with BuildPart() as ring:
        Cylinder(
            radius=outer_radius,
            height=thickness,
            align=(Align.CENTER, Align.CENTER, Align.CENTER),
        )
        Cylinder(
            radius=inner_radius,
            height=thickness + 0.4,
            align=(Align.CENTER, Align.CENTER, Align.CENTER),
            mode=Mode.SUBTRACT,
        )
        _safe_fillet(ring.edges(), 0.25)
    part = ring.part.moved(Location(center, _axis_rotation(axis)))
    return _set_metadata(part, label, color)


def _make_screw_head(
    label: str,
    axis: str,
    center: tuple[float, float, float],
    radius: float,
    height: float,
    color: Color = BRUSHED_STEEL,
):
    with BuildPart() as screw:
        Cylinder(
            radius=radius,
            height=height,
            align=(Align.CENTER, Align.CENTER, Align.CENTER),
        )
        with Locations(Location((0.0, 0.0, height / 2.0 - 0.18))):
            Cylinder(
                radius=radius * 0.43,
                height=0.45,
                align=(Align.CENTER, Align.CENTER, Align.CENTER),
                mode=Mode.SUBTRACT,
            )
        _safe_fillet(screw.edges(), min(0.5, radius * 0.22))
    part = screw.part.moved(Location(center, _axis_rotation(axis)))
    return _set_metadata(part, label, color)


def _make_rounded_box(
    label: str,
    size: tuple[float, float, float],
    center: tuple[float, float, float],
    radius: float,
    color: Color,
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0),
):
    with BuildPart() as box:
        Box(*size, align=(Align.CENTER, Align.CENTER, Align.CENTER))
        if radius > 0.0:
            _safe_fillet(box.edges(), radius)
    part = box.part.moved(Location(center, rotation))
    return _set_metadata(part, label, color)


def _rounded_plate_profile_points(
    x_min: float,
    x_max: float,
    z_min: float,
    z_max: float,
    radius: float,
    steps: int = 8,
) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    centers = (
        (x_max - radius, z_min + radius, -90.0, 0.0),
        (x_max - radius, z_max - radius, 0.0, 90.0),
        (x_min + radius, z_max - radius, 90.0, 180.0),
        (x_min + radius, z_min + radius, 180.0, 270.0),
    )
    for cx, cz, start, end in centers:
        for step in range(steps + 1):
            angle = radians(start + (end - start) * step / steps)
            points.append((cx + radius * cos(angle), cz + radius * sin(angle)))
    return points


def _outer_rect_edges(part, length: float, width: float, z_min: float, z_max: float, tol: float = 0.08):
    edges = []
    for edge in part.edges():
        bbox = edge.bounding_box()
        center = bbox.center()
        on_outer_x = abs(abs(center.X) - length / 2.0) <= tol
        on_outer_y = abs(abs(center.Y) - width / 2.0) <= tol
        on_top_or_bottom = abs(center.Z - z_min) <= tol or abs(center.Z - z_max) <= tol
        if (on_outer_x or on_outer_y) and on_top_or_bottom:
            edges.append(edge)
    return edges


def _make_display_base():
    with BuildPart() as base:
        with BuildSketch(Plane.XY):
            RectangleRounded(
                DISPLAY_BASE_LENGTH,
                DISPLAY_BASE_WIDTH,
                8.0,
                align=(Align.CENTER, Align.CENTER),
            )
        extrude(amount=DISPLAY_BASE_THICKNESS)

        for x_abs in (-20.0, 120.0):
            for y_pos in (-50.0, 50.0):
                x_pos = x_abs - DISPLAY_BASE_CENTER[0]
                with Locations(Location((x_pos, y_pos, -0.6))):
                    Cylinder(
                        radius=3.0,
                        height=DISPLAY_BASE_THICKNESS + 1.2,
                        align=(Align.CENTER, Align.CENTER, Align.MIN),
                        mode=Mode.SUBTRACT,
                    )
                with Locations(Location((x_pos, y_pos, DISPLAY_BASE_THICKNESS - 3.2))):
                    Cone(
                        bottom_radius=3.0,
                        top_radius=6.0,
                        height=3.4,
                        align=(Align.CENTER, Align.CENTER, Align.MIN),
                        mode=Mode.SUBTRACT,
                    )

        _safe_fillet(
            _outer_rect_edges(base.part, DISPLAY_BASE_LENGTH, DISPLAY_BASE_WIDTH, 0.0, DISPLAY_BASE_THICKNESS),
            3.0,
        )

    part = base.part.moved(Location(DISPLAY_BASE_CENTER))
    return _set_metadata(part, "rounded_rectangular_display_base_180x140x12_with_four_countersunk_holes", DARK_GRAPHITE)


def _make_fixed_base():
    return _make_axis_cylinder(
        "fixed_cylindrical_base_axis1_od82_z12_to_z42",
        "z",
        (0.0, 0.0, (FIXED_BASE_BOTTOM_Z + FIXED_BASE_TOP_Z) / 2.0),
        FIXED_BASE_DIAMETER / 2.0,
        FIXED_BASE_TOP_Z - FIXED_BASE_BOTTOM_Z,
        LIGHT_GRAY,
        fillet_radius=2.0,
    )


def _make_turntable():
    return _make_axis_cylinder(
        "rotating_base_turntable_axis1_od72_z42_to_z58",
        "z",
        (0.0, 0.0, (TURNTABLE_BOTTOM_Z + TURNTABLE_TOP_Z) / 2.0),
        TURNTABLE_DIAMETER / 2.0,
        TURNTABLE_TOP_Z - TURNTABLE_BOTTOM_Z,
        DARK_GRAPHITE,
        fillet_radius=1.5,
    )


def _make_pedestal():
    with BuildPart() as pedestal:
        with BuildSketch(Plane.XY):
            RectangleRounded(46.0, 58.0, 7.0, align=(Align.CENTER, Align.CENTER))
        extrude(amount=43.0)
        _safe_fillet(pedestal.edges(), 2.5)
    part = pedestal.part.moved(Location((0.0, 0.0, 47.0)))
    return _set_metadata(part, "rounded_shoulder_pedestal_46x58x43_to_axis2_center", MATTE_WHITE)


def _make_shoulder_lug(label: str, y_center: float):
    with BuildPart() as lug:
        with Locations(Location((3.0, y_center, 73.5))):
            Box(34.0, 12.0, 37.0, align=(Align.CENTER, Align.CENTER, Align.CENTER))
        with Locations(Location((0.0, y_center, 90.0))):
            Cylinder(
                radius=22.0,
                height=12.0,
                rotation=(90.0, 0.0, 0.0),
                align=(Align.CENTER, Align.CENTER, Align.CENTER),
            )
            Cylinder(
                radius=13.0,
                height=14.0,
                rotation=(90.0, 0.0, 0.0),
                align=(Align.CENTER, Align.CENTER, Align.CENTER),
                mode=Mode.SUBTRACT,
            )
        _safe_fillet(lug.edges(), 1.6)
    return _set_metadata(lug.part, label, MATTE_WHITE)


def _make_upper_arm_link(label: str, y_center: float):
    shoulder = SHOULDER_CENTER
    elbow = ELBOW_CENTER
    dx = elbow[0] - shoulder[0]
    dz = elbow[2] - shoulder[2]
    link_length = (dx * dx + dz * dz) ** 0.5 + 8.0
    link_angle = -degrees(atan2(dz, dx))
    mid = ((shoulder[0] + elbow[0]) / 2.0, y_center, (shoulder[2] + elbow[2]) / 2.0)

    with BuildPart() as link:
        with BuildSketch(Plane.XZ.offset(-5.0)):
            RectangleRounded(link_length, 18.0, 8.0, align=(Align.CENTER, Align.CENTER))
        extrude(amount=10.0)

        with BuildSketch(Plane.XZ.offset(-6.2)):
            RectangleRounded(56.0, 7.4, 3.5, align=(Align.CENTER, Align.CENTER))
        extrude(amount=12.4, mode=Mode.SUBTRACT)
        _safe_fillet(link.edges(), 1.5)

    part = link.part.moved(Location(mid, (0.0, link_angle, 0.0)))
    return _set_metadata(part, label, MATTE_WHITE)


def _make_forearm_housing():
    elbow = ELBOW_CENTER
    wrist = WRIST_ROLL_CENTER
    dx = wrist[0] - elbow[0]
    dz = wrist[2] - elbow[2]
    length = (dx * dx + dz * dz) ** 0.5
    angle = -degrees(atan2(dz, dx))
    center = ((elbow[0] + wrist[0]) / 2.0, 0.0, (elbow[2] + wrist[2]) / 2.0)

    with BuildPart() as forearm:
        Cone(
            bottom_radius=16.0,
            top_radius=12.0,
            height=length,
            rotation=(0.0, 90.0, 0.0),
            align=(Align.CENTER, Align.CENTER, Align.CENTER),
        )
        _safe_fillet(forearm.edges(), 1.6)

    part = forearm.part.moved(Location(center, (0.0, angle, 0.0)))
    return _set_metadata(part, "tapered_rounded_forearm_housing_elbow_to_wrist_axis4", MATTE_WHITE)


def _make_forearm_panel(label: str, side: float):
    elbow = ELBOW_CENTER
    wrist = WRIST_ROLL_CENTER
    dx = wrist[0] - elbow[0]
    dz = wrist[2] - elbow[2]
    angle = -degrees(atan2(dz, dx))
    center = ((elbow[0] + wrist[0]) / 2.0, 0.0, (elbow[2] + wrist[2]) / 2.0)

    with BuildPart() as panel:
        with Locations(Location((6.0, side * 15.3, 0.0))):
            Box(50.0, 1.2, 10.0, align=(Align.CENTER, Align.CENTER, Align.CENTER))
        _safe_fillet(panel.edges(), 0.7)

    part = panel.part.moved(Location(center, (0.0, angle, 0.0)))
    return _set_metadata(part, label, DEEP_GRAPHITE)


def _rotated_y_point(
    local: tuple[float, float, float],
    center: tuple[float, float, float],
    angle_deg: float,
) -> tuple[float, float, float]:
    angle = radians(angle_deg)
    x_pos = center[0] + local[0] * cos(angle) + local[2] * sin(angle)
    y_pos = center[1] + local[1]
    z_pos = center[2] - local[0] * sin(angle) + local[2] * cos(angle)
    return (x_pos, y_pos, z_pos)


def _forearm_panel_screws(parts: list):
    elbow = ELBOW_CENTER
    wrist = WRIST_ROLL_CENTER
    dx = wrist[0] - elbow[0]
    dz = wrist[2] - elbow[2]
    angle = -degrees(atan2(dz, dx))
    center = ((elbow[0] + wrist[0]) / 2.0, 0.0, (elbow[2] + wrist[2]) / 2.0)
    for side_name, side in (("positive_y", 1.0), ("negative_y", -1.0)):
        for index, local_x in enumerate((-16.0, 25.0), start=1):
            screw_center = _rotated_y_point((local_x, side * 16.1, 0.0), center, angle)
            parts.append(
                _make_screw_head(
                    f"forearm_recessed_panel_{side_name}_socket_screw_{index}",
                    "y",
                    screw_center,
                    1.55,
                    1.0,
                )
            )


def _add_circular_screws(
    parts: list,
    prefix: str,
    axis: str,
    axis_center: tuple[float, float, float],
    face_coordinates: tuple[float, ...],
    bolt_circle_radius: float,
    count: int,
    screw_radius: float,
    screw_height: float,
    start_angle: float = 0.0,
):
    for face_index, face_coord in enumerate(face_coordinates, start=1):
        for index in range(count):
            angle = start_angle + tau * index / count
            if axis == "z":
                center = (
                    axis_center[0] + bolt_circle_radius * cos(angle),
                    axis_center[1] + bolt_circle_radius * sin(angle),
                    face_coord,
                )
            elif axis == "y":
                center = (
                    axis_center[0] + bolt_circle_radius * cos(angle),
                    face_coord,
                    axis_center[2] + bolt_circle_radius * sin(angle),
                )
            else:
                center = (
                    face_coord,
                    axis_center[1] + bolt_circle_radius * cos(angle),
                    axis_center[2] + bolt_circle_radius * sin(angle),
                )
            parts.append(
                _make_screw_head(
                    f"{prefix}_face_{face_index}_socket_head_screw_{index + 1:02d}",
                    axis,
                    center,
                    screw_radius,
                    screw_height,
                )
            )


def _make_wrist_yoke_lug(label: str, y_center: float):
    with BuildPart() as lug:
        with Locations(Location((164.5, y_center, 128.0))):
            Box(25.0, 7.0, 17.0, align=(Align.CENTER, Align.CENTER, Align.CENTER))
        with Locations(Location((174.0, y_center, 128.0))):
            Cylinder(
                radius=14.5,
                height=7.0,
                rotation=(90.0, 0.0, 0.0),
                align=(Align.CENTER, Align.CENTER, Align.CENTER),
            )
            Cylinder(
                radius=8.0,
                height=8.0,
                rotation=(90.0, 0.0, 0.0),
                align=(Align.CENTER, Align.CENTER, Align.CENTER),
                mode=Mode.SUBTRACT,
            )
        _safe_fillet(lug.edges(), 1.0)
    return _set_metadata(lug.part, label, MATTE_WHITE)


def _make_tool_flange():
    with BuildPart() as flange:
        Cylinder(
            radius=19.0,
            height=7.0,
            rotation=(0.0, 90.0, 0.0),
            align=(Align.CENTER, Align.CENTER, Align.CENTER),
        )
        Cylinder(
            radius=5.0,
            height=9.0,
            rotation=(0.0, 90.0, 0.0),
            align=(Align.CENTER, Align.CENTER, Align.CENTER),
            mode=Mode.SUBTRACT,
        )
        for index in range(6):
            angle = tau * index / 6.0
            y_pos = 14.0 * cos(angle)
            z_pos = 14.0 * sin(angle)
            with Locations(Location((0.0, y_pos, z_pos))):
                Cylinder(
                    radius=2.0,
                    height=9.0,
                    rotation=(0.0, 90.0, 0.0),
                    align=(Align.CENTER, Align.CENTER, Align.CENTER),
                    mode=Mode.SUBTRACT,
                )
        _safe_fillet(flange.edges(), 0.6)
    part = flange.part.moved(Location(TOOL_FLANGE_CENTER))
    return _set_metadata(part, "standard_tool_flange_axis6_od38_thick7_with_10mm_bore_and_6x4mm_holes", BRUSHED_STEEL)


def _make_cable_guide():
    points = [
        (-15.0, -31.0, 94.0),
        (8.0, -31.0, 101.0),
        (36.0, -30.0, 119.0),
        (66.0, -28.0, 139.0),
        (78.0, -27.0, 148.0),
        (104.0, -28.0, 142.0),
        (134.0, -27.0, 135.0),
        (155.0, -22.0, 132.0),
        (174.0, -18.0, 130.0),
    ]
    path = Edge.make_spline(points)
    tangent = (
        points[1][0] - points[0][0],
        points[1][1] - points[0][1],
        points[1][2] - points[0][2],
    )
    profile_plane = Plane(origin=points[0], x_dir=(0.0, 1.0, 0.0), z_dir=tangent)

    with BuildPart() as cable:
        with BuildSketch(profile_plane):
            Circle(2.0)
        sweep(path=path, is_frenet=True)
        _safe_fillet(cable.edges(), 0.2)
    return _set_metadata(cable.part, "matte_black_external_cable_guide_4mm_swept_tube_shoulder_to_wrist", MATTE_BLACK)


def _make_cable_clamp(label: str, center: tuple[float, float, float], angle_y: float):
    with BuildPart() as clamp:
        Box(12.0, 6.0, 5.0, align=(Align.CENTER, Align.CENTER, Align.CENTER))
        Cylinder(
            radius=2.2,
            height=14.0,
            rotation=(90.0, 0.0, 0.0),
            align=(Align.CENTER, Align.CENTER, Align.CENTER),
            mode=Mode.SUBTRACT,
        )
        _safe_fillet(clamp.edges(), 0.6)
    part = clamp.part.moved(Location(center, (0.0, angle_y, 0.0)))
    return _set_metadata(part, label, DARK_STEEL)


def _make_axis_label_ring_set(parts: list):
    parts.append(_make_axis_ring("blue_accent_ring_axis1_base_yaw_vertical_z", "z", (0.0, 0.0, 58.9), 38.0, 35.4, 1.6, BLUE_ACCENT))
    parts.append(_make_axis_ring("orange_accent_ring_axis2_shoulder_pitch_y_left", "y", (0.0, -37.1, 90.0), 25.0, 22.0, 1.8, ORANGE_ACCENT))
    parts.append(_make_axis_ring("orange_accent_ring_axis2_shoulder_pitch_y_right", "y", (0.0, 37.1, 90.0), 25.0, 22.0, 1.8, ORANGE_ACCENT))
    parts.append(_make_axis_ring("blue_accent_ring_axis3_elbow_pitch_y_left", "y", (74.0, -34.6, 142.0), 24.0, 21.0, 1.8, BLUE_ACCENT))
    parts.append(_make_axis_ring("blue_accent_ring_axis3_elbow_pitch_y_right", "y", (74.0, 34.6, 142.0), 24.0, 21.0, 1.8, BLUE_ACCENT))
    parts.append(_make_axis_ring("orange_accent_ring_axis4_wrist_roll_x", "x", (154.0, 0.0, 128.0), 17.0, 15.0, 2.0, ORANGE_ACCENT))
    parts.append(_make_axis_ring("blue_accent_ring_axis5_wrist_pitch_y", "y", (174.0, 0.0, 128.0), 16.0, 14.0, 2.0, BLUE_ACCENT))
    parts.append(_make_axis_ring("orange_accent_ring_axis6_tool_roll_x", "x", (196.0, 0.0, 128.0), 14.0, 12.0, 2.0, ORANGE_ACCENT))


def gen_step():
    """Return a labeled six-axis industrial robot arm display assembly in millimeters."""
    parts = [
        _make_display_base(),
        _make_fixed_base(),
        _make_turntable(),
        _make_axis_ring("dark_circular_seam_between_fixed_base_and_turntable_axis1", "z", (0.0, 0.0, 42.2), 41.4, 36.0, 0.8, DEEP_GRAPHITE),
        _make_pedestal(),
        _make_shoulder_lug("shoulder_yoke_negative_y_lug_with_axis2_bore", -24.0),
        _make_shoulder_lug("shoulder_yoke_positive_y_lug_with_axis2_bore", 24.0),
        _make_axis_cylinder("dark_graphite_shoulder_motor_housing_axis2_od44_length72", "y", SHOULDER_CENTER, 22.0, 72.0, DARK_GRAPHITE, 1.6),
        _make_axis_cylinder("left_shoulder_raised_joint_cap_od48_thick3", "y", (0.0, -37.5, 90.0), 24.0, 3.0, LIGHT_GRAY, 0.6),
        _make_axis_cylinder("right_shoulder_raised_joint_cap_od48_thick3", "y", (0.0, 37.5, 90.0), 24.0, 3.0, LIGHT_GRAY, 0.6),
        _make_upper_arm_link("upper_arm_negative_y_rounded_side_link_with_oval_lightening_cutout", -18.0),
        _make_upper_arm_link("upper_arm_positive_y_rounded_side_link_with_oval_lightening_cutout", 18.0),
        _make_axis_cylinder("dark_graphite_elbow_joint_housing_axis3_od42_length66", "y", ELBOW_CENTER, 21.0, 66.0, DARK_GRAPHITE, 1.8),
        _make_axis_cylinder("negative_y_elbow_raised_joint_cap_od46_thick3", "y", (74.0, -34.5, 142.0), 23.0, 3.0, LIGHT_GRAY, 0.6),
        _make_axis_cylinder("positive_y_elbow_raised_joint_cap_od46_thick3", "y", (74.0, 34.5, 142.0), 23.0, 3.0, LIGHT_GRAY, 0.6),
        _make_forearm_housing(),
        _make_forearm_panel("negative_y_dark_recessed_side_panel_on_tapered_forearm", -1.0),
        _make_forearm_panel("positive_y_dark_recessed_side_panel_on_tapered_forearm", 1.0),
        _make_axis_cylinder("dark_graphite_wrist_roll_housing_axis4_od30_length28", "x", WRIST_ROLL_CENTER, 15.0, 28.0, DARK_GRAPHITE, 1.1),
        _make_wrist_yoke_lug("wrist_pitch_fork_negative_y_lug_axis5", -20.0),
        _make_wrist_yoke_lug("wrist_pitch_fork_positive_y_lug_axis5", 20.0),
        _make_axis_cylinder("dark_graphite_wrist_pitch_joint_axis5_od28_length46", "y", WRIST_PITCH_CENTER, 14.0, 46.0, DARK_GRAPHITE, 1.0),
        _make_axis_cylinder("negative_y_wrist_pitch_cap_od31_thick2", "y", (174.0, -24.0, 128.0), 15.5, 2.0, LIGHT_GRAY, 0.4),
        _make_axis_cylinder("positive_y_wrist_pitch_cap_od31_thick2", "y", (174.0, 24.0, 128.0), 15.5, 2.0, LIGHT_GRAY, 0.4),
        _make_axis_cylinder("dark_graphite_final_wrist_tool_roll_cylinder_axis6_od24_length30", "x", TOOL_ROLL_CENTER, 12.0, 30.0, DARK_GRAPHITE, 0.9),
        _make_axis_cylinder("short_steel_tool_flange_pilot_hub_axis6_od18_length5", "x", (211.0, 0.0, 128.0), 9.0, 5.0, BRUSHED_STEEL, 0.4),
        _make_tool_flange(),
        _make_cable_guide(),
    ]

    _make_axis_label_ring_set(parts)

    _add_circular_screws(parts, "turntable_top_bolt_circle_58mm", "z", (0.0, 0.0, 0.0), (59.0,), 29.0, 8, 2.1, 1.7, start_angle=tau / 16.0)
    _add_circular_screws(parts, "shoulder_axis2_joint_cap", "y", SHOULDER_CENTER, (-39.0, 39.0), 17.0, 6, 1.6, 1.1, start_angle=tau / 12.0)
    _add_circular_screws(parts, "elbow_axis3_joint_cap", "y", ELBOW_CENTER, (-36.0, 36.0), 16.0, 6, 1.55, 1.1, start_angle=tau / 12.0)
    _add_circular_screws(parts, "wrist_pitch_axis5_cap", "y", WRIST_PITCH_CENTER, (-25.2, 25.2), 10.5, 4, 1.25, 0.9, start_angle=tau / 8.0)
    _add_circular_screws(parts, "wrist_roll_axis4_cap", "x", WRIST_ROLL_CENTER, (139.2, 168.8), 10.5, 4, 1.25, 0.9, start_angle=tau / 8.0)
    _add_circular_screws(parts, "tool_flange_visible_fastener_circle", "x", TOOL_FLANGE_CENTER, (220.0,), 14.0, 6, 1.35, 0.8, start_angle=tau / 12.0)
    _forearm_panel_screws(parts)

    upper_angle = -degrees(atan2(ELBOW_CENTER[2] - SHOULDER_CENTER[2], ELBOW_CENTER[0] - SHOULDER_CENTER[0]))
    forearm_angle = -degrees(atan2(WRIST_ROLL_CENTER[2] - ELBOW_CENTER[2], WRIST_ROLL_CENTER[0] - ELBOW_CENTER[0]))
    parts.extend(
        [
            _make_cable_clamp("shoulder_cable_saddle_clamp_attached_to_rear_yoke", (-8.0, -29.5, 97.0), 0.0),
            _make_cable_clamp("upper_arm_cable_saddle_clamp_following_raised_link", (39.0, -29.5, 121.0), upper_angle),
            _make_cable_clamp("elbow_cable_saddle_clamp_at_cross_over", (78.0, -27.5, 148.0), 0.0),
            _make_cable_clamp("forearm_cable_saddle_clamp_on_tapered_cover", (131.0, -27.5, 136.0), forearm_angle),
            _make_cable_clamp("wrist_cable_saddle_clamp_near_axis4", (158.0, -21.5, 132.0), 0.0),
        ]
    )

    assembly = Compound(
        obj=parts,
        children=parts,
        label="six_axis_industrial_robot_arm_static_display_pose",
    )
    return assembly
