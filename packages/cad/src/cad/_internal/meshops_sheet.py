"""Plane geometry for a sheet's cut outline, numpy alone: what the flat pattern of a bent part
(``cad.build123d._dfm_sheet``) and a cut file (``cad.build123d._dfm_dxf``) are both measured with.

A **loop** is a closed outline in the XY plane: its points in order (the last joined back to the first),
with, for each segment (``points[i]`` to ``points[i + 1]``), whether it lies on a straight line of the
source (``straight``) and which source element it came from (``source``). Curves arrive sampled finely
enough (``arc_points``: a chord at most ``CHORD_MM`` from its arc) that every distance below is the
outline's to within that; a whole circle keeps its exact centre and radius (``circle``).

The measures: a loop's signed area (``area``), containment (``inside``, ``nest``), the distance between
two loops (``distance``), rays across the material or the void (``cast``), the narrowest material and
void about each loop (``widths``), the pockets of a loop off its convex hull (``pockets``: notches),
straight-sided protrusions (``tabs``), a loop crossing itself (``self_crossings``) or another
(``crossings``), and the smallest rectangle the points fit (``min_rectangle``) and their widths
(``feret``).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

import numpy as np

__all__ = ["CHORD_MM", "Loop", "Pocket", "Tab", "Width", "arc_points", "area", "cast", "crossings",
           "distance", "feret", "hull", "inside", "min_rectangle", "nest", "pockets", "self_crossings",
           "tabs", "widths"]

#: The most a sampled curve's chord strays from its arc.
CHORD_MM = 0.002


@dataclass
class Loop:
    """A closed outline: ``points`` (n, 2), segment ``i`` from point ``i`` to point ``i + 1`` (mod n)."""

    points: np.ndarray
    straight: np.ndarray                 # (n,) bool: segment i lies on a straight line of the source
    source: list[Any] = field(default_factory=list)  # (n,) the source element of each segment
    label: Any = None                    # whatever the caller names the loop by (a ref, a handle)
    circle: tuple[float, float, float] | None = None  # (cx, cy, r) when the loop is one whole circle
    through_diameter: float | None = None  # a countersunk hole's through diameter, its loop the countersink's

    def __post_init__(self) -> None:
        self.points = np.asarray(self.points, dtype=float).reshape(-1, 2)
        self.straight = np.asarray(self.straight, dtype=bool).reshape(-1)
        if len(self.straight) != len(self.points):
            self.straight = np.resize(self.straight, len(self.points)) if len(self.straight) else \
                np.zeros(len(self.points), dtype=bool)
        if len(self.source) != len(self.points):
            self.source = (list(self.source) + [None] * len(self.points))[:len(self.points)]

    @property
    def a(self) -> np.ndarray:
        return self.points

    @property
    def b(self) -> np.ndarray:
        return np.roll(self.points, -1, axis=0)

    def length(self) -> float:
        return float(np.linalg.norm(self.b - self.a, axis=1).sum())

    def bbox(self) -> tuple[np.ndarray, np.ndarray]:
        return self.points.min(axis=0), self.points.max(axis=0)

    def centroid(self) -> np.ndarray:
        if self.circle is not None:
            return np.array(self.circle[:2])
        x, y = self.points[:, 0], self.points[:, 1]
        xn, yn = np.roll(x, -1), np.roll(y, -1)
        cross = x * yn - xn * y
        total = cross.sum()
        if abs(total) < 1e-12:
            return self.points.mean(axis=0)
        return np.array([((x + xn) * cross).sum(), ((y + yn) * cross).sum()]) / (3.0 * total)


def arc_points(center: Sequence[float], radius: float, start: float, sweep: float,
               chord: float = CHORD_MM, most: int = 720) -> np.ndarray:
    """Points along an arc (angles in radians, ``sweep`` signed), both ends included, each chord within
    ``chord`` of the arc (and no more than 5 degrees long)."""
    radius = float(radius)
    if radius <= 0.0:
        return np.array([center, center], dtype=float)
    ratio = max(-1.0, min(1.0, 1.0 - chord / radius))
    step = 2.0 * math.acos(ratio) if ratio < 1.0 else math.radians(5.0)
    step = min(max(step, 1e-4), math.radians(5.0))
    count = int(min(most, max(2, math.ceil(abs(sweep) / step)))) + 1
    angles = start + np.linspace(0.0, sweep, count)
    return np.column_stack([center[0] + radius * np.cos(angles), center[1] + radius * np.sin(angles)])


def area(loop: Loop) -> float:
    """The signed area: positive when the loop turns anticlockwise."""
    x, y = loop.points[:, 0], loop.points[:, 1]
    return 0.5 * float((x * np.roll(y, -1) - np.roll(x, -1) * y).sum())


def _segments(loops: Iterable[Loop]) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Every segment of the loops: starts, ends, the loop each belongs to, its index in that loop."""
    a, b, owner, index = [], [], [], []
    for number, loop in enumerate(loops):
        a.append(loop.a)
        b.append(loop.b)
        owner.append(np.full(len(loop.points), number))
        index.append(np.arange(len(loop.points)))
    if not a:
        empty = np.zeros((0, 2))
        return empty, empty, np.zeros(0, int), np.zeros(0, int)
    return np.vstack(a), np.vstack(b), np.concatenate(owner), np.concatenate(index)


def inside(points: np.ndarray, loops: Sequence[Loop]) -> np.ndarray:
    """Whether each point lies inside an odd number of the loops (even-odd): inside a region's material
    when ``loops`` are its outer loop and its holes."""
    points = np.asarray(points, dtype=float).reshape(-1, 2)
    result = np.zeros(len(points), dtype=bool)
    a, b, _, _ = _segments(loops)
    if not len(a):
        return result
    chunk = max(1, 4_000_000 // max(1, len(a)))
    for start in range(0, len(points), chunk):
        p = points[start:start + chunk, None, :]
        ya, yb = a[None, :, 1], b[None, :, 1]
        crosses = (ya > p[..., 1]) != (yb > p[..., 1])
        dy = np.where(np.abs(yb - ya) < 1e-300, 1e-300, yb - ya)
        x_at = a[None, :, 0] + (p[..., 1] - ya) * (b[None, :, 0] - a[None, :, 0]) / dy
        result[start:start + chunk] = (crosses & (p[..., 0] < x_at)).sum(axis=1) % 2 == 1
    return result


def _point_segment(p: np.ndarray, a: np.ndarray, b: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Distances (n, m) from points ``p`` (n, 2) to segments ``a``-``b`` (m, 2), and the parameter along
    each segment of the nearest point."""
    ab = b - a
    length2 = np.maximum((ab * ab).sum(axis=1), 1e-300)
    ap = p[:, None, :] - a[None, :, :]
    t = np.clip((ap * ab[None]).sum(axis=2) / length2[None], 0.0, 1.0)
    nearest = a[None] + t[..., None] * ab[None]
    return np.linalg.norm(p[:, None, :] - nearest, axis=2), t


def _cross(u: np.ndarray, v: np.ndarray) -> np.ndarray:
    return u[..., 0] * v[..., 1] - u[..., 1] * v[..., 0]


def _segments_cross(a1: np.ndarray, b1: np.ndarray, a2: np.ndarray, b2: np.ndarray, proper: bool = False
                    ) -> np.ndarray:
    """(n, m): whether segment i of the first set crosses segment j of the second (``proper``: each
    through the other's interior; meeting at an end not counted)."""
    d1, d2 = (b1 - a1)[:, None, :], (b2 - a2)[None, :, :]
    denom = _cross(d1, d2)
    w = a2[None, :, :] - a1[:, None, :]
    with np.errstate(divide="ignore", invalid="ignore"):
        s = _cross(w, d2) / denom
        u = _cross(w, d1) / denom
    lo, hi = (1e-9, 1.0 - 1e-9) if proper else (-1e-12, 1.0 + 1e-12)
    return (np.abs(denom) > 1e-14) & (s > lo) & (s < hi) & (u > lo) & (u < hi)


def segments_distance(a: np.ndarray, b: np.ndarray, first: np.ndarray, second: np.ndarray
                      ) -> tuple[float, np.ndarray, np.ndarray]:
    """The least distance between segment sets ``a``-``b`` and ``first``-``second``, with the nearest points."""
    best = (math.inf, np.zeros(2), np.zeros(2))
    for (pa, pb, qa, qb, flip) in ((a, b, first, second, False), (first, second, a, b, True)):
        points = np.vstack([pa, pb])
        chunk = max(1, 2_000_000 // max(1, len(qa)))
        for start in range(0, len(points), chunk):
            d, t = _point_segment(points[start:start + chunk], qa, qb)
            if not d.size:
                continue
            i, j = divmod(int(np.argmin(d)), d.shape[1])
            if d[i, j] < best[0]:
                q = qa[j] + t[i, j] * (qb[j] - qa[j])
                p = points[start + i]
                best = (float(d[i, j]), q, p) if flip else (float(d[i, j]), p, q)
    if best[0] > 0.0 and len(a) * len(first) <= 4_000_000:
        crossing = _segments_cross(a, b, first, second)
        if crossing.any():
            i, _ = np.argwhere(crossing)[0]
            return 0.0, a[i], a[i]
    return best


def distance(first: Loop, second: Loop) -> tuple[float, np.ndarray, np.ndarray]:
    """The least distance between two loops (0 where they cross), with the nearest point of each."""
    if first.circle is not None and second.circle is not None:
        (x1, y1, r1), (x2, y2, r2) = first.circle, second.circle
        centres = math.hypot(x2 - x1, y2 - y1)
        gap = centres - r1 - r2 if centres >= abs(r1 - r2) else abs(r1 - r2) - centres
        if centres > 1e-12:
            u = np.array([x2 - x1, y2 - y1]) / centres
            return max(0.0, gap), np.array([x1, y1]) + u * r1, np.array([x2, y2]) - u * r2
    for circle, other in ((first.circle, second), (second.circle, first)):
        if circle is not None and other.circle is None:
            centre = np.array(circle[:2])[None]
            d, t = _point_segment(centre, other.a, other.b)
            j = int(np.argmin(d[0]))
            near = other.a[j] + t[0, j] * (other.b[j] - other.a[j])
            gap = float(d[0, j]) - circle[2]
            u = (near - centre[0]) / max(float(d[0, j]), 1e-300)
            on_circle = centre[0] + u * circle[2]
            pair = (on_circle, near) if circle is first.circle else (near, on_circle)
            return max(0.0, gap), pair[0], pair[1]
    return segments_distance(first.a, first.b, second.a, second.b)


def cast(origins: np.ndarray, directions: np.ndarray, loops: Sequence[Loop], skip: float = 1e-7
         ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Rays from ``origins`` along unit ``directions`` against every segment of ``loops``: the distance to
    the first crossing beyond ``skip`` (inf for none), the loop it crosses (-1 for none) and the segment's
    index in that loop."""
    origins = np.asarray(origins, dtype=float).reshape(-1, 2)
    directions = np.asarray(directions, dtype=float).reshape(-1, 2)
    a, b, owner, index = _segments(loops)
    hit = np.full(len(origins), np.inf)
    which = np.full(len(origins), -1)
    seg = np.full(len(origins), -1)
    if not len(a) or not len(origins):
        return hit, which, seg
    e = b - a
    chunk = max(1, 2_000_000 // max(1, len(a)))
    for start in range(0, len(origins), chunk):
        o = origins[start:start + chunk, None, :]
        d = directions[start:start + chunk, None, :]
        denom = _cross(d, e[None])
        w = a[None] - o
        with np.errstate(divide="ignore", invalid="ignore"):
            t = _cross(w, e[None]) / denom
            u = _cross(w, d) / denom
        valid = (np.abs(denom) > 1e-14) & (t > skip) & (u >= -1e-12) & (u <= 1.0 + 1e-12)
        t = np.where(valid, t, np.inf)
        j = np.argmin(t, axis=1)
        rows = np.arange(len(j))
        best = t[rows, j]
        hit[start:start + chunk] = best
        found = np.isfinite(best)
        which[start:start + chunk] = np.where(found, owner[j], -1)
        seg[start:start + chunk] = np.where(found, index[j], -1)
    return hit, which, seg


def _stations(loop: Loop, spacing: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Points spread along a loop (at most ``spacing`` apart, at least one at each segment's middle),
    the unit normal to the loop's left there, and the segment each lies on."""
    a, b = loop.a, loop.b
    edge = b - a
    length = np.linalg.norm(edge, axis=1)
    keep = np.nonzero(length > 1e-12)[0]
    if not len(keep):
        return np.zeros((0, 2)), np.zeros((0, 2)), np.zeros(0, int)
    counts = np.maximum(1, np.ceil(length[keep] / spacing).astype(int))
    owners = np.repeat(keep, counts)
    offsets = np.concatenate([(np.arange(count) + 0.5) / count for count in counts])
    points = a[owners] + offsets[:, None] * edge[owners]
    normals = np.column_stack([-edge[owners, 1], edge[owners, 0]]) / length[owners, None]
    return points, normals, owners


@dataclass(frozen=True)
class Width:
    """The narrowest place found across the material (``kind`` "material": a web, a bridge, a tab) or a
    void (``kind`` "void": a slot, a notch, a gap) between two loops (one loop twice: a neck)."""

    kind: str
    width: float
    loops: tuple[int, int]
    start: tuple[float, float]
    end: tuple[float, float]


def widths(loops: Sequence[Loop], outer: Sequence[bool], spacing: float = 0.5, most: int = 6000) -> list[Width]:
    """The narrowest material and void about a region's loops (``outer[i]``: loop ``i`` is an outline, else
    a hole): rays from points along the loops, square to them, to the next loop they cross. From an
    outline, into the material (to any loop: a neck of the outline, or a web to a hole) and out into the
    void (to an outline: a gap, a notch); from a hole, across it (to itself: its width). One ``Width`` per
    kind and pair of loops: the least found."""
    total = sum(loop.length() for loop in loops)
    spacing = max(spacing, total / most) if total > 0 else spacing
    best: dict[tuple[str, int, int], Width] = {}
    scale = max([1.0] + [float(np.abs(loop.points).max()) for loop in loops if len(loop.points)])
    step = 1e-7 * scale
    outlines = [loop for loop, flag in zip(loops, outer) if flag]
    outline_index = [i for i, flag in enumerate(outer) if flag]
    for number, loop in enumerate(loops):
        points, normals, _ = _stations(loop, spacing)
        if not len(points):
            continue
        left_is_material = inside(points + normals * step * 10, loops)
        into = np.where(left_is_material[:, None], normals, -normals)
        if outer[number]:
            runs = (("material", into, list(loops), list(range(len(loops)))),
                    ("void", -into, outlines, outline_index))
        else:
            runs = (("void", -into, [loop], [number]),)
        for kind, direction, targets, index in runs:
            hit, which, _ = cast(points, direction, targets, skip=step * 100)
            for i in np.nonzero(np.isfinite(hit))[0]:
                other = index[int(which[i])]
                key = (kind, *sorted((number, other)))
                found = best.get(key)
                if found is None or hit[i] < found.width:
                    end = points[i] + direction[i] * hit[i]
                    best[key] = Width(kind, float(hit[i]), (number, other), (float(points[i][0]), float(points[i][1])),
                                      (float(end[0]), float(end[1])))
    return sorted(best.values(), key=lambda width: width.width)


def hull(points: np.ndarray) -> np.ndarray:
    """The indices of the convex hull's vertices, anticlockwise (Andrew's monotone chain)."""
    points = np.asarray(points, dtype=float)
    order = np.lexsort((points[:, 1], points[:, 0]))
    if len(order) < 3:
        return order

    def chain(indices: Iterable[int]) -> list[int]:
        kept: list[int] = []
        for i in indices:
            while len(kept) >= 2 and float(_cross(points[kept[-1]] - points[kept[-2]],
                                                  points[i] - points[kept[-2]])) <= 1e-12:
                kept.pop()
            kept.append(int(i))
        return kept

    lower, upper = chain(order), chain(order[::-1])
    return np.array(lower[:-1] + upper[:-1])


def feret(points: np.ndarray) -> tuple[float, float, float]:
    """The points' least width over every direction (their convex hull's), their greatest length across,
    and the direction (radians) of the least width's sides."""
    points = np.asarray(points, dtype=float)
    ring = points[hull(points)]
    if len(ring) < 3:
        span = float(np.linalg.norm(points.max(axis=0) - points.min(axis=0)))
        return 0.0, span, 0.0
    least, angle = math.inf, 0.0
    for i in range(len(ring)):
        edge = ring[(i + 1) % len(ring)] - ring[i]
        size = float(np.linalg.norm(edge))
        if size < 1e-12:
            continue
        n = np.array([-edge[1], edge[0]]) / size
        width = float(np.ptp(ring @ n))
        if width < least:
            least, angle = width, math.atan2(edge[1], edge[0])
    diffs = ring[:, None, :] - ring[None, :, :]
    return least, float(np.sqrt((diffs ** 2).sum(axis=2)).max()), angle


def min_rectangle(points: np.ndarray) -> tuple[float, float, float]:
    """The smallest-area rectangle holding the points: its long side, its short side and the long side's
    direction (radians)."""
    points = np.asarray(points, dtype=float)
    ring = points[hull(points)]
    if len(ring) < 3:
        span = np.ptp(points, axis=0) if len(points) else np.zeros(2)
        return float(max(span)), float(min(span)), 0.0
    best = (math.inf, 0.0, 0.0, 0.0)
    for i in range(len(ring)):
        edge = ring[(i + 1) % len(ring)] - ring[i]
        size = float(np.linalg.norm(edge))
        if size < 1e-12:
            continue
        u = edge / size
        v = np.array([-u[1], u[0]])
        lu, lv = float(np.ptp(ring @ u)), float(np.ptp(ring @ v))
        if lu * lv < best[0] - 1e-9:
            best = (lu * lv, lu, lv, math.atan2(u[1], u[0]))
    _, lu, lv, angle = best
    return (lu, lv, angle) if lu >= lv else (lv, lu, angle + math.pi / 2)


@dataclass(frozen=True)
class Pocket:
    """A stretch of a loop off its convex hull: a notch. ``width`` is its mouth (the hull's chord across
    it), ``depth`` how far in from the mouth the loop goes, ``area`` the void it closes with the mouth."""

    width: float
    depth: float
    area: float
    mouth: tuple[tuple[float, float], tuple[float, float]]
    deepest: tuple[float, float]
    segments: tuple[int, ...]


def pockets(loop: Loop, least: float = 1e-4) -> list[Pocket]:
    """The loop's pockets off its convex hull deeper than ``least``."""
    points = loop.points
    n = len(points)
    on_hull = sorted(int(i) for i in hull(points))
    if len(on_hull) < 3:
        return []
    found: list[Pocket] = []
    for k, start in enumerate(on_hull):
        end = on_hull[(k + 1) % len(on_hull)]
        run = [(start + step) % n for step in range((end - start) % n + 1)]
        if len(run) < 3:
            continue
        a, b = points[start], points[end]
        chord = b - a
        size = float(np.linalg.norm(chord))
        if size < 1e-12:
            continue
        normal = np.array([-chord[1], chord[0]]) / size
        depths = np.abs((points[run] - a) @ normal)
        # the stretch between two hull vertices may leave the chord several times: a pocket each time
        on_chord = [i for i, depth in enumerate(depths) if depth <= least]
        for left, right in zip(on_chord, on_chord[1:]):
            if right - left < 2:
                continue
            inner = run[left + 1:right]
            depth = float(depths[left + 1:right].max())
            if depth <= least:
                continue
            p, q = points[run[left]], points[run[right]]
            ring = np.vstack([p, points[inner], q])
            x, y = ring[:, 0], ring[:, 1]
            enclosed = 0.5 * abs(float((x * np.roll(y, -1) - np.roll(x, -1) * y).sum()))
            deepest = points[inner][int(depths[left + 1:right].argmax())]
            found.append(Pocket(float(np.linalg.norm(q - p)), depth, enclosed,
                                ((float(p[0]), float(p[1])), (float(q[0]), float(q[1]))),
                                (float(deepest[0]), float(deepest[1])), tuple(sorted({run[left], *inner}))))
    return found


@dataclass(frozen=True)
class Tab:
    """A straight-sided protrusion of a loop: two facing straight sides ``width`` apart, joined beyond
    their overlap by a short tip, ``length`` the sides' overlap from the body to the tip."""

    width: float
    length: float
    base: tuple[float, float]
    tip: tuple[float, float]
    sides: tuple[int, int]


def _sides(loop: Loop, angle: float = 1e-6) -> list[tuple[int, int, np.ndarray, np.ndarray]]:
    """Runs of collinear straight segments: (first segment, last segment, start point, end point)."""
    n = len(loop.points)
    a, b = loop.a, loop.b
    runs: list[list[int]] = []

    def collinear(j: int, i: int) -> bool:
        u, v = b[j] - a[j], b[i] - a[i]
        return abs(float(_cross(u, v))) <= angle * float(np.linalg.norm(u) * np.linalg.norm(v)) and float(u @ v) > 0

    for i in range(n):
        if not loop.straight[i] or np.linalg.norm(b[i] - a[i]) < 1e-12:
            continue
        if runs and runs[-1][-1] == i - 1 and collinear(i - 1, i):
            runs[-1].append(i)
            continue
        runs.append([i])
    if len(runs) > 1 and runs[0][0] == 0 and runs[-1][-1] == n - 1 and collinear(n - 1, 0):
        runs[0] = runs.pop() + runs[0]
    return [(run[0], run[-1], a[run[0]], b[run[-1]]) for run in runs]


def _turn(loop: Loop, at: int) -> float:
    """The turn at point ``at``: the cross product of the unit directions before and after it."""
    n = len(loop.points)
    before = loop.points[at] - loop.points[(at - 1) % n]
    after = loop.points[(at + 1) % n] - loop.points[at]
    lb, la = float(np.linalg.norm(before)), float(np.linalg.norm(after))
    if lb < 1e-12 or la < 1e-12:
        return 0.0
    return float(_cross(before / lb, after / la))


def tabs(loop: Loop, material_left: bool) -> list[Tab]:
    """The loop's straight-sided protrusions: two facing straight sides with the material between them,
    joined beyond their overlap by a tip no longer than a half round across them plus their width, both
    meeting the body at an inside corner at the other end: the tip stands proud of the body on three sides
    (an outside corner at either makes the strip a lobe of the outline -- an L plate's leg, a shoulder --
    not a tab)."""
    n = len(loop.points)
    sides = _sides(loop)
    found: dict[tuple[int, int], Tab] = {}
    sign = 1.0 if material_left else -1.0
    for i, (fi, li, si, ei) in enumerate(sides):
        di = ei - si
        length_i = float(np.linalg.norm(di))
        if length_i < 1e-9:
            continue
        ui = di / length_i
        inward = sign * np.array([-ui[1], ui[0]])
        for j, (fj, lj, sj, ej) in enumerate(sides):
            if j == i:
                continue
            dj = ej - sj
            length_j = float(np.linalg.norm(dj))
            if length_j < 1e-9 or float(ui @ (dj / length_j)) > -1.0 + 1e-9:
                continue
            width = float((sj - si) @ inward)
            if width <= 1e-9:
                continue
            # i runs along +u, j back along -u: the tip lies past i's end and j's start, the body before.
            lo = max(0.0, float((ej - si) @ ui))
            hi = min(length_i, float((sj - si) @ ui))
            if hi - lo <= 1e-9:
                continue
            between = (fj - li) % n
            if between < 1 or between > 64:
                continue
            path = [(li + step) % n for step in range(1, between + 1)]
            tip_points = loop.points[path]
            along = (tip_points - si) @ ui
            across = (tip_points - si) @ inward
            if along.min() < hi - 1e-6 or across.min() < -1e-6 or across.max() > width + 1e-6:
                continue
            tip_length = float(np.linalg.norm(np.diff(np.vstack([ei, tip_points]), axis=0), axis=1).sum())
            if tip_length > width * (1.0 + math.pi / 2) + 1e-6:
                continue
            inside_i = sign * _turn(loop, fi) < -1e-9
            inside_j = sign * _turn(loop, (lj + 1) % n) < -1e-9
            if not (inside_i and inside_j):
                continue
            key = (min(i, j), max(i, j))
            base = si + ui * lo + inward * (width / 2)
            tip = si + ui * hi + inward * (width / 2)
            found.setdefault(key, Tab(width, float(hi - lo), (float(base[0]), float(base[1])),
                                      (float(tip[0]), float(tip[1])), key))
    return list(found.values())


def self_crossings(loop: Loop, most: int = 6000) -> list[tuple[float, float]]:
    """The points where a loop crosses itself (neighbouring segments meeting at their shared end not
    counted); none sought in a loop of more than ``most`` segments."""
    a, b = loop.a, loop.b
    n = len(a)
    if n < 4 or n > most:
        return []
    crossing = _segments_cross(a, b, a, b, proper=True)
    i, j = np.nonzero(np.triu(crossing, 2))
    keep = ~((i == 0) & (j == n - 1))
    found = []
    for p, q in zip(i[keep], j[keep]):
        d1, d2 = b[p] - a[p], b[q] - a[q]
        s = float(_cross(a[q] - a[p], d2) / _cross(d1, d2))
        point = a[p] + s * d1
        found.append((float(point[0]), float(point[1])))
    return found


def crossings(first: Loop, second: Loop) -> list[tuple[float, float]]:
    """The points where two loops cross through each other."""
    if len(first.points) * len(second.points) > 9_000_000:
        return []
    crossing = _segments_cross(first.a, first.b, second.a, second.b, proper=True)
    found = []
    for p, q in np.argwhere(crossing):
        d1, d2 = first.b[p] - first.a[p], second.b[q] - second.a[q]
        s = float(_cross(second.a[q] - first.a[p], d2) / _cross(d1, d2))
        point = first.a[p] + s * d1
        found.append((float(point[0]), float(point[1])))
    return found


def nest(loops: Sequence[Loop]) -> list[int]:
    """Each loop's depth: how many larger loops hold it (0: an outline, 1: a hole, 2: an island in a hole)."""
    areas = [abs(area(loop)) for loop in loops]
    boxes = [loop.bbox() for loop in loops]
    depth = []
    for i, loop in enumerate(loops):
        probe = loop.points[0]
        count = 0
        for j, other in enumerate(loops):
            if i == j or areas[j] <= areas[i]:
                continue
            lo, hi = boxes[j]
            if np.any(probe < lo - 1e-9) or np.any(probe > hi + 1e-9):
                continue
            if inside(probe[None], [other])[0]:
                count += 1
        depth.append(count)
    return depth
