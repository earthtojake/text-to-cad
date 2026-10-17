"""The engine's animation: three clips that pose parts by LABEL, baked to keyframes
in radial.py's sidecar when it builds.

  running           one 720 deg four-stroke cycle in 8 s, theta = 90 t deg, every
                    motion from lib/kin.py.
  explode           the teardown lib/explodeplan.py planned (lib/explode_plan.json),
                    then held.
  exploded-running  the running cycle with each group's constant exploded offset
                    from lib/explodedrun.py composed on top; some systems hidden.

Which parts move is decided by LABEL (BUILDING.md, "Moving parts: labels are
the contract"): every leaf label `<prefix>:<part>` whose prefix is a motion
group gets that group's pose. The labels are the built document's own
(`m.labels()`), so a part that lands or is renamed moves at the next build.
Crank-train parts are authored at theta = 0, where their pose is the identity;
valvetrain parts are authored at zero lift and placed with their theta = 0
pose, so they move by pose(theta) o pose(0)^-1. The valve springs are tube
deformations: rest = kin.spring_path(0), path = kin.spring_path(theta).

lib/animcheck.py proves `running` and `exploded-running` equal kin.py and the
layout on the built document; lib/explodecheck.py proves `explode` equals the plan.
"""

from __future__ import annotations

import functools
import json
import re
from pathlib import Path

import cadgen

from lib import explodedrun, kin

CYCLE_S = 8.0                  # one 720 deg cycle
DEG_PER_S = 720.0 / CYCLE_S    # theta = 90 t
SPRING_MAX_SEGMENT = 2.0       # deform_tube max_segment_length (mm)

# The teardown, read while radial.py loads so the build depends on it.
PLAN = json.loads((Path(__file__).resolve().parent / "explode_plan.json").read_text())

SYSTEM_NAMES = {
    "crankcase", "crankshaft", "rods", "pistons", "barrels", "heads", "valvetrain", "cam",
    "pushrods", "nose", "reduction", "propeller", "blower", "intake", "accessory", "ignition",
    "exhaust", "mount",
}

# ---------------------------------------------------------------------------
# The label contract (BUILDING.md). prefix regex -> motion kind
# ---------------------------------------------------------------------------
_CONTRACT = [
    ("crank", re.compile(r"crank")),
    ("master", re.compile(r"master")),
    ("artrod", re.compile(r"artrod([2-9])")),
    ("piston", re.compile(r"piston([1-9])")),
    ("camring", re.compile(r"camring")),
    ("camidler", re.compile(r"camidler")),
    ("tappet", re.compile(r"tappet([1-9])([IE])")),
    ("pushrod", re.compile(r"pushrod([1-9])([IE])")),
    ("rocker", re.compile(r"rocker([1-9])([IE])")),
    ("valve", re.compile(r"valve([1-9])([IE])")),
    ("spring", re.compile(r"spring([1-9])([IE])")),
    ("planet", re.compile(r"planet([1-6])")),
    ("propshaft", re.compile(r"propshaft")),
    ("prop", re.compile(r"prop")),
    ("impeller", re.compile(r"impeller")),
    ("blowergear", re.compile(r"blowergear([1-3])")),
]
_MOTION_STEM = re.compile(r"^(crank|master|art|conrod|rod\d|piston|cam|idler|tappet|lifter|follower|push|rocker|"
                          r"valve|spring|planet|carrier|prop|impel|blowergear|intermediate)", re.I)
SPRING_PARTS = ("outer", "inner")


def classify(label: str):
    """(kind, args) for a moving label, ("static", None) for a static one, or
    ("suspect", reason) when the label breaks the contract in a way that looks
    like a moving part that will NOT move."""
    if ":" not in label:
        return ("suspect", "no '<group>:' prefix")
    prefix, part = label.split(":", 1)
    for kind, rx in _CONTRACT:
        mt = rx.fullmatch(prefix)
        if not mt:
            continue
        args = mt.groups()
        if kind in ("artrod", "piston", "planet", "blowergear"):
            return (kind, (int(args[0]),))
        if kind in ("tappet", "pushrod", "rocker", "valve", "spring"):
            k, v = int(args[0]), args[1]
            if kind == "tappet" and part == "roller":
                return ("roller", (k, v))
            if kind == "spring":
                if part not in SPRING_PARTS:
                    return ("suspect", f"spring part must be one of {SPRING_PARTS} (tube deformation)")
                return ("spring", (k, v, part))
            return (kind, (k, v))
        return (kind, ())
    if prefix in SYSTEM_NAMES:
        return ("static", None)
    if _MOTION_STEM.match(prefix):
        return ("suspect", "prefix looks like a motion group but matches no contract group")
    return ("static", None)


def classify_leaf(label: str, owner: str):
    """classify() for a leaf; an unlabelled child of a nested compound inherits its owner's
    kind if static, and is flagged when the owner should move (it cannot be targeted)."""
    if ":" in label or not owner:
        return classify(label)
    kind, args = classify(owner)
    if kind in ("static", "suspect"):
        return ("static", None)
    return ("suspect", f"child of the MOVING nested compound {owner!r}: an unlabelled leaf cannot be "
                       "animated by label - make every moving leaf a flat, labelled solid")


# ---------------------------------------------------------------------------
# Motion: each kind's pose from kin.py, called as pose(theta, *args)
# ---------------------------------------------------------------------------
_POSES = {
    "crank": kin.pose_crank, "master": kin.pose_master, "artrod": kin.pose_art_rod,
    "piston": kin.pose_piston, "camring": kin.pose_cam_ring, "camidler": kin.pose_cam_idler,
    "planet": kin.pose_planet, "propshaft": kin.pose_propshaft, "prop": kin.pose_prop,
    "impeller": kin.pose_impeller, "blowergear": kin.pose_blower_gear,
    "tappet": kin.pose_tappet, "roller": kin.pose_tappet_roller, "pushrod": kin.pose_pushrod,
    "rocker": kin.pose_rocker, "valve": kin.pose_valve,
}
_VALVETRAIN = ("tappet", "roller", "pushrod", "rocker", "valve")    # authored at zero lift


def _play(handle, steps) -> None:
    """A kin.py pose's steps in order: each call premultiplies, as kin.pose_matrix composes."""
    for step in steps:
        if step[0] == "rotate":
            handle.rotate(step[1], step[2], step[3])
        else:
            handle.translate(step[1])


def _undo(steps) -> list:
    """The inverse of a pose: its steps reversed, each one undone."""
    return [("rotate", s[1], -s[2], s[3]) if s[0] == "rotate" else ("translate", tuple(-c for c in s[1]))
            for s in reversed(steps)]


@functools.cache
def _rest(kind: str, args: tuple) -> list:
    """What takes a part from where it is authored back to its theta = 0 pose."""
    return _undo(_POSES[kind](0.0, *args)) if kind in _VALVETRAIN else []


@functools.cache
def _spring_rest(k: int, v: str, which: str) -> dict:
    return kin.spring_path(0.0, k, v, which)


def _leaf_labels(m) -> tuple[str, ...]:
    """The built document's leaf labels: its other names, without a ':', are the
    systems and their finish groups."""
    return tuple(name for name in m.labels() if ":" in name)


@functools.cache
def _motions(labels: tuple[str, ...]):
    """The moving labels as [(kind, args, targets)], one entry per motion, and the
    springs as [(target, k, v, which)]."""
    groups, springs = {}, []
    for label in labels:
        kind, args = classify(label)
        if kind == "spring":
            springs.append((f"#{label}", *args))
        elif kind not in ("static", "suspect"):
            groups.setdefault((kind, args), []).append(f"#{label}")
    return [(kind, args, tuple(targets)) for (kind, args), targets in groups.items()], springs


def _run(m, labels: tuple[str, ...], theta: float) -> None:
    """Every running motion at crank angle theta (`running` and `exploded-running`)."""
    motions, springs = _motions(labels)
    for kind, args, targets in motions:
        _play(m.get(*targets), _rest(kind, args) + _POSES[kind](theta, *args))
    for target, k, v, which in springs:
        m.get(target).deform_tube(rest=_spring_rest(k, v, which), path=kin.spring_path(theta, k, v, which),
                                  max_segment_length=SPRING_MAX_SEGMENT)


# ---------------------------------------------------------------------------
# The exploded layouts
# ---------------------------------------------------------------------------
@functools.cache
def _explode_units(labels: tuple[str, ...]):
    """[(targets, moves)] for every planned unit with parts in this build. A label
    the plan never saw stays put until lib/explodeplan.py is rerun;
    lib/explodecheck.py lists both kinds of difference."""
    have = set(labels)
    units = []
    for unit in PLAN["units"].values():
        targets = tuple(f"#{label}" for label in unit["leaves"] if label in have)
        if targets and unit["moves"]:
            units.append((targets, unit["moves"]))
    return units


def _eased(moves, t: float) -> tuple[float, float, float]:
    """A unit's displacement at t: the sum of its smoothstep-eased straight moves
    [t0, t1, dx, dy, dz] (explodeplan.offset, the plan's own law)."""
    x = y = z = 0.0
    for t0, t1, dx, dy, dz in moves:
        if t <= t0:
            continue
        u = 1.0 if t >= t1 else (t - t0) / (t1 - t0)
        e = u * u * (3.0 - 2.0 * u)
        x, y, z = x + e * dx, y + e * dy, z + e * dz
    return (x, y, z)


@functools.cache
def _exploded_layout(labels: tuple[str, ...]):
    """lib/explodedrun.py's layout as ([(offset, targets)], hidden targets); the
    groups it never offsets just run."""
    groups, offsets, hidden = explodedrun.layout(labels)
    moved = [(offsets[g], tuple(f"#{label}" for label in groups[g])) for g in sorted(groups) if any(offsets[g])]
    return moved, tuple(f"#{label}" for label in hidden)


# ---------------------------------------------------------------------------
# The clips
# ---------------------------------------------------------------------------
def _running(t: float, m) -> None:
    _run(m, _leaf_labels(m), DEG_PER_S * t)


def _explode(t: float, m) -> None:
    # A designed teardown from the theta = 0 rest pose: every unit moves by eased
    # straight translations, a fastener by its own exit and then its host's.
    for targets, moves in _explode_units(_leaf_labels(m)):
        offset = _eased(moves, t)
        if any(offset):
            m.get(*targets).translate(offset)


def _exploded_running(t: float, m) -> None:
    # The running cycle exactly as `running`, with each group's constant offset
    # composed on top in world space: offsets never change, so the loop is as
    # seamless as `running`.
    labels = _leaf_labels(m)
    _run(m, labels, DEG_PER_S * t)
    moved, hidden = _exploded_layout(labels)
    for offset, targets in moved:
        m.get(*targets).translate(offset)
    if hidden:
        m.get(*hidden).visible(False)


ANIMATION = {
    "running": cadgen.clip(_running, duration=CYCLE_S, label="Running (720 deg cycle)"),
    "explode": cadgen.clip(_explode, duration=PLAN["duration"], loop=False, label="Exploded view (teardown)"),
    "exploded-running": cadgen.clip(_exploded_running, duration=CYCLE_S, label="Exploded, running (720 deg cycle)"),
}
