"""The radial's mechanism: build123d joints on the built systems' parts, chosen by label.

The original posed parts by LABEL in its animation clips (`BUILDING.md`, "Moving parts:
labels are the contract"): every part labelled `<group>:<part>` whose group is a motion
group moved with that group, as `lib/kin.py` says. Here the same contract picks the
parts, and each motion group is one link:

- its first part carries the joint that moves it, paired by label with a joint on the
  link it turns or slides on, and every other part of the group that leaves with it in
  the teardown is fastened to that first part (two rigid joints of one label);
- every joint stands at 0 as built: the authored rest, crank angle theta = 0, where the
  valvetrain stands at its theta = 0 lift. A joint's value is its part's motion from
  there, so `kin.py`'s rest-relative poses are its values.

A group's joint stands on the group it rides (the master rod on the crank, an
articulating rod on the master, a tappet's roller and pushrod on the tappet, a planet on
the propeller shaft), or on the ground, every part no joint moves. The exploded clips
move no joint: they are GLB animations (`lib/explode.py`).

The gear train is linear in theta -- the crank, cam ring and idler, the tappet rollers,
the propeller shaft (the carrier, the propeller riding it) and its planets, the
impeller and the blower gears -- so it is one coupling, `drive`, in degrees of crank: a
constraint, its joints moving through it alone. The crank train and valvetrain are not
linear in theta: the master and articulating rods, the pistons, tappets, pushrods,
rockers and valves are joints of their own, and `running` (`assemble`) poses all of it
from `kin.py`.

Two approximations, both under a tenth of a degree or millimetre where they show: a
pushrod turns about one fixed axis through its tappet socket (the plane of its swing at
full lift), where `kin.py` turns it about the axis between its rest and current
directions; and a valve spring, which `kin.py` compresses as a tube, rides nothing.
"""

from __future__ import annotations

import math
import re

import build123d as bd
from cadgen.ap242 import configuration_sequence, gear_pair, mechanism_state

from lib import explode, kin
from lib import spec as S

# prefix regex -> motion kind (the original's `lib/clips.py` contract)
CONTRACT = [
    ("crank", r"crank"),
    ("master", r"master"),
    ("artrod", r"artrod([2-9])"),
    ("piston", r"piston([1-9])"),
    ("camring", r"camring"),
    ("camidler", r"camidler"),
    ("tappet", r"tappet([1-9])([IE])"),
    ("pushrod", r"pushrod([1-9])([IE])"),
    ("rocker", r"rocker([1-9])([IE])"),
    ("valve", r"valve([1-9])([IE])"),
    ("spring", r"spring([1-9])([IE])"),
    ("planet", r"planet([1-6])"),
    ("propshaft", r"propshaft"),
    ("prop", r"prop"),
    ("impeller", r"impeller"),
    ("blowergear", r"blowergear([1-3])"),
]  # patterns as strings: a compiled pattern is a value the memo cannot key (re caches them)

CYCLE_S = 8.0                  # one 720 deg four-stroke cycle
DEG_PER_S = 720.0 / CYCLE_S    # theta = 90 t
AXIS = S.ROT_AXIS              # every crank-train and gear axis


def classify(label: str):
    """(kind, args) of a moving part's label, or None for a static one."""
    if ":" not in label:
        return None
    prefix, part = label.split(":", 1)
    for kind, pattern in CONTRACT:
        found = re.fullmatch(pattern, prefix)
        if not found:
            continue
        args = found.groups()
        if kind in ("artrod", "piston", "planet", "blowergear"):
            return kind, (int(args[0]),)
        if kind in ("tappet", "pushrod", "rocker", "valve", "spring"):
            k, v = int(args[0]), args[1]
            if kind == "tappet" and part == "roller":
                return "roller", (k, v)
            return kind, (k, v)
        if kind == "prop":
            return "propshaft", ()          # the propeller turns with its shaft
        return kind, ()
    return None


def joint_name(kind: str, args: tuple) -> str:
    return kind + "".join(str(a) for a in args)


# ---------------------------------------------------------------------------
# Each joint's value at crank angle theta, from the authored rest (theta = 0)
# ---------------------------------------------------------------------------
def _master(theta):
    return kin.master_angle(theta) - kin.master_angle(0.0)


def _rod(theta, k):
    return kin.rod_angle(theta, k) - kin.rod_angle(0.0, k)


def _pushrod_ends(lift_t, k, v, rocker):
    """The pushrod's socket and cup with its tappet lifted by lift_t and its rocker at
    `rocker` degrees."""
    b = kin._addv(kin.pushrod_bottom0(k, v), kin.tappet_dir(k, v), lift_t)
    t = kin._rot_about(kin.pushrod_top0(k, v), kin.ROCKER_AXIS, rocker, kin.rocker_pivot(k, v))
    return b, t


def _direction(k, v, lift_t, rocker):
    b, t = _pushrod_ends(lift_t, k, v, rocker)
    return kin._unit(kin._sub(t, b))


def _swing_axis(k, v):
    """The fixed axis a pushrod swings about: normal to its rest and full-lift directions."""
    lift = S.TAPPET_LIFT[v]
    d0 = _direction(k, v, 0.0, 0.0)
    d1 = _direction(k, v, lift, kin._rocker_angle_for(k, v, lift))
    return kin._unit(kin._cross(d0, d1))


def _turn(k, v, lift_t, rocker):
    """The pushrod's turn about its swing axis (degrees) from its zero-lift direction."""
    n = PUSHROD_AXES[k, v]
    d0, d1 = _direction(k, v, 0.0, 0.0), _direction(k, v, lift_t, rocker)
    return math.degrees(math.atan2(kin._dot(kin._cross(d0, d1), n), kin._dot(d0, d1)))


PUSHROD_AXES = {(k, v): _swing_axis(k, v) for k in range(1, S.N_CYL + 1) for v in kin.VALVES}


def _valvetrain(theta, k, v):
    """(tappet lift, pushrod turn, rocker angle, valve lift) at crank angle theta: one
    rocker solve, which kin.py's rocker_angle, pose_pushrod and valve_lift each repeat."""
    lift = kin.tappet_lift(theta, k, v)
    rocker = kin._rocker_angle_for(k, v, lift)
    return lift, _turn(k, v, lift, rocker), rocker, kin.valve_lift_for_rocker(k, v, rocker)


REST = {(k, v): _valvetrain(0.0, k, v) for k in range(1, S.N_CYL + 1) for v in kin.VALVES}


def running_values(theta: float) -> dict:
    """Every free joint's value, and the drive's, at crank angle theta."""
    master = _master(theta)
    values = {"drive": theta, "master": master - theta}
    for k in range(2, S.N_CYL + 1):
        values[f"artrod{k}"] = _rod(theta, k) - master
    for k in range(1, S.N_CYL + 1):
        values[f"piston{k}"] = kin.piston_h(theta, k) - kin.piston_h(0.0, k)
        for v in kin.VALVES:
            now, rest = _valvetrain(theta, k, v), REST[k, v]
            values[f"tappet{k}{v}"] = now[0] - rest[0]
            values[f"pushrod{k}{v}"] = now[1] - rest[1]
            values[f"rocker{k}{v}"] = now[2] - rest[2]
            values[f"valve{k}{v}"] = -(now[3] - rest[3])
    return values


# The drive's ratio for each gear-train joint (degrees per crank degree).
def _ratios() -> dict:
    ratios = {"crank": 1.0, "camring": S.CAM_RATIO, "camidler": kin.cam_idler_ratio(),
              "propshaft": S.RED_RATIO, "impeller": S.BLOWER_RATIO}
    for j in range(1, 7):
        ratios[f"planet{j}"] = S.RED_RATIO * (S.RED_SUN_T / S.RED_PLANET_T)
    for j in range(1, 4):
        ratios[f"blowergear{j}"] = -S.BLOWER_CRANK_GEAR[0] / S.BLOWER_INTERMEDIATE[0][0]
    for k in range(1, S.N_CYL + 1):
        for v in kin.VALVES:
            ratios[f"roller{k}{v}"] = -S.CAM_RATIO * S.CAM_BASE_R / S.TAPPET_ROLLER_R
    return ratios


DRIVE = _ratios()
DRIVE_RANGE = (0.0, 720.0)

# Named poses: the crank angle each stands at, every joint where kin.py puts it.
CONFIGURATIONS = {
    "cylinder1_bdc": 180.0,       # cylinder 1 at the bottom of its power stroke
    "cylinder1_overlap": 360.0,   # cylinder 1 at TDC between exhaust and intake, both valves open
}


def _range(values, margin):
    return (min(values) - margin, max(values) + margin)


def _travel(table, name: str, margin: float):
    """A free joint's range: what one cycle takes it through, with a margin."""
    return _range([row[name] for row in table], margin)


# ---------------------------------------------------------------------------
# Authoring the joints on the built systems
# ---------------------------------------------------------------------------
def _xyz(p2d, y=0.0):
    return kin.xz_to_3d(p2d, y)


def _axis_of(kind: str, args: tuple):
    """(joint kind, point, direction) of each motion group's joint at the rest pose."""
    if kind == "crank":
        return "revolute", (0.0, 0.0, 0.0), AXIS
    if kind == "master":
        return "revolute", _xyz(kin.crankpin(0.0)), AXIS
    if kind == "artrod":
        return "revolute", _xyz(kin.knuckle(0.0, args[0])), AXIS
    if kind == "piston":
        return "linear", (0.0, 0.0, 0.0), S.cyl_u(args[0])
    if kind == "camring":
        return "revolute", (0.0, 0.0, 0.0), AXIS
    if kind == "camidler":
        return "revolute", kin.cam_idler_axis_point(), AXIS
    if kind == "tappet":
        return "linear", kin.pushrod_bottom0(*args), kin.tappet_dir(*args)
    if kind == "roller":
        k, v = args
        centre = kin._addv(kin.tappet_roller_centre0(k, v), kin.tappet_dir(k, v), kin.tappet_lift(0.0, k, v))
        return "revolute", centre, AXIS
    if kind == "pushrod":
        k, v = args
        socket = kin._addv(kin.pushrod_bottom0(k, v), kin.tappet_dir(k, v), kin.tappet_lift(0.0, k, v))
        return "revolute", socket, PUSHROD_AXES[k, v]
    if kind == "rocker":
        return "revolute", kin.rocker_pivot(*args), kin.ROCKER_AXIS
    if kind == "valve":
        return "linear", kin.valve_seat(*args), kin.valve_axis(*args)
    if kind == "planet":
        return "revolute", kin.planet_centre0(args[0]), AXIS
    if kind == "propshaft":
        return "revolute", (0.0, 0.0, 0.0), AXIS
    if kind == "impeller":
        return "revolute", (0.0, 0.0, 0.0), AXIS
    if kind == "blowergear":
        return "revolute", kin.blower_gear_centre(args[0]), AXIS
    raise ValueError(kind)


def _parent_of(kind: str, args: tuple):
    """The motion group a group's joint stands on; None is the ground."""
    if kind == "master":
        return ("crank", ())
    if kind == "artrod":
        return ("master", ())
    if kind in ("roller", "pushrod"):
        return ("tappet", args)
    if kind == "planet":
        return ("propshaft", ())
    return None


def _joint_range(table, name: str, joint: str):
    if name in DRIVE:
        lo, hi = sorted((DRIVE[name] * DRIVE_RANGE[0], DRIVE[name] * DRIVE_RANGE[1]))
        return lo - 1.0, hi + 1.0
    return _travel(table, name, 1.0 if joint == "linear" else 2.0)


# The motion groups' kinds, each after the group it stands on.
ORDER = ("crank", "master", "artrod", "piston", "camring", "camidler", "tappet", "roller", "propshaft", "planet",
         "impeller", "blowergear", "rocker", "valve", "pushrod")


def _identity(location) -> bool:
    found = location.to_tuple()
    return all(abs(v) < 1e-9 for v in (*found[0], *found[1]))


def _held(holder, joint) -> bd.Location:
    """Where a linear joint's rigid half stands at 0: build123d slides it without turning
    it, so its frame keeps the holder's orientation, at the axis point."""
    return holder.location * bd.Location(joint.relative_axis.position)


def author(root) -> dict[str, str]:
    """Every joint on the engine `root` (a compound of the systems, each a compound of
    labelled parts): each motion group's first part on its joint, every other part of the
    group fastened to it. Returns each part's occurrence path, by its label."""
    if not _identity(root.location) or any(not _identity(system.location) for system in root.children):
        raise ValueError("the joints are authored in the world frame: the engine and its systems stand at the origin")
    shapes, path_of = {}, {}
    for system in root.children:
        for part in system.children:
            shapes[part.label] = part
            path_of[part.label] = f"{root.label}/{system.label}/{part.label}"
    groups: dict[tuple, list[str]] = {}
    for label in shapes:
        found = classify(label)
        if found is not None and found[0] != "spring":
            groups.setdefault(found, []).append(label)
    table = [running_values(i * 2.0) for i in range(361)]   # one cycle, every 2 degrees
    for kind_ in ORDER:
        for (kind, args), labels in groups.items():
            if kind != kind_:
                continue
            joint, point, direction = _axis_of(kind, args)
            name = joint_name(kind, args)
            parent = _parent_of(kind, args)
            holder = root if parent is None else shapes[groups[parent][0]]
            lead = shapes[labels[0]]
            axis = bd.Axis(point, tuple(float(c) for c in direction))
            if joint == "linear":
                found = bd.LinearJoint(name, holder, axis=axis, linear_range=_joint_range(table, name, "linear"))
                seat = _held(holder, found)
            else:
                found = bd.RevoluteJoint(name, holder, axis=axis, angular_range=_joint_range(table, name, "revolute"))
                seat = found.location
            bd.RigidJoint(name, lead, seat)
            for label in labels[1:]:
                part = shapes[label]
                bd.RigidJoint(label, lead, part.location)
                bd.RigidJoint(label, part, part.location)
    made = {joint_name(*key) for key in groups}
    expected = set(DRIVE) | set(table[0]) - {"drive"}
    if expected - made:
        raise ValueError(f"no parts carry the motion groups {sorted(expected - made)}: the label contract changed")
    return path_of


def assemble(systems):
    """The engine: the systems under one compound, its joints, the gear train's coupling
    `drive`, the configurations, the `running` motion (the 720-degree cycle) and two GLB
    animations -- `explode`, the teardown from the rest pose, and `exploded-running`, the
    cycle with the groups held apart (`lib/explode.py`)."""
    engine = bd.Compound(label="radial", children=systems)
    path_of = author(engine)
    gear_pair(engine, "drive", **DRIVE)

    def turns(t: float) -> dict:
        return running_values(DEG_PER_S * t)

    for name, theta in CONFIGURATIONS.items():
        mechanism_state(engine, name, **running_values(theta))
    configuration_sequence(engine, "running", turns, duration=CYCLE_S)
    explode.explode(engine, path_of)
    explode.exploded_running(engine, path_of, CYCLE_S, turns)
    return engine
