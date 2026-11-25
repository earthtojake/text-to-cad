"""Twin Orbit's mechanics, shared by the panel, the knobs, the nuts and the assembly.

Every hole the panel has for a jack, a pot or an LED is read from the board file: the centre of the part's
F.Fab circle (the jack's barrel, the pot's shaft, the LED's body) in its footprint, as KiCad placed it. Move a
jack on the board and the panel's hole follows on the next run; nothing here repeats a part's position.

Frames. The assembly frame is KiCad's STEP export of the board with its user origin at the board's top-left
corner: x right, y = -(board-local y), z up from the board's bottom face. The panel frame (its DXF) has its
origin at the panel's bottom-left corner, y up.

Eurorack (Doepfer A-100 mechanics, doepfer.de/a100_man/a100m_e.htm): 3U panel 128.5 mm; 10HP = 50.5 mm;
2 mm aluminium; mounting holes 3.2 mm at 3.0 mm from the top and bottom edges, 7.5 mm from the left edge
and 7.5 + n x 5.08 mm, here slotted 2 mm along x for racks whose threaded strips sit a little off."""

from __future__ import annotations

from pathlib import Path

from cad import kicad_pcb

BOARD = Path(__file__).resolve().parents[2] / "twin_orbit.kicad_pcb"   # the project folder's

HP = 10
PANEL_W = 50.5                      # Doepfer's 10HP width
PANEL_H = 128.5
PANEL_T = 2.0
BOARD_W, BOARD_H = 48.0, 107.0
BOARD_ORIGIN = (100.0, 50.0)        # the board's top-left corner on KiCad's page (its outline)
PCB_T = 1.6
# The panel's back face rests on the pots' mounting face, 10.0 mm above the board's top (Alpha RD901F-40
# drawing); a Thonkiconn stands 9.5 mm (its 9.0 mm body and 0.5 mm collar), so each jack gets a 0.5 mm spacer
# washer (JACK_SPACER_T).
PANEL_BACK_Z = PCB_T + 10.0
PANEL_FRONT_Z = PANEL_BACK_Z + PANEL_T
JACK_SPACER_T = 0.5
# panel edge to board edge: the board is centred on the panel
PANEL_X0 = -(PANEL_W - BOARD_W) / 2          # panel's left edge, assembly x
PANEL_Y_TOP = (PANEL_H - BOARD_H) / 2        # panel's top edge, assembly y (board top at y = 0)

HOLE_D = {"jack": 6.3, "pot": 7.3, "led": 3.5}   # M6 bushing, M7 bushing, 3 mm LED (clearance)
SLOT_W, SLOT_TRAVEL = 3.2, 2.0
MOUNT_X = [7.5, 7.5 + (HP - 3) * 5.08]       # from the panel's left edge
MOUNT_Y = [3.0, PANEL_H - 3.0]               # from the panel's bottom edge


def kind_of(ref: str) -> str | None:
    if ref.startswith("RV"):
        return "pot"
    if ref.startswith("J") and ref != "J1":
        return "jack"
    if ref.startswith("D") and ref.endswith("03"):
        return "led"
    return None


def panel_parts() -> list[dict]:
    """Every panel part on the board: ref, kind, value, its axis in the assembly frame and the panel frame."""
    board = kicad_pcb.read(BOARD)
    out = []
    for part in board.parts:
        kind = kind_of(part.ref)
        if not kind:
            continue
        circles = [s for s in board.shapes if s.part == part.ref and s.shape == "circle" and s.layer == "F.Fab"]
        if not circles:
            raise ValueError(f"{part.ref} has no F.Fab circle to take its axis from")
        pts = max(circles, key=lambda s: len(s.points)).points
        cx = sum(p[0] for p in pts) / len(pts) - BOARD_ORIGIN[0]
        cy = sum(p[1] for p in pts) / len(pts) - BOARD_ORIGIN[1]
        ax, ay = cx, -cy                                   # assembly frame
        px, py = ax - PANEL_X0, ay + (PANEL_H - PANEL_Y_TOP)   # panel frame
        out.append({"ref": part.ref, "kind": kind, "value": part.value, "asm": (round(ax, 4), round(ay, 4)),
                    "panel": (round(px, 4), round(py, 4))})
    return sorted(out, key=lambda d: d["ref"])


def to_asm(px: float, py: float) -> tuple[float, float]:
    return (px + PANEL_X0, py - (PANEL_H - PANEL_Y_TOP))
