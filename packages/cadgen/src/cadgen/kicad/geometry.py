"""Points and polygons the KiCad readers and writers share, and a board's script frame.

A point is ``(x, y)`` in millimetres, in whatever frame the caller works in;
nothing here changes frames but :func:`script_frame`.
"""

from __future__ import annotations

import math
from typing import Callable, Iterable, Sequence

from cadgen.kicad import sexpr

__all__ = [
    "ISO_PAGES",
    "XY",
    "arc_points",
    "area",
    "bezier_points",
    "board_origin",
    "box",
    "format_xy",
    "hull",
    "inside",
    "nm",
    "script_frame",
]

XY = tuple[float, float]

#: The landscape ISO sheets KiCad offers, smallest first: (name, width, height) in millimetres.
ISO_PAGES = (("A4", 297.0, 210.0), ("A3", 420.0, 297.0), ("A2", 594.0, 420.0), ("A1", 841.0, 594.0), ("A0", 1189.0, 841.0))

_ARC_STEP = math.radians(10)


def nm(value: float) -> float:
    """A length rounded to KiCad's resolution, one nanometre (never ``-0.0``)."""
    rounded = round(float(value), 6)
    return 0.0 if rounded == 0 else rounded


def format_xy(point: XY) -> str:
    return f"({point[0]:g}, {point[1]:g})"


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


def board_origin(tree: list) -> XY:
    """A board's drill/place origin in KiCad's frame: where cadgen puts the script's (0, 0)."""
    setup = sexpr.find(tree, "setup")
    origin = sexpr.find(setup, "aux_axis_origin") if setup is not None else None
    if origin is None or len(origin) < 3:
        return 0.0, 0.0
    return float(origin[1]), float(origin[2])


def script_frame(origin: XY, digits: int = 6) -> Callable[[float, float], XY]:
    """KiCad's frame to the board script's: from the drill/place ``origin``, y up, rounded to
    ``digits`` decimals (6 is KiCad's nanometre)."""

    def move(x: float, y: float) -> XY:
        dx, dy = round(x - origin[0], digits), round(origin[1] - y, digits)
        return 0.0 if dx == 0 else dx, 0.0 if dy == 0 else dy

    return move
