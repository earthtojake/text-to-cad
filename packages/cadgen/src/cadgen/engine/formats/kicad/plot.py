"""A KiCad board as the picture the CAD Viewer and ``cadgen pcb snapshot`` draw: geometry per layer.

The payload (``cadgen.plot.PLOT_SCHEMA_VERSION`` 3; its contract is the core
package's ``docs/plot-payload.md``) is built from the ``.kicad_pcb`` alone: no
KiCad runs. The file is KiCad's own, and everything the picture needs is in it,
the pours' saved fills included. Authors must refill changed zones in KiCad before saving.

The board is one SHEET: millimetres, y down, KiCad's frame moved so the
board's outline sits with its top-left corner at (0, 0) -- its ``width`` and
``height`` are the outline's. The sheet is a stack of LAYERS, back to front as
seen from the top (bottom courtyard, fabrication, silkscreen, paste and mask,
bottom copper, the inner coppers deepest first, top copper, mask, paste,
silkscreen, fabrication and courtyard, the user layers, the outline), then three
layers of what goes through the board: ``vias``, the ``ratsnest`` and ``drills``.
Each layer is a list of ITEMS, each a polygon, a stroked path, a circle or a
text's strokes, in sheet millimetres:

- a pad is its padstack's outline (rect, roundrect, oval, trapezoid, chamfered,
  custom) on every copper layer it is on, carrying its pad reference (``#R1.2``)
  and net; its hole, a via's and an unplated hole are circles (or a slot's
  polygon) on ``drills``;
- a track or arc is a path of its width; a via a filled circle on ``vias``;
- a pour's fill is the polygon KiCad saved, marked ``pour`` so a view can hide
  it, and its drawn outline a hairline;
- footprint and board graphics (lines, rectangles, circles, arcs, polygons,
  curves) are paths and polygons of their stroke width, a footprint's carrying
  its part reference (``#R1``);
- text is its strokes in a permissive font (:mod:`cadgen.engine.formats.kicad.stroke_font`) at
  KiCad's position, size, angle, justification and mirroring;
- solder mask openings and paste are derived from the pads: a pad's outline
  grown by its mask margin, a pad's outline shrunk or grown by its paste margin
  (a plotter's exact offsets they are not);
- the ratsnest is cadgen's connectivity over the copper
  (:mod:`cadgen.engine.formats.kicad.connectivity`): one line per connection still to make,
  no DRC.

``board`` beside the sheet is the board's index (:mod:`cadgen.engine.formats.kicad.board_index`)
in sheet millimetres, which the viewer's tools point with (its ``origin`` is where
KiCad's (0, 0) lies on the sheet, so a reference reads back in KiCad's own frame);
``unrouted`` counts the ratsnest's lines. The payload is a function of the file's bytes: the same board
gives the same bytes; each request reads the saved file anew.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Iterable, Sequence

from cadgen.engine.formats.kicad import sexpr
from cadgen.engine.formats.kicad.board_index import (
    FootprintFrame, copper_layers, expand_copper, footprint_property, graphic, item_layers, layer_of, net_of, net_table,
    pad_shape, points_of, read_index,
)
from cadgen.engine.formats.kicad.connectivity import Copper, ratsnest
from cadgen.engine.formats.kicad.geometry import XY, box, rotate
from cadgen.engine.formats.kicad.sexpr import Sym
from cadgen.engine.formats.kicad.stroke_font import text_strokes
from cadgen.engine.formats.kicad import PLOT_SCHEMA_VERSION, PlotError

__all__ = ["BOARD_BACKGROUND", "build_plot", "payload_bytes", "plot_payload_bytes"]

#: KiCad's default colour theme behind a board.
BOARD_BACKGROUND = "#001023"
_DIGITS = 4
_GRAPHICS = ("line", "rect", "poly", "circle", "arc", "curve")
_COPPER = re.compile(r"^(F|B|In\d+)\.Cu$")
# KiCad's default text stroke, as a share of the text's height, for text that names none.
_TEXT_STROKE = 0.15
# A board with no outline is framed on everything it draws, with this much air around it.
_BARE_MARGIN = 1.0
# A pour's drawn outline, and an unplated hole's own layer.
_HAIRLINE = 0.0


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


def _inner_number(layer: str) -> int:
    return int(re.sub(r"\D", "", layer) or 0)


def _stack(declared: Sequence[str], copper: Sequence[str]) -> list[str]:
    """Every drawable layer of the board, back to front as seen from the top."""
    inner = sorted((name for name in copper if name.startswith("In")), key=_inner_number, reverse=True)
    stack = ["B.CrtYd", "B.Fab", "B.SilkS", "B.Paste", "B.Adhes", "B.Mask"]
    stack += (["B.Cu"] if "B.Cu" in copper else []) + inner + (["F.Cu"] if "F.Cu" in copper else [])
    stack += ["F.Mask", "F.Adhes", "F.Paste", "F.SilkS", "F.Fab", "F.CrtYd"]
    users = [name for name in declared if name in ("Dwgs.User", "Cmts.User", "Eco1.User", "Eco2.User") or name.startswith("User.")]
    stack += users + ["Margin", "Edge.Cuts"]
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
    """The payload being built: items filed by layer, the copper for the ratsnest, every point."""

    def __init__(self) -> None:
        self.layers: dict[str, list[dict]] = {}
        self.copper: list[Copper] = []
        self.points: list[XY] = []

    def add(self, layer: str, item: dict, points: Iterable[XY] = ()) -> None:
        self.layers.setdefault(layer, []).append(item)
        self.points.extend(points)

    def polygon(self, layer: str, points: Sequence[XY], *, width: float = 0.0, **flags) -> None:
        pts = _dedupe(points)
        if len(pts) < 3:
            return
        item = {"t": "poly", "pts": pts}
        if width > 0:
            item["w"] = width
        item.update(flags)
        self.add(layer, item, pts)

    def path(self, layer: str, points: Sequence[XY], width: float, *, closed: bool = False, **flags) -> None:
        pts = _dedupe(points)
        if len(pts) < 2:
            return
        item = {"t": "path", "pts": pts, "w": max(0.0, width)}
        if closed:
            item["closed"] = True
        item.update(flags)
        self.add(layer, item, pts)

    def circle(self, layer: str, at: XY, radius: float, *, width: float = 0.0, **flags) -> None:
        if radius <= 0:
            return
        item = {"t": "circle", "at": at, "r": radius, "w": max(0.0, width)}
        item.update(flags)
        self.add(layer, item, [(at[0] - radius, at[1] - radius), (at[0] + radius, at[1] + radius)])

    def text(self, layer: str, text: str, strokes: list[list[XY]], width: float, **flags) -> None:
        strokes = [stroke for stroke in (_dedupe(points) for points in strokes) if len(stroke) >= 2]
        if not strokes:
            return
        item = {"t": "text", "text": text, "w": width, "strokes": strokes}
        item.update(flags)
        self.add(layer, item, (point for stroke in strokes for point in stroke))


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


def _text_style(node: list) -> tuple[tuple[float, float], float, list[str]]:
    """A text's ``(effects ...)``: its size (height, width), stroke thickness and justification."""
    effects = sexpr.find(node, "effects")
    font = sexpr.find(effects, "font") if effects is not None else None
    size = sexpr.pair(sexpr.find(font, "size"), (1.0, 1.0)) if font is not None else (1.0, 1.0)
    thickness = sexpr.number(sexpr.value(font, "thickness"), 0.0) if font is not None else 0.0
    justify = [str(atom) for atom in (sexpr.find(effects, "justify") or [])[1:]] if effects is not None else []
    return (abs(size[0]), abs(size[1])), thickness or abs(size[0]) * _TEXT_STROKE, justify


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


class _Builder:
    def __init__(self, tree: list):
        self.tree = tree
        self.table = net_table(tree)
        self.copper = copper_layers(tree)
        setup = sexpr.find(tree, "setup") or []
        self.mask_margin = sexpr.number(sexpr.value(setup, "pad_to_mask_clearance"), 0.0)
        self.paste_margin = sexpr.number(sexpr.value(setup, "pad_to_paste_clearance"), 0.0)
        self.paste_ratio = sexpr.number(sexpr.value(setup, "pad_to_paste_clearance_ratio"), 0.0)
        self.sheet = _Sheet()

    # -- footprints --------------------------------------------------------------------

    def footprint(self, node: list) -> None:
        frame = FootprintFrame(node)
        ref = footprint_property(node, "Reference") or ""
        value = footprint_property(node, "Value") or ""
        fields = {str(item[1]): str(item[2]) for item in sexpr.find_all(node, "property") if len(item) >= 3}
        selector = f"#{ref}" if ref else None
        margins = (
            sexpr.value(node, "solder_mask_margin"),
            sexpr.value(node, "solder_paste_margin"),
            sexpr.value(node, "solder_paste_ratio"),
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
                self.graphic(child, frame, selector)

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
            text = str(node[2])
            which = str(node[1])
            if which == "reference":
                text = ref
            elif which == "value":
                text = value
        text = re.sub(r"\$\{([^}]+)\}", lambda match: {"REFERENCE": ref, "VALUE": value}.get(match.group(1), fields.get(match.group(1), match.group(0))), text)
        if not text.strip():
            return
        layer = layer_of(node)
        at = sexpr.find(node, "at")
        if layer is None or at is None:
            return
        position = frame.place(sexpr.pair(at, (0.0, 0.0)))
        angle = sexpr.number(at[3]) if len(at) > 3 else 0.0
        self.text(layer, text, position, angle, node, selector=f"#{ref}" if ref else None)

    def text(self, layer: str, text: str, at: XY, angle: float, node: list, *, selector: str | None = None) -> None:
        size, thickness, justify = _text_style(node)
        strokes = text_strokes(text, size=size, at=at, angle=angle, justify=justify, mirror="mirror" in justify)
        self.sheet.text(layer, text, strokes, thickness, **({"ref": selector} if selector else {}))

    def graphic(self, node: list, frame: FootprintFrame | None, selector: str | None) -> None:
        drawn = graphic(node)
        layer = layer_of(node)
        if drawn is None or layer is None:
            return
        points, closed = drawn
        if frame is not None:
            points = [frame.place(point) for point in points]
        width = _stroke_width(node)
        flags = {"ref": selector} if selector else {}
        if closed and _filled(node):
            self.sheet.polygon(layer, points, width=width, **flags)
        else:
            self.sheet.path(layer, points, width, closed=closed, **flags)

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
        hole = self.hole(drill, centre, angle, kind)
        if kind == "np_thru_hole":
            opening = hole if hole is not None else shape
        else:
            opening = shape
            for layer in expand_copper(layers, self.copper):
                self.sheet.polygon(layer, shape, **flags)
            if net:
                anchor = (centre[0] + rotate(*offset, angle)[0], centre[1] + rotate(*offset, angle)[1])
                self.sheet.copper.append(Copper.polygon(net, expand_copper(layers, self.copper), shape, anchor=anchor, pad=True))
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
                    self.sheet.polygon(layer, _scaled(shape, centre, factor), **flags)
                else:
                    self.sheet.polygon(layer, shape, width=2 * paste_margin, **flags)

    def _technical(self, layers: Sequence[str], suffix: str) -> list[str]:
        out = []
        for layer in layers:
            if layer == f"*.{suffix}":
                out.extend([f"F.{suffix}", f"B.{suffix}"])
            elif layer in (f"F.{suffix}", f"B.{suffix}"):
                out.append(layer)
        return list(dict.fromkeys(out))

    def hole(self, drill: list | None, centre: XY, angle: float, kind: str) -> list[XY] | None:
        """A pad's hole on the ``drills`` layer: a circle, or a slot's outline; answers the outline
        of what was drilled (for the mask opening of an unplated hole)."""
        if drill is None or kind not in ("thru_hole", "np_thru_hole"):
            return None
        sizes = [float(value) for value in drill[1:] if isinstance(value, (int, float))]
        if not sizes:
            return None
        offset = sexpr.pair(sexpr.find(drill, "offset"), (0.0, 0.0))
        dx, dy = rotate(offset[0], offset[1], angle)
        at = (centre[0] + dx, centre[1] + dy)
        flag = {"hole": "npth" if kind == "np_thru_hole" else "pad"}
        if any(isinstance(value, Sym) and value == "oval" for value in drill[1:]) and len(sizes) >= 2 and abs(sizes[0] - sizes[1]) > 1e-9:
            outline = [(at[0] + x, at[1] + y) for x, y in (rotate(px, py, angle) for px, py in _slot(sizes[0], sizes[1]))]
            self.sheet.polygon("drills", outline, **flag)
            return outline
        radius = sizes[0] / 2
        self.sheet.circle("drills", at, radius, **flag)
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
            from cadgen.engine.formats.kicad.geometry import arc_points

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
            if isinstance(atom, Sym) and atom in ("blind", "micro"):
                kind = str(atom)
        size = sexpr.number(sexpr.value(node, "size"), 0.0)
        drill = sexpr.number(sexpr.value(node, "drill"), 0.0)
        net = net_of(node, self.table)
        flags = {"via": kind}
        if net:
            flags["net"] = net
        self.sheet.circle("vias", at, size / 2, **flags)
        self.sheet.circle("drills", at, drill / 2, hole="via")
        spanned = item_layers(node)
        if kind == "through" or len(spanned) < 2:
            layers = list(self.copper)
        else:
            order = [layer for layer in self.copper]
            ends = sorted(order.index(layer) for layer in spanned if layer in order) or [0, len(order) - 1]
            layers = order[ends[0]:ends[-1] + 1]
        if net:
            self.sheet.copper.append(Copper.disc(net, layers, at, size))

    def zone(self, node: list) -> None:
        if sexpr.find(node, "keepout") is not None:
            return
        layers = expand_copper(item_layers(node), self.copper)
        if not layers:
            return
        net = net_of(node, self.table)
        flags = {"net": net} if net else {}
        outline = points_of(sexpr.find(sexpr.find(node, "polygon") or [], "pts"))
        fills: dict[str, list[list[XY]]] = {}
        for filled in sexpr.find_all(node, "filled_polygon"):
            layer = layer_of(filled) or layers[0]
            fills.setdefault(layer, []).append(points_of(sexpr.find(filled, "pts")))
        for layer in layers:
            for fill in fills.get(layer, []):
                self.sheet.polygon(layer, fill, pour=True, **flags)
                if net and len(fill) >= 3:
                    self.sheet.copper.append(Copper.polygon(net, [layer], fill))
            if outline:
                self.sheet.path(layer, outline, _HAIRLINE, closed=True, **flags)

    # -- the board -----------------------------------------------------------------------

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
                if len(node) > 1 and isinstance(node[1], str) and not _hidden(node):
                    layer = layer_of(node)
                    at = sexpr.find(node, "at")
                    if layer and at is not None:
                        self.text(layer, node[1], sexpr.pair(at, (0.0, 0.0)), sexpr.number(at[3]) if len(at) > 3 else 0.0, node)
            elif head and head.startswith("gr_") and head[3:] in _GRAPHICS:
                self.graphic(node, None, None)
        return self.sheet


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
    return tree


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
        elif key == "at":
            out[key] = _xy((value[0] - dx, value[1] - dy))
        elif key == "strokes":
            out[key] = [[_xy((x - dx, y - dy)) for x, y in stroke] for stroke in value]
        elif key in ("w", "r"):
            out[key] = _num(value)
        else:
            out[key] = value
    return out


def build_plot(path: Path | str) -> dict:
    """The plot payload of the board at ``path``."""
    path = _checked(Path(path))
    data, _project = _read(path)
    return _build(path, _tree(path, data))


def _build(path: Path, tree: list) -> dict:
    index = read_index(tree, project=path.with_suffix(".kicad_pro"))
    sheet = _Builder(tree).build()
    lines = ratsnest(sheet.copper)
    for start, end in lines:
        sheet.path("ratsnest", [start, end], _HAIRLINE)
    left, top, right, bottom = _frame(index, sheet.points)
    declared = [str(entry[1]) for entry in (sexpr.find(tree, "layers") or [])[1:] if isinstance(entry, list) and len(entry) >= 2]
    stack = _stack(declared, copper_layers(tree)) + ["vias", "ratsnest", "drills"]
    layers = []
    for layer in stack:
        items = sheet.layers.get(layer, [])
        if not items and not _COPPER.match(layer):
            continue
        kind = {"vias": "via", "ratsnest": "ratsnest", "drills": "drill"}.get(layer) or _kind(layer)
        layers.append({"id": layer, "kind": kind, "side": _side(layer), "items": [_shifted(item, left, top) for item in items]})
    moved = index.mapped(lambda x, y: (x - left, y - top))
    return {
        "schemaVersion": PLOT_SCHEMA_VERSION,
        "kind": "board",
        "generator": _generator(tree),
        "unrouted": len(lines),
        "sheets": [{"name": path.stem, "width": _num(right - left), "height": _num(bottom - top), "background": BOARD_BACKGROUND, "layers": layers}],
        "board": moved.as_json(_DIGITS),
    }


def payload_bytes(payload: dict) -> bytes:
    """A payload as the JSON bytes the viewer and the snapshot read: compact, one shape, one order."""
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def plot_payload_bytes(path: Path) -> bytes:
    """Read the saved file now and return its plot; no persistent or in-memory board cache."""
    return payload_bytes(build_plot(path))
