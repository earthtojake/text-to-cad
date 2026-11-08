"""A KiCad schematic as plot geometry: each sheet a page of layers, drawn from the files alone.

``build_schematic_plot(path)`` reads the schematic's hierarchy (:mod:`.schematic`) and draws every
sheet instance from its file's own geometry: each symbol from the drawing the file embeds
(``lib_symbols``), placed by its transform, its pins (their names and numbers as the symbol shows
them), its shown fields; the wires, buses and bus entries, junctions and no-connects; the labels
(local, global, hierarchical) and their flags; the hierarchical sheets' boxes, names and pins; and
the free text and graphics. Text is the board's stroke font, Hershey Simplex
(:mod:`.stroke_font`), at KiCad's positions and sizes: same places, different glyphs. The page's
edge is a layer of its own (``page``), which a view leaves off unless asked; KiCad's drawing sheet
(its frame and title block) is not drawn.

The payload is the board's plot payload's shape (``packages/core/docs/plot-payload.md``), with
pages for sheets: ``kind: "schematic"``, one entry of ``sheets`` per sheet instance in page order,
each in KiCad's own frame (mm, y down, the page's top-left corner at (0, 0); ``width`` and
``height`` the page's), its layers bottom to top, each item one of the board's primitives
(``path``, ``poly``, ``circle``, ``text``). What a layer is drawn in is the renderer's (its
``kind``); an item may carry ``fill: "background"`` (a symbol body's fill, KiCad's device
background), ``color`` (a colour the file gives it, ``#rrggbb``, with ``opacity``), ``ref`` (the
reference of what drew it: ``#R1``, ``#R1.2`` a pin), ``net`` and ``id`` (the uuid KiCad saved it
with). ``schematic`` is the index (:meth:`.schematic.SchematicIndex.as_json`).
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Iterable, Sequence

from cad.engine.formats.kicad import PLOT_SCHEMA_VERSION, sexpr
from cad.engine.formats.kicad.geometry import arc_points, bezier_points
from cad.engine.formats.kicad.schematic import (
    BUS_WIDTH, JUNCTION_DIAMETER, NO_CONNECT_SIZE, WIRE_WIDTH, LibPin, LibSymbol, SchematicIndex, Symbol,
    read_schematic_index, screen_transform, symbol_transform,
)
from cad.engine.formats.kicad.sexpr import Sym
from cad.engine.formats.kicad.stroke_font import text_strokes

__all__ = ["LAYERS", "SCHEMATIC_BACKGROUND", "build_schematic_plot", "schematic_payload_bytes"]

#: The layers, bottom to top: ``(id, kind)``.
LAYERS = (
    ("page", "sheet"), ("notes", "notes"), ("sheets", "sheet_box"), ("symbols", "symbol"), ("pins", "pin"),
    ("wires", "wire"), ("buses", "bus"), ("junctions", "junction"), ("no_connects", "no_connect"),
    ("pin_numbers", "pin_number"), ("pin_names", "pin_name"), ("fields", "field"), ("labels", "label"),
)
#: KiCad's schematic background, its default theme's.
SCHEMATIC_BACKGROUND = "#F5F4EF"
_DIGITS = 4
_TEXT_MARGIN = 0.1016  # KiCad's PIN_TEXT_MARGIN, 4 mils: a pin's text off its line
_INVERT_RADIUS = 0.381  # an inverted pin's bubble
_CLOCK_SIZE = 0.508


def _r(value: float) -> float:
    return round(float(value), _DIGITS) + 0.0


def _pt(point) -> list[float]:
    return [_r(point[0]), _r(point[1])]


def _pts(points: Iterable) -> list[list[float]]:
    return [_pt(point) for point in points]


def _effects(node: list | None) -> dict[str, Any]:
    """A text's effects: size (height, width), stroke width, justification, bold, italic, hidden."""
    effects = sexpr.find(node, "effects") if node is not None else None
    font = sexpr.find(effects, "font") if effects is not None else None
    size = sexpr.pair(sexpr.find(font, "size"), (1.27, 1.27)) if font is not None else (1.27, 1.27)
    bold = font is not None and (str(sexpr.value(font, "bold", "")) == "yes" or any(
        isinstance(atom, Sym) and atom == "bold" for atom in font[1:]))
    italic = font is not None and (str(sexpr.value(font, "italic", "")) == "yes" or any(
        isinstance(atom, Sym) and atom == "italic" for atom in font[1:]))
    thickness = sexpr.number(sexpr.value(font, "thickness"), 0.0) if font is not None else 0.0
    height = abs(size[0])
    width = thickness or (height / 5 if bold else min(WIRE_WIDTH, height / 6))
    justify = [str(atom) for atom in (sexpr.find(effects, "justify") or [])[1:]] if effects is not None else []
    hidden = effects is not None and (str(sexpr.value(effects, "hide", "")) == "yes" or any(
        isinstance(atom, Sym) and atom == "hide" for atom in effects[1:]))
    hidden = hidden or (node is not None and (str(sexpr.value(node, "hide", "")) == "yes" or any(
        isinstance(atom, Sym) and atom == "hide" for atom in node[1:])))
    return {"size": (height, abs(size[1])), "w": width, "justify": justify, "italic": italic, "hidden": hidden}


def _stroke(node: list, default: float = WIRE_WIDTH) -> tuple[float, str | None, float]:
    """A stroke's width (its default for 0), its colour (``#rrggbb``, None for the theme's) and its opacity."""
    stroke = sexpr.find(node, "stroke")
    width = sexpr.number(sexpr.value(stroke, "width"), 0.0) if stroke is not None else sexpr.number(
        sexpr.value(node, "width"), 0.0)
    color, opacity = _color(sexpr.find(stroke, "color")) if stroke is not None else (None, 1.0)
    return (width if width > 0 else default), color, opacity


def _color(node: list | None) -> tuple[str | None, float]:
    if node is None or len(node) < 5:
        return None, 1.0
    r, g, b, a = (sexpr.number(value) for value in node[1:5])
    if a <= 0:
        return None, 1.0
    return f"#{int(r):02X}{int(g):02X}{int(b):02X}", a


def _fill(node: list) -> tuple[str, str | None, float]:
    """A shape's fill: ``none``, ``outline`` (its stroke's colour), ``background`` or ``color``."""
    fill = sexpr.find(node, "fill")
    if fill is None:
        return "none", None, 1.0
    kind = str(sexpr.value(fill, "type", "none"))
    color, opacity = _color(sexpr.find(fill, "color"))
    if kind == "color" and color is None:
        kind = "none"
    if kind == "none" and color is not None:  # a sheet's fill: (fill (color ...)) with no type
        kind = "color"
    return kind, color, opacity


def _with_color(item: dict, color: str | None, opacity: float) -> dict:
    if color is not None:
        item["color"] = color
        if opacity < 1:
            item["opacity"] = _r(opacity)
    return item


def _text(text: str, at, angle: float, effects: dict, *, justify: Sequence[str] | None = None, **flags) -> dict | None:
    if not text or effects["hidden"]:
        return None
    strokes = text_strokes(text, size=effects["size"], at=at, angle=angle,
                           justify=effects["justify"] if justify is None else justify, italic=effects["italic"])
    if not strokes:
        return None
    # A letter's strokes to the micrometre: the text is most of a page's payload.
    return {"t": "text", "text": text, "w": _r(effects["w"]),
            "strokes": [[[round(x, 3) + 0.0, round(y, 3) + 0.0] for x, y in stroke] for stroke in strokes], **flags}


def _shape(node: list, place, default_width: float, *, closed_box=None, **flags) -> list[dict]:
    """A graphic (``polyline``, ``rectangle``, ``circle``, ``arc``, ``bezier``) as plot items, its points
    mapped by ``place``."""
    head = sexpr.head(node)
    width, color, opacity = _stroke(node, default_width)
    fill, fill_color, fill_opacity = _fill(node)
    closed = False
    if head == "polyline":
        points = [sexpr.pair(xy) for xy in sexpr.find_all(sexpr.find(node, "pts") or [], "xy")]
        closed = len(points) > 2 and points[0] == points[-1]
    elif head == "rectangle":
        start, end = sexpr.pair(sexpr.find(node, "start"), (0.0, 0.0)), sexpr.pair(sexpr.find(node, "end"), (0.0, 0.0))
        points = [start, (end[0], start[1]), end, (start[0], end[1]), start]
        closed = True
    elif head == "circle":
        center = sexpr.pair(sexpr.find(node, "center"), (0.0, 0.0))
        radius = sexpr.number(sexpr.value(node, "radius"), 0.0)
        points = [(center[0] + radius * math.cos(2 * math.pi * k / 48), center[1] + radius * math.sin(2 * math.pi * k / 48))
                  for k in range(49)]
        closed = True
    elif head == "arc":
        start = sexpr.pair(sexpr.find(node, "start"), (0.0, 0.0))
        mid = sexpr.pair(sexpr.find(node, "mid"), None)
        end = sexpr.pair(sexpr.find(node, "end"), (0.0, 0.0))
        points = arc_points(start, mid, end) if mid is not None else [start, end]
    elif head == "bezier":
        points = bezier_points([sexpr.pair(xy) for xy in sexpr.find_all(sexpr.find(node, "pts") or [], "xy")])
    else:
        return []
    placed = [place(point) for point in points]
    if len(placed) < 2:
        return []
    items: list[dict] = []
    if fill != "none" and len(placed) > 2:
        item = {"t": "poly", "pts": _pts(placed[:-1] if closed else placed), **flags}
        if fill == "background":
            item["fill"] = "background"
        elif fill == "color":
            _with_color(item, fill_color, fill_opacity)
        else:
            _with_color(item, color, opacity)
        items.append(item)
    items.append(_with_color({"t": "path", "pts": _pts(placed), "w": _r(width), **({"closed": True} if closed else {}),
                              **flags}, color, opacity))
    return items


# --- symbols -------------------------------------------------------------------------------------


def _pin_geometry(symbol: Symbol, pin: LibPin):
    """A pin's tip and body end on the sheet, and its direction from the tip to the body."""
    transform = symbol_transform(symbol.angle, symbol.mirror)
    radians = math.radians(pin.angle)
    end_lib = (pin.at[0] + pin.length * math.cos(radians), pin.at[1] + pin.length * math.sin(radians))
    tip = transform(pin.at)
    end = transform(end_lib)
    tip = (symbol.at[0] + tip[0], symbol.at[1] + tip[1])
    end = (symbol.at[0] + end[0], symbol.at[1] + end[1])
    length = math.hypot(end[0] - tip[0], end[1] - tip[1])
    direction = ((end[0] - tip[0]) / length, (end[1] - tip[1]) / length) if length > 1e-9 else (1.0, 0.0)
    return tip, end, direction


def _pin_items(symbol: Symbol, lib: LibSymbol, pin: LibPin, net: str | None, layers: dict[str, list]) -> None:
    from cad.engine.formats.kicad.refs import selector_or_none

    tip, end, (dx, dy) = _pin_geometry(symbol, pin)
    ref = selector_or_none("pad", ref=symbol.ref, pad=pin.number)
    flags = {**({"ref": ref} if ref else {}), **({"net": net} if net else {})}
    line_end = end
    if pin.shape in ("inverted", "inverted_clock"):
        line_end = (end[0] - dx * 2 * _INVERT_RADIUS, end[1] - dy * 2 * _INVERT_RADIUS)
        center = (end[0] - dx * _INVERT_RADIUS, end[1] - dy * _INVERT_RADIUS)
        layers["pins"].append({"t": "circle", "at": _pt(center), "r": _r(_INVERT_RADIUS), "w": _r(WIRE_WIDTH), **flags})
    if pin.length > 0:
        layers["pins"].append({"t": "path", "pts": _pts([tip, line_end]), "w": _r(WIRE_WIDTH), **flags})
    if pin.shape in ("clock", "inverted_clock", "clock_low", "edge_clock_high"):
        nx, ny = -dy, dx
        points = [(end[0] + nx * _CLOCK_SIZE, end[1] + ny * _CLOCK_SIZE), (end[0] + dx * _CLOCK_SIZE, end[1] + dy * _CLOCK_SIZE),
                  (end[0] - nx * _CLOCK_SIZE, end[1] - ny * _CLOCK_SIZE)]
        layers["pins"].append({"t": "path", "pts": _pts(points), "w": _r(WIRE_WIDTH), **flags})
    horizontal = abs(dx) >= abs(dy)
    angle = 0.0 if horizontal else 90.0
    # "Above" a pin's line: up the page for a horizontal pin, to the left for a vertical one (its text turned).
    above = (0.0, -1.0) if horizontal else (-1.0, 0.0)
    middle = ((tip[0] + end[0]) / 2, (tip[1] + end[1]) / 2)
    name = pin.name if pin.name and pin.name != "~" else ""
    show_names = name and not lib.pin_names_hidden
    show_numbers = pin.number and not lib.pin_numbers_hidden
    number_size = pin.number_size[0]
    name_size = pin.name_size[0]
    if show_names and lib.pin_names_offset > 0:
        # Inside the body, past its end, justified away from the pin; the number above the line.
        at = (end[0] + dx * lib.pin_names_offset, end[1] + dy * lib.pin_names_offset)
        forward = dx > 0 if horizontal else dy < 0  # a vertical pin's text reads up the page
        item = _text(name, at, angle, _plain(pin.name_size), justify=["left" if forward else "right"], **flags)
        if item:
            layers["pin_names"].append(item)
        if show_numbers:
            off = _TEXT_MARGIN + number_size / 2 + WIRE_WIDTH / 2
            item = _text(pin.number, (middle[0] + above[0] * off, middle[1] + above[1] * off), angle,
                         _plain(pin.number_size), justify=[], **flags)
            if item:
                layers["pin_numbers"].append(item)
        return
    if show_names:
        off = _TEXT_MARGIN + name_size / 2 + WIRE_WIDTH / 2
        item = _text(name, (middle[0] + above[0] * off, middle[1] + above[1] * off), angle, _plain(pin.name_size),
                     justify=[], **flags)
        if item:
            layers["pin_names"].append(item)
    if show_numbers:
        off = _TEXT_MARGIN + number_size / 2 + WIRE_WIDTH / 2
        sign = -1 if show_names else 1
        item = _text(pin.number, (middle[0] + sign * above[0] * off, middle[1] + sign * above[1] * off), angle,
                     _plain(pin.number_size), justify=[], **flags)
        if item:
            layers["pin_numbers"].append(item)


def _plain(size: tuple[float, float]) -> dict[str, Any]:
    return {"size": size, "w": min(WIRE_WIDTH, size[0] / 6), "justify": [], "italic": False, "hidden": False}


def _field_items(symbol: Symbol, node: list) -> list[dict]:
    """A placed symbol's shown fields, each where KiCad draws it. The file holds a field's position as
    drawn (KiCad's ``SCH_FIELD::GetPosition``: the symbol's transform already applied) and its angle and
    justification as the unturned symbol has them: so its box -- its text laid at its position, justified,
    turned by its own angle -- is mirrored about its position and turned by the symbol's transform there,
    and its text centred in that box, horizontal, or vertical where the symbol's quarter turn makes it so."""
    from cad.engine.formats.kicad.refs import selector_or_none

    items = []
    transform = screen_transform(symbol.angle, symbol.mirror)
    turned = abs(math.sin(math.radians(symbol.angle))) > 0.5
    ref = selector_or_none("part", ref=symbol.ref)
    for prop in sexpr.find_all(node, "property"):
        if len(prop) < 3:
            continue
        name, text = str(prop[1]), str(prop[2])
        if name == "Reference":
            text = symbol.ref
        effects = _effects(prop)
        if effects["hidden"] or not text or sexpr.find(prop, "at") is None:
            continue
        at_node = sexpr.find(prop, "at")
        at = (sexpr.number(at_node[1]), sexpr.number(at_node[2]))
        own = sexpr.number(at_node[3]) if len(at_node) > 3 else 0.0
        strokes = text_strokes(text, size=effects["size"], at=at, angle=own, justify=effects["justify"])
        points = [p for stroke in strokes for p in stroke]
        if not points:
            continue
        cx = (min(p[0] for p in points) + max(p[0] for p in points)) / 2
        cy = (min(p[1] for p in points) + max(p[1] for p in points)) / 2
        moved = transform((cx - at[0], cy - at[1]))
        center = (at[0] + moved[0], at[1] + moved[1])
        horizontal = abs(math.sin(math.radians(own))) < 0.5
        if turned:
            horizontal = not horizontal
        item = _text(text, center, 0.0 if horizontal else 90.0, effects, justify=[],
                     field=name, **({"ref": ref} if ref else {}))
        if item:
            items.append(item)
    return items


def _symbol_items(symbol: Symbol, lib: LibSymbol | None, node: list, nets: dict[str, str | None],
                  layers: dict[str, list]) -> None:
    from cad.engine.formats.kicad.refs import selector_or_none

    ref = selector_or_none("part", ref=symbol.ref)
    flags = {**({"ref": ref} if ref else {}), **({"id": symbol.uuid} if symbol.uuid else {})}
    if lib is not None:
        transform = symbol_transform(symbol.angle, symbol.mirror)

        def place(point):
            x, y = transform(point)
            return symbol.at[0] + x, symbol.at[1] + y

        graphics = [g for g in lib.graphics if g[0] in (0, symbol.unit) and g[1] in (0, symbol.body_style)]
        # Fills first, under every outline, as KiCad draws a body's background behind its lines.
        drawn = []
        for _unit, _style, item in graphics:
            if sexpr.head(item) in ("text", "text_box"):
                continue
            drawn += _shape(item, place, WIRE_WIDTH, **flags)
        layers["symbols"] += [item for item in drawn if item["t"] == "poly"] + [item for item in drawn if item["t"] != "poly"]
        for _unit, _style, item in graphics:
            if sexpr.head(item) == "text":
                effects = _effects(item)
                at_node = sexpr.find(item, "at") or [Sym("at"), 0, 0, 0]
                own = sexpr.number(at_node[3]) if len(at_node) > 3 else 0.0
                own = own / 10 if abs(own) > 360 else own
                horizontal = (abs(math.sin(math.radians(own))) < 0.5) != (abs(math.sin(math.radians(symbol.angle))) > 0.5)
                text = _text(str(item[1]), place((sexpr.number(at_node[1]), sexpr.number(at_node[2]))),
                             0.0 if horizontal else 90.0, effects, justify=[], **flags)
                if text:
                    layers["symbols"].append(text)
        for pin in lib.pins:
            if pin.unit not in (0, symbol.unit) or pin.style not in (0, symbol.body_style) or pin.hidden:
                continue
            _pin_items(symbol, lib, pin, nets.get(pin.number), layers)
    layers["fields"] += _field_items(symbol, node)


# --- labels and sheets ---------------------------------------------------------------------------


def _direction(angle: float) -> tuple[float, float]:
    """The way a label's body runs from its anchor: angle 0 to the right, 90 up the page."""
    radians = math.radians(angle)
    return round(math.cos(radians), 9), round(-math.sin(radians), 9)


def _text_length(text: str, size: float) -> float:
    strokes = text_strokes(text, size=(size, size), justify=["left"])
    xs = [point[0] for stroke in strokes for point in stroke]
    return (max(xs) - min(xs)) if xs else 0.0


def _flag(shape: str | None, length: float, height: float, near: float = 0.0) -> list[tuple[float, float]]:
    """A label's flag outline in its own frame, the anchor at (0, 0), its body along +x: ``input``
    points at the anchor, ``output`` away, ``bidirectional`` and ``tri_state`` both ways, ``passive`` none."""
    half = height / 2
    tip = half if shape in ("input", "bidirectional", "tri_state") else 0.0
    far = half if shape in ("output", "bidirectional", "tri_state") else 0.0
    points = [(near, 0.0)] if tip else []
    points += [(near + tip, -half), (near + tip + length, -half)]
    points += [(near + tip + length + far, 0.0)] if far else []
    points += [(near + tip + length, half), (near + tip, half)]
    if not tip:
        points = [(near, -half), *points[1:], (near, half)]
    return points + [points[0]]


def _label_items(label, layers: dict[str, list], net: str | None) -> None:
    size = label.size
    effects = {"size": (size, size), "w": min(WIRE_WIDTH, size / 6), "justify": [], "italic": False, "hidden": False}
    dx, dy = _direction(label.angle)
    horizontal = abs(dx) >= abs(dy)
    angle = 0.0 if horizontal else 90.0
    flags = {"label": label.kind, **({"net": net} if net else {}), **({"id": label.uuid} if label.uuid else {})}
    x, y = label.at
    if label.kind == "local":
        # Its text sits on its wire, starting at its anchor, read the right way up.
        lift = size * 0.15 + WIRE_WIDTH
        forward = dx > 0 if horizontal else dy < 0
        at = (x, y - lift) if horizontal else (x - lift, y)
        item = _text(label.text, at, angle, effects, justify=["left" if forward else "right", "bottom"], **flags)
        if item:
            layers["labels"].append(item)
        return
    length = _text_length(label.text, size)
    if label.kind == "global":
        height = size * 1.6
        margin = size * 0.4
        outline = _flag(label.shape, length + 2 * margin, height)
        tip = height / 2 if label.shape in ("input", "bidirectional", "tri_state") else 0.0
        middle = tip + margin + length / 2
    else:  # hierarchical: a small flag at the anchor, the text after it
        height = size
        outline = _flag(label.shape, 0.0 if label.shape in ("input", "output", "bidirectional", "tri_state") else size / 2,
                        height)
        reach = max(point[0] for point in outline)
        middle = reach + size * 0.3 + length / 2
    # Its own frame turned onto the page: along (dx, dy), across (-dy, dx) for a horizontal label.
    placed = [(x + px * dx - py * dy, y + px * dy + py * dx) for px, py in outline]
    layers["labels"].append({"t": "path", "pts": _pts(placed), "w": _r(WIRE_WIDTH), "closed": True, **flags})
    center = (x + dx * middle, y + dy * middle)
    item = _text(label.text, center, angle, effects, **flags, justify=[])
    if item:
        layers["labels"].append(item)


def _sheet_items(sheet, node: list, layers: dict[str, list]) -> None:
    from cad.engine.formats.kicad.schematic_refs import format_sheet_selector

    if sheet.at is None or sheet.size is None:
        return
    (x, y), (w, h) = sheet.at, sheet.size
    flags = {"ref": format_sheet_selector(sheet.path), **({"id": sheet.uuid} if sheet.uuid else {})}
    width, color, opacity = _stroke(node, WIRE_WIDTH)
    box = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
    fill, fill_color, fill_opacity = _fill(node)
    if fill == "color" and fill_color:
        layers["sheets"].append(_with_color({"t": "poly", "pts": _pts(box), **flags}, fill_color, fill_opacity))
    layers["sheets"].append(_with_color({"t": "path", "pts": _pts(box + [box[0]]), "w": _r(width), "closed": True,
                                         **flags}, color, opacity))
    for prop in sexpr.find_all(node, "property"):
        if len(prop) < 3 or sexpr.find(prop, "at") is None:
            continue
        name = str(prop[1])
        role = "name" if name in ("Sheetname", "Sheet name") else "file" if name in ("Sheetfile", "Sheet file") else "field"
        text = str(prop[2]) if role != "file" else f"File: {prop[2]}"
        at_node = sexpr.find(prop, "at")
        item = _text(text, (sexpr.number(at_node[1]), sexpr.number(at_node[2])),
                     sexpr.number(at_node[3]) if len(at_node) > 3 else 0.0, _effects(prop), role=role, **flags)
        if item:
            layers["sheets"].append(item)
    for pin_node, pin in zip(sexpr.find_all(node, "pin"), sheet.pins):
        effects = _effects(pin_node)
        size = effects["size"][0]
        # A sheet pin's flag points into the box from its edge; its text runs on, inside the box.
        dx, dy = _direction(pin.angle + 180)
        horizontal = abs(dx) >= abs(dy)
        outline = _flag(pin.shape, 0.0, size)
        placed = [(pin.at[0] + px * dx - py * dy, pin.at[1] + px * dy + py * dx) for px, py in outline]
        pin_flags = {**flags, "role": "pin", **({"net": pin.net} if pin.net else {})}
        layers["sheets"].append({"t": "path", "pts": _pts(placed), "w": _r(WIRE_WIDTH), "closed": True, **pin_flags})
        reach = max(point[0] for point in outline) + size * 0.3
        length = _text_length(pin.name, size)
        center = (pin.at[0] + dx * (reach + length / 2), pin.at[1] + dy * (reach + length / 2))
        item = _text(pin.name, center, 0.0 if horizontal else 90.0, {**effects, "justify": []}, justify=[], **pin_flags)
        if item:
            layers["sheets"].append(item)


# --- the payload ---------------------------------------------------------------------------------


def _page_layers(index: SchematicIndex, sheet) -> list[dict]:
    layers: dict[str, list] = {layer_id: [] for layer_id, _kind in LAYERS}
    width, height = sheet.paper
    layers["page"].append({"t": "path", "pts": _pts([(0, 0), (width, 0), (width, height), (0, height), (0, 0)]), "w": 0,
                           "closed": True, "page": True})
    tree = index.trees.get(sheet.file)
    if tree is None:
        return [{"id": layer_id, "kind": kind, "side": "both", "items": layers[layer_id]} for layer_id, kind in LAYERS
                if layers[layer_id] or layer_id == "page"]
    library = index.lib_symbols.get(sheet.file, {})
    symbols = iter(symbol for symbol in index.symbols if symbol.sheet == sheet.path)
    # A sheet block is its own child sheet, by uuid: the index lists the children by page, and KiCad saves
    # the blocks in another order (by uuid), so a block's pins are never another sheet's.
    children = [child for child in index.sheets if child.parent == sheet.path]
    by_uuid = {child.uuid: child for child in children if child.uuid}
    unnamed = iter(child for child in children if not child.uuid)
    for node in tree[1:]:
        head = sexpr.head(node)
        if head == "symbol":
            symbol = next(symbols, None)
            if symbol is None:
                continue
            lib_name = str(sexpr.value(node, "lib_name", "") or "") or symbol.lib_id
            lib = library.get(lib_name) or library.get(symbol.lib_id)
            _symbol_items(symbol, lib, node, {pin.number: pin.net for pin in symbol.pins}, layers)
        elif head == "sheet":
            uuid = _id(node)
            child = by_uuid.get(uuid) if uuid else next(unnamed, None)
            if child is not None:
                _sheet_items(child, node, layers)
        elif head in ("polyline", "rectangle", "circle", "arc", "bezier"):
            layers["notes"] += _shape(node, lambda point: point, WIRE_WIDTH, **({"id": _id(node)} if _id(node) else {}))
        elif head == "text":
            at_node = sexpr.find(node, "at") or [Sym("at"), 0, 0, 0]
            item = _text(str(node[1]), (sexpr.number(at_node[1]), sexpr.number(at_node[2])),
                         sexpr.number(at_node[3]) if len(at_node) > 3 else 0.0, _effects(node),
                         **({"id": _id(node)} if _id(node) else {}))
            if item:
                layers["notes"].append(item)
        elif head == "text_box":
            at = sexpr.pair(sexpr.find(node, "at"), (0.0, 0.0))
            size = sexpr.pair(sexpr.find(node, "size"), (0.0, 0.0))
            box = [Sym("rectangle"), [Sym("start"), at[0], at[1]], [Sym("end"), at[0] + size[0], at[1] + size[1]],
                   *(child for child in node[1:] if sexpr.head(child) in ("stroke", "fill"))]
            layers["notes"] += _shape(box, lambda point: point, WIRE_WIDTH)
            effects = _effects(node)
            item = _text(str(node[1]), (at[0] + size[0] / 2, at[1] + size[1] / 2), 0.0, effects, justify=[])
            if item:
                layers["notes"].append(item)
    for wire in index.wires:
        if wire.sheet != sheet.path:
            continue
        layer = "wires" if wire.kind == "wire" else "buses"
        layers[layer].append({"t": "path", "pts": _pts(wire.points), "w": _r(WIRE_WIDTH if wire.kind == "wire" else BUS_WIDTH),
                              **({"net": wire.net} if wire.net else {}), **({"id": wire.uuid} if wire.uuid else {})})
    for entry in index.bus_entries:
        if entry.sheet == sheet.path:
            layers["buses"].append({"t": "path", "pts": _pts(entry.points), "w": _r(WIRE_WIDTH),
                                    **({"id": entry.uuid} if entry.uuid else {})})
    for junction in index.junctions:
        if junction.sheet == sheet.path:
            layers["junctions"].append({"t": "circle", "at": _pt(junction.at), "r": _r(JUNCTION_DIAMETER / 2), "w": 0,
                                        **({"net": junction.net} if junction.net else {}),
                                        **({"id": junction.uuid} if junction.uuid else {})})
    for item in index.no_connects:
        if item.sheet == sheet.path:
            half = NO_CONNECT_SIZE / 2
            (x, y) = item.at
            layers["no_connects"].append({"t": "path", "pts": _pts([(x - half, y - half), (x + half, y + half),
                                                                     (x - half, y + half), (x + half, y - half)]),
                                          "w": _r(WIRE_WIDTH), "pairs": True, **({"id": item.uuid} if item.uuid else {})})
    for label in index.labels:
        if label.sheet == sheet.path and label.kind not in ("power", "local_power"):
            _label_items(label, layers, label.net)
    return [{"id": layer_id, "kind": kind, "side": "both", "items": layers[layer_id]} for layer_id, kind in LAYERS
            if layers[layer_id] or layer_id == "page"]


def _id(node: list) -> str | None:
    found = sexpr.value(node, "uuid")
    return str(found).lower() if found else None


def build_schematic_plot(path: Path | str, *, sheets: Sequence[str] | None = None,
                         index: bool = True, read: tuple[SchematicIndex, list[str]] | None = None) -> dict[str, Any]:
    """The plot payload of the schematic hierarchy ``path`` belongs to (the module doc): every sheet
    instance a page, in page order; ``sheets`` (paths, ``/Power/``) draws those alone, and ``index``
    False leaves the index out (a still draws without it). ``read`` is the hierarchy already read
    (:func:`.schematic.read_schematic_index`'s answer for ``path``), which a caller that keeps it
    passes so the files are not parsed again."""
    read, warnings = read if read is not None else read_schematic_index(path)
    pages = []
    wanted = None if sheets is None else {_canonical(path_) for path_ in sheets}
    for sheet in read.sheets:
        if wanted is not None and sheet.path not in wanted:
            continue
        width, height = sheet.paper
        pages.append({"name": sheet.name, "path": sheet.path, "number": sheet.page, "file": sheet.file.name,
                      "title": dict(sheet.title), "width": _r(width), "height": _r(height),
                      "background": SCHEMATIC_BACKGROUND, "page": [0.0, 0.0, _r(width), _r(height)],
                      "layers": _page_layers(read, sheet)})
    if wanted is not None and len(pages) != len(wanted):
        known = ", ".join(sheet.path for sheet in read.sheets)
        missing = ", ".join(sorted(wanted - {page["path"] for page in pages}))
        raise ValueError(f"{read.root.name} has no sheet {missing}; its sheets are {known}")
    return {"schemaVersion": PLOT_SCHEMA_VERSION, "kind": "schematic", "generator": read.generator,
            "sheets": pages, "warnings": list(warnings), **({"schematic": read.as_json()} if index else {})}


def _canonical(path: str) -> str:
    parts = [part for part in str(path).split("/") if part]
    return "/" + "".join(f"{part}/" for part in parts)


def schematic_payload_bytes(path: Path | str, *, sheets: Sequence[str] | None = None, index: bool = True,
                            read: tuple[SchematicIndex, list[str]] | None = None) -> bytes:
    """The payload as compact JSON bytes, as the viewer's route answers it (``build_schematic_plot``'s
    ``sheets``, ``index`` and ``read``)."""
    return json.dumps(build_schematic_plot(path, sheets=sheets, index=index, read=read), separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")
