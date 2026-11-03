"""A small two-sheet KiCad schematic for the tests that read schematics, in KiCad 9's file format.

Written as KiCad 9 writes a schematic (``(kicad_sch (version 20250114) (generator "eeschema")``,
every symbol's drawing embedded in its ``lib_symbols``, each placed symbol's reference in its
``instances``), so the readers and the snapshot need neither KiCad nor the sample corpus; ERC and
the exports run the same files through ``kicad-cli``. The symbols' drawings are this file's own,
not KiCad's libraries'.

The project ``divider`` (``divider.kicad_pro``, ``divider.kicad_sch``, ``load.kicad_sch``), in
KiCad's frame (millimetres, y down, on an A4 page), every point on the 1.27 mm grid:

- the root sheet: a resistor divider from ``+5V`` (a power symbol) through ``R1`` and ``R2`` to
  ``GND``; the middle node, a T with a junction, carries the local label ``MID`` (in the middle of
  its wire) and runs to the pin ``IN`` of the sheet ``Load``; ``J1``, a two-pin connector, mirrored,
  its pin 1 on the global label ``VOUT`` and its pin 2 on a second ``GND`` symbol;
- the sheet ``Load`` (``load.kicad_sch``, path ``/Load/``, page 2): the hierarchical label ``IN``
  on ``C1`` pin 1, ``C1`` pin 2 on ``GND``; the global label ``VOUT`` on ``R3`` pin 1, ``R3`` turned
  a quarter turn, its pin 2 under a no-connect.

The nets it makes (KiCad's names): ``+5V`` (R1.1), ``/MID`` (R1.2, R2.1, C1.1), ``GND`` (R2.2,
J1.2, C1.2), ``VOUT`` (J1.1, R3.1), and R3.2 alone, unconnected.

:func:`write_bus_schematic` writes a second project, ``busses``, for what a net crosses besides
wires (its nets: ``BUS_NETS``): ``U1``, a driver whose pins ``D0`` and ``D1`` are on wires labeled
``D0`` and ``D1``, bus entries onto a bus labeled ``D[0..1]`` that runs to the sheet pin ``Q[0..1]`` of
the sheet ``Child``, where the hierarchical label ``Q[0..1]``'s bus enters wires labeled ``Q0`` and
``Q1`` on ``R3`` and ``R4`` (a bus's members meet by index: ``D0`` is ``Q0``); ``U1``'s hidden power
input ``VCC`` (a legacy part's), which is the net of the ``VCC`` power symbol on ``R2``; and ``U1``'s
pin ``SCL`` on ``R1`` alone, a net only pins name (``Net-(U1-SCL)``: the pin's name over its pad's).
"""

from __future__ import annotations

import json
from pathlib import Path

__all__ = ["BUS_NETS", "NETS", "ROOT_UUID", "SHEET_UUID", "UUIDS", "at", "write_bus_schematic", "write_schematic"]

ROOT_UUID = "5c4e0000-0000-4000-8000-000000000001"
LOAD_UUID = "5c4e0000-0000-4000-8000-000000000002"  # the child file's own uuid
SHEET_UUID = "5c4e0000-0000-4000-8000-000000000003"  # the sheet symbol's, on the root sheet
#: Items the tests name by uuid.
UUIDS = {
    "mid wire": "5c4e0000-0000-4000-8000-0000000000a1",
    "mid label": "5c4e0000-0000-4000-8000-0000000000a2",
    "junction": "5c4e0000-0000-4000-8000-0000000000a3",
    "no connect": "5c4e0000-0000-4000-8000-0000000000a4",
    "R1": "5c4e0000-0000-4000-8000-0000000000b1",
}
#: The nets the schematic makes, by KiCad's name: the pins on each.
NETS = {
    "+5V": {"R1.1"},
    "/MID": {"R1.2", "R2.1", "C1.1"},
    "GND": {"R2.2", "J1.2", "C1.2"},
    "VOUT": {"J1.1", "R3.1"},
}
#: The nets the bus project makes, by KiCad's name.
BUS_NETS = {
    "/D0": {"U1.1", "R3.1"},
    "/D1": {"U1.2", "R4.1"},
    "VCC": {"U1.3", "R2.1"},
    "Net-(U1-SCL)": {"U1.4", "R1.1"},
}
_GRID = 1.27
_counter = iter(range(1, 10_000))


def at(x: float, y: float) -> tuple[float, float]:
    """A point given in grid steps, in millimetres."""
    return round(x * _GRID, 4), round(y * _GRID, 4)


def _uuid() -> str:
    return f"5c4e0000-0000-4000-8000-{next(_counter):012x}"


def _xy(x: float, y: float) -> str:
    px, py = at(x, y)
    return f"{px:g} {py:g}"


_FONT = "(effects (font (size 1.27 1.27)))"
_HIDE = "(effects (font (size 1.27 1.27)) (hide yes))"


def _pin(kind: str, x: float, y: float, angle: int, length: float, name: str, number: str, hidden: bool = False) -> str:
    hide = " (hide yes)" if hidden else ""
    return (f'(pin {kind} line (at {x:g} {y:g} {angle}) (length {length:g}){hide} (name "{name}" {_FONT}) '
            f'(number "{number}" {_FONT}))')


def _prop(name: str, value: str, x: float = 0, y: float = 0, hidden: bool = False, angle: int = 0) -> str:
    return f'(property "{name}" "{value}" (at {x:g} {y:g} {angle}) {_HIDE if hidden else _FONT})'


_LIB_SYMBOLS = f"""(lib_symbols
  (symbol "Device:R" (pin_numbers (hide yes)) (pin_names (offset 0)) (exclude_from_sim no) (in_bom yes) (on_board yes)
    {_prop("Reference", "R", 2.032, 0, angle=90)} {_prop("Value", "R", 0, 0, angle=90)}
    {_prop("Footprint", "", hidden=True)} {_prop("Datasheet", "", hidden=True)}
    (symbol "R_0_1" (rectangle (start -1.016 -2.54) (end 1.016 2.54) (stroke (width 0.254) (type default)) (fill (type none))))
    (symbol "R_1_1" {_pin("passive", 0, 3.81, 270, 1.27, "~", "1")} {_pin("passive", 0, -3.81, 90, 1.27, "~", "2")}))
  (symbol "Device:C" (pin_numbers (hide yes)) (pin_names (offset 0.254)) (exclude_from_sim no) (in_bom yes) (on_board yes)
    {_prop("Reference", "C", 0.635, 2.54)} {_prop("Value", "C", 0.635, -2.54)}
    {_prop("Footprint", "", hidden=True)} {_prop("Datasheet", "", hidden=True)}
    (symbol "C_0_1"
      (polyline (pts (xy -2.032 -0.762) (xy 2.032 -0.762)) (stroke (width 0.508) (type default)) (fill (type none)))
      (polyline (pts (xy -2.032 0.762) (xy 2.032 0.762)) (stroke (width 0.508) (type default)) (fill (type none))))
    (symbol "C_1_1" {_pin("passive", 0, 3.81, 270, 3.048, "~", "1")} {_pin("passive", 0, -3.81, 90, 3.048, "~", "2")}))
  (symbol "Connector:Conn_01x02" (pin_names (offset 1.016) (hide yes)) (exclude_from_sim no) (in_bom yes) (on_board yes)
    {_prop("Reference", "J", 0, 2.54)} {_prop("Value", "Conn_01x02", 0, -5.08)}
    {_prop("Footprint", "", hidden=True)} {_prop("Datasheet", "", hidden=True)}
    (symbol "Conn_01x02_1_1"
      (rectangle (start -1.27 1.27) (end 1.27 -3.81) (stroke (width 0.254) (type default)) (fill (type background)))
      {_pin("passive", -5.08, 0, 0, 3.81, "Pin_1", "1")} {_pin("passive", -5.08, -2.54, 0, 3.81, "Pin_2", "2")}))
  (symbol "power:+5V" (power) (pin_numbers (hide yes)) (pin_names (offset 0) (hide yes)) (exclude_from_sim no) (in_bom yes) (on_board yes)
    {_prop("Reference", "#PWR", 0, -3.81, hidden=True)} {_prop("Value", "+5V", 0, 3.556)}
    {_prop("Footprint", "", hidden=True)} {_prop("Datasheet", "", hidden=True)}
    (symbol "+5V_0_1"
      (polyline (pts (xy -0.762 1.27) (xy 0 2.54) (xy 0.762 1.27)) (stroke (width 0) (type default)) (fill (type none)))
      (polyline (pts (xy 0 0) (xy 0 2.54)) (stroke (width 0) (type default)) (fill (type none))))
    (symbol "+5V_1_1" {_pin("power_in", 0, 0, 90, 0, "~", "1", hidden=True)}))
  (symbol "power:GND" (power) (pin_numbers (hide yes)) (pin_names (offset 0) (hide yes)) (exclude_from_sim no) (in_bom yes) (on_board yes)
    {_prop("Reference", "#PWR", 0, -6.35, hidden=True)} {_prop("Value", "GND", 0, -3.81)}
    {_prop("Footprint", "", hidden=True)} {_prop("Datasheet", "", hidden=True)}
    (symbol "GND_0_1"
      (polyline (pts (xy 0 0) (xy 0 -1.27) (xy 1.27 -1.27) (xy 0 -2.54) (xy -1.27 -1.27) (xy 0 -1.27))
        (stroke (width 0) (type default)) (fill (type none))))
    (symbol "GND_1_1" {_pin("power_in", 0, 0, 270, 0, "~", "1", hidden=True)})))"""


def _symbol(lib_id: str, ref: str, value: str, x: float, y: float, path: str, *, angle: int = 0, mirror: str = "",
            pins: tuple[str, ...] = ("1", "2"), uuid: str | None = None, footprint: str = "", mpn: str = "") -> str:
    px, py = at(x, y)
    mirrored = f" (mirror {mirror})" if mirror else ""
    hidden_ref = ref.startswith("#")
    fields = [_prop("Reference", ref, px + 2.54, py, hidden=hidden_ref), _prop("Value", value, px + 2.54, py + 2.54),
              _prop("Footprint", footprint, px, py, hidden=True), _prop("Datasheet", "", px, py, hidden=True)]
    if mpn:
        fields.append(_prop("MPN", mpn, px, py, hidden=True))
    pin_list = " ".join(f'(pin "{number}" (uuid "{_uuid()}"))' for number in pins)
    return (f'(symbol (lib_id "{lib_id}") (at {px:g} {py:g} {angle}){mirrored} (unit 1) (exclude_from_sim no) (in_bom yes) '
            f'(on_board yes) (dnp no) (uuid "{uuid or _uuid()}") {" ".join(fields)} {pin_list} '
            f'(instances (project "divider" (path "{path}" (reference "{ref}") (unit 1)))))')


def _wire(*points: tuple[float, float], uuid: str | None = None) -> str:
    return "\n".join(f'(wire (pts (xy {_xy(*a)}) (xy {_xy(*b)})) (stroke (width 0) (type default)) (uuid "{uuid or _uuid()}"))'
                     for a, b in zip(points, points[1:]))


def _label(kind: str, text: str, x: float, y: float, angle: int = 0, shape: str = "", uuid: str | None = None) -> str:
    shaped = f" (shape {shape})" if shape else ""
    justify = "(justify left bottom)" if kind == "label" else "(justify left)"
    fields = ' (fields_autoplaced yes)' if kind == "global_label" else ""
    return (f'({kind} "{text}"{shaped} (at {_xy(x, y)} {angle}){fields} (effects (font (size 1.27 1.27)) {justify}) '
            f'(uuid "{uuid or _uuid()}"))')


def _root() -> str:
    path = f"/{ROOT_UUID}"
    sx, sy = at(100, 45)
    return f"""(kicad_sch (version 20250114) (generator "eeschema") (generator_version "9.0") (uuid "{ROOT_UUID}") (paper "A4")
  (title_block (title "Divider") (rev "1"))
  {_LIB_SYMBOLS}
  (junction (at {_xy(80, 51)}) (diameter 0) (color 0 0 0 0) (uuid "{UUIDS['junction']}"))
  {_wire((80, 40), (80, 44))}
  {_wire((80, 50), (80, 51))}
  {_wire((80, 51), (80, 53))}
  {_wire((80, 51), (100, 51), uuid=UUIDS['mid wire'])}
  {_wire((80, 59), (80, 62))}
  {_wire((64, 50), (68, 50))}
  {_wire((64, 52), (66, 52), (66, 55))}
  {_label("label", "MID", 90, 51, uuid=UUIDS['mid label'])}
  {_label("global_label", "VOUT", 68, 50, 0, "output")}
  {_symbol("power:+5V", "#PWR01", "+5V", 80, 40, path, pins=("1",))}
  {_symbol("Device:R", "R1", "10k", 80, 47, path, uuid=UUIDS['R1'], footprint="Resistor_SMD:R_0603_1608Metric",
           mpn="RC0603FR-0710KL")}
  {_symbol("Device:R", "R2", "10k", 80, 56, path, footprint="Resistor_SMD:R_0603_1608Metric")}
  {_symbol("power:GND", "#PWR02", "GND", 80, 62, path, pins=("1",))}
  {_symbol("Connector:Conn_01x02", "J1", "Conn_01x02", 60, 50, path, mirror="y")}
  {_symbol("power:GND", "#PWR03", "GND", 66, 55, path, pins=("1",))}
  (sheet (at {sx:g} {sy:g}) (size {25 * _GRID:g} {15 * _GRID:g}) (exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no)
    (stroke (width 0.1524) (type solid)) (fill (color 0 0 0 0.0000)) (uuid "{SHEET_UUID}")
    (property "Sheetname" "Load" (at {sx:g} {sy - 0.7:g} 0) (effects (font (size 1.27 1.27)) (justify left bottom)))
    (property "Sheetfile" "load.kicad_sch" (at {sx:g} {sy + 15 * _GRID + 0.6:g} 0) (effects (font (size 1.27 1.27)) (justify left top)))
    (pin "IN" input (at {_xy(100, 51)} 180) (uuid "{_uuid()}") (effects (font (size 1.27 1.27)) (justify left)))
    (instances (project "divider" (path "{path}" (page "2")))))
  (sheet_instances (path "/" (page "1")))
  (embedded_fonts no)
)
"""


def _load() -> str:
    path = f"/{ROOT_UUID}/{SHEET_UUID}"
    return f"""(kicad_sch (version 20250114) (generator "eeschema") (generator_version "9.0") (uuid "{LOAD_UUID}") (paper "A4")
  {_LIB_SYMBOLS}
  (no_connect (at {_xy(52, 30)}) (uuid "{UUIDS['no connect']}"))
  {_wire((40, 40), (50, 40))}
  {_wire((50, 46), (50, 48))}
  {_wire((40, 30), (46, 30))}
  {_label("hierarchical_label", "IN", 40, 40, 180, "input")}
  {_label("global_label", "VOUT", 40, 30, 180, "input")}
  {_symbol("Device:C", "C1", "100n", 50, 43, path, footprint="Capacitor_SMD:C_0603_1608Metric")}
  {_symbol("power:GND", "#PWR04", "GND", 50, 48, path, pins=("1",))}
  {_symbol("Device:R", "R3", "1k", 49, 30, path, angle=90)}
  (embedded_fonts no)
)
"""


def _project() -> str:
    return json.dumps({"meta": {"filename": "divider.kicad_pro", "version": 3},
                       "sheets": [[ROOT_UUID, "Root"], [SHEET_UUID, "Load"]]}, indent=2)


def write_schematic(folder: Path | str) -> Path:
    """Write the project into ``folder`` and return its root sheet, ``divider.kicad_sch``."""
    global _counter
    _counter = iter(range(1, 10_000))
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "divider.kicad_pro").write_text(_project(), encoding="utf-8")
    (folder / "load.kicad_sch").write_text(_load(), encoding="utf-8")
    root = folder / "divider.kicad_sch"
    root.write_text(_root(), encoding="utf-8")
    return root


# --- the bus project -----------------------------------------------------------------------------

BUS_ROOT_UUID = "b05e0000-0000-4000-8000-000000000001"
BUS_CHILD_UUID = "b05e0000-0000-4000-8000-000000000002"
BUS_SHEET_UUID = "b05e0000-0000-4000-8000-000000000003"

_DRIVER = f"""(symbol "test:DRV" (pin_names (offset 0.508)) (exclude_from_sim no) (in_bom yes) (on_board yes)
    {_prop("Reference", "U", 0, 6.35)} {_prop("Value", "DRV", 0, -6.35)}
    {_prop("Footprint", "", hidden=True)} {_prop("Datasheet", "", hidden=True)}
    (symbol "DRV_0_1" (rectangle (start -2.54 3.81) (end 2.54 -3.81) (stroke (width 0.254) (type default)) (fill (type background))))
    (symbol "DRV_1_1" {_pin("output", 5.08, 2.54, 180, 2.54, "D0", "1")} {_pin("output", 5.08, 0, 180, 2.54, "D1", "2")}
      {_pin("power_in", 0, 5.08, 270, 1.27, "VCC", "3", hidden=True)} {_pin("bidirectional", 5.08, -2.54, 180, 2.54, "SCL", "4")}))"""
_VCC = f"""(symbol "power:VCC" (power) (pin_numbers (hide yes)) (pin_names (offset 0) (hide yes)) (exclude_from_sim no) (in_bom yes) (on_board yes)
    {_prop("Reference", "#PWR", 0, -3.81, hidden=True)} {_prop("Value", "VCC", 0, 3.556)}
    {_prop("Footprint", "", hidden=True)} {_prop("Datasheet", "", hidden=True)}
    (symbol "VCC_0_1" (polyline (pts (xy -0.762 1.27) (xy 0 2.54) (xy 0.762 1.27)) (stroke (width 0) (type default)) (fill (type none)))
      (polyline (pts (xy 0 0) (xy 0 2.54)) (stroke (width 0) (type default)) (fill (type none))))
    (symbol "VCC_1_1" {_pin("power_in", 0, 0, 90, 0, "~", "1", hidden=True)}))"""


def _libraries() -> str:
    return _LIB_SYMBOLS[:-1] + f"\n  {_DRIVER}\n  {_VCC})"


def _bus(*points: tuple[float, float]) -> str:
    return "\n".join(f'(bus (pts (xy {_xy(*a)}) (xy {_xy(*b)})) (stroke (width 0) (type default)) (uuid "{_uuid()}"))'
                     for a, b in zip(points, points[1:]))


def _entry(x: float, y: float, dx: float, dy: float) -> str:
    return (f'(bus_entry (at {_xy(x, y)}) (size {dx * _GRID:g} {dy * _GRID:g}) (stroke (width 0) (type default)) '
            f'(uuid "{_uuid()}"))')


def _bus_root() -> str:
    path = f"/{BUS_ROOT_UUID}"
    sx, sy = at(60, 40)
    return f"""(kicad_sch (version 20250114) (generator "eeschema") (generator_version "9.0") (uuid "{BUS_ROOT_UUID}") (paper "A4")
  {_libraries()}
  {_symbol("test:DRV", "U1", "DRV", 40, 40, path, pins=("1", "2", "3", "4"))}
  {_wire((44, 38), (48, 38))}
  {_wire((44, 40), (48, 40))}
  {_label("label", "D0", 45, 38)}
  {_label("label", "D1", 45, 40)}
  {_entry(48, 38, 2, -2)}
  {_entry(48, 40, 2, -2)}
  {_bus((50, 36), (50, 38), (50, 46), (60, 46))}
  {_label("label", "D[0..1]", 53, 46)}
  {_wire((44, 42), (45, 42), (45, 50), (46, 50))}
  {_symbol("Device:R", "R1", "1k", 49, 50, path, angle=90)}
  {_symbol("power:VCC", "#PWR01", "VCC", 30, 27, path, pins=("1",))}
  {_wire((30, 27), (30, 30))}
  {_symbol("Device:R", "R2", "1k", 30, 33, path)}
  (sheet (at {sx:g} {sy:g}) (size {20 * _GRID:g} {10 * _GRID:g}) (exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no)
    (stroke (width 0.1524) (type solid)) (fill (color 0 0 0 0.0000)) (uuid "{BUS_SHEET_UUID}")
    (property "Sheetname" "Child" (at {sx:g} {sy - 0.7:g} 0) (effects (font (size 1.27 1.27)) (justify left bottom)))
    (property "Sheetfile" "child.kicad_sch" (at {sx:g} {sy + 10 * _GRID + 0.6:g} 0) (effects (font (size 1.27 1.27)) (justify left top)))
    (pin "Q[0..1]" bidirectional (at {_xy(60, 46)} 180) (uuid "{_uuid()}") (effects (font (size 1.27 1.27)) (justify left)))
    (instances (project "busses" (path "{path}" (page "2")))))
  (sheet_instances (path "/" (page "1")))
  (embedded_fonts no)
)
"""


def _bus_child() -> str:
    path = f"/{BUS_ROOT_UUID}/{BUS_SHEET_UUID}"
    return f"""(kicad_sch (version 20250114) (generator "eeschema") (generator_version "9.0") (uuid "{BUS_CHILD_UUID}") (paper "A4")
  {_libraries()}
  {_label("hierarchical_label", "Q[0..1]", 20, 30, 180, "bidirectional")}
  {_bus((20, 30), (24, 30), (24, 40))}
  {_entry(24, 32, 2, 2)}
  {_entry(24, 36, 2, 2)}
  {_wire((26, 34), (30, 34))}
  {_wire((26, 38), (30, 38))}
  {_label("label", "Q0", 27, 34)}
  {_label("label", "Q1", 27, 38)}
  {_symbol("Device:R", "R3", "1k", 33, 34, path, angle=90)}
  {_symbol("Device:R", "R4", "1k", 33, 38, path, angle=90)}
  (embedded_fonts no)
)
"""


def write_bus_schematic(folder: Path | str) -> Path:
    """Write the bus project (the module doc) into ``folder`` and return its root sheet, ``busses.kicad_sch``."""
    global _counter
    _counter = iter(range(5_000, 10_000))
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "busses.kicad_pro").write_text(json.dumps({"meta": {"filename": "busses.kicad_pro", "version": 3}}),
                                             encoding="utf-8")
    (folder / "child.kicad_sch").write_text(_bus_child(), encoding="utf-8")
    root = folder / "busses.kicad_sch"
    root.write_text(_bus_root(), encoding="utf-8")
    return root
