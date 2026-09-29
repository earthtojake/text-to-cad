"""Pushrods: 18 moving pushrods (ground-steel rods with hardened ball ends) and
18 static polished pushrod tubes (OD 22, slimmer than spec.PUSHROD_TUBE_OD: the
least the pushrod excursion allows), each with the SAME slim castellated
packing nut + gland follower at both ends -- on the nose-case tappet-guide boss
and on the rocker-box inlet boss. Clean period look: no hoses, no clamps.

Authoring. Everything is authored ONCE per valve side v for cylinder 1, along
the pushrod REST axis (bottom ball B0 = kin.pushrod_bottom0, top ball
T0 = kin.pushrod_top0, zero lift): a local frame with origin at B0, local +Z
along u = (T0 - B0)/|T0 - B0| and local +X the unit perpendicular pointing
most toward the FRONT (-Y). Because the front view of the I and E lines is an
exact mirror in t (kin mirrors t; only the y stations differ), that choice of
+X keeps the castellations mirror-symmetric in the head-on star. Cylinder k gets `geo.on_cylinder(proto, k)`; pushrods are then
placed with `kin.place(..., kin.pose_pushrod(0, k, v))`.

Stations along the rest axis (s from the bottom ball centre):
  s = 16                  lower boss face (nose case)  = spec.PUSHROD_TUBE_START
  s = L - 34.5            upper nut seat on the rocker-box inlet boss (see HI_SEAT)
Section: cylinder 1's museum cut is its REAR half (y > 0); every part here lies at
y < -80, so cylinder 1 is built complete like the other eight.
"""

from __future__ import annotations

import math

from cadgen import build123d as bd

from lib import geo
from lib import kin
from lib import palette as P
from lib import spec as S

MATERIALS = ("steel_machined", "steel_polished")

VALVES = ("I", "E")

# pushrod
BALL_R = 7.0                     # Ø14 hardened balls (valvetrain / cam sockets are 7.05 / 7.25)
ROD_R = S.PUSHROD_D / 2.0        # Ø12
NECK_R = 4.5
FERRULE_R = 6.5                  # swaged end-fitting ferrules (bottom inside the lower nut, top inside the head bore)

# tube: slimmer than spec.PUSHROD_TUBE_OD (24) for the period look; OD 22 clears the pushrod
# because the tube runs through the middle of its swing (see tube_axis)
TUBE_OD = 22.0
TUBE_RO = TUBE_OD / 2.0                    # 11.0
TUBE_WALL = 0.55
TUBE_RI = TUBE_RO - TUBE_WALL              # 10.45

# ONE packing nut + ONE gland design, used at both ends of every tube (nut-local z from its seat face)
NUT_LEN = 11.0
NUT_FLANGE = (2.0, 13.4)         # seat flange (length, radius)
NUT_BODY_R = 12.7                # slim bright body, OD 25.4
NUT_BORE_R = TUBE_RO + 0.05      # over the tube end
NUT_LIP = (2.5, 10.6)            # retaining lip at the seat end
TUBE_IN_NUT = 2.5                # tube ends butt the lip, this far from the seat
GLAND = (NUT_LEN + 0.05, NUT_LEN + 3.3, 12.0)   # gland follower ring beyond the nut (from, to, radius)
CASTLES = 6
CASTLE_W, CASTLE_D = 3.0, 2.2

LO_SEAT = S.PUSHROD_TUBE_START   # s of the lower seat (nose tappet-guide boss face)
# The heads' tube relief (heads._tube_relief) stops 0.5 mm short of the spec boss face, leaving a
# 0.5 mm skin: the rocker-box inlet face is effectively at END_FROM_TOP + 0.5. Seat there (a 0.5 mm
# shadow gap if heads ever cuts to the spec face; an overlap otherwise).
HI_SEAT = S.PUSHROD_TUBE_END_FROM_TOP + 0.5


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _unit(a):
    n = math.sqrt(sum(x * x for x in a))
    return tuple(x / n for x in a)


def rest_line(v):
    """(B0, T0, u, L) of the cylinder-1 pushrod at rest."""
    b, t = kin.pushrod_bottom0(1, v), kin.pushrod_top0(1, v)
    return b, t, _unit(kin._sub(t, b)), kin.pushrod_length(v)


def _front_x(z):
    f = (0.0, -1.0, 0.0)
    d = kin._dot(f, z)
    return _unit((f[0] - d * z[0], f[1] - d * z[1], f[2] - d * z[2]))


def frame(v) -> bd.Plane:
    """Pushrod frame: origin B0, +Z along the rest axis, +X toward the front."""
    b, _, u, _ = rest_line(v)
    return geo.plane(b, u, _front_x(u))


def _swing_mid(v, s):
    """Centre of the pushrod axis's lateral swing (bounding-box midpoint, 0..720 deg, 2 deg steps)
    in the plane normal to the rest axis at station s: an engine point, cylinder 1."""
    b0, _, u, _ = rest_line(v)
    lo, hi = [1e9] * 3, [-1e9] * 3
    for i in range(360):
        pose = kin.pose_pushrod(2.0 * i, 1, v)
        pb = kin.apply_point(pose, b0)
        pt = kin.apply_point(pose, kin._addv(b0, u, 100.0))
        d = _unit(kin._sub(pt, pb))
        a = (s - kin._dot(kin._sub(pb, b0), u)) / kin._dot(d, u)
        q = kin._sub(kin._addv(pb, d, a), b0)
        for j in range(3):
            lo[j], hi[j] = min(lo[j], q[j]), max(hi[j], q[j])
    return tuple(b0[j] + (lo[j] + hi[j]) / 2.0 for j in range(3))


_AXES = {}


def tube_axis(v):
    """(A_lo, A_hi, w, Lt, seat_gap) of the tube, cylinder 1. The tube is NOT on the rest axis: the
    pushrod swings one way from rest (tappet lift leans it forward ~3.7 mm at both ends, the rocker
    arc moves the top ~4 mm sideways), so the tube runs through the MIDDLE of that swing at the two
    seat planes (normal to the rest axis at PUSHROD_TUBE_START from the bottom ball and HI_SEAT below
    the top ball). That halves the excursion the bore must clear. The axis differs from the rest
    axis by ~0.3 deg; the nut seats stand `seat_gap` off the boss planes so the tilt never digs in."""
    if v not in _AXES:
        _, _, u, L = rest_line(v)
        a_lo, a_hi = _swing_mid(v, LO_SEAT), _swing_mid(v, L - HI_SEAT)
        w = _unit(kin._sub(a_hi, a_lo))
        Lt = math.sqrt(sum(x * x for x in kin._sub(a_hi, a_lo)))
        tilt = math.acos(min(1.0, kin._dot(w, u)))
        gap = NUT_FLANGE[1] * math.sin(tilt) + 0.05
        _AXES[v] = (a_lo, a_hi, w, Lt, gap)
    return _AXES[v]


def tube_frame(v) -> bd.Plane:
    """Tube frame: origin at the lower seat point on the tube axis, +Z up the tube, +X front."""
    a_lo, _, w, _, _ = tube_axis(v)
    return geo.plane(a_lo, w, _front_x(w))


def _rev(pts):
    """Solid of revolution about local Z from a closed (r, z) polygon."""
    face = bd.make_face(bd.Polyline(*[(r, z) for r, z in pts], close=True).edges())
    return bd.revolve(bd.Plane.XZ * face, axis=bd.Axis.Z)


# ---------------------------------------------------------------------------
# pushrod (moving), local frame: ball centres at z = 0 and z = L
# ---------------------------------------------------------------------------
def pushrod_local(L):
    pts = [(0.0, 4.0), (NECK_R, 4.0), (NECK_R, 9.0), (FERRULE_R, 12.5), (FERRULE_R, 22.5),
           (ROD_R, 23.5), (ROD_R, L - 23.5), (FERRULE_R, L - 22.5), (FERRULE_R, L - 12.5),
           (NECK_R, L - 9.0), (NECK_R, L - 4.0), (0.0, L - 4.0)]
    shaft = _rev(pts)
    balls = [bd.Sphere(BALL_R), bd.Pos(0, 0, L) * bd.Sphere(BALL_R)]
    return shaft.fuse(*balls).clean()


# ---------------------------------------------------------------------------
# static parts, tube frame (z along the tube axis from the lower seat point)
# ---------------------------------------------------------------------------
def tube_local(Lt, gap):
    s0, s1 = gap + TUBE_IN_NUT, Lt - gap - TUBE_IN_NUT
    c = 0.25
    return _rev([(TUBE_RI + c, s0), (TUBE_RO - c, s0), (TUBE_RO, s0 + c), (TUBE_RO, s1 - c),
                 (TUBE_RO - c, s1), (TUBE_RI + c, s1), (TUBE_RI, s1 - c), (TUBE_RI, s0 + c)])


def _nut():
    """Packing nut, seat face at z = 0, body toward +z: seat flange, slim body, castellated end."""
    fl, rf = NUT_FLANGE
    ll, rl = NUT_LIP
    rb, c = NUT_BODY_R, 0.4
    body = _rev([(rl, 0.0), (rf - c, 0.0), (rf, c), (rf, fl - c), (rf - c, fl), (rb, fl + 0.6),
                 (rb, NUT_LEN - 0.6), (rb - 0.6, NUT_LEN), (NUT_BORE_R, NUT_LEN), (NUT_BORE_R, ll),
                 (rl, ll)])
    notches = [bd.Rot(0, 0, 360.0 / CASTLES * (i + 0.5))
               * bd.Pos((NUT_BORE_R + rb) / 2.0, 0, NUT_LEN - CASTLE_D / 2.0 + 0.5)
               * bd.Box(rb - NUT_BORE_R + 3.0, CASTLE_W, CASTLE_D + 1.0) for i in range(CASTLES)]
    return body - notches


def _gland():
    g0, g1, rg = GLAND
    ri, c = TUBE_RO + 0.05, 0.4
    return _rev([(ri, g0), (rg - c, g0), (rg, g0 + c), (rg, g1 - c), (rg - c, g1), (ri, g1)])


def _at_seat(shape, s, down=False):
    """Place a seat-at-origin part at axial station s; `down` turns it to face -z (upper end)."""
    return bd.Pos(0, 0, s) * (bd.Rot(180, 0, 0) * shape if down else shape)


# ---------------------------------------------------------------------------
_PROTO = None


def prototypes():
    """{v: {"rod": shape, "static": [(name_fmt, shape, color)]}} for cylinder 1, engine frame."""
    global _PROTO
    if _PROTO is not None:
        return _PROTO
    out = {}
    for v in VALVES:
        _, _, _, L = rest_line(v)
        _, _, _, Lt, gap = tube_axis(v)
        tloc = tube_frame(v).location
        nut, gland = _nut(), _gland()
        static = [
            ("tube_{}", tube_local(Lt, gap), P.STEEL_POLISHED),
            ("packing_nut_{}_lo", _at_seat(nut, gap), P.STEEL_POLISHED),
            ("packing_gland_{}_lo", _at_seat(gland, gap), P.STEEL_POLISHED),
            ("packing_nut_{}_hi", _at_seat(nut, Lt - gap, down=True), P.STEEL_POLISHED),
            ("packing_gland_{}_hi", _at_seat(gland, Lt - gap, down=True), P.STEEL_POLISHED),
        ]
        out[v] = {"rod": frame(v).location * pushrod_local(L),
                  "static": [(n, tloc * s, c) for n, s, c in static]}
    _PROTO = out
    return out


def build():
    protos = prototypes()
    parts = []
    for k in range(1, S.N_CYL + 1):
        for v in VALVES:
            kv = f"{k}{v}"
            pr = protos[v]
            rod = kin.place(geo.on_cylinder(pr["rod"], k), kin.pose_pushrod(0.0, k, v))
            parts.append(P.style(rod, f"pushrod{kv}:rod", P.STEEL_MACHINED))
            # cylinder 1's section is its REAR half (y > 0): the tubes (y < -80) are never in it
            for name, shape, color in pr["static"]:
                parts.append(P.style(geo.on_cylinder(shape, k), f"pushrods:{name.format(kv)}", color))
    return parts
