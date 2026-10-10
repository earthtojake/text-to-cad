"""A tiny KiCad library for tests that must not need KiCad itself.

Symbols and footprints written in KiCad 10's own formats into a temporary
folder that a ``Board``/``Circuit`` takes as ``libraries=``:

- ``Test:R``: two passive pins, ``1`` and ``2``; no default footprint.
- ``Test:AMP``: ``IN`` (1), ``OUT`` (2) and two pins named ``GND`` (3, 4);
  default footprint ``Test:SOT4``.
- ``Test:REG`` extends ``AMP`` (a derived symbol: KiCad flattens it on use).
- ``Test:DUAL``: two units, one input each, named with a slash: ``IN/A`` (1, unit A)
  and ``IN/B`` (2, unit B); default footprint ``Test:R_0603``.
- ``Test:TP``: one passive pin, in the BOM, default footprint ``Test:TEST_PAD`` (KiCad's
  test point: a symbol in the BOM on a footprint excluded from it).
- ``Test:FIDUCIAL``: one passive pin, and ``(in_bom no)``: on the board, not bought; a
  field of its own, ``Sim.Enable`` = ``0``, as KiCad's library symbols carry ``Sim.*``.
- ``Test:HDR``: four pins drawn at two points, as KiCad stacks a connector's repeated pins:
  ``3V3`` 1 (power out) and 3 at one, ``GND`` 2 and 4 at the other; default footprint
  ``Test:SOT4``.
- ``Test:PWR``: a power symbol (``(power global)``), which is a net, not a part.
- ``power:PWR_FLAG``: the flag a board's schematic puts on a net powered from
  off the board (KiCad's own is in its ``power`` library; this one stands in).
- footprints ``Test:R_0603`` (pads 1, 2 at x = -/+0.825), ``Test:SOT4``
  (pads 1-4), ``Test:ONE_PAD`` (pad 1 only), ``Test:TEST_PAD`` (pad 1,
  excluded from the BOM and position files, as KiCad's test points are) and
  ``Test:ZONED`` (pad 1 at (1, 0) and a keepout zone with a corner on it).
"""

from __future__ import annotations

from pathlib import Path

_FONT = "(effects (font (size 1.27 1.27)))"


def _pin(kind: str, x: float, y: float, angle: int, name: str, number: str) -> str:
    return f'(pin {kind} line (at {x} {y} {angle}) (length 2.54) (name "{name}" {_FONT}) (number "{number}" {_FONT}))'


def _properties(reference: str, value: str, footprint: str = "", description: str = "") -> str:
    return (
        f'(property "Reference" "{reference}" (at 0 5.08 0) {_FONT})'
        f'(property "Value" "{value}" (at 0 -5.08 0) {_FONT})'
        f'(property "Footprint" "{footprint}" (at 0 0 0) (hide yes) {_FONT})'
        f'(property "Datasheet" "" (at 0 0 0) (hide yes) {_FONT})'
        f'(property "Description" "{description}" (at 0 0 0) (hide yes) {_FONT})'
    )


SYMBOLS = (
    '(kicad_symbol_lib (version 20251024) (generator "cadgen-tests") (generator_version "10.0")'
    f'(symbol "R" (pin_numbers (hide yes)) (in_bom yes) (on_board yes) {_properties("R", "R", "", "Resistor")}'
    '(symbol "R_0_1" (rectangle (start -1.016 -2.54) (end 1.016 2.54) (stroke (width 0.254) (type default)) (fill (type none))))'
    f'(symbol "R_1_1" {_pin("passive", 0, 5.08, 270, "~", "1")} {_pin("passive", 0, -5.08, 90, "~", "2")}))'
    f'(symbol "AMP" (in_bom yes) (on_board yes) {_properties("U", "AMP", "Test:SOT4", "An amplifier")}'
    '(symbol "AMP_0_1" (rectangle (start -5.08 -5.08) (end 5.08 5.08) (stroke (width 0.254) (type default)) (fill (type background))))'
    f'(symbol "AMP_1_1" {_pin("input", -7.62, 2.54, 0, "IN", "1")} {_pin("output", 7.62, 2.54, 180, "OUT", "2")}'
    f'{_pin("passive", -7.62, -2.54, 0, "GND", "3")} {_pin("passive", 7.62, -2.54, 180, "GND", "4")}))'
    f'(symbol "REG" (extends "AMP") {_properties("U", "REG", "Test:SOT4", "A regulator")})'
    f'(symbol "DUAL" (in_bom yes) (on_board yes) {_properties("U", "DUAL", "Test:R_0603", "Two units")}'
    f'(symbol "DUAL_1_1" {_pin("input", -5.08, 0, 0, "IN/A", "1")})'
    f'(symbol "DUAL_2_1" {_pin("input", -5.08, 0, 0, "IN/B", "2")}))'
    f'(symbol "TP" (pin_numbers (hide yes)) (in_bom yes) (on_board yes) {_properties("TP", "TP", "Test:TEST_PAD", "A test point")}'
    f'(symbol "TP_1_1" {_pin("passive", 0, 2.54, 270, "~", "1")}))'
    f'(symbol "FIDUCIAL" (pin_numbers (hide yes)) (in_bom no) (on_board yes) {_properties("FID", "FIDUCIAL", "", "Not bought")}'
    f'(property "Sim.Enable" "0" (at 0 0 0) (hide yes) {_FONT})'
    f'(symbol "FIDUCIAL_1_1" {_pin("passive", 0, 2.54, 270, "~", "1")}))'
    f'(symbol "HDR" (in_bom yes) (on_board yes) {_properties("J", "HDR", "Test:SOT4", "Stacked pins")}'
    f'(symbol "HDR_1_1" {_pin("power_out", -5.08, 2.54, 0, "3V3", "1")} {_pin("passive", -5.08, 2.54, 0, "3V3", "3")}'
    f'{_pin("passive", -5.08, -2.54, 0, "GND", "2")} {_pin("passive", -5.08, -2.54, 0, "GND", "4")}))'
    f'(symbol "PWR" (power global) (pin_names (hide yes)) {_properties("#PWR", "PWR")}'
    f'(symbol "PWR_1_1" {_pin("power_in", 0, 0, 90, "~", "1")}))'
    ")"
)


def _pad(number: str, x: float, y: float) -> str:
    return (
        f'(pad "{number}" smd roundrect (at {x} {y}) (size 0.8 0.95) (layers "F.Cu" "F.Mask" "F.Paste") '
        "(roundrect_rratio 0.25))"
    )


def _footprint(name: str, pads: str) -> str:
    return (
        f'(footprint "{name}" (version 20241229) (generator "cadgen-tests") (layer "F.Cu")'
        '(property "Reference" "REF**" (at 0 -1.5 0) (layer "F.SilkS") (effects (font (size 1 1) (thickness 0.15))))'
        f'(property "Value" "{name}" (at 0 1.5 0) (layer "F.Fab") (effects (font (size 1 1) (thickness 0.15))))'
        "(attr smd)"
        '(fp_line (start -1 -0.6) (end 1 -0.6) (stroke (width 0.1) (type solid)) (layer "F.SilkS"))'
        f"{pads} (embedded_fonts no))"
    )


POWER = (
    '(kicad_symbol_lib (version 20251024) (generator "cadgen-tests") (generator_version "10.0")'
    f'(symbol "PWR_FLAG" (power global) (pin_numbers (hide yes)) (pin_names (hide yes)) (in_bom no) (on_board no)'
    f'{_properties("#FLG", "PWR_FLAG")}'
    f'(symbol "PWR_FLAG_0_0" {_pin("power_out", 0, 0, 90, "~", "1")}))'
    ")"
)


FOOTPRINTS = {
    "R_0603": _footprint("R_0603", _pad("1", -0.825, 0) + _pad("2", 0.825, 0)),
    "SOT4": _footprint("SOT4", _pad("1", -1.5, -0.95) + _pad("2", 1.5, -0.95) + _pad("3", -1.5, 0.95) + _pad("4", 1.5, 0.95)),
    "ONE_PAD": _footprint("ONE_PAD", _pad("1", 0, 0)),
    "TEST_PAD": _footprint("TEST_PAD", _pad("1", 0, 0)).replace("(attr smd)", "(attr smd exclude_from_pos_files exclude_from_bom)"),
    # A keepout drawn from pad 1's centre, as an RF module's antenna keepout is drawn.
    "ZONED": _footprint(
        "ZONED",
        _pad("1", 1, 0)
        + '(zone (net 0) (net_name "") (layers "F.Cu") (name "KEEP") (hatch edge 0.5) (connect_pads (clearance 0))'
        " (min_thickness 0.25) (filled_areas_thickness no)"
        " (keepout (tracks not_allowed) (vias not_allowed) (pads allowed) (copperpour not_allowed) (footprints allowed))"
        " (fill (thermal_gap 0.5) (thermal_bridge_width 0.5)) (polygon (pts (xy 1 0) (xy 3 0) (xy 3 2) (xy 1 2))))",
    ),
}


def write_test_library(folder: Path) -> Path:
    """Write the library into ``folder`` and return it (pass it as ``libraries=[folder]``)."""
    folder = Path(folder)
    (folder / "Test.kicad_sym").write_text(SYMBOLS, encoding="utf-8")
    (folder / "power.kicad_sym").write_text(POWER, encoding="utf-8")
    pretty = folder / "Test.pretty"
    pretty.mkdir(parents=True, exist_ok=True)
    for name, text in FOOTPRINTS.items():
        (pretty / f"{name}.kicad_mod").write_text(text, encoding="utf-8")
    return folder
