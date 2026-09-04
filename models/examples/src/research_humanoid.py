"""Production-realistic, adult-scale humanoid research platform.

This is an original STEP-first build123d assembly authored from a blank
mechanical brief.  It does not import or derive geometry from another model.

Coordinate convention
---------------------
+X is robot-left, +Y is forward, +Z is up.  The origin lies on the studio
floor midway between the ankle centers.  Dimensions are millimetres.

Layout
------
The shared builders live in ``lib/research_humanoid_lib.py``; each dexterous
hand is its own model (``research_humanoid_hand_left.py`` /
``_right.py``) that this assembly links.

Articulation contract
---------------------
The body has 28 articulated axes: six per leg, six per arm, two at the waist,
and two at the neck.  Each five-finger hand has 15 additional articulated
axes (three per digit), for 30 hand axes and 58 total modeled joint frames.
"""

from __future__ import annotations

from dataclasses import asdict

from cadgen import step
from cadgen.assembly import AssemblyHelper

from lib.research_humanoid_lib import (
    ANKLES,
    BODY_JOINT_SPECS,
    ELBOWS,
    HAND_JOINT_SPECS,
    HIPS,
    KNEES,
    PALMS,
    SHOULDERS,
    SIDES,
    WRISTS,
    _add_actuator,
    _add_foot,
    _add_head,
    _add_joint_yoke,
    _add_pelvis,
    _add_structural_link,
    _add_torso,
    _distance,
    _relate_revolute,
    _relate_rigid,
)
from research_humanoid_hand_left import research_humanoid_hand_left
from research_humanoid_hand_right import research_humanoid_hand_right

# The hands are sibling models: calling one inside the body builds it if stale
# (on its own worker, alongside the rest) or loads it, and the robot links its
# tree. Rebuilding a hand alone does not rebuild the robot; rerun this script.
HANDS = {"left": research_humanoid_hand_left, "right": research_humanoid_hand_right}


def _add_body_kinematics(
    assembly: AssemblyHelper,
    modules: dict[str, object],
    actuators: dict[str, object],
) -> None:
    """Connect the body as a true proximal-to-distal serial joint graph."""

    specs = {spec.name: spec for spec in BODY_JOINT_SPECS}

    _relate_revolute(assembly, modules["pelvis"], actuators["waist_yaw"], specs["waist_yaw"])
    _relate_revolute(assembly, actuators["waist_yaw"], actuators["waist_pitch"], specs["waist_pitch"])
    _relate_rigid(assembly, actuators["waist_pitch"], modules["torso"], (0.0, 8.0, 1215.0), "waist_to_torso")

    _relate_revolute(assembly, modules["torso"], actuators["neck_yaw"], specs["neck_yaw"])
    _relate_revolute(assembly, actuators["neck_yaw"], actuators["neck_pitch"], specs["neck_pitch"])
    _relate_rigid(assembly, actuators["neck_pitch"], modules["head"], (0.0, 6.0, 1570.0), "neck_to_head")

    for side in SIDES:
        hip_yaw = specs[f"{side}_hip_yaw"]
        hip_roll = specs[f"{side}_hip_roll"]
        hip_pitch = specs[f"{side}_hip_pitch"]
        knee = specs[f"{side}_knee_pitch"]
        ankle_pitch = specs[f"{side}_ankle_pitch"]
        ankle_roll = specs[f"{side}_ankle_roll"]
        shoulder_pitch = specs[f"{side}_shoulder_pitch"]
        shoulder_roll = specs[f"{side}_shoulder_roll"]
        shoulder_yaw = specs[f"{side}_shoulder_yaw"]
        elbow = specs[f"{side}_elbow_pitch"]
        wrist_roll = specs[f"{side}_wrist_roll"]
        wrist_pitch = specs[f"{side}_wrist_pitch"]

        _relate_revolute(assembly, modules["pelvis"], actuators[hip_yaw.name], hip_yaw)
        _relate_revolute(assembly, actuators[hip_yaw.name], actuators[hip_roll.name], hip_roll)
        _relate_revolute(assembly, actuators[hip_roll.name], actuators[hip_pitch.name], hip_pitch)
        _relate_rigid(assembly, actuators[hip_pitch.name], modules[f"{side}_thigh"], HIPS[side], f"{side}_hip_output")
        _relate_revolute(assembly, modules[f"{side}_thigh"], actuators[knee.name], knee)
        _relate_rigid(assembly, actuators[knee.name], modules[f"{side}_shank"], KNEES[side], f"{side}_knee_output")
        _relate_revolute(assembly, modules[f"{side}_shank"], actuators[ankle_pitch.name], ankle_pitch)
        _relate_revolute(assembly, actuators[ankle_pitch.name], actuators[ankle_roll.name], ankle_roll)
        _relate_rigid(assembly, actuators[ankle_roll.name], modules[f"{side}_foot"], ANKLES[side], f"{side}_ankle_output")

        _relate_revolute(assembly, modules["torso"], actuators[shoulder_pitch.name], shoulder_pitch)
        _relate_revolute(assembly, actuators[shoulder_pitch.name], actuators[shoulder_roll.name], shoulder_roll)
        _relate_revolute(assembly, actuators[shoulder_roll.name], actuators[shoulder_yaw.name], shoulder_yaw)
        _relate_rigid(assembly, actuators[shoulder_yaw.name], modules[f"{side}_upper_arm"], SHOULDERS[side], f"{side}_shoulder_output")
        _relate_revolute(assembly, modules[f"{side}_upper_arm"], actuators[elbow.name], elbow)
        _relate_rigid(assembly, actuators[elbow.name], modules[f"{side}_forearm"], ELBOWS[side], f"{side}_elbow_output")
        _relate_revolute(assembly, modules[f"{side}_forearm"], actuators[wrist_roll.name], wrist_roll)
        _relate_revolute(assembly, actuators[wrist_roll.name], actuators[wrist_pitch.name], wrist_pitch)
        _relate_rigid(assembly, actuators[wrist_pitch.name], modules[f"{side}_wrist_carrier"], WRISTS[side], f"{side}_wrist_output")
        _relate_rigid(assembly, modules[f"{side}_wrist_carrier"], modules[f"{side}_hand"], PALMS[side], f"{side}_hand_mount")


def _build_robot() -> object:
    assembly = AssemblyHelper("research_humanoid_28_body_dof_plus_dexterous_hands")
    modules: dict[str, object] = {
        "pelvis": _add_pelvis(assembly),
        "torso": _add_torso(assembly),
        "head": _add_head(assembly),
    }

    for side in SIDES:
        modules[f"{side}_foot"] = _add_foot(assembly, side)
        modules[f"{side}_shank"] = _add_structural_link(
            assembly,
            f"{side}_shank",
            ANKLES[side],
            KNEES[side],
            width=88.0,
            depth=64.0,
            trim_start=54.0,
            trim_end=58.0,
            preferred_x=(1.0, 0.0, 0.0),
            armor_fraction=0.40,
            start_scale=0.82,
            end_scale=1.0,
        )
        modules[f"{side}_thigh"] = _add_structural_link(
            assembly,
            f"{side}_thigh",
            KNEES[side],
            HIPS[side],
            width=100.0,
            depth=74.0,
            trim_start=60.0,
            trim_end=66.0,
            preferred_x=(1.0, 0.0, 0.0),
            armor_fraction=0.38,
            start_scale=0.82,
            end_scale=1.0,
        )
        modules[f"{side}_upper_arm"] = _add_structural_link(
            assembly,
            f"{side}_upper_arm",
            SHOULDERS[side],
            ELBOWS[side],
            width=72.0,
            depth=54.0,
            trim_start=40.0,
            trim_end=42.0,
            preferred_x=(0.0, 1.0, 0.0),
            armor_fraction=0.42,
            start_scale=1.0,
            end_scale=0.78,
        )
        modules[f"{side}_forearm"] = _add_structural_link(
            assembly,
            f"{side}_forearm",
            ELBOWS[side],
            WRISTS[side],
            width=64.0,
            depth=50.0,
            trim_start=38.0,
            trim_end=30.0,
            preferred_x=(0.0, 1.0, 0.0),
            armor_fraction=0.44,
            start_scale=1.0,
            end_scale=0.72,
        )
        modules[f"{side}_wrist_carrier"] = _add_structural_link(
            assembly,
            f"{side}_wrist_carrier",
            WRISTS[side],
            PALMS[side],
            width=46.0,
            depth=40.0,
            trim_start=14.0,
            trim_end=14.0,
            preferred_x=(0.0, 1.0, 0.0),
            armor_fraction=0.24,
            start_scale=1.0,
            end_scale=0.82,
        )
        modules[f"{side}_hand"] = assembly.add(HANDS[side](), "dexterous_hand", side)   # a linked child

    actuators: dict[str, object] = {}
    for spec in BODY_JOINT_SPECS:
        _add_joint_yoke(assembly, spec)
        actuators[spec.name] = _add_actuator(assembly, spec)

    _add_body_kinematics(assembly, modules, actuators)
    robot = assembly.build()
    robot.label = "research_humanoid_28_body_dof_plus_dexterous_hands"
    return robot


def joint_manifest() -> dict[str, list[dict[str, object]]]:
    return {
        "body": [asdict(spec) for spec in BODY_JOINT_SPECS],
        "hands": [asdict(spec) for spec in HAND_JOINT_SPECS],
    }


def design_metrics() -> dict[str, object]:
    return {
        "body_dof": len(BODY_JOINT_SPECS),
        "hand_dof": len(HAND_JOINT_SPECS),
        "total_articulated_axes": len(BODY_JOINT_SPECS) + len(HAND_JOINT_SPECS),
        "standing_height_target_mm": 1730.0,
        "shoulder_center_spacing_mm": abs(SHOULDERS["left"][0] - SHOULDERS["right"][0]),
        "ankle_center_spacing_mm": abs(ANKLES["left"][0] - ANKLES["right"][0]),
        "left_shank_length_mm": round(_distance(ANKLES["left"], KNEES["left"]), 3),
        "left_thigh_length_mm": round(_distance(KNEES["left"], HIPS["left"]), 3),
        "left_upper_arm_length_mm": round(_distance(SHOULDERS["left"], ELBOWS["left"]), 3),
        "left_forearm_length_mm": round(_distance(ELBOWS["left"], WRISTS["left"]), 3),
        "nominal_hand_axes_per_side": 15,
        "nominal_foot_length_mm": 270.0,
    }


@step(out="../STEP/research_humanoid.step")
def research_humanoid() -> object:
    return _build_robot()


if __name__ == "__main__":
    research_humanoid()
