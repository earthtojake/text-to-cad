"""A KiCad board as the picture the CAD Viewer and ``cad <type> snapshot`` draw: geometry per layer.

The payload (``cad.engine.formats.kicad.PLOT_SCHEMA_VERSION`` 4; its contract is the core
package's ``docs/plot-payload.md``) is built from the ``.kicad_pcb`` alone: no
KiCad runs here. The file is KiCad's own, and everything the picture needs is in it,
the pours' saved fills included -- which the viewer and the snapshot replace with KiCad's refill of
them, drawing from a refilled copy's bytes (``build_plot(path, data)``, :mod:`.poured`).

The picture is KiCad's PCB editor's, with its default display: every layer shown,
the front copper the active layer, and KiCad's drawing order for that (its
``pcb_draw_panel_gal.cpp``: the back side, the inner coppers, the user layers and the
outline, then the front side, then what goes through the board on top).

The board is one SHEET: millimetres, y down, KiCad's frame moved so the
board's outline sits with its top-left corner at (0, 0) -- its ``width`` and
``height`` are the outline's.
The sheet is a stack of LAYERS, bottom to top in that order: the board's area (``area``), the back side's fabrication, courtyard,
adhesive, paste, silkscreen and mask, the back copper, the inner coppers deepest
first, the user layers and ``Edge.Cuts``, the front side's in the same order up to
its copper, then four layers of what goes through the board: the pads' holes
(``drills``), the vias' (``vias``), the ``ratsnest`` and the through-hole pads' and
vias' names (``names``). Each layer is a list of ITEMS, each a polygon, a stroked
path, a circle, a text's strokes or a label the renderer lays out, in sheet
millimetres:

- a pad is its padstack's outline (rect, roundrect, oval, trapezoid, chamfered,
  custom) on every copper layer it flashes on, carrying its pad reference (``#R1.2``)
  and net; its number and net name are labels, a surface pad's on its copper, a
  through-hole pad's on ``names``;
- a via is a ring on each copper layer it flashes on, its annular width wide, and
  its hole on ``vias``; a pad's hole and an unplated hole are on ``drills``; a plated
  hole carries its wall's width;
- a track or arc is a path of its width; a pour's fill is the polygon KiCad
  saved, marked ``pour`` so a view can hide it (and drawn translucent, as KiCad draws
  zones), a teardrop also ``teardrop``, and its drawn outline a hairline;
- footprint and board graphics (lines, rectangles, circles, arcs, polygons,
  curves) are paths and polygons of their stroke width, a footprint's carrying
  its part reference (``#R1``); a dimension is the lines KiCad draws for it
  (:mod:`cad.engine.formats.kicad.dimensions`) and its text;
- text is its strokes in a permissive font (:mod:`cad.engine.formats.kicad.stroke_font`) at
  KiCad's position, size, angle, justification, mirroring and slant;
- solder mask openings and paste are derived from the pads: a pad's outline
  grown by its mask margin, a pad's outline shrunk or grown by its paste margin
  (a plotter's exact offsets they are not);
- the ratsnest is the engine's connectivity over the copper
  (:mod:`cad.engine.formats.kicad.connectivity`): one line per connection still to make,
  no DRC;
- the board's area is its outline filled, cutouts left open. No drawing sheet (the page's
  border and title block) is drawn: a board is the board alone.

``board`` beside the sheet is the board's index (:mod:`cad.engine.formats.kicad.board_index`)
in sheet millimetres, which the viewer's tools point with (its ``origin`` is where
KiCad's (0, 0) lies on the sheet, so a reference reads back in KiCad's own frame);
``unrouted`` counts the ratsnest's lines. The payload is a function of the file's bytes: the same board
gives the same bytes; each request reads the saved file anew.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Iterable, Sequence

from cad.engine.formats.kicad import sexpr
from cad.engine.formats.kicad.board_index import (
    FootprintFrame, canonical_copper, copper_layers, expand_copper, footprint_property, graphic, item_id, item_layers, layer_of, locked, net_of,
    net_table, pad_shape, points_of, read_index,
)
from cad.engine.formats.kicad.connectivity import Copper, ratsnest
from cad.engine.formats.kicad.dimensions import dimension_shapes
from cad.engine.formats.kicad.geometry import XY, area, box, inside, polygon_distance, rotate
from cad.engine.formats.kicad.labels import is_track, pad_labels, via_labels
from cad.engine.formats.kicad.naming import netclass_of, project_netclasses
from cad.engine.formats.kicad.sexpr import Sym
from cad.engine.formats.kicad.stroke_font import text_strokes
from cad.engine.formats.kicad.text_variables import title_variables
from cad.engine.formats.kicad import PLOT_SCHEMA_VERSION, PlotError

__all__ = ["BOARD_BACKGROUND", "build_plot", "payload_bytes", "plot_payload_bytes"]

#: The canvas behind a board: the viewer's neutral dark grey (its dark `--background`, `#292929`),
#: in place of KiCad's default theme's navy, so a board sits on the same canvas as every other view.
BOARD_BACKGROUND = "#292929"
_DIGITS = 4
_GRAPHICS = ("line", "rect", "poly", "circle", "arc", "curve")
_COPPER = re.compile(r"^(F|B|In\d+)\.Cu$")
# KiCad's default text stroke, as a share of the text's height, for text that names none.
_TEXT_STROKE = 0.15
# A board with no outline is framed on everything it draws, with this much air around it.
_BARE_MARGIN = 1.0
# A pour's drawn outline, and an unplated hole's own layer.
_HAIRLINE = 0.0
# A plated hole's wall as KiCad paints it: 20 um of plating (ADVANCED_CFG's HoleWallThickness), drawn 1.5 times
# as thick (HoleWallPaintingMultiplier).
_HOLE_WALL = 0.020 * 1.5
# The drill KiCad gives a via that names none: its net class's, else KiCad's own default (netclass.cpp).
_VIA_DRILL, _MICROVIA_DRILL = 0.3, 0.1
# A copper layer's items, bottom to top, as KiCad stacks its sub-layers: the zone fills, the tracks and
# graphics, the via copper, the pad copper, the names.
_TIERS = ("pour", "main", "via", "pad", "label")
# The layers of what goes through the board, and what is drawn under everything: (id, kind).
_THROUGH = (("drills", "drill"), ("vias", "via"), ("ratsnest", "ratsnest"), ("names", "names"))
_UNDER = (("area", "area"),)


# --- the stack ----------------------------------------------------------------------------


def _side(layer: str) -> str:
    return "front" if layer.startswith("F.") else "back" if layer.startswith("B.") else "both"


def _kind(layer: str) -> str:
    if _COPPER.match(layer):
        return "copper"
    suffix = layer.split(".", 1)[-1] if "." in layer else layer
    return {
        "SilkS": "silk", "Fab": "fab", "CrtYd": "courtyard", "Mask": "mask", "Paste": "paste", "Adhes": "adhesive",
        "Edge.Cuts": "outline", "Margin": "margin",
    }.get(layer if layer in ("Edge.Cuts", "Margin") else suffix, "user")


def _number(layer: str) -> int:
    return int(re.sub(r"\D", "", layer) or 0)


def _stack(declared: Sequence[str], copper: Sequence[str]) -> list[str]:
    """Every drawable board layer, bottom to top as KiCad draws them with the front copper active."""
    inner = sorted((name for name in copper if name.startswith("In")), key=_number, reverse=True)
    users = sorted((name for name in declared if name.startswith("User.")), key=_number, reverse=True)
    stack = ["B.Fab", "B.CrtYd", "B.Adhes", "B.Paste", "B.SilkS", "B.Mask"]
    stack += (["B.Cu"] if "B.Cu" in copper else []) + inner
    stack += users + ["Margin", "Edge.Cuts", "Eco2.User", "Eco1.User", "Cmts.User", "Dwgs.User"]
    stack += ["F.Fab", "F.CrtYd", "F.Adhes", "F.Paste", "F.SilkS", "F.Mask"] + (["F.Cu"] if "F.Cu" in copper else [])
    return [layer for layer in stack if layer in declared or _COPPER.match(layer)]


# --- items ---------------------------------------------------------------------------------


def _num(value: float) -> float:
    rounded = round(float(value), _DIGITS)
    return 0.0 if rounded == 0 else rounded


def _xy(point: XY) -> list[float]:
    return [_num(point[0]), _num(point[1])]


def _dedupe(points: Iterable[XY]) -> list[XY]:
    out: list[XY] = []
    for point in points:
        if not out or abs(point[0] - out[-1][0]) > 1e-9 or abs(point[1] - out[-1][1]) > 1e-9:
            out.append(point)
    return out


class _Sheet:
    """The payload being built: items filed by layer and tier, the copper for the ratsnest, every point."""

    def __init__(self) -> None:
        self.layers: dict[str, dict[str, list[dict]]] = {}
        self.copper: list[Copper] = []
        self.points: list[XY] = []

    def add(self, layer: str, item: dict, points: Iterable[XY] = (), tier: str = "main") -> None:
        self.layers.setdefault(layer, {}).setdefault(tier, []).append(item)
        self.points.extend(points)

    def items(self, layer: str) -> list[dict]:
        tiers = self.layers.get(layer, {})
        return [item for tier in _TIERS for item in tiers.get(tier, ())]

    def polygon(self, layer: str, points: Sequence[XY], *, width: float = 0.0, tier: str = "main", **flags) -> None:
        pts = _dedupe(points)
        if len(pts) < 3:
            return
        item = {"t": "poly", "pts": pts}
        if width > 0:
            item["w"] = width
        item.update(flags)
        self.add(layer, item, pts, tier)

    def path(self, layer: str, points: Sequence[XY], width: float, *, closed: bool = False, tier: str = "main",
             framed: bool = True, **flags) -> None:
        pts = _dedupe(points)
        if len(pts) < 2:
            return
        item = {"t": "path", "pts": pts, "w": max(0.0, width)}
        if closed:
            item["closed"] = True
        item.update(flags)
        self.add(layer, item, pts if framed else (), tier)

    def circle(self, layer: str, at: XY, radius: float, *, width: float = 0.0, tier: str = "main", **flags) -> None:
        if radius <= 0:
            return
        item = {"t": "circle", "at": at, "r": radius, "w": max(0.0, width)}
        item.update(flags)
        self.add(layer, item, [(at[0] - radius, at[1] - radius), (at[0] + radius, at[1] + radius)], tier)

    def text(self, layer: str, text: str, strokes: list[list[XY]], width: float, *, framed: bool = True, **flags) -> None:
        strokes = [stroke for stroke in (_dedupe(points) for points in strokes) if len(stroke) >= 2]
        if not strokes:
            return
        item = {"t": "text", "text": text, "w": width, "strokes": strokes}
        item.update(flags)
        self.add(layer, item, (point for stroke in strokes for point in stroke) if framed else ())

    def label(self, layer: str, item: dict, tier: str = "label") -> None:
        self.add(layer, item, (), tier)


def _stroke_width(node: list) -> float:
    stroke = sexpr.find(node, "stroke")
    if stroke is not None:
        return sexpr.number(sexpr.value(stroke, "width"), 0.0)
    return sexpr.number(sexpr.value(node, "width"), 0.0)


def _filled(node: list) -> bool:
    fill = sexpr.find(node, "fill")
    if fill is None or len(fill) < 2:
        return False
    value = fill[1]
    if isinstance(value, list):  # KiCad 6: (fill (type solid))
        value = sexpr.value(fill, "type")
    return str(value) in ("yes", "solid")


def _hidden(node: list) -> bool:
    return str(sexpr.value(node, "hide", "")) == "yes" or any(isinstance(atom, Sym) and atom == "hide" for atom in node[1:])


def _flag(node: list, name: str) -> bool:
    """A KiCad flag: ``(name)``, ``(name yes)`` or a bare ``name`` atom."""
    found = sexpr.find(node, name)
    if found is not None:
        return len(found) < 2 or str(found[1]) in ("yes", "true")
    return any(isinstance(atom, Sym) and atom == name for atom in node[1:])


def _text_style(node: list) -> tuple[tuple[float, float], float, list[str], bool]:
    """A text's ``(effects ...)``: its size (height, width), stroke thickness, justification and slant."""
    effects = sexpr.find(node, "effects")
    font = sexpr.find(effects, "font") if effects is not None else None
    size = sexpr.pair(sexpr.find(font, "size"), (1.0, 1.0)) if font is not None else (1.0, 1.0)
    thickness = sexpr.number(sexpr.value(font, "thickness"), 0.0) if font is not None else 0.0
    justify = [str(atom) for atom in (sexpr.find(effects, "justify") or [])[1:]] if effects is not None else []
    italic = font is not None and _flag(font, "italic")
    bold = font is not None and _flag(font, "bold")
    height = abs(size[0])
    # KiCad's pen for text that names none: a fifth of its size when bold, else its default share.
    pen = thickness or (min(height, abs(size[1])) / 5 if bold else height * _TEXT_STROKE)
    return (height, abs(size[1])), pen, justify, italic


def _slot(width: float, height: float) -> list[XY]:
    """A slotted hole's outline, centred, before its turn: a stadium ``width`` by ``height``."""
    radius = min(width, height) / 2
    hw, hh = width / 2 - radius, height / 2 - radius
    out: list[XY] = []
    for cx, cy, start in ((hw, -hh, -math.pi / 2), (hw, hh, 0.0), (-hw, hh, math.pi / 2), (-hw, -hh, math.pi)):
        for step in range(7):
            angle = start + (math.pi / 2) * step / 6
            out.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
    return out


def _scaled(polygon: Sequence[XY], centre: XY, factor: float) -> list[XY]:
    return [(centre[0] + (x - centre[0]) * factor, centre[1] + (y - centre[1]) * factor) for x, y in polygon]


def _legacy_text(text: str) -> str:
    """KiCad 5's ``%R`` and ``%V``, which KiCad reads as ``${REFERENCE}`` and ``${VALUE}`` in any text."""
    return text.replace("%V", "${VALUE}").replace("%R", "${REFERENCE}")


def _unused_layers(node: list) -> tuple[str, list[str]]:
    """How a pad or via keeps its copper on layers nothing connects to (KiCad's unconnected layer
    mode: ``all``, ``ends``, ``connected+ends`` or ``connected``), and the layers a zone connects it
    on (``zone_layer_connections``)."""
    zones = [str(atom) for atom in (sexpr.find(node, "zone_layer_connections") or [])[1:] if isinstance(atom, str)]
    if _flag(node, "start_end_only"):
        return "ends", zones
    if not _flag(node, "remove_unused_layers"):
        return "all", zones
    return ("connected+ends" if _flag(node, "keep_end_layers") else "connected"), zones


class _Ends:
    """Where each track and arc ends, by copper layer: what keeps a pad's or via's copper on a layer
    whose unused copper is removed (KiCad's ``FlashLayer``: connected there by a track)."""

    _CELL = 2.0

    def __init__(self, tree: list, table) -> None:
        self.cells: dict[tuple[str, int, int], list[tuple[float, float, float, str | None]]] = {}
        for node in tree[1:]:
            if sexpr.head(node) not in ("segment", "arc"):
                continue
            layer = layer_of(node)
            if layer is None:
                continue
            net = net_of(node, table)
            half = sexpr.number(sexpr.value(node, "width"), 0.0) / 2
            for key in ("start", "end"):
                point = sexpr.pair(sexpr.find(node, key))
                if point is not None:
                    cell = (layer, math.floor(point[0] / self._CELL), math.floor(point[1] / self._CELL))
                    self.cells.setdefault(cell, []).append((point[0], point[1], half, net))

    def _near(self, layer: str, x0: float, y0: float, x1: float, y1: float):
        for cx in range(math.floor(x0 / self._CELL) - 1, math.floor(x1 / self._CELL) + 2):
            for cy in range(math.floor(y0 / self._CELL) - 1, math.floor(y1 / self._CELL) + 2):
                yield from self.cells.get((layer, cx, cy), ())

    def disc(self, layer: str, at: XY, radius: float, net: str | None) -> bool:
        return any(other == net and math.hypot(x - at[0], y - at[1]) <= radius + half
                   for x, y, half, other in self._near(layer, at[0] - radius, at[1] - radius, at[0] + radius, at[1] + radius))

    def polygon(self, layer: str, polygon: Sequence[XY], net: str | None) -> bool:
        corners = box(polygon)
        return any(other == net and (inside((x, y), polygon) or polygon_distance((x, y), polygon) <= half)
                   for x, y, half, other in self._near(layer, corners[0][0], corners[0][1], corners[2][0], corners[2][1]))


def _flashed(mode: str, zones: Sequence[str], layers: Sequence[str], ends: Sequence[str], joined) -> list[str]:
    """The copper layers a pad or via keeps its copper on: all, its end layers, and those a zone or track joins it on."""
    if mode == "all":
        return list(layers)
    return [layer for layer in layers
            if (mode != "connected" and layer in ends) or (mode != "ends" and (layer in zones or joined(layer)))]


class _NetClasses:
    """A net's class's numbers the picture needs: its clearance (a pad's clearance outline) and its via
    drills (for a via that names none), from a KiCad 5 board's own ``(net_class ...)`` list or the
    project's ``net_settings``, else KiCad's defaults."""

    _DEFAULT = (0.2, _VIA_DRILL, _MICROVIA_DRILL)  # clearance, via drill, microvia drill (netclass.cpp)

    def __init__(self, tree: list, project: Path) -> None:
        self.classes: dict[str, tuple[float, float, float]] = {}
        self.members: dict[str, str] = {}
        for entry in sexpr.find_all(tree, "net_class"):
            if len(entry) < 2:
                continue
            name = str(entry[1])
            self.classes[name] = tuple(sexpr.number(sexpr.value(entry, key), default)
                                       for key, default in zip(("clearance", "via_drill", "uvia_drill"), self._DEFAULT))
            for net in sexpr.find_all(entry, "add_net"):
                if len(net) > 1:
                    self.members[str(net[1])] = name
        self.assigned, self.patterns = project_netclasses(project)
        if project.is_file():
            try:
                settings = json.loads(project.read_text(encoding="utf-8")).get("net_settings") or {}
                for entry in settings.get("classes") or []:
                    if isinstance(entry, dict) and entry.get("name"):
                        self.classes.setdefault(str(entry["name"]), tuple(
                            float(entry.get(key) if entry.get(key) is not None else default)
                            for key, default in zip(("clearance", "via_drill", "microvia_drill"), self._DEFAULT)))
            except (OSError, ValueError, AttributeError, TypeError):
                pass

    def _of(self, net: str | None) -> tuple[float, float, float]:
        name = self.members.get(net or "") or (netclass_of(net, self.assigned, self.patterns) if net else "Default")
        return self.classes.get(name) or self.classes.get("Default") or self._DEFAULT

    def clearance(self, net: str | None) -> float:
        return self._of(net)[0]

    def via_drill(self, net: str | None, micro: bool) -> float:
        return self._of(net)[2 if micro else 1]


def _hatch(outline: Sequence[XY], spacing: float, length: float, slope: float) -> list[XY]:
    """A zone's border hatch, as KiCad's ``SHAPE_POLY_SET::GenerateHatchLines`` lays it: lines of
    ``slope`` every ``spacing`` (in their intercept) across the outline, each cut to the outline,
    or only its two ends ``length`` long (measured along x) for an edge hatch; as point pairs."""
    if len(outline) < 3 or spacing <= 0:
        return []
    xs, ys = [p[0] for p in outline], [p[1] for p in outline]
    min_x, max_x, min_y, max_y = min(xs), max(xs), min(ys), max(ys)
    if slope > 0:
        top, low = max_y - slope * min_x, min_y - slope * max_x
    else:
        top, low = max_y - slope * max_x, min_y - slope * min_x
    low = math.trunc(low / spacing) * spacing
    edges = list(zip(outline, [*outline[1:], outline[0]]))
    # Each edge crosses the lines whose intercept lies between its ends': filed by line, not walked per line.
    lines: dict[int, list[XY]] = {}
    for (ax, ay), (bx, by) in edges:
        ia, ib = ay - slope * ax, by - slope * bx
        first, last = math.ceil((min(ia, ib) - low) / spacing), math.floor((max(ia, ib) - low) / spacing)
        for step in range(max(first, 0), last + 1):
            a = low + step * spacing
            if a >= top:
                break
            if ax == bx:
                x = ax
            else:
                m = (by - ay) / (bx - ax)
                if abs(m - slope) < 1e-12:
                    continue
                x = (ay - m * ax - a) / (slope - m)
            y = slope * x + a
            if min_x - 1e-9 <= x <= max_x + 1e-9 and min_y - 1e-9 <= y <= max_y + 1e-9:
                lines.setdefault(step, []).append((x, y))
    out: list[XY] = []
    for step in sorted(lines):
        crossings = sorted(lines[step], key=lambda point: -point[0])
        for p1, p2 in zip(crossings, crossings[1:]):
            if abs(p1[0] - p2[0]) < 1e-9 and abs(p1[1] - p2[1]) < 1e-9:
                continue
            if not inside(((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2), outline):
                continue
            dx = p2[0] - p1[0]
            if length < 0 or abs(dx) < 2 * length:
                out.extend((p1, p2))
            else:
                run = (p2[1] - p1[1]) / dx
                step_x = length if dx > 0 else -length
                out.extend((p1, (p1[0] + step_x, p1[1] + step_x * run), p2, (p2[0] - step_x, p2[1] - step_x * run)))
    return out


class _Builder:
    def __init__(self, tree: list, path: Path):
        self.tree = tree
        # Each graphic drawn with its uuid and its footprint's: the ids are settled once all are drawn.
        self.named: list[tuple[dict, str, str | None]] = []
        self.path = path
        self.table = net_table(tree)
        self.copper = copper_layers(tree)
        setup = sexpr.find(tree, "setup") or []
        self.mask_margin = sexpr.number(sexpr.value(setup, "pad_to_mask_clearance"), 0.0)
        self.paste_margin = sexpr.number(sexpr.value(setup, "pad_to_paste_clearance"), 0.0)
        self.paste_ratio = sexpr.number(sexpr.value(setup, "pad_to_paste_clearance_ratio"), 0.0)
        self.sheet = _Sheet()
        self.ends = _Ends(tree, self.table)
        self.classes = _NetClasses(tree, path.with_suffix(".kicad_pro"))
        self.variables = self._board_variables()

    def _board_variables(self) -> dict[str, str]:
        """What a board text's ``${...}`` names: its title block, its file and the project's text variables."""
        return title_variables(self.tree, file_name=self.path.name, project=self.path.with_suffix(".kicad_pro"))

    # -- footprints --------------------------------------------------------------------

    def footprint(self, node: list) -> None:
        frame = FootprintFrame(node)
        ref = footprint_property(node, "Reference") or ""
        value = footprint_property(node, "Value") or ""
        fields = {str(item[1]): str(item[2]) for item in sexpr.find_all(node, "property") if len(item) >= 3}
        selector = f"#{ref}" if ref else None
        owner = item_id(node)
        margins = (
            sexpr.value(node, "solder_mask_margin"),
            sexpr.value(node, "solder_paste_margin"),
            sexpr.value(node, "solder_paste_ratio"),
            sexpr.value(node, "clearance"),
        )
        for child in node[2:]:
            head = sexpr.head(child)
            if head == "pad":
                self.pad(child, frame, ref, margins)
            elif head == "zone":
                self.zone(child)
            elif head == "property" or head == "fp_text":
                self.footprint_text(child, frame, ref, value, fields)
            elif head and head.startswith("fp_") and head[3:] in _GRAPHICS:
                self.graphic(child, frame, selector, owner)
            elif head == "dimension":
                self.dimension(child)

    def footprint_text(self, node: list, frame: FootprintFrame, ref: str, value: str, fields: dict[str, str]) -> None:
        if _hidden(node):
            return
        head = sexpr.head(node)
        if head == "property":
            if len(node) < 3 or not isinstance(node[2], str):
                return
            text = node[2]
        else:  # fp_text reference|value|user "text"
            if len(node) < 3:
                return
            text = _legacy_text(str(node[2]))
            which = str(node[1])
            if which == "reference":
                text = ref
            elif which == "value":
                text = value
        names = {**self.variables, **fields, "REFERENCE": ref, "VALUE": value}
        text = re.sub(r"\$\{([^}]+)\}", lambda match: names.get(match.group(1), match.group(0)), text)
        if not text.strip():
            return
        layer = layer_of(node)
        at = sexpr.find(node, "at")
        if layer is None or at is None:
            return
        position = frame.place(sexpr.pair(at, (0.0, 0.0)))
        angle = sexpr.number(at[3]) if len(at) > 3 and isinstance(at[3], (int, float)) else 0.0
        # A footprint's text keeps upright unless it is unlocked (KiCad's PCB_TEXT::GetDrawRotation):
        # turned to read between -90 and 90 degrees.
        unlocked = _flag(node, "unlocked") or any(isinstance(atom, Sym) and atom == "unlocked" for atom in at[1:])
        if not unlocked:
            while angle > 90:
                angle -= 180
            while angle <= -90:
                angle += 180
        self.text(layer, text, position, angle, node, selector=f"#{ref}" if ref else None)

    def text(self, layer: str, text: str, at: XY, angle: float, node: list, *, selector: str | None = None) -> None:
        size, thickness, justify, italic = _text_style(node)
        strokes = text_strokes(text, size=size, at=at, angle=angle, justify=justify, mirror="mirror" in justify, italic=italic)
        flags = {"ref": selector} if selector else {}
        found = sexpr.find(node, "layer")
        if found is not None and any(isinstance(atom, Sym) and atom == "knockout" for atom in found[2:]) and strokes:
            # Knocked out: a box round the text in the layer's colour, the letters cut from it (KiCad's
            # knockout cache: the text's box, in its own frame, grown by its knockout margin).
            margin = max(thickness / 2, size[0] / 9) + thickness / 2
            flat = [rotate(x - at[0], y - at[1], -angle) for stroke in strokes for x, y in stroke]
            corners = box(flat)
            left, top, right, bottom = corners[0][0] - margin, corners[0][1] - margin, corners[2][0] + margin, corners[2][1] + margin
            flags["knockout"] = [(at[0] + dx, at[1] + dy) for dx, dy in
                                 (rotate(x, y, angle) for x, y in ((left, top), (right, top), (right, bottom), (left, bottom)))]
        self.sheet.text(layer, text, strokes, thickness, **flags)

    def text_box(self, node: list, grow_x: float, grow_y: float) -> tuple[list[XY], float, XY]:
        """A text's box in the stroke font, grown along and across it, turned with it (for a dimension)."""
        text = str(node[1]) if len(node) > 1 else ""
        size, _thickness, justify, italic = _text_style(node)
        at = sexpr.pair(sexpr.find(node, "at"), (0.0, 0.0))
        angle = sexpr.number(sexpr.find(node, "at")[3]) if len(sexpr.find(node, "at") or []) > 3 else 0.0
        flat = [point for stroke in text_strokes(text, size=size, at=at, justify=justify, italic=italic) for point in stroke]
        if not flat:
            flat = [at]
        corners = box(flat)
        left, top, right, bottom = corners[0][0] - grow_x, at[1] - size[0] / 2 - grow_y, corners[2][0] + grow_x, at[1] + size[0] / 2 + grow_y
        centre = ((left + right) / 2, (top + bottom) / 2)
        turned = []
        for x, y in ((left, top), (left, bottom), (right, bottom), (right, top)):
            dx, dy = rotate(x - centre[0], y - centre[1], angle)
            turned.append((centre[0] + dx, centre[1] + dy))
        # KiCad turns the box about its own centre; the text's turn is about its anchor, the box's centre here.
        return turned, right - left, centre

    def graphic(self, node: list, frame: FootprintFrame | None, selector: str | None, owner: str | None = None) -> None:
        drawn = graphic(node)
        layer = layer_of(node)
        if drawn is None or layer is None:
            return
        points, closed = drawn
        if frame is not None:
            points = [frame.place(point) for point in points]
        width = _stroke_width(node)
        flags = {"ref": selector} if selector else {}
        # What a pick names it by (`#shape:<id>`) and what it is, a line unless it says: the index's Shape.
        uid = item_id(node)
        if uid:
            shape = (sexpr.head(node) or "_").split("_", 1)[1]
            flags["id"] = uid
            if shape != "line":
                flags["shape"] = shape
            if locked(node):
                flags["locked"] = True
        # A shape on copper that carries a net is copper of that net (a filled rectangle joining pads):
        # drawn with it, and joined with it in the ratsnest.
        net = net_of(node, self.table) if expand_copper([layer], self.copper) else None
        if net:
            flags["net"] = net
        if closed and _filled(node):
            self.sheet.polygon(layer, points, width=width, **flags)
            if net:
                self.sheet.copper.append(Copper.polygon(net, [layer], points))
        else:
            self.sheet.path(layer, points, width, closed=closed, **flags)
            if net:
                ends = [*points, points[0]] if closed else points
                for start, end in zip(ends, ends[1:]):
                    self.sheet.copper.append(Copper.segment(net, layer, start, end, width))
        drawn_item = (self.sheet.layers.get(layer, {}).get("main") or [None])[-1]  # a graphic draws in the main tier
        if uid and drawn_item is not None and drawn_item.get("id") == uid:
            self.named.append((drawn_item, uid, owner))

    def dimension(self, node: list) -> None:
        drawn = dimension_shapes(node, self.text_box)
        if drawn is None or drawn.layer is None:
            return
        for start, end in drawn.segments:
            self.sheet.path(drawn.layer, [start, end], drawn.width)
        for centre, radius in drawn.circles:
            self.sheet.circle(drawn.layer, centre, radius, width=drawn.width)
        gr_text = drawn.text
        if gr_text is not None and len(gr_text) > 1 and isinstance(gr_text[1], str) and gr_text[1].strip():
            at = sexpr.find(gr_text, "at")
            if at is not None:
                self.text(drawn.layer, gr_text[1], sexpr.pair(at, (0.0, 0.0)), sexpr.number(at[3]) if len(at) > 3 else 0.0, gr_text)

    # -- pads --------------------------------------------------------------------------

    def pad(self, node: list, frame: FootprintFrame, ref: str, margins: tuple) -> None:
        kind = str(node[2]) if len(node) > 2 else ""
        number = str(node[1]) if len(node) > 1 else ""
        at = sexpr.find(node, "at")
        centre = frame.place(sexpr.pair(at, (0.0, 0.0)))
        angle = sexpr.number(at[3]) if at is not None and len(at) > 3 else 0.0
        layers = item_layers(node)
        drill = sexpr.find(node, "drill")
        offset = sexpr.pair(sexpr.find(drill, "offset"), (0.0, 0.0)) if drill is not None else (0.0, 0.0)
        shape = [(centre[0] + dx, centre[1] + dy) for dx, dy in (rotate(x + offset[0], y + offset[1], angle) for x, y in pad_shape(node))]
        size = sexpr.pair(sexpr.find(node, "size"), (0.0, 0.0))
        selector = f"#{ref}.{number}" if ref and number else None
        flags = {}
        if selector:
            flags["ref"] = selector
        net = net_of(node, self.table)
        if net:
            flags["net"] = net
        copper = expand_copper(layers, self.copper)
        hole = self.hole(drill, centre, angle, kind, size)
        if kind == "np_thru_hole":
            opening = hole if hole is not None else shape
            # An unplated hole has copper only where its pad is larger than the hole (KiCad's FlashLayer).
            sizes = [float(value) for value in (drill or [])[1:] if isinstance(value, (int, float))]
            form = str(node[3]) if len(node) > 3 else ""
            if sizes and not (form in ("circle", "oval") and offset == (0.0, 0.0) and sizes[0] >= abs(size[0]) - 1e-9
                              and (form == "circle" or sizes[-1] >= abs(size[1]) - 1e-9)):
                for layer in copper:
                    self.sheet.polygon(layer, shape, tier="pad", **({"ref": selector} if selector else {}))
        else:
            opening = shape
            mode, zones = _unused_layers(node) if kind == "thru_hole" else ("all", [])
            flashed = _flashed(mode, zones, copper, ("F.Cu", "B.Cu"), lambda layer: self.ends.polygon(layer, shape, net))
            # KiCad outlines a pad's clearance on the layer being edited, the front copper: a hairline
            # around the pad, its own clearance (the pad's or its footprint's, else its net class's) out.
            local = sexpr.value(node, "clearance")
            clearance = sexpr.number(local, sexpr.number(margins[3], self.classes.clearance(net)))
            for layer in flashed:
                extra = {"clearance": _num(clearance)} if layer == "F.Cu" and clearance > 0 else {}
                self.sheet.polygon(layer, shape, tier="pad", **flags, **extra)
            if net:
                anchor = (centre[0] + rotate(*offset, angle)[0], centre[1] + rotate(*offset, angle)[1])
                self.sheet.copper.append(Copper.polygon(net, copper, shape, anchor=anchor, pad=True))
            self.pad_names(node, number, net, shape, size, copper, kind)
        # Mask openings and paste, derived from the pad: KiCad's own margins, applied as one offset.
        mask_margin = sexpr.number(sexpr.value(node, "solder_mask_margin"), sexpr.number(margins[0], self.mask_margin))
        for layer in self._technical(layers, "Mask"):
            self.sheet.polygon(layer, opening, width=max(0.0, 2 * mask_margin), **flags)
        if kind != "np_thru_hole":
            ratio = sexpr.number(sexpr.value(node, "solder_paste_margin_ratio"), sexpr.number(margins[2], self.paste_ratio))
            paste_margin = sexpr.number(sexpr.value(node, "solder_paste_margin"), sexpr.number(margins[1], self.paste_margin))
            paste_margin += ratio * min(abs(size[0]), abs(size[1]))
            for layer in self._technical(layers, "Paste"):
                if paste_margin < 0 and min(abs(size[0]), abs(size[1])) > 0:
                    factor = max(0.0, 1 + 2 * paste_margin / min(abs(size[0]), abs(size[1])))
                    shifted = rotate(offset[0], offset[1], angle)  # shrunk about the shape's own centre
                    self.sheet.polygon(layer, _scaled(shape, (centre[0] + shifted[0], centre[1] + shifted[1]), factor),
                                       **flags)
                else:
                    self.sheet.polygon(layer, shape, width=2 * paste_margin, **flags)

    def pad_names(self, node: list, number: str, net: str | None, shape: Sequence[XY], size: XY, copper: Sequence[str], kind: str) -> None:
        """A pad's number and net name: on its copper for a surface pad, over everything for one through the board."""
        if not copper or len(shape) < 3:
            return
        corners = box(shape)
        pin_type = sexpr.value(node, "pintype")
        form = str(node[3]) if len(node) > 3 else ""
        labels = pad_labels(number=number, net=net, pin_type=str(pin_type) if pin_type is not None else None,
                            box=(corners[0][0], corners[0][1], corners[2][0], corners[2][1]), size=size,
                            round_shape=form in ("circle", "oval"), custom=form == "custom")
        if kind != "thru_hole" and len(copper) == 1 and copper[0] in ("F.Cu", "B.Cu"):
            layer, tier = copper[0], "label"
        else:
            layer, tier = "names", "main"
        for label in labels:
            self.sheet.label(layer, label, tier)

    def _technical(self, layers: Sequence[str], suffix: str) -> list[str]:
        out = []
        for layer in layers:
            if layer == f"*.{suffix}":
                out.extend([f"F.{suffix}", f"B.{suffix}"])
            elif layer in (f"F.{suffix}", f"B.{suffix}"):
                out.append(layer)
        return list(dict.fromkeys(out))

    def hole(self, drill: list | None, centre: XY, angle: float, kind: str, size: XY) -> list[XY] | None:
        """A pad's hole on the ``drills`` layer: a circle, or a slot's outline, a plated one carrying its
        wall's width; answers the outline of what was drilled (for the mask opening of an unplated hole)."""
        if drill is None or kind not in ("thru_hole", "np_thru_hole"):
            return None
        sizes = [float(value) for value in drill[1:] if isinstance(value, (int, float))]
        if not sizes:
            return None
        # The hole is at the pad's own position: a drill offset moves the copper shape, never the hole (KiCad's
        # pad position is its hole's; the shape is drawn at position + offset).
        at = centre
        plated = kind == "thru_hole"
        # KiCad keeps a hole's wall inside its pad: no wider than half the pad.
        wall = min(_HOLE_WALL, abs(size[0]) / 2, abs(size[1]) / 2) if plated else 0.0
        flag = {"hole": "pad" if plated else "npth"}
        if any(isinstance(value, Sym) and value == "oval" for value in drill[1:]) and len(sizes) >= 2 and abs(sizes[0] - sizes[1]) > 1e-9:
            outline = [(at[0] + x, at[1] + y) for x, y in (rotate(px, py, angle) for px, py in _slot(sizes[0], sizes[1]))]
            self.sheet.polygon("drills", outline, width=wall, **flag)
            return outline
        radius = sizes[0] / 2
        self.sheet.circle("drills", at, radius, width=wall, **flag)
        steps = 24
        return [(at[0] + radius * math.cos(2 * math.pi * k / steps), at[1] + radius * math.sin(2 * math.pi * k / steps)) for k in range(steps)]

    # -- copper ------------------------------------------------------------------------

    def track(self, node: list) -> None:
        head = sexpr.head(node)
        layer = layer_of(node)
        if layer is None:
            return
        if head == "segment":
            points = [sexpr.pair(sexpr.find(node, "start")), sexpr.pair(sexpr.find(node, "end"))]
        else:
            ends = [sexpr.pair(sexpr.find(node, key)) for key in ("start", "mid", "end")]
            if None in ends:
                return
            from cad.engine.formats.kicad.geometry import arc_points

            points = arc_points(*ends)
        if None in points:
            return
        width = sexpr.number(sexpr.value(node, "width"), 0.0)
        net = net_of(node, self.table)
        self.sheet.path(layer, points, width, **({"net": net} if net else {}))
        if net:
            for start, end in zip(points, points[1:]):
                self.sheet.copper.append(Copper.segment(net, layer, start, end, width))

    def via(self, node: list) -> None:
        at = sexpr.pair(sexpr.find(node, "at"))
        if at is None:
            return
        kind = "through"
        for atom in node[1:]:
            # KiCad 10 writes a buried via (inner layers only) apart from a blind one; KiCad 9's "blind" was
            # both. The payload's kinds are KiCad 9's, so a buried via is drawn and joined as a blind one.
            if isinstance(atom, Sym) and atom in ("blind", "buried", "micro"):
                kind = "blind" if atom == "buried" else str(atom)
        size = sexpr.number(sexpr.value(node, "size"), 0.0)
        net = net_of(node, self.table)
        drill = sexpr.number(sexpr.value(node, "drill"), 0.0) or self.classes.via_drill(net, kind == "micro")
        spanned = item_layers(node)
        order = list(self.copper)
        if kind == "through" or len(spanned) < 2:
            layers = order
        else:
            ends = sorted(order.index(layer) for layer in spanned if layer in order) or [0, len(order) - 1]
            layers = order[ends[0]:ends[-1] + 1]
        flags = {"via": kind}
        if net:
            flags["net"] = net
        radius = size / 2
        annular = max(0.0, (size - drill) / 2)
        mode, zones = _unused_layers(node)
        for layer in _flashed(mode, zones, layers, (layers[0], layers[-1]) if layers else (),
                              lambda layer: self.ends.disc(layer, at, radius, net)):
            if annular > 0:
                self.sheet.circle(layer, at, radius - annular / 2, width=annular, tier="via", **flags)
        hole = {"hole": "via", "via": kind}
        if kind != "through" and layers:
            hole["span"] = [layers[0], layers[-1]]
        self.sheet.circle("vias", at, drill / 2, width=max(0.0, min(_HOLE_WALL, radius - drill / 2)), **hole)
        for label in via_labels(net=net, at=at, width=size, kind=kind, span=layers, copper=order):
            self.sheet.label("names", label, "main")
        if net:
            self.sheet.copper.append(Copper.disc(net, layers, at, size))

    def zone(self, node: list) -> None:
        keepout = sexpr.find(node, "keepout") is not None
        layers = expand_copper(item_layers(node), self.copper)
        if keepout:
            # A rule area is an outline and its hatch, on every layer it keeps out of (KiCad draws no fill).
            layers = list(dict.fromkeys([*layers, *(layer for layer in item_layers(node) if not _COPPER.match(layer) and "*" not in layer and "&" not in layer)]))
        if not layers:
            return
        net = net_of(node, self.table)
        flags = {"net": net} if net and not keepout else {}
        outline = points_of(sexpr.find(sexpr.find(node, "polygon") or [], "pts"))
        attr = sexpr.find(node, "attr")
        teardrop = attr is not None and sexpr.find(attr, "teardrop") is not None
        fills: dict[str, list[list[XY]]] = {}
        for filled in sexpr.find_all(node, "filled_polygon"):
            layer = layer_of(filled) or layers[0]
            fills.setdefault(layer, []).append(points_of(sexpr.find(filled, "pts")))
        hatch = sexpr.find(node, "hatch")
        style = str(hatch[1]) if hatch is not None and len(hatch) > 1 else "edge"
        pitch = sexpr.number(hatch[2], 0.5) if hatch is not None and len(hatch) > 2 else 0.5
        for layer in layers:
            for fill in fills.get(layer, []):
                self.sheet.polygon(layer, fill, tier="pour", pour=True, **({"teardrop": True} if teardrop else {}), **flags)
                if net and len(fill) >= 3:
                    self.sheet.copper.append(Copper.polygon(net, [layer], fill))
            if outline and not teardrop:
                tier = "pour" if keepout else "main"
                self.sheet.path(layer, outline, _HAIRLINE, closed=True, tier=tier, **flags)
                if style in ("edge", "full") and pitch > 0:
                    slope = -1.0 if _COPPER.match(layer) else 1.0
                    pairs = _hatch(outline, pitch * (2 if style == "full" else 1), -1 if style == "full" else pitch, slope)
                    if pairs:
                        self.sheet.path(layer, pairs, _HAIRLINE, tier=tier, framed=False, pairs=True, **flags)

    # -- the board -----------------------------------------------------------------------

    def board_text(self, node: list) -> None:
        if len(node) > 1 and isinstance(node[1], str) and not _hidden(node):
            layer = layer_of(node)
            at = sexpr.find(node, "at")
            if layer and at is not None:
                text = re.sub(r"\$\{([^}]+)\}", lambda match: self.variables.get(match.group(1), match.group(0)), _legacy_text(node[1]))
                self.text(layer, text, sexpr.pair(at, (0.0, 0.0)), sexpr.number(at[3]) if len(at) > 3 else 0.0, node)

    def build(self) -> _Sheet:
        for node in self.tree[1:]:
            head = sexpr.head(node)
            if head in ("footprint", "module"):
                self.footprint(node)
            elif head in ("segment", "arc"):
                self.track(node)
            elif head == "via":
                self.via(node)
            elif head == "zone":
                self.zone(node)
            elif head == "gr_text":
                self.board_text(node)
            elif head == "dimension":
                self.dimension(node)
            elif head and head.startswith("gr_") and head[3:] in _GRAPHICS:
                self.graphic(node, None, None)
        # A uuid that copies of one footprint share names each under its footprint's, as the index names them.
        counts = Counter(uid for _item, uid, _owner in self.named)
        for item, uid, owner in self.named:
            if owner and counts[uid] > 1:
                item["id"] = f"{owner}/{uid}"
        return self.sheet

    def board_area(self, outline: Sequence[Sequence[XY]]) -> None:
        """The board's area on the ``area`` layer: the outline's largest closed loop filled, the loops inside it open."""
        loops = [list(line[:-1]) for line in outline if len(line) >= 4 and math.dist(line[0], line[-1]) <= 0.011]
        if not loops:
            return
        outer = max(loops, key=lambda loop: abs(area(loop)))
        holes = [loop for loop in loops if loop is not outer and inside(loop[0], outer)]
        item: dict = {"t": "poly", "pts": _dedupe(outer)}
        if holes:
            item["holes"] = [_dedupe(loop) for loop in holes]
        if len(item["pts"]) >= 3:
            self.sheet.add("area", item)


# --- the payload ------------------------------------------------------------------------


def _checked(path: Path) -> Path:
    path = Path(path).resolve()
    if path.suffix.lower() != ".kicad_pcb":
        raise PlotError(f"{path.name} is not a KiCad board (.kicad_pcb)")
    if not path.is_file():
        raise PlotError(f"{path.name} does not exist")
    return path


def _read(path: Path) -> tuple[bytes, bytes]:
    """The board's bytes and its project's (empty for none): everything the payload reads."""
    try:
        data = path.read_bytes()
        project = path.with_suffix(".kicad_pro")
        return data, project.read_bytes() if project.is_file() else b""
    except OSError as error:
        raise PlotError(f"{path.name} could not be read ({error.strerror or error}): check that it exists and this user can read it") from None


def _tree(path: Path, data: bytes) -> list:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise PlotError(f"{path.name} is not a readable KiCad board: it is not UTF-8 text") from None
    try:
        tree = sexpr.parse(text)
    except sexpr.SexprError as error:
        raise PlotError(f"{path.name} is not a readable KiCad board ({error})") from None
    if sexpr.head(tree) != "kicad_pcb":
        raise PlotError(f"{path.name} is not a KiCad board: a .kicad_pcb starts with (kicad_pcb ...)")
    return canonical_copper(tree)


def _generator(tree: list) -> str:
    """What wrote the file, for words: ``pcbnew 10.99``."""
    generator = sexpr.value(tree, "generator")
    version = sexpr.value(tree, "generator_version")
    return " ".join(str(part) for part in (generator, version) if part is not None)


def _frame(index, points: Sequence[XY]) -> tuple[float, float, float, float]:
    """The sheet's box in KiCad's frame: the outline's, else everything drawn with air around it."""
    outline = [point for line in index.outline for point in line]
    if outline:
        corners = box(outline)
        return corners[0][0], corners[0][1], corners[2][0], corners[2][1]
    if not points:
        return 0.0, 0.0, 10.0, 10.0
    corners = box(points)
    return corners[0][0] - _BARE_MARGIN, corners[0][1] - _BARE_MARGIN, corners[2][0] + _BARE_MARGIN, corners[2][1] + _BARE_MARGIN


def _shifted(item: dict, dx: float, dy: float) -> dict:
    out = {}
    for key, value in item.items():
        if key == "pts":
            out[key] = [_xy((x - dx, y - dy)) for x, y in value]
        elif key in ("holes",):
            out[key] = [[_xy((x - dx, y - dy)) for x, y in ring] for ring in value]
        elif key == "knockout":
            out[key] = [_xy((x - dx, y - dy)) for x, y in value]
        elif key == "at":
            out[key] = _xy((value[0] - dx, value[1] - dy))
        elif key == "strokes":
            out[key] = [[_xy((x - dx, y - dy)) for x, y in stroke] for stroke in value]
        elif key in ("w", "r"):
            out[key] = _num(value)
        else:
            out[key] = value
    return out


def build_plot(path: Path | str, data: bytes | None = None) -> dict:
    """The plot payload of the board at ``path``: of its saved bytes, or of ``data`` in their place (KiCad's
    refill of them, ``poured``), read beside the same project and named the same."""
    path = _checked(Path(path))
    if data is None:
        data, _project = _read(path)
    return _build(path, _tree(path, data))


def _build(path: Path, tree: list) -> dict:
    index = read_index(tree, project=path.with_suffix(".kicad_pro"), graphics=False)
    builder = _Builder(tree, path)
    sheet = builder.build()
    lines = ratsnest(sheet.copper)
    for start, end in lines:
        sheet.path("ratsnest", [start, end], _HAIRLINE)
    left, top, right, bottom = _frame(index, sheet.points)
    builder.board_area(index.outline)
    declared = [str(entry[1]) for entry in (sexpr.find(tree, "layers") or [])[1:] if isinstance(entry, list) and len(entry) >= 2]
    stack = list(_UNDER) + [(layer, _kind(layer)) for layer in _stack(declared, copper_layers(tree))] + list(_THROUGH)
    # The names layer stands whenever anything is named, so a view can hide a surface pad's names on its copper
    # too, and a track's (laid out by the renderer: a path with a net and a width).
    named = any(item.get("t") == "label" or is_track(item) for tiers in sheet.layers.values() for items in tiers.values() for item in items)
    layers = []
    for layer, kind in stack:
        items = sheet.items(layer)
        if not items and not _COPPER.match(layer) and not (layer == "names" and named):
            continue
        layers.append({"id": layer, "kind": kind, "side": _side(layer) if kind not in ("area", "names") else "both",
                       "items": [_shifted(item, left, top) for item in items]})
    moved = index.mapped(lambda x, y: (x - left, y - top))
    return {
        "schemaVersion": PLOT_SCHEMA_VERSION,
        "kind": "board",
        "generator": _generator(tree),
        "unrouted": len(lines),
        "sheets": [{
            "name": path.stem, "width": _num(right - left), "height": _num(bottom - top), "background": BOARD_BACKGROUND, "layers": layers,
        }],
        "board": moved.as_json(_DIGITS),
    }


def payload_bytes(payload: dict) -> bytes:
    """A payload as the JSON bytes the viewer and the snapshot read: compact, one shape, one order."""
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def plot_payload_bytes(path: Path) -> bytes:
    """Read the saved file now and return its plot; no persistent or in-memory board cache."""
    return payload_bytes(build_plot(path))
