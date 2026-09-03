"""W16 kinematics — pure math, no build123d.

Everything that moves is positioned by these functions, both when the STEP is
authored (theta = 0, the rest pose) and when it is animated (the .anim.js
re-describes the same formulas; `tables()` bakes the nonlinear follower solve
into interpolation tables for it). The collision harness samples them too.

Frames: engine frame per lib/spec.py. Rotations about +X are right-handed:
Rot_x(t): (y, z) -> (y cos t - z sin t, y sin t + z cos t), and the crank-angle
convention p(a) = (0, -sin a, cos a) INCREASES with such a rotation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from lib import spec as S

TAU = 2.0 * math.pi


def rot_yz(v, t_deg):
    """Rotate a (y, z) pair by t_deg about +X (right-handed)."""
    t = math.radians(t_deg)
    c, s = math.cos(t), math.sin(t)
    return (v[0] * c - v[1] * s, v[0] * s + v[1] * c)


def yz(p):
    return (p[1], p[2])


def sub(a, b):
    return (a[0] - b[0], a[1] - b[1])


def add(a, b):
    return (a[0] + b[0], a[1] + b[1])


def mul(a, k):
    return (a[0] * k, a[1] * k)


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1]


def norm(a):
    n = math.hypot(a[0], a[1])
    return (a[0] / n, a[1] / n)


def signed_angle(a, b):
    """Signed angle (deg) from direction a to direction b, about +X."""
    return math.degrees(math.atan2(a[0] * b[1] - a[1] * b[0], dot(a, b)))


# ---------------------------------------------------------------------------
# Crank, rods, pistons
# ---------------------------------------------------------------------------

def pin_yz(pin: int, theta: float):
    """Crankpin centre (y, z) for 0-based pin at crank angle theta (deg)."""
    a = math.radians(S.pin_angle(pin) + theta)
    return (-S.THROW * math.sin(a), S.THROW * math.cos(a))


@dataclass(frozen=True)
class PistonState:
    theta: float
    s: float             # wrist-pin centre along the bore axis from its foot
    pin: tuple           # crankpin centre (y, z)
    small_end: tuple     # wrist-pin centre (y, z)
    rod_dir: tuple       # unit (y, z) from big end to small end
    rod_tilt: float      # deg, signed angle from the bore axis to rod_dir (about +X)


def piston(cyl: int, theta: float) -> PistonState:
    c = S.CYLINDERS[cyl - 1]
    o = yz(c.foot)
    u = yz(c.axis)
    n = yz(c.toward_centre)
    P = pin_yz(c.pin, theta)
    e = sub(P, o)
    a = dot(e, u)
    h = dot(e, n)
    s = a + math.sqrt(S.ROD_LEN ** 2 - h * h)
    Q = add(o, mul(u, s))
    r = norm(sub(Q, P))
    return PistonState(theta=theta, s=s, pin=P, small_end=Q, rod_dir=r,
                       rod_tilt=signed_angle(u, r))


def piston_s_range(cyl: int):
    ss = [piston(cyl, t).s for t in range(0, 720, 2)]
    return min(ss), max(ss)


# ---------------------------------------------------------------------------
# Valves, followers, cams
# ---------------------------------------------------------------------------

def cam_angle(theta: float) -> float:
    return theta / 2.0


def lift_profile(x: float) -> float:
    """Normalised lift over x in [0, 1] (0 outside); smooth rise and fall."""
    if x <= 0.0 or x >= 1.0:
        return 0.0
    return 0.5 - 0.5 * math.cos(TAU * x)


def valve_lift(cyl: int, kind: str, theta: float) -> float:
    c = S.CYLINDERS[cyl - 1]
    centre = c.tdc + (S.INTAKE_CENTRE if kind == "intake" else S.EXHAUST_CENTRE)
    dur = S.INTAKE_DURATION if kind == "intake" else S.EXHAUST_DURATION
    rel = (theta - centre + 360.0) % 720.0 - 360.0       # in (-360, 360]
    return S.VALVE_LIFT * lift_profile(rel / dur + 0.5)


@dataclass(frozen=True)
class ValveGeom:
    """Everything static about one valve + its follower + its lobe (engine frame)."""

    cyl: int
    kind: str                # "intake" | "exhaust"
    side: int                # -1 / +1: which of the pair (x - / x +)
    x: float
    seat: tuple              # (y, z) seat centre on the roof plane
    tip: tuple               # (y, z) stem tip at rest
    v: tuple                 # unit (y, z) seat -> tip
    ridge: tuple             # (y, z) pent-roof ridge point for this cylinder
    pivot: tuple             # (y, z) follower pivot ball centre
    cam: tuple               # (y, z) cam axis
    roller0: tuple           # (y, z) roller centre at rest (base circle)
    pad0: tuple              # (y, z) pad centre at rest
    eps_sign: float          # +1/-1: rotation sense (about +X) that opens the valve

    @property
    def axis3(self):
        return (0.0, self.v[0], self.v[1])

    def point3(self, p):
        return (self.x, p[0], p[1])


def _bore_axis_point_at_h(c: S.Cylinder, h: float):
    up = S.bank_up(c.bank)
    s = (h - (c.foot[1] * up[1] + c.foot[2] * up[2])) / (c.axis[1] * up[1] + c.axis[2] * up[2])
    return yz(c.point(s))


def valve_geom(cyl: int, kind: str, side: int) -> ValveGeom:
    c = S.CYLINDERS[cyl - 1]
    b = c.bank
    ridge = _bore_axis_point_at_h(c, S.DECK_H + S.CHAMBER_DEPTH)
    m_ridge, h_ridge = S.bank_of_point_m_h(b, (0.0, ridge[0], ridge[1]))
    alpha = math.radians(S.VALVE_LEAN)
    sgn = 1.0 if kind == "intake" else -1.0          # +m = toward engine centre
    v_mh = (sgn * math.sin(alpha), math.cos(alpha))
    w_mh = (sgn * math.cos(alpha), -math.sin(alpha))  # in-roof, descending outward from the ridge
    seat_mh = (m_ridge + S.VALVE_LATERAL * w_mh[0], h_ridge + S.VALVE_LATERAL * w_mh[1])
    tip_mh = (seat_mh[0] + S.VALVE_LEN * v_mh[0], seat_mh[1] + S.VALVE_LEN * v_mh[1])
    pivot_mh = (S.FOLLOWER_PIVOT_M[(c.row, kind)], S.FOLLOWER_H_BAND)
    cam_mh = (S.CAM_M[kind], S.CAM_H)
    roller0_mh = (S.CAM_M[kind], S.CAM_H - (S.CAM_BASE_R + S.ROLLER_R))
    x = c.x + side * S.VALVE_X_HALF

    def eng(mh):
        return yz(S.bank_point(b, x, mh[0], mh[1]))

    seat, tip, pivot, cam, roller0 = map(eng, (seat_mh, tip_mh, pivot_mh, cam_mh, roller0_mh))
    v = norm(sub(tip, seat))
    pad0 = add(tip, mul(v, S.PAD_R))
    # Opening sense: rotating the pad about the pivot must move it along -v.
    d = sub(pad0, pivot)
    d_plus = rot_yz(d, 1.0)
    eps_sign = 1.0 if dot(sub(d_plus, d), v) < 0.0 else -1.0
    return ValveGeom(cyl=cyl, kind=kind, side=side, x=x, seat=seat, tip=tip, v=v,
                     ridge=ridge, pivot=pivot, cam=cam, roller0=roller0, pad0=pad0,
                     eps_sign=eps_sign)


def all_valves():
    out = []
    for cyl in range(1, 17):
        for kind in ("intake", "exhaust"):
            for side in (-1, 1):
                out.append(valve_geom(cyl, kind, side))
    return out


def follower_lift(g: ValveGeom, eps_deg: float) -> float:
    """Valve lift produced by rotating the follower by eps (signed about +X)."""
    pad = add(g.pivot, rot_yz(sub(g.pad0, g.pivot), eps_deg))
    return S.PAD_R - dot(sub(pad, g.tip), g.v)


def follower_angle(g: ValveGeom, lift: float) -> float:
    """Signed follower rotation (deg about +X) that produces `lift` (bisection)."""
    if lift <= 0.0:
        return 0.0
    lo, hi = 0.0, 45.0
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if follower_lift(g, g.eps_sign * mid) < lift:
            lo = mid
        else:
            hi = mid
    return g.eps_sign * 0.5 * (lo + hi)


def follower_state(g: ValveGeom, theta: float):
    """(lift, eps_deg, roller_centre_yz, pad_centre_yz) at crank angle theta."""
    lift = valve_lift(g.cyl, g.kind, theta)
    eps = follower_angle(g, lift)
    roller = add(g.pivot, rot_yz(sub(g.roller0, g.pivot), eps))
    pad = add(g.pivot, rot_yz(sub(g.pad0, g.pivot), eps))
    return lift, eps, roller, pad


def lobe_profile(g: ValveGeom, samples: int = 720):
    """Closed lobe outline in the CAM frame (theta = 0), as (y, z) points
    relative to the cam axis: the inner envelope of the roller circles.
    Every point lies on the exact envelope; the polyline between them is
    inside the true lobe, so the roller never penetrates it."""
    centres = []
    for i in range(samples):
        theta = 720.0 * i / samples
        _, _, roller, _ = follower_state(g, theta)
        q = rot_yz(sub(roller, g.cam), -cam_angle(theta))
        centres.append(q)
    pts = []
    n = len(centres)
    for i in range(n):
        p_prev = centres[i - 1]
        p_next = centres[(i + 1) % n]
        t = norm(sub(p_next, p_prev))
        # inward normal: pointing toward the cam axis
        nrm = (-t[1], t[0])
        if dot(nrm, centres[i]) > 0.0:
            nrm = (-nrm[0], -nrm[1])
        pts.append(add(centres[i], mul(nrm, S.ROLLER_R)))
    return pts


def lobe_profile_by_class(bank: int, row: str, kind: str, samples: int = 720):
    """Lobe outline for the (bank, row, kind) class with the cylinder's phase
    removed (so one profile serves every lobe of that class, rotated by its
    own phase): computed for an actual cylinder of that class and rotated back
    by that cylinder's peak cam angle."""
    cyl = next(c.number for c in S.CYLINDERS if c.bank == bank and c.row == row)
    g = valve_geom(cyl, kind, -1)
    pts = lobe_profile(g, samples)
    return [rot_yz(p, -lobe_phase(cyl, kind)) for p in pts]


def lobe_phase(cyl: int, kind: str) -> float:
    """Cam angle (deg) at which this cylinder's lobe of `kind` is at peak lift."""
    c = S.CYLINDERS[cyl - 1]
    centre = c.tdc + (S.INTAKE_CENTRE if kind == "intake" else S.EXHAUST_CENTRE)
    return (cam_angle(centre)) % 360.0


# ---------------------------------------------------------------------------
# Tables for the .anim.js (nonlinear follower solve baked to samples)
# ---------------------------------------------------------------------------

def tables(step_deg: float = 2.0):
    """Follower angle vs relative crank angle for each (bank,row,kind) class."""
    out = {}
    for bank in (1, 2):
        for row in ("inner", "outer"):
            for kind in ("intake", "exhaust"):
                cyl = next(c.number for c in S.CYLINDERS if c.bank == bank and c.row == row)
                g = valve_geom(cyl, kind, -1)
                c = S.CYLINDERS[cyl - 1]
                centre = c.tdc + (S.INTAKE_CENTRE if kind == "intake" else S.EXHAUST_CENTRE)
                dur = S.INTAKE_DURATION if kind == "intake" else S.EXHAUST_DURATION
                rel = []
                eps = []
                lift = []
                r = -dur / 2.0
                while r <= dur / 2.0 + 1e-9:
                    lf = S.VALVE_LIFT * lift_profile(r / dur + 0.5)
                    rel.append(r)
                    lift.append(lf)
                    eps.append(follower_angle(g, lf))
                    r += step_deg
                out[f"{bank}_{row}_{kind}"] = {"rel": rel, "lift": lift, "eps": eps,
                                               "centre_offset": centre - c.tdc}
    return out


if __name__ == "__main__":
    import json

    for cyl in (1, 2, 9, 10):
        lo, hi = piston_s_range(cyl)
        st0 = piston(cyl, 0.0)
        print(f"cyl {cyl}: s range {lo:.2f}..{hi:.2f} (stroke {hi - lo:.2f}), "
              f"rest s={st0.s:.2f} tilt={st0.rod_tilt:.2f}")
    g = valve_geom(1, "intake", -1)
    print("valve 1 intake -: seat", g.seat, "tip", g.tip, "pivot", g.pivot, "cam", g.cam,
          "eps_sign", g.eps_sign)
    for th in (0, 300, 400, 470, 540):
        lf, eps, roller, pad = follower_state(g, th)
        print(f"  theta {th}: lift {lf:.2f} eps {eps:.2f} roller {roller} pad {pad}")
    prof = lobe_profile(g, 360)
    rads = [math.hypot(*p) for p in prof]
    print("lobe radius range", min(rads), max(rads))
    t = tables()
    print("tables:", {k: (len(v["rel"]), max(v["eps"], key=abs)) for k, v in t.items()})


# ---------------------------------------------------------------------------
# Cam drive chain: one loop per bank around crank -> cam -> cam -> crank.
# All wraps are on the outside (every sprocket turns with the crank). The loop
# coordinate k is in LINK UNITS: one unit = one pitch on a straight run = one
# tooth (2*pi/N) on a wrap, so a roller at coordinate k + f at crank angle
# theta (f = theta/360 * N_crank) is exactly where the animation needs it and
# every tooth pocket meets its roller.
# ---------------------------------------------------------------------------

@dataclass
class Sprocket:
    name: str
    centre: tuple            # (y, z)
    teeth: int
    radius: float = 0.0      # pitch radius
    wrap_start: float = 0.0  # loop coordinate where the chain lands on this sprocket
    wrap_end: float = 0.0
    a_in: float = 0.0        # angle (rad, about +X, from +y axis) of the landing tangent point
    a_out: float = 0.0


@dataclass
class ChainLayout:
    bank: int
    pitch: float
    sprockets: list
    links: int               # M, whole number of links in the loop
    segments: list           # [(k0, k1, kind, data)] in loop order


def _pitch_radius(pitch, teeth):
    return pitch / (2.0 * math.sin(math.pi / teeth))


def _tangent(ci, ri, cj, rj):
    """External tangent from circle i to circle j for a CCW loop: returns the
    outward unit normal n and the two tangent points."""
    D = sub(cj, ci)
    L = math.hypot(*D)
    d = (D[0] / L, D[1] / L)
    r = (d[1], -d[0])                       # right of the travel direction = outward for CCW
    s = (ri - rj) / L
    c = math.sqrt(max(0.0, 1.0 - s * s))
    n = (c * r[0] + s * d[0], c * r[1] + s * d[1])
    return n, add(ci, mul(n, ri)), add(cj, mul(n, rj))


def chain_layout(bank: int, pitch: float | None = None) -> ChainLayout:
    S_ = S

    crank = Sprocket("crank", (0.0, 0.0), S_.CRANK_SPROCKET_T)
    cams = {}
    for kind in ("intake", "exhaust"):
        cams[kind] = Sprocket(f"cam_{kind}", S_.bank_point(bank, 0, S_.CAM_M[kind], S_.CAM_H)[1:], S_.CAM_SPROCKET_T)
    order = [crank, cams["exhaust"], cams["intake"]] if bank == 1 else [crank, cams["intake"], cams["exhaust"]]

    def solve(p):
        for sp in order:
            sp.radius = _pitch_radius(p, sp.teeth)
        n_s = len(order)
        tangents = []
        for i in range(n_s):
            a, b = order[i], order[(i + 1) % n_s]
            tangents.append(_tangent(a.centre, a.radius, b.centre, b.radius))
        k = 0.0
        segments = []
        for i in range(n_s):
            n, pa, pb = tangents[i]
            length = math.dist(pa, pb) / p
            segments.append((k, k + length, "straight", (pa, pb)))
            k += length
            sp = order[(i + 1) % n_s]
            n_next, _, _ = tangents[(i + 1) % n_s]
            a_in = math.atan2(n[1], n[0])
            a_out = math.atan2(n_next[1], n_next[0])
            wrap = (a_out - a_in) % TAU
            sp.wrap_start, sp.a_in, sp.a_out = k, a_in, a_out
            units = wrap * sp.teeth / TAU
            segments.append((k, k + units, "wrap", sp))
            k += units
            sp.wrap_end = k
        return k, segments

    p = pitch or S_.CHAIN_PITCH_NOMINAL
    total, segments = solve(p)
    if pitch is None:
        M = round(total)
        for _ in range(30):
            total, segments = solve(p)
            err = total - M
            if abs(err) < 1e-9:
                break
            p *= total / M
    else:
        M = int(round(total))
    # the crank wrap is the LAST segment; shift its coordinate range to start at 0 too
    return ChainLayout(bank=bank, pitch=p, sprockets=order, links=M, segments=segments)


def chain_point(layout: ChainLayout, k: float):
    """(position (y,z), travel direction unit (y,z)) at loop coordinate k."""
    k = k % layout.links
    for k0, k1, kind, data in layout.segments:
        if k0 - 1e-9 <= k <= k1 + 1e-9:
            if kind == "straight":
                pa, pb = data
                t = norm(sub(pb, pa))
                u = 0.0 if k1 == k0 else (k - k0) / (k1 - k0)
                return add(pa, mul(sub(pb, pa), u)), t
            sp = data
            a = sp.a_in + (k - k0) * TAU / sp.teeth
            pos = add(sp.centre, (sp.radius * math.cos(a), sp.radius * math.sin(a)))
            return pos, (-math.sin(a), math.cos(a))
    raise ValueError(k)


def chain_advance(theta: float) -> float:
    return theta / 360.0 * S.CRANK_SPROCKET_T


def pocket_angles(sp: Sprocket):
    """Tooth-pocket angles (rad) on a sprocket at rest: the rest roller
    positions on its wrap, continued around the full circle."""
    k_first = math.ceil(sp.wrap_start - 1e-9)
    a0 = sp.a_in + (k_first - sp.wrap_start) * TAU / sp.teeth
    return [(a0 + j * TAU / sp.teeth) % TAU for j in range(sp.teeth)]
