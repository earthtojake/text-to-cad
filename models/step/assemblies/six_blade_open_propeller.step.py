from __future__ import annotations

from math import cos, hypot, sin, tau

from build123d import (
    Align,
    Box,
    BuildPart,
    BuildSketch,
    Color,
    Compound,
    Cylinder,
    Face,
    Location,
    Locations,
    Mode,
    Plane,
    Polygon,
    Wire,
    chamfer,
    extrude,
    fillet,
    loft,
)


# Units: millimeters.
# Origin: central tube axis. XY is the blade layout plane. +Z is upward through
# the hollow hub. The image is interpreted as a stylized six-blade open propeller
# with separate visible blade/rim/hub solids rather than a single fused casting.

MODEL_LABEL = "six_blade_open_propeller_from_reference"

WARM_IVORY = Color(0.82, 0.78, 0.65, 1.0)
WARM_TAUPE = Color(0.72, 0.70, 0.61, 1.0)

BLADE_COUNT = 6
BLADE_ROOT_RADIUS = 10.8
BLADE_TIP_RADIUS = 68.0
BLADE_TIP_SWEEP = 14.5
BLADE_CURVE_EXPONENT = 1.55
BLADE_WIDTH = 31.5
BLADE_THICKNESS = 2.8
BLADE_SEGMENTS = 24
BLADE_EDGE_BLEND_RADIUS = 0.55
BLADE_EDGE_BLEND_MIN_SPAN = 0.2
BLADE_Z_OFFSET = -0.35
BLADE_TIP_TWIST_SPAN = 7.0
BLADE_TIP_CENTER_Z_DROP = 1.4

HUB_OUTER_RADIUS = 29.0
HUB_INNER_RADIUS = 23.5
HUB_HEIGHT = 30.0
HUB_WALL_FILLET = 0.65
HUB_CUTOUT_WIDTH = 10.0
HUB_CUTOUT_DEPTH = (HUB_OUTER_RADIUS - HUB_INNER_RADIUS) * 0.5
HUB_CUTOUT_BOTTOM_Z = -0.5
HUB_CUTOUT_HEIGHT = HUB_HEIGHT + 1.0
HUB_CUTOUT_BORE_OVERLAP = 1.0


def _label(part, label: str, color: Color):
    part.label = label
    part.color = color
    return part


def _safe_chamfer(part, length: float):
    try:
        return chamfer(part.edges(), length=length)
    except Exception:
        return part


def _safe_fillet(part, radius: float):
    try:
        return fillet(part.edges(), radius=radius)
    except Exception:
        return part


def _safe_fillet_edges(part, edges, radius: float):
    selected = list(edges)
    if not selected:
        return part
    try:
        return fillet(selected, radius=radius)
    except Exception:
        return part


def _safe_chamfer_edges(part, edges, length: float):
    selected = list(edges)
    if not selected:
        return part
    try:
        return chamfer(selected, length=length)
    except Exception:
        return part


def _circle_radius(edge) -> float | None:
    try:
        return edge.radius
    except Exception:
        return None


def _edge_z(edge) -> float:
    return edge.bounding_box().center().Z


def _edge_axis_spans(edge) -> tuple[float, float, float]:
    bbox = edge.bounding_box()
    return (
        bbox.max.X - bbox.min.X,
        bbox.max.Y - bbox.min.Y,
        bbox.max.Z - bbox.min.Z,
    )


def _non_planar_oriented_edges(part):
    edges = []
    for edge in part.edges():
        if all(span > BLADE_EDGE_BLEND_MIN_SPAN for span in _edge_axis_spans(edge)):
            edges.append(edge)
    return edges


def _hub_rim_edges(part, outer_radius: float, inner_radius: float, height: float):
    edges = []
    for edge in part.edges():
        radius = _circle_radius(edge)
        if radius is None:
            continue
        if min(abs(radius - outer_radius), abs(radius - inner_radius)) > 0.08:
            continue
        if min(abs(_edge_z(edge)), abs(_edge_z(edge) - height)) > 0.08:
            continue
        edges.append(edge)
    return edges


def _blade_center(t: float, *, root_radius: float, tip_radius: float) -> tuple[float, float]:
    span = tip_radius - root_radius
    x_pos = root_radius + span * t
    y_pos = BLADE_TIP_SWEEP * (0.5 - t**BLADE_CURVE_EXPONENT)
    return (x_pos, y_pos)


def _blade_tangent(t: float, *, root_radius: float, tip_radius: float) -> tuple[float, float]:
    low = max(0.0, t - 0.01)
    high = min(1.0, t + 0.01)
    x0, y0 = _blade_center(low, root_radius=root_radius, tip_radius=tip_radius)
    x1, y1 = _blade_center(high, root_radius=root_radius, tip_radius=tip_radius)
    dx = x1 - x0
    dy = y1 - y0
    length = hypot(dx, dy)
    return (dx / length, dy / length)


def _blade_width(t: float, width_offset: float) -> float:
    return max(2.0, BLADE_WIDTH + width_offset)


def _blade_outline(
    *,
    root_offset: float = 0.0,
    tip_offset: float = 0.0,
    width_offset: float = 0.0,
) -> list[tuple[float, float]]:
    root_radius = BLADE_ROOT_RADIUS + root_offset
    tip_radius = BLADE_TIP_RADIUS + tip_offset
    left_side: list[tuple[float, float]] = []
    right_side: list[tuple[float, float]] = []

    for index in range(BLADE_SEGMENTS + 1):
        t = index / BLADE_SEGMENTS
        x_pos, y_pos = _blade_center(t, root_radius=root_radius, tip_radius=tip_radius)
        tangent_x, tangent_y = _blade_tangent(
            t,
            root_radius=root_radius,
            tip_radius=tip_radius,
        )
        normal_x, normal_y = -tangent_y, tangent_x
        half_width = _blade_width(t, width_offset) / 2.0
        left_side.append((x_pos + normal_x * half_width, y_pos + normal_y * half_width))
        right_side.append((x_pos - normal_x * half_width, y_pos - normal_y * half_width))

    tip_tangent_x, tip_tangent_y = _blade_tangent(
        1.0,
        root_radius=root_radius,
        tip_radius=tip_radius,
    )
    tip_normal_x, tip_normal_y = -tip_tangent_y, tip_tangent_x
    tip_x, tip_y = _blade_center(1.0, root_radius=root_radius, tip_radius=tip_radius)
    tip_half_width = _blade_width(1.0, width_offset) / 2.0
    cap_points = []
    for index in range(1, 11):
        angle = index * tau / 20.0
        cap_points.append(
            (
                tip_x
                + tip_normal_x * cos(angle) * tip_half_width
                + tip_tangent_x * sin(angle) * tip_half_width,
                tip_y
                + tip_normal_y * cos(angle) * tip_half_width
                + tip_tangent_y * sin(angle) * tip_half_width,
            )
        )

    return left_side + cap_points + list(reversed(right_side))


def _outline_solid(points: list[tuple[float, float]], height: float):
    with BuildPart() as part:
        with BuildSketch(Plane.XY):
            Polygon(points, align=None)
        extrude(amount=height)
    return part.part


def _place_blade_part(part, index: int):
    blade_angle = index * 360.0 / BLADE_COUNT
    return part.moved(Location((0.0, 0.0, 0.0), (0.0, 0.0, blade_angle)))


def _blade_twist_span(t: float) -> float:
    root_span = HUB_HEIGHT - BLADE_THICKNESS
    blend = t**0.85
    return root_span * (1.0 - blend) + BLADE_TIP_TWIST_SPAN * blend


def _blade_center_z(t: float) -> float:
    return HUB_HEIGHT / 2.0 + BLADE_Z_OFFSET - BLADE_TIP_CENTER_Z_DROP * t


def _make_blade_section_face(
    *,
    x_pos: float,
    y_pos: float,
    tangent_x: float,
    tangent_y: float,
    width: float,
    twist_span: float,
    center_z: float,
) -> Face:
    normal_x, normal_y = -tangent_y, tangent_x
    half_width = width / 2.0
    half_thickness = BLADE_THICKNESS / 2.0
    half_twist_span = twist_span / 2.0

    high_edge = (
        x_pos + normal_x * half_width,
        y_pos + normal_y * half_width,
        center_z + half_twist_span,
    )
    low_edge = (
        x_pos - normal_x * half_width,
        y_pos - normal_y * half_width,
        center_z - half_twist_span,
    )
    points = [
        (high_edge[0], high_edge[1], high_edge[2] + half_thickness),
        (low_edge[0], low_edge[1], low_edge[2] + half_thickness),
        (low_edge[0], low_edge[1], low_edge[2] - half_thickness),
        (high_edge[0], high_edge[1], high_edge[2] - half_thickness),
    ]
    return Face.make_surface(Wire.make_polygon(points, close=True))


def _make_section_face(t: float) -> Face:
    x_pos, y_pos = _blade_center(t, root_radius=BLADE_ROOT_RADIUS, tip_radius=BLADE_TIP_RADIUS)
    tangent_x, tangent_y = _blade_tangent(
        t,
        root_radius=BLADE_ROOT_RADIUS,
        tip_radius=BLADE_TIP_RADIUS,
    )
    return _make_blade_section_face(
        x_pos=x_pos,
        y_pos=y_pos,
        tangent_x=tangent_x,
        tangent_y=tangent_y,
        width=_blade_width(t, 0.0),
        twist_span=_blade_twist_span(t),
        center_z=_blade_center_z(t),
    )


def _make_blade_body_local():
    faces = [
        _make_section_face(index / BLADE_SEGMENTS)
        for index in range(BLADE_SEGMENTS + 1)
    ]
    return loft(faces, ruled=False)


def _make_blade_body(index: int):
    body = _make_blade_body_local()
    hub_trim = Cylinder(
        radius=HUB_OUTER_RADIUS,
        height=120.0,
        align=(Align.CENTER, Align.CENTER, Align.MIN),
    ).moved(Location((0.0, 0.0, -45.0)))
    body = body - hub_trim
    body = _safe_fillet_edges(
        body,
        _non_planar_oriented_edges(body),
        BLADE_EDGE_BLEND_RADIUS,
    )
    body = _place_blade_part(body, index)
    return _label(body, f"blade_{index + 1:02d}_broad_swept_petal", WARM_IVORY)


def _annular_cylinder(
    *,
    label: str,
    outer_radius: float,
    inner_radius: float,
    height: float,
    z_bottom: float,
    color: Color,
):
    with BuildPart() as ring:
        Cylinder(
            radius=outer_radius,
            height=height,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
        )
        Cylinder(
            radius=inner_radius,
            height=height + 2.0,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
            mode=Mode.SUBTRACT,
        )
        # Internal keyway-style recess: open to the bore, blind before the
        # outside wall, matching the rectangular cut visible inside the hub.
        slot_depth = HUB_CUTOUT_DEPTH + HUB_CUTOUT_BORE_OVERLAP
        slot_x = inner_radius - HUB_CUTOUT_BORE_OVERLAP + slot_depth / 2.0
        slot_z = HUB_CUTOUT_BOTTOM_Z + HUB_CUTOUT_HEIGHT / 2.0
        with Locations(Location((slot_x, 0.0, slot_z))):
            Box(
                slot_depth,
                HUB_CUTOUT_WIDTH,
                HUB_CUTOUT_HEIGHT,
                mode=Mode.SUBTRACT,
            )

    part = ring.part.moved(Location((0.0, 0.0, z_bottom)))
    part = _safe_chamfer_edges(
        part,
        _hub_rim_edges(part, outer_radius, inner_radius, height),
        HUB_WALL_FILLET,
    )
    return _label(part, label, color)


def _make_hub_shell():
    return _annular_cylinder(
        label="hollow_cylindrical_center_tube_open_bore",
        outer_radius=HUB_OUTER_RADIUS,
        inner_radius=HUB_INNER_RADIUS,
        height=HUB_HEIGHT,
        z_bottom=0.0,
        color=WARM_TAUPE,
    )


def gen_step():
    parts = [_make_hub_shell()]

    for index in range(BLADE_COUNT):
        parts.append(_make_blade_body(index))

    return Compound(obj=parts, children=parts, label=MODEL_LABEL)
