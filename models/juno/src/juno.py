"""juno — compact humanoid robotics platform concept.

A sleek research humanoid with Unitree-G1-like proportions: ~1.40 m tall,
athletic stance, exposed cylindrical actuator modules at every joint,
warm-porcelain composite shells over graphite structure with machined
aluminum joint rims, coral accents on repeated functional details, a gloss
midnight-blue sensor visor with cyan pixel-grid eyes, and dexterous
five-digit hands. No logos.

Degrees of freedom (27 body DOF, statically posed):
  - each leg (x2): hip yaw, hip roll, hip pitch, knee pitch,
    ankle pitch, ankle roll                                   -> 12
  - each arm (x2): shoulder pitch, shoulder roll, shoulder yaw,
    elbow pitch, wrist roll, wrist pitch                      -> 12
  - waist yaw                                                 -> 1
  - neck yaw, neck pitch                                      -> 2
  Hands add cosmetic posed finger articulation (not counted).

Coordinates: pelvis waist-yaw joint center = world origin, +X forward,
+Y robot-left, +Z up. Soles rest near z = -876 in the athletic stance.

Chain offsets (parent-local joint origins, mm):
  pelvis:   waist yaw (0,0,0); hip yaw (0,+-90,-120)
  bracket:  hip roll (0,0,-64)
  carrier:  hip pitch (0,0,-78)
  thigh:    knee (0,0,-290)
  shin:     ankle pitch (0,0,-290)
  ankle:    ankle roll (0,0,-30)
  foot:     sole 26 below origin
  torso:    shoulder pitch (0,+-148,290); neck yaw (0,0,324)
  pod:      shoulder roll (0, s*34, -72)
  housing:  shoulder yaw (0,0,-24)
  bicep:    elbow (0,0,-156)
  forearm:  wrist roll (0,0,-150)
  wrist:    wrist pitch (0,0,-28)
  collar:   neck pitch (0,0,46)

Chain offsets and pose angles live in lib/chain.py; juno.urdf and
juno.srdf are directly authored XML artifacts derived from the same spec
(see the ledger comments in those files).

The STEP is written IN THE ATHLETIC STANCE, so the typed mates below
declare that stance as q=0: every mate axis is resolved into world
millimetres at the authored pose, every limit is shifted by the authored
angle, and every SRDF group state is expressed as a DELTA from it.
"""

from __future__ import annotations

import cadgen
from cadgen import build123d as bd
from cadgen import step
from cadgen.assembly import AssemblyHelper

from ankle_link_left import ankle_link_left
from ankle_link_right import ankle_link_right
from bicep_left import bicep_left
from bicep_right import bicep_right
from foot_left import foot_left
from foot_right import foot_right
from forearm_left import forearm_left
from forearm_right import forearm_right
from hand_left import hand_left
from hand_right import hand_right
from head import head
from hip_bracket_left import hip_bracket_left
from hip_bracket_right import hip_bracket_right
from hip_carrier_left import hip_carrier_left
from hip_carrier_right import hip_carrier_right
from neck_collar import neck_collar
from pelvis import pelvis
from shin_left import shin_left
from shin_right import shin_right
from shoulder_pod_left import shoulder_pod_left
from shoulder_pod_right import shoulder_pod_right
from thigh_left import thigh_left
from thigh_right import thigh_right
from torso import torso
from wrist_carrier_left import wrist_carrier_left
from wrist_carrier_right import wrist_carrier_right
from yaw_housing_left import yaw_housing_left
from yaw_housing_right import yaw_housing_right

from lib import chain
from lib.juno_lib import revolute_attach

# Every link is a sibling MODEL (one script per URDF link, part-local frame).
# Calling one inside the body builds it if stale — on its own worker, in
# parallel with the other 27 — or loads it, and the robot links its tree.
# Rebuilding a link alone does not rebuild the robot: rerun this script.
LINKS = {
    "left": {
        "hip_bracket": hip_bracket_left, "hip_carrier": hip_carrier_left,
        "thigh": thigh_left, "shin": shin_left, "ankle_link": ankle_link_left,
        "foot": foot_left, "shoulder_pod": shoulder_pod_left,
        "yaw_housing": yaw_housing_left, "bicep": bicep_left,
        "forearm": forearm_left, "wrist_carrier": wrist_carrier_left,
        "hand": hand_left,
    },
    "right": {
        "hip_bracket": hip_bracket_right, "hip_carrier": hip_carrier_right,
        "thigh": thigh_right, "shin": shin_right, "ankle_link": ankle_link_right,
        "foot": foot_right, "shoulder_pod": shoulder_pod_right,
        "yaw_housing": yaw_housing_right, "bicep": bicep_right,
        "forearm": forearm_right, "wrist_carrier": wrist_carrier_right,
        "hand": hand_right,
    },
}

# ----------------------------------------------------------- pose (degrees)
# Athletic ready stance: knees bent, feet flat, arms relaxed forward.
# Pose angles and chain offsets are shared with the authored URDF/SRDF
# artifacts through lib/chain.py; edit them there.
HIP_PITCH_DEG = chain.HIP_PITCH_DEG
KNEE_DEG = chain.KNEE_DEG
ANKLE_PITCH_DEG = chain.ANKLE_PITCH_DEG
HIP_ROLL_ABDUCT_DEG = chain.HIP_ROLL_ABDUCT_DEG
HIP_YAW_DEG = chain.HIP_YAW_DEG
WAIST_YAW_DEG = chain.WAIST_YAW_DEG
SHOULDER_PITCH_DEG = chain.SHOULDER_PITCH_DEG
SHOULDER_ROLL_ABDUCT_DEG = chain.SHOULDER_ROLL_ABDUCT_DEG
SHOULDER_YAW_INTERNAL_DEG = chain.SHOULDER_YAW_INTERNAL_DEG
ELBOW_DEG = chain.ELBOW_DEG
WRIST_ROLL_DEG = chain.WRIST_ROLL_DEG
WRIST_PITCH_DEG = chain.WRIST_PITCH_DEG
NECK_YAW_DEG = chain.NECK_YAW_DEG
NECK_PITCH_DEG = chain.NECK_PITCH_DEG

HIP_Y = chain.HIP_Y_MM
SHOULDER_Y = chain.SHOULDER_Y_MM

X = chain.X_AXIS
Y = chain.Y_AXIS
Z = chain.Z_AXIS

_s = chain.side_sign


# --------------------------------------------------------------- kinematics
# The 27-DOF body chain IS a tree of revolute mates, so it is declared as
# typed mates rather than re-derived anywhere: the mate list, the URDF and
# the CAD all read lib/chain.py, and cannot drift.
#
# ZERO IS THE ARTIFACT AS WRITTEN. The STEP is baked in the athletic ready
# stance, so each mate's rest value is that stance:
#   - axis   = the joint's world frame AT the authored pose (chain FK), which
#              is exactly the screw axis a product-of-exponentials FK needs;
#   - limits = the URDF travel range minus the authored angle;
#   - poses  = each SRDF group state minus the authored angle.
def _kinematics() -> dict:
    axes = chain.world_joint_axes()
    rest = chain.athletic_ready_deg()
    mates = []
    for joint in chain.all_joints():
        name = joint["name"]
        origin, direction = axes[name]
        lo, hi = joint["range_deg"]
        mates.append(
            cadgen.revolute(
                name,
                parent=f"#{joint['parent']}",
                child=f"#{joint['child']}",
                origin=origin,
                direction=direction,
                limits=(lo - rest[name], hi - rest[name]),
            )
        )
    return {"mates": mates, "poses": chain.named_pose_deltas_deg()}


KINEMATICS = _kinematics()


def assemble() -> bd.Compound:
    asm = AssemblyHelper("juno")

    pelvis_link = asm.add(pelvis(), "pelvis")
    torso_link = asm.add(torso(), "torso")
    revolute_attach(
        asm, pelvis_link, torso_link, "waist_yaw",
        chain.WAIST_YAW_ORIGIN_MM, Z, X, (0, 0, 0), Z, X, WAIST_YAW_DEG,
    )

    collar = asm.add(neck_collar(), "neck_collar")
    revolute_attach(
        asm, torso_link, collar, "neck_yaw",
        chain.NECK_YAW_ORIGIN_MM, Z, X, (0, 0, 0), Z, X, NECK_YAW_DEG,
    )
    head_link = asm.add(head(), "head")
    revolute_attach(
        asm, collar, head_link, "neck_pitch",
        chain.NECK_PITCH_ORIGIN_MM, Y, X, (0, 0, 0), Y, X, NECK_PITCH_DEG,
    )

    for side in ("left", "right"):
        s = _s(side)
        link = LINKS[side]

        # ---- leg chain (6 DOF)
        bracket = asm.add(link["hip_bracket"](), f"hip_bracket_{side}")
        revolute_attach(
            asm, pelvis_link, bracket, f"hip_yaw_{side}",
            (0, s * HIP_Y, chain.HIP_YAW_DROP_Z_MM), Z, X, (0, 0, 0), Z, X, HIP_YAW_DEG,
        )
        carrier = asm.add(link["hip_carrier"](), f"hip_carrier_{side}")
        revolute_attach(
            asm, bracket, carrier, f"hip_roll_{side}",
            chain.HIP_ROLL_ORIGIN_MM, X, Y, (0, 0, 0), X, Y, s * HIP_ROLL_ABDUCT_DEG,
        )
        thigh = asm.add(link["thigh"](), f"thigh_{side}")
        revolute_attach(
            asm, carrier, thigh, f"hip_pitch_{side}",
            chain.HIP_PITCH_ORIGIN_MM, Y, X, (0, 0, 0), Y, X, HIP_PITCH_DEG,
        )
        shin = asm.add(link["shin"](), f"shin_{side}")
        revolute_attach(
            asm, thigh, shin, f"knee_{side}",
            chain.KNEE_ORIGIN_MM, Y, X, (0, 0, 0), Y, X, KNEE_DEG,
        )
        ankle = asm.add(link["ankle_link"](), f"ankle_link_{side}")
        revolute_attach(
            asm, shin, ankle, f"ankle_pitch_{side}",
            chain.ANKLE_PITCH_ORIGIN_MM, Y, X, (0, 0, 0), Y, X, ANKLE_PITCH_DEG,
        )
        foot = asm.add(link["foot"](), f"foot_{side}")
        revolute_attach(
            asm, ankle, foot, f"ankle_roll_{side}",
            chain.ANKLE_ROLL_ORIGIN_MM, X, Y, (0, 0, 0), X, Y, -s * HIP_ROLL_ABDUCT_DEG,
        )

        # ---- arm chain (6 DOF)
        pod = asm.add(link["shoulder_pod"](), f"shoulder_pod_{side}")
        revolute_attach(
            asm, torso_link, pod, f"shoulder_pitch_{side}",
            (0, s * SHOULDER_Y, chain.SHOULDER_PITCH_RAISE_Z_MM), Y, X, (0, 0, 0), Y, X, SHOULDER_PITCH_DEG,
        )
        housing = asm.add(link["yaw_housing"](), f"yaw_housing_{side}")
        revolute_attach(
            asm, pod, housing, f"shoulder_roll_{side}",
            (0, s * chain.SHOULDER_ROLL_Y_MM, chain.SHOULDER_ROLL_Z_MM), X, Y,
            (0, 0, 0), X, Y, s * SHOULDER_ROLL_ABDUCT_DEG,
        )
        bicep = asm.add(link["bicep"](), f"bicep_{side}")
        revolute_attach(
            asm, housing, bicep, f"shoulder_yaw_{side}",
            chain.SHOULDER_YAW_ORIGIN_MM, Z, X, (0, 0, 0), Z, X, -s * SHOULDER_YAW_INTERNAL_DEG,
        )
        forearm = asm.add(link["forearm"](), f"forearm_{side}")
        revolute_attach(
            asm, bicep, forearm, f"elbow_{side}",
            chain.ELBOW_ORIGIN_MM, Y, X, (0, 0, 0), Y, X, ELBOW_DEG,
        )
        wrist = asm.add(link["wrist_carrier"](), f"wrist_carrier_{side}")
        revolute_attach(
            asm, forearm, wrist, f"wrist_roll_{side}",
            chain.WRIST_ROLL_ORIGIN_MM, Z, X, (0, 0, 0), Z, X, WRIST_ROLL_DEG,
        )
        hand = asm.add(link["hand"](), f"hand_{side}")
        revolute_attach(
            asm, wrist, hand, f"wrist_pitch_{side}",
            chain.WRIST_PITCH_ORIGIN_MM, Y, X, (0, 0, 0), Y, X, WRIST_PITCH_DEG,
        )

    return asm.build()


@step(out="../STEP/juno.step", kinematics=KINEMATICS, animation="juno.anim.js")
def juno():
    return assemble()


if __name__ == "__main__":
    juno()
