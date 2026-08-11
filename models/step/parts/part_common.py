from __future__ import annotations

from math import cos, hypot, sin, tau
from typing import Iterable

from build123d import Axis, BuildPart, Color, Location, Mode, chamfer, fillet


TOLERANCE = 1e-6


def polar_point(radius: float, angle: float) -> tuple[float, float]:
    return (radius * cos(angle), radius * sin(angle))


def safe_fillet(part, edges: Iterable, radius: float):
    selected = list(edges)
    if not selected:
        return part
    try:
        return fillet(selected, radius=radius)
    except Exception:
        return part


def safe_chamfer(part, edges: Iterable, length: float):
    selected = list(edges)
    if not selected:
        return part
    try:
        return chamfer(selected, length=length)
    except Exception:
        return part


def line_edges_at_z(part, z_value: float, *, tol: float = 0.02):
    edges = []
    for edge in part.edges():
        bbox = edge.bounding_box()
        if abs(bbox.min.Z - z_value) <= tol and abs(bbox.max.Z - z_value) <= tol:
            if str(edge.geom_type).endswith("LINE"):
                edges.append(edge)
    return edges


def circular_edges(
    part,
    *,
    radius: float | None = None,
    axis: str | None = None,
    coordinate: float | None = None,
    tol: float = 0.05,
):
    edges = []
    for edge in part.edges():
        try:
            edge_radius = edge.radius
            edge_center = edge.arc_center
            edge_normal = edge.normal()
        except Exception:
            continue

        if radius is not None and abs(edge_radius - radius) > tol:
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
            if abs(coord - coordinate) > tol:
                continue

        edges.append(edge)

    return edges


def cylinder_axis_x(radius: float, length: float, center: tuple[float, float, float], *, mode=Mode.ADD):
    from build123d import Align, Cylinder

    return Cylinder(
        radius=radius,
        height=length,
        rotation=(0.0, 90.0, 0.0),
        align=(Align.CENTER, Align.CENTER, Align.CENTER),
        mode=mode,
    ).locate(Location(center))


def cylinder_axis_y(radius: float, length: float, center: tuple[float, float, float], *, mode=Mode.ADD):
    from build123d import Align, Cylinder

    return Cylinder(
        radius=radius,
        height=length,
        rotation=(90.0, 0.0, 0.0),
        align=(Align.CENTER, Align.CENTER, Align.CENTER),
        mode=mode,
    ).locate(Location(center))


def rounded_triangle_points(
    vertices: list[tuple[float, float]],
    *,
    radius: float,
    segments: int = 5,
) -> list[tuple[float, float]]:
    """Approximate a rounded triangular loop with quadratic corner arcs."""
    points: list[tuple[float, float]] = []
    count = len(vertices)

    for index, vertex in enumerate(vertices):
        previous = vertices[(index - 1) % count]
        next_vertex = vertices[(index + 1) % count]

        to_previous = (previous[0] - vertex[0], previous[1] - vertex[1])
        to_next = (next_vertex[0] - vertex[0], next_vertex[1] - vertex[1])
        previous_length = hypot(*to_previous)
        next_length = hypot(*to_next)
        offset = min(radius, previous_length * 0.35, next_length * 0.35)

        start = (
            vertex[0] + to_previous[0] / previous_length * offset,
            vertex[1] + to_previous[1] / previous_length * offset,
        )
        end = (
            vertex[0] + to_next[0] / next_length * offset,
            vertex[1] + to_next[1] / next_length * offset,
        )

        for step in range(segments + 1):
            t = step / segments
            x_pos = (1.0 - t) ** 2 * start[0] + 2.0 * (1.0 - t) * t * vertex[0] + t**2 * end[0]
            y_pos = (1.0 - t) ** 2 * start[1] + 2.0 * (1.0 - t) * t * vertex[1] + t**2 * end[1]
            points.append((x_pos, y_pos))

    return points


def trapezoid_tooth_profile(
    *,
    teeth: int,
    root_radius: float,
    tip_radius: float,
    phase: float,
    root_span_fraction: float = 0.72,
    tip_span_fraction: float = 0.38,
) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    pitch_angle = tau / teeth

    for tooth_index in range(teeth):
        center_angle = phase + tooth_index * pitch_angle
        points.extend(
            (
                polar_point(root_radius, center_angle - root_span_fraction * pitch_angle / 2.0),
                polar_point(tip_radius, center_angle - tip_span_fraction * pitch_angle / 2.0),
                polar_point(tip_radius, center_angle + tip_span_fraction * pitch_angle / 2.0),
                polar_point(root_radius, center_angle + root_span_fraction * pitch_angle / 2.0),
            )
        )

    return points


def label(part, name: str, color: Color | None = None):
    part.label = name
    if color is not None:
        part.color = color
    return part
