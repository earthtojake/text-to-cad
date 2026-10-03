"""A board's netlist as a ``.kicad_sch`` net-label schematic.

The script states the circuit; the schematic is generated from it, so it is
correct by construction and needs no wires routed between symbols. Each symbol
unit stands on a grid in the order the parts were made; every connected pin
gets a short stub and a global label carrying its net's name (labels with one
name are one net, in KiCad as on paper, and a global label names the net
exactly as the script does); a pin marked no-connect gets KiCad's ``X``; a
net powered from off the board gets a ``PWR_FLAG``. KiCad's ERC and its
schematic-to-board parity check then run on a real schematic.

Symbols are copied from the library into ``lib_symbols`` (a derived symbol
flattened onto its parent, as KiCad does), so the file stands alone. All
coordinates sit on KiCad's 1.27 mm connection grid.
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass

from cadgen.kicad import sexpr
from cadgen.kicad.design import Board, Part, _natural, kicad_net_name
from cadgen.kicad.ids import Ids
from cadgen.kicad.library import Symbol
from cadgen.kicad.sexpr import Sym

__all__ = ["SCHEMATIC_FORMAT_VERSION", "schematic_document", "symbol_path_key"]

SCHEMATIC_FORMAT_VERSION = 20260101
GENERATOR = "cadgen"
GENERATOR_VERSION = "10.0"

GRID = 1.27
STUB = 2.54
LABEL_SIZE = 1.27
_SPACING = 7.62
_PAGE_MARGIN = 25.4
_PAGES = (("A4", 297.0, 210.0), ("A3", 420.0, 297.0), ("A2", 594.0, 420.0), ("A1", 841.0, 594.0), ("A0", 1189.0, 841.0))


def symbol_path_key(ref: str, unit: int) -> str:
    return f"symbol:{ref}:{unit}"


def _snap(value: float) -> float:
    snapped = round(round(value / GRID) * GRID, 4)
    return 0.0 if snapped == 0 else snapped


@dataclass(frozen=True)
class _Unit:
    part: Part | None
    symbol: Symbol
    unit: int
    ref: str
    value: str
    # Extents in symbol coordinates (y up), labels included.
    left: float
    right: float
    bottom: float
    top: float


def _graphic_extent(symbol: Symbol, unit: int) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for sub in sexpr.find_all(symbol.tree, "symbol"):
        name = str(sub[1])
        try:
            sub_unit = int(name.rsplit("_", 2)[-2])
        except (ValueError, IndexError):
            continue
        if sub_unit not in (0, unit):
            continue
        for item in sub[2:]:
            if not isinstance(item, list) or item[0] == "pin":
                continue
            for key in ("start", "end", "mid", "center", "at"):
                node = sexpr.find(item, key)
                if node is not None and len(node) >= 3:
                    points.append((float(node[1]), float(node[2])))
            if item[0] == "circle":
                center, radius = sexpr.find(item, "center"), sexpr.value(item, "radius", 0)
                if center is not None:
                    points.extend([(float(center[1]) - float(radius), float(center[2]) - float(radius)),
                                   (float(center[1]) + float(radius), float(center[2]) + float(radius))])
            pts = sexpr.find(item, "pts")
            if pts is not None:
                points.extend((float(xy[1]), float(xy[2])) for xy in sexpr.find_all(pts, "xy"))
    return points


def _outward(angle: float) -> tuple[float, float]:
    """A pin's outward direction in SCHEMATIC coordinates (y down) from its library angle."""
    radians = math.radians(angle)
    # The library angle points from the pin's tip into the body, y up.
    return (round(-math.cos(radians)), round(math.sin(radians)))


def _label_length(text: str) -> float:
    return len(text) * LABEL_SIZE * 0.8 + 1.0


def _unit_pins(symbol: Symbol, unit: int):
    return [pin for pin in symbol.pins if pin.unit in (0, unit) and pin.body_style in (0, 1)]


def _measure(part: Part | None, symbol: Symbol, unit: int, ref: str, value: str, net_of) -> _Unit:
    points = _graphic_extent(symbol, unit)
    left = right = bottom = top = 0.0
    if points:
        left, right = min(p[0] for p in points), max(p[0] for p in points)
        bottom, top = min(p[1] for p in points), max(p[1] for p in points)
    reach = {"left": 0.0, "right": 0.0, "up": 0.0, "down": 0.0}
    for pin in _unit_pins(symbol, unit):
        left, right = min(left, pin.x), max(right, pin.x)
        bottom, top = min(bottom, pin.y), max(top, pin.y)
        name = net_of(pin.number)
        if name is None:
            continue
        dx, dy = _outward(pin.angle)
        length = STUB + _label_length(name)
        if dx > 0:
            reach["right"] = max(reach["right"], pin.x + length - right)
        elif dx < 0:
            reach["left"] = max(reach["left"], left - (pin.x - length))
        elif dy < 0:
            reach["up"] = max(reach["up"], pin.y + length - top)
        else:
            reach["down"] = max(reach["down"], bottom - (pin.y - length))
    text_room = 2 * 2.54  # reference and value above and below
    return _Unit(
        part=part,
        symbol=symbol,
        unit=unit,
        ref=ref,
        value=value,
        left=left - max(reach["left"], 0.0),
        right=right + max(reach["right"], 0.0),
        bottom=bottom - max(reach["down"], 0.0) - text_room,
        top=top + max(reach["up"], 0.0) + text_room,
    )


def _pack(units: list[_Unit]) -> tuple[str, float, float, list[tuple[float, float]]]:
    """A page and each unit's symbol origin, packed in rows (schematic coordinates)."""
    widest = max((unit.right - unit.left for unit in units), default=0.0)
    area = sum((unit.right - unit.left + _SPACING) * (unit.top - unit.bottom + _SPACING) for unit in units)
    for name, width, height in _PAGES:
        usable_width, usable_height = width - 2 * _PAGE_MARGIN, height - 2 * _PAGE_MARGIN
        if widest > usable_width or area * 1.3 > usable_width * usable_height:
            continue
        origins = _rows(units, usable_width)
        if origins is not None and origins[1] <= usable_height:
            return name, width, height, origins[0]
    width = max(1189.0, widest + 2 * _PAGE_MARGIN)
    origins, used_height = _rows(units, width - 2 * _PAGE_MARGIN)
    return "User", width, used_height + 2 * _PAGE_MARGIN, origins


def _rows(units: list[_Unit], usable_width: float):
    origins: list[tuple[float, float]] = []
    x = y = row_height = 0.0
    for unit in units:
        width, height = unit.right - unit.left, unit.top - unit.bottom
        if x > 0 and x + width > usable_width:
            x, y = 0.0, y + row_height + _SPACING
            row_height = 0.0
        origins.append((_snap(_PAGE_MARGIN + x - unit.left), _snap(_PAGE_MARGIN + y + unit.top)))
        x += width + _SPACING
        row_height = max(row_height, height)
    return origins, y + row_height


def _effects(*, hidden: bool = False, justify: list | None = None) -> list:
    node: list = [Sym("effects"), [Sym("font"), [Sym("size"), LABEL_SIZE, LABEL_SIZE]]]
    if justify:
        node.append([Sym("justify"), *justify])
    if hidden:
        node.append([Sym("hide"), Sym("yes")])
    return node


def _property(key: str, value: str, at: tuple[float, float, float], *, hidden: bool, effects: list | None = None) -> list:
    """A symbol field. ``effects`` is the library field's (its font and justification), as
    KiCad copies them when placing a symbol; whether it shows is the writer's to say."""
    node: list = [Sym("property"), key, value, [Sym("at"), at[0], at[1], at[2]]]
    if hidden:
        node.append([Sym("hide"), Sym("yes")])
    if effects is None:
        node.append(_effects())
    else:
        node.append([entry for entry in copy.deepcopy(effects) if sexpr.head(entry) != "hide"])
    return node


def _library_property(symbol: Symbol, key: str) -> list | None:
    for node in sexpr.find_all(symbol.tree, "property"):
        if node[1] == key:
            return node
    return None


def _library_property_at(symbol: Symbol, key: str) -> tuple[float, float, float] | None:
    node = _library_property(symbol, key)
    at = sexpr.find(node, "at") if node is not None else None
    if at is None:
        return None
    return float(at[1]), float(at[2]), float(at[3]) if len(at) > 3 else 0.0


def schematic_document(board: Board, *, project: str, net_of_pin, power_flag_nets: list[str]) -> tuple[list, dict[str, str]]:
    """The ``.kicad_sch`` tree, and each reference's symbol path for the board's footprints.

    ``net_of_pin(part, number)`` names the net a pin is on, or ``None``.
    """
    ids = Ids(project)
    root = ids("sheet:/")
    used_symbols: dict[str, Symbol] = {}
    units: list[_Unit] = []
    for part in board.parts:
        used_symbols.setdefault(part.symbol.lib_id, part.symbol)
        for unit in range(1, part.symbol.unit_count + 1):
            units.append(_measure(part, part.symbol, unit, part.ref, part.value, lambda number, part=part: net_of_pin(part, number)))
    flag_symbol: Symbol | None = None
    if power_flag_nets:
        flag_symbol = board.libraries.symbol("power:PWR_FLAG")
        used_symbols.setdefault(flag_symbol.lib_id, flag_symbol)
        for index, net_name in enumerate(power_flag_nets, start=1):
            units.append(_measure(None, flag_symbol, 1, f"#FLG{index:02d}", "PWR_FLAG", lambda number, net_name=net_name: net_name))
    page, page_width, page_height, origins = _pack(units)

    document: list = [
        Sym("kicad_sch"),
        [Sym("version"), SCHEMATIC_FORMAT_VERSION],
        [Sym("generator"), GENERATOR],
        [Sym("generator_version"), GENERATOR_VERSION],
        [Sym("uuid"), root],
        [Sym("paper"), page] if page != "User" else [Sym("paper"), "User", page_width, page_height],
        [Sym("title_block"), [Sym("title"), board.title or project]],
        [Sym("lib_symbols"), *(symbol.tree for _lib_id, symbol in sorted(used_symbols.items()))],
    ]
    items: list[list] = []
    symbols: list[list] = []
    paths: dict[str, str] = {}
    flag_index = 0
    for unit, (origin_x, origin_y) in zip(units, origins):
        symbol = unit.symbol
        key = symbol_path_key(unit.ref, unit.unit)
        instance_uuid = ids(key)
        if unit.part is not None and unit.ref not in paths:
            paths[unit.ref] = f"/{instance_uuid}"
        is_flag = unit.part is None
        if is_flag:
            flag_index += 1
        node: list = [
            Sym("symbol"),
            [Sym("lib_id"), symbol.lib_id],
            [Sym("at"), origin_x, origin_y, 0],
            [Sym("unit"), unit.unit],
            [Sym("body_style"), 1],
            [Sym("exclude_from_sim"), Sym("yes" if str(sexpr.value(symbol.tree, "exclude_from_sim") or "no") == "yes" else "no")],
            [Sym("in_bom"), Sym("no" if is_flag or not symbol.in_bom else "yes")],
            [Sym("on_board"), Sym("no" if is_flag else "yes")],
            [Sym("in_pos_files"), Sym("no" if is_flag else "yes")],
            [Sym("dnp"), Sym("yes" if unit.part is not None and unit.part.dnp else "no")],
            [Sym("uuid"), instance_uuid],
        ]
        fields = [("Reference", unit.ref, False), ("Value", unit.value, False)]
        if unit.part is not None:
            fields.append(("Footprint", unit.part.footprint.lib_id, True))
            fields.append(("Datasheet", symbol.properties.get("Datasheet", ""), True))
            fields.append(("Description", symbol.properties.get("Description", ""), True))
            # The library symbol's own fields travel with it (a diode's Sim.Device, so KiCad's
            # simulator can read the schematic), then the part's properties=.
            fields.extend((key_, value_, True) for key_, value_ in sorted(unit.part.fields.items()))
        else:
            fields.append(("Footprint", "", True))
            fields.append(("Datasheet", "", True))
            fields.append(("Description", symbol.properties.get("Description", ""), True))
        for field_key, field_value, hidden in fields:
            library_at = _library_property_at(symbol, field_key)
            if library_at is None:
                at = (origin_x, origin_y, 0.0)
            else:
                at = (_snap(origin_x + library_at[0]), _snap(origin_y - library_at[1]), library_at[2])
            library_field = _library_property(symbol, field_key)
            effects = sexpr.find(library_field, "effects") if library_field is not None else None
            node.append(_property(field_key, field_value, at, hidden=hidden, effects=effects))
        for number in symbol.pin_numbers():
            node.append([Sym("pin"), number, [Sym("uuid"), ids(f"{key}:pin:{number}")]])
        node.append(
            [Sym("instances"), [Sym("project"), project, [Sym("path"), f"/{root}", [Sym("reference"), unit.ref], [Sym("unit"), unit.unit]]]]
        )
        symbols.append(node)
        # Stubs and labels, and no-connect flags.
        for pin in _unit_pins(symbol, unit.unit):
            tip = (_snap(origin_x + pin.x), _snap(origin_y - pin.y))
            pin_key = f"{key}:pin:{pin.number}:{pin.x}:{pin.y}"
            if is_flag:
                net_name = power_flag_nets[flag_index - 1]
            else:
                net_name = net_of_pin(unit.part, pin.number)
            if net_name is None:
                if not is_flag and (unit.part._index, pin.number) in board._no_connects:
                    items.append([Sym("no_connect"), [Sym("at"), *tip], [Sym("uuid"), ids(f"{pin_key}:nc")]])
                continue
            dx, dy = _outward(pin.angle)
            end = (_snap(tip[0] + dx * STUB), _snap(tip[1] + dy * STUB))
            items.append(
                [Sym("wire"), [Sym("pts"), [Sym("xy"), *tip], [Sym("xy"), *end]],
                 [Sym("stroke"), [Sym("width"), 0], [Sym("type"), Sym("default")]], [Sym("uuid"), ids(f"{pin_key}:wire")]]
            )
            if dx > 0:
                angle, justify = 0, Sym("left")
            elif dx < 0:
                angle, justify = 180, Sym("right")
            elif dy < 0:
                angle, justify = 90, Sym("left")
            else:
                angle, justify = 270, Sym("right")
            # GLOBAL labels: a net is named exactly as the script names it ("GND"),
            # where a local label would make it "/GND" and disagree with the board.
            items.append(
                [
                    Sym("global_label"),
                    kicad_net_name(net_name),
                    [Sym("shape"), Sym("passive")],
                    [Sym("at"), end[0], end[1], angle],
                    [Sym("fields_autoplaced"), Sym("yes")],
                    _effects(justify=[justify]),
                    [Sym("uuid"), ids(f"{pin_key}:label")],
                    [
                        Sym("property"),
                        "Intersheetrefs",
                        "${INTERSHEET_REFS}",
                        [Sym("at"), end[0], end[1], 0],
                        _effects(justify=[justify], hidden=True),
                    ],
                ]
            )
    document.extend(items)
    document.extend(symbols)
    document.append([Sym("sheet_instances"), [Sym("path"), "/", [Sym("page"), "1"]]])
    document.append([Sym("embedded_fonts"), Sym("no")])
    return document, paths


def sorted_parts(board: Board) -> list[Part]:
    return sorted(board.parts, key=lambda part: _natural(part.ref))
