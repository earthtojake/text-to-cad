"""A small KiCad board for the tests that read boards, in the file format KiCad 11 writes.

Written in KiCad 11's native board syntax (``(kicad_pcb (version 20260901)
(generator "pcbnew") (generator_version "10.99")``, footprints placed by a
``transform``, zone fills saved), so the readers cover the newer transform and net syntax without needing
a KiCad process or the sample corpus.

The board, in KiCad's frame (millimetres, y down; no drill/place origin, so the
script frame is the same x and y up), 40 x 30 mm, its outline from (0, 0):

- ``J1``, a 1x02 pin header at (5, 15): through-hole pads ``1`` (VBUS, a 1.7 mm
  square at (5, 15)) and ``2`` (GND, a 1.7 mm circle at (5, 17.54)), 1 mm drills;
- ``R1``, an 0603 resistor at (35, 15): roundrect pads ``1`` (VBUS, at 34.175) and
  ``2`` (LED, at 35.825);
- ``D1``, an 0603 LED at (20, 24) turned a quarter turn, on the resistor's pads:
  ``1`` (GND, at (20, 24.825)) and ``2`` (LED, at (20, 23.175));
- a 1 mm VBUS track across the middle of the board, y = 15, from J1.1 to R1.1;
  a 0.25 mm GND track from D1.1 to a via at (18, 27) (0.6 mm, 0.3 mm drill);
- a GND pour on ``B.Cu`` over the bottom left, its fill saved: (1.5, 16.5) to
  (19.5, 28.5), which J1.2 and the via land in;
- the LED net is unrouted: D1.2 to R1.2 is the one ratsnest line;
- the text ``blinky`` on the top silkscreen at (20, 5), and each part's
  reference and value.
"""

from __future__ import annotations

from pathlib import Path

__all__ = ["BOARD", "write_board"]

_FONT = "(effects (font (size 1 1) (thickness 0.15)))"
_HIDDEN = '(effects (font (size 1.27 1.27)))'


def _property(name: str, value: str, at: str, layer: str, hidden: bool = False) -> str:
    hide = "(hide yes) " if hidden else ""
    return f'(property "{name}" "{value}" (at {at}) (layer "{layer}") {hide}{_HIDDEN if hidden else _FONT})'


def _line(start: str, end: str, width: float, layer: str) -> str:
    return f'(fp_line (start {start}) (end {end}) (stroke (width {width}) (type solid)) (layer "{layer}"))'


def _rect(start: str, end: str, width: float, layer: str) -> str:
    return f'(fp_rect (start {start}) (end {end}) (stroke (width {width}) (type solid)) (fill no) (layer "{layer}"))'


def _footprint(name: str, at: str, rotate: int, ref: str, value: str, body: str) -> str:
    return (
        f'(footprint "{name}" (layer "F.Cu") (transform (translate {at}) (rotate {rotate}) (scale 1 1))\n'
        f'  {_property("Reference", ref, "0 -1.43 " + str(rotate % 360), "F.SilkS")}\n'
        f'  {_property("Value", value, "0 1.43 " + str(rotate % 360), "F.Fab")}\n'
        f'  {_property("Datasheet", "", "0 0 0", "F.Fab", hidden=True)}\n'
        f'  {_property("Description", "", "0 0 0", "F.Fab", hidden=True)}\n'
        f"{body}\n)"
    )


_R0603 = (
    f'  {_line("-0.237258 -0.5225", "0.237258 -0.5225", 0.12, "F.SilkS")}\n'
    f'  {_line("-0.237258 0.5225", "0.237258 0.5225", 0.12, "F.SilkS")}\n'
    f'  {_rect("-1.48 -0.73", "1.48 0.73", 0.05, "F.CrtYd")}\n'
    f'  {_rect("-0.8 -0.4", "0.8 0.4", 0.1, "F.Fab")}\n'
    f'  (fp_text user "${{REFERENCE}}" (at 0 0 ROT) (layer "F.Fab") (effects (font (size 0.4 0.4) (thickness 0.06))))\n'
    '  (pad "1" smd roundrect (at -0.825 0 ROT) (size 0.8 0.95) (layers "F.Cu" "F.Mask" "F.Paste") (roundrect_rratio 0.25) (net "NET1"))\n'
    '  (pad "2" smd roundrect (at 0.825 0 ROT) (size 0.8 0.95) (layers "F.Cu" "F.Mask" "F.Paste") (roundrect_rratio 0.25) (net "NET2"))'
)

_HEADER = (
    f'  {_line("-1.38 -1.38", "0 -1.38", 0.12, "F.SilkS")}\n'
    f'  {_line("-1.38 0", "-1.38 -1.38", 0.12, "F.SilkS")}\n'
    f'  {_line("-1.38 1.27", "-1.38 3.92", 0.12, "F.SilkS")}\n'
    f'  {_line("-1.38 1.27", "1.38 1.27", 0.12, "F.SilkS")}\n'
    f'  {_line("-1.38 3.92", "1.38 3.92", 0.12, "F.SilkS")}\n'
    f'  {_line("1.38 1.27", "1.38 3.92", 0.12, "F.SilkS")}\n'
    f'  {_rect("-1.77 -1.77", "1.77 4.32", 0.05, "F.CrtYd")}\n'
    f'  {_line("-1.27 -0.635", "-0.635 -1.27", 0.1, "F.Fab")}\n'
    f'  {_line("-1.27 3.81", "-1.27 -0.635", 0.1, "F.Fab")}\n'
    f'  {_line("-0.635 -1.27", "1.27 -1.27", 0.1, "F.Fab")}\n'
    f'  {_line("1.27 -1.27", "1.27 3.81", 0.1, "F.Fab")}\n'
    f'  {_line("1.27 3.81", "-1.27 3.81", 0.1, "F.Fab")}\n'
    '  (pad "1" thru_hole rect (at 0 0) (size 1.7 1.7) (drill 1) (layers "*.Cu" "*.Mask") (remove_unused_layers no) (net "VBUS"))\n'
    '  (pad "2" thru_hole circle (at 0 2.54) (size 1.7 1.7) (drill 1) (layers "*.Cu" "*.Mask") (remove_unused_layers no) (net "GND"))'
)


def _segment(start: str, end: str, width: float, net: str) -> str:
    return f'(segment (start {start}) (end {end}) (width {width}) (layer "F.Cu") (net "{net}"))'


BOARD = f"""(kicad_pcb
  (version 20260901)
  (generator "pcbnew")
  (generator_version "10.99")
  (general (thickness 1.6) (legacy_teardrops no))
  (paper "A4")
  (layers
    (0 "F.Cu" signal)
    (2 "B.Cu" signal)
    (13 "F.Paste" user)
    (15 "B.Paste" user)
    (5 "F.SilkS" user "F.Silkscreen")
    (7 "B.SilkS" user "B.Silkscreen")
    (1 "F.Mask" user)
    (3 "B.Mask" user)
    (17 "Dwgs.User" user "User.Drawings")
    (25 "Edge.Cuts" user)
    (31 "F.CrtYd" user "F.Courtyard")
    (29 "B.CrtYd" user "B.Courtyard")
    (35 "F.Fab" user)
    (33 "B.Fab" user)
  )
  (setup (pad_to_mask_clearance 0) (allow_soldermask_bridges_in_footprints no))
  {_footprint("Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical", "5 15", 0, "J1", "Conn_01x02", _HEADER)}
  {_footprint("Resistor_SMD:R_0603_1608Metric", "35 15", 0, "R1", "10k", _R0603.replace("ROT", "0").replace("NET1", "VBUS").replace("NET2", "LED"))}
  {_footprint("LED_SMD:LED_0603_1608Metric", "20 24", 90, "D1", "LED", _R0603.replace("ROT", "90").replace("NET1", "GND").replace("NET2", "LED"))}
  (gr_rect (start 0 0) (end 40 30) (stroke (width 0.1) (type default)) (fill no) (layer "Edge.Cuts"))
  (gr_text "blinky" (at 20 5 0) (layer "F.SilkS") (effects (font (size 1.5 1.5) (thickness 0.3))))
  {_segment("5 15", "34.175 15", 1, "VBUS")}
  {_segment("20 24.825", "18 27", 0.25, "GND")}
  (via (at 18 27) (size 0.6) (drill 0.3) (layers "F.Cu" "B.Cu") (net "GND"))
  (zone (net "GND") (layer "B.Cu") (name "GND pour") (hatch edge 0.5)
    (connect_pads (clearance 0.5))
    (min_thickness 0.25)
    (filled_areas_thickness no)
    (fill yes (thermal_gap 0.5) (thermal_bridge_width 0.5))
    (polygon (pts (xy 1 16) (xy 20 16) (xy 20 29) (xy 1 29)))
    (filled_polygon (layer "B.Cu") (pts (xy 1.5 16.5) (xy 19.5 16.5) (xy 19.5 28.5) (xy 1.5 28.5)))
  )
)
"""


def write_board(folder: Path, name: str = "blinky") -> Path:
    """Write the board as ``<folder>/<name>.kicad_pcb`` and answer its path."""
    path = Path(folder) / f"{name}.kicad_pcb"
    path.write_text(BOARD, encoding="utf-8")
    return path
