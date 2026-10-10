"""Small KiCad 10 schematics written by hand, for tests that read a schematic back.

A schematic embeds the library symbols it uses (``lib_symbols``), so these need no
library and no KiCad to write. The symbols, in their library's frame (y up):

- ``Test:R``: two passive pins, ``1`` at (0, 5.08) and ``2`` at (0, -5.08), each 2.54
  long into a body from (-1.016, -2.54) to (1.016, 2.54): placed unturned, pin 1 is
  5.08 above the symbol's point on the sheet and pin 2 5.08 below.
- ``Test:ODD``: four pins, one on each side, none where another could land under a
  turn or a mirror: ``1`` (-7.62, 2.54) pointing right, ``2`` (10.16, -2.54) left,
  ``3`` (2.54, 7.62) down, ``4`` (-2.54, -10.16) up; each ends on its body's edge,
  the square from (-5.08, -5.08) to (5.08, 5.08).
- ``Test:PWR``: a global power symbol, its one ``power_in`` pin at its point.

Every UUID is derived from the document's name and a count, so the same calls write
the same bytes. Two fixtures both suites read, with what KiCad 10 makes of them:
:func:`write_hierarchy` (sheets in sheets, one file shown twice, files in a subfolder) and
:func:`write_connections` (the ways a wire, a label, a junction and a pin meet).
"""

from __future__ import annotations

import uuid as _uuid
from pathlib import Path

_FONT = "(effects (font (size 1.27 1.27)))"


def _pin(kind: str, x: float, y: float, angle: int, length: float, name: str, number: str, *, hidden: bool = False) -> str:
    hide = " (hide yes)" if hidden else ""
    return f'(pin {kind} line (at {x} {y} {angle}) (length {length}){hide} (name "{name}" {_FONT}) (number "{number}" {_FONT}))'


def _fields(reference: str, value: str, *, power: bool = False) -> str:
    hide = " (hide yes)" if power else ""
    return (
        f'(property "Reference" "{reference}" (at 0 7.62 0){hide} {_FONT}) (property "Value" "{value}" (at 0 -7.62 0) {_FONT})'
        f'(property "Footprint" "" (at 0 0 0) (hide yes) {_FONT}) (property "Datasheet" "" (at 0 0 0) (hide yes) {_FONT})'
    )


SYMBOLS = {
    "Test:R": (
        f'(symbol "Test:R" (pin_numbers (hide yes)) (in_bom yes) (on_board yes) {_fields("R", "R")}'
        '(symbol "R_0_1" (rectangle (start -1.016 -2.54) (end 1.016 2.54) (stroke (width 0.254) (type default)) (fill (type none))))'
        f'(symbol "R_1_1" {_pin("passive", 0, 5.08, 270, 2.54, "~", "1")} {_pin("passive", 0, -5.08, 90, 2.54, "~", "2")}))'
    ),
    "Test:ODD": (
        f'(symbol "Test:ODD" (in_bom yes) (on_board yes) {_fields("U", "ODD")}'
        '(symbol "ODD_0_1" (rectangle (start -5.08 -5.08) (end 5.08 5.08) (stroke (width 0.254) (type default)) (fill (type background))))'
        f'(symbol "ODD_1_1" {_pin("input", -7.62, 2.54, 0, 2.54, "A", "1")} {_pin("output", 10.16, -2.54, 180, 5.08, "B", "2")}'
        f'{_pin("passive", 2.54, 7.62, 270, 2.54, "C", "3")} {_pin("passive", -2.54, -10.16, 90, 5.08, "D", "4")}))'
    ),
    "Test:PWR": (
        f'(symbol "Test:PWR" (power global) (pin_names (hide yes)) (in_bom yes) (on_board yes) {_fields("#PWR", "PWR", power=True)}'
        '(symbol "PWR_0_1" (polyline (pts (xy 0 0) (xy 0 1.27) (xy -0.762 1.27) (xy 0 2.54) (xy 0.762 1.27) (xy 0 1.27))'
        ' (stroke (width 0) (type default)) (fill (type none))))'
        f'(symbol "PWR_1_1" {_pin("power_in", 0, 0, 90, 0, "~", "1", hidden=True)}))'
    ),
}


class SchematicText:
    """One ``.kicad_sch`` of a project, written item by item. ``root`` is the project's root
    sheet's UUID (this document's own, for the root); a sheet instance's path is
    ``/<root>/<sheet uuid>...``, and a symbol on a sheet used twice names its reference in each."""

    def __init__(self, project: str, name: str, *, root: str | None = None, title: str = "", paper: str = "A4"):
        self.project, self.name, self.title, self.paper = project, name, title, paper
        self._count = 0
        self.uuid = self.new_uuid()
        self.root = root or self.uuid
        self._items: list[str] = []
        self._used: set[str] = set()

    def new_uuid(self) -> str:
        self._count += 1
        return str(_uuid.uuid5(_uuid.NAMESPACE_URL, f"cadgen-tests:{self.project}:{self.name}:{self._count}"))

    def symbol(
        self,
        lib_id: str,
        at: tuple[float, float],
        references,
        *,
        rotation: int = 0,
        mirror: str | None = None,
        value: str | None = None,
        fields: dict[str, str] | None = None,
        dnp: bool = False,
    ) -> None:
        """A placed symbol. ``references`` is its reference (on the root), or a list of
        ``(instance path, reference)`` for a sheet used more than once."""
        self._used.add(lib_id)
        if isinstance(references, str):
            references = [(f"/{self.root}", references)]
        x, y = at
        mirrored = f"(mirror {mirror})" if mirror else ""
        hidden = " (hide yes)" if references[0][1].startswith("#") else ""
        extra = "".join(
            f'(property "{key}" "{text}" (at {x} {y} 0) (hide yes) {_FONT})' for key, text in (fields or {}).items()
        )
        paths = " ".join(f'(path "{path}" (reference "{ref}") (unit 1))' for path, ref in references)
        pins = {"Test:R": ("1", "2"), "Test:ODD": ("1", "2", "3", "4"), "Test:PWR": ("1",)}[lib_id]
        self._items.append(
            f'(symbol (lib_id "{lib_id}") (at {x} {y} {rotation}) {mirrored} (unit 1) (body_style 1) (exclude_from_sim no)'
            f' (in_bom yes) (on_board yes) (dnp {"yes" if dnp else "no"}) (uuid "{self.new_uuid()}")'
            f' (property "Reference" "{references[0][1]}" (at {x} {y - 7.62} 0){hidden} {_FONT})'
            f' (property "Value" "{value or lib_id.split(":")[1]}" (at {x} {y + 7.62} 0) {_FONT})'
            f' (property "Footprint" "" (at {x} {y} 0) (hide yes) {_FONT}) {extra}'
            + "".join(f' (pin "{number}" (uuid "{self.new_uuid()}"))' for number in pins)
            + f' (instances (project "{self.project}" {paths})))'
        )

    def wire(self, a: tuple[float, float], b: tuple[float, float]) -> None:
        self._items.append(f'(wire (pts (xy {a[0]} {a[1]}) (xy {b[0]} {b[1]})) (stroke (width 0) (type default)) (uuid "{self.new_uuid()}"))')

    def label(self, text: str, at: tuple[float, float], kind: str = "label", *, angle: int = 0, justify: str = "left") -> None:
        """A label: ``kind`` ``label`` (local), ``global_label`` or ``hierarchical_label``."""
        if kind == "label":
            effects = f"(effects (font (size 1.27 1.27)) (justify {justify} bottom))"
            self._items.append(f'(label "{text}" (at {at[0]} {at[1]} {angle}) {effects} (uuid "{self.new_uuid()}"))')
        else:
            effects = f"(effects (font (size 1.27 1.27)) (justify {justify}))"
            self._items.append(f'({kind} "{text}" (shape input) (at {at[0]} {at[1]} {angle}) {effects} (uuid "{self.new_uuid()}"))')

    def junction(self, at: tuple[float, float]) -> None:
        self._items.append(f'(junction (at {at[0]} {at[1]}) (diameter 0) (color 0 0 0 0) (uuid "{self.new_uuid()}"))')

    def no_connect(self, at: tuple[float, float]) -> None:
        self._items.append(f'(no_connect (at {at[0]} {at[1]}) (uuid "{self.new_uuid()}"))')

    def sheet(self, name: str, file: str, at: tuple[float, float], pins: dict[str, tuple[float, float]], pages: list[tuple[str, str]]) -> str:
        """A sheet symbol showing ``file``, its pins on its left edge; ``pages`` is
        ``(instance path of this document, page)`` for each instance. Its UUID."""
        sheet_uuid = self.new_uuid()
        pin_text = " ".join(
            f'(pin "{pin}" input (at {x} {y} 180) (uuid "{self.new_uuid()}") (effects (font (size 1.27 1.27)) (justify left)))'
            for pin, (x, y) in pins.items()
        )
        paths = " ".join(f'(path "{path}" (page "{page}"))' for path, page in pages)
        self._items.append(
            f'(sheet (at {at[0]} {at[1]}) (size 20.32 10.16) (exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no)'
            f' (stroke (width 0.1524) (type solid)) (fill (color 0 0 0 0.0000)) (uuid "{sheet_uuid}")'
            f' (property "Sheetname" "{name}" (at {at[0]} {at[1] - 0.7} 0) (effects (font (size 1.27 1.27)) (justify left bottom)))'
            f' (property "Sheetfile" "{file}" (at {at[0]} {at[1] + 10.9} 0) (effects (font (size 1.27 1.27)) (justify left top)))'
            f" {pin_text} (instances (project \"{self.project}\" {paths})))"
        )
        return sheet_uuid

    def text(self) -> str:
        title = f'(title_block (title "{self.title}"))' if self.title else ""
        instances = '(sheet_instances (path "/" (page "1")))' if self.root == self.uuid else ""
        symbols = " ".join(SYMBOLS[lib_id] for lib_id in sorted(self._used))
        return (
            f'(kicad_sch (version 20260101) (generator "cadgen-tests") (generator_version "10.0") (uuid "{self.uuid}")'
            f' (paper "{self.paper}") {title} (lib_symbols {symbols}) {" ".join(self._items)} {instances} (embedded_fonts no))\n'
        )


def resistor_pins(at: tuple[float, float]) -> tuple[tuple[float, float], tuple[float, float]]:
    """Where an unturned ``Test:R`` at ``at`` connects: pin 1 above it, pin 2 below (y down)."""
    return (at[0], round(at[1] - 5.08, 4)), (at[0], round(at[1] + 5.08, 4))


def write_hierarchy(folder: Path) -> None:
    """A root with one file shown twice (Left, Right), a sheet inside that file (Deep: so two
    instances of it too), and a sheet whose name has a space and an umlaut (which macOS writes
    decomposed in the name of its plot). The twice-shown file and its sheet lie in a subfolder,
    ``sheets/``, as a KiCad project often keeps them."""
    root = SchematicText("hier", "root", title="Hier root")
    r1 = resistor_pins((25.4, 50.8))
    root.symbol("Test:R", (25.4, 50.8), "R1")
    root.wire(r1[0], (50.8, 45.72))
    left = root.sheet("Left", "sheets/child.kicad_sch", (50.8, 40.64), {"SIG": (50.8, 45.72)}, [(f"/{root.uuid}", "2")])
    right = root.sheet("Right", "sheets/child.kicad_sch", (50.8, 76.2), {"SIG": (50.8, 81.28)}, [(f"/{root.uuid}", "3")])
    root.wire((50.8, 81.28), (40.64, 81.28))
    root.label("RSIG", (40.64, 81.28), "global_label", angle=180, justify="right")
    power = root.sheet("Power Stäge", "power.kicad_sch", (101.6, 40.64), {}, [(f"/{root.uuid}", "4")])
    root.label("VLOC", r1[1])
    child = SchematicText("hier", "child", root=root.uuid, title="Child")
    halves = [f"/{root.uuid}/{left}", f"/{root.uuid}/{right}"]
    child.symbol("Test:R", (25.4, 50.8), list(zip(halves, ["R2", "R3"])))
    child.wire((25.4, 45.72), (35.56, 45.72))
    child.label("SIG", (35.56, 45.72), "hierarchical_label")
    child.label("LOC", (25.4, 55.88))
    deep_sheet = child.sheet("Deep", "deep.kicad_sch", (50.8, 40.64), {"DSIG": (50.8, 45.72)}, [(halves[0], "5"), (halves[1], "6")])
    child.wire((50.8, 45.72), (45.72, 45.72))
    child.label("LOC", (45.72, 45.72), angle=180, justify="right")
    deep = SchematicText("hier", "deep", root=root.uuid)
    deep.symbol("Test:R", (25.4, 50.8), [(f"{halves[0]}/{deep_sheet}", "R4"), (f"{halves[1]}/{deep_sheet}", "R5")])
    deep.wire((25.4, 45.72), (35.56, 45.72))
    deep.label("DSIG", (35.56, 45.72), "hierarchical_label")
    deep.label("GND", (25.4, 55.88), "global_label")
    stage = SchematicText("hier", "power", root=root.uuid, title="Power")
    stage.symbol("Test:R", (25.4, 50.8), [(f"/{root.uuid}/{power}", "R6")])
    stage.label("GND", (25.4, 45.72), "global_label")
    stage.label("VLOC", (25.4, 55.88))
    stage.wire((60.96, 60.96), (71.12, 60.96))
    stage.label("FLOAT", (60.96, 60.96))
    (folder / "sheets").mkdir(exist_ok=True)
    for name, document in (("hier", root), ("sheets/child", child), ("sheets/deep", deep), ("power", stage)):
        (folder / f"{name}.kicad_sch").write_text(document.text(), encoding="utf-8")


#: What KiCad 10 makes of write_hierarchy: its sheets in its page order (the root, then pages 2
#: to 6), named as its plot names them, and its netlist.
HIERARCHY_SHEETS = [
    ("hier", "/", "hier.kicad_sch"), ("Left", "/Left/", "sheets/child.kicad_sch"), ("Right", "/Right/", "sheets/child.kicad_sch"),
    ("Power Stäge", "/Power Stäge/", "power.kicad_sch"), ("Left-Deep", "/Left/Deep/", "deep.kicad_sch"),
    ("Right-Deep", "/Right/Deep/", "deep.kicad_sch"),
]
HIERARCHY_NETS = {
    "/Left/SIG": ["R1.1", "R2.1"], "/VLOC": ["R1.2"], "/Left/LOC": ["R2.2", "R4.1"], "/Right/LOC": ["R3.2", "R5.1"],
    "RSIG": ["R3.1"], "GND": ["R4.2", "R5.2", "R6.1"], "/Power Stäge/VLOC": ["R6.2"],
}


def write_connections(path: Path) -> None:
    """One sheet of the ways things meet, each a resistor's pin 1 and what touches it."""
    sheet = SchematicText("joins", "joins")
    # A wire ending on another's middle, with no junction: apart.
    sheet.symbol("Test:R", (25.4, 30.48), "R1")
    sheet.wire((25.4, 25.4), (35.56, 25.4))
    sheet.label("TA", (35.56, 25.4), "global_label")
    sheet.symbol("Test:R", (30.48, 40.64), "R2")
    sheet.wire((30.48, 35.56), (30.48, 25.4))
    # The same with a junction there: joined.
    sheet.symbol("Test:R", (25.4, 60.96), "R3")
    sheet.wire((25.4, 55.88), (35.56, 55.88))
    sheet.label("TB", (35.56, 55.88), "global_label")
    sheet.symbol("Test:R", (30.48, 71.12), "R4")
    sheet.wire((30.48, 66.04), (30.48, 55.88))
    sheet.junction((30.48, 55.88))
    # A local label on a wire's middle names it.
    sheet.symbol("Test:R", (50.8, 30.48), "R5")
    sheet.wire((50.8, 25.4), (60.96, 25.4))
    sheet.label("MID", (55.88, 25.4))
    # A pin on a wire's middle is not on it.
    sheet.symbol("Test:R", (50.8, 60.96), "R6")
    sheet.wire((50.8, 55.88), (60.96, 55.88))
    sheet.label("PD", (60.96, 55.88), "global_label")
    sheet.symbol("Test:R", (55.88, 60.96), "R7")
    # A label on a wire no pin reaches; a power symbol on a pin; a no-connect flag.
    sheet.wire((76.2, 25.4), (86.36, 25.4))
    sheet.label("FLOAT", (76.2, 25.4))
    sheet.symbol("Test:R", (76.2, 60.96), "R8")
    sheet.symbol("Test:PWR", (76.2, 55.88), "#PWR01", value="+5V")
    sheet.no_connect((76.2, 66.04))
    path.write_text(sheet.text(), encoding="utf-8")


#: KiCad 10's netlist of write_connections, as ``kicad-cli sch export netlist`` writes it (nets only).
CONNECTIONS_NETLIST = """(export (version "E")
  (nets
    (net (code "1") (name "+5V") (class "Default") (node (ref "R8") (pin "1") (pintype "passive")))
    (net (code "2") (name "/MID") (class "Default") (node (ref "R5") (pin "1") (pintype "passive")))
    (net (code "3") (name "PD") (class "Default") (node (ref "R6") (pin "1") (pintype "passive")))
    (net (code "4") (name "TA") (class "Default") (node (ref "R1") (pin "1") (pintype "passive")))
    (net (code "5") (name "TB") (class "Default") (node (ref "R3") (pin "1") (pintype "passive")) (node (ref "R4") (pin "1") (pintype "passive")))
    (net (code "6") (name "unconnected-(R2-~-Pad1)") (class "Default") (node (ref "R2") (pin "1") (pintype "passive")))
    (net (code "7") (name "unconnected-(R7-~-Pad1)") (class "Default") (node (ref "R7") (pin "1") (pintype "passive")))
    (net (code "8") (name "unconnected-(R8-~-Pad2)") (class "Default") (node (ref "R8") (pin "2") (pintype "passive+no_connect")))))
"""
