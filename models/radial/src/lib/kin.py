"""Radial kinematics: the ONE source of truth for where every moving part is.

Every function takes the crank angle `theta` in degrees (0 = cylinder 1 at
firing TDC; the model is authored at theta = 0). Positions are engine-frame mm
(see spec.py for the frame). `lib/animgen.py` bakes these same formulas into the
viewer animation, and `lib/collide.py` checks the geometry they place.

Motion is planar for the crank train (everything turns about ROT_AXIS or moves
in the y = const plane); the valvetrain is solved per cylinder in 3D.
"""

from __future__ import annotations

import math

from lib import spec as S


# ---------------------------------------------------------------------------
# 2D helpers in the cylinder plane: a point is (x, z); in-plane angle b maps to
# the unit vector (-sin b, cos b) (see spec.py)
# ---------------------------------------------------------------------------
def _dir(b_deg):
    b = math.radians(b_deg)
    return (-math.sin(b), math.cos(b))


def _angle_of(v):
    """In-plane angle (deg) of a 2D vector (x, z)."""
    return math.degrees(math.atan2(-v[0], v[1]))


def _add(a, b, s=1.0):
    return (a[0] + s * b[0], a[1] + s * b[1])


# ---------------------------------------------------------------------------
# Crank train
# ---------------------------------------------------------------------------
def crankpin(theta):
    return _add((0.0, 0.0), _dir(theta), S.R_CRANK)


def master_h(theta):
    """Cylinder-1 wrist-pin height along +Z."""
    c = crankpin(theta)
    return c[1] + math.sqrt(S.L_MASTER ** 2 - c[0] ** 2)


def master_angle(theta):
    """In-plane angle of the master rod (crankpin -> wrist pin 1)."""
    c = crankpin(theta)
    p = (0.0, master_h(theta))
    return _angle_of((p[0] - c[0], p[1] - c[1]))


def knuckle(theta, k):
    """Knuckle-pin centre (x, z) for articulating cylinder k (2..9)."""
    return _add(crankpin(theta), _dir(master_angle(theta) + S.KNUCKLE_ANGLE(k)), S.RHO_KNUCKLE)


def piston_h(theta, k):
    """Wrist-pin height of cylinder k along its own axis."""
    if k == 1:
        return master_h(theta)
    kx = knuckle(theta, k)
    u = _dir(S.ALPHA(k))
    d = kx[0] * u[0] + kx[1] * u[1]
    perp2 = kx[0] ** 2 + kx[1] ** 2 - d * d
    return d + math.sqrt(S.L_ART ** 2 - perp2)


def wrist_pin(theta, k):
    u = _dir(S.ALPHA(k))
    h = piston_h(theta, k)
    return (h * u[0], h * u[1])


def rod_angle(theta, k):
    """In-plane angle of rod k (master for k=1: crankpin->pin; else knuckle->pin)."""
    if k == 1:
        return master_angle(theta)
    kx, p = knuckle(theta, k), wrist_pin(theta, k)
    return _angle_of((p[0] - kx[0], p[1] - kx[1]))


def xz_to_3d(p, y=0.0):
    return (p[0], y, p[1])


# ---------------------------------------------------------------------------
# Rigid "poses" relative to the authored rest (theta = 0). A pose is a list of
# ("rotate", axis, deg, origin) / ("translate", vec) steps applied IN ORDER to
# the part as authored — exactly the viewer's premultiply semantics.
# ---------------------------------------------------------------------------
def pose_crank(theta):
    return [("rotate", S.ROT_AXIS, theta, (0.0, 0.0, 0.0))]


def pose_master(theta):
    c0, c = crankpin(0.0), crankpin(theta)
    return [("rotate", S.ROT_AXIS, master_angle(theta) - master_angle(0.0), xz_to_3d(c0)),
            ("translate", (c[0] - c0[0], 0.0, c[1] - c0[1]))]


def pose_art_rod(theta, k):
    k0, k1 = knuckle(0.0, k), knuckle(theta, k)
    return [("rotate", S.ROT_AXIS, rod_angle(theta, k) - rod_angle(0.0, k), xz_to_3d(k0)),
            ("translate", (k1[0] - k0[0], 0.0, k1[1] - k0[1]))]


def pose_piston(theta, k):
    u = _dir(S.ALPHA(k))
    dh = piston_h(theta, k) - piston_h(0.0, k)
    return [("translate", (u[0] * dh, 0.0, u[1] * dh))]


def pose_spin(theta, ratio, origin=(0.0, 0.0, 0.0), axis=S.ROT_AXIS):
    return [("rotate", axis, ratio * theta, origin)]


# ---------------------------------------------------------------------------
# Valvetrain. v is "I" (intake, +t side) or "E" (exhaust, -t side).
# ---------------------------------------------------------------------------
VALVES = ("I", "E")


def _side(v):
    return 1.0 if v == "I" else -1.0


def _v3(a):
    return tuple(float(x) for x in a)


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _addv(a, b, s=1.0):
    return (a[0] + s * b[0], a[1] + s * b[1], a[2] + s * b[2])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(a):
    return math.sqrt(_dot(a, a))


def _unit(a):
    n = _norm(a)
    return (a[0] / n, a[1] / n, a[2] / n)


def local_point(k, h, y, t):
    return S.cyl_point(k, h, y, t)


def local_dir(k, h, y, t):
    u, tt = S.cyl_u(k), S.cyl_t(k)
    return (h * u[0] + t * tt[0], y, h * u[2] + t * tt[2])


def valve_axis(k, v):
    """Unit vector along the valve stem, seat -> tip (outward)."""
    c, s = math.cos(math.radians(S.VALVE_INCLINE_DEG)), math.sin(math.radians(S.VALVE_INCLINE_DEG))
    return local_dir(k, c, 0.0, _side(v) * s)


def valve_seat(k, v):
    return local_point(k, S.VALVE_SEAT_H, 0.0, _side(v) * S.VALVE_SEAT_T)


def valve_tip(k, v):
    return _addv(valve_seat(k, v), valve_axis(k, v), S.VALVE_LENGTH)


ROCKER_PAD_R = 12.0      # spherical pad on the rocker's valve end


def rocker_pivot(k, v):
    return local_point(k, S.ROCKER_PIVOT[0], 0.0, _side(v) * S.ROCKER_PIVOT[1])


ROCKER_AXIS = (0.0, 1.0, 0.0)   # every rocker shaft runs fore-aft


def pushrod_top0(k, v):
    h, y, t = S.PUSHROD_SOCKET
    return local_point(k, h, y, _side(v) * t)


def tappet_angle(k, v):
    """In-plane angle of the tappet axis (exhaust at +delta -> -t side)."""
    return S.ALPHA(k) - _side(v) * S.TAPPET_DELTA_DEG


def tappet_dir(k, v):
    return S.inplane(tappet_angle(k, v))


def pushrod_bottom0(k, v):
    return S.inplane(tappet_angle(k, v), S.TAPPET_SOCKET_R, S.TAPPET_Y[v])


def cam_angle(theta):
    """Cam-ring rotation (deg about ROT_AXIS) at crank angle theta."""
    return S.CAM_RATIO * theta


def lobe_width(v):
    """Angular width of a lobe on the ring (ring degrees)."""
    return S.VALVE_DURATION[v] * abs(S.CAM_RATIO)


def lobe_phase(v):
    """In-plane angle (at theta = 0) of one lobe CENTRE of track v; the others are +90 k.
    Derived from cylinder 1's timing; check_timing() proves it serves all nine."""
    theta_c = S.firing_tdc(1) + S.VALVE_OPEN[v] + S.VALVE_DURATION[v] / 2.0
    return (tappet_angle(1, v) - S.CAM_RATIO * theta_c) % (360.0 / S.CAM_LOBES)


def lift_profile(rho, v):
    """Tappet lift for ring-relative angle rho (deg, 0 = lobe centre)."""
    w = lobe_width(v)
    if abs(rho) >= w / 2.0:
        return 0.0
    return S.TAPPET_LIFT[v] * math.sin(math.pi * (rho / w + 0.5)) ** 2


def _wrap(a, period):
    return (a + period / 2.0) % period - period / 2.0


def tappet_rho(theta, k, v):
    return _wrap(tappet_angle(k, v) - (lobe_phase(v) + cam_angle(theta)), 360.0 / S.CAM_LOBES)


def tappet_lift(theta, k, v):
    return lift_profile(tappet_rho(theta, k, v), v)


def pushrod_length(v):
    return _norm(_sub(pushrod_top0(1, v), pushrod_bottom0(1, v)))


def _rot_about(p, axis, deg, origin):
    R = _rot_matrix(axis, deg)
    d = _sub(p, origin)
    return _addv(origin, (sum(R[0][j] * d[j] for j in range(3)),
                          sum(R[1][j] * d[j] for j in range(3)),
                          sum(R[2][j] * d[j] for j in range(3))))


def _rocker_angle_for(k, v, lift_t):
    """Rocker angle (deg about ROCKER_AXIS) that keeps the pushrod at its length
    when the tappet has lifted by lift_t. The rest pose (lift 0) is angle 0."""
    B = _addv(pushrod_bottom0(k, v), tappet_dir(k, v), lift_t)
    P, T0, L = rocker_pivot(k, v), pushrod_top0(k, v), pushrod_length(v)
    f = lambda a: _norm(_sub(_rot_about(T0, ROCKER_AXIS, a, P), B)) - L
    a = 0.0
    for _ in range(50):
        fa = f(a)
        if abs(fa) < 1e-11:
            break
        d = (f(a + 1e-5) - f(a - 1e-5)) / 2e-5
        a -= fa / d
    return a


def rocker_angle(theta, k, v):
    return _rocker_angle_for(k, v, tappet_lift(theta, k, v))


def pad_centre0(k, v):
    return _addv(valve_tip(k, v), valve_axis(k, v), ROCKER_PAD_R)


def valve_lift_for_rocker(k, v, angle):
    c0 = pad_centre0(k, v)
    c = _rot_about(c0, ROCKER_AXIS, angle, rocker_pivot(k, v))
    return _dot(_sub(c0, c), valve_axis(k, v))


def valve_lift(theta, k, v):
    return valve_lift_for_rocker(k, v, rocker_angle(theta, k, v))


# ---- rest-relative poses of valvetrain parts (these parts are authored at
# ZERO LIFT, rocker angle 0: `place(shape, pose_x(0, ...))` puts a copy at
# theta = 0, and the animation applies pose(theta) after undoing pose(0)) ---
def pose_tappet(theta, k, v):
    return [("translate", _v3(_mul(tappet_dir(k, v), tappet_lift(theta, k, v))))]


def _mul(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def pose_rocker(theta, k, v):
    return [("rotate", ROCKER_AXIS, rocker_angle(theta, k, v), rocker_pivot(k, v))]


def pose_valve(theta, k, v):
    return [("translate", _mul(valve_axis(k, v), -valve_lift(theta, k, v)))]


def pose_pushrod(theta, k, v):
    B0, T0 = pushrod_bottom0(k, v), pushrod_top0(k, v)
    lift_t = tappet_lift(theta, k, v)
    B = _addv(B0, tappet_dir(k, v), lift_t)
    T = _rot_about(T0, ROCKER_AXIS, _rocker_angle_for(k, v, lift_t), rocker_pivot(k, v))
    d0, d1 = _unit(_sub(T0, B0)), _unit(_sub(T, B))
    ax = _cross(d0, d1)
    s = _norm(ax)
    steps = []
    if s > 1e-12:
        ang = math.degrees(math.atan2(s, _dot(d0, d1)))
        steps.append(("rotate", _unit(ax), ang, B0))
    steps.append(("translate", _sub(B, B0)))
    return steps


def pose_cam_ring(theta):
    return pose_spin(theta, S.CAM_RATIO)


# ---- gear trains and the other rotating parts ---------------------------------
def cam_idler_axis_point():
    return S.inplane(S.CAM_IDLER_ANGLE, S.CAM_IDLER_R)


def cam_idler_ratio():
    return -S.CAM_CRANK_GEAR[0] / S.CAM_IDLER[0][0]          # -2/3


def pose_cam_idler(theta):
    return [("rotate", S.ROT_AXIS, cam_idler_ratio() * theta, cam_idler_axis_point())]


def tappet_roller_centre0(k, v):
    return S.inplane(tappet_angle(k, v), S.CAM_BASE_R + S.TAPPET_ROLLER_R, S.TAPPET_Y[v])


def tappet_roller_spin(theta):
    """Roller angle about its axle (parallel to ROT_AXIS): rolls on the ring's base circle."""
    return -cam_angle(theta) * S.CAM_BASE_R / S.TAPPET_ROLLER_R


def pose_tappet_roller(theta, k, v):
    return [("rotate", S.ROT_AXIS, tappet_roller_spin(theta), tappet_roller_centre0(k, v)),
            ("translate", _mul(tappet_dir(k, v), tappet_lift(theta, k, v)))]


def carrier_angle(theta):
    return S.RED_RATIO * theta


def planet_centre0(j):
    """Planet j (1..6) axis point at theta = 0; planet 1 at in-plane 0 deg."""
    return S.inplane(60.0 * (j - 1), S.RED_PLANET_R, sum(S.RED_FACE_Y) / 2.0)


def pose_planet(theta, j):
    c = carrier_angle(theta)
    spin = c * (S.RED_SUN_T / S.RED_PLANET_T)        # relative to the carrier (fixed sun)
    return [("rotate", S.ROT_AXIS, spin, planet_centre0(j)),
            ("rotate", S.ROT_AXIS, c, (0.0, 0.0, 0.0))]


def pose_propshaft(theta):
    return pose_spin(theta, S.RED_RATIO)


def pose_prop(theta):
    return pose_spin(theta, S.RED_RATIO)


def pose_impeller(theta):
    return pose_spin(theta, S.BLOWER_RATIO)


def blower_gear_centre(j):
    return S.inplane(S.BLOWER_INTERMEDIATE_ANGLES[j - 1], S.BLOWER_INTERMEDIATE_R)


def pose_blower_gear(theta, j):
    ratio = -S.BLOWER_CRANK_GEAR[0] / S.BLOWER_INTERMEDIATE[0][0]    # -3
    return [("rotate", S.ROT_AXIS, ratio * theta, blower_gear_centre(j))]


# ---- valve springs: helices that COMPRESS with the valve ----------------------
SPRING_SEAT_FROM_TIP = 64.0      # spring-seat plane, measured down the stem from the tip
SPRING_TOP_FROM_TIP = 14.0       # retainer underside at zero lift
SPRINGS = {  # mean radius, wire diameter, turns
    "outer": (17.0, 4.2, 5.5),
    "inner": (11.5, 3.0, 7.0),
}


def spring_length(theta, k, v):
    return SPRING_SEAT_FROM_TIP - SPRING_TOP_FROM_TIP - valve_lift(theta, k, v)


def spring_frame(k, v):
    """(base centre, axis (outward), x-ref, y-ref) of the spring on its seat plane."""
    ax = valve_axis(k, v)
    base = _addv(valve_tip(k, v), ax, -SPRING_SEAT_FROM_TIP)
    xr = _unit(_cross(ax, (0.0, 1.0, 0.0)))
    yr = _cross(ax, xr)
    return base, ax, xr, yr


def spring_path(theta, k, v, which):
    """The spring's wire centreline at crank angle theta as cubic Bezier segments
    (quarter turns, tangent-continuous): {"normal": axis, "segments": [...]},
    exactly the form the viewer's tube deformation takes. Build the spring by
    sweeping its wire circle along THESE curves at theta = 0."""
    R, wire, turns = SPRINGS[which]
    base, ax, xr, yr = spring_frame(k, v)
    L = spring_length(theta, k, v) - wire          # wire centre from r_w above the seat to r_w below the retainer
    z0 = wire / 2.0
    nseg = int(round(turns * 4))
    dz = L / nseg
    kk = 4.0 / 3.0 * math.tan(math.pi / 8.0) * R
    phase0 = 90.0 if which == "outer" else 270.0   # stagger the wire ends of the two springs

    def P(ang_deg, z):
        a = math.radians(ang_deg)
        return _addv(_addv(_addv(base, xr, R * math.cos(a)), yr, R * math.sin(a)), ax, z)

    def T(ang_deg):
        a = math.radians(ang_deg)
        return _addv(_mul(xr, -math.sin(a)), yr, math.cos(a))

    segs = []
    for i in range(nseg):
        a0, a1 = phase0 + 90.0 * i, phase0 + 90.0 * (i + 1)
        zs, ze = z0 + dz * i, z0 + dz * (i + 1)
        p0, p3 = P(a0, zs), P(a1, ze)
        p1 = _addv(_addv(p0, T(a0), kk), ax, dz / 3.0)
        p2 = _addv(_addv(p3, T(a1), -kk), ax, -dz / 3.0)
        segs.append({"kind": "bezier", "points": [list(p0), list(p1), list(p2), list(p3)]})
    return {"normal": list(ax), "segments": segs}


def check_timing():
    """Every cylinder's valve events happen at the intended crank angles (+-0.01 deg),
    from the SAME four lobes per track."""
    for k in range(1, S.N_CYL + 1):
        for v in VALVES:
            centre = S.firing_tdc(k) + S.VALVE_OPEN[v] + S.VALVE_DURATION[v] / 2.0
            assert abs(tappet_rho(centre, k, v)) < 1e-6, (k, v, tappet_rho(centre, k, v))
            assert abs(tappet_lift(centre, k, v) - S.TAPPET_LIFT[v]) < 1e-9
            for dt in (-S.VALVE_DURATION[v] / 2.0 - 1.0, S.VALVE_DURATION[v] / 2.0 + 1.0):
                assert tappet_lift(centre + dt, k, v) == 0.0, (k, v, dt)


# ---------------------------------------------------------------------------
# Applying a pose in Python (the collision gate and builders use this)
# ---------------------------------------------------------------------------
def _rot_matrix(axis, deg):
    ax = math.sqrt(sum(a * a for a in axis))
    x, y, z = (a / ax for a in axis)
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    C = 1 - c
    return ((c + x * x * C, x * y * C - z * s, x * z * C + y * s),
            (y * x * C + z * s, c + y * y * C, y * z * C - x * s),
            (z * x * C - y * s, z * y * C + x * s, c + z * z * C))


def pose_matrix(pose):
    """4x4 row-major matrix (as nested tuples) of a pose."""
    M = [[1.0, 0, 0, 0], [0, 1.0, 0, 0], [0, 0, 1.0, 0], [0, 0, 0, 1.0]]
    for step in pose:
        if step[0] == "translate":
            T = [[1.0, 0, 0, step[1][0]], [0, 1.0, 0, step[1][1]], [0, 0, 1.0, step[1][2]], [0, 0, 0, 1.0]]
        else:
            _, axis, deg, o = step
            R = _rot_matrix(axis, deg)
            T = [[R[i][0], R[i][1], R[i][2], o[i] - sum(R[i][j] * o[j] for j in range(3))] for i in range(3)]
            T.append([0, 0, 0, 1.0])
        M = [[sum(T[i][k] * M[k][j] for k in range(4)) for j in range(4)] for i in range(4)]
    return M


def apply_point(pose, p):
    M = pose_matrix(pose)
    return tuple(M[i][0] * p[0] + M[i][1] * p[1] + M[i][2] * p[2] + M[i][3] for i in range(3))


def place(shape, pose):
    """Copy of `shape` moved by `pose` (build123d)."""
    from cadgen import build123d as bd
    M = pose_matrix(pose)
    from OCP.gp import gp_Trsf
    tr = gp_Trsf()
    tr.SetValues(M[0][0], M[0][1], M[0][2], M[0][3],
                 M[1][0], M[1][1], M[1][2], M[1][3],
                 M[2][0], M[2][1], M[2][2], M[2][3])
    return bd.Location(tr) * shape


# ---------------------------------------------------------------------------
# Self-report: python -m lib.kin
# ---------------------------------------------------------------------------
def report():
    check_timing()
    for v in VALVES:
        lifts = [valve_lift_for_rocker(1, v, _rocker_angle_for(1, v, S.TAPPET_LIFT[v] * i / 10)) for i in range(11)]
        print(f"valve {v}: lobe phase {lobe_phase(v):.3f} deg, width {lobe_width(v):.2f} deg, "
              f"pushrod {pushrod_length(v):.1f} mm, max valve lift {lifts[-1]:.2f} mm, "
              f"max rocker angle {_rocker_angle_for(1, v, S.TAPPET_LIFT[v]):.2f} deg")
    print("cyl  TDC_h    BDC_h    stroke  maxRodAng  rest_h(theta=0)")
    for k in range(1, S.N_CYL + 1):
        hs = [piston_h(i / 4.0, k) for i in range(1440)]
        angs = [abs(((rod_angle(i / 4.0, k) - S.ALPHA(k)) + 180) % 360 - 180) for i in range(1440)]
        print(f"{k:>3}  {max(hs):7.2f}  {min(hs):7.2f}  {max(hs) - min(hs):6.2f}  {max(angs):6.2f}     {piston_h(0.0, k):7.2f}")


if __name__ == "__main__":
    report()
