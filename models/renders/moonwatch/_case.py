"""Case cluster for the moonwatch chronograph.

Case middle with twisted lyre lugs and asymmetric crown guard, tachymeter
bezel (steel ring + black insert + filled scale), hesalite-style domed
crystal, display caseback (sapphire + retaining ring), crown, pump pushers
(machined case bosses, slender collared tubes, short domed caps, coil
springs), gaskets, and spring bars.

Frame: WATCH frame per `_spec` — z = 0 at the case-middle / caseback joint
plane, +Z through the crystal, crown at +X.  All `build_*` functions return
parts already positioned in the watch frame; `build_case_parts()` returns the
full labeled, colored list.

Finishing (geometric, shared `_finishing` vocabulary): the lug top fields and
the exposed guard-top shoulder carry directional satin grain along Y (the
strap direction, `straight_grain_cutter`), the case flank's widest zone and
the bezel steel ring's top annulus carry fine circumferential/circular
graining, and everything else — the twisted lug bevel facets, bezel edge
chamfers, crown flutes, pusher caps — stays smooth as the polished contrast.
"""

from __future__ import annotations

import math

from build123d import (
    Align,
    Axis,
    BuildLine,
    BuildSketch,
    Circle,
    Color,
    Cylinder,
    Helix,
    Line,
    Plane,
    Polygon,
    Pos,
    RadiusArc,
    Rectangle,
    Rot,
    Sphere,
    Text,
    Torus,
    extrude,
    loft,
    make_face,
    mirror,
    revolve,
    sweep,
)

import _spec as S
import _finishing as F

# ---------------------------------------------------------------------------
# Derived case-middle geometry (local modeling choices only; every shared
# dimension comes from _spec).
# ---------------------------------------------------------------------------

R_BAND = S.CASE_MIDDLE_DIAMETER / 2.0          # 20.5
GUARD_CENTER_X = 4.0                            # offset circle forming the
GUARD_RADIUS = 18.0                             # asymmetric crown guard:
# reach = GUARD_CENTER_X + GUARD_RADIUS = 22.0 (+1.5 over the band at +X),
# blending to the round band at roughly +/-47 degrees.

BORE_RADIUS = 15.1                              # movement bore
SEAT_RADIUS = 19.55                             # crystal/gasket seat rebate
SEAT_Z = 6.0                                    # rebate floor
BACK_RECESS_RADIUS = 18.3                       # caseback boss recess
BACK_RECESS_TOP = 1.3

BEZEL_TOP_Z = S.CASE_MIDDLE_HEIGHT + S.BEZEL_HEIGHT          # 9.2
CRYSTAL_APEX_Z = BEZEL_TOP_Z + S.CRYSTAL_DOME_RISE           # 10.9

# --- Finishing fields (geometric brushed/polished contrast) ----------------
# Satin fields use the shared straight_grain_cutter vocabulary; the case
# reads slightly coarser than the bracelet links (0.18 vs 0.14 pitch).
GRAIN_PITCH = 0.18
GRAIN_DEPTH = 0.018
GRAIN_FACET_MARGIN = 0.45       # polished margin kept to the lug facet line
GRAIN_INNER_MARGIN = 0.30       # margin to the lug inner face
# Circumferential flank graining (reads as circular brushing on the band's
# widest zone): stacked V-rings, same V vocabulary as snailing_cutter but
# revolved on the band/guard radius instead of a flat top face.
FLANK_RING_PITCH = 0.16
FLANK_RING_DEPTH = 0.015
FLANK_RING_Z_LO = 2.04
FLANK_RING_Z_HI = 4.92
FLANK_RING_REACH = 0.45         # radial overshoot into air outside the wall
# Clip sectors (start_deg, span_deg). Band-centered rings stay out of the
# four lug quadrants (lugs cross the band radius there — a full ring would
# tunnel a subsurface void through the lug roots). The guard-centered family
# uses angles LOCAL to the guard axis at (4*s, 0): +/-27 deg local stays
# short of the pusher bosses (+/-42 deg local, ~8 deg half-width, so their
# root edges reach ~34 deg local) and of the band/guard blend seam.
FLANK_SECTORS_BAND = ((68.0, 44.0), (150.0, 60.0), (248.0, 44.0))
FLANK_SECTOR_GUARD = (-27.0, 54.0)

LUG_HALF_GAP = S.LUG_WIDTH / 2.0                # 10.0 (lug inner faces)
LUG_TIP_Y = S.LUG_TO_LUG / 2.0                  # 24.0

# Lyre-lug loft stations: (y, z_top, z_bot, x_out, x_bevel_top, z_bevel_out).
# The polished facet runs from (x_bevel_top, z_top) to (x_out, z_bevel_out):
# nearly horizontal at the root (a top bevel) rotating to nearly vertical at
# the tip (a flank bevel) — the twisted-facet read.  Root station is fully
# buried inside the case band so the loft emerges from the flank.
_LUG_STATIONS = (
    (10.5, 5.95, 0.30, 17.40, 15.80, 5.30),
    (14.0, 5.85, 0.85, 16.90, 15.10, 4.50),
    (17.5, 5.60, 1.35, 15.90, 14.10, 3.55),
    (20.5, 5.10, 1.75, 14.55, 13.00, 2.90),
    (22.8, 4.45, 2.00, 13.30, 12.25, 2.55),
    (23.7, 4.05, 2.15, 12.60, 11.85, 2.45),
    (LUG_TIP_Y, 3.35, 2.35, 11.95, 11.35, 2.60),
)


def _catmull_rom(p0, p1, p2, p3, t):
    return 0.5 * (
        2 * p1
        + (-p0 + p2) * t
        + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
        + (-p0 + 3 * p1 - 3 * p2 + p3) * t * t * t
    )


def _dense_lug_stations(n_sub: int = 3):
    """Catmull-Rom interpolation of the control stations so the ruled loft
    reads as a smooth sculpted horn instead of creased planar panels."""
    rows = [tuple(map(float, r)) for r in _LUG_STATIONS]
    ext = [rows[0]] + rows + [rows[-1]]
    out = []
    for i in range(1, len(ext) - 2):
        p0, p1, p2, p3 = ext[i - 1], ext[i], ext[i + 1], ext[i + 2]
        for k in range(n_sub):
            t = k / n_sub
            out.append(tuple(
                _catmull_rom(p0[j], p1[j], p2[j], p3[j], t) for j in range(6)
            ))
    out.append(rows[-1])
    return out

STEEL_C = Color(*S.STEEL)
STEEL_DARK_C = Color(*S.STEEL_DARK)
GASKET_C = Color(*S.GASKET)


# ---------------------------------------------------------------------------
# Case middle with lugs
# ---------------------------------------------------------------------------

def _band_profile(scale: float):
    """Plan profile of the case band: round band + crown-guard bulge."""
    return Circle(R_BAND * scale) + Pos(GUARD_CENTER_X * scale, 0) * Circle(
        GUARD_RADIUS * scale
    )


_BAND_CHAMFER_APPLIED = 0.0     # set by _case_band (safe_chamfer retry ladder)


def _case_band():
    global _BAND_CHAMFER_APPLIED
    sections = [
        Pos(0, 0, 0.0) * _band_profile(0.985),
        Pos(0, 0, 3.2) * _band_profile(1.0),
        Pos(0, 0, S.CASE_MIDDLE_HEIGHT) * _band_profile(0.975),
    ]
    band = loft(sections)
    bottom_edges = [e for e in band.edges() if e.bounding_box().max.Z < 1e-4]
    band, applied = F.safe_chamfer(band, bottom_edges, 0.35)
    _BAND_CHAMFER_APPLIED = applied or 0.0
    return band


def _lug_section(y, z_top, z_bot, x_out, x_bev, z_bev):
    # bottom-outer chamfer; must stay below the facet's lower edge
    ch = min(0.6, (z_bev - z_bot) * 0.45)
    pts = (
        (LUG_HALF_GAP, z_bot),
        (x_out - 0.5, z_bot),
        (x_out, z_bot + ch),
        (x_out, z_bev),
        (x_bev, z_top),
        (LUG_HALF_GAP, z_top),
    )
    return Plane.XZ.offset(-y) * Polygon(*pts, align=None)


def _lug_ne():
    """Lug in the +X/+Y quadrant; the other three are mirrors."""
    sections = [_lug_section(*st) for st in _dense_lug_stations()]
    # smooth loft over the DENSE stations: sparse control stations overshot
    # (~2 mm bulge), but the Catmull-Rom densified set pins the interpolating
    # surface (max z stays 5.95, volume within 0.1% of ruled) while removing
    # the piecewise-planar facet bands a ruled loft leaves on the organic
    # faces.  The polygon vertex tracks stay sharp edges, so the twisted
    # polished-bevel character line keeps its crisp boundary.
    return loft(sections, ruled=False)


def _case_middle_cuts():
    cuts = []
    # movement bore, through
    cuts.append(Pos(0, 0, 3.5) * Cylinder(BORE_RADIUS, 7.6))
    # crystal / gasket seat rebate at the top
    cuts.append(
        Pos(0, 0, (SEAT_Z + 7.2) / 2)
        * Cylinder(SEAT_RADIUS, 7.2 - SEAT_Z)
    )
    # caseback boss recess at the bottom
    cuts.append(
        Pos(0, 0, (BACK_RECESS_TOP - 0.1) / 2)
        * Cylinder(BACK_RECESS_RADIUS, BACK_RECESS_TOP + 0.1)
    )
    # crown tube seat + stem channel at +X
    cuts.append(
        Pos(21.1, 0, S.CROWN_Z) * Rot(0, 90, 0) * Cylinder(1.6, 3.0)
    )
    cuts.append(
        Pos(17.0, 0, S.CROWN_Z) * Rot(0, 90, 0) * Cylinder(0.8, 6.0)
    )
    # pusher tube seat bores (drilled through the fused bosses) + pin
    # channels at the pusher angles
    for ang in S.PUSHER_ANGLES:
        cuts.append(
            Rot(0, 0, ang)
            * Pos(20.5, 0, S.PUSHER_Z)
            * Rot(0, 90, 0)
            * Cylinder(1.62, 3.8)
        )
        cuts.append(
            Rot(0, 0, ang)
            * Pos(17.15, 0, S.PUSHER_Z)
            * Rot(0, 90, 0)
            * Cylinder(1.1, 3.3)
        )
    # spring-bar holes in the lug inner faces (one long cutter per pair)
    for sy in (S.SPRING_BAR_Y, -S.SPRING_BAR_Y):
        cuts.append(
            Pos(0, sy, S.SPRING_BAR_Z)
            * Rot(0, 90, 0)
            * Cylinder(0.85, 23.0)
        )
    return cuts


def _lug_grain_tools():
    """Brushed-grain tools for the NE lug's top field: grooves along Y (the
    strap direction), seated per dense-station segment and tilted to the
    segment's own top slope so the shallow bite stays uniform down the
    descending horn (the crown-following re-seat pattern from _bracelet).
    The field stops GRAIN_FACET_MARGIN short of the twisted facet line and
    short of the tip roll-off, so the polished bevel keeps a clean boundary.
    Returns tools for ONE multi-tool subtract on the un-mirrored lug; grooves
    still buried inside the case band are re-absorbed by the fuse."""
    tools = []
    stations = _dense_lug_stations()
    x_lo = LUG_HALF_GAP + GRAIN_INNER_MARGIN
    for st1, st2 in zip(stations, stations[1:]):
        y1, zt1, xb1 = st1[0], st1[1], st1[4]
        y2, zt2, xb2 = st2[0], st2[1], st2[4]
        if y1 < 12.3 or y2 > 22.85:
            continue  # root segments are buried; the tip roll-off stays polished
        x_hi = min(xb1, xb2) - GRAIN_FACET_MARGIN
        span_x = x_hi - x_lo
        if span_x < GRAIN_PITCH or y2 - y1 < 0.2:
            continue
        # +0.30 overlap past both segment ends: abutting prisms otherwise
        # leave a ~0.1 mm unground band at every station (measured) — the
        # adjacent chord's deviation over 0.15 mm stays within the V margin
        seg_tools = F.straight_grain_cutter(
            span_x, (y2 - y1 + 0.30) / 1.15, pitch=GRAIN_PITCH,
            depth=GRAIN_DEPTH, along_x=False,
        )
        tilt = math.degrees(math.atan2(zt2 - zt1, y2 - y1))
        place = Pos((x_lo + x_hi) / 2.0, (y1 + y2) / 2.0, (zt1 + zt2) / 2.0)
        place = place * Rot(tilt, 0, 0)
        for i, tool in enumerate(seg_tools):
            off = -span_x / 2.0 + i * GRAIN_PITCH  # helper's groove offsets
            if off > span_x / 2.0 + 1e-9:
                continue  # helper over-emits past the far (facet-side) edge
            tools.append(place * tool)
    return tools


def _shoulder_grain_tools():
    """Grain (along Y) for the exposed case-top shoulder: the guard-side
    crescent of the band top face (z = 7) proud of the bezel's 21.0 radius.
    Overshoot inward lands under the bezel or in the seat-rebate air."""
    span_x = 2.4
    seg_tools = F.straight_grain_cutter(
        span_x, 16.0 / 1.15, pitch=GRAIN_PITCH, depth=GRAIN_DEPTH,
        along_x=False,
    )
    out = []
    for i, tool in enumerate(seg_tools):
        off = -span_x / 2.0 + i * GRAIN_PITCH
        if off > span_x / 2.0 + 1e-9:
            continue
        out.append(Pos(20.4, 0, S.CASE_MIDDLE_HEIGHT) * tool)
    return out


def _band_metrics_at(band, z):
    """Measured band radius and profile scale at height z, from a thin wafer
    intersection: max.Y is the round band radius (the guard bulge lies on +X),
    max.X is the guard reach = (GUARD_CENTER_X + GUARD_RADIUS) * scale."""
    wafer = band & Pos(0, 0, z) * Cylinder(24.0, 0.02)
    bb = wafer.bounding_box()
    return bb.max.Y, bb.max.X / (GUARD_CENTER_X + GUARD_RADIUS)


def _flank_ring(center_x, radius, z, start_deg, arc_deg):
    """One circumferential V-ring cutter: a 'pencil' profile (V tip backed by
    a rectangle reaching FLANK_RING_REACH into air) revolved arc_deg about
    the vertical axis through (center_x, 0), starting start_deg from +X in
    that axis's local frame. Tolerates small radius error either way: a
    slightly proud wall gets a hair-wider groove, a shy one a shallower V."""
    w = FLANK_RING_PITCH * 0.475
    r_out = center_x + radius + FLANK_RING_REACH
    profile = Plane.XZ * Polygon(
        (center_x + radius - FLANK_RING_DEPTH, z),
        (center_x + radius, z - w),
        (r_out, z - w),
        (r_out, z + w),
        (center_x + radius, z + w),
        align=None,
    )
    ring = revolve(profile, Axis((center_x, 0, 0), (0, 0, 1)),
                   revolution_arc=arc_deg)
    return Pos(center_x, 0, 0) * Rot(0, 0, start_deg) * Pos(-center_x, 0, 0) * ring


def _flank_grain_cuts(band):
    """Circumferential flank graining over the band's widest zone: stacked
    fine V-rings (FLANK_RING_PITCH / FLANK_RING_DEPTH) following the measured
    band and guard radii, clipped to the sectors that avoid the lugs and
    pushers — those transitions stay polished against the circular satin."""
    cuts = []
    n = int(round((FLANK_RING_Z_HI - FLANK_RING_Z_LO) / FLANK_RING_PITCH)) + 1
    for k in range(n):
        z = FLANK_RING_Z_LO + k * FLANK_RING_PITCH
        r_band, scale = _band_metrics_at(band, z)
        for start, arc in FLANK_SECTORS_BAND:
            cuts.append(_flank_ring(0.0, r_band, z, start, arc))
        cuts.append(_flank_ring(GUARD_CENTER_X * scale, GUARD_RADIUS * scale,
                                z, *FLANK_SECTOR_GUARD))
    return cuts


def build_case_middle():
    band = _case_band()
    lug = _lug_ne()
    lug = lug - _lug_grain_tools()      # ONE multi-tool grain subtract
    lugs = [
        lug,
        mirror(lug, about=Plane.YZ),
        mirror(lug, about=Plane.XZ),
        mirror(mirror(lug, about=Plane.YZ), about=Plane.XZ),
    ]
    bosses = [_pusher_boss(ang) for ang in S.PUSHER_ANGLES]
    body = band + (lugs + bosses)
    # two batched multi-tool subtracts: functional cuts, then the grain
    # fields.  (One combined BOP is wrong-answer territory: the crown-seat
    # bore and the flank rings overlap, and OCC leaves the bore plug plus
    # knife-edge slivers behind as extra solids — measured.)
    body = body - _case_middle_cuts()
    body = body - (_flank_grain_cuts(band) + _shoulder_grain_tools())
    body.label = "case_middle"
    body.color = STEEL_C
    return body


# ---------------------------------------------------------------------------
# Polished ribbon overlays — SEPARATE material zones over the brushed body.
#
# The case middle is ONE solid, so its twisted lug bevel facets inherit the
# body's BRUSHED material no matter how the geometry reads. Exactly like the
# movement's anglage ribbons (`_mvt_base._cap`/`_add_anglage`), thin
# skins hover POLISH_GAP off each polished facet and carry a true mirror PBR
# set inline on the part: the `case_polish:*` labels deliberately match NO
# `_materials.RULES` pattern (fnmatch-verified), so `M.apply` leaves the
# inline `cad_material` untouched.
# ---------------------------------------------------------------------------

POLISH_GAP = 0.02           # hover off the facet — no z-fighting
POLISH_THICKNESS = 0.05
POLISH_EDGE_INSET = 0.04    # stay just inside the facet's crease lines
STEEL_BRIGHT_C = Color(*S.STEEL_BRIGHT)
# Mirror-polish PBR (same channel values as _materials.ANGLAGE_MIRROR,
# restated inline: these zones must not depend on a rule-table match).
_POLISH_MATERIAL = {"roughness": 0.08, "metalness": 0.95,
                    "clearcoat": 0.3, "clearcoatRoughness": 0.05}


def _polish_part(sol, label):
    sol.label = label
    sol.color = STEEL_BRIGHT_C
    sol.cad_material = dict(_POLISH_MATERIAL)
    return sol


def _lug_polish_ribbon():
    """Thin skin lofted over the NE lug's twisted polished bevel facet: at
    each dense station the facet segment runs (x_bev, z_top) -> (x_out,
    z_bev); the section quad is that segment inset POLISH_EDGE_INSET from
    both crease lines and offset [POLISH_GAP, POLISH_GAP+POLISH_THICKNESS]
    along the facet's outward normal. Lofted ruled=False with the same
    station parameterization as `_lug_ne`, so the skin follows the same
    smooth interpolating surface (a ruled skin would drift off the smooth
    facet between stations). Root stations are buried inside the case band;
    callers clip with `- band` after mirroring so each quadrant emerges at
    its own flank (the crown-guard side covers more of the root)."""
    sections = []
    for y, z_top, z_bot, x_out, x_bev, z_bev in _dense_lug_stations():
        ux, uz = x_out - x_bev, z_bev - z_top
        n = math.hypot(ux, uz)
        ux, uz = ux / n, uz / n
        nx, nz = -uz, ux                    # outward facet normal (+x, +z)
        e = POLISH_EDGE_INSET
        # Only the OUTER band of the facet is mirror-polished — a narrow
        # highlight hugging the outer crease (a full-facet skin reads as a
        # big flat chrome slab at 3/4 camera angles; measured in review).
        t0 = 0.52
        ax0 = x_bev + t0 * (x_out - x_bev)
        az0 = z_top + t0 * (z_bev - z_top)
        quads = []
        for d in (POLISH_GAP, POLISH_GAP + POLISH_THICKNESS):
            quads.append((
                (ax0 + d * nx, az0 + d * nz),
                (x_out - e * ux + d * nx, z_bev - e * uz + d * nz),
            ))
        (a1, b1), (a2, b2) = quads
        sections.append(
            Plane.XZ.offset(-y) * Polygon(a1, b1, b2, a2, align=None)
        )
    return loft(sections, ruled=False)


def _bezel_polish_ring():
    """Polished skin over the bezel ring's outer wall (r 21.0, z 7.35-8.90)
    and its top rim chamfer ((21.0, 8.9) -> (20.85, 9.2)) — the grained top
    annulus starts at r 20.85 and stays uncovered. One revolved quad-chain:
    wall offset radially, chamfer offset along its (2,1)/sqrt(5) normal, the
    shared corner at the offset-line intersection (21+d, 8.9+0.2361d)."""
    profile = Plane.XZ * Polygon(
        (21.0200, 7.4200),      # inner wall, above the base cone corner
        (21.0200, 8.9047),      # inner wall/chamfer offset corner (d=0.02)
        (20.8813, 9.1821),      # inner chamfer end, inset off the top crease
        (20.9260, 9.2045),      # outer chamfer end (d=0.07)
        (21.0700, 8.9165),      # outer wall/chamfer offset corner
        (21.0700, 7.4200),      # outer wall, bottom
        align=None,
    )
    return revolve(profile, Axis.Z)


def _band_lower_polish():
    """Polished skin over the case band's bottom-edge chamfer (the 0.35
    `safe_chamfer` in `_case_band`): the chamfer face at height z sits at
    constant 2D offset from the z=0 plan outline, so the skin lofts between
    two offset-ring sections following the full band+guard outline. Returns
    None when the retry ladder dropped the chamfer entirely.

    Deliberately NOT clipped `- band`: measured overlap between this ring
    and the band is exactly 0 (the constant-offset model deviates < 0.01
    normal from the real chamfer face, inside the 0.02 gap), and the
    subtraction manufactures tangent-face slivers near the band/guard seam
    corners that trip the BOPAlgo self-intersection check (measured)."""
    from build123d import Kind, offset

    ch = _BAND_CHAMFER_APPLIED
    if ch < 0.1:
        return None
    k = R_BAND * (1.0 - 0.985) / 3.2        # wall lean dR/dz at the base
    z_top = ch / math.sqrt(1.0 + k * k)     # chamfer face top height
    m = k + math.sqrt(1.0 + k * k)          # chamfer face slope dr/dz
    perp = math.sqrt(1.0 + m * m)           # normal offset -> radial offset
    za, zb = 0.14 * z_top, 0.86 * z_top
    prof = _band_profile(0.985)

    def rings(z):
        faces = []
        for d in (POLISH_GAP + POLISH_THICKNESS, POLISH_GAP):
            faces.append(offset(prof, m * z + d * perp - ch, kind=Kind.ARC))
        return faces
    outer_a, inner_a = rings(za)
    outer_b, inner_b = rings(zb)
    return (
        loft([Pos(0, 0, za) * outer_a, Pos(0, 0, zb) * outer_b])
        - loft([Pos(0, 0, za) * inner_a, Pos(0, 0, zb) * inner_b])
    )


def build_case_polish_parts():
    band = _case_band()
    ribbon = _lug_polish_ribbon()
    quadrants = (
        ("ne", ribbon),
        ("nw", mirror(ribbon, about=Plane.YZ)),
        ("se", mirror(ribbon, about=Plane.XZ)),
        ("sw", mirror(mirror(ribbon, about=Plane.YZ), about=Plane.XZ)),
    )
    parts = []
    for name, rib in quadrants:
        clipped = rib - band
        sols = [s for s in clipped.solids() if s.volume > 1e-4]
        if len(sols) == 1:
            parts.append(_polish_part(sols[0], f"case_polish:lug_{name}"))
        else:   # disjoint slivers in one part trip validation (_mvt_base)
            for i, s in enumerate(sols):
                parts.append(_polish_part(s, f"case_polish:lug_{name}:{i}"))
    parts.append(_polish_part(_bezel_polish_ring(), "case_polish:bezel"))
    lower = _band_lower_polish()
    if lower is not None:
        sols = [s for s in lower.solids() if s.volume > 1e-4]
        if len(sols) == 1:
            parts.append(_polish_part(sols[0], "case_polish:band_lower"))
        else:
            for i, s in enumerate(sols):
                parts.append(_polish_part(s, f"case_polish:band_lower:{i}"))
    return parts


# ---------------------------------------------------------------------------
# Bezel: steel ring + black tachymeter insert + filled scale
# ---------------------------------------------------------------------------

_BEZEL_RING_PROFILE = (
    (20.00, 7.00),
    (21.00, 7.35),
    (21.00, 8.90),
    (20.85, 9.20),
    (20.55, 9.20),
    (20.55, 8.42),
    (19.00, 8.42),
    (19.00, 9.05),
    (18.80, 8.95),
    (18.80, 8.20),
    (19.55, 7.55),
    (19.55, 7.00),
)

_INSERT_PROFILE = (
    (19.05, 8.44),
    (20.50, 8.44),
    (20.50, 9.10),
    (20.42, 9.16),
    (19.13, 9.16),
    (19.05, 9.10),
)


def build_bezel_ring():
    ring = revolve(Plane.XZ * Polygon(*_BEZEL_RING_PROFILE, align=None), Axis.Z)
    # fine circular graining on the exposed steel top annulus (r 20.55-20.85
    # at z 9.20); the rim chamfers and walls stay polished
    snail = F.snailing_cutter(
        outer_diameter=41.66, inner_diameter=41.0,
        pitch=0.14, groove_depth=0.012,
    )
    ring = ring - Pos(0, 0, 9.20) * snail
    ring.label = "bezel_ring"
    ring.color = STEEL_C
    return ring


def build_bezel_insert():
    ins = revolve(Plane.XZ * Polygon(*_INSERT_PROFILE, align=None), Axis.Z)
    ins.label = "bezel_insert"
    ins.color = Color(*S.BEZEL_BLACK)
    return ins


TACHY_VALUES = (
    500, 400, 350, 300, 275, 250, 225, 200, 190, 180, 170, 160,
    150, 140, 130, 120, 110, 100, 95, 90, 85, 80, 75, 70, 65, 60,
)

_TACHY_FONT = "Helvetica Neue"
_NUM_R = 19.95        # numeral centerline radius
_NUM_SIZE = 0.92
_TICK_R = 19.33       # major tick center radius (inner band)
_LABEL_R = 19.90      # TACHYMETRE letter radius


def _tachy_angle(value: float) -> float:
    """Clockwise degrees from 12 o'clock for a tachymeter value."""
    return 6.0 * 3600.0 / value


def _at_angle(a_cw: float, r: float, obj):
    return Rot(0, 0, -a_cw) * Pos(0, r) * obj


def _tachy_text(txt: str, size: float):
    return Text(txt, size, font=_TACHY_FONT, align=(Align.CENTER, Align.CENTER))


def build_tachymeter_scale():
    shapes = []
    # numerals + major ticks
    for v in TACHY_VALUES:
        a = _tachy_angle(v) % 360.0
        num_a = 352.0 if v == 60 else a       # nudge 60 clear of 12
        shapes.append(_at_angle(num_a, _NUM_R, _tachy_text(str(v), _NUM_SIZE)))
        shapes.append(_at_angle(a, _TICK_R, Rectangle(0.13, 0.36)))
    # intermediate marks: unit ticks below 100, dots above
    for hi, lo in zip(TACHY_VALUES, TACHY_VALUES[1:]):
        if hi <= 100:
            for v in range(lo + 1, hi):
                shapes.append(
                    _at_angle(_tachy_angle(v) % 360.0, 19.28, Rectangle(0.09, 0.26))
                )
        else:
            mid = (hi + lo) / 2.0
            shapes.append(_at_angle(_tachy_angle(mid), _NUM_R, Circle(0.12)))
    # TACHYMETRE label arcing right of 12
    label = "TACHYMÈTRE"
    start_a, step_a = 10.5, 2.55
    for i, ch in enumerate(label):
        shapes.append(_at_angle(start_a + i * step_a, _LABEL_R, _tachy_text(ch, 0.78)))

    sk = shapes[0] + shapes[1:]
    scale = Pos(0, 0, 9.14) * extrude(sk, amount=0.07)   # 0.05 proud of insert
    scale.label = "tachymeter_scale"
    scale.color = Color(*S.BEZEL_FILL)
    return scale


# ---------------------------------------------------------------------------
# Crystal (hesalite read: steep toroidal shoulder, near-flat top)
# ---------------------------------------------------------------------------

def build_crystal():
    """Hesalite-read domed crystal as one revolved shell profile: near-flat
    top arc, tight toroidal shoulder, straight outer wall, Ø38.4 seating
    skirt, and an inner cavity clearing the dial edge and hands."""
    r_skirt = S.CRYSTAL_DIAMETER / 2.0            # 19.2
    apex = CRYSTAL_APEX_Z                          # 10.9
    # outer dome: top arc sagging `sag` over its radius, blended to the wall
    # by a tight shoulder arc tangent to vertical at (18.7, 8.9)
    sag = 0.85
    sh_minor = apex - sag - 8.9                    # shoulder arc radius
    r_top = 18.7 - sh_minor                        # top arc outer radius
    top_r = (r_top**2 + sag**2) / (2 * sag)
    sag_i = 0.6
    shi_minor = 0.75
    r_top_i = 17.9 - shi_minor
    z_shi = (apex - 0.6) - sag_i                   # inner shoulder top z
    top_r_i = (r_top_i**2 + sag_i**2) / (2 * sag_i)
    with BuildSketch(Plane.XZ) as sk:
        with BuildLine():
            # outer surface
            RadiusArc((0, apex), (r_top, apex - sag), top_r)        # dome top
            RadiusArc((r_top, apex - sag), (18.7, 8.9), sh_minor)   # shoulder
            Line((18.7, 8.9), (18.7, 8.1))                          # upper wall
            Line((18.7, 8.1), (r_skirt, 8.1))
            Line((r_skirt, 8.1), (r_skirt, 6.6))                    # skirt
            Line((r_skirt, 6.6), (18.65, 6.6))
            # inner cavity
            Line((18.65, 6.6), (18.65, 8.3))                        # dial edge
            Line((18.65, 8.3), (17.9, 8.5))
            Line((17.9, 8.5), (17.9, z_shi - shi_minor))
            RadiusArc((17.9, z_shi - shi_minor), (r_top_i, z_shi), -shi_minor)
            RadiusArc((r_top_i, z_shi), (0, apex - 0.6), -top_r_i)  # under-dome
            Line((0, apex - 0.6), (0, apex))
        make_face()
    body = revolve(sk.sketch, Axis.Z)
    body.label = "crystal"
    body.color = Color(*S.CRYSTAL)
    return body


# ---------------------------------------------------------------------------
# Display caseback
# ---------------------------------------------------------------------------

_CASEBACK_PROFILE = (
    (14.20, -S.CASEBACK_DEPTH),
    (14.20, -2.05),
    (15.35, -2.05),
    (15.35, -0.50),
    (15.00, -0.50),
    (15.00, 1.20),
    (17.95, 1.20),        # thread boss (CASEBACK_THREAD_DIAMETER ~ 36)
    (17.95, -0.02),
    (19.30, -0.02),
    (19.30, -S.CASEBACK_DEPTH),
)


def build_caseback():
    body = revolve(Plane.XZ * Polygon(*_CASEBACK_PROFILE, align=None), Axis.Z)
    # slight outer dome on the back face
    dome_r = 450.0
    body = body & Pos(0, 0, dome_r - S.CASEBACK_DEPTH) * Sphere(dome_r)

    cuts = []
    # thread relief grooves on the boss flank
    for gz in (0.35, 0.75):
        cuts.append(Pos(0, 0, gz) * Torus(17.98, 0.13))
    # fine knurl ring on the flank (grip / thread suggestion)
    knurl = Pos(19.46, 0, -1.25) * Cylinder(0.18, 1.1)
    for k in range(120):
        cuts.append(Rot(0, 0, k * 3.0) * knurl)
    # opener tool notches on the back rim (centered box cutter)
    notch = Pos(17.6 - 0.75, -1.3, -2.5) * F._box(1.5, 2.6, 0.5)
    for k in range(8):
        cuts.append(Rot(0, 0, 22.5 + k * 45.0) * notch)
    body = body - cuts
    body.label = "caseback"
    body.color = STEEL_C
    return body


def build_caseback_sapphire():
    r = S.CASEBACK_SAPPHIRE_DIAMETER / 2.0 + 0.3   # seats in the 15.35 rebate
    disk = Pos(0, 0, -1.0) * Cylinder(r, 1.0)
    disk.label = "caseback_sapphire"
    disk.color = Color(*S.SAPPHIRE)
    return disk


def build_caseback_retaining_ring():
    outer = Pos(0, 0, -1.775) * Cylinder(15.3, 0.45)
    ring = outer - Pos(0, 0, -1.775) * Cylinder(14.25, 0.6)
    ring.label = "caseback_retaining_ring"
    ring.color = STEEL_DARK_C
    return ring


def build_caseback_o_ring():
    o = Pos(0, 0, 0.25) * Torus(18.1, 0.25)
    o.label = "caseback_o_ring"
    o.color = GASKET_C
    return o


# ---------------------------------------------------------------------------
# Crown + tube
# ---------------------------------------------------------------------------

CROWN_INNER_X = 23.0     # crown inner face (1.0 mm reveal off the guard)


def build_crown():
    """Crown, stem, and retaining collar as one revolved profile (local +Z =
    outward crown axis), fluted by a polar pattern of cylinder cuts."""
    r = S.CROWN_DIAMETER / 2.0
    t = S.CROWN_THICKNESS
    sag = 0.35
    sph_r = (r**2 + sag**2) / (2 * sag)
    with BuildSketch(Plane.XZ) as sk:
        with BuildLine():
            Line((0.001, -4.4), (0.45, -4.4))          # stem
            Line((0.45, -4.4), (0.45, -1.2))
            Line((0.45, -1.2), (0.95, -1.2))           # collar
            Line((0.95, -1.2), (0.95, 0.1))
            Line((0.95, 0.1), (0.45, 0.1))
            Line((0.45, 0.1), (0.45, 1.1))
            Line((0.45, 1.1), (1.75, 1.1))             # tube recess floor
            Line((1.75, 1.1), (1.75, 0.0))
            Line((1.75, 0.0), (2.65, 0.0))             # inner face
            Line((2.65, 0.0), (r, 0.25))               # rim chamfer
            Line((r, 0.25), (r, t - sag))              # fluted band
            RadiusArc((r, t - sag), (0.001, t), -sph_r)  # domed outer face
            Line((0.001, t), (0.001, -4.4))
        make_face()
    body = revolve(sk.sketch, Axis.Z)

    flute = Pos(3.02, 0, t / 2) * Cylinder(0.42, t + 1.6)
    body = body - [Rot(0, 0, k * 15.0) * flute for k in range(24)]

    crown = Pos(CROWN_INNER_X, 0, S.CROWN_Z) * Rot(0, 90, 0) * body
    crown.label = "crown"
    crown.color = STEEL_C
    return crown


def build_crown_tube():
    tube = Cylinder(1.55, 3.1) - Cylinder(
        0.55, 3.4
    )
    tube = Pos(21.55, 0, S.CROWN_Z) * Rot(0, 90, 0) * tube
    tube.label = "crown_tube"
    tube.color = STEEL_DARK_C
    return tube


def build_crown_o_ring():
    o = Pos(20.2, 0, S.CROWN_Z) * Rot(0, 90, 0) * Torus(1.15, 0.28)
    o.label = "crown_o_ring"
    o.color = GASKET_C
    return o


# ---------------------------------------------------------------------------
# Pushers — small turned assemblies seated in machined case bosses.
# Local frame: +Z = radially outward along the pusher axis (exactly radial
# through the watch center), origin on the axis at r = _PUSHER_FLANK_R; the
# guard flank surface sits near local z 0.10.  Stack, inside out: a Ø5.2
# boss turned on the case band (merged into case_middle, ~1.2 proud of the
# flank), a slender Ø3.2 barrel with a Ø3.8 collar ring step mid-length,
# and a short Ø4.4 gently domed pump cap.  Cap apex at local z 4.50 keeps
# the total protrusion off the flank at ~4.4.  Spring and o-ring hide
# inside the tube bore.  All revolved profiles — no sphere booleans.
# ---------------------------------------------------------------------------

_PUSHER_FLANK_R = 21.0   # local origin radius on the guard flank
_BOSS_R = 2.6            # Ø5.2 machined boss
_BOSS_FACE = 1.30        # boss face -> ~1.2 proud of the flank
_TUBE_R = 1.6            # Ø3.2 slender turned barrel
_COLLAR_R = 1.9          # Ø3.8 collar ring step
_TUBE_END = 2.90         # barrel end plane
_CAP_R = 2.2             # Ø4.4 pump-pusher cap (S.PUSHER_DIAMETER is the
                         # legacy fat-cap envelope; the remodel reads 0.2
                         # under it so the cap stays slender over the boss)
_CAP_TIP = 4.50          # domed apex


def _pusher_transform(angle_deg: float):
    return Rot(0, 0, angle_deg) * Pos(_PUSHER_FLANK_R, 0, S.PUSHER_Z) * Rot(0, 90, 0)


def _pusher_boss(angle_deg: float):
    """Machined pusher boss: a turned Ø5.2 cylinder emerging from the case
    flank with a chamfered face rim, fused into case_middle; the tube seat
    bore is drilled through it afterwards with the other case cuts."""
    profile = Plane.XZ * Polygon(
        (0.001, -2.5),
        (_BOSS_R, -2.5),
        (_BOSS_R, _BOSS_FACE - 0.25),
        (_BOSS_R - 0.25, _BOSS_FACE),      # polished face chamfer
        (0.001, _BOSS_FACE),
        align=None,
    )
    return _pusher_transform(angle_deg) * revolve(profile, Axis.Z)


def _pusher_cap_local():
    """Short pump cap: skirt sliding over the barrel, flat turned band, a
    crisp step ring, and a gently domed top — one revolved profile."""
    sag = 0.44                              # dome rise over its r 2.0 land
    dome_r = (2.0**2 + sag**2) / (2 * sag)
    with BuildSketch(Plane.XZ) as sk:
        with BuildLine():
            Line((0.001, -1.6), (0.55, -1.6))      # actuation stem
            Line((0.55, -1.6), (0.55, 3.10))
            Line((0.55, 3.10), (1.70, 3.10))       # cavity ceiling
            Line((1.70, 3.10), (1.70, 2.50))       # skirt inner wall
            Line((1.70, 2.50), (2.05, 2.50))       # skirt mouth
            Line((2.05, 2.50), (_CAP_R, 2.65))     # mouth chamfer
            Line((_CAP_R, 2.65), (_CAP_R, 3.90))   # turned outer band
            Line((_CAP_R, 3.90), (2.0, 3.90))      # crisp step ring
            Line((2.0, 3.90), (2.0, 4.06))
            RadiusArc((2.0, 4.06), (0.001, _CAP_TIP), -dome_r)  # domed top
            Line((0.001, _CAP_TIP), (0.001, -1.6))
        make_face()
    return revolve(sk.sketch, Axis.Z)


def _pusher_tube_local():
    """Slender turned barrel seated through the case boss, with a chamfered
    collar ring step mid-length of the exposed run."""
    profile = Plane.XZ * Polygon(
        (1.05, -2.0),
        (_TUBE_R, -2.0),
        (_TUBE_R, 1.50),
        (_COLLAR_R, 1.62),                 # collar lower chamfer
        (_COLLAR_R, 2.00),
        (_TUBE_R, 2.12),                   # collar upper chamfer
        (_TUBE_R, _TUBE_END),
        (1.05, _TUBE_END),
        align=None,
    )
    return revolve(profile, Axis.Z)


def _pusher_spring_local():
    helix = Pos(0, 0, 0.3) * Helix(0.8, 2.4, 0.83)
    section = Plane(origin=helix @ 0, z_dir=helix % 0) * Circle(0.19)
    return sweep(section, path=helix, is_frenet=True)


def build_pusher(angle_deg: float, role: str):
    tf = _pusher_transform(angle_deg)
    cap = tf * _pusher_cap_local()
    cap.label = f"pusher_cap:{role}"
    cap.color = STEEL_C
    tube = tf * _pusher_tube_local()
    tube.label = f"pusher_tube:{role}"
    tube.color = STEEL_DARK_C
    spring = tf * _pusher_spring_local()
    spring.label = f"pusher_spring:{role}"
    spring.color = STEEL_DARK_C
    o_ring = tf * (Pos(0, 0, -1.0) * Torus(0.85, 0.22))
    o_ring.label = f"pusher_o_ring:{role}"
    o_ring.color = GASKET_C
    return [cap, tube, spring, o_ring]


# ---------------------------------------------------------------------------
# Gaskets + spring bars
# ---------------------------------------------------------------------------

def build_crystal_gasket():
    g = Pos(0, 0, 7.0) * Cylinder(19.52, 1.0) - Pos(
        0, 0, 7.0
    ) * Cylinder(19.22, 1.2)
    g.label = "crystal_gasket"
    g.color = GASKET_C
    return g


def build_spring_bar(role: str, y_sign: float):
    body = Cylinder(S.SPRING_BAR_DIAMETER / 2.0, 19.4)
    pistons = [
        Pos(0, 0, sz * 10.5) * Cylinder(0.5, 1.6)
        for sz in (1.0, -1.0)
    ]
    bar = body + pistons
    bar = Pos(0, y_sign * S.SPRING_BAR_Y, S.SPRING_BAR_Z) * Rot(0, 90, 0) * bar
    bar.label = f"spring_bar:{role}"
    bar.color = STEEL_C
    return bar


# ---------------------------------------------------------------------------
# Full cluster
# ---------------------------------------------------------------------------

def build_case_parts():
    parts = [
        build_case_middle(),
        build_bezel_ring(),
        build_bezel_insert(),
        build_tachymeter_scale(),
        build_crystal(),
        build_crystal_gasket(),
        build_caseback(),
        build_caseback_sapphire(),
        build_caseback_retaining_ring(),
        build_caseback_o_ring(),
        build_crown(),
        build_crown_tube(),
        build_crown_o_ring(),
    ]
    parts += build_pusher(S.PUSHER_ANGLES[0], "2oclock")
    parts += build_pusher(S.PUSHER_ANGLES[1], "4oclock")
    parts.append(build_spring_bar("12", 1.0))
    parts.append(build_spring_bar("6", -1.0))
    parts += build_case_polish_parts()
    return parts


__all__ = [
    "build_case_middle",
    "build_case_polish_parts",
    "build_bezel_ring",
    "build_bezel_insert",
    "build_tachymeter_scale",
    "build_crystal",
    "build_crystal_gasket",
    "build_caseback",
    "build_caseback_sapphire",
    "build_caseback_retaining_ring",
    "build_caseback_o_ring",
    "build_crown",
    "build_crown_tube",
    "build_crown_o_ring",
    "build_pusher",
    "build_spring_bar",
    "build_case_parts",
]
