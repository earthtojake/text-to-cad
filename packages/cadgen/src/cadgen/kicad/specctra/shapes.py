"""Specctra geometry: a KiCad board's curves and outline in DSN micrometres, and shapes as
Freerouting reads them (convex pieces, polygons outside a curve)."""

from __future__ import annotations

import math
from dataclasses import dataclass

from cadgen.kicad import sexpr
from cadgen.kicad.design import DesignError
from cadgen.kicad.geometry import area, bezier_points, inside, nm
from cadgen.kicad.geometry import hull as _convex_hull

# Curves become polygons whose edges stay within this many micrometres of the curve.
_TOLERANCE_UM = 2.5
_MAX_STEP = math.radians(10.0)
# Edge.Cuts ends nearer than this join, as KiCad chains an outline (millimetres).
_CHAIN_EPSILON = 0.02


Point = tuple[float, float]


# --- the frame --------------------------------------------------------------------


@dataclass(frozen=True)
class DsnFrame:
    """KiCad millimetres (y down, page origin) to DSN micrometres (y up, the board's origin)."""

    ox: float
    oy: float

    def to_dsn(self, x: float, y: float) -> Point:
        return (x - self.ox) * 1000.0, (self.oy - y) * 1000.0

    def to_kicad(self, ux: float, uy: float) -> Point:
        return nm(self.ox + ux / 1000.0), nm(self.oy - uy / 1000.0)


def node_xy(node: list | None, default: Point | None = None) -> Point:
    if node is None or len(node) < 3:
        if default is None:
            raise DesignError(f"a board item has no coordinates where KiCad writes them: {node!r}")
        return default
    return float(node[1]), float(node[2])


def placed(at: Point, angle: float):
    """A footprint's frame: local KiCad mm to board KiCad mm (both y down)."""
    radians = math.radians(angle)
    cos, sin = math.cos(radians), math.sin(radians)

    def place(point: Point) -> Point:
        x, y = point
        return at[0] + x * cos + y * sin, at[1] - x * sin + y * cos

    return place


# --- curves ---------------------------------------------------------------------------


def curve_step(radius: float) -> float:
    if radius <= _TOLERANCE_UM:
        return _MAX_STEP
    return min(_MAX_STEP, 2 * math.acos(1 - _TOLERANCE_UM / radius))


def _circle_through(a: Point, b: Point, c: Point) -> tuple[Point, float] | None:
    ax, ay = a
    bx, by = b
    cx, cy = c
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-9:
        return None
    a2, b2, c2 = ax * ax + ay * ay, bx * bx + by * by, cx * cx + cy * cy
    ux = (a2 * (by - cy) + b2 * (cy - ay) + c2 * (ay - by)) / d
    uy = (a2 * (cx - bx) + b2 * (ax - cx) + c2 * (bx - ax)) / d
    return (ux, uy), math.hypot(ax - ux, ay - uy)


@dataclass(frozen=True)
class Edge:
    """A line, or an arc of ``sweep`` radians (counter-clockwise positive, y up) about ``center``."""

    start: Point
    end: Point
    center: Point | None = None
    sweep: float = 0.0

    @property
    def radius(self) -> float:
        return math.hypot(self.start[0] - self.center[0], self.start[1] - self.center[1])

    def reversed(self) -> "Edge":
        return Edge(self.end, self.start, self.center, -self.sweep)

    def sample(self, count: int) -> list[Point]:
        """``count`` + 1 points on the edge, start and end included."""
        if self.center is None:
            return [self.start, self.end]
        cx, cy = self.center
        a0 = math.atan2(self.start[1] - cy, self.start[0] - cx)
        r = self.radius
        points = [(cx + r * math.cos(a0 + self.sweep * k / count), cy + r * math.sin(a0 + self.sweep * k / count)) for k in range(count + 1)]
        points[0], points[-1] = self.start, self.end
        return points


def arc_edge(start: Point, mid: Point, end: Point) -> Edge:
    found = _circle_through(start, mid, end)
    if found is None:
        return Edge(start, end)
    center, _radius = found
    cross = (mid[0] - start[0]) * (end[1] - mid[1]) - (mid[1] - start[1]) * (end[0] - mid[0])
    a0 = math.atan2(start[1] - center[1], start[0] - center[0])
    a1 = math.atan2(end[1] - center[1], end[0] - center[0])
    if cross > 0:
        sweep = (a1 - a0) % (2 * math.pi) or 2 * math.pi
    else:
        sweep = -((a0 - a1) % (2 * math.pi) or 2 * math.pi)
    return Edge(start, end, center, sweep)


def circle_edge(center: Point, radius: float) -> Edge:
    start = (center[0] + radius, center[1])
    return Edge(start, start, center, 2 * math.pi)


def curve_points(edge: Edge, *, outside: bool) -> list[Point]:
    """The edge as points from its start, its end excluded, never inside ``outside``'s side.

    ``outside`` True keeps the polygon on the far side of the arc from its
    centre (tangent lines: the region on the centre's side only grows); False
    keeps it on the centre's side (chords: that region only shrinks).
    """
    if edge.center is None:
        return [edge.start]
    radius = edge.radius
    count = max(1, math.ceil(abs(edge.sweep) / curve_step(radius) - 1e-9))
    if not outside:
        return edge.sample(count)[:-1]
    cx, cy = edge.center
    a0 = math.atan2(edge.start[1] - cy, edge.start[0] - cx)
    delta = edge.sweep / count
    reach = radius / math.cos(delta / 2)
    points = [edge.start]
    for k in range(count):
        angle = a0 + (k + 0.5) * delta
        points.append((cx + reach * math.cos(angle), cy + reach * math.sin(angle)))
    return points


def _coarse(loop: list[Edge]) -> list[Point]:
    points: list[Point] = []
    for edge in loop:
        points.extend(edge.sample(8)[:-1] if edge.center is not None else [edge.start])
    return points


def loop_points(loop: list[Edge], *, keep_inside: bool) -> list[Point]:
    """A closed loop as a polygon whose copper side only shrinks.

    ``keep_inside`` says where copper may be: inside the loop (an outer
    boundary) or outside it (a hole, a keepout).
    """
    ccw = area(_coarse(loop)) > 0
    copper_on_left = keep_inside == ccw
    points: list[Point] = []
    for edge in loop:
        if edge.center is None:
            points.append(edge.start)
            continue
        centre_on_left = edge.sweep > 0
        # Copper on the centre's side: chords (they cut into it). Otherwise tangents.
        points.extend(curve_points(edge, outside=centre_on_left != copper_on_left))
    return points


def bezier(points: list[Point]) -> list[Edge]:
    samples = bezier_points(points, 32)
    return [Edge(a, b) for a, b in zip(samples, samples[1:]) if a != b]


def pts_loop(pts: list, convert) -> list[Edge]:
    """A KiCad ``(pts ...)`` polygon (``xy`` points, KiCad 7's ``arc`` runs) as a closed loop."""
    edges: list[Edge] = []
    cursor: Point | None = None
    first: Point | None = None
    for item in pts[1:]:
        head = sexpr.head(item)
        if head == "xy":
            point = convert(node_xy(item))
            if cursor is not None and point != cursor:
                edges.append(Edge(cursor, point))
            cursor = point
        elif head == "arc":
            start, mid, end = (convert(node_xy(sexpr.find(item, key))) for key in ("start", "mid", "end"))
            if cursor is not None and start != cursor:
                edges.append(Edge(cursor, start))
            edges.append(arc_edge(start, mid, end))
            cursor = end
        else:
            continue
        if first is None:
            first = edges[0].start if edges else cursor
    if cursor is not None and first is not None and cursor != first:
        edges.append(Edge(cursor, first))
    return edges


# --- the outline ------------------------------------------------------------------------

GRAPHIC = {"line", "arc", "circle", "rect", "poly", "curve"}


def _graphic_pieces(node: list, convert) -> tuple[list[Edge], list[list[Edge]]]:
    """``(open edges, closed loops)`` of one gr_/fp_ graphic, in DSN micrometres."""
    kind = str(node[0])[3:]
    if kind == "line":
        start, end = convert(node_xy(sexpr.find(node, "start"))), convert(node_xy(sexpr.find(node, "end")))
        return ([Edge(start, end)] if start != end else []), []
    if kind == "arc":
        start, mid, end = (convert(node_xy(sexpr.find(node, key))) for key in ("start", "mid", "end"))
        return [arc_edge(start, mid, end)], []
    if kind == "circle":
        center = convert(node_xy(sexpr.find(node, "center")))
        rim = convert(node_xy(sexpr.find(node, "end")))
        radius = math.hypot(rim[0] - center[0], rim[1] - center[1])
        return [], ([[circle_edge(center, radius)]] if radius > 0 else [])
    if kind == "rect":
        (x1, y1), (x2, y2) = node_xy(sexpr.find(node, "start")), node_xy(sexpr.find(node, "end"))
        corners = [convert(point) for point in ((x1, y1), (x2, y1), (x2, y2), (x1, y2))]
        return [], [[Edge(a, b) for a, b in zip(corners, corners[1:] + corners[:1])]]
    if kind == "poly":
        pts = sexpr.find(node, "pts")
        loop = pts_loop(pts, convert) if pts is not None else []
        return [], ([loop] if loop else [])
    pts = sexpr.find(node, "pts")
    points = [convert(node_xy(xy)) for xy in sexpr.find_all(pts, "xy")] if pts is not None else []
    return (bezier(points) if len(points) == 4 else []), []


def _edge_cuts(tree: list, frame: DsnFrame) -> list[list[Edge]]:
    """Every closed loop of Edge.Cuts, footprints' included, in DSN micrometres."""
    pieces: list[Edge] = []
    loops: list[list[Edge]] = []

    def take(node: list, convert) -> None:
        if sexpr.value(node, "layer") != "Edge.Cuts":
            return
        open_edges, closed = _graphic_pieces(node, convert)
        pieces.extend(open_edges)
        loops.extend(closed)

    board = lambda point: frame.to_dsn(*point)  # noqa: E731
    for item in tree[1:]:
        head = sexpr.head(item)
        if head is not None and head.startswith("gr_") and head[3:] in GRAPHIC:
            take(item, board)
        elif head == "footprint":
            at = sexpr.find(item, "at")
            place = placed(node_xy(at), float(at[3]) if at is not None and len(at) > 3 else 0.0)
            in_footprint = lambda point, place=place: frame.to_dsn(*place(point))  # noqa: E731
            for child in item[1:]:
                child_head = sexpr.head(child)
                if child_head is not None and child_head.startswith("fp_") and child_head[3:] in GRAPHIC:
                    take(child, in_footprint)
    loops.extend(_chain(pieces, frame))
    return loops


def _near(a: Point, b: Point) -> bool:
    return math.hypot(a[0] - b[0], a[1] - b[1]) <= _CHAIN_EPSILON * 1000.0


def _chain(pieces: list[Edge], frame: DsnFrame) -> list[list[Edge]]:
    unused = list(range(len(pieces)))
    loops: list[list[Edge]] = []
    while unused:
        loop = [pieces[unused.pop(0)]]
        while not (_near(loop[-1].end, loop[0].start) and (len(loop) > 1 or loop[0].center is not None)):
            end = loop[-1].end
            following = next((j for j in unused if _near(pieces[j].start, end) or _near(pieces[j].end, end)), None)
            if following is None:
                x, y = frame.to_kicad(*end)
                sx, sy = end[0] / 1000.0, end[1] / 1000.0
                raise DesignError(
                    f"the board outline (Edge.Cuts) does not close: nothing continues it at ({sx:g}, {sy:g}) mm "
                    f"(KiCad {x:g}, {y:g}); an autorouted board needs a closed outline"
                )
            unused.remove(following)
            piece = pieces[following]
            loop.append(piece if _near(piece.start, end) else piece.reversed())
        loops.append(loop)
    return loops


def board_outline(tree: list, frame: DsnFrame) -> tuple[list[list[Point]], list[list[Point]]]:
    """``(boundaries, holes)``: the outline's outer loops and the cutouts inside them."""
    loops = _edge_cuts(tree, frame)
    if not loops:
        raise DesignError("the board has no outline on Edge.Cuts, so there is nothing to route inside")
    coarse = [_coarse(loop) for loop in loops]
    boundaries: list[list[Point]] = []
    holes: list[list[Point]] = []
    for index, loop in enumerate(loops):
        depth = sum(1 for other, polygon in enumerate(coarse) if other != index and inside(coarse[index][0], polygon))
        if depth % 2 == 0:
            boundaries.append(loop_points(loop, keep_inside=True))
        else:
            holes.append(loop_points(loop, keep_inside=False))
    return boundaries, holes


# --- outlines a pad or a stroke needs -----------------------------------------------


def rounded_rect(width: float, height: float, radius: float, cx: float, cy: float) -> list[Point]:
    radius = min(radius, width / 2, height / 2)
    hx, hy = width / 2 - radius, height / 2 - radius
    points: list[Point] = []
    for (sx, sy), start in (((1, 1), 0.0), ((-1, 1), 90.0), ((-1, -1), 180.0), ((1, -1), 270.0)):
        centre = (cx + sx * hx, cy + sy * hy)
        a0 = math.radians(start)
        first = (centre[0] + radius * math.cos(a0), centre[1] + radius * math.sin(a0))
        last = (centre[0] + radius * math.cos(a0 + math.pi / 2), centre[1] + radius * math.sin(a0 + math.pi / 2))
        points.extend(curve_points(Edge(first, last, centre, math.pi / 2), outside=True))
        points.append(last)
    return points


def stadium(width: float, height: float, cx: float, cy: float) -> list[Point]:
    """An oval pad: a slot of round ends, ``width`` along x."""
    if width >= height:
        r, half = height / 2, width / 2 - height / 2
        ends = (((cx + half, cy), -90.0), ((cx - half, cy), 90.0))
    else:
        r, half = width / 2, height / 2 - width / 2
        ends = (((cx, cy + half), 0.0), ((cx, cy - half), 180.0))
    points: list[Point] = []
    for centre, start in ends:
        a0 = math.radians(start)
        first = (centre[0] + r * math.cos(a0), centre[1] + r * math.sin(a0))
        last = (centre[0] + r * math.cos(a0 + math.pi), centre[1] + r * math.sin(a0 + math.pi))
        points.extend(curve_points(Edge(first, last, centre, math.pi), outside=True))
        points.append(last)
    return points


def hull(points: list[Point]) -> list[Point]:
    """The hull of ``points`` taken to a micrometre's millionth, so near-repeats are one point."""
    return _convex_hull((round(x, 6), round(y, 6)) for x, y in points)


def blob(x: float, y: float, radius: float) -> list[Point]:
    """Points whose hull holds a disc of ``radius`` about (x, y)."""
    if radius <= 0:
        return [(x, y)]
    return curve_points(circle_edge((x, y), radius), outside=True)


def strokes(points: list[Point], radius: float, *, closed: bool) -> list[list[Point]]:
    """A stroked polyline as one convex region per segment (a stroke of no width gets a micrometre)."""
    radius = max(radius, 1.0)
    ends = points + points[:1] if closed else points
    return [hull(blob(*a, radius) + blob(*b, radius)) for a, b in zip(ends, ends[1:]) if a != b]



# --- convex pieces ------------------------------------------------------------------


def _cross(o: Point, a: Point, b: Point) -> float:
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _cleaned(points: list[Point]) -> list[Point]:
    """``points`` counter-clockwise, without repeats or straight-through corners."""
    ring: list[Point] = []
    for point in points:
        point = (round(point[0], 3), round(point[1], 3))
        if not ring or ring[-1] != point:
            ring.append(point)
    while len(ring) > 1 and ring[0] == ring[-1]:
        ring.pop()
    changed = True
    while changed and len(ring) > 3:
        changed = False
        for index in range(len(ring)):
            if abs(_cross(ring[index - 1], ring[index], ring[(index + 1) % len(ring)])) < 1e-6:
                del ring[index]
                changed = True
                break
    if len(ring) >= 3 and area(ring) < 0:
        ring.reverse()
    return ring


def _convex(ring: list[Point]) -> bool:
    return all(_cross(ring[index - 2], ring[index - 1], ring[index]) >= 0 for index in range(len(ring)))


def _in_triangle(point: Point, a: Point, b: Point, c: Point) -> bool:
    return _cross(a, b, point) >= 0 and _cross(b, c, point) >= 0 and _cross(c, a, point) >= 0


def _merged(a: list[Point], b: list[Point]) -> list[Point] | None:
    """``a`` and ``b`` joined along an edge they share, or None."""
    for i in range(len(a)):
        p, q = a[i], a[(i + 1) % len(a)]
        for j in range(len(b)):
            if b[j] == q and b[(j + 1) % len(b)] == p:
                from_q = a[i + 1:] + a[:i + 1]
                from_p = b[j + 1:] + b[:j + 1]
                return from_q + from_p[1:-1]
    return None


def convex_pieces(points: list[Point]) -> list[list[Point]]:
    """A polygon as convex pieces whose union is it (a padstack shape must be convex).

    Ear-clipped into triangles, then neighbours merged while they stay convex;
    a polygon that crosses itself is held by its hull.
    """
    ring = _cleaned(points)
    if len(ring) < 3:
        return []
    if _convex(ring):
        return [ring]
    remaining = list(ring)
    pieces: list[list[Point]] = []
    while len(remaining) > 3:
        for index in range(len(remaining)):
            a, b, c = remaining[index - 1], remaining[index], remaining[(index + 1) % len(remaining)]
            if _cross(a, b, c) <= 0:
                continue
            if any(_in_triangle(point, a, b, c) for point in remaining if point not in (a, b, c)):
                continue
            pieces.append([a, b, c])
            del remaining[index]
            break
        else:
            return [hull(ring)]
    pieces.append(remaining)
    merging = True
    while merging:
        merging = False
        for i in range(len(pieces)):
            for j in range(i + 1, len(pieces)):
                joined = _merged(pieces[i], pieces[j])
                if joined is not None and _convex(_cleaned(joined)):
                    pieces[i] = _cleaned(joined)
                    del pieces[j]
                    merging = True
                    break
            if merging:
                break
    return pieces
