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
(lyra.urdf / lyra.srdf ledger comments) and the CAD Viewer animation
module (src/lyra.anim.js); edit them there.
"""

from __future__ import annotations

import cadgen
from cadgen import build123d as bd
from cadgen import step
from cadgen.assembly import AssemblyHelper

from lib import chain
from lib.digits import (
    build_finger_distal,
    build_finger_middle,
    build_finger_proximal,
    build_thumb_base,
    build_thumb_distal,
    build_thumb_metacarpal,
    build_thumb_proximal,
)
from lib.common import revolute_attach
from lib.palm import build_palm


def _builders():
    builders = {}
    for finger in chain.FINGERS:
        builders[f"{finger}_proximal"] = lambda f=finger: build_finger_proximal(f)
        builders[f"{finger}_middle"] = lambda f=finger: build_finger_middle(f)
        builders[f"{finger}_distal"] = lambda f=finger: build_finger_distal(f)
    builders["thumb_base"] = build_thumb_base
    builders["thumb_metacarpal"] = build_thumb_metacarpal
    builders["thumb_proximal"] = build_thumb_proximal
    builders["thumb_distal"] = build_thumb_distal
    return builders


def _xref_for(axis) -> tuple:
    return (0.0, 1.0, 0.0) if abs(axis[0]) > 0.9 else (1.0, 0.0, 0.0)


def assemble() -> bd.Compound:
    """Labeled assembly baked in the chain's relaxed pose.

    Occurrence order (#o1.N in the generated STEP) is palm first, then
    chain.all_joints() child order: index, middle, ring, pinky
    (proximal/middle/distal each), then thumb base/metacarpal/proximal/
    distal — the animation module relies on this order.
    """
    asm = AssemblyHelper(chain.ROBOT_NAME)
    builders = _builders()
    pose = chain.named_poses_deg()[chain.BAKED_POSE_NAME]

    parts = {"palm": asm.add(build_palm(), "palm")}
    for joint in chain.all_joints():
        child = asm.add(builders[joint["child"]](), joint["child"])
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


@step(out="../STEP/lyra.step", kinematics=KINEMATICS, animation="lyra.anim.js")
def lyra():
    return assemble()


if __name__ == "__main__":
    lyra()
