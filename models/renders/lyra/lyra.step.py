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
lyra_parts/chain.py and are shared with the authored URDF/SRDF artifacts
(lyra.urdf / lyra.srdf ledger comments) and the CAD Viewer animation
sidecar (lyra.params.js); edit them there.
"""

from __future__ import annotations

from build123d import Compound

from cadgen.assembly import AssemblyHelper

from lyra_parts import chain
from lyra_parts.digits import (
    build_finger_distal,
    build_finger_middle,
    build_finger_proximal,
    build_thumb_base,
    build_thumb_distal,
    build_thumb_metacarpal,
    build_thumb_proximal,
)
from lyra_parts.lib import revolute_attach
from lyra_parts.palm import build_palm


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


def assemble() -> Compound:
    """Labeled assembly baked in the chain's relaxed pose.

    Occurrence order (#o1.N in the generated STEP) is palm first, then
    chain.all_joints() child order: index, middle, ring, pinky
    (proximal/middle/distal each), then thumb base/metacarpal/proximal/
    distal — the animation sidecar relies on this order.
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


def gen_step():
    return {"shape": assemble(), "params": "lyra.params.js"}
