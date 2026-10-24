"""F1 concept car — a modern ground-effect Formula 1 single-seater.

An original design. No team, livery, logo or sponsor marks. Three materials
only: carbon, exposed metal, and one vermillion accent.

Coordinates, package dimensions, suspension hardpoints, the DRS four-bar and
the material palette all live in `lib/spec.py`; the shared surface vocabulary
(airfoil family, blade family, body lofts) lives in `lib/surfaces.py`. Read
those two before changing anything here. Every child below is a function in
its own file under `src/` (`front_wing.py`, `corner_fl.py`, ...), built from
`lib/`; the car's body calls them through its `@memo` stages (`stages.py`, and
the four children that are stages of their own: `power_unit`, `drivetrain`,
`suspension_rear`, `details`) and holds each, labelled with its name, in this
order:

  front_wing        rear_wing
  nose              drs_flap        <- turns (drs_flap joint)
  monocoque         drs_actuator    <- turns (drs_crank joint)
  halo              beam_wing
  cockpit           suspension_front
  sidepod_left      suspension_rear
  sidepod_right     corner_fl       <- turns (steer_left joint)
  engine_cover      corner_fr       <- turns (steer_right joint)
  airbox            track_rod_left  <- swivels on the rack (ball joint)
  floor             track_rod_right <- swivels on the rack (ball joint)
  diffuser          corner_rl
  cooling           corner_rr
  power_unit        steering_rack   <- slides (rack joint)
  drivetrain        details

Every child but the monocoque also moves apart along its own direction, and the
power unit's twelve systems in it (`eng_*`): the old teardown choreography, as GLB
animations (`showcase`, `teardown`, `engine`). The car is one model, `f1`, and its
GLB, exported on demand, carries those three and the two motions, `drs` and
`steering`, as clips.
"""

from __future__ import annotations

from cadgen import model
from cadgen.ap242 import configuration_sequence, mechanism_state
from cadgen.gltf import animation

import math

import build123d as bd

from details import details
from drivetrain import drivetrain
from lib import spec
from power_unit import power_unit
from stages import (corners, engine_bodywork, front_end, front_suspension, rear_aero, sidepods,
                    survival_cell, underbody)
from suspension_rear import suspension_rear

# The car's children, in the order it holds them.
CHILDREN = (
    "front_wing", "nose", "monocoque", "halo", "cockpit", "sidepod_left", "sidepod_right",
    "engine_cover", "airbox", "floor", "diffuser", "cooling", "power_unit", "drivetrain",
    "rear_wing", "drs_flap", "drs_actuator", "beam_wing", "suspension_front", "suspension_rear",
    "corner_fl", "corner_fr", "track_rod_left", "track_rod_right", "corner_rl", "corner_rr",
    "steering_rack", "details",
)


# ---------------------------------------------------------------------------
# Kinematics: the DRS and the steering.
#
# Both mechanisms are CLOSED LOOPS: the DRS is a planar four-bar, and the
# steering solves each wheel against a fixed-length track rod. The joints below
# are the loops' tree -- every moving child on a joint to a part that holds it
# -- and the closing links are left unjointed; the motions and configurations
# solve each loop in Python, from the `lib/spec.py` hardpoints the geometry is
# built from, and set every joint of it. Each joint is authored where its parts
# stand as built and paired by its label, so no build moves a child.
#
# WHAT STEERING MOVES, AND WHY IT IS NOT EVERYTHING. The upright, wheel,
# brake, track rod and rack move. The pushrods and rockers deliberately DO
# NOT: both front ball joints sit exactly on the steer axis (spec.F_LOWER_BALL
# and spec.F_UPPER_BALL define it), which is precisely why steering does not
# disturb the wishbones or anything inboard of them.
# ---------------------------------------------------------------------------

# Rack shift at full lock, measured with the solve below: the inside wheel
# reaches spec.MAX_STEER_DEG here (the outside one, 20.5 deg).
_MAX_RACK_TRAVEL = 55.4
_Y_AXIS = (0.0, 1.0, 0.0)
# Each track rod's ball swivels this far about each axis on the rack.
_BALL_RANGE = 10.0


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _scale(a, k: float):
    return (a[0] * k, a[1] * k, a[2] * k)


def _dot(a, b) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _unit(v):
    n = math.hypot(*v) or 1.0
    return (v[0] / n, v[1] / n, v[2] / n)


def _clamp(v: float, lo: float, hi: float) -> float:
    return min(max(v, lo), hi)


def _rotation(axis, deg: float):
    """The 3x3 rotation of `deg` about `axis` (right-handed), as rows."""
    a = math.radians(deg)
    x, y, z = _unit(axis)
    c, s = math.cos(a), math.sin(a)
    k = 1.0 - c
    return ((c + x * x * k, x * y * k - z * s, x * z * k + y * s),
            (y * x * k + z * s, c + y * y * k, y * z * k - x * s),
            (z * x * k - y * s, z * y * k + x * s, c + z * z * k))


def _rotate_about_axis(p, origin, axis, deg: float):
    """Rodrigues rotation of `p` about the axis through `origin` along `axis`."""
    r = _rotation(axis, deg)
    v = _sub(p, origin)
    return _add(origin, tuple(_dot(row, v) for row in r))


def _ball_angles(r):
    """A ball joint's three angles for the rotation `r`: build123d's intrinsic X-Y-Z
    turns, the frame's own axes, as the document reads a spherical pair."""
    pitch = math.degrees(math.asin(_clamp(r[0][2], -1.0, 1.0)))
    roll = math.degrees(math.atan2(-r[1][2], r[2][2]))
    yaw = math.degrees(math.atan2(-r[0][1], r[0][0]))
    return (roll, pitch, yaw)


def _pingpong(u: float) -> float:
    """Symmetric there-and-back on a raised cosine, so a loop closes exactly."""
    return 0.5 * (1.0 - math.cos(math.tau * (u % 1.0)))


# ---- DRS -------------------------------------------------------------------
# The four-bar works in the y = spec.DRS_LINK_Y plane, so its points are (x, z).


def _xz(p):
    return (p[0], p[2])


_DRS_PIVOT = _xz(spec.DRS_PIVOT)
_DRS_CRANK_PIVOT = _xz(spec.DRS_CRANK_PIVOT)
_LUG_CLOSED = _xz(spec.DRS_LUG_CLOSED)
_CRANK_END_CLOSED = _xz(spec.DRS_CRANK_END_CLOSED)
_DRS_TRAVEL_DEG = spec.RW_FLAP_INCIDENCE_OPEN_DEG - spec.RW_FLAP_INCIDENCE_CLOSED_DEG  # -64


def _rot_incidence(p, pivot, deg: float):
    """Rotate an (x, z) point about a pivot; +deg lifts a trailing edge."""
    a = math.radians(deg)
    ca, sa = math.cos(a), math.sin(a)
    dx, dz = p[0] - pivot[0], p[1] - pivot[1]
    return (pivot[0] + dx * ca + dz * sa, pivot[1] - dx * sa + dz * ca)


def _solve_drs(t: float) -> tuple[float, float]:
    """The DRS four-bar at normalized travel `t` (0 shut, 1 fully open): the
    flap's turn and the crank's turn from shut, in degrees, each right-handed
    about +Y (the joints' axis).

    The circle-circle solve has two roots; we lock to the branch that
    reproduces the closed pose so the linkage never snaps through.
    """
    flap_deg = _DRS_TRAVEL_DEG * _clamp(t, 0.0, 1.0)
    if flap_deg == 0:
        # Shut is the modeled pose, exactly: the solve below reproduces it only
        # to rounding.
        return 0.0, 0.0
    lug = _rot_incidence(_LUG_CLOSED, _DRS_PIVOT, flap_deg)

    cx, cz = _DRS_CRANK_PIVOT
    dx, dz = lug[0] - cx, lug[1] - cz
    d = math.hypot(dx, dz)
    r, link = spec.DRS_CRANK_R, spec.DRS_LINK_L

    end = _CRANK_END_CLOSED
    if abs(r - link) <= d <= r + link and d > 1e-9:
        a = (r * r - link * link + d * d) / (2.0 * d)
        h = math.sqrt(max(r * r - a * a, 0.0))
        mx, mz = cx + a * dx / d, cz + a * dz / d
        s1 = (mx - h * dz / d, mz + h * dx / d)
        s2 = (mx + h * dz / d, mz - h * dx / d)
        # branch lock: at t = 0 this must reproduce the closed crank end
        end = s1 if math.dist(s1, _CRANK_END_CLOSED) <= math.dist(s2, _CRANK_END_CLOSED) else s2

    # The crank end's angle is measured from +X toward +Z, which is a turn about
    # -Y: the joint's turn about +Y is its negative.
    crank_deg = math.degrees(math.atan2(end[1] - cz, end[0] - cx))
    return flap_deg, spec.DRS_CRANK_ANGLE_CLOSED_DEG - crank_deg


def _drs_pose(t: float) -> dict:
    flap, crank = _solve_drs(t)
    return {"drs_flap": flap, "drs_crank": crank}


# ---- steering --------------------------------------------------------------


def _on_side(p, side: int):
    """A hardpoint stated for the left side, on `side` (+1 left, -1 right)."""
    return p if side > 0 else (p[0], -p[1], p[2])


def _steer_axis(side: int):
    """Steer-axis origin and direction for one side."""
    lower = _on_side(spec.F_LOWER_BALL, side)
    return lower, _unit(_sub(_on_side(spec.F_UPPER_BALL, side), lower))


_TRACK_ROD_L = math.dist(spec.F_TRACKROD_OUT, spec.F_RACK_END)


def _solve_steer_angle(side: int, d: float) -> float:
    """Given a rack displacement `d` (mm, +y), solve ONE wheel's steer angle.

    The track rod is a fixed-length link between the rack end (which translates
    with the rack) and the steering-arm ball (which swings about the steer axis),
    so the angle is the root of |P(theta) - rack_end(d)| = L. Solved by bisection
    on a bracket around zero — Newton is unnecessary and bisection cannot jump
    branches, which matters because the far root folds the upright over.
    """
    if d == 0:
        return 0.0  # rack centred: the modeled pose, exactly (see _solve_drs)
    origin, axis = _steer_axis(side)
    arm = _on_side(spec.F_TRACKROD_OUT, side)
    rest = _on_side(spec.F_RACK_END, side)
    rack = (rest[0], rest[1] + d, rest[2])

    def err(deg: float) -> float:
        return math.dist(_rotate_about_axis(arm, origin, axis, deg), rack) - _TRACK_ROD_L

    lo, hi = -34.0, 34.0
    flo, fhi = err(lo), err(hi)
    if flo * fhi > 0:
        # No sign change in the bracket: clamp to whichever end is closer
        # rather than returning a bogus root.
        return lo if abs(flo) < abs(fhi) else hi
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        fm = err(mid)
        if flo * fm <= 0:
            hi = mid
        else:
            lo, flo = mid, fm
    return 0.5 * (lo + hi)


def _track_rod_ball(side: int, rack_dy: float, deg: float):
    """The track rod's swivel on the rack as its ball joint's angles: the turn that
    carries the rod from (rack end, arm ball) at rest to where the rack and the
    upright put them. Exact whenever the two lengths match, which the solve
    guarantees."""
    rack_end, arm = _on_side(spec.F_RACK_END, side), _on_side(spec.F_TRACKROD_OUT, side)
    origin, axis = _steer_axis(side)
    moved_end = (rack_end[0], rack_end[1] + rack_dy, rack_end[2])
    moved_arm = _rotate_about_axis(arm, origin, axis, deg)
    n0, n1 = _unit(_sub(arm, rack_end)), _unit(_sub(moved_arm, moved_end))
    turn = _cross(n0, n1)
    s = math.hypot(*turn)
    if s <= 1e-12:
        return (0.0, 0.0, 0.0)
    return _ball_angles(_rotation(turn, math.degrees(math.atan2(s, _clamp(_dot(n0, n1), -1.0, 1.0)))))


def _steer_pose(steer: float) -> dict:
    """The steering at `steer` (-1 full right lock .. 1 full left lock).

    Positive steers LEFT (the car's +Y side is the inside of the turn). The
    rack is one bar, so both wheels take the same shift and each wheel's
    angle is solved against its OWN track rod — the two sides differ
    slightly, which is where the anti-Ackermann comes from.
    """
    rack_dy = _clamp(steer, -1.0, 1.0) * _MAX_RACK_TRAVEL
    pose = {"rack": rack_dy}
    for side, wheel, rod in ((1, "steer_left", "track_rod_left"), (-1, "steer_right", "track_rod_right")):
        deg = _solve_steer_angle(side, rack_dy)
        pose[wheel] = deg
        pose[rod] = _track_rod_ball(side, rack_dy, deg)
    return pose


# ---- the joints -------------------------------------------------------------


def _revolute(label, fixed, moving, point, direction, limits):
    """A revolute joint on `fixed` and its rigid mate on `moving`, coincident as built."""
    bd.RevoluteJoint(label, fixed, axis=bd.Axis(point, direction), angular_range=limits)
    bd.RigidJoint(label, moving, bd.Plane(origin=point, z_dir=direction).location)


def _joints(parts):
    """The DRS and steering joints on the car's children, by name."""
    # DRS: the flap turns about its pivot on the endplates, the crank (and with it
    # the whole linkage) about the crank pivot, both along Y.
    flap_open, crank_open = _solve_drs(1.0)
    _revolute("drs_flap", parts["rear_wing"], parts["drs_flap"], spec.DRS_PIVOT, _Y_AXIS, (flap_open, 0.0))
    _revolute("drs_crank", parts["rear_wing"], parts["drs_actuator"], spec.DRS_CRANK_PIVOT, _Y_AXIS,
              (0.0, crank_open))

    # Steering: each corner turns about its steer axis on the wishbones; the rack
    # slides across the tub; each track rod swivels on its ball at the rack end.
    for side, wheel, corner, rod in ((1, "steer_left", "corner_fl", "track_rod_left"),
                                     (-1, "steer_right", "corner_fr", "track_rod_right")):
        origin, axis = _steer_axis(side)
        lock = sorted(_solve_steer_angle(side, travel) for travel in (-spec.F_RACK_TRAVEL, spec.F_RACK_TRAVEL))
        _revolute(wheel, parts["suspension_front"], parts[corner], origin, axis, tuple(lock))
        ball = bd.Location(_on_side(spec.F_RACK_END, side))
        bd.BallJoint(rod, parts["steering_rack"], ball, angular_range=((-_BALL_RANGE, _BALL_RANGE),) * 3)
        bd.RigidJoint(rod, parts[rod], ball)
    rack_axis = bd.Axis((spec.F_RACK_X, 0.0, spec.F_RACK_Z), _Y_AXIS)
    bd.LinearJoint("rack", parts["monocoque"], axis=rack_axis,
                   linear_range=(-spec.F_RACK_TRAVEL, spec.F_RACK_TRAVEL))
    bd.RigidJoint("rack", parts["steering_rack"], bd.Location(rack_axis.position))


# ---------------------------------------------------------------------------
# The teardown: the old `showcase`, `teardown` and `engine` clips.
#
# Each child but the monocoque translates along its own direction by its
# distance times an eased TIME WINDOW on the explode clock. Windows overlap only
# slightly and run in a deliberate order -- bodywork, then cooling and rear aero,
# then running gear, then power unit and drivetrain last -- which is what keeps
# the teardown readable. Directions are car coordinates (+X forward, +Y left,
# +Z up), normalized before use. PURE TRANSLATION: a rotating subject and a
# rotating part fight the one thing the viewer is meant to be reading. Distances
# are sized so parts clear each other in PROJECTION, not just in space.
#
# The monocoque never moves. The teardown is a GLB animation (`cadgen.gltf`), never
# the mechanism's: each child, a sibling of every other in the car's tree, moves by its
# own translation alone, so a child holding a joint for another (rear_wing,
# suspension_front, steering_rack) drags nothing by its explode, and one hanging on a
# joint (drs_flap, the front corners, the track rods) moves by its own vector.
# ---------------------------------------------------------------------------

_BODYWORK = (
    # (child, direction, distance mm, window on the explode clock). Both covers are
    # pushed off the centreline: the column straight above the car is reserved for
    # the power unit, which rises into it as the hero.
    ("engine_cover", (-0.22, -0.72, 0.72), 1150.0, (0.0, 0.3)),
    ("airbox", (0.18, -0.78, 0.7), 1180.0, (0.03, 0.33)),
    ("sidepod_left", (0.0, 1.0, 0.34), 1320.0, (0.05, 0.33)),
    ("sidepod_right", (0.0, -1.0, 0.34), 1320.0, (0.05, 0.33)),
    ("floor", (0.0, 0.0, -1.0), 980.0, (0.08, 0.33)),
    ("diffuser", (-0.45, 0.0, -1.0), 1020.0, (0.1, 0.33)),
)
_INTERNALS = (
    ("cooling", (0.0, 1.0, 0.55), 1860.0, (0.33, 0.52)),
    ("rear_wing", (-0.34, 0.0, 1.0), 1160.0, (0.33, 0.52)),
    ("drs_flap", (-0.34, 0.0, 1.0), 1420.0, (0.33, 0.52)),
    ("drs_actuator", (-0.34, 0.0, 1.0), 1280.0, (0.33, 0.52)),
    ("beam_wing", (-1.0, 0.0, 0.25), 980.0, (0.36, 0.55)),
    ("front_wing", (1.0, 0.0, -0.08), 1420.0, (0.36, 0.55)),
    ("nose", (1.0, 0.0, 0.22), 1680.0, (0.38, 0.58)),
    ("corner_fl", (0.0, 1.0, 0.05), 1180.0, (0.5, 0.72)),
    ("corner_fr", (0.0, -1.0, 0.05), 1180.0, (0.5, 0.72)),
    ("corner_rl", (0.0, 1.0, 0.05), 1180.0, (0.5, 0.72)),
    ("corner_rr", (0.0, -1.0, 0.05), 1180.0, (0.5, 0.72)),
    ("track_rod_left", (0.0, 1.0, 0.18), 820.0, (0.53, 0.74)),
    ("track_rod_right", (0.0, -1.0, 0.18), 820.0, (0.53, 0.74)),
    ("suspension_front", (0.35, 0.0, 0.85), 880.0, (0.55, 0.76)),
    ("suspension_rear", (-0.35, 0.0, 0.85), 880.0, (0.55, 0.76)),
    ("steering_rack", (1.0, 0.0, 0.2), 980.0, (0.57, 0.78)),
    ("details", (0.0, 1.0, 0.62), 1320.0, (0.62, 0.84)),
    ("halo", (0.42, 0.55, 0.68), 940.0, (0.62, 0.82)),
    ("cockpit", (0.12, 0.85, 0.62), 1180.0, (0.64, 0.86)),
    ("drivetrain", (-1.0, 0.0, 0.32), 1560.0, (0.7, 0.92)),
    # THE HERO: it lifts straight up and out of the car, early, into the column
    # everything else was pushed clear of, then takes itself apart.
    ("power_unit", (0.0, 0.0, 1.0), 1080.0, (0.08, 0.34)),
)
_EXPLODE = _BODYWORK + _INTERNALS

# The engine sub-explode: the power unit's 100 leaves collapsed into 12 systems,
# addressed BY LABEL, each moving along its own direction by its distance times
# the engine clock, on top of the power unit's own explode. The crankcase, sump,
# front and gearbox faces, belt ribs and main webs never move in it.
_SIDES = ("left", "right")


def _seq(base: str, n: int) -> list[str]:
    return [f"{base}:{i + 1}" for i in range(n)]


_ENGINE_GROUPS = (
    ("eng_induction", ["plenum", "charge_pipe", "charge_pipe_clamp", "airbox_trunk",
                       *(f"trumpet:{side}:{i}" for side in _SIDES for i in (1, 2, 3))], (0.0, 0.0, 1.0), 760.0),
    ("eng_head_left", ["cylinder_head:left", "cam_cover:left", "fuel_rail:left", "head_joint_rail:left",
                       *(f"coil_pack:left:{i}" for i in (1, 2, 3))], (0.0, 1.0, 0.5), 620.0),
    ("eng_head_right", ["cylinder_head:right", "cam_cover:right", "fuel_rail:right", "head_joint_rail:right",
                        *(f"coil_pack:right:{i}" for i in (1, 2, 3))], (0.0, -1.0, 0.5), 620.0),
    # split turbo: compressor forward, turbine aft -- the layout reads instantly
    ("eng_compressor", ["compressor_volute", "compressor_housing"], (1.0, 0.0, 0.2), 620.0),
    ("eng_turbine", ["turbine_volute", "turbine_housing", "turbine_inlet"], (-1.0, 0.0, 0.2), 620.0),
    ("eng_mguh", ["turbo_shaft", "mgu_h", "mgu_h_gland", "mgu_h_cable"], (0.0, 0.0, 1.0), 380.0),
    ("eng_exhaust_left", [*(f"exhaust_primary:left:{i}" for i in (1, 2, 3)), "collector:left",
                          "heat_shield:collector"], (-0.45, 1.0, 0.45), 760.0),
    ("eng_exhaust_right", [*(f"exhaust_primary:right:{i}" for i in (1, 2, 3)), "collector:right"],
     (-0.45, -1.0, 0.45), 760.0),
    ("eng_tailpipe", ["collector_merge", "tailpipe", "tailpipe_tip", "heat_shield:tailpipe", "wastegate_body",
                      "wastegate_flange", "wastegate_pipe", "wastegate_tip"], (-1.0, 0.0, 0.15), 900.0),
    ("eng_mguk", ["mgu_k", "mgu_k_ring", "mgu_k_drive_housing", *_seq("mgu_k_cable", 2)], (0.35, 1.0, -0.3), 700.0),
    ("eng_ers", ["ers_battery_case", "ers_battery_lid", "ers_terminal_block", *_seq("ers_bracket", 4),
                 *_seq("ers_bus_bar", 6), *_seq("ers_coolant", 2)], (1.0, 0.0, -0.35), 860.0),
    ("eng_ancillaries", ["water_pump", "oil_pump", "oil_tank", "ecu_box", "ecu_connector", "water_feed",
                         "water_return", "oil_feed", "oil_return", "fuel_line", "fuel_crossover",
                         *_seq("ecu_pin", 3), *_seq("line_bracket", 4)], (0.0, -1.0, -0.28), 780.0),
)


def _smoothstep(u: float) -> float:
    u = _clamp(u, 0.0, 1.0)
    return u * u * (3.0 - 2.0 * u)


def _window(a: float, b: float, u: float) -> float:
    """Eased window: 0 before `a`, 1 after `b`, smooth between."""
    return _smoothstep((u - a) / max(b - a, 1e-6))


def _teardown_pose(explode: float = 0.0, engine: float = 0.0) -> dict:
    """Every group's travel along its direction (mm) at an explode clock and an engine clock,
    each 0..1, by the group's name (`explode_<child>`, `eng_*`)."""
    pose = {f"explode_{child}": distance * _window(a, b, explode)
            for child, _direction, distance, (a, b) in _EXPLODE}
    for group, _labels, _direction, distance in _ENGINE_GROUPS:
        pose[group] = distance * _clamp(engine, 0.0, 1.0)
    return pose


def _showcase_at(u: float) -> dict:
    """The showcase's one loop-closed timeline (22.5 s): hold assembled to 1.5 s, the car
    opens to 10.5 s, a short handover, the engine opens 11.2-14.8 s, the money frame holds
    to 16.3 s, the engine closes to 18.8 s, the car to 22.3 s, and it settles. Both clocks
    are exactly 0 at u = 0 and u = 1; each switch point sits inside a plateau where both
    branches are 1, so neither steps."""
    u = _clamp(u, 0.0, 1.0)
    explode = _window(0.067, 0.467, u) if u < 0.7 else 1.0 - _window(0.836, 0.991, u)
    engine = _window(0.498, 0.658, u) if u < 0.69 else 1.0 - _window(0.724, 0.836, u)
    return _teardown_pose(explode=_clamp(explode, 0.0, 1.0), engine=_clamp(engine, 0.0, 1.0))


# Each group's references in the car's tree, from its root, and its unit direction: a child
# by its label, an engine system by its leaves' paths in the power unit.
_CAR = "f1_concept_car"
_GROUPS = {**{f"explode_{child}": ([f"{_CAR}/{child}"], _unit(direction)) for child, direction, _d, _w in _EXPLODE},
           **{group: ([f"{_CAR}/power_unit/{label}" for label in labels], _unit(direction))
              for group, labels, direction, _d in _ENGINE_GROUPS}}
_KEY_STEP = 0.05  # s between the sampled keys of an explode's channels


def _teardown_animation(car, name: str, duration: float, pose_at) -> None:
    """A GLB animation of the teardown: each group's translation along its direction by
    ``pose_at(t)``'s travel, sampled every ``_KEY_STEP`` as LINEAR keys (a key whose
    neighbours hold its value is dropped), so the old clip's eases play as they were."""
    show = animation(car, name, duration=duration)
    count = round(duration / _KEY_STEP)
    times = [duration * i / count for i in range(count + 1)]
    poses = [pose_at(t) for t in times]
    for group, (refs, unit) in _GROUPS.items():
        values = [pose[group] for pose in poses]
        if not any(values):
            continue
        kept = [i for i in range(len(times))
                if i in (0, len(times) - 1) or not values[i - 1] == values[i] == values[i + 1]]
        keys = [(times[i], tuple(c * values[i] for c in unit)) for i in kept]
        show.channel(refs, path="translation", keys=keys, interpolation="LINEAR")


@model
def f1():
    parts = {**front_end(), **survival_cell(), **sidepods(), **engine_bodywork(), **underbody(),
             "power_unit": power_unit(), "drivetrain": drivetrain(), **rear_aero(), **front_suspension(),
             "suspension_rear": suspension_rear(), **corners(), "details": details()}
    for name, part in parts.items():
        part.label = name
    _joints(parts)
    car = bd.Compound(children=[parts[name] for name in CHILDREN], label=_CAR)
    mechanism_state(car, "drs_open", **_drs_pose(1.0))
    mechanism_state(car, "full_lock_left", **_steer_pose(1.0))
    mechanism_state(car, "full_lock_right", **_steer_pose(-1.0))
    # The exploded view and nothing else, one loop-closed timeline: the car opens, then
    # the engine, and both close again, 22.5 s: a GLB animation, as the teardowns below.
    _teardown_animation(car, "showcase", 22.5, lambda t: _showcase_at((t / 22.5) % 1.0))
    # The one mechanism you can show while the car is still whole: open and shut, 4 s.
    configuration_sequence(car, "drs", lambda t: _drs_pose(_pingpong(t / 4.0)), duration=4)
    # Left, through centre, to right and back — the car "looking around", 6 s.
    configuration_sequence(car, "steering", lambda t: _steer_pose(math.sin(math.tau * t / 6.0)), duration=6)
    # The car apart and back together, 12 s; the engine apart and back, 8 s.
    _teardown_animation(car, "teardown", 12, lambda t: _teardown_pose(explode=_pingpong(t / 12.0)))
    _teardown_animation(car, "engine", 8, lambda t: _teardown_pose(engine=_pingpong(t / 8.0)))
    return car


if __name__ == "__main__":
    f1()
