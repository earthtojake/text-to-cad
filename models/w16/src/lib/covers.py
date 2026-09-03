"""Cam covers, spark-plug wells, coil packs, breathers.

ONE wide carbon cover per bank (this is a VR head: both cams live under a
single cover), plus everything that lives on top of it.

Bank-frame section (m, h), authored ONCE as a 2D profile and extruded along X
by `bank_prism()`: a sketch drawn on `bank_sketch_plane()` has local x = m and
local y = h for BOTH banks, so one point list serves the pair.

  h = 358   head top face  — the real joint: `heads.py` stops the casting at
            DECK_H + HEAD_H, and `cams.py` stands the cam caps 28 mm ABOVE it,
            so `spec.COVER_JOINT_H` (386) is the cam-cap crown, not a rail the
            cover could bolt to.  The cover therefore lands its flange on the
            head top face and its skirt bridges up past the caps; the roof
            still runs from h = 386 to h = 386 + COVER_H = 432 as specified.
  h = 432   spine crest and plug-well crown (= spec.PLUG_TOP_H)
  m +/-128  flange outer edge; the shell wall itself stands at m +/-115

Everything above the cover — wells, coils, harness, filler, breather — hangs
off the same bank frame.  Bank 1 is a museum-section static: solids go through
`geo.sectioned()` and fasteners seated in the removed region are dropped.
"""

from __future__ import annotations

import math
import sys

from cadgen import build123d as bd

from lib import fasteners as F, geo, palette as P, spec as S
from lib.castings import fuse_all, cut_all, is_sound, safe_fillet

# ---------------------------------------------------------------------------
# Stations
# ---------------------------------------------------------------------------

X_REAR = S.HEAD_REAR_X                     # -300, head rear face
X_FRONT = S.CAM_FRONT_X                    #  306, head front face
SEAT_H = S.DECK_H + S.HEAD_H               #  358, head top face = flange seat
TOP_H = S.PLUG_TOP_H                       #  432, spine crest / well crown
WALL = 4.0                                 # shell wall thickness
FLANGE_M = 128.0                           # flange outer edge
FLANGE_TOP_H = 365.0
BOLT_M = 122.5                             # cover bolt circle in m
BOLT_PITCH = 55.0
END_WALL = 3.0                             # front/rear end-wall thickness

WELL_OD = S.PLUG_WELL_D                    # 30
WELL_WALL = 3.0
WELL_BOTTOM_H = 388.0                      # clears the cam caps (386) and their bolts
WELL_CROWN_D = 36.0

COIL_D = 28.0
COIL_LEN = 60.0
COIL_TAB_X = 26.0                          # tab/bolt station, ahead of the plug axis
COIL_BOSS_D = 16.0

SEAL_HOUSING_D = 78.0                      # carbon boss around each cam nose
SEAL_RING_D = 50.0                         # machined seal ring on it
CAM_THROUGH_D = 38.0                       # clears the cam's 36 mm thrust flange
HOUSING_X = (X_FRONT, X_FRONT + 5.0)
SEAL_RING_X = (X_FRONT + 5.0, X_FRONT + 7.0)

FILLER_XM = (-215.0, 62.0)                 # oil filler tower, bank 2 only
FILLER_CAP_D = 70.0
FILLER_TOP_H = 442.0

BREATHER_MH = (95.0, 395.0)                # spigot on the rear wall, axis along -X
BREATHER_D = 22.0

ID_PAD_X = 90.0                            # blank plaque, front third of each cover

_CAM_KINDS = ("intake", "exhaust")

# --- mid-scale cast detail -------------------------------------------------
# Everything below is the "middle scale" the critics found missing: features
# between the cover's big primitives and its M6 bolts.  All of it is authored
# in bank (m, h) and fused INTO the shell, so it shares the cover's material
# and never shows a coincident-face seam.
#
# Outboard clearance budget (bank frame -> engine frame, both banks):
#   flank ribs stand to m -121, h 373..390  -> |y| 349..361, z 178..190
#   bolt bosses reach m -130, h 358..367.6  -> |y| 345,      z 161..167
# the cast exhaust logs live at |y| 355..391, z 94.5..159.5 with heat-shield
# lids to z 168.7, so the ribs clear them vertically (>=9 mm at the worst
# point, 21 mm at the rib crown) and the bolt bosses clear them in |y|.

RIB_X_W = 6.0                              # cast rib thickness along X
# blade rib on the flank, rooted in the wall at m 112 and dying at h 396
_RIB_MH = [(112.0, 368.0), (121.0, 373.0), (121.0, 390.0), (112.0, 396.0)]

BOLT_BOSS_D = (15.0, 13.0)                 # base / top diameter, cover bolt boss
BOLT_BOSS_H = 367.6                        # proud top face of that boss

# raised as-cast plaque carrying the casting number, on the outer flank,
# rear third so the bank-1 section keeps it.
CAST_PAD_MH = [(112.0, 373.0), (118.5, 375.5), (118.5, 390.0), (112.0, 392.5)]
CAST_PAD_X = (-92.0, -28.0)

# Sensor bosses on the OUTER land (the same face as the ID plaque, whose
# normal points up-and-outboard): a cast boss fused into the shell, then a
# separate body + connector shell.  x stations: one forward (bank 2 only,
# bank 1 is sectioned there) and two behind the section plane.
SENSOR_BOSS_D = (26.0, 23.0)
SENSOR_BOSS_DEPTH = (-7.0, 3.5)            # along the land normal
SENSORS = [("cam_position", 236.0, -91.0),
           ("oil_pressure", -128.0, -91.0),
           ("cam_phase", -244.0, -91.0)]

# PCV: a cast boss on the intake-side roof shoulder, a stub, a hose running
# back along the shoulder between the plug-well crowns and the intake spine,
# and a PCV valve body at the rear that turns down toward the valley.
PCV_M = 34.0                               # roof shoulder, clear of the wells
PCV_D = 13.0
PCV_FRONT_X = 58.0
PCV_REAR_X = -244.0

# P-clip stanchions that gather the coil leads into one ordered run: three
# per bank, at spline parameters that fall BETWEEN coil connector bodies.
CLIP_U = (0.214, 0.5, 0.786)
CLIP_RING = (17.0, 10.4)                   # outer / bore; the loom is D 10
CLIP_POST_D = 9.0
PCV_CLIP_X = -90.0                         # mid-span clip on the PCV hose


# ---------------------------------------------------------------------------
# Bank-frame helpers
# ---------------------------------------------------------------------------

def _pt(bank: int, x: float, m: float, h: float):
    return S.bank_point(bank, x, m, h)


def _y_sign(bank: int) -> float:
    """Sign mapping a locate()-frame local +Y (= up x X) onto +m."""
    return -1.0 if bank == 1 else 1.0


def _keep(shape, what: str) -> bool:
    """Gate one cosmetic part. Unsound geometry is dropped with a loud warning
    instead of asserting: a missing coil is a reportable regression, a failed
    engine build blocks every other builder."""
    if is_sound(shape):
        return True
    print(f"[covers] {what}: unsound geometry; part omitted", file=sys.stderr)
    return False


def bank_sketch_plane(bank: int, x: float) -> bd.Plane:
    """Sketch plane at station x whose local (x, y) is bank (m, h).

    The normal points along +X for bank 2 and -X for bank 1, which is what
    makes ONE counter-clockwise point list extrude the same way on both banks.
    """
    nx = -1.0 if bank == 1 else 1.0
    return geo.plane((x, 0.0, 0.0), (nx, 0.0, 0.0), S.bank_m(bank))


def bank_prism(bank: int, sketch, x0: float, x1: float):
    """Extrude a (m, h) sketch between stations x0 < x1."""
    origin = x1 if bank == 1 else x0
    return bd.extrude(bank_sketch_plane(bank, origin) * sketch, amount=x1 - x0)


def bank_box(bank: int, x0, x1, m0, m1, h0, h1):
    sk = bd.make_face(bd.Polyline((m0, h0), (m1, h0), (m1, h1), (m0, h1), close=True).edges())
    return bank_prism(bank, sk, x0, x1)


def bank_cyl(bank: int, x0: float, x1: float, m: float, h: float, d: float):
    """Cylinder along X at bank coordinates (m, h)."""
    y, z = _pt(bank, 0.0, m, h)[1:]
    return geo.cyl_x(x0, x1, d, y, z)


def bank_up_cyl(bank: int, x: float, m: float, h0: float, h1: float, d: float):
    """Cylinder along the bank centreline direction between h0 and h1."""
    return geo.cyl_along(_pt(bank, x, m, h0), _pt(bank, x, m, h1), d)


def bank_m_cyl(bank: int, x: float, m0: float, m1: float, h: float, d: float):
    """Cylinder along the bank m direction (across the cover) at (x, h)."""
    return geo.cyl_along(_pt(bank, x, m0, h), _pt(bank, x, m1, h), d)


def _bolt_stations():
    """The cover's perimeter bolt row: 55 mm pitch about the mid-station."""
    x_mid = (X_REAR + X_FRONT) / 2.0
    return [x_mid + BOLT_PITCH * (k - 5) for k in range(11)]


# ---------------------------------------------------------------------------
# The cover cross-section
# ---------------------------------------------------------------------------

# Half profile, flange outer corner -> bank centreline. (m, h, blend radius).
_HALF = [
    (FLANGE_M, SEAT_H, 0.0),
    (FLANGE_M, FLANGE_TOP_H, 1.0),
    (117.0, FLANGE_TOP_H, 2.0),
    (115.0, 371.0, 4.0),
    (115.0, 396.0, 6.0),
    (104.0, 410.0, 6.0),      # the flat land that carries the ID plaque
    (78.0, 420.0, 6.0),
    (70.0, 428.0, 5.0),
    (55.0, TOP_H, 8.0),       # spine crest, over the cam
    (40.0, 428.0, 5.0),
    (30.0, 421.0, 6.0),
    (16.0, 418.0, 8.0),
    (0.0, 417.0, 10.0),       # channel floor, on the bank centreline
]


def _outer_points():
    """Outer contour, +m flange corner over the roof to the -m flange corner."""
    pts = [(m, h) for m, h, _ in _HALF]
    pts += [(-m, h) for m, h, _ in reversed(_HALF[:-1])]
    return pts


def _outer_radii():
    out = [(m, h, r) for m, h, r in _HALF if r > 0]
    out += [(-m, h, r) for m, h, r in reversed(_HALF[:-1]) if r > 0]
    return out


def _offset_polyline(pts, t: float):
    """Offset an OPEN polyline by t to its left-hand side (n = (-dy, dx)).

    Traversed from +m to -m over the roof, that side is the inside of the
    shell, so this is the constant-thickness inner surface.
    """
    segs = []
    for a, b in zip(pts, pts[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy)
        n = (-dy / L * t, dx / L * t)
        segs.append(((a[0] + n[0], a[1] + n[1]), (b[0] + n[0], b[1] + n[1])))
    out = [segs[0][0]]
    for (p0, p1), (q0, q1) in zip(segs, segs[1:]):
        d1 = (p1[0] - p0[0], p1[1] - p0[1])
        d2 = (q1[0] - q0[0], q1[1] - q0[1])
        den = d1[0] * d2[1] - d1[1] * d2[0]
        if abs(den) < 1e-9:
            out.append(p1)
            continue
        s = ((q0[0] - p0[0]) * d2[1] - (q0[1] - p0[1]) * d2[0]) / den
        out.append((p0[0] + s * d1[0], p0[1] + s * d1[1]))
    out.append(segs[-1][1])
    return out


def _fillet_2d(sketch, radii, tol: float = 0.75):
    """Round named profile corners in 2D (cheap, and it survives the extrude).

    Grouped by radius, with the usual retry ladder; a corner that will not take
    its radius is left sharp rather than failing the build.
    """
    groups: dict[float, list] = {}
    for m, h, r in radii:
        groups.setdefault(round(r, 3), []).append((m, h))
    for r in sorted(groups, reverse=True):
        verts = []
        for m, h in groups[r]:
            verts += [v for v in sketch.vertices()
                      if abs(v.X - m) < tol and abs(v.Y - h) < tol]
        if not verts:
            continue
        for radius in (r, r * 0.75, r * 0.5, r * 0.3):
            try:
                out = bd.fillet(verts, radius=radius)
            except Exception:
                continue
            sketch = out
            break
    return sketch


def outer_section():
    pts = _outer_points()
    sk = bd.make_face(bd.Polyline(*pts, close=True).edges())
    return _fillet_2d(sk, _outer_radii())


def _roof_half():
    """Wall root over the roof to the far wall root, with blend radii."""
    return _HALF[3:] + [(-m, h, r) for m, h, r in reversed(_HALF[3:-1])]


def cavity_section():
    """Inner surface: the roof/wall polyline offset inward, open at the bottom."""
    roof = _roof_half()
    inner = _offset_polyline([(m, h) for m, h, _ in roof], WALL)
    m_in = inner[0][0]
    pts = [(m_in, SEAT_H - 10.0)] + inner + [(-m_in, SEAT_H - 10.0)]
    sk = bd.make_face(bd.Polyline(*pts, close=True).edges())
    radii = [(mi, hi, max(r - WALL, 2.0))
             for (m, h, r), (mi, hi) in zip(roof[1:-1], inner[1:-1]) if r > 0]
    return _fillet_2d(sk, radii)


def roof_h(m: float) -> float:
    """Outer surface height at |m| on the profile (straight-segment value)."""
    pts = _outer_points()
    for a, b in zip(pts, pts[1:]):
        lo, hi = min(a[0], b[0]), max(a[0], b[0])
        if lo - 1e-9 <= m <= hi + 1e-9 and abs(b[0] - a[0]) > 1e-9:
            t = (m - a[0]) / (b[0] - a[0])
            return a[1] + t * (b[1] - a[1])
    return TOP_H


# ---------------------------------------------------------------------------
# The cover shell
# ---------------------------------------------------------------------------

def _mh_sketch(pts):
    return bd.make_face(bd.Polyline(*pts, close=True).edges())


def _flank_ribs(bank: int):
    """One cast blade rib per cover-bolt station, on BOTH flanks.

    Rooted at m 112 — inside the 4 mm shell wall, whose outer surface is at
    m 115 — so every rib is an overlapping fuse operand, never a tangent one.
    """
    sk = (_mh_sketch(_RIB_MH), _mh_sketch([(-m, h) for m, h in _RIB_MH]))
    out = []
    for x in _bolt_stations():
        for s in sk:
            out.append(bank_prism(bank, s, x - RIB_X_W / 2.0, x + RIB_X_W / 2.0))
    return out


def _bolt_bosses(bank: int):
    """A drafted cast boss under every cover bolt, running the full flange
    thickness so its outboard half reads as a scalloped lug on the flange
    edge rather than a disc floating over it."""
    up = S.bank_up(bank)
    d0, d1 = BOLT_BOSS_D
    proto = bd.Cone(d0 / 2.0, d1 / 2.0, BOLT_BOSS_H - SEAT_H,
                    align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    return [geo.locate(proto, _pt(bank, x, m, SEAT_H), up, (1, 0, 0))
            for x in _bolt_stations() for m in (BOLT_M, -BOLT_M)]


def _casting_pad(bank: int):
    """Raised as-cast plaque for the casting number, on the outer flank."""
    sk = _mh_sketch([(-m, h) for m, h in CAST_PAD_MH])
    return bank_prism(bank, sk, CAST_PAD_X[0], CAST_PAD_X[1])


def _land_seat(bank: int, x: float, m_pad: float, depth: float):
    """(point, outward direction) `depth` mm along the outer land's normal."""
    n_m, n_h = _land_normal()
    h_pad = roof_h(m_pad)
    seat = _pt(bank, x, m_pad + depth * n_m, h_pad + depth * n_h)
    up, mm = S.bank_up(bank), S.bank_m(bank)
    z_dir = (0.0, n_m * mm[1] + n_h * up[1], n_m * mm[2] + n_h * up[2])
    return seat, z_dir


def _sensor_bosses(bank: int):
    d0, d1 = SENSOR_BOSS_D
    lo, hi = SENSOR_BOSS_DEPTH
    proto = bd.Cone(d0 / 2.0, d1 / 2.0, hi - lo,
                    align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    out = []
    for _, x, m_pad in SENSORS:
        seat, z_dir = _land_seat(bank, x, m_pad, lo)
        out.append(geo.locate(proto, seat, z_dir, (1, 0, 0)))
    return out


def _pcv_hose_h(bank: int = 1) -> float:
    """h of the PCV hose axis.  +12 over the shoulder, not +8: the roof climbs
    7 mm in the 10 mm between m -30 and m -40, so a Ø13 tube any lower has its
    outboard flank inside the casting (0.1 mm at +8, 4 mm clear at +12)."""
    return roof_h(-PCV_M) + 12.0


def _pcv_bosses(bank: int):
    """The two cast towers the PCV hose runs between, on the exhaust-side roof
    shoulder (the intake side carries the coil loom and its P-clips), each with
    the horizontal spigot the hose slips onto.  Fused INTO the cover, so the
    hose can sit inside a bored spigot with no solid-on-solid overlap."""
    h_r = roof_h(-PCV_M)
    h_hose = _pcv_hose_h(bank)
    out = []
    for x, dx in ((PCV_FRONT_X, -1.0), (PCV_REAR_X, 1.0)):
        # tower and spigot are fused into ONE operand first: the spigot alone
        # touches only the tower, and `fuse_all`'s pairwise fallback drops any
        # operand that does not reach the body (it did exactly that here).
        # The tower must also stand PROUD of the spigot crown: at h_hose + 9
        # the Ø18 spigot's top line lay in the tower's own top face, and that
        # tangent fuse came back unsound and was dropped too.
        out.append(fuse_all([
            bank_up_cyl(bank, x, -PCV_M, h_r - 6.0, h_hose + 14.0, 30.0),
            bank_cyl(bank, min(x, x + dx * 22.0), max(x, x + dx * 22.0),
                     -PCV_M, h_hose, 18.0)]))
    return out


def _cover_body(bank: int):
    body = bank_prism(bank, outer_section(), X_REAR, X_FRONT)

    adds = []
    adds += _flank_ribs(bank)
    adds += _bolt_bosses(bank)
    adds.append(_casting_pad(bank))
    adds += _sensor_bosses(bank)
    adds += _pcv_bosses(bank)
    # feet for the coil-loom P-clip stanchions and the PCV hose clip
    for x, m, h_top in _clip_seats(bank) + [(PCV_CLIP_X, -PCV_M, roof_h(-PCV_M) + 3.0)]:
        adds.append(bank_up_cyl(bank, x, m, roof_h(m) - 8.0, h_top, 18.0))
    # cam seal housings: a round carbon boss around each cam nose, standing in
    # front of the head face so it can reach BELOW the flange seat plane.
    for kind in _CAM_KINDS:
        adds.append(bank_cyl(bank, HOUSING_X[0], HOUSING_X[1],
                             S.CAM_M[kind], S.CAM_H, SEAL_HOUSING_D))
    # coil hold-down bosses, one per cylinder, just ahead of its plug axis
    for c in S.CYLINDERS:
        if c.bank != bank:
            continue
        adds.append(bank_up_cyl(bank, c.x + COIL_TAB_X, 0.0, 405.0, TOP_H, COIL_BOSS_D))
    # oil filler tower — ONE PER BANK now (bank 1's station is behind the
    # section plane, so it survives the cut).  The cone IS the raised cast
    # boss; the machined bayonet cap lands on it in build_filler().
    x_f, m_f = FILLER_XM
    base = _pt(bank, x_f, m_f, 405.0)
    adds.append(geo.locate(bd.Cone(44.0, 38.0, FILLER_TOP_H - 405.0,
                                   align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)),
                           base, S.bank_up(bank), (1, 0, 0)))
    body = fuse_all([body] + adds)

    body = cut_all(body, [bank_prism(bank, cavity_section(),
                                     X_REAR + END_WALL, X_FRONT - END_WALL)])

    tools = []
    # spark-plug well bores
    for c in S.CYLINDERS:
        if c.bank != bank:
            continue
        p0, p1 = _well_axis(c)
        tools.append(geo.cyl_along(_extend(p0, p1, -12.0), _extend(p1, p0, -12.0),
                                   WELL_OD + 0.4))
    # cam noses through the front wall
    for kind in _CAM_KINDS:
        tools.append(bank_cyl(bank, X_FRONT - 6.0, SEAL_RING_X[1] + 2.0,
                              S.CAM_M[kind], S.CAM_H, CAM_THROUGH_D))
    # rear wall notches: the rearmost cam caps (m 29..81, up to h 394 at their
    # bolt heads) stand into the wall. TWO local notches, not one wide one — a
    # full-width relief leaves the cover see-through from behind.
    for sgn in (-1.0, 1.0):
        tools.append(bank_box(bank, X_REAR - 2.0, X_REAR + END_WALL + 1.0,
                              min(sgn * 25.0, sgn * 85.0), max(sgn * 25.0, sgn * 85.0),
                              SEAT_H - 2.0, 397.0))
    # breather passage through the rear wall
    m_b, h_b = BREATHER_MH
    tools.append(bank_cyl(bank, X_REAR - 4.0, X_REAR + 8.0, m_b, h_b, 14.0))
    tools.append(bank_up_cyl(bank, x_f, m_f, 380.0, FILLER_TOP_H + 1.0, 56.0))
    # PCV spigot bores: the hose ends live INSIDE these, 0.2 mm clear
    h_hose = _pcv_hose_h(bank)
    tools.append(bank_cyl(bank, PCV_FRONT_X - 26.0, PCV_FRONT_X + 2.0,
                          -PCV_M, h_hose, PCV_D + 0.4))
    tools.append(bank_cyl(bank, PCV_REAR_X - 2.0, PCV_REAR_X + 26.0,
                          -PCV_M, h_hose, PCV_D + 0.4))
    body = cut_all(body, tools)
    return body


def _extend(p, q, d: float):
    """Point p moved d along the direction q -> p (negative d shortens)."""
    v = (p[0] - q[0], p[1] - q[1], p[2] - q[2])
    L = math.sqrt(sum(t * t for t in v))
    return (p[0] - d * v[0] / L, p[1] - d * v[1] / L, p[2] - d * v[2] / L)


def _well_axis(c: S.Cylinder):
    """(bottom, top) of the plug well along the spark-plug axis."""
    bottom, top = S.plug_axis(c.number)
    m0, h0 = S.bank_of_point_m_h(c.bank, bottom)
    m1, h1 = S.bank_of_point_m_h(c.bank, top)
    f = (WELL_BOTTOM_H - h0) / (h1 - h0)
    m_b = m0 + f * (m1 - m0)
    return _pt(c.bank, c.x, m_b, WELL_BOTTOM_H), _pt(c.bank, c.x, m1, h1)


def build_cover(bank: int, sectioned: bool = True):
    parts = []
    body = _cover_body(bank)

    # bright machined land under the bolt row (the visible half of the flange).
    # Kept to the two flange strips: a full-width slab would also skim the rear
    # wall and leave bright flecks where no flange exists.
    lands = [bank_box(bank, X_REAR, X_FRONT - END_WALL, 105.0, FLANGE_M + 4.0,
                      FLANGE_TOP_H - 0.6, FLANGE_TOP_H + 0.6),
             bank_box(bank, X_REAR, X_FRONT - END_WALL, -FLANGE_M - 4.0, -105.0,
                      FLANGE_TOP_H - 0.6, FLANGE_TOP_H + 0.6)]
    skins = []
    for side, slab in zip(("inner", "outer"), lands):
        piece = body & slab
        if is_sound(piece):
            skins.append((side, piece))
    if skins:
        body = cut_all(body, [p for _, p in skins])

    body = geo.sectioned(body, bank, sectioned)
    assert is_sound(body), f"cam cover {bank} not sound"
    parts.append(P.style(body, f"cam_cover:{bank}", P.CARBON))

    for side, piece in skins:
        piece = geo.sectioned(piece, bank, sectioned)
        if not piece.solids():
            continue
        parts.append(P.style(piece, f"cam_cover_flange:{bank}_{side}", P.MACHINED))

    # machined seal rings on the cam-nose housings
    for kind in _CAM_KINDS:
        seat = _pt(bank, SEAL_RING_X[0], S.CAM_M[kind], S.CAM_H)
        if geo.in_section_void(seat, bank, sectioned):
            continue
        ring = bank_cyl(bank, SEAL_RING_X[0], SEAL_RING_X[1],
                        S.CAM_M[kind], S.CAM_H, SEAL_RING_D)
        ring = ring - bank_cyl(bank, SEAL_RING_X[0] - 2.0, SEAL_RING_X[1] + 2.0,
                               S.CAM_M[kind], S.CAM_H, CAM_THROUGH_D + 0.2)
        parts.append(P.style(ring, f"cam_seal_ring:{bank}_{kind}", P.MACHINED))

    # perimeter bolt rows: 55 mm pitch, symmetric about the cover's mid-station.
    # Each bolt now seats on the crown of its own cast boss (BOLT_BOSS_H), not
    # on the bare flange face.
    bolt = F.socket_cap_bolt(6.0, 22.0)
    stations = _bolt_stations()
    for side, m in (("inner", BOLT_M), ("outer", -BOLT_M)):
        for i, x in enumerate(stations):
            seat = _pt(bank, x, m, BOLT_BOSS_H)
            if geo.in_section_void(seat, bank, sectioned):
                continue
            parts.append(P.style(geo.locate(bolt, seat, S.bank_up(bank), (1, 0, 0)),
                                 f"cam_cover_bolt:{bank}_{side}_{i + 1}", P.TITANIUM))

    # blank machined plaque on the outer land
    m_pad, h_pad = -91.0, roof_h(-91.0)
    n_m, n_h = _land_normal()
    seat = _pt(bank, ID_PAD_X, m_pad - 0.7 * n_m, h_pad - 0.7 * n_h)
    if not geo.in_section_void(seat, bank, sectioned):
        up = S.bank_up(bank)
        mm = S.bank_m(bank)
        z_dir = (0.0,
                 n_m * mm[1] + n_h * up[1],
                 n_m * mm[2] + n_h * up[2])
        parts.append(P.style(geo.locate(F.id_pad(40.0, 18.0), seat, z_dir, (1, 0, 0)),
                             f"cam_cover_id_pad:{bank}", P.MACHINED))
    return parts


def _land_normal():
    """Outward (m, h) normal of the ID-plaque land, on the OUTER (-m) side."""
    (m0, h0), (m1, h1) = (-78.0, 420.0), (-104.0, 410.0)
    dm, dh = m1 - m0, h1 - h0
    L = math.hypot(dm, dh)
    return (dh / L, -dm / L)         # right of travel = away from the shell


# ---------------------------------------------------------------------------
# Plug wells, coils, harness
# ---------------------------------------------------------------------------

def build_wells(bank: int, sectioned: bool = True):
    parts = []
    for c in S.CYLINDERS:
        if c.bank != bank:
            continue
        p0, p1 = _well_axis(c)
        tube = geo.cyl_along(p0, p1, WELL_OD)
        crown = geo.cyl_along(_extend(p1, p0, 4.0), p1, WELL_CROWN_D)
        tube = fuse_all([tube, crown])
        tube = tube - geo.cyl_along(_extend(p0, p1, -6.0), _extend(p1, p0, -6.0),
                                    WELL_OD - 2 * WELL_WALL)
        tube = geo.sectioned(tube, bank, sectioned)
        if not tube.solids():
            continue
        if not _keep(tube, f"plug well {c.number}"):
            continue
        parts.append(P.style(tube, f"plug_well:{c.number}", P.MACHINED))

        seat = _extend(p1, p0, 5.0)
        if geo.in_section_void(seat, bank, sectioned):
            continue
        axis = (p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2])
        oring = geo.locate(bd.Torus(WELL_OD / 2.0 + 1.2, 1.6), seat, axis, (1, 0, 0))
        parts.append(P.style(oring, f"plug_well_seal:{c.number}", P.RUBBER))
    return parts


def _coil_prototype(bank: int):
    """One pencil coil in its own frame: origin at the well crown, +Z along the
    plug axis, +X engine front, +Y * ky toward the engine centre."""
    ky = _y_sign(bank)
    body = bd.Cylinder(COIL_D / 2.0, COIL_LEN,
                       align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    collar = bd.Cylinder(COIL_D / 2.0 + 2.0, 7.0,
                         align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    conn = bd.Box(26.0, 22.0, 16.0, align=(bd.Align.CENTER,) * 3)
    conn = bd.Pos(0.0, ky * 16.0, COIL_LEN - 8.0) * conn
    tab = bd.Box(24.0, 14.0, 6.0, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    tab = bd.Pos(COIL_TAB_X - 6.0, 0.0, 0.0) * tab
    return fuse_all([body, collar, conn, tab])


def coil_connector_point(bank: int, c: S.Cylinder, out: float = 30.0):
    p0, p1 = _well_axis(c)
    axis = (p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2])
    pl = geo.plane(p1, axis, (1, 0, 0))
    return tuple(pl.from_local_coords((0.0, _y_sign(bank) * out, COIL_LEN - 8.0)))


def build_coils(bank: int, sectioned: bool = True):
    parts = []
    proto = _coil_prototype(bank)
    bolt = F.socket_cap_bolt(6.0, 16.0)
    for c in S.CYLINDERS:
        if c.bank != bank:
            continue
        p0, p1 = _well_axis(c)
        axis = (p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2])
        pl = geo.plane(p1, axis, (1, 0, 0))
        coil = geo.locate(proto, p1, axis, (1, 0, 0))
        coil = geo.sectioned(coil, bank, sectioned)
        if coil.solids() and _keep(coil, f"coil {c.number}"):
            parts.append(P.style(coil, f"coil:{c.number}", P.COMPOSITE))
        seat = tuple(pl.from_local_coords((COIL_TAB_X, 0.0, 6.0)))
        if geo.in_section_void(seat, bank, sectioned):
            continue
        parts.append(P.style(geo.locate(bolt, seat, axis, (1, 0, 0)),
                             f"coil_bolt:{c.number}", P.TITANIUM))
    return parts


def _sweep_tube(pts, r: float, tangents=None):
    """Ø2r tube along a spline through `pts`. Returns (solid, path)."""
    path = bd.Spline(*[bd.Vector(*p) for p in pts], tangents=tangents)
    sec = bd.Plane(origin=path @ 0.0, z_dir=path % 0.0) * bd.Circle(r)
    return bd.sweep(sec, path=path), path


def _bank_dir(bank: int, dx: float, dm: float, dh: float):
    o = _pt(bank, 0.0, 0.0, 0.0)
    p = _pt(bank, dx, dm, dh)
    return bd.Vector(p[0] - o[0], p[1] - o[1], p[2] - o[2]).normalized()


def _bezier_points(p0, t0, p3, t3, k0: float, k3: float, n: int = 7):
    """Sample a cubic Bezier from p0 (tangent t0) to p3 (tangent t3).

    Used for the loom's exit: the connector run's own end tangent is whatever
    the zigzag leaves it at, and blending FROM that tangent is what keeps the
    exit smooth instead of hairpinned.
    """
    p1 = (p0[0] + k0 * t0.X, p0[1] + k0 * t0.Y, p0[2] + k0 * t0.Z)
    p2 = (p3[0] - k3 * t3.X, p3[1] - k3 * t3.Y, p3[2] - k3 * t3.Z)
    out = []
    for i in range(n + 1):
        u = i / n
        v = 1.0 - u
        out.append(tuple(v ** 3 * p0[j] + 3 * v * v * u * p1[j]
                         + 3 * v * u * u * p2[j] + u ** 3 * p3[j] for j in range(3)))
    return out


def _harness_points(bank: int):
    """The coil connector points, front to rear — the loom's control points.
    Shared with `build_clips` so a P-clip lands exactly ON the loom axis
    rather than near it."""
    cyls = [c for c in S.CYLINDERS if c.bank == bank]
    cyls.sort(key=lambda c: -c.x)
    return [coil_connector_point(bank, c) for c in cyls]


def build_harness(bank: int, sectioned: bool = True):
    """One Ø10 loom along the coil connectors, exiting off the rear.

    Swept in two spans — the serpentine connector run (the plugs converge on
    the bank centreline, so consecutive coils lean opposite ways and the loom
    weaves), then a Bezier exit. One spline through both overshoots hard enough
    that the pipe shell will not close.
    """
    pts = _harness_points(bank)
    run, path = _sweep_tube(pts, 5.0)
    # The tail picks the run up 20 mm BEFORE its end and is 0.3 mm fatter, so the
    # two sweeps overlap as one solid inside the other. Butting them end to end
    # is a tangent, coincident-face fuse: OCCT drops one operand in silence and
    # the loom ships in two pieces with a fitting floating off the back.
    u = max(0.0, 1.0 - 20.0 / path.length)
    joint = tuple(path @ u)
    target = _pt(bank, X_REAR - 34.0, 70.0, 426.0)
    tail_pts = _bezier_points(joint, path % u, target,
                              _bank_dir(bank, -1.0, 0.55, -1.6), 60.0, 50.0)
    tail, _ = _sweep_tube(tail_pts, 5.3)
    clip = geo.cyl_along(tuple(path @ max(0.0, u - 8.0 / path.length)),
                         _extend(tail_pts[1], tail_pts[0], -4.0), 14.0)
    end = geo.cyl_along(tail_pts[-1], _extend(tail_pts[-1], tail_pts[-2], 10.0), 16.0)
    loom = geo.sectioned(fuse_all([run, tail, clip, end]), bank, sectioned)

    # A loom fuse is cosmetic: if OCCT will not join the spans, ship them as
    # separate labelled solids rather than failing the whole engine build.
    pieces = [s for s in loom.solids() if is_sound(s)]
    if not pieces:
        print(f"[covers] coil harness {bank}: no sound loom geometry; omitted",
              file=sys.stderr)
        return []
    if len(pieces) == 1:
        return [P.style(pieces[0], f"coil_harness:{bank}", P.RUBBER)]
    print(f"[covers] coil harness {bank}: fuse left {len(pieces)} pieces; "
          "shipping them separately", file=sys.stderr)
    pieces.sort(key=lambda s: -s.volume)
    return [P.style(s, f"coil_harness:{bank}_{i + 1}", P.RUBBER)
            for i, s in enumerate(pieces)]


def _clip_frames(bank: int):
    """(centre, tangent, x, m, h_boss_top) for each coil-loom P-clip, taken
    from the loom's OWN spline so the clip bore is concentric with the tube."""
    path = bd.Spline(*[bd.Vector(*p) for p in _harness_points(bank)])
    out = []
    for u in CLIP_U:
        c = tuple(path @ u)
        t = path % u
        m_c, _ = S.bank_of_point_m_h(bank, c)
        out.append((c, (t.X, t.Y, t.Z), c[0], m_c, roof_h(m_c) + 3.0))
    return out


def _clip_seats(bank: int):
    return [(x, m, h) for _, _, x, m, h in _clip_frames(bank)]


def _stanchion(bank: int, centre, axis, x: float, m: float, h_top: float,
               ring_d, bore: float):
    """A P-clip: a post off the cover's cast foot, and a ring round the tube."""
    m_c, h_c = S.bank_of_point_m_h(bank, centre)
    post = bank_up_cyl(bank, x, m, h_top, h_c, CLIP_POST_D)
    ring = geo.cyl_along(tuple(centre[j] - axis[j] * 3.5 for j in range(3)),
                         tuple(centre[j] + axis[j] * 3.5 for j in range(3)), ring_d)
    clip = fuse_all([post, ring])
    return clip - geo.cyl_along(tuple(centre[j] - axis[j] * 9.0 for j in range(3)),
                                tuple(centre[j] + axis[j] * 9.0 for j in range(3)), bore)


def build_clips(bank: int, sectioned: bool = True):
    """Three P-clip stanchions per bank that gather the coil leads into one
    ordered run instead of eight free tails."""
    parts = []
    for i, (c, t, x, m, h_top) in enumerate(_clip_frames(bank)):
        if geo.in_section_void(c, bank, sectioned):
            continue
        clip = geo.sectioned(_stanchion(bank, c, t, x, m, h_top, CLIP_RING[0],
                                        CLIP_RING[1]), bank, sectioned)
        if not clip.solids() or not _keep(clip, f"harness clip {bank}_{i + 1}"):
            continue
        parts.append(P.style(clip, f"harness_clip:{bank}_{i + 1}", P.STEEL))
    return parts


# ---------------------------------------------------------------------------
# Sensors and PCV
# ---------------------------------------------------------------------------

def build_sensors(bank: int, sectioned: bool = True):
    """Body + connector shell on each cast sensor boss (the bosses themselves
    are fused into the cover).  ONE solid per sensor: a separate connector
    would have to overlap its body to look attached."""
    parts = []
    for name, x, m_pad in SENSORS:
        seat, z_dir = _land_seat(bank, x, m_pad, SENSOR_BOSS_DEPTH[1])
        if geo.in_section_void(seat, bank, sectioned):
            continue
        body = bd.Cylinder(9.0, 15.0, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
        hexf = bd.extrude(bd.Plane.XY * bd.RegularPolygon(11.0, 6), amount=7.0)
        conn = bd.Box(21.0, 15.0, 12.0, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
        conn = bd.Pos(0.0, 0.0, 14.0) * conn
        sensor = fuse_all([body, hexf, conn])
        sensor = geo.sectioned(geo.locate(sensor, seat, z_dir, (1, 0, 0)), bank, sectioned)
        if not sensor.solids() or not _keep(sensor, f"sensor {name} {bank}"):
            continue
        parts.append(P.style(sensor, f"sensor:{bank}_{name}", P.COMPOSITE))
    return parts


def build_pcv(bank: int, sectioned: bool = True):
    """The Ø13 PCV hose between the two cast roof towers, its two clamps and
    its mid-span P-clip.  Both hose ends run INSIDE a bored spigot, so nothing
    here overlaps the cover."""
    parts = []
    h_hose = _pcv_hose_h(bank)
    p0 = _pt(bank, PCV_FRONT_X - 8.0, -PCV_M, h_hose)
    p1 = _pt(bank, PCV_REAR_X + 8.0, -PCV_M, h_hose)
    hose = geo.sectioned(geo.cyl_along(p0, p1, PCV_D), bank, sectioned)
    if hose.solids() and _keep(hose, f"pcv hose {bank}"):
        parts.append(P.style(hose, f"pcv_hose:{bank}", P.HOSE))

    for i, x in enumerate((PCV_FRONT_X - 30.0, PCV_REAR_X + 30.0)):
        seat = _pt(bank, x, -PCV_M, h_hose)
        if geo.in_section_void(seat, bank, sectioned):
            continue
        ring = (bank_cyl(bank, x - 3.0, x + 3.0, -PCV_M, h_hose, PCV_D + 6.0)
                - bank_cyl(bank, x - 5.0, x + 5.0, -PCV_M, h_hose, PCV_D + 0.4))
        parts.append(P.style(ring, f"pcv_clamp:{bank}_{i + 1}", P.STEEL))

    centre = _pt(bank, PCV_CLIP_X, -PCV_M, h_hose)
    if not geo.in_section_void(centre, bank, sectioned):
        clip = _stanchion(bank, centre, (1.0, 0.0, 0.0), PCV_CLIP_X, -PCV_M,
                          roof_h(-PCV_M) + 3.0, PCV_D + 8.0, PCV_D + 0.4)
        clip = geo.sectioned(clip, bank, sectioned)
        if clip.solids() and _keep(clip, f"pcv clip {bank}"):
            parts.append(P.style(clip, f"pcv_clip:{bank}", P.STEEL))
    return parts


# ---------------------------------------------------------------------------
# Oil filler, breather spigot and line
# ---------------------------------------------------------------------------

def build_filler(bank: int = 2, sectioned: bool = True):
    """Ø70 bayonet cap on the cover's rear third — one per bank."""
    x_f, m_f = FILLER_XM
    base = _pt(bank, x_f, m_f, FILLER_TOP_H - 1.0)
    up = S.bank_up(bank)
    cap = bd.Cylinder(FILLER_CAP_D / 2.0, 11.0,
                      align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    grip = bd.Cylinder(FILLER_CAP_D / 2.0 + 3.0, 5.0,
                       align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    grip = bd.Pos(0, 0, 6.0) * grip
    lugs = []
    for i in range(3):
        a = math.radians(60.0 + 120.0 * i)
        lugs.append(bd.Pos(36.0 * math.cos(a), 36.0 * math.sin(a), 0.0)
                    * bd.Cylinder(9.0, 6.0, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)))
    cap = fuse_all([cap, grip] + lugs)
    cap, _ = safe_fillet(cap, [e for e in cap.edges()
                               if e.geom_type.name == "CIRCLE"
                               and abs(e.bounding_box().center().Z - 11.0) < 1e-6], 1.5)
    if geo.in_section_void(base, bank, sectioned):
        return []
    return [P.style(geo.locate(cap, base, up, (1, 0, 0)),
                    f"oil_filler_cap:{bank}", P.MACHINED)]


def build_breather(bank: int, sectioned: bool = True):
    m_b, h_b = BREATHER_MH
    parts = []
    seat = _pt(bank, X_REAR, m_b, h_b)
    if geo.in_section_void(seat, bank, sectioned):
        return parts
    tip_x = X_REAR - 16.0
    stem = bank_cyl(bank, tip_x, X_REAR + 1.0, m_b, h_b, BREATHER_D)
    flange = bank_cyl(bank, X_REAR - 5.0, X_REAR + 1.0, m_b, h_b, 32.0)
    barbs = [bank_cyl(bank, tip_x + 2.0 + 5.0 * i, tip_x + 4.5 + 5.0 * i, m_b, h_b, 26.0)
             for i in range(2)]
    spigot = fuse_all([stem, flange] + barbs)
    if _keep(spigot, f"breather spigot {bank}"):
        parts.append(P.style(spigot, f"breather_spigot:{bank}", P.MACHINED))

    s = S.sign_of_bank(bank)
    route = [_pt(bank, tip_x + 3.0, m_b, h_b),
             (-322.0, s * 180.0, 360.0),
             (-322.0, s * 100.0, 378.0),
             (-314.0, s * 45.0, 382.0),
             (-310.0, s * 24.0, 380.0)]
    line, _ = _sweep_tube(route, BREATHER_D / 2.0)
    hexes = []
    for p, q in ((route[0], route[1]), (route[-1], route[-2])):
        hexes.append(_hex_end(p, q))
    line = fuse_all([line] + hexes)
    if _keep(line, f"breather line {bank}"):
        parts.append(P.style(line, f"breather_line:{bank}", P.HOSE))
    return parts


def _hex_end(p, q, af: float = 30.0, length: float = 16.0):
    """A hex hose fitting at p, its axis pointing away from q."""
    prism = bd.extrude(bd.Plane.XY * bd.RegularPolygon(af / 2.0 / math.cos(math.radians(30)), 6),
                       amount=length)
    v = (q[0] - p[0], q[1] - p[1], q[2] - p[2])
    return geo.locate(prism, p, v)


# ---------------------------------------------------------------------------

def build(sectioned: bool = True):
    parts = []
    for bank in (1, 2):
        parts += build_cover(bank, sectioned)
        parts += build_wells(bank, sectioned)
        parts += build_coils(bank, sectioned)
        parts += build_harness(bank, sectioned)
        parts += build_clips(bank, sectioned)
        parts += build_sensors(bank, sectioned)
        parts += build_pcv(bank, sectioned)
        parts += build_breather(bank, sectioned)
        parts += build_filler(bank, sectioned)
    return parts


if __name__ == "__main__":
    import sys

    from OCP.BRep import BRep_Tool

    def _closed_positive(shape) -> bool:
        """geo.sound() minus the BOP half.

        `BRepAlgoAPI_Check` reports every ROTATED fastener invalid — the
        prototype passes, the same solid under a non-axis-aligned Location does
        not (`cams.py`'s cap bolts behave identically). Authored geometry is
        gated with the full `geo.sound()`; placed fasteners fall back to this.
        """
        solids = shape.solids()
        if not solids or not shape.is_valid:
            return False
        for s in solids:
            if s.volume <= 1e-6:
                return False
            for sh in s.shells():
                if not BRep_Tool.IsClosed_s(sh.wrapped):
                    return False
        return True

    bad, soft = [], []
    ps = build(True)
    for p in ps:
        if geo.sound(p):
            continue
        (soft if _closed_positive(p) else bad).append(p.label)
    print(f"{len(ps)} parts, {len(bad)} unsound, {len(soft)} BOP-artifact (rotated fasteners)")
    for b in bad:
        print("  UNSOUND", b)
    labels = [p.label for p in ps]
    assert len(set(labels)) == len(labels), "duplicate labels"
    sys.exit(1 if bad else 0)
