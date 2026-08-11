"""Glazing: the DLO glass and the lamp lenses.

Everything here is cut from a master surface, never modelled standalone:

  * windscreen / side glass / rear screen are the canopy shell intersected
    with the DLO openings, so the glass is exactly flush with the pillars and
    the tumblehome is inherited from the canopy section;
  * the lamp lenses are the BODY shell intersected with a lens region, so the
    reflection line runs off the fender and straight across the lamp with no
    step -- the thing that usually gives a CAD car away.
"""

from __future__ import annotations

from hypercar_parts import palette as P
from hypercar_parts import surfaces as S
from hypercar_parts.context import group, style

GLASS_COLOR = {
    "windscreen": (P.GLASS, P.GLASS_ALPHA),
    "side_glass:left": (P.GLASS, P.GLASS_ALPHA),
    "side_glass:right": (P.GLASS, P.GLASS_ALPHA),
    "rear_screen": (P.GLASS_DARK, P.GLASS_ALPHA - 0.06),
}


def build():
    kids = []

    shell = S.canopy_glass_shell()
    for name, region in S.glazing_regions().items():
        pane = shell & region
        if not pane.solids():
            continue
        colour, alpha = GLASS_COLOR[name]
        kids.append(style(pane, name, colour, alpha))

    skin = S.body_skin()
    for name, region in S.lens_regions().items():
        lens = skin & region
        if not lens.solids():
            continue
        if name.startswith("taillight"):
            kids.append(style(lens, name, P.LENS_RED, P.LENS_ALPHA))
        else:
            kids.append(style(lens, name, P.LENS_CLEAR, P.LENS_ALPHA))

    return group("glazing", kids)
