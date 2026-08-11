"""Floor, venturi tunnels, floor edge, fences, plank; diffuser, strakes, gurney.

The floor is one continuous shell, and every station is a closed cross-section
whose WETTED side is drawn as a polyline of straight runs joined by explicit
small-radius corner arcs (`_poly`).  That is the whole trick of this module:
a spline through evenly spaced points rounds everything it touches, so a
venturi tunnel described by six control points comes out as a soft dish.  By
emitting a real 4-point arc of radius 7-11 mm at each corner and subdividing
the runs between them, the same spline is forced to hold a flat keel, a steep
inboard tunnel wall, an arched roof and a crisp outboard wall — the channel
reads as something CARVED into the underside rather than pressed into it.

The topside is NOT an offset of that polyline.  Offsetting a 9 mm corner by a
20 mm skin folds the surface, and a constant-thickness shell also mirrors every
underside feature onto the deck, which is what turned this part into a smooth
blob.  The deck is its own smooth law — keel spine, crest over the tunnel,
fall to the floor-edge flank — clamped to stay above the wetted side.

The outboard element is one continuous idea from x = 780 to the exit plane: a
downturned edge wing whose bottom bead is the car's lowest visible line, and
whose flank grows into the diffuser side wall as `wall_f` goes 0 -> 1.  The
floor edge therefore never fades out; it turns into the diffuser.
"""

from __future__ import annotations

import math

from build123d import Cylinder, Plane, Pos, Vector, make_face

from . import lib, spec

# ==========================================================================
# 2-D polyline machinery — hard corners inside a spline section
# ==========================================================================


def _dist(a, b) -> float:
    return math.hypot(b[0] - a[0], b[1] - a[1])


def _unit(a, b):
    d = _dist(a, b) or 1.0
    return ((b[0] - a[0]) / d, (b[1] - a[1]) / d)


def _corner_pts(p0, p1, p2, r: float, n: int = 4):
    """Arc of radius `r` replacing the vertex p1, tangent to both runs."""
    d0 = _unit(p0, p1)
    d1 = _unit(p1, p2)
    cross = d0[0] * d1[1] - d0[1] * d1[0]
    dot = d0[0] * d1[0] + d0[1] * d1[1]
    turn = math.atan2(cross, dot)
    if r <= 0.0 or abs(turn) < 0.03:
        return [p1]
    half = abs(turn) / 2.0
    t = min(r * math.tan(half), 0.42 * _dist(p0, p1), 0.42 * _dist(p1, p2))
    if t < 0.9:
        return [p1]
    r_eff = t / math.tan(half)
    n = max(2, min(n, int(r_eff * abs(turn) / 1.6)))
    ps = (p1[0] - d0[0] * t, p1[1] - d0[1] * t)
    sgn = 1.0 if turn > 0 else -1.0
    c = (ps[0] - d0[1] * sgn * r_eff, ps[1] + d0[0] * sgn * r_eff)
    vy, vz = ps[0] - c[0], ps[1] - c[1]
    out = []
    for k in range(n + 1):
        a = turn * k / n
        ca, sa = math.cos(a), math.sin(a)
        out.append((c[0] + vy * ca - vz * sa, c[1] + vy * sa + vz * ca))
    return out


def _fill(a, b, max_seg: float):
    """Interior points that keep a straight run's sampling near the arcs'."""
    d = _dist(a, b)
    n = int(d // max_seg)
    if n < 1:
        return []
    return [
        (a[0] + (b[0] - a[0]) * i / (n + 1), a[1] + (b[1] - a[1]) * i / (n + 1))
        for i in range(1, n + 1)
    ]


def _poly(verts, max_seg: float = 24.0, arc_n: int = 4):
    """Densified polyline from (y, z, corner_radius) key vertices."""
    pieces = [[verts[0][:2]]]
    for i in range(1, len(verts) - 1):
        pieces.append(
            _corner_pts(
                verts[i - 1][:2], verts[i][:2], verts[i + 1][:2], verts[i][2], arc_n
            )
        )
    pieces.append([verts[-1][:2]])
    out = list(pieces[0])
    for pc in pieces[1:]:
        out += _fill(out[-1], pc[0], max_seg)
        out += pc
    return _dedup(out)


def _dedup(pts, min_gap: float = 1.6):
    """Drop points a periodic spline cannot tell apart from their neighbour.

    A corner arc squeezed by a short adjacent run can collapse to a few points
    0.15 mm apart; the spline through them and their 26 mm neighbours is what
    fails `make_face` with OCC's opaque "BRep_API: command not done".
    """
    out = [pts[0]]
    for p in pts[1:-1]:
        if _dist(out[-1], p) >= min_gap:
            out.append(p)
    if _dist(out[-1], pts[-1]) < min_gap and len(out) > 1:
        out.pop()
    out.append(pts[-1])
    return out


# ==========================================================================
# station tables
# ==========================================================================


def _tab(table, x):
    """Linear lookup on a (station_x, value) table written front -> rear."""
    if x >= table[0][0]:
        return table[0][1]
    if x <= table[-1][0]:
        return table[-1][1]
    for i in range(len(table) - 1):
        x0, v0 = table[i]
        x1, v1 = table[i + 1]
        if x1 <= x <= x0:
            return spec.lerp(v0, v1, (x0 - x) / (x0 - x1))
    return table[-1][1]


# Plan-form half width.  Necked in around both tyres (front tyre inner face
# 682.5, rear 577.5), flared to its widest across the sidepod, then drawn into
# the coke-bottle waist ahead of the rear wheel.
_HW = (
    (780.0, 318.0),
    (740.0, 396.0),
    (700.0, 452.0),
    (620.0, 532.0),
    (520.0, 600.0),
    (400.0, 634.0),
    (250.0, 642.0),
    (80.0, 640.0),
    (-100.0, 642.0),
    (-260.0, 648.0),
    (-380.0, 664.0),
    (-560.0, 748.0),
    (-760.0, 836.0),
    (-1000.0, 872.0),
    (-1400.0, 888.0),
    (-1900.0, 892.0),
    (-2300.0, 888.0),
    (-2600.0, 862.0),
    (-2900.0, 776.0),
    (-3050.0, 656.0),
    (-3120.0, 600.0),
    (-3200.0, 552.0),
    (-3320.0, 536.0),
    (-3500.0, 528.0),
    (-3700.0, 532.0),
    (-3820.0, 544.0),
)

# Tunnel-roof crown height above the LOCAL keel underside.  Tall inlet mouth,
# a genuine throat under the sidepod undercut (the roof has to duck below the
# undercut lip or it swallows the sidepod's best feature), then a long
# expansion into the diffuser.
_TUNNEL_H = (
    (780.0, 94.0),
    (740.0, 110.0),
    (700.0, 126.0),
    (620.0, 152.0),
    (520.0, 174.0),
    (400.0, 190.0),
    (250.0, 200.0),
    (80.0, 206.0),
    (-100.0, 208.0),
    (-300.0, 204.0),
    (-560.0, 190.0),
    (-760.0, 166.0),
    (-900.0, 140.0),
    (-1100.0, 118.0),
    (-1300.0, 108.0),
    (-1600.0, 104.0),
    (-1900.0, 110.0),
    (-2200.0, 126.0),
    (-2500.0, 152.0),
    (-2800.0, 186.0),
    (-3050.0, 214.0),
    (-3120.0, 228.0),
)

# Half width of the flat central keel.  It tracks the survival cell's belly
# (measured off `mono_tub`: 195 at the bulkhead, 344 by the cockpit rear) plus
# a margin, so the tunnels start OUTBOARD of the tub instead of running the
# roof up through it, and the keel reads as a wide flat spine.
_KEEL_Y = (
    (780.0, 172.0),
    (700.0, 208.0),
    (620.0, 218.0),
    (480.0, 234.0),
    (300.0, 264.0),
    (80.0, 300.0),
    (-100.0, 316.0),
    (-330.0, 330.0),
    (-700.0, 344.0),
    (-1100.0, 354.0),
    (-1420.0, 358.0),
    (-1700.0, 360.0),
    (-1980.0, 350.0),
    (-2400.0, 320.0),
    (-2900.0, 262.0),
    (-3120.0, 232.0),
    (-3450.0, 186.0),
    (-3820.0, 158.0),
)

# Wall thickness (in Y) of the outboard element: the downturned edge wing up
# front, the diffuser side wall at the back.
_WALL_T = (
    (780.0, 15.0),
    (400.0, 17.0),
    (-1600.0, 19.0),
    (-2900.0, 19.0),
    (-3120.0, 18.0),
    (-3450.0, 16.0),
    (-3820.0, 15.0),
)

# Absolute z of the edge-wing bottom bead — the car's lowest visible line.  It
# rises gently down the length of the floor and then flares back DOWN through
# the diffuser while the roof soars away from it.
_WALL_BOT = (
    (780.0, 34.0),
    (400.0, 36.0),
    (0.0, 40.0),
    (-1000.0, 46.0),
    (-2000.0, 52.0),
    (-2900.0, 58.0),
    (-3120.0, 60.0),
    (-3400.0, 54.0),
    (-3600.0, 48.0),
    (-3820.0, 44.0),
)

# Top of the centre keel spine.  Hugs the tub / PU / gearbox floor above it.
_KEEL_TOP = (
    (780.0, 92.0),
    (700.0, 96.0),
    (480.0, 98.0),
    (0.0, 102.0),
    (-560.0, 116.0),
    (-1100.0, 140.0),
    (-1600.0, 168.0),
    (-1980.0, 190.0),
    (-2400.0, 192.0),
    (-2900.0, 186.0),
    (-3120.0, 182.0),
    (-3312.0, 208.0),
    (-3450.0, 240.0),
    (-3600.0, 276.0),
    (-3820.0, 312.0),
)

_SHELL_T = (
    (780.0, 12.0),
    (620.0, 15.0),
    (400.0, 18.0),
    (-1600.0, 18.0),
    (-3120.0, 17.0),
    (-3450.0, 15.0),
    (-3820.0, 13.0),
)

# --- scalloped floor-edge plan profile -------------------------------------

_SCALLOP_FRONT = -520.0
_SCALLOP_REAR = -2980.0
_SCALLOP_LOBES = 2.5
_SCALLOP_A = 46.0
_SCALLOP_LIFT = 17.0


def _scallop(x: float):
    """(inboard notch, bottom-edge lift) of the wavy floor-edge plan profile."""
    if x > _SCALLOP_FRONT or x < _SCALLOP_REAR:
        return 0.0, 0.0
    s = (_SCALLOP_FRONT - x) / (_SCALLOP_FRONT - _SCALLOP_REAR)
    win = math.sin(math.pi * s) ** 0.55
    lobe = 0.5 - 0.5 * math.cos(2.0 * math.pi * _SCALLOP_LOBES * s)
    return _SCALLOP_A * lobe * win, _SCALLOP_LIFT * lobe * win


# ==========================================================================
# longitudinal laws
# ==========================================================================

_KEEL_EXIT_Z = 200.0  # centre spine underside at the exit plane
_ROOF_EXIT_Z = spec.DIFFUSER_EXIT_Z  # 385 — crown of the exit arch


def _ramp_t(x: float) -> float:
    t = (spec.DIFFUSER_START_X - x) / (spec.DIFFUSER_START_X - spec.FLOOR_TE_X)
    return min(max(t, 0.0), 1.0)


def _wall_f(x: float) -> float:
    """0 on the flat floor, 1 at the exit: edge wing -> diffuser side wall."""
    return _ramp_t(x) ** 0.85


def _keel_bot(x: float) -> float:
    """Underside of the centre keel: raked flat floor, then the diffuser ramp."""
    if x >= spec.DIFFUSER_START_X:
        return spec.floor_z(x)
    t = _ramp_t(x)
    z0 = spec.floor_z(spec.DIFFUSER_START_X)
    # a real kick line: non-zero slope at t = 0 (about 6 deg against the
    # floor's 0.7 deg rake), then a strongly curved expansion.
    return z0 + (_KEEL_EXIT_Z - z0) * (0.26 * t + 0.74 * t**2.3)


def _roof_z(x: float) -> float:
    if x >= spec.DIFFUSER_START_X:
        return spec.floor_z(x) + _tab(_TUNNEL_H, x)
    t = _ramp_t(x)
    z0 = spec.floor_z(spec.DIFFUSER_START_X) + _tab(_TUNNEL_H, spec.DIFFUSER_START_X)
    return z0 + (_ROOF_EXIT_Z - z0) * (0.30 * t + 0.70 * t**1.9)


# ==========================================================================
# one station
# ==========================================================================

_ST_CACHE: dict = {}


def _build_station(x: float) -> dict:
    notch, lift = _scallop(x)
    wf = _wall_f(x)
    zk = _keel_bot(x)
    zr = _roof_z(x)
    h = max(zr - zk, 30.0)

    hw = _tab(_HW, x) - notch
    yk = _tab(_KEEL_Y, x)
    wt = _tab(_WALL_T, x)
    t = _tab(_SHELL_T, x)
    zb = _tab(_WALL_BOT, x) + lift

    ywi = hw - wt  # inner face of the outboard wall
    span = max(ywi - yk, 60.0)

    # How far the roof falls on its way OUT to the wall: a lot on the flat
    # floor (the roof has to duck under the sidepod undercut), much less in the
    # diffuser.  `arch_in` does the same at the inboard end, so the diffuser
    # exit is a genuine ARCH springing off the keel and the side wall rather
    # than a flat lid — from behind, that is the whole difference between two
    # tunnels flaring open and one rectangular hole.
    drop = lib.taper(0.56, 0.22, wf)
    arch_in = h * 0.22 * wf
    zro = max(zk + h * (1.0 - drop), zb + 34.0)

    ri = max(min(0.24 * span, 0.44 * h) * (1.0 - 0.55 * wf), 15.0)
    ro = max(min(0.26 * span, 0.60 * (zro - zb)) * (1.0 - 0.75 * wf), 13.0)
    if ri + ro > 0.78 * span:
        k = 0.78 * span / (ri + ro)
        ri, ro = ri * k, ro * k

    roof_run = span - ri - ro
    y_crown = yk + ri + lib.taper(0.26, 0.46, wf) * roof_run
    z_crown = zr + 3.0 * (1.0 - wf)
    z_spring = zr - arch_in  # roof height where the inboard wall tops out

    lean = 7.0 + 15.0 * wf
    y_flank = hw - 0.05 * wt - lean
    z_flank = zro + 0.82 * t

    st = {
        "x": x,
        "wf": wf,
        "zk": zk,
        "zr": zr,
        "zro": zro,
        "z_spring": z_spring,
        "zb": zb,
        "hw": hw,
        "yk": yk,
        "wt": wt,
        "t": t,
        "ywi": ywi,
        "run_in": ri,
        "run_out": ro,
        "y_crown": y_crown,
        "z_crown": z_crown,
        "y_flank": y_flank,
        "z_flank": z_flank,
        "z_deck0": _tab(_KEEL_TOP, x),
        "y_in": yk + ri,
        "y_out": ywi - ro,
    }
    st["under"] = _poly(_under_verts(st), max_seg=42.0, arc_n=3)
    return st


def _station(x: float) -> dict:
    key = round(float(x), 3)
    st = _ST_CACHE.get(key)
    if st is None:
        st = _build_station(float(x))
        _ST_CACHE[key] = st
    return st


def _under_verts(st: dict):
    """Key vertices of the wetted side: keel -> tunnel -> edge-wing bead."""
    zk, zro, zb = st["zk"], st["zro"], st["zb"]
    yk, ywi, hw, wt = st["yk"], st["ywi"], st["hw"], st["wt"]
    return [
        (0.0, zk, 0.0),
        (yk * 0.58, zk, 0.0),
        (yk, zk, 9.0),  # foot of the inboard tunnel wall
        (yk + st["run_in"], st["z_spring"], 11.0),  # its top, into the roof
        (st["y_crown"], st["z_crown"], 0.0),  # arch crown
        (st["y_out"], zro, 11.0),  # roof rolls into the outboard wall
        (ywi, zb + 9.0, 7.0),  # foot of the outboard wall
        (hw - 0.72 * wt, zb, 3.5),  # bottom bead, inner corner
        (hw - 0.05 * wt, zb + 2.6, 3.5),  # bottom bead, outermost point
        (st["y_flank"], st["z_flank"], 10.0),  # flank meets the deck
    ]


def _deck_pts(st: dict):
    """Smooth topside, flank corner -> crest over the tunnel -> keel spine."""
    y_f, z_f = st["y_flank"], st["z_flank"]
    y_c = st["y_crown"]
    z_c = st["z_crown"] + st["t"]
    y_k = st["yk"] * 0.90
    z_k = min(st["z_deck0"], z_c - 6.0)

    pts = []
    for i in range(1, 7):
        u = i / 6.0
        pts.append((y_f + (y_c - y_f) * u, z_f + (z_c - z_f) * spec.smoothstep(u)))
    for i in range(1, 8):
        u = i / 7.0
        pts.append((y_c + (y_k - y_c) * u, z_c + (z_k - z_c) * spec.smoothstep(u)))
    pts.append((y_k * 0.5, z_k))
    pts.append((0.0, z_k))
    # The deck must clear the wetted side even where the two laws cross — over
    # the steep inboard tunnel wall the keel spine's top is far BELOW the roof,
    # so a plain max() puts a hard kink in the deck and the periodic spline
    # through it overshoots straight into the underside.  A soft max keeps the
    # skin over the wall smooth and never thinner than `gap`.
    gap, k = 12.0, 26.0
    out = []
    for y, z in pts:
        b = _under_z(st, y) + gap
        out.append((y, 0.5 * (z + b + math.sqrt((z - b) ** 2 + k * k))))
    return out


def _under_z(st: dict, y: float) -> float:
    """Wetted-side height at |y| (linear between polyline points)."""
    pts = st["under"]
    y = abs(y)
    if y <= pts[0][0]:
        return pts[0][1]
    best = pts[-1][1]
    for i in range(len(pts) - 1):
        y0, z0 = pts[i]
        y1, z1 = pts[i + 1]
        if y0 <= y <= y1 and y1 > y0:
            return z0 + (z1 - z0) * (y - y0) / (y1 - y0)
        if y > y1:
            best = z1
    return best


def _section_pts(st: dict):
    return list(st["under"]) + _deck_pts(st)


def _section_face(st: dict):
    return lib.half_section_face(st["x"], _section_pts(st))


def _tunnel_band(x: float):
    """(inboard, outboard) y limits of the open tunnel at station x."""
    st = _station(x)
    return st["y_in"], st["y_out"]


def _band_y(x: float, f: float) -> float:
    a, b = _tunnel_band(x)
    return a + (b - a) * f


# ==========================================================================
# lofts
# ==========================================================================


def _loft_stack(xs):
    """Loft a station stack, coarsening if OCC refuses the full set."""
    faces = [_section_face(_station(x)) for x in xs]
    trials = [faces]
    for step in (2, 3):
        sub = faces[::step]
        if sub[-1] is not faces[-1]:
            sub = sub + [faces[-1]]
        if len(sub) >= 3:
            trials.append(sub)
    trials.append([faces[0], faces[len(faces) // 2], faces[-1]])
    last = None
    for fs in trials:
        try:
            out = lib.body_loft(fs)
            if lib.is_valid_shape(out):
                return out
        except Exception as exc:  # noqa: BLE001
            last = exc
    raise RuntimeError(f"floor loft failed: {last}")


_FLOOR_X = (
    780.0, 748.0, 714.0, 678.0, 640.0, 600.0, 556.0, 508.0, 452.0, 392.0,
    326.0, 254.0, 176.0, 92.0, 0.0, -104.0, -216.0, -338.0, -470.0, -610.0,
    -760.0, -920.0, -1090.0, -1270.0, -1450.0, -1630.0, -1810.0, -1990.0,
    -2170.0, -2350.0, -2530.0, -2700.0, -2850.0, -2970.0, -3060.0, -3120.0,
)

_DIFF_X = (
    -3120.0, -3172.0, -3230.0, -3294.0, -3364.0, -3440.0, -3522.0, -3610.0,
    -3700.0, -3768.0, -3820.0,
)


# ==========================================================================
# vane machinery — the ONE aerofoil family, stood on end
# ==========================================================================


def _vane(stations):
    """Loft a VERTICAL aerofoil vane through raked/yawed station planes."""
    faces = []
    for st in stations:
        wire = lib.airfoil_profile(
            st["chord"],
            thickness=st.get("thickness", 0.070),
            camber=st.get("camber", 0.0),
            camber_pos=st.get("camber_pos", 0.42),
            te_thickness=st.get("te"),
        )
        faces.append(st["plane"] * make_face(wire))
    return lib.loft_solid(faces)


def _vane_plane(le, yaw_deg=0.0, tilt_deg=0.0):
    """Plane for a VERTICAL vane section: local +x rearward, +y outboard.

    `yaw_deg` turns the section outboard about the vertical; `tilt_deg` rakes
    the section so a vane's upper edge can follow a rising floor surface.
    """
    ca, sa = math.cos(math.radians(tilt_deg)), math.sin(math.radians(tilt_deg))
    plane = Plane(origin=Vector(le), x_dir=(-ca, 0.0, sa), z_dir=(sa, 0.0, ca))
    if yaw_deg:
        # NOTE the sign: the section's local +x runs REARWARD, so a positive
        # rotation about world Z swings the trailing edge INBOARD.  Negating
        # here makes `yaw_deg` mean what every caller assumes — trailing edge
        # outboard — which is the bug that had the fence array marching into
        # the keel instead of fanning out with the tunnel.
        plane = plane.rotated((0.0, 0.0, -yaw_deg))
    return plane


def _rect_pts(length, height, corner, flats=5):
    """Rounded rectangle sampled along its flats as well as its corners."""
    r = min(corner, length * 0.45, height * 0.45)
    pts = lib.rounded_plate_pts(length, height, r, samples=4)
    out = []
    n = len(pts)
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        out.append(a)
        d = math.hypot(b[0] - a[0], b[1] - a[1])
        if d > 1.6 * r:
            for k in range(1, flats):
                f = k / flats
                out.append((a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f))
    return out


# ==========================================================================
# A. FLOOR
# ==========================================================================


def _floor_shell():
    return _loft_stack(_FLOOR_X)


# --- floor fences ----------------------------------------------------------
# Four per side, standing in the tunnel inlet.  Each one is placed by the same
# FRACTION across the open tunnel at its leading and trailing edges, so the
# array fans out exactly as the tunnel flares and can never be swallowed by the
# tunnel wall.  Chord follows CHORD_RATIO and the lower edges step up outboard,
# which is what leaves visible daylight between the blades.

_FENCE_N = 4
_FENCE_ROOT_CHORD = 1080.0
_FENCE_LE_X = (664.0, 622.0, 578.0, 532.0)
_FENCE_F = (0.13, 0.39, 0.65, 0.90)
_FENCE_BOT_Z = (30.0, 39.0, 50.0, 63.0)
_FENCE_CAMBER = (0.020, 0.036, 0.054, 0.074)


def _fence(i: int):
    chord_l = spec.cascade_chords(_FENCE_ROOT_CHORD, _FENCE_N, 0.87)[i]
    x_le = _FENCE_LE_X[i]
    x_te = x_le - chord_l
    f = _FENCE_F[i]
    y_le = _band_y(x_le + 6.0, f)
    y_te = _band_y(x_te, f)
    yaw = math.degrees(math.atan2(y_te - y_le, x_le - x_te))

    z_le = _under_z(_station(x_le), y_le) - 2.0
    z_te = _under_z(_station(x_te), y_te) - 2.0
    tilt = math.degrees(math.atan2(z_te - z_le, chord_l))
    chord = math.hypot(chord_l, z_te - z_le)
    depth = max(z_le - _FENCE_BOT_Z[i], 40.0)

    ct = math.cos(math.radians(tilt))
    stt = math.sin(math.radians(tilt))
    stations = []
    for d in (0.0, 0.26, 0.54, 0.80, 1.0):
        # the free lower edge is shorter than the bonded top and walks aft, so
        # every blade ends on a clean raked line instead of a ragged point
        g = 1.0 - 0.30 * d**1.35
        back = (1.0 - g) * chord * 0.62
        stations.append(
            {
                "plane": _vane_plane(
                    (
                        x_le - back * ct,
                        y_le + (y_te - y_le) * 0.04 * d,
                        z_le + back * stt - depth * d,
                    ),
                    yaw * (1.0 + 0.22 * d),
                    tilt,
                ),
                "chord": chord * g,
                "thickness": lib.taper(0.068, 0.046, d),
                "camber": _FENCE_CAMBER[i],
            }
        )
    return _vane(stations)


# --- plank -----------------------------------------------------------------
# Terminates ON the kick line, which is the one place a straight feature line
# on the underside has something to die into.

_PLANK_X = (
    780.0, 752.0, 700.0, 560.0, 380.0, 160.0, -80.0, -340.0, -620.0, -920.0,
    -1240.0, -1580.0, -1940.0, -2300.0, -2660.0, -2960.0, -3090.0, -3124.0,
)
_PLUG_X = (420.0, -220.0, -900.0, -1620.0, -2380.0)


def _plank():
    faces = []
    for x in _PLANK_X:
        # chamfered leading edge and a chamfered termination at the kick
        lead = 0.42 if x > 770.0 else (0.55 if x < -3110.0 else 1.0)
        hw = spec.PLANK_W / 2.0 * lead
        th = spec.PLANK_T * (0.34 if x > 770.0 else (0.5 if x < -3110.0 else 1.0))
        cz = _keel_bot(x) - th / 2.0 - 0.2
        pts = [
            (u, v + cz)
            for (u, v) in _rect_pts(2 * hw, th, min(2.4, th * 0.35), flats=9)
        ]
        faces.append(lib.section_face(x, pts))
    solid = lib.body_loft(faces)
    for px in _PLUG_X:
        # the customary circular wear plugs, recessed into the plank's underside
        z = _keel_bot(px) - spec.PLANK_T + 1.5
        try:
            solid = lib.cut(solid, Pos(px, 0.0, z) * Cylinder(34.0, 7.0))
        except Exception:
            pass
    return solid


# --- floor-edge accent stripe + gloss shoulder rail -------------------------

# Both lines run THROUGH the kick and die on the diffuser exit plane, so the
# floor edge hands off to the diffuser instead of fading out at the waist.
_STRIPE_FRONT = -420.0
_STRIPE_REAR = spec.FLOOR_TE_X + 8.0
_STRIPE_X = tuple(
    _STRIPE_FRONT + (_STRIPE_REAR - _STRIPE_FRONT) * i / 46.0 for i in range(47)
)

_RAIL_FRONT = 470.0
_RAIL_REAR = spec.FLOOR_TE_X + 8.0
_RAIL_X = tuple(
    _RAIL_FRONT + (_RAIL_REAR - _RAIL_FRONT) * i / 52.0 for i in range(53)
)


def _bead_pt(st: dict):
    """(y, z) of the outermost point of the edge-wing bottom bead."""
    return st["hw"] - 0.05 * st["wt"], st["zb"] + 2.6


def _edge_rail(xs, profile_l, profile_h, dy, dz, ref="bead"):
    """A fine strip swept along a floor-edge feature line."""
    stations = []
    for x in xs:
        st = _station(x)
        if ref == "flank":
            y, z = st["y_flank"], st["z_flank"]
        else:
            y, z = _bead_pt(st)
        stations.append(
            {
                "plane": lib.plate_plane((x, y + dy, z + dz), (1, 0, 0)),
                "pts": _rect_pts(profile_l, profile_h, min(profile_l, profile_h) * 0.34),
            }
        )
    return lib.swept_plate(stations)


# --- edge-wing winglets ahead of the rear tyre -----------------------------
# A three-element cascade sitting ON the floor-edge flank, repeating the front
# wing's chord/gap/incidence rhythm at a small scale.

_WINGLET_X = (-2790.0, -2910.0, -3020.0)
_WINGLET_CHORD = spec.cascade_chords(224.0, 3)
_WINGLET_TWIST = (7.0, 11.0, 15.5)


def _winglet(i: int):
    x = _WINGLET_X[i]
    st = _station(x)
    c = _WINGLET_CHORD[i]
    root_y = st["y_flank"] - 26.0
    tip_y = st["hw"] + 30.0
    z0 = st["z_flank"] + 12.0
    stations = []
    for f in (0.0, 0.55, 1.0):
        stations.append(
            {
                "le": (
                    x + 0.10 * c * f,
                    root_y + (tip_y - root_y) * f,
                    z0 + 22.0 * f,
                ),
                "chord": c * (1.0 - 0.34 * f),
                "twist": _WINGLET_TWIST[i] * (1.0 + 0.25 * f),
                "thickness": lib.taper(0.085, 0.062, f),
                "camber": 0.052,
            }
        )
    return lib.wing_element(stations)


def build_floor():
    bodies = [
        lib.styled(_floor_shell(), "floor_shell", spec.CARBON_MATTE),
        lib.styled(_plank(), "plank", spec.CARBON_WEAVE),
    ]
    bodies += lib.pair(
        _edge_rail(_STRIPE_X, 5.0, 4.6, 1.2, 7.0), "floor_edge_stripe", spec.ACCENT
    )
    bodies += lib.pair(
        _edge_rail(_RAIL_X, 12.0, 5.4, -4.0, -2.0, ref="flank"),
        "floor_edge_rail",
        spec.CARBON_GLOSS,
    )
    for i in range(_FENCE_N):
        bodies += lib.pair(_fence(i), f"floor_fence_{i + 1}", spec.CARBON)
    for i in range(len(_WINGLET_X)):
        bodies += lib.pair(_winglet(i), f"edge_winglet_{i + 1}", spec.CARBON_GLOSS)
    return lib.group("floor", bodies)


# ==========================================================================
# B. DIFFUSER
# ==========================================================================


def _diffuser_shell():
    return _loft_stack(_DIFF_X)


# --- strakes ---------------------------------------------------------------
# Three per side, hung from the tunnel roof on planes raked to the ramp, placed
# by tunnel fraction like the fences so they fan with the flare, and walked aft
# as they deepen so EVERY station's trailing edge lands on the exit plane.

_STRAKE_LE_X = (-3190.0, -3300.0, -3402.0)
_STRAKE_F = (0.10, 0.40, 0.72)
# Height of each blade's lower TE corner ON the exit plane.  Stated as an
# absolute z (not a depth) so the three lower edges fan open outboard by a
# fixed, readable step instead of tracking the arch and coming out parallel.
_STRAKE_EXIT_Z = (124.0, 166.0, 208.0)


def _strake(i: int):
    x_le = _STRAKE_LE_X[i]
    x_te = spec.FLOOR_TE_X
    f = _STRAKE_F[i]
    y_le = _band_y(x_le, f)
    y_te = _band_y(x_te, f)
    yaw = math.degrees(math.atan2(y_te - y_le, x_le - x_te))

    z_le = _under_z(_station(x_le), y_le) - 2.0
    z_te = _under_z(_station(x_te), y_te) - 2.0
    tilt = math.degrees(math.atan2(z_te - z_le, x_le - x_te))
    chord = math.hypot(x_le - x_te, z_te - z_le)
    depth = max(z_te - _STRAKE_EXIT_Z[i], 60.0)

    ct = math.cos(math.radians(tilt))
    stt = math.sin(math.radians(tilt))
    stations = []
    for d in (0.0, 0.30, 0.60, 0.84, 1.0):
        g = 1.0 - 0.26 * d**1.4
        back = (1.0 - g) * chord
        stations.append(
            {
                "plane": _vane_plane(
                    (
                        x_le - back * ct,
                        y_le + (y_te - y_le) * 0.05 * d,
                        z_le + back * stt - depth * d,
                    ),
                    yaw * (1.0 + 0.18 * d),
                    tilt,
                ),
                "chord": chord * g,
                "thickness": lib.taper(0.058, 0.042, d),
                "camber": 0.028 + 0.016 * i,
                "camber_pos": 0.45,
            }
        )
    return _vane(stations)


# --- gurney lip ------------------------------------------------------------


def _gurney():
    """A fine crisp lip standing off the diffuser roof's trailing edge."""
    st = _station(spec.FLOOR_TE_X)
    y0, y1 = st["y_in"] + 8.0, st["y_out"] + 2.0
    n = 13
    ys = [y0 + (y1 - y0) * i / n for i in range(n + 1)]
    stations = []
    for y in ys:
        z = _under_z(st, y)
        h = 13.0 - 4.0 * abs(2.0 * (y - y0) / (y1 - y0) - 1.0) ** 2
        stations.append(
            {
                "plane": lib.plate_plane(
                    (spec.FLOOR_TE_X - 1.4, y, z - h / 2.0 + 2.5), (0, 1, 0)
                ),
                "pts": _rect_pts(2.8, h, 0.9),
            }
        )
    return lib.swept_plate(stations, ruled=True)


def build_diffuser():
    bodies = [lib.styled(_diffuser_shell(), "diffuser_shell", spec.CARBON_MATTE)]
    for i in range(len(_STRAKE_LE_X)):
        bodies += lib.pair(_strake(i), f"diffuser_strake_{i + 1}", spec.CARBON)
    bodies += lib.pair(_gurney(), "diffuser_gurney", spec.CARBON_GLOSS)
    return lib.group("diffuser", bodies)
