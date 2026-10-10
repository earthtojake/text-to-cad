"""Any KiCad 10 schematic, read as what a person can point at, and schematic references answered.

:func:`read_index` reads a ``.kicad_sch`` and every sheet under it -- cadgen's
net-label schematics and hierarchies drawn in KiCad alike -- into its sheets,
parts (symbols, with their fields and the units placed on each sheet), pins,
wires, labels, junctions, no-connect flags and nets. KiCad names the nets: its
netlist (``kicad-cli sch export netlist``, :func:`export_netlist`) says which
net each pin is on, and everything drawn takes the net of the pins it is wired
to. :func:`read_schematic` (``pcb.read_schematic``) answers schematic
references (:mod:`cadgen.kicad.refs`) against that index:
``schematic.resolve("#U3.9")`` is pin 9 of U3, its net, and through its part
the script line that made it.

Sheets
------
A hierarchy is read as KiCad reads it: each ``(sheet ...)`` names a file,
relative to the folder of the file that holds it, and a file used by two sheets
is two SHEET INSTANCES, each with its own references (a symbol's ``instances``
entry for that instance's path of UUIDs). A sheet instance is named as
KiCad's ``sch export svg`` names its plot, ``<root>-<Sheet>-<Subsheet>.svg``,
less ``<root>-`` (the root: its file's stem), so a sheet here and a sheet of the
plot payload (:mod:`cadgen.kicad.plot`) share a name; both are in KiCad's page
order: the root, then by page number (sheets of one page as KiCad lists them,
depth first). A sheet file may lie in another folder (``sheets/power.kicad_sch``,
``../common/io.kicad_sch``): :func:`hierarchy_files` finds every file a
schematic reads, which a plot or a netlist stages together.

Frames
------
Everything is in the SHEET frame, KiCad's own for a schematic: millimetres, y
down, from the corner of the sheet's page. It is also the frame of KiCad's SVG
plot of the sheet (one SVG unit is one millimetre: an A3 page plots
``viewBox="0 0 419.989 297.0022"``). A library symbol is drawn y up; a library
point (x, y) lands on the sheet at the symbol's ``at`` plus (x, -y) turned by
the symbol's angle counter-clockwise on the sheet ((-y, -x) at 90), THEN
mirrored -- ``(mirror x)`` flips y, ``(mirror y)`` flips x -- as KiCad reads a
symbol: held to KiCad's netlist for every angle and mirror.

Connections, as KiCad makes them: things touch where their connection points
meet (a wire's ends, a pin's point, a label's anchor, a junction, a sheet pin);
a label or a junction on a wire's middle joins that wire, and a wire end or a
pin on a wire's middle does not (KiCad's editor puts a junction at such a T; a
file without one is two nets). Labels of one name are one net: a local or
hierarchical label on its sheet instance, a hierarchical label with its sheet's
pin of that name in the parent, a global label and a power symbol everywhere (a
power flag, whose pin is no power input, names nothing). Net names are
unescaped as KiCad displays them (``TX/RX``, never ``TX{slash}RX``), as a
board's are.
"""

from __future__ import annotations

import math
import os
import re
import tempfile
import unicodedata
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from cadgen.kicad import sexpr
from cadgen.kicad.geometry import XY, arc_points, box, format_xy, nm
from cadgen.kicad.naming import natural, netclass_of, project_netclasses, unescape_net_name
from cadgen.kicad.refs import BoardSelector, ReferenceView, format_board_selector, selector_or_none

__all__ = [
    "Junction",
    "Label",
    "Net",
    "NoConnect",
    "Part",
    "Pin",
    "SchematicIndex",
    "SchematicView",
    "Sheet",
    "Unit",
    "Wire",
    "export_netlist",
    "hierarchy_files",
    "read_index",
    "read_schematic",
]

_IU = 10_000  # KiCad's schematic unit is 100 nm: points meet when they agree to it
_TEXT_SIZE = 1.27  # KiCad's default text height, mm
_LABEL_HEIGHT = 1.6  # a label's pickable box, in text heights
_CHARACTER = 0.8  # a generous width of KiCad's stroke font, in text heights per character
_GRAPHICS = ("rectangle", "polyline", "circle", "arc", "bezier")
_DIRECTIONS = {0: (1.0, 0.0), 90: (0.0, 1.0), 180: (-1.0, 0.0), 270: (0.0, -1.0)}
_NETLIST = "cadgen-netlist.net"


# --- what a schematic holds ---------------------------------------------------------


@dataclass(frozen=True)
class Sheet:
    """One sheet instance. ``name`` is its plot's (the root: the file's stem); ``path`` the human
    path KiCad prefixes its local nets with (``/``, ``/Power/``); ``file`` the file it shows."""

    name: str
    path: str
    file: str
    title: str
    instance: str = field(default="", repr=False)  # KiCad's path of UUIDs: "/<root>/<sheet>"


@dataclass(frozen=True)
class Unit:
    """One unit of a part, placed on a sheet. ``outline`` is the box round its body."""

    unit: int
    sheet: int  # index into the schematic's sheets
    at: XY
    rotation: int  # 0, 90, 180 or 270: degrees counter-clockwise on the sheet
    mirror: str | None  # "x" (flipped top to bottom) or "y" (left to right), applied after the rotation
    outline: tuple[XY, ...]


@dataclass(frozen=True)
class Pin:
    """One pin of a placed unit. ``at`` is where a wire connects; ``end`` where it meets the body."""

    part: str
    number: str
    name: str | None  # the pin's name, when it has one
    type: str  # its electrical type: "passive", "power_in"...
    unit: int
    sheet: int
    net: str | None
    at: XY
    end: XY
    hidden: bool = False

    kind = "pin"

    @property
    def selector(self) -> str | None:
        """``#U3.9``; ``None`` for a pin the language cannot name (no number, or one with a dot)."""
        return selector_or_none("pad", ref=self.part, pad=self.number)

    def __repr__(self) -> str:
        name = f" ({self.name})" if self.name and self.name != self.number else ""
        return f"Pin({self.part}.{self.number}{name}, {self.type}, net={self.net!r}, sheet {self.sheet}, at={format_xy(self.at)})"


@dataclass(frozen=True)
class Part:
    """A symbol, by its reference designator, with every unit of it placed on a sheet."""

    ref: str
    value: str
    lib: str  # the library id: "Device:R"
    footprint: str
    fields: Mapping[str, str]  # every field but Reference, Value and Footprint with something in it, Script included
    dnp: bool
    units: tuple[Unit, ...] = ()
    pins: tuple[Pin, ...] = ()

    kind = "part"

    @property
    def script(self) -> str | None:
        """The script line that made the part, ``"board.py:183"`` (relative to the model script's
        folder), from its ``Script`` field; ``None`` for a part no cadgen script made."""
        return self.fields.get("Script")

    @property
    def selector(self) -> str | None:
        return selector_or_none("part", ref=self.ref)

    def pin(self, number: str) -> Pin:
        """The part's pin ``number`` (the first, when several units draw it)."""
        for pin in self.pins:
            if pin.number == str(number):
                return pin
        numbers = ", ".join(sorted({pin.number for pin in self.pins if pin.number}, key=natural)) or "none"
        raise ValueError(f"{self.ref} has no pin {number}; its pins are {numbers}")

    def __repr__(self) -> str:
        made = f", script={self.script!r}" if self.script else ""
        sheets = sorted({unit.sheet for unit in self.units})
        return (
            f"Part({self.ref}, value={self.value!r}, lib={self.lib!r}, footprint={self.footprint!r}, "
            f"{len(self.units)} unit(s) on sheet {', '.join(str(sheet) for sheet in sheets) or '-'}{made})"
        )


@dataclass(frozen=True)
class Wire:
    net: str | None
    sheet: int
    points: tuple[XY, ...]

    def __repr__(self) -> str:
        return f"Wire({self.net!r} on sheet {self.sheet}, {format_xy(self.points[0])} -> {format_xy(self.points[-1])})"


@dataclass(frozen=True)
class Label:
    """A net label, or a power symbol (``kind`` "power", its text the symbol's value).
    ``at`` is where it connects; ``outline`` a box round what it draws, generous."""

    net: str | None
    sheet: int
    text: str
    kind: str  # "local", "global", "hierarchical" or "power"
    at: XY
    outline: tuple[XY, ...]

    def __repr__(self) -> str:
        return f"Label({self.kind} {self.text!r}, net={self.net!r}, sheet {self.sheet}, at={format_xy(self.at)})"


@dataclass(frozen=True)
class Junction:
    net: str | None
    sheet: int
    at: XY


@dataclass(frozen=True)
class NoConnect:
    """KiCad's ``X`` on a pin left unconnected: the pin it marks, when one is there."""

    sheet: int
    at: XY
    part: str | None = None
    pin: str | None = None


@dataclass(frozen=True)
class Net:
    """A net and everything on it."""

    name: str
    netclass: str
    pins: tuple[Pin, ...] = ()
    parts: tuple[Part, ...] = ()
    labels: tuple[Label, ...] = ()
    wires: tuple[Wire, ...] = ()

    kind = "net"

    @property
    def selector(self) -> str:
        return format_board_selector("net", net=self.name)

    @property
    def nodes(self) -> tuple[str, ...]:
        """Its pins as references read, ``("R1.2", "U3.9")``, each once."""
        return tuple(dict.fromkeys(f"{pin.part}.{pin.number}" for pin in self.pins))

    def __repr__(self) -> str:
        nodes = self.nodes
        shown = ", ".join(nodes[:8]) + (f" and {len(nodes) - 8} more" if len(nodes) > 8 else "")
        return f"Net({self.name!r}, class {self.netclass!r}: {shown or 'no pins'}; {len(self.labels)} labels, {len(self.wires)} wires)"


@dataclass(frozen=True)
class SchematicIndex:
    """A schematic, every sheet of it, in the sheet frame."""

    sheets: tuple[Sheet, ...]
    parts: tuple[Part, ...]
    wires: tuple[Wire, ...]
    labels: tuple[Label, ...]
    junctions: tuple[Junction, ...]
    no_connects: tuple[NoConnect, ...]
    nets: tuple[tuple[str, str], ...]  # (name, class), in natural order

    @property
    def pins(self) -> tuple[Pin, ...]:
        return tuple(pin for part in self.parts for pin in part.pins)

    def aligned(self, names: Sequence[str]) -> "SchematicIndex":
        """The same schematic on the sheets ``names`` (a plot's), in that order: an item is moved
        to its sheet's new place, a sheet not named is dropped with what is on it, and a name no
        sheet has gets an empty sheet."""
        found = {sheet.name: index for index, sheet in enumerate(self.sheets)}
        moved = {found[name]: index for index, name in enumerate(names) if name in found}
        sheets = tuple(
            self.sheets[found[name]] if name in found else Sheet(name=name, path="", file="", title="")
            for name in names
        )

        def keep(items):
            return tuple(replace(item, sheet=moved[item.sheet]) for item in items if item.sheet in moved)

        parts = tuple(replace(part, units=keep(part.units), pins=keep(part.pins)) for part in self.parts)
        return replace(
            self,
            sheets=sheets,
            parts=tuple(part for part in parts if part.units),
            wires=keep(self.wires),
            labels=keep(self.labels),
            junctions=keep(self.junctions),
            no_connects=keep(self.no_connects),
        )

    def as_json(self, digits: int = 4) -> dict:
        """The index as a schematic plot payload's ``schematic``: every point in the sheet frame,
        rounded to ``digits`` decimals (a tenth of a micron at 4)."""

        def num(value: float) -> float:
            rounded = round(float(value), digits)
            return 0.0 if rounded == 0 else rounded

        def xy(point: XY) -> list[float]:
            return [num(point[0]), num(point[1])]

        def path(points: Iterable[XY]) -> list[list[float]]:
            return [xy(point) for point in points]

        return {
            "sheets": [{"name": sheet.name, "path": sheet.path, "file": sheet.file, "title": sheet.title} for sheet in self.sheets],
            "parts": [
                {
                    "ref": part.ref, "value": part.value, "lib": part.lib, "footprint": part.footprint,
                    "fields": dict(part.fields), "script": part.script, "dnp": part.dnp,
                    "units": [
                        {
                            "unit": unit.unit, "sheet": unit.sheet, "at": xy(unit.at), "rotation": unit.rotation,
                            "mirror": unit.mirror, "outline": path(unit.outline),
                        }
                        for unit in part.units
                    ],
                }
                for part in self.parts
            ],
            "pins": [
                {
                    "part": pin.part, "number": pin.number, "name": pin.name, "type": pin.type, "unit": pin.unit,
                    "sheet": pin.sheet, "net": pin.net, "at": xy(pin.at), "end": xy(pin.end), "hidden": pin.hidden,
                }
                for pin in self.pins
            ],
            "wires": [{"net": wire.net, "sheet": wire.sheet, "points": path(wire.points)} for wire in self.wires],
            "labels": [
                {
                    "net": label.net, "sheet": label.sheet, "text": label.text, "kind": label.kind,
                    "at": xy(label.at), "outline": path(label.outline),
                }
                for label in self.labels
            ],
            "junctions": [{"net": junction.net, "sheet": junction.sheet, "at": xy(junction.at)} for junction in self.junctions],
            "noConnects": [
                {"sheet": flag.sheet, "at": xy(flag.at), "part": flag.part, "pin": flag.pin} for flag in self.no_connects
            ],
            "nets": [{"name": name, "class": netclass} for name, netclass in self.nets],
        }


# --- reading a document -------------------------------------------------------------------


def _angle(node: list | None) -> float:
    return sexpr.number(node[3]) if node is not None and len(node) > 3 else 0.0


def _key(point: XY) -> tuple[int, int]:
    """A point to KiCad's 100 nm: two points meet when their keys do."""
    return round(point[0] * _IU), round(point[1] * _IU)


def _properties(node: list) -> dict[str, str]:
    return {str(item[1]): str(item[2]) for item in sexpr.find_all(node, "property") if len(item) >= 3}


def _hidden(node: list) -> bool:
    hide = sexpr.find(node, "hide")
    if hide is not None:
        return len(hide) < 2 or hide[1] == "yes"
    return any(item == "hide" for item in node[1:] if isinstance(item, sexpr.Sym))  # an older file's bare `hide`


def _text(node: list | None) -> str:
    return str(node[1]) if node is not None and len(node) > 1 and not isinstance(node[1], list) else ""


class _Place:
    """A placed symbol's frame: where a library point (y up) lands on the sheet (y down)."""

    def __init__(self, at: XY, rotation: int, mirror: str | None):
        self.at, self.rotation, self.mirror = at, rotation, mirror

    def __call__(self, point: XY) -> XY:
        x, y = point[0], -point[1]
        if self.rotation == 90:
            x, y = y, -x
        elif self.rotation == 180:
            x, y = -x, -y
        elif self.rotation == 270:
            x, y = -y, x
        elif self.rotation:
            angle = math.radians(self.rotation)
            x, y = x * math.cos(angle) + y * math.sin(angle), -x * math.sin(angle) + y * math.cos(angle)
        if self.mirror == "x":
            y = -y
        elif self.mirror == "y":
            x = -x
        return nm(self.at[0] + x), nm(self.at[1] + y)


def _drawn_unit(name: str) -> tuple[int, int] | None:
    """``"R_1_1"`` -> ``(1, 1)``: the unit and body style a library sub-symbol draws."""
    pieces = name.rsplit("_", 2)
    if len(pieces) != 3:
        return None
    try:
        return int(pieces[1]), int(pieces[2])
    except ValueError:
        return None


def _drawings(library: list, unit: int, style: int) -> Iterable[list]:
    """The library symbol's sub-symbols drawn for ``unit`` and body ``style`` (0 means every one)."""
    for sub in sexpr.find_all(library, "symbol"):
        drawn = _drawn_unit(str(sub[1]))
        if drawn is not None and drawn[0] in (0, unit) and drawn[1] in (0, style):
            yield sub


def _graphic_points(item: list) -> list[XY]:
    head = sexpr.head(item)
    if head == "rectangle":
        start, end = sexpr.pair(sexpr.find(item, "start")), sexpr.pair(sexpr.find(item, "end"))
        return [start, end] if start and end else []
    if head in ("polyline", "bezier"):  # a bezier lies inside the box of its control points
        return [sexpr.pair(xy) for xy in sexpr.find_all(sexpr.find(item, "pts") or [], "xy")]
    if head == "circle":
        center, radius = sexpr.pair(sexpr.find(item, "center")), sexpr.number(sexpr.value(item, "radius"))
        return [(center[0] - radius, center[1] - radius), (center[0] + radius, center[1] + radius)] if center else []
    if head == "arc":
        start, mid, end = (sexpr.pair(sexpr.find(item, key)) for key in ("start", "mid", "end"))
        if start and mid and end:
            return arc_points(start, mid, end)
        return [point for point in (start, end) if point]
    return []


@dataclass(frozen=True)
class _LibraryPin:
    number: str
    name: str | None
    type: str
    at: XY
    end: XY
    hidden: bool


def _library_pins(library: list, unit: int, style: int) -> list[_LibraryPin]:
    """The pins a unit draws, in the library's frame: a pin's angle points from where a wire
    connects into the body, ``length`` long."""
    pins = []
    for sub in _drawings(library, unit, style):
        for node in sexpr.find_all(sub, "pin"):
            at = sexpr.find(node, "at")
            point = sexpr.pair(at) or (0.0, 0.0)
            angle = _angle(at) % 360
            length = sexpr.number(sexpr.value(node, "length"))
            dx, dy = _DIRECTIONS.get(angle) or (math.cos(math.radians(angle)), math.sin(math.radians(angle)))
            name = _text(sexpr.find(node, "name"))
            pins.append(_LibraryPin(
                number=_text(sexpr.find(node, "number")),
                name=name if name and name != "~" else None,
                type=str(node[1]) if len(node) > 1 and not isinstance(node[1], list) else "unspecified",
                at=point,
                end=(point[0] + dx * length, point[1] + dy * length),
                hidden=_hidden(node),
            ))
    return pins


@dataclass
class _Symbol:
    """A placed symbol on one sheet instance, before nets."""

    ref: str
    unit: int
    lib: str
    power: str | None  # "global" or "local" for a power symbol
    properties: dict[str, str]
    dnp: bool
    placement: Unit
    pins: list[tuple[_LibraryPin, XY, XY]]  # (library pin, at, end) on the sheet


@dataclass(frozen=True)
class _DrawnLabel:
    kind: str
    text: str  # as the file stores it: "TX{slash}RX"
    at: XY
    outline: tuple[XY, ...]


@dataclass
class _Drawn:
    """One sheet instance's connectable things, before nets."""

    symbols: list[_Symbol] = field(default_factory=list)
    wires: list[tuple[XY, XY]] = field(default_factory=list)
    labels: list[_DrawnLabel] = field(default_factory=list)
    junctions: list[XY] = field(default_factory=list)
    no_connects: list[XY] = field(default_factory=list)
    sheet_pins: dict[str, list[tuple[str, XY]]] = field(default_factory=dict)  # a sub-sheet's uuid: its pins


def _library_symbols(tree: list) -> dict[str, list]:
    table = sexpr.find(tree, "lib_symbols")
    return {str(node[1]): node for node in sexpr.find_all(table or [], "symbol") if len(node) > 1}


def _instance(node: list, instance: str) -> tuple[str | None, int | None]:
    """The reference and unit a placed symbol has in the sheet instance ``instance``."""
    for project in sexpr.find_all(sexpr.find(node, "instances") or [], "project"):
        for entry in sexpr.find_all(project, "path"):
            if len(entry) > 1 and str(entry[1]) == instance:
                reference = sexpr.value(entry, "reference")
                unit = sexpr.value(entry, "unit")
                return (str(reference) if reference is not None else None), (int(unit) if isinstance(unit, (int, float)) else None)
    return None, None


def _place_symbol(node: list, libraries: Mapping[str, list], instance: str, sheet: int) -> _Symbol | None:
    lib_id = str(sexpr.value(node, "lib_id") or "")
    library = libraries.get(str(sexpr.value(node, "lib_name") or lib_id))
    if library is None:
        return None
    at_node = sexpr.find(node, "at")
    at = sexpr.pair(at_node) or (0.0, 0.0)
    rotation = round(_angle(at_node)) % 360
    mirror_node = sexpr.find(node, "mirror")
    mirror = str(mirror_node[1]) if mirror_node is not None and len(mirror_node) > 1 else None
    properties = _properties(node)
    reference, unit = _instance(node, instance)
    unit = unit or int(sexpr.number(sexpr.value(node, "unit"), 1))
    style = int(sexpr.number(sexpr.value(node, "body_style") or sexpr.value(node, "convert"), 1))
    place = _Place(at, rotation, mirror if mirror in ("x", "y") else None)
    pins = _library_pins(library, unit, style)
    body = [point for sub in _drawings(library, unit, style) for item in sub[2:] if sexpr.head(item) in _GRAPHICS for point in _graphic_points(item)]
    if not body:  # a unit that draws nothing but its pins is outlined by them
        body = [point for pin in pins for point in (pin.at, pin.end)]
    power = sexpr.find(library, "power")
    return _Symbol(
        ref=reference or properties.get("Reference", ""),
        unit=unit,
        lib=lib_id,
        power=(str(power[1]) if len(power) > 1 else "global") if power is not None else None,
        properties=properties,
        dnp=str(sexpr.value(node, "dnp") or "no") == "yes",
        placement=Unit(
            unit=unit, sheet=sheet, at=(nm(at[0]), nm(at[1])), rotation=rotation, mirror=place.mirror,
            outline=tuple(box(place(point) for point in body)),
        ),
        pins=[(pin, place(pin.at), place(pin.end)) for pin in pins],
    )


def _label_outline(kind: str, text: str, at: XY, angle: float, justify: set[str], size: float) -> tuple[XY, ...]:
    """A box round what a label draws, from its anchor along its text: KiCad's stroke font
    estimated generously, and a global or hierarchical label's shape at the anchor."""
    length = (_CHARACTER * len(text) + _CHARACTER) * size
    if kind in ("global", "hierarchical"):
        length += size
    upright = round(angle) % 180
    if justify & {"left", "right"}:
        backward = "right" in justify
    else:
        backward = round(angle) % 360 in (180, 270)
    if upright == 0:
        forward, up = ((-1.0, 0.0) if backward else (1.0, 0.0)), (0.0, -1.0)
    else:
        forward, up = ((0.0, 1.0) if backward else (0.0, -1.0)), (-1.0, 0.0)
    height = _LABEL_HEIGHT * size
    low, high = (-0.25 * size, height) if kind == "local" else (-height / 2, height / 2)
    return tuple(
        (nm(at[0] + forward[0] * along + up[0] * across), nm(at[1] + forward[1] * along + up[1] * across))
        for along, across in ((0.0, low), (length, low), (length, high), (0.0, high))
    )


_LABELS = {"label": "local", "global_label": "global", "hierarchical_label": "hierarchical"}


def _read_sheet(tree: list, instance: str, sheet: int) -> _Drawn:
    drawn = _Drawn()
    libraries = _library_symbols(tree)
    for node in tree[1:]:
        head = sexpr.head(node)
        if head == "symbol":
            symbol = _place_symbol(node, libraries, instance, sheet)
            if symbol is not None:
                drawn.symbols.append(symbol)
        elif head == "wire":
            points = [sexpr.pair(xy) for xy in sexpr.find_all(sexpr.find(node, "pts") or [], "xy")]
            drawn.wires.extend((a, b) for a, b in zip(points, points[1:]) if a and b)
        elif head in _LABELS:
            at_node = sexpr.find(node, "at")
            at = sexpr.pair(at_node) or (0.0, 0.0)
            effects = sexpr.find(node, "effects") or []
            size = sexpr.find(sexpr.find(effects, "font") or [], "size")
            justify = sexpr.find(effects, "justify")
            outline = _label_outline(
                _LABELS[head], unescape_net_name(_text(node)), at, _angle(at_node), {str(item) for item in (justify or [])[1:]},
                sexpr.number(size[1], _TEXT_SIZE) if size is not None and len(size) > 1 else _TEXT_SIZE,
            )
            drawn.labels.append(_DrawnLabel(_LABELS[head], _text(node), (nm(at[0]), nm(at[1])), outline))
        elif head == "junction":
            at = sexpr.pair(sexpr.find(node, "at"))
            if at:
                drawn.junctions.append(at)
        elif head == "no_connect":
            at = sexpr.pair(sexpr.find(node, "at"))
            if at:
                drawn.no_connects.append(at)
        elif head == "sheet":
            pins = [(_text(pin), sexpr.pair(sexpr.find(pin, "at"))) for pin in sexpr.find_all(node, "pin")]
            drawn.sheet_pins[str(sexpr.value(node, "uuid") or "")] = [(name, at) for name, at in pins if at]
    return drawn


# --- the hierarchy ------------------------------------------------------------------------


@dataclass
class _SheetInstance:
    sheet: Sheet
    tree: list
    names: tuple[str, ...]  # the sheet names from the root down: the plot names the sheet after them
    parent: int | None = None
    uuid: str = ""  # its sheet symbol's uuid in the parent
    page: str = ""  # the page number KiCad gives this instance


def _plot_name(stem: str, names: Sequence[str]) -> str:
    """The sheet's name as its plot is named: KiCad's ``<root>-<Sheet>-<Subsheet>.svg`` less ``<root>-``,
    composed (Unicode NFC), as the plot's names are read whatever form the platform wrote."""
    name = "-".join(names).replace("/", "_").replace("\\", "_") if names else stem
    return unicodedata.normalize("NFC", name)


def _decoded(path: Path, data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError(f"{path.name} is not a readable KiCad schematic: it is not UTF-8 text") from None


def _parse(path: Path) -> list:
    try:
        tree = sexpr.parse(_decoded(path, path.read_bytes()))
    except sexpr.SexprError as error:
        raise ValueError(f"{path.name} is not a readable KiCad schematic ({error})") from None
    if sexpr.head(tree) != "kicad_sch":
        raise ValueError(f"{path.name} is not a KiCad schematic: a .kicad_sch starts with (kicad_sch ...)")
    return tree


def _title(tree: list) -> str:
    return str(sexpr.value(sexpr.find(tree, "title_block") or [], "title") or "")


def _page(node: list, parent_instance: str) -> str:
    """The page number of the sheet ``node`` in its parent's instance ``parent_instance``."""
    for project in sexpr.find_all(sexpr.find(node, "instances") or [], "project"):
        for entry in sexpr.find_all(project, "path"):
            if len(entry) > 1 and str(entry[1]) == parent_instance:
                return str(sexpr.value(entry, "page") or "")
    return ""


def _page_order(page: str) -> tuple:
    """KiCad's order of page numbers: whole numbers first, by value; any other after, naturally."""
    try:
        return (0, int(page), ())
    except ValueError:
        return (1, 0, natural(page))


def _hierarchy(root: Path) -> tuple[list[_SheetInstance], list[Path]]:
    """Every sheet instance under ``root`` in KiCad's page order, and every file they show (each
    once, the root first).

    The order is the one KiCad pages and plots a schematic in: the root first, then by page
    number; sheets of one page (or none) in the order KiCad lists them, depth first, a sheet's
    own sheets by where they sit on it (left to right, then top to bottom).
    """
    trees: dict[Path, list] = {}

    def load(path: Path) -> list:
        key = path.resolve()
        if key not in trees:
            trees[key] = _parse(path)
        return trees[key]

    root = Path(root)
    tree = load(root)
    instances = [_SheetInstance(
        sheet=Sheet(name=_plot_name(root.stem, ()), path="/", file=root.name, title=_title(tree), instance=f"/{sexpr.value(tree, 'uuid') or ''}"),
        tree=tree, names=(),
    )]

    def visit(parent: int, folder: Path, above: tuple[Path, ...]) -> None:
        outer = instances[parent]
        children = []
        for node in sexpr.find_all(outer.tree, "sheet"):
            properties = _properties(node)
            name = properties.get("Sheetname", properties.get("Sheet name", ""))
            file = properties.get("Sheetfile", properties.get("Sheet file", ""))
            path = Path(file) if os.path.isabs(file) else folder / file
            if not file or path.suffix.lower() != ".kicad_sch" or not path.is_file() or path.resolve() in above:
                continue  # KiCad cannot show it either
            children.append((_key(sexpr.pair(sexpr.find(node, "at")) or (0.0, 0.0)), str(sexpr.value(node, "uuid") or ""), name, file, path, node))
        for _at, uuid, name, file, path, node in sorted(children, key=lambda child: child[:2]):
            sheet_tree = load(path)
            instances.append(_SheetInstance(
                sheet=Sheet(
                    name=_plot_name(root.stem, (*outer.names, name)),
                    path=f"{outer.sheet.path}{name}/",
                    file=file,
                    title=_title(sheet_tree),
                    instance=f"{outer.sheet.instance}/{uuid}",
                ),
                tree=sheet_tree, names=(*outer.names, name), parent=parent, uuid=uuid,
                page=_page(node, outer.sheet.instance),
            ))
            visit(len(instances) - 1, path.parent, (*above, path.resolve()))

    visit(0, root.parent, (root.resolve(),))
    order = [0] + sorted(range(1, len(instances)), key=lambda index: (_page_order(instances[index].page), index))
    position = {old: new for new, old in enumerate(order)}
    ordered = [
        replace(instances[old], parent=position[instances[old].parent] if instances[old].parent is not None else None)
        for old in order
    ]
    files = list(dict.fromkeys(trees))
    return ordered, files


_SHEET_FILE = re.compile(r'\(property\s+"Sheet ?file"\s+"((?:[^"\\]|\\.)*)"')


def hierarchy_files(root: Path) -> list[tuple[Path, bytes]]:
    """Every file KiCad reads with the schematic whose root sheet is ``root``, with its bytes,
    each read once: the root, every sheet file under it (each once), and the project and symbol
    table beside the root. Paths are absolute, the root's first.

    The sheets are found by their ``Sheetfile`` fields, not by parsing, so the plot's cache key
    (these bytes) costs a request no parse; a sheet named but missing is left out, as KiCad
    shows it empty, and so is a file that is no ``.kicad_sch``: a document never has another
    file read for it.
    """
    root = Path(os.path.abspath(root))
    found: dict[Path, bytes] = {}
    pending = [root]
    while pending:
        path = pending.pop(0)
        if path in found:
            continue
        found[path] = path.read_bytes()
        for name in _SHEET_FILE.findall(_decoded(path, found[path])):
            sheet = Path(sexpr._unescape(name))
            sheet = Path(os.path.abspath(sheet if sheet.is_absolute() else path.parent / sheet))
            if sheet.suffix.lower() == ".kicad_sch" and sheet not in found and sheet.is_file():
                pending.append(sheet)
    for extra in (root.with_suffix(".kicad_pro"), root.parent / "sym-lib-table"):
        if extra.is_file():
            found[extra] = extra.read_bytes()
    return list(found.items())


# --- connections ---------------------------------------------------------------------------


class _Links:
    """Union-find: what is connected to what."""

    def __init__(self):
        self.parent: dict = {}

    def find(self, key):
        self.parent.setdefault(key, key)
        while self.parent[key] != key:
            self.parent[key] = self.parent[self.parent[key]]
            key = self.parent[key]
        return key

    def join(self, a, b) -> None:
        a, b = self.find(a), self.find(b)
        if a != b:
            self.parent[max(a, b, key=repr)] = min(a, b, key=repr)


def _on_wire(point: tuple[int, int], a: tuple[int, int], b: tuple[int, int]) -> bool:
    """Whether ``point`` lies on the wire from ``a`` to ``b`` (KiCad's units: exact)."""
    (px, py), (ax, ay), (bx, by) = point, a, b
    if (bx - ax) * (py - ay) != (by - ay) * (px - ax):
        return False
    return min(ax, bx) <= px <= max(ax, bx) and min(ay, by) <= py <= max(ay, by)


_CELL = 254_000  # a grid cell for finding wires near a point: 25.4 mm in KiCad's units
_CELLS_PER_WIRE = 64  # a wire whose box covers more cells is checked against every point


def _wires_near(wires: Sequence[tuple[tuple[int, int], tuple[int, int]]]):
    """``near(point)``: the wires whose box could hold ``point``. Each wire is filed under the grid
    cells its box covers, so a sheet's points are not each checked against all its wires."""
    cells: dict[tuple[int, int], list[int]] = {}
    everywhere: list[int] = []
    for number, (a, b) in enumerate(wires):
        (x0, x1), (y0, y1) = sorted((a[0] // _CELL, b[0] // _CELL)), sorted((a[1] // _CELL, b[1] // _CELL))
        if (x1 - x0 + 1) * (y1 - y0 + 1) > _CELLS_PER_WIRE:
            everywhere.append(number)
            continue
        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                cells.setdefault((x, y), []).append(number)

    def near(point: tuple[int, int]) -> list[int]:
        return cells.get((point[0] // _CELL, point[1] // _CELL), []) + everywhere

    return near


def _connect(drawn: _Drawn, sheet: int, links: _Links) -> None:
    """Join what touches on one sheet instance, keyed ``(sheet, ...)``."""
    wires = [(_key(a), _key(b)) for a, b in drawn.wires]
    for number, (a, b) in enumerate(wires):
        links.join((sheet, "wire", number), (sheet, *a))
        links.join((sheet, "wire", number), (sheet, *b))
    for symbol in drawn.symbols:
        for _pin, at, _end in symbol.pins:
            links.find((sheet, *_key(at)))
    # A label or a junction on a wire's middle joins it; a wire end or a pin there does not.
    near = _wires_near(wires)
    for point in [label.at for label in drawn.labels] + drawn.junctions:
        key = _key(point)
        links.find((sheet, *key))
        for number in near(key):
            if _on_wire(key, *wires[number]):
                links.join((sheet, *key), (sheet, "wire", number))
    for pins in drawn.sheet_pins.values():
        for _name, at in pins:
            links.find((sheet, *_key(at)))


# --- nets ------------------------------------------------------------------------------------


def _read_netlist(netlist: str | list) -> tuple[dict[tuple[str, str], str], dict[str, str]]:
    """KiCad's netlist (``kicadsexpr``): each pin's net by (reference, number), and each net's
    class (of a net in several, ``Power,Default``, the first: KiCad lists the strongest first)."""
    tree = sexpr.parse(netlist) if isinstance(netlist, str) else netlist
    pins: dict[tuple[str, str], str] = {}
    classes: dict[str, str] = {}
    for net in sexpr.find_all(sexpr.find(tree, "nets") or [], "net"):
        name = unescape_net_name(str(sexpr.value(net, "name") or ""))
        if not name:
            continue
        netclass = sexpr.value(net, "class")
        classes[name] = str(netclass).split(",")[0].strip() if netclass else ""
        for node in sexpr.find_all(net, "node"):
            pins.setdefault((str(sexpr.value(node, "ref") or ""), str(sexpr.value(node, "pin") or "")), name)
    return pins, classes


# Which label names a net when several could, as KiCad chooses: a global label, a global power
# symbol, a local label or local power symbol, then a hierarchical label; alike, the first name.
_PRIORITY = {"global": 0, "power": 1, "local": 2, "power local": 2, "hierarchical": 3}


def _label_net(kind: str, text: str, sheet: Sheet) -> str:
    name = unescape_net_name(text)
    return name if kind in ("global", "power") else f"{sheet.path}{name}"


def read_index(root: Path | str, *, netlist: str | list | None = None, project: Path | None = None) -> SchematicIndex:
    """The schematic whose root sheet is ``root``, every sheet under it, as an index.

    ``netlist`` is KiCad's netlist of it (``kicadsexpr``, its text or parsed tree:
    :func:`export_netlist`): each pin's net is KiCad's, and what is drawn takes the net of the
    pins it is wired to, else of the labels on it. Without one, every net is what the labels
    name -- exact for cadgen's net-label schematics, where every connected pin has a global
    label; a pin wired to no label has none. ``project`` is the ``.kicad_pro``, read for the
    classes of nets the netlist does not class. Raises ``ValueError`` for a file that is not a
    KiCad schematic.
    """
    instances, _files = _hierarchy(Path(root))
    return _index(instances, netlist=netlist, project=project)


def _index(instances: list[_SheetInstance], *, netlist, project: Path | None) -> SchematicIndex:
    sheets = [instance.sheet for instance in instances]
    drawn = [_read_sheet(instance.tree, instance.sheet.instance, number) for number, instance in enumerate(instances)]
    links = _Links()  # what touches on a sheet: a group's root is its key
    for number, sheet in enumerate(drawn):
        _connect(sheet, number, links)
    across = _Links()  # groups one net by name, across sheets

    def group(sheet: int, point: XY):
        found = links.find((sheet, *_key(point)))
        across.find(found)
        return found

    def wire_group(sheet: int, number: int):
        found = links.find((sheet, "wire", number))
        across.find(found)
        return found

    # Labels of one name are one net: a global label or global power symbol everywhere, a local
    # or hierarchical label (or a local power symbol) on its sheet instance. A hierarchical
    # label is also its sheet's pin of that name, in the parent.
    named: dict[tuple, list] = {}
    drivers: dict = {}  # a group: the names its labels give it, (priority, sheet depth, name)

    def drive(found, kind: str, text: str, number: int) -> None:
        scope = ("global", text) if kind in ("global", "power") else (number, text)
        named.setdefault(scope, []).append(found)
        sheet = sheets[number]
        drivers.setdefault(found, []).append((_PRIORITY[kind], sheet.path.count("/"), _label_net(kind, text, sheet)))

    for number, sheet in enumerate(drawn):
        for label in sheet.labels:
            drive(group(number, label.at), label.kind, label.text, number)
        for symbol in sheet.symbols:
            for pin, at, _end in symbol.pins if symbol.power is not None else ():
                if pin.type == "power_in":  # a power flag's pin drives a net without naming it
                    kind = "power local" if symbol.power == "local" else "power"
                    drive(group(number, at), kind, symbol.properties.get("Value", ""), number)
    for members in named.values():
        for member in members[1:]:
            across.join(members[0], member)
    for number, instance in enumerate(instances):
        if instance.parent is None:
            continue
        for pin_name, at in drawn[instance.parent].sheet_pins.get(instance.uuid, []):
            for label in drawn[number].labels:
                if label.kind == "hierarchical" and label.text == pin_name:
                    across.join(group(instance.parent, at), group(number, label.at))

    pin_nets, classes = _read_netlist(netlist) if netlist is not None else ({}, {})
    # Each group's net: KiCad's for a pin in it, else for a pin anywhere its labels reach, else
    # the name its labels give (a local one only when KiCad has that net).
    known: dict = {}
    for number, sheet in enumerate(drawn):
        for symbol in sorted(sheet.symbols, key=lambda symbol: natural(symbol.ref)):
            if symbol.power is not None or symbol.ref.startswith("#"):
                continue
            for pin, at, _end in sorted(symbol.pins, key=lambda entry: natural(entry[0].number)):
                net = pin_nets.get((symbol.ref, pin.number))
                if net is not None:
                    known.setdefault(group(number, at), net)
    merged: dict = {}
    for found, net in known.items():
        merged.setdefault(across.find(found), net)
    by_label: dict = {}
    for found, options in drivers.items():
        whole = across.find(found)
        by_label.setdefault(whole, []).extend(options)

    def net_of(found) -> str | None:
        if found in known:
            return known[found]
        whole = across.find(found)
        if whole in merged:
            return merged[whole]
        for priority, _depth, name in sorted(by_label.get(whole, ())):
            if netlist is None or name in classes or priority < _PRIORITY["local"]:
                return name
        return None

    parts: dict[str, dict] = {}
    labels: list[Label] = []
    wires: list[Wire] = []
    junctions: list[Junction] = []
    flags: list[NoConnect] = []
    for number, sheet in enumerate(drawn):
        pin_at: dict[tuple[int, int], tuple[str, str]] = {}
        for symbol in sheet.symbols:
            if symbol.power is not None:
                if symbol.pins:
                    labels.append(Label(
                        net=net_of(group(number, symbol.pins[0][1])), sheet=number,
                        text=unescape_net_name(symbol.properties.get("Value", "")), kind="power",
                        at=symbol.pins[0][1], outline=symbol.placement.outline,
                    ))
                continue
            if symbol.ref.startswith("#"):
                continue
            entry = parts.setdefault(symbol.ref, {"symbols": [], "pins": []})
            entry["symbols"].append(symbol)
            for pin, at, end in sorted(symbol.pins, key=lambda entry: natural(entry[0].number)):
                net = pin_nets.get((symbol.ref, pin.number)) or net_of(group(number, at))
                entry["pins"].append(Pin(
                    part=symbol.ref, number=pin.number, name=pin.name, type=pin.type, unit=symbol.unit,
                    sheet=number, net=net, at=at, end=end, hidden=pin.hidden,
                ))
                pin_at.setdefault(_key(at), (symbol.ref, pin.number))
        for label in sheet.labels:
            labels.append(Label(
                net=net_of(group(number, label.at)), sheet=number, text=unescape_net_name(label.text),
                kind=label.kind, at=label.at, outline=label.outline,
            ))
        for index, (a, b) in enumerate(sheet.wires):
            wires.append(Wire(net=net_of(wire_group(number, index)), sheet=number, points=(a, b)))
        for at in sheet.junctions:
            junctions.append(Junction(net=net_of(group(number, at)), sheet=number, at=at))
        for at in sheet.no_connects:
            ref, pin = pin_at.get(_key(at), (None, None))
            flags.append(NoConnect(sheet=number, at=at, part=ref, pin=pin))

    built = []
    for ref in sorted(parts, key=natural):
        symbols = sorted(parts[ref]["symbols"], key=lambda symbol: (symbol.unit, symbol.placement.sheet))
        first = symbols[0]
        fields = {
            name: value for name, value in first.properties.items()
            if name not in ("Reference", "Value", "Footprint") and value
        }
        built.append(Part(
            ref=ref,
            value=first.properties.get("Value", ""),
            lib=first.lib,
            footprint=first.properties.get("Footprint", ""),
            fields=fields,
            dnp=first.dnp,
            units=tuple(symbol.placement for symbol in symbols),
            pins=tuple(sorted(parts[ref]["pins"], key=lambda pin: (pin.unit, pin.sheet, natural(pin.number)))),
        ))
    names = set(classes) | {pin.net for part in built for pin in part.pins} | {item.net for item in (*labels, *wires, *junctions)}
    assigned, patterns = project_netclasses(project)
    nets = tuple(
        (name, classes.get(name) or netclass_of(name, assigned, patterns))
        for name in sorted((name for name in names if name), key=natural)
    )
    return SchematicIndex(
        sheets=tuple(sheets),
        parts=tuple(built),
        wires=tuple(wires),
        labels=tuple(labels),
        junctions=tuple(junctions),
        no_connects=tuple(flags),
        nets=nets,
    )


# --- KiCad's netlist --------------------------------------------------------------------------


def export_netlist(root: Path, install) -> str:
    """KiCad's netlist of the schematic ``root``, a staged copy (``kicad-cli`` writes beside
    what it reads): one ``kicad-cli sch export netlist`` run."""
    from cadgen.kicad.cli import run_kicad_cli

    root = Path(root)
    run_kicad_cli(install, ["sch", "export", "netlist", "--format", "kicadsexpr", "-o", _NETLIST, root.name], cwd=root.parent)
    return (root.parent / _NETLIST).read_text(encoding="utf-8")


# --- answering references ---------------------------------------------------------------------


class SchematicView(ReferenceView):
    """A schematic read for references, in the sheet frame (millimetres, y down).

    ``parts`` and ``nets`` are everything on it, ``sheets`` each sheet instance (an item's
    ``sheet`` is its index here); :meth:`resolve` answers a schematic reference (with or without
    its file): ``#U3`` is a :class:`Part` (its ``script`` is the line that made it, its ``units``
    where each is drawn), ``#U3.9`` a :class:`Pin` and its net, ``#net:VIN`` a :class:`Net` with
    its pins and parts. A point (``#@x..y..``, ``#net:VIN@x..y..``) names a place on a board,
    never on a schematic.
    """

    _DOCUMENT = "schematic"
    _FORMS = "a schematic's are a part #U3, a pin #U3.9 or a net #net:VIN"
    _NAMEABLE = "a part, pin or net"

    def __init__(self, path: Path, index: SchematicIndex):
        self.path = Path(path)
        self._index = index
        self.sheets: tuple[Sheet, ...] = index.sheets
        self.parts: tuple[Part, ...] = index.parts
        self.wires: tuple[Wire, ...] = index.wires
        self.labels: tuple[Label, ...] = index.labels
        self.junctions: tuple[Junction, ...] = index.junctions
        self.no_connects: tuple[NoConnect, ...] = index.no_connects
        self._parts = {part.ref: part for part in index.parts}
        # Everything on each net, in one pass over the schematic (a pass per net is quadratic).
        on: dict[str, tuple[list, dict, list, list]] = {name: ([], {}, [], []) for name, _netclass in index.nets}
        for part in index.parts:
            for pin in part.pins:
                if pin.net in on:
                    on[pin.net][0].append(pin)
                    on[pin.net][1][part.ref] = part
        for slot, items in ((2, index.labels), (3, index.wires)):
            for item in items:
                if item.net in on:
                    on[item.net][slot].append(item)
        self.nets: tuple[Net, ...] = tuple(
            Net(name=name, netclass=netclass, pins=tuple(on[name][0]), parts=tuple(on[name][1].values()), labels=tuple(on[name][2]), wires=tuple(on[name][3]))
            for name, netclass in index.nets
        )
        self._nets = {net.name: net for net in self.nets}

    def __repr__(self) -> str:
        return f"SchematicView({self.path.name}: {len(self.sheets)} sheets, {len(self.parts)} parts, {len(self.nets)} nets)"

    def _pad(self, part: Part, number: str) -> Pin:
        return part.pin(number)

    def _place(self, selector: BoardSelector):
        raise ValueError(
            f"{selector.canonical} names a point, and points belong to boards: on a schematic, name a "
            "part #U3, a pin #U3.9 or a net #net:VIN (the board's .kicad_pcb answers points)"
        )


def read_schematic(path: Path | str) -> SchematicView:
    """The KiCad schematic at ``path`` (a ``.kicad_sch``, the root of its hierarchy; any KiCad 10
    schematic) for schematic references.

    Everything is in the sheet's frame: millimetres, y down, from the corner of its page, as
    the viewer shows it. The nets are KiCad's own, so this runs KiCad: one
    ``kicad-cli sch export netlist``, on a copy of the hierarchy staged in a temporary folder
    (the project's files are only read). Net classes come from the netlist, else the
    ``.kicad_pro`` beside it.
    """
    from cadgen.kicad.cli import stage_files
    from cadgen.kicad.install import find_kicad

    schematic = Path(path).expanduser()
    if schematic.suffix.lower() != ".kicad_sch":
        raise ValueError(f"{schematic.name} is not a KiCad schematic (.kicad_sch)")
    if not schematic.is_file():
        raise FileNotFoundError(f"{schematic} does not exist")
    instances, _files = _hierarchy(schematic)
    install = find_kicad()
    with tempfile.TemporaryDirectory(prefix="cadgen-kicad-netlist-") as folder:
        staged = stage_files(hierarchy_files(schematic), Path(folder))
        netlist = export_netlist(staged, install)
    index = _index(instances, netlist=netlist, project=schematic.with_suffix(".kicad_pro"))
    return SchematicView(schematic.resolve(), index)
