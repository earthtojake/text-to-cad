# Prompt: Shared implementation library for the simple CAD prompt scripts.

from math import cos, sin, tau

from build123d import (
    Align,
    Box,
    BuildPart,
    BuildSketch,
    Color,
    Cylinder,
    Location,
    Locations,
    Mode,
    Plane,
    Polygon,
    RectangleRounded,
    Torus,
    add,
    chamfer,
    extrude,
    fillet,
)


def _polar_point(radius: float, angle: float) -> tuple[float, float]:
    return (radius * cos(angle), radius * sin(angle))


def _safe_fillet(shape, edges, radius: float):
    selected = list(edges)
    if not selected:
        return shape
    try:
        return fillet(selected, radius=radius)
    except Exception:
        return shape


def _safe_chamfer(shape, edges, length: float):
    selected = list(edges)
    if not selected:
        return shape
    try:
        return chamfer(selected, length=length)
    except Exception:
        return shape


def _line_edges(shape):
    return [edge for edge in shape.edges() if str(edge.geom_type).endswith("LINE")]


def _circular_edges(shape, *, radius: float | None = None, axis: str | None = None, coordinate: float | None = None):
    edges = []
    for edge in shape.edges():
        try:
            edge_radius = edge.radius
            edge_center = edge.arc_center
            edge_normal = edge.normal()
        except Exception:
            continue

        if radius is not None and abs(edge_radius - radius) > 0.08:
            continue

        if axis is not None:
            components = {
                "x": abs(edge_normal.X),
                "y": abs(edge_normal.Y),
                "z": abs(edge_normal.Z),
            }
            if components[axis] < 1.0 - 1e-4:
                continue

        if coordinate is not None:
            coord = {"x": edge_center.X, "y": edge_center.Y, "z": edge_center.Z}[axis or "z"]
            if abs(coord - coordinate) > 0.08:
                continue

        edges.append(edge)
    return edges


def _finish(shape, label: str, color: Color):
    shape.label = label
    shape.color = color
    return shape


def _hole_z(diameter: float, height: float, x: float, y: float, z_min: float = -1.0):
    with Locations(Location((x, y, z_min))):
        Cylinder(
            radius=diameter / 2.0,
            height=height,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
            mode=Mode.SUBTRACT,
        )


def _hole_x(diameter: float, length: float, x: float, y: float, z: float):
    with Locations(Location((x, y, z))):
        Cylinder(
            radius=diameter / 2.0,
            height=length,
            rotation=(0.0, 90.0, 0.0),
            align=(Align.CENTER, Align.CENTER, Align.CENTER),
            mode=Mode.SUBTRACT,
        )


def _hole_y(diameter: float, length: float, x: float, y: float, z: float):
    with Locations(Location((x, y, z))):
        Cylinder(
            radius=diameter / 2.0,
            height=length,
            rotation=(90.0, 0.0, 0.0),
            align=(Align.CENTER, Align.CENTER, Align.CENTER),
            mode=Mode.SUBTRACT,
        )


def _slot_z(length: float, width: float, height: float, center: tuple[float, float], z_min: float, *, axis: str = "x"):
    span = max(0.0, length - width)
    if axis == "x":
        if span > 0.01:
            with Locations(Location((center[0], center[1], z_min))):
                Box(span, width, height, align=(Align.CENTER, Align.CENTER, Align.MIN), mode=Mode.SUBTRACT)
        for x_offset in (-span / 2.0, span / 2.0):
            _hole_z(width, height, center[0] + x_offset, center[1], z_min)
    else:
        if span > 0.01:
            with Locations(Location((center[0], center[1], z_min))):
                Box(width, span, height, align=(Align.CENTER, Align.CENTER, Align.MIN), mode=Mode.SUBTRACT)
        for y_offset in (-span / 2.0, span / 2.0):
            _hole_z(width, height, center[0], center[1] + y_offset, z_min)


def _trapezoid_tooth_profile(
    *,
    teeth: int,
    root_radius: float,
    tip_radius: float,
    phase: float,
    root_span_fraction: float = 0.72,
    tip_span_fraction: float = 0.38,
):
    points = []
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


def make_cylindrical_spacer_sleeve():
    outer_radius = 15.0
    bore_radius = 5.0
    height = 28.0

    with BuildPart() as model:
        Cylinder(outer_radius, height, align=(Align.CENTER, Align.CENTER, Align.MIN))
        _hole_z(bore_radius * 2.0, height + 2.0, 0.0, 0.0)

    rim_edges = []
    for z_pos in (0.0, height):
        rim_edges.extend(_circular_edges(model.part, radius=outer_radius, axis="z", coordinate=z_pos))
        rim_edges.extend(_circular_edges(model.part, radius=bore_radius, axis="z", coordinate=z_pos))
    part = _safe_fillet(model.part, rim_edges, 1.1)
    return _finish(part, "cylindrical_spacer_sleeve_through_bore_rounded_rims", Color(0.68, 0.68, 0.64, 1.0))


def make_square_mounting_block():
    size = 48.0
    height = 28.0

    with BuildPart() as model:
        Box(size, size, height, align=(Align.CENTER, Align.CENTER, Align.MIN))
        _hole_z(12.0, height + 2.0, 0.0, 0.0)
        for y_pos in (-14.0, 14.0):
            _hole_x(5.5, size + 2.0, 0.0, y_pos, height / 2.0)

    part = _safe_chamfer(model.part, _line_edges(model.part), 0.8)
    return _finish(part, "square_mounting_block_vertical_and_side_clearance_holes", Color(0.50, 0.58, 0.64, 1.0))


def make_gusset_plate():
    base_length = 88.0
    base_width = 30.0
    base_thickness = 6.0
    web_thickness = 8.0
    web_height = 48.0

    with BuildPart() as web:
        with BuildSketch(Plane.YZ):
            Polygon(
                [
                    (-12.0, base_thickness),
                    (12.0, base_thickness),
                    (12.0, base_thickness + web_height),
                ],
                align=None,
            )
        extrude(amount=web_thickness)
    web_part = web.part.moved(Location((-web_thickness / 2.0, 0.0, 0.0)))

    with BuildPart() as model:
        Box(base_length, base_width, base_thickness, align=(Align.CENTER, Align.CENTER, Align.MIN))
        add(web_part, mode=Mode.ADD)
        for x_pos in (-28.0, 28.0):
            _hole_z(6.0, base_thickness + 2.0, x_pos, -6.0)

    part = _safe_fillet(model.part, _line_edges(model.part), 0.9)
    return _finish(part, "gusset_plate_triangular_web_base_holes_softened_edges", Color(0.58, 0.63, 0.58, 1.0))


def make_rectangular_clamp_block():
    length = 70.0
    width = 34.0
    height = 28.0

    with BuildPart() as model:
        Box(length, width, height, align=(Align.CENTER, Align.CENTER, Align.MIN))
        with Locations(Location((0.0, 0.0, -1.0))):
            Box(length + 2.0, 4.0, height + 2.0, align=(Align.CENTER, Align.CENTER, Align.MIN), mode=Mode.SUBTRACT)
        for x_pos in (-20.0, 20.0):
            _hole_y(5.5, width + 2.0, x_pos, 0.0, height / 2.0)

    part = _safe_chamfer(model.part, _line_edges(model.part), 0.7)
    return _finish(part, "rectangular_clamp_block_split_slot_two_transverse_screw_holes", Color(0.57, 0.60, 0.64, 1.0))


def make_shaft_collar():
    outer_radius = 21.0
    bore_radius = 10.0
    height = 16.0

    with BuildPart() as model:
        Cylinder(outer_radius, height, align=(Align.CENTER, Align.CENTER, Align.MIN))
        _hole_z(bore_radius * 2.0, height + 2.0, 0.0, 0.0)
        _hole_x(5.0, outer_radius + 3.0, outer_radius / 2.0, 0.0, height / 2.0)

    edge_set = []
    for z_pos in (0.0, height):
        edge_set.extend(_circular_edges(model.part, axis="z", coordinate=z_pos))
    part = _safe_chamfer(model.part, edge_set, 0.8)
    return _finish(part, "shaft_collar_bore_radial_set_screw_hole_chamfered_faces", Color(0.46, 0.50, 0.55, 1.0))


def make_pulley_wheel():
    outer_radius = 35.0
    thickness = 16.0
    hub_radius = 18.0
    hub_height = 24.0

    with BuildPart() as model:
        Cylinder(outer_radius, thickness, align=(Align.CENTER, Align.CENTER, Align.MIN))
        with Locations(Location((0.0, 0.0, thickness / 2.0))):
            Cylinder(hub_radius, hub_height, align=(Align.CENTER, Align.CENTER, Align.CENTER), mode=Mode.ADD)
            Torus(outer_radius - 1.2, 3.0, mode=Mode.SUBTRACT)
        _hole_z(10.0, hub_height + 4.0, 0.0, 0.0, z_min=-4.0)

    part = _safe_fillet(model.part, _circular_edges(model.part, axis="z"), 0.8)
    return _finish(part, "pulley_wheel_central_hub_outer_groove_through_bore", Color(0.42, 0.46, 0.50, 1.0))


def make_spur_gear_blank():
    thickness = 10.0
    teeth = 24
    root_radius = 35.0
    tip_radius = 39.0
    hub_radius = 17.0
    hub_height = 16.0

    with BuildPart() as model:
        with BuildSketch(Plane.XY):
            Polygon(
                _trapezoid_tooth_profile(
                    teeth=teeth,
                    root_radius=root_radius,
                    tip_radius=tip_radius,
                    phase=-tau / teeth / 2.0,
                ),
                align=None,
            )
        extrude(amount=thickness)
        with Locations(Location((0.0, 0.0, -3.0))):
            Cylinder(hub_radius, hub_height, align=(Align.CENTER, Align.CENTER, Align.MIN), mode=Mode.ADD)
        _hole_z(18.0, hub_height + 4.0, 0.0, 0.0, z_min=-4.0)

    part = _safe_chamfer(model.part, _circular_edges(model.part, axis="z"), 0.6)
    return _finish(part, "spur_gear_blank_central_bore_raised_hub_simplified_teeth", Color(0.70, 0.58, 0.36, 1.0))


def make_flywheel_disk():
    radius = 45.0
    thickness = 12.0

    with BuildPart() as model:
        Cylinder(radius, thickness, align=(Align.CENTER, Align.CENTER, Align.MIN))
        with Locations(Location((0.0, 0.0, thickness - 2.2))):
            Cylinder(34.0, 3.0, align=(Align.CENTER, Align.CENTER, Align.MIN), mode=Mode.SUBTRACT)
        with Locations(Location((0.0, 0.0, -0.8))):
            Cylinder(34.0, 3.0, align=(Align.CENTER, Align.CENTER, Align.MIN), mode=Mode.SUBTRACT)
        _hole_z(18.0, thickness + 2.0, 0.0, 0.0)
        for index in range(6):
            x_pos, y_pos = _polar_point(25.0, tau * index / 6)
            _hole_z(10.0, thickness + 2.0, x_pos, y_pos)

    part = _safe_fillet(model.part, _circular_edges(model.part, axis="z"), 0.8)
    return _finish(part, "flywheel_disk_central_bore_annular_rim_lightening_holes", Color(0.59, 0.61, 0.63, 1.0))


def make_cam_follower_roller():
    radius = 16.0
    width = 18.0

    with BuildPart() as model:
        Cylinder(radius, width, align=(Align.CENTER, Align.CENTER, Align.MIN))
        _hole_z(12.0, width + 2.0, 0.0, 0.0)

    edge_set = []
    for z_pos in (0.0, width):
        edge_set.extend(_circular_edges(model.part, radius=radius, axis="z", coordinate=z_pos))
        edge_set.extend(_circular_edges(model.part, radius=6.0, axis="z", coordinate=z_pos))
    part = _safe_fillet(model.part, edge_set, 1.8)
    return _finish(part, "cam_follower_roller_bearing_bore_rounded_outer_profile", Color(0.60, 0.64, 0.67, 1.0))


def make_small_enclosure_cover():
    length = 90.0
    width = 60.0
    base_thickness = 4.0
    rim_height = 3.0

    with BuildPart() as model:
        with BuildSketch(Plane.XY):
            RectangleRounded(length, width, 4.0, align=(Align.CENTER, Align.CENTER))
        extrude(amount=base_thickness)
        with Locations(Location((0.0, 0.0, base_thickness))):
            with BuildSketch(Plane.XY):
                RectangleRounded(length - 10.0, width - 10.0, 3.0, align=(Align.CENTER, Align.CENTER))
            extrude(amount=rim_height, mode=Mode.ADD)
        with Locations(Location((0.0, 0.0, base_thickness - 0.8))):
            Box(58.0, 28.0, rim_height + 1.2, align=(Align.CENTER, Align.CENTER, Align.MIN), mode=Mode.SUBTRACT)
        with Locations(Location((0.0, 0.0, base_thickness))):
            Box(66.0, 36.0, rim_height + 1.0, align=(Align.CENTER, Align.CENTER, Align.MIN), mode=Mode.SUBTRACT)
        for x_pos in (-35.0, 35.0):
            for y_pos in (-22.0, 22.0):
                _hole_z(4.2, base_thickness + 1.5, x_pos, y_pos)

    part = _safe_fillet(model.part, _line_edges(model.part), 0.5)
    return _finish(part, "small_enclosure_cover_raised_rim_corner_screw_holes_recessed_center", Color(0.38, 0.51, 0.62, 1.0))


def make_cylindrical_cap():
    outer_radius = 21.0
    height = 28.0
    wall = 3.0
    top_thickness = 4.0

    with BuildPart() as model:
        Cylinder(outer_radius, height, align=(Align.CENTER, Align.CENTER, Align.MIN))
        with Locations(Location((0.0, 0.0, -1.0))):
            Cylinder(outer_radius - wall, height - top_thickness + 1.0, align=(Align.CENTER, Align.CENTER, Align.MIN), mode=Mode.SUBTRACT)
        with Locations(Location((0.0, 0.0, height))):
            Cylinder(10.0, 6.0, align=(Align.CENTER, Align.CENTER, Align.MIN), mode=Mode.ADD)

    part = _safe_fillet(model.part, _circular_edges(model.part, axis="z"), 1.0)
    return _finish(part, "cylindrical_cap_hollow_interior_top_boss_rounded_external_edges", Color(0.52, 0.57, 0.61, 1.0))


def make_retainer_plate():
    length = 82.0
    width = 34.0
    thickness = 6.0

    with BuildPart() as model:
        Box(length, width, thickness, align=(Align.CENTER, Align.CENTER, Align.MIN))
        _slot_z(36.0, 10.0, thickness + 2.0, (0.0, 0.0), -1.0)
        for x_pos in (-30.0, 30.0):
            _hole_z(7.0, thickness + 2.0, x_pos, 0.0)

    part = _safe_chamfer(model.part, _line_edges(model.part), 0.8)
    return _finish(part, "retainer_plate_elongated_slot_two_holes_chamfered_perimeter", Color(0.60, 0.62, 0.66, 1.0))


def make_keyed_shaft_hub():
    outer_radius = 27.0
    height = 22.0
    bore_radius = 10.0

    with BuildPart() as model:
        Cylinder(outer_radius, height, align=(Align.CENTER, Align.CENTER, Align.MIN))
        _hole_z(bore_radius * 2.0, height + 2.0, 0.0, 0.0)
        with Locations(Location((0.0, bore_radius + 2.0, -1.0))):
            Box(6.0, 7.0, height + 2.0, align=(Align.CENTER, Align.CENTER, Align.MIN), mode=Mode.SUBTRACT)
        for index in range(4):
            x_pos, y_pos = _polar_point(19.5, tau * index / 4.0 + tau / 8.0)
            _hole_z(5.5, height + 2.0, x_pos, y_pos)

    part = _safe_chamfer(model.part, _circular_edges(model.part, axis="z"), 0.7)
    return _finish(part, "keyed_shaft_hub_central_bore_keyway_bolt_hole_pattern", Color(0.49, 0.52, 0.56, 1.0))


def make_t_slot_slider_block():
    length = 80.0
    width = 36.0
    height = 18.0

    with BuildPart() as model:
        Box(length, width, height, align=(Align.CENTER, Align.CENTER, Align.MIN))
        with Locations(Location((0.0, 0.0, 6.0))):
            Box(length + 2.0, 24.0, 6.0, align=(Align.CENTER, Align.CENTER, Align.MIN), mode=Mode.SUBTRACT)
        with Locations(Location((0.0, 0.0, 6.0))):
            Box(length + 2.0, 10.0, height, align=(Align.CENTER, Align.CENTER, Align.MIN), mode=Mode.SUBTRACT)
        for y_pos in (-18.0, 18.0):
            with Locations(Location((0.0, y_pos, 8.0))):
                Box(48.0, 5.0, 8.0, align=(Align.CENTER, Align.CENTER, Align.CENTER), mode=Mode.SUBTRACT)
        for x_pos in (-28.0, 28.0):
            for y_pos in (-14.0, 14.0):
                _hole_z(4.5, height + 2.0, x_pos, y_pos)

    part = _safe_chamfer(model.part, _line_edges(model.part), 0.5)
    return _finish(part, "t_slot_slider_block_central_channel_side_reliefs_mounting_holes", Color(0.47, 0.53, 0.55, 1.0))


def make_mounting_plate():
    length = 100.0
    width = 70.0
    thickness = 8.0

    with BuildPart() as model:
        with BuildSketch(Plane.XY):
            RectangleRounded(length, width, 5.0, align=(Align.CENTER, Align.CENTER))
        extrude(amount=thickness)
        _hole_z(28.0, thickness + 2.0, 0.0, 0.0)
        _slot_z(30.0, 8.0, thickness + 2.0, (32.0, 0.0), -1.0, axis="y")
        for x_pos in (-38.0, 38.0):
            for y_pos in (-24.0, 24.0):
                _hole_z(5.5, thickness + 2.0, x_pos, y_pos)

    part = _safe_fillet(model.part, _line_edges(model.part), 0.8)
    return _finish(part, "mounting_plate_central_cutout_side_slot_four_corner_holes_rounded_edges", Color(0.58, 0.65, 0.69, 1.0))
