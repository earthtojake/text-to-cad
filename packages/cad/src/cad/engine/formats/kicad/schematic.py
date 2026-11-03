"""Any KiCad schematic, read as what a person can point at, its nets resolved, and references answered.

:func:`read_schematic` reads a saved ``.kicad_sch`` and the whole hierarchy under its project's root
sheet (the ``<project>.kicad_sch`` beside the ``.kicad_pro``, else the file itself) into an index:
its sheets (each instance of a sheet file is a sheet of its own, with its path ``/Power/``, its page
number and the file it draws), its symbols (each unit placed, with its reference, value, footprint,
library id, fields, the sheet it is on and its pins: number, name, electrical type, where it
connects), wires and buses, junctions, labels (local, global, hierarchical, and each power symbol's
net), no-connects, bus entries, and the nets they make. From the files alone: a schematic embeds
its symbols' drawings (``lib_symbols``), so no library and no KiCad runs.

The nets are resolved as KiCad's connection graph resolves them (``eeschema/connection_graph.cpp``):

1. On each sheet instance, the items that touch are one *subgraph*: a wire's ends and every point
   item -- a pin's tip, a label's anchor, a junction, a no-connect, a sheet pin -- at the same point
   (to KiCad's 100 nm), a point item on a wire's run, and the wires a junction or a shared end joins.
   Wires and buses are apart: a bus's subgraph holds the bus labels on it.
2. A subgraph's *drivers* name it: in KiCad's priority, a global label, then a power pin (a power
   symbol's, or an ordinary symbol's hidden power input), a local label, a hierarchical label, a sheet
   pin, then a symbol pin (``Net-(R1-Pad2)``, or ``Net-(U1-PB3)`` for a pin with a name;
   ``unconnected-(...)`` alone under a no-connect); the best one names it, ties to the lowest name.
3. Subgraphs join across the sheet by name -- every local label of one text on one sheet instance is
   one net, every global label and power net of one name on any sheet is one -- and across the
   hierarchy, a sheet pin to the hierarchical label of its name in the child. A bus's members
   (``D[0..7]``: ``D0`` ... ``D7``; ``USB{DP DM}``: ``USB.DP``, ``USB.DM``) are the nets of those
   names on its sheet, joined to the child's through a bus sheet pin.
4. A net joined from several subgraphs takes the best driver over them: a global one, then a
   strong one (a label) over a weak one (pins), the higher priority, the shorter sheet path, then
   the lower name. A local name carries its sheet's path (``/Power/VBUS``), a global one none.

A reference names a schematic's things as a board's names the board's (:mod:`.refs`, the same
grammar where they mean the same: ``#U3`` the symbol, every unit of it; ``#U3.7`` its pin 7;
``#net:VBUS`` the net, by KiCad's name, which is the board's), plus ``#sheet:/Power/`` a sheet and an
item by the uuid KiCad saved it with (``#wire:<uuid>``, ``#bus:``, ``#label:``, ``#junction:``,
``#no_connect:``, ``#symbol:``: one unit's placement). See :mod:`.schematic_refs`.

Frames: a schematic's page is in KiCad's frame, millimetres, y down, from the page's top-left
corner, as the file holds it; every answer is in it. A library symbol's drawing is y up, about its
anchor: a placed symbol's transform (its angle, counter-clockwise, then its mirror) maps it.
"""

from __future__ import annotations

import difflib
import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from cad.engine.formats.kicad import sexpr
from cad.engine.formats.kicad.naming import natural
from cad.engine.formats.kicad.ref_path import ref_prefix_names
from cad.engine.formats.kicad.sexpr import Sym

__all__ = [
    "BusEntry",
    "Junction",
    "Label",
    "LibPin",
    "LibSymbol",
    "Net",
    "NoConnect",
    "Pin",
    "SchematicIndex",
    "SchematicView",
    "Sheet",
    "SheetPin",
    "Symbol",
    "Wire",
    "bus_members",
    "is_bus_name",
    "read_schematic",
    "read_schematic_index",
    "root_of",
    "screen_transform",
    "symbol_transform",
]

XY = tuple[float, float]

#: KiCad's schematic unit, 100 nm: two points closer than this are one.
_UNIT = 1e-4
#: The default line widths KiCad draws a stroke of width 0 with, mm: a wire's and a symbol's, a bus's.
WIRE_WIDTH = 0.1524
BUS_WIDTH = 0.3048
JUNCTION_DIAMETER = 0.9144
NO_CONNECT_SIZE = 1.2192
#: The fields a part number is found under, in the order they are looked for.
MPN_FIELDS = ("MPN", "Manufacturer_Part_Number", "Manufacturer Part Number", "Mfr. Part #", "MFR_PN", "PartNumber",
              "Part Number")
#: KiCad's driver priorities (``CONNECTION_SUBGRAPH::PRIORITY``).
PRIORITY = {"none": 0, "pin": 1, "sheet_pin": 2, "hierarchical": 3, "local": 4, "local_power": 5, "power": 6,
            "global": 7}
_STRONG = PRIORITY["hierarchical"]
_GLOBAL = PRIORITY["power"]


def _key(point: XY) -> tuple[int, int]:
    return round(point[0] / _UNIT), round(point[1] / _UNIT)


def _round(point: XY) -> XY:
    return round(point[0], 4) + 0.0, round(point[1], 4) + 0.0


# --- bus names ----------------------------------------------------------------------------------

_VECTOR = re.compile(r"^(?P<prefix>[^\[\]{}\s]*)\[(?P<start>-?\d+)\.\.(?P<end>-?\d+)\](?P<suffix>[^\[\]{}\s]*)$")
_GROUP = re.compile(r"^(?P<name>[^{}\s]*)\{(?P<members>[^{}]*)\}$")


def is_bus_name(text: str) -> bool:
    """Whether a label's text names a bus: a vector ``D[0..7]`` or a group ``{SDA SCL}``."""
    text = str(text)
    return bool(_VECTOR.match(text) or _GROUP.match(text))


def bus_members(text: str) -> list[str]:
    """The nets a bus name holds, as KiCad names them: ``D[0..3]`` is ``D0``..``D3``, ``USB{DP DM}``
    is ``USB.DP``, ``USB.DM``, ``{SDA SCL}`` is ``SDA``, ``SCL``; a group's vector members expand. A net
    name is its own one member."""
    text = str(text)
    vector = _VECTOR.match(text)
    if vector:
        start, end = int(vector["start"]), int(vector["end"])
        step = 1 if end >= start else -1
        return [f"{vector['prefix']}{index}{vector['suffix']}" for index in range(start, end + step, step)]
    group = _GROUP.match(text)
    if group:
        prefix = f"{group['name']}." if group["name"] else ""
        members: list[str] = []
        for member in group["members"].replace(",", " ").split():
            members += [prefix + name for name in bus_members(member)]
        return members
    return [text]


def _slots(text: str) -> list[tuple[tuple, str]]:
    """A bus name's members with the slot each is matched by on a bus: a vector's by its index
    (``D3`` of ``D[0..7]`` meets ``Q3`` of ``Q[0..7]``), a group's by its member's own name."""
    vector = _VECTOR.match(str(text))
    if vector:
        start, end = int(vector["start"]), int(vector["end"])
        step = 1 if end >= start else -1
        return [(("v", index), f"{vector['prefix']}{index}{vector['suffix']}") for index in range(start, end + step, step)]
    group = _GROUP.match(str(text))
    if group:
        prefix = f"{group['name']}." if group["name"] else ""
        slots = []
        for member in group["members"].replace(",", " ").split():
            slots += [(("g", name), prefix + name) for name in bus_members(member)]
        return slots
    return [(("g", str(text)), str(text))]


# --- what a schematic holds ---------------------------------------------------------------------


@dataclass(frozen=True)
class LibPin:
    """A pin of a library symbol, in the symbol's own frame (mm, y up): its tip ``at``, the direction
    it runs from the tip to the body (``angle``, degrees counter-clockwise), its ``length``."""

    number: str
    name: str
    type: str  # KiCad's electrical type: "passive", "input", "power_in", "no_connect"...
    shape: str  # "line", "inverted", "clock"...
    at: XY
    angle: float
    length: float
    hidden: bool
    unit: int
    style: int
    name_size: tuple[float, float] = (1.27, 1.27)
    number_size: tuple[float, float] = (1.27, 1.27)


@dataclass
class LibSymbol:
    """A symbol as the schematic embeds it (``lib_symbols``): its pins and its drawing, by unit
    (0: every unit) and body style (0: every style)."""

    name: str
    power: str | None  # "global" for a power symbol, "local" for KiCad 9's local power, else None
    pins: list[LibPin]
    graphics: list[tuple[int, int, list]]  # (unit, style, node)
    pin_names_offset: float
    pin_names_hidden: bool
    pin_numbers_hidden: bool
    properties: dict[str, str]
    units: int


@dataclass(frozen=True)
class Pin:
    """One pin of a placed symbol, in the sheet's frame: where it connects (``at``, its tip), its net."""

    ref: str
    number: str
    name: str
    type: str
    sheet: str
    at: XY
    hidden: bool
    unit: int
    net: str | None = None

    @property
    def selector(self) -> str | None:
        from cad.engine.formats.kicad.refs import selector_or_none

        return selector_or_none("pad", ref=self.ref, pad=self.number)

    def __repr__(self) -> str:
        return f"Pin({self.ref}.{self.number}{f' {self.name}' if self.name else ''} on {self.net}, {self.type})"


@dataclass(frozen=True)
class Symbol:
    """One unit of a part placed on a sheet: what KiCad's symbol is. Several units of one part share
    its reference; ``#U3`` names them all (:meth:`SchematicView.part`)."""

    ref: str
    value: str
    footprint: str
    lib_id: str
    unit: int
    units: int
    sheet: str
    at: XY
    angle: float
    mirror: str | None  # "x", "y" or None
    uuid: str | None
    fields: Mapping[str, str]
    pins: tuple[Pin, ...]
    power: bool = False
    in_bom: bool = True
    on_board: bool = True
    dnp: bool = False
    body_style: int = 1

    @property
    def mpn(self) -> str | None:
        """The manufacturer's part number, from the first of the usual fields that holds one."""
        return next((self.fields[name] for name in MPN_FIELDS if self.fields.get(name)), None)

    @property
    def selector(self) -> str | None:
        from cad.engine.formats.kicad.refs import selector_or_none

        return selector_or_none("part", ref=self.ref)

    def pin(self, number: str) -> Pin:
        found = [pin for pin in self.pins if pin.number == str(number)]
        if not found:
            raise ValueError(f"{self.ref} has no pin {number}; its pins are {', '.join(pin.number for pin in self.pins)}")
        return found[0]

    def __repr__(self) -> str:
        unit = f" unit {self.unit}" if self.units > 1 else ""
        return f"Symbol({self.ref}{unit} {self.value} [{self.lib_id}] on {self.sheet}, {len(self.pins)} pins)"


@dataclass(frozen=True)
class Wire:
    """A wire or a bus segment (``kind``) on a sheet, from end to end."""

    kind: str  # "wire" or "bus"
    sheet: str
    points: tuple[XY, XY]
    uuid: str | None
    net: str | None = None  # a wire's net; a bus's first name

    def __repr__(self) -> str:
        return f"Wire({self.kind} on {self.sheet} {self.points[0]}-{self.points[1]}, {self.net})"


@dataclass(frozen=True)
class Junction:
    sheet: str
    at: XY
    uuid: str | None
    net: str | None = None


@dataclass(frozen=True)
class NoConnect:
    sheet: str
    at: XY
    uuid: str | None


@dataclass(frozen=True)
class BusEntry:
    sheet: str
    points: tuple[XY, XY]
    uuid: str | None


@dataclass(frozen=True)
class Label:
    """A name put on a wire or a bus: a ``local`` label, a ``global`` one, a ``hierarchical`` one (a
    sheet's port), or a ``power`` symbol's net (its value, where its pin is; ``uuid`` the symbol's)."""

    kind: str
    text: str
    sheet: str
    at: XY
    angle: float
    shape: str | None
    uuid: str | None
    net: str | None = None
    size: float = 1.27  # its letters' height, mm

    @property
    def bus(self) -> bool:
        return is_bus_name(self.text)

    def __repr__(self) -> str:
        return f"Label({self.kind} {self.text!r} on {self.sheet} at {self.at}, {self.net})"


@dataclass(frozen=True)
class SheetPin:
    """A pin of a hierarchical sheet's box, on the parent sheet: the child's hierarchical label of its name."""

    name: str
    shape: str
    at: XY
    angle: float
    uuid: str | None
    net: str | None = None


@dataclass(frozen=True)
class Sheet:
    """One sheet instance: the root (``/``) or a hierarchical sheet placed on its parent (``/Power/``).
    ``file`` is the sheet file as resolved; ``at``, ``size`` and ``pins`` its box on the parent."""

    path: str
    name: str
    file: Path
    page: str
    uuid_path: str
    uuid: str | None
    parent: str | None
    paper: tuple[float, float]
    at: XY | None = None
    size: XY | None = None
    pins: tuple[SheetPin, ...] = ()
    title: Mapping[str, str] = field(default_factory=dict)

    @property
    def selector(self) -> str:
        from cad.engine.formats.kicad.schematic_refs import format_sheet_selector

        return format_sheet_selector(self.path)

    def __repr__(self) -> str:
        return f"Sheet({self.path} page {self.page}: {self.file.name})"


@dataclass(frozen=True)
class Net:
    """One net: its name as KiCad gives it, the pins on it (``pins``: every symbol pin, by reference
    and number), the sheets it reaches, and its labels."""

    name: str
    pins: tuple[Pin, ...]
    labels: tuple[Label, ...]
    sheets: tuple[str, ...]

    @property
    def selector(self) -> str:
        from cad.engine.formats.kicad.refs import format_board_selector

        return format_board_selector("net", net=self.name)

    def __repr__(self) -> str:
        return f"Net({self.name}: {len(self.pins)} pins on {', '.join(self.sheets)})"


@dataclass
class SchematicIndex:
    """A schematic's hierarchy read: every sheet, symbol, wire and bus, junction, label, no-connect and
    bus entry, and its nets."""

    root: Path
    version: int | None
    generator: str
    sheets: tuple[Sheet, ...]
    symbols: tuple[Symbol, ...]
    wires: tuple[Wire, ...]
    junctions: tuple[Junction, ...]
    labels: tuple[Label, ...]
    no_connects: tuple[NoConnect, ...]
    bus_entries: tuple[BusEntry, ...]
    nets: tuple[Net, ...]
    texts: tuple[dict, ...] = ()
    #: The parsed files, by resolved path: the plot draws from the same trees.
    trees: Mapping[Path, list] = field(default_factory=dict, repr=False)
    lib_symbols: Mapping[Path, Mapping[str, LibSymbol]] = field(default_factory=dict, repr=False)

    @property
    def pins(self) -> tuple[Pin, ...]:
        return tuple(pin for symbol in self.symbols for pin in symbol.pins)

    def as_json(self, digits: int = 4) -> dict:
        """The index as plain data, the plot payload's ``schematic`` (``schematic_plot``)."""

        def num(value: float) -> float:
            return round(float(value), digits) + 0.0

        def xy(point: XY) -> list[float]:
            return [num(point[0]), num(point[1])]

        parts: dict[str, dict] = {}
        for symbol in self.symbols:
            if symbol.power:
                continue
            part = parts.setdefault(symbol.ref, {
                "ref": symbol.ref, "value": symbol.value, "footprint": symbol.footprint, "lib_id": symbol.lib_id,
                "mpn": symbol.mpn, "fields": dict(symbol.fields), "dnp": symbol.dnp, "in_bom": symbol.in_bom,
                "on_board": symbol.on_board, "units": []})
            part["units"].append({"unit": symbol.unit, "sheet": symbol.sheet, "at": xy(symbol.at),
                                  "angle": num(symbol.angle), "mirror": symbol.mirror, "id": symbol.uuid})
        return {
            "root": self.root.name,
            "sheets": [{"path": sheet.path, "name": sheet.name, "file": sheet.file.name, "page": sheet.page,
                        "parent": sheet.parent, "id": sheet.uuid,
                        **({"at": xy(sheet.at), "size": xy(sheet.size)} if sheet.at and sheet.size else {}),
                        "pins": [{"name": pin.name, "shape": pin.shape, "at": xy(pin.at), "net": pin.net, "id": pin.uuid}
                                 for pin in sheet.pins]} for sheet in self.sheets],
            "parts": sorted(parts.values(), key=lambda part: natural(part["ref"])),
            "pins": [{"part": pin.ref, "number": pin.number, "name": pin.name, "type": pin.type, "sheet": pin.sheet,
                      "at": xy(pin.at), "net": pin.net, "hidden": pin.hidden} for pin in self.pins
                     if not pin.ref.startswith("#")],
            "wires": [{"kind": wire.kind, "sheet": wire.sheet, "points": [xy(p) for p in wire.points], "net": wire.net,
                       "id": wire.uuid} for wire in self.wires],
            "junctions": [{"sheet": item.sheet, "at": xy(item.at), "net": item.net, "id": item.uuid} for item in self.junctions],
            "labels": [{"kind": label.kind, "text": label.text, "sheet": label.sheet, "at": xy(label.at),
                        "angle": num(label.angle), "shape": label.shape, "net": label.net, "id": label.uuid}
                       for label in self.labels],
            "no_connects": [{"sheet": item.sheet, "at": xy(item.at), "id": item.uuid} for item in self.no_connects],
            "bus_entries": [{"sheet": item.sheet, "points": [xy(p) for p in item.points], "id": item.uuid}
                            for item in self.bus_entries],
            "nets": [{"name": net.name, "pins": [f"{pin.ref}.{pin.number}" for pin in net.pins], "sheets": list(net.sheets)}
                     for net in self.nets],
        }


# --- reading the files -------------------------------------------------------------------------


def _hidden(node: list) -> bool:
    """``(hide yes)``, or an older file's bare ``hide``."""
    if str(sexpr.value(node, "hide", "")) == "yes":
        return True
    if any(isinstance(atom, Sym) and atom == "hide" for atom in node[1:]):
        return True
    effects = sexpr.find(node, "effects")
    return effects is not None and effects is not node and _hidden(effects)


def _yes(node: list, name: str, default: bool) -> bool:
    found = sexpr.value(node, name)
    return default if found is None else str(found) == "yes"


def _uuid(node: list) -> str | None:
    found = sexpr.value(node, "uuid")
    return str(found).lower() if found not in (None, "") else None


def _properties(node: list) -> dict[str, str]:
    return {str(prop[1]): str(prop[2]) for prop in sexpr.find_all(node, "property") if len(prop) > 2}


def _font_size(node: list | None) -> tuple[float, float]:
    effects = sexpr.find(node, "effects") if node is not None else None
    font = sexpr.find(effects, "font") if effects is not None else None
    size = sexpr.pair(sexpr.find(font, "size"), (1.27, 1.27)) if font is not None else (1.27, 1.27)
    return abs(size[0]), abs(size[1])


_SUBSYMBOL = re.compile(r"_(\d+)_(\d+)$")


def _lib_symbol(node: list, library: Mapping[str, list]) -> LibSymbol:
    name = str(node[1])
    parent = sexpr.value(node, "extends")
    base = _lib_symbol(library[str(parent)], library) if parent is not None and str(parent) in library else None
    power_node = sexpr.find(node, "power")
    power = ("local" if len(power_node) > 1 and str(power_node[1]) == "local" else "global") if power_node is not None else (
        base.power if base else None)
    names = sexpr.find(node, "pin_names")
    numbers = sexpr.find(node, "pin_numbers")
    pins: list[LibPin] = list(base.pins) if base else []
    graphics: list[tuple[int, int, list]] = list(base.graphics) if base else []
    units = 1
    for sub in sexpr.find_all(node, "symbol"):
        match = _SUBSYMBOL.search(str(sub[1]))
        unit, style = (int(match[1]), int(match[2])) if match else (0, 0)
        units = max(units, unit)
        for item in sub[1:]:
            head = sexpr.head(item)
            if head == "pin":
                at = sexpr.find(item, "at") or [Sym("at"), 0, 0, 0]
                name_node = sexpr.find(item, "name")
                number_node = sexpr.find(item, "number")
                pins.append(LibPin(
                    number=str(number_node[1]) if number_node is not None and len(number_node) > 1 else "",
                    name=str(name_node[1]) if name_node is not None and len(name_node) > 1 else "",
                    type=str(item[1]) if len(item) > 1 else "passive",
                    shape=str(item[2]) if len(item) > 2 and isinstance(item[2], Sym) else "line",
                    at=(sexpr.number(at[1]), sexpr.number(at[2])),
                    angle=sexpr.number(at[3]) if len(at) > 3 else 0.0,
                    length=sexpr.number(sexpr.value(item, "length"), 2.54),
                    hidden=_hidden_pin(item), unit=unit, style=style,
                    name_size=_font_size(name_node), number_size=_font_size(number_node)))
            elif head in ("polyline", "rectangle", "circle", "arc", "bezier", "text", "text_box"):
                graphics.append((unit, style, item))
    return LibSymbol(
        name=name, power=power, pins=pins, graphics=graphics,
        pin_names_offset=sexpr.number(sexpr.value(names, "offset"), 0.508) if names is not None else 0.508,
        pin_names_hidden=names is not None and _hidden(names),
        pin_numbers_hidden=numbers is not None and _hidden(numbers),
        properties={**(base.properties if base else {}), **_properties(node)}, units=max(units, base.units if base else 1))


def _hidden_pin(node: list) -> bool:
    """A pin's own ``(hide yes)`` or bare ``hide``, not its name's or number's."""
    return str(sexpr.value(node, "hide", "")) == "yes" or any(isinstance(atom, Sym) and atom == "hide" for atom in node[1:])


def symbol_transform(angle: float, mirror: str | None):
    """The map from a library symbol's frame (mm, y up, about its anchor) to a placed symbol's offset on
    the sheet (mm, y down): KiCad's ``TRANSFORM``, its angle (counter-clockwise on the page) applied,
    then its mirror (``x``: about the horizontal axis, ``y``: about the vertical one)."""
    quarter = round(angle / 90) % 4
    cos, sin = ((1, 0), (0, 1), (-1, 0), (0, -1))[quarter] if abs(angle / 90 - round(angle / 90)) < 1e-9 else (
        math.cos(math.radians(angle)), math.sin(math.radians(angle)))

    def apply(point: XY) -> XY:
        x, y = point[0], -point[1]
        x, y = x * cos + y * sin, -x * sin + y * cos
        if mirror == "x":
            y = -y
        elif mirror == "y":
            x = -x
        return x, y

    return apply


def screen_transform(angle: float, mirror: str | None):
    """:func:`symbol_transform` for an offset already in the sheet's frame (y down): what KiCad applies
    to a placed symbol's fields, about the symbol's anchor."""
    lib = symbol_transform(angle, mirror)
    return lambda point: lib((point[0], -point[1]))


def _placed(at: XY, transform, point: XY) -> XY:
    dx, dy = transform(point)
    return _round((at[0] + dx, at[1] + dy))


def _paper(node: list) -> tuple[float, float]:
    """The page's size, mm: ``(paper "A4")``, ``(paper "User" W H)``, ``portrait`` turned."""
    paper = sexpr.find(node, "paper")
    sizes = {"A5": (210, 148), "A4": (297, 210), "A3": (420, 297), "A2": (594, 420), "A1": (841, 594),
             "A0": (1189, 841), "A": (279.4, 215.9), "B": (431.8, 279.4), "C": (558.8, 431.8), "D": (863.6, 558.8),
             "E": (1117.6, 863.6), "USLetter": (279.4, 215.9), "USLegal": (355.6, 215.9), "USLedger": (431.8, 279.4)}
    if paper is None or len(paper) < 2:
        return sizes["A4"]
    name = str(paper[1])
    if name == "User" and len(paper) > 3:
        size = (sexpr.number(paper[2]), sexpr.number(paper[3]))
    else:
        size = sizes.get(name, sizes["A4"])
    if any(isinstance(atom, Sym) and atom == "portrait" for atom in paper[2:]):
        size = (size[1], size[0])
    return float(size[0]), float(size[1])


def _title(node: list) -> dict[str, str]:
    block = sexpr.find(node, "title_block")
    if block is None:
        return {}
    title = {}
    for item in block[1:]:
        head = sexpr.head(item)
        if head == "comment" and len(item) > 2:
            title[f"comment{item[1]}"] = str(item[2])
        elif head and len(item) > 1:
            title[head] = str(item[1])
    return title


def root_of(path: Path | str) -> Path:
    """The root sheet of the project ``path`` belongs to: the ``<project>.kicad_sch`` beside the
    ``.kicad_pro`` in its folder when there is one, else ``path`` itself."""
    sheet = Path(path).expanduser().resolve()
    projects = sorted(sheet.parent.glob("*.kicad_pro"))
    for project in projects:
        root = project.with_suffix(".kicad_sch")
        if root.is_file():
            return root
    return sheet


class _Reader:
    """The hierarchy under one root, read file by file (each file parsed once)."""

    def __init__(self, root: Path):
        self.root = root
        self.trees: dict[Path, list] = {}
        self.libraries: dict[Path, dict[str, LibSymbol]] = {}
        self.sheets: list[Sheet] = []
        self.symbols: list[Symbol] = []
        self.wires: list[Wire] = []
        self.junctions: list[Junction] = []
        self.labels: list[Label] = []
        self.no_connects: list[NoConnect] = []
        self.bus_entries: list[BusEntry] = []
        self.texts: list[dict] = []
        self.warnings: list[str] = []
        self.page_numbers: dict[str, str] = {}

    def tree(self, file: Path) -> list:
        if file not in self.trees:
            try:
                text = file.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                raise ValueError(f"{file.name} is not a readable KiCad schematic: it is not UTF-8 text") from None
            tree = sexpr.parse(text)
            if sexpr.head(tree) != "kicad_sch":
                raise ValueError(f"{file.name} is not a KiCad schematic: it is a {sexpr.head(tree)}")
            self.trees[file] = tree
            nodes = {str(item[1]): item for item in (sexpr.find(tree, "lib_symbols") or [])[1:]
                     if sexpr.head(item) == "symbol" and len(item) > 1}
            self.libraries[file] = {name: _lib_symbol(item, nodes) for name, item in nodes.items()}
        return self.trees[file]

    def read(self) -> None:
        tree = self.tree(self.root)
        root_uuid = _uuid(tree) or ""
        for instances in sexpr.find_all(tree, "sheet_instances"):
            for path in sexpr.find_all(instances, "path"):
                self.page_numbers[str(path[1])] = str(sexpr.value(path, "page", ""))
        page = self.page_numbers.get("/") or self.page_numbers.get(f"/{root_uuid}") or "1"
        self.walk(self.root, "/", "/", f"/{root_uuid}", root_uuid, None, page, None, (), [self.root])

    def walk(self, file: Path, path: str, name: str, uuid_path: str, uuid: str | None, parent: str | None, page: str,
             box: tuple[XY, XY] | None, pins: tuple[SheetPin, ...], seen: list[Path]) -> None:
        tree = self.tree(file)
        self.sheets.append(Sheet(path=path, name=name, file=file, page=page, uuid_path=uuid_path, uuid=uuid,
                                 parent=parent, paper=_paper(tree), at=box[0] if box else None,
                                 size=box[1] if box else None, pins=pins, title=_title(tree)))
        library = self.libraries[file]
        children = []
        for item in tree[1:]:
            head = sexpr.head(item)
            if head == "symbol":
                self.symbol(item, library, path, uuid_path)
            elif head in ("wire", "bus"):
                points = [sexpr.pair(xy) for xy in sexpr.find_all(sexpr.find(item, "pts") or [], "xy")]
                for a, b in zip(points, points[1:]):
                    self.wires.append(Wire(head, path, (_round(a), _round(b)), _uuid(item)))
            elif head == "junction":
                self.junctions.append(Junction(path, _round(sexpr.pair(sexpr.find(item, "at"), (0.0, 0.0))), _uuid(item)))
            elif head == "no_connect":
                self.no_connects.append(NoConnect(path, _round(sexpr.pair(sexpr.find(item, "at"), (0.0, 0.0))), _uuid(item)))
            elif head == "bus_entry":
                at = sexpr.pair(sexpr.find(item, "at"), (0.0, 0.0))
                size = sexpr.pair(sexpr.find(item, "size"), (0.0, 0.0))
                self.bus_entries.append(BusEntry(path, (_round(at), _round((at[0] + size[0], at[1] + size[1]))), _uuid(item)))
            elif head in ("label", "global_label", "hierarchical_label"):
                at = sexpr.find(item, "at") or [Sym("at"), 0, 0, 0]
                kind = {"label": "local", "global_label": "global", "hierarchical_label": "hierarchical"}[head]
                shape = sexpr.value(item, "shape")
                self.labels.append(Label(kind, str(item[1]), path, _round((sexpr.number(at[1]), sexpr.number(at[2]))),
                                         sexpr.number(at[3]) if len(at) > 3 else 0.0,
                                         str(shape) if shape is not None else None, _uuid(item),
                                         size=_font_size(item)[0]))
            elif head == "sheet":
                children.append(item)
        for item in children:
            props = _properties(item)
            child_name = props.get("Sheetname") or props.get("Sheet name") or "sheet"
            child_file = props.get("Sheetfile") or props.get("Sheet file") or ""
            child = (file.parent / child_file).resolve()
            child_uuid = _uuid(item) or ""
            child_path = f"{path}{child_name}/"
            child_uuid_path = f"{uuid_path}/{child_uuid}"
            child_page = ""
            for project in sexpr.find_all(sexpr.find(item, "instances") or [], "project"):
                for entry in sexpr.find_all(project, "path"):
                    if str(entry[1]) == uuid_path:
                        child_page = str(sexpr.value(entry, "page", ""))
            child_page = child_page or self.page_numbers.get(child_uuid_path, "") or str(len(self.sheets) + 1)
            at = sexpr.pair(sexpr.find(item, "at"), (0.0, 0.0))
            size = sexpr.pair(sexpr.find(item, "size"), (0.0, 0.0))
            sheet_pins = tuple(
                SheetPin(str(pin[1]), str(pin[2]) if len(pin) > 2 else "input",
                         _round(sexpr.pair(sexpr.find(pin, "at"), (0.0, 0.0))),
                         sexpr.number((sexpr.find(pin, "at") or [0, 0, 0, 0])[3]) if len(sexpr.find(pin, "at") or []) > 3 else 0.0,
                         _uuid(pin))
                for pin in sexpr.find_all(item, "pin"))
            if not child.is_file():
                self.warnings.append(f"{path}: the sheet {child_name} names {child_file}, which is not there")
                self.sheets.append(Sheet(path=child_path, name=child_name, file=child, page=child_page,
                                         uuid_path=child_uuid_path, uuid=child_uuid, parent=path, paper=(297.0, 210.0),
                                         at=_round(at), size=size, pins=sheet_pins))
                continue
            if child in seen:
                raise ValueError(f"the sheet {child_name} ({child_file}) contains itself")
            self.walk(child, child_path, child_name, child_uuid_path, child_uuid, path, child_page,
                      (_round(at), size), sheet_pins, [*seen, child])

    def symbol(self, node: list, library: Mapping[str, LibSymbol], sheet: str, uuid_path: str) -> None:
        lib_id = str(sexpr.value(node, "lib_id", "") or "")
        lib_name = str(sexpr.value(node, "lib_name", "") or "") or lib_id
        lib = library.get(lib_name) or library.get(lib_id)
        at_node = sexpr.find(node, "at") or [Sym("at"), 0, 0, 0]
        at = (sexpr.number(at_node[1]), sexpr.number(at_node[2]))
        angle = sexpr.number(at_node[3]) if len(at_node) > 3 else 0.0
        mirror_node = sexpr.value(node, "mirror")
        mirror = str(mirror_node) if mirror_node is not None else None
        props = _properties(node)
        ref, unit = props.get("Reference", "?"), int(sexpr.number(sexpr.value(node, "unit"), 1))
        for project in sexpr.find_all(sexpr.find(node, "instances") or [], "project"):
            for entry in sexpr.find_all(project, "path"):
                if str(entry[1]) == uuid_path:
                    ref = str(sexpr.value(entry, "reference", ref))
                    unit = int(sexpr.number(sexpr.value(entry, "unit"), unit))
        style = int(sexpr.number(sexpr.value(node, "body_style", sexpr.value(node, "convert")), 1))
        transform = symbol_transform(angle, mirror)
        pins: list[Pin] = []
        if lib is None:
            self.warnings.append(f"{sheet}: {ref} names {lib_name}, which the schematic does not embed")
        else:
            for pin in lib.pins:
                if pin.unit not in (0, unit) or pin.style not in (0, style):
                    continue
                pins.append(Pin(ref=ref, number=pin.number, name=pin.name if pin.name != "~" else "", type=pin.type,
                                sheet=sheet, at=_placed(at, transform, pin.at), hidden=pin.hidden, unit=unit))
        fields = {name: value for name, value in props.items()}
        self.symbols.append(Symbol(
            ref=ref, value=props.get("Value", ""), footprint=props.get("Footprint", ""), lib_id=lib_id, unit=unit,
            units=lib.units if lib else 1, sheet=sheet, at=_round(at), angle=angle, mirror=mirror, uuid=_uuid(node),
            fields=fields, pins=tuple(pins), power=bool(lib and lib.power), in_bom=_yes(node, "in_bom", True),
            on_board=_yes(node, "on_board", True), dnp=_yes(node, "dnp", False), body_style=style))
        powered = [pin for pin in pins if pin.type == "power_in"]
        if lib is not None and lib.power and powered:
            # A power symbol's power input names its net where its pin is, by the symbol's value (a
            # PWR_FLAG's power output names nothing).
            self.labels.append(Label("power" if lib.power == "global" else "local_power", props.get("Value", ""), sheet,
                                     powered[0].at, angle, None, _uuid(node)))


# --- connectivity -------------------------------------------------------------------------------


class _Union:
    def __init__(self) -> None:
        self.parent: dict[Any, Any] = {}

    def find(self, item: Any) -> Any:
        parent = self.parent.setdefault(item, item)
        if parent != item:
            parent = self.parent[item] = self.find(parent)
        return parent

    def join(self, a: Any, b: Any) -> None:
        a, b = self.find(a), self.find(b)
        if a != b:
            self.parent[b] = a


def _on_segment(point: tuple[int, int], a: tuple[int, int], b: tuple[int, int]) -> bool:
    """Whether ``point`` lies on the run of the segment ``a``-``b``, its ends excluded (integer units)."""
    (px, py), (ax, ay), (bx, by) = point, a, b
    if (px, py) in (a, b):
        return False
    if not (min(ax, bx) <= px <= max(ax, bx) and min(ay, by) <= py <= max(ay, by)):
        return False
    cross = (bx - ax) * (py - ay) - (by - ay) * (px - ax)
    length = math.hypot(bx - ax, by - ay)
    return length > 0 and abs(cross) / length <= 1.0


def _driver_name(kind: str, text: str, sheet: str) -> str:
    """The name a driver gives a net: a global one its text, a local one its text after its sheet's path."""
    if kind in ("global", "power"):
        return text
    return f"{sheet}{text}"


def _pin_name(pin: Pin, alone: bool) -> str:
    """KiCad's name for a net only pins drive (``SCH_PIN::GetDefaultNetName``)."""
    function = pin.name if pin.name and pin.name not in ("~", pin.number) else ""
    if alone:
        return f"unconnected-({pin.ref}-{function + '-' if function else ''}Pad{pin.number})"
    return f"Net-({pin.ref}-{function or 'Pad' + pin.number})"


def resolve_nets(index: _Reader) -> tuple[dict[int, str], list[Net], list[str]]:
    """The nets of the hierarchy read into ``index`` (the module doc's steps): the net of every item,
    keyed by ``id()``; the nets; and what could not be resolved."""
    warnings: list[str] = []
    union = _Union()
    by_sheet: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for wire in index.wires:
        by_sheet[wire.sheet][wire.kind].append(wire)
    for kind, items in (("pin", [pin for symbol in index.symbols for pin in symbol.pins]), ("label", index.labels),
                        ("junction", index.junctions), ("no_connect", index.no_connects)):
        for item in items:
            by_sheet[item.sheet][kind].append(item)
    sheets = {sheet.path: sheet for sheet in index.sheets}
    for sheet in index.sheets:
        if sheet.parent is not None and sheet.parent in sheets:
            for pin in sheet.pins:
                by_sheet[sheet.parent]["sheet_pin"].append((sheet, pin))

    # 1. The subgraphs of each sheet, on its wires and on its buses.
    for items in by_sheet.values():
        for layer in ("wire", "bus"):
            segments = items.get(layer, [])
            ends: dict[tuple[int, int], list] = defaultdict(list)
            for wire in segments:
                for point in wire.points:
                    ends[_key(point)].append(("seg", id(wire)))
            points: list[tuple[tuple[int, int], Any]] = []
            for pin in items.get("pin", []) if layer == "wire" else ():
                points.append((_key(pin.at), ("item", id(pin))))
            for label in items.get("label", []):
                if (layer == "bus") == label.bus:  # a bus label names a bus, a net label (and a power net) a wire
                    points.append((_key(label.at), ("item", id(label))))
            for junction in items.get("junction", []):
                points.append((_key(junction.at), ("junction", layer, id(junction))))
            for no_connect in items.get("no_connect", []) if layer == "wire" else ():
                points.append((_key(no_connect.at), ("item", id(no_connect))))
            for sheet, pin in items.get("sheet_pin", []):
                if (layer == "bus") == is_bus_name(pin.name):
                    points.append((_key(pin.at), ("item", id(pin))))
            # Items at one point are one; an item on a segment's end or its run is on it.
            at_point: dict[tuple[int, int], list] = defaultdict(list)
            for point, node in points:
                at_point[point].append(node)
            for point, nodes in at_point.items():
                for node in nodes[1:]:
                    union.join(nodes[0], node)
                for seg in ends.get(point, ()):
                    union.join(nodes[0], seg)
            for point, seg_nodes in ends.items():
                for seg in seg_nodes[1:]:
                    union.join(seg_nodes[0], seg)
            # A point on a segment's run: a grid of the segments keeps this from being quadratic.
            cell = 25.4 / _UNIT
            grid: dict[tuple[int, int], list] = defaultdict(list)
            for wire in segments:
                a, b = _key(wire.points[0]), _key(wire.points[1])
                for gx in range(int(min(a[0], b[0]) // cell), int(max(a[0], b[0]) // cell) + 1):
                    for gy in range(int(min(a[1], b[1]) // cell), int(max(a[1], b[1]) // cell) + 1):
                        grid[(gx, gy)].append((a, b, ("seg", id(wire))))
            candidates = list(at_point) + list(ends)
            for point in candidates:
                for a, b, seg in grid.get((int(point[0] // cell), int(point[1] // cell)), ()):
                    if _on_segment(point, a, b):
                        anchor = at_point[point][0] if point in at_point else ends[point][0]
                        union.join(anchor, seg)
    # The subgraph an item is in. A junction is a point of a sheet's wires and of its buses, two nodes,
    # so it never bridges a wire and a bus; its wire node stands for it.
    def node_of(item: Any) -> Any:
        if isinstance(item, Junction):
            return union.find(("junction", "wire", id(item)))
        if isinstance(item, Wire):
            return union.find(("seg", id(item)))
        return union.find(("item", id(item)))

    # 2. The drivers of every subgraph, and the names that join subgraphs.
    groups: dict[Any, dict[str, Any]] = defaultdict(lambda: {"drivers": [], "pins": [], "no_connect": False,
                                                              "sheet": None, "bus": False})
    for label in index.labels:
        group = groups[node_of(label)]
        group["sheet"] = label.sheet
        group["bus"] = group["bus"] or label.bus
        kind = label.kind
        priority = PRIORITY["global"] if kind == "global" else PRIORITY["power"] if kind == "power" else (
            PRIORITY["local_power"] if kind == "local_power" else PRIORITY["local"] if kind == "local" else
            PRIORITY["hierarchical"])
        group["drivers"].append((priority, _driver_name(kind, label.text, label.sheet), label.sheet))
    for symbol in index.symbols:
        for pin in symbol.pins:
            group = groups[node_of(pin)]
            group["sheet"] = pin.sheet
            group["pins"].append(pin)
            if pin.type == "power_in" and pin.hidden and not symbol.power:
                # An ordinary symbol's hidden power input is a global net of its pin's name (legacy parts).
                group["drivers"].append((PRIORITY["power"], pin.name, pin.sheet))
            elif not symbol.power:
                group["drivers"].append((PRIORITY["pin"], None, pin.sheet, pin))
    for item in index.no_connects:
        groups[node_of(item)]["no_connect"] = True
    for sheet in index.sheets:
        for pin in sheet.pins:
            if sheet.parent is None:
                continue
            group = groups[node_of(pin)]
            group["sheet"] = sheet.parent
            group["bus"] = group["bus"] or is_bus_name(pin.name)
            group["drivers"].append((PRIORITY["sheet_pin"], f"{sheet.parent}{pin.name}", sheet.parent))
    for wire in index.wires:
        groups[node_of(wire)]["sheet"] = wire.sheet
        if wire.kind == "bus":
            groups[node_of(wire)]["bus"] = True

    nets = _Union()  # the subgraphs joined: by name on a sheet and across it, and through the hierarchy
    for node, group in groups.items():
        nets.find(("sub", node))
    for label in index.labels:
        if label.bus:
            continue
        sub = ("sub", node_of(label))
        nets.join(sub, ("G", label.text) if label.kind in ("global", "power") else ("L", label.sheet, label.text))
        if label.kind == "hierarchical":
            nets.join(sub, ("H", label.sheet, label.text))
    for symbol in index.symbols:
        for pin in symbol.pins:
            if pin.type == "power_in" and pin.hidden and not symbol.power:
                nets.join(("sub", node_of(pin)), ("G", pin.name))
    # A bus: each of its names' members is joined by its slot (a vector's index, a group's member name)
    # to the members of the bus's other names, the member in each name's own namespace, and the bus's
    # best name names its members as its driver would (``/D3`` for a local ``D[0..7]``).
    buses: dict[Any, list] = defaultdict(list)
    for label in index.labels:
        if label.bus:
            namespace = "G" if label.kind == "global" else ("L", label.sheet)
            priority = PRIORITY["global"] if label.kind == "global" else PRIORITY[label.kind]
            buses[node_of(label)].append((priority, label.kind, label.text, label.sheet, namespace))
    for sheet in index.sheets:
        if sheet.parent is None:
            continue
        for pin in sheet.pins:
            if is_bus_name(pin.name):
                buses[node_of(pin)].append((PRIORITY["sheet_pin"], "sheet_pin", pin.name, sheet.parent, ("L", sheet.path)))
            else:
                nets.join(("sub", node_of(pin)), ("H", sheet.path, pin.name))
    extra: list[tuple[Any, dict]] = []
    for node, drivers in buses.items():
        best = min(drivers, key=lambda driver: (-driver[0], _driver_name(driver[1], driver[2], driver[3])))
        for priority, kind, text, sheet, namespace in drivers:
            for slot, member in _slots(text):
                key = ("G", member) if namespace == "G" else (*namespace, member)
                nets.join(("bus", node, slot), key)
                if (priority, kind, text, sheet) == best[:4]:
                    extra.append((("bus", node, slot), {"drivers": [(priority, _driver_name(kind, member, sheet), sheet)],
                                                        "pins": [], "no_connect": False, "sheet": sheet, "bus": False}))

    # 3. The nets: every subgraph on wires with its joined neighbours, named by the best driver.
    joined: dict[Any, list] = defaultdict(list)
    for node, group in groups.items():
        if group["bus"]:
            continue
        joined[nets.find(("sub", node))].append(group)
    for key, group in extra:
        root = nets.find(key)
        if root in joined:  # a bus member no wire carries makes no net
            joined[root].append(group)
    names: dict[Any, str] = {}
    built: list[Net] = []
    net_of_node: dict[Any, str] = {}
    for root, members in joined.items():
        name = _best_name(members)
        if name is None:
            continue
        names[root] = name
        pins = sorted((pin for group in members for pin in group["pins"] if not pin.ref.startswith("#")),
                      key=lambda pin: (natural(pin.ref), natural(pin.number)))
        built.append(Net(name=name, pins=tuple(pins), labels=(), sheets=tuple(sorted({group["sheet"] for group in members
                                                                                      if group["sheet"]}))))
    for node, group in groups.items():
        if group["bus"]:
            bus_names = [driver[1] for driver in sorted(group["drivers"], key=lambda d: (-d[0], d[1] or ""))
                         if driver[1]]
            net_of_node[node] = bus_names[0] if bus_names else None
        else:
            net_of_node[node] = names.get(nets.find(("sub", node)))
    item_net = {}
    for item in [*index.wires, *index.labels, *index.junctions, *(pin for s in index.symbols for pin in s.pins),
                 *(pin for sheet in index.sheets for pin in sheet.pins)]:
        item_net[id(item)] = net_of_node.get(node_of(item))
    # A junction on a bus names the bus.
    for junction in index.junctions:
        if item_net.get(id(junction)) is None:
            item_net[id(junction)] = net_of_node.get(union.find(("junction", "bus", id(junction))))
    return item_net, built, warnings


def _best_name(members: list[dict]) -> str | None:
    """The best driver over a net's subgraphs (the module doc's step 4), or None for one with nothing."""
    best = None
    for group in members:
        drivers = group["drivers"]
        if not drivers:
            continue
        top = max(driver[0] for driver in drivers)
        candidates = [driver for driver in drivers if driver[0] == top]
        if top == PRIORITY["pin"]:
            pins = [driver[3] for driver in candidates]
            alone = len(group["pins"]) == 1 and (group["no_connect"] or pins[0].type == "no_connect")
            # KiCad's choice among pins: a name with the pin's function over one with its pad number.
            name = min((_pin_name(pin, alone) for pin in pins), key=lambda text: ("-Pad" in text, text))
            if len(group["pins"]) == 1 and len(members) == 1 and not alone:
                name = _pin_name(pins[0], True)
        else:
            name = min(driver[1] for driver in candidates)
        depth = group["sheet"].count("/") if group["sheet"] else 0
        key = (top >= _GLOBAL, top >= _STRONG, top, -depth)
        if best is None or key > best[0] or (key == best[0] and name < best[1]):
            best = (key, name)
    return best[1] if best else None


# --- the view ------------------------------------------------------------------------------------


class SchematicView:
    """A schematic read for references, in KiCad's frame (millimetres, y down, each sheet's page).

    ``sheets``, ``symbols``, ``nets`` and the rest are everything in it; :meth:`resolve` answers a
    reference: ``#U3`` a :class:`Part`-like list of the symbol's units (:meth:`part`), ``#U3.7`` a
    :class:`Pin`, ``#net:VBUS`` a :class:`Net`, ``#sheet:/Power/`` a :class:`Sheet`, ``#wire:<uuid>``
    (``#bus:``, ``#label:``, ``#junction:``, ``#no_connect:``, ``#symbol:``) the item KiCad saved with
    that uuid.
    """

    def __init__(self, path: Path, index: SchematicIndex, warnings: Sequence[str] = ()):
        self.path = Path(path)
        self.index = index
        self.root = index.root
        self.sheets = index.sheets
        self.symbols = index.symbols
        self.wires = index.wires
        self.junctions = index.junctions
        self.labels = index.labels
        self.no_connects = index.no_connects
        self.bus_entries = index.bus_entries
        self.nets = index.nets
        self.warnings = tuple(warnings)
        self._sheets = {sheet.path: sheet for sheet in index.sheets}
        self._parts: dict[str, list[Symbol]] = defaultdict(list)
        for symbol in index.symbols:
            self._parts[symbol.ref].append(symbol)
        self._nets = {net.name: net for net in index.nets}
        self._items: dict[str, dict[str, list]] = {kind: defaultdict(list) for kind in _ITEM_KINDS}
        for kind, items in (("wire", [w for w in index.wires if w.kind == "wire"]),
                            ("bus", [w for w in index.wires if w.kind == "bus"]),
                            ("label", [label for label in index.labels if label.kind not in ("power", "local_power")]),
                            ("junction", index.junctions), ("no_connect", index.no_connects),
                            ("symbol", index.symbols), ("bus_entry", index.bus_entries)):
            for item in items:
                if item.uuid:
                    self._items[kind][item.uuid].append(item)

    def __repr__(self) -> str:
        parts = sum(1 for ref in self._parts if not ref.startswith("#"))
        return f"SchematicView({self.root.name}: {len(self.sheets)} sheets, {parts} parts, {len(self.nets)} nets)"

    @property
    def pins(self) -> tuple[Pin, ...]:
        return self.index.pins

    @property
    def parts(self) -> tuple[str, ...]:
        """Every part's reference (power symbols' ``#PWR`` excepted), in KiCad's order."""
        return tuple(sorted((ref for ref in self._parts if not ref.startswith("#")), key=natural))

    def sheet(self, path: str) -> Sheet:
        """The sheet at ``path`` (``/``, ``/Power/``; the slashes round it optional)."""
        wanted = "/" + "/".join(part for part in str(path).split("/") if part) + "/"
        wanted = "/" if wanted == "//" else wanted
        found = self._sheets.get(wanted)
        if found is None:
            names = ", ".join(self._sheets)
            raise ValueError(f"{self.root.name} has no sheet {path}; its sheets are {names}")
        return found

    def part(self, ref: str) -> tuple[Symbol, ...]:
        """Every unit placed of the part ``ref`` (``"U3"``), in unit order."""
        found = self._parts.get(str(ref))
        if not found:
            close = sorted(difflib.get_close_matches(str(ref), list(self._parts), n=3), key=natural)
            hint = f"; did you mean {', '.join(close)}?" if close else f"; its parts are {', '.join(self.parts[:40])}"
            raise ValueError(f"{self.root.name} has no part {ref}{hint}")
        return tuple(sorted(found, key=lambda symbol: symbol.unit))

    def pin(self, ref: str, number: str) -> Pin:
        """Pin ``number`` of the part ``ref``, on whichever of its units holds it."""
        units = self.part(ref)
        for symbol in units:
            for pin in symbol.pins:
                if pin.number == str(number):
                    return pin
        numbers = sorted({pin.number for symbol in units for pin in symbol.pins}, key=natural)
        raise ValueError(f"{ref} has no pin {number}; its pins are {', '.join(numbers)}")

    def net(self, name: str) -> Net:
        """The net ``name``, as KiCad names it (``/MID``, ``GND``, ``/Power/VBUS``). A local net is
        found by its bare name too when only one sheet has it."""
        found = self._nets.get(str(name))
        if found is None:
            local = [net for net in self.nets if net.name.rsplit("/", 1)[-1] == str(name) and net.name.startswith("/")]
            if len(local) == 1:
                return local[0]
            close = sorted(difflib.get_close_matches(str(name), list(self._nets), n=3), key=natural)
            hint = f"; did you mean {', '.join(close)}?" if close else ""
            if len(local) > 1:
                hint = f"; on several sheets: {', '.join(net.name for net in local)}"
            raise ValueError(f"{self.root.name} has no net {name!r}{hint}")
        return found

    def item(self, kind: str, uid: str):
        """The ``kind`` (``wire``, ``bus``, ``label``, ``junction``, ``no_connect``, ``symbol``, ``bus_entry``)
        KiCad saved with uuid ``uid``. A sheet used twice holds its items twice: the first instance's answers."""
        if kind not in _ITEM_KINDS:
            raise ValueError(f"a schematic's items are its {', '.join(_ITEM_KINDS)}, not {kind!r}")
        found = self._items[kind].get(str(uid or "").lower())
        if not found:
            raise ValueError(f"{self.root.name} has no {kind} {uid}: an item is named by the uuid its file saved it with")
        return found[0]

    def resolve(self, ref: str):
        """What the reference ``ref`` names (see the class doc); a file before the ``#`` must name one of
        this schematic's sheet files."""
        answers = self.resolve_all(ref)
        if len(answers) != 1:
            raise ValueError(f"{ref!r} names {len(answers)} things; resolve_all() answers each, in the order written")
        return answers[0]

    def resolve_all(self, ref: str) -> list:
        """Every selector of a reference token (``divider.kicad_sch#R1,net:GND``), each resolved."""
        from cad.engine.formats.kicad.schematic_refs import parse_schematic_token

        token = parse_schematic_token(ref)
        if token is None:
            raise ValueError(f"not a schematic reference: {ref!r}; a schematic reference is #R1, #R1.2, #net:GND, "
                             f"#sheet:/Power/, #wire:<uuid>")
        if token.path and not any(ref_prefix_names(token.path, str(sheet.file)) for sheet in self.sheets):
            raise ValueError(f"reference names {token.path!r}, which is no sheet of {self.root.name}")
        if not token.selectors:
            raise ValueError(f"{ref!r} names the whole schematic; name a part, pin, net, sheet or item in it")
        return [self._answer(selector) for selector in token.selectors]

    def _answer(self, selector):
        if selector.kind == "part":
            return self.part(selector.ref)
        if selector.kind == "pad":
            return self.pin(selector.ref, selector.pad)
        if selector.kind == "net":
            return self.net(selector.net)
        if selector.kind == "sheet":
            return self.sheet(selector.sheet)
        return self.item(selector.kind, selector.id)


_ITEM_KINDS = ("wire", "bus", "label", "junction", "no_connect", "symbol", "bus_entry")


def read_schematic_index(path: Path | str) -> tuple[SchematicIndex, list[str]]:
    """The index of the schematic hierarchy ``path`` belongs to (:func:`read_schematic`'s), and what
    could not be read (a sheet file not there, a symbol the file does not embed)."""
    sheet = Path(path).expanduser()
    if sheet.suffix.lower() != ".kicad_sch":
        raise ValueError(f"{sheet.name} is not a KiCad schematic (.kicad_sch)")
    if not sheet.is_file():
        raise FileNotFoundError(f"{sheet} does not exist")
    root = root_of(sheet)
    reader = _Reader(root)
    try:
        reader.read()
    except sexpr.SexprError as error:
        raise ValueError(f"{root.name} is not a readable KiCad schematic: {error}") from None
    if sheet.resolve() not in {item.file for item in reader.sheets}:
        # A file outside its project's hierarchy is a root of its own.
        reader = _Reader(sheet.resolve())
        reader.read()
    item_net, nets, warnings = resolve_nets(reader)

    def named(items: Iterable) -> list:
        return [_with_net(item, item_net.get(id(item))) for item in items]

    labels = named(reader.labels)
    by_net: dict[str, list[Label]] = defaultdict(list)
    for label in labels:
        if label.net:
            by_net[label.net].append(label)
    symbols = []
    for symbol in reader.symbols:
        pins = tuple(_with_net(pin, item_net.get(id(pin))) for pin in symbol.pins)
        symbols.append(Symbol(**{**symbol.__dict__, "pins": pins}))
    pins_by_net: dict[str, list[Pin]] = defaultdict(list)
    for symbol in symbols:
        for pin in symbol.pins:
            if pin.net and not pin.ref.startswith("#"):
                pins_by_net[pin.net].append(pin)
    nets = sorted((Net(name=net.name, pins=tuple(sorted(pins_by_net.get(net.name, ()),
                                                         key=lambda pin: (natural(pin.ref), natural(pin.number)))),
                       labels=tuple(by_net.get(net.name, ())), sheets=net.sheets) for net in nets),
                  key=lambda net: natural(net.name))
    sheets = []
    ordered = sorted(reader.sheets, key=lambda sheet: (sheet.parent is not None, natural(sheet.page), sheet.path))
    for sheet_item in ordered:
        pins = tuple(_with_net(pin, item_net.get(id(pin))) for pin in sheet_item.pins)
        sheets.append(Sheet(**{**sheet_item.__dict__, "pins": pins}))
    index = SchematicIndex(
        root=reader.root, version=int(sexpr.number(sexpr.value(reader.trees[reader.root], "version"), 0)) or None,
        generator=" ".join(str(sexpr.value(reader.trees[reader.root], name, "") or "")
                           for name in ("generator", "generator_version")).strip(),
        sheets=tuple(sheets), symbols=tuple(symbols), wires=tuple(named(reader.wires)),
        junctions=tuple(named(reader.junctions)), labels=tuple(labels), no_connects=tuple(reader.no_connects),
        bus_entries=tuple(reader.bus_entries), nets=tuple(nets), trees=reader.trees, lib_symbols=reader.libraries)
    return index, [*reader.warnings, *warnings]


def _with_net(item, net: str | None):
    if not hasattr(item, "net"):
        return item
    return type(item)(**{**item.__dict__, "net": net})


def read_schematic(path: Path | str) -> SchematicView:
    """The KiCad schematic at ``path`` (a ``.kicad_sch``: the root sheet or any sheet of its project's
    hierarchy) for references: every sheet from the project's root down, its symbols and its nets.

    Everything is in KiCad's frame: millimetres, y down, on each sheet's page. Reads the sheet files
    alone; runs nothing.
    """
    index, warnings = read_schematic_index(path)
    return SchematicView(Path(path).expanduser().resolve(), index, warnings)
