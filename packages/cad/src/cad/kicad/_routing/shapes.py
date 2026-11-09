"""Exact shapes for the router: a piece of copper, a hole or a keep-out as a core grown by a radius.

The core is a point, a segment, a polygon or a circular arc; the shape is every point within ``radius`` of it.
A round pad is a point grown by its radius, a track a segment grown by half its width, an oval pad a segment
grown by half its narrow side, a rounded rectangle the rectangle inside its corners grown by the corner
radius, an arc track an arc grown by half its width. Every copper shape KiCad draws for a pad, a track or a via
is one of these or a union of them, so a distance here is the shape's own, never a polygon's chords: the
clearance the router keeps is the clearance DRC measures.

Two questions are asked of a shape: how far each node of a grid is from it (``grid_distance``, vectorized with
numpy, for the clearance fields), and how far a segment is from it (``segment_distance``, exact, in float64,
for the pull-tight pass and the final check). Both answer 0 where they touch or overlap: the router needs the
gap, never the depth. Millimetres, KiCad's frame (y down) throughout.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

__all__ = ["Shape", "segment_point_distance", "segments_distance"]

XY = tuple[float, float]
_TAU = 2.0 * math.pi


def segment_point_distance(ax: float, ay: float, bx: float, by: float, px: float, py: float) -> float:
    """The distance from the point ``p`` to the segment ``a``-``b``."""
    dx, dy = bx - ax, by - ay
    length2 = dx * dx + dy * dy
    if length2 <= 0.0:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / length2
    t = 0.0 if t < 0.0 else 1.0 if t > 1.0 else t
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def _cross(ax: float, ay: float, bx: float, by: float, cx: float, cy: float) -> float:
    return (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)


def _segments_cross(ax: float, ay: float, bx: float, by: float, cx: float, cy: float, dx: float, dy: float) -> bool:
    """Whether the segments a-b and c-d share a point (touching counts)."""
    d1, d2 = _cross(cx, cy, dx, dy, ax, ay), _cross(cx, cy, dx, dy, bx, by)
    d3, d4 = _cross(ax, ay, bx, by, cx, cy), _cross(ax, ay, bx, by, dx, dy)
    if ((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) and ((d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0)):
        return True

    def on(px: float, py: float, qx: float, qy: float, rx: float, ry: float) -> bool:  # r on segment p-q, collinear
        return min(px, qx) <= rx <= max(px, qx) and min(py, qy) <= ry <= max(py, qy)

    return ((d1 == 0 and on(cx, cy, dx, dy, ax, ay)) or (d2 == 0 and on(cx, cy, dx, dy, bx, by))
            or (d3 == 0 and on(ax, ay, bx, by, cx, cy)) or (d4 == 0 and on(ax, ay, bx, by, dx, dy)))


def segments_distance(ax: float, ay: float, bx: float, by: float, cx: float, cy: float, dx: float, dy: float) -> float:
    """The distance between the segments a-b and c-d: 0 when they cross or touch."""
    if _segments_cross(ax, ay, bx, by, cx, cy, dx, dy):
        return 0.0
    return min(segment_point_distance(ax, ay, bx, by, cx, cy), segment_point_distance(ax, ay, bx, by, dx, dy),
               segment_point_distance(cx, cy, dx, dy, ax, ay), segment_point_distance(cx, cy, dx, dy, bx, by))


def _grid_segment_distance(X: np.ndarray, Y: np.ndarray, ax: float, ay: float, bx: float, by: float) -> np.ndarray:
    dx, dy = bx - ax, by - ay
    length2 = dx * dx + dy * dy
    if length2 <= 0.0:
        return np.hypot(X - ax, Y - ay)
    t = np.clip(((X - ax) * dx + (Y - ay) * dy) / length2, 0.0, 1.0)
    return np.hypot(X - ax - t * dx, Y - ay - t * dy)


def _grid_inside(X: np.ndarray, Y: np.ndarray, ring: np.ndarray) -> np.ndarray:
    """Even-odd containment of each node in the closed ring (its points, the last joined to the first)."""
    found = np.zeros(X.shape, dtype=bool)
    x1, y1 = ring[:, 0], ring[:, 1]
    x2, y2 = np.roll(x1, -1), np.roll(y1, -1)
    for k in range(len(ring)):
        if y1[k] == y2[k]:
            continue
        straddles = (y1[k] > Y) != (y2[k] > Y)
        crossing = x1[k] + (Y - y1[k]) * (x2[k] - x1[k]) / (y2[k] - y1[k])
        found ^= straddles & (X < crossing)
    return found


def _inside(px: float, py: float, ring: Sequence[XY]) -> bool:
    found = False
    count = len(ring)
    for k in range(count):
        x1, y1 = ring[k]
        x2, y2 = ring[(k + 1) % count]
        if (y1 > py) != (y2 > py) and px < x1 + (py - y1) * (x2 - x1) / (y2 - y1):
            found = not found
    return found


def _angle_in(angle: float | np.ndarray, start: float, sweep: float) -> bool | np.ndarray:
    """Whether ``angle`` (radians) lies on the arc that starts at ``start`` and turns ``sweep`` (signed)."""
    if sweep >= 0:
        return np.mod(angle - start, _TAU) <= sweep + 1e-12
    return np.mod(start - angle, _TAU) <= -sweep + 1e-12


@dataclass(frozen=True)
class Shape:
    """A core grown by ``radius``: ``kind`` is ``"point"`` (``points`` one point), ``"segment"`` (two),
    ``"polygon"`` (a closed ring, the last point joined to the first; even-odd inside) or ``"arc"`` (its centre,
    then ``arc`` = (radius, start angle, signed sweep) in radians, in KiCad's frame). ``box`` is the shape's
    bounding box, its radius included."""

    kind: str
    points: tuple[XY, ...]
    radius: float = 0.0
    arc: tuple[float, float, float] | None = None
    box: tuple[float, float, float, float] = field(default=(0.0, 0.0, 0.0, 0.0), compare=False)
    _ring: np.ndarray | None = field(default=None, compare=False, repr=False)

    # --- making them -------------------------------------------------------------------------------------

    @staticmethod
    def point(x: float, y: float, radius: float) -> "Shape":
        return Shape("point", ((x, y),), radius, None, (x - radius, y - radius, x + radius, y + radius))

    @staticmethod
    def segment(a: XY, b: XY, radius: float) -> "Shape":
        if a == b:
            return Shape.point(a[0], a[1], radius)
        box = (min(a[0], b[0]) - radius, min(a[1], b[1]) - radius, max(a[0], b[0]) + radius, max(a[1], b[1]) + radius)
        return Shape("segment", (a, b), radius, None, box)

    @staticmethod
    def polygon(points: Sequence[XY], radius: float = 0.0) -> "Shape":
        ring = [tuple(map(float, point)) for point in points]
        if len(ring) > 1 and ring[0] == ring[-1]:
            ring = ring[:-1]
        if len(ring) == 1:
            return Shape.point(ring[0][0], ring[0][1], radius)
        if len(ring) == 2:
            return Shape.segment(ring[0], ring[1], radius)
        xs, ys = [p[0] for p in ring], [p[1] for p in ring]
        box = (min(xs) - radius, min(ys) - radius, max(xs) + radius, max(ys) + radius)
        return Shape("polygon", tuple(ring), radius, None, box, np.array(ring, dtype=float))

    @staticmethod
    def arc_through(start: XY, mid: XY, end: XY, radius: float) -> "Shape":
        """The arc from ``start`` through ``mid`` to ``end`` (KiCad's arc track), grown by ``radius``; three points
        on one line are the segment from ``start`` to ``end``."""
        (ax, ay), (bx, by), (cx, cy) = start, mid, end
        determinant = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
        if abs(determinant) < 1e-12:
            return Shape.segment(start, end, radius)
        a2, b2, c2 = ax * ax + ay * ay, bx * bx + by * by, cx * cx + cy * cy
        ox = (a2 * (by - cy) + b2 * (cy - ay) + c2 * (ay - by)) / determinant
        oy = (a2 * (cx - bx) + b2 * (ax - cx) + c2 * (bx - ax)) / determinant
        big = math.hypot(ax - ox, ay - oy)
        first = math.atan2(ay - oy, ax - ox)
        through = (math.atan2(by - oy, bx - ox) - first) % _TAU
        sweep = (math.atan2(cy - oy, cx - ox) - first) % _TAU
        if through > sweep:  # the mid point lies the other way round
            sweep -= _TAU
        reach = big + radius  # a box round the whole circle: generous, never short
        return Shape("arc", ((ox, oy), start, end), radius, (big, first, sweep), (ox - reach, oy - reach, ox + reach, oy + reach))

    # --- asking them -------------------------------------------------------------------------------------

    def grid_distance(self, X: np.ndarray, Y: np.ndarray) -> np.ndarray:
        """How far each node (``X``, ``Y``: arrays of one shape) is from the shape: 0 inside it."""
        if self.kind == "point":
            (px, py), = self.points
            core = np.hypot(X - px, Y - py)
        elif self.kind == "segment":
            (ax, ay), (bx, by) = self.points
            core = _grid_segment_distance(X, Y, ax, ay, bx, by)
        elif self.kind == "polygon":
            ring = self._ring
            assert ring is not None
            core = np.full(X.shape, np.inf)
            nxt = np.roll(ring, -1, axis=0)
            for (ax, ay), (bx, by) in zip(ring, nxt):
                np.minimum(core, _grid_segment_distance(X, Y, ax, ay, bx, by), out=core)
            core[_grid_inside(X, Y, ring)] = 0.0
        else:
            core = self._grid_arc(X, Y)
        return np.maximum(core - self.radius, 0.0)

    def _grid_arc(self, X: np.ndarray, Y: np.ndarray) -> np.ndarray:
        (ox, oy), start, end = self.points
        assert self.arc is not None
        big, first, sweep = self.arc
        on = _angle_in(np.arctan2(Y - oy, X - ox), first, sweep)
        to_circle = np.abs(np.hypot(X - ox, Y - oy) - big)
        to_ends = np.minimum(np.hypot(X - start[0], Y - start[1]), np.hypot(X - end[0], Y - end[1]))
        return np.where(on, np.minimum(to_circle, to_ends), to_ends)

    def point_distance(self, px: float, py: float) -> float:
        """How far the point is from the shape: 0 inside it."""
        if self.kind == "point":
            (qx, qy), = self.points
            core = math.hypot(px - qx, py - qy)
        elif self.kind == "segment":
            (ax, ay), (bx, by) = self.points
            core = segment_point_distance(ax, ay, bx, by, px, py)
        elif self.kind == "polygon":
            ring = self.points
            if _inside(px, py, ring):
                return 0.0
            core = min(segment_point_distance(a[0], a[1], b[0], b[1], px, py) for a, b in zip(ring, ring[1:] + ring[:1]))
        else:
            core = self._arc_point(px, py)
        return max(core - self.radius, 0.0)

    def _arc_point(self, px: float, py: float) -> float:
        (ox, oy), start, end = self.points
        assert self.arc is not None
        big, first, sweep = self.arc
        to_ends = min(math.hypot(px - start[0], py - start[1]), math.hypot(px - end[0], py - end[1]))
        if _angle_in(math.atan2(py - oy, px - ox), first, sweep):
            return min(abs(math.hypot(px - ox, py - oy) - big), to_ends)
        return to_ends

    def segment_distance(self, a: XY, b: XY) -> float:
        """How far the segment ``a``-``b`` is from the shape: 0 where they touch or overlap. Exact."""
        ax, ay = a
        bx, by = b
        if self.kind == "point":
            (px, py), = self.points
            core = segment_point_distance(ax, ay, bx, by, px, py)
        elif self.kind == "segment":
            (cx, cy), (dx, dy) = self.points
            core = segments_distance(ax, ay, bx, by, cx, cy, dx, dy)
        elif self.kind == "polygon":
            ring = self.points
            if _inside(ax, ay, ring) or _inside(bx, by, ring):
                return 0.0
            core = min(segments_distance(ax, ay, bx, by, p[0], p[1], q[0], q[1]) for p, q in zip(ring, ring[1:] + ring[:1]))
        else:
            core = self._arc_segment(ax, ay, bx, by)
        return max(core - self.radius, 0.0)

    def _arc_segment(self, ax: float, ay: float, bx: float, by: float) -> float:
        """The distance from a segment to the arc: the least of its ends' distances to the arc, the arc's ends'
        to the segment, and, where on the arc's sweep, the gap to the circle at the segment's nearest point to
        the centre and wherever the segment crosses the circle (0)."""
        (ox, oy), start, end = self.points
        assert self.arc is not None
        big, first, sweep = self.arc
        best = min(self._arc_point(ax, ay), self._arc_point(bx, by),
                   segment_point_distance(ax, ay, bx, by, start[0], start[1]),
                   segment_point_distance(ax, ay, bx, by, end[0], end[1]))
        dx, dy = bx - ax, by - ay
        length2 = dx * dx + dy * dy
        if length2 <= 0.0:
            return best
        t = max(0.0, min(1.0, ((ox - ax) * dx + (oy - ay) * dy) / length2))
        qx, qy = ax + t * dx, ay + t * dy
        if _angle_in(math.atan2(qy - oy, qx - ox), first, sweep):
            best = min(best, abs(math.hypot(qx - ox, qy - oy) - big))
        # Where the segment meets the circle: |a + s d - o|^2 = R^2.
        fx, fy = ax - ox, ay - oy
        bq = 2 * (fx * dx + fy * dy)
        cq = fx * fx + fy * fy - big * big
        disc = bq * bq - 4 * length2 * cq
        if disc >= 0:
            root = math.sqrt(disc)
            for s in ((-bq - root) / (2 * length2), (-bq + root) / (2 * length2)):
                if 0.0 <= s <= 1.0 and _angle_in(math.atan2(ay + s * dy - oy, ax + s * dx - ox), first, sweep):
                    return 0.0
        return best

    def contains(self, px: float, py: float) -> bool:
        """Whether the point lies in the shape (its boundary included)."""
        return self.point_distance(px, py) <= 0.0
