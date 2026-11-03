"""Points and polygons the KiCad readers share.

A point is ``(x, y)`` in millimetres, in whatever frame the caller works in;
nothing here changes frames. Distances are between
copper as KiCad's connectivity sees it: a pad is its polygon, a track a segment
of a width, a via a disc, a pour its filled polygons, and two pieces touch when
the distance between them is zero.
"""

from __future__ import annotations

import math
from typing import Iterable, Iterator, Sequence

__all__ = [
    "XY",
    "arc_points",
    "area",
    "bezier_points",
    "box",
    "format_xy",
    "hull",
    "inside",
    "polygon_distance",
    "polygons_overlap",
    "polyline_distance",
    "rotate",
    "segment_distance",
    "segments_distance",
]

XY = tuple[float, float]

_ARC_STEP = math.radians(10)


def format_xy(point: XY) -> str:
    return f"({point[0]:g}, {point[1]:g})"


def rotate(x: float, y: float, degrees: float) -> XY:
    """KiCad's rotation of a point in its y-down frame: counter-clockwise on screen."""
    if not degrees:
        return x, y
    angle = math.radians(degrees)
    cos, sin = math.cos(angle), math.sin(angle)
    return x * cos + y * sin, -x * sin + y * cos


def arc_points(start: XY, mid: XY, end: XY) -> list[XY]:
    """Points along the circular arc from ``start`` through ``mid`` to ``end``."""
    (ax, ay), (bx, by), (cx, cy) = start, mid, end
    determinant = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(determinant) < 1e-12:
        return [start, end]
    a2, b2, c2 = ax * ax + ay * ay, bx * bx + by * by, cx * cx + cy * cy
    ox = (a2 * (by - cy) + b2 * (cy - ay) + c2 * (ay - by)) / determinant
    oy = (a2 * (cx - bx) + b2 * (ax - cx) + c2 * (bx - ax)) / determinant
    radius = math.hypot(ax - ox, ay - oy)
    first = math.atan2(ay - oy, ax - ox)
    through = (math.atan2(by - oy, bx - ox) - first) % (2 * math.pi)
    sweep = (math.atan2(cy - oy, cx - ox) - first) % (2 * math.pi)
    if through > sweep:  # the mid point lies the other way round
        sweep -= 2 * math.pi
    steps = max(2, math.ceil(abs(sweep) / _ARC_STEP))
    points = [(ox + radius * math.cos(first + sweep * step / steps), oy + radius * math.sin(first + sweep * step / steps)) for step in range(steps)]
    return points + [end]


def bezier_points(points: Sequence[XY], segments: int = 16) -> list[XY]:
    """The cubic Bezier of four control points as ``segments`` + 1 points, both ends included."""
    if len(points) != 4:
        return list(points)
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = points
    out = []
    for step in range(segments + 1):
        t = step / segments
        u = 1 - t
        out.append((
            u ** 3 * x0 + 3 * u * u * t * x1 + 3 * u * t * t * x2 + t ** 3 * x3,
            u ** 3 * y0 + 3 * u * u * t * y1 + 3 * u * t * t * y2 + t ** 3 * y3,
        ))
    return out


def area(polygon: Sequence[XY]) -> float:
    """The signed area: positive when the points run counter-clockwise (in a y-up frame)."""
    return 0.5 * sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(polygon, [*polygon[1:], polygon[0]])) if polygon else 0.0


def inside(point: XY, polygon: Sequence[XY]) -> bool:
    """Even-odd: KiCad's fills are single outlines with their holes cut in by slits."""
    x, y = point
    found = False
    count = len(polygon)
    for index in range(count):
        (x1, y1), (x2, y2) = polygon[index], polygon[(index + 1) % count]
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            found = not found
    return found


def hull(points: Iterable[XY]) -> list[XY]:
    """The convex hull, counter-clockwise (in a y-up frame), without repeated points."""
    unique = sorted(set(points))
    if len(unique) < 3:
        return unique

    def cross(o: XY, a: XY, b: XY) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[XY] = []
    for p in unique:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: list[XY] = []
    for p in reversed(unique):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def box(points: Iterable[XY]) -> list[XY]:
    """The corners of the box round ``points``; none for no points."""
    points = list(points)
    if not points:
        return []
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return [(min(xs), min(ys)), (max(xs), min(ys)), (max(xs), max(ys)), (min(xs), max(ys))]


# --- distances -----------------------------------------------------------------------


def segment_distance(point: XY, a: XY, b: XY) -> float:
    """How far ``point`` is from the segment ``a``-``b``."""
    (px, py), (ax, ay), (bx, by) = point, a, b
    dx, dy = bx - ax, by - ay
    length = dx * dx + dy * dy
    t = 0.0 if length == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def polyline_distance(point: XY, points: Sequence[XY]) -> float:
    """How far ``point`` is from the open polyline ``points``."""
    if len(points) == 1:
        return math.hypot(point[0] - points[0][0], point[1] - points[0][1])
    return min(segment_distance(point, a, b) for a, b in zip(points, points[1:]))


def polygon_distance(point: XY, polygon: Sequence[XY]) -> float:
    """0 inside ``polygon``, else the distance to its edge."""
    if len(polygon) >= 3 and inside(point, polygon):
        return 0.0
    if not polygon:
        return math.inf
    return polyline_distance(point, [*polygon, polygon[0]])


def _orientation(a: XY, b: XY, c: XY) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _segments_cross(a: XY, b: XY, c: XY, d: XY) -> bool:
    """Whether the segments ``a``-``b`` and ``c``-``d`` meet (a shared point counts)."""
    o1, o2 = _orientation(a, b, c), _orientation(a, b, d)
    o3, o4 = _orientation(c, d, a), _orientation(c, d, b)
    if (o1 > 0) != (o2 > 0) and (o3 > 0) != (o4 > 0) and o1 != 0 and o2 != 0 and o3 != 0 and o4 != 0:
        return True
    # Collinear or touching: an end of one lies on the other.
    return any(
        _orientation(p, q, r) == 0 and min(p[0], q[0]) <= r[0] <= max(p[0], q[0]) and min(p[1], q[1]) <= r[1] <= max(p[1], q[1])
        for p, q, r in ((a, b, c), (a, b, d), (c, d, a), (c, d, b))
    )


def segments_distance(a: XY, b: XY, c: XY, d: XY) -> float:
    """How far the segment ``a``-``b`` is from the segment ``c``-``d``: 0 when they meet."""
    if _segments_cross(a, b, c, d):
        return 0.0
    return min(segment_distance(a, c, d), segment_distance(b, c, d), segment_distance(c, a, b), segment_distance(d, a, b))


def _bounds(points: Sequence[XY]) -> tuple[float, float, float, float]:
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def _edges_in(points: Sequence[XY], region: tuple[float, float, float, float]) -> list[tuple[XY, XY]]:
    """The polygon's edges whose bounding box reaches ``region``: only those can meet an edge inside it."""
    left, top, right, bottom = region
    return [(a, b) for a, b in zip(points, [*points[1:], points[0]])
            if min(a[0], b[0]) <= right and max(a[0], b[0]) >= left and min(a[1], b[1]) <= bottom and max(a[1], b[1]) >= top]


# Below this many edge pairs every pair is tested; above it the second polygon's edges are bucketed.
_PAIRS_DIRECT = 4096


def polygons_overlap(first: Sequence[XY], second: Sequence[XY]) -> bool:
    """Whether two polygons share any area or touch: a point of one inside the other, or two
    edges that meet.

    Only edges inside the region both polygons' boxes share can meet, and each is tested only against
    the other's edges in the same cells of a grid over that region: two pours of thousands of vertices
    that do not touch cost about their edge counts, not their product."""
    if len(first) < 3 or len(second) < 3:
        return False
    if inside(first[0], second) or inside(second[0], first):
        return True
    a_box, b_box = _bounds(first), _bounds(second)
    region = (max(a_box[0], b_box[0]), max(a_box[1], b_box[1]), min(a_box[2], b_box[2]), min(a_box[3], b_box[3]))
    if region[0] > region[2] or region[1] > region[3]:
        return False
    mine, theirs = _edges_in(first, region), _edges_in(second, region)
    if not mine or not theirs:
        return False
    if len(mine) * len(theirs) <= _PAIRS_DIRECT:
        return any(_segments_cross(a, b, c, d) for a, b in mine for c, d in theirs)
    across = max(1, math.isqrt(len(theirs)))
    left, top = region[0], region[1]
    width = max(region[2] - left, 1e-9) / across
    height = max(region[3] - top, 1e-9) / across

    def cells(a: XY, b: XY) -> Iterator[tuple[int, int]]:
        x0 = min(across - 1, max(0, int((min(a[0], b[0]) - left) / width)))
        x1 = min(across - 1, max(0, int((max(a[0], b[0]) - left) / width)))
        y0 = min(across - 1, max(0, int((min(a[1], b[1]) - top) / height)))
        y1 = min(across - 1, max(0, int((max(a[1], b[1]) - top) / height)))
        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                yield x, y

    grid: dict[tuple[int, int], list[int]] = {}
    for index, (c, d) in enumerate(theirs):
        for cell in cells(c, d):
            grid.setdefault(cell, []).append(index)
    for a, b in mine:
        tested: set[int] = set()
        for cell in cells(a, b):
            for index in grid.get(cell, ()):
                if index not in tested:
                    tested.add(index)
                    c, d = theirs[index]
                    if _segments_cross(a, b, c, d):
                        return True
    return False
