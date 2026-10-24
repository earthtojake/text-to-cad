"""Project a folded part's panels into one flat pattern, and hand the result to the DXF engine.

WHY THIS IS HERE. cadgen used to carry the projection helpers this repo's flat patterns are built
on; 0.5 replaced them with an exact single-panel unfolder (``flatten.flat_pattern``) and dropped
``project_wire_points`` / ``project_face_polygon`` / ``union_projected_faces``. The unfolding this
repo needs is not single-panel: tom's brackets fold two or three ways, and each panel reaches the
flat run through its OWN map, which distributes that bend's allowance. That mapping is design
intent belonging to the part, so it lives here now rather than in the toolchain.

The projection stays what it always was -- sample each wire, run the panel's map over the points,
union the polygons -- so the outlines are the ones this repo has been ordering against.

WHAT CHANGED. A ``@dxf`` model returns build123d geometry and never touches a document, so the
final step is no longer "write polylines into a modelspace" but ``faces_from_shapely()``, which
rebuilds the union as build123d faces. It restores true circles on the way out, the job
``flat_circles.restore_circles`` used to do on the finished document: a ring whose points all sit
one radius from their centroid becomes a real circle, so an M2 hole is a circle and not a
19-segment polygon. Anything that fails the test stays a polygon, which is the safe direction.
"""

from __future__ import annotations

import math
from typing import Callable, Sequence

import build123d as bd
# so a part can import this module in place of `cadgen.flatten` and keep every call site.
from lib.flatten import (  # noqa: F401
    axis_value,
    flat_pattern,
    flatten_face,
    flatten_faces,
    offset_profile,
    planar_faces,
    snap,
    union_faces,
)

Point2D = tuple[float, float]
ProjectFn = Callable[[object], Point2D]

CIRCLE_TOL_MM = 1e-3
MIN_CIRCLE_POINTS = 8


def project_wire_points(wire, project: ProjectFn, *, max_segment_mm: float = 0.10) -> list[Point2D]:
    """Preserve every corner and sample curved edges to <=0.001 mm chord error.

    Sampling the entire perimeter at equal distances can skip a line junction
    and cut across the corner. Panel dimensions must retain their true vertices.
    """
    points: list[Point2D] = []
    for edge in wire.order_edges():
        segment = max_segment_mm
        if edge.geom_type == bd.GeomType.LINE:
            count = 1
        else:
            if edge.geom_type == bd.GeomType.CIRCLE:
                segment = min(segment, math.sqrt(8.0 * edge.radius * 0.001))
            count = max(8, int(math.ceil(edge.length / segment)))
        for index in range(count):
            point = project(edge.position_at(index / count))
            if not points or math.dist(points[-1], point) > 1e-7:
                points.append(point)
    if len(points) >= 2 and math.dist(points[0], points[-1]) < 1e-6:
        points.pop()
    return points


def _circle_from_points(points: Sequence[Point2D]) -> tuple[Point2D, float] | None:
    """Recover an analytic circle even when split arcs have unequal sample counts.

    Fit all vertices, then require every radial residual to be below the export
    tolerance. A vertex centroid is biased by uneven sampling of split arcs.
    """
    if len(points) < MIN_CIRCLE_POINTS:
        return None
    import numpy as np

    coords = np.asarray(points, dtype=float)
    origin = coords.mean(axis=0)
    local = coords - origin
    matrix = np.column_stack((2 * local, np.ones(len(local))))
    solution, _, rank, _ = np.linalg.lstsq(matrix, (local * local).sum(axis=1), rcond=None)
    if rank < 3:
        return None
    cx, cy = solution[:2] + origin
    radii = [math.hypot(x - cx, y - cy) for x, y in points]
    if max(radii) - min(radii) > CIRCLE_TOL_MM:
        return None
    return (cx, cy), sum(radii) / len(radii)
