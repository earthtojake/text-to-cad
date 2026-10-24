"""The meshes ../juno.urdf references: a 3MF of each link model, in the link's own frame.

Run it after changing a link, before loading the URDF; the URDF scales each mesh by 0.001
(a 3MF is in millimetres).
"""
from pathlib import Path

from cadgen import export

from juno import (
    ankle_link_left,
    ankle_link_right,
    bicep_left,
    bicep_right,
    foot_left,
    foot_right,
    forearm_left,
    forearm_right,
    hand_left,
    hand_right,
    head,
    hip_bracket_left,
    hip_bracket_right,
    hip_carrier_left,
    hip_carrier_right,
    neck_collar,
    pelvis,
    shin_left,
    shin_right,
    shoulder_pod_left,
    shoulder_pod_right,
    thigh_left,
    thigh_right,
    torso,
    wrist_carrier_left,
    wrist_carrier_right,
    yaw_housing_left,
    yaw_housing_right,
)

ROOT = Path(__file__).resolve().parent.parent      # models/juno
LINKS = (pelvis, torso, neck_collar, head, hip_bracket_left, hip_carrier_left, thigh_left,
         shin_left, ankle_link_left, foot_left, shoulder_pod_left, yaw_housing_left, bicep_left,
         forearm_left, wrist_carrier_left, hand_left, hip_bracket_right, hip_carrier_right,
         thigh_right, shin_right, ankle_link_right, foot_right, shoulder_pod_right,
         yaw_housing_right, bicep_right, forearm_right, wrist_carrier_right, hand_right)

if __name__ == "__main__":
    for link in LINKS:
        export(link, ROOT / "3MF" / f"{link.__name__}.3mf")
