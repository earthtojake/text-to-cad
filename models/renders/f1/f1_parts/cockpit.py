"""Cockpit interior — seat, headrest, steering wheel, pedals, harness, furniture.

Everything lives inside the survival cell's cockpit opening:
`spec.COCKPIT_OPENING_FRONT_X` .. `spec.COCKPIT_OPENING_REAR_X`, under
`spec.COCKPIT_RIM_Z`, inside the tub's inner flanks (|y| < 230). The seat and
the headrest pads are `lib.body_loft()` bathtub sections; the wheel, pedals and
harness hardware are built from `lib.swept_plate()` paths and lofted section
stacks so nothing is a bare extrusion.

The one accent on this part is the steering wheel's quick-release ring.
"""

from __future__ import annotations

import math

from build123d import Circle, Plane, Spline, Vector, make_face

from . import lib, spec

# ==========================================================================
# local helpers
# ==========================================================================


def _sym(pts):
    """Close a half outline (top-centre -> down the +u side -> bottom-centre)."""
    p = list(pts)
    return p + [(-u, v) for (u, v) in reversed(p[1:-1])]


def _sec(plane, pts):
    """Closed periodic section face on an arbitrary plane from (u, v) points."""
    p = [(float(a), float(b)) for a, b in pts]
    if abs(p[0][0] - p[-1][0]) < 1e-9 and abs(p[0][1] - p[-1][1]) < 1e-9:
        p = p[:-1]
    return plane * make_face(Spline(*p, periodic=True))


def _prism_estimate(faces):
    """Rough prism volume of a section stack — a floor for loft sanity."""
    total = 0.0
    prev = None
    for f in faces:
        lo, hi = lib.bbox(f)
        c = tuple((lo[i] + hi[i]) / 2.0 for i in range(3))
        a = f.area
        if prev is not None:
            total += 0.5 * (a + prev[1]) * math.dist(c, prev[0])
        prev = (c, a)
    return total


def _solid(faces, smooth=False, tol=20.0):
    """Loft a section stack into a positively-oriented solid.

    A stack lofted against its own section normals comes out inside-out, so
    the reversed winding is used when the first attempt gives negative volume.

    A ruled loft is always exact but leaves a visible crease at every station.
    A smooth loft gives one continuous surface, but past ~25 sections OCC's
    ThruSections quietly returns a self-intersecting shape (measured: metres
    of bulge, or a tenth of the correct volume) while still reporting valid.
    So `smooth=True` builds BOTH and only keeps the smooth one when its tight
    bounds and its volume agree with the ruled reference.
    """
    fs = [f for f in faces if f is not None]
    base = seq = None
    err = None
    for order in (fs, list(reversed(fs))):
        try:
            out = lib.body_loft(order, ruled=True)
        except Exception as exc:  # noqa: BLE001 - retry the other winding
            err = exc
            continue
        if out is not None and out.is_valid and out.volume > 0:
            base, seq = out, order
            break
    if base is None:
        raise err if err is not None else RuntimeError("cockpit: loft failed")
    est = _prism_estimate(fs)
    if est > 0.0 and base.volume < 0.35 * est:
        raise RuntimeError(
            "cockpit: degenerate loft (%d sections, %.0f mm3 vs ~%.0f expected)"
            % (len(fs), base.volume, est))
    if not smooth or len(seq) < 3:
        return base
    try:
        fine = lib.body_loft(seq, ruled=False)
    except Exception:
        return base
    if fine is None or not fine.is_valid or not 0.62 < fine.volume / base.volume < 1.12:
        return base
    lo, hi = lib.bbox(base)   # conservative for splines, but so is `fine`
    fl, fh = lib.bbox(fine)
    if max(max(lo[i] - fl[i], fh[i] - hi[i]) for i in range(3)) > tol:
        return base
    return fine


def _ruled(faces):
    return _solid(faces)


def _cr(p0, p1, p2, p3, t):
    return 0.5 * (2 * p1 + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3)
                  * t * t + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3)


def _resample(rows, n):
    """Catmull-Rom resample of a station table so ruled lofts read smooth."""
    r = [tuple(float(v) for v in row) for row in rows]
    m = len(r)
    if m < 2:
        return r
    out = []
    for k in range(n):
        u = k / (n - 1) * (m - 1)
        i = min(int(u), m - 2)
        t = u - i
        p0, p1 = r[max(i - 1, 0)], r[i]
        p2, p3 = r[i + 1], r[min(i + 2, m - 1)]
        out.append(tuple(_cr(a, b, c, d, t) for a, b, c, d in zip(p0, p1, p2, p3)))
    return out


def _disc_stack(plane, rings):
    """Loft circles: rings = [(offset_along_normal, radius), ...]. Ruled."""
    return _ruled([plane.offset(o) * Circle(r) for o, r in rings])


def _rbox(plane, length, height, depth, corner, taper=0.94):
    """Rounded slab: `length` x `height` in-plane, `depth` along the normal."""
    c = min(corner, length / 2.0 - 0.05, height / 2.0 - 0.05)
    return _ruled([
        _sec(plane, lib.rounded_plate_pts(length, height, c)),
        _sec(plane.offset(depth),
             lib.rounded_plate_pts(length * taper, height * taper, c * taper)),
    ])


def _wave_pts(r, amp, lobes):
    """Knurl / spline outline: r(theta) = r + amp*cos(lobes*theta)."""
    n = lobes * 4
    out = []
    for i in range(n):
        a = 2.0 * math.pi * i / n
        rr = r + amp * math.cos(lobes * a)
        out.append((rr * math.cos(a), rr * math.sin(a)))
    return out


def _unit2(v):
    m = math.hypot(v[0], v[1]) or 1.0
    return (v[0] / m, v[1] / m)


def _round_poly(corners, radii, arc_n=7, edge_n=4):
    """Dense outline of a rounded polygon.

    A periodic spline through a sparse outline wanders between its points and
    the shape goes soft — which is exactly what a machined steering wheel must
    not do. Sampling the arcs and putting points along the straight runs pins
    the spline to the intended shape.
    """
    n = len(corners)
    parts = []
    for i in range(n):
        p = corners[i]
        vi = _unit2((p[0] - corners[i - 1][0], p[1] - corners[i - 1][1]))
        vo = _unit2((corners[(i + 1) % n][0] - p[0],
                     corners[(i + 1) % n][1] - p[1]))
        d = max(-1.0, min(1.0, -vi[0] * vo[0] - vi[1] * vo[1]))
        phi = math.acos(d)
        r = radii[i]
        if phi < 1e-6 or phi > math.pi - 1e-6 or r <= 0:
            parts.append(([p], p))
            continue
        t = r / math.tan(phi / 2.0)
        t1 = (p[0] - vi[0] * t, p[1] - vi[1] * t)
        t2 = (p[0] + vo[0] * t, p[1] + vo[1] * t)
        bis = _unit2((vo[0] - vi[0], vo[1] - vi[1]))
        h = r / math.sin(phi / 2.0)
        c = (p[0] + bis[0] * h, p[1] + bis[1] * h)
        a0 = math.atan2(t1[1] - c[1], t1[0] - c[0])
        a1 = math.atan2(t2[1] - c[1], t2[0] - c[0])
        while a1 - a0 > math.pi:
            a1 -= 2 * math.pi
        while a1 - a0 < -math.pi:
            a1 += 2 * math.pi
        arc = [(c[0] + r * math.cos(a0 + (a1 - a0) * k / (arc_n - 1)),
                c[1] + r * math.sin(a0 + (a1 - a0) * k / (arc_n - 1)))
               for k in range(arc_n)]
        parts.append((arc, t2))
    out = []
    for i in range(n):
        arc, _ = parts[i]
        out += arc
        nxt = parts[(i + 1) % n][0][0]
        for k in range(1, edge_n):
            f = k / edge_n
            out.append((arc[-1][0] + (nxt[0] - arc[-1][0]) * f,
                        arc[-1][1] + (nxt[1] - arc[-1][1]) * f))
    return out


def _sweep(path, sec_at, up=(0, 0, 1), samples=None, smooth=True):
    """Loft a section along a polyline; `sec_at(t)` returns (u, v) points.

    `up` is either a fixed vector or a callable taking the station point.
    """
    pts = [Vector(*p) for p in
           (_resample([tuple(q) for q in path], samples) if samples else path)]
    faces = []
    n = len(pts)
    for i, p in enumerate(pts):
        if i == 0:
            tan = pts[1] - pts[0]
        elif i == n - 1:
            tan = pts[-1] - pts[-2]
        else:
            tan = pts[i + 1] - pts[i - 1]
        u = up(p) if callable(up) else up
        faces.append(_sec(lib.plate_plane(p, tan, u), sec_at(i / (n - 1))))
    return _solid(faces, smooth=smooth)


# ==========================================================================
# 1. DRIVER SEAT — moulded carbon bathtub shell
#
# One profile family per station: a central ridge, a trough either side of it
# (thigh trough forward, shoulder-blade relief aft) and a bolster wall that
# steepens outboard. The shell is a closed BAND lofted through those stations,
# so the rolled rim falls out of the section itself — no post-boolean fillets.
# ==========================================================================

# x, surface z on the centreline, half width, bolster rise, trough y, ridge h
_SEAT_STATIONS = (
    (-828.0, 344.0, 138.0, 26.0, 68.0, 9.0),
    (-848.0, 337.0, 152.0, 46.0, 73.0, 21.0),
    (-890.0, 328.0, 160.0, 50.0, 76.0, 24.0),
    (-944.0, 315.0, 168.0, 54.0, 78.0, 25.0),
    (-1000.0, 301.0, 175.0, 60.0, 81.0, 24.0),
    (-1052.0, 287.0, 181.0, 66.0, 83.0, 22.0),
    (-1102.0, 272.0, 186.0, 73.0, 85.0, 19.0),
    (-1148.0, 256.0, 190.0, 81.0, 87.0, 15.0),
    (-1190.0, 240.0, 193.0, 90.0, 89.0, 10.0),
    (-1222.0, 224.0, 195.0, 99.0, 92.0, 6.0),
    (-1248.0, 210.0, 197.0, 106.0, 95.0, 4.0),
    (-1272.0, 208.0, 198.0, 112.0, 98.0, 4.0),
    (-1298.0, 218.0, 198.0, 117.0, 100.0, 5.0),
    (-1326.0, 240.0, 198.0, 120.0, 102.0, 7.0),
    (-1354.0, 272.0, 197.0, 121.0, 104.0, 10.0),
    (-1380.0, 306.0, 195.0, 118.0, 106.0, 13.0),
    (-1408.0, 344.0, 190.0, 122.0, 108.0, 14.0),
    (-1432.0, 380.0, 184.0, 118.0, 110.0, 12.0),
)

_SEAT_T = 16.0  # shell laminate thickness
_PAD_T = 15.0  # upholstery pad thickness
_SEAT_DENSE = _resample(_SEAT_STATIONS, 25)


def _seat_params(x):
    """Linear blend of the station table at x (clamped)."""
    t = _SEAT_DENSE
    if x >= t[0][0]:
        return t[0][1:]
    if x <= t[-1][0]:
        return t[-1][1:]
    for i in range(len(t) - 1):
        if t[i + 1][0] <= x <= t[i][0]:
            f = (t[i][0] - x) / (t[i][0] - t[i + 1][0])
            return tuple(
                t[i][1 + k] + (t[i + 1][1 + k] - t[i][1 + k]) * f
                for k in range(5)
            )
    return t[-1][1:]


def _prof_z(p, y):
    """Driver-facing surface height at (station params, y)."""
    zc, w, rise, tr_y, tr_d = p
    ay = abs(y)
    if ay <= tr_y:
        return zc + tr_d * (0.5 + 0.5 * math.cos(math.pi * ay / tr_y))
    s = min((ay - tr_y) / max(w - tr_y, 1e-6), 1.6)
    return zc + rise * (s**2.2)


def seat_surface(x, y):
    """Public: the seat's driver-facing surface — the harness rides on it."""
    return _prof_z(_seat_params(x), y)


def _seat_slope(x):
    """dz/dx of the seat surface, one-sided at the ends.

    A centred difference clamps at the last station and halves the reported
    slope there, which makes the shell's laminate thickness jump between the
    final two sections and self-intersects the loft.
    """
    lo, hi = _SEAT_DENSE[-1][0], _SEAT_DENSE[0][0]
    a = max(min(x - 7.0, hi), lo)
    b = max(min(x + 7.0, hi), lo)
    if b - a < 1e-6:
        return 0.0
    return (_seat_params(b)[0] - _seat_params(a)[0]) / (b - a)


def _seat_normal(x, y):
    e = 5.0
    fx = (seat_surface(x + e, y) - seat_surface(x - e, y)) / (2 * e)
    fy = (seat_surface(x, y + e) - seat_surface(x, y - e)) / (2 * e)
    return Vector(-fx, -fy, 1.0).normalized()


_TROUGH_F = (0.0, 0.40, 0.72, 1.0)
_WALL_F = (0.18, 0.40, 0.62, 0.82, 1.0)


def _inner_pts(p, w_scale=1.0):
    """Half the driver-facing profile: centreline out to the bolster top."""
    w_end = p[1] * w_scale
    tr_y = p[3]
    pts = [(tr_y * f, _prof_z(p, tr_y * f)) for f in _TROUGH_F]
    for s in _WALL_F:
        y = tr_y + (w_end - tr_y) * s
        pts.append((y, _prof_z(p, y)))
    return pts


def _offset_path(pts, dist, ksl):
    """Offset a half profile outward (away from the driver) by `dist`."""
    out = []
    n = len(pts)
    for i in range(n):
        y, z = pts[i]
        if i == 0:
            ty, tz = 1.0, 0.0  # forced flat so the spine stays on y = 0
        elif i == n - 1:
            ty, tz = pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]
        else:
            ty, tz = pts[i + 1][0] - pts[i - 1][0], pts[i + 1][1] - pts[i - 1][1]
        m = math.hypot(ty, tz) or 1.0
        ny, nz = tz / m, -ty / m
        out.append((y + ny * dist, z + nz * dist * ksl))
    return out


def _band_loop(inner, t, ksl, roll=5):
    """Closed symmetric band: inner surface, rolled rim, outer surface back."""
    outer = _offset_path(inner, t, ksl)
    pi, po = inner[-1], outer[-1]
    dy, dz = po[0] - pi[0], po[1] - pi[1]
    r = math.hypot(dy, dz) / 2.0
    cy, cz = pi[0] + dy / 2.0, pi[1] + dz / 2.0
    ny, nz = (dy / (2 * r), dz / (2 * r)) if r > 1e-6 else (1.0, 0.0)
    ty, tz = inner[-1][0] - inner[-2][0], inner[-1][1] - inner[-2][1]
    d = ty * ny + tz * nz
    ty, tz = ty - d * ny, tz - d * nz
    m = math.hypot(ty, tz) or 1.0
    ty, tz = ty / m, tz / m
    arc = []
    for i in range(1, roll + 1):
        a = math.pi * i / (roll + 1)
        ca, sa = math.cos(a), math.sin(a)
        arc.append((cy + r * (-ny * ca + ty * sa), cz + r * (-nz * ca + tz * sa)))
    left = list(inner) + arc + list(reversed(outer))
    right = [(-y, z) for (y, z) in reversed(left)]
    return left + right[1:-1]


_KSL_MAX = 1.95  # see _seat_band_face


def _seat_band_face(x, w_scale, lift, t):
    """One closed band section of the shell (or the pad) at station x.

    The laminate is offset normal to the surface inside the section plane and
    scaled by 1/cos(slope) vertically. On the steep part of the backrest that
    factor reaches 2.5, and a 40 mm-tall band between two 20 mm-apart sections
    makes OCC's ruled loft twist. Capping it thins the laminate there by a few
    millimetres — invisible — and the loft stays clean.
    """
    p = _seat_params(x)
    ksl = min(math.sqrt(1.0 + _seat_slope(x) ** 2), _KSL_MAX)
    inner = _inner_pts(p, w_scale)
    if lift:
        inner = _offset_path(inner, -lift, ksl)
    return lib.section_face(x, _band_loop(inner, t, ksl))


def _seat_stations(x_min=None):
    return [r[0] for r in _SEAT_DENSE if x_min is None or r[0] >= x_min]


def _belt_slot(origin, normal, length, height, corner, reach=64.0):
    """Through-cutter for a webbing slot, normal to the local seat surface."""
    n = Vector(normal).normalized()
    up = (0, 0, 1) if abs(n.Z) < 0.9 else (1, 0, 0)
    o = Vector(origin)
    pts = lib.rounded_plate_pts(length, height, corner)
    return _ruled([
        _sec(lib.plate_plane(o - n * reach, n, up), pts),
        _sec(lib.plate_plane(o + n * reach, n, up), pts),
    ])


def _lap_slot_y(x, side=1.0):
    p = _seat_params(x)
    return (p[3] + (p[1] - p[3]) * 0.74) * side


def _seat():
    bodies = []

    shell = _solid(
        [_seat_band_face(x, 1.0, 0.0, _SEAT_T) for x in _seat_stations()],
        smooth=True,
    )

    cutters = []
    for side in (1.0, -1.0):
        sx, sy = -1378.0, 116.0 * side
        cutters.append(_belt_slot((sx, sy, seat_surface(sx, sy)),
                                  _seat_normal(sx, sy), 68.0, 17.0, 7.5))
        lx, ly = -1236.0, _lap_slot_y(-1236.0, side)
        cutters.append(_belt_slot((lx, ly, seat_surface(lx, ly)),
                                  _seat_normal(lx, ly), 58.0, 15.0, 6.5))
    for c in cutters:
        # a boolean that reports valid can still come back self-intersecting,
        # so a slot only lands if it removed a plausible amount of material
        try:
            cut = shell - c
        except Exception:
            continue
        if cut is not None and cut.is_valid and 0.90 < cut.volume / shell.volume < 1.0:
            shell = cut
    bodies.append(lib.styled(shell, "seat_shell", spec.CARBON_WEAVE))

    pad = _solid([
        _seat_band_face(x, 0.84, _PAD_T + 1.0, _PAD_T)
        for x in _seat_stations(-1350.0)
    ], smooth=True)
    bodies.append(lib.styled(pad, "seat_pad", spec.SEAT))
    return bodies


# ==========================================================================
# 2. HEADREST — energy-absorbing surround: rear pad, two side pads, a carbon
#    backing plate that wraps them and four quick-release fixings.
# ==========================================================================

_HR_X0 = -1288.0
_HR_A = 150.0
_HR_B = 198.0


def _hr_point(theta):
    return (_HR_X0 - _HR_A * math.cos(theta), _HR_B * math.sin(theta))


def _hr_outward(theta):
    return Vector(-_HR_A * math.cos(theta), _HR_B * math.sin(theta),
                  0.0).normalized()


def _headrest():
    bodies = []

    rear = _solid([
        lib.section_face(x, lib.superellipse_pts(hw, hh, 3.0, 2.6, 0.0, cz))
        for x, hw, hh, cz in _resample((
            (-1380.0, 112.0, 50.0, 604.0),
            (-1392.0, 138.0, 66.0, 609.0),
            (-1410.0, 148.0, 74.0, 612.0),
            (-1426.0, 142.0, 69.0, 611.0),
            (-1436.0, 118.0, 53.0, 607.0),
        ), 15)
    ], smooth=True)
    bodies.append(lib.styled(rear, "headrest_pad_rear", spec.SEAT))

    side = _solid([
        lib.section_face(x, lib.superellipse_pts(hw, hh, 3.2, 2.8, cy, cz))
        for x, cy, hw, hh, cz in _resample((
            (-1266.0, 146.0, 19.0, 42.0, 580.0),
            (-1294.0, 154.0, 29.0, 58.0, 594.0),
            (-1330.0, 160.0, 34.0, 68.0, 604.0),
            (-1368.0, 165.0, 36.0, 73.0, 610.0),
            (-1402.0, 166.0, 35.0, 73.0, 612.0),
            (-1428.0, 162.0, 27.0, 61.0, 610.0),
        ), 19)
    ], smooth=True)
    bodies += lib.pair(side, "headrest_pad_side", spec.SEAT)

    plate = []
    for a_deg, h, cz in _resample((
            (-72.0, 140.0, 582.0), (-52.0, 162.0, 588.0), (-28.0, 180.0, 592.0),
            (0.0, 188.0, 594.0), (28.0, 180.0, 592.0), (52.0, 162.0, 588.0),
            (72.0, 140.0, 582.0)), 19):
        th = math.radians(a_deg)
        x, y = _hr_point(th)
        tan = (_HR_A * math.sin(th), _HR_B * math.cos(th), 0.0)
        plate.append(_sec(lib.plate_plane((x, y, cz), tan, (0, 0, 1)),
                          lib.rounded_plate_pts(15.0, h, 5.0)))
    bodies.append(lib.styled(_solid(plate, smooth=True), "headrest_backplate",
                             spec.CARBON))

    for a_deg, dz in ((36.0, 56.0), (36.0, -56.0), (66.0, 40.0), (66.0, -40.0)):
        for side_s in (1.0, -1.0):
            th = math.radians(a_deg) * side_s
            x, y = _hr_point(th)
            out = _hr_outward(th)
            base = Vector(x, y, 596.0 + dz) + out * 7.0
            pl = Plane(origin=base, x_dir=(0, 0, 1), z_dir=out)
            bodies.append(lib.styled(
                _disc_stack(pl, ((0.0, 14.0), (5.0, 14.0), (6.4, 11.0),
                                 (12.0, 10.5), (13.4, 7.0))),
                "headrest_qr_boss", spec.ALLOY))
            bodies.append(lib.styled(
                _rbox(pl.offset(12.4), 9.0, 34.0, 4.4, 2.0),
                "headrest_qr_lever", spec.STEEL))
    return bodies


# ==========================================================================
# 3. STEERING WHEEL — the hero. Local frame:
#       u = lateral (driver's right positive), v = wheel "up",
#       c = out of the face, toward the driver.
#    Tilted 22 deg back from vertical, so a camera looking down into the
#    cockpit reads the whole button layout instead of the wheel's edge.
# ==========================================================================

_W_C = Vector(-640.0, 0.0, 560.0)
_W_TILT = math.radians(22.0)
_W_UP = Vector(math.sin(_W_TILT), 0.0, math.cos(_W_TILT))
_W_N = Vector(-math.cos(_W_TILT), 0.0, math.sin(_W_TILT))  # toward the driver
_W_LAT = Vector(0.0, -1.0, 0.0)  # driver's right


def _wpt(u, v, c=0.0):
    return _W_C + _W_LAT * u + _W_UP * v + _W_N * c


def _wplane(c=0.0, u=0.0, v=0.0):
    return Plane(origin=_wpt(u, v, c), x_dir=_W_LAT, z_dir=_W_N)


# A machined shield: wide flat top, straight flanks, tapered base. Crisp.
_FACE = _round_poly(
    ((-104.0, 92.0), (104.0, 92.0), (104.0, -30.0), (86.0, -88.0),
     (-86.0, -88.0), (-104.0, -30.0)),
    (32.0, 32.0, 20.0, 26.0, 26.0, 20.0),
)


def _button(pl, r, cap_color):
    """Machined bezel + domed pushbutton; `pl` normal is the press axis."""
    h, hd = 3.4, 0.52 * r
    rr = (r * r + hd * hd) / (2.0 * hd)
    z0 = h + hd - rr
    rings = [(0.0, r), (h, r)]
    for i in range(1, 7):
        z = h + hd * (i / 6.0) * 0.985
        rings.append((z, math.sqrt(max(rr * rr - (z - z0) ** 2, 0.16))))
    return [
        lib.styled(
            _disc_stack(pl, ((0.0, r + 3.8), (2.4, r + 3.6), (3.2, r + 1.5))),
            "wheel_button_bezel", spec.ANODIZED),
        lib.styled(_disc_stack(pl, rings), "wheel_button", cap_color),
    ]


def _rotary(pl, r, lobes):
    """Knurled rotary switch: knurl body, machined cap, raised pointer."""
    body = _ruled([
        _sec(pl, _wave_pts(r * 1.06, 1.0, lobes)),
        _sec(pl.offset(2.4), _wave_pts(r * 1.06, 1.0, lobes)),
        _sec(pl.offset(3.2), _wave_pts(r, 1.0, lobes)),
        _sec(pl.offset(11.5), _wave_pts(r * 0.985, 1.0, lobes)),
    ])
    cap = _disc_stack(pl.offset(11.5),
                      ((0.0, r * 0.90), (3.0, r * 0.86), (4.2, r * 0.70)))
    mark_pl = Plane(origin=pl.offset(15.5).origin + pl.x_dir * (r * 0.34),
                    x_dir=pl.x_dir, z_dir=pl.z_dir)
    return [
        lib.styled(body, "wheel_rotary_knurl", spec.ANODIZED),
        lib.styled(cap, "wheel_rotary_cap", spec.ALLOY),
        lib.styled(_rbox(mark_pl, r * 0.62, 3.6, 1.8, 1.2),
                   "wheel_rotary_mark", spec.STEEL),
    ]


def _grip(side):
    """Moulded handgrip: canted forward, finger-contoured along its length."""
    n = 21

    def at(t):
        return _wpt((106.0 + 40.0 * t * (1.0 - t) * 1.5) * side,
                    -58.0 + 124.0 * t, 20.0 - 34.0 * t)

    def sec(t):
        # three finger contours: the section swells at the fingers, pinches between
        f = 1.0 + 0.036 * math.cos(2 * math.pi * (3.0 * t - 0.12))
        g = 1.0 - 0.14 * t * t  # slims toward the top of the grip
        return lib.rounded_plate_pts(30.0 * f * g, 58.0 * f, 13.0)

    return _sweep([at(i / (n - 1)) for i in range(n)], sec, up=_W_N)


def _paddle(u0, u1, v0, v1, c0, c1, h0, h1, t0, t1):
    n = 13
    # u runs out, v and c ease away — the blade curves back behind the rim
    path = [_wpt(spec.lerp(u0, u1, t),
                 spec.lerp(v0, v1, t**1.7),
                 spec.lerp(c0, c1, t**1.5))
            for t in (i / (n - 1) for i in range(n))]
    return _sweep(
        path,
        lambda t: lib.rounded_plate_pts(spec.lerp(t0, t1, t),
                                        spec.lerp(h0, h1, t), 1.55),
        up=_W_UP)


def _steering_wheel():
    bodies = []

    bodies.append(lib.styled(
        _solid([
            _sec(_wplane(c), [(u * s, v * s) for u, v in _FACE])
            for c, s in _resample(((-20.0, 0.880), (-14.0, 0.940),
                                   (-8.0, 0.972), (3.0, 1.000),
                                   (12.0, 0.985), (16.0, 0.955),
                                   (19.0, 0.900)), 15)
        ], smooth=True),
        "wheel_body", spec.CARBON))

    for side in (1.0, -1.0):
        bodies.append(lib.styled(
            _grip(side), "wheel_grip:%s" % ("right" if side > 0 else "left"),
            spec.CARBON_WEAVE))

    for side in (1.0, -1.0):
        bodies.append(lib.styled(
            _rbox(_wplane(9.0, 103.0 * side, 4.0), 30.0, 62.0, 17.0, 8.0,
                  taper=0.80),
            "wheel_grip_clamp", spec.ANODIZED))

    bodies.append(lib.styled(
        _rbox(_wplane(12.5, 0.0, 30.0), 130.0, 58.0, 8.0, 8.0, taper=0.92),
        "wheel_display_bezel", spec.ANODIZED))
    bodies.append(lib.styled(
        _rbox(_wplane(19.4, 0.0, 30.0), 116.0, 44.0, 1.8, 4.0, taper=0.995),
        "wheel_display", spec.GLASS))

    bodies.append(lib.styled(
        _rbox(_wplane(11.0, 0.0, 78.0), 160.0, 16.0, 7.0, 6.0),
        "wheel_led_channel", spec.ANODIZED))
    for i in range(12):
        bodies.append(lib.styled(
            _rbox(_wplane(17.4, -74.8 + 13.6 * i, 78.0), 9.4, 9.0, 1.8, 2.6,
                  taper=0.99),
            "wheel_led_lens", spec.GLASS))

    # three rotaries per side, descending in size — the layout's hierarchy
    for side in (1.0, -1.0):
        for u, v, r, lobes in ((80.0, 54.0, 19.0, 28),
                               (84.0, -8.0, 16.0, 24),
                               (72.0, -58.0, 14.0, 20)):
            bodies += _rotary(_wplane(13.5, u * side, v), r, lobes)

    # 6x2 centre matrix, a 4-wide bottom row, two outboard buttons
    layout = []
    for v in (-16.0, -46.0):
        for u in (12.0, 32.0, 52.0):
            layout += [(u, v, 8.5, spec.STEEL), (-u, v, 8.5, spec.STEEL)]
    for u in (18.0, 42.0):
        layout += [(u, -70.0, 10.5, spec.ALLOY), (-u, -70.0, 10.5, spec.ALLOY)]
    layout += [(86.0, 26.0, 8.5, spec.ALLOY), (-86.0, 26.0, 8.5, spec.ALLOY)]
    for u, v, r, col in layout:
        bodies += _button(_wplane(13.5, u, v), r, col)

    for side in (1.0, -1.0):
        bodies.append(lib.styled(
            _paddle(28.0 * side, 100.0 * side, 2.0, -16.0, -30.0, -47.0,
                    46.0, 34.0, 5.4, 4.2),
            "wheel_paddle_shift", spec.CARBON))
        bodies.append(lib.styled(
            _paddle(24.0 * side, 80.0 * side, -46.0, -54.0, -27.0, -35.0,
                    26.0, 20.0, 4.4, 3.6),
            "wheel_paddle_clutch", spec.CARBON))
        for u, v, c in ((26.0 * side, 2.0, -30.0), (22.0 * side, -46.0, -27.0)):
            bodies.append(lib.styled(
                _disc_stack(
                    Plane(origin=_wpt(u, v, c) - _W_LAT * (9.0 * side),
                          x_dir=_W_UP, z_dir=_W_LAT * side),
                    ((0.0, 5.0), (3.0, 6.6), (15.0, 6.6), (18.0, 5.0))),
                "wheel_paddle_pivot", spec.ALLOY))

    hub = _wplane(0.0)
    bodies.append(lib.styled(
        _disc_stack(hub.offset(-16.0),
                    ((0.0, 50.0), (-4.0, 49.0), (-16.0, 41.0), (-18.0, 38.0))),
        "wheel_hub_boss", spec.ANODIZED))
    bodies.append(lib.styled(
        _ruled([_sec(hub.offset(-34.0), _wave_pts(37.0, 2.6, 18)),
                _sec(hub.offset(-58.0), _wave_pts(37.0, 2.6, 18))]),
        "wheel_qr_collar", spec.ALLOY))
    bodies.append(lib.styled(  # THE accent
        _ruled([_sec(hub.offset(-56.0), _wave_pts(47.0, 1.4, 34)),
                _sec(hub.offset(-67.0), _wave_pts(47.0, 1.4, 34))]),
        "wheel_qr_ring", spec.ACCENT))
    bodies.append(lib.styled(
        _disc_stack(hub.offset(-56.0),
                    ((0.0, 29.0), (-16.0, 29.0), (-20.0, 25.0), (-22.0, 22.0))),
        "wheel_qr_nose", spec.ALLOY))
    for i in range(3):
        a = math.radians(90.0 + 120.0 * i)
        bodies.append(lib.styled(
            _disc_stack(_wplane(-14.0, 34.0 * math.cos(a), 34.0 * math.sin(a)),
                        ((0.0, 5.4), (-3.6, 5.4), (-4.6, 4.2))),
            "wheel_hub_bolt", spec.STEEL))
    return bodies


# ==========================================================================
# 4. PEDALS — machined faces, drilled and ribbed, on pivoting arms with
#    clevises, pushrods, master cylinders and reservoirs.
# ==========================================================================

_PEDAL_Y = 95.0
_PEDAL_N = Vector(-math.cos(math.radians(34.0)), 0.0,
                  math.sin(math.radians(34.0))).normalized()


def _pedal_set(side, label):
    bodies = []
    y = _PEDAL_Y * side
    pl = lib.plate_plane((-578.0, y, 344.0), _PEDAL_N, (0, 0, 1))

    plate = _ruled([
        _sec(pl, lib.rounded_plate_pts(60.0, 116.0, 13.0)),
        _sec(pl.offset(7.0), lib.rounded_plate_pts(56.0, 112.0, 12.0)),
    ])
    for row in range(4):
        for col in (-1, 1):
            o = (pl.origin + pl.x_dir * (col * 15.0)
                 + pl.y_dir * (-40.5 + 27.0 * row) - pl.z_dir * 8.0)
            hole = _disc_stack(
                Plane(origin=o, x_dir=pl.x_dir, z_dir=pl.z_dir),
                ((0.0, 7.0), (24.0, 7.0)))
            try:
                cut = plate - hole
            except Exception:
                continue
            if cut is not None and cut.is_valid and 0.8 < cut.volume / plate.volume < 1.0:
                plate = cut
    bodies.append(lib.styled(plate, "pedal_face_%s" % label, spec.ALLOY))

    for v in (-52.0, -26.0, 0.0, 26.0, 52.0):
        bodies.append(lib.styled(
            _rbox(Plane(origin=pl.offset(7.0).origin + pl.y_dir * v,
                        x_dir=pl.x_dir, z_dir=pl.z_dir),
                  56.0, 5.2, 2.6, 2.4, taper=0.78),
            "pedal_tread_%s" % label, spec.TITANIUM))

    bodies.append(lib.styled(
        _sweep([(-548.0, y, 402.0), (-566.0, y, 372.0), (-580.0, y, 330.0),
                (-586.0, y, 300.0)],
               lambda t: lib.rounded_plate_pts(
                   spec.lerp(26.0, 20.0, t), spec.lerp(16.0, 12.0, t), 5.0),
               up=(1, 0, 0), samples=11),
        "pedal_arm_%s" % label, spec.CARBON))
    bodies.append(lib.styled(
        _disc_stack(Plane(origin=(-548.0, y - 15.0 * side, 402.0),
                          x_dir=(0, 0, 1), z_dir=(0, side, 0)),
                    ((0.0, 6.5), (3.5, 10.0), (26.0, 10.0), (29.5, 6.5))),
        "pedal_pivot_%s" % label, spec.TITANIUM))
    bodies.append(lib.styled(
        _rbox(Plane(origin=(-566.0, y - 11.0 * side, 316.0),
                    x_dir=(1, 0, 0), z_dir=(0, side, 0)),
              44.0, 22.0, 20.0, 7.0, taper=0.86),
        "pedal_clevis_%s" % label, spec.ANODIZED))

    bodies.append(lib.styled(
        _sweep([(-568.0, y, 318.0), (-514.0, y, 308.0), (-462.0, y, 300.0)],
               lambda t: lib.rounded_plate_pts(
                   spec.lerp(11.0, 9.0, t), spec.lerp(11.0, 9.0, t), 4.4),
               up=(0, 0, 1)),
        "pedal_pushrod_%s" % label, spec.STEEL))

    bodies.append(lib.styled(
        _disc_stack(Plane(origin=(-462.0, y, 300.0), x_dir=(0, 1, 0),
                          z_dir=(1, 0, -0.17)),
                    ((0.0, 10.0), (5.0, 16.0), (12.0, 17.0), (62.0, 17.0),
                     (68.0, 13.0), (72.0, 10.0))),
        "master_cylinder_%s" % label, spec.ANODIZED))
    bodies.append(lib.styled(
        _disc_stack(Plane(origin=(-412.0, y, 318.0), x_dir=(1, 0, 0),
                          z_dir=(0, 0, 1)),
                    ((0.0, 7.0), (5.0, 12.0), (34.0, 13.0), (39.0, 10.0),
                     (42.0, 7.0))),
        "reservoir_%s" % label, spec.CARBON_MATTE))
    return bodies


def _pedals():
    return _pedal_set(1.0, "brake") + _pedal_set(-1.0, "throttle")


# ==========================================================================
# 5. BELTS — six-point harness. Flat webbing swept along the seat's own
#    surface, meeting at a machined rotary buckle.
# ==========================================================================

_BUCKLE_X = -1244.0
_WEB_LIFT = 15.0


def _belt_path(x0, x1, y0, y1, side, ease, n=15):
    """Evenly-spaced strap centreline riding `_WEB_LIFT` above the seat.

    Kept smooth and monotone on purpose: a flat 46-50 mm band swept round a
    tight in-plane corner self-intersects and the loft dies.
    """
    out = []
    for i in range(n):
        t = i / (n - 1)
        x = spec.lerp(x0, x1, t)
        y = spec.lerp(y0, y1, t**ease) * side
        out.append((x, y, seat_surface(x, y) + _WEB_LIFT))
    return out


def _webbing(path, width, label):
    return lib.styled(
        _sweep(path, lambda t: lib.rounded_plate_pts(width, 5.0, 2.1),
               up=lambda p: _seat_normal(p.X, p.Y)),
        label, spec.BELT)


def _adjuster(path, frac, width):
    i = max(1, min(len(path) - 2, int(round(frac * (len(path) - 1)))))
    p = Vector(*path[i])
    tan = Vector(*path[i + 1]) - Vector(*path[i - 1])
    n = _seat_normal(p.X, p.Y)
    return lib.styled(
        _rbox(lib.plate_plane(p - n * 4.0, tan, n), width + 12.0, 16.0, 9.5,
              4.0, taper=0.9),
        "harness_adjuster", spec.ALLOY)


def _belts():
    bodies = []
    bz = seat_surface(_BUCKLE_X, 0.0) + 26.0

    for side in (1.0, -1.0):
        sh = _belt_path(-1384.0, -1250.0, 114.0, 32.0, side, 1.55)
        bodies.append(_webbing(sh, 48.0, "harness_shoulder"))
        bodies.append(_adjuster(sh, 0.30, 48.0))

        ly = _lap_slot_y(-1234.0, side)
        lap = _belt_path(-1234.0, -1248.0, ly, 34.0, side, 1.0, n=11)
        bodies.append(_webbing(lap, 44.0, "harness_lap"))
        bodies.append(_adjuster(lap, 0.45, 44.0))

        sub = _belt_path(-1122.0, -1236.0, 46.0, 20.0, side, 1.35, n=11)
        bodies.append(_webbing(sub, 38.0, "harness_antisub"))
        bodies.append(_adjuster(sub, 0.30, 38.0))

        bodies.append(lib.styled(
            _rbox(lib.plate_plane(
                (-1118.0, 46.0 * side,
                 seat_surface(-1118.0, 46.0 * side) + 4.0), (1, 0, 0), (0, 0, 1)),
                48.0, 28.0, 7.0, 7.0, taper=0.86),
            "harness_anchor", spec.ANODIZED))

    bn = _seat_normal(_BUCKLE_X, 0.0)
    bp = Plane(origin=(_BUCKLE_X, 0.0, bz - 12.0),
               x_dir=Vector(0, 1, 0).cross(bn).normalized(), z_dir=bn)
    bodies.append(lib.styled(
        _disc_stack(bp, ((0.0, 34.0), (4.0, 38.0), (14.0, 38.0), (18.0, 34.0),
                         (20.0, 30.0))),
        "harness_buckle", spec.ALLOY))
    bodies.append(lib.styled(
        _ruled([_sec(bp.offset(13.0), _wave_pts(40.0, 1.2, 30)),
                _sec(bp.offset(17.5), _wave_pts(40.0, 1.2, 30))]),
        "harness_buckle_ring", spec.ANODIZED))
    bodies.append(lib.styled(
        _rbox(bp.offset(20.0), 54.0, 17.0, 9.0, 6.0, taper=0.82),
        "harness_buckle_handle", spec.ALLOY))
    return bodies


# ==========================================================================
# 6. COCKPIT FURNITURE — steering column with a universal joint, drink-bottle
#    mount, heel rest, electronics box.
# ==========================================================================

_BOTTLE_CY = 170.0
_BOTTLE_CZ = 250.0


def _heel_pts(z):
    return _sym([
        (0.0, z + 12.0), (52.0, z + 11.0), (98.0, z + 13.0), (126.0, z + 22.0),
        (132.0, z + 10.0), (104.0, z + 1.0), (56.0, z - 1.0), (0.0, z),
    ])


def _furniture():
    bodies = []

    # --- steering column, forward and down to the rack ---------------------
    bodies.append(lib.styled(
        _sweep([(-568.0, 0.0, 531.0), (-470.0, 0.0, 527.0),
                (-372.0, 0.0, 523.0), (-330.0, 0.0, 521.0)],
               lambda t: lib.rounded_plate_pts(
                   spec.lerp(26.0, 23.0, t), spec.lerp(26.0, 23.0, t), 11.0),
               up=(0, 0, 1), samples=9),
        "steering_column_upper", spec.CARBON))
    bodies.append(lib.styled(
        _sweep([(-292.0, 0.0, 519.0), (-100.0, 0.0, 512.0),
                (110.0, 0.0, spec.F_RACK_Z)],
               lambda t: lib.rounded_plate_pts(
                   spec.lerp(22.0, 19.0, t), spec.lerp(22.0, 19.0, t), 9.0),
               up=(0, 0, 1), samples=9),
        "steering_column_lower", spec.CARBON))
    for x in (-322.0, -300.0):
        bodies.append(lib.styled(
            _rbox(Plane(origin=(x, -15.0, 520.0), x_dir=(0, 0, 1),
                        z_dir=(0, 1, 0)), 30.0, 34.0, 30.0, 9.0, taper=0.84),
            "column_uj_yoke", spec.ALLOY))
    bodies.append(lib.styled(
        _disc_stack(Plane(origin=(-311.0, -22.0, 520.0), x_dir=(1, 0, 0),
                          z_dir=(0, 1, 0)),
                    ((0.0, 6.0), (3.0, 7.5), (41.0, 7.5), (44.0, 6.0))),
        "column_uj_cross", spec.STEEL))

    # --- drink bottle, wrap strap and bracket ------------------------------
    bodies.append(lib.styled(
        _solid([
            lib.section_face(
                x, lib.superellipse_pts(hw, hh, 2.8, 2.4, _BOTTLE_CY, _BOTTLE_CZ))
            for x, hw, hh in _resample(
                ((-704.0, 20.0, 40.0), (-716.0, 31.0, 56.0),
                 (-746.0, 34.0, 60.0), (-782.0, 30.0, 55.0),
                 (-796.0, 19.0, 38.0)), 15)
        ], smooth=True),
        "drink_bottle", spec.SEAT))
    band = []
    for i in range(19):
        a = math.radians(-150.0 + 300.0 * i / 18.0)
        band.append((-746.0,
                     _BOTTLE_CY + 38.0 * math.copysign(
                         abs(math.cos(a)) ** (2.0 / 2.8), math.cos(a)),
                     _BOTTLE_CZ + 64.0 * math.copysign(
                         abs(math.sin(a)) ** (2.0 / 2.8), math.sin(a))))
    bodies.append(lib.styled(
        _sweep(band, lambda t: lib.rounded_plate_pts(5.0, 30.0, 2.2),
               up=(1, 0, 0)),
        "drink_bottle_strap", spec.BELT))
    bodies.append(lib.styled(
        _rbox(Plane(origin=(-746.0, 206.0, _BOTTLE_CZ), x_dir=(1, 0, 0),
                    z_dir=(0, 1, 0)), 74.0, 116.0, 9.0, 16.0, taper=0.9),
        "drink_bottle_bracket", spec.ANODIZED))

    # --- heel rest ----------------------------------------------------------
    bodies.append(lib.styled(
        _solid([
            lib.section_face(x, _heel_pts(z))
            for x, z in _resample(
                ((-618.0, 268.0), (-664.0, 252.0), (-712.0, 236.0),
                 (-760.0, 224.0)), 11)
        ], smooth=True),
        "heel_rest", spec.CARBON_MATTE))
    for x, z in ((-650.0, 266.0), (-686.0, 254.0), (-722.0, 242.0)):
        bodies.append(lib.styled(
            _rbox(Plane(origin=(x, 0.0, z), x_dir=(0, 1, 0), z_dir=(0, 0, 1)),
                  208.0, 11.0, 3.6, 4.4, taper=0.78),
            "heel_rest_tread", spec.TITANIUM))

    # --- electronics box ahead of the pedals --------------------------------
    bodies.append(lib.styled(
        _solid([
            lib.section_face(x, [(u, v + 236.0)
                                 for u, v in lib.rounded_plate_pts(w, h, 11.0)])
            for x, w, h in ((-442.0, 152.0, 48.0), (-452.0, 166.0, 56.0),
                            (-536.0, 166.0, 56.0), (-546.0, 152.0, 48.0))
        ]),
        "electronics_box", spec.CARBON_MATTE))
    for y in (-50.0, 0.0, 50.0):
        bodies.append(lib.styled(
            _disc_stack(Plane(origin=(-546.0, y, 236.0), x_dir=(0, 1, 0),
                              z_dir=(-1, 0, 0)),
                        ((0.0, 11.0), (6.0, 11.0), (8.0, 8.5), (15.0, 8.5))),
            "electronics_connector", spec.ANODIZED))
    return bodies


# ==========================================================================


def build_cockpit():
    return lib.group("cockpit", [
        *_seat(),
        *_headrest(),
        *_steering_wheel(),
        *_pedals(),
        *_belts(),
        *_furniture(),
    ])
