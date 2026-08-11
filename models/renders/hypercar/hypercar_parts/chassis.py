"""Chassis: carbon monocoque tub, front/rear subframes, crash structures.

Architecture
------------
The whole module is organised around ONE line.  A single lower spine runs
unbroken from the front crash flange, forward-to-aft along a machined box
longeron, straight into the tub's **chine** crease, out again into the rear box
longeron and dies on the rear crash flange.  Front to rear, at one height, one
continuous edge -- that is the thing the eye is meant to follow, and everything
else is subordinate to it.

The tub is a real *bathtub*: one lofted solid whose closed section runs from the
centre of the underfloor, out through the tuck-under, up the rocker flank, over
the sill crown and back down to the cockpit floor.  It is built from FOUR spline
bands, so the section carries three deliberate lines instead of one soft bulge:

``chine``     where the undercut tuck stops and the rocker flank begins.  A ~50
              degree tangent break: a genuine crease, not a large radius.  It is
              also the tub's share of the full-length spine, so its Y and Z at
              the tub end faces are exactly where the box longerons start.
``waist``     the max-width line, low on the flank.  A ~25 degree break that
              splits the flank into a rising lower plane and a tumbling-in upper
              plane, which is what puts tension in it.
``crown``     a tight 13 mm roll over the top of the sill.  Tangent-continuous
              into the flank, so it reads as a narrow bright band, not an edge.

Everything else on the section is G1, so the moulded-carbon read comes for free.

Two things fought back and are worth knowing before editing:

* ThruSections will not close this section family if a band split lands on the
  outboard edge of a raised cockpit lip, and a lip that tight ripples along X
  anyway -- the sill crown came out visibly quilted.  The opening is edged with
  a bonded rail instead, which is crisper and is how a real tub is finished.
* A varying skin inset on the end plugs barrels their surface over an 80 mm span
  and wrinkles it.  They keep a constant 3 mm inset and live entirely inside the
  tub skin; the *walls* carry the shaping instead.

The bulkhead (X~+780) and firewall (X~-780) each pair such a plug with a lofted
wall.  The firewall's top edge IS the roll hoop; the engine-bay aperture is cut
under it and it is braced by two back-stays into the rear subframe.

Subframes are NOT tube spaceframes.  The four main members are lofted box
longerons with small corner radii, because a swept circle cannot hold a line:
a box longeron carries four continuous highlight edges down its length and picks
the tub's creases up where they stop.  Round tubes are kept for the diagonal
bracing only, so the soft members read as subordinate to the sharp ones.  Nodes
are machined billets, not spheres, for the same reason.  Crash structures are
tapered carbon boxes on machined flanges -- four hard edges converging on the
tip, aimed straight down the car.
"""

from __future__ import annotations

import math

from build123d import (
    Compound,
    Cylinder,
    Plane,
    Pos,
    RectangleRounded,
    Rot,
    Spline,
    Vector,
    loft,
    make_face,
    mirror,
)

from hypercar_parts import surfaces as S
from hypercar_parts import palette as P
from hypercar_parts.context import group, style

# ---------------------------------------------------------------------------
# tub control curves -- smooth, non-overshooting, exactly like the body master
# ---------------------------------------------------------------------------

TUB_X0 = 816.0          # front face of the rocker loft
TUB_X1 = -816.0         # rear face of the rocker loft

# outer face of the rocker at the waist -- the tub's widest line
OUT_Y = S.C1("tub_out_y", [
    (920, 606), (816, 674), (700, 726), (500, 754), (250, 763),
    (100, 764), (-250, 762), (-500, 755), (-700, 734), (-816, 694),
    (-920, 632),
])

# top of the rocker -- the "high sill" line
SILL_TOP = S.C1("tub_sill_top", [
    (920, 348), (816, 404), (700, 444), (500, 466), (250, 474),
    (100, 476), (-250, 476), (-500, 472), (-700, 460), (-816, 436),
    (-920, 392),
])

# half width of the underfloor where it turns up into the tuck
BOT_Y = S.C1("tub_bot_y", [
    (920, 330), (816, 400), (700, 472), (500, 524), (250, 543),
    (100, 548), (-250, 545), (-500, 530), (-700, 494), (-816, 438),
    (-920, 376),
])

# inner (cockpit) face of the rocker at the crown
IN_Y = S.C1("tub_in_y", [
    (920, 430), (816, 480), (700, 528), (500, 556), (250, 566),
    (100, 568), (-250, 566), (-500, 559), (-700, 542), (-816, 502),
    (-920, 448),
])

FLOOR_GAP = 13.0        # clearance under the tub to the body underside
FLOOR_T = 38.0          # carbon sandwich floor thickness

# The three section lines, as fractions of the flank box (width = OUT_Y - BOT_Y,
# height = SILL_TOP - underfloor).  CHINE_H is deliberately high enough that the
# crease stands clear of the tub's own silhouette edge in side view; the tuck
# below it flattens as it approaches, which is what buys the hard tangent break.
CHINE_W = 0.74
CHINE_H = 0.240
WAIST_H = 0.620         # max-width line, low on the flank
SHOULDER_H = 0.900      # where the flank stops and the crown roll starts
TUMBLE_IN = 16.0        # how far the flank leans back in above the waist
CROWN_R = 13.0          # the sill crown roll


def _bot_z(x):
    return S.FLOOR_Z(x) + FLOOR_GAP


def _floor_top_z(x):
    return _bot_z(x) + FLOOR_T


def _dir(a, b):
    dy, dz = b[0] - a[0], b[1] - a[1]
    n = math.hypot(dy, dz) or 1.0
    return (dy / n, dz / n)


def _face(bands, x):
    """Close N spline bands into a mirrored section face at station x.

    Horizontal end tangents at the centreline keep the underfloor and the
    cockpit floor G1 across it; the band joins are left free, which is exactly
    where the creases are wanted.
    """
    edges = []
    last = len(bands) - 1
    for i, pts in enumerate(bands):
        t0 = (1.0, 0.0) if i == 0 else None
        t1 = (-1.0, 0.0) if i == last else None
        if t0 and t1:
            e = Spline(*pts, tangents=(t0, t1))
        elif t0:
            e = Spline(*pts, tangents=(t0, _dir(pts[-2], pts[-1])))
        elif t1:
            e = Spline(*pts, tangents=(_dir(pts[0], pts[1]), t1))
        else:
            e = Spline(*pts)
        edges.append(e)
    half = edges[0]
    for e in edges[1:]:
        half = half + e
    return Plane.YZ.offset(x) * make_face(half + mirror(half, Plane.YZ))


def _box(x, inset=0.0):
    """The flank box at station x: (out_y, sill_top_z, bot_y, bot_z, h, w)."""
    oy = OUT_Y(x) - inset
    stz = SILL_TOP(x) - inset
    by = BOT_Y(x) - inset
    bz = _bot_z(x) + inset
    return oy, stz, by, bz, stz - bz, oy - by


def chine_yz(x, inset=0.0):
    """The chine crease at station x.  The spine longerons start from this."""
    oy, stz, by, bz, h, w = _box(x, inset)
    return by + CHINE_W * w, bz + CHINE_H * h


def crown_yz(x, inset=0.0):
    """Outboard top corner of the sill crown -- the tub's upper line."""
    oy, stz, by, bz, h, w = _box(x, inset)
    return oy - TUMBLE_IN - CROWN_R, stz - CROWN_R


def _floor_band(x, inset=0.0):
    """Underfloor centre -> undercut tuck -> chine.  Ends AT the crease.

    The tuck turns up hard off the floor and then FLATTENS under the chine.
    That flattening is the whole trick: it lets the crease sit a fifth of the
    way up the section (so it is clear of the silhouette in side view) while
    still meeting the rising flank at a ~50 degree break.
    """
    oy, stz, by, bz, h, w = _box(x, inset)
    return [
        (0.0, bz + 4.5),                                   # gentle floor arch
        (0.55 * by, bz + 1.5),
        (0.93 * by, bz),                                   # lowest point
        (by + 0.26 * w, bz + 0.085 * h),                   # tuck turns up
        (by + 0.52 * w, bz + 0.185 * h),
        (by + 0.68 * w, bz + 0.228 * h),                   # ... and flattens
        (by + CHINE_W * w, bz + CHINE_H * h),              # CHINE crease
    ]


def _lower_flank_band(x, inset=0.0):
    """Chine -> waist.  A single taut plane, bowed very slightly proud."""
    oy, stz, by, bz, h, w = _box(x, inset)
    cy, cz = by + CHINE_W * w, bz + CHINE_H * h
    wy, wz = oy, bz + WAIST_H * h
    dy, dz = wy - cy, wz - cz
    return [
        (cy, cz),
        (cy + 0.52 * dy, cz + 0.50 * dz),
        (cy + 0.80 * dy, cz + 0.78 * dz),
        (wy, wz),                                          # WAIST crease
    ]


def _upper_flank_band(x, inset=0.0):
    """Waist -> shoulder.  Leans back in: tumblehome on the rocker."""
    oy, stz, by, bz, h, w = _box(x, inset)
    wy, wz = oy, bz + WAIST_H * h
    sy, sz = oy - TUMBLE_IN, bz + SHOULDER_H * h
    return [
        (wy, wz),
        (wy - 0.30 * TUMBLE_IN, wz + 0.45 * (sz - wz)),
        (sy, sz),
    ]


def _crown_band(x, inset=0.0):
    """Shoulder -> tight crown roll -> flat sill top.

    Tangent-continuous into the flank at the shoulder, so the roll reads as a
    narrow bright band along the top of the sill rather than a second edge.
    """
    oy, stz, by, bz, h, w = _box(x, inset)
    sy, sz = oy - TUMBLE_IN, bz + SHOULDER_H * h
    return [
        (sy, sz),
        (sy - 0.22 * CROWN_R, stz - CROWN_R),
        (sy - CROWN_R, stz - 0.24 * CROWN_R),
        (sy - 2.4 * CROWN_R, stz - 1.5),
    ]


def _flank_line(x, inset=0.0):
    """The flank polyline chine -> waist -> shoulder, for flush-mounted parts."""
    oy, stz, by, bz, h, w = _box(x, inset)
    return [
        (by + CHINE_W * w, bz + CHINE_H * h),
        (oy, bz + WAIST_H * h),
        (oy - TUMBLE_IN, bz + SHOULDER_H * h),
    ]


def _rocker_face_y(x, z):
    """Where the rocker flank sits at height z (for flush-mounted parts)."""
    b = _flank_line(x)
    for (y0, z0), (y1, z1) in zip(b, b[1:]):
        if z0 <= z <= z1:
            t = (z - z0) / (z1 - z0) if z1 != z0 else 0.0
            return y0 + t * (y1 - y0)
    return b[-1][0]


def _inner_band(x):
    """Sill top -> cockpit inner face -> cockpit floor."""
    stz = SILL_TOP(x)
    iy = IN_Y(x)
    ftz = _floor_top_z(x)
    return [
        (iy + 62.0, stz - 2.0),
        (iy + 20.0, stz - 12.0),
        (iy, stz - 46.0),                                  # cockpit inner face
        (iy - 14.0, ftz + 0.44 * (stz - ftz)),
        (iy - 30.0, ftz + 54.0),
        (iy - 78.0, ftz),                                  # fillet into floor
        (0.46 * (iy - 78.0), ftz + 1.6),
        (0.0, ftz + 3.0),
    ]


def _tub_section(x):
    """Four bands, three lines: chine, waist, crown roll.

    A raised moulded lip round the cockpit was tried here and abandoned -- a
    feature that tight makes ThruSections ripple along X, and the sill crown
    came out visibly quilted.  The opening is edged with a bonded rail instead
    (see :func:`_cockpit_rails`), which is both crisper and how a real tub is
    finished.
    """
    return _face([
        _floor_band(x),
        _lower_flank_band(x),
        _upper_flank_band(x),
        _crown_band(x) + _inner_band(x),
    ], x)


def _end_base_section(x, inset):
    """Filled tub cross-section: the structural plug at either end of the tub.

    Its outer boundary is the tub's own boundary, so the fuse adds material
    without ever changing the skin the eye sees.
    """
    oy, stz, by, bz, h, w = _box(x, inset)
    sy, sz = oy - TUMBLE_IN, bz + SHOULDER_H * h
    iy = IN_Y(x)
    top = [
        (sy, sz),
        (sy - CROWN_R, stz + 6.0),                         # domed, never flat:
        (0.62 * (iy + 40.0), stz + 18.0),                  # a flat closing run
        (0.26 * (iy + 40.0), stz + 23.0),                  # makes the spline
        (0.0, stz + 24.0),                                 # self-intersect
    ]
    return _face([
        _floor_band(x, inset),
        _lower_flank_band(x, inset),
        _upper_flank_band(x, inset) + top[1:],
    ], x)


# The end plugs keep a CONSTANT skin inset: a varying one barrelled the surface
# over an 80 mm span and the loft came out visibly wrinkled.
BASE_INSET = 3.0
BULK_BASE_X = [812.0, 774.0, 736.0]
FIRE_BASE_X = [-736.0, -774.0, -812.0]

# End walls are stacked in Z rather than lofted along X: that is the only way
# to give them RAKE.  Lofted along X they came out as sawn vertical blades in
# side view; stacked, each level can step back and narrow, so the scuttle leans
# away from the driver and the roll hoop leans over the engine.  Corner radii
# are kept SMALL -- these are machined/bonded structural walls and they have to
# read as flat panels with edges, not as pillows fused into the tub.
# (z, x centre, depth in X, half width in Y, corner radius)
BULK_WALL = [
    (300.0, 778.0, 90.0, 556.0, 13.0),
    (430.0, 775.0, 90.0, 556.0, 13.0),
    (508.0, 769.0, 87.0, 549.0, 13.0),
    (572.0, 761.0, 81.0, 531.0, 12.0),
    (622.0, 753.0, 73.0, 488.0, 11.0),
    (650.0, 747.0, 59.0, 402.0, 10.0),
    (664.0, 744.0, 34.0, 250.0, 8.0),
]

FIRE_WALL = [
    (300.0, -776.0, 92.0, 566.0, 14.0),
    (486.0, -778.0, 92.0, 566.0, 14.0),
    (622.0, -784.0, 90.0, 564.0, 14.0),
    (702.0, -790.0, 88.0, 560.0, 13.0),
    (792.0, -796.0, 86.0, 547.0, 13.0),
    (864.0, -801.0, 84.0, 500.0, 12.0),
    (910.0, -805.0, 82.0, 416.0, 12.0),
    (940.0, -807.0, 78.0, 298.0, 11.0),
    (954.0, -808.0, 67.0, 178.0, 10.0),
    (963.0, -808.0, 42.0, 84.0, 8.0),
]


def _tunnel_section(x):
    """Low central spine on the cockpit floor."""
    t = (x - TUB_X1) / (TUB_X0 - TUB_X1)          # 0 at rear, 1 at front
    thy = 190.0 - 44.0 * t
    ttz = _floor_top_z(x) + 108.0 - 28.0 * t
    base = _floor_top_z(x) - 16.0
    return _face([[
        (0.0, ttz),
        (0.50 * thy, ttz - 4.0),
        (thy - 22.0, ttz - 10.0),
        (thy - 6.0, ttz - 44.0),                           # hard tunnel edge
        (thy, ttz - 62.0),
        (thy + 8.0, base + 16.0),
        (thy + 13.0, base),
        (0.5 * (thy + 13.0), base),
        (0.0, base),
    ]], x)


TUB_STATIONS = [
    816, 790, 750, 705, 655, 600, 540, 470, 390, 300, 200,
    100, 0, -100, -200, -300, -400, -490, -570, -640, -700,
    -750, -790, -816,
]

# stations for the bonded cockpit rail that edges the opening
RAIL_STATIONS = [
    788, 720, 640, 550, 450, 340, 220, 100, -20, -140,
    -260, -380, -500, -600, -690, -755, -788,
]


def _monocoque():
    # ruled=True: the smooth ThruSections fit fails on these sections with
    # "BRep_API: command not done" even though every section is individually
    # valid and they all carry the same 6-edge topology.  With 24 dense
    # stations the ruled result is visually indistinguishable, and the tub is
    # structure rather than a show surface.
    tub = loft([_tub_section(x) for x in TUB_STATIONS], ruled=True)

    for xs in (BULK_BASE_X, FIRE_BASE_X):
        tub += loft([_end_base_section(x, BASE_INSET) for x in xs])

    tub += _block([(z, cx, 0.0, d, 2.0 * hy, r)
                   for (z, cx, d, hy, r) in BULK_WALL])

    hoop = _block([(z, cx, 0.0, d, 2.0 * hy, r)
                   for (z, cx, d, hy, r) in FIRE_WALL])
    hoop -= loft([
        Plane.YZ.offset(xx) * Pos(0.0, 686.0)
        * RectangleRounded(748.0, 274.0, 30.0)
        for xx in (-640.0, -910.0)
    ])
    tub += hoop

    tub += loft([_tunnel_section(x) for x in (770.0, 380.0, 0.0, -380.0, -770.0)])

    for side in (1, -1):                       # bulkhead access apertures
        tub -= Pos(774.0, side * 336.0, 344.0) * (
            Rot(0, 90, 0) * Cylinder(radius=94.0, height=260.0)
        )
    return tub


# ---------------------------------------------------------------------------
# small builders
# ---------------------------------------------------------------------------


def _straight(p0, p1, r):
    a, b = Vector(*p0), Vector(*p1)
    d = b - a
    return Plane(origin=(a + b) * 0.5, z_dir=d) * Cylinder(radius=r, height=d.length)


def _node(p, r):
    """A machined billet node.

    Spheres were used here and they were the single most 'melted' thing in the
    module -- a ball has no edge anywhere, so every joint bloated.  A short
    waisted billet with a 5 mm corner break reads as machined hardware and its
    edges catch light.
    """
    x, y, z = p
    return _block([
        (z - 1.20 * r, x, y, 1.50 * r, 1.50 * r, 0.16 * r),
        (z - 0.62 * r, x, y, 1.98 * r, 1.98 * r, 0.20 * r),
        (z + 0.62 * r, x, y, 1.98 * r, 1.98 * r, 0.20 * r),
        (z + 1.20 * r, x, y, 1.50 * r, 1.50 * r, 0.16 * r),
    ])


def _block(sections):
    """Machined billet: loft of rounded rects given as (z, cx, cy, lx, ly, r)."""
    return loft([
        Plane.XY.offset(z) * Pos(cx, cy) * RectangleRounded(lx, ly, rr)
        for (z, cx, cy, lx, ly, rr) in sections
    ])


def _longeron(stations, side=1):
    """A lofted box longeron: (x, cy, cz, ly, lz, r) sections.

    Four continuous edges down its length.  This is the member that carries the
    car's spine forward and aft of the tub, so it is a box, not a tube.
    """
    return loft([
        Plane.YZ.offset(x) * Pos(side * cy, cz) * RectangleRounded(ly, lz, r)
        for (x, cy, cz, ly, lz, r) in stations
    ])


def _plate_yz(x0, x1, cy, cz, ly, lz, r):
    return loft([
        Plane.YZ.offset(xx) * Pos(cy, cz) * RectangleRounded(ly, lz, r)
        for xx in (x0, x1)
    ])


def _cone(stations):
    """Tapered crash box: (x, cy, cz, w, h, r) sections.

    Small radii on purpose -- four hard edges converging on the tip, pointing
    straight down the car, so the crash structures extend the spine instead of
    capping it with a soft lump.
    """
    return loft([
        Plane.YZ.offset(x) * Pos(cy, cz) * RectangleRounded(w, h, r)
        for (x, cy, cz, w, h, r) in stations
    ])


def _beam(stations):
    """Bumper beam swept across Y: (x, y, z, lx, lz, r) sections."""
    return loft([
        Plane(origin=(x, y, z), x_dir=(1, 0, 0), z_dir=(0, 1, 0))
        * RectangleRounded(lx, lz, r)
        for (x, y, z, lx, lz, r) in stations
    ])


# ---------------------------------------------------------------------------
# front subframe
# ---------------------------------------------------------------------------

# Box longerons.  Their first station is pinned to the tub: the LOWER one puts
# its outboard-bottom edge exactly on the chine crease and the UPPER one puts
# its outboard-bottom edge exactly on the crown corner, so both tub lines walk
# straight out of the bulkhead instead of dying on it.
F_UPPER = [
    (816, 597, 440, 96, 100, 10),
    (1000, 590, 458, 96, 100, 10),
    (1200, 574, 476, 96, 100, 10),
    (1350, 540, 486, 92, 96, 10),
    (1560, 486, 470, 90, 94, 9),
    (1740, 414, 440, 86, 90, 9),
    (1888, 340, 400, 80, 84, 8),
]
F_LOWER = [
    (816, 555, 226, 96, 104, 10),
    (1000, 546, 220, 100, 108, 10),
    (1200, 530, 214, 104, 112, 11),
    (1350, 520, 224, 106, 116, 11),
    (1560, 486, 262, 100, 110, 10),
    (1740, 424, 322, 92, 100, 9),
    (1888, 356, 372, 84, 92, 8),
]

F_UP_NODES = [(1350, 540, 486), (1740, 414, 440), (1000, 592, 458)]
F_LO_NODES = [(1350, 520, 224), (1740, 424, 322), (1000, 546, 220)]


def _front_subframe():
    kids = []
    for side in (1, -1):
        tag = "left" if side > 0 else "right"
        kids.append(style(_longeron(F_UPPER, side),
                          f"front_longeron_upper:{tag}", P.ALUMINIUM_DARK))
        kids.append(style(_longeron(F_LOWER, side),
                          f"front_longeron_lower:{tag}", P.ALUMINIUM_DARK))

        kids.append(style(
            _straight((1350, side * 520, 210), (1350, side * 540, 480), 16.0),
            f"front_post_axle:{tag}", P.SUBFRAME))
        kids.append(style(
            _straight((1740, side * 424, 316), (1740, side * 414, 438), 14.0),
            f"front_post_fwd:{tag}", P.SUBFRAME))
        kids.append(style(
            _straight((1000, side * 546, 224), (1350, side * 540, 480), 14.0),
            f"front_brace_rear:{tag}", P.SUBFRAME))
        kids.append(style(
            _straight((1350, side * 520, 212), (1740, side * 414, 438), 14.0),
            f"front_brace_fwd:{tag}", P.SUBFRAME))
        kids.append(style(
            _straight((1352, side * 352, 606), (836, side * 580, 452), 15.0),
            f"front_tower_stay:{tag}", P.SUBFRAME))

        for i, p in enumerate(F_UP_NODES + F_LO_NODES):
            kids.append(style(_node((p[0], side * p[1], p[2]), 26.0),
                              f"front_node_{i}:{tag}", P.ALUMINIUM_DARK))

        # machined damper / rocker tower
        kids.append(style(_block([
            (412, 1350, side * 396, 148, 224, 13),
            (520, 1352, side * 380, 124, 182, 11),
            (614, 1354, side * 364, 94, 132, 9),
        ]), f"front_damper_tower:{tag}", P.ALUMINIUM_DARK))
        kids.append(style(
            Pos(1354, side * 364, 596) * (Rot(-90, 0, 0) * Cylinder(24.0, 194.0)),
            f"front_rocker_pin:{tag}", P.BRONZE_DARK))

        # suspension pickup rails
        kids.append(style(_block([
            (448, 1350, side * 470, 252, 76, 9),
            (512, 1350, side * 466, 226, 62, 8),
        ]), f"front_pickup_upper:{tag}", P.ALUMINIUM))
        kids.append(style(_block([
            (136, 1350, side * 478, 292, 78, 9),
            (204, 1350, side * 474, 262, 64, 8),
        ]), f"front_pickup_lower:{tag}", P.ALUMINIUM))

        # bulkhead mounting pads + bronze jewellery
        for i, (yy, zz) in enumerate(((604, 438), (555, 226))):
            kids.append(style(
                _plate_yz(812, 836, side * yy, zz, 116, 104, 8),
                f"front_mount_pad_{i}:{tag}", P.ALUMINIUM))
            kids.append(style(
                Pos(840, side * yy, zz) * (Rot(0, 90, 0) * Cylinder(17.0, 22.0)),
                f"front_mount_bolt_{i}:{tag}", P.BRONZE))

    # cross members
    kids.append(style(
        _straight((1180, -576, 476), (1180, 576, 476), 19.0),
        "front_cross_upper:centre", P.SUBFRAME))
    kids.append(style(
        _straight((1350, -520, 224), (1350, 520, 224), 19.0),
        "front_cross_lower:centre", P.SUBFRAME))
    kids.append(style(
        _straight((1190, -444, 300), (1190, 444, 300), 31.0),
        "steering_rack_body:centre", P.ALUMINIUM))
    for side in (1, -1):
        kids.append(style(
            Pos(1190, side * 300, 300) * (Rot(-90, 0, 0) * Cylinder(41.0, 62.0)),
            f"steering_rack_clamp:{'left' if side > 0 else 'right'}",
            P.ALUMINIUM_DARK))
    kids.append(style(
        _plate_yz(1878, 1904, 0, 386, 706, 150, 14),
        "front_crash_mount_plate:centre", P.ALUMINIUM_DARK))
    return kids


# ---------------------------------------------------------------------------
# rear subframe
# ---------------------------------------------------------------------------

R_UPPER = [
    (-816, 618, 468, 92, 96, 10),
    (-1000, 594, 552, 92, 96, 10),
    (-1200, 566, 616, 94, 98, 10),
    (-1400, 540, 636, 94, 98, 10),
    (-1620, 500, 620, 90, 94, 9),
    (-1820, 444, 566, 86, 90, 9),
    (-1958, 392, 514, 80, 84, 8),
]
R_LOWER = [
    (-816, 581, 249, 92, 100, 10),
    (-1000, 568, 262, 96, 106, 10),
    (-1200, 550, 286, 100, 112, 11),
    (-1400, 528, 318, 102, 116, 11),
    (-1620, 488, 372, 96, 108, 10),
    (-1820, 430, 434, 90, 98, 9),
    (-1958, 376, 482, 82, 90, 8),
]

R_UP_NODES = [(-1400, 540, 636), (-1620, 500, 620), (-1000, 594, 552)]
R_LO_NODES = [(-1400, 528, 318), (-1620, 488, 372), (-1000, 568, 262)]


def _rear_subframe():
    kids = []
    for side in (1, -1):
        tag = "left" if side > 0 else "right"
        kids.append(style(_longeron(R_UPPER, side),
                          f"rear_longeron_upper:{tag}", P.ALUMINIUM_DARK))
        kids.append(style(_longeron(R_LOWER, side),
                          f"rear_longeron_lower:{tag}", P.ALUMINIUM_DARK))

        kids.append(style(
            _straight((-1350, side * 532, 306), (-1350, side * 542, 630), 17.0),
            f"rear_post_axle:{tag}", P.SUBFRAME))
        kids.append(style(
            _straight((-1000, side * 568, 268), (-1350, side * 542, 630), 15.0),
            f"rear_brace_fwd:{tag}", P.SUBFRAME))
        kids.append(style(
            _straight((-1350, side * 532, 306), (-1820, side * 444, 562), 15.0),
            f"rear_brace_aft:{tag}", P.SUBFRAME))
        kids.append(style(
            _straight((-1620, side * 488, 366), (-1620, side * 500, 616), 14.0),
            f"rear_post_aft:{tag}", P.SUBFRAME))
        # roll-hoop back-stay
        kids.append(style(
            _straight((-808, side * 318, 886), (-1400, side * 522, 632), 16.0),
            f"hoop_back_stay:{tag}", P.SUBFRAME))

        for i, p in enumerate(R_UP_NODES + R_LO_NODES):
            kids.append(style(_node((p[0], side * p[1], p[2]), 26.0),
                              f"rear_node_{i}:{tag}", P.ALUMINIUM_DARK))

        kids.append(style(_block([
            (604, -1350, side * 392, 146, 220, 13),
            (700, -1352, side * 378, 122, 178, 11),
            (790, -1354, side * 362, 92, 130, 9),
        ]), f"rear_damper_tower:{tag}", P.ALUMINIUM_DARK))
        kids.append(style(
            Pos(-1354, side * 362, 772) * (Rot(-90, 0, 0) * Cylinder(24.0, 190.0)),
            f"rear_rocker_pin:{tag}", P.BRONZE_DARK))

        kids.append(style(_block([
            (616, -1350, side * 470, 256, 76, 9),
            (680, -1350, side * 466, 230, 62, 8),
        ]), f"rear_pickup_upper:{tag}", P.ALUMINIUM))
        kids.append(style(_block([
            (220, -1350, side * 486, 294, 78, 9),
            (288, -1350, side * 482, 264, 64, 8),
        ]), f"rear_pickup_lower:{tag}", P.ALUMINIUM))

        for i, (yy, zz) in enumerate(((618, 468), (581, 249))):
            kids.append(style(
                _plate_yz(-812, -838, side * yy, zz, 118, 106, 8),
                f"rear_mount_pad_{i}:{tag}", P.ALUMINIUM))
            kids.append(style(
                Pos(-842, side * yy, zz) * (Rot(0, 90, 0) * Cylinder(17.0, 22.0)),
                f"rear_mount_bolt_{i}:{tag}", P.BRONZE))

        # engine mounts hanging off the firewall
        for i, (yy, zz) in enumerate(((334, 470), (256, 226))):
            kids.append(style(
                _plate_yz(-816, -874, side * yy, zz, 104, 96, 8),
                f"engine_mount_pad_{i}:{tag}", P.ALUMINIUM))
            kids.append(style(
                Pos(-878, side * yy, zz) * (Rot(0, 90, 0) * Cylinder(15.0, 20.0)),
                f"engine_mount_bolt_{i}:{tag}", P.BRONZE))

    kids.append(style(
        _straight((-1150, -572, 610), (-1150, 572, 610), 20.0),
        "rear_cross_upper:centre", P.SUBFRAME))
    kids.append(style(
        _straight((-1400, -528, 318), (-1400, 528, 318), 20.0),
        "rear_cross_lower:centre", P.SUBFRAME))
    kids.append(style(
        _straight((-1820, -430, 434), (-1820, 430, 434), 24.0),
        "gearbox_cradle_beam:centre", P.ALUMINIUM))
    kids.append(style(
        _plate_yz(-1946, -1974, 0, 492, 726, 156, 16),
        "rear_crash_mount_plate:centre", P.ALUMINIUM_DARK))
    return kids


# ---------------------------------------------------------------------------
# crash structures
# ---------------------------------------------------------------------------


def _crash():
    kids = []
    for side in (1, -1):
        tag = "left" if side > 0 else "right"
        kids.append(style(_cone([
            (1880, side * 264, 392, 214, 226, 22),
            (1972, side * 250, 382, 194, 204, 19),
            (2064, side * 222, 366, 164, 172, 16),
            (2152, side * 184, 342, 124, 128, 12),
        ]), f"front_crash_cone:{tag}", P.CARBON))
        kids.append(style(
            _plate_yz(1874, 1892, side * 264, 392, 250, 262, 16),
            f"front_crash_flange:{tag}", P.ALUMINIUM_DARK))

        kids.append(style(_cone([
            (-1960, side * 282, 494, 216, 232, 23),
            (-2068, side * 262, 490, 196, 212, 20),
            (-2178, side * 232, 484, 164, 178, 16),
            (-2288, side * 196, 476, 124, 136, 12),
        ]), f"rear_crash_cone:{tag}", P.CARBON))
        kids.append(style(
            _plate_yz(-1952, -1970, side * 282, 494, 252, 268, 17),
            f"rear_crash_flange:{tag}", P.ALUMINIUM_DARK))

    kids.append(style(_beam([
        (2100, -320, 306, 82, 152, 11),
        (2146, -186, 310, 86, 160, 12),
        (2174, 0, 314, 90, 166, 13),
        (2146, 186, 310, 86, 160, 12),
        (2100, 320, 306, 82, 152, 11),
    ]), "front_bumper_beam:centre", P.ALUMINIUM_DARK))

    kids.append(style(_beam([
        (-2258, -352, 476, 84, 158, 11),
        (-2292, -198, 478, 88, 166, 12),
        (-2314, 0, 480, 92, 172, 13),
        (-2292, 198, 478, 88, 166, 12),
        (-2258, 352, 476, 84, 158, 11),
    ]), "rear_bumper_beam:centre", P.ALUMINIUM_DARK))
    return kids


# ---------------------------------------------------------------------------


def _cockpit_rails():
    """Bonded rail along each sill top: the crisp edge of the opening."""
    out = []
    for side in (1, -1):
        secs = []
        for x in RAIL_STATIONS:
            inner = IN_Y(x) + 60.0
            outer = OUT_Y(x) - 54.0
            secs.append(
                Plane.YZ.offset(x)
                * Pos(side * (inner + 0.40 * (outer - inner)),
                      SILL_TOP(x) + 1.0)
                * RectangleRounded(0.80 * (outer - inner), 22.0, 4.0)
            )
        out.append(style(loft(secs),
                         f"cockpit_rail:{'left' if side > 0 else 'right'}",
                         P.ALUMINIUM_DARK))
    return out


def _chine_strakes():
    """A slim carbon blade bonded along the tub chine.

    The tub's own chine is a real crease, but the tub is a near-black gloss and
    a crease in near-black gloss only reads where a highlight crosses it.  The
    strake gives that crease a hard, self-shadowing shelf so it holds the line
    at every camera angle, and -- more importantly -- it is the same section as
    the box longerons that continue fore and aft, so the whole spine reads as
    ONE member that passes through the tub.
    """
    xs = [812, 750, 660, 550, 420, 260, 90, -90, -260, -420,
          -550, -660, -750, -812]
    out = []
    for side in (1, -1):
        secs = []
        for x in xs:
            cy, cz = chine_yz(x)
            secs.append(
                Plane.YZ.offset(x)
                * Pos(side * (cy - 18.0), cz - 8.0)
                * RectangleRounded(54.0, 26.0, 4.0)
            )
        out.append(style(loft(secs),
                         f"chine_strake:{'left' if side > 0 else 'right'}",
                         P.CARBON))
    return out


def _tub_details():
    """Machined jewellery bonded to the tub -- stops the flank reading dead."""
    kids = list(_cockpit_rails())
    kids += _chine_strakes()
    for side in (1, -1):
        tag = "left" if side > 0 else "right"
        for i, (xx, zz) in enumerate(((540.0, 300.0), (-560.0, 308.0))):
            fy = _rocker_face_y(xx, zz)
            kids.append(style(
                Pos(xx, side * (fy - 14.0), zz)
                * (Rot(-90, 0, 0) * Cylinder(radius=44.0, height=40.0)),
                f"jacking_pad_{i}:{tag}", P.ALUMINIUM_DARK))
            kids.append(style(
                Pos(xx, side * (fy + 4.0), zz)
                * (Rot(-90, 0, 0) * Cylinder(radius=16.0, height=24.0)),
                f"jacking_boss_{i}:{tag}", P.BRONZE_DARK))
        # harness / seat-belt anchor rail on the inner rocker face
        kids.append(style(_block([
            (SILL_TOP(-260.0) - 96.0, -260.0, side * (IN_Y(-260.0) - 22.0),
             300.0, 40.0, 6.0),
            (SILL_TOP(-260.0) - 58.0, -260.0, side * (IN_Y(-260.0) - 26.0),
             276.0, 34.0, 5.0),
        ]), f"harness_anchor:{tag}", P.ALUMINIUM))
    kids.append(style(
        _plate_yz(812.0, 826.0, 0.0, 552.0, 142.0, 48.0, 5.0),
        "build_plate:centre", P.BRONZE))
    return kids


def _tub_solid():
    """One clean, watertight tub solid.

    ``tub += _block([...])`` turns the accumulator into a ShapeList, and simply
    wrapping those pieces in a compound left coincident faces between them (26
    non-manifold edges) plus two degenerate zero-volume fragments.  Drop the
    degenerate pieces first -- fusing with one of them nulls the whole result --
    then union the rest for real.
    """
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    raw = _monocoque()
    pieces = list(raw) if isinstance(raw, (list, tuple)) else [raw]

    solid_parts = []
    for piece in pieces:
        for sol in piece.solids():
            props = GProp_GProps()
            BRepGProp.VolumeProperties_s(sol.wrapped, props, False, False, True)
            if props.Mass() > 1.0:
                solid_parts.append(sol)
    if not solid_parts:
        raise RuntimeError("monocoque produced no non-degenerate solids")

    fused = solid_parts[0]
    for extra in solid_parts[1:]:
        try:
            merged = fused + extra
        except Exception:  # noqa: BLE001  -- OCC raises on a null fuse result
            continue
        # a boolean that nulls out is worse than not fusing that piece
        if merged is not None and merged.solids():
            fused = merged
    return fused


def build():
    """Return ONE labelled group Compound."""
    # `tub += _block([...])` makes the accumulator a ShapeList once a list is
    # added to it, and a raw list cannot be a compound child.  Fuse back to a
    # single shape so the tub stays ONE occurrence.
    tub = _tub_solid()
    kids = [style(tub, "monocoque_tub:centre", P.MONOCOQUE)]
    kids += _tub_details()
    kids += _front_subframe()
    kids += _rear_subframe()
    kids += _crash()
    return group("chassis", kids)
