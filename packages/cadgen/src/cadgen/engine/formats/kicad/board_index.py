"""Any KiCad board, read as what a person can point at, and board references answered.

:func:`read_index` reads a saved ``.kicad_pcb`` into its parts (footprints, with their fields and outlines), pads,
tracks, vias, pours, unplated holes, ``Edge.Cuts`` outline and nets, from the
file alone: no KiCad runs. :func:`read_board` (``pcb.read_board``) answers
board references (:mod:`cadgen.engine.formats.kicad.refs`) against that index:
``board.resolve("#U3.9")`` is pad 9 of U3, where it is, its net, and its part.

Frames
------
A board file is in KiCad's frame: millimetres, y down, on its page -- the frame
every reference and every answer of :func:`read_board` is in, so a point
the viewer copies can be used directly in a native board edit. :meth:`BoardIndex.mapped` moves the
index into the plot's SHEET frame (:mod:`cadgen.engine.formats.kicad.plot`): KiCad's frame moved
so the board's top-left corner is (0, 0); ``origin`` is where KiCad's (0, 0)
lands. Angles are degrees counter-clockwise as seen from the top, in every frame.

What is read, as KiCad stores it: a footprint is placed by its ``(at x y angle)``
or, in KiCad 11's files, its ``(transform (translate ..) (rotate ..) (scale ..))``;
its pads and graphics are in its own frame (a pad's position relative to the
footprint, before its rotation; its angle absolute), a bottom-side footprint's
already flipped; a pad's shape
is a polygon (rect, roundrect, oval, circle, trapezoid, chamfered rect; a
custom pad's is the hull of its primitives); arcs and circles are sampled; a
part's outline is its courtyard (else the box around its pads and fabrication
drawing); the outline's segments are joined where their ends meet within
KiCad's own chaining epsilon. Net names are unescaped as KiCad displays them
(``TX/RX``, never ``TX{slash}RX``); a net's class comes from the project file
beside the board. Older boards KiCad opens read too: numbered nets, ``fp_text``
references, and a KiCad 5 board's modules and its arcs drawn by centre and angle.

The readers of the file's items (``graphic``, ``pad_shape``, ``FootprintFrame``,
``item_layers``, ``net_of``...) are shared with the plot, which walks the same
tree for everything it draws.
"""

from __future__ import annotations

import difflib
import math
import re
from collections import deque
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence

from cadgen.engine.formats.kicad.ref_path import ref_prefix_names
from cadgen.engine.formats.kicad import sexpr
from cadgen.engine.formats.kicad.geometry import (
    XY, arc_points, area, bezier_points, box, format_xy, hull, inside, polygon_distance, polyline_distance, rotate,
)
from cadgen.engine.formats.kicad.naming import natural, netclass_of, project_netclasses, unescape_net_name
from cadgen.engine.formats.kicad.refs import BoardSelector, format_board_selector, parse_board_selector, parse_board_token, selector_or_none

__all__ = [
    "BoardIndex",
    "BoardView",
    "Copper",
    "FootprintFrame",
    "Hole",
    "Net",
    "Pad",
    "Part",
    "Point",
    "Track",
    "Via",
    "Zone",
    "copper_layers",
    "expand_copper",
    "footprint_property",
    "graphic",
    "item_layers",
    "layer_of",
    "net_of",
    "net_table",
    "pad_shape",
    "points_of",
    "read_board",
    "read_board_index",
    "read_index",
]

#: How far beyond a piece of copper a ``#net:NAME@x..y..`` point may land and still name it, mm.
COPPER_TOLERANCE = 0.1
_JOIN = 1e-4  # a polygon's point this close to the one before it is that point, mm
# KiCad's outline chaining epsilon (DEFAULT_CHAINING_EPSILON_MM): segments whose ends are this
# close are one outline. Its own library footprints leave gaps of microns in their cutouts.
_CHAIN = 0.01
_CIRCLE_SEGMENTS = 24
_CORNER_SEGMENTS = 4

_GRAPHICS = ("line", "rect", "poly", "circle", "arc", "curve")


# --- what a board holds ------------------------------------------------------------


@dataclass(frozen=True)
class Pad:
    """One copper pad of a part. ``at`` is its position (the hole's, for a through-hole pad)."""

    part: str
    number: str
    name: str | None  # the pin function KiCad shows, when the pad has one
    net: str | None
    type: str | None  # the pin's electrical type: "passive", "power_in"...
    side: str  # "top", "bottom" or "both" (through the board)
    at: XY
    polygon: tuple[XY, ...]
    drill: float | None = None  # a through-hole pad's hole, its smaller size
    # How many of the part's pads share this number: a connector's shell, a tab, a thermal pad's
    # islands are one pin of several pads. ``#J1.SH`` names them all; ``Part.pads_numbered`` lists them.
    shared: int = 1

    kind = "pad"

    @property
    def selector(self) -> str | None:
        """``#U3.9``; ``None`` for a pad the language cannot name (no number, or one with a dot)."""
        return selector_or_none("pad", ref=self.part, pad=self.number)

    def __repr__(self) -> str:
        name = f" ({self.name})" if self.name and self.name != self.number else ""
        shared = (f"; one of {self.shared} pads numbered {self.number}: "
                  f"part.pads_numbered({self.number!r}) lists them") if self.shared > 1 else ""
        return f"Pad({self.part}.{self.number}{name}, net={self.net!r}, at={format_xy(self.at)}, {self.side}{shared})"


@dataclass(frozen=True)
class Part:
    """A footprint on the board, by its reference designator."""

    ref: str
    value: str
    footprint: str  # the library id: "Resistor_SMD:R_0603_1608Metric"
    side: str  # "top" or "bottom"
    at: XY
    rotation: float  # degrees counter-clockwise, seen from the top
    fields: Mapping[str, str]  # every field but Reference and Value with something in it
    dnp: bool
    outline: tuple[XY, ...]  # the courtyard, else the box around its pads and fabrication drawing
    pads: tuple[Pad, ...] = ()
    in_bom: bool = True  # False when the footprint is excluded from the BOM (or on the board only)

    kind = "part"

    @property
    def selector(self) -> str | None:
        return selector_or_none("part", ref=self.ref)

    def pads_numbered(self, number: str) -> tuple[Pad, ...]:
        """Every pad of the part numbered ``number``: one, or the several a shell or a tab has."""
        found = tuple(pad for pad in self.pads if pad.number == str(number))
        if not found:
            self.pad(number)  # raises, naming the numbers there are
        return found

    def pad(self, number: str) -> Pad:
        """The part's pad ``number`` (the first, when several share it: see :meth:`pads_numbered`)."""
        for pad in self.pads:
            if pad.number == str(number):
                return pad
        numbers = ", ".join(sorted({pad.number for pad in self.pads if pad.number}, key=natural)) or "none"
        raise ValueError(f"{self.ref} has no pad {number}; its pads are {numbers}")

    def __repr__(self) -> str:
        return (
            f"Part({self.ref}, value={self.value!r}, footprint={self.footprint!r}, at={format_xy(self.at)}, "
            f"rotation={self.rotation:g}, {self.side})"
        )


@dataclass(frozen=True)
class Track:
    """A copper segment or arc (sampled to points), on one layer."""

    net: str | None
    layer: str
    width: float
    points: tuple[XY, ...]
    arc: bool = False

    kind = "track"

    def __repr__(self) -> str:
        what = "arc" if self.arc else "track"
        return f"Track({what} {self.net!r} on {self.layer}, {self.width:g} mm, {format_xy(self.points[0])} -> {format_xy(self.points[-1])})"


@dataclass(frozen=True)
class Via:
    net: str | None
    at: XY
    diameter: float
    drill: float
    layers: tuple[str, ...] = ("F.Cu", "B.Cu")

    kind = "via"

    def __repr__(self) -> str:
        return f"Via({self.net!r} at {format_xy(self.at)}, {self.diameter:g}/{self.drill:g} mm)"


@dataclass(frozen=True)
class Zone:
    """A pour on one copper layer: its outline as drawn, and the copper KiCad filled it with."""

    net: str | None
    layer: str
    outline: tuple[XY, ...]
    fills: tuple[tuple[XY, ...], ...] = ()

    kind = "zone"

    def __repr__(self) -> str:
        state = "filled" if self.fills else "unfilled"
        return f"Zone({self.net!r} on {self.layer}, {state})"


@dataclass(frozen=True)
class Hole:
    """An unplated hole: a mounting hole, a connector's locating peg. ``part`` holds it."""

    at: XY
    diameter: float
    part: str | None = None

    kind = "hole"

    def __repr__(self) -> str:
        owner = f" of {self.part}" if self.part else ""
        return f"Hole({self.diameter:g} mm{owner} at {format_xy(self.at)})"


@dataclass(frozen=True)
class Net:
    """A net and everything on it."""

    name: str
    netclass: str
    pads: tuple[Pad, ...] = ()
    tracks: tuple[Track, ...] = ()
    vias: tuple[Via, ...] = ()
    zones: tuple[Zone, ...] = ()

    kind = "net"

    @property
    def selector(self) -> str:
        return format_board_selector("net", net=self.name)

    def __repr__(self) -> str:
        return (
            f"Net({self.name!r}, class {self.netclass!r}: {len(self.pads)} pads, {len(self.tracks)} tracks, "
            f"{len(self.vias)} vias, {len(self.zones)} zones)"
        )


@dataclass(frozen=True)
class Copper:
    """A net's copper at a point: its pads, tracks, vias and pours there, nearest first."""

    net: Net
    at: XY
    items: tuple[Pad | Track | Via | Zone, ...]

    kind = "copper"

    @property
    def selector(self) -> str:
        return format_board_selector("copper", net=self.net.name, at=self.at)

    def __repr__(self) -> str:
        return f"Copper({self.net.name!r} at {format_xy(self.at)}: {', '.join(repr(item) for item in self.items)})"


@dataclass(frozen=True)
class Point:
    """A point on (or off) the board and what is there."""

    at: XY
    on_board: bool  # inside the Edge.Cuts outline (and outside its cutouts)
    parts: tuple[Part, ...]  # whose outline holds the point
    pads: tuple[Pad, ...]
    copper: tuple[Track | Via | Zone, ...]  # tracks, vias and filled pours, any net
    holes: tuple[Hole, ...]

    kind = "point"

    @property
    def selector(self) -> str:
        return format_board_selector("point", at=self.at)

    def __repr__(self) -> str:
        what = [repr(item) for item in (*self.pads, *self.copper, *self.holes)]
        what += [f"inside {part.ref}" for part in self.parts]
        where = "on the board" if self.on_board else "off the board"
        return f"Point({format_xy(self.at)}, {where}" + (f": {'; '.join(what)}" if what else "") + ")"


@dataclass(frozen=True)
class BoardIndex:
    """A board in one frame. ``origin`` is where KiCad's page origin (0, 0) lies in that frame."""

    parts: tuple[Part, ...]
    tracks: tuple[Track, ...]
    vias: tuple[Via, ...]
    zones: tuple[Zone, ...]
    holes: tuple[Hole, ...]
    outline: tuple[tuple[XY, ...], ...]  # Edge.Cuts as polylines; a closed one repeats its first point
    nets: tuple[tuple[str, str], ...]  # (name, class), in natural order
    origin: XY

    @property
    def pads(self) -> tuple[Pad, ...]:
        return tuple(pad for part in self.parts for pad in part.pads)

    def mapped(self, move: Callable[[float, float], XY]) -> "BoardIndex":
        """The same board in another frame: ``move(x, y)`` is where a point of this one lands."""

        def point(xy: XY) -> XY:
            return move(xy[0], xy[1])

        def points(items: Iterable[XY]) -> tuple[XY, ...]:
            return tuple(point(xy) for xy in items)

        def pad(item: Pad) -> Pad:
            return replace(item, at=point(item.at), polygon=points(item.polygon))

        parts = tuple(
            replace(part, at=point(part.at), outline=points(part.outline), pads=tuple(pad(item) for item in part.pads))
            for part in self.parts
        )
        return replace(
            self,
            parts=parts,
            tracks=tuple(replace(track, points=points(track.points)) for track in self.tracks),
            vias=tuple(replace(via, at=point(via.at)) for via in self.vias),
            zones=tuple(
                replace(zone, outline=points(zone.outline), fills=tuple(points(fill) for fill in zone.fills))
                for zone in self.zones
            ),
            holes=tuple(replace(hole, at=point(hole.at)) for hole in self.holes),
            outline=tuple(points(line) for line in self.outline),
            origin=point(self.origin),
        )

    def as_json(self, digits: int = 4) -> dict:
        """The index as the plot payload's ``board``: every point in this frame, rounded to
        ``digits`` decimals (a tenth of a micron at 4)."""

        def num(value: float) -> float:
            rounded = round(float(value), digits)
            return 0.0 if rounded == 0 else rounded

        def xy(point: XY) -> list[float]:
            return [num(point[0]), num(point[1])]

        def path(points: Iterable[XY]) -> list[list[float]]:
            return [xy(point) for point in points]

        return {
            "origin": xy(self.origin),
            "parts": [
                {
                    "ref": part.ref, "value": part.value, "footprint": part.footprint, "side": part.side,
                    "at": xy(part.at), "rotation": num(part.rotation), "fields": dict(part.fields),
                    "dnp": part.dnp, "outline": path(part.outline),
                }
                for part in self.parts
            ],
            "pads": [
                {
                    "part": pad.part, "number": pad.number, "name": pad.name, "net": pad.net, "type": pad.type,
                    "side": pad.side, "at": xy(pad.at), "polygon": path(pad.polygon),
                    **({"drill": num(pad.drill)} if pad.drill else {}),
                }
                for pad in self.pads
            ],
            "tracks": [
                {"net": track.net, "layer": track.layer, "width": num(track.width), "points": path(track.points)}
                for track in self.tracks
            ],
            "vias": [
                {"net": via.net, "at": xy(via.at), "diameter": num(via.diameter), "drill": num(via.drill)}
                for via in self.vias
            ],
            "zones": [{"net": zone.net, "layer": zone.layer, "outline": path(zone.outline)} for zone in self.zones],
            "holes": [{"at": xy(hole.at), "diameter": num(hole.diameter), "part": hole.part} for hole in self.holes],
            "outline": [path(line) for line in self.outline],
            "nets": [{"name": name, "class": netclass} for name, netclass in self.nets],
        }


# --- geometry ------------------------------------------------------------------------


def _circle(center: XY, radius: float, segments: int = _CIRCLE_SEGMENTS) -> list[XY]:
    return [(center[0] + radius * math.cos(2 * math.pi * k / segments), center[1] + radius * math.sin(2 * math.pi * k / segments)) for k in range(segments)]


def _close(a: XY, b: XY, within: float = _JOIN) -> bool:
    return abs(a[0] - b[0]) <= within and abs(a[1] - b[1]) <= within


def _chain(pieces: list[list[XY]]) -> list[list[XY]]:
    """Open polylines joined end to end, as KiCad chains an outline's segments: from each line's
    end, on to the piece whose end is nearest it within KiCad's chaining epsilon (``_CHAIN``),
    until none is; then, if that end meets the line's start, the line is closed (a closed line
    repeats its first point), else it grows from its start the same way.

    Each piece's ends are filed in a grid of ``_CHAIN`` cells, so a line's end meets only its
    neighbours: linear in the pieces, which an outline imported from a drawing has thousands
    of, in no order.
    """
    pending = [list(piece) for piece in pieces if len(piece) >= 2]
    cells: dict[tuple[int, int], list[int]] = {}

    def cell(point: XY) -> tuple[int, int]:
        return math.floor(point[0] / _CHAIN), math.floor(point[1] / _CHAIN)

    for index, piece in enumerate(pending):
        for end in (piece[0], piece[-1]):
            cells.setdefault(cell(end), []).append(index)
    used = [False] * len(pending)

    def nearest(point: XY) -> tuple[int, bool] | None:
        """The unused piece with an end nearest ``point`` (the first in the outline's order of
        those as near), and whether that end is its start."""
        x, y = cell(point)
        best = None
        for index in sorted({index for dx in (-1, 0, 1) for dy in (-1, 0, 1) for index in cells.get((x + dx, y + dy), ())}):
            if used[index]:
                continue
            for at_start, end in ((True, pending[index][0]), (False, pending[index][-1])):
                if _close(point, end, _CHAIN):
                    distance = (point[0] - end[0]) ** 2 + (point[1] - end[1]) ** 2
                    if best is None or distance < best[0]:
                        best = (distance, index, at_start)
        return None if best is None else best[1:]

    def closed(line) -> bool:
        return len(line) > 2 and _close(line[0], line[-1], _CHAIN)

    lines: list[list[XY]] = []
    for first, start in enumerate(pending):
        if used[first]:
            continue
        used[first] = True
        line = deque(start)
        while (found := nearest(line[-1])) is not None:
            index, at_start = found
            used[index] = True
            line.extend(pending[index][1:] if at_start else reversed(pending[index][:-1]))
        while not closed(line) and (found := nearest(line[0])) is not None:
            index, at_start = found
            used[index] = True
            line.extendleft(pending[index][1:] if at_start else reversed(pending[index][:-1]))
        joined = list(line)
        if closed(joined):
            joined[-1] = joined[0]
        lines.append(joined)
    return lines


def _closed(line: Sequence[XY]) -> bool:
    return len(line) > 3 and line[0] == line[-1]


# --- reading graphics ------------------------------------------------------------------


def points_of(node: list | None) -> list[XY]:
    """A ``(pts ...)`` list: its points, an ``(arc ...)`` in it sampled."""
    out: list[XY] = []
    for child in (node or [])[1:]:
        head = sexpr.head(child)
        if head == "xy":
            out.append(sexpr.pair(child))
        elif head == "arc":
            start, mid, end = (sexpr.pair(sexpr.find(child, key)) for key in ("start", "mid", "end"))
            if None not in (start, mid, end):
                sampled = arc_points(start, mid, end)
                out.extend(sampled[1:] if out and _close(out[-1], sampled[0]) else sampled)
    return out


def _legacy_arc(center: XY, start: XY, angle: float) -> tuple[XY, XY, XY]:
    """A KiCad 5 arc, ``(start <centre>) (end <start>) (angle <degrees>)``, as its start, middle
    and end: KiCad 5 turned its start point about the centre by ``-angle``."""

    def turned(degrees: float) -> XY:
        x, y = rotate(start[0] - center[0], start[1] - center[1], degrees)
        return center[0] + x, center[1] + y

    return start, turned(-angle / 2), turned(-angle)


def graphic(node: list) -> tuple[list[XY], bool] | None:
    """A graphic item (``gr_*``, ``fp_*`` or a custom pad's primitive) as points, and whether
    they close on themselves (a rectangle, a circle, a polygon; a line, an arc or a curve do not)."""
    head = sexpr.head(node) or ""
    kind = head.split("_", 1)[-1]
    if kind == "line":
        start, end = sexpr.pair(sexpr.find(node, "start")), sexpr.pair(sexpr.find(node, "end"))
        return ([start, end], False) if start and end else None
    if kind == "arc":
        start, mid, end = (sexpr.pair(sexpr.find(node, key)) for key in ("start", "mid", "end"))
        if start and end and mid is None and sexpr.value(node, "angle") is not None:
            start, mid, end = _legacy_arc(start, end, sexpr.number(sexpr.value(node, "angle")))
        return (arc_points(start, mid, end), False) if start and mid and end else None
    if kind == "circle":
        center, end = sexpr.pair(sexpr.find(node, "center")), sexpr.pair(sexpr.find(node, "end"))
        if not center or not end:
            return None
        return _circle(center, math.hypot(end[0] - center[0], end[1] - center[1])), True
    if kind == "rect":
        start, end = sexpr.pair(sexpr.find(node, "start")), sexpr.pair(sexpr.find(node, "end"))
        if not start or not end:
            return None
        return [start, (end[0], start[1]), end, (start[0], end[1])], True
    if kind == "poly":
        points = points_of(sexpr.find(node, "pts"))
        return (points, True) if points else None
    if kind == "curve":
        points = points_of(sexpr.find(node, "pts"))
        return (bezier_points(points), False) if points else None
    return None


def layer_of(node: list) -> str | None:
    """An item's ``(layer NAME)``, or ``None``."""
    layer = sexpr.value(node, "layer")
    return str(layer) if layer is not None else None


# --- pads ----------------------------------------------------------------------------------


def _rounded_rect(width: float, height: float, radius: float, chamfer: float = 0.0, corners: frozenset = frozenset()) -> list[XY]:
    """A rectangle, its corners rounded by ``radius`` or cut by ``chamfer`` (the named ones)."""
    hw, hh = width / 2, height / 2
    radius = max(0.0, min(radius, hw, hh))
    out: list[XY] = []
    # KiCad's corners (y down), walked top left, top right, bottom right, bottom left; (sx, sy)
    # points from each into the pad. Corner k's rounding sweeps pi + k pi/2 to a quarter turn on.
    for k, (name, cx, cy, sx, sy) in enumerate((
        ("top_left", -hw, -hh, 1, 1),
        ("top_right", hw, -hh, -1, 1),
        ("bottom_right", hw, hh, -1, -1),
        ("bottom_left", -hw, hh, 1, -1),
    )):
        if name in corners and chamfer > 0:
            on_side, on_top_or_bottom = (cx, cy + sy * chamfer), (cx + sx * chamfer, cy)
            out.extend([on_side, on_top_or_bottom] if k % 2 == 0 else [on_top_or_bottom, on_side])
        elif radius > 0:
            ox, oy = cx + sx * radius, cy + sy * radius
            for step in range(_CORNER_SEGMENTS + 1):
                angle = math.pi + k * math.pi / 2 + (math.pi / 2) * step / _CORNER_SEGMENTS
                out.append((ox + radius * math.cos(angle), oy + radius * math.sin(angle)))
        else:
            out.append((cx, cy))
    return out


def _oval(width: float, height: float) -> list[XY]:
    if abs(width - height) < 1e-9:
        return _circle((0.0, 0.0), width / 2)
    out: list[XY] = []
    half = _CIRCLE_SEGMENTS // 2
    if width > height:
        radius, reach = height / 2, width / 2 - height / 2
        for step in range(half + 1):  # the right end, top to bottom
            angle = -math.pi / 2 + math.pi * step / half
            out.append((reach + radius * math.cos(angle), radius * math.sin(angle)))
        for step in range(half + 1):
            angle = math.pi / 2 + math.pi * step / half
            out.append((-reach + radius * math.cos(angle), radius * math.sin(angle)))
    else:
        radius, reach = width / 2, height / 2 - width / 2
        for step in range(half + 1):
            angle = math.pi + math.pi * step / half
            out.append((radius * math.cos(angle), -reach + radius * math.sin(angle)))
        for step in range(half + 1):
            angle = math.pi * step / half
            out.append((radius * math.cos(angle), reach + radius * math.sin(angle)))
    return out


def pad_shape(pad: list) -> list[XY]:
    """The pad's copper outline in its own frame, centred on its shape (not yet offset or turned)."""
    shape = str(pad[3]) if len(pad) > 3 and isinstance(pad[3], str) else "rect"
    size = sexpr.pair(sexpr.find(pad, "size"), (0.0, 0.0))
    width, height = abs(size[0]), abs(size[1])
    if shape == "circle":
        return _circle((0.0, 0.0), width / 2)
    if shape == "oval":
        return _oval(width, height)
    if shape == "trapezoid":
        dx, dy = (value / 2 for value in sexpr.pair(sexpr.find(pad, "rect_delta"), (0.0, 0.0)))
        hw, hh = width / 2, height / 2
        return [(-hw - dy, hh + dx), (hw + dy, hh - dx), (hw - dy, -hh + dx), (-hw + dy, -hh - dx)]
    if shape in ("rect", "roundrect"):
        radius = sexpr.number(sexpr.value(pad, "roundrect_rratio"), 0.0) * min(width, height) if shape == "roundrect" else 0.0
        chamfer_node = sexpr.find(pad, "chamfer")
        corners = frozenset(str(item) for item in (chamfer_node or [])[1:])
        chamfer = sexpr.number(sexpr.value(pad, "chamfer_ratio"), 0.0) * min(width, height) if corners else 0.0
        return _rounded_rect(width, height, radius, chamfer, corners)
    if shape == "custom":
        options = sexpr.find(pad, "options")
        anchor = str(sexpr.value(options, "anchor") or "circle") if options is not None else "circle"
        points = list(_circle((0.0, 0.0), width / 2) if anchor == "circle" else _rounded_rect(width, height, 0.0))
        for primitive in (sexpr.find(pad, "primitives") or [])[1:]:
            if not isinstance(primitive, list):
                continue
            drawn = graphic(primitive)
            if drawn is None:
                continue
            reach = sexpr.number(sexpr.value(primitive, "width"), 0.0) / 2
            for x, y in drawn[0]:
                points.extend([(x - reach, y - reach), (x + reach, y - reach), (x + reach, y + reach), (x - reach, y + reach)] if reach else [(x, y)])
        return hull(points)
    return _rounded_rect(width, height, 0.0)


_COPPER = re.compile(r"^(F|B|In\d+)\.Cu$")


def _copper_side(layers: Sequence[str]) -> str | None:
    names = set(layers)
    if names & {"*.Cu", "F&B.Cu"}:
        return "both"
    front, back = "F.Cu" in names, "B.Cu" in names
    if front and back:
        return "both"
    if front:
        return "top"
    if back:
        return "bottom"
    return "both" if any(_COPPER.match(name) for name in names) else None


# --- the board ---------------------------------------------------------------------------


def net_table(tree: list) -> dict[int, str]:
    """An older board's net table, ``(net 3 "GND")``: its numbers' names."""
    table = {}
    for node in sexpr.find_all(tree, "net"):
        if len(node) >= 3 and isinstance(node[1], int) and isinstance(node[2], str):
            table[node[1]] = node[2]
    return table


def net_of(node: list, table: Mapping[int, str]) -> str | None:
    """The net an item is on, as KiCad shows its name: ``(net "GND")``, or an older board's
    ``(net 3)`` looked up in ``table`` (:func:`net_table`); ``None`` for none."""
    found = sexpr.find(node, "net")
    name = None
    if found is not None and len(found) >= 2:
        last = found[-1]
        if isinstance(last, str):
            name = last
        elif isinstance(found[1], int):
            name = table.get(found[1])
    if name is None:
        named = sexpr.value(node, "net_name")
        name = named if isinstance(named, str) else None
    name = unescape_net_name(name) if name else None
    return name or None


def item_layers(node: list) -> list[str]:
    """An item's layers: its ``(layers ...)`` (a pad's, a via's, a zone's), else its one ``(layer ..)``."""
    layers = sexpr.find(node, "layers")
    if layers is not None:
        return [str(layer) for layer in layers[1:]]
    layer = layer_of(node)
    return [layer] if layer else []


def copper_layers(tree: list) -> list[str]:
    """The board's copper layers as its layer table declares them, front first."""
    table = sexpr.find(tree, "layers")
    names = [str(entry[1]) for entry in (table or [])[1:] if isinstance(entry, list) and len(entry) >= 2 and str(entry[1]).endswith(".Cu")]
    return names or ["F.Cu", "B.Cu"]


def expand_copper(layers: Sequence[str], copper: Sequence[str]) -> list[str]:
    """The copper layers among ``layers``, ``*.Cu`` and ``F&B.Cu`` spelled out over ``copper``."""
    out: list[str] = []
    for layer in layers:
        if layer in ("*.Cu", "F&B.Cu"):
            out.extend(copper if layer == "*.Cu" else ("F.Cu", "B.Cu"))
        elif _COPPER.match(layer):
            out.append(layer)
    return list(dict.fromkeys(out))


class FootprintFrame:
    """One footprint's frame: its children's points as they land on the board (KiCad's frame).

    A footprint is placed by ``(at x y angle)`` or, since KiCad 11, by ``(transform (translate x y)
    (rotate angle) (scale sx sy))``; the angle is degrees counter-clockwise on screen either way, and
    a scale (1 1 on every board KiCad writes today) multiplies a child's point before the turn.
    """

    def __init__(self, node: list):
        transform = sexpr.find(node, "transform")
        if transform is not None:
            self.x, self.y = sexpr.pair(sexpr.find(transform, "translate"), (0.0, 0.0))
            self.angle = sexpr.number(sexpr.value(transform, "rotate"), 0.0)
            self.scale = sexpr.pair(sexpr.find(transform, "scale"), (1.0, 1.0))
        else:
            at = sexpr.find(node, "at")
            self.x, self.y = sexpr.pair(at, (0.0, 0.0))
            self.angle = sexpr.number(at[3]) if at is not None and len(at) > 3 else 0.0
            self.scale = (1.0, 1.0)

    def place(self, point: XY) -> XY:
        dx, dy = rotate(point[0] * self.scale[0], point[1] * self.scale[1], self.angle)
        return self.x + dx, self.y + dy


def footprint_property(node: list, name: str) -> str | None:
    """A footprint's field ``name`` (``Reference``, ``Value``, ``MPN``...), an older board's
    ``fp_text reference`` included; ``None`` when it has none."""
    for item in sexpr.find_all(node, "property"):
        if len(item) >= 3 and item[1] == name:
            return str(item[2])
    for item in sexpr.find_all(node, "fp_text"):  # an older board's reference and value
        if len(item) >= 3 and str(item[1]) == name.lower():
            return str(item[2])
    return None


def _read_pad(node: list, frame: FootprintFrame, ref: str, table, copper: Sequence[str]) -> tuple[Pad | None, Hole | None]:
    kind = str(node[2]) if len(node) > 2 else ""
    at = sexpr.find(node, "at")
    local = sexpr.pair(at, (0.0, 0.0))
    angle = sexpr.number(at[3]) if at is not None and len(at) > 3 else 0.0
    center = frame.place(local)
    drill = sexpr.find(node, "drill")
    drill_sizes = [value for value in (drill or [])[1:] if isinstance(value, (int, float))]
    if kind == "np_thru_hole":
        size = drill_sizes[0] if drill_sizes else sexpr.pair(sexpr.find(node, "size"), (0.0, 0.0))[0]
        return None, Hole(at=center, diameter=float(size), part=ref)
    side = _copper_side(item_layers(node))
    if side is None:
        return None, None  # paste or mask only: no copper to point at
    offset = sexpr.pair(sexpr.find(drill, "offset"), (0.0, 0.0)) if drill is not None else (0.0, 0.0)
    polygon = []
    for x, y in pad_shape(node):
        dx, dy = rotate(x + offset[0], y + offset[1], angle)
        polygon.append((center[0] + dx, center[1] + dy))
    name = sexpr.value(node, "pinfunction")
    kind_of_pin = sexpr.value(node, "pintype")
    return Pad(
        part=ref,
        number=str(node[1]) if len(node) > 1 else "",
        name=str(name) if name is not None else None,
        net=net_of(node, table),
        type=str(kind_of_pin) if kind_of_pin is not None else None,
        side=side,
        at=center,
        polygon=tuple(polygon),
        drill=float(min(drill_sizes)) if drill_sizes and kind == "thru_hole" else None,
    ), None


def _read_footprint(node: list, table, copper: Sequence[str]) -> tuple[Part, list[Hole], list[Zone], list[list[XY]]]:
    frame = FootprintFrame(node)
    bottom = layer_of(node) == "B.Cu"
    ref = footprint_property(node, "Reference") or ""
    value = footprint_property(node, "Value") or ""
    fields: dict[str, str] = {}
    for item in sexpr.find_all(node, "property"):
        if len(item) >= 3 and item[1] not in ("Reference", "Value") and str(item[2]):
            fields[str(item[1])] = str(item[2])
    attr = sexpr.find(node, "attr")
    dnp = attr is not None and any(str(flag) == "dnp" for flag in attr[1:])
    in_bom = attr is None or not any(str(flag) in ("exclude_from_bom", "board_only") for flag in attr[1:])
    pads: list[Pad] = []
    holes: list[Hole] = []
    zones: list[Zone] = []
    edges: list[list[XY]] = []
    courtyard: dict[str, list[tuple[list[XY], bool]]] = {"F.CrtYd": [], "B.CrtYd": []}
    fab: list[XY] = []
    for child in node[2:]:
        head = sexpr.head(child)
        if head is None:
            continue
        if head == "pad":
            pad, hole = _read_pad(child, frame, ref, table, copper)
            if pad is not None:
                pads.append(pad)
            if hole is not None:
                holes.append(hole)
            continue
        if head == "zone":
            zones.extend(_read_zone(child, table, copper))  # stored in the board's frame
            continue
        if not head.startswith("fp_") or head.split("_", 1)[1] not in _GRAPHICS:
            continue
        drawn = graphic(child)
        if drawn is None:
            continue
        points = [frame.place(point) for point in drawn[0]]
        layer = layer_of(child)
        if layer in courtyard:
            courtyard[layer].append((points, drawn[1]))
        elif layer in ("F.Fab", "B.Fab"):
            fab.extend(points)
        elif layer == "Edge.Cuts":
            edges.append(points + [points[0]] if drawn[1] else points)
    sides = ("B.CrtYd", "F.CrtYd") if bottom else ("F.CrtYd", "B.CrtYd")
    outline = _outline(courtyard[sides[0]]) or _outline(courtyard[sides[1]])
    if not outline:
        drawn = [point for pad in pads for point in pad.polygon] + fab
        for hole in holes:
            reach = hole.diameter / 2
            drawn += [(hole.at[0] - reach, hole.at[1] - reach), (hole.at[0] + reach, hole.at[1] + reach)]
        outline = box(drawn)
    part = Part(
        ref=ref,
        value=value,
        footprint=str(node[1]) if len(node) > 1 and isinstance(node[1], str) else "",
        side="bottom" if bottom else "top",
        at=(frame.x, frame.y),
        rotation=frame.angle % 360.0,
        fields=fields,
        dnp=dnp,
        outline=tuple(outline),
        pads=_counted(pads),
        in_bom=in_bom,
    )
    return part, holes, zones, edges


def _counted(pads: list[Pad]) -> tuple[Pad, ...]:
    """``pads``, each knowing how many of them share its number."""
    counts: dict[str, int] = {}
    for pad in pads:
        counts[pad.number] = counts.get(pad.number, 0) + 1
    return tuple(replace(pad, shared=counts[pad.number]) if counts[pad.number] > 1 else pad for pad in pads)


def _outline(items: list[tuple[list[XY], bool]]) -> list[XY]:
    """A courtyard's outline: its largest closed loop, else the hull of what it draws."""
    if not items:
        return []
    loops = [points for points, closed in items if closed]
    loops += [line[:-1] for line in _chain([points for points, closed in items if not closed]) if _closed(line)]
    if loops:
        return list(max(loops, key=lambda loop: abs(area(loop))))
    return hull(point for points, _closed_ in items for point in points)


def _read_zone(node: list, table, copper: Sequence[str]) -> list[Zone]:
    if sexpr.find(node, "keepout") is not None:
        return []  # a rule area, not copper
    layers = expand_copper(item_layers(node), copper)
    if not layers:
        return []
    outline = tuple(points_of(sexpr.find(sexpr.find(node, "polygon") or [], "pts")))
    fills: dict[str, list[tuple[XY, ...]]] = {}
    for filled in sexpr.find_all(node, "filled_polygon"):
        layer = layer_of(filled) or layers[0]
        fills.setdefault(layer, []).append(tuple(points_of(sexpr.find(filled, "pts"))))
    net = net_of(node, table)
    return [Zone(net=net, layer=layer, outline=outline, fills=tuple(fills.get(layer, ()))) for layer in layers]


def read_index(text: str | list, *, project: Path | None = None) -> BoardIndex:
    """The board ``text`` (a ``.kicad_pcb``'s, or its parsed tree) as an index in KiCad's frame.

    ``project`` is the ``.kicad_pcb``'s ``.kicad_pro``, read for the nets' classes when it
    exists. Raises ``ValueError`` for text that is not a KiCad board.
    """
    if isinstance(text, list):
        tree = text
    else:
        try:
            tree = sexpr.parse(text)
        except sexpr.SexprError as error:
            raise ValueError(f"not a readable KiCad board ({error})") from None
    if sexpr.head(tree) != "kicad_pcb":
        raise ValueError("not a KiCad board: a .kicad_pcb starts with (kicad_pcb ...)")
    table = net_table(tree)
    copper = copper_layers(tree)
    parts: list[Part] = []
    holes: list[Hole] = []
    zones: list[Zone] = []
    edges: list[list[XY]] = []
    tracks: list[Track] = []
    vias: list[Via] = []
    for node in tree[1:]:
        head = sexpr.head(node)
        if head in ("footprint", "module"):  # a KiCad 5 board's footprints are modules
            part, part_holes, part_zones, part_edges = _read_footprint(node, table, copper)
            parts.append(part)
            holes.extend(part_holes)
            zones.extend(part_zones)
            edges.extend(part_edges)
        elif head in ("segment", "arc"):
            if head == "segment":
                points = [sexpr.pair(sexpr.find(node, "start")), sexpr.pair(sexpr.find(node, "end"))]
            else:
                points = arc_points(*(sexpr.pair(sexpr.find(node, key)) for key in ("start", "mid", "end")))
            if None in points:
                continue
            net = net_of(node, table)
            tracks.append(Track(net=net, layer=layer_of(node) or "", width=sexpr.number(sexpr.value(node, "width")), points=tuple(points), arc=head == "arc"))
        elif head == "via":
            at = sexpr.pair(sexpr.find(node, "at"))
            if at is None:
                continue
            net = net_of(node, table)
            vias.append(Via(
                net=net, at=at, diameter=sexpr.number(sexpr.value(node, "size")), drill=sexpr.number(sexpr.value(node, "drill")),
                layers=tuple(item_layers(node)) or ("F.Cu", "B.Cu"),
            ))
        elif head == "zone":
            zones.extend(_read_zone(node, table, copper))
        elif head and head.startswith("gr_") and head[3:] in _GRAPHICS and layer_of(node) == "Edge.Cuts":
            drawn = graphic(node)
            if drawn is not None:
                edges.append(drawn[0] + [drawn[0][0]] if drawn[1] else drawn[0])
    names = {pad.net for part in parts for pad in part.pads} | {track.net for track in tracks} | {via.net for via in vias} | {zone.net for zone in zones}
    names |= {unescape_net_name(name) for name in table.values()}
    assigned, patterns = project_netclasses(project)
    nets = tuple((name, netclass_of(name, assigned, patterns)) for name in sorted((name for name in names if name), key=natural))
    return BoardIndex(
        parts=tuple(sorted(parts, key=lambda part: natural(part.ref))),
        tracks=tuple(tracks),
        vias=tuple(vias),
        zones=tuple(zones),
        holes=tuple(holes),
        outline=tuple(tuple(line) for line in _chain(edges)),
        nets=nets,
        origin=(0.0, 0.0),
    )


# --- answering references -------------------------------------------------------------


_FORMS = (
    "a board's are a part #U3, a pad #U3.9, a net #net:VIN, copper #net:VIN@x40.1y21.6 or a point "
    "#@x40.1y21.6 (millimetres in KiCad's frame, y down)"
)


class BoardView:
    """A board read for references, in KiCad's frame (millimetres, y down).

    ``parts`` and ``nets`` are everything on it; :meth:`resolve` answers a board
    reference (with or without its file): ``#U3`` is a :class:`Part`, ``#U3.9`` a
    :class:`Pad`, ``#net:VIN`` a :class:`Net` with everything
    on it, ``#net:VIN@x40.1y21.6`` that net's :class:`Copper` at the point (within
    ``COPPER_TOLERANCE``), ``#@x40.1y21.6`` a :class:`Point` and what is there (:meth:`at`).
    """

    def __init__(self, path: Path, index: BoardIndex):
        self.path = Path(path)
        self._index = index
        self.parts: tuple[Part, ...] = index.parts
        self.tracks: tuple[Track, ...] = index.tracks
        self.vias: tuple[Via, ...] = index.vias
        self.zones: tuple[Zone, ...] = index.zones
        self.holes: tuple[Hole, ...] = index.holes
        #: Edge.Cuts as polylines; a closed one repeats its first point.
        self.outline: tuple[tuple[XY, ...], ...] = index.outline
        self._parts = {part.ref: part for part in index.parts}
        # Everything on each net, in one pass over the board (a pass per net is quadratic).
        on: dict[str, tuple[list, list, list, list]] = {name: ([], [], [], []) for name, _netclass in index.nets}
        for slot, items in enumerate((index.pads, index.tracks, index.vias, index.zones)):
            for item in items:
                if item.net in on:
                    on[item.net][slot].append(item)
        self.nets: tuple[Net, ...] = tuple(
            Net(name=name, netclass=netclass, pads=tuple(on[name][0]), tracks=tuple(on[name][1]), vias=tuple(on[name][2]), zones=tuple(on[name][3]))
            for name, netclass in index.nets
        )
        self._nets = {net.name: net for net in self.nets}

    def __repr__(self) -> str:
        return f"BoardView({self.path.name}: {len(self.parts)} parts, {len(self.nets)} nets)"

    @property
    def pads(self) -> tuple[Pad, ...]:
        """Every pad of every part."""
        return self._index.pads

    def part(self, ref: str) -> Part:
        """The part ``ref`` (``"U3"``)."""
        found = self._parts.get(str(ref))
        if found is None:
            close = sorted(difflib.get_close_matches(str(ref), list(self._parts), n=3), key=natural)
            if close:
                hint = f"; did you mean {', '.join(close)}?"
            else:
                refs = sorted(self._parts, key=natural)
                hint = f"; its parts are {', '.join(refs[:40])}" + (f" and {len(refs) - 40} more" if len(refs) > 40 else "")
            raise ValueError(f"{self.path.name} has no part {ref}{hint}")
        return found

    def net(self, name: str) -> Net:
        """The net ``name``, as KiCad shows it (``"TX/RX"``)."""
        found = self._nets.get(str(name))
        if found is None:
            close = sorted(difflib.get_close_matches(str(name), list(self._nets), n=3), key=natural)
            hint = f"; did you mean {', '.join(close)}?" if close else ""
            raise ValueError(f"{self.path.name} has no net {name!r}{hint}")
        return found

    def resolve(self, ref: str):
        """What the reference ``ref`` names: a :class:`Part`, :class:`Pad`, :class:`Net`,
        :class:`Copper` or :class:`Point`. A file before the ``#`` must name this board."""
        answers = self.resolve_all(ref)
        if len(answers) != 1:
            raise ValueError(f"{ref!r} names {len(answers)} things; resolve_all() answers each, in the order written")
        return answers[0]

    def resolve_all(self, ref: str) -> list:
        """Every selector of a reference token (``board.kicad_pcb#U3,C14.2``), each resolved."""
        token = parse_board_token(ref)
        if token is None:
            selector = parse_board_selector(ref)
            if selector is None:
                raise ValueError(f"not a board reference: {ref!r}; {_FORMS}")
            path, selectors = "", (selector,)
        else:
            path, selectors = token.path, token.selectors
        if path and not ref_prefix_names(path, str(self.path)):
            raise ValueError(f"reference names {path!r}, but this board is {str(self.path)!r}")
        if not selectors:
            raise ValueError(f"{ref!r} names the whole board; name a part, pad, net, copper or point in it")
        return [self._answer(selector) for selector in selectors]

    def _answer(self, selector: BoardSelector):
        if selector.kind == "part":
            return self.part(selector.ref)
        if selector.kind == "pad":
            return self.part(selector.ref).pad(selector.pad)
        if selector.kind == "net":
            return self.net(selector.net)
        if selector.kind == "copper":
            return self.copper(selector.net, *selector.at)
        return self.at(*selector.at)

    def copper(self, net: str, x: float, y: float) -> Copper:
        """``net``'s pads, tracks, vias and filled pours at (x, y), nearest first."""
        found = self.net(net)
        point = (float(x), float(y))
        near = []
        for item in (*found.pads, *found.tracks, *found.vias, *found.zones):
            distance = _reach(item, point)
            if distance <= COPPER_TOLERANCE:
                near.append((distance, item))
        if not near:
            candidates = [(_reach(item, point), item) for item in (*found.pads, *found.tracks, *found.vias, *found.zones)]
            candidates = [entry for entry in candidates if math.isfinite(entry[0])]
            if not candidates:
                raise ValueError(f"net {found.name!r} has no copper on {self.path.name}")
            distance, item = min(candidates, key=lambda entry: entry[0])
            raise ValueError(
                f"net {found.name!r} has no copper at {format_xy(point)}: the nearest is {item!r}, {distance:.3g} mm away"
            )
        near.sort(key=lambda entry: entry[0])
        return Copper(net=found, at=point, items=tuple(item for _distance, item in near))

    def at(self, x: float, y: float) -> Point:
        """What is at (x, y): the parts whose outline holds it, pads, copper and holes there."""
        point = (float(x), float(y))
        closed = [line for line in self.outline if _closed(line)]
        crossings = sum(inside(point, line[:-1]) for line in closed)
        pads = tuple(pad for part in self.parts for pad in part.pads if polygon_distance(point, pad.polygon) == 0)
        copper = tuple(item for item in (*self.tracks, *self.vias, *self.zones) if _reach(item, point) == 0)
        holes = tuple(hole for hole in self.holes if math.hypot(point[0] - hole.at[0], point[1] - hole.at[1]) <= hole.diameter / 2)
        parts = tuple(part for part in self.parts if len(part.outline) >= 3 and inside(point, part.outline))
        return Point(at=point, on_board=crossings % 2 == 1, parts=parts, pads=pads, copper=copper, holes=holes)


def _reach(item, point: XY) -> float:
    """How far ``point`` is from the copper of ``item``: 0 on it."""
    if isinstance(item, Pad):
        return polygon_distance(point, item.polygon)
    if isinstance(item, Track):
        return max(0.0, polyline_distance(point, item.points) - item.width / 2)
    if isinstance(item, Via):
        return max(0.0, math.hypot(point[0] - item.at[0], point[1] - item.at[1]) - item.diameter / 2)
    if isinstance(item, Zone):
        return min((polygon_distance(point, fill) for fill in item.fills), default=math.inf)
    return math.inf


def read_board(path: Path | str) -> BoardView:
    """The KiCad board at ``path`` (a ``.kicad_pcb``; any board KiCad opens) for board references.

    Everything is in KiCad's frame: millimetres, y down, the frame a script's
    ``Vector2.from_xy_mm`` takes. Reads the file and the ``.kicad_pro`` beside it (for net
    classes); runs nothing.
    """
    board = Path(path).expanduser()
    return BoardView(board.resolve(), read_board_index(board))


def read_board_index(path: Path | str) -> BoardIndex:
    """The index of the KiCad board at ``path``, in KiCad's frame (:func:`read_board`'s)."""
    board = Path(path).expanduser()
    if board.suffix.lower() != ".kicad_pcb":
        raise ValueError(f"{board.name} is not a KiCad board (.kicad_pcb)")
    if not board.is_file():
        raise FileNotFoundError(f"{board} does not exist")
    try:
        text = board.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise ValueError(f"{board.name} is not a readable KiCad board: it is not UTF-8 text") from None
    try:
        return read_index(text, project=board.with_suffix(".kicad_pro"))
    except ValueError as error:
        raise ValueError(f"{board.name} is {error}") from None
