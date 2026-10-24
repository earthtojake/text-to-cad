"""Tom rev4's clips (showcase, wrist, approach) and poses, on the joints src/tom.py authors.

The choreography is the control showcase's (control/ik/showcase.py): wake at the hero pose,
fold to the park, three party beats, a yaw slew, a full-extension reach, then the planted-claw
lap (tip held 330 mm out, pointing straight down, while elbow roll drives the arm's one degree
of self-motion), release and settle. A second clip, `wrist`, holds the claw tip at one point
while its approach sweeps a full 360 deg cone on the 3-DOF wrist. A third, `approach`, reaches
one point from seven directions to show what the gripper can do. That module validates every
sampled frame against the URDF limits, the tabletop plane and the sphere-model self-collision
check, then writes its beat table to showcase_keys.json (`python -m control.ik.showcase
--write-cad-keys`). This module plays the same table, interpolated and breathing exactly as the
page samples it, as motions of the arm: each a function of time over the joints `lib/joints.py`
names after the mates (`MATES` maps the table's URDF names to them). The table's degrees are
joint values from joint zero (lib/joint_zero.py), the same convention and the same right-handed
turn about each mate's axis as the joints', so a clip's angles mean what the old ones meant.

The mates' presets (``kinematics["poses"]``) are configurations of the arm.

The occurrence ids the old clips addressed stay pinned in tom_occurrence_ids.json and are
checked against the tree the build makes: an occurrence id is a tree position (the root is o1,
each child appends its 1-based index), and the ids must still name the labelled occurrences, or
the build fails.
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, is_dataclass
from pathlib import Path

from cadgen.ap242 import configuration_sequence, mechanism_state

__all__ = ["CLIPS", "MATES", "add_poses", "add_clips", "beat_table", "clip_pose", "occurrence_ids",
           "check_occurrence_ids"]

HERE = Path(__file__).resolve().parent
KEYS_PATH = HERE / "showcase_keys.json"
IDS_PATH = HERE / "tom_occurrence_ids.json"
# URDF joint -> CAD mate (the joint's label), chain order (base first): the same names
# write_xml.py snake-cases.
MATES = {"shoulder_yaw": "shoulderYaw", "shoulder_pitch": "shoulderPitch",
         "elbow_pitch": "elbowPitch", "elbow_roll": "elbowRoll", "wrist_pitch": "wristPitch",
         "wrist_yaw": "wristYaw", "gripper_jaw": "gripperJaw"}

# Clip name -> (label, description), as the viewer listed them. The beat tables come from
# showcase_keys.json.
CLIPS = {
    "showcase": ("Showcase",
                 "Hero pose, fold to the park, three party beats, a yaw slew and a full reach, then "
                 "plant the claw 330 mm out pointing straight down and sweep the arm around it on "
                 "elbow roll, release and settle. The control showcase's validated performance."),
    "wrist": ("3-DOF wrist",
              "The claw tip held at one point, 300 mm out and 180 mm over the desk, while its "
              "approach sweeps a full 360 deg cone: elbow roll, wrist pitch and wrist yaw re-point "
              "the gripper about a fixed tip, with no spin about its own axis."),
    "approach": ("One point, seven approaches",
                 "The gripper reaches the same point, 310 mm out and 95 mm over the desk, from seven "
                 "directions: level from the right, the front-right diagonal, 30 and 60 deg below "
                 "level, top-down, the front-left diagonal and level from the left. Each time it "
                 "opens, slides in along its own axis, grips, releases and backs out."),
}


def occurrence_ids() -> dict[str, str]:
    return json.loads(IDS_PATH.read_text())


def _mates(kinematics) -> list[dict]:
    return [asdict(m) if is_dataclass(m) else dict(m) for m in kinematics["mates"]]


def _id_key(oid: str) -> tuple[int, ...]:
    return tuple(int(x) for x in oid[1:].split("."))


def beat_table(kinematics) -> dict[str, dict]:
    """showcase_keys.json's clips, checked against the arm's mates as the old module did
    (the table's joints and clips, every key plus its breath inside the joint's audited
    range), each as ``{duration, keys: [(t, [deg per joint in MATES order], linear)],
    breath: [deg per joint], cycles}``."""
    table = json.loads(KEYS_PATH.read_text())
    mates = {m["name"]: m for m in _mates(kinematics)}
    if table["joints"] != list(MATES):
        raise ValueError(f"showcase keys name joints {table['joints']}, expected {list(MATES)}")
    if set(table["clips"]) != set(CLIPS):
        raise ValueError(f"showcase keys hold clips {sorted(table['clips'])}, expected {sorted(CLIPS)}")
    for joint, mate_name in MATES.items():
        lo, hi = mates[mate_name]["limits"]["value"]
        for name, clip in table["clips"].items():
            values = [key["deg"][joint] for key in clip["keys"]]
            breath = clip["breath"]["deg"].get(joint, 0.0)
            if min(values) - breath < lo - 1e-6 or max(values) + breath > hi + 1e-6:
                raise ValueError(f"{name} keys leave {joint}'s limits {lo}..{hi}")
    return {
        name: {
            "duration": clip["duration_s"],
            "keys": [(key["t"], [key["deg"][j] for j in MATES], key.get("ease") == "linear") for key in clip["keys"]],
            "breath": [clip["breath"]["deg"].get(j, 0.0) for j in MATES],
            "cycles": clip["breath"]["cycles"],
        }
        for name, clip in table["clips"].items()
    }


def _smoothstep(s: float) -> float:
    return s * s * (3 - 2 * s)


def clip_pose(clip: dict, t: float) -> list[float]:
    """The joint values (MATES order) at ``t`` seconds into ``clip``: the old page's sampling.
    Each segment eases with smoothstep unless the key it arrives at is marked linear, and a low
    breathing drift rides on top, an integer number of cycles so the clip ends where it starts."""
    duration = clip["duration"]
    t = t % duration
    keys = clip["keys"]
    seg = 0
    while seg + 1 < len(keys) - 1 and t >= keys[seg + 1][0]:
        seg += 1
    t0, a, _ = keys[seg]
    t1, b, linear = keys[seg + 1]
    u = min(1.0, max(0.0, (t - t0) / (t1 - t0))) if t1 > t0 else 0.0
    s = u if linear else _smoothstep(u)
    wave = math.sin(2 * math.pi * clip["cycles"] * t / duration)
    return [v + s * (b[i] - v) + clip["breath"][i] * wave for i, v in enumerate(a)]


def add_poses(arm, kinematics):
    """The mates' presets as configurations of ``arm``, by joint label."""
    for name, pose in kinematics.get("poses", {}).items():
        mechanism_state(arm, name, **pose)
    return arm


def add_clips(arm, kinematics):
    """The three clips as motions of ``arm`` with their old names and durations (no loop: a
    player repeats a clip, and each ends on the pose it starts from)."""
    for name, clip in beat_table(kinematics).items():
        def at(t, clip=clip):
            return dict(zip(MATES.values(), clip_pose(clip, t)))

        configuration_sequence(arm, name, at, duration=clip["duration"])
    return arm


def check_occurrence_ids(assembly, ids: dict[str, str] | None = None) -> None:
    """Fail the build when the pinned ids no longer name the labelled occurrences.

    Occurrence ids are tree positions: the root is o1 and each child appends its 1-based index.
    """
    ids = occurrence_ids() if ids is None else ids
    found: dict[str, str] = {}

    def walk(shape, oid: str) -> None:
        if shape.label in ids and shape.label not in found:
            found[shape.label] = oid
        for index, child in enumerate(shape.children or (), 1):
            walk(child, f"{oid}.{index}")

    walk(assembly, "o1")
    wrong = {label: (pinned, found.get(label)) for label, pinned in ids.items() if found.get(label) != pinned}
    if wrong:
        current = dict(sorted(found.items(), key=lambda kv: _id_key(kv[1])))
        raise ValueError(f"showcase occurrence ids moved {wrong}; write this to {IDS_PATH}:\n"
                         + json.dumps(current, indent=1))
