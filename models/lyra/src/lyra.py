"""lyra — dexterous humanoid right hand concept for an advanced biped.

An aesthetically refined five-digit robotic hand: slim pearl-composite
shells over a graphite structural core, machined-aluminum precision
knuckle clevises with visible pivot pins, tendon-driven architecture
(dorsal tendon channels with a tensioner dial row at the wrist), integrated
tactile pads (palm array, per-phalanx strips, soft-touch fingertip caps),
an amber-ringed palm sensor, and a bolt-circle wrist flange. No logos.

Degrees of freedom (16, statically posed in the baked STEP):
  - each finger (index/middle/ring/pinky): MCP, PIP, DIP flexion -> 12
  - thumb: CMC yaw (opposition swing), CMC flex, MP, IP           -> 4

Coordinates: RIGHT hand; wrist-flange mount face center = origin,
+Z distal (fingers up), +Y palmar, +X radial (thumb side). Units mm.

Chain offsets, joint limits, and the baked "relaxed" pose live in
src/lib/chain.py and are shared with the authored URDF/SRDF artifacts
(lyra.urdf / lyra.srdf ledger comments) and the `ANIMATION` clips below,
which drive the same FK; edit the choreography there.
"""

from __future__ import annotations

import math

import cadgen
from cadgen import build123d as bd
from cadgen import step
from cadgen.assembly import AssemblyHelper

from index_distal import index_distal
from index_middle import index_middle
from index_proximal import index_proximal
from middle_distal import middle_distal
from middle_middle import middle_middle
from middle_proximal import middle_proximal
from palm import palm
from pinky_distal import pinky_distal
from pinky_middle import pinky_middle
from pinky_proximal import pinky_proximal
from ring_distal import ring_distal
from ring_middle import ring_middle
from ring_proximal import ring_proximal
from thumb_base import thumb_base
from thumb_distal import thumb_distal
from thumb_metacarpal import thumb_metacarpal
from thumb_proximal import thumb_proximal

from lib import chain
from lib.common import revolute_attach

# Every link is a sibling MODEL (one script per URDF link, part-local frame),
# keyed by the chain's link name. Calling one inside the body builds it if
# stale — on its own worker, alongside the rest — or loads it, and the hand
# links its tree. Rebuilding a link alone does not rebuild the hand: rerun
# this script.
LINKS = {
    "palm": palm,
    "index_proximal": index_proximal, "index_middle": index_middle, "index_distal": index_distal,
    "middle_proximal": middle_proximal, "middle_middle": middle_middle, "middle_distal": middle_distal,
    "ring_proximal": ring_proximal, "ring_middle": ring_middle, "ring_distal": ring_distal,
    "pinky_proximal": pinky_proximal, "pinky_middle": pinky_middle, "pinky_distal": pinky_distal,
    "thumb_base": thumb_base, "thumb_metacarpal": thumb_metacarpal,
    "thumb_proximal": thumb_proximal, "thumb_distal": thumb_distal,
}


def _xref_for(axis) -> tuple:
    return (0.0, 1.0, 0.0) if abs(axis[0]) > 0.9 else (1.0, 0.0, 0.0)


def assemble() -> bd.Compound:
    """Labeled assembly baked in the chain's relaxed pose.

    Occurrence order (#o1.N in the generated STEP) is palm first, then
    chain.all_joints() child order: index, middle, ring, pinky
    (proximal/middle/distal each), then thumb base/metacarpal/proximal/
    distal. The mates and the animation clips name links by label, so
    neither relies on this order.
    """
    asm = AssemblyHelper(chain.ROBOT_NAME)
    pose = chain.named_poses_deg()[chain.BAKED_POSE_NAME]

    parts = {"palm": asm.add(LINKS["palm"](), "palm")}
    for joint in chain.all_joints():
        child = asm.add(LINKS[joint["child"]](), joint["child"])
        axis = joint["axis"]
        xref = _xref_for(axis)
        revolute_attach(
            asm,
            parts[joint["parent"]],
            child,
            joint["name"],
            joint["origin_mm"],
            axis,
            xref,
            (0.0, 0.0, 0.0),
            axis,
            xref,
            pose[joint["name"]],
        )
        parts[joint["child"]] = child
    return asm.build()


# ---------------------------------------------------------------------------
# Kinematics: the 16-DOF chain as typed mates
# ---------------------------------------------------------------------------
# ZERO IS THE ARTIFACT AS WRITTEN. The STEP is baked in chain.BAKED_POSE_NAME
# ("relaxed"), so every mate's rest value is the RELAXED angle, not the chain's
# own zero. Limits and pose presets are therefore expressed as DELTAS from the
# baked pose — writing the chain's absolute angles here would double-offset
# every joint.
#
# Axis origins and directions are taken from FK through the baked pose, so each
# mate names the joint where the written geometry actually put it. The instance
# tree is FLAT (every link is a top-level `asm.add`), so the parent/child
# relationships have to be declared: a mate is what makes the fingertip ride
# its knuckle.


def _mates_and_poses():
    baked = chain.named_poses_deg()[chain.BAKED_POSE_NAME]
    frames = chain.fk_frames(baked)

    mates = []
    for joint in chain.all_joints():
        name = joint["name"]
        rot_parent, _ = frames[joint["parent"]]
        _, origin = frames[joint["child"]]
        direction = chain._mat_vec(rot_parent, joint["axis"])
        lo, hi = joint["range_deg"]
        rest = baked[name]
        mates.append(
            cadgen.revolute(
                name,
                parent=f"#{joint['parent']}",
                child=f"#{joint['child']}",
                origin=origin,
                direction=direction,
                limits=(lo - rest, hi - rest),
            )
        )

    poses = {
        pose_name: {j: values[j] - baked[j] for j in values}
        for pose_name, values in chain.named_poses_deg().items()
    }
    return mates, poses


_MATES, _POSES = _mates_and_poses()

KINEMATICS = {"mates": _MATES, "poses": _POSES}


# ---------------------------------------------------------------------------
# Animation: clips sampled to keyframes when the model builds
# ---------------------------------------------------------------------------
# The STEP geometry is baked in the "relaxed" pose (chain.BAKED_POSE_NAME).
# Each clip computes full-chain FK at its target pose — lib/chain.py's own FK,
# offsets and named poses — and applies, per link, the rigid delta
# T_target * inverse(T_relaxed). The STATIC space (joint limits, the named
# poses as viewer presets) is the `kinematics=` block above; the clips are the
# motion. Poses are blended in JOINT space with smoothstep easing: every
# intermediate state of a serial digit chain is itself a valid pose, so a
# blend can never break the mechanism. Every loop starts and ends on the exact
# pose it began with.
#
# Key orders are capsule-verified collision-free (src/lib/clearance.py, which
# mirrors them) — re-run that check after changing a pose or a key order.

_JOINT_NAMES = [joint["name"] for joint in chain.all_joints()]
_LINKS = chain.all_links()
_NAMED_POSES = chain.named_poses_deg()
_BAKED_FRAMES = chain.fk_frames(_NAMED_POSES[chain.BAKED_POSE_NAME])


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


def _apply(m, pose: dict[str, float]) -> None:
    """Carry each link from its baked frame to its FK frame at `pose`."""
    frames = chain.fk_frames(pose)
    for link in _LINKS:
        baked_rot, baked_pos = _BAKED_FRAMES[link]
        rot, pos = frames[link]
        turn = chain._mat_mul(rot, [list(column) for column in zip(*baked_rot)])
        moved = chain._mat_vec(turn, baked_pos)
        m.get(f"#{link}").transform([
            [*turn[0], pos[0] - moved[0]],
            [*turn[1], pos[1] - moved[1]],
            [*turn[2], pos[2] - moved[2]],
            [0.0, 0.0, 0.0, 1.0],
        ])


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
    pose = dict(_NAMED_POSES[chain.BAKED_POSE_NAME])
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


def _pose_tour(t: float, m) -> None:
    _apply(m, _tour_pose(t / 11.5))


def _grasp_loop(t: float, m) -> None:
    _apply(m, _grasp_pose(t / 2.6))


def _pinch_loop(t: float, m) -> None:
    _apply(m, _pinch_pose(t / 2.8))


def _ripple_loop(t: float, m) -> None:
    _apply(m, _ripple_pose(t / 2.6))


def _count_loop(t: float, m) -> None:
    _apply(m, _count_pose(t / 7.0))


ANIMATION = {
    "poseTour": cadgen.clip(_pose_tour, duration=11.5, label="Pose tour"),
    "graspLoop": cadgen.clip(_grasp_loop, duration=2.6, label="Power grasp"),
    "pinchLoop": cadgen.clip(_pinch_loop, duration=2.8, label="Precision pinch"),
    "rippleLoop": cadgen.clip(_ripple_loop, duration=2.6, label="Finger ripple"),
    "countLoop": cadgen.clip(_count_loop, duration=7.0, label="Count to five"),
}


@step(out="../STEP/lyra.step", kinematics=KINEMATICS, animation=ANIMATION)
def lyra():
    return assemble()


if __name__ == "__main__":
    lyra()
