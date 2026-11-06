"""Exact checks and the pull-tight pass: copper a person would draw, from the path the search found.

``Obstacles`` holds every obstacle with its exact shape and the clearance it keeps, filed in a grid of cells, and
answers whether a track segment or a via of a net is clear of all of them by the board's rules, in continuous
geometry (float64): nothing here rounds to the search's grid. The pull-tight pass (``pull``) and the final check
of every route ask it.

``pull`` takes a layer's run of a path (octolinear, every segment clear) between two fixed ends and replaces
what it can with fewer, shorter octolinear segments: from each vertex, the farthest later vertex reachable by a
clear straight segment, or by a clear elbow of a 45-degree and a straight leg (either order), replaces the
vertices between; until a pass changes nothing. Every segment it keeps was checked exactly, so the run stays
clear, and a straight or an elbow is the shortest octolinear way between its two ends, so the run never grows.
Points are integer nanometres, KiCad's own unit, so a 45-degree leg is exactly 45 degrees.
"""

from __future__ import annotations

import math
from typing import Callable, Sequence

from .shapes import Shape, segment_point_distance, segments_distance

__all__ = ["Obstacles", "elbows", "octolinear", "pull", "straighten"]

NM = 1_000_000  # nanometres per millimetre
Point = tuple[int, int]  # nanometres


def octolinear(a: Point, b: Point) -> bool:
    dx, dy = b[0] - a[0], b[1] - a[1]
    return dx == 0 or dy == 0 or abs(dx) == abs(dy)


def elbows(a: Point, b: Point) -> list[Point]:
    """The corners of the two octolinear elbows from ``a`` to ``b``: the 45-degree leg first, then the straight
    leg first; none when ``a`` to ``b`` is octolinear already."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    if dx == 0 or dy == 0 or abs(dx) == abs(dy):
        return []
    sx, sy = (1 if dx > 0 else -1), (1 if dy > 0 else -1)
    run = min(abs(dx), abs(dy))
    diagonal_first = (a[0] + sx * run, a[1] + sy * run)
    straight_first = (b[0] - sx * run, b[1] - sy * run)
    return [diagonal_first, straight_first]


def straighten(points: Sequence[Point]) -> list[Point]:
    """``points`` without repeats and without the middle of any three in one straight line, same direction."""
    out: list[Point] = []
    for point in points:
        if out and out[-1] == point:
            continue
        if len(out) >= 2:
            (ax, ay), (bx, by) = out[-2], out[-1]
            if (bx - ax) * (point[1] - by) == (by - ay) * (point[0] - bx) and (bx - ax) * (point[0] - bx) + (by - ay) * (point[1] - by) >= 0:
                out[-1] = point
                continue
        out.append(point)
    return out


def pull(points: Sequence[Point], clear: Callable[[Point, Point], bool], passes: int = 4) -> list[Point]:
    """The run ``points`` (its ends fixed) pulled tight: see the module's doc. ``clear(a, b)`` answers whether a
    segment may be added."""
    run = straighten(points)
    for _ in range(passes):
        out = [run[0]]
        i, last = 0, len(run) - 1
        while i < last:
            j = i + 1  # the run's own next segment, octolinear and clear already, unless a later vertex is reachable
            for far in range(last, i + 1, -1):
                a, b = run[i], run[far]
                if octolinear(a, b):
                    if clear(a, b):
                        j = far
                        break
                    continue
                corner = next((c for c in elbows(a, b) if clear(a, c) and clear(c, b)), None)
                if corner is not None:
                    out.append(corner)
                    j = far
                    break
            out.append(run[j])
            i = j
        out = straighten(out)
        if out == run:
            break
        run = out
    return run


class Obstacles:
    """Every obstacle a route keeps clear of, exact: copper by net and clearance, holes, keep-outs, pads (no via
    lands in one) and the board's edge. ``reach``: no obstacle affects anything further than this from it."""

    def __init__(self, layers: int, reach: float, cell: float = 1.0):
        self.layers = layers
        self.reach = reach
        self.cell = cell
        self._items: list[tuple[str, Shape, int, float]] = []  # kind, shape, net, clearance
        self._cells: dict[tuple[int, int, int], list[int]] = {}  # (layer or -1, cx, cy) -> items
        self._rings: list[tuple[tuple[float, float], ...]] = []

    def _file(self, index: int, box: tuple[float, float, float, float], layers: Sequence[int]) -> None:
        c = self.cell
        x0, y0 = math.floor((box[0] - self.reach) / c), math.floor((box[1] - self.reach) / c)
        x1, y1 = math.floor((box[2] + self.reach) / c), math.floor((box[3] + self.reach) / c)
        for layer in layers:
            for cx in range(x0, x1 + 1):
                for cy in range(y0, y1 + 1):
                    self._cells.setdefault((layer, cx, cy), []).append(index)

    def add(self, kind: str, shape: Shape, layers: Sequence[int], net: int, clearance: float = 0.0) -> None:
        """``kind``: ``copper`` (of ``net``, keeping ``clearance``), ``hole`` (``net``'s drill: other copper keeps
        ``clearance`` from it, every new drill the hole-to-hole gap), ``tracks`` (a keep-out of tracks on
        ``layers``), ``vias`` (a keep-out of vias), ``pad`` (any pad's copper: no via in it) or ``edge`` (a piece of
        the board's outline)."""
        self._items.append((kind, shape, net, clearance))
        self._file(len(self._items) - 1, shape.box, [-1] if kind in ("vias", "pad") else layers)

    def set_edge(self, rings: Sequence[Sequence[tuple[float, float]]]) -> None:
        self._rings = [tuple(ring) for ring in rings]
        everywhere = list(range(self.layers))
        for ring in rings:
            for a, b in zip(ring, ring[1:]):
                self.add("edge", Shape.segment(a, b, 0.0), everywhere, -1)

    def _near(self, box: tuple[float, float, float, float], layers: Sequence[int]) -> list[int]:
        c = self.cell
        x0, y0, x1, y1 = (math.floor(box[0] / c), math.floor(box[1] / c), math.floor(box[2] / c), math.floor(box[3] / c))
        found: dict[int, None] = {}
        for layer in layers:
            for cx in range(x0, x1 + 1):
                for cy in range(y0, y1 + 1):
                    for index in self._cells.get((layer, cx, cy), ()):
                        found[index] = None
        return list(found)

    def inside(self, x: float, y: float) -> bool:
        """Whether the point is on the board: inside its outline, even-odd over every ring."""
        found = False
        for ring in self._rings:
            count = len(ring)
            for k in range(count - 1):
                (x1, y1), (x2, y2) = ring[k], ring[k + 1]
                if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
                    found = not found
        return found

    def segment_clear(self, layer: int, a: tuple[float, float], b: tuple[float, float], half: float, net: int,
                      clearance: float, holes: float, edge: float, epsilon: float) -> bool:
        """Whether a track of ``net`` on ``layer`` from ``a`` to ``b`` (mm), ``half`` its half width, keeping
        ``clearance`` from other nets' copper (and their own, where larger), ``holes`` from their drills and
        ``edge`` from the board's edge, keeps them all, ``epsilon`` to spare."""
        if self._rings and not self.inside(*a):
            return False
        box = (min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]))
        for index in self._near(box, [layer]):
            kind, shape, owner, keep = self._items[index]
            if kind == "copper":
                if owner == net:
                    continue
                need = max(keep, clearance)
            elif kind == "hole":
                if owner == net:
                    continue
                need = holes
            elif kind == "tracks":
                need = 0.0
            elif kind == "edge":
                need = edge
            else:
                continue
            if shape.segment_distance(a, b) - half < need + epsilon:
                return False
        return True

    def via_clear(self, at: tuple[float, float], radius: float, drill: float, net: int, clearance: float,
                  holes: float, hole_gap: float, edge: float, epsilon: float) -> bool:
        """Whether a through via of ``net`` at ``at`` (its copper ``radius``, its drill's ``drill``) keeps every
        rule: its copper from other copper and drills, its drill from other copper (``holes``) and from every hole
        (``hole_gap``, its own net's too), the edge, the via keep-outs, and no pad under it."""
        x, y = at
        if self._rings and not self.inside(x, y):
            return False
        box = (x, y, x, y)
        for index in self._near(box, [*range(self.layers), -1]):
            kind, shape, owner, keep = self._items[index]
            gap = shape.point_distance(x, y)
            if kind == "copper":
                if owner != net and (gap - radius < max(keep, clearance) + epsilon or gap - drill < holes + epsilon):
                    return False
            elif kind == "hole":
                if gap - drill < hole_gap + epsilon or (owner != net and gap - radius < holes + epsilon):
                    return False
            elif kind in ("vias", "pad"):
                if gap - radius < epsilon:
                    return False
            elif kind == "edge":
                if gap - radius < edge + epsilon:
                    return False
        return True
