"""lyra — dexterous humanoid right hand concept for an advanced biped.

An aesthetically refined five-digit robotic hand: slim pearl-composite
shells over a graphite structural core, machined-aluminum precision
knuckle clevises with visible pivot pins, tendon-driven architecture
(dorsal tendon channels with a tensioner dial row at the wrist), integrated
tactile pads (palm array, per-phalanx strips, soft-touch fingertip caps),
an amber-ringed palm sensor, and a bolt-circle wrist flange. No logos.

Degrees of freedom (16, one build123d revolute joint each):
  - each finger (index/middle/ring/pinky): MCP, PIP, DIP flexion -> 12
  - thumb: CMC yaw (opposition swing), CMC flex, MP, IP           -> 4

Coordinates: RIGHT hand; wrist-flange mount face center = origin,
+Z distal (fingers up), +Y palmar, +X radial (thumb side). Units mm.

Chain offsets, joint travel and the named poses live in lib/chain.py,
which ../lyra.urdf and ../lyra.srdf mirror, and so do the motions below;
edit the choreography there and here, then rerun `python -m lib.clearance`.

The models of this script:

- `lyra`: the hand. Its 17 links are placed by their joints,
  connected at the relaxed pose: that pose is the as-built configuration,
  every joint's value its absolute angle, every range the URDF's travel, the
  SRDF's seven hand group states are configurations, and the five clips are
  motions (functions of time over the joints).
- one model per URDF link (`palm` ... `thumb_distal`): the link alone in its
  part-local frame, whose 3MF ../lyra.urdf references (3MF/<link>.3mf, which
  exports.py writes).

Every link is made once a build. `links()` is the one `@memo` stage: all 17
links, which the hand and each link model call. The first call in a build
runs it (or replays it, when no edit reaches a builder) and every other call
is a new placement of its result.
"""

from __future__ import annotations

from cadgen import memo, model
from cadgen.ap242 import configuration_sequence, mechanism_state

import math

import build123d as bd

from lib import chain
from lib.common import revolute_attach
from lib.digits import (
    build_finger_distal,
    build_finger_middle,
    build_finger_proximal,
    build_thumb_base,
    build_thumb_distal,
    build_thumb_metacarpal,
    build_thumb_proximal,
)
from lib.palm import build_palm

_NAMED_POSES = chain.named_poses_deg()
RELAXED = _NAMED_POSES[chain.BAKED_POSE_NAME]


@memo
def links():
    """All 17 links, each in its own part-local frame, keyed by its URDF name."""
    made = {"palm": build_palm()}
    for finger in chain.FINGERS:
        made[f"{finger}_proximal"] = build_finger_proximal(finger)
        made[f"{finger}_middle"] = build_finger_middle(finger)
        made[f"{finger}_distal"] = build_finger_distal(finger)
    made["thumb_base"] = build_thumb_base()
    made["thumb_metacarpal"] = build_thumb_metacarpal()
    made["thumb_proximal"] = build_thumb_proximal()
    made["thumb_distal"] = build_thumb_distal()
    return made


def _xref_for(axis) -> tuple:
    return (0.0, 1.0, 0.0) if abs(axis[0]) > 0.9 else (1.0, 0.0, 0.0)


# ---------------------------------------------------------------------------
# Motions: the old clips, as joint values over time
# ---------------------------------------------------------------------------
# Every clip was joint-space already (chain FK at each sample, applied as a
# rigid delta against the relaxed build): a motion poses the joints directly,
# so the values below are absolute joint angles. Poses blend in JOINT space
# with smoothstep easing: every intermediate state of a serial digit chain is
# itself a valid pose, so a blend can never break the mechanism. Every loop
# starts and ends on the exact pose it began with.
#
# Key orders are capsule-verified collision-free (lib/clearance.py, which
# mirrors them) — re-run that check after changing a pose or a key order.

_JOINT_NAMES = [joint["name"] for joint in chain.all_joints()]


def _hand_pose(curls: dict[str, tuple], thumb: tuple) -> dict[str, float]:
    """A full-hand pose from each finger's (mcp, pip, dip) and the thumb's
    (cmc_yaw, cmc_flex, mp, ip)."""
    pose = {}
    for finger in chain.FINGERS:
        mcp, pip, dip = curls[finger]
        pose.update({f"{finger}_mcp": mcp, f"{finger}_pip": pip, f"{finger}_dip": dip})
    yaw, flex, mp, ip = thumb
    pose.update({"thumb_cmc_yaw": yaw, "thumb_cmc_flex": flex, "thumb_mp": mp, "thumb_ip": ip})
    return pose


def _smoothstep(u: float) -> float:
    t = min(max(u, 0.0), 1.0)
    return t * t * (3 - 2 * t)


def _blend(a: dict[str, float], b: dict[str, float], u: float) -> dict[str, float]:
    e = _smoothstep(u)
    return {name: a[name] + (b[name] - a[name]) * e for name in _JOINT_NAMES}


def _add_scaled(pose: dict[str, float], d: dict[str, float], scale: float) -> dict[str, float]:
    return {name: pose[name] + d[name] * scale for name in _JOINT_NAMES}


# Keyframe cycle through the showpiece poses; each segment blends for 65% of
# its window and dwells for 35%, wrapping back to its first key so the loop is
# exact. Key order is capsule-verified collision-free: the fist only neighbours
# tripod/relaxed, because blending it with pinch/point/ok would sweep the thumb
# through the index.
_TOUR_KEYS = ("relaxed", "precision_pinch", "ok_sign", "point", "tripod_pinch", "fist")
# The tour opens with one finger-ripple wave — it starts and ends exactly on
# the relaxed pose, so it splices seamlessly before the first keyframe blend.
_TOUR_RIPPLE_FRAC = 0.22


def _tour_pose(phase: float) -> dict[str, float]:
    p = phase % 1.0
    if p < _TOUR_RIPPLE_FRAC:
        return _ripple_pose(p / _TOUR_RIPPLE_FRAC)
    q = (p - _TOUR_RIPPLE_FRAC) / (1 - _TOUR_RIPPLE_FRAC)
    count = len(_TOUR_KEYS)
    seg = min(math.floor(q * count), count - 1)
    u = q * count - seg
    return _blend(_NAMED_POSES[_TOUR_KEYS[seg]], _NAMED_POSES[_TOUR_KEYS[(seg + 1) % count]], u / 0.65)


def _grasp_pose(phase: float) -> dict[str, float]:
    """Open-close power grasp: relaxed -> fist -> relaxed on a raised cosine."""
    wave = 0.5 * (1 - math.cos(math.tau * (phase % 1.0)))
    return _blend(_NAMED_POSES["relaxed"], _NAMED_POSES["fist"], wave)


# Precision pinch with a double pad tap while closed.
_PINCH_TAP = _hand_pose(
    {"index": (-5, -7, -4), "middle": (0, 0, 0), "ring": (0, 0, 0), "pinky": (0, 0, 0)},
    (0, 0, -7, -5),
)


def _pinch_pose(phase: float) -> dict[str, float]:
    p = phase % 1.0
    if p < 0.3:
        return _blend(_NAMED_POSES["relaxed"], _NAMED_POSES["precision_pinch"], p / 0.3)
    if p < 0.72:
        tap = math.sin(math.tau * 2 * ((p - 0.3) / 0.42))
        return _add_scaled(_NAMED_POSES["precision_pinch"], _PINCH_TAP, max(0.0, tap))
    return _blend(_NAMED_POSES["precision_pinch"], _NAMED_POSES["relaxed"], (p - 0.72) / 0.28)


# Traveling curl wave: each digit pulses inside its own window (raised cosine,
# zero at both ends), thumb last. The windows are wide relative to the digit
# spacing, so each digit starts curling while its neighbour is still mid-pulse
# and the wave reads as one continuous motion.
_RIPPLE_ORDER = ("index", "middle", "ring", "pinky", "thumb")
_RIPPLE_CURL = {"mcp": 30.0, "pip": 40.0, "dip": 22.0, "thumbFlex": 12.0, "thumbMp": 30.0, "thumbIp": 30.0}
_RIPPLE_WINDOW = 0.45


def _ripple_pose(phase: float) -> dict[str, float]:
    p = phase % 1.0
    step = (1 - _RIPPLE_WINDOW) / (len(_RIPPLE_ORDER) - 1)
    pose = dict(RELAXED)
    for i, digit in enumerate(_RIPPLE_ORDER):
        u = (p - i * step) / _RIPPLE_WINDOW
        if u <= 0 or u >= 1:
            continue
        lobe = math.sin(math.pi * u)
        amp = lobe * lobe
        if digit == "thumb":
            pose["thumb_cmc_flex"] += _RIPPLE_CURL["thumbFlex"] * amp
            pose["thumb_mp"] += _RIPPLE_CURL["thumbMp"] * amp
            pose["thumb_ip"] += _RIPPLE_CURL["thumbIp"] * amp
        else:
            pose[f"{digit}_mcp"] += _RIPPLE_CURL["mcp"] * amp
            pose[f"{digit}_pip"] += _RIPPLE_CURL["pip"] * amp
            pose[f"{digit}_dip"] += _RIPPLE_CURL["dip"] * amp
    return pose


# Count 1..5 from a fist (index first, thumb last), then close back. The thumb
# lifts to a hover clear of the fingers before any finger extends, and only
# re-wraps once the fingers are curled again — every adjacent blend is
# capsule-verified collision-free.
_COUNT_EXTENDED = {"index": (2, 2, 1), "middle": (2, 2, 1), "ring": (4, 4, 2), "pinky": (6, 6, 3)}
_COUNT_THUMB_FIST = (92, 13, 58, 74)
_COUNT_THUMB_HOVER = (50, 30, 25, 20)
_COUNT_THUMB_OPEN = (20, 10, 4, 4)


def _count_key(step: int, thumb: tuple) -> dict[str, float]:
    """The first `step` fingers extended, the rest curled as in the fist."""
    return _hand_pose(
        {finger: _COUNT_EXTENDED[finger] if step >= i + 1 else (78, 100, 60) for i, finger in enumerate(chain.FINGERS)},
        thumb,
    )


# 8 segments: fist -> thumb hover -> 1 -> 2 -> 3 -> 4 -> 5 (thumb opens) ->
# hover (fingers re-curl) -> wrap back to the fist.
_COUNT_KEYS = (
    _count_key(0, _COUNT_THUMB_FIST),
    _count_key(0, _COUNT_THUMB_HOVER),
    _count_key(1, _COUNT_THUMB_HOVER),
    _count_key(2, _COUNT_THUMB_HOVER),
    _count_key(3, _COUNT_THUMB_HOVER),
    _count_key(4, _COUNT_THUMB_HOVER),
    _count_key(5, _COUNT_THUMB_OPEN),
    _count_key(0, _COUNT_THUMB_HOVER),
)


def _count_pose(phase: float) -> dict[str, float]:
    p = phase % 1.0
    count = len(_COUNT_KEYS)
    seg = min(math.floor(p * count), count - 1)
    u = p * count - seg
    return _blend(_COUNT_KEYS[seg], _COUNT_KEYS[(seg + 1) % count], u / 0.6)


def _over_time(pose_at, duration):
    """A motion's function of time: the pose at its phase, ``t / duration``."""
    return lambda t: pose_at(t / duration)


# name: (the pose at a phase 0..1, the clip's duration in seconds)
MOTIONS = {
    "poseTour": (_tour_pose, 11.5),
    "graspLoop": (_grasp_pose, 2.6),
    "pinchLoop": (_pinch_pose, 2.8),
    "rippleLoop": (_ripple_pose, 2.6),
    "countLoop": (_count_pose, 7.0),
}


@model
def lyra():
    link = links()
    # Root to leaf: each joint on its parent link, connected at the relaxed pose.
    for joint in chain.all_joints():
        axis = joint["axis"]
        xref = _xref_for(axis)
        revolute_attach(link[joint["parent"]], link[joint["child"]], joint["name"], joint["origin_mm"],
                        axis, xref, (0.0, 0.0, 0.0), axis, xref, RELAXED[joint["name"]], joint["range_deg"])

    hand = bd.Compound(children=[link[name] for name in chain.all_links()], label="lyra")
    for name, pose in _NAMED_POSES.items():
        mechanism_state(hand, name, **pose)
    # Each clip ends on the pose it starts from, so a player repeats it as the old looping
    # clips ran (a motion has no loop of its own).
    for name, (pose_at, duration) in MOTIONS.items():
        configuration_sequence(hand, name, _over_time(pose_at, duration), duration=duration)
    return hand


# --- the URDF's link meshes: each link alone, in its part-local frame -------------------------


@model
def palm():
    return links()["palm"]


@model
def index_proximal():
    return links()["index_proximal"]


@model
def index_middle():
    return links()["index_middle"]


@model
def index_distal():
    return links()["index_distal"]


@model
def middle_proximal():
    return links()["middle_proximal"]


@model
def middle_middle():
    return links()["middle_middle"]


@model
def middle_distal():
    return links()["middle_distal"]


@model
def ring_proximal():
    return links()["ring_proximal"]


@model
def ring_middle():
    return links()["ring_middle"]


@model
def ring_distal():
    return links()["ring_distal"]


@model
def pinky_proximal():
    return links()["pinky_proximal"]


@model
def pinky_middle():
    return links()["pinky_middle"]


@model
def pinky_distal():
    return links()["pinky_distal"]


@model
def thumb_base():
    return links()["thumb_base"]


@model
def thumb_metacarpal():
    return links()["thumb_metacarpal"]


@model
def thumb_proximal():
    return links()["thumb_proximal"]


@model
def thumb_distal():
    return links()["thumb_distal"]


if __name__ == "__main__":
    lyra()
    palm()
    index_proximal()
    index_middle()
    index_distal()
    middle_proximal()
    middle_middle()
    middle_distal()
    ring_proximal()
    ring_middle()
    ring_distal()
    pinky_proximal()
    pinky_middle()
    pinky_distal()
    thumb_base()
    thumb_metacarpal()
    thumb_proximal()
    thumb_distal()
