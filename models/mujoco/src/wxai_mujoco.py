"""The WidowX AI's MuJoCo function: the simulator's choices for the arm ``wxai.py`` models.

    python src/wxai_mujoco.py      # writes out/wxai/wxai.xml, its assets/ and a scene.xml

The model (``wxai.py``) holds what is true of the arm: its parts, materials, joints, Trossen's published
ranges, speeds and efforts, its frames and the ``gripper_open`` state. This holds what is chosen for a
simulation of it, on the ``mujoco.MjSpec`` ``spec`` makes of the model, and saves the robot's file.
Nothing here is copied from Menagerie's model or Trossen's URDF.

Collision. Every part keeps its mesh, which MuJoCo collides as its convex hull: the STEP's parts are
blocky envelopes already, so a hull is close for every part but ``link_6`` (its rails and end stops
span +-90 mm in Y: the hull fills the gripper's throat behind the fingers) and ``link_2`` (the hull
fills the step under its shoulder end). The two carriages collide as nothing: each one's rack arm
reaches across to the other side, so their hulls overlap by 18.5 mm as built and would jam the
gripper; they run inside ``link_6``, and the fingers and pads, which carry every contact a grasp
makes, keep theirs.

Joints. One position actuator a joint, its force bounded by the model's effort (``limits`` there,
which the spec carries as each joint's ``actfrcrange``). The stiffnesses are chosen, not measured
(``KP``): 600 N*m/rad for the three 27 N*m joints, so the arm's own weight (about 6 N*m at joint_2 in
the pose below) bends one under a degree; 100 for the three 7 N*m ones; and a carriage's 100 N at
10 mm of error. No joint armature, damping or dry friction is set: Trossen publishes none.

Contact excludes. ``spec`` excludes each pair of jointed bodies whose collisions touch as built, found
on the parts' own meshes, so it excludes ``link_6`` from each carriage's body. With the carriages
colliding as nothing those two pairs no longer touch, and the exclude would also stop a finger (in
its carriage's body) from colliding with ``link_6``: the function removes the two.

The key ``home`` commands a pose with the arm lifted off its folded zero and the gripper half open,
every joint inside its range, the same values as the controls. The two carriages are two joints in
the model (no coupling), so two actuators here.
"""

from __future__ import annotations

import math

import mujoco
from cad.mujoco import collisions, save, spec

from wxai import GRIPPER_TRAVEL, OUT, wxai

KP = {"joint_0": 600.0, "joint_1": 600.0, "joint_2": 600.0, "joint_3": 100.0, "joint_4": 100.0, "joint_5": 100.0,
      "left_carriage_joint": 10000.0, "right_carriage_joint": 10000.0}  # N*m/rad; the carriages' N/m
# The pose the key commands: degrees from the folded zero, and each carriage half way open (m).
REACH = {"joint_0": math.radians(30), "joint_1": math.radians(60), "joint_2": math.radians(45),
         "joint_3": math.radians(20), "joint_4": math.radians(-20), "joint_5": math.radians(45),
         "left_carriage_joint": GRIPPER_TRAVEL / 2000, "right_carriage_joint": GRIPPER_TRAVEL / 2000}


def wxai_mujoco() -> mujoco.MjSpec:
    s = spec(wxai())

    for side in ("left", "right"):
        for geom in collisions(s, f"carriage_{side}"):
            s.delete(geom)
    for exclude in list(s.excludes):
        if exclude.bodyname2.startswith("carriage_"):
            s.delete(exclude)

    for joint in s.joints:
        servo = s.add_actuator(name=joint.name, target=joint.name, trntype=mujoco.mjtTrn.mjTRN_JOINT)
        servo.set_to_position(kp=KP[joint.name], dampratio=1, inheritrange=True)

    pose = [REACH[joint.name] for joint in s.joints]
    s.add_key(name="home", qpos=pose, ctrl=pose)
    return s


if __name__ == "__main__":
    save(wxai_mujoco(), OUT / "wxai.xml")
