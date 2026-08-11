"""Powertrain -- transverse 60 deg V12, ITB intake, wrapped headers, transaxle.

Layout note (why transverse).  The brief fixes the block at (-1500, 0, ~500)
with the crank along Y and the transaxle behind it.  That is Miura lineage, and
in this package it is also the only arrangement that keeps the driveshafts
STRAIGHT on the rear axle line: the final drive sits under the nose of the
crankcase, right on ``S.REAR_AXLE_X``, and the gear cluster runs back to the
tail underneath and behind the engine.

The consequence that matters visually is the intake valley.  With the crank
along Y the 60 deg vee opens straight UP at the engine-cover glass, so the
twelve polished velocity stacks read as two clean rows of six from above and
from the rear three-quarter -- the money shot the brief asks for.

Everything is kept under Z = 880 (engine deck) and inside |Y| < 820.
"""

from __future__ import annotations

import math
from bisect import bisect_left

from build123d import (
    Axis,
    Circle,
    Cylinder,
    Line,
    Location,
    Plane,
    Polyline,
    Pos,
    RectangleRounded,
    Rot,
    Spline,
    Vector,
    loft,
    make_face,
    mirror,
    revolve,
    sweep,
)

import cadgen

from hypercar_parts import surfaces as S  # noqa: F401  (package datums)
from hypercar_parts.context import group
from hypercar_parts import palette as P
from hypercar_parts.palette import style

# ---------------------------------------------------------------------------
# hard points
# ---------------------------------------------------------------------------

X_E = -1500.0          # crank centre, X
Z_CRANK = 382.0        # crank centre, Z  (rear hub sits at 385.9 -- deliberate)
V_ANGLE = 30.0         # half of the 60 deg included vee
CA = math.cos(math.radians(V_ANGLE))
SA = math.sin(math.radians(V_ANGLE))

BORE_PITCH = 108.0
Y_CYL = [(i - 2.5) * BORE_PITCH for i in range(6)]     # -270 .. +270
Y_END = 374.0                                          # block half length

ITB_U = 62.0           # stack row offset from the crank plane
ITB_Z = 718.0          # throttle-body base, seated into the plenum crown
ITB_TILT = 10.0        # stacks splay outward as they rise

PORT_D = 292.0         # exhaust port: along the bank axis...
PORT_W = 74.0          # ...sunk just inside the bank's outer face
TUBE_R = 19.0

# The collector, the megaphone and the tip are ONE straight run: the six
# primaries per side bunch into a mouth behind the gearbox and the taper aims
# directly at the tip exit, so from every angle the exhaust reads as one line
# instead of a cone plus a bent pipe.
COLL_M = Vector(-2090.0, 300.0, 496.0)          # mouth centre (|y|)
COLL_N = Vector(-0.9623, -0.1750, 0.2086)       # unit axis (y flips per side)
COLL_END_T = 196.0                              # megaphone ends here
TIP_T = 297.0                                   # ...tip exit here

# Materials.  One extra tone either side of the palette's engine greys so the
# block / head / cover / plenum / stack sequence reads as a value gradient
# climbing toward the glass, with bronze as the only warm note.
BLOCK_C = P.ENGINE
HEAD_C = "#4A5058"
COVER_C = "#6C737A"
PLENUM_C = P.PLENUM
POLISH_C = "#C6CDD4"       # mirror-polished velocity stacks
THROTTLE_C = "#7E858C"
CASE_C = "#5A6067"
CASE_DARK = "#454B52"
RUBBER_C = "#292D33"
HEADER_C = "#6E747B"       # heat-tinted titanium primaries -- deliberately
COLLECT_C = P.TITANIUM     # a value ramp so the nest reads dark and the tip
TIP_C = P.ALUMINIUM        # is the only bright note back there


# ---------------------------------------------------------------------------
# frames and lofting helpers
# ---------------------------------------------------------------------------


def _bank_xz(s, d, w):
    """(x, z) at bank-axis distance ``d`` and outward-lateral offset ``w``.

    ``s`` = +1 forward bank, -1 rearward bank.  Bank axis is
    ``(s*sin30, 0, cos30)``; outward lateral is ``(s*cos30, 0, -sin30)``.
    """
    return (X_E + s * (SA * d + CA * w), Z_CRANK + CA * d - SA * w)


def _bank_plane(s, d, w, y):
    x, z = _bank_xz(s, d, w)
    return Plane(origin=(x, y, z), x_dir=(s * CA, 0.0, -SA), z_dir=(0.0, -s, 0.0))


def _bank_loft(s, stations, ruled=True):
    """Rounded-rect sections stacked along Y in one bank's frame.

    stations: ``(y, w0, w1, d0, d1, radius)``
    """
    faces = []
    for (y, w0, w1, d0, d1, r) in stations:
        pl = _bank_plane(s, 0.5 * (d0 + d1), 0.5 * (w0 + w1), y)
        faces.append(pl * RectangleRounded(w1 - w0, d1 - d0, r))
    return loft(faces, ruled=ruled)


def _xz_loft(stations, ruled=True):
    """Rounded-rect XZ sections lofted along Y.  ``(y, xc, zc, w, h, r)``."""
    faces = []
    for (y, xc, zc, w, h, r) in stations:
        pl = Plane(origin=(xc, y, zc), x_dir=(1, 0, 0), z_dir=(0, -1, 0))
        faces.append(pl * RectangleRounded(w, h, r))
    return loft(faces, ruled=ruled)


def _yz_loft(stations, ruled=True):
    """Rounded-rect YZ sections lofted along X.  ``(x, yc, zc, w, h, r)``."""
    faces = []
    for (x, yc, zc, w, h, r) in stations:
        pl = Plane(origin=(x, yc, zc), x_dir=(0, 1, 0), z_dir=(1, 0, 0))
        faces.append(pl * RectangleRounded(w, h, r))
    return loft(faces, ruled=ruled)


def _catmull(xs, vs, x):
    """Non-overshooting C1 interpolation (same reasoning as surfaces.C1)."""
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
    return ((2 * t3 - 3 * t2 + 1) * p1 + (t3 - 2 * t2 + t) * m1
            + (-2 * t3 + 3 * t2) * p2 + (t3 - t2) * m2)


def _resample(keys, count):
    """Smooth ``(x, zc, w, h, r)`` keys into ``count`` even ``_yz_loft`` rows.

    A ruled loft straight off the key stations leaves a crease at every one --
    they show up as cast-in fins down the gearbox.  Interpolating first and
    lofting ruled through many close sections keeps the surface reading smooth
    while staying predictable (a smooth loft balloons on these sections).
    """
    ks = sorted(keys)
    xs = [k[0] for k in ks]
    cols = [[k[i] for k in ks] for i in (1, 2, 3, 4)]
    out = []
    for i in range(count):
        x = xs[0] + (xs[-1] - xs[0]) * i / (count - 1)
        zc, w, h, r = (_catmull(xs, c, x) for c in cols)
        out.append((x, 0.0, zc, w, h, min(r, 0.49 * min(w, h))))
    return out


def _x_loft(stations, ruled=False):
    """Circles lofted along X.  ``(x, y, z, r)``."""
    faces = [
        Plane(origin=(x, y, z), x_dir=(0, 1, 0), z_dir=(1, 0, 0)) * Circle(r)
        for (x, y, z, r) in stations
    ]
    return loft(faces, ruled=ruled)


def _turned(points, close_axis=True):
    """Solid of revolution from a (radius, height) polyline about Z."""
    wire = Polyline(*points, close=close_axis)
    return revolve(Plane.XZ * make_face(wire), Axis.Z)


def _smooth_path(ctrl, samples=10):
    """Even-arc-length resample of a Catmull-Rom through ``ctrl``.

    Splining straight through control points that are 60 mm apart at one end
    and 280 mm apart at the other puts a curvature ripple in the curve, and a
    swept tube shows that ripple as a corrugated surface.  Resampling at even
    arc length first is what makes the primaries read as drawn tube.
    """
    pts = [Vector(*c) for c in ctrl]
    ext = [pts[0] + (pts[0] - pts[1])] + pts + [pts[-1] + (pts[-1] - pts[-2])]
    dense = []
    for i in range(len(pts) - 1):
        p0, p1, p2, p3 = ext[i], ext[i + 1], ext[i + 2], ext[i + 3]
        for k in range(24):
            t = k / 24.0
            t2, t3 = t * t, t * t * t
            dense.append(
                (p1 * 2.0 + (p2 - p0) * t
                 + (p0 * 2.0 - p1 * 5.0 + p2 * 4.0 - p3) * t2
                 + (p1 * 3.0 - p0 - p2 * 3.0 + p3) * t3) * 0.5
            )
    dense.append(pts[-1])
    cum = [0.0]
    for a, b in zip(dense, dense[1:]):
        cum.append(cum[-1] + (b - a).length)
    total = cum[-1]
    out = []
    j = 0
    for i in range(samples):
        target = total * i / (samples - 1)
        while j < len(cum) - 2 and cum[j + 1] < target:
            j += 1
        span = (cum[j + 1] - cum[j]) or 1.0
        v = dense[j] + (dense[j + 1] - dense[j]) * ((target - cum[j]) / span)
        out.append((v.X, v.Y, v.Z))
    return out


def _tube(points, radius, t0, t1):
    """Round tube swept along a smooth, evenly sampled spline."""
    path = Spline(*_smooth_path(points), tangents=(t0, t1))
    section = Plane(origin=Vector(*points[0]), z_dir=Vector(*t0)) * Circle(radius)
    # is_frenet=True: the corrected-Frenet frame produces an inverted solid on
    # the tighter rear runners here (negative volume), so keep the true Frenet
    # frame and keep the path smooth instead.
    return sweep(section, path, is_frenet=True)


# ---------------------------------------------------------------------------
# block, heads, cam covers
# ---------------------------------------------------------------------------


def _block():
    solid = _xz_loft([
        (-Y_END, X_E, 404, 300, 116, 40),
        (-352.0, X_E, 402, 332, 134, 44),
        (-300.0, X_E, 402, 340, 140, 46),
        (300.0, X_E, 402, 340, 140, 46),
        (352.0, X_E, 402, 332, 134, 44),
        (Y_END, X_E, 404, 300, 116, 40),
    ])
    for s in (1, -1):
        solid = solid + _bank_loft(s, [
            (-368.0, -64, 64, 40, 250, 24),
            (-340.0, -74, 74, 32, 250, 28),
            (340.0, -74, 74, 32, 250, 28),
            (368.0, -64, 64, 40, 250, 24),
        ])
    return solid


def _head(s):
    return _bank_loft(s, [
        (-353.0, -56, 82, 250, 329, 17),
        (-336.0, -62, 88, 249, 331, 20),
        (336.0, -62, 88, 249, 331, 20),
        (353.0, -56, 82, 250, 329, 17),
    ])


def _cam_cover(s):
    return _bank_loft(s, [
        (-346.0, -48, 70, 331, 370, 16),
        (-330.0, -56, 80, 329, 386, 20),
        (330.0, -56, 80, 329, 386, 20),
        (346.0, -48, 70, 331, 370, 16),
    ])


def _end_cover(sy):
    """Gear-drive cover closing one end of the vee."""
    y0 = sy * 372.0
    return _xz_loft([
        (y0, X_E, 468, 396, 262, 60),
        (y0 + sy * 20.0, X_E, 466, 380, 244, 58),
        (y0 + sy * 32.0, X_E, 462, 326, 202, 52),
    ])


# ---------------------------------------------------------------------------
# intake -- plenum, throttle bodies, velocity stacks
# ---------------------------------------------------------------------------

# Half section of the intake plenum, as two spline bands meeting with a shared
# tangent at the shoulder.  One band through the whole run overshoots into a
# self-intersecting loop where the section turns over onto its crown.
_PLENUM_SIDE = [
    (0.0, 594.0), (30.0, 599.0), (54.0, 620.0), (78.0, 650.0),
    (97.0, 680.0), (110.0, 706.0),
]
_PLENUM_CROWN = [(110.0, 706.0), (103.0, 719.0), (78.0, 725.0), (0.0, 728.0)]
_PLENUM_TANGENT = (0.16, 0.99)


def _plenum_face(y, k, kz):
    def sc(pts):
        return [(u * k, 660.0 + (v - 660.0) * kz) for (u, v) in pts]

    side = Spline(*sc(_PLENUM_SIDE), tangents=((1, 0), _PLENUM_TANGENT))
    crown = Spline(*sc(_PLENUM_CROWN), tangents=(_PLENUM_TANGENT, (-1, 0)))
    half = side + crown
    face = make_face(half + mirror(half, Plane.YZ))
    return Pos(X_E, 0, 0) * (Plane.XZ.offset(-y) * face)


def _plenum():
    """Blunt-ended and ruled, with just a two-band chamfer closing each end.

    A smooth loft balloons ~10% on these sections; a long ruled taper prints a
    contour ring per station and end-on the plenum reads like a fingerprint.
    A short chamfer keeps it machined and keeps the ring count to two.
    """
    ends = [(298.0, 1.0, 1.0), (305.0, 0.90, 0.93), (310.0, 0.64, 0.78)]
    stations = [(-y, k, kz) for (y, k, kz) in reversed(ends)] + ends
    return loft([_plenum_face(*st) for st in stations], ruled=True)


def _spine():
    """Bronze rail down the crown of the vee -- the warm note up top."""
    return _xz_loft([
        (-292.0, X_E, 725, 20, 12, 5),
        (-268.0, X_E, 728, 32, 18, 8),
        (268.0, X_E, 728, 32, 18, 8),
        (292.0, X_E, 725, 20, 12, 5),
    ])


def _stack_proto():
    """Trumpet: flared bell, rolled lip, tapered inner throat."""
    outer = Spline(
        (30.0, 0.0), (30.6, 14.0), (33.0, 27.0), (38.4, 39.0), (46.0, 49.0),
        tangents=((0, 1), (0.66, 0.75)),
    )
    lip_a = Spline(
        (46.0, 49.0), (48.6, 52.6), (46.6, 55.4),
        tangents=((0.66, 0.75), (-0.92, -0.39)),
    )
    lip_b = Spline(
        (46.6, 55.4), (43.8, 52.8), (42.8, 48.6),
        tangents=((-0.92, -0.39), (-0.22, -0.98)),
    )
    inner = Spline(
        (42.8, 48.6), (35.4, 37.0), (29.2, 23.0), (26.9, 9.0), (26.8, 0.0),
        tangents=((-0.22, -0.98), (0, -1)),
    )
    base = Line((26.8, 0.0), (30.0, 0.0))
    wire = outer + lip_a + lip_b + inner + base
    return Pos(0, 0, 60.0) * revolve(Plane.XZ * make_face(wire), Axis.Z)


def _throttle_proto():
    return _turned([
        (0.0, -8.0), (34.0, -8.0), (34.0, 2.0), (29.5, 8.0), (29.5, 40.0),
        (32.0, 46.0), (32.0, 52.0), (29.5, 52.0), (29.5, 60.0), (0.0, 60.0),
    ])


def _clamp_proto():
    return _turned([
        (0.0, 54.0), (30.4, 54.0), (34.2, 57.5), (34.2, 64.5), (30.4, 68.0),
        (0.0, 68.0),
    ])


def _intake_row(s, proto, kind, colour):
    tag = "front" if s > 0 else "rear"
    style(proto, f"{kind}:{tag}", colour)
    x = X_E + s * ITB_U
    inst = [
        (proto, Location((x, y, ITB_Z), (0.0, s * ITB_TILT, 0.0)),
         f"{kind}:{tag}_{i + 1}")
        for i, y in enumerate(Y_CYL)
    ]
    return cadgen.compound_from_instances(f"{kind}_{tag}", inst)


def _oil_cap():
    solid = _turned([
        (0.0, 0.0), (31.0, 0.0), (33.0, 5.0), (33.0, 12.0), (28.0, 18.0),
        (20.0, 19.0), (0.0, 19.0),
    ])
    x, z = _bank_xz(-1, 380.0, 8.0)
    return Location((x, -206.0, z), (0.0, -V_ANGLE, 0.0)) * solid


def _cover_bolts():
    proto = _turned([
        (0.0, 0.0), (9.0, 0.0), (9.0, 4.0), (7.0, 6.6), (0.0, 6.6),
    ])
    style(proto, "cam_cover_bolt:proto", P.BRONZE)
    inst = []
    n = 0
    for s in (1, -1):
        tag = "front" if s > 0 else "rear"
        for w in (-42.0, 66.0):
            for y in (-292.0, -175.0, -58.0, 58.0, 175.0, 292.0):
                x, z = _bank_xz(s, 385.0, w)
                n += 1
                inst.append((
                    proto,
                    Location((x, y, z), (0.0, s * V_ANGLE, 0.0)),
                    f"cam_cover_bolt:{tag}_{n}",
                ))
    return cadgen.compound_from_instances("cam_cover_bolts", inst)


# ---------------------------------------------------------------------------
# exhaust -- twelve primaries into two 6-into-1 collectors
# ---------------------------------------------------------------------------


def _mouth_frame(sy):
    centre = Vector(COLL_M.X, sy * COLL_M.Y, COLL_M.Z)
    n = Vector(COLL_N.X, sy * COLL_N.Y, COLL_N.Z).normalized()
    u = n.cross(Vector(0, 0, 1)).normalized()
    v = n.cross(u).normalized()
    return centre, n, u, v


def _axis_point(sy, t):
    centre, n, _u, _v = _mouth_frame(sy)
    return centre + n * t


def _axis_plane(sy, t):
    centre, n, _u, _v = _mouth_frame(sy)
    o = centre + n * t
    return Plane(origin=(o.X, o.Y, o.Z), z_dir=(n.X, n.Y, n.Z))


def _mouth_point(sy, angle_deg, radius=38.0):
    centre, n, u, v = _mouth_frame(sy)
    a = math.radians(angle_deg)
    p = centre + u * (radius * math.cos(a)) + v * (radius * math.sin(a))
    return (p.X, p.Y, p.Z), (n.X, n.Y, n.Z)


def _rear_primary(sy, j):
    """Rearward bank: a clean straight shot back into the collector."""
    y0 = sy * (54.0 + 108.0 * j)
    px, pz = _bank_xz(-1, PORT_D, PORT_W)
    t0 = (-CA, 0.0, -SA)
    p0 = (px, y0, pz)
    p1 = (px - 70.0 * CA, y0, pz - 70.0 * SA)
    p2 = (-1876.0 - 10.0 * j,
          sy * (0.32 * abs(y0) + 0.68 * COLL_M.Y), 542.0 - 20.0 * j)
    p3 = (-1992.0,
          sy * (0.15 * abs(y0) + 0.85 * COLL_M.Y), 514.0 - 8.0 * j)
    end, t1 = _mouth_point(sy, 40.0 + 60.0 * j)
    return _tube([p0, p1, p2, p3, end], TUBE_R, t0, t1)


def _front_primary(sy, j):
    """Forward bank: three nested tubes wrap outboard round the engine's nose.

    They leave the port already angled outboard so the wrap stays tight -- a
    port-normal exit needs a 150 deg turn and throws the loop 100 mm further
    forward, into the cabin bulkhead.
    """
    y0 = sy * (54.0 + 108.0 * j)
    run = 444.0 + 52.0 * j
    px, pz = _bank_xz(1, PORT_D, PORT_W)
    t0 = Vector(0.72 * CA, sy * 0.62, -0.72 * SA).normalized()
    p0 = Vector(px, y0, pz)
    p1 = p0 + t0 * 60.0
    p2 = (-1236.0, sy * (0.34 * abs(y0) + 0.66 * run), 528.0)
    p3 = (-1292.0, sy * run, 494.0)
    p4 = (-1572.0, sy * run, 486.0)
    p5 = (-1832.0, sy * (0.62 * run + 0.38 * COLL_M.Y), 484.0)
    p6 = (-2006.0, sy * (0.25 * run + 0.75 * COLL_M.Y), 490.0)
    end, t1 = _mouth_point(sy, 220.0 + 60.0 * j)
    pts = [(p0.X, p0.Y, p0.Z), (p1.X, p1.Y, p1.Z), p2, p3, p4, p5, p6, end]
    return _tube(pts, TUBE_R, (t0.X, t0.Y, t0.Z), t1)


def _port_bosses():
    """Machined port flanges where the primaries meet the heads."""
    proto = _turned([
        (0.0, 0.0), (33.0, 0.0), (33.0, 9.0), (27.5, 14.0), (26.0, 21.0),
        (0.0, 21.0),
    ])
    style(proto, "exhaust_port_boss:proto", P.ALUMINIUM_DARK)
    inst = []
    for s_ in (1, -1):
        tag = "front" if s_ > 0 else "rear"
        x, z = _bank_xz(s_, PORT_D, 74.0)
        for i, y in enumerate(Y_CYL):
            inst.append((
                proto,
                Location((x, y, z), (0.0, s_ * 120.0, 0.0)),
                f"exhaust_port_boss:{tag}_{i + 1}",
            ))
    return cadgen.compound_from_instances("exhaust_port_bosses", inst)


def _megaphone(sy):
    """6-into-1 collector tapering straight at the tip."""
    return loft([
        _axis_plane(sy, t) * Circle(r)
        for (t, r) in ((0.0, 64.0), (22.0, 63.0), (64.0, 55.0), (112.0, 45.0),
                       (158.0, 38.0), (COLL_END_T, 35.0))
    ], ruled=False)


def _tip(sy):
    outer = loft([
        _axis_plane(sy, t) * Circle(r)
        for (t, r) in ((COLL_END_T, 41.0), (COLL_END_T + 16.0, 49.0),
                       (COLL_END_T + 44.0, 55.0), (TIP_T - 9.0, 56.0),
                       (TIP_T, 56.0))
    ], ruled=False)
    bore = loft([
        _axis_plane(sy, t) * Circle(r)
        for (t, r) in ((COLL_END_T - 14.0, 28.0), (COLL_END_T + 40.0, 41.0),
                       (TIP_T + 14.0, 48.0))
    ], ruled=False)
    return outer - bore


def _tip_plug(sy):
    return loft([
        _axis_plane(sy, TIP_T - 34.0) * Circle(36.0),
        _axis_plane(sy, TIP_T - 22.0) * Circle(38.0),
    ], ruled=True)


# ---------------------------------------------------------------------------
# transaxle and driveshafts
# ---------------------------------------------------------------------------


def _revolved_along_y(points, sy, x, z):
    """Revolve a (radius, Y) polyline and stand it on the Y axis."""
    solid = Rot(-90, 0, 0) * _turned(points)
    if sy < 0:
        solid = Rot(0, 0, 180) * solid
    return Pos(x, 0.0, z) * solid


_FINAL_DRIVE_KEYS = [
    (-1246.0, 406, 300, 122, 44),
    (-1288.0, 403, 566, 148, 56),
    (-1330.0, 401, 736, 158, 62),
    (-1368.0, 400, 782, 160, 62),
    (-1410.0, 399, 762, 154, 60),
    (-1450.0, 397, 690, 146, 56),
    (-1478.0, 396, 600, 136, 50),
]

_GEARBOX_KEYS = [
    (-1338.0, 302, 462, 76, 22),
    (-1470.0, 304, 546, 84, 24),
    (-1620.0, 310, 572, 100, 26),
    (-1700.0, 326, 566, 138, 30),
    (-1770.0, 354, 536, 194, 34),
    (-1850.0, 374, 496, 226, 36),
    (-1930.0, 388, 448, 218, 36),
    (-2010.0, 396, 392, 204, 34),
    (-2090.0, 400, 312, 182, 32),
    (-2160.0, 404, 222, 144, 28),
    (-2218.0, 408, 110, 80, 20),
]


def _key_at(keys, x):
    ks = sorted(keys)
    xs = [k[0] for k in ks]
    return tuple(_catmull(xs, [k[i] for k in ks], x) for i in (1, 2, 3, 4))


def _final_drive():
    return _yz_loft(_resample(_FINAL_DRIVE_KEYS, 18), ruled=False)


def _gearbox():
    return _yz_loft(_resample(_GEARBOX_KEYS, 22), ruled=False)


def _case_parting():
    """Horizontal split line down the transaxle -- reads as a real casting."""
    keys = [(x, zc, w + 13.0, 17.0, 7.0) for (x, zc, w, _h, _r) in _GEARBOX_KEYS]
    return _yz_loft(_resample(keys, 22), ruled=False)


def _case_flange(x, grow=17.0, width=24.0):
    """Bearing-carrier girth rib -- gives the case scale and a cast pedigree."""
    zc, w, h, r = _key_at(_GEARBOX_KEYS, x)
    half = width / 2.0
    big = min(r + 7.0, 0.48 * min(w + grow, h + grow))
    small = min(r, 0.48 * min(w, h))
    # grow in width only: a rib that also stood proud of the case FLOOR read
    # as three dark straps hanging under the car in side view.
    return _yz_loft([
        (x + half, 0.0, zc, w + 0.3 * grow, h - 8.0, small),
        (x + half - 5.0, 0.0, zc, w + grow, h - 4.0, big),
        (x - half + 5.0, 0.0, zc, w + grow, h - 4.0, big),
        (x - half, 0.0, zc, w + 0.3 * grow, h - 8.0, small),
    ], ruled=True)


def _drive_boss(sy):
    """Turned cam-drive boss on the outer face of the gear cover."""
    return _revolved_along_y([
        (0.0, 404.0), (78.0, 404.0), (78.0, 415.0), (58.0, 415.0),
        (58.0, 424.0), (0.0, 424.0),
    ], sy, X_E, 470.0)


def _output_boss(sy):
    return Pos(-1352.0, sy * 386.0, 400.0) * Rot(-90, 0, 0) * Cylinder(
        radius=64.0, height=52.0)


def _driveshaft(sy):
    return _revolved_along_y([
        (0.0, 404.0), (54.0, 404.0), (54.0, 450.0), (46.0, 460.0),
        (46.0, 472.0), (27.0, 480.0), (24.0, 494.0), (23.0, 600.0),
        (28.0, 612.0), (30.0, 620.0), (30.0, 656.0), (27.0, 664.0),
        (25.0, 674.0), (31.0, 680.0), (45.0, 694.0), (49.0, 714.0),
        (47.0, 736.0), (0.0, 736.0),
    ], sy, -1356.0, 394.0)


def _cv_boot(sy):
    return _revolved_along_y([
        (0.0, 612.0), (32.0, 612.0), (37.0, 620.0), (34.0, 629.0),
        (38.0, 640.0), (34.0, 651.0), (37.0, 661.0), (32.0, 670.0),
        (0.0, 670.0),
    ], sy, -1356.0, 394.0)


# ---------------------------------------------------------------------------


def build():
    kids = []

    kids.append(style(_block(), "engine_block:v12", BLOCK_C))
    for s in (1, -1):
        tag = "front" if s > 0 else "rear"
        kids.append(style(_head(s), f"cylinder_head:{tag}", HEAD_C))
        kids.append(style(_cam_cover(s), f"cam_cover:{tag}", COVER_C))
    for sy in (1, -1):
        side = "left" if sy > 0 else "right"
        kids.append(style(_end_cover(sy), f"gear_drive_cover:{side}", CASE_DARK))
        kids.append(style(_drive_boss(sy), f"cam_drive_boss:{side}",
                          P.ALUMINIUM))

    intake = [
        style(_plenum(), "intake_plenum:vee", PLENUM_C),
        style(_spine(), "plenum_spine:centre", P.BRONZE),
    ]
    for s in (1, -1):
        intake.append(_intake_row(s, _throttle_proto(), "throttle_body",
                                  THROTTLE_C))
        intake.append(_intake_row(s, _clamp_proto(), "stack_clamp", P.BRONZE))
        intake.append(_intake_row(s, _stack_proto(), "velocity_stack",
                                  POLISH_C))
    intake.append(style(_oil_cap(), "oil_filler_cap:rear", P.BRONZE))
    intake.append(_cover_bolts())
    kids.append(group("intake", intake))

    exhaust = [_port_bosses()]
    for sy in (1, -1):
        side = "left" if sy > 0 else "right"
        for j in range(3):
            exhaust.append(style(_rear_primary(sy, j),
                                 f"exhaust_primary:rear_{side}_{j + 1}",
                                 HEADER_C))
            exhaust.append(style(_front_primary(sy, j),
                                 f"exhaust_primary:front_{side}_{j + 1}",
                                 HEADER_C))
        exhaust.append(style(_megaphone(sy), f"exhaust_collector:{side}",
                             COLLECT_C))
        exhaust.append(style(_tip(sy), f"exhaust_tip:{side}", TIP_C))
        exhaust.append(style(_tip_plug(sy), f"exhaust_tip_plug:{side}",
                             P.CARBON))
    kids.append(group("exhaust", exhaust))

    drive = [
        style(_gearbox(), "transaxle_case:main", CASE_C),
        style(_final_drive(), "final_drive:housing", CASE_C),
    ]
    drive.append(style(_case_parting(), "case_parting:line", CASE_DARK))
    for i, x in enumerate((-1772.0, -1896.0, -2022.0)):
        drive.append(style(_case_flange(x), f"case_flange:rib_{i + 1}",
                           CASE_C))
    for sy in (1, -1):
        side = "left" if sy > 0 else "right"
        drive.append(style(_output_boss(sy), f"output_boss:{side}", CASE_DARK))
        drive.append(style(_driveshaft(sy), f"driveshaft:{side}", P.ALUMINIUM))
        drive.append(style(_cv_boot(sy), f"cv_boot:{side}", RUBBER_C))
    kids.append(group("transaxle", drive))

    return group("powertrain", kids)
