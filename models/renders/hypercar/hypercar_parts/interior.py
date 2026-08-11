"""Cabin interior: seats, wheel, dash, console, pedal box, door cards.

Seen almost entirely *through* the glass, so this module is built to be read
from outside and above: silhouette and top surfaces carry the design, and every
horizontal is a long continuous sweep rather than a collection of blocks.

Construction notes
------------------
The seat is a single swept shell -- a trough section (concave centre rising
into razor bolster tips) driven along a spine curve that runs from the
headrest, down the backrest, through the hip and out to the cushion lip.  The
bolster tip is where the two section bands meet with free tangents, so it
becomes a real crease that runs the entire length of the seat: one unbroken
feature line from headrest to cushion nose.

Everything else uses the same idea -- lofted section families rather than
boolean-assembled blocks -- so the highlights run continuously.
"""

from __future__ import annotations

import math

from build123d import (
    Axis,
    Circle,
    Cylinder,
    Ellipse,
    Plane,
    Polyline,
    Pos,
    RectangleRounded,
    Rot,
    Spline,
    extrude,
    loft,
    make_face,
    mirror,
    revolve,
    sweep,
)

from hypercar_parts import surfaces as S
from hypercar_parts.context import group, style
from hypercar_parts import palette as P


# ---------------------------------------------------------------------------
# cabin datums
# ---------------------------------------------------------------------------

FLOOR_BOT = 290.0
FLOOR_TOP = 308.0

SEAT_Y = 380.0
SEAT_TH = 26.0

DRIVER_Y = 400.0

STEER_C = (502.0, DRIVER_Y, 688.0)
STEER_TILT = 25.0
RIM_A = 168.0
RIM_B = 140.0

DASH_HALF_Y = 620.0
DASH_XC = 726.0
DASH_ZC = 706.0

BULKHEAD_X = -545.0

DOOR_X0 = 652.0
DOOR_X1 = -430.0
DOOR_CREASE_TOP = 596.0
DOOR_CREASE_BOT = 576.0


# ---------------------------------------------------------------------------
# small maths helpers
# ---------------------------------------------------------------------------


def _sm(t):
    """Smootherstep -- C2, so blending a control table leaves no curvature
    break at a knot.  A C1 smoothstep does, and a loft driven through many
    sections turns every one of those breaks into a visible ripple."""
    t = max(0.0, min(1.0, t))
    return t * t * t * (t * (t * 6.0 - 15.0) + 10.0)


def _tab(table, s):
    """Smooth-stepped lookup through a (key, value) table."""
    if s <= table[0][0]:
        return table[0][1]
    if s >= table[-1][0]:
        return table[-1][1]
    for (a, va), (b, vb) in zip(table, table[1:]):
        if a <= s <= b:
            return va + (vb - va) * _sm((s - a) / (b - a))
    return table[-1][1]


def _spine(pts):
    """A curve in the car's XZ plane, sampled by normalised arc length."""
    return Spline(*[(p[0], 0.0, p[1]) for p in pts])


def _frame(edge, s):
    """Section plane at arc-length ``s``: local (u, v) = (lateral, surface out)."""
    return Plane(origin=edge @ s, x_dir=(0, 1, 0), z_dir=edge % s)


def _closed_face(run_a, run_b):
    """Face closed by two point runs that share their end points."""
    return make_face(Spline(*run_a) + Spline(*run_b))


def _face_from_runs(runs):
    """Face from N runs laid end to end.

    Two-point runs become straight edges, so a corner between runs is a real
    corner instead of a spline rounding it off -- that is what keeps a panel
    edge crisp rather than letting the panel read as a padded roll.
    """
    edges = None
    for run in runs:
        e = Polyline(*run) if len(run) == 2 else Spline(*run)
        edges = e if edges is None else edges + e
    return make_face(edges)


def _loft_stations(planes_and_faces):
    return loft(planes_and_faces)


# ---------------------------------------------------------------------------
# seat
# ---------------------------------------------------------------------------

# headrest crown -> backrest -> hip -> cushion nose (which rolls under)
SEAT_SPINE = [
    (-266, 982), (-257, 967), (-245, 946), (-225, 906), (-197, 856),
    (-161, 796), (-117, 727), (-71, 655), (-27, 576), (9, 501),
    (39, 439), (71, 401), (128, 381), (210, 375), (300, 379),
    (390, 389), (470, 405), (528, 425), (556, 421), (566, 403),
]

# half-width of the shell along the spine (s = 0 at the headrest crown).
# The crown and the cushion nose taper towards nothing so the loft closes on
# a sliver instead of a chopped-off flat end.
SEAT_HW = [
    (0.000, 52), (0.022, 108), (0.050, 142), (0.082, 150), (0.120, 162),
    (0.170, 206), (0.220, 244), (0.280, 250), (0.355, 238), (0.455, 228),
    (0.565, 236), (0.700, 246), (0.845, 248), (0.935, 236), (0.978, 206),
    (1.000, 140),
]

# how proud the bolster crease stands above the trough centre
SEAT_BH = [
    (0.000, 7), (0.022, 26), (0.052, 46), (0.085, 50), (0.125, 55),
    (0.175, 68), (0.225, 84), (0.285, 82), (0.365, 62), (0.465, 48),
    (0.575, 56), (0.720, 62), (0.865, 54), (0.945, 38), (1.000, 12),
]

HEAD_PAD_S = (0.045, 0.150)
BACK_PAD_S = (0.300, 0.590)
SEAT_PAD_S = (0.640, 0.960)
SHOULDER_SLOT_S = 0.245
LAP_SLOT_S = 0.625


def _shell_section(hw, bh, th, p=2.3, n=11):
    top, bot = [], []
    for i in range(n + 1):
        ut = -1.0 + 2.0 * i / n
        top.append((hw * ut, bh * abs(ut) ** p))
    for i in range(n + 1):
        ut = 1.0 - 2.0 * i / n
        au = abs(ut)
        bot.append((hw * ut, bh * au ** p - th * (1.0 - au ** 3)))
    return _closed_face(top, bot)


def _pad_section(hw, bh, frac, ph, p=2.3, n=11):
    hp = hw * frac
    lo, hi = [], []
    for i in range(n + 1):
        ut = -1.0 + 2.0 * i / n
        u = hp * ut
        base = bh * abs(u / hw) ** p + 0.8
        lo.append((u, base))
    for i in range(n + 1):
        ut = 1.0 - 2.0 * i / n
        u = hp * ut
        base = bh * abs(u / hw) ** p + 0.8
        hi.append((u, base + ph * (1.0 - abs(ut) ** 3) ** 0.5))
    return _closed_face(lo, hi)


def _strap_section(hw, bh, u0, half_w, th, lift, p=2.3, n=7):
    lo, hi = [], []
    for i in range(n + 1):
        ut = -1.0 + 2.0 * i / n
        u = u0 + half_w * ut
        lo.append((u, bh * abs(u / hw) ** p + lift))
    for i in range(n + 1):
        ut = 1.0 - 2.0 * i / n
        u = u0 + half_w * ut
        base = bh * abs(u / hw) ** p + lift
        hi.append((u, base + th * (1.0 - abs(ut) ** 4) ** 0.35))
    return _closed_face(lo, hi)


def _sweep_sections(edge, s0, s1, n, fn):
    faces = []
    for i in range(n + 1):
        ls = i / n
        s = s0 + (s1 - s0) * ls
        faces.append(_frame(edge, s) * fn(s, ls))
    return loft(faces)


def _pad_window(ls, e=0.16, floor=0.10):
    return floor + (1.0 - floor) * _sm(ls / e) * _sm((1.0 - ls) / e)


def _seat_pad(edge, span, frac, ph, n=16):
    def fn(s, ls):
        w = _pad_window(ls)
        return _pad_section(
            _tab(SEAT_HW, s), _tab(SEAT_BH, s), frac * (0.52 + 0.48 * w), ph * w
        )

    return _sweep_sections(edge, span[0], span[1], n, fn)


def _slot_cutter(edge, s, u, w, h):
    plane = _frame(edge, s)
    return plane * (
        Pos(u, 0, 0) * extrude(Plane.XZ * RectangleRounded(w, h, w * 0.44), 140, both=True)
    )


def _seat_parts():
    """Seat built about y = 0; the caller translates it to each side."""
    edge = _spine(SEAT_SPINE)

    def shell_fn(s, ls):
        taper = 0.30 + 0.70 * _sm(min(ls, 1.0 - ls) / 0.05)
        return _shell_section(
            _tab(SEAT_HW, s), _tab(SEAT_BH, s), SEAT_TH * taper
        )

    shell = _sweep_sections(edge, 0.0, 1.0, 32, shell_fn)
    for s, u, w, h in (
        (SHOULDER_SLOT_S, 106, 34, 82),
        (SHOULDER_SLOT_S, -106, 34, 82),
        (LAP_SLOT_S, 176, 30, 62),
        (LAP_SLOT_S, -176, 30, 62),
    ):
        try:
            shell = shell - _slot_cutter(edge, s, u, w, h)
        except Exception:  # pragma: no cover - kernel guard
            pass

    head_pad = _seat_pad(edge, HEAD_PAD_S, 0.60, 34, n=9)
    back_pad = _seat_pad(edge, BACK_PAD_S, 0.68, 40, n=12)
    seat_pad = _seat_pad(edge, SEAT_PAD_S, 0.70, 44, n=12)
    stripe = _seat_pad(edge, (0.300, 0.585), 0.075, 46, n=11)

    out = [
        (shell, "seat_shell", P.CARBON),
        (head_pad, "seat_head_pad", P.SEAT),
        (back_pad, "seat_back_pad", P.ALCANTARA),
        (seat_pad, "seat_cushion_pad", P.ALCANTARA),
        (stripe, "seat_centre_stripe", P.SEAT_STITCH),
    ]

    # 6-point harness: shoulder straps out of the slots, lap straps in to the
    # buckle.  The webbing is the one lighter graphic on an otherwise black
    # seat, so it carries the eye down the backrest.
    for sign in (1, -1):
        side = "l" if sign > 0 else "r"

        def shoulder(s, ls, sign=sign):
            u0 = sign * (104.0 - 48.0 * _sm(max(0.0, (ls - 0.70) / 0.30)))
            return _strap_section(
                _tab(SEAT_HW, s), _tab(SEAT_BH, s), u0, 33.0,
                10.0, 22.0 + 20.0 * _sm(min(ls / 0.18, 1.0)),
            )

        out.append((
            _sweep_sections(edge, SHOULDER_SLOT_S - 0.005, 0.742, 14, shoulder),
            f"harness_shoulder_{side}",
            P.STEEL_DARK,
        ))

        def lap(s, ls, sign=sign):
            u0 = sign * (176.0 - 130.0 * _sm(ls))
            return _strap_section(
                _tab(SEAT_HW, s), _tab(SEAT_BH, s), u0, 31.0, 10.0,
                10.0 + 30.0 * _sm(ls),
            )

        out.append((
            _sweep_sections(edge, LAP_SLOT_S, 0.735, 9, lap),
            f"harness_lap_{side}",
            P.STEEL_DARK,
        ))

    buckle_pl = _frame(edge, 0.755)
    out.append((
        buckle_pl
        * (
            Pos(0, 50, 0)
            * (
                extrude(Plane.XZ * RectangleRounded(74, 92, 22), 12, both=True)
                - Pos(0, 8, 0) * extrude(
                    Plane.XZ * RectangleRounded(52, 68, 16), 12, both=True
                )
            )
        ),
        "harness_buckle",
        P.BRONZE,
    ))
    out.append((
        buckle_pl * (Pos(0, 50, 0) * extrude(
            Plane.XZ * RectangleRounded(50, 66, 15), 8, both=True
        )),
        "harness_buckle_face",
        P.CARBON_GLOSS,
    ))

    # machined rails carrying the shell down to the floor
    for i, ry in ((0, 138), (1, -138)):
        rail = Pos(200, ry, FLOOR_TOP) * extrude(
            RectangleRounded(470, 42, 18), 68
        )
        out.append((rail, f"seat_rail_{i}", P.ALUMINIUM_DARK))
    return out


def _seats():
    kids = []
    parts = _seat_parts()
    for side in (1, -1):
        name = "left" if side > 0 else "right"
        for shape, label, colour in parts:
            kids.append(
                style(Pos(0, side * SEAT_Y, 0) * shape, f"{label}:{name}", colour)
            )
    return kids


# ---------------------------------------------------------------------------
# steering wheel
# ---------------------------------------------------------------------------


def _steer_plane():
    t = math.radians(STEER_TILT)
    return Plane(
        origin=STEER_C, x_dir=(0, -1, 0), z_dir=(-math.cos(t), 0.0, math.sin(t))
    )


def _rim_path(a, b, n=40, flat=0.42):
    pts = []
    for i in range(n):
        th = 2.0 * math.pi * i / n
        s = math.sin(th)
        v = b * (1.0 if s >= 0 else -1.0) * abs(s) ** flat
        pts.append((a * math.cos(th), v, 0.0))
    return Spline(*pts, periodic=True)


def _blade(p0, p1, sec0, sec1, axis):
    """Tapered spoke blade lofted between two rounded sections."""
    if axis == "u":
        x_dir, z_dir = (0, 1, 0), (1, 0, 0)
    else:
        x_dir, z_dir = (1, 0, 0), (0, -1, 0)
    f0 = Plane(origin=p0, x_dir=x_dir, z_dir=z_dir) * RectangleRounded(*sec0)
    f1 = Plane(origin=p1, x_dir=x_dir, z_dir=z_dir) * RectangleRounded(*sec1)
    return loft([f0, f1])


def _steering():
    plane = _steer_plane()
    local = []

    path = _rim_path(RIM_A, RIM_B)
    sec = Plane(origin=path @ 0, x_dir=(1, 0, 0), z_dir=path % 0) * RectangleRounded(
        36, 28, 13
    )
    # is_frenet=True does not close cleanly on this closed rim path -- the
    # Frenet frame does not return to its start orientation, leaving 8 free
    # edges and 8 non-manifold edges at the seam.  Parallel transport closes.
    local.append((sweep(sec, path), "steering_rim", P.CARBON))

    # spokes: 3 and 9 o'clock, plus 6 o'clock
    for sign in (1, -1):
        local.append((
            _blade(
                (sign * 54, 0, -4), (sign * (RIM_A - 12), 0, -15),
                (92, 24, 10), (52, 17, 8), "u",
            ),
            f"steering_spoke_h{'l' if sign > 0 else 'r'}",
            P.CARBON,
        ))
        local.append((
            Pos(sign * 104, 0, 5) * extrude(RectangleRounded(58, 11, 5), 4),
            f"steering_spoke_inlay{'l' if sign > 0 else 'r'}",
            P.BRONZE,
        ))
    local.append((
        _blade(
            (0, -50, -4), (0, -(RIM_B - 12), -13),
            (98, 24, 10), (58, 17, 8), "v",
        ),
        "steering_spoke_low",
        P.CARBON,
    ))

    # hub jewellery
    local.append((Pos(0, 0, -16) * Cylinder(64, 34), "steering_hub", P.ALUMINIUM_DARK))
    local.append((
        Cylinder(58, 10) - Cylinder(50, 14),
        "steering_hub_ring",
        P.BRONZE,
    ))
    local.append((Pos(0, 0, 4) * Cylinder(50, 12), "steering_hub_pad", P.CARBON_GLOSS))
    local.append((
        Pos(0, RIM_B - 4, 10) * extrude(RectangleRounded(30, 26, 8), 9),
        "steering_top_marker",
        P.BRONZE,
    ))

    # shift paddles behind the rim
    for sign in (1, -1):
        local.append((
            Pos(sign * 86, 10, -54) * extrude(
                RectangleRounded(24, 106, 11, rotation=sign * 8), 8
            ),
            f"shift_paddle:{'left' if sign > 0 else 'right'}",
            P.BRONZE,
        ))

    # column shroud running forward from the hub
    shroud = loft([
        Plane.XY.offset(-30) * Ellipse(72, 56),
        Plane.XY.offset(-150) * Ellipse(56, 44),
        Plane.XY.offset(-262) * Ellipse(42, 34),
    ])
    local.append((shroud, "steering_column_shroud", P.CARBON))

    return [style(plane * shape, label, colour) for shape, label, colour in local]


# ---------------------------------------------------------------------------
# dash
# ---------------------------------------------------------------------------


def _dash_station(ty):
    a = abs(ty)
    xc = DASH_XC - 108.0 * a ** 1.7
    zc = DASH_ZC - 30.0 * a * a
    c = 68.0 - 15.0 * a * a
    up = 10.0 - 3.0 * a * a
    dn = 15.0 - 4.0 * a * a
    return xc, zc, c, up, dn


def _dash_blade():
    faces = []
    n = 14
    for i in range(n + 1):
        ty = -1.0 + 2.0 * i / n
        xc, zc, c, up, dn = _dash_station(ty)
        # aerofoil: flat top, cambered underside, razor tips -- so it reads as
        # a blade and not as a rolled-over tube
        front = (xc + c, zc + 0.24 * up)
        rear = (xc - c, zc + 0.46 * up)
        top = [
            rear,
            (xc - 0.62 * c, zc + 0.97 * up),
            (xc - 0.06 * c, zc + up),
            (xc + 0.56 * c, zc + 0.94 * up),
            front,
        ]
        bot = [
            front,
            (xc + 0.46 * c, zc - 0.78 * dn),
            (xc - 0.06 * c, zc - dn),
            (xc - 0.62 * c, zc - 0.74 * dn),
            rear,
        ]
        faces.append(Plane.XZ.offset(-DASH_HALF_Y * ty) * _closed_face(top, bot))
    return loft(faces)


DASH_SKIN = 26.0


def _dash_core():
    """The dark fascia under the blade.

    A *thin swept panel*, not a second volume: it drops almost vertically out
    of the blade's shadow and only turns forward at its bottom lip, so the
    dash silhouette is one slim blade over one slim wall with open dark space
    between them.  It is also narrower than the blade in plan, which is what
    lets the blade read as a blade.
    """
    faces = []
    n = 14
    for i in range(n + 1):
        ty = -1.0 + 2.0 * i / n
        xc, zc, c, up, dn = _dash_station(ty)
        top_z = zc - dn - 22.0
        face_run = [
            (xc - 0.16 * c, top_z),
            (xc - 0.06 * c, top_z - 64.0),
            (xc + 0.30 * c, top_z - 128.0),
            (xc + 0.86 * c, 516.0),
            (xc + c + 30.0, 484.0),
        ]
        d = DASH_SKIN
        lip = (xc + c + 34.0, 484.0 + d)
        back_run = [
            lip,
            (xc + 0.86 * c + d * 0.70, 516.0 + d * 0.72),
            (xc + 0.30 * c + d * 0.96, top_z - 128.0 + d * 0.28),
            (xc - 0.06 * c + d, top_z - 64.0),
            (xc - 0.16 * c + d, top_z),
            face_run[0],
        ]
        faces.append(
            Plane.XZ.offset(-DASH_HALF_Y * 0.93 * ty)
            * _closed_face(face_run + [lip], back_run)
        )
    return loft(faces)


BINN_C = (648.0, 372.0, 744.0)
BINN_TILT = 20.0


def _binnacle():
    t = math.radians(BINN_TILT)
    plane = Plane(
        origin=BINN_C, x_dir=(0, -1, 0), z_dir=(-math.cos(t), 0.0, math.sin(t))
    )
    bezel = extrude(RectangleRounded(196, 80, 24), 11, both=True) - Pos(
        0, 0, 5
    ) * extrude(RectangleRounded(176, 60, 17), 20)
    rim = Pos(0, 0, 10) * (
        extrude(RectangleRounded(196, 80, 24), 4)
        - Pos(0, 0, -1) * extrude(RectangleRounded(184, 68, 20), 8)
    )
    screen = Pos(0, 0, 1) * extrude(RectangleRounded(174, 58, 16), 10)
    out = [
        style(plane * bezel, "binnacle_bezel", P.CARBON_GLOSS),
        style(plane * rim, "binnacle_rim", P.BRONZE),
        style(plane * screen, "binnacle_screen", P.GLASS_DARK),
    ]
    for i, sy in ((0, 62), (1, -62)):
        stalk = Pos(638.0, BINN_C[1] + sy, 690.0) * extrude(
            RectangleRounded(12, 24, 5), 30
        )
        out.append(style(stalk, f"binnacle_stalk_{i}", P.BRONZE_DARK))
    return out


def _dash():
    kids = [
        style(_dash_core(), "dash_core", P.CARBON),
        style(_dash_blade(), "dash_blade", P.DASH),
    ]
    kids += _binnacle()
    return kids


# ---------------------------------------------------------------------------
# centre console
# ---------------------------------------------------------------------------

CONSOLE = [
    (700, 660, 128, 176), (620, 628, 122, 172), (520, 586, 114, 167),
    (400, 546, 106, 162), (260, 520, 100, 157), (110, 508, 96, 154),
    (-40, 504, 96, 153), (-190, 508, 100, 155), (-330, 520, 108, 161),
    (-430, 538, 118, 169), (-505, 562, 128, 177), (-545, 588, 136, 184),
]


def _console_at(x):
    xs = [c[0] for c in CONSOLE][::-1]
    vals = [c[1:] for c in CONSOLE][::-1]
    if x <= xs[0]:
        return vals[0]
    if x >= xs[-1]:
        return vals[-1]
    for i in range(len(xs) - 1):
        if xs[i] <= x <= xs[i + 1]:
            t = _sm((x - xs[i]) / (xs[i + 1] - xs[i]))
            return tuple(a + (b - a) * t for a, b in zip(vals[i], vals[i + 1]))
    return vals[-1]


def _console_face(x):
    zt, hw, hb = _console_at(x)
    zb = FLOOR_TOP - 2.0
    crown = Spline(
        (0.0, zt), (0.40 * hw, zt - 3.0), (0.76 * hw, zt - 13.0), (hw, zt - 31.0)
    )
    side = Spline(
        (hw, zt - 31.0),
        (0.995 * hb, 0.55 * (zt - 31.0) + 0.45 * zb),
        (hb, zb + 92.0),
        (0.975 * hb, zb + 28.0),
        (0.88 * hb, zb),
    )
    base = Polyline((0.88 * hb, zb), (0.0, zb))
    half = crown + side + base
    return Plane.YZ.offset(x) * make_face(half + mirror(half, Plane.YZ))


def _console_body():
    xs = [700 - (700 + 545) * i / 16.0 for i in range(17)]
    return loft([_console_face(x) for x in xs])


def _console_pinstripe(side):
    faces = []
    for i in range(17):
        x = 690 - (690 + 538) * i / 16.0
        zt, hw, _hb = _console_at(x)
        faces.append(
            Plane.YZ.offset(x)
            * (Pos(side * (hw - 1.5), zt - 29.5) * RectangleRounded(13, 8, 3.5))
        )
    return loft(faces)


def _selector():
    prof = Spline(
        (33, 0), (35, 7), (30, 15), (14, 24), (12, 52),
        (16, 61), (24, 74), (25, 88), (20, 100), (7, 109),
    )
    face = make_face(Polyline((0, 0), (33, 0)) + prof + Polyline((7, 109), (0, 111), (0, 0)))
    return revolve(Plane.XZ * face, Axis.Z)


def _knurl(radius, height):
    prof = Spline(
        (radius, 0), (radius + 2.0, 0.28 * height), (radius - 1.5, 0.55 * height),
        (radius + 1.5, 0.80 * height), (radius - 6.0, height),
    )
    face = make_face(
        Polyline((0, 0), (radius, 0))
        + prof
        + Polyline((radius - 6.0, height), (0, height), (0, 0))
    )
    return revolve(Plane.XZ * face, Axis.Z)


def _console():
    kids = [style(_console_body(), "console_spine", P.CARBON)]
    for side in (1, -1):
        kids.append(
            style(
                _console_pinstripe(side),
                f"console_inlay:{'left' if side > 0 else 'right'}",
                P.BRONZE,
            )
        )

    gate_z = _console_at(255)[0]
    kids.append(
        style(
            Pos(255, 0, gate_z - 14.0) * extrude(RectangleRounded(168, 106, 26), 14),
            "console_gate",
            P.BRONZE_DARK,
        )
    )
    kids.append(
        style(
            Pos(240, 0, gate_z - 4.0) * (Rot(0, -12, 0) * _selector()),
            "drive_selector",
            P.BRONZE,
        )
    )

    rot_z = _console_at(430)[0]
    for i, ry in ((0, 54), (1, -54)):
        kids.append(
            style(
                Pos(430, ry, rot_z - 20.0) * _knurl(25, 26),
                f"console_rotary_{i}",
                P.BRONZE,
            )
        )
    start_z = _console_at(540)[0]
    kids.append(
        style(Pos(540, 0, start_z - 12.0) * _knurl(20, 19), "start_button", P.BRONZE)
    )
    return kids


# ---------------------------------------------------------------------------
# door cards
# ---------------------------------------------------------------------------


def _door_stations():
    n = 11
    return [DOOR_X0 + (DOOR_X1 - DOOR_X0) * i / n for i in range(n + 1)]


def _door_taper(x):
    """1 through the body of the door, dying to a sliver at both cuts."""
    t = (x - DOOR_X1) / (DOOR_X0 - DOOR_X1)
    return _sm(t / 0.16) * _sm((1.0 - t) / 0.11)


def _door_refs(x):
    """(top edge y, bottom edge y, top edge z, bottom edge z) for one station.

    The whole card is driven off these four numbers so its section keeps the
    same character from the A-pillar to the rear cut -- the crease then runs
    parallel to the glass base instead of wandering -- and the card's lower
    edge lifts at both ends so it dies into the dash and the rear quarter
    rather than being chopped square.
    """
    chw = S.CANOPY_HW(x)
    wall = 0.60 * chw + 0.40 * 0.92 * S.SILL_Y(x)
    lift = 176.0 * (1.0 - _door_taper(x))
    return 0.945 * chw, 0.985 * wall, S.CANOPY_BASE_Z(x) - 14.0, 330.0 + lift


# (k, lateral ramp, sculpt offset) -- k is the fraction of the card's height
DOOR_UPPER = [
    (0.00, 0.00, 0.0),
    (0.15, 0.19, 5.0),
    (0.29, 0.32, -1.0),
    (0.375, 0.385, -14.0),
    (0.42, 0.42, -34.0),
]
DOOR_LOWER = [
    (0.475, 0.475, -30.0),
    (0.60, 0.62, -8.0),
    (0.76, 0.78, 4.0),
    (0.90, 0.91, 3.0),
    (1.00, 1.00, 0.0),
]
DOOR_BACK = 40.0


def _door_pt(x, k, g, extra, scale=True):
    yt, yb, zt, zb = _door_refs(x)
    if scale:
        extra *= _door_taper(x)
    return (yt + (yb - yt) * g + extra, zt + (zb - zt) * k)


def _door_face(x, table):
    depth = DOOR_BACK * (0.22 + 0.78 * _door_taper(x))
    inner = [_door_pt(x, *row) for row in table]
    back = [
        _door_pt(x, row[0], row[1], depth, scale=False) for row in reversed(table)
    ]
    runs = [
        inner,
        [inner[-1], back[0]],
        back,
        [back[-1], inner[0]],
    ]
    return Plane.YZ.offset(x) * _face_from_runs(runs)


def _door_pull():
    faces = []
    for i in range(11):
        x = 250.0 - 470.0 * i / 10.0
        y, z = _door_pt(x, 0.4475, 0.4475, -34.0)
        w = 0.36 + 0.64 * _sm(min(i, 10 - i) / 1.6)
        faces.append(
            Plane.YZ.offset(x)
            * (Pos(y, z) * RectangleRounded(30 * w, 24 * w, 10 * w))
        )
    return loft(faces)


def _door_cards():
    xs = _door_stations()
    upper = loft([_door_face(x, DOOR_UPPER) for x in xs])
    lower = loft([_door_face(x, DOOR_LOWER) for x in xs])
    pull = _door_pull()
    kids = []
    for side in (1, -1):
        name = "left" if side > 0 else "right"
        for shape, label, colour in (
            (upper, "door_card_upper", P.ALCANTARA),
            (lower, "door_card_lower", P.CARBON),
            (pull, "door_pull", P.BRONZE),
        ):
            piece = shape if side > 0 else mirror(shape, Plane.XZ)
            kids.append(style(piece, f"{label}:{name}", colour))
    return kids


# ---------------------------------------------------------------------------
# floor, sills, rear bulkhead
# ---------------------------------------------------------------------------

FLOOR_X0 = 1080.0
FLOOR_X1 = -540.0


def _floor_edge(x):
    """Cabin floor half-width -- necks down into the footwell."""
    neck = 0.54 + 0.46 * _sm((1020.0 - x) / 380.0)
    return min(0.90 * S.SILL_Y(x), 700.0) * neck


def _floor_outline(inset=0.0):
    xs = [FLOOR_X0 - (FLOOR_X0 - FLOOR_X1) * i / 13.0 for i in range(14)]
    pts = [(x, _floor_edge(x) - inset) for x in xs]
    half = (
        Polyline((FLOOR_X0, 0.0), pts[0])
        + Spline(*pts)
        + Polyline(pts[-1], (FLOOR_X1, 0.0))
    )
    return make_face(half + mirror(half, Plane.XZ))


def _floor():
    plate = extrude(Plane.XY.offset(FLOOR_BOT) * _floor_outline(), FLOOR_TOP - FLOOR_BOT)
    kids = [style(plate, "cabin_floor", P.CARBON)]

    for side in (1, -1):
        faces = []
        for i in range(12):
            t = i / 11.0
            x = 610.0 - 1020.0 * t
            y = _floor_edge(x)
            w = 44.0 * (0.30 + 0.70 * _sm(min(t, 1.0 - t) / 0.10))
            faces.append(
                Plane.YZ.offset(x)
                * (Pos(side * (y - 26.0), FLOOR_TOP + 2.0) * RectangleRounded(w, 9, 4))
            )
        kids.append(
            style(
                loft(faces),
                f"sill_scuff_plate:{'left' if side > 0 else 'right'}",
                P.BRONZE,
            )
        )
    return kids


# Head fairing: starts *inside* the headrest so its first section is a hidden
# cap, then swells rearward and dies into the bulkhead -- the cabin's echo of
# the body's flying buttresses.
FAIRING = [
    (-238, 26, 958, 932),
    (-268, 66, 970, 910),
    (-302, 116, 972, 878),
    (-350, 158, 960, 846),
    (-408, 190, 934, 806),
    (-468, 210, 898, 766),
    (-522, 220, 862, 730),
    (-560, 224, 834, 712),
]


def _fairing_face(x, hw, zt, zb):
    half = Spline(
        (0.0, zt),
        (0.42 * hw, zt - 0.10 * (zt - zb)),
        (0.78 * hw, zt - 0.34 * (zt - zb)),
        (hw, zt - 0.70 * (zt - zb)),
        (0.94 * hw, zb),
    ) + Polyline((0.94 * hw, zb), (0.0, zb))
    return Plane.YZ.offset(x) * make_face(half + mirror(half, Plane.YZ))


def _head_fairing():
    faces = []
    n = 14
    for i in range(n + 1):
        t = i / n
        j = t * (len(FAIRING) - 1)
        k = min(int(j), len(FAIRING) - 2)
        u = _sm(j - k)
        a, b = FAIRING[k], FAIRING[k + 1]
        x, hw, zt, zb = (p + (q - p) * u for p, q in zip(a, b))
        faces.append(_fairing_face(x, hw, zt, zb))
    return loft(faces)


def _bulkhead():
    half = Spline(
        (0.0, 792.0), (170.0, 806.0), (320.0, 842.0), (430.0, 846.0),
        (536.0, 806.0), (606.0, 704.0), (640.0, 540.0), (650.0, 380.0),
        (648.0, 304.0),
    ) + Polyline((648.0, 304.0), (0.0, 304.0))
    face = Plane.YZ.offset(BULKHEAD_X) * make_face(half + mirror(half, Plane.YZ))
    kids = [style(extrude(face, 26.0), "rear_bulkhead", P.MONOCOQUE)]

    fairing = _head_fairing()
    for side in (1, -1):
        name = "left" if side > 0 else "right"
        kids.append(
            style(Pos(0, side * SEAT_Y, 0) * fairing, f"head_fairing:{name}", P.CARBON)
        )

    strip = Pos(BULKHEAD_X + 24.0, 0.0, 700.0) * extrude(
        Plane.YZ * RectangleRounded(300, 22, 9), 8
    )
    kids.append(style(strip, "bulkhead_inlay", P.BRONZE))

    for i, y in ((0, 168), (1, -168)):
        vent = Pos(BULKHEAD_X + 22.0, y, 560.0) * extrude(
            Plane.YZ * RectangleRounded(150, 190, 34), 8
        )
        kids.append(style(vent, f"bulkhead_vent_{i}", P.CARBON_GLOSS))
        ring = Pos(BULKHEAD_X + 26.0, y, 560.0) * (
            extrude(Plane.YZ * RectangleRounded(164, 204, 40), 7)
            - Pos(4, 0, 0) * extrude(Plane.YZ * RectangleRounded(146, 186, 33), 9)
        )
        kids.append(style(ring, f"bulkhead_vent_ring_{i}", P.BRONZE_DARK))
    return kids


# ---------------------------------------------------------------------------
# pedal box
# ---------------------------------------------------------------------------

PIVOT_X = 1024.0
PIVOT_Z = 566.0


def _pedal(px, py, pz, w, h):
    t = math.radians(20.0)
    plane = Plane(
        origin=(px, py, pz), x_dir=(0, -1, 0), z_dir=(-math.cos(t), 0.0, math.sin(t))
    )
    pad = extrude(RectangleRounded(w, h, 16), 14)
    for k in (-1, 0, 1):
        pad = pad - Pos(0, k * h * 0.29, -4) * Cylinder(w * 0.17, 30)
    return plane * pad


def _pedal_arm(py, tip_x, tip_z):
    dx, dz = PIVOT_X - tip_x, PIVOT_Z - tip_z
    length = math.hypot(dx, dz)
    ang = math.degrees(math.atan2(dz, dx))
    sk = Pos((tip_x + PIVOT_X) / 2.0, (tip_z + PIVOT_Z) / 2.0) * RectangleRounded(
        length + 26.0, 28, 13, rotation=ang
    )
    return Pos(0, py, 0) * extrude(Plane.XZ * sk, 9, both=True)


def _pedals():
    kids = []
    specs = (
        ("brake", 402.0, 936.0, 418.0, 86.0, 168.0, P.ALUMINIUM),
        ("throttle", 258.0, 950.0, 402.0, 68.0, 146.0, P.ALUMINIUM),
    )
    for name, py, px, pz, w, h, colour in specs:
        kids.append(style(_pedal(px, py, pz, w, h), f"pedal:{name}", colour))
        kids.append(
            style(_pedal_arm(py, px, pz + h * 0.42), f"pedal_arm:{name}", P.ALUMINIUM_DARK)
        )

    bar = Pos(PIVOT_X, 330.0, PIVOT_Z) * (Rot(-90, 0, 0) * Cylinder(13, 216))
    kids.append(style(bar, "pedal_pivot_bar", P.BRONZE))

    t = math.radians(24.0)
    rest_plane = Plane(
        origin=(918.0, 552.0, 402.0),
        x_dir=(0, -1, 0),
        z_dir=(-math.cos(t), 0.0, math.sin(t)),
    )
    rest = extrude(RectangleRounded(112, 224, 26), 15)
    for k in (-1.0, -0.34, 0.34, 1.0):
        rest = rest - Pos(0, k * 74.0, -4) * Cylinder(17, 30)
    kids.append(style(rest_plane * rest, "footrest", P.ALUMINIUM))

    heel = Pos(866.0, 336.0, FLOOR_TOP - 1.0) * extrude(
        RectangleRounded(200, 300, 42), 9
    )
    kids.append(style(heel, "heel_plate", P.STEEL_DARK))
    return kids


# ---------------------------------------------------------------------------


def build():
    kids = []
    kids += _floor()
    kids += _seats()
    kids += _console()
    kids += _dash()
    kids += _steering()
    kids += _door_cards()
    kids += _bulkhead()
    kids += _pedals()
    return group("interior", kids)
