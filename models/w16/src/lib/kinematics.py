"""W16 kinematics: the engine's mechanism as build123d joints, and its `crank` motion.

Everything that turns or slides is placed by `lib/kin.py` at theta = 0 (the
rest pose every file shows), and every joint here is authored where its parts
stand as built, paired by its label: a moving joint on the part that carries
it and a `RigidJoint` of the same label on the part it moves, at the moving
joint's own frame, so each stands at 0 as built. Whatever rides a moving part
(the rings on a piston, the sprocket on a cam) is fastened to it by a pair of
`RigidJoint`s of one label, which makes it part of that link.

    crank            revolute about the crank axis (X) on the crank system's group:
                     the crankshaft, damper, flywheel and their bolts
    crank_sprockets  revolute about the crank axis on the cam drive's group: the
                     crank sprocket hub and both crank sprockets
    crank_oil_drive  revolute about the crank axis on the oil system's group: the
                     crank pulley hub, the oil-pump drive pulley and its bolts
    piston_N         prismatic along cylinder N's bore axis on the block casting
    rod_N            revolute about the wrist pin on piston N (the rod-to-crankpin
                     joint closes the loop: it is the one not jointed)
    cam_B_K          revolute about each cam axis on that cam's first bearing cap
    cam_sprocket_B_K revolute about each cam axis on the cam drive's group: the
                     cam sprocket, its bolt and washer
    valve_T          prismatic along each valve's stem on its valve guide
    follower_T       revolute about each roller follower's pivot on its lash adjuster
    oil_pump         revolute about the pump stack's axis on the oil system's group
    turbo_B_P        revolute about each turbo's shaft on its centre housing
    pulley_NAME      revolute about each accessory pulley's axis on the ancillaries' group

Each turning part's joint is held by the part (or the system's group) that carries
it: the crank on its system, the sprockets on the cam drive, the oil-pump drive and
the pulleys on their systems, the cams on their caps, the valves on their guides and
the followers on their lash adjusters. The `explode` and `running_reveal` animations
(`lib/explode.py`) move each part after the crank cycle poses it.

The slider-crank and the cam train are closed loops, so no coupling can say
them: the `crank` motion is a function of time that poses every joint as
`lib/kin.py` solves it (the rod's angle, each valve's lift, each follower's
rock), one 720 deg cycle in 6 s. The chains stay put: a link riding its loop
moves in the plane of the chain, which no joint between two parts says.
"""

from __future__ import annotations

import math
from typing import Callable

import build123d as bd

from lib import ancillaries as A, kin, oil_system as O, spec as S
from lib.cams import cam_axis
from lib.valvetrain import valve_tag

CRANK_SECONDS = 6.0          # one 720 deg cycle
_X = (1.0, 0.0, 0.0)

# The crank and everything of the crank system bolted to it.
_CRANK_RIDERS = ("crank_damper", "damper_washer", "damper_bolt", "flywheel",
                 *(f"flywheel_bolt:{k}" for k in range(1, 9)))
# What turns with the crank but belongs to another system, each on its own joint about the
# crank axis, held by its system's group: the cam drive's sprockets and the oil system's
# drive pulley (with its hub and bolts).
_CRANK_SPROCKETS = ("crank_sprocket:1", "crank_sprocket:2")
_CRANK_OIL_DRIVE = ("crank_oil_pulley", *(f"crank_pulley_bolt:{k}" for k in range(1, 7)))

# The oil pump is belt-driven off the crank's oil pulley onto its own, about an
# axis along X through OIL_PUMP_CENTRE.
_OIL_PUMP_RATIO = O.CRANK_PULLEY_D / O.PUMP_PULLEY_D

# Both wheels and the shaft nut of each turbo spin about its axis, a whole
# number of turns a cycle so the loop is seamless.
_TURBO_TURNS_PER_CYCLE = 12


def _belt_ratio(radius: float) -> float:
    """A pulley's speed over the crank's: the belt's rib face wraps every wheel
    at its radius + BELT_CLEAR (`lib/ancillaries.py`), the damper's included."""
    return (A.DAMPER_R + A.BELT_CLEAR) / (radius + A.BELT_CLEAR)


# The accessory drive: every pulley turns about its own X axis at its belt ratio.
_PULLEYS = (
    ("water_pump_1", A.WP_YZ[1], _belt_ratio(A.WP_R)),
    ("water_pump_2", A.WP_YZ[2], _belt_ratio(A.WP_R)),
    ("alternator", A.ALT_YZ, _belt_ratio(A.ALT_R)),
    ("idler", A.IDLER_YZ, _belt_ratio(A.IDLER_R)),
    ("tensioner", A.TENS_YZ, _belt_ratio(A.TENS_R)),
)

_VALVES = kin.all_valves()
_REST = {c.number: kin.piston(c.number, 0.0) for c in S.CYLINDERS}


# How far the explode draws each piston (and its rod) out of its bore (`lib/explode.py`).
PISTON_OUT = 220.0


def _travel(cyl: int) -> tuple[tuple[float, float], tuple[float, float]]:
    """Piston `cyl`'s slide and its rod's swing from rest, over a cycle sampled each
    degree, with a margin past the samples (mm, deg)."""
    states = [kin.piston(cyl, float(t)) for t in range(720)]
    rest = _REST[cyl]
    slide = [state.s - rest.s for state in states]
    swing = [state.rod_tilt - rest.rod_tilt for state in states]
    return (min(slide) - 0.5, max(slide) + 0.5), (min(swing) - 1.0, max(swing) + 1.0)


_STROKE, _SWING = {}, {}
for _c in S.CYLINDERS:
    _STROKE[_c.number], _SWING[_c.number] = _travel(_c.number)
_LIFT0 = {valve_tag(g): kin.valve_lift(g.cyl, g.kind, 0.0) for g in _VALVES}
_EPS0 = {valve_tag(g): kin.follower_angle(g, _LIFT0[valve_tag(g)]) for g in _VALVES}


def _piston_riders(n: int) -> tuple[str, ...]:
    return (f"piston_ring:{n}_1", f"piston_ring:{n}_2", f"piston_ring:{n}_3",
            f"wrist_pin:{n}", f"circlip:{n}_f", f"circlip:{n}_r")


def _rod_riders(n: int) -> tuple[str, ...]:
    return (f"rod_cap:{n}", f"rod_bolt:{n}_1", f"rod_bolt:{n}_2",
            f"rod_shell:{n}_upper", f"rod_shell:{n}_lower", f"rod_bush:{n}")


def _parts(engine) -> dict[str, list[bd.Shape]]:
    """Every leaf of the engine by its label."""
    found: dict[str, list[bd.Shape]] = {}
    for node in engine.descendants:
        if not node.children:
            found.setdefault(node.label, []).append(node)
    return found


class _Author:
    """Joints on the engine's parts, by label."""

    def __init__(self, engine):
        self.parts = _parts(engine)

    def part(self, label: str) -> bd.Shape:
        found = self.parts.get(label, [])
        if len(found) != 1:
            raise LookupError(f"{len(found)} parts of the engine are labelled {label!r}")
        return found[0]

    def present(self, *labels: str) -> list[str]:
        """The labels of these that were built (the museum section cuts some away)."""
        return [label for label in labels if label in self.parts]

    def joint(self, name: str, kind: str, on, moves: str, origin, direction, limits, riders=()):
        """A `kind` joint `name` on `on` (a part's label, or a system's group) about
        (revolute) or along (prismatic) the axis through `origin` along `direction`,
        moving part `moves` and every rider with it. Every group and part stands in the
        engine's frame (the groups at the identity), so one frame serves both halves."""
        base = self.part(on) if isinstance(on, str) else on
        moving = self.part(moves)
        axis = bd.Axis(origin, direction)
        if kind == "revolute":
            joint = bd.RevoluteJoint(name, base, axis=axis, angular_range=limits)
        else:
            joint = bd.LinearJoint(name, base, axis=axis, linear_range=limits)
        # The rigid half where the moving joint holds it at 0, as build123d's relative_to reads
        # each: a revolute's frame is its axis's; a linear joint slides a frame that keeps the
        # part's axes, at the axis's origin.
        if kind == "revolute":
            frame = base.location * joint.relative_axis.location
        else:
            frame = base.location * bd.Location(joint.relative_axis.position)
        bd.RigidJoint(name, moving, frame)
        for rider in riders:
            fastening = f"{name}_{rider.replace(':', '_')}"
            bd.RigidJoint(fastening, moving, frame)
            bd.RigidJoint(fastening, self.part(rider), frame)


_FREE = (-math.inf, math.inf)


def systems_of(engine) -> dict[str, bd.Compound]:
    """The engine's thirteen system groups by name (`block`, `crank`, ... `ancillaries`)."""
    return {system.label: system for system in engine.children}


def first_cap(present: Callable, bank: int, kind: str) -> str:
    """The first of a cam's five bearing caps the section left standing: the part its joint
    is held by (the museum section cuts bank 1's front caps away)."""
    found = present(*(f"cam_cap:{bank}_{kind}_{k}" for k in range(1, 6)))
    if not found:
        raise LookupError(f"no bearing cap of cam {bank}_{kind} was built")
    return found[0]


def author_joints(engine) -> None:
    """Every joint of the engine's mechanism, on the parts `engine` holds."""
    a = _Author(engine)
    systems = systems_of(engine)
    block = "block"                                   # the crankcase casting
    a.joint("crank", "revolute", systems["crank"], "crankshaft", (0.0, 0.0, 0.0), _X, _FREE, _CRANK_RIDERS)
    a.joint("crank_sprockets", "revolute", systems["camdrive"], "crank_sprocket_hub", (0.0, 0.0, 0.0), _X, _FREE,
            _CRANK_SPROCKETS)
    a.joint("crank_oil_drive", "revolute", systems["oil_system"], "crank_pulley_hub", (0.0, 0.0, 0.0), _X, _FREE,
            _CRANK_OIL_DRIVE)
    for c in S.CYLINDERS:
        n, rest = c.number, _REST[c.number]
        foot = (c.x, rest.small_end[0], rest.small_end[1])
        a.joint(f"piston_{n}", "prismatic", block, f"piston:{n}", foot, (0.0, c.axis[1], c.axis[2]),
                _STROKE[n], _piston_riders(n))
        a.joint(f"rod_{n}", "revolute", f"piston:{n}", f"rod:{n}", foot, _X, _SWING[n], _rod_riders(n))
    for bank in (1, 2):
        for kind in ("intake", "exhaust"):
            key = f"{bank}_{kind}"
            axis = (0.0, *cam_axis(bank, kind))
            a.joint(f"cam_{key}", "revolute", first_cap(a.present, bank, kind), f"camshaft:{key}", axis, _X, _FREE)
            a.joint(f"cam_sprocket_{key}", "revolute", systems["camdrive"], f"cam_sprocket:{key}", axis, _X, _FREE,
                    (f"cam_sprocket_bolt:{key}", f"cam_sprocket_washer:{key}"))
    for g in _VALVES:
        tag = valve_tag(g)
        lift0 = _LIFT0[tag]
        # the stem opens along -v (seat -> tip is +v): lift moves it by -v
        a.joint(f"valve_{tag}", "prismatic", f"valve_guide:{tag}", f"valve:{tag}", (g.x, *g.tip),
                (0.0, -g.v[0], -g.v[1]), (-lift0, S.VALVE_LIFT - lift0),
                (f"valve_spring:{tag}", f"retainer:{tag}", f"collet:{tag}_a", f"collet:{tag}_b"))
        a.joint(f"follower_{tag}", "revolute", f"lash_adjuster:{tag}", f"follower:{tag}", (g.x, *g.pivot), _X,
                (-45.0, 45.0), (f"roller:{tag}", f"roller_axle:{tag}"))
    a.joint("oil_pump", "revolute", systems["oil_system"], "oil_pump_shaft", S.OIL_PUMP_CENTRE, _X, _FREE,
            ("oil_pump_pulley",))
    for t in S.TURBOS:
        tag = f"{t['bank']}_{t['pos']}"
        rotor = a.present(f"turbine_wheel:{tag}", f"compressor_wheel:{tag}", f"compressor_shaft_nut:{tag}")
        if rotor:
            _, y, z = t["centre"]
            a.joint(f"turbo_{tag}", "revolute", f"centre_housing:{tag}", rotor[0], (0.0, y, z), _X, _FREE, rotor[1:])
    for name, (y, z), _ratio in _PULLEYS:
        a.joint(f"pulley_{name}", "revolute", systems["ancillaries"], f"pulley:{name}", (0.0, y, z), _X, _FREE)


def pose(theta: float, turbos=None) -> dict[str, float]:
    """Every joint's value at crank angle `theta` (deg, run on through every cycle)."""
    values = {"crank": theta, "crank_sprockets": theta, "crank_oil_drive": theta,
              "oil_pump": theta * _OIL_PUMP_RATIO}
    for c in S.CYLINDERS:
        now, rest = kin.piston(c.number, theta), _REST[c.number]
        values[f"piston_{c.number}"] = now.s - rest.s
        values[f"rod_{c.number}"] = now.rod_tilt - rest.rod_tilt
    for bank in (1, 2):
        for kind in ("intake", "exhaust"):
            values[f"cam_{bank}_{kind}"] = values[f"cam_sprocket_{bank}_{kind}"] = kin.cam_angle(theta)
    for g in _VALVES:
        tag = valve_tag(g)
        lift = kin.valve_lift(g.cyl, g.kind, theta)
        values[f"valve_{tag}"] = lift - _LIFT0[tag]
        values[f"follower_{tag}"] = kin.follower_angle(g, lift) - _EPS0[tag]
    for tag in turbos or ():
        values[f"turbo_{tag}"] = theta * _TURBO_TURNS_PER_CYCLE * 360.0 / 720.0
    for name, _yz, ratio in _PULLEYS:
        values[f"pulley_{name}"] = theta * ratio
    return values


def turbos(engine) -> list[str]:
    """The turbos the engine was built with (the section lifts one off)."""
    labels = {node.label for node in engine.descendants}
    return [f"{t['bank']}_{t['pos']}" for t in S.TURBOS if f"turbine_wheel:{t['bank']}_{t['pos']}" in labels]


def crank_cycle(turbo_tags):
    """The `crank` motion's function of time: one 720 deg cycle in CRANK_SECONDS."""
    def at(t: float) -> dict[str, float]:
        return pose(720.0 * t / CRANK_SECONDS, turbo_tags)
    return at
