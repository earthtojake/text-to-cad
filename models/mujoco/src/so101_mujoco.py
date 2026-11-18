"""The SO-101's MuJoCo function: the simulator's choices for the arm ``so101.py`` models.

    python src/so101_mujoco.py      # writes out/so101/so101.xml, its assets/ and a scene.xml

The model (``so101.py``) holds what is true of the arm: its parts, materials, joints, stops and the
``tcp`` frame. This holds what is chosen for a simulation of it, on the ``mujoco.MjSpec`` ``spec`` makes
of the model, and saves the robot's file. Nothing here is copied from Menagerie's model or the maker's
MJCF; each number names its source.

Collision. The plain export collides each of the 133 parts as its mesh. Here:

- the printed parts keep theirs (MuJoCo collides a mesh as its convex hull; the two jaws are split in
  the model into a cradle and a finger, so each hull leaves the space between the jaws open);
- each servo's three case shells (``CASE``) collide as a box fitted to the shell's exact solid;
- every other part collides as nothing: the motor, board and gears inside a servo's case, its horns
  (inside the printed part they drive), the screws, nuts and connector housings.

Joints. The six servos are one model (Feetech ST3215), so one set of numbers:

- its force bound is the model's (``limits`` there: the stall torque), which the spec carries as each
  joint's ``actfrcrange``;
- ``KP``, the stiffness of its position loop as a simulator's position actuator. Not measured: chosen
  so the arm stretched out level sags under 1 degree at the shoulder (the arm's own gravity torque
  there, about 0.87 N*m, over ``KP``), and well under the stall torque for a 10 degree error;
No joint armature, damping or dry friction is set: nobody has measured them on this servo, and the arm
holds its pose without them (``check.py``; the integrator is the export's ``implicitfast``, which
takes the actuator's damping implicitly).

The key ``home`` commands a pose with the arm lifted off its rest and the jaw half open: every joint
at an angle inside its stops, the same angles as the controls.
"""

from __future__ import annotations

import math

import mujoco
from cad.mujoco import collisions, fit, parts, save, spec

from so101 import CASE, OUT, PRINTED, _slug, so101

KP = 60.0  # N*m/rad: the position loop's stiffness (chosen, see the module's words)
TIMESTEP = 0.002  # s: MuJoCo's default, said so a reader of the file sees it
# The pose the key commands, degrees from the STEP pose, each inside the joint's stops.
REACH = {"shoulder_pan": 30, "shoulder_lift": -60, "elbow_flex": 60, "wrist_flex": 30, "wrist_roll": 45,
         "gripper": 30}


def so101_mujoco() -> mujoco.MjSpec:
    s = spec(so101())
    s.option.timestep = TIMESTEP

    # Collision: printed parts as their meshes, servo cases as boxes, everything else as nothing.
    printed = {_slug(name) for names in PRINTED.values() for name in names}
    case = tuple(_slug(prefix) for prefix in CASE)
    for path in parts(s):
        label = path.rsplit("/", 1)[-1]
        if label in printed or label.removesuffix("_cradle").removesuffix("_finger") in printed:
            continue
        servo_part = label.partition("_")[2].partition("_")[2] if label.startswith("st3215_") else ""
        if servo_part.startswith(case):
            fit(s, path, "box")
        else:
            for geom in collisions(s, path):
                s.delete(geom)

    # The servos: one position actuator a joint (the model's stall torque bounds its force).
    for joint in s.joints:
        servo = s.add_actuator(name=joint.name, target=joint.name, trntype=mujoco.mjtTrn.mjTRN_JOINT)
        servo.set_to_position(kp=KP, dampratio=1, inheritrange=True)

    angles = [math.radians(REACH[joint.name]) for joint in s.joints]
    s.add_key(name="home", qpos=angles, ctrl=angles)
    return s


if __name__ == "__main__":
    save(so101_mujoco(), OUT / "so101.xml")
