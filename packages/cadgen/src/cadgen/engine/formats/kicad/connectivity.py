"""Which copper touches which: a board's connectivity, and the ratsnest of what is still apart.

KiCad's connectivity is geometric: two pieces of copper on one net are joined
when they share a layer and overlap. This module answers the same question from
the file alone -- a pad is its polygon, a track a segment of a width, a via a
disc on the layers it spans, a pour its filled polygons -- so the viewer can draw
the ratsnest (one line per connection still to make) without a DRC. No
clearance, no rule: touching copper is joined, nothing else is.

A net's copper is first filed in a grid of cells so that only neighbours are
tested against each other; a pour is tested against the pads on it by their
anchors before any edge is walked, since a pour that joins a pad almost always
holds its centre or a vertex of its own inside the pad. The pieces that remain
apart and hold a pad are joined by their shortest tree, each line between the two
nearest pads' centres, as KiCad draws its own; copper on a net with no pad (a
dangling track, a stray via) is nothing to connect, and draws no line.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, Sequence

from cadgen.engine.formats.kicad.geometry import XY, inside, polygon_distance, polygons_overlap, segment_distance, segments_distance

__all__ = ["Copper", "ratsnest"]

# The grid's cell, millimetres: a few pads wide, so a pad meets its neighbours and little else.
_CELL = 2.0


@dataclass(frozen=True)
class Copper:
    """One piece of copper on a net: a polygon (a pad, a pour's fill), a segment of a width (a
    track) or a disc (a via), on ``layers``. ``anchors`` are where a ratsnest line may end on it."""

    net: str
    layers: frozenset[str]
    shape: str  # "polygon", "segment" or "disc"
    points: tuple[XY, ...]  # the polygon's vertices, the segment's two ends, or the disc's centre
    width: float = 0.0  # a segment's width, or a disc's diameter
    anchors: tuple[XY, ...] = ()
    pad: bool = False  # a pad: the ratsnest ends on pads first
    box: tuple[float, float, float, float] = field(default=(0.0, 0.0, 0.0, 0.0), compare=False)

    @staticmethod
    def polygon(net: str, layers: Iterable[str], points: Sequence[XY], *, anchor: XY | None = None, pad: bool = False) -> "Copper":
        pts = tuple(points)
        return Copper(net, frozenset(layers), "polygon", pts, 0.0, (anchor,) if anchor else (), pad, _box(pts, 0.0))

    @staticmethod
    def segment(net: str, layer: str, start: XY, end: XY, width: float) -> "Copper":
        return Copper(net, frozenset([layer]), "segment", (start, end), width, (start, end), False, _box((start, end), width / 2))

    @staticmethod
    def disc(net: str, layers: Iterable[str], centre: XY, diameter: float) -> "Copper":
        return Copper(net, frozenset(layers), "disc", (centre,), diameter, (centre,), False, _box((centre,), diameter / 2))


def _box(points: Sequence[XY], reach: float) -> tuple[float, float, float, float]:
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return min(xs) - reach, min(ys) - reach, max(xs) + reach, max(ys) + reach


def _boxes_meet(a: Copper, b: Copper) -> bool:
    return a.box[0] <= b.box[2] and b.box[0] <= a.box[2] and a.box[1] <= b.box[3] and b.box[1] <= a.box[3]


def _segment_polygon_distance(a: XY, b: XY, polygon: Sequence[XY]) -> float:
    """How far the segment ``a``-``b`` is from ``polygon``: 0 when it enters or crosses it."""
    if inside(a, polygon) or inside(b, polygon):
        return 0.0
    return min(segments_distance(a, b, p, q) for p, q in zip(polygon, [*polygon[1:], polygon[0]]))


def _polygons_touch(a: Copper, b: Copper) -> bool:
    """Whether two polygons overlap, the cheap tests first: a pour of thousands of vertices is
    almost always found holding the pad's anchor, or a vertex of its own inside the pad."""
    small, large = (a, b) if len(a.points) <= len(b.points) else (b, a)
    if any(inside(anchor, large.points) for anchor in small.anchors):
        return True
    left, top, right, bottom = small.box
    for vertex in large.points:
        if left <= vertex[0] <= right and top <= vertex[1] <= bottom and inside(vertex, small.points):
            return True
    return polygons_overlap(small.points, large.points)


def touches(a: Copper, b: Copper) -> bool:
    """Whether two pieces of copper are joined: they share a layer and their shapes meet."""
    if not (a.layers & b.layers) or not _boxes_meet(a, b):
        return False
    first, second = sorted((a, b), key=lambda item: item.shape)  # disc < polygon < segment
    if first.shape == "disc":
        centre, reach = first.points[0], first.width / 2
        if second.shape == "disc":
            return math.dist(centre, second.points[0]) <= reach + second.width / 2
        if second.shape == "polygon":
            return polygon_distance(centre, second.points) <= reach
        return segment_distance(centre, *second.points) <= reach + second.width / 2
    if first.shape == "polygon":
        if second.shape == "polygon":
            return _polygons_touch(first, second)
        return _segment_polygon_distance(*second.points, first.points) <= second.width / 2
    return segments_distance(*first.points, *second.points) <= (first.width + second.width) / 2


class _Groups:
    def __init__(self, count: int):
        self.parent = list(range(count))

    def find(self, index: int) -> int:
        while self.parent[index] != index:
            self.parent[index] = self.parent[self.parent[index]]
            index = self.parent[index]
        return index

    def join(self, a: int, b: int) -> None:
        a, b = self.find(a), self.find(b)
        if a != b:
            self.parent[max(a, b)] = min(a, b)


def _candidate_pairs(items: Sequence[Copper]) -> Iterable[tuple[int, int]]:
    """Pairs of items whose boxes share a grid cell, each pair once."""
    cells: dict[tuple[int, int], list[int]] = {}
    for index, item in enumerate(items):
        left, top, right, bottom = (math.floor(value / _CELL) for value in item.box)
        for cx in range(left, right + 1):
            for cy in range(top, bottom + 1):
                cells.setdefault((cx, cy), []).append(index)
    seen: set[tuple[int, int]] = set()
    for members in cells.values():
        for position, a in enumerate(members):
            for b in members[position + 1:]:
                pair = (a, b) if a < b else (b, a)
                if pair not in seen:
                    seen.add(pair)
                    yield pair


def _clusters(items: Sequence[Copper]) -> list[list[Copper]]:
    groups = _Groups(len(items))
    for a, b in _candidate_pairs(items):
        if groups.find(a) != groups.find(b) and touches(items[a], items[b]):
            groups.join(a, b)
    found: dict[int, list[Copper]] = {}
    for index, item in enumerate(items):
        found.setdefault(groups.find(index), []).append(item)
    return list(found.values())


def _anchors(cluster: Sequence[Copper]) -> list[XY]:
    """Where a line to this cluster ends: its pads' centres; none for a cluster without a pad."""
    return [anchor for item in cluster if item.pad for anchor in item.anchors]


def _nearest(a: Sequence[XY], b: Sequence[XY]) -> tuple[float, XY, XY]:
    best = (math.inf, a[0], b[0])
    for p in a:
        for q in b:
            distance = math.dist(p, q)
            if distance < best[0]:
                best = (distance, p, q)
    return best


def ratsnest(items: Iterable[Copper]) -> list[tuple[XY, XY]]:
    """The lines joining each net's separate pieces of copper: the net's clusters, each a
    group of touching items with a pad in it, joined by their shortest tree between nearest pads."""
    by_net: dict[str, list[Copper]] = {}
    for item in items:
        if item.net:
            by_net.setdefault(item.net, []).append(item)
    lines: list[tuple[XY, XY]] = []
    for net in sorted(by_net):
        clusters = [_anchors(cluster) for cluster in _clusters(by_net[net])]
        clusters = [anchors for anchors in clusters if anchors]
        if len(clusters) < 2:
            continue
        # Prim's tree over the clusters, each step the nearest pair of anchors to the tree.
        joined = [0]
        apart = list(range(1, len(clusters)))
        while apart:
            best = None
            for index in apart:
                for member in joined:
                    distance, p, q = _nearest(clusters[member], clusters[index])
                    if best is None or distance < best[0]:
                        best = (distance, p, q, index)
            assert best is not None
            lines.append((best[1], best[2]))
            joined.append(best[3])
            apart.remove(best[3])
    return lines
