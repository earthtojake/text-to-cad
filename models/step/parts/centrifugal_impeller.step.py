from math import asin, cos, hypot, radians, sin, tau

from build123d import (
    Align,
    BuildPart,
    BuildSketch,
    Color,
    Cylinder,
    Location,
    Locations,
    Mode,
    Plane,
    Polygon,
    add,
    extrude,
    fillet,
)


# Units: millimeters.
# Origin: impeller axis centered at X=0, Y=0.
# XY: backplate plane. +Z: vertical impeller axis.
# Assumed rotation direction: counter-clockwise viewed from +Z, so blade tips
# trail clockwise by the specified backward sweep.

BACKPLATE_DIAMETER = 90.0
BACKPLATE_RADIUS = BACKPLATE_DIAMETER / 2.0
BACKPLATE_THICKNESS = 6.0
BACKPLATE_OUTER_FILLET_RADIUS = 1.5

HUB_DIAMETER = 26.0
HUB_RADIUS = HUB_DIAMETER / 2.0
HUB_HEIGHT_ABOVE_BACKPLATE = 22.0

BORE_DIAMETER = 8.0
BORE_RADIUS = BORE_DIAMETER / 2.0

BLADE_COUNT = 12
BLADE_ROOT_RADIUS = 18.0
BLADE_TIP_RADIUS = 43.0
BLADE_THICKNESS = 3.0
BLADE_HEIGHT_ABOVE_BACKPLATE = 16.0
BLADE_BACKWARD_SWEEP_ANGLE = radians(45.0)
BLADE_CURVE_SEGMENTS = 5
BLADE_ROOT_FILLET_RADIUS = 1.0
BLADE_ROOT_FILLET_MAX_RADIUS = 30.0

MODEL_LABEL = "centrifugal_impeller_12_backward_curved_blades"


def _polar_point(radius: float, angle: float) -> tuple[float, float]:
    return (radius * cos(angle), radius * sin(angle))


def _clamp_radius(point: tuple[float, float]) -> tuple[float, float]:
    x_pos, y_pos = point
    radius = hypot(x_pos, y_pos)

    if radius < BLADE_ROOT_RADIUS:
        scale = BLADE_ROOT_RADIUS / radius
        return (x_pos * scale, y_pos * scale)
    if radius > BLADE_TIP_RADIUS:
        scale = BLADE_TIP_RADIUS / radius
        return (x_pos * scale, y_pos * scale)
    return point


def _blade_center_point(base_angle: float, t: float) -> tuple[float, float]:
    radius = BLADE_ROOT_RADIUS + (BLADE_TIP_RADIUS - BLADE_ROOT_RADIUS) * t
    angle = base_angle - BLADE_BACKWARD_SWEEP_ANGLE * t
    return _polar_point(radius, angle)


def _blade_normal(base_angle: float, t: float) -> tuple[float, float]:
    radius = BLADE_ROOT_RADIUS + (BLADE_TIP_RADIUS - BLADE_ROOT_RADIUS) * t
    dr_dt = BLADE_TIP_RADIUS - BLADE_ROOT_RADIUS
    dtheta_dt = -BLADE_BACKWARD_SWEEP_ANGLE
    angle = base_angle + dtheta_dt * t

    dx_dt = dr_dt * cos(angle) - radius * sin(angle) * dtheta_dt
    dy_dt = dr_dt * sin(angle) + radius * cos(angle) * dtheta_dt
    length = hypot(dx_dt, dy_dt)
    return (-dy_dt / length, dx_dt / length)


def _blade_endpoint_points(base_angle: float, t: float) -> tuple[tuple[float, float], tuple[float, float]]:
    radius = BLADE_ROOT_RADIUS if t == 0.0 else BLADE_TIP_RADIUS
    angle = base_angle - BLADE_BACKWARD_SWEEP_ANGLE * t
    half_angle = asin((BLADE_THICKNESS / 2.0) / radius)
    return (
        _polar_point(radius, angle + half_angle),
        _polar_point(radius, angle - half_angle),
    )


def _blade_outline(base_angle: float) -> list[tuple[float, float]]:
    left_side: list[tuple[float, float]] = []
    right_side: list[tuple[float, float]] = []
    half_thickness = BLADE_THICKNESS / 2.0

    for index in range(BLADE_CURVE_SEGMENTS + 1):
        t = index / BLADE_CURVE_SEGMENTS
        if index == 0 or index == BLADE_CURVE_SEGMENTS:
            left_point, right_point = _blade_endpoint_points(base_angle, t)
            left_side.append(left_point)
            right_side.append(right_point)
            continue

        x_pos, y_pos = _blade_center_point(base_angle, t)
        nx, ny = _blade_normal(base_angle, t)
        left_side.append(
            _clamp_radius((x_pos + nx * half_thickness, y_pos + ny * half_thickness))
        )
        right_side.append(
            _clamp_radius((x_pos - nx * half_thickness, y_pos - ny * half_thickness))
        )

    return left_side + list(reversed(right_side))


def _make_blade(index: int):
    base_angle = tau * index / BLADE_COUNT

    with BuildPart() as blade:
        with BuildSketch(Plane.XY):
            Polygon(_blade_outline(base_angle), align=None)
        extrude(amount=BLADE_HEIGHT_ABOVE_BACKPLATE)

    part = blade.part.moved(Location((0.0, 0.0, BACKPLATE_THICKNESS)))
    part.label = f"blade_{index + 1:02d}"
    return part


def _make_backplate():
    with BuildPart() as backplate:
        Cylinder(
            radius=BACKPLATE_RADIUS,
            height=BACKPLATE_THICKNESS,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
        )

    part = backplate.part
    outer_edges = []
    outer_edges.extend(_edges_near_z_radius(part, 0.0, BACKPLATE_RADIUS))
    outer_edges.extend(_edges_near_z_radius(part, BACKPLATE_THICKNESS, BACKPLATE_RADIUS))
    part = fillet(outer_edges, radius=BACKPLATE_OUTER_FILLET_RADIUS)
    part.label = "filleted_backplate"
    return part


def _edge_z(edge) -> float:
    return edge.bounding_box().center().Z


def _edge_xy_radius(edge) -> float:
    center = edge.bounding_box().center()
    return hypot(center.X, center.Y)


def _circle_radius(edge) -> float | None:
    try:
        return edge.radius
    except ValueError:
        return None


def _edges_near_z_radius(part, z_value: float, radius: float, tolerance: float = 0.02):
    edges = []
    for edge in part.edges():
        circle_radius = _circle_radius(edge)
        if circle_radius is None:
            continue
        if abs(_edge_z(edge) - z_value) <= tolerance and abs(circle_radius - radius) <= tolerance:
            edges.append(edge)
    return edges


def _blade_root_edges(part):
    min_radius = BLADE_ROOT_RADIUS - BLADE_THICKNESS
    edges = []

    for edge in part.edges():
        if _circle_radius(edge) is not None:
            continue
        if abs(_edge_z(edge) - BACKPLATE_THICKNESS) > 0.02:
            continue
        if min_radius <= _edge_xy_radius(edge) <= BLADE_ROOT_FILLET_MAX_RADIUS:
            edges.append(edge)

    return edges


def gen_step():
    """Return a single solid centrifugal impeller in millimeters."""
    total_height = BACKPLATE_THICKNESS + HUB_HEIGHT_ABOVE_BACKPLATE
    backplate = _make_backplate()

    with BuildPart() as impeller:
        add(backplate, mode=Mode.ADD)

        with Locations(Location((0.0, 0.0, BACKPLATE_THICKNESS))):
            Cylinder(
                radius=HUB_RADIUS,
                height=HUB_HEIGHT_ABOVE_BACKPLATE,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
                mode=Mode.ADD,
            )

        for blade_index in range(BLADE_COUNT):
            add(_make_blade(blade_index), mode=Mode.ADD)

        with Locations(Location((0.0, 0.0, -1.0))):
            Cylinder(
                radius=BORE_RADIUS,
                height=total_height + 2.0,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
                mode=Mode.SUBTRACT,
            )

    part = impeller.part

    root_edges = _blade_root_edges(part)
    root_edges.extend(_edges_near_z_radius(part, BACKPLATE_THICKNESS, HUB_RADIUS))
    if root_edges:
        part = fillet(root_edges, radius=BLADE_ROOT_FILLET_RADIUS)

    part.label = MODEL_LABEL
    part.color = Color(0.62, 0.66, 0.70, 1.0)
    return part
