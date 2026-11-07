"""The board as the router sees it: every piece of copper, hole and keep-out, as exact shapes, from its text.

The text is the open board's own (KiPy's ``Board.get_as_string()``, inside the edit), so the router sees what
the block has done to it so far, not the file on disk. It is read with the board readers' shared parts
(``cad.engine.formats.kicad``: the S-expression parser, a footprint's frame, net and layer names, a zone's
outline placed as KiCad places it), and every shape is the item's own (``shapes``): a pad by its shape, size,
corner radius, offset and turn; a track as a segment or an arc of its width; a via as a disc on each layer it
spans. A pad whose padstack draws other shapes on other layers is all of them on every layer (more copper,
never less); a chamfered corner is the square corner (likewise). A copper pour is not read: KiCad refills it round
the new copper, so it is neither an obstacle nor a connection to the router. The outline and the copper graphics and texts
(rare; a footprint's as well as the board's) come from the board index (``read_index``), their arcs as chords
within ``CHORD_TOLERANCE`` and their curves as chords within ``curve_reach``, which the router grows them by.

Millimetres, KiCad's frame (y down), as the file holds them.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence

from cad.engine.formats.kicad import sexpr
from cad.engine.formats.kicad.board_index import (
    FootprintFrame, canonical_copper, copper_layers, expand_copper, footprint_property, item_id, item_layers, layer_of,
    net_of, net_table, points_of, read_index, zone_outline,
)
from cad.engine.formats.kicad.geometry import CHORD_TOLERANCE, bezier_points, rotate

from .shapes import Shape

__all__ = ["BoardCopper", "Graphic", "Keepout", "Pad", "Track", "Via", "read_copper"]

XY = tuple[float, float]


@dataclass(frozen=True)
class Pad:
    """A pad: ``ref`` is ``U1.3`` (its part's reference and its number), ``at`` KiCad's anchor (its hole's centre,
    for a through-hole pad), ``copper`` its copper on each of ``layers`` (a union of shapes), ``inner`` where a
    track may end and be in its copper on every layer, ``hole`` its drill, ``clearance`` its own (or its
    footprint's) clearance where it overrides the netclass, ``end`` where a route to it ends: ``at``, or the middle
    of its shape where its copper is offset past its anchor (an SMD pad's ``offset``)."""

    ref: str
    part: str
    number: str
    net: str | None
    layers: tuple[str, ...]
    at: XY
    copper: tuple[Shape, ...]
    inner: tuple[Shape, ...]
    hole: Shape | None = None
    clearance: float | None = None
    end: XY | None = None

    @property
    def anchor(self) -> XY:
        """Where a route to the pad ends: in its copper, on its anchor where that is."""
        return self.end or self.at


@dataclass(frozen=True)
class Track:
    """A track: a segment or an arc of ``width`` on ``layer``; ``shape`` its copper, ``ends`` its two ends."""

    net: str | None
    layer: str
    width: float
    shape: Shape
    ends: tuple[XY, XY]
    id: str | None = None


@dataclass(frozen=True)
class Via:
    """A via: its copper a disc of ``diameter`` on each of ``layers`` (the copper layers it spans), its drill
    ``drill``."""

    net: str | None
    at: XY
    diameter: float
    drill: float
    layers: tuple[str, ...]
    id: str | None = None


@dataclass(frozen=True)
class Graphic:
    """Copper that is neither a pad, a track nor a via: a graphic or a text on a copper layer (``net`` when the
    file gives it one), its arcs' chords grown by ``CHORD_TOLERANCE`` so that it covers what it draws."""

    net: str | None
    layer: str
    shapes: tuple[Shape, ...]


@dataclass(frozen=True)
class Keepout:
    """A rule area (KiCad's keep-out zone), the board's or a footprint's: no track on ``layers`` where
    ``tracks``, no via where ``vias``."""

    layers: tuple[str, ...]
    tracks: bool
    vias: bool
    shape: Shape


@dataclass(frozen=True)
class BoardCopper:
    """What the router reads of a board: its copper layers (front first) and every item it routes round."""

    copper: tuple[str, ...]
    pads: tuple[Pad, ...]
    tracks: tuple[Track, ...]
    vias: tuple[Via, ...]
    graphics: tuple[Graphic, ...]
    keepouts: tuple[Keepout, ...]
    holes: tuple[Shape, ...]  # unplated holes
    outline: tuple[tuple[XY, ...], ...]  # closed rings: the edge, and any cutout
    open_outline: tuple[tuple[XY, ...], ...]  # Edge.Cuts pieces that close on nothing

    def pad(self, ref: str) -> Pad:
        """The pad ``U1.3`` (the first of several sharing that number)."""
        for pad in self.pads:
            if pad.ref == ref:
                return pad
        part, _, number = ref.rpartition(".")
        numbers = sorted({pad.number for pad in self.pads if pad.part == part})
        if not numbers:
            raise ValueError(f"no part {part!r} on the board" if part else f"{ref!r} names no pad: a pad is PART.NUMBER (U1.3)")
        raise ValueError(f"{part} has no pad {number!r}; its pads are {', '.join(numbers)}")


# --- pads ----------------------------------------------------------------------------------------------------


def _local(spec: list) -> dict[str, Any]:
    """A pad's shape fields (its own, or one padstack layer's): shape, size, offset, corner ratios."""
    shape = None
    for atom in spec[1:4]:
        if isinstance(atom, sexpr.Sym) and str(atom) in ("circle", "rect", "oval", "trapezoid", "roundrect", "custom",
                                                         "chamfered_rect"):
            shape = str(atom)
    named = sexpr.value(spec, "shape")
    if named is not None:
        shape = str(named)
    size = sexpr.pair(sexpr.find(spec, "size"), (0.0, 0.0))
    drill = sexpr.find(spec, "drill")
    offset = sexpr.pair(sexpr.find(drill, "offset"), None) if drill is not None else None
    offset = offset or sexpr.pair(sexpr.find(spec, "offset"), (0.0, 0.0))
    return {
        "shape": shape or "rect",
        "size": (abs(size[0]), abs(size[1])),
        "offset": offset,
        "rratio": sexpr.number(sexpr.value(spec, "roundrect_rratio"), 0.0),
        "chamfer": sexpr.number(sexpr.value(spec, "chamfer_ratio"), 0.0),
        "corners": tuple(str(atom) for atom in (sexpr.find(spec, "chamfer") or [])[1:]),
        "delta": sexpr.pair(sexpr.find(spec, "rect_delta"), (0.0, 0.0)),
    }


def _rect_core(hw: float, hh: float, radius: float) -> Shape:
    """The rectangle of half sizes ``hw`` x ``hh``, its corners rounded by ``radius``: the smaller rectangle inside
    the corners grown by the radius (a segment or a point where that rectangle is flat)."""
    radius = max(0.0, min(radius, hw, hh))
    iw, ih = hw - radius, hh - radius
    if iw <= 1e-9 and ih <= 1e-9:
        return Shape.point(0.0, 0.0, radius)
    if ih <= 1e-9:
        return Shape.segment((-iw, 0.0), (iw, 0.0), radius)
    if iw <= 1e-9:
        return Shape.segment((0.0, -ih), (0.0, ih), radius)
    return Shape.polygon(((-iw, -ih), (iw, -ih), (iw, ih), (-iw, ih)), radius)


def curve_reach(points: Sequence[XY]) -> float:
    """How far a cubic Bezier strays from its chords, sampled at even steps of its parameter (``points``, as
    ``bezier_points`` samples it): each chord is within h^2/8 |B''| of the curve, and a cubic's second difference
    is h^2 B'' exactly, which is linear along the curve, so its largest is at an end."""
    if len(points) < 4:
        return 0.0
    second = [(a[0] - 2 * b[0] + c[0], a[1] - 2 * b[1] + c[1]) for a, b, c in zip(points, points[1:], points[2:])]
    first, step = second[0], (second[1][0] - second[0][0], second[1][1] - second[0][1])
    ends = ((first[0] - step[0], first[1] - step[1]),
            (first[0] + (len(points) - 2) * step[0], first[1] + (len(points) - 2) * step[1]))
    return max(math.hypot(*end) for end in ends) / 8


#: A custom pad's primitives that draw no copper: KiCad's proxies, its number's box and its thermal spoke's
#: direction.
_PROXIES = ("gr_bbox", "gr_vector")


def _primitive(node: list) -> list[Shape]:
    """One of a custom pad's primitives, in the pad's frame, grown by its stroke: a polygon, a rectangle and a
    circle are filled (KiCad fills a custom pad's primitives), a line, an arc and a curve are strokes. A primitive
    it does not know is a ``ValueError``: copper the router would not see."""
    head = sexpr.head(node) or ""
    reach = sexpr.number(sexpr.value(node, "width"), 0.0) / 2
    stroke = sexpr.find(node, "stroke")
    if stroke is not None:
        reach = sexpr.number(sexpr.value(stroke, "width"), 0.0) / 2
    if head == "gr_poly":
        points = points_of(sexpr.find(node, "pts"), CHORD_TOLERANCE)
        return [Shape.polygon(points, reach + CHORD_TOLERANCE)] if points else []
    if head == "gr_curve":
        points = bezier_points(points_of(sexpr.find(node, "pts")))
        grown = reach + curve_reach(points)
        return [Shape.segment(a, b, grown) for a, b in zip(points, points[1:])]
    if head in _PROXIES:
        return []
    if head in ("gr_line", "gr_rect", "gr_arc", "gr_circle"):
        start, end = sexpr.pair(sexpr.find(node, "start")), sexpr.pair(sexpr.find(node, "end"))
        if head == "gr_line" and start and end:
            return [Shape.segment(start, end, reach)]
        if head == "gr_rect" and start and end:
            return [Shape.polygon((start, (end[0], start[1]), end, (start[0], end[1])), reach)]
        if head == "gr_arc":
            mid = sexpr.pair(sexpr.find(node, "mid"))
            return [Shape.arc_through(start, mid, end, reach)] if start and mid and end else []
        center = sexpr.pair(sexpr.find(node, "center"))
        if head == "gr_circle" and center and end:
            return [Shape.point(center[0], center[1], math.hypot(end[0] - center[0], end[1] - center[1]) + reach)]
        return []
    raise ValueError(f"its primitive {head}" if head else f"its primitive {node!r}")


def _shapes_of(fields: dict[str, Any], node: list) -> tuple[list[Shape], list[Shape]]:
    """A pad's copper and the part of it a track may end in, in the pad's own frame (before its offset and turn):
    for a chamfered pad, the copper is its square corners and the inside its rectangle short of the chamfers."""
    shape, (width, height) = fields["shape"], fields["size"]
    hw, hh = width / 2, height / 2
    if shape == "circle":
        core = Shape.point(0.0, 0.0, hw)
        return [core], [core]
    if shape == "oval":
        core = _rect_core(hw, hh, min(hw, hh))
        return [core], [core]
    if shape == "trapezoid":
        dx, dy = fields["delta"][0] / 2, fields["delta"][1] / 2
        core = Shape.polygon([(-hw - dy, hh + dx), (hw + dy, hh - dx), (hw - dy, -hh + dx), (-hw + dy, -hh - dx)])
        return [core], [core]
    if shape in ("rect", "roundrect", "chamfered_rect"):
        radius = fields["rratio"] * min(width, height) if shape == "roundrect" else 0.0
        core = _rect_core(hw, hh, radius)
        if fields["corners"] and fields["chamfer"] > 0:
            cut = fields["chamfer"] * min(width, height)
            return [core], [_rect_core(max(hw - cut, 0.0), max(hh - cut, 0.0), 0.0)]
        return [core], [core]
    if shape == "custom":
        options = sexpr.find(node, "options")
        anchor = str(sexpr.value(options, "anchor") or "circle") if options is not None else "circle"
        core = Shape.point(0.0, 0.0, hw) if anchor == "circle" else _rect_core(hw, hh, 0.0)
        drawn = [piece for primitive in (sexpr.find(node, "primitives") or [])[1:] if isinstance(primitive, list)
                 for piece in _primitive(primitive)]
        return [core, *drawn], [core]
    core = _rect_core(hw, hh, 0.0)
    return [core], [core]


def _placed(shape: Shape, offset: XY, angle: float, center: XY) -> Shape:
    """``shape``, from a pad's frame onto the board: offset, turned by the pad's (absolute) angle, moved to it."""

    def place(point: XY) -> XY:
        x, y = rotate(point[0] + offset[0], point[1] + offset[1], angle)
        return center[0] + x, center[1] + y

    if shape.kind == "point":
        x, y = place(shape.points[0])
        return Shape.point(x, y, shape.radius)
    if shape.kind == "segment":
        return Shape.segment(place(shape.points[0]), place(shape.points[1]), shape.radius)
    if shape.kind == "polygon":
        return Shape.polygon([place(point) for point in shape.points], shape.radius)
    assert shape.arc is not None
    (ox, oy), start, end = shape.points
    big, first, sweep = shape.arc
    mid = (ox + big * math.cos(first + sweep / 2), oy + big * math.sin(first + sweep / 2))
    return Shape.arc_through(place(start), place(mid), place(end), shape.radius)


def _hole(node: list, center: XY, angle: float) -> Shape | None:
    """A pad's drilled hole: a circle, or an oval slot along its longer side."""
    drill = sexpr.find(node, "drill")
    if drill is None:
        return None
    sizes = [float(value) for value in drill[1:] if isinstance(value, (int, float))]
    if not sizes or sizes[0] <= 0:
        return None
    oval = any(isinstance(atom, sexpr.Sym) and str(atom) == "oval" for atom in drill[1:])
    if not oval or len(sizes) < 2 or abs(sizes[0] - sizes[1]) < 1e-9:
        return Shape.point(center[0], center[1], min(sizes[:2]) / 2)
    core = _rect_core(sizes[0] / 2, sizes[1] / 2, min(sizes[:2]) / 2)
    return _placed(core, (0.0, 0.0), angle, center)


def _clearance_of(node: list) -> float | None:
    found = sexpr.value(node, "clearance")
    return float(found) if isinstance(found, (int, float)) and not isinstance(found, bool) and found > 0 else None


def _read_pads(footprint: list, table, copper: Sequence[str]) -> tuple[list[Pad], list[Shape]]:
    frame = FootprintFrame(footprint)
    ref = footprint_property(footprint, "Reference") or ""
    own = _clearance_of(footprint)
    pads: list[Pad] = []
    holes: list[Shape] = []
    for node in sexpr.find_all(footprint, "pad"):
        kind = str(node[2]) if len(node) > 2 else ""
        at = sexpr.find(node, "at")
        center = frame.place(sexpr.pair(at, (0.0, 0.0)))
        angle = sexpr.number(at[3]) if at is not None and len(at) > 3 else 0.0
        hole = _hole(node, center, angle)
        layers = tuple(expand_copper(item_layers(node), copper))
        if kind == "np_thru_hole":
            if hole is not None:
                holes.append(hole)
            continue
        if not layers:
            continue  # paste or mask only: no copper
        fields = _local(node)
        number = str(node[1]) if len(node) > 1 else ""
        try:
            made, inner = _shapes_of(fields, node)
            for spec in sexpr.find_all(sexpr.find(node, "padstack") or [], "layer"):  # other layers' shapes: all, everywhere
                made += _shapes_of(_local(spec), spec)[0]
        except ValueError as error:
            raise ValueError(f"route cannot see all the copper of pad {ref or 'of a part'}.{number}: {error} is no shape "
                             "it reads, so it routes nothing on this board") from None
        offset = fields["offset"]
        inside = tuple(_placed(shape, offset, angle, center) for shape in inner)
        middle = _placed(Shape.point(0.0, 0.0, 0.0), offset, angle, center).points[0]
        pads.append(Pad(
            ref=f"{ref}.{number}" if ref and number else "", part=ref, number=number, net=net_of(node, table),
            layers=layers, at=center,
            copper=tuple(_placed(shape, offset, angle, center) for shape in made),
            inner=inside, hole=hole if kind == "thru_hole" else None, clearance=_clearance_of(node) or own,
            end=center if any(shape.contains(*center) for shape in inside) else middle,
        ))
    return pads, holes


# --- the rest of the copper ------------------------------------------------------------------------------------


def _span(layers: Sequence[str], kind: str, copper: Sequence[str]) -> tuple[str, ...]:
    """The copper layers a via joins: all of them for a through via, those between its two for the others."""
    named = expand_copper(layers, copper)
    if kind == "through" or len(named) < 2 or not all(layer in copper for layer in named[:2]):
        return tuple(copper)
    a, b = sorted(copper.index(layer) for layer in named[:2])
    return tuple(copper[a:b + 1])


def _keepout(node: list, copper: Sequence[str], frame: FootprintFrame | None) -> Keepout | None:
    rules = sexpr.find(node, "keepout")
    if rules is None:
        return None

    def banned(name: str) -> bool:
        return str(sexpr.value(rules, name, "allowed")) == "not_allowed"

    outline = zone_outline(node, frame if frame is not None and frame.zones_placed else None)
    layers = tuple(expand_copper(item_layers(node), copper))
    if len(outline) < 3 or not layers or not (banned("tracks") or banned("vias")):
        return None
    return Keepout(layers, banned("tracks"), banned("vias"), Shape.polygon(outline))


def _drawn(points: Sequence[XY], closed: bool, filled: bool, reach: float) -> tuple[Shape, ...]:
    if filled and closed and len(points) >= 3:
        return (Shape.polygon(points, reach),)
    ring = list(points) + ([points[0]] if closed and len(points) > 2 else [])
    return tuple(Shape.segment(a, b, reach) for a, b in zip(ring, ring[1:]))


def read_copper(text: str | list) -> BoardCopper:
    """The board ``text`` (a ``.kicad_pcb``'s, or its parsed tree), as the router sees it."""
    tree = sexpr.parse(text) if isinstance(text, str) else text
    if sexpr.head(tree) != "kicad_pcb":
        raise ValueError("not a KiCad board: a .kicad_pcb starts with (kicad_pcb ...)")
    tree = canonical_copper(tree)
    table = net_table(tree)
    copper = tuple(copper_layers(tree))
    pads: list[Pad] = []
    holes: list[Shape] = []
    tracks: list[Track] = []
    vias: list[Via] = []
    keepouts: list[Keepout] = []
    for node in tree[1:]:
        head = sexpr.head(node)
        if head in ("footprint", "module"):
            found, unplated = _read_pads(node, table, copper)
            pads += found
            holes += unplated
            frame = FootprintFrame(node)
            for zone in sexpr.find_all(node, "zone"):
                keepout = _keepout(zone, copper, frame)
                if keepout is not None:
                    keepouts.append(keepout)
        elif head == "segment":
            start, end = sexpr.pair(sexpr.find(node, "start")), sexpr.pair(sexpr.find(node, "end"))
            layer, width = layer_of(node), sexpr.number(sexpr.value(node, "width"))
            if start and end and layer in copper and width > 0:
                tracks.append(Track(net_of(node, table), layer, width, Shape.segment(start, end, width / 2), (start, end),
                                    item_id(node)))
        elif head == "arc":
            start, mid, end = (sexpr.pair(sexpr.find(node, key)) for key in ("start", "mid", "end"))
            layer, width = layer_of(node), sexpr.number(sexpr.value(node, "width"))
            if start and mid and end and layer in copper and width > 0:
                tracks.append(Track(net_of(node, table), layer, width, Shape.arc_through(start, mid, end, width / 2),
                                    (start, end), item_id(node)))
        elif head == "via":
            at = sexpr.pair(sexpr.find(node, "at"))
            if at is None:
                continue
            kind = next((str(atom) for atom in node[1:] if isinstance(atom, sexpr.Sym)
                         and str(atom) in ("blind", "buried", "micro")), "through")
            vias.append(Via(net_of(node, table), at, sexpr.number(sexpr.value(node, "size")),
                            sexpr.number(sexpr.value(node, "drill")), _span(item_layers(node), kind, copper), item_id(node)))
        elif head == "zone":
            keepout = _keepout(node, copper, None)
            if keepout is not None:
                keepouts.append(keepout)
    index = read_index(tree)
    graphics = [Graphic(shape.net, shape.layer, _drawn(shape.points, shape.closed, shape.filled, shape.width / 2 + (
                        curve_reach(shape.points) if shape.shape == "curve"
                        else CHORD_TOLERANCE if shape.shape in ("arc", "circle", "poly") else 0.0)))
                for shape in index.shapes if shape.layer in copper]
    graphics += [Graphic(None, text.layer, (Shape.polygon(text.polygon),))
                 for text in index.texts if text.layer in copper and len(text.polygon) >= 3]
    rings = tuple(tuple(line) for line in index.outline
                  if len(line) > 3 and math.dist(line[0], line[-1]) <= 0.01)
    open_ = tuple(tuple(line) for line in index.outline if tuple(line) not in rings)
    return BoardCopper(copper, tuple(pads), tuple(tracks), tuple(vias), tuple(graphics), tuple(keepouts),
                       tuple(holes), rings, open_)
