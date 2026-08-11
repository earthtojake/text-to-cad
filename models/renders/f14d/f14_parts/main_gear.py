"""F-14D main landing gear -- legs, wheels, brakes, doors and the bays.

Gear DOWN, parked on the deck, both oleos at static compression and both
tyres deflected onto a flat contact patch.

Frame and stance
----------------
Everything here is authored in the WATERLINE frame (``+X`` aft, ``+Y`` port,
``z`` relative to the engine axis) and the whole group is wrapped in
:func:`f14_parts.airframe.stance` exactly once, like every other part module.
The stance is a rotation of ``G.GROUND_PITCH`` about Y followed by a lift of
``G.WATERLINE``, so "straight down in the world" is NOT ``-Z`` in this frame:
it is :data:`DOWN`, tilted 0.6 deg forward.  The tyre contact plane and the
ground-clearance solve both use it, which is what puts the two contact patches
exactly on ``Z = 0`` after the transform rather than 100 mm out.

Architecture (the Tomcat's, not a generic jet's)
------------------------------------------------
The F-14's track (2.010 m) is far narrower than its nacelle spacing (2.92 m),
so the main wheels sit tucked well INBOARD, under the nacelle/tunnel shoulder,
while the legs lean OUTBOARD as they rise to their trunnions up inside the
nacelle structure.  That inboard-leaning splay is the signature of the aircraft
from head on, and it is why the leg is outboard of its wheel: the axle
cantilevers inboard off the oleo, which leaves the whole brake pack -- torque
plate, piston housing, disc stack -- in the open between the leg and the wheel
where it can actually be seen.

The gear retracts FORWARD and up, so the trunnion pin is transverse (along Y),
the bay runs forward from it, and the side brace breaks outboard to the bay's
outer wall.  Down and locked, the brace knuckle is a few degrees over centre.

The bay is a real box cut up INTO the structure: its walls, bulkheads and frames
stop at whatever ``SEC.surfaces`` says the skin is doing at that (x, y), so the
well is recessed into the nacelle instead of hanging below it.  Its roof is not
a flat lid -- a barrel ARCH runs forward over the stowed wheel and the forward
frames are cut around it, which is what stops the well reading as the empty
rectangular box the brief warns about.  The airframe skin is currently lofted
CLOSED, so the well is modelled in its right place and will be revealed the
moment the aperture is cut; :func:`aperture` publishes the exact opening.

Doors
-----
The large door hinges on the INBOARD edge and swings past vertical, which is
the only way round that turns its ribbed inner face outboard where a camera can
see it, and it keeps the open door clear of the wheel.  The small fairing door
is bolted to the strut and rides down with it -- deliberately short, because a
full-length strut door blanks the leg, the brace and the scissors from every
side view and the gear stops reading as a mechanism.

Tyre deflection
---------------
A parked tyre is not a torus.  The carcass is revolved over the 238 deg that is
NOT in contact and lofted over the remaining 124 deg with the section widening
toward the contact, so the sidewalls bulge where the load is; the two halves
butt on identical sections so the seam is invisible.  The tread cap is then
sliced by the ground plane, which is what actually produces the flat.  Without
this the aircraft reads as parked on four hard rings.
"""

from __future__ import annotations

import math

from build123d import (Align, Axis, Box, Circle, Cylinder, Cone, Location,
                       Plane, Polyline, Pos, Rot, Sphere, Spline, Vector,
                       extrude, loft, make_face, mirror, revolve, sweep)

from f14_parts import geometry as G
from f14_parts import sections as SEC
from f14_parts.airframe import stance
from f14_parts.context import group, mirror_pair
from f14_parts import palette as P
from f14_parts.palette import style

# ---------------------------------------------------------------------------
# the stance frame
# ---------------------------------------------------------------------------

_TH = math.radians(G.GROUND_PITCH)
_CT, _ST = math.cos(_TH), math.sin(_TH)

#: unit vector that ``stance()`` maps onto world -Z.  The aircraft is pitched
#: nose down, so "down" in this frame leans very slightly FORWARD.
DOWN = Vector(_ST, 0.0, -_CT).normalized()
UP = -DOWN
#: unit vector that ``stance()`` maps onto world +X (level, aft).
AFT = Vector(_CT, 0.0, _ST).normalized()


def world_z(x, z):
    """World Z of a waterline-frame point, after ``stance()``."""
    return G.WATERLINE - x * _ST + z * _CT


def frame_z(x, zw):
    """Waterline-frame z that lands a point at world height ``zw``."""
    return (zw - G.WATERLINE + x * _ST) / _CT


def _skin(x, y):
    """Underside of the airframe skin at (x, y), waterline frame."""
    _, bot = SEC.surfaces(x, y)
    return -700.0 if bot is None else bot


# ---------------------------------------------------------------------------
# station book -- every number the module places anything against
# ---------------------------------------------------------------------------

X_G = G.X_MAIN_GEAR                 # axle station, 10.640 m
Y_W = G.Y_MAIN_GEAR                 # wheel centre plane, 1.005 m
R_TYRE = G.MAIN_TIRE_D / 2.0        # 470
HW_TYRE = G.MAIN_TIRE_W / 2.0       # 150
DEFL = 28.0                         # static tyre deflection at the patch
R_CONTACT = R_TYRE - DEFL

Z_AXLE = frame_z(X_G, R_CONTACT)    # solved so the patch lands on Z = 0

R_OLEO = 76.0                       # oleo outer cylinder
R_PISTON = 58.0                     # exposed chrome piston
Y_LEG_LO = 1318.0                   # leg centreline at the axle
Y_LEG_HI = 1400.0                   # ... and at the trunnion: leans inboard
X_LEG_HI = 10495.0                  # trunnion station (leg trails aft)
Z_TRUN = -300.0

# bay: a box up inside the nacelle/tunnel shoulder, running FORWARD from the
# trunnion because that is the way the gear folds
BAY_X0, BAY_X1 = 9380.0, 11040.0
BAY_Y0, BAY_Y1 = 760.0, 1660.0
BAY_Z = -190.0                      # roof line, ~570 mm up inside the structure
WALL_T = 22.0
FRAME_T = 16.0
FRAME_D = 118.0                     # how far the frames stand off the roof

# the barrel arch the stowed wheel lives in
ARCH_Y = Y_W
ARCH_A_IN, ARCH_B_IN = 162.0, 252.0
ARCH_A_OUT, ARCH_B_OUT = 184.0, 274.0
ARCH_X1 = 10470.0                   # aft end of the arch

# aperture in the skin (see :func:`aperture`)
AP_X0, AP_X1 = 9430.0, 10980.0
AP_Y0, AP_Y1 = 790.0, 1630.0
DOOR_Y1 = 1400.0                    # main door outboard edge; the fairing door
                                    # carries the strut slot
DOOR_OPEN = 100.0                   # deg, hinged on the INBOARD edge so the
                                    # ribbed inner face turns outboard


def aperture():
    """The skin opening one main gear bay needs, as (x0, x1, y0, y1).

    Published so the module that cuts the airframe skin can take the well's own
    numbers instead of re-deriving them and missing by 30 mm.
    """
    return (AP_X0, AP_X1, AP_Y0, AP_Y1)


# ---------------------------------------------------------------------------
# small builders
# ---------------------------------------------------------------------------


def _v(p):
    return p if isinstance(p, Vector) else Vector(*p)


def _seg(p0, p1, r, r1=None):
    """Round bar between two points; ``r1`` makes it a taper."""
    a, b = _v(p0), _v(p1)
    d = b - a
    h = max(d.length, 1e-6)
    pl = Plane(origin=a, z_dir=d)
    al = (Align.CENTER, Align.CENTER, Align.MIN)
    if r1 is None or abs(r1 - r) < 1e-6:
        return pl * Cylinder(radius=r, height=h, align=al)
    return pl * Cone(bottom_radius=r, top_radius=r1, height=h, align=al)


def _tube(pts, r):
    """A hydraulic/electrical run: circular section swept along a spline."""
    vs = [_v(p) for p in pts]
    try:
        path = Spline(*vs)
        pl = Plane(origin=vs[0], z_dir=path % 0.0)
        return sweep(pl * Circle(r), path=path, is_frenet=True)
    except Exception:                                    # pragma: no cover
        out = _seg(vs[0], vs[1], r)
        for a, b in zip(vs[1:], vs[2:]):
            out = out + _seg(a, b, r) + (Pos(*a) * Sphere(r))
        return out


def _blk(x0, x1, y0, y1, z0, z1):
    """Axis-aligned block from two opposite corners."""
    return Pos((x0 + x1) / 2.0, (y0 + y1) / 2.0, (z0 + z1) / 2.0) * Box(
        abs(x1 - x0), abs(y1 - y0), abs(z1 - z0))


def _plate_xz(y_at, pts, thick):
    """Closed (x, z) polygon standing at ``y_at``, given ``thick`` toward +Y."""
    pl = Plane(origin=(0, y_at, 0), x_dir=(1, 0, 0), z_dir=(0, -1, 0))
    return extrude(pl * make_face(Polyline(*pts, close=True)), amount=-thick)


def _plate_yz(x_at, pts, thick):
    """Closed (y, z) polygon standing at ``x_at``, given ``thick`` toward +X."""
    pl = Plane(origin=(x_at, 0, 0), x_dir=(0, 1, 0), z_dir=(1, 0, 0))
    return extrude(pl * make_face(Polyline(*pts, close=True)), amount=thick)


def _plate_xy(z_at, pts, thick):
    """Closed (x, y) polygon lying at ``z_at``, given ``thick`` toward +Z."""
    pl = Plane(origin=(0, 0, z_at), x_dir=(1, 0, 0), z_dir=(0, 0, 1))
    return extrude(pl * make_face(Polyline(*pts, close=True)), amount=thick)


def _rect_xz(y_at, x0, x1, z0, z1, thick):
    return _plate_xz(y_at, [(x0, z0), (x1, z0), (x1, z1), (x0, z1)], thick)


def _rect_yz(x_at, y0, y1, z0, z1, thick):
    return _plate_yz(x_at, [(y0, z0), (y1, z0), (y1, z1), (y0, z1)], thick)


def _rect_xy(z_at, x0, x1, y0, y1, thick):
    return _plate_xy(z_at, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], thick)


def _holes_x(x_at, spots, r, depth):
    """Lightening holes for a plate standing at ``x_at`` (axis along X)."""
    return [_seg((x_at - depth, y, z), (x_at + depth, y, z), r) for y, z in spots]


def _holes_y(y_at, spots, r, depth):
    return [_seg((x, y_at - depth, z), (x, y_at + depth, z), r) for x, z in spots]


# ---------------------------------------------------------------------------
# the leg
# ---------------------------------------------------------------------------


def _leg_pt(t):
    """Point on the oleo centreline; t = 0 at the trunnion, 1 at the axle."""
    return Vector(X_LEG_HI + (X_G - X_LEG_HI) * t,
                  Y_LEG_HI + (Y_LEG_LO - Y_LEG_HI) * t,
                  Z_TRUN + (Z_AXLE - Z_TRUN) * t)


_LEG_U = (_leg_pt(1.0) - _leg_pt(0.0)).normalized()
#: aft, made perpendicular to the leg, so lugs stand off it squarely
_LEG_AFT = (AFT - _LEG_U * AFT.dot(_LEG_U)).normalized()
#: outboard, likewise
_LEG_OUT = _LEG_U.cross(_LEG_AFT).normalized()
if _LEG_OUT.Y < 0:
    _LEG_OUT = -_LEG_OUT


def _leg_off(t, aft=0.0, out=0.0):
    return _leg_pt(t) + _LEG_AFT * aft + _LEG_OUT * out


def _oleo(sfx):
    """Trunnion, oleo cylinder, chrome piston, axle housing and the axle."""
    out = []
    top = _leg_pt(-0.02)
    # trunnion: a cast yoke on a transverse pin -- the gear folds forward
    out.append(style(_seg(_leg_pt(0.10), top, 96.0, 82.0),
                     f"mlg_trunnion_yoke:{sfx}", P.GEAR_WHITE))
    out.append(style(_seg((X_LEG_HI, Y_LEG_HI - 172.0, Z_TRUN),
                          (X_LEG_HI, Y_LEG_HI + 156.0, Z_TRUN), 44.0),
                     f"mlg_trunnion_pin:{sfx}", P.STEEL_DARK))
    for tag, y in (("inbd", Y_LEG_HI - 154.0), ("outbd", Y_LEG_HI + 138.0)):
        out.append(style(_rect_xz(y, X_LEG_HI - 122.0, X_LEG_HI + 122.0,
                                  Z_TRUN - 100.0, BAY_Z + 2.0, 36.0),
                         f"mlg_trunnion_lug:{sfx}_{tag}", P.ALUM_DARK))
        out.append(style(_seg((X_LEG_HI, y - 6.0, Z_TRUN),
                              (X_LEG_HI, y + 42.0, Z_TRUN), 64.0),
                         f"mlg_trunnion_boss:{sfx}_{tag}", P.ALUM_DARK))
        # doubler tying the lug into the bay roof
        out.append(style(_rect_xy(BAY_Z - 12.0, X_LEG_HI - 150.0, X_LEG_HI + 150.0,
                                  y - 40.0, y + 46.0, 14.0),
                         f"mlg_trunnion_doubler:{sfx}_{tag}", P.ALUM_DARK))
    # oleo
    out.append(style(_seg(_leg_pt(0.06), _leg_pt(0.575), R_OLEO),
                     f"mlg_oleo_cylinder:{sfx}", P.GEAR_WHITE))
    out.append(style(_seg(_leg_pt(0.545), _leg_pt(0.605), R_OLEO + 8.0),
                     f"mlg_oleo_gland:{sfx}", P.ALUM_DARK))
    out.append(style(_seg(_leg_pt(0.595), _leg_pt(0.875), R_PISTON),
                     f"mlg_oleo_piston:{sfx}", P.OLEO_CHROME))
    out.append(style(_seg(_leg_pt(0.845), _leg_pt(1.02), 80.0),
                     f"mlg_axle_housing:{sfx}", P.GEAR_WHITE))
    # charging valve, pressure gauge and the WoW switch box
    out.append(style(_seg(_leg_off(0.16, aft=52.0), _leg_off(0.16, aft=98.0), 16.0),
                     f"mlg_oleo_charge_valve:{sfx}", P.BRASS))
    out.append(style(_seg(_leg_off(0.30, out=60.0), _leg_off(0.30, out=90.0), 13.0),
                     f"mlg_oleo_gauge:{sfx}", P.ALUM_DARK))
    wow = _leg_off(0.80, aft=-72.0, out=-26.0)
    out.append(style(_seg(wow, wow + _LEG_AFT * -46.0, 30.0),
                     f"mlg_wow_switch:{sfx}", P.ALUM_DARK))
    # axle: cantilevered INBOARD, the wheel and the whole brake pack ride on it
    ax = _leg_pt(1.0)
    out.append(style(_seg((X_G, ax.Y - 34.0, Z_AXLE), (X_G, Y_W - 176.0, Z_AXLE), 54.0),
                     f"mlg_axle:{sfx}", P.STEEL_DARK))
    out.append(style(_seg((X_G, Y_W - 176.0, Z_AXLE), (X_G, Y_W - 208.0, Z_AXLE), 62.0),
                     f"mlg_axle_nut:{sfx}", P.ALUM_DARK))
    return out


def _torque_links(sfx):
    """Scissors on the aft face -- the piston cannot rotate in the cylinder."""
    a = _leg_off(0.46, aft=86.0)
    knee = _leg_off(0.685, aft=158.0)
    b = _leg_off(0.895, aft=78.0)
    out = [
        style(_seg(a, knee, 30.0, 24.0), f"mlg_torque_link_upper:{sfx}", P.GEAR_WHITE),
        style(_seg(knee, b, 30.0, 24.0), f"mlg_torque_link_lower:{sfx}", P.GEAR_WHITE),
    ]
    for tag, p, r in (("upper", a, 34.0), ("knee", knee, 30.0), ("lower", b, 34.0)):
        out.append(style(_seg(p - _LEG_OUT * 46.0, p + _LEG_OUT * 46.0, r),
                         f"mlg_torque_pin:{sfx}_{tag}", P.STEEL_DARK))
    out.append(style(_seg(_leg_pt(0.46), a, 40.0, 30.0),
                     f"mlg_torque_lug:{sfx}_upper", P.GEAR_WHITE))
    out.append(style(_seg(_leg_pt(0.895), b, 40.0, 30.0),
                     f"mlg_torque_lug:{sfx}_lower", P.GEAR_WHITE))
    return out


_BRACE_LEG = _leg_off(0.615, out=72.0)
_BRACE_TOP = Vector(10545.0, BAY_Y1 - 54.0, -430.0)
_BRACE_KNEE = (_BRACE_LEG + _BRACE_TOP) * 0.5 + Vector(30.0, 0.0, -16.0)


def _side_brace(sfx):
    """Two-piece folding side brace, down and a few degrees over centre."""
    out = [
        style(_seg(_BRACE_TOP, _BRACE_KNEE, 34.0, 40.0),
              f"mlg_side_brace_upper:{sfx}", P.GEAR_WHITE),
        style(_seg(_BRACE_KNEE, _BRACE_LEG, 40.0, 34.0),
              f"mlg_side_brace_lower:{sfx}", P.GEAR_WHITE),
    ]
    hinge = Vector(1, 0, 0) * 62.0
    out.append(style(_seg(_BRACE_KNEE - hinge, _BRACE_KNEE + hinge, 34.0),
                     f"mlg_brace_knuckle:{sfx}", P.ALUM_DARK))
    out.append(style(_seg(_BRACE_TOP - hinge * 0.8, _BRACE_TOP + hinge * 0.8, 30.0),
                     f"mlg_brace_pin:{sfx}_top", P.STEEL_DARK))
    out.append(style(_seg(_BRACE_LEG - hinge * 0.8, _BRACE_LEG + hinge * 0.8, 30.0),
                     f"mlg_brace_pin:{sfx}_leg", P.STEEL_DARK))
    out.append(style(_rect_xz(BAY_Y1 - 86.0, _BRACE_TOP.X - 96.0, _BRACE_TOP.X + 96.0,
                              _BRACE_TOP.Z - 44.0, BAY_Z + 2.0, 74.0),
                     f"mlg_brace_fitting:{sfx}", P.ALUM_DARK))
    # downlock: a short over-centre link and its return spring
    lk0 = _BRACE_KNEE + Vector(-52.0, 0.0, 62.0)
    lk1 = _leg_off(0.40, out=70.0)
    out.append(style(_seg(lk0, lk1, 20.0), f"mlg_downlock_link:{sfx}", P.ALUM_DARK))
    out.append(style(_seg(_BRACE_KNEE + Vector(-8.0, 0.0, 34.0),
                          lk1 + Vector(6.0, 0.0, -26.0), 13.0),
                     f"mlg_downlock_spring:{sfx}", P.STEEL_BURN))
    return out


_ACT_TOP = Vector(10150.0, 1430.0, -336.0)
_ACT_MID = Vector(10362.0, 1404.0, -604.0)
_ACT_ROD = _leg_off(0.40, aft=-96.0, out=42.0)


def _retract_actuator(sfx):
    out = [
        style(_seg(_ACT_TOP, _ACT_MID, 54.0), f"mlg_retract_actuator:{sfx}", P.ALUM_DARK),
        style(_seg(_ACT_MID, _ACT_ROD, 28.0), f"mlg_retract_rod:{sfx}", P.OLEO_CHROME),
        style(_seg(_ACT_MID + Vector(-16.0, 0, 20.0), _ACT_MID + Vector(6.0, 0, -8.0), 62.0),
              f"mlg_actuator_gland:{sfx}", P.STEEL_DARK),
    ]
    hinge = Vector(0, 54.0, 0)
    out.append(style(_seg(_ACT_TOP - hinge, _ACT_TOP + hinge, 26.0),
                     f"mlg_actuator_pin:{sfx}_bay", P.STEEL_DARK))
    out.append(style(_rect_yz(_ACT_TOP.X - 15.0, _ACT_TOP.Y - 74.0, _ACT_TOP.Y + 74.0,
                              _ACT_TOP.Z - 26.0, BAY_Z + 2.0, 30.0),
                     f"mlg_actuator_mount:{sfx}", P.ALUM_DARK))
    out.append(style(_seg(_leg_pt(0.40), _ACT_ROD, 40.0, 28.0),
                     f"mlg_actuator_lug:{sfx}", P.GEAR_WHITE))
    for tag, dy in (("ext", -34.0), ("ret", 4.0)):
        out.append(style(_tube([
            (10600.0, 1560.0, BAY_Z - 44.0),
            (10440.0, 1520.0 + dy * 0.4, BAY_Z - 66.0),
            (10230.0, 1462.0 + dy, BAY_Z - 108.0),
            (_ACT_TOP.X + 26.0, _ACT_TOP.Y + dy * 0.5, _ACT_TOP.Z + 24.0),
        ], 13.0), f"mlg_actuator_line:{sfx}_{tag}", P.HYDRAULIC))
    return out


def _leg_plumbing(sfx):
    """Brake lines and the weight-on-wheels loom, clamped down the leg."""
    out = []
    top = _leg_off(0.02, aft=64.0, out=-28.0)
    for tag, dy, r, col in (("a", -30.0, 13.0, P.HYDRAULIC),
                            ("b", 6.0, 13.0, P.HYDRAULIC),
                            ("loom", 40.0, 17.0, P.WIRE_LOOM)):
        pts = [
            (10820.0, 900.0, BAY_Z - 46.0 - dy * 0.2),
            (10700.0, 1180.0 + dy * 0.5, BAY_Z - 82.0),
            (top.X + dy * 0.3, top.Y + dy * 0.6, top.Z),
            tuple(_leg_off(0.30, aft=70.0 + dy * 0.5, out=-30.0)),
            tuple(_leg_off(0.62, aft=64.0 + dy * 0.5, out=-34.0)),
            tuple(_leg_off(0.90, aft=52.0 + dy * 0.4, out=-56.0)),
            (X_G + 44.0 + dy * 0.3, Y_W + 186.0, Z_AXLE + 66.0),
        ]
        out.append(style(_tube(pts, r), f"mlg_leg_line:{sfx}_{tag}", col))
    for i, t in enumerate((0.20, 0.42, 0.66, 0.86)):
        c = _leg_off(t, aft=52.0, out=-30.0)
        out.append(style(_seg(c - _LEG_AFT * 30.0, c + _LEG_AFT * 22.0, 34.0, 28.0),
                         f"mlg_line_clamp:{sfx}_{i}", P.ALUM_DARK))
    return out


# ---------------------------------------------------------------------------
# the wheel
# ---------------------------------------------------------------------------

# Carcass: bead -> max section -> shoulder.  The tread cap covers everything
# outboard of r = 418, so the carcass's outer edge only ever shows as a thin
# shoulder line.  Kept to SEVEN smooth points on purpose: the raised sidewall
# band belongs on its own revolved ring, because a 4 mm step in this profile is
# a near-vertical edge in every one of the bulge loft's sections and it took the
# tyre from 1.5 s to 14 s to fit.
_CARCASS = [
    (228.0, 116.0), (250.0, 133.0), (288.0, 145.0), (334.0, 150.0),
    (376.0, 146.0), (404.0, 140.0), (418.0, 136.0),
]
_TREAD_HW = 112.0
_TREAD_R = 470.0
_GROOVE_D = 9.0


def _tread_profile():
    """Crowned tread cap with four moulded circumferential grooves."""

    def rc(a):
        return _TREAD_R - 3.4 * (a / _TREAD_HW) ** 2

    pts = [(405.0, 132.0), (424.0, 130.0), (446.0, 122.0), (460.0, 114.0)]
    seq = [("p", _TREAD_HW), ("p", 96.0), ("p", 84.0)]
    for c in (66.0, 22.0, -22.0, -66.0):
        seq.append(("g", c))
        seq.append(("p", c - 22.0))
    seq = seq[:-1] + [("p", -84.0), ("p", -96.0), ("p", -_TREAD_HW)]
    outer = []
    for kind, a in seq:
        if kind == "p":
            outer.append((rc(a), a))
        else:
            outer += [(rc(a + 8.0), a + 8.0), (rc(a + 8.0) - _GROOVE_D, a + 8.0),
                      (rc(a - 8.0) - _GROOVE_D, a - 8.0), (rc(a - 8.0), a - 8.0)]
    return pts + outer + [(r, -a) for r, a in reversed(pts)]


def _wheel_frame(side, phi=0.0):
    """Section plane at ``phi`` about the axle; phi = 0 is straight up.

    ``(u, v)`` in the returned plane is (radius, axial-outboard), so the same
    2-D profile serves both sides and the pair comes out a true mirror.
    """
    origin = Vector(X_G, side * Y_W, Z_AXLE)
    axle = Vector(0.0, side, 0.0)
    rad = UP * math.cos(phi) + (AFT * side) * math.sin(phi)
    return Plane(origin=origin, x_dir=rad, z_dir=rad.cross(axle))


def _wheel_axis(side):
    return Axis(Vector(X_G, side * Y_W, Z_AXLE), Vector(0.0, side, 0.0))


def _ground_cutter(side):
    """Half space below the contact plane, exactly on world Z = 0."""
    o = Vector(X_G, side * Y_W, Z_AXLE) + DOWN * R_CONTACT
    pl = Plane(origin=o, x_dir=AFT * side, z_dir=DOWN)
    return pl * Box(1600.0, 900.0, 900.0, align=(Align.CENTER, Align.CENTER, Align.MIN))


_BULGE = 0.105                       # sidewall growth at the contact patch
_SPREAD = math.radians(62.0)         # ... dying out this far round the tyre


def _carcass_section(dphi):
    """Full closed carcass profile, widened by the local contact bulge."""
    g = max(0.0, 1.0 - (dphi / _SPREAD) ** 2)
    pts = []
    for r, a in _CARCASS:
        # the bulge is centred on the max section: nothing at the bead, nothing
        # at the shoulder, so the tread cap still sits flush over the carcass
        taper = min((r - 228.0) / 70.0, (418.0 - r) / 60.0, 1.0)
        pts.append((r, a * (1.0 + _BULGE * g * max(0.0, taper))))
    return pts + [(r, -a) for r, a in reversed(pts)]


def _tyre(side, sfx):
    """Carcass + tread, deflected onto a flat patch with a sidewall bulge."""
    prof = _carcass_section(_SPREAD * 9.9)          # = undeflected section
    face = _wheel_frame(side, math.radians(241.0)) * make_face(
        Polyline(*prof, close=True))
    body = revolve(face, axis=_wheel_axis(side), revolution_arc=238.0)
    faces = []
    n = 19
    for i in range(n):
        phi = math.radians(118.0 + 124.0 * i / (n - 1.0))
        faces.append(_wheel_frame(side, phi) * make_face(
            Polyline(*_carcass_section(phi - math.pi), close=True)))
    carcass = body + loft(faces)

    tread = revolve(_wheel_frame(side, 0.0) * make_face(
        Polyline(*_tread_profile(), close=True)),
        axis=_wheel_axis(side), revolution_arc=360.0)

    # raised sidewall band (the moulded lettering ring).  A plain revolve, so
    # the contact bulge simply swallows it where the sidewall is loaded --
    # which is exactly what happens to the real one.
    band = revolve(_wheel_frame(side, 0.0) * make_face(Polyline(
        (344.0, 148.0), (350.0, 153.0), (372.0, 150.0), (376.0, 145.0),
        (376.0, -145.0), (372.0, -150.0), (350.0, -153.0), (344.0, -148.0),
        close=True)), axis=_wheel_axis(side), revolution_arc=360.0)

    cut = _ground_cutter(side)
    return [style(carcass - cut, f"mlg_tyre_carcass:{sfx}", P.TYRE_WALL),
            style(band - cut, f"mlg_tyre_band:{sfx}", P.TYRE_WALL),
            style(tread - cut, f"mlg_tyre_tread:{sfx}", P.TYRE)]


def _revolved(side, prof, arc=360.0, phi=0.0):
    return revolve(_wheel_frame(side, phi) * make_face(Polyline(*prof, close=True)),
                   axis=_wheel_axis(side), revolution_arc=arc)


def _polar(side, r, deg, v=0.0):
    """Point at radius ``r``, clock angle ``deg`` and axial offset ``v``."""
    pl = _wheel_frame(side, 0.0)
    a = math.radians(deg)
    return pl.origin + pl.x_dir * (r * math.cos(a)) - pl.z_dir * (r * math.sin(a)) \
        + pl.y_dir * v


def _wheel(side, sfx):
    """Forged two-piece wheel: barrel, bead flanges, web, hub cap, tie bolts."""
    pl = _wheel_frame(side, 0.0)
    n_ax = pl.y_dir
    out = [
        style(_revolved(side, [
            (196.0, -152.0), (232.0, -152.0), (250.0, -138.0), (238.0, -126.0),
            (228.0, -118.0), (228.0, 118.0), (238.0, 126.0), (250.0, 138.0),
            (232.0, 152.0), (196.0, 152.0), (196.0, 118.0), (208.0, 104.0),
            (208.0, -104.0), (196.0, -118.0),
        ]), f"mlg_wheel_rim:{sfx}", P.ALUMINIUM),
        # inboard web: the closed face of the wheel, dished away from the brake
        style(_revolved(side, [
            (86.0, -152.0), (196.0, -152.0), (196.0, -118.0), (150.0, -104.0),
            (108.0, -110.0), (86.0, -124.0),
        ]), f"mlg_wheel_web:{sfx}", P.ALUM_DARK),
        style(_revolved(side, [
            (0.0, -172.0), (66.0, -170.0), (98.0, -156.0), (104.0, -142.0),
            (0.0, -142.0),
        ]), f"mlg_wheel_hubcap:{sfx}", P.ALUMINIUM),
        style(_revolved(side, [
            (78.0, -132.0), (112.0, -132.0), (112.0, 96.0), (78.0, 96.0),
        ]), f"mlg_wheel_bearing:{sfx}", P.STEEL_DARK),
    ]
    for k in range(14):
        c = _polar(side, 176.0, k * 360.0 / 14.0)
        out.append(style(_seg(c - n_ax * 156.0, c - n_ax * 138.0, 15.0),
                         f"mlg_wheel_bolt:{sfx}_{k:02d}", P.STEEL_DARK))
    for k in range(3):
        c = _polar(side, 150.0, 24.0 + k * 120.0)
        out.append(style(_seg(c - n_ax * 162.0, c - n_ax * 149.0, 14.0),
                         f"mlg_fuse_plug:{sfx}_{k}", P.BRASS))
    c = _polar(side, 132.0, 78.0)
    out.append(style(_seg(c - n_ax * 168.0, c - n_ax * 150.0, 11.0),
                     f"mlg_valve_stem:{sfx}", P.BRASS))
    return out


def _brakes(side, sfx):
    """Multi-disc pack, torque plate and piston housing, out in plain sight."""
    out = []
    n_ax = _wheel_frame(side, 0.0).y_dir
    for k in range(7):
        v = 118.0 - 19.0 * k
        rotor = k % 2 == 0
        r0, r1 = (108.0, 192.0) if rotor else (96.0, 178.0)
        out.append(style(_revolved(side, [
            (r0, v - 6.0), (r1, v - 6.0), (r1, v + 6.0), (r0, v + 6.0)]),
            f"mlg_brake_{'rotor' if rotor else 'stator'}:{sfx}_{k}",
            P.STEEL_DARK if rotor else P.STEEL_BURN))
    out.append(style(_revolved(side, [
        (74.0, -100.0), (92.0, -100.0), (92.0, 122.0), (74.0, 122.0)]),
        f"mlg_brake_torque_tube:{sfx}", P.ALUM_DARK))
    out.append(style(_revolved(side, [
        (70.0, 130.0), (196.0, 130.0), (196.0, 150.0), (172.0, 168.0),
        (96.0, 168.0), (70.0, 156.0)]),
        f"mlg_brake_housing:{sfx}", P.ALUM_DARK))
    for k in range(6):
        c = _polar(side, 158.0, 15.0 + k * 60.0)
        out.append(style(_seg(c + n_ax * 148.0, c + n_ax * 188.0, 26.0),
                         f"mlg_brake_piston:{sfx}_{k}", P.OLEO_CHROME))
    arm0 = _polar(side, 190.0, 0.0, 160.0)
    out.append(style(_seg(arm0, _leg_off(0.94, aft=-58.0), 26.0, 22.0),
                     f"mlg_brake_torque_arm:{sfx}", P.ALUM_DARK))
    for tag, deg in (("in", 66.0), ("out", 90.0)):
        c = _polar(side, 150.0, deg)
        out.append(style(_seg(c + n_ax * 160.0, c + n_ax * 198.0, 17.0),
                         f"mlg_brake_fitting:{sfx}_{tag}", P.BRASS))
    return out


# ---------------------------------------------------------------------------
# the bay
# ---------------------------------------------------------------------------


def _arch_poly(a, b, floor=None):
    """(y, z) closed polygon: half-ellipse standing on the roof line."""
    floor = BAY_Z - 40.0 if floor is None else floor
    pts = []
    n = 17
    for i in range(n + 1):
        t = i / n
        y = ARCH_Y - a + 2.0 * a * t
        z = BAY_Z + b * math.sqrt(max(0.0, 1.0 - ((y - ARCH_Y) / a) ** 2))
        pts.append((y, z))
    return [(ARCH_Y - a, floor)] + pts + [(ARCH_Y + a, floor)]


def _arch_solid(x0, x1, a, b):
    return _plate_yz(x0, _arch_poly(a, b), x1 - x0)


def _wall_pts(y_at, x0, x1, z_top, n=11):
    """(x, z) polygon for a fore/aft wall: bottom edge riding the skin."""
    bot = [(x0 + (x1 - x0) * i / (n - 1.0),) for i in range(n)]
    bot = [(x, _skin(x, y_at) + 4.0) for (x,) in bot]
    return bot + [(x1, z_top), (x0, z_top)]


def _bulk_pts(x_at, y0, y1, z_top, n=9):
    """(y, z) polygon for a bulkhead: bottom edge riding the skin."""
    bot = [(y0 + (y1 - y0) * i / (n - 1.0),) for i in range(n)]
    bot = [(y, _skin(x_at, y) + 4.0) for (y,) in bot]
    return bot + [(y1, z_top), (y0, z_top)]


def _bay_shell(sfx):
    """Roof, wheel arch, walls, bulkheads and the aperture sill."""
    out = []
    ax0 = BAY_X0 - 24.0
    # the arch the stowed wheel lives in -- the reason the well is not a box
    out.append(style(_arch_solid(ax0, ARCH_X1, ARCH_A_OUT, ARCH_B_OUT)
                     - _arch_solid(ax0 - 30.0, ARCH_X1 + 30.0, ARCH_A_IN, ARCH_B_IN),
                     f"mlg_wheel_arch:{sfx}", P.BAY_GREEN))
    for tag, x in (("fwd", ax0), ("aft", ARCH_X1)):
        out.append(style(_plate_yz(x, _arch_poly(ARCH_A_OUT, ARCH_B_OUT), 24.0),
                         f"mlg_arch_closure:{sfx}_{tag}", P.BAY_GREEN))
    # roof: two strips either side of the arch, plus the flat aft lid
    out.append(style(_rect_xy(BAY_Z, ax0, ARCH_X1, BAY_Y0 - WALL_T,
                              ARCH_Y - ARCH_A_OUT + 2.0, 26.0),
                     f"mlg_bay_roof:{sfx}_inbd", P.BAY_GREEN))
    out.append(style(_rect_xy(BAY_Z, ax0, ARCH_X1, ARCH_Y + ARCH_A_OUT - 2.0,
                              BAY_Y1 + WALL_T, 26.0),
                     f"mlg_bay_roof:{sfx}_outbd", P.BAY_GREEN))
    out.append(style(_rect_xy(BAY_Z, ARCH_X1, BAY_X1 + 24.0, BAY_Y0 - WALL_T,
                              BAY_Y1 + WALL_T, 26.0),
                     f"mlg_bay_roof:{sfx}_aft", P.BAY_GREEN))
    # walls and bulkheads, every bottom edge sitting on the queried skin
    out.append(style(_plate_xz(BAY_Y0 - WALL_T,
                               _wall_pts(BAY_Y0, BAY_X0, BAY_X1, BAY_Z), WALL_T),
                     f"mlg_bay_wall:{sfx}_inbd", P.BAY_GREEN))
    out.append(style(_plate_xz(BAY_Y1,
                               _wall_pts(BAY_Y1, BAY_X0, BAY_X1, BAY_Z), WALL_T),
                     f"mlg_bay_wall:{sfx}_outbd", P.BAY_GREEN))
    out.append(style(_plate_yz(ax0, _bulk_pts(BAY_X0, BAY_Y0, BAY_Y1, BAY_Z), 24.0),
                     f"mlg_bay_bulkhead:{sfx}_fwd", P.BAY_GREEN))
    out.append(style(_plate_yz(BAY_X1, _bulk_pts(BAY_X1, BAY_Y0, BAY_Y1, BAY_Z), 24.0),
                     f"mlg_bay_bulkhead:{sfx}_aft", P.BAY_GREEN))
    # sill: the rolled flange round the aperture the doors seal against
    for tag, y in (("inbd", AP_Y0), ("outbd", AP_Y1)):
        pts = [(AP_X0, _skin(AP_X0, y) + 6.0)]
        pts += [(AP_X0 + (AP_X1 - AP_X0) * i / 8.0,
                 _skin(AP_X0 + (AP_X1 - AP_X0) * i / 8.0, y) + 6.0) for i in range(1, 9)]
        pts += [(AP_X1, _skin(AP_X1, y) + 62.0), (AP_X0, _skin(AP_X0, y) + 62.0)]
        out.append(style(_plate_xz(y - (14.0 if tag == "inbd" else 0.0), pts, 14.0),
                         f"mlg_bay_sill:{sfx}_{tag}", P.GEAR_WHITE))
    for tag, x in (("fwd", AP_X0), ("aft", AP_X1)):
        pts = [(AP_Y0 + (AP_Y1 - AP_Y0) * i / 8.0,
                _skin(x, AP_Y0 + (AP_Y1 - AP_Y0) * i / 8.0) + 6.0) for i in range(9)]
        pts += [(AP_Y1, _skin(x, AP_Y1) + 62.0), (AP_Y0, _skin(x, AP_Y0) + 62.0)]
        out.append(style(_plate_yz(x - (14.0 if tag == "fwd" else 0.0), pts, 14.0),
                         f"mlg_bay_sill:{sfx}_{tag}", P.GEAR_WHITE))
    return out


def _bay_frames(sfx):
    """Frames, longerons, stiffeners and gussets -- the well's structure."""
    out = []
    z0, z1 = BAY_Z - FRAME_D, BAY_Z + 2.0
    # forward frames arch OVER the wheel well: a plate with the arch cut out
    arch = _arch_solid(BAY_X0 - 60.0, ARCH_X1 + 60.0, ARCH_A_OUT, ARCH_B_OUT)
    for i, x in enumerate((9520.0, 9790.0, 10060.0, 10330.0)):
        plate = _rect_yz(x, BAY_Y0 - 2.0, BAY_Y1 + 2.0, z0, BAY_Z + ARCH_B_OUT + 70.0,
                         FRAME_T)
        plate = plate - ([arch] + _holes_x(x, [(1290.0, z0 + 48.0),
                                               (1450.0, z0 + 48.0),
                                               (1580.0, z0 + 48.0)], 28.0, 60.0))
        out.append(style(plate, f"mlg_bay_frame:{sfx}_f{i}", P.BAY_GREEN))
    for i, x in enumerate((10600.0, 10830.0, 11010.0)):
        plate = _rect_yz(x, BAY_Y0 - 2.0, BAY_Y1 + 2.0, z0, z1, FRAME_T)
        plate = plate - _holes_x(x, [(y, z0 + 48.0) for y in
                                     (890.0, 1060.0, 1230.0, 1400.0, 1570.0)],
                                 30.0, 60.0)
        out.append(style(plate, f"mlg_bay_frame:{sfx}_a{i}", P.BAY_GREEN))
    # longerons
    for tag, y, zd in (("inbd", 800.0, 130.0), ("outbd", 1600.0, 150.0)):
        plate = _rect_xz(y, BAY_X0, BAY_X1, BAY_Z - zd, BAY_Z + 2.0, FRAME_T)
        spots = [(x, BAY_Z - zd * 0.52) for x in
                 (9560.0, 9840.0, 10120.0, 10400.0, 10680.0, 10940.0)]
        plate = plate - _holes_y(y, spots, 34.0, 60.0)
        out.append(style(plate, f"mlg_bay_longeron:{sfx}_{tag}", P.BAY_GREEN))
    # wall stiffeners
    for i, x in enumerate((9560.0, 9920.0, 10280.0, 10640.0, 10960.0)):
        for tag, y, t in (("inbd", BAY_Y0 - WALL_T, -14.0),
                          ("outbd", BAY_Y1 + WALL_T, 14.0)):
            zb = _skin(x, BAY_Y0 if tag == "inbd" else BAY_Y1) + 34.0
            out.append(style(_rect_xz(y, x - 26.0, x + 26.0, zb, BAY_Z, t),
                             f"mlg_bay_stiffener:{sfx}_{tag}{i}", P.BAY_GREEN))
    # corner gussets
    for tag, x, y in (("f0", BAY_X0 + 4.0, BAY_Y0), ("f1", BAY_X0 + 4.0, BAY_Y1),
                      ("a0", BAY_X1 - 130.0, BAY_Y0), ("a1", BAY_X1 - 130.0, BAY_Y1)):
        sy = 1.0 if y < 1000.0 else -1.0
        pts = [(y, BAY_Z), (y + sy * 150.0, BAY_Z), (y, BAY_Z - 150.0)]
        out.append(style(_plate_yz(x, pts, 120.0),
                         f"mlg_bay_gusset:{sfx}_{tag}", P.BAY_GREEN))
    return out


def _bay_systems(sfx):
    """Accumulators, reservoir, uplock, manifold, lines and looms."""
    out = []
    # two hydraulic accumulators lying transversely between frames
    out.append(style(_seg((10450.0, 1310.0, BAY_Z - 118.0),
                          (10450.0, 1620.0, BAY_Z - 118.0), 66.0),
                     f"mlg_accumulator:{sfx}_a", P.ALUMINIUM))
    for tag, y, d in (("a0", 1310.0, -36.0), ("a1", 1620.0, 36.0)):
        out.append(style(_seg((10450.0, y, BAY_Z - 118.0),
                              (10450.0, y + d, BAY_Z - 118.0), 68.0, 42.0),
                         f"mlg_accum_cap:{sfx}_{tag}", P.STEEL_DARK))
    out.append(style(_seg((10730.0, 880.0, BAY_Z - 112.0),
                          (10730.0, 1160.0, BAY_Z - 112.0), 54.0),
                     f"mlg_accumulator:{sfx}_b", P.ALUMINIUM))
    for i, y in enumerate((1360.0, 1580.0)):
        out.append(style(_rect_yz(10410.0, y - 32.0, y + 32.0,
                                  BAY_Z - 132.0, BAY_Z, 80.0),
                         f"mlg_accum_strap:{sfx}_{i}", P.ALUM_DARK))
    # reservoir and the emergency-extension bottle on the outboard wall
    out.append(style(_seg((9640.0, 1600.0, BAY_Z - 150.0),
                          (10160.0, 1600.0, BAY_Z - 150.0), 74.0),
                     f"mlg_hyd_reservoir:{sfx}", P.ALUMINIUM))
    out.append(style(_seg((9600.0, 1600.0, BAY_Z - 150.0),
                          (9640.0, 1600.0, BAY_Z - 150.0), 46.0, 76.0),
                     f"mlg_reservoir_cap:{sfx}_f", P.STEEL_DARK))
    out.append(style(_seg((10200.0, 1600.0, BAY_Z - 150.0),
                          (10160.0, 1600.0, BAY_Z - 150.0), 46.0, 76.0),
                     f"mlg_reservoir_cap:{sfx}_a", P.STEEL_DARK))
    for i, x in enumerate((9760.0, 10060.0)):
        out.append(style(_rect_yz(x, 1520.0, BAY_Y1, BAY_Z - 170.0, BAY_Z, 28.0),
                         f"mlg_reservoir_strap:{sfx}_{i}", P.ALUM_DARK))
    out.append(style(_seg((9480.0, 830.0, BAY_Z - 140.0),
                          (9840.0, 830.0, BAY_Z - 140.0), 62.0),
                     f"mlg_air_bottle:{sfx}", P.STEEL_BURN))
    out.append(style(_seg((9840.0, 830.0, BAY_Z - 140.0),
                          (9880.0, 830.0, BAY_Z - 140.0), 30.0),
                     f"mlg_air_bottle_valve:{sfx}", P.BRASS))
    # uplock: the hook that catches the leg when it is folded away forward
    up = Vector(9700.0, ARCH_Y + 60.0, BAY_Z - 40.0)
    out.append(style(_blk(up.X - 70.0, up.X + 70.0, up.Y - 46.0, up.Y + 46.0,
                          BAY_Z - 150.0, BAY_Z), f"mlg_uplock_body:{sfx}", P.ALUM_DARK))
    out.append(style(_seg((up.X - 40.0, up.Y - 60.0, BAY_Z - 190.0),
                          (up.X - 40.0, up.Y + 60.0, BAY_Z - 190.0), 26.0),
                     f"mlg_uplock_hook:{sfx}", P.STEEL_DARK))
    out.append(style(_seg((up.X + 60.0, up.Y, BAY_Z - 90.0),
                          (up.X + 240.0, up.Y - 30.0, BAY_Z - 60.0), 30.0),
                     f"mlg_uplock_actuator:{sfx}", P.ALUM_DARK))
    out.append(style(_seg((up.X - 40.0, up.Y + 60.0, BAY_Z - 190.0),
                          (up.X - 40.0, up.Y + 90.0, BAY_Z - 190.0), 34.0),
                     f"mlg_uplock_roller:{sfx}", P.STEEL_BURN))
    # manifold block and its valves
    out.append(style(_blk(10820.0, 11000.0, 800.0, 950.0, BAY_Z - 120.0, BAY_Z),
                     f"mlg_hyd_manifold:{sfx}", P.ALUM_DARK))
    for i, x in enumerate((10860.0, 10940.0)):
        out.append(style(_seg((x, 870.0, BAY_Z - 120.0), (x, 870.0, BAY_Z - 178.0), 26.0),
                         f"mlg_hyd_valve:{sfx}_{i}", P.BRASS))
    out.append(style(_seg((10910.0, 950.0, BAY_Z - 62.0),
                          (10910.0, 1010.0, BAY_Z - 62.0), 22.0),
                     f"mlg_hyd_filter:{sfx}", P.STEEL_DARK))
    # electrical junction boxes and their connectors
    for i, x in enumerate((9560.0, 10740.0)):
        out.append(style(_blk(x, x + 160.0, BAY_Y0 - 2.0, BAY_Y0 + 78.0,
                              BAY_Z - 268.0, BAY_Z - 142.0),
                         f"mlg_junction_box:{sfx}_{i}", P.ALUM_DARK))
        for k in range(2):
            out.append(style(_seg((x + 44.0 + 64.0 * k, BAY_Y0 + 78.0, BAY_Z - 206.0),
                                  (x + 44.0 + 64.0 * k, BAY_Y0 + 114.0, BAY_Z - 206.0),
                                  17.0), f"mlg_connector:{sfx}_{i}{k}", P.BRASS))
    # cable tray along the inboard wall
    out.append(style(_rect_xz(BAY_Y0 + 26.0, BAY_X0 + 60.0, BAY_X1 - 60.0,
                              BAY_Z - 330.0, BAY_Z - 300.0, 90.0),
                     f"mlg_cable_tray:{sfx}", P.ALUM_DARK))
    # roof runs
    for tag, y, r, col in (("p1", 826.0, 14.0, P.HYDRAULIC),
                           ("p2", 858.0, 14.0, P.HYDRAULIC),
                           ("p3", 1636.0, 12.0, P.HYDRAULIC),
                           ("loom", 1604.0, 19.0, P.WIRE_LOOM)):
        out.append(style(_tube([
            (BAY_X0 + 20.0, y, BAY_Z - 40.0),
            (BAY_X0 + 460.0, y + 26.0, BAY_Z - 60.0),
            ((BAY_X0 + BAY_X1) / 2.0, y + 8.0, BAY_Z - 46.0),
            (BAY_X1 - 400.0, y + 26.0, BAY_Z - 62.0),
            (BAY_X1 - 20.0, y, BAY_Z - 40.0),
        ], r), f"mlg_bay_line:{sfx}_{tag}", col))
    out.append(style(_tube([
        (10980.0, 850.0, BAY_Z - 50.0), (10760.0, 1180.0, BAY_Z - 70.0),
        (10600.0, 1500.0, BAY_Z - 58.0), (10360.0, BAY_Y1 - 34.0, BAY_Z - 70.0),
        (9760.0, BAY_Y1 - 34.0, BAY_Z - 78.0),
    ], 18.0), f"mlg_bay_loom:{sfx}_cross", P.WIRE_LOOM))
    out.append(style(_tube([
        (9440.0, 866.0, BAY_Z - 300.0), (9900.0, 850.0, BAY_Z - 312.0),
        (10500.0, 856.0, BAY_Z - 312.0), (10960.0, 870.0, BAY_Z - 300.0),
    ], 21.0), f"mlg_bay_loom:{sfx}_tray", P.WIRE_LOOM))
    for i, (x, y) in enumerate(((9700.0, 842.0), (10300.0, 850.0), (10900.0, 842.0),
                                (10520.0, 1620.0), (9980.0, 1620.0))):
        out.append(style(_seg((x, y, BAY_Z - 8.0), (x, y, BAY_Z - 66.0), 26.0, 20.0),
                         f"mlg_line_clip:{sfx}_{i}", P.ALUM_DARK))
    out.append(style(_seg((10480.0, 1540.0, -470.0), (10480.0, 1584.0, -470.0), 20.0),
                     f"mlg_prox_switch:{sfx}_brace", P.STEEL_DARK))
    out.append(style(_seg((10380.0, ARCH_Y - 130.0, BAY_Z - 60.0),
                          (10380.0, ARCH_Y - 90.0, BAY_Z - 60.0), 18.0),
                     f"mlg_prox_switch:{sfx}_uplock", P.STEEL_DARK))
    for i, (x, y) in enumerate(((10180.0, 1240.0), (10700.0, 1500.0))):
        out.append(style(_rect_xy(BAY_Z - 30.0, x, x + 190.0, y, y + 120.0, 6.0),
                         f"mlg_bay_placard:{sfx}_{i}", P.STENCIL))
    return out


# ---------------------------------------------------------------------------
# doors
# ---------------------------------------------------------------------------


_HINGE_Y = AP_Y0
_HINGE_Z = _skin((AP_X0 + AP_X1) / 2.0, AP_Y0) - 16.0
_DOOR_X0, _DOOR_X1 = AP_X0 - 24.0, AP_X1 + 24.0


def _hinged(shape, deg=DOOR_OPEN):
    """Swing a door body about the inboard hinge line (an axis along X)."""
    return (Location((0.0, _HINGE_Y, _HINGE_Z)) * Rot(-deg, 0.0, 0.0)
            * Location((0.0, -_HINGE_Y, -_HINGE_Z)) * shape)


def _door_pts(x_at, y0, y1, drop, n=7):
    """(y, z) section of a closed door lying on the belly, ``drop`` thick."""
    top = [(y0 + (y1 - y0) * i / (n - 1.0),) for i in range(n)]
    top = [(y, _skin(x_at, y) - 2.0) for (y,) in top]
    return top + [(y, z - drop) for y, z in reversed(top)]


def _main_door(sfx):
    """The big inboard-hinged bay door, ribbed inner face turned outboard."""
    out = []
    x0, x1, y0, y1 = _DOOR_X0, _DOOR_X1, AP_Y0, DOOR_Y1
    xm = (x0 + x1) / 2.0
    out.append(style(_hinged(_plate_yz(x0, _door_pts(xm, y0, y1, 14.0), x1 - x0)),
                     f"mlg_door_skin:{sfx}_main", P.GREY_LIGHT))
    out.append(style(_hinged(_plate_yz(x0 + 34.0,
                                       _door_pts(xm, y0 + 26.0, y1 - 26.0, -9.0),
                                       x1 - x0 - 68.0)),
                     f"mlg_door_liner:{sfx}_main", P.GEAR_WHITE))
    for i, x in enumerate((9520.0, 9780.0, 10040.0, 10300.0, 10560.0, 10820.0, 10970.0)):
        out.append(style(_hinged(_plate_yz(x - 13.0,
                                           _door_pts(xm, y0 + 20.0, y1 - 20.0, -58.0),
                                           26.0)),
                         f"mlg_door_rib:{sfx}_{i}", P.GEAR_WHITE))
    for i, y in enumerate((y0 + 140.0, (y0 + y1) / 2.0, y1 - 140.0)):
        z = _skin(xm, y) - 2.0
        out.append(style(_hinged(_rect_xz(y - 11.0, x0 + 40.0, x1 - 40.0,
                                          z + 8.0, z + 64.0, 22.0)),
                         f"mlg_door_stringer:{sfx}_{i}", P.GEAR_WHITE))
    for i, x in enumerate((9640.0, 10205.0, 10770.0)):
        out.append(style(_hinged(_rect_xz(y0 - 4.0, x - 62.0, x + 62.0,
                                          _HINGE_Z - 8.0, _HINGE_Z + 96.0, 48.0)),
                         f"mlg_door_hinge:{sfx}_{i}", P.ALUM_DARK))
    out.append(style(_seg((x0, _HINGE_Y, _HINGE_Z), (x1, _HINGE_Y, _HINGE_Z), 22.0),
                     f"mlg_door_hinge_pin:{sfx}", P.STEEL_DARK))
    for tag, x in (("fwd", x0 - 8.0), ("aft", x1 - 2.0)):
        out.append(style(_hinged(_plate_yz(x, _door_pts(xm, y0 + 6.0, y1 + 8.0, -8.0),
                                           10.0)),
                         f"mlg_door_seal:{sfx}_{tag}", P.RUBBER))
    for i, (x, y) in enumerate(((10000.0, y1 - 104.0), (10600.0, y0 + 160.0))):
        z = _skin(xm, y) - 2.0
        out.append(style(_hinged(_blk(x, x + 200.0, y - 62.0, y + 62.0, z + 6.0, z + 11.0)),
                         f"mlg_door_placard:{sfx}_{i}", P.STENCIL))
    # actuator: bay fitting -> lug standing off the open door
    lug_y, lug_x = y1 - 96.0, 10205.0
    lug_z = _skin(xm, lug_y) + 104.0
    out.append(style(_hinged(_rect_xz(lug_y - 16.0, lug_x - 56.0, lug_x + 56.0,
                                      _skin(xm, lug_y) - 2.0, lug_z, 32.0)),
                     f"mlg_door_lug:{sfx}", P.ALUM_DARK))
    rod_end = _hinged(Pos(lug_x, lug_y, lug_z - 26.0) * Sphere(1.0)).center()
    base = Vector(10205.0, BAY_Y0 + 140.0, BAY_Z - 108.0)
    mid = base + (rod_end - base) * 0.55
    out.append(style(_seg(base, mid, 40.0), f"mlg_door_actuator:{sfx}", P.ALUM_DARK))
    out.append(style(_seg(mid, rod_end, 21.0), f"mlg_door_act_rod:{sfx}", P.OLEO_CHROME))
    out.append(style(_seg(base + Vector(0, -48.0, 0), base + Vector(0, 48.0, 0), 24.0),
                     f"mlg_door_act_pin:{sfx}", P.STEEL_DARK))
    out.append(style(_tube([
        (10900.0, BAY_Y0 + 40.0, BAY_Z - 66.0),
        (10520.0, BAY_Y0 + 110.0, BAY_Z - 92.0),
        (base.X + 30.0, base.Y, base.Z + 28.0)], 13.0),
        f"mlg_door_act_line:{sfx}", P.HYDRAULIC))
    return out


# outer face of the fairing door in (y, z): a shallow curve hugging the strut
_LEGDOOR = ((1596.0, -676.0), (1570.0, -800.0), (1538.0, -930.0), (1516.0, -1036.0))


def _leg_door(sfx):
    """Short fairing door bolted to the strut; it rides down with the leg.

    Deliberately short.  A full-length strut door is the single easiest way to
    lose this gear: it stands outboard of everything and blanks the leg, the
    brace and the scissors from every side view.
    """
    out = []
    x0, x1 = 10382.0, 10884.0
    outer = list(_LEGDOOR)
    out.append(style(_plate_yz(x0, outer + [(y - 15.0, z) for y, z in reversed(outer)],
                               x1 - x0), f"mlg_leg_door_skin:{sfx}", P.GREY_LIGHT))
    out.append(style(_plate_yz(x0 + 28.0,
                               [(y - 15.0, z) for y, z in outer]
                               + [(y - 9.0, z) for y, z in reversed(outer)],
                               x1 - x0 - 56.0),
                     f"mlg_leg_door_liner:{sfx}", P.GEAR_WHITE))
    for i, x in enumerate((10440.0, 10630.0, 10820.0)):
        out.append(style(_plate_yz(x - 12.0,
                                   [(y - 15.0, z) for y, z in outer]
                                   + [(y - 58.0, z) for y, z in reversed(outer)], 24.0),
                         f"mlg_leg_door_rib:{sfx}_{i}", P.GEAR_WHITE))
    for i, (t, k) in enumerate(((0.36, 1), (0.62, 3))):
        p = _leg_off(t, out=70.0)
        q = Vector(p.X, _LEGDOOR[k][0] - 36.0, _LEGDOOR[k][1])
        out.append(style(_seg(p, q, 26.0, 20.0), f"mlg_leg_door_arm:{sfx}_{i}", P.ALUM_DARK))
    return out


# ---------------------------------------------------------------------------
# assembly
# ---------------------------------------------------------------------------


def _leaves(sfx):
    """Every leaf of ONE main gear, built in PORT (+Y) coordinates."""
    kids = []
    kids += _bay_shell(sfx)
    kids += _bay_frames(sfx)
    kids += _bay_systems(sfx)
    kids += _oleo(sfx)
    kids += _torque_links(sfx)
    kids += _side_brace(sfx)
    kids += _retract_actuator(sfx)
    kids += _leg_plumbing(sfx)
    kids += _tyre(1, sfx)
    kids += _wheel(1, sfx)
    kids += _brakes(1, sfx)
    kids += _main_door(sfx)
    kids += _leg_door(sfx)
    return kids


def _mirrored(shape):
    m = mirror(shape, about=Plane.XZ)
    m.label = shape.label
    m.color = shape.color
    return m


def _unit(side):
    sfx = "port" if side > 0 else "stbd"
    kids = _leaves(sfx)
    if side < 0:
        kids = [_mirrored(k) for k in kids]
    return group("main_gear_unit", kids)


def build():
    """Both main gear: legs, wheels, brakes, doors and bays, on the deck."""
    return stance(group("main_gear", mirror_pair(_unit, "mlg")))


if __name__ == "__main__":
    import time

    t0 = time.time()
    part = build()
    bb = part.bounding_box()
    print(f"build {time.time() - t0:5.2f}s  leaves/side "
          f"{len(list(part.children[0].children))}")
    print(f"world bbox  x {bb.min.X:9.1f}..{bb.max.X:9.1f}  "
          f"y {bb.min.Y:9.1f}..{bb.max.Y:9.1f}  z {bb.min.Z:9.3f}..{bb.max.Z:9.3f}")
