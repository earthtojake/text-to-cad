"""Flat-pattern / 2D-projection helpers for DXF drawing generators.

The shared engine for deriving DXF cut geometry from 3D topology: select planar
faces, project their wires into 2D, union the projections (shapely), and emit
clean closed contours into an ezdxf modelspace. Also provides kerf/tool-radius
offsetting for cut compensation. Drawing generators (`<name>.dxf.py`) should
consume this module instead of hand-rolling projection math; hand-drawn
parametric outlines remain appropriate only when there is no reliable 3D
topology to project.
"""

from __future__ import annotations

import math
from typing import Callable, Iterable

import build123d


Point2D = tuple[float, float]
ProjectFn = Callable[[build123d.Vector], Point2D]
MIN_CUT_CONTOUR_AREA_MM2 = 0.05
# Drop micron-scale duplicate edges from topology projection before writing DXF.
# This is far below fabrication tolerance but keeps upload parsers from seeing
# accidental stray/duplicate cut fragments.
POINT_MERGE_TOLERANCE_MM = 0.01


def axis_value(vector: build123d.Vector, axis: str) -> float:
    return {"x": vector.X, "y": vector.Y, "z": vector.Z}[axis]


def snap(value: float, source: float, target: float, *, tolerance: float = 1e-3) -> float:
    return target if abs(value - source) <= tolerance else value


def planar_faces(
    shape: build123d.Shape,
    *,
    normal_axis: str,
    normal_sign: float,
    coordinate_axis: str,
    coordinate: float,
    tolerance: float = 0.02,
    min_area: float = 1e-5,
) -> tuple[build123d.Face, ...]:
    matches: list[build123d.Face] = []
    for face in shape.faces():
        if face.geom_type != build123d.GeomType.PLANE:
            continue
        normal = face.normal_at()
        center = face.center()
        if abs(axis_value(normal, normal_axis) - normal_sign) > 0.02:
            continue
        if abs(axis_value(center, coordinate_axis) - coordinate) > tolerance:
            continue
        if face.area <= min_area:
            continue
        matches.append(face)
    if not matches:
        raise RuntimeError(
            "Could not find planar topology faces for DXF projection: "
            f"normal {normal_sign:+.0f}{normal_axis}, {coordinate_axis}={coordinate:.3f}"
        )
    return tuple(matches)


def project_wire_points(
    wire: build123d.Wire,
    project: ProjectFn,
    *,
    max_segment_mm: float = 0.25,
) -> list[Point2D]:
    sample_count = max(16, int(math.ceil(wire.length / max_segment_mm)))
    points: list[Point2D] = []
    for index in range(sample_count):
        point = project(wire.position_at(index / sample_count))
        if not points or math.dist(points[-1], point) > 1e-6:
            points.append(point)
    if len(points) >= 2 and math.dist(points[0], points[-1]) < 1e-6:
        points.pop()
    return points


def project_face_polygon(face: build123d.Face, project: ProjectFn):
    from shapely.geometry import Polygon

    outer = project_wire_points(face.outer_wire(), project)
    holes = [
        project_wire_points(wire, project)
        for wire in face.inner_wires()
        if wire.length > 1e-6
    ]
    polygon = Polygon(outer, holes)
    if not polygon.is_valid:
        polygon = polygon.buffer(0)
    if polygon.is_empty:
        raise RuntimeError("Projected topology face produced an empty DXF polygon")
    return polygon


def union_projected_faces(
    face_groups: Iterable[tuple[Iterable[build123d.Face], ProjectFn]],
    *,
    merge_touching_tolerance_mm: float = 0.0,
):
    from shapely.ops import unary_union

    polygons = [
        project_face_polygon(face, project)
        for faces, project in face_groups
        for face in faces
    ]
    if not polygons:
        raise RuntimeError("No topology faces were projected into the DXF")
    if merge_touching_tolerance_mm > 0.0:
        expanded = [
            polygon.buffer(merge_touching_tolerance_mm, join_style=2)
            for polygon in polygons
        ]
        geometry = unary_union(expanded).buffer(
            -merge_touching_tolerance_mm,
            join_style=2,
        )
    else:
        geometry = unary_union(polygons)
    geometry = geometry.buffer(0)
    if not geometry.is_valid:
        geometry = geometry.buffer(0)
    if geometry.is_empty:
        raise RuntimeError("Projected topology union produced an empty DXF geometry")
    return geometry


def polyline_points_from_ring(ring) -> list[Point2D]:
    points = [(float(x), float(y)) for x, y in ring.coords]
    if (
        len(points) >= 2
        and math.dist(points[0], points[-1]) <= POINT_MERGE_TOLERANCE_MM
    ):
        points.pop()
    return clean_closed_polyline_points(points)


def clean_closed_polyline_points(
    points: list[Point2D],
    *,
    tolerance_mm: float = POINT_MERGE_TOLERANCE_MM,
) -> list[Point2D]:
    cleaned: list[Point2D] = []
    for point in points:
        if not cleaned or math.dist(cleaned[-1], point) > tolerance_mm:
            cleaned.append(point)

    while (
        len(cleaned) >= 2
        and math.dist(cleaned[0], cleaned[-1]) <= tolerance_mm
    ):
        cleaned.pop()

    index = 0
    while len(cleaned) >= 2 and index < len(cleaned):
        next_index = (index + 1) % len(cleaned)
        if math.dist(cleaned[index], cleaned[next_index]) <= tolerance_mm:
            del cleaned[next_index]
            if next_index < index:
                index = 0
            continue
        index += 1

    return cleaned


def polygon_area(points: list[Point2D]) -> float:
    if len(points) < 3:
        return 0.0
    area = 0.0
    for index, point in enumerate(points):
        next_point = points[(index + 1) % len(points)]
        area += (point[0] * next_point[1]) - (next_point[0] * point[1])
    return abs(0.5 * area)


def circle_from_ring(
    ring,
    *,
    tolerance_mm: float = 0.03,
    min_points: int = 12,
) -> tuple[Point2D, float] | None:
    points = polyline_points_from_ring(ring)
    if len(points) < min_points:
        return None
    matrix = [[0.0, 0.0, 0.0] for _ in range(3)]
    vector = [0.0, 0.0, 0.0]
    for x, y in points:
        row = (x, y, 1.0)
        rhs = -(x * x + y * y)
        for i in range(3):
            vector[i] += row[i] * rhs
            for j in range(3):
                matrix[i][j] += row[i] * row[j]
    try:
        coeff_a, coeff_b, coeff_c = _solve_3x3(matrix, vector)
    except ZeroDivisionError:
        return None
    center = (-0.5 * coeff_a, -0.5 * coeff_b)
    radius_squared = (center[0] * center[0]) + (center[1] * center[1]) - coeff_c
    if radius_squared <= 0.0:
        return None
    radius = math.sqrt(radius_squared)
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    min_x = min(xs)
    max_x = max(xs)
    min_y = min(ys)
    max_y = max(ys)
    width = max_x - min_x
    height = max_y - min_y
    if abs(width - height) > max(tolerance_mm, 0.04 * radius):
        return None
    radial_errors = [
        abs(math.dist(point, center) - radius)
        for point in points
    ]
    if max(radial_errors) > max(tolerance_mm, 0.02 * radius):
        return None
    return center, radius


def _solve_3x3(matrix: list[list[float]], vector: list[float]) -> tuple[float, float, float]:
    augmented = [row[:] + [value] for row, value in zip(matrix, vector)]
    for column in range(3):
        pivot_row = max(range(column, 3), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot_row][column]) < 1e-12:
            raise ZeroDivisionError("singular circle fit")
        if pivot_row != column:
            augmented[column], augmented[pivot_row] = augmented[pivot_row], augmented[column]
        pivot = augmented[column][column]
        for item in range(column, 4):
            augmented[column][item] /= pivot
        for row in range(3):
            if row == column:
                continue
            factor = augmented[row][column]
            for item in range(column, 4):
                augmented[row][item] -= factor * augmented[column][item]
    return (augmented[0][3], augmented[1][3], augmented[2][3])


def add_closed_polyline(msp, points: list[Point2D], *, layer: str = "CUT") -> None:
    points = clean_closed_polyline_points(points)
    if len(points) < 3:
        return
    msp.add_lwpolyline(points, close=True, dxfattribs={"layer": layer})


def add_circle_polyline(
    msp,
    center: Point2D,
    radius: float,
    *,
    layer: str = "CUT",
    segments: int = 72,
) -> None:
    # Keep circles as plain closed polylines. Bulge arcs are valid DXF, but
    # some upload parsers classify them as unexpected entity data.
    if radius <= 0.0:
        return
    center_x, center_y = center
    point_count = max(24, int(segments))
    points = [
        (
            center_x + (radius * math.cos((2.0 * math.pi * index) / point_count)),
            center_y + (radius * math.sin((2.0 * math.pi * index) / point_count)),
        )
        for index in range(point_count)
    ]
    msp.add_lwpolyline(
        points,
        close=True,
        dxfattribs={"layer": layer},
    )


def add_ring(
    msp,
    ring,
    *,
    layer: str = "CUT",
    prefer_circle: bool = False,
    min_area_mm2: float = MIN_CUT_CONTOUR_AREA_MM2,
) -> None:
    points = polyline_points_from_ring(ring)
    if polygon_area(points) < min_area_mm2:
        return
    if prefer_circle:
        circle = circle_from_ring(ring)
        if circle is not None:
            center, radius = circle
            add_circle_polyline(msp, center, radius, layer=layer)
            return
    add_closed_polyline(msp, points, layer=layer)


def add_shapely_geometry(msp, geometry, *, layer: str = "CUT") -> None:
    polygons = [geometry] if geometry.geom_type == "Polygon" else list(geometry.geoms)
    for polygon in polygons:
        if polygon.area < MIN_CUT_CONTOUR_AREA_MM2:
            continue
        add_ring(msp, polygon.exterior, layer=layer)
        for interior in polygon.interiors:
            add_ring(msp, interior, layer=layer, prefer_circle=True)


def offset_geometry(geometry, distance_mm: float):
    """Offset closed cut geometry by a kerf / tool-radius compensation.

    Positive ``distance_mm`` grows the profile (cut outside the line), negative
    shrinks it (cut inside). Returns cleaned shapely geometry ready for
    :func:`add_shapely_geometry`."""
    if distance_mm == 0.0:
        return geometry
    offset = geometry.buffer(distance_mm, join_style=2)
    offset = offset.buffer(0)
    if offset.is_empty:
        raise RuntimeError(
            f"Kerf offset of {distance_mm:+.3f} mm produced an empty DXF geometry"
        )
    return offset


def offset_closed_points(
    points: list[Point2D],
    distance_mm: float,
) -> list[list[Point2D]]:
    """Offset one closed contour (a point list) by a kerf / tool-radius
    compensation; returns the resulting closed contour(s) as point lists."""
    from shapely.geometry import Polygon

    polygon = Polygon(points)
    if not polygon.is_valid:
        polygon = polygon.buffer(0)
    offset = offset_geometry(polygon, distance_mm)
    polygons = [offset] if offset.geom_type == "Polygon" else list(offset.geoms)
    return [polyline_points_from_ring(polygon.exterior) for polygon in polygons]
