"""A tiny KiCad board made in colours and with a comb-shaped custom pad, for the tests of what a board is made
in (its stack-up's colours and copper finish) and of a custom pad's real shape.

The board, in KiCad's frame (millimetres, y down), 20 x 10 mm from (0, 0):

- a stack-up: white silkscreen, black solder mask on both sides, two coppers on an FR-4 core named
  without a colour, an ENIG finish;
- ``S1`` at (10, 5), one custom pad ``1`` on F.Cu (net ``SENSE``): a 0.4 mm square anchor and a comb of
  primitives -- a spine (a filled polygon) from x -2 to 2 at y -1.2..-0.8, five fingers drawn as lines
  0.4 mm wide from y -1 to 1 at x -2, -1, 0, 1, 2, and an arc 0.2 mm wide bowing below the last
  finger, from (2, 1) through (2.5, 1.5) to (3, 1). Between two fingers, (10.5, 5.5) on the board, is
  no copper, nor is the inside of the arc's bow, (12.5, 6.0): the hull round them would cover both.
"""

from __future__ import annotations

from pathlib import Path

__all__ = ["LOOK_BOARD", "write_look_board"]

_FINGERS = "".join(
    f'(gr_line (start {x} -1) (end {x} 1) (width 0.4))' for x in (-2, -1, 0, 1, 2)
)

LOOK_BOARD = f"""(kicad_pcb (version 20240108) (generator "pcbnew") (generator_version "8.0")
  (general (thickness 1.6))
  (paper "A4")
  (layers (0 "F.Cu" signal) (31 "B.Cu" signal) (37 "F.SilkS" user "F.Silkscreen") (36 "B.SilkS" user "B.Silkscreen")
    (39 "F.Mask" user) (38 "B.Mask" user) (44 "Edge.Cuts" user))
  (setup
    (stackup
      (layer "F.SilkS" (type "Top Silk Screen") (color "White"))
      (layer "F.Mask" (type "Top Solder Mask") (color "Black") (thickness 0.01))
      (layer "F.Cu" (type "copper") (thickness 0.035))
      (layer "dielectric 1" (type "core") (thickness 1.51) (material "FR4") (epsilon_r 4.5) (loss_tangent 0.02))
      (layer "B.Cu" (type "copper") (thickness 0.035))
      (layer "B.Mask" (type "Bottom Solder Mask") (color "Black") (thickness 0.01))
      (layer "B.SilkS" (type "Bottom Silk Screen") (color "White"))
      (copper_finish "ENIG")
      (dielectric_constraints no))
    (pad_to_mask_clearance 0))
  (net 0 "")
  (net 1 "SENSE")
  (footprint "comb:Comb" (layer "F.Cu") (uuid "c0mb0000-0000-4000-8000-000000000001") (at 10 5)
    (property "Reference" "S1" (at 0 -2.5 0) (layer "F.SilkS") (uuid "c0mb0000-0000-4000-8000-000000000002")
      (effects (font (size 0.8 0.8) (thickness 0.12))))
    (pad "1" smd custom (at 0 0) (size 0.4 0.4) (layers "F.Cu" "F.Mask") (net 1 "SENSE")
      (options (clearance outline) (anchor rect))
      (primitives
        (gr_poly (pts (xy -2 -1.2) (xy 2 -1.2) (xy 2 -0.8) (xy -2 -0.8)) (width 0) (fill yes))
        {_FINGERS}
        (gr_arc (start 2 1) (mid 2.5 1.5) (end 3 1) (width 0.2)))
      (uuid "c0mb0000-0000-4000-8000-000000000003")))
  (gr_rect (start 0 0) (end 20 10) (stroke (width 0.05) (type solid)) (fill no) (layer "Edge.Cuts")
    (uuid "c0mb0000-0000-4000-8000-000000000004"))
)
"""


def write_look_board(folder: Path, name: str = "look") -> Path:
    """The board written to ``folder/<name>.kicad_pcb``; answers its path."""
    path = Path(folder) / f"{name}.kicad_pcb"
    path.write_text(LOOK_BOARD, encoding="utf-8")
    return path
