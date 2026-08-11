"""Body panels, cut out of the one master shell.

No panel here is modelled on its own.  Each is ``body_skin() & region``, and
the regions are separated by ``SHUT_GAP``, so:

  * neighbouring panels are literally the same surface -- highlight and
    reflection lines cross every break with no kink, by construction;
  * every shutline is a real constant-width gap, not a drawn line;
  * the panels tile the car exactly, so nothing floats or overlaps.

The greenhouse is handled the same way: the canopy shell is split into the DLO
glass openings (owned by ``glazing``) and the pillar/roof structure (here), so
the A-pillar, roof rail and C-pillar are exactly ``DLO_PILLAR`` wide.
"""

from __future__ import annotations

import math

from build123d import Cylinder, Plane, Pos, RectangleRounded, Rot, Spline, extrude, make_face

from hypercar_parts import palette as P
from hypercar_parts import surfaces as S
from hypercar_parts.context import group, style

# which panels are painted body colour, which are exposed carbon
CARBON_PANELS = {"rocker:left", "rocker:right", "underbody", "front_fascia_lower"}

PANEL_COLOR = {
    "rocker:left": P.CARBON,
    "rocker:right": P.CARBON,
    "underbody": P.CARBON,
}


def _side_intake_solid():
    """The side intakes: a long wedge carved out of the flank ahead of each
    rear wheel.

    This is what turns a smooth flank into a hypercar flank, and it gives the
    shoulder crease somewhere deliberate to die into instead of fading out.
    """
    prof = [
        (-430.0, 306.0), (-548.0, 512.0), (-742.0, 584.0), (-948.0, 556.0),
        (-1016.0, 428.0), (-962.0, 306.0), (-742.0, 254.0), (-528.0, 262.0),
    ]
    # Plane.XZ's normal is -Y, so extrude(-520) sweeps the profile from local
    # y=0 to y=+520.  Place each copy so that span lands ON the flank
    # (half-width is about 950 here) instead of outside the car.
    out = []
    for y0 in (700.0, -1220.0):
        wire = Spline(*prof, prof[0])
        block = extrude(Plane.XZ * make_face(wire), amount=-520.0)
        out.append(Pos(0, y0, 0) * block)
    return out


def _front_apertures():
    """Front-end breathing: one central slot plus a big duct each side.

    Cut as prisms swept back along -X, so each opening's edge is the
    intersection with the curved fascia -- the aperture inherits the nose
    surface instead of being a decal on it.
    Returns (cutters, duct_blocks).
    """
    cutters = []
    ducts = []

    def prism(y, z, w, h, r, depth, x_start=2330.0):
        face = Plane.YZ.offset(x_start) * Pos(y, z, 0) * RectangleRounded(w, h, r)
        return extrude(face, amount=-depth)

    # central slot, low and wide -- the car's "mouth"
    cutters.append(prism(0.0, 268.0, 900.0, 132.0, 44.0, 520.0))
    ducts.append(prism(0.0, 268.0, 830.0, 96.0, 34.0, 380.0, x_start=2180.0))

    # flanking ducts feeding the front radiators, raked outboard
    for side in (1, -1):
        cutters.append(prism(side * 700.0, 330.0, 380.0, 250.0, 62.0, 560.0))
        ducts.append(prism(side * 700.0, 330.0, 320.0, 196.0, 50.0, 400.0, x_start=2160.0))

    # bonnet extractor: air that comes in the nose has to leave, and the
    # outlet gives the hood surface an event instead of a dead flat panel
    for side in (1, -1):
        face = Plane.XY.offset(900.0) * Pos(1560.0, side * 330.0, 0) * RectangleRounded(420.0, 190.0, 54.0)
        cutters.append(extrude(face, amount=-460.0))
    return cutters, ducts


def _wheelhouse_liners():
    """Close the view into the hollow body through each wheel arch.

    A cylindrical band at the arch radius, kept only where it falls inside the
    body's inner volume, so it lines the arch exactly and stops nowhere else.
    """
    liners = []
    inner_volume = S.body_master_inner()
    corners = (
        ("front", S.FRONT_AXLE_X, S.FRONT_HUB_Z, S.FRONT_ARCH_R),
        ("rear", S.REAR_AXLE_X, S.REAR_HUB_Z, S.REAR_ARCH_R),
    )
    for end, x, z, r in corners:
        for side, nm in ((1, "left"), (-1, "right")):
            length = S.ARCH_OUTER_Y - S.ARCH_INNER_Y
            y_mid = side * (S.ARCH_INNER_Y + length / 2.0)
            outer = Pos(x, y_mid, z) * (Rot(-90, 0, 0) * Cylinder(radius=r + 16.0, height=length))
            inner = Pos(x, y_mid, z) * (Rot(-90, 0, 0) * Cylinder(radius=r, height=length + 4.0))
            band = (outer - inner) & inner_volume
            if band.solids():
                liners.append(style(band, f"wheelhouse_liner:{end}_{nm}", P.BODY_DARK))
    return liners


def _intake_ducts():
    """Back the side intakes so they read as scoops rather than holes.

    A carbon block filling the inboard end of each intake volume: the visible
    result is a duct floor and back wall set well inside the flank, which is
    what gives the intake depth.
    """
    ducts = []
    inner_volume = S.body_master_inner()
    blocks = _side_intake_solid()
    for block, nm, sign in zip(blocks, ("left", "right"), (1.0, -1.0)):
        y0, y1 = sorted((sign * 640.0, sign * 806.0))
        duct = (block & S.slab(-4000, 4000, y0, y1, -4000, 4000)) & inner_volume
        if duct.solids():
            ducts.append(style(duct, f"intake_duct:{nm}", P.BODY_DARK))
    return ducts


def build():
    skin = S.body_skin()
    regions = S.panel_regions()

    # carve every aperture out of the master shell BEFORE splitting into
    # panels, so an opening that straddles a shutline (the side intake does)
    # cuts cleanly across it instead of leaving a mismatched edge
    for cut in _side_intake_solid():
        skin = skin - cut
    # NOTE: an open bay for the door mechanism was tried here and removed.  Any
    # opening big enough to show the mechanism also shows straight through the
    # hollow flank, and a hole in the bodyside costs far more than exposed
    # jewellery gains.  The mechanism is clipped inboard of the skin instead
    # (see hinge.py) so it is concealed when shut and revealed BY the motion.

    front_cutters, front_ducts = _front_apertures()
    for cut in front_cutters:
        skin = skin - cut

    under = S.underfloor_prism()

    # the lamp lenses are cut from this same shell by `glazing`; remove them
    # here so the panel and the lens do not occupy the same space
    lenses = None
    for reg in S.lens_regions().values():
        lenses = reg if lenses is None else (lenses + reg)

    kids = []
    for name, region in regions.items():
        panel = skin & region
        if name == "underbody":
            panel = panel & under
        else:
            panel = panel - under
        panel = panel - lenses
        if not panel.solids():
            continue
        colour = PANEL_COLOR.get(name, P.BODY)
        kids.append(style(panel, name, colour))

    # ---- greenhouse structure: pillars + roof from the canopy shell --------
    glass_shell = S.canopy_glass_shell()
    opening = None
    for reg in S.glazing_regions().values():
        opening = reg if opening is None else (opening + reg)
    structure = glass_shell - opening
    if structure.solids():
        kids.append(style(structure, "pillar_structure", P.BODY))

    kids.extend(_wheelhouse_liners())
    kids.extend(_intake_ducts())

    inner_volume = S.body_master_inner()
    for i, duct in enumerate(front_ducts):
        blocked = duct & inner_volume
        if blocked.solids():
            kids.append(style(blocked, f"front_duct:{i + 1}", P.BODY_DARK))

    return group("body", kids)
