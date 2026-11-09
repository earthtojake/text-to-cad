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

Every answer is the same bits on every platform: IEEE-754's + - * / and sqrt (numpy's elementwise ones as well)
and CPython's own ``math.hypot``, never the C library's atan2 or hypot, which round some arguments differently on
glibc, Apple's libm and the MSVC runtime. Whether a point is on an arc's sweep is a cross-product test against the
arc's ends, not an angle.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

__all__ = ["Shape", "segment_point_distance", "segments_distance"]

XY = tuple[float, float]


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
        return _grid_length(X - ax, Y - ay)
    t = np.clip(((X - ax) * dx + (Y - ay) * dy) / length2, 0.0, 1.0)
    return _grid_length(X - ax - t * dx, Y - ay - t * dy)


def _grid_length(dx: np.ndarray, dy: np.ndarray) -> np.ndarray:
    """sqrt(dx^2 + dy^2), elementwise: correctly rounded steps, alike on every platform (``np.hypot`` is the C
    library's, which is not)."""
    return np.sqrt(dx * dx + dy * dy)


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


def _on_sweep(vx, vy, sx: float, sy: float, ex: float, ey: float, major: bool):
    """Whether the direction ``(vx, vy)`` from an arc's centre lies on its sweep, the sweep turning from the
    direction ``s`` to ``e`` the way x turns to y, by more than half a turn where ``major``: inside both half planes
    of its ends for a sweep of half a turn or less, inside either for more. Its ends and its centre count. Scalars
    or numpy arrays alike."""
    after_start = sx * vy - sy * vx >= 0
    before_end = vx * ey - vy * ex >= 0
    return (after_start | before_end) if major else (after_start & before_end)


@dataclass(frozen=True)
class Shape:
    """A core grown by ``radius``: ``kind`` is ``"point"`` (``points`` one point), ``"segment"`` (two),
    ``"polygon"`` (a closed ring, the last point joined to the first; even-odd inside) or ``"arc"`` (``points`` its
    centre, start and end; ``arc`` = (its radius, the point it was drawn through, whether it turns from start to
    end the way x turns to y, whether by more than half a turn), in KiCad's frame). ``box`` is the shape's
    bounding box, its radius included."""

    kind: str
    points: tuple[XY, ...]
    radius: float = 0.0
    arc: tuple[float, XY, bool, bool] | None = None
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
        # The way it turns is the way the three points do (the determinant is twice their orientation); it turns by
        # more than half a turn where the centre is on the mid point's side of the chord from start to end.
        turns_up = determinant > 0
        side, centre_side = _cross(ax, ay, cx, cy, bx, by), _cross(ax, ay, cx, cy, ox, oy)
        major = (side > 0 and centre_side > 0) or (side < 0 and centre_side < 0)
        reach = big + radius  # a box round the whole circle: generous, never short
        return Shape("arc", ((ox, oy), start, end), radius, (big, (bx, by), turns_up, major),
                     (ox - reach, oy - reach, ox + reach, oy + reach))

    # --- asking them -------------------------------------------------------------------------------------

    def grid_distance(self, X: np.ndarray, Y: np.ndarray) -> np.ndarray:
        """How far each node (``X``, ``Y``: arrays of one shape) is from the shape: 0 inside it."""
        if self.kind == "point":
            (px, py), = self.points
            core = _grid_length(X - px, Y - py)
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

    def _sweep(self) -> tuple[float, float, float, float, bool]:
        """The arc's end directions from its centre, in the order it turns the way x turns to y, and whether it
        turns by more than half a turn: what ``_on_sweep`` asks."""
        (ox, oy), (ax, ay), (cx, cy) = self.points
        assert self.arc is not None
        _, _, turns_up, major = self.arc
        s, e = (ax - ox, ay - oy), (cx - ox, cy - oy)
        if not turns_up:
            s, e = e, s
        return s[0], s[1], e[0], e[1], major

    def _grid_arc(self, X: np.ndarray, Y: np.ndarray) -> np.ndarray:
        (ox, oy), start, end = self.points
        assert self.arc is not None
        big = self.arc[0]
        VX, VY = X - ox, Y - oy
        on = _on_sweep(VX, VY, *self._sweep())
        to_circle = np.abs(_grid_length(VX, VY) - big)
        to_ends = np.minimum(_grid_length(X - start[0], Y - start[1]), _grid_length(X - end[0], Y - end[1]))
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
        big = self.arc[0]
        to_ends = min(math.hypot(px - start[0], py - start[1]), math.hypot(px - end[0], py - end[1]))
        if _on_sweep(px - ox, py - oy, *self._sweep()):
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
        big = self.arc[0]
        sweep = self._sweep()
        best = min(self._arc_point(ax, ay), self._arc_point(bx, by),
                   segment_point_distance(ax, ay, bx, by, start[0], start[1]),
                   segment_point_distance(ax, ay, bx, by, end[0], end[1]))
        dx, dy = bx - ax, by - ay
        length2 = dx * dx + dy * dy
        if length2 <= 0.0:
            return best
        t = max(0.0, min(1.0, ((ox - ax) * dx + (oy - ay) * dy) / length2))
        qx, qy = ax + t * dx, ay + t * dy
        if _on_sweep(qx - ox, qy - oy, *sweep):
            best = min(best, abs(math.hypot(qx - ox, qy - oy) - big))
        # Where the segment meets the circle: |a + s d - o|^2 = R^2.
        fx, fy = ax - ox, ay - oy
        bq = 2 * (fx * dx + fy * dy)
        cq = fx * fx + fy * fy - big * big
        disc = bq * bq - 4 * length2 * cq
        if disc >= 0:
            root = math.sqrt(disc)
            for s in ((-bq - root) / (2 * length2), (-bq + root) / (2 * length2)):
                if 0.0 <= s <= 1.0 and _on_sweep(ax + s * dx - ox, ay + s * dy - oy, *sweep):
                    return 0.0
        return best

    def contains(self, px: float, py: float) -> bool:
        """Whether the point lies in the shape (its boundary included)."""
        return self.point_distance(px, py) <= 0.0
