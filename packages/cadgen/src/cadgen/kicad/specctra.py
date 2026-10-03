"""Specctra DSN and SES: a KiCad board as the routing problem Freerouting reads, and its answer.

Freerouting, the open-source autorouter KiCad users run, reads a board as a
Specctra design file (DSN) and answers with a Specctra session (SES): the wires
and vias it added. ``kicad-cli`` has no DSN export, so :func:`board_dsn` writes
the DSN itself, from a board tree in KiCad 10's format and the project's net
classes, and :func:`read_session` reads the session back as KiCad tracks and
vias, which :func:`with_routes` adds to the board. Nothing here runs a program
(:mod:`cadgen.kicad.route` runs Freerouting); every function is pure, so the
same board always writes the same DSN.

Frame
-----
DSN coordinates are micrometres, y up, from the board's drill/place origin --
the board script's own (0, 0): a KiCad point ``(x, y)`` mm is
``(1000 (x - ox), 1000 (oy - y))`` µm. The resolution is a tenth of a
micrometre, so the session's integers are tenths of a micrometre and come back
to KiCad's nanometres exactly.

Names
-----
Freerouting's reader splits a pin reference at its first ``-``, strips any
``.<digits>`` from a padstack name and reads a tab as part of a name, so no
spelling of the board's own goes into the file: nets, parts, pins, padstacks,
images and classes get aliases of letters, digits, ``_`` and ``@``
(``N3_GND``, ``R1``, ``@4``), and the :class:`Dsn` keeps the way back.

What goes in
------------
- the copper layers, front to back;
- the outline (``Edge.Cuts``, a footprint's included) as the boundary, kept the
  board's edge clearance from copper;
- each footprint as an image seen from the top, placed ``back`` and turned
  180 degrees more when it sits on the bottom (how KiCad's own exporter places
  a flipped footprint), its pads as padstacks;
- every net with two or more pads, less the nets asked to stay unrouted, in its
  net class: track width, clearance (never under the board's minimum) and via;
- every other obstacle to tracks as a pin of no net on a locked part: a hole in
  the outline (kept the edge clearance), an unplated hole (grown by the hole
  clearance), a keepout zone that forbids tracks, copper drawn or written on a
  copper layer. Freerouting 2.4's search keeps a keepout's bare clearance while
  its trace insertion asks a little more, so a route that hugs a keepout is
  found and then refused; around a pin the two agree. A zone that forbids only
  vias is a via keepout;
- the board's own tracks and vias as fixed wiring: Freerouting continues from
  them and routes around them, and never moves one.

A shape Freerouting has no word for is written larger than it is, never
smaller: a rounded or oval pad as a polygon outside its curve, an arc of the
outline on the side away from the copper, an arc track as a wider polyline.
Every clearance is written :data:`MARGIN` above the board's. KiCad's DRC runs
on the routed board and judges the result; an approximation only ever costs
the router room.
"""

from __future__ import annotations

import copy
import fnmatch
import json
import math
import re
from dataclasses import dataclass
from typing import Iterable

from cadgen.kicad import sexpr
from cadgen.kicad.design import DesignError
from cadgen.kicad.ids import Ids
from cadgen.kicad.sexpr import Sym

__all__ = [
    "MARGIN",
    "RESOLUTION",
    "Dsn",
    "DsnFrame",
    "RoutedTrack",
    "RoutedVia",
    "Routes",
    "SessionError",
    "ViaKind",
    "board_dsn",
    "read_session",
    "with_routes",
]

#: Tenths of a micrometre: Freerouting's grid, and the unit of the session's integers.
RESOLUTION = 10
#: Millimetres every clearance is written above the board's, for the session's rounding.
MARGIN = 0.001

# Curves become polygons whose edges stay within this many micrometres of the curve.
_TOLERANCE_UM = 2.5
_MAX_STEP = math.radians(10.0)
# Edge.Cuts ends nearer than this join, as KiCad chains an outline (millimetres).
_CHAIN_EPSILON = 0.02
_DEFAULT_CLASS = "kicad_default"
# KiCad's defaults for a project that does not say (Board Setup > Constraints).
_KICAD_RULES = {"min_clearance": 0.0, "min_copper_edge_clearance": 0.5, "min_hole_clearance": 0.25}
_KICAD_NETCLASS = {"track_width": 0.2, "clearance": 0.2, "via_diameter": 0.6, "via_drill": 0.3}
_SAFE_PIN = re.compile(r"[A-Za-z0-9]+")
_SAFE_REF = re.compile(r"[A-Za-z][A-Za-z0-9_]*")


class SessionError(RuntimeError):
    """A Specctra session that does not answer the design it was routed from."""


Point = tuple[float, float]


def _nm(value: float) -> float:
    rounded = round(float(value), 6)
    return 0.0 if rounded == 0 else rounded


def _num(value: float) -> str:
    """A DSN number: micrometres to the nanometre, never in exponent form."""
    text = f"{value:.3f}".rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


def _sanitize(text: str, limit: int = 32) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", str(text)).strip("_")[:limit]


def _shown(net: str) -> str:
    """A net's name as KiCad shows it (its files escape ``/`` as ``{slash}``)."""
    return net.replace("{slash}", "/")


# --- the frame --------------------------------------------------------------------


@dataclass(frozen=True)
class DsnFrame:
    """KiCad millimetres (y down, page origin) to DSN micrometres (y up, the board's origin)."""

    ox: float
    oy: float

    def to_dsn(self, x: float, y: float) -> Point:
        return (x - self.ox) * 1000.0, (self.oy - y) * 1000.0

    def to_kicad(self, ux: float, uy: float) -> Point:
        return _nm(self.ox + ux / 1000.0), _nm(self.oy - uy / 1000.0)


def _origin(tree: list) -> Point:
    setup = sexpr.find(tree, "setup")
    origin = sexpr.find(setup, "aux_axis_origin") if setup is not None else None
    if origin is None or len(origin) < 3:
        return 0.0, 0.0
    return float(origin[1]), float(origin[2])


def _xy(node: list | None, default: Point | None = None) -> Point:
    if node is None or len(node) < 3:
        if default is None:
            raise DesignError(f"a board item has no coordinates where KiCad writes them: {node!r}")
        return default
    return float(node[1]), float(node[2])


def _placed(at: Point, angle: float):
    """A footprint's frame: local KiCad mm to board KiCad mm (both y down)."""
    radians = math.radians(angle)
    cos, sin = math.cos(radians), math.sin(radians)

    def place(point: Point) -> Point:
        x, y = point
        return at[0] + x * cos + y * sin, at[1] - x * sin + y * cos

    return place


# --- curves ---------------------------------------------------------------------------


def _step(radius: float) -> float:
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
class _Edge:
    """A line, or an arc of ``sweep`` radians (counter-clockwise positive, y up) about ``center``."""

    start: Point
    end: Point
    center: Point | None = None
    sweep: float = 0.0

    @property
    def radius(self) -> float:
        return math.hypot(self.start[0] - self.center[0], self.start[1] - self.center[1])

    def reversed(self) -> "_Edge":
        return _Edge(self.end, self.start, self.center, -self.sweep)

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


def _arc_edge(start: Point, mid: Point, end: Point) -> _Edge:
    found = _circle_through(start, mid, end)
    if found is None:
        return _Edge(start, end)
    center, _radius = found
    cross = (mid[0] - start[0]) * (end[1] - mid[1]) - (mid[1] - start[1]) * (end[0] - mid[0])
    a0 = math.atan2(start[1] - center[1], start[0] - center[0])
    a1 = math.atan2(end[1] - center[1], end[0] - center[0])
    if cross > 0:
        sweep = (a1 - a0) % (2 * math.pi) or 2 * math.pi
    else:
        sweep = -((a0 - a1) % (2 * math.pi) or 2 * math.pi)
    return _Edge(start, end, center, sweep)


def _circle_edge(center: Point, radius: float) -> _Edge:
    start = (center[0] + radius, center[1])
    return _Edge(start, start, center, 2 * math.pi)


def _curve_points(edge: _Edge, *, outside: bool) -> list[Point]:
    """The edge as points from its start, its end excluded, never inside ``outside``'s side.

    ``outside`` True keeps the polygon on the far side of the arc from its
    centre (tangent lines: the region on the centre's side only grows); False
    keeps it on the centre's side (chords: that region only shrinks).
    """
    if edge.center is None:
        return [edge.start]
    radius = edge.radius
    count = max(1, math.ceil(abs(edge.sweep) / _step(radius) - 1e-9))
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


def _coarse(loop: list[_Edge]) -> list[Point]:
    points: list[Point] = []
    for edge in loop:
        points.extend(edge.sample(8)[:-1] if edge.center is not None else [edge.start])
    return points


def _area(points: list[Point]) -> float:
    return 0.5 * sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(points, points[1:] + points[:1]))


def _inside(point: Point, polygon: list[Point]) -> bool:
    x, y = point
    inside = False
    for (x1, y1), (x2, y2) in zip(polygon, polygon[1:] + polygon[:1]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def _loop_points(loop: list[_Edge], *, keep_inside: bool) -> list[Point]:
    """A closed loop as a polygon whose copper side only shrinks.

    ``keep_inside`` says where copper may be: inside the loop (an outer
    boundary) or outside it (a hole, a keepout).
    """
    ccw = _area(_coarse(loop)) > 0
    copper_on_left = keep_inside == ccw
    points: list[Point] = []
    for edge in loop:
        if edge.center is None:
            points.append(edge.start)
            continue
        centre_on_left = edge.sweep > 0
        # Copper on the centre's side: chords (they cut into it). Otherwise tangents.
        points.extend(_curve_points(edge, outside=centre_on_left != copper_on_left))
    return points


def _bezier(points: list[Point], count: int = 32) -> list[_Edge]:
    p0, p1, p2, p3 = points
    samples = []
    for k in range(count + 1):
        t = k / count
        u = 1 - t
        samples.append(
            (
                u**3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t**3 * p3[0],
                u**3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t**3 * p3[1],
            )
        )
    return [_Edge(a, b) for a, b in zip(samples, samples[1:]) if a != b]


def _pts_loop(pts: list, convert) -> list[_Edge]:
    """A KiCad ``(pts ...)`` polygon (``xy`` points, KiCad 7's ``arc`` runs) as a closed loop."""
    edges: list[_Edge] = []
    cursor: Point | None = None
    first: Point | None = None
    for item in pts[1:]:
        head = sexpr.head(item)
        if head == "xy":
            point = convert(_xy(item))
            if cursor is not None and point != cursor:
                edges.append(_Edge(cursor, point))
            cursor = point
        elif head == "arc":
            start, mid, end = (convert(_xy(sexpr.find(item, key))) for key in ("start", "mid", "end"))
            if cursor is not None and start != cursor:
                edges.append(_Edge(cursor, start))
            edges.append(_arc_edge(start, mid, end))
            cursor = end
        else:
            continue
        if first is None:
            first = edges[0].start if edges else cursor
    if cursor is not None and first is not None and cursor != first:
        edges.append(_Edge(cursor, first))
    return edges


# --- the outline ------------------------------------------------------------------------

_GRAPHIC = {"line", "arc", "circle", "rect", "poly", "curve"}


def _graphic_pieces(node: list, convert) -> tuple[list[_Edge], list[list[_Edge]]]:
    """``(open edges, closed loops)`` of one gr_/fp_ graphic, in DSN micrometres."""
    kind = str(node[0])[3:]
    if kind == "line":
        start, end = convert(_xy(sexpr.find(node, "start"))), convert(_xy(sexpr.find(node, "end")))
        return ([_Edge(start, end)] if start != end else []), []
    if kind == "arc":
        start, mid, end = (convert(_xy(sexpr.find(node, key))) for key in ("start", "mid", "end"))
        return [_arc_edge(start, mid, end)], []
    if kind == "circle":
        center = convert(_xy(sexpr.find(node, "center")))
        rim = convert(_xy(sexpr.find(node, "end")))
        radius = math.hypot(rim[0] - center[0], rim[1] - center[1])
        return [], ([[_circle_edge(center, radius)]] if radius > 0 else [])
    if kind == "rect":
        (x1, y1), (x2, y2) = _xy(sexpr.find(node, "start")), _xy(sexpr.find(node, "end"))
        corners = [convert(point) for point in ((x1, y1), (x2, y1), (x2, y2), (x1, y2))]
        return [], [[_Edge(a, b) for a, b in zip(corners, corners[1:] + corners[:1])]]
    if kind == "poly":
        pts = sexpr.find(node, "pts")
        loop = _pts_loop(pts, convert) if pts is not None else []
        return [], ([loop] if loop else [])
    pts = sexpr.find(node, "pts")
    points = [convert(_xy(xy)) for xy in sexpr.find_all(pts, "xy")] if pts is not None else []
    return (_bezier(points) if len(points) == 4 else []), []


def _edge_cuts(tree: list, frame: DsnFrame) -> list[list[_Edge]]:
    """Every closed loop of Edge.Cuts, footprints' included, in DSN micrometres."""
    pieces: list[_Edge] = []
    loops: list[list[_Edge]] = []

    def take(node: list, convert) -> None:
        if sexpr.value(node, "layer") != "Edge.Cuts":
            return
        open_edges, closed = _graphic_pieces(node, convert)
        pieces.extend(open_edges)
        loops.extend(closed)

    board = lambda point: frame.to_dsn(*point)  # noqa: E731
    for item in tree[1:]:
        head = sexpr.head(item)
        if head is not None and head.startswith("gr_") and head[3:] in _GRAPHIC:
            take(item, board)
        elif head == "footprint":
            at = sexpr.find(item, "at")
            place = _placed(_xy(at), float(at[3]) if at is not None and len(at) > 3 else 0.0)
            in_footprint = lambda point, place=place: frame.to_dsn(*place(point))  # noqa: E731
            for child in item[1:]:
                child_head = sexpr.head(child)
                if child_head is not None and child_head.startswith("fp_") and child_head[3:] in _GRAPHIC:
                    take(child, in_footprint)
    loops.extend(_chain(pieces, frame))
    return loops


def _near(a: Point, b: Point) -> bool:
    return math.hypot(a[0] - b[0], a[1] - b[1]) <= _CHAIN_EPSILON * 1000.0


def _chain(pieces: list[_Edge], frame: DsnFrame) -> list[list[_Edge]]:
    unused = list(range(len(pieces)))
    loops: list[list[_Edge]] = []
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


def _outline(tree: list, frame: DsnFrame) -> tuple[list[list[Point]], list[list[Point]]]:
    """``(boundaries, holes)``: the outline's outer loops and the cutouts inside them."""
    loops = _edge_cuts(tree, frame)
    if not loops:
        raise DesignError("the board has no outline on Edge.Cuts, so there is nothing to route inside")
    coarse = [_coarse(loop) for loop in loops]
    boundaries: list[list[Point]] = []
    holes: list[list[Point]] = []
    for index, loop in enumerate(loops):
        depth = sum(1 for other, polygon in enumerate(coarse) if other != index and _inside(coarse[index][0], polygon))
        if depth % 2 == 0:
            boundaries.append(_loop_points(loop, keep_inside=True))
        else:
            holes.append(_loop_points(loop, keep_inside=False))
    return boundaries, holes


# --- rules and net classes ---------------------------------------------------------------------


@dataclass(frozen=True)
class _NetClass:
    name: str
    track_width: float
    clearance: float
    via_diameter: float
    via_drill: float
    priority: int


def _project(project: str | dict) -> dict:
    if isinstance(project, dict):
        return project
    try:
        return json.loads(project)
    except (TypeError, ValueError) as error:
        raise DesignError(f"the board's .kicad_pro is not KiCad's project JSON ({error})") from None


def _rules(project: dict) -> dict[str, float]:
    found = (((project.get("board") or {}).get("design_settings") or {}).get("rules")) or {}
    return {key: float(found.get(key, default) or 0.0) for key, default in _KICAD_RULES.items()}


def _netclasses(project: dict) -> tuple[dict[str, _NetClass], list[tuple[str, str]], dict[str, list[str]]]:
    settings = project.get("net_settings") or {}
    raw = {str(entry.get("name")): entry for entry in settings.get("classes") or [] if entry.get("name")}
    default_raw = raw.get("Default", {})
    default_values = {key: float(default_raw.get(key) or value) for key, value in _KICAD_NETCLASS.items()}
    classes: dict[str, _NetClass] = {}
    for name, entry in raw.items():
        values = {key: float(entry[key]) if entry.get(key) is not None else default_values[key] for key in _KICAD_NETCLASS}
        priority = entry.get("priority")
        classes[name] = _NetClass(name=name, priority=int(priority) if priority is not None else 2**31 - 1, **values)
    if "Default" not in classes:
        classes["Default"] = _NetClass(name="Default", priority=2**31 - 1, **default_values)
    patterns = [
        (str(entry.get("pattern")), str(entry.get("netclass")))
        for entry in settings.get("netclass_patterns") or []
        if entry.get("pattern") is not None and entry.get("netclass") is not None
    ]
    assigned: dict[str, list[str]] = {}
    for net, names in (settings.get("netclass_assignments") or {}).items():
        assigned[str(net)] = [str(names)] if isinstance(names, str) else [str(name) for name in names or []]
    return classes, patterns, assigned


def _class_of(net: str, classes: dict[str, _NetClass], patterns, assigned) -> _NetClass:
    names = list(assigned.get(net, []))
    names += [netclass for pattern, netclass in patterns if pattern == net or fnmatch.fnmatchcase(net, pattern)]
    found = [classes[name] for name in names if name in classes]
    if not found:
        return classes["Default"]
    return min(found, key=lambda netclass: (netclass.priority, netclass.name))


# --- footprints ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Pad:
    """One pad seen from the top, in its footprint's frame (KiCad mm, y down)."""

    number: str
    kind: str
    x: float
    y: float
    angle: float  # relative to the footprint, degrees
    copper: tuple[str, ...]
    shape: tuple  # hashable: the copper outline in the pad's frame
    drill: tuple[float, float] | None
    hole: tuple[float, float]  # the drill's offset from the pad's position (front view)
    net: str | None


def _flip_layer(name: str) -> str:
    if name.startswith("F."):
        return "B." + name[2:]
    if name.startswith("B."):
        return "F." + name[2:]
    return name


def _copper(layers: Iterable[str], board_copper: tuple[str, ...], *, flipped: bool) -> tuple[str, ...]:
    names: set[str] = set()
    for layer in layers:
        layer = str(layer)
        if layer in ("*.Cu", "F&B.Cu"):
            names.update(board_copper if layer == "*.Cu" else ("F.Cu", "B.Cu"))
        elif layer.endswith(".Cu"):
            names.add(_flip_layer(layer) if flipped else layer)
    return tuple(name for name in board_copper if name in names)


def _mirror(node):
    """``node`` with every y in it negated (a footprint's bottom-side flip, undone)."""
    if not isinstance(node, list):
        return node
    out = [node[0]]
    head = sexpr.head(node)
    if head in {"start", "end", "mid", "center", "xy", "at", "offset"} and len(node) >= 3 and isinstance(node[2], (int, float)):
        return [node[0], node[1], -node[2], *node[3:]]
    for child in node[1:]:
        out.append(_mirror(child))
    return out


def _freeze(node):
    if isinstance(node, list):
        return tuple(_freeze(child) for child in node)
    if isinstance(node, float):
        return round(node, 9)
    return node if not isinstance(node, Sym) else str(node)


def _read_pad(pad: list, *, theta: float, bottom: bool, board_copper: tuple[str, ...]) -> _Pad:
    if bottom:
        pad = _mirror(pad)
    at = sexpr.find(pad, "at")
    x, y = _xy(at, (0.0, 0.0))
    stored_angle = float(at[3]) if at is not None and len(at) > 3 else 0.0
    angle = (theta - stored_angle) if bottom else (stored_angle - theta)
    angle = round(angle % 360.0, 6) % 360.0
    size = sexpr.find(pad, "size")
    width = float(size[1]) if size is not None and len(size) > 1 else 0.0
    height = float(size[2]) if size is not None and len(size) > 2 else width
    drill_node = sexpr.find(pad, "drill")
    drill = None
    hole = (0.0, 0.0)
    if drill_node is not None:
        numbers = [float(item) for item in drill_node[1:] if isinstance(item, (int, float))]
        if numbers:
            drill = (numbers[0], numbers[1] if len(numbers) > 1 else numbers[0])
        hole = _xy(sexpr.find(drill_node, "offset"), (0.0, 0.0))
    layers = sexpr.find(pad, "layers")
    copper = _copper(layers[1:] if layers is not None else (), board_copper, flipped=bottom)
    shape_name = str(pad[3]) if len(pad) > 3 else "circle"
    details = []
    for key in ("roundrect_rratio", "rect_delta", "options", "primitives"):
        child = sexpr.find(pad, key)
        if child is not None:
            details.append(_freeze(child))
    net = sexpr.value(pad, "net")
    if isinstance(net, int):
        # A board written before KiCad 10 numbers its nets: (net 3 "GND").
        net_node = sexpr.find(pad, "net")
        net = net_node[2] if net_node is not None and len(net_node) > 2 else None
    return _Pad(
        number=str(pad[1]),
        kind=str(pad[2]),
        x=x,
        y=y,
        angle=angle,
        copper=copper,
        shape=(shape_name, round(width, 9), round(height, 9), round(hole[0], 9), round(hole[1], 9), tuple(details)),
        drill=drill,
        hole=hole,
        net=str(net) if net not in (None, "") else None,
    )


def _reference(footprint: list) -> str:
    for prop in sexpr.find_all(footprint, "property"):
        if len(prop) > 2 and prop[1] == "Reference":
            return str(prop[2])
    for text in sexpr.find_all(footprint, "fp_text"):
        if len(text) > 2 and text[1] == "reference":
            return str(text[2])
    return ""


# Pad outlines, in the pad's own frame: DSN micrometres, y up, centred on the pad's position.


def _rounded_rect(width: float, height: float, radius: float, cx: float, cy: float) -> list[Point]:
    radius = min(radius, width / 2, height / 2)
    hx, hy = width / 2 - radius, height / 2 - radius
    points: list[Point] = []
    for (sx, sy), start in (((1, 1), 0.0), ((-1, 1), 90.0), ((-1, -1), 180.0), ((1, -1), 270.0)):
        centre = (cx + sx * hx, cy + sy * hy)
        a0 = math.radians(start)
        first = (centre[0] + radius * math.cos(a0), centre[1] + radius * math.sin(a0))
        last = (centre[0] + radius * math.cos(a0 + math.pi / 2), centre[1] + radius * math.sin(a0 + math.pi / 2))
        points.extend(_curve_points(_Edge(first, last, centre, math.pi / 2), outside=True))
        points.append(last)
    return points


def _stadium(width: float, height: float, cx: float, cy: float) -> list[Point]:
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
        points.extend(_curve_points(_Edge(first, last, centre, math.pi), outside=True))
        points.append(last)
    return points


def _hull(points: list[Point]) -> list[Point]:
    unique = sorted(set((round(x, 6), round(y, 6)) for x, y in points))
    if len(unique) < 3:
        return unique

    def cross(o: Point, a: Point, b: Point) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[Point] = []
    for point in unique:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    upper: list[Point] = []
    for point in reversed(unique):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    return lower[:-1] + upper[:-1]


def _blob(x: float, y: float, radius: float) -> list[Point]:
    """Points whose hull holds a disc of ``radius`` about (x, y)."""
    if radius <= 0:
        return [(x, y)]
    return _curve_points(_circle_edge((x, y), radius), outside=True)


def _custom_outline(pad_shape: tuple, width: float, height: float, cx: float, cy: float) -> list[Point]:
    """A custom pad's convex hull: its anchor and every primitive, strokes included."""
    details = {item[0]: item for item in pad_shape[5]}
    anchor = "circle"
    options = details.get("options")
    if options is not None:
        for child in options[1:]:
            if isinstance(child, tuple) and child and child[0] == "anchor" and len(child) > 1:
                anchor = str(child[1])
    points: list[Point] = _blob(cx, cy, width / 2) if anchor == "circle" else [
        (cx - width / 2, cy - height / 2), (cx + width / 2, cy - height / 2),
        (cx + width / 2, cy + height / 2), (cx - width / 2, cy + height / 2),
    ]
    primitives = details.get("primitives")
    for primitive in (primitives[1:] if primitives is not None else ()):
        if not isinstance(primitive, tuple) or not primitive:
            continue
        values = {child[0]: child for child in primitive[1:] if isinstance(child, tuple) and child}
        stroke = float(values["width"][1]) * 1000.0 / 2 if "width" in values and len(values["width"]) > 1 else 0.0

        def local(key: str) -> Point:
            node = values[key]
            return cx + float(node[1]) * 1000.0, cy - float(node[2]) * 1000.0

        kind = str(primitive[0])
        if kind in ("gr_poly", "gr_line", "gr_rect", "gr_curve", "gr_arc", "gr_circle", "gr_bbox"):
            corners: list[Point] = []
            if kind == "gr_poly" and "pts" in values:
                corners = [(cx + float(xy[1]) * 1000.0, cy - float(xy[2]) * 1000.0) for xy in values["pts"][1:] if xy and xy[0] == "xy"]
            elif kind in ("gr_line",) and {"start", "end"} <= set(values):
                corners = [local("start"), local("end")]
            elif kind in ("gr_rect", "gr_bbox") and {"start", "end"} <= set(values):
                (x1, y1), (x2, y2) = local("start"), local("end")
                corners = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
            elif kind == "gr_curve" and "pts" in values:
                corners = [(cx + float(xy[1]) * 1000.0, cy - float(xy[2]) * 1000.0) for xy in values["pts"][1:] if xy and xy[0] == "xy"]
            elif kind == "gr_arc" and {"start", "mid", "end"} <= set(values):
                edge = _arc_edge(local("start"), local("mid"), local("end"))
                corners = _curve_points(edge, outside=True) + [edge.end]
            elif kind == "gr_circle" and {"center", "end"} <= set(values):
                centre, rim = local("center"), local("end")
                corners = _blob(centre[0], centre[1], math.hypot(rim[0] - centre[0], rim[1] - centre[1]) + stroke)
                stroke = 0.0
            for x, y in corners:
                points.extend(_blob(x, y, stroke))
    return _hull(points)


def _pad_outline(pad: _Pad) -> tuple:
    """The pad's copper as one DSN shape spec in its own frame: ``(kind, numbers...)``."""
    name, width, height, ox, oy, _details = pad.shape
    w, h = width * 1000.0, height * 1000.0
    cx, cy = ox * 1000.0, -oy * 1000.0
    details = {item[0]: item for item in pad.shape[5]}
    if name == "circle" or (name == "oval" and abs(w - h) < 1e-9):
        return ("circle", max(w, h), cx, cy)
    if name == "rect":
        return ("rect", cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
    if name == "oval":
        return ("polygon", tuple(_stadium(w, h, cx, cy)))
    if name in ("roundrect", "chamfered_rect"):
        ratio = float(details["roundrect_rratio"][1]) if "roundrect_rratio" in details else 0.0
        radius = ratio * min(w, h)
        if radius <= 0:
            return ("rect", cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
        return ("polygon", tuple(_rounded_rect(w, h, radius, cx, cy)))
    if name == "trapezoid":
        delta = details.get("rect_delta")
        dx = abs(float(delta[1])) * 1000.0 if delta is not None and len(delta) > 1 else 0.0
        dy = abs(float(delta[2])) * 1000.0 if delta is not None and len(delta) > 2 else 0.0
        # The trapezoid's bounding box holds it whichever way its delta leans.
        return ("rect", cx - (w + dy) / 2, cy - (h + dx) / 2, cx + (w + dy) / 2, cy + (h + dx) / 2)
    if name == "custom":
        return ("polygon", tuple(_custom_outline(pad.shape, w, h, cx, cy)))
    raise DesignError(f"pad {pad.number} has a shape KiCad 10 does not write: {name!r}")


def _shape_node(spec: tuple, layer: str) -> list:
    kind = spec[0]
    if kind == "circle":
        return ["circle", layer, _num(spec[1]), _num(spec[2]), _num(spec[3])]
    if kind == "rect":
        return ["rect", layer, *(_num(value) for value in spec[1:])]
    return ["polygon", layer, "0", *(_num(value) for point in spec[1] for value in point)]


# --- the DSN document ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class ViaKind:
    diameter: float
    drill: float
    layers: tuple[str, str]


@dataclass(frozen=True)
class Dsn:
    """A board's routing problem, and the way from its aliases back to the board."""

    text: str
    frame: DsnFrame
    layers: tuple[str, ...]
    nets: dict[str, str]  # DSN net alias -> KiCad net name
    widths: dict[str, float]  # DSN net alias -> its class's track width (mm)
    vias: dict[str, ViaKind]  # DSN padstack name -> the via it is
    routed: tuple[str, ...]  # KiCad nets the router was given, sorted


class _Q(str):
    """A DSN string written in quotes."""


def _atom(item) -> str:
    if isinstance(item, _Q):
        if '"' in item or "\n" in item:
            raise DesignError(f"{str(item)!r} cannot be written into a Specctra file (it holds a quote or a newline)")
        return f'"{item}"'
    return str(item)


def _render(node: list, depth: int, out: list[str]) -> None:
    indent = "  " * depth
    if not any(isinstance(item, list) for item in node):
        line = indent + "(" + " ".join(_atom(item) for item in node) + ")"
        if len(line) <= 120:
            out.append(line)
            return
        # Long runs of numbers wrap; Freerouting reads whitespace (never a tab) between tokens.
        words = [_atom(item) for item in node]
        head, rest = words[:3], words[3:]
        out.append(indent + "(" + " ".join(head))
        for start in range(0, len(rest), 10):
            out.append(indent + "  " + " ".join(rest[start:start + 10]))
        out[-1] += ")"
        return
    first = next(index for index, item in enumerate(node) if isinstance(item, list))
    out.append(indent + "(" + " ".join(_atom(item) for item in node[:first]))
    for item in node[first:]:
        if isinstance(item, list):
            _render(item, depth + 1, out)
        else:
            out.append(indent + "  " + _atom(item))
    out.append(indent + ")")


def _via_name(index: int, kind: ViaKind, board_copper: tuple[str, ...]) -> str:
    first, last = board_copper.index(kind.layers[0]), board_copper.index(kind.layers[1])
    # KiCad's spelling (outer:drill in µm) is how Freerouting reads a via's drill from its name.
    return f"V{index}_{round(kind.diameter * 1000)}:{round(kind.drill * 1000)}_um_L{first}_{last}"


def board_dsn(
    pcb_tree: list,
    project: str | dict,
    *,
    skip: Iterable[str] = (),
    layers: Iterable[str] | None = None,
    name: str = "board",
    host_version: str = "",
) -> Dsn:
    """The DSN routing problem of the board ``pcb_tree`` (a ``.kicad_pcb`` tree, KiCad 10).

    ``project`` is the board's ``.kicad_pro`` (text or parsed): its net classes
    and constraints are the routing rules. ``skip`` names nets the router must
    leave alone (a ground carried by a pour): their pads and copper stay in the
    problem as obstacles. A name that is no net of the board is refused.
    ``layers`` names the copper layers tracks may run on (all by default); the
    rest are written as Freerouting's power layers, which it never routes and
    vias pass through.
    """
    if sexpr.head(pcb_tree) != "kicad_pcb":
        raise DesignError("board_dsn takes a KiCad board tree, (kicad_pcb ...)")
    settings = _project(project)
    rules = _rules(settings)
    classes, patterns, assigned = _netclasses(settings)
    frame = DsnFrame(*_origin(pcb_tree))
    board_copper = _copper_layers(pcb_tree)
    default = classes["Default"]

    # Footprints: images (seen from the top), padstacks, placements, pins of nets.
    padstacks: dict[tuple, str] = {}
    padstack_nodes: list[list] = []
    images: dict[tuple, str] = {}
    image_nodes: list[list] = []
    placements: dict[str, list[list]] = {}
    net_pins: dict[str, list[str]] = {}
    refs_seen: set[str] = set()
    hole_growth = max(0.0, rules["min_hole_clearance"] - max(default.clearance, rules["min_clearance"])) * 1000.0
    footprints = [item for item in pcb_tree[1:] if sexpr.head(item) == "footprint"]
    for index, footprint in enumerate(footprints):
        at = sexpr.find(footprint, "at")
        theta = float(at[3]) if at is not None and len(at) > 3 else 0.0
        bottom = sexpr.value(footprint, "layer") == "B.Cu"
        pads = [
            _read_pad(pad, theta=theta, bottom=bottom, board_copper=board_copper)
            for pad in sexpr.find_all(footprint, "pad")
        ]
        numbers = [pad.number for pad in pads if pad.copper and pad.kind != "np_thru_hole"]
        pins: list[list] = []
        pin_of: list[tuple[str, _Pad]] = []
        for pad_index, pad in enumerate(pads):
            px, py = pad.x * 1000.0, -pad.y * 1000.0
            if pad.kind == "np_thru_hole":
                if pad.drill is None:
                    continue
                # An unplated hole is a pin of no net: an obstacle on every layer.
                outline, pad_layers, drilled, pin_name = _hole_outline(pad, hole_growth), board_copper, False, f"@{pad_index + 1}"
            elif pad.copper:
                pin_name = pad.number if _SAFE_PIN.fullmatch(pad.number) and numbers.count(pad.number) == 1 else f"@{pad_index + 1}"
                outline, pad_layers, drilled = _pad_outline(pad), pad.copper, pad.drill is not None and pad.kind == "thru_hole"
            else:
                continue
            key = (outline, pad_layers, drilled, pad.drill if drilled else None, pad.kind == "np_thru_hole")
            stack = padstacks.get(key)
            if stack is None:
                number = len(padstacks) + 1
                if pad.kind == "np_thru_hole":
                    stack = f"H{number}"
                elif drilled:
                    outer = min(pad.shape[1], pad.shape[2])
                    stack = f"T{number}_{round(outer * 1000)}:{round(min(pad.drill) * 1000)}_um"
                else:
                    stack = f"S{number}"
                padstacks[key] = stack
                padstack_nodes.append(
                    ["padstack", stack, *(["shape", _shape_node(outline, layer)] for layer in pad_layers), ["attach", "off"]]
                )
            pin: list = ["pin", stack, pin_name, _num(px), _num(py)]
            if pad.angle:
                pin.append(["rotate", _num(pad.angle)])
            pins.append(pin)
            pin_of.append((pin_name, pad))
        if not pins:
            continue
        lib_id = str(footprint[1]) if len(footprint) > 1 and not isinstance(footprint[1], list) else "footprint"
        image_key = (lib_id, _freeze(pins))
        image = images.get(image_key)
        if image is None:
            image = f"I{len(images) + 1}_{_sanitize(lib_id.split(':')[-1])}"
            images[image_key] = image
            image_nodes.append(["image", image, *pins])
        ref = _reference(footprint)
        component = ref if _SAFE_REF.fullmatch(ref) and ref not in refs_seen else f"@{index + 1}"
        refs_seen.add(component)
        x, y = frame.to_dsn(*_xy(at, (0.0, 0.0)))
        rotation = round(((theta + 180.0) if bottom else theta) % 360.0, 6) % 360.0
        placements.setdefault(image, []).append(
            ["place", component, _num(x), _num(y), "back" if bottom else "front", _num(rotation), ["lock_type", "position"]]
        )
        for pin_name, pad in pin_of:
            if pad.net is not None and pad.kind != "np_thru_hole":
                net_pins.setdefault(pad.net, []).append(f"{component}-{pin_name}")

    # The nets the router is given: two pads or more, and not skipped.
    skipped = set()
    for net in skip:
        if net not in net_pins:
            listing = ", ".join(sorted(_shown(name) for name, pins in net_pins.items() if len(pins) > 1)) or "none"
            raise DesignError(
                f"autoroute(skip=...) names {_shown(net)!r}, which is no net with pads on this board "
                f"(its routable nets are {listing})"
            )
        skipped.add(net)
    routed = sorted(net for net, pins in net_pins.items() if len(pins) > 1 and net not in skipped)
    aliases = {net: f"N{index + 1}_{_sanitize(net)}".rstrip("_") for index, net in enumerate(routed)}
    net_class = {net: _class_of(net, classes, patterns, assigned) for net in routed}

    # Vias: one kind per net class the router may drop, and every kind the board already has.
    via_kinds: dict[ViaKind, str] = {}

    def via_named(kind: ViaKind) -> str:
        if kind not in via_kinds:
            via_kinds[kind] = _via_name(len(via_kinds) + 1, kind, board_copper)
        return via_kinds[kind]

    through = (board_copper[0], board_copper[-1])
    used_classes = sorted({netclass.name: netclass for netclass in net_class.values()}.values(), key=lambda c: (c.name != "Default", c.name))
    class_via = {netclass.name: via_named(ViaKind(netclass.via_diameter, netclass.via_drill, through)) for netclass in used_classes}
    if "Default" not in class_via:
        class_via["Default"] = via_named(ViaKind(default.via_diameter, default.via_drill, through))

    # The board's own copper, fixed.
    wiring: list[list] = []
    for item in pcb_tree[1:]:
        head = sexpr.head(item)
        if head in ("segment", "arc", "via"):
            wiring.extend(_fixed_wiring(item, head, frame, board_copper, aliases, via_named))

    def clearance_of(netclass: _NetClass) -> float:
        return max(netclass.clearance, rules["min_clearance"]) + MARGIN

    routing = set(board_copper) if layers is None else set(layers)
    unknown = sorted(routing - set(board_copper))
    if unknown or not routing:
        raise DesignError(
            f"autoroute(layers=...) takes this board's copper layers ({', '.join(board_copper)}); got {', '.join(unknown) or 'none'}"
        )
    structure: list = ["structure"]
    for index, layer in enumerate(board_copper):
        kind = "signal" if layer in routing else "power"
        structure.append(["layer", layer, ["type", kind], ["property", ["index", str(index)]]])
    boundaries, holes = _outline(pcb_tree, frame)
    for boundary in boundaries:
        points = boundary + boundary[:1]
        structure.append(["boundary", ["path", "pcb", "0", *(_num(value) for point in points for value in point)], ["clearance_class", "edge"]])
    track_zones, via_zones = _zone_obstacles(pcb_tree, frame, board_copper)
    obstacles = [(hole, board_copper, True) for hole in holes]
    obstacles += [(points, zone_layers, False) for points, zone_layers in track_zones]
    obstacles += [(points, drawn_layers, False) for points, drawn_layers in _copper_obstacles(pcb_tree, frame, board_copper)]
    _add_obstacles(obstacles, image_nodes, padstack_nodes, placements)
    for index, (points, zone_layers) in enumerate(via_zones):
        targets = ["signal"] if set(zone_layers) == set(board_copper) else list(zone_layers)
        for layer in targets:
            structure.append(["via_keepout", f"zone{index + 1}", ["polygon", layer, "0", *(_num(value) for point in points for value in point)]])
    structure.append(["via", *[via_kinds[kind] for kind in via_kinds if via_kinds[kind] in class_via.values()]])
    structure.append(
        [
            "rule",
            ["width", _num(default.track_width * 1000.0)],
            ["clearance", _num(clearance_of(default) * 1000.0)],
            ["clearance", _num((rules["min_copper_edge_clearance"] + MARGIN) * 1000.0), ["type", "default_edge"]],
        ]
    )
    structure.append(["control", ["via_at_smd", "off"]])

    library: list = ["library", *image_nodes, *padstack_nodes]
    for kind, via in via_kinds.items():
        library.append(
            ["padstack", via, *(["shape", ["circle", layer, _num(kind.diameter * 1000.0), "0", "0"]]
                               for layer in board_copper[board_copper.index(kind.layers[0]):board_copper.index(kind.layers[1]) + 1]), ["attach", "off"]]
        )

    network: list = ["network"]
    for net in routed:
        network.append(["net", aliases[net], ["pins", *net_pins[net]]])
    for number, netclass in enumerate(used_classes):
        members = [aliases[net] for net in routed if net_class[net] is netclass]
        class_name = _DEFAULT_CLASS if netclass.name == "Default" else f"C{number}{_sanitize(netclass.name).replace('_', '')}"
        network.append(
            [
                "class",
                class_name,
                *members,
                ["circuit", ["use_via", class_via[netclass.name]]],
                ["rule", ["width", _num(netclass.track_width * 1000.0)], ["clearance", _num(clearance_of(netclass) * 1000.0)]],
            ]
        )

    document: list = [
        "pcb",
        _Q(f"{name}.dsn"),
        ["parser", ["string_quote", '"'], ["space_in_quoted_tokens", "on"], ["host_cad", "cadgen"], ["host_version", _Q(host_version or "cadgen")]],
        ["resolution", "um", str(RESOLUTION)],
        ["unit", "um"],
        structure,
        ["placement", *(["component", image, *places] for image, places in placements.items())],
        library,
        network,
        ["wiring", *wiring],
    ]
    out: list[str] = []
    _render(document, 0, out)
    text = "\n".join(out) + "\n"
    return Dsn(
        text=text,
        frame=frame,
        layers=board_copper,
        nets={alias: net for net, alias in aliases.items()},
        widths={aliases[net]: net_class[net].track_width for net in routed},
        vias={name: kind for kind, name in via_kinds.items()},
        routed=tuple(routed),
    )


def _copper_layers(tree: list) -> tuple[str, ...]:
    layers = sexpr.find(tree, "layers")
    names = [
        str(entry[1])
        for entry in (layers[1:] if layers is not None else [])
        if isinstance(entry, list) and len(entry) >= 2 and str(entry[1]).endswith(".Cu")
    ]
    inner = sorted((name for name in names if name.startswith("In")), key=lambda name: int(re.sub(r"\D", "", name) or 0))
    ordered = (["F.Cu"] if "F.Cu" in names else []) + inner + (["B.Cu"] if "B.Cu" in names else [])
    if len(ordered) < 2:
        raise DesignError("the board has fewer than two copper layers to route on")
    return tuple(ordered)


def _hole_outline(pad: _Pad, growth: float) -> tuple:
    """An unplated hole as a pad outline in its own frame, grown so copper keeps the hole clearance.

    A pad wider than its drill has a copper ring of no net: the outline holds
    the ring too.
    """
    dx, dy = (value * 1000.0 for value in pad.drill)
    if pad.copper:
        dx, dy = max(dx, pad.shape[1] * 1000.0), max(dy, pad.shape[2] * 1000.0)
    cx, cy = pad.hole[0] * 1000.0, -pad.hole[1] * 1000.0
    if abs(dx - dy) < 1e-9:
        return ("circle", dx + 2 * growth, cx, cy)
    return ("polygon", tuple(_stadium(dx + 2 * growth, dy + 2 * growth, cx, cy)))


def _zone_layers(zone: list, board_copper: tuple[str, ...]) -> tuple[str, ...]:
    layers = sexpr.find(zone, "layers")
    names = [str(name) for name in layers[1:]] if layers is not None else [str(sexpr.value(zone, "layer", ""))]
    return _copper(names, board_copper, flipped=False)


def _zone_obstacles(tree: list, frame: DsnFrame, board_copper: tuple[str, ...]):
    """Rule areas that forbid tracks, and those that forbid only vias: ``(points, layers)`` each.

    A footprint's rule areas count too (KiCad stores a footprint's zones in
    board coordinates). A zone's later polygons are cutouts of its first,
    which an obstacle may cover.
    """
    zones = [item for item in tree[1:] if sexpr.head(item) == "zone"]
    for footprint in (item for item in tree[1:] if sexpr.head(item) == "footprint"):
        zones.extend(sexpr.find_all(footprint, "zone"))
    tracks_out: list[tuple[list[Point], tuple[str, ...]]] = []
    vias_out: list[tuple[list[Point], tuple[str, ...]]] = []
    for zone in zones:
        keepout = sexpr.find(zone, "keepout")
        if keepout is None:
            continue
        rules = {str(child[0]): str(child[1]) for child in keepout[1:] if isinstance(child, list) and len(child) > 1}
        tracks, vias = rules.get("tracks") == "not_allowed", rules.get("vias") == "not_allowed"
        layers = _zone_layers(zone, board_copper)
        if not (tracks or vias) or not layers:
            continue
        polygon = sexpr.find(zone, "polygon")
        pts = sexpr.find(polygon, "pts") if polygon is not None else None
        loop = _pts_loop(pts, lambda point: frame.to_dsn(*point)) if pts is not None else []
        if len(loop) < 2:
            continue
        (tracks_out if tracks else vias_out).append((_loop_points(loop, keep_inside=False), layers))
    return tracks_out, vias_out


def _stroke_radius(node: list) -> float:
    """Half a graphic's stroke width, in micrometres."""
    stroke = sexpr.find(node, "stroke")
    width = sexpr.value(stroke, "width") if stroke is not None else sexpr.value(node, "width")
    return float(width or 0.0) * 1000.0 / 2


def _filled(node: list) -> bool:
    fill = sexpr.find(node, "fill")
    if fill is None or len(fill) < 2:
        return False
    value = fill[1]
    if isinstance(value, list):  # KiCad 6: (fill (type solid))
        value = sexpr.value(fill, "type", "none")
    return str(value) in ("yes", "solid")


def _strokes(points: list[Point], radius: float, *, closed: bool) -> list[list[Point]]:
    """A stroked polyline as one convex region per segment (a stroke of no width gets a micrometre)."""
    radius = max(radius, 1.0)
    ends = points + points[:1] if closed else points
    return [_hull(_blob(*a, radius) + _blob(*b, radius)) for a, b in zip(ends, ends[1:]) if a != b]


def _graphic_regions(node: list, convert) -> list[list[Point]]:
    """The copper of one gr_/fp_ graphic as regions that hold it (DSN micrometres)."""
    kind = str(node[0])[3:]
    radius = _stroke_radius(node)
    filled = _filled(node)
    if kind == "line":
        return _strokes([convert(_xy(sexpr.find(node, "start"))), convert(_xy(sexpr.find(node, "end")))], radius, closed=False)
    if kind in ("arc", "circle"):
        if kind == "arc":
            edge = _arc_edge(*(convert(_xy(sexpr.find(node, key))) for key in ("start", "mid", "end")))
        else:
            center = convert(_xy(sexpr.find(node, "center")))
            rim = convert(_xy(sexpr.find(node, "end")))
            edge = _circle_edge(center, math.hypot(rim[0] - center[0], rim[1] - center[1]))
        if edge.center is None:
            return _strokes([edge.start, edge.end], radius, closed=False)
        if kind == "circle" and filled:
            return [_curve_points(_circle_edge(edge.center, edge.radius + radius), outside=True)]
        count = max(1, math.ceil(abs(edge.sweep) / _step(edge.radius)))
        sagitta = edge.radius * (1 - math.cos(abs(edge.sweep) / count / 2))
        points = edge.sample(count)
        return _strokes(points[:-1] if kind == "circle" else points, radius + sagitta, closed=kind == "circle")
    if kind == "rect":
        (x1, y1), (x2, y2) = _xy(sexpr.find(node, "start")), _xy(sexpr.find(node, "end"))
        corners = [convert(point) for point in ((x1, y1), (x2, y1), (x2, y2), (x1, y2))]
        return ([corners] if filled else []) + _strokes(corners, radius, closed=True)
    if kind == "poly":
        pts = sexpr.find(node, "pts")
        loop = _pts_loop(pts, convert) if pts is not None else []
        if len(loop) < 2:
            return []
        points = _loop_points(loop, keep_inside=False)
        return ([points] if filled else []) + _strokes(points, radius, closed=True)
    pts = sexpr.find(node, "pts")
    points = [convert(_xy(xy)) for xy in sexpr.find_all(pts, "xy")] if pts is not None else []
    if len(points) != 4:
        return []
    curve = [edge.start for edge in _bezier(points)] + [points[-1]]
    return _strokes(curve, radius, closed=False)


def _hidden(node: list) -> bool:
    hide = sexpr.find(node, "hide")
    if hide is not None:
        return len(hide) < 2 or hide[1] == "yes"
    effects = sexpr.find(node, "effects")
    return any(item == "hide" for item in node[1:]) or (effects is not None and any(item == "hide" for item in effects[1:]))


def _text_region(node: list, place, frame: DsnFrame) -> list[Point] | None:
    """A box that holds a copper text's strokes, estimated from its font, never smaller.

    KiCad's stroke font advances about a glyph width per character and stands a
    little over its height: the box allows 1.25 widths a character and 1.7
    heights a line, plus the stroke.
    """
    index = 1 if sexpr.head(node) == "gr_text" else 2  # (gr_text "T" ...), (fp_text reference "R1" ...)
    text = str(node[index]) if len(node) > index and not isinstance(node[index], list) else ""
    if not text.strip() or _hidden(node):
        return None
    at = sexpr.find(node, "at")
    anchor = place(_xy(at, (0.0, 0.0)))
    angle = float(at[3]) if at is not None and len(at) > 3 and isinstance(at[3], (int, float)) else 0.0
    effects = sexpr.find(node, "effects")
    font = sexpr.find(effects, "font") if effects is not None else None
    size = sexpr.find(font, "size") if font is not None else None
    height = float(size[1]) if size is not None and len(size) > 1 else 1.0
    width = float(size[2]) if size is not None and len(size) > 2 else height
    thickness = float(sexpr.value(font, "thickness", 0.15 * height) if font is not None else 0.15 * height)
    lines = text.split("\n")
    length = max(len(line) for line in lines) * width * 1.25 + thickness
    tall = len(lines) * height * 1.7 + thickness
    justify = [str(item) for item in (sexpr.find(effects, "justify") or [])[1:]] if effects is not None else []
    xs = (0.0, length) if "left" in justify else (-length, 0.0) if "right" in justify else (-length / 2, length / 2)
    if "mirror" in justify:
        xs = (-xs[1], -xs[0])
    ys = (0.0, tall) if "top" in justify else (-tall, 0.0) if "bottom" in justify else (-tall / 2, tall / 2)
    corners = []
    for x, y in ((xs[0], ys[0]), (xs[1], ys[0]), (xs[1], ys[1]), (xs[0], ys[1])):
        dx, dy = _placed((0.0, 0.0), angle)((x, y))
        corners.append(frame.to_dsn(anchor[0] + dx, anchor[1] + dy))
    return corners


def _box(points: list[Point]) -> tuple[float, float, float, float]:
    xs, ys = [point[0] for point in points], [point[1] for point in points]
    return min(xs), min(ys), max(xs), max(ys)


def _overlaps(a: tuple, b: tuple) -> bool:
    return a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]


def _copper_obstacles(tree: list, frame: DsnFrame, board_copper: tuple[str, ...]) -> list[tuple[list[Point], tuple[str, ...]]]:
    """Copper that is no pad, track or pour -- graphics and text on a copper layer -- as ``(points, layers)``.

    A footprint's copper graphic that touches one of its pads (a net tie, a
    solder jumper's bridge, an antenna's feed) is that pad's copper, and is
    left to KiCad's check rather than walled off from its own net. A board
    graphic on a net is that net's copper, likewise.
    """
    board = lambda point: point  # noqa: E731
    regions: list[tuple[str, list[Point]]] = []

    def take(node: list, place, pads: list[tuple] | None) -> None:
        layer = str(sexpr.value(node, "layer", ""))
        if layer not in board_copper:
            return
        head = sexpr.head(node)
        if head in ("gr_text", "fp_text", "property"):
            region = _text_region(node, place, frame)
            found = [region] if region is not None else []
        else:
            if head.startswith("gr_") and sexpr.value(node, "net") not in (None, "", 0):
                return
            found = [region for region in _graphic_regions(node, lambda point: frame.to_dsn(*place(point))) if len(region) >= 3]
        if pads is not None and any(_overlaps(_box(region), pad) for region in found for pad in pads):
            return
        regions.extend((layer, region) for region in found)

    for item in tree[1:]:
        head = sexpr.head(item)
        if head == "gr_text" or (head is not None and head.startswith("gr_") and head[3:] in _GRAPHIC):
            take(item, board, None)
        elif head == "footprint":
            at = sexpr.find(item, "at")
            theta = float(at[3]) if at is not None and len(at) > 3 else 0.0
            place = _placed(_xy(at, (0.0, 0.0)), theta)
            pads = []
            for pad in sexpr.find_all(item, "pad"):
                size = sexpr.find(pad, "size")
                reach = math.hypot(float(size[1]), float(size[2]) if len(size) > 2 else float(size[1])) * 500.0 if size is not None else 0.0
                cx, cy = frame.to_dsn(*place(_xy(sexpr.find(pad, "at"), (0.0, 0.0))))
                pads.append((cx - reach, cy - reach, cx + reach, cy + reach))
            for child in item[1:]:
                child_head = sexpr.head(child)
                if child_head in ("fp_text", "property") or (child_head is not None and child_head.startswith("fp_") and child_head[3:] in _GRAPHIC):
                    take(child, place, pads)
    return [(region, (layer,)) for layer, region in regions]


# Every obstacle to tracks is a pin of no net on a locked part of its own. Freerouting
# 2.4's maze search keeps a keepout's bare clearance while its trace insertion asks a
# little more (ClearanceMatrix.clearance_safety_margin), so a route that hugs a keepout
# is found and then refused; around a pin both agree.
_OBSTACLES = "I0_obstacles"


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
    if len(ring) >= 3 and _area(ring) < 0:
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


def _convex_pieces(points: list[Point]) -> list[list[Point]]:
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
            return [_hull(ring)]
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


def _add_obstacles(obstacles, image_nodes: list[list], padstack_nodes: list[list], placements: dict[str, list[list]]) -> None:
    """``(points, layers, edge)`` obstacles as pins of no net on one locked part at the origin.

    An ``edge`` obstacle (a hole in the outline) keeps the edge clearance;
    the rest the board's.
    """
    pins: list[list] = []
    infos: list[list] = []
    for points, layers, edge in obstacles:
        for piece in _convex_pieces(points):
            number = len(pins) + 1
            stack = f"K{number}"
            coordinates = [_num(value) for point in piece for value in point]
            padstack_nodes.append(["padstack", stack, *(["shape", ["polygon", layer, "0", *coordinates]] for layer in layers), ["attach", "off"]])
            pins.append(["pin", stack, str(number), "0", "0"])
            if edge:
                infos.append(["pin", str(number), ["clearance_class", "edge"]])
    if pins:
        image_nodes.append(["image", _OBSTACLES, *pins])
        placements[_OBSTACLES] = [["place", "@obstacles", "0", "0", "front", "0", ["lock_type", "position"], *infos]]


def _fixed_wiring(item: list, head: str, frame: DsnFrame, board_copper, aliases: dict[str, str], via_named) -> list[list]:
    net = sexpr.value(item, "net")
    if isinstance(net, int):
        node = sexpr.find(item, "net")
        net = node[2] if node is not None and len(node) > 2 else None
    alias = aliases.get(str(net)) if net not in (None, "") else None
    tail: list = ([["net", alias]] if alias is not None else []) + [["type", "fix"]]
    if head == "via":
        size, drill = sexpr.value(item, "size"), sexpr.value(item, "drill")
        layers = sexpr.find(item, "layers")
        pair = tuple(str(name) for name in (layers[1:3] if layers is not None else ()))
        if len(pair) != 2 or any(name not in board_copper for name in pair):
            pair = (board_copper[0], board_copper[-1])
        if board_copper.index(pair[0]) > board_copper.index(pair[1]):
            pair = (pair[1], pair[0])
        if size is None or drill is None:
            return []
        name = via_named(ViaKind(float(size), float(drill), pair))
        x, y = frame.to_dsn(*_xy(sexpr.find(item, "at")))
        return [["via", name, _num(x), _num(y), *tail]]
    layer = str(sexpr.value(item, "layer", ""))
    if layer not in board_copper:
        return []
    width = float(sexpr.value(item, "width", 0.0)) * 1000.0
    start = frame.to_dsn(*_xy(sexpr.find(item, "start")))
    end = frame.to_dsn(*_xy(sexpr.find(item, "end")))
    if head == "segment":
        if start == end:
            return []
        points = [start, end]
    else:
        edge = _arc_edge(start, frame.to_dsn(*_xy(sexpr.find(item, "mid"))), end)
        if edge.center is None:
            points = [start, end]
        else:
            count = max(1, math.ceil(abs(edge.sweep) / _step(edge.radius)))
            points = edge.sample(count)
            # The arc bulges past its chords by up to the sagitta: widen the polyline to cover it.
            width += 2 * edge.radius * (1 - math.cos(abs(edge.sweep) / count / 2)) + 2 * MARGIN * 1000.0
    return [["wire", ["path", layer, _num(width), *(_num(value) for point in points for value in point)], *tail]]


# --- the session ---------------------------------------------------------------------------------

_TOKEN = re.compile(r'\s*(?:(\()|(\))|"([^"]*)"|([^\s()"]+))')
_UNIT_UM = {"inch": 25400.0, "mil": 25.4, "cm": 10000.0, "mm": 1000.0, "um": 1.0}


def _specctra(text: str) -> list:
    """A Specctra file as nested lists of strings (atoms keep their spelling)."""
    stack: list[list] = []
    root: list | None = None
    position = 0
    for match in _TOKEN.finditer(text):
        if match.start() != position:
            break
        position = match.end()
        opened, closed, quoted, bare = match.groups()
        if opened:
            node: list = []
            if stack:
                stack[-1].append(node)
            elif root is None:
                root = node
            else:
                raise SessionError("a Specctra session holds more than one expression")
            stack.append(node)
        elif closed:
            if not stack:
                raise SessionError("a Specctra session closes a list it never opened")
            stack.pop()
        elif stack:
            stack[-1].append(quoted if quoted is not None else bare)
        else:
            raise SessionError("a Specctra session has text outside its list")
    if text[position:].strip() or stack or root is None:
        raise SessionError("Freerouting's session file is cut short or unreadable")
    return root


def _scope(node: list, name: str) -> list | None:
    return next((child for child in node[1:] if isinstance(child, list) and child and str(child[0]).lower() == name), None)


def _scopes(node: list, name: str) -> list[list]:
    return [child for child in node[1:] if isinstance(child, list) and child and str(child[0]).lower() == name]


@dataclass(frozen=True)
class RoutedTrack:
    net: str
    layer: str
    width: float
    start: Point  # KiCad millimetres
    end: Point


@dataclass(frozen=True)
class RoutedVia:
    net: str
    at: Point  # KiCad millimetres
    kind: ViaKind


@dataclass(frozen=True)
class Routes:
    tracks: tuple[RoutedTrack, ...]
    vias: tuple[RoutedVia, ...]


def _number(text: str) -> float:
    try:
        return float(text)
    except (TypeError, ValueError):
        raise SessionError(f"Freerouting's session has {text!r} where a number belongs") from None


def read_session(text: str, dsn: Dsn) -> Routes:
    """The tracks and vias a Specctra session adds to the board ``dsn`` was written from.

    Only what the router added comes back: the board's own copper went in fixed,
    and a session leaves fixed copper out. Everything is checked against the
    design -- a net, layer or via the DSN never named, a swapped pin, a
    copper area -- and refused, rather than guessed.
    """
    root = _specctra(text)
    if not root or str(root[0]).lower() != "session":
        raise SessionError("Freerouting's output is not a Specctra session (session ...)")
    was_is = _scope(root, "was_is")
    if was_is is not None and _scopes(was_is, "pins"):
        raise SessionError("Freerouting swapped pins (was_is); cadgen does not let the router change the netlist")
    routes = _scope(root, "routes")
    if routes is None:
        return Routes(tracks=(), vias=())
    resolution = _scope(routes, "resolution")
    if resolution is None or len(resolution) < 3 or str(resolution[1]).lower() not in _UNIT_UM:
        raise SessionError("Freerouting's session gives no resolution for its routes")
    scale = _UNIT_UM[str(resolution[1]).lower()] / _number(resolution[2])  # µm per session unit
    frame = dsn.frame
    tracks: list[RoutedTrack] = []
    vias: list[RoutedVia] = []
    network = _scope(routes, "network_out")
    for net_node in _scopes(network, "net") if network is not None else []:
        alias = str(net_node[1]) if len(net_node) > 1 else ""
        net = dsn.nets.get(alias)
        if net is None:
            raise SessionError(f"Freerouting routed a net the design does not have: {alias!r}")
        for item in net_node[2:]:
            if not isinstance(item, list) or not item:
                continue
            kind = str(item[0]).lower()
            if kind == "wire":
                path = _scope(item, "path")
                if path is None:
                    raise SessionError(f"Freerouting answered net {net} with a copper area rather than a track")
                layer = str(path[1])
                if layer not in dsn.layers:
                    raise SessionError(f"Freerouting routed net {net} on {layer!r}, a layer the board does not have")
                width = _nm(_number(path[2]) * scale / 1000.0)
                expected = dsn.widths.get(alias)
                if expected is not None and abs(width - expected) <= 0.0005:
                    width = expected
                numbers = [_number(value) * scale for value in path[3:]]
                if len(numbers) % 2 or len(numbers) < 4:
                    raise SessionError(f"Freerouting wrote a track of net {net} with an odd or short list of points")
                points = [frame.to_kicad(numbers[i], numbers[i + 1]) for i in range(0, len(numbers), 2)]
                for start, end in zip(points, points[1:]):
                    if start != end:
                        tracks.append(RoutedTrack(net=net, layer=layer, width=width, start=start, end=end))
            elif kind == "via":
                padstack = str(item[1]) if len(item) > 1 else ""
                via = dsn.vias.get(padstack)
                if via is None:
                    raise SessionError(f"Freerouting placed a via the design does not offer: {padstack!r}")
                at = frame.to_kicad(_number(item[2]) * scale, _number(item[3]) * scale)
                vias.append(RoutedVia(net=net, at=at, kind=via))
            else:
                raise SessionError(f"Freerouting's session holds a {kind!r} in net {net}, which cadgen does not read")
    tracks.sort(key=lambda track: (track.net, track.layer, track.start, track.end, track.width))
    vias.sort(key=lambda via: (via.net, via.at, via.kind.diameter, via.kind.drill))
    unique_tracks = tuple(dict.fromkeys(tracks))
    return Routes(tracks=unique_tracks, vias=tuple(dict.fromkeys(vias)))


# --- routes into the board -----------------------------------------------------------------------


def _route_nodes(routes: Routes, ids: Ids) -> list[list]:
    nodes: list[list] = []
    index = 0
    for track in routes.tracks:
        nodes.append(
            [
                Sym("segment"),
                [Sym("start"), *track.start],
                [Sym("end"), *track.end],
                [Sym("width"), track.width],
                [Sym("layer"), track.layer],
                [Sym("net"), track.net],
                [Sym("uuid"), ids(f"route:{index}")],
            ]
        )
        index += 1
    for via in routes.vias:
        nodes.append(
            [
                Sym("via"),
                [Sym("at"), *via.at],
                [Sym("size"), via.kind.diameter],
                [Sym("drill"), via.kind.drill],
                [Sym("layers"), *via.kind.layers],
                [Sym("net"), via.net],
                [Sym("uuid"), ids(f"route:{index}")],
            ]
        )
        index += 1
    return nodes


def with_routes(pcb_tree: list, routes: Routes, *, project: str) -> list:
    """``pcb_tree`` with the routes added after its own tracks and vias (a copy).

    Each route gets a UUID derived from its place in the sorted routes
    (``route:<index>`` in the project's namespace), so the same routes always
    write the same board.
    """
    tree = copy.deepcopy(pcb_tree)
    nodes = _route_nodes(routes, Ids(project))
    heads = [sexpr.head(item) for item in tree]
    copper = [index for index, head in enumerate(heads) if head in ("segment", "arc", "via")]
    if copper:
        at = copper[-1] + 1
    elif "zone" in heads:
        at = heads.index("zone")
    elif "embedded_fonts" in heads:
        at = heads.index("embedded_fonts")
    else:
        at = len(tree)
    tree[at:at] = nodes
    return tree
