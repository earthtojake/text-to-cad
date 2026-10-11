"""F1 concept car — a modern ground-effect Formula 1 single-seater.

An original design. No team, livery, logo or sponsor marks. Three materials
only: carbon, exposed metal, and one vermillion accent.

Coordinates, package dimensions, suspension hardpoints, the DRS four-bar and
the material palette all live in `lib/spec.py`; the shared surface vocabulary
(airfoil family, blade family, body lofts) lives in `lib/surfaces.py`. Read
those two before changing anything here. Every child below is its own model
file under `src/` (`front_wing.py`, `corner_fl.py`, ...), built from `lib/`
and composed here by CALLING it.

--------------------------------------------------------------------------
OCCURRENCE ORDER IS FROZEN
--------------------------------------------------------------------------
The `ANIMATION` clips address children as `#o1.N` in the order below. Do not
reorder, insert or remove a child without updating their occurrence table
(`_F`) in the same change.

  #o1.1   front_wing        #o1.15  rear_wing
  #o1.2   nose              #o1.16  drs_flap        <- rotates (DRS)
  #o1.3   monocoque         #o1.17  drs_actuator    <- four-bar (DRS)
  #o1.4   halo              #o1.18  beam_wing
  #o1.5   cockpit           #o1.19  suspension_front
  #o1.6   sidepod_left      #o1.20  suspension_rear
  #o1.7   sidepod_right     #o1.21  corner_fl       <- rotates (steering)
  #o1.8   engine_cover      #o1.22  corner_fr       <- rotates (steering)
  #o1.9   airbox            #o1.23  track_rod_left  <- re-aimed (steering)
  #o1.10  floor             #o1.24  track_rod_right <- re-aimed (steering)
  #o1.11  diffuser          #o1.25  corner_rl
  #o1.12  cooling           #o1.26  corner_rr
  #o1.13  power_unit        #o1.27  steering_rack   <- translates (steering)
  #o1.14  drivetrain        #o1.28  details
"""

from __future__ import annotations

import math

import cadgen
from cadgen import build123d as bd
from cadgen import step
from cadgen.assembly import AssemblyHelper

from airbox import airbox
from beam_wing import beam_wing
from cockpit import cockpit
from cooling import cooling
from corner_fl import corner_fl
from corner_fr import corner_fr
from corner_rl import corner_rl
from corner_rr import corner_rr
from details import details
from diffuser import diffuser
from drivetrain import drivetrain
from drs_actuator import drs_actuator
from drs_flap import drs_flap
from engine_cover import engine_cover
from floor import floor
from front_wing import front_wing
from halo import halo
from lib import spec
from monocoque import monocoque
from nose import nose
from power_unit import power_unit
from rear_wing import rear_wing
from sidepod_left import sidepod_left
from sidepod_right import sidepod_right
from steering_rack import steering_rack
from suspension_front import suspension_front
from suspension_rear import suspension_rear
from track_rod_left import track_rod_left
from track_rod_right import track_rod_right


def assemble() -> bd.Compound:
    """Every child is a sibling MODEL under `src/`, added in the frozen order.

    Calling a model inside this body submits its build (if stale) to the pool
    and returns at once; the car links each child's tree, so a part edit is
    picked up by rerunning this script and nothing else is rebuilt.
    """
    asm = AssemblyHelper("f1_concept_car")
    asm.add(front_wing(), "front_wing")
    asm.add(nose(), "nose")
    asm.add(monocoque(), "monocoque")
    asm.add(halo(), "halo")
    asm.add(cockpit(), "cockpit")
    asm.add(sidepod_left(), "sidepod_left")
    asm.add(sidepod_right(), "sidepod_right")
    asm.add(engine_cover(), "engine_cover")
    asm.add(airbox(), "airbox")
    asm.add(floor(), "floor")
    asm.add(diffuser(), "diffuser")
    asm.add(cooling(), "cooling")
    asm.add(power_unit(), "power_unit")
    asm.add(drivetrain(), "drivetrain")
    asm.add(rear_wing(), "rear_wing")
    asm.add(drs_flap(), "drs_flap")
    asm.add(drs_actuator(), "drs_actuator")
    asm.add(beam_wing(), "beam_wing")
    asm.add(suspension_front(), "suspension_front")
    asm.add(suspension_rear(), "suspension_rear")
    asm.add(corner_fl(), "corner_fl")
    asm.add(corner_fr(), "corner_fr")
    asm.add(track_rod_left(), "track_rod_left")
    asm.add(track_rod_right(), "track_rod_right")
    asm.add(corner_rl(), "corner_rl")
    asm.add(corner_rr(), "corner_rr")
    asm.add(steering_rack(), "steering_rack")
    asm.add(details(), "details")
    return asm.build()


# ---------------------------------------------------------------------------
# Animation: clips sampled to keyframes when the car builds.
#
# No `kinematics=`: both of this car's mechanisms are CLOSED LOOPS. The DRS is
# a planar four-bar and the steering solves each wheel against a fixed-length
# track rod, and typed mates evaluate pure forward kinematics on a TREE — a
# loop needs a solver. Both solves therefore live in the clips below, which is
# where the teardown belongs anyway. Every hardpoint and pivot they use is the
# `lib/spec.py` constant the geometry is built from.
#
# WHAT STEERING MOVES, AND WHY IT IS NOT EVERYTHING. The upright, wheel,
# brake, track rod and rack move. The pushrods and rockers deliberately DO
# NOT: both front ball joints sit exactly on the steer axis (spec.F_LOWER_BALL
# and spec.F_UPPER_BALL define it), which is precisely why steering does not
# disturb the wishbones or anything inboard of them. That is the real
# geometry — animating the rockers would look busier and be wrong.
# ---------------------------------------------------------------------------

# Rack shift at full lock, measured with the solve below: the inside wheel
# reaches spec.MAX_STEER_DEG here (the outside one, 20.5 deg).
_MAX_RACK_TRAVEL = 55.4
_Y_AXIS = (0.0, 1.0, 0.0)


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


def _ramp(a: float, b: float, u: float) -> float:
    """Eased window: 0 before `a`, 1 after `b`, smooth between."""
    return spec.smoothstep((u - a) / max(b - a, 1e-6))


def _rotate_about_axis(p, origin, axis, deg: float):
    """Rodrigues rotation of `p` about the axis through `origin` along `axis`."""
    a = math.radians(deg)
    k = _unit(axis)
    v = _sub(p, origin)
    c, s = math.cos(a), math.sin(a)
    return _add(origin, _add(_add(_scale(v, c), _scale(_cross(k, v), s)), _scale(k, _dot(k, v) * (1.0 - c))))


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
    flap's turn and the crank's turn from shut, in degrees.

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

    crank_deg = math.degrees(math.atan2(end[1] - cz, end[0] - cx))
    return flap_deg, crank_deg - spec.DRS_CRANK_ANGLE_CLOSED_DEG


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


def _reaim(handle, a0, b0, a1, b1):
    """Carry a two-ended member from (a0, b0) to (a1, b1) on a handle: rotate
    about the member's own first end, then translate that end onto its new
    position. Exact whenever the two lengths match, which the rack solve
    guarantees."""
    n0, n1 = _unit(_sub(b0, a0)), _unit(_sub(b1, a1))
    axis = _cross(n0, n1)
    s = math.hypot(*axis)
    if s > 1e-9:
        handle.rotate(axis, math.degrees(math.atan2(s, _clamp(_dot(n0, n1), -1.0, 1.0))), a0)
    t = _sub(a1, a0)
    if abs(t[0]) + abs(t[1]) + abs(t[2]) > 1e-9:
        handle.translate(t)
    return handle


# ---------------------------------------------------------------------------
# OCCURRENCES
# Top-level occurrence order is frozen by assemble(); see the OCCURRENCE ORDER
# block in this module's docstring. Do not renumber without updating both.
# ---------------------------------------------------------------------------

_F = {
    "front_wing": "#o1.1",
    "nose": "#o1.2",
    "monocoque": "#o1.3",
    "halo": "#o1.4",
    "cockpit": "#o1.5",
    "sidepod_left": "#o1.6",
    "sidepod_right": "#o1.7",
    "engine_cover": "#o1.8",
    "airbox": "#o1.9",
    "floor": "#o1.10",
    "diffuser": "#o1.11",
    "cooling": "#o1.12",
    "power_unit": "#o1.13",
    "drivetrain": "#o1.14",
    "rear_wing": "#o1.15",
    "drs_flap": "#o1.16",
    "drs_actuator": "#o1.17",
    "beam_wing": "#o1.18",
    "suspension_front": "#o1.19",
    "suspension_rear": "#o1.20",
    "corner_fl": "#o1.21",
    "corner_fr": "#o1.22",
    "track_rod_left": "#o1.23",
    "track_rod_right": "#o1.24",
    "corner_rl": "#o1.25",
    "corner_rr": "#o1.26",
    "steering_rack": "#o1.27",
    "details": "#o1.28",
}

# ---------------------------------------------------------------------------
# EXPLODE STAGING
#
# Each group gets a direction, a distance and a TIME WINDOW. Windows overlap
# only slightly and run in a deliberate order — bodywork, then cooling and rear
# aero, then running gear, then power unit and drivetrain last. That sequencing
# is what keeps the teardown readable. The direction is in car coordinates (+X
# forward, +Y left, +Z up) and is normalized before use.
#
# PURE TRANSLATION. An earlier pass also spun each part a few degrees about its
# own centroid and turntabled the whole car; both are gone. A rotating subject
# and a rotating part fight the one thing the viewer is meant to be reading.
#
# Distances are sized so parts clear each other in PROJECTION, not just in
# space: at 500-900 mm they still overlapped in silhouette from a three-quarter
# view and the frame read as a pile.
#
# THE POWER UNIT DELIBERATELY BARELY MOVES sideways. Everything else evacuates
# around it, which leaves the engine sitting alone at the centre of the frame
# as the hero — then it takes itself apart.
#
# Entries are (child, direction, distance mm, (window start, window end)).
# ---------------------------------------------------------------------------

_BODYWORK = (
    # Both are pushed off the centreline: the column straight above the car is
    # reserved for the power unit, which rises into it as the hero.
    ("engine_cover", (-0.22, -0.72, 0.72), 1150, (0.0, 0.3)),
    ("airbox", (0.18, -0.78, 0.7), 1180, (0.03, 0.33)),
    ("sidepod_left", (0, 1, 0.34), 1320, (0.05, 0.33)),
    ("sidepod_right", (0, -1, 0.34), 1320, (0.05, 0.33)),
    ("floor", (0, 0, -1), 980, (0.08, 0.33)),
    ("diffuser", (-0.45, 0, -1), 1020, (0.1, 0.33)),
)

_INTERNALS = (
    ("cooling", (0, 1, 0.55), 1860, (0.33, 0.52)),
    ("rear_wing", (-0.34, 0, 1), 1160, (0.33, 0.52)),
    ("drs_flap", (-0.34, 0, 1), 1420, (0.33, 0.52)),
    ("drs_actuator", (-0.34, 0, 1), 1280, (0.33, 0.52)),
    ("beam_wing", (-1, 0, 0.25), 980, (0.36, 0.55)),
    ("front_wing", (1, 0, -0.08), 1420, (0.36, 0.55)),
    ("nose", (1, 0, 0.22), 1680, (0.38, 0.58)),

    ("corner_fl", (0, 1, 0.05), 1180, (0.5, 0.72)),
    ("corner_fr", (0, -1, 0.05), 1180, (0.5, 0.72)),
    ("corner_rl", (0, 1, 0.05), 1180, (0.5, 0.72)),
    ("corner_rr", (0, -1, 0.05), 1180, (0.5, 0.72)),
    ("track_rod_left", (0, 1, 0.18), 820, (0.53, 0.74)),
    ("track_rod_right", (0, -1, 0.18), 820, (0.53, 0.74)),
    ("suspension_front", (0.35, 0, 0.85), 880, (0.55, 0.76)),
    ("suspension_rear", (-0.35, 0, 0.85), 880, (0.55, 0.76)),
    ("steering_rack", (1, 0, 0.2), 980, (0.57, 0.78)),
    ("details", (0, 1, 0.62), 1320, (0.62, 0.84)),

    ("halo", (0.42, 0.55, 0.68), 940, (0.62, 0.82)),
    ("cockpit", (0.12, 0.85, 0.62), 1180, (0.64, 0.86)),
    ("drivetrain", (-1, 0, 0.32), 1560, (0.7, 0.92)),

    # THE HERO. It lifts straight up and OUT of the car, early, into the column
    # everything else was pushed clear of — so by the time the teardown settles
    # the engine is hanging in open air above the wreck with nothing in front of
    # it. Sitting it in the middle of the spread (the first attempt, a 150 mm
    # token lift late in the sequence) buried it: geometrically exploded and
    # visually invisible.
    ("power_unit", (0, 0, 1), 1080, (0.08, 0.34)),
)

_EXPLODE_GROUPS = _BODYWORK + _INTERNALS

# ---------------------------------------------------------------------------
# ENGINE SUB-EXPLODE
#
# Addressed BY NAME, not by occurrence id. Occurrence ids under a part model
# are positional and shift the moment that model's child count changes, so a
# ref pinned to `#o1.13.36` can silently start driving a different body — and a
# ref that matches the WRONG part is indistinguishable from a correct one. A
# name that matches nothing RAISES instead.
#
# The 100 leaves are collapsed into 12 SYSTEMS plus a static core. Exploding
# 100 individual bodies is the "cloud of debris" failure: what a viewer can
# actually read is induction lifting off the vee, the heads splitting outward,
# the split turbo separating fore and aft, the exhaust sweeping back. The
# crankcase, sump, bearing webs and joint rails never move — they are the spine
# everything else is measured against.
#
# Entries are (system, part names, direction, distance mm).
# ---------------------------------------------------------------------------


def _seq(base: str, n: int) -> list[str]:
    return [f"{base}:{i}" for i in range(1, n + 1)]


_ENGINE_GROUPS = (
    ("eng_induction",
     ["plenum", "charge_pipe", "charge_pipe_clamp", "airbox_trunk",
      *_seq("trumpet:left", 3), *_seq("trumpet:right", 3)],
     (0, 0, 1), 760),

    ("eng_head_left",
     ["cylinder_head:left", "cam_cover:left", "fuel_rail:left", "head_joint_rail:left",
      *_seq("coil_pack:left", 3)],
     (0, 1, 0.5), 620),
    ("eng_head_right",
     ["cylinder_head:right", "cam_cover:right", "fuel_rail:right", "head_joint_rail:right",
      *_seq("coil_pack:right", 3)],
     (0, -1, 0.5), 620),

    # split turbo: compressor forward, turbine aft — the layout reads instantly
    ("eng_compressor", ["compressor_volute", "compressor_housing"], (1, 0, 0.2), 620),
    ("eng_turbine", ["turbine_volute", "turbine_housing", "turbine_inlet"], (-1, 0, 0.2), 620),
    ("eng_mguh", ["turbo_shaft", "mgu_h", "mgu_h_gland", "mgu_h_cable"], (0, 0, 1), 380),

    ("eng_exhaust_left",
     [*_seq("exhaust_primary:left", 3), "collector:left", "heat_shield:collector"],
     (-0.45, 1, 0.45), 760),
    ("eng_exhaust_right",
     [*_seq("exhaust_primary:right", 3), "collector:right"],
     (-0.45, -1, 0.45), 760),
    ("eng_tailpipe",
     ["collector_merge", "tailpipe", "tailpipe_tip", "heat_shield:tailpipe",
      "wastegate_body", "wastegate_flange", "wastegate_pipe", "wastegate_tip"],
     (-1, 0, 0.15), 900),

    ("eng_mguk",
     ["mgu_k", "mgu_k_ring", "mgu_k_drive_housing", *_seq("mgu_k_cable", 2)],
     (0.35, 1, -0.3), 700),

    ("eng_ers",
     ["ers_battery_case", "ers_battery_lid", "ers_terminal_block",
      *_seq("ers_bracket", 4), *_seq("ers_bus_bar", 6), *_seq("ers_coolant", 2)],
     (1, 0, -0.35), 860),

    ("eng_ancillaries",
     ["water_pump", "oil_pump", "oil_tank", "ecu_box", "ecu_connector",
      "water_feed", "water_return", "oil_feed", "oil_return",
      "fuel_line", "fuel_crossover",
      *_seq("ecu_pin", 3), *_seq("line_bracket", 4)],
     (0, -1, -0.28), 780),
)

# Children whose transform is authored explicitly below; everything else gets
# its explode offset and nothing more.
_DRIVEN = {"drs_flap", "drs_actuator", "corner_fl", "corner_fr", "steering_rack", "track_rod_left", "track_rod_right"}


def _frame(m, *, drs: float = 0.0, steer: float = 0.0, explode: float = 0.0, engine: float = 0.0) -> None:
    """One pose of the car.

    The explode translation is applied LAST on every handle, so a part can be
    simultaneously articulated (DRS, steering) and exploded without the
    articulation dragging the offset around with it — successive handle calls
    PREMULTIPLY, which is exactly that ordering.
    """
    offset = {}
    for name, direction, dist, (start, end) in _EXPLODE_GROUPS:
        amount = _ramp(start, end, explode)
        if amount <= 0:
            continue
        d0 = _unit(direction)
        offset[name] = (d0[0] * dist * amount, d0[1] * dist * amount, d0[2] * dist * amount)

    def shift(handle, name: str):
        if name in offset:
            handle.translate(offset[name])
        return handle

    # Engine sub-explode runs on its OWN clock, so the engine can come apart
    # while the car around it is already fully spread and stationary. Sub-parts
    # ride the power unit's own offset — its translate below reaches every part
    # under it — so only their own spread is added here.
    for _system, names, direction, dist in _ENGINE_GROUPS:
        d0 = _unit(direction)
        t = (d0[0] * dist * engine, d0[1] * dist * engine, d0[2] * dist * engine)
        for name in names:
            m.get(f"#{name}").translate(t)

    # ---- DRS ---------------------------------------------------------------
    flap_deg, crank_deg = _solve_drs(drs)
    shift(m.get(_F["drs_flap"]).rotate(_Y_AXIS, flap_deg, spec.DRS_PIVOT), "drs_flap")
    shift(m.get(_F["drs_actuator"]).rotate(_Y_AXIS, crank_deg, spec.DRS_CRANK_PIVOT), "drs_actuator")

    # ---- steering ----------------------------------------------------------
    # Positive steers LEFT (the car's +Y side is the inside of the turn). The
    # rack is one bar, so both wheels take the same shift and each wheel's
    # angle is solved against its OWN track rod — the two sides differ
    # slightly, which is where the anti-Ackermann comes from.
    rack_dy = _clamp(steer, -1.0, 1.0) * _MAX_RACK_TRAVEL
    for side, corner, rod in ((1, "corner_fl", "track_rod_left"), (-1, "corner_fr", "track_rod_right")):
        origin, axis = _steer_axis(side)
        deg = _solve_steer_angle(side, rack_dy)
        shift(m.get(_F[corner]).rotate(axis, deg, origin), corner)
        rack_end, arm = _on_side(spec.F_RACK_END, side), _on_side(spec.F_TRACKROD_OUT, side)
        moved_end = (rack_end[0], rack_end[1] + rack_dy, rack_end[2])
        moved_arm = _rotate_about_axis(arm, origin, axis, deg)
        shift(_reaim(m.get(_F[rod]), rack_end, arm, moved_end, moved_arm), rod)
    shift(m.get(_F["steering_rack"]).translate((0.0, rack_dy, 0.0)), "steering_rack")

    # ---- everything else: explode offset only -------------------------------
    for name, ref in _F.items():
        if name not in _DRIVEN:
            shift(m.get(ref), name)


# ---------------------------------------------------------------------------
# SHOWCASE — one loop-closed timeline
#
# Built so showcase(1) is IDENTICAL to showcase(0): a looping clip runs its
# last pose straight back into its first, so a plain 0->1 explode sweep would
# snap shut on the wrap. Every segment is a there-and-back, so the loop is
# seamless by construction rather than by trimming frames.
#
# The beat sheet, in seconds against the 22.5 s loop:
#    0.0 -  1.5  hold assembled — a showcase needs a moment of the whole object
#                before it starts taking itself apart, or the viewer never
#                registers what is being disassembled
#    1.5 - 10.5  CAR opens (9.0 s — deliberately slow; at half this length the
#                panels moved faster than the eye could follow one of them)
#   10.5 - 11.2  short handover (long enough to register the engine as a
#                subject, short enough not to stall)
#   11.2 - 14.8  ENGINE opens
#   14.8 - 16.3  hold at full spread — the money frame
#   16.3 - 18.8  engine closes
#   18.8 - 22.3  car closes
#   22.3 - 22.5  settle, closing the loop exactly
#
# The two piecewise switch points (0.70 / 0.69) each sit inside a plateau where
# both branches evaluate to 1, so neither introduces a step.
# ---------------------------------------------------------------------------


def _showcase_at(u: float) -> tuple[float, float]:
    """The showcase clock as (explode, engine); at u=0 and u=1 both are exactly 0."""
    u = _clamp(u, 0.0, 1.0)
    explode = _ramp(0.067, 0.467, u) if u < 0.7 else 1.0 - _ramp(0.836, 0.991, u)
    engine = _ramp(0.498, 0.658, u) if u < 0.69 else 1.0 - _ramp(0.724, 0.836, u)
    # DRS and steering are deliberately absent: this clip is the exploded view
    # and nothing else.
    return _clamp(explode, 0.0, 1.0), _clamp(engine, 0.0, 1.0)


def _pingpong(u: float) -> float:
    """Symmetric there-and-back on a raised cosine, so a loop closes exactly."""
    return 0.5 * (1.0 - math.cos(math.tau * (u % 1.0)))


def _showcase(t: float, m) -> None:
    explode, engine = _showcase_at((t / 22.5) % 1.0)
    _frame(m, explode=explode, engine=engine)


def _drs(t: float, m) -> None:
    # The one mechanism you can show while the car is still whole.
    _frame(m, drs=_pingpong(t / 4.0))


def _steering(t: float, m) -> None:
    # Left, through centre, to right and back — the car "looking around".
    _frame(m, steer=math.sin(math.tau * ((t / 6.0) % 1.0)))


def _teardown(t: float, m) -> None:
    _frame(m, explode=_pingpong(t / 12.0))


def _engine(t: float, m) -> None:
    _frame(m, engine=_pingpong(t / 8.0))


ANIMATION = {
    "showcase": cadgen.clip(_showcase, duration=22.5, label="Showcase"),
    "drs": cadgen.clip(_drs, duration=4, label="DRS"),
    "steering": cadgen.clip(_steering, duration=6, label="Steering"),
    "teardown": cadgen.clip(_teardown, duration=12, label="Teardown"),
    "engine": cadgen.clip(_engine, duration=8, label="Engine explode"),
}


@step(out="../STEP/f1.step", animation=ANIMATION)
def f1():
    return assemble()


if __name__ == "__main__":
    f1()
