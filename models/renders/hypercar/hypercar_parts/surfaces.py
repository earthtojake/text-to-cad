"""Master surface language for the mid-engine hypercar.

EVERY part builder must work from this module.  It is the single source of
truth for the car's proportions, its section curves and its datums, and it is
the reason panels line up: body panels are not modelled individually, they are
*cut out of one master surface*, so highlight and reflection lines run
continuously across every shutline by construction.

Frame
-----
    +X  forward (nose)          origin X = wheelbase centre
    +Y  car left                origin Y = centreline
    +Z  up                      origin Z = ground plane
Units mm.

Surface architecture
--------------------
Two lofts, exactly as a real car is surfaced:

``body_master()``    the full-width lower volume -- nose, fenders, flanks,
                     rocker, haunches, engine deck.  Its top edge carries a
                     Gaussian *ridge* term, which is what makes the front
                     fender crests stand proud of the hood valley and the rear
                     flying buttresses stand proud of the sunken engine deck.

``canopy_master()``  the greenhouse teardrop -- narrower, with tumblehome.

They are unioned into ``body_solid()``.  Panels are then split off that solid
with cutter volumes, never modelled standalone.
"""

from __future__ import annotations

import math
from bisect import bisect_left

from build123d import (
    Axis,
    Cylinder,
    Plane,
    Pos,
    Rot,
    Spline,
    loft,
    make_face,
    mirror,
)

# ---------------------------------------------------------------------------
# package / hard points
# ---------------------------------------------------------------------------

WHEELBASE = 2700.0
FRONT_AXLE_X = WHEELBASE / 2.0          # +1350
REAR_AXLE_X = -WHEELBASE / 2.0          # -1350

NOSE_X = 2300.0
TAIL_X = -2400.0
LENGTH = NOSE_X - TAIL_X                # 4700

# 285/35R21 front, 355/30R22 rear
FRONT_RIM_D = 21 * 25.4                 # 533.4
REAR_RIM_D = 22 * 25.4                  # 558.8
FRONT_TYRE_W = 285.0
REAR_TYRE_W = 355.0
FRONT_TYRE_OD = FRONT_RIM_D + 2 * 0.35 * FRONT_TYRE_W    # 732.9
REAR_TYRE_OD = REAR_RIM_D + 2 * 0.30 * REAR_TYRE_W       # 771.8
FRONT_TYRE_R = FRONT_TYRE_OD / 2.0
REAR_TYRE_R = REAR_TYRE_OD / 2.0

FRONT_TRACK = 1700.0
REAR_TRACK = 1660.0
FRONT_HUB_Y = FRONT_TRACK / 2.0         # 830
REAR_HUB_Y = REAR_TRACK / 2.0           # 810

FRONT_HUB_Z = FRONT_TYRE_R              # 366.45
REAR_HUB_Z = REAR_TYRE_R                # 385.9

HALF_WIDTH_MAX = 1025.0                 # 2050 overall
ROOF_Z = 1150.0

# wheel-arch openings (radius about the hub centre)
FRONT_ARCH_R = FRONT_TYRE_R + 26.0
REAR_ARCH_R = REAR_TYRE_R + 28.0
ARCH_INNER_Y = 560.0                    # arch cutters start outboard of this


# ---------------------------------------------------------------------------
# smooth 1-D control curves
# ---------------------------------------------------------------------------


def _catmull(xs, vs, x):
    """Catmull-Rom: C1 but, unlike a natural cubic, it does NOT overshoot.

    Overshoot matters here -- these tables have steep runs (the nose gains
    530 mm of half-width in 400 mm of length) and a natural cubic rings hard
    enough on them to produce self-intersecting sections.
    """
    if x <= xs[0]:
        return vs[0]
    if x >= xs[-1]:
        return vs[-1]
    i = max(0, min(bisect_left(xs, x) - 1, len(xs) - 2))
    x0, x1 = xs[i], xs[i + 1]
    t = (x - x0) / (x1 - x0)
    p0 = vs[i - 1] if i > 0 else vs[i]
    p1, p2 = vs[i], vs[i + 1]
    p3 = vs[i + 2] if i + 2 < len(vs) else vs[i + 1]
    m1, m2 = 0.5 * (p2 - p0), 0.5 * (p3 - p1)
    t2, t3 = t * t, t * t * t
    return (
        (2 * t3 - 3 * t2 + 1) * p1
        + (t3 - 2 * t2 + t) * m1
        + (-2 * t3 + 3 * t2) * p2
        + (t3 - t2) * m2
    )


_DENSE_N = 601
_SMOOTH_PASSES = 26


class C1:
    """A smooth, non-overshooting 1-D control curve over X.

    Built once: sample the Catmull-Rom form densely, then relax it with
    Laplacian passes (endpoints pinned).  Catmull-Rom alone leaves a curvature
    break at every control point, and those breaks show up as ripples in the
    lofted surface -- the "unintended kinks" the brief forbids.  Relaxing the
    dense samples removes the breaks without the ringing a C2 natural cubic
    would introduce on these steep tables.
    """

    def __init__(self, name, table):
        self.name = name
        xs = [p[0] for p in table]
        vs = [p[1] for p in table]
        if xs[0] > xs[-1]:
            xs, vs = xs[::-1], vs[::-1]
        self.x0, self.x1 = xs[0], xs[-1]
        span = self.x1 - self.x0
        self.step = span / (_DENSE_N - 1)
        dense = [
            _catmull(xs, vs, self.x0 + i * self.step) for i in range(_DENSE_N)
        ]
        for _ in range(_SMOOTH_PASSES):
            prev = dense[:]
            for i in range(1, _DENSE_N - 1):
                dense[i] = 0.25 * prev[i - 1] + 0.5 * prev[i] + 0.25 * prev[i + 1]
        self.dense = dense

    def __call__(self, x):
        if x <= self.x0:
            return self.dense[0]
        if x >= self.x1:
            return self.dense[-1]
        f = (x - self.x0) / self.step
        i = int(f)
        if i >= _DENSE_N - 1:
            return self.dense[-1]
        t = f - i
        return self.dense[i] * (1.0 - t) + self.dense[i + 1] * t


# -- lower body -------------------------------------------------------------

# centreline top: the hood valley up front, the beltline through the cabin,
# the sunken engine deck between the rear buttresses.
DECK_Z = C1("deck_z", [
    (2300, 372), (2150, 436), (1900, 528), (1650, 598), (1350, 638),
    (1050, 676), (800, 742), (500, 792), (200, 812),
    (-200, 828), (-600, 846), (-1000, 862), (-1350, 866),
    (-1700, 862), (-2050, 852), (-2400, 826),
])

# the crest where the top surface turns down into the flank: the fender-crest
# line up front, the wheel-arch crest at the back.  This is THE line the eye
# follows down the side of the car.
CREST_Z = C1("crest_z", [
    (2300, 392), (2150, 512), (1900, 672), (1650, 782), (1350, 818),
    (1050, 782), (800, 762), (500, 776), (200, 790),
    (-200, 810), (-600, 838), (-1000, 862), (-1350, 872),
    (-1700, 880), (-2050, 876), (-2400, 852),
])

# Gaussian ridge riding on the top edge: 0 through the nose and cabin, large
# over the rear deck where it becomes the flying buttresses.
RIDGE_H = C1("ridge_h", [
    (2300, 0), (1900, 0), (1350, 0), (800, 0), (200, 0),
    (-200, 0), (-500, 34), (-800, 104), (-1000, 146),
    (-1350, 168), (-1700, 158), (-2050, 108), (-2400, 44),
])

# where the ridge peaks, as a fraction of the crest half-width
RIDGE_POS = C1("ridge_pos", [
    (-200, 0.60), (-600, 0.64), (-1000, 0.70),
    (-1350, 0.73), (-1700, 0.74), (-2400, 0.74),
])

RIDGE_WIDTH = C1("ridge_width", [
    (-200, 0.30), (-1000, 0.26), (-2400, 0.28),
])

HALF_WIDTH = C1("half_width", [
    (2300, 232), (2150, 470), (1900, 762), (1650, 940), (1350, 1010),
    (1050, 930), (800, 866), (500, 846), (200, 844),
    (-200, 856), (-600, 924), (-1000, 1004), (-1350, 1025),
    (-1700, 1006), (-2050, 966), (-2400, 902),
])

# height at which the body is widest -- keeping this well below the crest is
# what puts tension in the flank instead of letting it go slack
MAXW_Z = C1("maxw_z", [
    (2300, 320), (2150, 372), (1900, 444), (1650, 528), (1350, 596),
    (1050, 552), (800, 528), (500, 520), (200, 522),
    (-200, 534), (-600, 592), (-1000, 656), (-1350, 692),
    (-1700, 698), (-2050, 680), (-2400, 642),
])

SILL_Y = C1("sill_y", [
    (2300, 186), (2150, 426), (1900, 656), (1650, 790), (1350, 838),
    (1050, 788), (800, 754), (500, 742), (200, 740),
    (-200, 750), (-600, 806), (-1000, 866), (-1350, 890),
    (-1700, 878), (-2050, 848), (-2400, 800),
])

SILL_Z = C1("sill_z", [
    (2300, 214), (2150, 206), (1900, 194), (1650, 182), (1350, 172),
    (1050, 160), (800, 152), (500, 150), (200, 150),
    (-200, 152), (-600, 164), (-1000, 190), (-1350, 216),
    (-1700, 248), (-2050, 298), (-2400, 358),
])

FLOOR_Z = C1("floor_z", [
    (2300, 176), (2150, 140), (1900, 114), (1650, 100), (1350, 94),
    (1050, 90), (800, 88), (500, 88), (200, 88),
    (-200, 90), (-600, 98), (-1000, 122), (-1350, 154),
    (-1700, 200), (-2050, 262), (-2400, 326),
])

FLOOR_Y = C1("floor_y", [
    (2300, 118), (2150, 322), (1900, 512), (1650, 622), (1350, 664),
    (1050, 630), (800, 606), (500, 596), (200, 594),
    (-200, 602), (-600, 646), (-1000, 700), (-1350, 726),
    (-1700, 716), (-2050, 690), (-2400, 640),
])


# -- canopy -----------------------------------------------------------------

CANOPY_X0 = 780.0
CANOPY_X1 = -1240.0

CANOPY_TOP_Z = C1("canopy_top_z", [
    (780, 790), (620, 892), (420, 1006), (180, 1098),
    (-60, 1142), (-260, 1150), (-460, 1138), (-700, 1094),
    (-950, 1024), (-1120, 962), (-1240, 916),
])

CANOPY_HW = C1("canopy_hw", [
    (780, 486), (620, 578), (420, 650), (180, 694),
    (-60, 712), (-260, 712), (-460, 698), (-700, 656),
    (-950, 588), (-1120, 512), (-1240, 448),
])

CANOPY_MAXW_Z = C1("canopy_maxw_z", [
    (780, 772), (620, 790), (420, 818), (180, 842),
    (-60, 854), (-260, 856), (-460, 852), (-700, 836),
    (-950, 810), (-1120, 786), (-1240, 770),
])

CANOPY_BASE_Z = C1("canopy_base_z", [
    (780, 700), (620, 714), (420, 736), (180, 756),
    (-60, 768), (-260, 770), (-460, 768), (-700, 754),
    (-950, 730), (-1120, 706), (-1240, 688),
])


# ---------------------------------------------------------------------------
# section construction
# ---------------------------------------------------------------------------

_TOP_SAMPLES = 7


def _top_shape(t):
    """How the top edge travels from centreline (t=0) to crest (t=1).

    Deliberately biased so most of the height change happens outboard: that
    keeps the deck flat and readable and puts the visual event at the crest.
    """
    return t * t * (3.0 - 2.0 * t) ** 1.0 * 0.35 + t ** 1.6 * 0.65


def body_section_bands(x):
    """Half-section as THREE separate spline bands.

    The bands meet at the shoulder crest and at the rocker with *free*
    tangents, so the loft puts a real tangent discontinuity there.  That is
    deliberate on two counts:

      * design -- the shoulder line and the rocker line are creases on a real
        car, not tiny-radius blends, and a crease terminates the highlight
        crisply instead of letting it wander;
      * fidelity -- a tight-radius ridge is the worst case for triangulation
        and makes the specular highlight sparkle.  A true edge tessellates
        exactly, so the highlight stays a clean line at default mesh settings.

    Returns (top_band, flank_band, under_band) as (y, z) point lists.
    """
    deck = DECK_Z(x)
    crest = CREST_Z(x)
    hw = HALF_WIDTH(x)
    mz = MAXW_Z(x)
    sy, sz = SILL_Y(x), SILL_Z(x)
    fy, fz = FLOOR_Y(x), FLOOR_Z(x)

    crest_y = 0.952 * hw
    ridge_h = RIDGE_H(x)
    ridge_pos = RIDGE_POS(x)
    ridge_w = RIDGE_WIDTH(x)

    top = []
    for i in range(_TOP_SAMPLES + 1):
        t = i / _TOP_SAMPLES
        base = deck + (crest - deck) * _top_shape(t)
        bump = 0.0
        if ridge_h > 0.01:
            bump = ridge_h * math.exp(-(((t - ridge_pos) / ridge_w) ** 2))
        top.append((crest_y * t, base + bump))

    flank = [
        (crest_y, crest[0] if isinstance(crest, tuple) else top[-1][1]),
        (hw, mz),
        (0.62 * hw + 0.38 * sy, 0.58 * mz + 0.42 * sz),
        (sy, sz),
    ]
    flank[0] = top[-1]

    under = [
        (sy, sz),
        (0.55 * sy + 0.45 * fy, fz + 0.44 * (sz - fz)),
        (fy, fz),
        (0.56 * fy, fz - 2.0),
        (0.0, fz - 3.0),
    ]
    return top, flank, under


def canopy_section_points(x):
    top = CANOPY_TOP_Z(x)
    hw = CANOPY_HW(x)
    mz = CANOPY_MAXW_Z(x)
    bz = CANOPY_BASE_Z(x)
    return [
        (0.0, top),
        (0.38 * hw, top - 0.08 * (top - mz)),
        (0.70 * hw, top - 0.32 * (top - mz)),
        (0.90 * hw, top - 0.66 * (top - mz)),
        (hw, mz),
        (0.988 * hw, bz + 0.46 * (mz - bz)),
        (0.95 * hw, bz),
        (0.55 * hw, bz - 30.0),
        (0.0, bz - 40.0),
    ]


def _mirrored_face(bands, x):
    """Close a half-section made of N spline bands into a face at station x.

    Built in local 2D (u, v) = (y, z) on Plane.XY, then mapped onto
    Plane.YZ.offset(x), which sends local (u, v) -> global (x, u, v).
    Horizontal end tangents at the centreline give G1 continuity across it, so
    the crown of the hood and the roof read as one unbroken surface.
    """
    edges = []
    last = len(bands) - 1
    for i, pts in enumerate(bands):
        tangents = None
        if i == 0:
            tangents = ((1, 0), None)
        if i == last:
            tangents = (tangents[0] if tangents else None, (-1, 0))
        if tangents and tangents[0] and tangents[1]:
            edges.append(Spline(*pts, tangents=tangents))
        elif tangents and tangents[0]:
            edges.append(Spline(*pts, tangents=(tangents[0], _dir(pts[-2], pts[-1]))))
        elif tangents and tangents[1]:
            edges.append(Spline(*pts, tangents=(_dir(pts[0], pts[1]), tangents[1])))
        else:
            edges.append(Spline(*pts))
    half = edges[0]
    for e in edges[1:]:
        half = half + e
    return Plane.YZ.offset(x) * make_face(half + mirror(half, Plane.YZ))


def _dir(a, b):
    dy, dz = b[0] - a[0], b[1] - a[1]
    n = math.hypot(dy, dz) or 1.0
    return (dy / n, dz / n)


def body_section_face(x):
    return _mirrored_face(body_section_bands(x), x)


def canopy_section_face(x):
    return _mirrored_face([canopy_section_points(x)], x)


BODY_STATIONS = [
    2300, 2240, 2150, 2020, 1860, 1680, 1500, 1350, 1180, 980,
    780, 560, 330, 100, -140, -390, -640, -890, -1130, -1350,
    -1570, -1790, -2000, -2190, -2320, -2400,
]

CANOPY_STATIONS = [
    780, 690, 590, 480, 360, 235, 110, -20, -150, -260,
    -380, -500, -620, -740, -860, -970, -1075, -1165, -1240,
]


def body_master():
    return loft([body_section_face(x) for x in BODY_STATIONS])


def canopy_master():
    return loft([canopy_section_face(x) for x in CANOPY_STATIONS])


# ---------------------------------------------------------------------------
# wheel arches
# ---------------------------------------------------------------------------


ARCH_OUTER_Y = 1400.0


def arch_cutter(x, z, radius, side):
    """Wheelhouse cutter for one corner.

    The cylinder axis runs along Y and is limited to one side of the car, so
    it opens an arch in that flank without severing the centre structure.
    """
    length = ARCH_OUTER_Y - ARCH_INNER_Y
    y_mid = side * (ARCH_INNER_Y + length / 2.0)
    cyl = Rot(-90, 0, 0) * Cylinder(radius=radius, height=length)
    return Pos(x, y_mid, z) * cyl


def arch_cutters():
    out = []
    for side in (1, -1):
        out.append(arch_cutter(FRONT_AXLE_X, FRONT_HUB_Z, FRONT_ARCH_R, side))
        out.append(arch_cutter(REAR_AXLE_X, REAR_HUB_Z, REAR_ARCH_R, side))
    return out


def wheel_centres():
    """(x, y, z, tyre_radius, tyre_width, rim_diameter) per corner."""
    return [
        (FRONT_AXLE_X, s * FRONT_HUB_Y, FRONT_HUB_Z, FRONT_TYRE_R, FRONT_TYRE_W, FRONT_RIM_D)
        for s in (1, -1)
    ] + [
        (REAR_AXLE_X, s * REAR_HUB_Y, REAR_HUB_Z, REAR_TYRE_R, REAR_TYRE_W, REAR_RIM_D)
        for s in (1, -1)
    ]

# ---------------------------------------------------------------------------
# inset (shell) variants
# ---------------------------------------------------------------------------


def _inset_band(points, d):
    """Offset a half-section band inward by ``d`` mm.

    Walking a half-section from centreline-top, outboard, and back to
    centreline-floor traverses the outline so that the interior is always at
    rotate(direction, -90) = (dz, -dy).  Offsetting the section points instead
    of offsetting the finished solid keeps the inner loft exactly parallel and
    avoids OCC's offset operator, which is fragile on freeform shells.
    """
    n = len(points)
    out = []
    for i, (y, z) in enumerate(points):
        a = points[max(i - 1, 0)]
        b = points[min(i + 1, n - 1)]
        dy, dz = b[0] - a[0], b[1] - a[1]
        m = math.hypot(dy, dz) or 1.0
        ny, nz = dz / m, -dy / m
        out.append((y + ny * d, z + nz * d))
    # Pin the two centreline points back to y=0.  The offset nudges them a
    # fraction of a millimetre negative, and once mirrored that tiny crossing
    # makes the section face invalid and the loft fails outright.
    out[0] = (0.0, out[0][1])
    out[-1] = (0.0, out[-1][1])
    return out


def body_section_face_inset(x, d):
    top, flank, under = body_section_bands(x)
    whole = top + flank[1:] + under[1:]
    inner = _inset_band(whole, d)
    nt, nf = len(top), len(flank) - 1
    return _mirrored_face(
        [inner[:nt], inner[nt - 1:nt + nf], inner[nt + nf - 1:]], x
    )


def canopy_section_face_inset(x, d):
    return _mirrored_face([_inset_band(canopy_section_points(x), d)], x)


BODY_SKIN_T = 14.0
GLASS_T = 9.0


def body_master_inner(d=BODY_SKIN_T):
    return loft([body_section_face_inset(x, d) for x in BODY_STATIONS])


def canopy_master_inner(d=GLASS_T):
    return loft([canopy_section_face_inset(x, d) for x in CANOPY_STATIONS])


def body_solid():
    """Outer master volume with the wheel arches opened."""
    solid = body_master() + canopy_master()
    for cutter in arch_cutters():
        solid -= cutter
    return solid


def body_skin():
    """The body as a thin shell -- what the panels are actually cut from.

    Panels cut from a shell read as real pressed/moulded skins in the exploded
    view, and the arch cuts expose a believable panel edge.
    """
    outer = body_master()
    inner = body_master_inner()
    shell = outer - inner
    for cutter in arch_cutters():
        shell -= cutter
    return shell


def canopy_glass_shell():
    """The greenhouse shell, trimmed to what actually stands PROUD of the body.

    The canopy loft and the body loft overlap wherever the buttresses rise and
    wherever the windscreen dips toward the cowl.  Without this trim the glass
    and the pillar structure occupy the same space as the door, the rear
    fender and the beltline -- three separate rest-pose interpenetrations.
    Subtracting the body master resolves all of them at once, and it is also
    physically what the greenhouse is: the part above the body.
    """
    return (canopy_master() - canopy_master_inner()) - body_master()



# ---------------------------------------------------------------------------
# panel regions
# ---------------------------------------------------------------------------
#
# Panels are NOT modelled individually.  Each one is the master shell
# intersected with a region volume, and the regions are separated by SHUT_GAP.
# Two consequences, both of which the brief demands:
#   * highlight and reflection lines cross every panel break exactly, because
#     neighbouring panels are literally the same surface;
#   * every shutline is a real, constant-width gap rather than a drawn line.

SHUT_GAP = 5.0
_G = SHUT_GAP / 2.0

# lengthwise shutlines
BX_FASCIA_F = 1795.0     # front fascia | hood + front fender
BX_DOOR_F = 785.0        # front clip | door
BX_DOOR_R = -435.0       # door | rear quarter
BX_FASCIA_R = -1960.0    # rear quarter | rear fascia
BX_COVER_F = -1010.0     # tonneau | engine cover
BX_COVER_R = -1800.0     # engine cover | tail deck

# crosswise shutlines
BY_HOOD = 600.0          # hood | front fender
BY_COVER = 520.0         # engine cover | rear haunch
BZ_ROCKER = 300.0        # door | rocker
BY_DOOR_IN = 250.0       # door inner edge (hidden under the canopy)
BY_ROCKER_IN = 400.0     # rocker | underbody
# extra clearance between the door's top edge and the greenhouse, so the
# door's front-top corner does not graze the windscreen early in the lift
DOOR_GLASS_CLEARANCE = 22.0
BX_DOOR_CORNER_X = 540.0   # front-top corner relief on the door
BX_DOOR_CORNER_Y = 748.0
BX_DOOR_CORNER_Z = 716.0

_BIG = 4000.0


def slab(x0, x1, y0, y1, z0, z1):
    from build123d import Box, Pos
    return Pos((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2) * Box(
        x1 - x0, y1 - y0, z1 - z0
    )


def canopy_footprint_prism(margin=0.0):
    """Plan footprint of the greenhouse, swept vertically.

    The body's top deck continues underneath the canopy.  That strip is fixed
    scuttle structure, NOT part of the door -- if the door owns it, opening the
    door drives a shelf straight up through the windscreen.  This prism is what
    separates the two.
    """
    from build123d import Plane, Polyline, Pos, extrude, make_face

    xs = [x for x in CANOPY_STATIONS]
    half = [(x, CANOPY_HW(x) + margin) for x in xs]
    pts = half + [(x, -y) for (x, y) in reversed(half)]
    face = Plane.XY * make_face(Polyline(*pts, pts[0]))
    return Pos(0, 0, -600.0) * extrude(face, amount=2600.0)


def panel_regions():
    """name -> region solid, for the LOWER body shell."""
    r = {}
    r["front_fascia"] = slab(BX_FASCIA_F + _G, _BIG, -_BIG, _BIG, -_BIG, _BIG)
    r["hood"] = slab(BX_DOOR_F + _G, BX_FASCIA_F - _G, -BY_HOOD + _G, BY_HOOD - _G, -_BIG, _BIG)
    for s, nm in ((1, "left"), (-1, "right")):
        lo, hi = (BY_HOOD + _G, _BIG) if s > 0 else (-_BIG, -BY_HOOD - _G)
        r[f"front_fender:{nm}"] = slab(BX_DOOR_F + _G, BX_FASCIA_F - _G, lo, hi, -_BIG, _BIG)
        dlo, dhi = (BY_DOOR_IN + _G, _BIG) if s > 0 else (-_BIG, -BY_DOOR_IN - _G)
        # the door is the FLANK outboard of the greenhouse; the deck under the
        # canopy belongs to the scuttle (see canopy_footprint_prism)
        r[f"door:{nm}"] = (
            slab(BX_DOOR_R + _G, BX_DOOR_F - _G, dlo, dhi, BZ_ROCKER + _G, _BIG)
            - canopy_footprint_prism(DOOR_GLASS_CLEARANCE)
            # drop the door's front-top corner away from the windscreen's
            # lower edge: without it the ledge grazes the glass through the
            # first quarter of the lift.  A beltline that dips at the A-pillar
            # is also the normal, better-looking shape for a door.
            - slab(BX_DOOR_CORNER_X, _BIG, -BX_DOOR_CORNER_Y, BX_DOOR_CORNER_Y,
                   BX_DOOR_CORNER_Z, _BIG)
        )
        rlo, rhi = (BY_ROCKER_IN + _G, _BIG) if s > 0 else (-_BIG, -BY_ROCKER_IN - _G)
        r[f"rocker:{nm}"] = slab(BX_DOOR_R + _G, BX_DOOR_F - _G, rlo, rhi, -_BIG, BZ_ROCKER - _G)
        ylo, yhi = (BY_COVER + _G, _BIG) if s > 0 else (-_BIG, -BY_COVER - _G)
        r[f"rear_fender:{nm}"] = slab(BX_FASCIA_R + _G, BX_DOOR_R - _G, ylo, yhi, -_BIG, _BIG)
    # scuttle deck: the centre strip plus everything under the canopy footprint
    r["cowl_deck"] = (
        slab(BX_DOOR_R + _G, BX_DOOR_F - _G, -_BIG, _BIG, BZ_ROCKER + _G, _BIG)
        & canopy_footprint_prism(-_G)
    )
    r["underbody"] = slab(BX_DOOR_R + _G, BX_DOOR_F - _G, -BY_ROCKER_IN + _G, BY_ROCKER_IN - _G, -_BIG, BZ_ROCKER - _G)
    r["tonneau"] = slab(BX_COVER_F + _G, BX_DOOR_R - _G, -BY_COVER + _G, BY_COVER - _G, -_BIG, _BIG)
    r["engine_cover"] = slab(BX_COVER_R + _G, BX_COVER_F - _G, -BY_COVER + _G, BY_COVER - _G, -_BIG, _BIG)
    r["tail_deck"] = slab(BX_FASCIA_R + _G, BX_COVER_R - _G, -BY_COVER + _G, BY_COVER - _G, -_BIG, _BIG)
    r["rear_fascia"] = slab(-_BIG, BX_FASCIA_R - _G, -_BIG, _BIG, -_BIG, _BIG)
    return r


# -- greenhouse / DLO graphic ----------------------------------------------
#
# The canopy shell is divided the same way: glass where the DLO is open,
# body-coloured pillars everywhere else.  Pillar width is the gap between
# these regions, so the A-pillar, roof rail and C-pillar are all exactly
# DLO_PILLAR wide by construction.

DLO_PILLAR = 46.0
_P = DLO_PILLAR / 2.0

# The DLO is defined by CURVES in plan, not axis-aligned boxes.  Box regions
# gave the greenhouse square corners and a straight header rail, which reads
# as a tinted rectangle dropped on the roof instead of a designed graphic.
# Each boundary below is a plan-view curve swept vertically, so the header
# sweeps, the backlight tapers, and the A- and C-pillars come out as curved
# bands of exactly DLO_PILLAR width.

_DLO_Z0 = 280.0
_DLO_Z1 = 1420.0

# header rail: further aft on the centreline, so the screen comes to a point
_HEADER = [(-820.0, 176.0), (-540.0, 132.0), (-260.0, 96.0), (0.0, 74.0),
           (260.0, 96.0), (540.0, 132.0), (820.0, 176.0)]

# backlight root: further forward on the centreline, mirroring the header
_BACKLIGHT = [(-820.0, -742.0), (-540.0, -560.0), (-260.0, -444.0), (0.0, -404.0),
              (260.0, -444.0), (540.0, -560.0), (820.0, -742.0)]

# roof panel in plan: a tapering teardrop, widest just behind the header
_ROOF_HALF = [(160.0, 0.0), (110.0, 250.0), (40.0, 396.0), (-90.0, 470.0),
              (-250.0, 486.0), (-410.0, 462.0), (-540.0, 404.0), (-640.0, 306.0),
              (-700.0, 170.0), (-724.0, 0.0)]


def _plan_prism(points, z0=_DLO_Z0, z1=_DLO_Z1):
    from build123d import Plane, Polyline, Pos, extrude, make_face
    face = Plane.XY * make_face(Polyline(*points, points[0]))
    return Pos(0, 0, z0) * extrude(face, amount=(z1 - z0))


def _offset_curve(curve, dx):
    return [(y, x + dx) for (y, x) in curve]


def _forward_of(curve, dx=0.0):
    """Prism covering everything forward of a plan curve."""
    pts = [(x + dx, y) for (y, x) in curve]
    return _plan_prism(pts + [(3000.0, curve[-1][0]), (3000.0, curve[0][0])])


def _aft_of(curve, dx=0.0):
    pts = [(x + dx, y) for (y, x) in curve]
    return _plan_prism(pts + [(-3000.0, curve[-1][0]), (-3000.0, curve[0][0])])


def _roof_plan_prism(shrink=0.0):
    half = [(x, y) for (x, y) in _ROOF_HALF]
    pts = half + [(x, -y) for (x, y) in reversed(half[1:-1])]
    if shrink:
        pts = [(x, y - shrink if y > 0 else (y + shrink if y < 0 else y)) for (x, y) in pts]
    return _plan_prism(pts)


def glazing_regions():
    r = {}
    r["windscreen"] = _forward_of(_HEADER, _P)
    roof_block = _roof_plan_prism()
    side_band = _aft_of(_HEADER, -_P) & _forward_of(_BACKLIGHT, _P)
    side_band = side_band - roof_block
    for s_side, nm in ((1, "left"), (-1, "right")):
        lo, hi = (0.0, 3000.0) if s_side > 0 else (-3000.0, 0.0)
        r[f"side_glass:{nm}"] = side_band & slab(-3000, 3000, lo, hi, -_BIG, _BIG)
    r["rear_screen"] = _aft_of(_BACKLIGHT, -_P)
    return r


def roof_region():
    return _roof_plan_prism()


def underfloor_prism(drop=12.0):
    """Everything below the rocker line, as one prism.

    Box regions cannot follow the sill, which sweeps from Z=214 at the nose to
    Z=358 at the tail, so the underfloor is claimed by a prism built from that
    curve and subtracted from every other panel region.  Without it the hood
    and deck panels each pick up a stray slab of floor.
    """
    from build123d import Plane, Polyline, extrude, make_face

    xs = [x for x in BODY_STATIONS]
    top = [(x, SILL_Z(x) - drop) for x in xs]
    pts = top + [(xs[-1], -600.0), (xs[0], -600.0), top[0]]
    face = Plane.XZ * make_face(Polyline(*pts))
    return extrude(face, amount=-_BIG) + extrude(face, amount=_BIG)


# -- lamp lenses ------------------------------------------------------------
#
# The lenses are cut FROM the master shell rather than modelled as separate
# blisters, so the lens surface is exactly the body surface: the reflection
# line runs off the fender and across the lamp without a step.  The lighting
# module builds the internals that sit behind them.


def headlight_lens_regions():
    """One slim blade per side, raked back off the fender crest."""
    from build123d import Plane, Polyline, Pos, Rot, extrude, make_face

    plan = [
        (2286.0, 300.0), (2210.0, 520.0), (2090.0, 700.0), (1946.0, 812.0),
        (1898.0, 742.0), (2036.0, 620.0), (2150.0, 452.0), (2236.0, 252.0),
    ]
    out = {}
    for s, nm in ((1, "left"), (-1, "right")):
        pts = [(x, s * y) for (x, y) in plan]
        face = Plane.XY * make_face(Polyline(*pts, pts[0]))
        out[f"headlight_lens:{nm}"] = Pos(0, 0, 300.0) * extrude(face, amount=460.0)
    return out


def taillight_lens_regions():
    """A single slim bar across the tail, plus a return down each haunch."""
    from build123d import Plane, Polyline, Pos, extrude, make_face

    prof = [
        (-2404.0, 712.0), (-2300.0, 726.0), (-2180.0, 730.0),
        (-2180.0, 668.0), (-2300.0, 664.0), (-2404.0, 650.0),
    ]
    face = Plane.XZ * make_face(Polyline(*prof, prof[0]))
    bar = extrude(face, amount=-1100.0) + extrude(face, amount=1100.0)
    return {"taillight_lens": bar}


def lens_regions():
    r = {}
    r.update(headlight_lens_regions())
    r.update(taillight_lens_regions())
    return r
