"""Flat three-link bracelet builder (moonwatch archetype).

Frame: WATCH assembly frame from `_spec` — +Z through the crystal, 12
o'clock at +Y, z = 0 at the case-middle/caseback joint. The bracelet
attaches at the spring-bar axes (y = +/-SPRING_BAR_Y, z = SPRING_BAR_Z)
and drapes outward along +/-Y on ONE smooth arc: the per-joint relative
pitch eases from DRAPE_DELTA0 to DRAPE_DELTA1 (2 -> 7 degrees), so
curvature grows monotonically like a bracelet resting over an invisible
wrist form, with no kink at any joint; the clasp chord continues the
same arc one increment further.

Construction vocabulary (all rows share it):

- A row is three separate bodies: two wider brushed outer links
  (BRACELET_OUTER) and a narrower polished center link (BRACELET_CENTER),
  so the center row reads brighter than the brushed outers.
- Row ends articulate on shared pin axes. At every joint the earlier
  row's OUTER links carry convex knuckle eyes (radius EYE_R, centered on
  the axis, deliberately SMALLER than the link half-thickness so the
  hinge stays below the top surface) and the later row's CENTER link
  carries the mating eye; the complementary ends are cut back with a
  concave recess of radius EYE_R + JOINT_CLEARANCE about the same axis,
  so any relative pitch articulates with a constant 0.06 radial
  clearance and zero interpenetration. Above and below the hinge the
  link ends are flat walls, cut PARALLEL TO THE JOINT BISECTOR (each
  end tilted by half the joint's posed relative pitch), so the two
  walls of every joint are parallel planes 2*SHUT_EDGE apart at every
  drape angle.
- Every joint gets a steel pin body (visible ends on the link flanks)
  passing through bores in the knuckle eyes.
- Width tapers linearly BRACELET_WIDTH_AT_LUG -> BRACELET_WIDTH_AT_CLASP
  over each strap; every link is planned as a trapezoid so the taper is
  smooth link to link.
- Every link carries a crowned cross-section baked into its planned
  SECTION (never post-chamfered): the top is a shallow arc across the
  link's own width (sagitta CROWN_SAG) flanked by crisp 45-degree bevel
  facets of leg BEVEL; the bottom is a flatter dome (CROWN_SAG_BOT) with
  the same bevels. The clasp outer plate, inner cover, and flip-lock bow
  sweep the same crowned+beveled section along the clasp curvature arc.
- Joint shutlines: every row end is finished as a ROLLED SHOULDER about
  its pin axis. The shutline walls stay parallel planes 2*SHUT_EDGE =
  0.28 apart (leaned onto each joint's bisector), but instead of meeting
  the crowned top at a scribed edge, each link's crown rolls over a
  convex quarter-round of radius ROLL_R — tangent to the crown ROLL_R
  before the wall and tangent to the wall itself — so the surface normal
  rotates through ~86-90 degrees at every link end and each row reads as
  its own convex pillow with a dark shadow valley at the joint. On
  knuckle-EYE ends the roll stops EYE_ROLL_DEPTH below the crown and a
  flat deck runs across the opening (shaving the knuckle crest), the
  whole cutter clamped above the pin bore roof (FLOOR_Z_MIN); on RECESS
  ends the roll runs the full quarter round into the full-height end
  wall. Laterally the center<->outer walls sit LINK_GAP apart and the
  facing top edges carry the same rolled treatment at radius R_LAT,
  baked into the lofted SECTION, so the three columns also read as
  separate convex bodies over parallel shadow grooves. All shutline cuts
  only REMOVE material, so the 0.06 articulation clearance is untouched.
- Directional finish: every link, end link, and clasp plate carries axial
  satin brushing on its crown — fine parallel V-grooves (pitch
  GRAIN_PITCH, depth GRAIN_DEPTH) along the LOCAL strap axis. Links and
  end links subtract shared `_finishing.straight_grain_cutter` tools
  seated groove-by-groove onto the crown arc (`_grain_field`) in the
  construction frame before posing, so the grain drapes with each link;
  the clasp plates bake the same V-notches into their swept section
  (`_crowned_band(grain=True)`) so the grooves follow the clasp's
  longitudinal curvature. Bevels, rolled shoulders, lateral shoulder
  rounds, and flanks are never grained: they stay mirror-polished
  against the satin field.
"""

from __future__ import annotations

import math

from build123d import (
    Box,
    CenterArc,
    Circle,
    Color,
    Compound,
    Cylinder,
    Part,
    Plane,
    Polygon,
    Polyline,
    Pos,
    RectangleRounded,
    Rot,
    ThreePointArc,
    extrude,
    loft,
    make_face,
    sweep,
)

import _spec as S
import _finishing as F

# ---------------------------------------------------------------------------
# Derived constants (shared dims come from _spec; only construction-local
# values are defined here)
# ---------------------------------------------------------------------------

T2 = S.LINK_THICKNESS / 2.0        # link half thickness
EYE_R = 1.10                        # knuckle eye radius — deliberately SUB-surface:
#                                     with a full-height eye (T2) the mating wrap
#                                     crests through the crowned top and its lip
#                                     traces a 0.49 -> 1.02 plan curve (crescent
#                                     voids at every joint, uncorrectable by cuts)
JOINT_CLEARANCE = 0.06              # radial clearance at every articulation
RECESS_R = EYE_R + JOINT_CLEARANCE  # 1.16 < flank crown height (1.18): the wrap
#                                     never breaks the top surface, so joint edges
#                                     can be straight walls across the full width
PIN_R = 0.9                         # link pin body radius
BORE_R = 0.95                       # knuckle bore radius (0.05 pin clearance)
CENTER_FRAC = 0.34                  # center link share of the row width
LINK_GAP = 0.12                     # lateral WALL gap center <-> outer links
BEVEL = 0.15                        # built-in 45-degree edge-break bevel leg
R_LAT = 0.18                        # rounded-shoulder radius on the facing
#                                     center<->outer top edges: the walls stay
#                                     LINK_GAP apart, but each top edge rolls
#                                     over a convex quarter-round so the three
#                                     columns read as separate convex bodies
#                                     over a shadow groove, not scribed lines
# row-to-row joint: ROLLED SHOULDERS about every pin axis (see module
# docstring). The shutline walls stay parallel planes 2*SHUT_EDGE apart;
# each link's crowned top rolls over a convex quarter-round into the gap.
SHUT_EDGE = 0.14                    # 2 * 0.14 = 0.28 wall-to-wall opening
ROLL_R = 0.32                       # quarter-round shoulder radius at row joints
EYE_ROLL_DEPTH = 0.30               # eye-end roll stops here (~86 deg of
#                                     surface-normal rotation); the shadow deck
#                                     then runs across the knuckle at this
#                                     depth below the crown
FLOOR_Z_MIN = 1.02                  # clamp for eye-end joint cutters: at the
#                                     flanks the crown-following deck would
#                                     otherwise dip below the pin bore roof
#                                     (BORE_R 0.95) and open pinholes
SHUT_RUN = 0.78                     # deck run past the shoulder's wall tangent:
#                                     spans the whole opening and shaves the
#                                     knuckle crest where it pokes above deck
CROWN_SAG = 0.30                    # top crown sagitta across each link width
CROWN_SAG_BOT = 0.10                # gentler dome on the wrist side
CROWN_APEX = T2 - 0.02              # crown apex just inside the stadium envelope
P = S.LINK_PITCH

# directional satin brushing on every link/clasp TOP crown: fine parallel
# V-grooves (shared _finishing.straight_grain_cutter) running along each
# part's LOCAL strap axis, cut in the construction frame BEFORE posing so
# the grain drapes with the link. Only the flat-ish crown field is grained
# — bevels, rolled shoulders, lateral shoulder rounds, and flanks stay
# un-cut and read mirror-polished against the satin field.
GRAIN_PITCH = 0.14                  # groove spacing (helper default)
GRAIN_DEPTH = 0.018                 # groove depth (helper default)
GRAIN_INSET = 0.35                  # field inset from every bevel/shoulder

# first pin axis (end link -> row 1), watch frame, +Y strap
JOINT1_Y = 26.0
JOINT1_Z = 2.6

# drape: ONE smooth arc over the invisible wrist form. The per-joint
# relative pitch eases linearly from DRAPE_DELTA0 (end link -> row 1) to
# DRAPE_DELTA1 (last joint), so curvature grows monotonically and no
# joint reads as a kink; the clasp chord continues the same arc exactly
# one more DRAPE_DELTA1 increment past the last row.
DRAPE_DELTA0 = 2.0                  # relative pitch at the first joint (deg)
DRAPE_DELTA1 = 7.0                  # relative pitch at the last joint (deg)

# end link
END_LINK_WIDTH = S.LUG_WIDTH - 0.2  # 0.1 clearance to each lug inner face
NOSE_HUG_R = S.END_LINK_SEAT_Y      # concave nose arc hugging the case

# clasp construction
CLASP_R = 70.0                      # outer-surface curvature radius
CLASP_PLATE_T = 2.0
CLASP_HALF_W = S.CLASP_WIDTH / 2.0


# ---------------------------------------------------------------------------
# Small geometry helpers
# ---------------------------------------------------------------------------

def _prism_x(profile2d, half_width):
    """Extrude a YZ-plane sketch symmetrically along X."""
    return extrude(Plane.YZ * profile2d, amount=half_width, both=True)


def _crowned_face(xa, xb, z_top, z_bot, s_top, bev, s_bot=0.0, rnd=(False, False)):
    """Closed crowned cross-section face in local (x, z) coordinates.

    Top: shallow arc (sagitta `s_top`, apex at `z_top`) flanked by top
    corner treatments meeting vertical side walls at x = xa / xb. Each
    side is a crisp 45-degree bevel facet of leg `bev` or, when that
    side's `rnd` flag is set, a convex quarter-round of radius `bev`
    (same endpoints, tangent to the crown shoulder and to the wall) so
    the surface normal ROLLS through the corner instead of breaking —
    the rounded-shoulder read of the lateral center<->outer gaps. `bev`
    may be a (left, right) pair. Bottom: flat at `z_bot` when `s_bot`
    == 0, else a gentler downward arc; bottom corners always stay
    45-degree bevels (wrist side). Baking crown, bevels, and shoulder
    rounds into the SECTION replaces 3D edge chamfers/fillets entirely
    — OCC's chamfer on link perimeters that touch dome/eye-cap tangent
    chains silently fails, churns for minutes, or segfaults (see
    /BUGS.md).
    """
    ba, bb = bev if isinstance(bev, tuple) else (bev, bev)
    ra, rb = rnd
    k = 1.0 - math.sqrt(0.5)  # 45-degree midpoint pull-in of a corner round
    xc = (xa + xb) / 2.0
    z_sh = z_top - s_top
    top = ThreePointArc((xb - bb, z_sh), (xc, z_top), (xa + ba, z_sh))

    def corner(x_wall, b, rounded, sgn):
        """Top corner from the crown-arc end down onto the side wall;
        sgn = +1 on the left (xa) side, -1 on the right (xb) side."""
        p_arc = (x_wall + sgn * b, z_sh)
        p_wall = (x_wall, z_sh - b)
        if rounded:
            return ThreePointArc(
                p_arc, (x_wall + sgn * b * k, z_sh - b * k), p_wall
            )
        return Polyline(p_arc, p_wall)

    if s_bot > 0.0:
        left = Polyline(
            (xa, z_sh - ba),
            (xa, z_bot + s_bot + ba),
            (xa + ba, z_bot + s_bot),
        )
        bottom = ThreePointArc(
            (xa + ba, z_bot + s_bot), (xc, z_bot), (xb - bb, z_bot + s_bot)
        )
        right = Polyline(
            (xb - bb, z_bot + s_bot),
            (xb, z_bot + s_bot + bb),
            (xb, z_sh - bb),
        )
    else:
        left = Polyline((xa, z_sh - ba), (xa, z_bot))
        bottom = Polyline((xa, z_bot), (xb, z_bot))
        right = Polyline((xb, z_bot), (xb, z_sh - bb))
    return make_face(
        top
        + corner(xa, ba, ra, +1.0)
        + left
        + bottom
        + right
        + corner(xb, bb, rb, -1.0)
    )


def _plan_prism(xa0, xb0, xa1, xb1, y0, y1, bev=BEVEL, rnd=(False, False)):
    """Tapered side-wall prism with a crowned, edge-broken section.

    Lofted between two crowned XZ sections (x in [xa, xb] at y0 linearly
    to y1): the top of each section is a shallow arc across the link's
    own width (sagitta CROWN_SAG) flanked by 45-degree bevel facets or,
    per `rnd` side flags, convex quarter-round shoulders (R_LAT on the
    facing center<->outer edges); the bottom a flatter dome
    (CROWN_SAG_BOT) with plain bevels. The apex sits at CROWN_APEX, 0.02
    below the stadium/eye-cap envelope, so the knuckle-eye cylinders
    cross the crown transversally (no tangent contact) and only a short
    realistic knuckle crest pokes through at each pin axis. See
    `_crowned_face` for why no 3D chamfer is used.
    """

    def section(xa, xb, y):
        plane = Plane(origin=(0, y, 0), x_dir=(1, 0, 0), z_dir=(0, -1, 0))
        return plane * _crowned_face(
            xa, xb, CROWN_APEX, -CROWN_APEX, CROWN_SAG, bev,
            s_bot=CROWN_SAG_BOT, rnd=rnd,
        )

    return loft([section(xa0, xb0, y0), section(xa1, xb1, y1)], ruled=True)


def _xcyl(r, length, y, z, x_mid=0.0):
    """Cylinder along the X axis at (y, z)."""
    return Pos(x_mid, y, z) * Rot(0, 90, 0) * Cylinder(r, length)


def _crown_cap(half_w, length, s_top=CROWN_SAG, bev=BEVEL):
    """Crowning cap prism (intersect with it): crowned top arc with apex
    at local z = 0 and 45-degree bevel facets at x = +/-half_w, side
    walls dropping far below — bakes the crown + top edge breaks into a
    body whose plan is not a `_plan_prism` trapezoid (end link)."""
    plane = Plane(origin=(0, 0, 0), x_dir=(1, 0, 0), z_dir=(0, -1, 0))
    face = plane * _crowned_face(-half_w, half_w, 0.0, -12.0, s_top, bev)
    return extrude(face, amount=length, both=True)


def _crown_drop(u, half_chord, sag):
    """Depth of a crown arc (sagitta `sag` over half-chord `half_chord`)
    below its apex at transverse offset `u` from the apex."""
    r = (half_chord * half_chord + sag * sag) / (2.0 * sag)
    if abs(u) >= r:
        return sag
    return r - math.sqrt(r * r - u * u)


def _grain_field(x_lo, x_hi, y_lo, y_hi, crown_xc, half_chord, sag, z_apex,
                 skew_deg=0.0):
    """Brushed-grain tool list conformed to a crowned top.

    Grooves run along Y (the strap direction) over the plan rectangle
    [x_lo, x_hi] x [y_lo, y_hi]. The shared straight_grain_cutter emits
    its V-prisms on a flat z = 0 plane; each groove is re-seated here at
    the crown's own height at that groove's x (arc apex `z_apex` at
    x = crown_xc, sagitta `sag` over `half_chord`), so the shallow
    GRAIN_DEPTH bite stays uniform across the crowned width instead of
    fading off the apex. `skew_deg` leans the grooves onto a tapered
    link's own centerline so the crown's apex drift along Y stays within
    the V-prism's 0.02 top margin (a groove whose surface climbs past
    that margin would seal into a subsurface void). Returns tools for
    ONE multi-tool subtract; overshoot along Y is pre-divided out of the
    helper's 1.15 length factor so groove ends stop at y_lo/y_hi, and
    where a rolled shoulder curves away below the field the grooves
    simply fade out (removal only, never a void)."""
    span_x = x_hi - x_lo
    if span_x < GRAIN_PITCH or y_hi - y_lo < 0.5:
        return []
    tools = F.straight_grain_cutter(
        span_x, (y_hi - y_lo) / 1.15, pitch=GRAIN_PITCH, depth=GRAIN_DEPTH,
        along_x=False,
    )
    xm, ym = (x_lo + x_hi) / 2.0, (y_lo + y_hi) / 2.0
    place = Pos(xm, ym, z_apex) * Rot(0, 0, skew_deg)
    out = []
    for i, tool in enumerate(tools):
        off = -span_x / 2.0 + i * GRAIN_PITCH  # helper's groove offsets
        if off > span_x / 2.0 + 1e-9:
            continue  # helper over-emits +2 rows past the far edge
        drop = _crown_drop(xm + off - crown_xc, half_chord, sag)
        out.append(place * Pos(0, 0, -drop) * tool)
    return out


def _reveal_face(xa, xb, y, drop, bev, z_apex=CROWN_APEX, sag=CROWN_SAG):
    """Loft section for `_reveal_cutter`: the region ABOVE the link's own
    crowned top arc lowered by `drop`, up to z = +3, extended 0.3 past
    the plan width so the side walls sit in air. The floor runs FLAT at
    the arc-end height across each side-bevel corner (it does not follow
    the bevel down): at the flanks the lowered bevel corner would dip
    below the knuckle bore's top (0.95) and open pinholes into the bore
    at every groove corner."""
    ba, bb = bev if isinstance(bev, tuple) else (bev, bev)
    z_ap = z_apex - drop
    z_sh = z_ap - sag
    xc = (xa + xb) / 2.0
    arc = ThreePointArc((xb - bb, z_sh), (xc, z_ap), (xa + ba, z_sh))
    lid = Polyline(
        (xa + ba, z_sh),
        (xa - 0.3, z_sh),
        (xa - 0.3, 3.0),
        (xb + 0.3, 3.0),
        (xb + 0.3, z_sh),
        (xb - bb, z_sh),
    )
    plane = Plane(origin=(0, y, 0), x_dir=(1, 0, 0), z_dir=(0, -1, 0))
    return plane * make_face(arc + lid)


def _reveal_cutter(xa, xb, axis_y, direction, edge, depth, run, bev=BEVEL,
                   roll_r=ROLL_R, z_apex=CROWN_APEX, sag=CROWN_SAG):
    """Rolled-shoulder joint cutter about a pin axis.

    Subtracting it rolls the link's crowned top over a convex
    quarter-round shoulder of radius `roll_r`: tangent to the crown at
    y = axis_y - direction*(edge + roll_r) and tangent to a vertical
    wall at y = axis_y - direction*edge, so the surface normal rotates
    through up to 90 degrees while the shutline wall (and the
    2*SHUT_EDGE opening) stays put. The roll follows the crown arc
    across x — stations loft the crown lowered by the roll's drop, in
    15-degree steps (chord sagitta < 0.003, invisible). It stops at
    `depth` below the crown; with `run` > 0 a flat shadow deck at that
    depth continues `run` further (over the knuckle). direction = +1
    for the far end (link body at y < axis), -1 for the near end.
    Removal only: articulation clearances are untouched. Callers must
    clamp eye-end cutters above the pin bore roof (FLOOR_Z_MIN): at the
    link flanks the crown-following deck otherwise dips below it.
    """
    lead = 0.06  # start the loft slightly above the crown: transversal cut
    pts = [(edge + roll_r + lead, -lead)]
    for th_deg in range(15, 91, 15):
        th = math.radians(th_deg)
        d = roll_r * (1.0 - math.cos(th))
        if d < depth - 1e-9:
            pts.append((edge + roll_r * (1.0 - math.sin(th)), d))
        else:
            th_d = math.acos(1.0 - depth / roll_r)
            pts.append((edge + roll_r * (1.0 - math.sin(th_d)), depth))
            break
    if run > 0.0:
        pts.append((pts[-1][0] - run, depth))
    return loft(
        [
            _reveal_face(xa, xb, axis_y - direction * u, d, bev, z_apex, sag)
            for u, d in pts
        ],
        ruled=True,
    )


def _stadium_side(pitch):
    """Side (YZ) profile: rect between the two pin axes + both end discs."""
    rect = Polygon((0, -T2), (pitch, -T2), (pitch, T2), (0, T2), align=None)
    return rect + Circle(EYE_R) + Pos(pitch, 0) * Circle(EYE_R)


def _chamfer_link(part):
    """safe_chamfer ladder on the knuckle-arc flank edges only.

    The top/bottom perimeter bevel is carried by `_plan_prism`'s lofted
    section instead of a 3D chamfer (see its docstring for why).
    """
    flank = [
        e
        for e in part.edges()
        if (e.bounding_box().max.Z - e.bounding_box().min.Z) > 2.0
    ]
    part, _ = F.safe_chamfer(part, flank, 0.10)
    return part


# ---------------------------------------------------------------------------
# Links, rows, pins
# ---------------------------------------------------------------------------

def _make_link(
    xn0, xn1, xf0, xf1, pitch, near, far, color, bev=BEVEL, rnd=(False, False),
    tilt_near=0.0, tilt_far=0.0,
):
    """One link body in row-local frame (origin = near pin axis, +Y along
    the strap, z = 0 mid-thickness). `near`/`far` are 'eye' or 'recess'.

    Every end is finished as a rolled shoulder (see `_reveal_cutter`).
    EYE ends: the crown rolls a ROLL_R quarter-round down to a shadow
    deck EYE_ROLL_DEPTH below the crown that runs across the opening
    (the sub-surface knuckle crest is shaved to the deck); the cutter is
    clamped above FLOOR_Z_MIN so it cannot pinhole into the pin bore.
    RECESS ends: the same ROLL_R roll carries the crown a full quarter
    round onto a full-height flat wall SHUT_EDGE past the axis (the
    wrap opening sits entirely below the surface). `tilt_near`/
    `tilt_far` (degrees) lean each end cut onto the joint's bisector —
    half the posed relative pitch, positive magnitude — so both walls
    of a joint are parallel and the wall opening stays 2*SHUT_EDGE at
    every drape angle (untilted walls pinch shut at the bottom on the
    steepest DRAPE_DELTA1 joints).
    """
    ya, yb = -EYE_R - 0.3, pitch + EYE_R + 0.3
    body = (
        _prism_x(_stadium_side(pitch), 12.0)
        & _plan_prism(xn0, xn1, xf0, xf1, ya, yb, bev=bev, rnd=rnd)
    )
    tools = []
    tools.append(_xcyl(RECESS_R if near == "recess" else BORE_R, 30.0, 0.0, 0.0))
    tools.append(_xcyl(RECESS_R if far == "recess" else BORE_R, 30.0, pitch, 0.0))
    for axis_y, direction, kind, x0, x1, tilt in (
        (0.0, -1.0, near, xn0, xn1, tilt_near),
        (pitch, 1.0, far, xf0, xf1, -tilt_far),
    ):
        place = Pos(0, axis_y, 0) * Rot(tilt, 0, 0)
        if kind == "eye":
            cut = place * _reveal_cutter(
                x0, x1, 0.0, direction, SHUT_EDGE, EYE_ROLL_DEPTH, SHUT_RUN,
                bev=bev,
            )
            # clamp horizontal in the ROW frame (the bore is too), so the
            # tilted crown-following deck stays above the bore roof
            cut = cut & (Pos(0, axis_y, FLOOR_Z_MIN + 3.0) * Box(26.0, 8.0, 6.0))
        else:
            # full-height end wall SHUT_EDGE past the axis (slab away from
            # the body), its top rolled over the same quarter-round; the
            # roll overruns the slab by 0.05 so no faces coincide
            cut = place * (
                Pos(0, direction * (0.27 - SHUT_EDGE), 0) * Box(30.0, 0.54, 3.6)
                + _reveal_cutter(
                    x0, x1, 0.0, direction, SHUT_EDGE, ROLL_R, 0.05, bev=bev
                )
            )
        tools.append(cut)

    # axial satin brushing on the crown field between the rolled shoulders:
    # grooves along local +Y, skewed onto the tapered link's own centerline,
    # inset off the bevels/shoulder rounds so those stay mirror-polished.
    # Same batched subtract as the joint cutters (ONE boolean per link).
    ba, bb = bev if isinstance(bev, tuple) else (bev, bev)
    xc_near, xc_far = (xn0 + xn1) / 2.0, (xf0 + xf1) / 2.0
    half_chord = ((xn1 - xn0) + (xf1 - xf0)) / 4.0 - (ba + bb) / 2.0
    tools += _grain_field(
        max(xn0, xf0) + ba + GRAIN_INSET,
        min(xn1, xf1) - bb - GRAIN_INSET,
        SHUT_EDGE + ROLL_R,
        pitch - (SHUT_EDGE + ROLL_R),
        (xc_near + xc_far) / 2.0,
        half_chord,
        CROWN_SAG,
        CROWN_APEX,
        skew_deg=math.degrees(math.atan2(xc_far - xc_near, yb - ya)),
    )
    body = body - tools
    body = _chamfer_link(body)
    body.color = Color(*color)
    return body


def make_row(w0, w1, pitch=P, terminal=False, tilt_near=0.0, tilt_far=0.0):
    """One bracelet row: (left, center, right) bodies in row-local frame.

    w0/w1: row width at the near/far pin axis (taper is smooth link to
    link). Outer links: recess near / eye far. Center link: eye near /
    recess far (eye both ends when `terminal`). `tilt_near`/`tilt_far`:
    joint-bisector half-angles (degrees) for the end cuts.
    """
    ya, yb = -EYE_R - 0.3, pitch + EYE_R + 0.3

    def hw(y):
        return (w0 + (w1 - w0) * y / pitch) / 2.0

    def ch(y):
        return CENTER_FRAC * (w0 + (w1 - w0) * y / pitch) / 2.0

    tilts = {"tilt_near": tilt_near, "tilt_far": tilt_far}
    center = _make_link(
        -ch(ya), ch(ya), -ch(yb), ch(yb), pitch,
        near="eye", far=("eye" if terminal else "recess"),
        color=S.BRACELET_CENTER, bev=(R_LAT, R_LAT), rnd=(True, True), **tilts,
    )
    left = _make_link(
        -hw(ya), -(ch(ya) + LINK_GAP), -hw(yb), -(ch(yb) + LINK_GAP), pitch,
        near="recess", far="eye", color=S.BRACELET_OUTER,
        bev=(BEVEL, R_LAT), rnd=(False, True), **tilts,
    )
    right = _make_link(
        ch(ya) + LINK_GAP, hw(ya), ch(yb) + LINK_GAP, hw(yb), pitch,
        near="recess", far="eye", color=S.BRACELET_OUTER,
        bev=(R_LAT, BEVEL), rnd=(True, False), **tilts,
    )
    return left, center, right


def make_pin(length):
    """Link pin body along X, visible ends on the link flanks.

    Ends are flat discs with only a 0.05 edge break, sitting near-flush
    in the bore — a 0.18 end chamfer on the 0.9 radius read as a pointed
    cone tip recessed in the bore at macro scale."""
    pin = Rot(0, 90, 0) * Cylinder(PIN_R, length)
    ends = [
        e
        for e in pin.edges()
        if (e.bounding_box().max.X - e.bounding_box().min.X) < 0.01
    ]
    pin, _ = F.safe_chamfer(pin, ends, 0.05)
    pin.color = Color(*S.STEEL_DARK)
    return pin


def make_spring_bar():
    """Spring bar on the lug axis (watch frame, +Y side).

    The visible barrel is kept SHORTER than the end link (its ends stop
    0.1 inside the end-link bore, at x = +/-9.8 vs the end-link flanks at
    +/-9.9): only the sprung reduced-diameter tips would enter the lug
    holes on a real bar, and modeling the full barrel through the 0.1
    flank<->lug slot left a bright exposed stub sliver on each side in
    dial-side 3/4 views. The bar is fully shielded behind the end-link
    wings; the lug holes still read as drilled from outside."""
    bar = _xcyl(S.SPRING_BAR_DIAMETER / 2.0, 19.6, S.SPRING_BAR_Y, S.SPRING_BAR_Z)
    ends = [
        e
        for e in bar.edges()
        if (e.bounding_box().max.X - e.bounding_box().min.X) < 0.01
    ]
    bar, _ = F.safe_chamfer(bar, ends, 0.2)
    bar.color = Color(*S.STEEL_DARK)
    return bar


# ---------------------------------------------------------------------------
# End link
# ---------------------------------------------------------------------------

def make_end_link():
    """End link in the watch frame (+Y side): hugs the lug opening, nose
    tucked between the lugs against the case flank, hollow-look back,
    knuckle eyes at the outer widths of the first joint."""
    jy, jz = JOINT1_Y, JOINT1_Z
    nose_y = 19.2                     # flat flank front; arc trims the center
    top_nose, top_tail = 4.45, 4.05
    bot_nose, bot_tail = 1.9, 1.35
    slope = (top_nose - top_tail) / (24.8 - nose_y)
    slope_deg = math.degrees(math.atan(slope))

    prof = Polygon(
        (nose_y, bot_nose),
        (nose_y, top_nose),
        (24.8, top_tail),
        (jy, 3.95),   # deck stays at cap height to the axis: the sub-surface
        (jy, 1.6),    # eye (r 1.10, top 3.70) no longer carries the tail
        (24.8, bot_tail),
        align=None,
    ) + Pos(jy, jz) * Circle(EYE_R)

    half_w = END_LINK_WIDTH / 2.0
    # crown + 45-degree top edge bevels baked in, pitched to follow the
    # nose->tail top slope so the crown runs the full link length
    cap = (
        Pos(0, nose_y, top_nose)
        * Rot(-slope_deg, 0, 0)
        * _crown_cap(half_w, 14.0)
    )
    body = _prism_x(prof, half_w) & cap

    cw1 = CENTER_FRAC * S.BRACELET_WIDTH_AT_LUG      # center width at joint 1
    slot_half = cw1 / 2.0 + LINK_GAP

    # groove pair continuing the three-column separation over the top: a
    # LINK_GAP slot flanked by R_LAT rounded shoulders, matching the rows'
    # lateral rolled edges (profile extruded along the strap, pitched with
    # the nose->tail top slope)
    def groove(x):
        y_mid = 22.9
        z_top = top_nose - slope * (y_mid - nose_y)
        g = LINK_GAP / 2.0
        r = R_LAT
        k = 1.0 - math.sqrt(0.5)
        prof = make_face(
            Polyline((-g - r, 0.8), (-g - r, 0.0))
            + ThreePointArc((-g - r, 0.0), (-g - r * k, -r * k), (-g, -r))
            + Polyline((-g, -r), (-g, -0.34), (g, -0.34), (g, -r))
            + ThreePointArc((g, -r), (g + r * k, -r * k), (g + r, 0.0))
            + Polyline((g + r, 0.0), (g + r, 0.8), (-g - r, 0.8))
        )
        plane = Plane(origin=(0, 0, 0), x_dir=(1, 0, 0), z_dir=(0, -1, 0))
        prism = extrude(plane * prof, amount=2.3, both=True)
        return Pos(x, y_mid, z_top) * Rot(-slope_deg, 0, 0) * prism

    # joint-1 rolled shoulder: the same vocabulary as the row joints — the
    # tail deck rolls over a ROLL_R quarter-round whose vertical-tangent
    # wall sits SHUT_EDGE before the pin axis, leaned onto the joint
    # bisector (half of row 1's DRAPE_DELTA0 pitch, tracking the drape
    # schedule so the joint-1 walls stay parallel 0.28 apart); the shadow
    # deck past the wall shaves the eye knuckle crest. The whole cutter is
    # clamped at z >= 3.62 (bore roof at the shutline is 3.55) so it
    # cannot pinhole into the pin bore.
    tail_roll = (
        Pos(0, jy, jz)
        * Rot(-DRAPE_DELTA0 / 2.0, 0, 0)
        * _reveal_cutter(
            -half_w, half_w, 0.0, 1.0, SHUT_EDGE, EYE_ROLL_DEPTH, 0.40,
            bev=BEVEL, z_apex=3.95 - jz,
        )
    ) & (Pos(0, jy, 3.62 + 3.0) * Box(26.0, 8.0, 6.0))

    tools = [
        Cylinder(NOSE_HUG_R, 20.0, align=(None, None, None)),  # case-hugging nose arc
        _xcyl(S.SPRING_BAR_DIAMETER / 2.0 + 0.1, 30.0, S.SPRING_BAR_Y, S.SPRING_BAR_Z),
        Pos(0, 23.05, 1.7) * Box(16.6, 3.7, 2.4),    # hollow back (centered)
        _xcyl(RECESS_R, 2 * slot_half, jy, jz),      # center-link recess slot
        _xcyl(BORE_R, 30.0, jy, jz),                 # pin bore
        groove(cw1 / 2.0 + LINK_GAP / 2.0),
        groove(-(cw1 / 2.0 + LINK_GAP / 2.0)),
        tail_roll,
    ]
    body = body - tools

    # break remaining edges, but keep the profile-baked crown/bevel facet
    # lines (along Y at the outer widths, near the top), the joint-1
    # rolled shoulder (chamfering its loft-station seams would flatten
    # the roll — and OCC chamfers on such tangent chains fail or
    # segfault, see /BUGS.md), and the groove shoulders crisp
    def _keep(e):
        bb = e.bounding_box()
        on_bevel_band = (
            bb.min.Z > 3.0 and min(abs(bb.min.X), abs(bb.max.X)) > 9.3
        )
        on_shutline = bb.max.Y > jy - 0.85 and bb.min.Z > 3.2
        xs = sorted((abs(bb.min.X), abs(bb.max.X)))
        on_groove = (
            bb.min.Z > 3.2
            and bb.min.X * bb.max.X > 0.0
            and xs[0] > 2.9
            and xs[1] < 4.1
        )
        return not (on_bevel_band or on_shutline or on_groove)

    body, _ = F.safe_chamfer(body, [e for e in body.edges() if _keep(e)], 0.12)

    # axial satin brushing on the three crown bands between the groove
    # pair, in the pitched crown-cap frame (grain follows the nose->tail
    # top slope). Applied AFTER the edge-break chamfer so the groove
    # micro-edges never enter the chamfer candidate set; still ONE
    # batched multi-tool subtract. Bevels, groove shoulders, and the
    # joint-1 rolled shoulder stay un-grained (mirror-polished).
    x_g = cw1 / 2.0 + LINK_GAP / 2.0            # groove pair centerlines
    band_in = x_g - (LINK_GAP / 2.0 + R_LAT) - GRAIN_INSET
    out_lo = x_g + LINK_GAP / 2.0 + R_LAT + GRAIN_INSET
    out_hi = half_w - BEVEL - GRAIN_INSET
    y_roll = (jy - (SHUT_EDGE + ROLL_R)) - nose_y - 0.05  # tail roll start
    y_nose_c = NOSE_HUG_R - nose_y + GRAIN_INSET          # case-hugging arc
    y_nose_o = (
        math.sqrt(NOSE_HUG_R * NOSE_HUG_R - out_lo * out_lo)
        - nose_y + GRAIN_INSET
    )
    frame = Pos(0, nose_y, top_nose) * Rot(-slope_deg, 0, 0)
    grain = (
        _grain_field(-band_in, band_in, y_nose_c, y_roll,
                     0.0, half_w - BEVEL, CROWN_SAG, 0.0)
        + _grain_field(out_lo, out_hi, y_nose_o, y_roll,
                       0.0, half_w - BEVEL, CROWN_SAG, 0.0)
        + _grain_field(-out_hi, -out_lo, y_nose_o, y_roll,
                       0.0, half_w - BEVEL, CROWN_SAG, 0.0)
    )
    body = body - [frame * t for t in grain]
    body.color = Color(*S.BRACELET_OUTER)
    return body


# ---------------------------------------------------------------------------
# Clasp (closed, unbranded)
# ---------------------------------------------------------------------------

def _band(r_out, r_in, phi0_deg, phi1_deg, half_w):
    """Curved plate segment: annular sector about the clasp curvature
    center (clasp-local YZ), extruded across X."""
    zc = T2 - CLASP_R
    p0, p1 = math.radians(phi0_deg), math.radians(phi1_deg)
    ann = Pos(0, zc) * (Circle(r_out) - Circle(r_in))
    wedge = Polygon(
        (0, zc),
        (200.0 * math.sin(p0), zc + 200.0 * math.cos(p0)),
        (200.0 * math.sin(p1), zc + 200.0 * math.cos(p1)),
        align=None,
    )
    return _prism_x(ann & wedge, half_w)


def _crowned_band(r_out, r_in, phi0_deg, phi1_deg, half_w, s_top, bev,
                  grain=False):
    """Curved crowned plate: the crowned + 45-degree-beveled cross-section
    (see `_crowned_face`) swept along the clasp curvature arc, so the edge
    breaks are baked into the profile instead of post-chamfered.

    `grain=True` bakes the axial satin brushing into the SECTION: fine
    V-notches (GRAIN_PITCH / GRAIN_DEPTH, same vocabulary as
    `_grain_field`) are subtracted from the 2D crown arc before the
    sweep, so the grooves follow the clasp's longitudinal curvature
    exactly and continuously — a straight 3D grain tool cannot (the
    CLASP_R sagitta over the plate is ~150x the groove depth, and chord
    segmenting both costs minutes of booleans and multiplies the face
    count ~25x). The notch field keeps GRAIN_INSET off the profile-baked
    bevels so they stay mirror-polished; each notch is 0.004 narrower
    than the pitch so mirrored-pair notch corners never meet in exact
    (sliver-shedding) point tangency."""
    zc = T2 - CLASP_R
    t = r_out - r_in
    r_mid = (r_out + r_in) / 2.0
    face = _crowned_face(-half_w, half_w, t / 2.0, -t / 2.0, s_top, bev)
    if grain:
        half_chord = half_w - bev
        span = 2.0 * (half_chord - GRAIN_INSET)
        w = GRAIN_PITCH / 2.0 - 0.002
        notches = []
        for i in range(int(span / GRAIN_PITCH) + 1):
            u = -span / 2.0 + i * GRAIN_PITCH
            z_i = t / 2.0 - _crown_drop(u, half_chord, s_top)
            notches.append(Polygon(
                (u - w, z_i + 0.02), (u + w, z_i + 0.02),
                (u, z_i - GRAIN_DEPTH), align=None,
            ))
        face = face - notches
    path = Plane.YZ * CenterArc(
        (0, zc), r_mid,
        start_angle=90.0 - phi1_deg,
        arc_size=phi1_deg - phi0_deg,
    )
    plane = Plane(origin=path @ 0, x_dir=(1, 0, 0), z_dir=path % 0)
    section = plane * face
    return sweep(section, path=path)


def _arc_point(phi_deg, radius):
    """(y, z) of a point on the clasp curvature arc (clasp-local)."""
    zc = T2 - CLASP_R
    p = math.radians(phi_deg)
    return radius * math.sin(p), zc + radius * math.cos(p)


def make_clasp():
    """Closed fold-over clasp in clasp-local frame (origin = hinge pin
    axis to the last 6-o'clock row, +Y along the strap, +Z outward).

    Returns a list of (part, label) with colors set. Unbranded: plain
    brushed outer plate, chamfered edges only.
    """
    parts = []
    # pusher axis sits 0.55 below the outer face so the through-hole stays
    # clear of the crown's edge bevels (crown drop at the flank = 0.45)
    y_push, z_push = _arc_point(26.0, CLASP_R - 2.15)

    # --- outer plate (brushed, curved, crowned) + center hinge tab ----------
    # axial satin brushing baked into the swept section (grain=True): the
    # grooves follow the clasp's long axis; bevels stay mirror-polished
    plate = _crowned_band(
        CLASP_R, CLASP_R - CLASP_PLATE_T, 1.0, 31.0, CLASP_HALF_W,
        CROWN_SAG, BEVEL, grain=True,
    )
    plan = extrude(
        Pos(0, 18.3) * RectangleRounded(S.CLASP_WIDTH, 35.0, 3.0),
        amount=40.0, both=True,
    )
    plate = plate & plan
    plate = plate - [
        _xcyl(RECESS_R, 40.0, 0.0, 0.0),          # hinge relief at the strap joint
        _xcyl(1.6, 40.0, y_push, z_push),         # pusher through-holes
    ]
    tab_prof = Circle(EYE_R) + Polygon(
        (0, -T2), (3.5, -T2), (3.5, T2), (0, T2), align=None
    )
    tab = _prism_x(tab_prof, 2.65) - _xcyl(BORE_R, 30.0, 0.0, 0.0)
    body = plate + tab
    # break only the short cut/end edges; the long swept facets already
    # carry their profile-baked bevels and must stay crisp, and the grain
    # micro-edges (groove flanks crossed by the plan end cuts, all well
    # under 0.6 long) must never enter the chamfer candidate set
    short_edges = [
        e
        for e in body.edges()
        if (e.bounding_box().max.Y - e.bounding_box().min.Y) < 12.0
        and e.length > 0.6
    ]
    body, _ = F.safe_chamfer(body, short_edges, 0.12)
    body.color = Color(*S.BRACELET_OUTER)
    parts.append((body, "clasp_body"))

    # --- inner cover plate (folded closed under the outer plate) ------------
    # crowned + beveled section baked in (with the same axial brushing as
    # the outer plate); no post chamfer
    cover = _crowned_band(CLASP_R - 2.3, CLASP_R - 3.5, 4.0, 29.5, 7.0,
                          0.18, 0.10, grain=True)
    cover.color = Color(*S.BRACELET_OUTER)
    parts.append((cover, "clasp_cover"))

    # --- internal spring blade ----------------------------------------------
    blade = _band(CLASP_R - 2.06, CLASP_R - 2.24, 8.0, 20.0, 2.0)
    blade.color = Color(*S.STEEL_DARK)
    parts.append((blade, "clasp_spring_blade"))

    # --- flank pushers -------------------------------------------------------
    # outer end protrudes 1.1 past the plate flank (8.5); inner end stops at
    # 7.3, clear of the inner cover's 7.0 half-width (a 2.7-long pusher at
    # x_mid 8.25 penetrated the cover by 0.1 — pairwise-probe clash)
    for sgn, side in ((1.0, "right"), (-1.0, "left")):
        push = _xcyl(1.5, 2.3, y_push, z_push, x_mid=sgn * 8.45)
        ends = [
            e
            for e in push.edges()
            if (e.bounding_box().max.X - e.bounding_box().min.X) < 0.01
        ]
        push, _ = F.safe_chamfer(push, ends, 0.3)
        push.color = Color(*S.BRACELET_CENTER)
        parts.append((push, f"clasp_pusher_{side}"))

    # --- fold hinge knuckle --------------------------------------------------
    yk, zk = _arc_point(30.6, CLASP_R - 3.1)
    knuckle = _xcyl(1.0, 13.0, yk, zk)
    ends = [
        e
        for e in knuckle.edges()
        if (e.bounding_box().max.X - e.bounding_box().min.X) < 0.01
    ]
    knuckle, _ = F.safe_chamfer(knuckle, ends, 0.15)
    knuckle.color = Color(*S.STEEL_DARK)
    parts.append((knuckle, "clasp_hinge_knuckle"))

    # --- flip-lock bow (polished stirrup hugging the outer plate) -----------
    # crowned + beveled section baked in; only the window-cut edges (all
    # strictly inside the window plan) still need a break
    bow = _crowned_band(CLASP_R + 0.66, CLASP_R + 0.06, 20.6, 30.4, 4.5, 0.15, 0.08)
    y_w, _zw = _arc_point(25.5, CLASP_R + 0.45)
    window = extrude(
        Pos(0, y_w) * RectangleRounded(7.0, 9.8, 2.2), amount=60.0, both=True
    )
    bow = bow - window

    def _in_window(e):
        bb = e.bounding_box()
        return (
            max(abs(bb.min.X), abs(bb.max.X)) < 3.8
            and bb.min.Y > y_w - 5.3
            and bb.max.Y < y_w + 5.3
        )

    bow, _ = F.safe_chamfer(bow, [e for e in bow.edges() if _in_window(e)], 0.08)
    bow.color = Color(*S.BRACELET_CENTER)
    parts.append((bow, "clasp_flip_lock"))

    return parts


# ---------------------------------------------------------------------------
# Strap assembly (drape chain)
# ---------------------------------------------------------------------------

def _row_deltas(n):
    """Per-joint relative pitch (degrees): eases linearly from
    DRAPE_DELTA0 at the first joint to DRAPE_DELTA1 at the last, so the
    strap's curvature grows smoothly instead of stepping."""
    if n <= 1:
        return [DRAPE_DELTA0] * n
    return [
        DRAPE_DELTA0 + (DRAPE_DELTA1 - DRAPE_DELTA0) * k / (n - 1)
        for k in range(n)
    ]


def _row_angles(n):
    """Cumulative downward pitch per row: one continuous convex arc (the
    running sum of the eased `_row_deltas`), no kink at any joint."""
    out, acc = [], 0.0
    for d in _row_deltas(n):
        acc += d
        out.append(acc)
    return out


def _joint_chain(angles):
    """Pin-axis (y, z) positions from JOINT1 through the last joint."""
    joints = [(JOINT1_Y, JOINT1_Z)]
    for th in angles:
        y, z = joints[-1]
        t = math.radians(th)
        joints.append((y + P * math.cos(t), z - P * math.sin(t)))
    return joints


def _joint_width(k, n_rows):
    """Row width at 1-based joint index k (1 = lug end)."""
    taper = S.BRACELET_WIDTH_AT_LUG - S.BRACELET_WIDTH_AT_CLASP
    return S.BRACELET_WIDTH_AT_LUG - taper * (k - 1) / n_rows


def _build_strap(side):
    """All parts of one strap as (part, label) in the watch frame.

    `side` is "12" (+Y, 6 rows) or "6" (-Y, 5 rows + clasp).
    """
    n = S.LINKS_PER_SIDE_12 if side == "12" else S.LINKS_PER_SIDE_6
    angles = _row_angles(n)
    joints = _joint_chain(angles)
    # clasp chord continues the drape arc one more increment (6 side)
    clasp_pitch = angles[-1] + DRAPE_DELTA1
    flip = Rot(0, 0, 180) if side == "6" else None

    def world(p):
        return (flip * p) if flip is not None else p

    parts = []
    parts.append((world(make_end_link()), f"end_link_{side}"))
    parts.append((world(make_spring_bar()), f"spring_bar_{side}"))

    for i in range(n):
        w0 = _joint_width(i + 1, n)
        w1 = _joint_width(i + 2, n)
        terminal = side == "12" and i == n - 1
        th = angles[i]
        jy, jz = joints[i]
        place = Pos(0, jy, jz) * Rot(-th, 0, 0)
        # joint-bisector half-angles: previous body is the end link (0 deg);
        # past the last row sits the clasp (6 side) or nothing (12 side)
        th_prev = angles[i - 1] if i > 0 else 0.0
        if i + 1 < n:
            th_next = angles[i + 1]
        else:
            th_next = clasp_pitch if side == "6" else th
        left, center, right = make_row(
            w0, w1, terminal=terminal,
            tilt_near=(th - th_prev) / 2.0, tilt_far=(th_next - th) / 2.0,
        )
        parts.append((world(place * left), f"link_{side}_r{i + 1}_left"))
        parts.append((world(place * center), f"link_{side}_r{i + 1}_center"))
        parts.append((world(place * right), f"link_{side}_r{i + 1}_right"))

    for k, (jy, jz) in enumerate(joints, start=1):
        pin = make_pin(_joint_width(k, n) - 0.10)
        parts.append((world(Pos(0, jy, jz) * pin), f"pin_{side}_j{k}"))

    clasp_parts = []
    if side == "6":
        jy, jz = joints[-1]
        place = Pos(0, jy, jz) * Rot(-clasp_pitch, 0, 0)
        for part, label in make_clasp():
            clasp_parts.append((world(place * part), label))
    return parts, clasp_parts


def build_bracelet():
    """Full bracelet as a labeled assembly Compound in the watch frame."""
    strap12, _ = _build_strap("12")
    strap6, clasp = _build_strap("6")

    def compound(pairs, label):
        kids = []
        for part, name in pairs:
            if not isinstance(part, Part):
                # some boolean/chamfer chains return a bare Compound; the
                # per-component STEP/GLB export only colors Part/Sketch/
                # Curve leaves ("Unknown Compound type, color not set"),
                # which silently drops the finish contrast
                solid = Part(part.wrapped)
                solid.color = part.color
                part = solid
            part.label = name
            kids.append(part)
        return Compound(children=kids, label=label)

    return Compound(
        children=[
            compound(strap12, "strap_12"),
            compound(strap6, "strap_6"),
            compound(clasp, "clasp"),
        ],
        label="bracelet",
    )
