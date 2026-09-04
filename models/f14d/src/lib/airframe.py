"""The one-piece blended airframe skin, cut and lifted onto its gear stance."""

from __future__ import annotations

import sys

from cadgen import build123d as bd

from lib import body as B
from lib import geometry as G
from lib.context import group
from lib import palette as P

def stance(shape):
    """Lift a waterline-referenced shape onto the ground and set the rest
    attitude.

    EVERY part module builds in the waterline frame and applies this same
    transform, so parts stay attached to the skin when the stance is tuned.
    """
    return bd.Location((0, 0, G.WATERLINE), (0, G.GROUND_PITCH, 0)) * shape


def build(cutters=()):
    """The skin, minus ``cutters`` — solids in the waterline frame, chosen by the
    caller (the `airframe` model names them explicitly; see its docstring for
    which are structural and which were dropped as too costly)."""
    skin = B.build_skin()

    cutters = [c for c in cutters if c is not None]
    if cutters:
        # ONE list operand, never pairwise: pairwise re-runs the whole
        # intersection network per tool and decays O(n^2).
        try:
            cut = skin - cutters
            if cut is not None and cut.volume > 0:
                skin = cut
            else:
                print("[airframe] skin cut produced no volume; keeping uncut",
                      file=sys.stderr)
        except Exception as exc:  # noqa: BLE001
            print(f"[airframe] skin cut failed, keeping uncut: {exc}",
                  file=sys.stderr)

    solids = skin.solids() if hasattr(skin, "solids") else [skin]
    kids = []
    for i, s in enumerate(solids):
        label = "airframe_skin" if len(solids) == 1 else f"airframe_skin:{i}"
        kids.append(P.style(s, label, P.GREY_DARK))
    return group("airframe", [stance(k) for k in kids])
