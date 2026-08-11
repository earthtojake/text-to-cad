"""The one-piece blended airframe skin, cut and lifted onto its gear stance."""

from __future__ import annotations

import sys

from build123d import Location

from f14_parts import body as B
from f14_parts import geometry as G
from f14_parts.context import group
from f14_parts import palette as P

# Modules that may publish `SKIN_CUTTERS` -- solids to subtract from the skin.
#
# The skin is lofted with certain real openings FILLED, because a section taken
# through them is two disconnected regions and cannot be lofted as one wire:
# the boundary-layer diverter slot, and the cockpit opening under the canopy
# bubble. Those features are cut back in here, which also gives them crisp
# machined walls rather than a lofted approximation of a slot.
CUTTER_MODULES = ("inlets", "cockpit", "aft", "nose_gear", "main_gear", "details")


def stance(shape):
    """Lift a waterline-referenced shape onto the ground and set the rest
    attitude.

    EVERY part module builds in the waterline frame and applies this same
    transform, so parts stay attached to the skin when the stance is tuned.
    """
    return Location((0, 0, G.WATERLINE), (0, G.GROUND_PITCH, 0)) * shape


def _collect_cutters():
    """Cutters published by already-imported part modules.

    Looked up through ``sys.modules`` rather than imported.  Those modules
    import ``stance`` from here, so importing them back would be circular; by
    the time ``build()`` runs the assembly has already imported them all.
    """
    out = []
    for name in CUTTER_MODULES:
        mod = sys.modules.get(f"f14_parts.{name}")
        if mod is None:
            continue
        cutters = getattr(mod, "SKIN_CUTTERS", None) or []
        for c in cutters:
            if c is not None:
                out.append(c)
    return out


def build():
    skin = B.build_skin()

    cutters = _collect_cutters()
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
