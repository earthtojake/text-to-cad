"""Shared by the board scripts: the board's frame, the placement table (LFO B is LFO A moved 20 mm right,
part for part), and small helpers over KiPy's board items."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BOARD = ROOT / "twin_orbit.kicad_pcb"

# The board: 48.0 x 107.0 mm (10HP), its top-left corner at (X0, Y0) on KiCad's page.
X0, Y0 = 100.0, 50.0
W, H = 48.0, 107.0
CORNER_R = 1.0
LFO_PITCH = 25.0            # LFO B = LFO A + 25 mm in x (the panel's two columns)
COL_X = 11.5                # LFO A's column (jacks, pots, LED), board-local


def A(x: float, y: float) -> tuple[float, float]:
    """Board-local millimetres to KiCad's page."""
    return (round(X0 + x, 4), round(Y0 + y, 4))


JACK_Y = [50.0, 64.4, 78.8, 93.2]          # J101 CV, J102 TRI, J103 SQR, J104 MIX (origins; barrels +6.48)


def mm(v: int) -> float:
    return v / 1e6


def ref_of(fp) -> str:
    return fp.reference_field.text.value


def b_ref(ref: str) -> str:
    """LFO A's reference -> LFO B's (R101 -> R201)."""
    i = len(ref.rstrip("0123456789"))
    return ref[:i] + "2" + ref[i + 1:]
