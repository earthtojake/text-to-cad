"""1.6 l V6 turbo hybrid power unit.

Cylinder block, heads and cam covers, plenum with six trumpets, split
turbocharger (compressor front / turbine rear), MGU-H on the turbo shaft,
MGU-K low on the block, the ERS battery under the fuel cell, the exhaust
manifold, wastegate, fluid lines and ancillaries.

Everything is built directly in car coordinates. The bank frame is derived
from `spec.VEE_ANGLE_DEG` about the crankshaft centreline at `spec.CRANK_Z`,
so the whole engine follows the shared datum rather than a local frame.
"""

from __future__ import annotations

import math

from build123d import Plane, Spline, Vector, make_face

from . import lib, spec

# ==========================================================================
# ENGINE FRAME — everything hangs off the crank centreline and the vee angle
# ==========================================================================

X_FRONT = spec.ENGINE_FRONT_X  # -1980, bolts to the survival cell
X_REAR = spec.ENGINE_REAR_X  # -2880, bolts to the gearbox
CZ = spec.CRANK_Z  # 220

_HALF_VEE = math.radians(spec.VEE_ANGLE_DEG / 2.0)
SB = math.sin(_HALF_VEE)
CB = math.cos(_HALF_VEE)

# cylinder stations and main-bearing webs
CYL_X = (-2280.0, -2400.0, -2520.0)
WEB_X = (-2220.0, -2340.0, -2460.0, -2580.0, -2686.0, -2790.0)
HEAD_X0, HEAD_X1 = -2215.0, -2585.0

# bank stack: distance along the bank axis from the crank centreline
D_DECK = 185.0
D_HEAD = 262.0
D_COVER0 = 266.0
D_COVER1 = 326.0

SHAFT_Z = 530.0  # turbo / MGU-H shaft centreline
COMP_X = -2166.0
TURB_X = -2848.0
R_COMP = 46.0
R_TURB = 46.0

PLENUM_X0, PLENUM_X1 = -2235.0, -2570.0
PLENUM_Z0, PLENUM_Z1 = 566.0, 688.0

BAT_X0, BAT_X1 = -1600.0, -1950.0
BAT_Z0, BAT_Z1 = 132.0, 258.0
BAT_HW = 252.0


def _bank(d: float, v: float, side: float = 1.0):
    """(y, z) at distance `d` up a bank axis and `v` across it.

    +v is outboard/down on the left bank, so the head's outer face (where the
    exhaust leaves) is at +v and its inner face (the vee, where the trumpets
    drop in) is at -v.
    """
    return (side * (SB * d + CB * v), CZ + CB * d - SB * v)


# ==========================================================================
# local geometry helpers built on the lib vocabulary
# ==========================================================================


def _circle_pts(r: float, n: int = 26):
    return [(r * math.cos(2 * math.pi * i / n), r * math.sin(2 * math.pi * i / n))
            for i in range(n)]


def _frames(points, up=(0.0, 0.0, 1.0)):
    """Rotation-minimising planes along a centreline (local +y hugs `up`)."""
    pts = [Vector(*p) for p in points]
    n = len(pts)
    tans = []
    for i in range(n):
        if i == 0:
            t = pts[1] - pts[0]
        elif i == n - 1:
            t = pts[-1] - pts[-2]
        else:
            t = pts[i + 1] - pts[i - 1]
        tans.append(t.normalized())
    ref = Vector(*up)
    if abs(ref.dot(tans[0])) > 0.95:
        ref = Vector(1, 0, 0)
    planes = []
    for p, t in zip(pts, tans):
        r = ref - t * ref.dot(t)
        if r.length < 1e-6:
            r = Vector(1, 0, 0) - t * t.X
        r = r.normalized()
        planes.append(Plane(origin=p, x_dir=r.cross(t).normalized(), z_dir=t))
        ref = r
    return planes


def _catmull(points, radii, step: float = 9.0):
    """Resample a control polyline into a dense smooth centreline.

    Lofting a pipe through widely spaced sections lets the smooth loft bulge
    well outside the sections it was given, which is how a tidy manifold turns
    into a bag of balloons. Densifying first and lofting RULED keeps the
    surface bounded by its own stations and still reads smooth.
    """
    P = [Vector(*p) for p in points]
    R = [float(r) for r in radii]
    ext = [P[0] + (P[0] - P[1])] + P + [P[-1] + (P[-1] - P[-2])]
    op, orr = [], []
    for i in range(len(P) - 1):
        p0, p1, p2, p3 = ext[i], ext[i + 1], ext[i + 2], ext[i + 3]
        r1, r2 = R[i], R[i + 1]
        n = max(2, int((p2 - p1).length / step))
        for j in range(n):
            t = j / n
            t2, t3 = t * t, t * t * t
            q = (p1 * 2.0 + (p2 - p0) * t
                 + (p0 * 2.0 - p1 * 5.0 + p2 * 4.0 - p3) * t2
                 + (p1 * 3.0 - p0 - p2 * 3.0 + p3) * t3) * 0.5
            op.append(q)
            e = t * t * (3.0 - 2.0 * t)
            orr.append(r1 + (r2 - r1) * e)
    op.append(P[-1])
    orr.append(R[-1])
    return op, orr


def _tube(points, radii, samples: int = 26, step: float = 9.0):
    """Round tube lofted through a centreline — the pipework vocabulary."""
    if isinstance(radii, (int, float)):
        radii = [float(radii)] * len(points)
    if step:
        points, radii = _catmull(points, radii, step)
    planes = _frames(points)
    faces = [pl * make_face(Spline(*_circle_pts(r, samples), periodic=True))
             for pl, r in zip(planes, radii)]
    return lib.loft_solid(faces, ruled=not step)


def _stations(keys, step: float = 12.0):
    """Catmull-Rom densify (x, *params) control stations for a ruled loft."""
    K = [[float(v) for v in k] for k in keys]
    m = len(K[0])
    head = [2.0 * K[0][i] - K[1][i] for i in range(m)]
    tail = [2.0 * K[-1][i] - K[-2][i] for i in range(m)]
    ext = [head] + K + [tail]
    out = []
    for i in range(len(K) - 1):
        a, b, c, d = ext[i], ext[i + 1], ext[i + 2], ext[i + 3]
        n = max(2, int(abs(c[0] - b[0]) / step))
        for j in range(n):
            t = j / n
            t2, t3 = t * t, t * t * t
            out.append([0.5 * (2.0 * b[k] + (c[k] - a[k]) * t
                               + (2.0 * a[k] - 5.0 * b[k] + 4.0 * c[k] - d[k]) * t2
                               + (3.0 * b[k] - a[k] - 3.0 * c[k] + d[k]) * t3)
                        for k in range(m)])
    out.append(K[-1])
    return out


def _sup(x, hw, hh, cz, nt=3.0, nb=3.0, cy=0.0, samples=34):
    """Superellipse bodywork section at station x."""
    return lib.section_face(
        x, lib.superellipse_pts(hw, hh, n_top=nt, n_bot=nb, cy=cy, cz=cz,
                                samples=samples))


def _fuse(base, extras):
    out = base
    for e in extras:
        if e is None:
            continue
        try:
            cand = out + e
            if cand is not None and cand.is_valid and cand.volume > 0:
                out = cand
        except Exception:
            continue
    return out


def _ring(center, axis, r_in, r_out, half_len, n=30):
    """Machined collar / clamp band about an axis."""
    a = Vector(*axis).normalized()
    c = Vector(*center)
    faces = []
    for s in (-half_len, half_len):
        pl = _frames([c + a * (s * 1.0), c + a * (s + 1.0)])[0]
        outer = _circle_pts(r_out, n)
        inner = list(reversed(_circle_pts(r_in, n)))
        faces.append(pl * make_face(Spline(*(outer + inner), periodic=True)))
    return lib.loft_solid(faces, ruled=True)


def _volute(cx, cz, r_wheel, wrap_deg, theta_end, hand,
            h0, h1, w0, w1, n=30, gap=3.0):
    """A real scroll: section area shrinks as it wraps, so it is a volute.

    Returns (solid, end_point, end_tangent, half_axial, half_radial) so the
    inlet/discharge duct can be attached to the scroll's own end frame instead
    of a hand-computed guess.
    """
    theta_start = theta_end - hand * wrap_deg
    faces = []
    end = None
    for i in range(n + 1):
        f = i / n
        th = math.radians(theta_start + hand * wrap_deg * f)
        hv = h0 + (h1 - h0) * f
        hu = w0 + (w1 - w0) * f
        rad = Vector(0.0, math.cos(th), math.sin(th))
        origin = Vector(cx, 0.0, cz) + rad * (r_wheel + gap + hv)
        tang = Vector(1, 0, 0).cross(rad) * hand
        pl = Plane(origin=origin, x_dir=(1, 0, 0), z_dir=tang)
        pts = lib.superellipse_pts(hu, hv, n_top=2.8, n_bot=2.8, samples=26)
        faces.append(pl * make_face(Spline(*pts, periodic=True)))
        if i == n:
            end = (origin, tang, hu, hv)
    solid = lib.loft_solid(faces, ruled=False)
    return solid, end[0], end[1], end[2], end[3]


# ==========================================================================
# 1. CYLINDER BLOCK / CRANKCASE — the stressed member
# ==========================================================================
#
# Three archetype half-sections with matching point indices, blended along X:
#   0      bottom centreline of the crankcase rail
#   1..6   lower flank, swelling over the main-bearing barrel
#   7      deck outer corner
#   8..11  the 45 deg bank deck, running up to the vee
#   12..16 the vee valley floor, back to the centreline
# Blending them instead of stacking boxes is what gives one continuous
# casting: a rounded front cover, a hard vee through the cylinder run, and a
# bellhousing that squares up onto the gearbox face.

_SEC_FRONT = [
    (0, 176), (58, 178), (100, 190), (130, 210), (150, 238), (159, 268),
    (159, 300), (156, 326), (140, 350), (117, 368), (90, 380), (73, 385),
    (60, 388), (46, 390), (32, 392), (16, 393), (0, 393),
]

_SEC_REAR = [
    (0, 150), (60, 152), (104, 161), (133, 180), (149, 206), (156, 234),
    (156, 264), (153, 290), (142, 314), (124, 334), (102, 346), (88, 351),
    (74, 354), (56, 356), (38, 357), (20, 357), (0, 357),
]


def _sec_vee():
    """Cylinder-run section: crankcase barrel, 45 deg decks, vee valley."""
    do = _bank(D_DECK, 60.0)  # deck outer corner
    di = _bank(D_DECK, -60.0)  # deck inner corner
    pts = [(0, 178), (58, 180), (100, 191), (129, 210), (148, 236),
           (154, 264), (152, 290), (do[0], do[1])]
    for t in (0.28, 0.56, 0.84, 1.0):  # straight run down the deck
        pts.append((do[0] + (di[0] - do[0]) * t, do[1] + (di[1] - do[1]) * t))
    pts += [(78, 379), (66, 361), (54, 350), (28, 346), (0, 345)]
    return pts


_SEC_VEE = _sec_vee()


def _block_pts(x: float):
    """Blended block half-section at station x (left side, y >= 0)."""
    if x >= -2190.0:
        t = spec.smoothstep((X_FRONT - x) / (X_FRONT + 2190.0))
        a, b = _SEC_FRONT, _SEC_VEE
    elif x >= -2600.0:
        return list(_SEC_VEE)
    else:
        t = spec.smoothstep((-2600.0 - x) / 280.0)
        a, b = _SEC_VEE, _SEC_REAR
    return [(a[i][0] + (b[i][0] - a[i][0]) * t,
             a[i][1] + (b[i][1] - a[i][1]) * t) for i in range(len(a))]


# rib growth is full on the flanks and dies to nothing on the deck and in
# the valley, so a main-bearing rib never stands proud inside the head.
_RIB_W = (1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 0.92, 0.55,
          0.16, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

# the belt rib is concentrated on the main-bearing flank only, so the line
# runs the whole length of the casting and dies into a machined face at each
# end rather than fading out mid-surface.
_BELT_W = (0.0, 0.0, 0.0, 0.34, 0.9, 1.0, 0.82, 0.2,
           0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)


def _grow(pts, delta: float, weights=None):
    """Offset a half-section outward along its own local normals."""
    n = len(pts)
    out = []
    for i, (y, z) in enumerate(pts):
        w = 1.0 if weights is None else weights[i]
        d = delta * w
        if i == 0:
            out.append((0.0, z - d))
            continue
        if i == n - 1:
            out.append((0.0, z + d))
            continue
        dy = pts[i + 1][0] - pts[i - 1][0]
        dz = pts[i + 1][1] - pts[i - 1][1]
        m = math.hypot(dy, dz) or 1.0
        out.append((y + d * dz / m, z - d * dy / m))
    return out


def _block_face(x: float, delta: float = 0.0, weights=None):
    pts = _block_pts(x)
    if delta:
        pts = _grow(pts, delta, weights)
    return lib.half_section_face(x, pts)


def _crankcase():
    xs = [X_FRONT, -2020, -2070, -2125, -2190, -2260, -2340, -2420,
          -2500, -2565, -2600, -2660, -2720, -2780, -2840, X_REAR]
    return lib.body_loft([_block_face(x) for x in xs])


def _web_ribs():
    out = []
    for i, xw in enumerate(WEB_X):
        prof = ((-12.0, 0.9), (-7.0, 6.4), (0.0, 11.0), (7.0, 6.4),
                (12.0, 0.9))
        faces = [_block_face(xw + dx, d, _RIB_W) for dx, d in prof]
        out.append(lib.styled(lib.body_loft(faces), f"main_web_rib_{i + 1}",
                              spec.MAGNESIUM))
    return out


def _face_flange(x_out: float, depth: float, label: str):
    """Machined mounting face with a proud flange and bolt bosses."""
    sgn = 1.0 if depth > 0 else -1.0
    xs = [x_out, x_out + depth * 0.35, x_out + depth]
    grows = [10.0, 10.0, 2.0]
    flange = lib.body_loft([_block_face(x, g) for x, g in zip(xs, grows)])
    bosses = []
    pts = _block_pts(x_out)
    for idx in (2, 5, 8, 12, 15):
        for s in (1.0, -1.0):
            y, z = pts[idx]
            if abs(y) < 4.0 and s < 0:
                continue
            gy, gz = _grow(pts, 12.0)[idx]
            c = (s * gy, gz)
            p0 = (x_out, c[0], c[1])
            p1 = (x_out + sgn * 30.0, c[0], c[1])
            bosses.append(_tube([p0, p1], [13.0, 11.0], samples=18))
    return lib.styled(_fuse(flange, bosses), label, spec.ANODIZED)


def _sump():
    keys = []
    for i in range(15):
        t = i / 14.0
        x = -2040.0 - 710.0 * t
        e = math.sin(math.pi * t) ** 0.5
        top, bot = 212.0, 208.0 - (10.0 + 72.0 * e)
        keys.append((x, 50.0 + 90.0 * e, (top - bot) / 2.0, (top + bot) / 2.0))
    return lib.body_loft([_sup(x, hw, hh, cz, nt=5.0, nb=2.6)
                          for x, hw, hh, cz in _stations(keys, 12.0)],
                         ruled=False)


def _deck_rail(side):
    """The block/head parting flange plus its row of head studs.

    A casting this size needs one uninterrupted horizontal line or it reads as
    a smooth pod; this is that line, and the studs give it rhythm.
    """
    def face(x, sc=1.0):
        c = [_bank(168.0, 56.0 * sc, side), _bank(168.0, 78.0 * sc, side),
             _bank(202.0, 78.0 * sc, side), _bank(202.0, 56.0 * sc, side)]
        return lib.section_face(x, _quad_pts(c, r=0.2))
    rail = lib.body_loft([face(-2196, 0.55), face(-2208, 1.0),
                          face(-2596, 1.0), face(-2608, 0.55)], ruled=True)
    studs = []
    n = 11
    for i in range(n):
        x = -2206.0 - 392.0 * i / (n - 1)
        p0 = Vector(*_bank_pt(x, 190.0, 70.0, side))
        studs.append(_tube([p0 - _v_dir(side) * 14.0, p0 + _v_dir(side) * 13.0],
                           [11.0, 9.5], samples=16, step=0.0))
    return lib.styled(_fuse(rail, studs), f"head_joint_rail:{side}",
                      spec.MAGNESIUM)


def _belt_face(x: float, grow: float, half: float, side: float = 1.0):
    """Cross-section of the flank belt rib, riding on the casting surface."""
    pts = _block_pts(x)
    y, z = pts[5]
    gy, gz = _grow(pts, grow)[5]
    dy = pts[6][0] - pts[4][0]
    dz = pts[6][1] - pts[4][1]
    m = math.hypot(dy, dz) or 1.0
    ty, tz = dy / m, dz / m
    c = [(side * (y - ty * half), z - tz * half),
         (side * (gy - ty * half * 0.72), gz - tz * half * 0.72),
         (side * (gy + ty * half * 0.72), gz + tz * half * 0.72),
         (side * (y + ty * half), z + tz * half)]
    return lib.section_face(x, _quad_pts(c, r=0.22))


def _belt_rib(side):
    prof = ((-2016, 1.5, 12.0), (-2034, 10.0, 21.0), (-2260, 10.5, 22.0),
            (-2500, 10.5, 22.0), (-2700, 10.0, 21.0), (-2828, 8.5, 19.0),
            (-2846, 1.5, 12.0))
    return lib.body_loft([_belt_face(x, g, h, side) for x, g, h in prof],
                         ruled=True)


def build_block():
    kids = [
        lib.styled(_crankcase(), "crankcase", spec.MAGNESIUM),
        lib.styled(_sump(), "sump_pan", spec.ANODIZED),
        _face_flange(X_FRONT, -34.0, "engine_front_face"),
        _face_flange(X_REAR, 34.0, "gearbox_mating_face"),
    ]
    for side, tag in ((1.0, 'left'), (-1.0, 'right')):
        kids.append(lib.styled(_belt_rib(side),
                               f'crankcase_belt_rib:{tag}',
                               spec.MAGNESIUM))
    kids += _web_ribs()
    for side, tag in ((1.0, 'left'), (-1.0, 'right')):
        r = _deck_rail(side)
        r.label = f'head_joint_rail:{tag}'
        kids.append(r)
    return kids


# ==========================================================================
# 2. CYLINDER HEADS + CAM COVERS
# ==========================================================================

D_PORT_EX = 205.0
V_PORT_EX = 58.0
D_PORT_IN = 225.0
V_PORT_IN = -58.0
D_RAIL = 254.0
V_RAIL = 56.0


def _u_dir(side=1.0):
    return Vector(0.0, side * SB, CB)


def _v_dir(side=1.0):
    return Vector(0.0, side * CB, -SB)


def _bank_pt(x, d, v, side=1.0):
    y, z = _bank(d, v, side)
    return (x, y, z)


def _quad_pts(corners, r=0.13):
    pts = []
    for i in range(4):
        a, b = corners[i], corners[(i + 1) % 4]
        for t in (r, 0.5, 1.0 - r):
            pts.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
    return pts


def _head_face(x, side, sc=1.0):
    dh = D_DECK + (D_HEAD - D_DECK) * sc
    c = [_bank(D_DECK, 60.0 * sc, side), _bank(dh, 56.0 * sc, side),
         _bank(dh, -56.0 * sc, side), _bank(D_DECK, -60.0 * sc, side)]
    return lib.section_face(x, _quad_pts(c))


def _cover_face(x, side, sc=1.0, flute=3.6):
    w0, w1 = 50.0 * sc, 40.0 * sc
    d0 = D_COVER0
    d1 = D_COVER0 + (D_COVER1 - D_COVER0) * sc
    pts = []
    for t in (0.14, 0.36, 0.58, 0.8, 0.94):
        pts.append(_bank(d0 + (d1 - d0) * t, w0 + (w1 - w0) * t, side))
    n = 28
    for i in range(n + 1):
        t = i / n
        v = w1 - 2.0 * w1 * t
        f = -flute * abs(math.sin(math.pi * 4.0 * t)) if 0.03 < t < 0.97 else 0.0
        pts.append(_bank(d1 + f, v, side))
    for t in (0.06, 0.2, 0.42, 0.64, 0.86):
        pts.append(_bank(d1 + (d0 - d1) * t, -(w1 + (w0 - w1) * t), side))
    for t in (0.16, 0.34, 0.5, 0.66, 0.84):
        pts.append(_bank(d0, -w0 + 2.0 * w0 * t, side))
    return lib.section_face(x, pts)


def _head(side):
    xs = [(HEAD_X0, 0.88), (HEAD_X0 - 12, 1.0), (HEAD_X1 + 12, 1.0),
          (HEAD_X1, 0.88)]
    head = lib.body_loft([_head_face(x, side, s) for x, s in xs], ruled=True)
    bosses = []
    for xc in CYL_X:
        for d, v, r0, r1, ln in ((D_PORT_EX, V_PORT_EX, 34.0, 30.0, 16.0),
                                 (D_PORT_IN, V_PORT_IN, 36.0, 32.0, 14.0)):
            sgn = 1.0 if v > 0 else -1.0
            p = Vector(*_bank_pt(xc, d, v - sgn * 6.0, side))
            q = p + _v_dir(side) * (sgn * (ln + 6.0))
            bosses.append(_tube([p, q], [r0, r1], samples=20))
    return lib.styled(_fuse(head, bosses), f"cylinder_head:{side}",
                      spec.MAGNESIUM)


def _cam_cover(side):
    xs = [(HEAD_X0 + 4, 0.86), (HEAD_X0 - 14, 1.0), (HEAD_X1 + 14, 1.0),
          (HEAD_X1 - 4, 0.86)]
    cover = lib.body_loft([_cover_face(x, side, s) for x, s in xs], ruled=True)
    studs = []
    n = 9
    for i in range(n):
        x = HEAD_X0 - 16 + (HEAD_X1 - HEAD_X0 + 32) * i / (n - 1)
        for v in (34.0, -34.0):
            p = Vector(*_bank_pt(x, D_COVER1 - 16.0, v, side))
            q = p + _u_dir(side) * 22.0
            studs.append(_tube([p, q], [9.5, 8.0], samples=16))
    return lib.styled(_fuse(cover, studs), f"cam_cover:{side}", spec.ANODIZED)


def build_heads():
    kids = []
    for side in (1.0, -1.0):
        tag = "left" if side > 0 else "right"
        h = _head(side)
        h.label = f"cylinder_head:{tag}"
        c = _cam_cover(side)
        c.label = f"cam_cover:{tag}"
        kids += [h, c]
        # spark-plug / coil towers down the crown of each cover
        for i, xc in enumerate(CYL_X):
            p0 = Vector(*_bank_pt(xc, D_COVER1 - 12.0, 0.0, side))
            u = _u_dir(side)
            tower = _tube([p0, p0 + u * 14.0, p0 + u * 20.0, p0 + u * 46.0,
                           p0 + u * 52.0],
                          [21.0, 20.0, 15.0, 14.5, 11.0], samples=20)
            kids.append(lib.styled(tower, f"coil_pack:{tag}:{i + 1}", spec.ANODIZED))
        # fuel rail with its three injectors, tucked under the cover lip
        rail_pts = [_bank_pt(HEAD_X0 + 6, D_RAIL, V_RAIL, side),
                    _bank_pt(HEAD_X1 - 6, D_RAIL, V_RAIL, side)]
        rail = _tube(rail_pts, [12.0, 12.0], samples=20)
        inj = []
        for xc in CYL_X:
            a = Vector(*_bank_pt(xc, D_RAIL, V_RAIL, side))
            b = Vector(*_bank_pt(xc, D_PORT_EX + 26.0, V_PORT_EX - 6.0, side))
            inj.append(_tube([a, a + (b - a) * 0.55, b], [9.0, 7.5, 7.0],
                             samples=16))
        kids.append(lib.styled(_fuse(rail, inj), f"fuel_rail:{tag}", spec.ALLOY))
    return kids


# ==========================================================================
# 3. PLENUM / AIR BOX + the six trumpets
# ==========================================================================

TRUMPET_Y = 78.0
TRUMPET_TOP_Z = 572.0

_PLENUM_STATIONS = (
    (-2235.0, 90.0, 50.0, 622.0), (-2252.0, 106.0, 57.0, 625.0),
    (-2290.0, 116.0, 60.0, 627.0), (-2360.0, 121.0, 61.0, 627.0),
    (-2440.0, 120.0, 61.0, 627.0), (-2510.0, 113.0, 59.0, 626.0),
    (-2548.0, 100.0, 54.0, 623.0), (-2570.0, 84.0, 46.0, 620.0),
)


def _plenum():
    return lib.body_loft(
        [_sup(x, hw, hh, cz, nt=3.3, nb=2.6)
         for x, hw, hh, cz in _stations(_PLENUM_STATIONS, 11.0)], ruled=False)


def _trumpet(x, side):
    pts = [(x, side * 118.0, 420.0), (x, side * 106.0, 432.0),
           (x, side * 94.0, 452.0), (x, side * 84.0, 478.0),
           (x, side * 79.0, 506.0), (x, side * TRUMPET_Y, 536.0),
           (x, side * TRUMPET_Y, 556.0), (x, side * TRUMPET_Y, 566.0),
           (x, side * TRUMPET_Y, TRUMPET_TOP_Z)]
    radii = [33.0, 32.0, 31.0, 31.0, 32.0, 34.0, 39.0, 46.0, 51.0]
    return _tube(pts, radii, samples=24)


def build_plenum():
    kids = [lib.styled(_plenum(), "plenum", spec.CARBON)]
    for side, tag in ((1.0, "left"), (-1.0, "right")):
        for i, xc in enumerate(CYL_X):
            kids.append(lib.styled(_trumpet(xc, side),
                                   f"trumpet:{tag}:{i + 1}", spec.ALLOY))
    return kids


# ==========================================================================
# 4. TURBOCHARGER — compressor forward, turbine aft, shaft through the vee
# ==========================================================================


def _axial(xs_rs, y=0.0, z=SHAFT_Z, samples=28):
    """Machined turning about the X axis: crisp steps, no path smoothing."""
    return _tube([(x, y, z) for x, _ in xs_rs], [r for _, r in xs_rs],
                 samples=samples, step=0.0)


def build_turbo():
    kids = []

    # --- compressor ------------------------------------------------------
    vol, cend, ctan, chu, chv = _volute(
        COMP_X, SHAFT_Z, R_COMP, 330.0, 90.0, 1.0, 7.0, 30.0, 10.0, 31.0)
    kids.append(lib.styled(vol, "compressor_volute", spec.ALLOY))
    kids.append(lib.styled(
        _axial(((-2214, 50), (-2200, 74), (-2197, 71), (-2135, 49),
                (-2116, 38), (-2100, 36), (-2086, 45), (-2079, 40))),
        "compressor_housing", spec.ALLOY))

    d = [tuple(cend), (-2168, -34, 637), (-2178, -63, 632), (-2199, -78, 628),
         (-2226, -79, 626), (-2256, -73, 624)]
    kids.append(lib.styled(_tube(d, [44, 44, 43, 42, 41, 40]),
                           "charge_pipe", spec.ANODIZED))
    kids.append(lib.styled(
        _ring((-2200, -78, 627), (0.35, 0.93, 0.06), 41, 52, 7),
        "charge_pipe_clamp", spec.ALLOY))

    # airbox -> compressor inlet trunk, hung off the airbox duct mouth
    trunk = [(-2044, 0, 700), (-2043, 0, 660), (-2047, 0, 622),
             (-2056, 0, 588), (-2068, 0, 561), (-2082, 0, 543),
             (-2098, 0, 534), (-2116, 0, 531)]
    kids.append(lib.styled(_tube(trunk, [43, 43, 44, 45, 46, 47, 45, 41]),
                           "airbox_trunk", spec.CARBON))

    # --- shaft through the vee -------------------------------------------
    kids.append(lib.styled(
        _axial(((-2196, 16), (-2600, 15), (-2812, 16))), "turbo_shaft",
        spec.ANODIZED))

    # --- MGU-H on the shaft ----------------------------------------------
    body = _axial(((-2628, 44), (-2640, 68), (-2646, 70), (-2764, 70),
                   (-2770, 68), (-2782, 44)))
    fins = [_ring((-2762 + 13 * i, 0, SHAFT_Z), (1, 0, 0), 66, 80, 3.4)
            for i in range(10)]
    kids.append(lib.styled(_fuse(body, fins), "mgu_h", spec.ANODIZED))
    gl = [(-2704, 0, 596), (-2706, 0, 616), (-2712, 0, 634)]
    kids.append(lib.styled(_tube(gl, [26, 24, 21]), "mgu_h_gland",
                           spec.ANODIZED))

    # --- turbine ---------------------------------------------------------
    tvol, tend, ttan, thu, thv = _volute(
        TURB_X, SHAFT_Z, R_TURB, 330.0, 0.0, -1.0, 6.0, 30.0, 9.0, 29.0)
    kids.append(lib.styled(tvol, "turbine_volute", spec.INCONEL))
    kids.append(lib.styled(
        _axial(((-2806, 52), (-2818, 72), (-2821, 69), (-2875, 49),
                (-2882, 47), (-2906, 43), (-2932, 40), (-2950, 42))),
        "turbine_housing", spec.INCONEL))
    stub = [tuple(tend), (-2848, 109, 496), (-2846, 106, 464),
            (-2842, 100, 438), (-2838, 95, 418)]
    kids.append(lib.styled(_tube(stub, [42, 43, 45, 47, 49]),
                           "turbine_inlet", spec.INCONEL))
    return kids


# ==========================================================================
# 5. EXHAUST — 3-into-1 per bank, 2-into-1 into the turbine, one tailpipe
# ==========================================================================

_PRIMARY = (
    ((-2280, 184, 322), (-2292, 202, 304), (-2316, 214, 292), (-2364, 219, 288),
     (-2436, 220, 288), (-2512, 218, 292), (-2580, 210, 304), (-2638, 190, 324),
     (-2680, 156, 344), (-2702, 128, 354)),
    ((-2400, 184, 322), (-2412, 200, 310), (-2436, 208, 316), (-2482, 210, 328),
     (-2542, 207, 336), (-2600, 196, 344), (-2652, 172, 352), (-2694, 142, 356)),
    ((-2520, 184, 322), (-2534, 198, 312), (-2560, 200, 320), (-2600, 196, 332),
     (-2640, 184, 342), (-2678, 156, 352), (-2698, 130, 358)),
)

_COLL_L = ((-2700, 126, 356), (-2736, 122, 372), (-2776, 116, 388),
           (-2808, 108, 398))
_COLL_R = ((-2700, -126, 358), (-2726, -108, 374), (-2752, -70, 392),
           (-2778, -20, 404), (-2800, 34, 408), (-2820, 84, 408))

_TAILPIPE = ((-2944, 0, 530), (-3060, 0, 522), (-3200, 0, 502),
             (-3330, 0, 472), (-3450, 0, 442), (-3552, 0, 420))
_TAIL_R = (42, 44, 44, 43, 42, 41)

_WASTEGATE = ((-2754, 148, 442), (-2790, 152, 462), (-2900, 144, 470),
              (-3060, 122, 470), (-3210, 100, 466), (-3350, 82, 458),
              (-3462, 68, 450), (-3512, 62, 446))


def build_exhaust():
    kids = []
    for side, tag in ((1.0, "left"), (-1.0, "right")):
        for i, path in enumerate(_PRIMARY):
            pts = [(x, side * y, z) for x, y, z in path]
            kids.append(lib.styled(_tube(pts, 21.0, samples=22),
                                   f"exhaust_primary:{tag}:{i + 1}",
                                   spec.INCONEL))
    kids.append(lib.styled(_tube(_COLL_L, [46, 45, 44, 43]),
                           "collector:left", spec.INCONEL))
    kids.append(lib.styled(_tube(_COLL_R, [46, 45, 45, 44, 43, 43]),
                           "collector:right", spec.INCONEL))
    kids.append(lib.styled(
        _tube(((-2788, 100, 400), (-2814, 98, 408), (-2838, 96, 416)),
              [64, 58, 52]), "collector_merge", spec.INCONEL))
    kids.append(lib.styled(_tube(_TAILPIPE, _TAIL_R), "tailpipe", spec.INCONEL))
    kids.append(lib.styled(
        _tube(((-3556, 0, 419), (-3538, 0, 423), (-3524, 0, 426)),
              [45, 45, 42]), "tailpipe_tip", spec.ALLOY))

    # wastegate off the left collector, with its own small tailpipe
    kids.append(lib.styled(
        _tube(((-2748, 124, 388), (-2752, 138, 414), (-2756, 150, 446),
               (-2757, 152, 470)), [30, 33, 33, 27]),
        "wastegate_body", spec.INCONEL))
    kids.append(lib.styled(
        _ring((-2756, 150, 452), (0.1, 0.3, 1.0), 32, 42, 6),
        "wastegate_flange", spec.ALLOY))
    kids.append(lib.styled(_tube(_WASTEGATE, 24.0, samples=20),
                           "wastegate_pipe", spec.INCONEL))
    kids.append(lib.styled(
        _tube(((-3516, 61, 446), (-3500, 62, 447)), [27, 25]),
        "wastegate_tip", spec.ALLOY))

    # gold foil, used twice only: over the left collector (ECU side) and
    # under the tailpipe root where it runs across the gearbox
    kids.append(lib.styled(
        _tube(((-2712, 125, 360), (-2724, 124, 365), (-2760, 119, 381),
               (-2792, 113, 393), (-2804, 109, 397)),
              [47.5, 53, 53, 51, 45.5]),
        "heat_shield:collector", spec.GOLD_FOIL))
    kids.append(lib.styled(
        _tube(((-2960, 0, 529), (-2982, 0, 527), (-3070, 0, 521),
               (-3148, 0, 511), (-3170, 0, 507)),
              [46.5, 52, 52, 51, 45.5]),
        "heat_shield:tailpipe", spec.GOLD_FOIL))
    return kids


# ==========================================================================
# 6. MGU-K + 7. ERS BATTERY + 10. ANCILLARIES
# ==========================================================================

MGUK_Y, MGUK_Z = 175.0, 250.0


def build_mguk():
    kids = []
    body = _tube(((-2088, MGUK_Y, MGUK_Z), (-2100, MGUK_Y, MGUK_Z),
                  (-2316, MGUK_Y, MGUK_Z), (-2328, MGUK_Y, MGUK_Z)),
                 [40, 62, 62, 40], step=0.0)
    fins = [_ring((-2136 - 21 * i, MGUK_Y, MGUK_Z), (1, 0, 0), 60, 72, 3.4)
            for i in range(8)]
    kids.append(lib.styled(_fuse(body, fins), "mgu_k", spec.ALLOY))
    kids.append(lib.styled(
        _ring((-2114, MGUK_Y, MGUK_Z), (1, 0, 0), 60, 74, 6.5),
        "mgu_k_ring", spec.ACCENT))  # the car's single accent on this part
    kids.append(lib.styled(
        _tube(((-2014, 92, 234), (-2032, 120, 240), (-2066, 152, 246),
               (-2100, MGUK_Y, MGUK_Z)), [52, 60, 66, 68]),
        "mgu_k_drive_housing", spec.MAGNESIUM))
    for i, dy in enumerate((0.0, -30.0)):
        kids.append(lib.styled(
            _tube(((-2116, 196 + dy, 300), (-2062, 200 + dy, 288),
                   (-2016, 190 + dy, 262), (-1978, 172 + dy, 240),
                   (-1936, 150 + dy, 228)), 15.0, samples=18),
            f"mgu_k_cable:{i + 1}", spec.CARBON))
    kids.append(lib.styled(
        _tube(((-2712, 0, 628), (-2716, -50, 618), (-2700, -104, 578),
               (-2640, -138, 536), (-2480, -146, 516), (-2300, -142, 508),
               (-2216, -140, 494), (-2170, -152, 448), (-2120, -170, 392),
               (-2062, -182, 330), (-2000, -184, 292), (-1950, -176, 268),
               (-1918, -166, 254)), 18.0, samples=18),
        "mgu_h_cable", spec.CARBON))
    return kids


def build_battery():
    kids = []
    case = [(BAT_X0, 228, 52, 190), (BAT_X0 - 22, 246, 58, 190),
            (-1700, 252, 60, 190), (-1850, 252, 60, 190),
            (BAT_X1 + 22, 246, 58, 190), (BAT_X1, 228, 52, 190)]
    kids.append(lib.styled(
        lib.body_loft([_sup(x, hw, hh, cz, nt=5.5, nb=5.0)
                       for x, hw, hh, cz in _stations(case, 14.0)], ruled=False),
        "ers_battery_case", spec.CARBON))
    lid = [(BAT_X0 - 18, 214, 10, 249), (BAT_X0 - 40, 232, 13, 249),
           (-1780, 236, 13, 249), (BAT_X1 + 40, 232, 13, 249),
           (BAT_X1 + 18, 214, 10, 249)]
    kids.append(lib.styled(
        lib.body_loft([_sup(x, hw, hh, cz, nt=5.5, nb=5.0)
                       for x, hw, hh, cz in _stations(lid, 14.0)], ruled=False),
        "ers_battery_lid", spec.CARBON_WEAVE))
    for i, (bx, by) in enumerate(((-1624, 240), (-1624, -240),
                                  (-1926, 240), (-1926, -240))):
        kids.append(lib.styled(
            _tube(((bx - 34, by, 168), (bx - 22, by, 168), (bx + 22, by, 168),
                   (bx + 34, by, 168)), [16, 26, 26, 16], step=0.0),
            f"ers_bracket:{i + 1}", spec.ANODIZED))
    term = [(-1944, 152, 30, 214), (-1950, 158, 33, 214),
            (-1966, 158, 33, 214), (-1972, 150, 29, 214)]
    kids.append(lib.styled(
        lib.body_loft([_sup(x, hw, hh, cz, nt=6.0, nb=6.0)
                       for x, hw, hh, cz in _stations(term, 5.0)], ruled=False),
        "ers_terminal_block", spec.ANODIZED))
    for i, by in enumerate((-120, -72, -24, 24, 72, 120)):
        kids.append(lib.styled(
            _tube(((-1962, by, 214), (-1982, by, 214)), [13, 12], step=0.0),
            f"ers_bus_bar:{i + 1}", spec.COPPER))
    for i, by in enumerate((-196, 196)):
        kids.append(lib.styled(
            _tube(((-1944, by, 176), (-1972, by, 178), (-1998, by, 186)),
                  [21, 21, 19]), f"ers_coolant:{i + 1}", spec.COPPER))
    return kids


def build_ancillaries():
    kids = [
        lib.styled(_tube(((-2004, -140, 202), (-2014, -142, 202),
                          (-2078, -146, 204), (-2088, -146, 204)),
                         [40, 50, 50, 40]), "water_pump", spec.ANODIZED),
        lib.styled(_tube(((-2004, 116, 190), (-2012, 118, 190),
                          (-2068, 122, 192), (-2076, 122, 192)),
                         [34, 44, 44, 34]), "oil_pump", spec.ANODIZED),
    ]
    # oil tank between engine and gearbox, on the right flank
    tank = [(-2600, 46, 40, 400), (-2620, 62, 60, 400), (-2700, 66, 68, 400),
            (-2790, 62, 64, 398), (-2820, 44, 44, 396)]
    kids.append(lib.styled(
        lib.body_loft([_sup(x, hw, hh, cz, nt=3.0, nb=2.6, cy=-192.0)
                       for x, hw, hh, cz in _stations(tank, 12.0)], ruled=False),
        "oil_tank", spec.CARBON))
    # engine-control box on the left flank, shaded by the collector shield
    ecu = [(-2618, 48, 34, 486), (-2634, 60, 43, 486), (-2760, 60, 43, 486),
           (-2778, 48, 34, 486)]
    kids.append(lib.styled(
        lib.body_loft([_sup(x, hw, hh, cz, nt=6.0, nb=6.0, cy=178.0)
                       for x, hw, hh, cz in _stations(ecu, 12.0)], ruled=False),
        "ecu_box", spec.CARBON))
    kids.append(lib.styled(
        _tube(((-2612, 178, 486), (-2622, 178, 486)), [40, 44], step=0.0),
        "ecu_connector", spec.ALLOY))
    for i, dy in enumerate((-20.0, 0.0, 20.0)):
        kids.append(lib.styled(
            _tube(((-2600, 178 + dy, 486), (-2610, 178 + dy, 486)),
                  [8, 8], step=0.0), f"ecu_pin:{i + 1}", spec.ANODIZED))

    # fluid lines: slim, rhythmic, bracketed — not spaghetti
    lines = {
        "water_feed": (((-2078, -150, 210), (-2042, -186, 238),
                        (-2012, -212, 274), (-1998, -216, 300)), 20.0),
        "water_return": (((-2104, 168, 330), (-2058, 190, 348),
                          (-2016, 206, 364), (-1998, 212, 372)), 20.0),
        "oil_feed": (((-2762, -186, 350), (-2680, -186, 318),
                      (-2560, -188, 286), (-2400, -188, 278),
                      (-2260, -186, 276), (-2120, -176, 262),
                      (-2020, -160, 246), (-1996, -152, 240)), 15.0),
        "oil_return": (((-2758, -190, 316), (-2680, -190, 288),
                        (-2560, -192, 254), (-2400, -192, 246),
                        (-2260, -190, 244), (-2120, -180, 232),
                        (-2020, -164, 218), (-1996, -156, 212)), 13.0),
        "fuel_line": (((-1992, 96, 404), (-2060, 140, 392),
                       (-2140, 176, 376), (-2200, 206, 364),
                       (-2214, 219, 358)), 11.0),
        "fuel_crossover": (((-2211, 219, 359), (-2200, 150, 420),
                            (-2196, 60, 452), (-2196, -60, 452),
                            (-2200, -150, 420), (-2211, -219, 359)), 10.0),
    }
    for name, (pts, r) in lines.items():
        kids.append(lib.styled(_tube(pts, r, samples=18), name, spec.ANODIZED))
    for i, (bx, by, bz) in enumerate(((-2560, -190, 270), (-2260, -188, 260),
                                      (-2660, -188, 302), (-2120, -178, 247))):
        kids.append(lib.styled(
            _tube(((bx, by + 16, bz), (bx, by - 22, bz)), [10, 9], step=0.0),
            f"line_bracket:{i + 1}", spec.ANODIZED))
    return kids


def build_power_unit():
    return lib.group("power_unit",
                     build_block() + build_heads() + build_plenum()
                     + build_turbo() + build_exhaust() + build_mguk()
                     + build_battery() + build_ancillaries())
