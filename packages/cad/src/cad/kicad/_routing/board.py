"""The board as the router sees it: every piece of copper, hole and keep-out, as exact shapes, from its text.

The text is the open board's own (KiPy's ``Board.get_as_string()``, inside the edit), so the router sees what
the block has done to it so far, not the file on disk. It is read with the board readers' shared parts
(``cad.engine.formats.kicad``: the S-expression parser, a footprint's frame, net and layer names, a zone's
outline placed as KiCad places it), and every shape is the item's own (``shapes``): a pad by its shape, size,
corner radius, offset and turn; a track as a segment or an arc of its width; a via as a disc on each layer it
spans. A pad whose padstack draws other shapes on other layers is all of them on every layer (more copper,
never less), each at its own offset, and a track ends in it inside a disc that lies in its copper on every
layer; a chamfered corner is the square corner (likewise). A copper pour is not read: KiCad refills it round
the new copper, so it is neither an obstacle nor a connection to the router. The outline and the copper graphics
(rare; a footprint's as well as the board's) come from the board index (``read_index``), their arcs as chords
within ``CHORD_TOLERANCE`` and their curves as chords within ``curve_reach``, which the router grows them by. The
texts, text boxes, tables, barcodes and dimensions on a copper layer (a footprint's too) are read here, each as
large as what KiCad draws or larger (see their section): a stroke-font text by KiCad's own font's measured
advances, not the plot's font, a TrueType one by the outline KiCad saved with it.

Millimetres, KiCad's frame (y down), as the file holds them.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence

from cad.engine.formats.kicad import sexpr
from cad.engine.formats.kicad.board_index import _CHAIN as CHAIN  # KiCad's chaining epsilon: an outline closes within it
from cad.engine.formats.kicad.board_index import (
    FootprintFrame, canonical_copper, copper_layers, expand_copper, footprint_property, item_id, item_layers, layer_of,
    net_of, net_table, points_of, read_index, zone_outline,
)
from cad.engine.formats.kicad.board_index import (  # the board readers' own: a text as KiCad shows it
    _footprint_text, _hidden, _read_dimension, _stroke_width, _text_effects,
)
from cad.engine.formats.kicad.geometry import CHORD_TOLERANCE, bezier_points, hull, rotate

from .shapes import Shape, segment_point_distance

__all__ = ["BoardCopper", "Graphic", "Keepout", "Pad", "Track", "Via", "read_copper"]

XY = tuple[float, float]


@dataclass(frozen=True)
class Pad:
    """A pad: ``ref`` is ``U1.3`` (its part's reference and its number), ``at`` KiCad's anchor (its hole's centre,
    for a through-hole pad), ``copper`` its copper on each of ``layers`` (a union of shapes), ``inner`` where a
    track may end and be in its copper on every layer (for a padstack of several shapes, a disc round ``end``
    that lies in each layer's), ``hole`` its drill, ``clearance`` its own (or its footprint's) clearance where it
    overrides the netclass, ``end`` where a route to it ends: ``at``, or the middle of its shape where its copper
    is offset past its anchor (an SMD pad's ``offset``); ``mask`` its solder-mask opening on each outer copper
    layer it has one over, as (layer, how far it reaches past the copper: its expansion)."""

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
    mask: tuple[tuple[str, float], ...] = ()

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
    ``drill``; ``mask`` the outer copper layers KiCad leaves it untented on (a solder-mask opening round it)."""

    net: str | None
    at: XY
    diameter: float
    drill: float
    layers: tuple[str, ...]
    id: str | None = None
    mask: tuple[str, ...] = ()


@dataclass(frozen=True)
class Graphic:
    """Copper that is neither a pad, a track nor a via: a graphic, a text, a text box, a table, a barcode or a
    dimension on a copper layer (``net`` when the file gives it one), as large as what KiCad draws or larger (its
    arcs' chords grown by ``CHORD_TOLERANCE``, a text by its font's measured reach); ``clearance`` what other copper
    keeps from it where DRC holds it to more than its net's (a barcode's visual separation)."""

    net: str | None
    layer: str
    shapes: tuple[Shape, ...]
    clearance: float | None = None


@dataclass(frozen=True)
class Keepout:
    """A rule area (KiCad's keep-out zone), the board's or a footprint's: no track on ``layers`` where
    ``tracks``, no via where ``vias``; ``shape`` its outline, an arc in it as chords within ``CHORD_TOLERANCE``
    grown by that, so that it covers the true arc."""

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
    # The solder mask, as DRC's solder_mask_bridge judges it: an opening of a pad's or an untented via's exposes
    # any copper of another net within it (or within mask_to_copper of it), and two openings closer than
    # mask_min_width are one. New vias are untented on the outer layers ``untented`` names (the board's setting),
    # their opening ``via_mask`` round them (the board's pad-to-mask clearance).
    untented: tuple[str, ...] = ()
    via_mask: float = 0.0
    mask_min_width: float = 0.0
    mask_to_copper: float = 0.0

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
    _, start, end = shape.points
    through = shape.arc[1]  # the point it was drawn through: placed with its ends, the same arc
    return Shape.arc_through(place(start), place(through), place(end), shape.radius)


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


def _margin(node: list) -> float | None:
    found = sexpr.value(node, "solder_mask_margin")
    return float(found) if isinstance(found, (int, float)) and not isinstance(found, bool) else None


def _mask_sides(names: Sequence[str]) -> set[str]:
    """The sides (``F``, ``B``) a pad's layers open the solder mask on: ``F.Mask``, ``B.Mask``, ``*.Mask``."""
    sides = set()
    for name in names:
        side, _, kind = name.partition(".")
        if kind == "Mask":
            sides |= {"F", "B"} if side in ("*", "F&B") else {side}
    return sides


def _read_pads(footprint: list, table, copper: Sequence[str], expansion: float = 0.0) -> tuple[list[Pad], list[Shape]]:
    """A footprint's pads and its unplated holes; ``expansion`` the board's pad-to-mask clearance, a pad's
    solder-mask expansion where neither it nor its footprint gives one (KiCad's order)."""
    frame = FootprintFrame(footprint)
    ref = footprint_property(footprint, "Reference") or ""
    own = _clearance_of(footprint)
    own_margin = _margin(footprint)
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
        name = f"{ref or 'of a part'}.{number}"

        def placed(local: dict[str, Any], shapes: Sequence[Shape]) -> list[Shape]:
            return [_placed(shape, local["offset"], angle, center) for shape in shapes]

        try:
            made, inner = _shapes_of(fields, node)
            copper_shapes, inside = placed(fields, made), placed(fields, inner)
            # The other layers' shapes (KiCad's padstack), each at its own offset (KiCad draws a layer that gives
            # none on the pad's anchor, not at the main layer's offset): all of them on every layer, more copper,
            # never less, and where a track may end on each layer.
            stack: dict[str, list[Shape]] = {}
            for spec in sexpr.find_all(sexpr.find(node, "padstack") or [], "layer"):
                local = _local(spec)
                drawn, within = _shapes_of(local, spec)
                copper_shapes += placed(local, drawn)
                if len(spec) > 1 and isinstance(spec[1], str):
                    stack[spec[1]] = placed(local, within)
        except ValueError as error:
            raise ValueError(f"route cannot see all the copper of pad {name}: {error} is no shape "
                             "it reads, so it routes nothing on this board") from None
        middle = _placed(Shape.point(0.0, 0.0, 0.0), fields["offset"], angle, center).points[0]
        end = center if any(shape.contains(*center) for shape in inside) else middle
        if stack:
            inside, end = _common_inside(name, layers, inside, stack, (center, middle))
        margin = _margin(node)
        margin = margin if margin is not None else own_margin if own_margin is not None else expansion
        sides = _mask_sides(item_layers(node))
        outer = {"F": copper[0], "B": copper[-1]} if copper else {}
        mask = tuple((outer[side], margin) for side in ("F", "B") if side in sides and outer.get(side) in layers)
        pads.append(Pad(
            ref=f"{ref}.{number}" if ref and number else "", part=ref, number=number, net=net_of(node, table),
            layers=layers, at=center, copper=tuple(copper_shapes), inner=tuple(inside),
            hole=hole if kind == "thru_hole" else None, clearance=_clearance_of(node) or own, end=end, mask=mask,
        ))
    return pads, holes


def _depth(shape: Shape, point: XY) -> float:
    """How deep ``point`` lies in ``shape``: the radius of a disc round it inside the shape, the largest for a
    point, a segment or a polygon grown by its radius (an arc, which no pad's inside is, answers 0 at most);
    0 or less outside it."""
    x, y = point
    if shape.kind == "polygon":
        ring = shape.points
        edge = min(segment_point_distance(a[0], a[1], b[0], b[1], x, y) for a, b in zip(ring, ring[1:] + ring[:1]))
        return shape.radius + edge if Shape.polygon(ring).contains(x, y) else shape.radius - edge
    if shape.kind == "point":
        return shape.radius - math.dist(point, shape.points[0])
    if shape.kind == "segment":
        (ax, ay), (bx, by) = shape.points
        return shape.radius - segment_point_distance(ax, ay, bx, by, x, y)
    return -shape.point_distance(x, y)


def _common_inside(name: str, layers: Sequence[str], main: Sequence[Shape], stack: dict[str, list[Shape]],
                   candidates: Sequence[XY]) -> tuple[list[Shape], XY]:
    """Where a track may end in a padstack pad, on whichever of its ``layers`` it lands: a disc round the first of
    ``candidates`` (its anchor, then its main shape's middle) that lies in its copper on every layer, of the least
    over the layers of how deep it lies there (on each layer, the deepest it lies in any of that layer's shapes,
    a lower bound of the disc that fits). ``stack`` is the padstack's own layers: a copper layer's name, or
    ``Inner`` for the inner layers it does not name; any other layer draws the main shape (``main``)."""

    def shapes_on(layer: str) -> list[Shape]:
        if layer in stack:
            return stack[layer]
        if layer not in ("F.Cu", "B.Cu") and "Inner" in stack:
            return stack["Inner"]
        return list(main)

    on = [shapes_on(layer) for layer in layers]
    for point in candidates:
        depth = min(max(_depth(shape, point) for shape in shapes) for shapes in on)
        if depth > 0:
            return [Shape.point(point[0], point[1], depth)], point
    raise ValueError(f"route cannot end a track in pad {name}: no point of its anchor or its shape's middle lies in "
                     f"its copper on every layer its padstack draws ({', '.join(layers)}), so a track could end off "
                     "the copper on one of them; give its layers' shapes a common point (round its anchor) in KiCad's "
                     "pad properties, or route to it by hand")


# --- the rest of the copper ------------------------------------------------------------------------------------


def _span(layers: Sequence[str], kind: str, copper: Sequence[str]) -> tuple[str, ...]:
    """The copper layers a via joins: all of them for a through via, those between its two for the others."""
    named = expand_copper(layers, copper)
    if kind == "through" or len(named) < 2 or not all(layer in copper for layer in named[:2]):
        return tuple(copper)
    a, b = sorted(copper.index(layer) for layer in named[:2])
    return tuple(copper[a:b + 1])


def _tenting(node: list | None) -> dict[str, bool]:
    """The sides a ``(tenting ...)`` names tented or not: ``(tenting (front yes) (back no))`` (KiCad 10), or the
    tented sides listed, ``(tenting front back)``, ``(tenting none)`` (KiCad 9); empty where it says nothing."""
    found = sexpr.find(node, "tenting") if node is not None else None
    if found is None:
        return {}
    sides: dict[str, bool] = {}
    listed = False
    for child in found[1:]:
        if isinstance(child, list) and sexpr.head(child) in ("front", "back"):
            sides[sexpr.head(child)] = len(child) < 2 or str(child[1]) in ("yes", "true")
        elif isinstance(child, sexpr.Sym) and str(child) in ("front", "back", "none"):
            listed = True
            if str(child) != "none":
                sides[str(child)] = True
    if listed:
        sides = {"front": sides.get("front", False), "back": sides.get("back", False)}
    return sides


def _untented(tenting: dict[str, bool], copper: Sequence[str], layers: Sequence[str]) -> tuple[str, ...]:
    """The outer copper layers of ``layers`` a via is untented on, by ``tenting`` (a side it does not name is
    tented: KiCad's default)."""
    if not copper:
        return ()
    sides = (("front", copper[0]), ("back", copper[-1]))
    return tuple(dict.fromkeys(layer for side, layer in sides if not tenting.get(side, True) and layer in layers))


def _keepout(node: list, copper: Sequence[str], frame: FootprintFrame | None) -> Keepout | None:
    rules = sexpr.find(node, "keepout")
    if rules is None:
        return None

    def banned(name: str) -> bool:
        return str(sexpr.value(rules, name, "allowed")) == "not_allowed"

    # An arc in the outline as chords within CHORD_TOLERANCE of it, the keep-out grown by that so that it covers
    # the true arc where it bulges past them (a plain outline is exact as written).
    outline = zone_outline(node, frame if frame is not None and frame.zones_placed else None, CHORD_TOLERANCE)
    arcs = sexpr.find(sexpr.find(sexpr.find(node, "polygon") or [], "pts") or [], "arc") is not None
    layers = tuple(expand_copper(item_layers(node), copper))
    if len(outline) < 3 or not layers or not (banned("tracks") or banned("vias")):
        return None
    return Keepout(layers, banned("tracks"), banned("vias"), Shape.polygon(outline, CHORD_TOLERANCE if arcs else 0.0))


def _drawn(points: Sequence[XY], closed: bool, filled: bool, reach: float) -> tuple[Shape, ...]:
    if filled and closed and len(points) >= 3:
        return (Shape.polygon(points, reach),)
    ring = list(points) + ([points[0]] if closed and len(points) > 2 else [])
    return tuple(Shape.segment(a, b, reach) for a, b in zip(ring, ring[1:]))


# --- texts, text boxes, tables, barcodes and dimensions on a copper layer ------------------------------------
#
# Each is an obstacle as large as what KiCad draws or larger, never smaller: a stroke-font text a box its letters
# lie in (``_letters``), a TrueType one the hull of the outline KiCad saved with it (its render cache), a knockout
# the box KiCad fills round its letters, a text box or a table's cell its box (its border's stroke round it) and
# its text where that may spill past the box, a barcode its symbol and its text, a dimension its lines, its
# arrows and its text.

#: KiCad's stroke font (newstroke), measured with kicode 10.99 (KiCad's own outline of each text,
#: ``get_text_as_shapes``): each character's advance, space to ``~``, in 21sts of the text's width (a whole number
#: each); any other character takes 34, past the widest measured (``Ж`` 32, CJK 31, Latin-1, Greek, kana 26 or
#: less). Its letters lie within a tenth of the width before the pen's start and a quarter after its end (0.05 and
#: 0.19 measured), within 0.45 of the height below the baseline (0.41 measured: a bracket's foot) and above the
#: capitals (0.41: an accented capital, an overbar 0.30), 0.25 for ASCII with no overbar (0.19: a bracket's head).
#: Lines are 1.62 heights apart (1.61 measured); the capitals of
#: one line stand 0.04 heights below a top-justified anchor, centre 0.04 above a centred one and their baseline 0.13
#: above a bottom-justified one; an italic letter leans an eighth of its height above the baseline.
_ADVANCE = (16, 10, 16, 21, 20, 24, 26, 10, 14, 14, 16, 26, 10, 26, 10, 22, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20,
            10, 10, 26, 26, 26, 18, 27, 18, 21, 21, 21, 19, 18, 21, 22, 10, 16, 21, 17, 24, 22, 22, 21, 22, 21, 20, 16,
            22, 18, 24, 20, 18, 20, 14, 14, 14, 12, 16, 8, 19, 19, 18, 19, 18, 12, 19, 19, 10, 10, 17, 11, 28, 19, 19,
            19, 19, 13, 17, 12, 19, 16, 22, 17, 16, 17, 14, 20, 14, 15)
_ADVANCE_OTHER = 34
_BEFORE, _AFTER, _OVER, _OVER_ASCII, _PITCH, _LEAN = 0.1, 0.25, 0.45, 0.25, 1.62, 0.2


def _advance(line: str) -> float:
    """A line's width in KiCad's stroke font, in widths of its text: each character's advance, its markup's
    characters as glyphs too (more, never less)."""
    return sum(_ADVANCE[ord(c) - 32] if 32 <= ord(c) <= 126 else _ADVANCE_OTHER for c in line) / 21


def _font(node: list) -> list:
    effects = sexpr.find(node, "effects")
    return (sexpr.find(effects, "font") if effects is not None else None) or []


def _flag(node: list, name: str) -> bool:
    """``(name yes)``, or the bare atom ``name`` (an older board's)."""
    found = sexpr.find(node, name)
    if found is not None:
        return len(found) < 2 or str(found[1]) in ("yes", "true")
    return any(isinstance(atom, sexpr.Sym) and str(atom) == name for atom in node[1:])


def _knockout(node: list) -> bool:
    """A knockout: KiCad fills a box round the letters and cuts them out of it (``(layer "F.Cu" knockout)`` for a
    text, ``(knockout yes)`` for a text box or a barcode)."""
    layer = sexpr.find(node, "layer")
    return _flag(node, "knockout") or (layer is not None and any(str(atom) == "knockout" for atom in layer[2:]))


def _effects(node: list) -> tuple[tuple[float, float], float, list[str], bool]:
    """A text's size (height, width), stroke, justification and slant, as KiCad draws it: a bold stroke-font text
    with no stroke of its own is a fifth of its width."""
    size, thickness, justify = _text_effects(node)
    font = _font(node)
    if _flag(font, "bold") and sexpr.value(font, "thickness") is None:
        thickness = size[1] / 5
    return size, thickness, justify, _flag(font, "italic")


def _letters(text: str, node: list) -> list[XY]:
    """A box ``text``'s letters lie in, in KiCad's stroke font as ``node``'s effects lay it out, in the text's frame
    (unturned about its anchor): its widest line by the font's advances, its lines by their pitch, each justified as
    KiCad justifies them, with the margins the font's letters keep within (the table's note), its stroke round it."""
    (height, width), thickness, justify, italic = _effects(node)
    lines = text.split("\n")
    wide = max(_advance(line) for line in lines) * width
    tall = height + (len(lines) - 1) * _PITCH * height
    if "left" in justify:
        x0, x1 = -_BEFORE * width, wide + _AFTER * width
    elif "right" in justify:
        x0, x1 = -wide - _BEFORE * width, _AFTER * width
    else:
        x0, x1 = -wide / 2 - _BEFORE * width, wide / 2 + _AFTER * width
    if "mirror" in justify:
        x0, x1 = -x1, -x0
    if "top" in justify:
        y0, y1 = 0.0, tall + 0.05 * height
    elif "bottom" in justify:
        y0, y1 = -tall - 0.15 * height, -0.1 * height
    else:
        y0, y1 = -tall / 2 - 0.05 * height, tall / 2
    lean = _LEAN * height if italic else 0.0
    grow = thickness / 2
    over = (_OVER_ASCII if text.isascii() and "~{" not in text else _OVER) * height
    return _box_of([(x0 - lean - grow, y0 - over - grow), (x1 + lean + grow, y1 + _OVER * height + grow)])


def _turned(points: Sequence[XY], at: XY, angle: float) -> list[XY]:
    """``points``, in a text's frame (unturned about its anchor), on the board: turned as KiCad turns text."""
    radians = math.radians(angle)
    cos, sin = math.cos(radians), math.sin(radians)
    return [(at[0] + x * cos + y * sin, at[1] - x * sin + y * cos) for x, y in points]


def _unturned(points: Sequence[XY], at: XY, angle: float) -> list[XY]:
    radians = math.radians(angle)
    cos, sin = math.cos(radians), math.sin(radians)
    return [((x - at[0]) * cos - (y - at[1]) * sin, (x - at[0]) * sin + (y - at[1]) * cos) for x, y in points]


def _box_of(points: Sequence[XY], grow: float = 0.0) -> list[XY]:
    x0, y0 = min(x for x, _ in points) - grow, min(y for _, y in points) - grow
    x1, y1 = max(x for x, _ in points) + grow, max(y for _, y in points) + grow
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def _cached(node: list) -> list[XY] | None:
    """The points of the outline KiCad saved with a TrueType text (its ``render_cache``, on the board), or None."""
    cache = sexpr.find(node, "render_cache")
    if cache is None:
        return None
    return [point for polygon in sexpr.find_all(cache, "polygon") for pts in sexpr.find_all(polygon, "pts")
            for point in points_of(pts)]


def _truetype(node: list, text: str, layer: str) -> list[XY]:
    """A TrueType text's outline as KiCad drew it; a ``ValueError`` where the board holds none."""
    points = _cached(node)
    if not points:
        face = sexpr.value(_font(node), "face")
        raise ValueError(f"route cannot see the copper of the text {text!r} on {layer}: its font is {face!r}, a "
                         "TrueType face, and the board holds no outline of it (KiCad saves one with the text, its "
                         "render cache); open and save the board in KiCad, or give the text KiCad's own font")
    return points


def _text_copper(node: list, text: str, at: XY, angle: float, layer: str, upright: bool = False) -> tuple[Shape, ...]:
    """A text's copper on ``layer``, the text ``text`` anchored ``at`` and turned ``angle`` as KiCad places it; an
    ``upright`` one (a footprint's, which KiCad turns half round where it would read upside down, about its
    anchor, measured) at both angles."""
    if upright and sexpr.value(_font(node), "face") is None and math.cos(math.radians(angle)) < 1e-9:
        return (*_text_copper(node, text, at, angle, layer), *_text_copper(node, text, at, angle - 180, layer))
    size, thickness, _, _ = _effects(node)
    if sexpr.value(_font(node), "face") is not None:  # TrueType: the outline KiCad drew, on the board
        drawn = _truetype(node, text, layer)
        cache = sexpr.find(node, "render_cache")
        if len(cache) > 2 and isinstance(cache[2], (int, float)):
            angle = float(cache[2])
        letters = _unturned(drawn, at, angle)
    else:
        letters = _letters(text, node)
    if not letters:
        return ()
    if _knockout(node):
        # KiCad's knockout: the letters' box in their frame grown by max(stroke / 2, height / 9)
        # (GetKnockoutTextMargin), filled, square cornered.
        return (Shape.polygon(_turned(_box_of(letters, max(thickness / 2, size[0] / 9)), at, angle)),)
    if sexpr.value(_font(node), "face") is not None:
        return (Shape.polygon(hull(_turned(letters, at, angle))),)
    return (Shape.polygon(_turned(letters, at, angle)),)


def _text_box_copper(node: list, frame: FootprintFrame | None, stroke: float, layer: str) -> tuple[Shape, ...]:
    """A text box's (or a table cell's) copper: its box, filled, grown by half of ``stroke`` (its border's, drawn
    or not), and its text where that may lie past the box. A TrueType text is the outline KiCad saved. A
    stroke-font text is laid out as KiCad lays out a text box's (``GetDrawPos``: from the margin of the side it is
    justified to, or the middle, in the box's own frame, along its text); one whose every line is no wider than the
    box inside its margins is not wrapped, and is the box and its letters' box (``_letters``) there. One wider
    KiCad wraps, and it may spill past the box however it is wrapped: the box is grown along and across its text by
    the most its letters can reach from their anchor (the widest and tallest of the text unwrapped and of one word
    a line), the anchor in the box (or as far past it as a margin is wider than the box)."""
    pts = sexpr.find(node, "pts")
    if pts is not None:
        corners = points_of(pts)[:4]
    else:
        start, end = sexpr.pair(sexpr.find(node, "start")), sexpr.pair(sexpr.find(node, "end"))
        if start is None or end is None:
            return ()
        (x0, x1), (y0, y1) = sorted((start[0], end[0])), sorted((start[1], end[1]))
        corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    if len(corners) < 4:
        return ()
    if frame is not None:
        corners = [frame.place(point) for point in corners]
    box = Shape.polygon(corners, stroke / 2)
    text = node[1] if len(node) > 1 and isinstance(node[1], str) else ""
    if not text.strip():
        return (box,)
    if sexpr.value(_font(node), "face") is not None:
        return (box, Shape.polygon(hull(_truetype(node, text, layer))))
    # The text's frame: x along it, y down across it, from where the box's corners are least on both. The text
    # is turned by the box's own angle (in a footprint as well: KiCad's is absolute, as a footprint text's is,
    # measured), so a box a turned footprint holds may not be square to it: then the box is its bounding box in
    # the text's frame, and the text may lie anywhere in it.
    angle = sexpr.number(sexpr.value(node, "angle"), 0.0)
    u, v = rotate(1.0, 0.0, angle), rotate(0.0, 1.0, angle)
    along = [c[0] * u[0] + c[1] * u[1] for c in corners]
    down_ = [c[0] * v[0] + c[1] * v[1] for c in corners]
    u0, v0 = min(along), min(down_)
    across, down = max(along) - u0, max(down_) - v0

    def board_point(x: float, y: float) -> XY:
        return (u0 + x) * u[0] + (v0 + y) * v[0], (u0 + x) * u[1] + (v0 + y) * v[1]

    square = all(min(abs(a - u0), abs(a - u0 - across)) < 1e-6 and min(abs(b - v0), abs(b - v0 - down)) < 1e-6
                 for a, b in zip(along, down_))
    if not square:
        box = Shape.polygon([board_point(x, y) for x, y in ((0, 0), (across, 0), (across, down), (0, down))], stroke / 2)

    margins = [abs(float(value)) for value in (sexpr.find(node, "margins") or [])[1:] if isinstance(value, (int, float))]
    left, top, right, bottom = (margins + [0.0] * 4)[:4]
    (_, wide), _, justify, _ = _effects(node)
    ax = left if "left" in justify else across - right if "right" in justify else across / 2
    ay = top if "top" in justify else down - bottom if "bottom" in justify else down / 2
    letters = [(ax + x, ay + y) for x, y in _letters(text, node)]
    if square and max(_advance(line) for line in text.split("\n")) * wide <= across - left - right:  # not wrapped
        (x0, y0), (x1, y1) = letters[0], letters[2]
        if 0 <= x0 and x1 <= across and 0 <= y0 and y1 <= down:
            return (box,)
        return (box, Shape.polygon([board_point(x, y) for x, y in letters]))
    words = _letters("\n".join(text.split()), node)
    reach = (max(letters[1][0] - letters[0][0], letters[2][1] - letters[0][1], words[1][0] - words[0][0],
                 words[2][1] - words[0][1]) + max([0.0] + [margin - min(across, down) for margin in margins]))
    grown = [(-reach, -reach), (across + reach, -reach), (across + reach, down + reach), (-reach, down + reach)]
    return (Shape.polygon([board_point(x, y) for x, y in grown], stroke / 2),)


def _table_copper(node: list, frame: FootprintFrame | None, copper: Sequence[str]) -> list[Graphic]:
    """A table's cells, each a text box grown by half its widest border or separator stroke."""
    strokes = [sexpr.number(sexpr.value(sexpr.find(part, "stroke") or [], "width"), 0.0)
               for part in (sexpr.find(node, "border"), sexpr.find(node, "separators")) if part is not None]
    stroke = max(strokes + [0.0])
    own = layer_of(node)
    found = []
    for cell in sexpr.find_all(sexpr.find(node, "cells") or [], "table_cell"):
        layer = layer_of(cell) or own
        if layer in copper:
            found.append(Graphic(None, layer, _text_box_copper(cell, frame, stroke, layer)))
    return found


#: A barcode's text, below its symbol (KiCad 10.99, measured with its bounding box): of the text height, centred,
#: its foot 1 mm + 1.125 text heights below the symbol; the router takes 1 mm + 1.25 text heights, and the text's
#: advance a quarter of a text height wider. A knockout fills a box 0.4 mm round both.
_BARCODE_GAP, _BARCODE_TEXT, _BARCODE_KNOCKOUT = 1.0, 1.25, 0.4
#: What KiCad's DRC holds other copper to from a barcode, whatever its net's clearance ("barcode visual
#: separation", a default constraint of 1 mm, measured).
_BARCODE_SEPARATION = 1.0


def _barcode_copper(node: list, frame: FootprintFrame | None) -> tuple[Shape, ...]:
    """A barcode's copper: its symbol fills ``size`` round its anchor, its text (unless hidden) below it, turned
    by its angle; in a footprint, the disc round its anchor that holds that box however it is turned."""
    at = sexpr.find(node, "at")
    width, height = sexpr.pair(sexpr.find(node, "size"), (0.0, 0.0))
    if at is None or width <= 0 or height <= 0:
        return ()
    center, angle = sexpr.pair(at, (0.0, 0.0)), sexpr.number(at[3]) if len(at) > 3 else 0.0
    half, top, foot = width / 2, -height / 2, height / 2
    text = sexpr.value(node, "text")
    size = sexpr.number(sexpr.value(node, "text_height"), 0.0)
    if isinstance(text, str) and text.strip() and size > 0 and not _flag(node, "hide"):
        half = max(half, _advance(text) * size / 2 + size / 4)
        foot = height / 2 + _BARCODE_GAP + _BARCODE_TEXT * size
    grow = _BARCODE_KNOCKOUT if _flag(node, "knockout") else 0.0
    box = [(-half - grow, top - grow), (half + grow, top - grow), (half + grow, foot + grow), (-half - grow, foot + grow)]
    if frame is not None:  # KiCad 10.99's DRC takes its position as the board's, not the footprint's (measured): both
        reach = max(math.hypot(x, y) for x, y in box)
        return tuple(Shape.point(x, y, reach) for x, y in (frame.place(center), center))
    return (Shape.polygon([(center[0] + x, center[1] + y) for x, y in (rotate(px, py, angle) for px, py in box)]),)


def _dimension_copper(node: list, layer: str) -> tuple[Shape, ...]:
    """A dimension's copper (on the board's frame, a footprint's too): its lines at its stroke, a disc of twice its
    arrow's length (or its extension line's overshoot) round each line's end, a leader on to its text, and
    its text, in a frame (a box or a circle) where it has one."""
    found = _read_dimension(node, None)
    if found is None:
        return ()
    style = sexpr.find(node, "style") or []
    stroke = sexpr.number(sexpr.value(style, "thickness"), 0.0)
    # An arrow drawn inward stands outside the crossbar's end, twice its length past it (measured).
    tip = max(2 * sexpr.number(sexpr.value(style, "arrow_length"), 0.0),
              sexpr.number(sexpr.value(style, "extension_height"), 0.0))
    lines = list(found.lines)
    shown = sexpr.find(node, "gr_text")
    at = sexpr.pair(sexpr.find(shown, "at")) if shown is not None else None
    if lines and at is not None and found.type in ("leader", "radial"):
        (sx, sy), (ex, ey) = lines[0]
        if found.type == "radial":  # the leader stands out from the arrow's point, then turns to the text
            length, run = sexpr.number(sexpr.value(node, "leader_length"), 0.0), math.hypot(ex - sx, ey - sy)
            if run > 0 and length > 0:
                knee = (ex + (ex - sx) / run * length, ey + (ey - sy) / run * length)
                lines.append(((ex, ey), knee))
                ex, ey = knee
        lines.append(((ex, ey), at))
    shapes: list[Shape] = [Shape.segment(a, b, stroke / 2) for a, b in lines]
    shapes += [Shape.point(x, y, tip + stroke / 2) for line in lines for x, y in line]
    if shown is not None and at is not None and len(shown) > 1 and isinstance(shown[1], str) and shown[1].strip():
        angle = sexpr.number(sexpr.find(shown, "at")[3]) if len(sexpr.find(shown, "at")) > 3 else 0.0
        text = _text_copper(shown, shown[1], at, angle, layer)
        shapes += text
        frame = sexpr.number(sexpr.value(style, "text_frame"), 0.0)
        if frame and text:
            size, thickness, _, _ = _effects(shown)
            margin = max(size) + stroke + thickness
            corners = [point for shape in text for point in (shape.points if shape.kind == "polygon" else [])]
            box = _box_of(_unturned(corners, at, angle), margin)
            if frame == 2:  # a circle
                shapes.append(Shape.point(at[0], at[1], max(math.hypot(x, y) for x, y in box) + stroke / 2))
            else:
                shapes.append(Shape.polygon(_turned(box, at, angle), stroke / 2))
    return tuple(shapes)


def _drawn_copper(tree: list, copper: Sequence[str]) -> list[Graphic]:
    """Every text, text box, table, barcode and dimension on a copper layer, the board's and the footprints'
    (their fields and texts with ``${REFERENCE}`` and its kin substituted, as KiCad shows them); a hidden text
    draws none."""
    found: list[Graphic] = []

    def drawn(node: list, frame: FootprintFrame | None, text: Any = None) -> None:
        head = sexpr.head(node) or ""
        layer = layer_of(node)
        if head == "table":
            found.extend(_table_copper(node, frame, copper))
            return
        if layer not in copper:
            return
        shapes: tuple[Shape, ...] = ()
        if text is not None:
            shapes = _text_copper(node, text.text, text.at, text.angle, layer, upright=True)
        elif head == "gr_text":
            at = sexpr.find(node, "at")
            if len(node) > 1 and isinstance(node[1], str) and node[1].strip() and not _hidden(node) and at is not None:
                shapes = _text_copper(node, node[1], sexpr.pair(at, (0.0, 0.0)), sexpr.number(at[3]) if len(at) > 3 else 0.0,
                                      layer)
        elif head in ("gr_text_box", "fp_text_box"):
            if not _hidden(node):
                shapes = _text_box_copper(node, frame, _stroke_width(node), layer)
        elif head == "barcode":
            shapes = _barcode_copper(node, frame)
            if shapes:
                found.append(Graphic(None, layer, shapes, _BARCODE_SEPARATION))
            return
        elif head in ("dimension", "gr_dimension"):
            shapes = _dimension_copper(node, layer)
        if shapes:
            found.append(Graphic(None, layer, shapes))

    for node in tree[1:]:
        head = sexpr.head(node)
        if head not in ("footprint", "module"):
            drawn(node, None)
            continue
        frame = FootprintFrame(node)
        ref, value = footprint_property(node, "Reference") or "", footprint_property(node, "Value") or ""
        shown = {str(item[1]): str(item[2]) for item in sexpr.find_all(node, "property") if len(item) >= 3}
        for child in node[2:]:
            if not isinstance(child, list):
                continue
            if sexpr.head(child) in ("property", "fp_text"):
                text = _footprint_text(child, frame, ref, value, shown)
                if text is not None:
                    drawn(child, frame, text)
            elif sexpr.head(child) in ("fp_text_box", "table", "barcode", "dimension", "gr_dimension"):
                drawn(child, frame)
    return found


def read_copper(text: str | list, *, mask_to_copper: float = 0.0) -> BoardCopper:
    """The board ``text`` (a ``.kicad_pcb``'s, or its parsed tree), as the router sees it. ``mask_to_copper`` is
    the board's solder-mask-to-copper clearance (a rule of its project's, which the text does not hold: KiPy's
    ``get_design_rules()``; KiCad's default 0)."""
    tree = sexpr.parse(text) if isinstance(text, str) else text
    if sexpr.head(tree) != "kicad_pcb":
        raise ValueError("not a KiCad board: a .kicad_pcb starts with (kicad_pcb ...)")
    tree = canonical_copper(tree)
    table = net_table(tree)
    copper = tuple(copper_layers(tree))
    setup = sexpr.find(tree, "setup")
    expansion = sexpr.number(sexpr.value(setup, "pad_to_mask_clearance"), 0.0) if setup is not None else 0.0
    min_width = sexpr.number(sexpr.value(setup, "solder_mask_min_width"), 0.0) if setup is not None else 0.0
    tenting = _tenting(setup)
    pads: list[Pad] = []
    holes: list[Shape] = []
    tracks: list[Track] = []
    vias: list[Via] = []
    keepouts: list[Keepout] = []
    for node in tree[1:]:
        head = sexpr.head(node)
        if head in ("footprint", "module"):
            found, unplated = _read_pads(node, table, copper, expansion)
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
            span = _span(item_layers(node), kind, copper)
            vias.append(Via(net_of(node, table), at, sexpr.number(sexpr.value(node, "size")),
                            sexpr.number(sexpr.value(node, "drill")), span, item_id(node),
                            _untented({**tenting, **_tenting(node)}, copper, span)))
        elif head == "zone":
            keepout = _keepout(node, copper, None)
            if keepout is not None:
                keepouts.append(keepout)
    index = read_index(tree)
    graphics = [Graphic(shape.net, shape.layer, _drawn(shape.points, shape.closed, shape.filled, shape.width / 2 + (
                        curve_reach(shape.points) if shape.shape == "curve"
                        else CHORD_TOLERANCE if shape.shape in ("arc", "circle", "poly") else 0.0)))
                for shape in index.shapes if shape.layer in copper]
    graphics += _drawn_copper(tree, copper)
    rings = tuple(tuple(line) for line in index.outline
                  if len(line) > 3 and math.dist(line[0], line[-1]) <= CHAIN)
    open_ = tuple(tuple(line) for line in index.outline if tuple(line) not in rings)
    return BoardCopper(copper, tuple(pads), tuple(tracks), tuple(vias), tuple(graphics), tuple(keepouts),
                       tuple(holes), rings, open_, _untented(tenting, copper, copper), expansion, min_width,
                       mask_to_copper)
