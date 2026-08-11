"""Front pushrod and rear pullrod suspension.

Everything here obeys spec rule 7 (DELICACY): every member that sees air is a
lofted `lib.blade_*` teardrop, chord aligned to flow, fat at the inboard root
where the bending moment lives and slim at the ball joint. Nothing is a bar.

The hardpoints in `spec` are law. Every member terminates exactly on its named
point — the uprights build their ball-joint eyes on the same coordinates and
the animation sidecar solves the steering from them — so no number in this
file may "nearly" reach a joint.

Layout, front to rear:

  FRONT   pushrod, launched off the LOWER wishbone, up to a rocker on a
          near-longitudinal axis; torsion bar coaxial with that bearing;
          damper laid inboard across the top of the tub; blade-type ARB
          ahead of the rockers with short vertical drop links.
  REAR    pullrod, the opposite diagonal — HIGH at the upper wishbone,
          DOWN to a low rocker beside the gearbox; toe link aft and low.
"""

from __future__ import annotations

import math

from build123d import (
    Cylinder,
    Plane,
    Pos,
    Sphere,
    Spline,
    Vector,
    extrude,
    make_face,
)

from . import lib, spec

# ==========================================================================
# small vector / construction helpers
# ==========================================================================


def _p(t) -> Vector:
    if isinstance(t, Vector):
        return t
    return Vector(float(t[0]), float(t[1]), float(t[2]))


def _unit(v) -> Vector:
    return Vector(v).normalized()


def _perp(axis, ref) -> Vector:
    """Component of `ref` perpendicular to `axis`, normalised."""
    n = _unit(axis)
    r = Vector(ref)
    r = r - n * r.dot(n)
    if r.length < 1e-6:
        r = Vector(0, 0, 1) if abs(n.Z) < 0.9 else Vector(1, 0, 0)
        r = r - n * r.dot(n)
    return r.normalized()


def ey_of(ax, ex) -> Vector:
    return Vector(ax).cross(Vector(ex))


def _blade_dirs(axis, roll_deg: float = 0.0):
    """(chord direction, thin direction) of a `lib.blade_*` section.

    Mirrors `lib.blade_face`'s frame so a clevis straddling a member knows
    which way the blade is thin.
    """
    n = _unit(axis)
    ref = Vector(lib.FLOW)
    if abs(ref.dot(n)) > 0.97:
        ref = Vector(0, 0, 1)
        if abs(ref.dot(n)) > 0.97:
            ref = Vector(0, 1, 0)
    xd = (ref - n * ref.dot(n)).normalized()
    yd = n.cross(xd)
    a = math.radians(roll_deg)
    return xd * math.cos(a) + yd * math.sin(a), yd * math.cos(a) - xd * math.sin(a)


def _vol(s) -> float:
    try:
        return float(s.volume)
    except Exception:
        return 0.0


_NUDGES = ((0.0017, 0.0, 0.0), (0.0, 0.0015, 0.0), (0.0, 0.0, 0.0019),
           (0.0013, 0.0011, 0.0009))


def _fuse(parts):
    """Fuse with a micron-nudge retry.

    OCC silently returns an EMPTY compound when two solids share exactly
    coplanar faces over an overlapping region — which happens constantly when
    plates of equal thickness are lofted in the same plane. A 2 um offset makes
    the same boolean succeed and is invisible at any render resolution.
    """
    out = None
    for q in parts:
        if q is None:
            continue
        if out is None:
            out = q
            continue
        floor = 0.5 * max(_vol(out), _vol(q))
        try:
            res = out + q
        except Exception:
            res = None
        if res is None or _vol(res) < floor:
            for d in _NUDGES:
                try:
                    cand = out + Pos(d) * q
                except Exception:
                    continue
                if _vol(cand) >= floor:
                    res = cand
                    break
        out = res if res is not None and _vol(res) > 0.0 else out
    return out


def _cut(base, tools):
    """Subtract, keeping the original body if a boolean collapses."""
    for t in tools:
        if t is None:
            continue
        v0 = _vol(base)
        try:
            res = base - t
        except Exception:
            res = None
        if res is None or _vol(res) < 1e-6:
            for d in _NUDGES:
                try:
                    cand = base - Pos(d) * t
                except Exception:
                    continue
                if _vol(cand) > 1e-6:
                    res = cand
                    break
        if res is not None and 1e-6 < _vol(res) <= v0 + 1e-6:
            base = res
    return base


def _dedupe(pts, eps=1e-4):
    out = []
    for q in pts:
        if not out or abs(q[0] - out[-1][0]) > eps or abs(q[1] - out[-1][1]) > eps:
            out.append((float(q[0]), float(q[1])))
    while len(out) > 3 and abs(out[0][0] - out[-1][0]) < eps and abs(out[0][1] - out[-1][1]) < eps:
        out.pop()
    return out


def _face(plane: Plane, pts):
    return plane * make_face(Spline(*_dedupe(pts), periodic=True))


def _plate(plane: Plane, pts, thick: float):
    """Rounded plate: a 2D outline in `plane`, extruded symmetrically."""
    return extrude(_face(plane, pts), thick / 2.0, both=True)


def _cyl(center, axis, r: float, h: float):
    return Plane(origin=_p(center), z_dir=_unit(axis)) * Cylinder(r, h)


def _shaft(p0, p1, r: float):
    a, b = _p(p0), _p(p1)
    return _cyl((a + b) * 0.5, b - a, r, (b - a).length)


def _ball(c, r: float):
    return Pos(_p(c)) * Sphere(r)


def _beam(p0, p1, stations, thin=(0, 0, 1), n_top: float = 2.4, n_bot: float = 2.4,
          ruled: bool = False):
    """Lofted rounded-rect / elliptical beam from p0 to p1.

    `stations` is [(t, half_width, half_thickness)] with t along p0->p1;
    `thin` names the direction the half_thickness is measured along.
    `ruled=True` for anything whose radius alternates quickly (a bellows) — a
    smooth loft balloons wildly between rapidly alternating sections.
    """
    a, b = _p(p0), _p(p1)
    ax = (b - a).normalized()
    td = _perp(ax, thin)
    wd = td.cross(ax)
    faces = []
    for st in stations:
        t, hw, ht = st[0], st[1], st[2]
        nt = st[3] if len(st) > 3 else n_top
        nb = st[4] if len(st) > 4 else n_bot
        pl = Plane(origin=a + (b - a) * t, x_dir=wd, z_dir=ax)
        faces.append(_face(pl, lib.superellipse_pts(hw, ht, nt, nb, samples=26)))
    return lib.loft_solid(faces, ruled=ruled)


def _hull_discs(discs, n: int = 10):
    """Outline of the convex hull of a set of discs.

    Every machined plan-shape in this module — wishbone clevis ears, rocker
    arms, bearing carriers — is the hull of two or three discs, so the outline
    is tangent-continuous by construction and there are no invented curves.
    """
    m = len(discs)
    cx = sum(c[0] for c, _ in discs) / m
    cy = sum(c[1] for c, _ in discs) / m
    if m > 2:
        discs = sorted(discs, key=lambda d: math.atan2(d[0][1] - cy, d[0][0] - cx))

    def tang(i, j):
        (c0, r0), (c1, r1) = discs[i], discs[j]
        dx, dy = c1[0] - c0[0], c1[1] - c0[1]
        d = max(math.hypot(dx, dy), 1e-6)
        return math.atan2(dy, dx) - math.acos(max(-1.0, min(1.0, (r0 - r1) / d)))

    pts = []
    for i in range(m):
        c, r = discs[i]
        a_in = tang((i - 1) % m, i)
        a_out = tang(i, (i + 1) % m)
        sweep = (a_out - a_in) % (2.0 * math.pi)
        k = max(3, int(round(n * sweep / math.pi)))
        for s in range(k + 1):
            a = a_in + sweep * s / k
            pts.append((c[0] + r * math.cos(a), c[1] + r * math.sin(a)))
    return pts


def _hull2(c0, r0: float, c1, r1: float, n: int = 12):
    return _hull_discs([(c0, r0), (c1, r1)], n=n)


def _scallop_pts(radius: float, depth: float, lobes: int, samples: int = 96):
    """Indexed / knurled collar outline — the ARB blade-angle adjuster."""
    pts = []
    for i in range(samples):
        a = 2.0 * math.pi * i / samples
        f = (0.5 + 0.5 * math.cos(lobes * a)) ** 5
        r = radius - depth * f
        pts.append((r * math.cos(a), r * math.sin(a)))
    return pts


# ==========================================================================
# member vocabulary
#
# ONE hardware family, and it is deliberately SMALL. A modern F1 rod-end is a
# jewel: a 13 mm ball in a 19 mm race. Sizing joints off a generic bearing
# instead of off the member they terminate is exactly what makes a suspension
# read as shop-built linkage, so every number below is set from its blade.
# ==========================================================================

BALL_R = 6.8  # spherical rod-end ball radius, one family everywhere
BORE_R = 6.2
EYE_OD = 19.0
EYE_W = 11.5
FORK_GAP = 13.5


def _eye(pt, axis, od: float = EYE_OD, width: float = EYE_W, bore: float = BORE_R):
    """Integral machined eye — how a wishbone leg ends at the chassis.

    Chamfered on both faces so it reads as a turned part, not as a length of
    tube stuck on the end of the blade.
    """
    P, ax = _p(pt), _unit(axis)
    r = od / 2.0
    body = _beam(
        P - ax * (width / 2.0), P + ax * (width / 2.0),
        [(0.0, r * 0.78, r * 0.78), (0.17, r, r), (0.83, r, r), (1.0, r * 0.78, r * 0.78)],
        thin=_perp(ax, (0, 0, 1)), n_top=2.0, n_bot=2.0,
    )
    return _cut(body, [_cyl(pt, ax, bore, width * 2.2)])


def _rod_end(pt, rod_dir, eye_axis, shank: float = 21.0, neck: float = 5.2,
             od: float = EYE_OD, width: float = EYE_W):
    """Spherical rod-end centred exactly on `pt`.

    Returns (anodized housing, polished ball). The ball stands a whisker proud
    of the race on both faces so the joint reads as a joint, not a hole; the
    race is chamfered and the shank waists into the blade rather than meeting
    it as a cylindrical lump.
    """
    P = _p(pt)
    rd = _unit(rod_dir)
    ea = _perp(rd, eye_axis)
    r = od / 2.0
    ring = _beam(
        P - ea * (width / 2.0), P + ea * (width / 2.0),
        [(0.0, r * 0.76, r * 0.76), (0.18, r, r), (0.82, r, r), (1.0, r * 0.76, r * 0.76)],
        thin=rd, n_top=2.0, n_bot=2.0,
    )
    collar = _beam(
        P + rd * 0.5, P + rd * shank,
        [(0.0, r * 0.88, width * 0.44), (0.5, neck * 1.28, neck * 1.00),
         (1.0, neck, neck * 0.78)],
        thin=ea,
        n_top=2.2,
        n_bot=2.2,
    )
    housing = _cut(_fuse([ring, collar]), [_cyl(pt, ea, BORE_R, width * 2.4)])
    return housing, _ball(pt, BALL_R)


def _tip_k(t: float, drop: float, power: float = 1.5, start: float = 0.94) -> float:
    """Round-off multiplier over the last few percent of a member.

    Short and gentle on purpose: a long, hard nose-off turns the end of a
    wishbone leg into a dart, which reads as a sheet-metal point rather than as
    a blade dying into a ball joint.
    """
    if t <= start:
        return 1.0
    return 1.0 - drop * ((t - start) / (1.0 - start)) ** power


def _leg(p_in, p_out, c_root: float, c_tip: float, t_max: float, t_tip: float,
         neck: float, roll: float = 0.0, bow: float = 0.0, bow_dir=(1, 0, 0),
         ease: float = 0.80, peak: float = 0.20):
    """One wishbone leg: a WIDE, knife-thin aerofoil blade.

    Chord and thickness run SEPARATE laws, which is why this lofts
    `lib.blade_face` directly instead of calling `lib.blade_path` (one ratio
    for the whole member — a wishbone does not have one). Chord sheds hard off
    the root (`ease` < 1) so the leg is broad where it is bolted and slender
    over most of its length; thickness necks to `neck` right at the pin so a
    compact eye and a small chassis clevis fit, swells to `t_max` just outboard
    of the root where the bending moment peaks, then knifes to `t_tip` and
    noses off into the upright's ball-joint eye.

    Every station is thin: t/c runs about 0.16 at the root swell and under 0.10
    at the pin, which is what makes the blade almost vanish head-on while
    reading as a full aerofoil from above.
    """
    a, b = _p(p_in), _p(p_out)
    bd = _perp(b - a, bow_dir)
    ts = (0.0, 0.055, peak, 0.40, 0.62, 0.80, 0.90, 0.965, 1.0)
    pts = [a + (b - a) * t + bd * (bow * math.sin(math.pi * t)) for t in ts]
    faces = []
    for i, t in enumerate(ts):
        c = lib.taper(c_root, c_tip, t, ease)
        if t <= peak:
            th = neck + (t_max - neck) * (t / peak)
        else:
            th = t_max + (t_tip - t_max) * ((t - peak) / (1.0 - peak)) ** 0.85
        c *= _tip_k(t, 0.34, 1.5)
        th *= _tip_k(t, 0.30, 1.4)
        if i == 0:
            axis = pts[1] - pts[0]
        elif i == len(ts) - 1:
            axis = pts[-1] - pts[-2]
        else:
            axis = pts[i + 1] - pts[i - 1]
        faces.append(lib.blade_face(pts[i], axis, c, th / c, roll, samples=29))
    return lib.loft_solid(faces, ruled=False)


def _fork_boss(pt, axis, open_dir, od: float = 22.0, width: float = 25.0,
               gap: float = 13.0, throat: float = 4.0, reach: float = 2.6):
    """Compact machined fork ON a member — not a bracket bolted to one.

    A short barrel across the member, then a milled slot opened toward
    `open_dir`, so a rod-end drops INSIDE the member's own section. The slot
    stops short of the pin, which leaves a solid web underneath it: that web is
    what carries the load into the blade (and what keeps the two ears part of
    the same solid). Returns (body, slot) — the caller fuses the body and
    subtracts the slot with the rest of its bores.
    """
    P, ax = _p(pt), _unit(axis)
    r = od / 2.0
    ex = _perp(ax, open_dir)
    body = _beam(
        P - ax * (width / 2.0), P + ax * (width / 2.0),
        [(0.0, r * 0.74, r * 0.74), (0.15, r, r), (0.85, r, r), (1.0, r * 0.74, r * 0.74)],
        thin=ex, n_top=2.0, n_bot=2.0,
    )
    rs = r * 0.64
    slot = _plate(
        Plane(origin=P + ex * throat, x_dir=ex, z_dir=ax),
        _hull2((0.0, 0.0), rs, (r * reach, 0.0), rs, n=11),
        gap,
    )
    return body, slot


# chord law for a link: parallel over the middle, feathering into the rod-ends
_ROD_TS = (0.0, 0.10, 0.28, 0.5, 0.72, 0.90, 1.0)
_ROD_KS = (0.0, 0.62, 0.93, 1.0, 0.95, 0.70, 0.06)


def _blade_rod(p0, p1, c_end: float, c_mid: float, tr: float,
               eye0, eye1, roll: float = 0.0, shank: float = 20.0,
               bow: float = 0.0, bow_dir=(1, 0, 0), neck: float = 5.2):
    """Slender tapered blade with a spherical rod-end at each end.

    Returns [blade, housing0, ball0, housing1, ball1]; the balls sit exactly
    on p0 / p1, so the member's endpoints ARE the hardpoints. Each rod-end's
    shank runs 4 mm past the blade's first section, so the machined waist
    disappears INTO the aerofoil instead of butting against it.
    """
    a, b = _p(p0), _p(p1)
    u = (b - a).normalized()
    q0, q1 = a + u * shank, b - u * shank
    bd = _perp(u, bow_dir)
    pts, chords = [], []
    for t, k in zip(_ROD_TS, _ROD_KS):
        pts.append(q0 + (q1 - q0) * t + bd * (bow * math.sin(math.pi * t)))
        chords.append(c_end + (c_mid - c_end) * k)
    blade = lib.blade_path(pts, chords, thickness_ratio=tr, roll_deg=roll)
    h0, b0 = _rod_end(a, u, eye0, shank=shank + 4.0, neck=neck)
    h1, b1 = _rod_end(b, -u, eye1, shank=shank + 4.0, neck=neck)
    return blade, h0, b0, h1, b1


def _clevis(pt, out_dir, jaw_axis, gap: float = FORK_GAP, jaw_r: float = 10.0,
            jaw_t: float = 5.2, reach: float = 25.0, base_r: float = 11.0):
    """Machined chassis clevis at an inboard hardpoint.

    Jaws straddle `jaw_axis` and the bracket runs back along -`out_dir` to a
    mounting pad, so the member attaches to something instead of vanishing.
    Sized off the blade root it holds — the jaws are barely wider than the
    necked eye between them, which is the whole difference between a machined
    pickup and a fabricated bracket.
    """
    P = _p(pt)
    ja = _unit(jaw_axis)
    ex = _perp(ja, out_dir)
    off = gap / 2.0 + jaw_t / 2.0
    outline = _hull2((0.0, 0.0), jaw_r, (-reach, 0.0), base_r, n=11)
    parts = []
    for sgn in (1.0, -1.0):
        parts.append(_plate(Plane(origin=P + ja * (sgn * off), x_dir=ex, z_dir=ja), outline, jaw_t))
    parts.append(
        _beam(
            P - ex * (reach * 0.42),
            P - ex * (reach + base_r * 0.62),
            [(0.0, base_r * 0.72, off + jaw_t / 2.0), (1.0, base_r * 1.06, off + jaw_t / 2.0)],
            thin=ja,
            n_top=2.9,
            n_bot=2.9,
        )
    )
    bracket = _cut(_fuse(parts), [_cyl(P, ja, BORE_R, gap + 4.0 * jaw_t + 20.0)])
    bolt = _fuse([
        _cyl(P, ja, BORE_R - 0.35, gap + 2.0 * jaw_t + 10.0),
        _cyl(P + ja * (off + jaw_t / 2.0 + 4.4), ja, 9.2, 5.2),
        _cyl(P - ja * (off + jaw_t / 2.0 + 3.8), ja, 8.4, 4.4),
    ])
    return bracket, bolt


# ==========================================================================
# the rocker — the most beautiful component on the car
# ==========================================================================


def _rocker(pivot, axis, p_rod, p_damper, lug_deg: float, lug_r: float,
            hub_r: float = 21.0, plate_t: float = 36.0, slot_w: float = 14.5):
    """A machined titanium bellcrank on a spread bearing.

    The two arms sit at their own axial stations on a long stepped hub, each a
    forked plate with a sculpted lightening cut-out, tied together by a
    diagonal load-path strut. Returns (solid, arb_lug_point, (d_lo, d_hi)).
    """
    P, ax = _p(pivot), _unit(axis)
    ex = _perp(ax, (0, 1, 0))
    ey = ax.cross(ex)

    def split(pt):
        v = _p(pt) - P
        d = v.dot(ax)
        rad = v - ax * d
        return d, (rad.dot(ex), rad.dot(ey)), rad.length

    d_rod, uv_rod, l_rod = split(p_rod)
    d_dmp, uv_dmp, l_dmp = split(p_damper)

    lug_uv = (lug_r * math.cos(math.radians(lug_deg)), lug_r * math.sin(math.radians(lug_deg)))
    lug_pt = P + ax * d_rod + ex * lug_uv[0] + ey * lug_uv[1]

    d_lo = min(d_rod, d_dmp) - 26.0
    d_hi = max(d_rod, d_dmp) + 30.0

    def plane_at(d):
        return Plane(origin=P + ax * d, x_dir=ex, z_dir=ax)

    def arm(d, uv, eye_r, hole_a, hole_b, extra=None):
        pl = plane_at(d)
        discs = [((0.0, 0.0), hub_r + 10.0), (uv, eye_r)]
        if extra is not None:
            discs.append((extra[0], extra[1]))
        body = _plate(pl, _hull_discs(discs, n=13), plate_t)
        # sculpted lightening cut-out along the load path
        ln = math.hypot(uv[0], uv[1])
        dr = (uv[0] / ln, uv[1] / ln)
        ca = (dr[0] * ln * hole_a[0], dr[1] * ln * hole_a[0])
        cb = (dr[0] * ln * hole_b[0], dr[1] * ln * hole_b[0])
        body = body - _plate(pl, _hull2(ca, hole_a[1], cb, hole_b[1], n=11), plate_t * 3.0)
        # machined fork so a spherical rod-end can sit in the arm
        slot = _hull2((dr[0] * ln * 0.52, dr[1] * ln * 0.52), 7.0,
                      (dr[0] * (ln + eye_r), dr[1] * (ln + eye_r)), eye_r * 0.92, n=11)
        body = body - _plate(pl, slot, slot_w)
        if extra is not None:
            eln = math.hypot(extra[0][0], extra[0][1])
            edr = (extra[0][0] / eln, extra[0][1] / eln)
            eslot = _hull2((edr[0] * eln * 0.58, edr[1] * eln * 0.58), 6.0,
                           (edr[0] * (eln + extra[1]), edr[1] * (eln + extra[1])), extra[1] * 0.9, n=11)
            body = body - _plate(pl, eslot, slot_w)
        return body

    arm_rod = arm(d_rod, uv_rod, 15.5, (0.34, 12.0), (0.70, 8.5), extra=(lug_uv, 14.0))
    arm_dmp = arm(d_dmp, uv_dmp, 15.0, (0.32, 12.5), (0.72, 8.5))

    hub = _beam(
        P + ax * d_lo, P + ax * d_hi,
        [(0.0, hub_r + 4.0, hub_r + 4.0), (0.055, hub_r + 4.0, hub_r + 4.0),
         (0.10, hub_r - 1.0, hub_r - 1.0), (0.5, hub_r - 2.5, hub_r - 2.5),
         (0.90, hub_r - 1.0, hub_r - 1.0), (0.945, hub_r + 4.0, hub_r + 4.0),
         (1.0, hub_r + 4.0, hub_r + 4.0)],
        thin=ex, n_top=2.0, n_bot=2.0,
    )
    strut = _beam(
        P + ax * d_rod + Vector(ex * uv_rod[0] + ey * uv_rod[1]) * 0.54,
        P + ax * d_dmp + Vector(ex * uv_dmp[0] + ey * uv_dmp[1]) * 0.54,
        [(0.0, 11.0, 8.5), (0.5, 8.5, 7.0), (1.0, 11.0, 8.5)], thin=ax,
    )

    body = _fuse([hub, arm_rod, arm_dmp, strut])
    # bearing bore, visible circlip groove, and the two rod-end bores
    grv = _cyl(P + ax * (d_hi - 9.0), ax, hub_r + 8.0, 3.2) - _cyl(P + ax * (d_hi - 9.0), ax, hub_r + 1.6, 5.0)
    body = _cut(body, [
        _cyl(P, ax, 9.6, (d_hi - d_lo) * 1.3),
        grv,
        _cyl(_p(p_rod), ax, BORE_R, plate_t * 2.0),
        _cyl(_p(p_damper), ax, BORE_R, plate_t * 2.0),
        _cyl(lug_pt, ax, BORE_R, plate_t * 2.0),
    ])
    return body, lug_pt, (d_lo, d_hi)


def _rocker_pin(pivot, axis, span):
    """The pivot shaft, proud of the hub at both ends."""
    P, ax = _p(pivot), _unit(axis)
    d_lo, d_hi = span
    a = P + ax * (d_lo - 26.0)
    b = P + ax * (d_hi + 22.0)
    return _fuse([_shaft(a, b, 9.4), _cyl(a, ax, 14.0, 6.0), _cyl(b, ax, 14.0, 6.0)])


def _rocker_carrier(pivot, axis, span, inboard, hub_r: float = 21.0):
    """Machined bearing carrier: an ear just outside each end of the hub, on a
    common rail that bolts to the tub / gearbox casing."""
    P, ax = _p(pivot), _unit(axis)
    d_lo, d_hi = span
    ex = _perp(ax, inboard)
    foot = (48.0, -14.0)
    outline = _hull_discs([((0.0, 0.0), hub_r + 12.0), (foot, 16.0),
                           ((foot[0] * 0.30, 34.0), 11.0)], n=12)
    ears = []
    for s in (d_lo - 15.0, d_hi + 15.0):
        pl = Plane(origin=P + ax * s, x_dir=ex, z_dir=ax)
        ears.append(_plate(pl, outline, 12.0))
    anchor = ex * foot[0] + ey_of(ax, ex) * foot[1]
    rail = _beam(
        P + ax * (d_lo - 20.0) + anchor, P + ax * (d_hi + 20.0) + anchor,
        [(0.0, 18.0, 10.0), (0.5, 14.0, 8.0), (1.0, 18.0, 10.0)], thin=ex,
        n_top=2.9, n_bot=2.9,
    )
    body = _fuse(ears + [rail])
    return _cut(body, [_cyl(P, ax, hub_r + 6.0, (d_hi - d_lo) + 90.0)])


# ==========================================================================
# damper
# ==========================================================================


def _damper(p_out, p_in, eye_axis):
    """A real damper: machined body, exposed rod, threaded adjuster with THE
    accent ring, bump-stop and end eyes. Returns [(solid, label, color), ...]."""
    a, b = _p(p_out), _p(p_in)
    u = (b - a).normalized()
    L = (b - a).length

    def at(t):
        return a + u * (L * t)

    h_out, ball_out = _rod_end(a, u, eye_axis, shank=20.0, neck=5.6)
    h_in, ball_in = _rod_end(b, -u, eye_axis, shank=20.0, neck=5.6)

    rod = _shaft(at(0.055), at(0.455), 7.0)
    bump = _beam(at(0.255), at(0.335), [(0.0, 8.0, 8.0), (0.25, 11.6, 11.6),
                                        (0.75, 11.6, 11.6), (1.0, 8.5, 8.5)],
                 thin=(0, 0, 1), n_top=2.0, n_bot=2.0)
    # threaded adjuster collar: stacked lands read as a thread at render scale
    lands = []
    for i in range(6):
        t = 0.395 + i * (14.0 / L)
        lands.append(_shaft(at(t), at(t + 8.4 / L), 17.4))
    collar = _fuse(lands + [_shaft(at(0.385), at(0.395 + 6 * 14.0 / L), 15.8)])
    ring = _shaft(at(0.383), at(0.383 + 4.2 / L), 18.9)
    body = _fuse([
        _beam(at(0.50), at(0.905),
              [(0.0, 16.4, 16.4), (0.04, 15.6, 15.6), (0.90, 15.6, 15.6),
               (0.94, 17.2, 17.2), (1.0, 17.2, 17.2)], thin=(0, 0, 1), n_top=2.0, n_bot=2.0),
        _shaft(at(0.60), at(0.74), 17.6),
    ])
    body = _cut(body, [_cyl(at(0.67), _perp(u, (0, 0, 1)), 4.6, 60.0)])
    kn = _perp(u, (0, 0, 1))
    knob = _fuse([
        _cyl(at(0.855) + kn * 16.0, kn, 9.2, 15.0),
        _cyl(at(0.855) + kn * 24.0, kn, 6.0, 9.0),
    ])
    return [
        (h_out, "damper_eye_out", spec.ANODIZED),
        (ball_out, "damper_ball_out", spec.ALLOY),
        (rod, "damper_rod", spec.ALLOY),
        (bump, "damper_bumpstop", spec.ANODIZED),
        (collar, "damper_adjuster", spec.ALLOY),
        (ring, "damper_ring", spec.ACCENT),
        (body, "damper_body", spec.ANODIZED),
        (knob, "damper_knob", spec.ALLOY),
        (h_in, "damper_eye_in", spec.ANODIZED),
        (ball_in, "damper_ball_in", spec.ALLOY),
    ]


# ==========================================================================
# anti-roll bar
# ==========================================================================


def _arb(tube_x, z, half_span: float, blade_len: float, blade_y: float,
         lug_pt, roll_deg: float = 26.0, aft: bool = False, mount_y: float = 86.0):
    """Blade-type ARB: torsion tube across the car, a flat blade at each end
    whose ANGLE sets the stiffness, and a short drop link to the rocker.

    Returns (centre bodies, left-side bodies) as [(solid, label, color)].
    """
    sgn = -1.0 if aft else 1.0
    tip_x = tube_x + sgn * blade_len
    tube = _beam(
        (tube_x, -half_span, z), (tube_x, half_span, z),
        [(0.0, 11.5, 11.5), (0.035, 13.0, 13.0), (0.12, 11.0, 11.0), (0.5, 10.4, 10.4),
         (0.88, 11.0, 11.0), (0.965, 13.0, 13.0), (1.0, 11.5, 11.5)],
        thin=(0, 0, 1), n_top=2.0, n_bot=2.0,
    )
    tube = tube - _shaft((tube_x, -half_span - 4, z), (tube_x, half_span + 4, z), 6.4)

    thin = Vector(0, math.sin(math.radians(roll_deg)), math.cos(math.radians(roll_deg)))
    blade = _beam(
        (tube_x + sgn * 20.0, blade_y, z), (tip_x, blade_y, z),
        [(0.0, 21.0, 3.9), (0.35, 20.0, 3.4), (0.78, 18.0, 3.0), (1.0, 15.0, 3.9)],
        thin=thin, n_top=2.6, n_bot=2.6,
    )
    adj_c = (tube_x + sgn * 19.0, blade_y, z)
    adjuster = _fuse([
        _plate(Plane(origin=_p(adj_c), x_dir=(0, 0, 1), z_dir=(1, 0, 0)),
               _scallop_pts(13.0, 2.0, 12, samples=96), 5.5),
        _cyl((tube_x + sgn * 7.5, blade_y, z), (1, 0, 0), 11.4, 15.0),
    ])
    # pillow block: a side-view profile around the tube, extruded across it
    mpl = Plane(origin=(tube_x, mount_y, z), x_dir=(1, 0, 0), z_dir=(0, -1, 0))
    mount = _cut(
        _plate(mpl, _hull_discs([((0.0, 0.0), 16.5), ((-13.0, 36.0), 8.5),
                                 ((13.0, 36.0), 8.5)], n=11), 28.0),
        [_shaft((tube_x, mount_y - 40, z), (tube_x, mount_y + 40, z), 10.8)],
    )
    tip = (tip_x, blade_y, z)
    link = _blade_rod(tip, tuple(lug_pt), 14.0, 24.0, 0.20,
                      (1, 0, 0), (1, 0, 0), shank=15.0, neck=4.6)
    centre = [(tube, "arb_tube", spec.TITANIUM)]
    side = [
        (blade, "arb_blade", spec.TITANIUM),
        (adjuster, "arb_adjuster", spec.ALLOY),
        (mount, "arb_mount", spec.ANODIZED),
        (link[0], "arb_droplink", spec.TITANIUM),
        (link[1], "arb_droplink_eye_up", spec.ANODIZED),
        (link[2], "arb_droplink_ball_up", spec.ALLOY),
        (link[3], "arb_droplink_eye_lo", spec.ANODIZED),
        (link[4], "arb_droplink_ball_lo", spec.ALLOY),
    ]
    return centre, side


# ==========================================================================
# FRONT — pushrod
# ==========================================================================

F_LUG_DEG = 88.0
F_LUG_R = 56.0
F_ARB_TUBE_X = 130.0
F_ARB_BLADE_Y = 190.0


def _front_left():
    """Every LEFT-side front body: [(solid, label, color)]."""
    out = []
    LB, UB = spec.F_LOWER_BALL, spec.F_UPPER_BALL
    LF, LA = spec.F_LOWER_IN_FWD, spec.F_LOWER_IN_AFT
    UF, UA = spec.F_UPPER_IN_FWD, spec.F_UPPER_IN_AFT
    PO, PI = spec.F_PUSHROD_OUT, spec.F_PUSHROD_IN

    # ---- lower wishbone: wide-based A-arm, forward leg the fatter one -----
    # The two legs are rolled in OPPOSITE senses about their own axes, so the
    # A-arm catches light as two sculpted aerofoils instead of one flat plane.
    # Nothing caps the outboard ends: each blade noses off exactly on the ball
    # joint and dies inside the upright's eye, which is what "blends into the
    # upright" means. A boss there would only be a lump around somebody else's
    # machining.
    lo_fwd = _leg(LF, LB, 134.0, 46.0, t_max=17.5, t_tip=7.0, neck=13.0,
                  roll=10.0, bow=22.0, bow_dir=(1, 0, 0))
    lo_aft = _leg(LA, LB, 100.0, 40.0, t_max=13.8, t_tip=6.2, neck=11.0,
                  roll=-8.0, bow=16.0, bow_dir=(-1, 0, 0))
    lf_ax = _blade_dirs(_p(LB) - _p(LF), 10.0)[1]
    la_ax = _blade_dirs(_p(LB) - _p(LA), -8.0)[1]
    lower = _fuse([
        lo_fwd, lo_aft,
        _eye(LF, lf_ax, od=22.0, width=15.0),
        _eye(LA, la_ax, od=20.0, width=13.0),
    ])
    # pushrod pickup: a pedestal off the forward leg, gusseted to the aft leg
    root_f = _p(LF) + (_p(LB) - _p(LF)) * ((PO[1] - LF[1]) / (LB[1] - LF[1]))
    root_a = _p(LA) + (_p(LB) - _p(LA)) * ((PO[1] - LA[1]) / (LB[1] - LA[1]))
    lower = _fuse([
        lower,
        _beam(root_f, _p(PO), [(0.0, 24.0, 9.5), (0.5, 16.0, 8.0), (1.0, 11.5, 7.0)],
              thin=(0, 1, 0), n_top=2.5, n_bot=2.5),
        _beam(root_a + Vector(0, 0, 2.0), _p(PO), [(0.0, 12.5, 6.0), (1.0, 10.0, 6.5)],
              thin=(0, 1, 0), n_top=2.5, n_bot=2.5),
    ])
    po_jaw = Vector(1, 0, 0)
    po_fork, po_slot = _fork_boss(PO, po_jaw, _p(PI) - _p(PO),
                                  od=22.0, width=25.0, gap=13.0, throat=4.0)
    lower = _fuse([lower, po_fork])
    lower = _cut(lower, [
        po_slot,
        _cyl(PO, po_jaw, BORE_R, 60.0),
        _cyl(LF, lf_ax, BORE_R, 60.0),
        _cyl(LA, la_ax, BORE_R, 60.0),
    ])
    out.append((lower, "f_lower_wishbone", spec.TITANIUM))

    # ---- upper wishbone: the lightly loaded one, and it should look it ----
    up_fwd = _leg(UF, UB, 112.0, 40.0, t_max=13.6, t_tip=5.8, neck=11.0,
                  roll=9.0, bow=20.0, bow_dir=(1, 0, 0))
    up_aft = _leg(UA, UB, 84.0, 34.0, t_max=11.2, t_tip=5.0, neck=9.5,
                  roll=-7.0, bow=15.0, bow_dir=(-1, 0, 0))
    uf_ax = _blade_dirs(_p(UB) - _p(UF), 9.0)[1]
    ua_ax = _blade_dirs(_p(UB) - _p(UA), -7.0)[1]
    upper = _fuse([
        up_fwd, up_aft,
        _eye(UF, uf_ax, od=20.0, width=13.0),
        _eye(UA, ua_ax, od=19.0, width=11.5),
    ])
    upper = _cut(upper, [
        _cyl(UF, uf_ax, BORE_R, 56.0),
        _cyl(UA, ua_ax, BORE_R, 56.0),
    ])
    out.append((upper, "f_upper_wishbone", spec.TITANIUM))

    # ---- pushrod ---------------------------------------------------------
    pr = _blade_rod(PO, PI, 26.0, 64.0, 0.165, (1, 0, 0), spec.F_ROCKER_AXIS,
                    roll=6.0, shank=20.0)
    out += [
        (pr[0], "f_pushrod", spec.TITANIUM),
        (pr[1], "f_pushrod_eye_out", spec.ANODIZED),
        (pr[2], "f_pushrod_ball_out", spec.ALLOY),
        (pr[3], "f_pushrod_eye_in", spec.ANODIZED),
        (pr[4], "f_pushrod_ball_in", spec.ALLOY),
    ]

    # ---- rocker ----------------------------------------------------------
    rk, lug, span = _rocker(spec.F_ROCKER_PIVOT, spec.F_ROCKER_AXIS,
                            PI, spec.F_DAMPER_OUT, F_LUG_DEG, F_LUG_R)
    out.append((rk, "f_rocker", spec.TITANIUM))
    out.append((_rocker_carrier(spec.F_ROCKER_PIVOT, spec.F_ROCKER_AXIS, span, (0, -1, 0)),
                "f_rocker_carrier", spec.ANODIZED))

    # ---- damper ----------------------------------------------------------
    for solid, label, color in _damper(spec.F_DAMPER_OUT, spec.F_DAMPER_IN, spec.F_ROCKER_AXIS):
        out.append((solid, "f_" + label, color))

    # ---- torsion bar -----------------------------------------------------
    # It IS the rocker's pivot shaft: through the bearing bore at
    # F_TORSION_BAR, then inboard along the rocker axis to a splined end and a
    # reaction anchor on the tub. No separate pivot pin exists, because on a
    # torsion-bar car there isn't one.
    ax = _unit(spec.F_ROCKER_AXIS)
    tb0 = _p(spec.F_TORSION_BAR) + ax * (span[1] + 26.0)
    tb1 = _p(spec.F_TORSION_BAR) + ax * (span[0] - 258.0)
    out.append((_fuse([
        _beam(tb0, tb1, [(0.0, 9.4, 9.4), (0.035, 7.6, 7.6), (0.30, 6.6, 6.6),
                         (0.62, 6.6, 6.6), (0.95, 7.6, 7.6), (1.0, 9.2, 9.2)],
              thin=(0, 0, 1), n_top=2.0, n_bot=2.0),
        _cyl(tb0, ax, 14.0, 6.0),
    ]), "f_torsion_bar", spec.TITANIUM))
    spl = _cyl(tb1 + ax * 14.0, ax, 13.0, 30.0)
    for i in range(12):
        a = 2.0 * math.pi * i / 12.0
        r = _perp(ax, (0, 0, 1)) * (13.0 * math.sin(a)) + _perp(ax, (0, 1, 0)) * (13.0 * math.cos(a))
        spl = spl - _shaft(tb1 + ax * 4.0 + r, tb1 + ax * 30.0 + r, 2.3)
    out.append((spl, "f_torsion_spline", spec.ALLOY))
    out.append((_cut(_beam(tb1 + ax * 22.0, tb1 - ax * 16.0,
                           [(0.0, 24.0, 24.0), (1.0, 27.0, 27.0)], thin=(0, 0, 1),
                           n_top=2.9, n_bot=2.9),
                     [_shaft(tb1 + ax * 40.0, tb1 - ax * 40.0, 13.4)]),
                "f_torsion_anchor", spec.ANODIZED))

    # ---- inboard pickup clevises ----------------------------------------
    for pt, ball, label, gap, rl in (
        (LF, LB, "f_clevis_lower_fwd", 17.0, 10.0),
        (LA, LB, "f_clevis_lower_aft", 15.0, -8.0),
        (UF, UB, "f_clevis_upper_fwd", 15.0, 9.0),
        (UA, UB, "f_clevis_upper_aft", 13.5, -7.0),
    ):
        d = _p(ball) - _p(pt)
        br, bolt = _clevis(pt, d, _blade_dirs(d, rl)[1], gap=gap)
        out.append((br, label, spec.ANODIZED))
        out.append((bolt, label + "_bolt", spec.STEEL))
    br, bolt = _clevis(spec.F_DAMPER_IN, _p(spec.F_DAMPER_OUT) - _p(spec.F_DAMPER_IN),
                       spec.F_ROCKER_AXIS, gap=FORK_GAP, jaw_r=11.5, reach=28.0)
    out.append((br, "f_clevis_damper_in", spec.ANODIZED))
    out.append((bolt, "f_clevis_damper_in_bolt", spec.STEEL))

    # ---- rod-end retaining bolts at the rocker ---------------------------
    for pt, label in ((PI, "f_bolt_pushrod_in"), (spec.F_DAMPER_OUT, "f_bolt_damper_out"), (lug, "f_bolt_arb_lug")):
        out.append((_fuse([
            _cyl(pt, ax, BORE_R - 0.35, 42.0),
            _cyl(_p(pt) + ax * 21.0, ax, 9.2, 5.2),
            _cyl(_p(pt) - ax * 20.0, ax, 8.4, 4.4),
        ]), label, spec.STEEL))

    return out, lug


def build_suspension_front():
    """Front pushrod corner, both sides — everything but the rack and rods."""
    left, lug = _front_left()
    kids = []
    for solid, label, color in left:
        kids += lib.pair(lib.styled(solid, label, color), label, color)

    centre, side = _arb(F_ARB_TUBE_X, spec.F_ARB_Z, F_ARB_BLADE_Y + 18.0, 110.0,
                        F_ARB_BLADE_Y, lug, roll_deg=26.0, aft=False, mount_y=86.0)
    for solid, label, color in centre:
        kids.append(lib.styled(solid, "f_" + label, color))
    for solid, label, color in side:
        kids += lib.pair(lib.styled(solid, "f_" + label, color), "f_" + label, color)
    return lib.group("suspension_front", kids)


# ==========================================================================
# REAR — pullrod (the opposite diagonal: HIGH outboard, DOWN to a low rocker)
# ==========================================================================

R_LUG_DEG = -20.0
R_LUG_R = 70.0
R_ARB_TUBE_X = -3196.0
R_ARB_BLADE_Y = 228.0


def _rear_left():
    out = []
    LB, UB = spec.R_LOWER_BALL, spec.R_UPPER_BALL
    LF, LA = spec.R_LOWER_IN_FWD, spec.R_LOWER_IN_AFT
    UF, UA = spec.R_UPPER_IN_FWD, spec.R_UPPER_IN_AFT
    PO, PI = spec.R_PULLROD_OUT, spec.R_PULLROD_IN
    TI, TO = spec.R_TOELINK_IN, spec.R_TOELINK_OUT

    # ---- lower wishbone --------------------------------------------------
    lo_fwd = _leg(LF, LB, 138.0, 46.0, t_max=17.8, t_tip=7.0, neck=13.0,
                  roll=9.0, bow=22.0, bow_dir=(1, 0, 0))
    lo_aft = _leg(LA, LB, 102.0, 40.0, t_max=14.0, t_tip=6.2, neck=11.0,
                  roll=-7.0, bow=16.0, bow_dir=(-1, 0, 0))
    lf_ax = _blade_dirs(_p(LB) - _p(LF), 9.0)[1]
    la_ax = _blade_dirs(_p(LB) - _p(LA), -7.0)[1]
    lower = _fuse([
        lo_fwd, lo_aft,
        _eye(LF, lf_ax, od=22.0, width=15.0),
        _eye(LA, la_ax, od=20.0, width=13.0),
    ])
    lower = _cut(lower, [
        _cyl(LF, lf_ax, BORE_R, 60.0),
        _cyl(LA, la_ax, BORE_R, 60.0),
    ])
    out.append((lower, "r_lower_wishbone", spec.TITANIUM))

    # ---- upper wishbone, with the pullrod pickup on the aft leg ----------
    up_fwd = _leg(UF, UB, 118.0, 42.0, t_max=14.2, t_tip=6.0, neck=11.5,
                  roll=8.0, bow=20.0, bow_dir=(1, 0, 0))
    up_aft = _leg(UA, UB, 90.0, 36.0, t_max=11.8, t_tip=5.2, neck=10.0,
                  roll=-6.0, bow=14.0, bow_dir=(-1, 0, 0))
    uf_ax = _blade_dirs(_p(UB) - _p(UF), 8.0)[1]
    po_jaw = _blade_dirs(_p(UB) - _p(UA), -6.0)[1]
    # the pullrod pickup is MILLED INTO the aft leg, not bolted onto it
    po_fork, po_slot = _fork_boss(PO, po_jaw, _p(PI) - _p(PO),
                                  od=22.0, width=25.0, gap=13.0, throat=4.0)
    upper = _fuse([
        up_fwd, up_aft,
        _eye(UF, uf_ax, od=20.0, width=13.5),
        _eye(UA, po_jaw, od=19.0, width=12.0),
        po_fork,
    ])
    upper = _cut(upper, [
        po_slot,
        _cyl(UF, uf_ax, BORE_R, 58.0),
        _cyl(UA, po_jaw, BORE_R, 56.0),
        _cyl(PO, po_jaw, BORE_R, 60.0),
    ])
    out.append((upper, "r_upper_wishbone", spec.TITANIUM))

    # ---- pullrod ---------------------------------------------------------
    pl = _blade_rod(PO, PI, 26.0, 66.0, 0.165, po_jaw, spec.R_ROCKER_AXIS,
                    roll=6.0, shank=20.0)
    out += [
        (pl[0], "r_pullrod", spec.TITANIUM),
        (pl[1], "r_pullrod_eye_out", spec.ANODIZED),
        (pl[2], "r_pullrod_ball_out", spec.ALLOY),
        (pl[3], "r_pullrod_eye_in", spec.ANODIZED),
        (pl[4], "r_pullrod_ball_in", spec.ALLOY),
    ]

    # ---- toe link (the rear's track rod) ---------------------------------
    tl = _blade_rod(TI, TO, 22.0, 50.0, 0.16, (0, 0, 1), (0, 0, 1), roll=4.0,
                    shank=20.0, bow=22.0, bow_dir=(1, 0, 0))
    out += [
        (tl[0], "r_toelink", spec.TITANIUM),
        (tl[1], "r_toelink_eye_in", spec.ANODIZED),
        (tl[2], "r_toelink_ball_in", spec.ALLOY),
        (tl[3], "r_toelink_eye_out", spec.ANODIZED),
        (tl[4], "r_toelink_ball_out", spec.ALLOY),
    ]

    # ---- rocker ----------------------------------------------------------
    rk, lug, span = _rocker(spec.R_ROCKER_PIVOT, spec.R_ROCKER_AXIS,
                            PI, spec.R_DAMPER_OUT, R_LUG_DEG, R_LUG_R,
                            hub_r=19.0, plate_t=34.0, slot_w=14.5)
    out.append((rk, "r_rocker", spec.TITANIUM))
    out.append((_rocker_pin(spec.R_ROCKER_PIVOT, spec.R_ROCKER_AXIS, span), "r_rocker_pin", spec.ALLOY))
    out.append((_rocker_carrier(spec.R_ROCKER_PIVOT, spec.R_ROCKER_AXIS, span, (0, -1, 0), hub_r=19.0),
                "r_rocker_carrier", spec.ANODIZED))

    # ---- damper ----------------------------------------------------------
    for solid, label, color in _damper(spec.R_DAMPER_OUT, spec.R_DAMPER_IN, spec.R_ROCKER_AXIS):
        out.append((solid, "r_" + label, color))

    # ---- inboard pickup clevises ----------------------------------------
    for pt, ball, label, gap, rl in (
        (LF, LB, "r_clevis_lower_fwd", 17.0, 9.0),
        (LA, LB, "r_clevis_lower_aft", 15.0, -7.0),
        (UF, UB, "r_clevis_upper_fwd", 15.5, 8.0),
        (UA, UB, "r_clevis_upper_aft", 14.0, -6.0),
        (TI, TO, "r_clevis_toelink_in", FORK_GAP, 4.0),
    ):
        d = _p(ball) - _p(pt)
        br, bolt = _clevis(pt, d, _blade_dirs(d, rl)[1], gap=gap)
        out.append((br, label, spec.ANODIZED))
        out.append((bolt, label + "_bolt", spec.STEEL))
    br, bolt = _clevis(spec.R_DAMPER_IN, _p(spec.R_DAMPER_OUT) - _p(spec.R_DAMPER_IN),
                       spec.R_ROCKER_AXIS, gap=FORK_GAP, jaw_r=11.5, reach=28.0)
    out.append((br, "r_clevis_damper_in", spec.ANODIZED))
    out.append((bolt, "r_clevis_damper_in_bolt", spec.STEEL))

    ax = _unit(spec.R_ROCKER_AXIS)
    for pt, label in ((PI, "r_bolt_pullrod_in"), (spec.R_DAMPER_OUT, "r_bolt_damper_out"), (lug, "r_bolt_arb_lug")):
        out.append((_fuse([
            _cyl(pt, ax, BORE_R - 0.35, 40.0),
            _cyl(_p(pt) + ax * 20.0, ax, 9.2, 5.2),
            _cyl(_p(pt) - ax * 19.0, ax, 8.4, 4.4),
        ]), label, spec.STEEL))

    return out, lug


def build_suspension_rear():
    """Rear pullrod corner, both sides, toe links included."""
    left, lug = _rear_left()
    kids = []
    for solid, label, color in left:
        kids += lib.pair(lib.styled(solid, label, color), label, color)

    centre, side = _arb(R_ARB_TUBE_X, spec.R_ARB_Z, R_ARB_BLADE_Y + 16.0, 104.0,
                        R_ARB_BLADE_Y, lug, roll_deg=32.0, aft=True, mount_y=78.0)
    for solid, label, color in centre:
        kids.append(lib.styled(solid, "r_" + label, color))
    for solid, label, color in side:
        kids += lib.pair(lib.styled(solid, "r_" + label, color), "r_" + label, color)
    return lib.group("suspension_rear", kids)


# ==========================================================================
# TRACK ROD — its own child, the sidecar re-aims it during steering
# ==========================================================================


def build_track_rod(side: str):
    s = 1.0 if side == "left" else -1.0
    inner = (spec.F_RACK_END[0], s * spec.F_RACK_END[1], spec.F_RACK_END[2])
    outer = (spec.F_TRACKROD_OUT[0], s * spec.F_TRACKROD_OUT[1], spec.F_TRACKROD_OUT[2])
    blade, h0, b0, h1, b1 = _blade_rod(inner, outer, 22.0, 54.0, 0.16,
                                       (0, 0, 1), (0, 0, 1), roll=5.0 * s, shank=20.0)
    return lib.group(f"track_rod_{side}", [
        lib.styled(blade, f"track_rod:{side}", spec.TITANIUM),
        lib.styled(h0, f"track_rod_eye_in:{side}", spec.ANODIZED),
        lib.styled(b0, f"track_rod_ball_in:{side}", spec.ALLOY),
        lib.styled(h1, f"track_rod_eye_out:{side}", spec.ANODIZED),
        lib.styled(b1, f"track_rod_ball_out:{side}", spec.ALLOY),
    ])


# ==========================================================================
# STEERING RACK — its own child, it translates laterally with steering
# ==========================================================================

RACK_HALF = 250.0
BOOT_OUT = 302.0


def build_steering_rack():
    x, z = spec.F_RACK_X, spec.F_RACK_Z
    end_y = spec.F_RACK_END[1]

    housing = _beam(
        (x, -RACK_HALF, z), (x, RACK_HALF, z),
        [(0.0, 25.0, 18.0), (0.045, 31.0, 23.0), (0.13, 28.0, 21.0), (0.30, 27.0, 20.0),
         (0.44, 31.0, 24.0), (0.56, 31.0, 24.0), (0.70, 27.0, 20.0), (0.87, 28.0, 21.0),
         (0.955, 31.0, 23.0), (1.0, 25.0, 18.0)],
        thin=(0, 0, 1), n_top=2.9, n_bot=2.7,
    )
    # machined top rib + the clamp saddles the rack ships with
    housing = _fuse([
        housing,
        _beam((x - 6.0, -186.0, z + 17.0), (x - 6.0, 186.0, z + 17.0),
              [(0.0, 12.0, 9.0), (0.5, 14.0, 11.0), (1.0, 12.0, 9.0)], thin=(0, 0, 1),
              n_top=2.8, n_bot=2.8),
    ])
    for sy in (-152.0, 152.0):
        housing = _fuse([housing,
                         _beam((x, sy, z - 26.0), (x, sy, z + 34.0),
                               [(0.0, 30.0, 26.0), (0.55, 26.0, 22.0), (1.0, 30.0, 15.0)],
                               thin=(1, 0, 0), n_top=2.9, n_bot=2.9)])
    housing = _cut(housing, [_shaft((x, -RACK_HALF - 40, z), (x, RACK_HALF + 40, z), 11.6)])

    # pinion housing, angled up-and-aft toward the column
    pin_ax = _unit((-0.46, 0.0, 0.89))
    pin_c = _p((x, 74.0, z + 8.0))
    pinion = _cut(_fuse([
        _beam(pin_c, pin_c + pin_ax * 76.0,
              [(0.0, 26.0, 26.0), (0.30, 21.0, 21.0), (0.80, 19.0, 19.0),
               (0.90, 23.0, 23.0), (1.0, 23.0, 23.0)], thin=(0, 1, 0), n_top=2.0, n_bot=2.0),
    ]), [_shaft(pin_c, pin_c + pin_ax * 100.0, 9.6)])
    column = _fuse([
        _shaft(pin_c + pin_ax * 40.0, pin_c + pin_ax * 132.0, 9.0),
        _cyl(pin_c + pin_ax * 118.0, pin_ax, 15.0, 16.0),
    ])

    bodies = [
        (housing, "rack_housing", spec.ANODIZED),
        (pinion, "rack_pinion_housing", spec.ANODIZED),
        (column, "rack_pinion_shaft", spec.ALLOY),
    ]

    for s in (1.0, -1.0):
        # concertina boot — ruled, so each fold is a crisp cone
        sts = [(0.0, 19.0, 19.0), (0.035, 19.0, 19.0)]
        for i in range(5):
            t0 = 0.08 + i * 0.176
            sts += [(t0, 13.0, 13.0), (t0 + 0.088, 20.4, 20.4)]
        sts += [(0.965, 12.6, 12.6), (1.0, 12.6, 12.6)]
        boot = _beam((x, s * (RACK_HALF + 2.0), z), (x, s * BOOT_OUT, z), sts,
                     thin=(0, 0, 1), n_top=2.0, n_bot=2.0, ruled=True)
        bodies.append((boot, f"rack_boot_{'l' if s > 0 else 'r'}", spec.RUBBER))
        # rack end shaft out to the track-rod ball, and its clevis
        shaft = _shaft((x, s * (BOOT_OUT - 12.0), z), (x, s * (end_y - 2.0), z), 8.4)
        bodies.append((shaft, f"rack_end_{'l' if s > 0 else 'r'}", spec.ALLOY))
        br, bolt = _clevis((x, s * end_y, z), (0.0, s, 0.0), (0, 0, 1),
                           gap=FORK_GAP, jaw_r=11.5, jaw_t=5.5, reach=20.0, base_r=10.0)
        bodies.append((br, f"rack_end_clevis_{'l' if s > 0 else 'r'}", spec.ANODIZED))
        bodies.append((bolt, f"rack_end_bolt_{'l' if s > 0 else 'r'}", spec.STEEL))

    return lib.group("steering_rack", [lib.styled(b, n, c) for b, n, c in bodies])
