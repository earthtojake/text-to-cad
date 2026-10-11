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

import functools
import math
from typing import NamedTuple

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


# ---------------------------------------------------------------------------
# Animation: clips sampled to keyframes when the model builds.
#
# The STEP is baked in the athletic ready stance, so every clip recomputes
# the full chain FK at (athletic pose + its deltas) and moves each link
# subtree by the rigid delta T_target * inverse(T_athletic) in the fixed model
# frame (mm, +X forward, +Y robot-left, +Z up, pelvis waist-yaw center at the
# origin). The FK walks lib/chain.py's joint table and athletic angles, the
# spec the mates are declared from; the clips describe the motion in it
# rather than driving the mates. Seven clips: four in-place gaits (walk,
# stride, run, jump) and three showpieces (Elvis dance, handstand, karate
# kick), each a pure function of t that starts and ends in the athletic
# stance.
#
# Gait design: an in-place march. Each leg swings inside its own window of
# the cycle with a raised-cosine envelope that starts and ends at zero, and
# is EXACTLY at the athletic pose for the rest of the cycle, so the stance
# foot stays planted on the ground with no IK. The pelvis root is static for
# the same reason. Arms swing continuously, antiphase to their own-side leg;
# the torso counter-rotates about the waist with a hint of roll, and the neck
# compensates so the head keeps facing forward.
# ---------------------------------------------------------------------------

# Gait amplitudes (deg). Sign conventions follow the chain ledger: pitch about
# +Y (negative = forward), roll about +X (positive = toward robot-left), yaw
# about +Z (positive = turn left).
HIP_LIFT_DEG = 24.0      # swing-leg thigh raise (forward = negative pitch)
KNEE_FOLD_DEG = 44.0     # extra swing-leg knee flexion
TOE_POINT_DEG = 8.0      # slight toes-down of the airborne foot
ARM_SWING_DEG = 12.0     # shoulder pitch swing, antiphase to own-side leg
ELBOW_EXTRA_DEG = 10.0   # extra elbow flexion on the forward arm swing
WAIST_SWAY_DEG = 4.0     # torso counter-rotation about the waist yaw axis
TORSO_ROLL_DEG = 1.2     # weight-shift hint, roll about +X at the waist
NECK_COMPENSATION = 0.8  # head stabilization fraction against waist sway

# Swing windows of the normalized cycle (left lifts first), with
# double-support dwell between them.
SWING = {"left": (0.05, 0.45), "right": (0.55, 0.95)}

# The leg's two IK segments (hip pitch to knee, knee to ankle pitch), and the
# foot points the contacts use, in the foot frame (origin at the ankle-roll
# center): the sole's front edge and half width (the sole plate in
# lib/legs.py), and the ankle-pitch joint's height over a flat sole.
THIGH_MM = -chain.KNEE_ORIGIN_MM[2]
SHIN_MM = -chain.ANKLE_PITCH_ORIGIN_MM[2]
TOE_EDGE_X_MM = 112.0
SOLE_HALF_WIDTH_MM = 35.0
ANKLE_OVER_SOLE_MM = -chain.ANKLE_ROLL_ORIGIN_MM[2] + chain.SOLE_BELOW_FOOT_MM
TOE_LOCAL_MM = (TOE_EDGE_X_MM, 0.0, -chain.SOLE_BELOW_FOOT_MM)
# The hip-roll joint's height in the pelvis frame: the lateral pendulum for
# weight shifts. Rolling there (with the ankle roll compensating) moves the
# planted sole sideways by about (sole z - HIP_ROLL_Z_MM) * sin(roll).
HIP_ROLL_Z_MM = chain.HIP_YAW_DROP_Z_MM + chain.HIP_ROLL_ORIGIN_MM[2]

# Stride gait (treadmill-style walk in place): the stance foot slides
# backward flat on the ground while the swing leg passes through the air,
# both solved with planar two-link leg IK in each leg's (slightly rolled)
# sagittal plane. The athletic stance is exactly the IK solution at stride
# center.
STRIDE_MM = 230.0          # stride length (at most 300 keeps the IK in reach)
STANCE_FRACTION = 0.58     # ground-contact share of each leg cycle
STRIDE_LIFT_MM = 60.0      # swing-foot apex clearance
STRIDE_TOE_OFF_DEG = 14.0  # toes-down just after toe-off
STRIDE_HEEL_DEG = 10.0     # toes-up heel-first approach to contact
STRIDE_ARM_FACTOR = 1.5    # arms swing wider with long strides
STRIDE_SWAY_FACTOR = 1.25
STRIDE_PHASE = {"left": 0.0, "right": 0.5}
# Mid-swing cycle positions (offset + stance + half the swing window).
STRIDE_MID_SWING = {
    side: (STRIDE_PHASE[side] + STANCE_FRACTION + (1 - STANCE_FRACTION) / 2) % 1.0
    for side in chain.SIDES
}

# Run gait: short ground contacts with a FLIGHT phase between them (both feet
# airborne), a vertical body bounce absorbed by the stance-leg IK (lowest at
# mid-stance, highest at mid-flight), toe-pivot heel-off into push-off, high
# heel-recovery swing, forward torso lean, and pumping bent arms. Foot contact
# lands slightly ahead of the hip and pushes off well behind it (asymmetric
# split of the stride travel).
RUN_STANCE_FRACTION = 0.35
RUN_PHASE = {"left": 0.0, "right": 0.5}
RUN_MID_STANCE = {side: (RUN_PHASE[side] + RUN_STANCE_FRACTION / 2) % 1.0 for side in chain.SIDES}
RUN_MID_SWING = {
    side: (RUN_PHASE[side] + RUN_STANCE_FRACTION + (1 - RUN_STANCE_FRACTION) / 2) % 1.0
    for side in chain.SIDES
}
RUN_CONTACT_SHARE = 0.3     # stride share landing ahead of the hip
RUN_BOUNCE_MM = 22.0        # body bounce amplitude
RUN_APEX_MM = 140.0         # swing-ankle apex over flat stance (heel tuck)
RUN_HEEL_OFF_DEG = 26.0     # toe-pivot heel rise into push-off
RUN_HEEL_OFF_START = 0.62   # stance progress where the heel starts rising
RUN_HEEL_IN_DEG = 8.0       # toes-up into the next contact
RUN_LEAN_DEG = 7.0          # forward torso lean (waist pitch extra)
RUN_ARM_SWING_DEG = 26.0    # shoulder pump amplitude
RUN_ELBOW_BASE_DEG = -60.0  # extra constant elbow flexion (runner's arms)
RUN_ELBOW_PUMP_DEG = 15.0   # extra flexion on the forward pump
RUN_SWAY_DEG = 5.0          # waist yaw counter-rotation
RUN_ROLL_DEG = 1.6          # lean toward the stance side

# Jump gait: countermovement crouch -> push -> ballistic flight with toe point
# and leg tuck -> springy landing (underdamped body-height response absorbed
# by the leg IK) -> recover. Arms swing back in the crouch, sweep overhead for
# the flight ("hands in the air"), dip with the landing spring, and settle
# back. Both legs work symmetrically; takeoff and landing fall out of the IK
# reach clamp (targets go out of reach -> legs straight -> feet leave/meet
# the ground smoothly).
JUMP_TIMING = (0.18, 0.3, 0.62, 0.74)  # where the crouch, push, flight and absorb end
JUMP_CROUCH_MM = 120.0            # countermovement depth
JUMP_TAKEOFF_MM = 20.0            # body rise at full leg extension (reach limit)
JUMP_APEX_MM = 160.0              # ballistic apex above standing
JUMP_TUCK_MM = 250.0              # mid-flight ankle tuck toward the body
JUMP_TOE_POINT_DEG = 25.0         # toes point down in the air
JUMP_LAND_DIP_MM = -80.0          # first landing compression
JUMP_SPRING_DECAY = 3.5           # landing spring: exp decay rate ...
JUMP_SPRING_CYCLES = 1.25         # ... and bounce count (ends at zero crossing)
JUMP_ARM_BACK_DEG = 30.0          # crouch arm backswing (shoulder pitch)
JUMP_ARM_UP_DEG = -155.0          # overhead shoulder pitch in flight
JUMP_ARM_V_DEG = 20.0             # shoulder roll abduction for an overhead V
JUMP_ARM_SPRING_DEG_PER_MM = 0.3  # landing arm dip coupled to body spring
JUMP_LEAN_DEG = 8.0               # crouch/landing forward lean
JUMP_HEAD_UP_DEG = -8.0           # look up slightly while airborne

# Karate kick: weight shifts over the left leg, the right leg chambers and
# snaps a front kick at hip height with a guard up.
KICK_WEIGHT_SHIFT_MM = 42.0
KICK_DIP_MM = 18.0
KICK_CHAMBER_HIP_DEG = -70.0
KICK_CHAMBER_KNEE_DEG = 115.0
KICK_CHAMBER_ANKLE_DEG = 10.0
KICK_EXTEND_HIP_DEG = -20.0    # added on top of the chamber
KICK_EXTEND_KNEE_DEG = -105.0  # snaps the shin out nearly straight
KICK_EXTEND_ANKLE_DEG = -25.0  # ball-of-foot strike (toes pulled back)
KICK_GUARD_SHOULDER_DEG = -45.0
KICK_GUARD_ELBOW_DEG = -105.0
KICK_GUARD_ROLL_OUT_DEG = 18.0
KICK_HIP_TURN_DEG = -14.0      # hips rotate into the kick
KICK_LEAN_BACK_DEG = -7.0      # counterbalance during the snap

# Handstand: keyframed root rotation about +Y with contact anchoring --
# toe-pinned while folding, palm-pinned once the hands plant.
HS_PLANT_X_MM = 430.0  # hand plant line in front of the feet
# Palm contact point in the hand frame: the hands plant palm-down with the
# fingers pointing forward (total hand pitch -90 at the hold), so contact is
# on the local -x palm face -- the one extent that is symmetric between the
# two hands (the posed finger curl differs in local z).
HS_PALM_LOCAL_MM = (-35.0, 0.0, -70.0)
HS_WOBBLE_DEG = 1.6  # leg wobble while holding the stand

# Elvis dance (4 beats): weight over the right leg, left leg kicked out to
# the left planted on a pointed toe (closed-form lateral+sagittal leg IK),
# rubber-leg shake, right arm pointing up to the right with a beat pulse, hip
# swivel, head turned toward the pointing hand.
ELVIS_BEATS = 4
ELVIS_WEIGHT_SHIFT_MM = -55.0    # pelvis shifts over the right leg
ELVIS_DIP_MM = 20.0              # settled crouch on the stance leg
ELVIS_BOUNCE_MM = 8.0            # beat bounce on top of the dip
ELVIS_TOE_X_MM = 80.0            # kicked-out toe plant, forward of the hips
ELVIS_TOE_Y_MM = 330.0           # ... and out to the robot-left
ELVIS_TOE_SHAKE_MM = 28.0        # rubber-leg lateral toe shake (2x beat)
ELVIS_TOE_LIFT_MM = 45.0         # lift bump while the toe travels out and back
ELVIS_FOOT_POINT_DEG = 55.0      # pointed toe of the kicked-out foot
ELVIS_FOOT_POINT_SHAKE_DEG = 7.0
ELVIS_POINT_ROLL_DEG = -115.0    # right arm raised out-and-up to the right
ELVIS_POINT_PITCH_DEG = -25.0
ELVIS_POINT_ELBOW_DEG = -12.0    # nearly straight: the finger points
ELVIS_POINT_PULSE_DEG = 8.0      # beat pulse of the pointing arm
ELVIS_OFF_ARM_PITCH_DEG = -30.0  # left arm low and bent across
ELVIS_OFF_ARM_ELBOW_DEG = -70.0
ELVIS_TWIST_DEG = 10.0           # hip swivel via the waist
ELVIS_LEAN_RIGHT_DEG = -3.0      # lean into the point
ELVIS_HEAD_TURN_DEG = -20.0      # look toward the pointing hand
ELVIS_CHIN_UP_DEG = -5.0

JOINTS = chain.all_joints()
ATHLETIC_ANGLES = chain.athletic_ready_deg()
_IDENTITY3 = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))


def _rot(axis: tuple[float, float, float], deg: float) -> tuple:
    """Rotation matrix about a principal axis."""
    rad = math.radians(deg)
    c, s = math.cos(rad), math.sin(rad)
    if axis == X:
        return ((1.0, 0.0, 0.0), (0.0, c, -s), (0.0, s, c))
    if axis == Y:
        return ((c, 0.0, s), (0.0, 1.0, 0.0), (-s, 0.0, c))
    return ((c, -s, 0.0), (s, c, 0.0), (0.0, 0.0, 1.0))


def _mat_mul(a, b) -> tuple:
    return tuple(
        tuple(a[i][0] * b[0][j] + a[i][1] * b[1][j] + a[i][2] * b[2][j] for j in range(3))
        for i in range(3)
    )


def _mat_vec(a, v) -> tuple:
    return tuple(a[i][0] * v[0] + a[i][1] * v[1] + a[i][2] * v[2] for i in range(3))


def _clamp(value: float, lo: float, hi: float) -> float:
    return min(max(value, lo), hi)


def _lerp(a: float, b: float, u: float) -> float:
    return a + (b - a) * u


def _smooth01(value: float) -> float:
    u = _clamp(value, 0.0, 1.0)
    return u * u * (3.0 - 2.0 * u)


def _pulse(u: float, in_start: float, in_end: float, out_start: float, out_end: float) -> float:
    """Smooth on/off window: ramps up over [in_start, in_end], back down over
    [out_start, out_end], zero outside."""
    rise = _smooth01((u - in_start) / (in_end - in_start))
    fall = _smooth01((u - out_start) / (out_end - out_start))
    return rise * (1.0 - fall)


def _fk_frames(
    angles: dict[str, float],
    *,
    lean_deg: float = 0.0,
    roll_deg: float = 0.0,
    root: tuple[float, float, float] = (0.0, 0.0, 0.0),
    root_pitch_deg: float = 0.0,
) -> dict[str, tuple]:
    """World frame (R, p) of every link at a joint pose. lean_deg / roll_deg
    fold small artistic +Y / +X rotations in at the waist (torso lean and
    weight shift); root translates the pelvis (body bounce in the air gaits,
    which the stance-leg IK absorbs on the ground side); root_pitch_deg turns
    the whole body about +Y at the pelvis (the handstand inversion, whose
    callers solve the matching root so the contacts stay put)."""
    frames = {"pelvis": (_rot(Y, root_pitch_deg) if root_pitch_deg else _IDENTITY3, tuple(root))}
    for joint in JOINTS:
        parent_r, parent_p = frames[joint["parent"]]
        offset = _mat_vec(parent_r, joint["origin_mm"])
        r = _mat_mul(parent_r, _rot(joint["axis"], angles[joint["name"]]))
        if joint["name"] == "waist_yaw":
            if lean_deg:
                r = _mat_mul(r, _rot(Y, lean_deg))
            if roll_deg:
                r = _mat_mul(r, _rot(X, roll_deg))
        frames[joint["child"]] = (r, (parent_p[0] + offset[0], parent_p[1] + offset[1], parent_p[2] + offset[2]))
    return frames


def _world_point(frames: dict[str, tuple], link: str, local: tuple) -> tuple:
    r, p = frames[link]
    v = _mat_vec(r, local)
    return (v[0] + p[0], v[1] + p[1], v[2] + p[2])


ATHLETIC_FRAMES = _fk_frames(ATHLETIC_ANGLES)
# The athletic left toe edge: the handstand pivots there, and the Elvis
# kick-out toe starts and ends its path there so the dance rests exactly on
# the athletic stance.
ATHLETIC_TOE = _world_point(ATHLETIC_FRAMES, "foot_left", TOE_LOCAL_MM)


class _LegRig(NamedTuple):
    hip_z: float          # hip-pitch joint center height
    cos_roll: float       # the sagittal plane is rolled by the hip abduction
    sole_z: float         # the ground: the athletic sole plane
    ankle_to_sole: float  # ankle-pitch joint height over a flat sole


def _leg_rig(side: str) -> _LegRig:
    """Per-side leg-IK constants from the athletic FK: the hip-pitch joint
    center stays fixed in the world (static pelvis, athletic hip yaw/roll),
    and the compensated ankle roll keeps the foot flat, so the ankle-pitch
    target maps exactly onto the rolled sagittal plane. The ankle-roll drop
    is still rolled by the hip roll; the sole sits below the
    roll-compensated (world-aligned) foot frame."""
    foot_r, foot_p = ATHLETIC_FRAMES[f"foot_{side}"]
    cos_roll = math.cos(math.radians(_s(side) * HIP_ROLL_ABDUCT_DEG))
    return _LegRig(
        hip_z=ATHLETIC_FRAMES[f"thigh_{side}"][1][2],
        cos_roll=cos_roll,
        sole_z=foot_p[2] + _mat_vec(foot_r, (0.0, 0.0, -chain.SOLE_BELOW_FOOT_MM))[2],
        ankle_to_sole=-chain.ANKLE_ROLL_ORIGIN_MM[2] * cos_roll + chain.SOLE_BELOW_FOOT_MM,
    )


LEG_RIG = {side: _leg_rig(side) for side in chain.SIDES}


def _leg_pitch_ik(dx: float, d: float, foot_pitch_deg: float) -> tuple[float, float, float]:
    """Two-link planar leg IK in the rolled sagittal plane, targeting the
    ankle-pitch joint at forward offset dx (mm, from the hip-pitch joint) and
    plane depth d (mm); foot_pitch_deg is the desired world pitch of the
    foot. Returns (hip pitch, knee, ankle pitch) in the chain's conventions
    (hip negative = forward, knee positive = flexion)."""
    dist = _clamp(math.hypot(dx, d), abs(THIGH_MM - SHIN_MM) + 1.0, THIGH_MM + SHIN_MM - 1.0)
    phi = math.atan2(dx, d)  # forward angle of the hip->ankle line from straight down
    thigh2, shin2 = THIGH_MM * THIGH_MM, SHIN_MM * SHIN_MM
    cos_interior = _clamp((thigh2 + shin2 - dist * dist) / (2.0 * THIGH_MM * SHIN_MM), -1.0, 1.0)
    knee = math.pi - math.acos(cos_interior)  # knee flexion, >= 0 (the knee bends forward)
    cos_beta = _clamp((thigh2 + dist * dist - shin2) / (2.0 * THIGH_MM * dist), -1.0, 1.0)
    thigh = phi + math.acos(cos_beta)  # thigh angle from straight down, + forward
    hip_deg, knee_deg = -math.degrees(thigh), math.degrees(knee)
    return hip_deg, knee_deg, foot_pitch_deg - (hip_deg + knee_deg)


def _set_leg(angles: dict[str, float], side: str, ik: tuple[float, float, float]) -> None:
    angles[f"hip_pitch_{side}"], angles[f"knee_{side}"], angles[f"ankle_pitch_{side}"] = ik


def _swing_envelope(phase: float, window: tuple[float, float]) -> float:
    """Raised-cosine swing envelope: 0 at lift-off and touch-down, 1
    mid-swing, identically 0 outside the window so the stance foot never
    moves."""
    start, end = window
    if phase <= start or phase >= end:
        return 0.0
    u = (phase - start) / (end - start)
    lobe = math.sin(math.pi * u)
    return lobe * lobe


def _forwardness(phase: float, peak: float) -> float:
    """Cosine forwardness peaking at the given cycle position."""
    return math.cos(math.tau * (phase - peak))


# ----------------------------------------------------------------- gaits
# Each takes the cycle phase in [0, 1) and returns every link's frame.


def _walk(phase: float) -> dict[str, tuple]:
    """Continuous march loop: alternating leg lift with planted stance feet,
    antiphase arm swing, torso counter-sway, and a head that keeps facing
    forward."""
    angles = dict(ATHLETIC_ANGLES)
    for side in chain.SIDES:
        env = _swing_envelope(phase, SWING[side])
        hip = -HIP_LIFT_DEG * env
        knee = KNEE_FOLD_DEG * env
        angles[f"hip_pitch_{side}"] += hip
        angles[f"knee_{side}"] += knee
        # Cancel hip+knee so the airborne foot stays near level, then point
        # the toes down a touch mid-swing.
        angles[f"ankle_pitch_{side}"] += -(hip + knee) + TOE_POINT_DEG * env
        # Arms swing antiphase to the own-side leg: the left arm leads when
        # the right leg lifts (left swing centered at 0.25, right at 0.75).
        own_leg_peak = 0.25 if side == "left" else 0.75
        arm_forward = _forwardness(phase, own_leg_peak + 0.5)
        angles[f"shoulder_pitch_{side}"] += -ARM_SWING_DEG * arm_forward
        angles[f"elbow_{side}"] += -ELBOW_EXTRA_DEG * max(0.0, arm_forward)
    # Torso counter-rotation: turning left brings the right shoulder forward
    # exactly while the left leg swings; the neck compensates most of it so
    # the head keeps facing forward.
    sway = WAIST_SWAY_DEG * math.sin(math.tau * phase)
    angles["waist_yaw"] += sway
    angles["neck_yaw"] += -sway * NECK_COMPENSATION
    # Lean toward the stance side: negative roll (lean robot-right) while the
    # left leg is lifted at phase 0.25.
    return _fk_frames(angles, roll_deg=-TORSO_ROLL_DEG * math.sin(math.tau * phase))


def _stride(phase: float) -> dict[str, tuple]:
    """Bigger strides: legs sweep back and forward with the stance foot
    sliding flat on the ground, wider arm swing, stronger torso counter-sway.
    The stance foot slides backward from +stride/2 to -stride/2; the swing
    leg returns through the air with toe-off and heel-strike accents, and the
    two halves meet in position, so the loop is seamless."""
    angles = dict(ATHLETIC_ANGLES)
    for side in chain.SIDES:
        rig = LEG_RIG[side]
        q = (phase + STRIDE_PHASE[side]) % 1.0
        if q < STANCE_FRACTION:
            ankle_x = STRIDE_MM / 2 - STRIDE_MM * (q / STANCE_FRACTION)  # front contact -> push-off behind
            sole_z = rig.sole_z
            foot_pitch = 0.0
        else:
            u = (q - STANCE_FRACTION) / (1 - STANCE_FRACTION)
            ankle_x = -STRIDE_MM / 2 + STRIDE_MM * _smooth01(u)
            lobe = math.sin(math.pi * u)
            sole_z = rig.sole_z + STRIDE_LIFT_MM * lobe
            # Toes down right after toe-off, toes up (heel first) into contact.
            foot_pitch = STRIDE_TOE_OFF_DEG * lobe * (1 - u) - STRIDE_HEEL_DEG * lobe * u
        depth = (rig.hip_z - (sole_z + rig.ankle_to_sole)) / rig.cos_roll
        # ankle_x is relative to the hip-pitch joint; the athletic ankle sits
        # exactly under the hip, so a zero stride reproduces the athletic legs.
        _set_leg(angles, side, _leg_pitch_ik(ankle_x, depth, foot_pitch))
        # Arms counter the opposite leg: forward peak at the other side's
        # mid-swing, wider than the march to match the longer stride.
        other = "right" if side == "left" else "left"
        arm_forward = _forwardness(phase, STRIDE_MID_SWING[other]) * STRIDE_ARM_FACTOR
        angles[f"shoulder_pitch_{side}"] += -ARM_SWING_DEG * arm_forward
        angles[f"elbow_{side}"] += -ELBOW_EXTRA_DEG * max(0.0, arm_forward)
    # Shoulder girdle counters the hips: the right shoulder leads while the
    # right arm swings forward (right-arm peak == left leg mid-swing), and the
    # torso leans toward the stance side, robot-right while the left leg swings.
    counter = _forwardness(phase, STRIDE_MID_SWING["left"])
    sway = WAIST_SWAY_DEG * STRIDE_SWAY_FACTOR * counter
    angles["waist_yaw"] += sway
    angles["neck_yaw"] += -sway * NECK_COMPENSATION
    return _fk_frames(angles, roll_deg=-TORSO_ROLL_DEG * STRIDE_SWAY_FACTOR * counter)


def _run_stance(s: float, rig: _LegRig) -> tuple[float, float, float]:
    """Stance-foot target (ankle x, ankle z, foot pitch) at stance progress s,
    with a toe-pivot heel-off: the foot pivots about the sole's front edge so
    the heel rises into push-off without the toe digging below the ground."""
    flat_x = STRIDE_MM * RUN_CONTACT_SHARE - STRIDE_MM * s
    pitch = 0.0
    if s > RUN_HEEL_OFF_START:
        pitch = RUN_HEEL_OFF_DEG * _smooth01((s - RUN_HEEL_OFF_START) / (1 - RUN_HEEL_OFF_START))
    c, sn = math.cos(math.radians(pitch)), math.sin(math.radians(pitch))
    # The ankle sits TOE_EDGE_X_MM behind and ANKLE_OVER_SOLE_MM above the
    # toe pivot when the foot is flat.
    ankle_x = flat_x + TOE_EDGE_X_MM * (1 - c) + ANKLE_OVER_SOLE_MM * sn
    ankle_z = rig.sole_z + TOE_EDGE_X_MM * sn + rig.ankle_to_sole * c
    return ankle_x, ankle_z, pitch


def _run(phase: float) -> dict[str, tuple]:
    """Running cadence with flight phases: body bounce, toe-pivot push-off,
    high heel recovery, forward lean, and pumping bent arms."""
    angles = dict(ATHLETIC_ANGLES)
    # Twice per cycle: lowest at each mid-stance, highest at mid-flight.
    bounce = -RUN_BOUNCE_MM * math.cos(4.0 * math.pi * (phase - RUN_MID_STANCE["left"]))
    for side in chain.SIDES:
        rig = LEG_RIG[side]
        q = (phase + RUN_PHASE[side]) % 1.0
        if q < RUN_STANCE_FRACTION:
            ankle_x, ankle_z, pitch = _run_stance(q / RUN_STANCE_FRACTION, rig)
        else:
            # Swing: from push-off to the next contact over a high heel tuck.
            u = (q - RUN_STANCE_FRACTION) / (1 - RUN_STANCE_FRACTION)
            k = _smooth01(u)
            lobe = math.sin(math.pi * u)
            off_x, off_z, off_pitch = _run_stance(1.0, rig)
            ankle_x = _lerp(off_x, STRIDE_MM * RUN_CONTACT_SHARE, k)
            ankle_z = _lerp(off_z, rig.sole_z + rig.ankle_to_sole, k) + RUN_APEX_MM * lobe
            pitch = off_pitch * (1 - k) * (1 - k) - RUN_HEEL_IN_DEG * lobe * u
        depth = (rig.hip_z + bounce - ankle_z) / rig.cos_roll
        _set_leg(angles, side, _leg_pitch_ik(ankle_x, depth, pitch))
        # Runner's arm pump: bent elbows, antiphase to the own-side leg.
        other = "right" if side == "left" else "left"
        arm_forward = _forwardness(phase, RUN_MID_SWING[other])
        angles[f"shoulder_pitch_{side}"] += -RUN_ARM_SWING_DEG * arm_forward
        angles[f"elbow_{side}"] += RUN_ELBOW_BASE_DEG - RUN_ELBOW_PUMP_DEG * max(0.0, arm_forward)
    # Shoulder girdle counters the hips; the head keeps level against both
    # the sway and the forward lean.
    sway = RUN_SWAY_DEG * _forwardness(phase, RUN_MID_SWING["left"])
    angles["waist_yaw"] += sway
    angles["neck_yaw"] += -sway * NECK_COMPENSATION
    angles["neck_pitch"] += -RUN_LEAN_DEG * NECK_COMPENSATION
    # Constant forward lean plus a lean toward the stance side.
    roll = RUN_ROLL_DEG * _forwardness(phase, RUN_MID_STANCE["left"])
    return _fk_frames(angles, lean_deg=RUN_LEAN_DEG, roll_deg=roll, root=(0.0, 0.0, bounce))


def _jump_body_z(p: float) -> float:
    """Pelvis height over the jump cycle."""
    crouch, push, land, absorb = JUMP_TIMING
    if p < crouch:
        return -JUMP_CROUCH_MM * _smooth01(p / crouch)
    if p < push:
        return _lerp(-JUMP_CROUCH_MM, JUMP_TAKEOFF_MM, _smooth01((p - crouch) / (push - crouch)))
    if p < land:
        # Ballistic parabola between takeoff and landing at the same height.
        u = (p - push) / (land - push)
        return JUMP_TAKEOFF_MM + (JUMP_APEX_MM - JUMP_TAKEOFF_MM) * (1 - (2 * u - 1) * (2 * u - 1))
    if p < absorb:
        # Impact: ride down into the first compression.
        return _lerp(JUMP_TAKEOFF_MM, JUMP_LAND_DIP_MM, _smooth01((p - land) / (absorb - land)))
    # Springy recovery: underdamped wobble that ends exactly at zero.
    u = (p - absorb) / (1 - absorb)
    return JUMP_LAND_DIP_MM * math.exp(-JUMP_SPRING_DECAY * u) * math.cos(math.tau * JUMP_SPRING_CYCLES * u)


def _jump_shoulder_pitch(p: float, body_z: float) -> float:
    """Arms: backswing in the crouch, sweep overhead for the flight, dip with
    the landing spring, settle back to athletic by the end of the cycle."""
    crouch, push, land, absorb = JUMP_TIMING
    if p < crouch:
        return _lerp(SHOULDER_PITCH_DEG, JUMP_ARM_BACK_DEG, _smooth01(p / crouch))
    if p < push:
        return _lerp(JUMP_ARM_BACK_DEG, JUMP_ARM_UP_DEG, _smooth01((p - crouch) / (push - crouch)))
    if p < land:
        return JUMP_ARM_UP_DEG
    # Dip with the impact: arms lower in proportion to the body drop.
    dipped = JUMP_ARM_UP_DEG + abs(min(0.0, body_z)) * JUMP_ARM_SPRING_DEG_PER_MM
    if p < absorb:
        return dipped
    return _lerp(dipped, SHOULDER_PITCH_DEG, _smooth01((p - absorb) / (1 - absorb)))


def _jump(phase: float) -> dict[str, tuple]:
    """Crouch, leap with hands overhead, and land with a springy
    knee-absorbed wobble before settling back to the ready stance."""
    _crouch, push, land, _absorb = JUMP_TIMING
    angles = dict(ATHLETIC_ANGLES)
    body_z = _jump_body_z(phase)
    flight = (phase - push) / (land - push) if push < phase < land else 0.0
    tuck = math.sin(math.pi * flight)
    # Overhead V: pitch sweeps the arms up; roll spreads them outward in
    # proportion to how raised they are.
    shoulder_pitch = _jump_shoulder_pitch(phase, body_z)
    raised = _clamp((shoulder_pitch - SHOULDER_PITCH_DEG) / (JUMP_ARM_UP_DEG - SHOULDER_PITCH_DEG), 0.0, 1.0)
    for side in chain.SIDES:
        rig = LEG_RIG[side]
        # Feet stay planted under the hips; in flight the ankle target rises
        # (tuck) and the IK reach clamp straightens the legs at takeoff and
        # landing.
        ankle_z = rig.sole_z + rig.ankle_to_sole + (JUMP_TUCK_MM * tuck if flight > 0 else 0.0)
        pitch = JUMP_TOE_POINT_DEG * tuck if flight > 0 else 0.0
        depth = (rig.hip_z + body_z - ankle_z) / rig.cos_roll
        _set_leg(angles, side, _leg_pitch_ik(0.0, depth, pitch))
        angles[f"shoulder_pitch_{side}"] = shoulder_pitch
        angles[f"shoulder_roll_{side}"] += _s(side) * JUMP_ARM_V_DEG * raised
        angles[f"elbow_{side}"] = ELBOW_DEG + 5.0 * raised
    # Look up a touch while airborne.
    angles["neck_pitch"] += JUMP_HEAD_UP_DEG * tuck
    # Lean into the crouch and the landing compression, upright in the air.
    compression = _clamp(-min(0.0, body_z) / JUMP_CROUCH_MM, 0.0, 1.2)
    return _fk_frames(angles, lean_deg=JUMP_LEAN_DEG * compression * (1 - flight), root=(0.0, 0.0, body_z))


# ------------------------------------------------------------ showpieces


def _planted_leg(side: str, body_z: float, dy: float) -> dict[str, float]:
    """Planted-leg solve shared by the kick support leg and the dance: the
    pitch IK keeps the sole at ground height under a bobbing pelvis, and a
    hip/ankle roll pair absorbs a lateral pelvis shift dy (the second-order
    foot lift from the roll arc is under 2 mm at these amplitudes)."""
    rig = LEG_RIG[side]
    depth = (rig.hip_z + body_z - (rig.sole_z + rig.ankle_to_sole)) / rig.cos_roll
    hip, knee, ankle = _leg_pitch_ik(0.0, depth, 0.0)
    roll_delta = math.degrees(math.asin(_clamp(dy / (HIP_ROLL_Z_MM - rig.sole_z), -0.5, 0.5)))
    roll = _s(side) * HIP_ROLL_ABDUCT_DEG - roll_delta
    return {f"hip_pitch_{side}": hip, f"knee_{side}": knee, f"ankle_pitch_{side}": ankle,
            f"hip_roll_{side}": roll, f"ankle_roll_{side}": -roll}


def _kick(phase: float) -> dict[str, tuple]:
    """Weight shifts over the left leg, the right leg chambers and snaps a
    ball-of-foot front kick at hip height behind a fists-up guard, then
    re-chambers and plants."""
    angles = dict(ATHLETIC_ANGLES)
    weight = _pulse(phase, 0.0, 0.12, 0.86, 0.98)
    chamber = _pulse(phase, 0.14, 0.3, 0.72, 0.88)
    extend = _pulse(phase, 0.36, 0.48, 0.58, 0.7)
    guard = _pulse(phase, 0.04, 0.16, 0.8, 0.94)
    dy = KICK_WEIGHT_SHIFT_MM * weight
    body_z = -KICK_DIP_MM * chamber
    angles.update(_planted_leg("left", body_z, dy))
    # Kicking leg, authored in joint space (airborne): the chamber, with the
    # snap on top of it.
    for joint, rest, chambered, snap in (
        ("hip_pitch", HIP_PITCH_DEG, KICK_CHAMBER_HIP_DEG, KICK_EXTEND_HIP_DEG),
        ("knee", KNEE_DEG, KICK_CHAMBER_KNEE_DEG, KICK_EXTEND_KNEE_DEG),
        ("ankle_pitch", ANKLE_PITCH_DEG, KICK_CHAMBER_ANKLE_DEG, KICK_EXTEND_ANKLE_DEG),
    ):
        angles[f"{joint}_right"] = _lerp(rest, chambered, chamber) + snap * extend
    # Guard: both fists up, elbows tight.
    for side in chain.SIDES:
        s = _s(side)
        angles[f"shoulder_pitch_{side}"] = _lerp(SHOULDER_PITCH_DEG, KICK_GUARD_SHOULDER_DEG, guard)
        angles[f"shoulder_roll_{side}"] = s * SHOULDER_ROLL_ABDUCT_DEG + s * KICK_GUARD_ROLL_OUT_DEG * guard
        angles[f"elbow_{side}"] = _lerp(ELBOW_DEG, KICK_GUARD_ELBOW_DEG, guard)
    turn = KICK_HIP_TURN_DEG * (0.5 * chamber + 0.5 * extend)
    angles["waist_yaw"] += turn
    angles["neck_yaw"] += -turn * NECK_COMPENSATION
    return _fk_frames(angles, lean_deg=KICK_LEAN_BACK_DEG * extend, root=(0.0, dy, body_z))


def _anchored_root(
    angles: dict[str, float], root_pitch_deg: float, link: str, local: tuple, target: tuple
) -> tuple[float, float, float]:
    """The pelvis offset that puts a contact point (local, in link's frame)
    on target; a None target component leaves that axis where the pose puts
    it."""
    at = _world_point(_fk_frames(angles, root_pitch_deg=root_pitch_deg), link, local)
    return tuple(0.0 if goal is None else goal - here for goal, here in zip(target, at))


class _HandstandKey(NamedTuple):
    t: float                  # cycle position
    pitch: float              # whole-body pitch about +Y at the pelvis
    anchor: str               # "toe", "palm", or "press": palms planted, toes on the ground
    legs: dict | None = None  # leg joints (both sides); None keeps the athletic pose
    arms: dict | None = None  # arm joints (both sides)


# The arms stay roughly vertical under the rotating body: the world arm
# direction is root pitch + shoulder pitch, so the shoulder tracks -root
# pitch as the body goes over, reaching shoulder -180 / elbow -18 / wrist -70
# at the hold (total hand pitch -90: palms flat, fingers forward), all inside
# the URDF joint limits.
_HOLD_LEGS = {"hip_pitch": -6, "knee": 4, "ankle_pitch": 25}
_HOLD_ARMS = {"shoulder_pitch": -180, "shoulder_roll": 0, "elbow": -18, "wrist_roll": 0, "wrist_pitch": -70}
_HANDSTAND_UP = (
    _HandstandKey(0.0, 0, "toe"),
    _HandstandKey(
        0.09, 12, "toe",
        {"hip_pitch": -30, "knee": 20, "ankle_pitch": 3},  # foot pitch +5: heel just off the ground
        {"shoulder_pitch": -52, "shoulder_roll": 0, "elbow": -10, "wrist_roll": 0, "wrist_pitch": -20},
    ),
    _HandstandKey(
        0.2, 55, "toe",
        {"hip_pitch": -100, "knee": 30, "ankle_pitch": 27},  # foot pitch +12: heels rise in the fold
        {"shoulder_pitch": -70, "shoulder_roll": 0, "elbow": -8, "wrist_roll": 0, "wrist_pitch": -45},
    ),
    # Press position: palms planted, arms vertical, pike fold with the toes
    # still resting on the ground (the hip pitch is solved).
    _HandstandKey(
        0.3, 95, "press",
        {"hip_pitch": -80, "knee": 8, "ankle_pitch": 30},
        {"shoulder_pitch": -95, "shoulder_roll": 0, "elbow": -20, "wrist_roll": 0, "wrist_pitch": -70},
    ),
    _HandstandKey(
        0.4, 140, "palm",
        {"hip_pitch": -45, "knee": 25, "ankle_pitch": 10},
        {"shoulder_pitch": -145, "shoulder_roll": 0, "elbow": -18, "wrist_roll": 0, "wrist_pitch": -67},
    ),
    _HandstandKey(0.48, 178, "palm", _HOLD_LEGS, _HOLD_ARMS),
    _HandstandKey(0.58, 178, "palm", _HOLD_LEGS, _HOLD_ARMS),
)
# The way back down mirrors the same shapes.
_HANDSTAND = _HANDSTAND_UP + tuple(
    _HANDSTAND_UP[index]._replace(t=t) for index, t in ((4, 0.66), (3, 0.76), (2, 0.86), (1, 0.94), (0, 1.0))
)


def _handstand_key_angles(key: _HandstandKey) -> dict[str, float]:
    angles = dict(ATHLETIC_ANGLES)
    if key.legs is None:
        return angles
    for side in chain.SIDES:
        # Square the limbs for the gymnastic line: no abduction or twist.
        for name in ("hip_roll", "ankle_roll", "shoulder_yaw", "wrist_pitch"):
            angles[f"{name}_{side}"] = 0.0
        for name, value in (*key.legs.items(), *key.arms.items()):
            angles[f"{name}_{side}"] = value
    return angles


class _Keyframe(NamedTuple):
    t: float
    pitch: float
    palm: bool                # palm-anchored (else toe-anchored)
    toe_x: float              # where the key's pose puts the toe line
    angles: dict[str, float]


@functools.cache
def _handstand_keys() -> tuple[_Keyframe, ...]:
    """Every handstand key resolved to its joint angles, its anchor type and
    the toe-line x it implies. Each frame solves its own root translation, so
    the contacts stay exact through every interpolated pose; palm keys still
    record their natural toe x so toe<->palm boundary intervals can slide the
    toe target continuously."""
    ground = LEG_RIG["left"].sole_z
    palm_target = (HS_PLANT_X_MM, None, ground)
    toe_target = (ATHLETIC_TOE[0], None, ATHLETIC_TOE[2])  # x/z only: the pose keeps its lateral position
    keys = []
    for key in _HANDSTAND:
        angles = _handstand_key_angles(key)
        if key.anchor == "press":
            # Bisect the pike fold so the toes rest exactly on the ground
            # behind the planted hands (toe height grows monotonically with
            # hip angle on the toes-behind branch). The palm anchor depends
            # only on the arm chain, so the hip search does not disturb it.
            root = _anchored_root(angles, key.pitch, "hand_left", HS_PALM_LOCAL_MM, palm_target)
            lo, hi = -95.0, -40.0
            for _ in range(48):
                mid = (lo + hi) / 2
                for side in chain.SIDES:
                    angles[f"hip_pitch_{side}"] = mid
                frames = _fk_frames(angles, root=root, root_pitch_deg=key.pitch)
                if _world_point(frames, "foot_left", TOE_LOCAL_MM)[2] < ground:
                    lo = mid
                else:
                    hi = mid
        palm = key.anchor != "toe"
        if palm:
            root = _anchored_root(angles, key.pitch, "hand_left", HS_PALM_LOCAL_MM, palm_target)
        else:
            root = _anchored_root(angles, key.pitch, "foot_left", TOE_LOCAL_MM, toe_target)
        frames = _fk_frames(angles, root=root, root_pitch_deg=key.pitch)
        keys.append(_Keyframe(key.t, key.pitch, palm, _world_point(frames, "foot_left", TOE_LOCAL_MM)[0], angles))
    return tuple(keys)


def _handstand(phase: float) -> dict[str, tuple]:
    """Toe-pivot fold, press to a palms-flat inverted hold with a breathing
    wobble, and back up to the ready stance: the whole body turns about +Y,
    its root anchored so the sole front edge stays on the ground while
    folding (heels rise, toe pivot) and the palms stay on the plant line once
    the hands are down."""
    keys = _handstand_keys()
    a, b = next((a, b) for a, b in zip(keys, keys[1:]) if a.t <= phase <= b.t)
    s = _smooth01((phase - a.t) / (b.t - a.t))
    angles = {name: _lerp(a.angles[name], b.angles[name], s) for name in ATHLETIC_ANGLES}
    # A breath of leg wobble during the hold (hips only, so the planted
    # hands stay put).
    hold = _pulse(phase, 0.46, 0.5, 0.56, 0.6)
    wobble = HS_WOBBLE_DEG * hold * math.sin(math.tau * ((phase - 0.46) / 0.14) * 2)
    for side in chain.SIDES:
        angles[f"hip_pitch_{side}"] += wobble
        angles[f"knee_{side}"] += -wobble * 0.6
    pitch = _lerp(a.pitch, b.pitch, s)
    # Palm-anchored only while both bracketing keys are palm keys (the press
    # key satisfies both contacts, so the anchor handoff there is seamless);
    # otherwise toe-anchored, the toe target sliding along the ground line
    # between the keys.
    if a.palm and b.palm:
        target = (HS_PLANT_X_MM, None, LEG_RIG["left"].sole_z)
        root = _anchored_root(angles, pitch, "hand_left", HS_PALM_LOCAL_MM, target)
    else:
        target = (_lerp(a.toe_x, b.toe_x, s), None, ATHLETIC_TOE[2])
        root = _anchored_root(angles, pitch, "foot_left", TOE_LOCAL_MM, target)
    return _fk_frames(angles, root=root, root_pitch_deg=pitch)


def _elvis_kick_out_leg(
    body_z: float, dy: float, toe_x: float, toe_y: float, point_deg: float, lift: float, edge: float
) -> dict[str, float]:
    """The kicked-out left leg, planted on a pointed toe at (toe_x, toe_y),
    by closed-form leg IK: the hip roll follows directly from requiring the
    toe target to lie in the leg's (rolled) pitch plane, then the in-plane
    two-link IK places the ankle-pitch joint so the toe tip lands exactly on
    the target. With the kick-out engaged (edge 1) the ankle roll is 0, so
    the pointed foot rolls onto its outer toe edge with the leg -- the
    classic look."""
    rig = LEG_RIG["left"]
    # Left hip-roll joint center in the world, with the shifted pelvis.
    hip_roll = (0.0, HIP_Y + dy, HIP_ROLL_Z_MM + body_z)
    # The foot rolls with the leg, so at full kick-out the contact is the
    # OUTER toe corner: lift the centerline target by the rolled half foot
    # width (scaled in with the pose; roll barely changes with the lift, so
    # one extra pass converges).
    v = (toe_x - hip_roll[0], toe_y - hip_roll[1], rig.sole_z + lift - hip_roll[2])
    edge_lift = (SOLE_HALF_WIDTH_MM * abs(math.sin(math.atan2(v[1], -v[2]))) + 1.0) * edge
    v = (toe_x - hip_roll[0], toe_y - hip_roll[1], rig.sole_z + lift + edge_lift - hip_roll[2])
    # Roll that brings the target into the leg's pitch plane.
    roll = math.atan2(v[1], -v[2])
    plane_depth = math.hypot(v[1], v[2])  # hip roll -> target, in-plane
    # Toe tip relative to the ankle-pitch joint at the pointed foot pitch.
    c, s = math.cos(math.radians(point_deg)), math.sin(math.radians(point_deg))
    toe_forward = TOE_EDGE_X_MM * c - ANKLE_OVER_SOLE_MM * s
    toe_drop = TOE_EDGE_X_MM * s + ANKLE_OVER_SOLE_MM * c
    # The ankle-pitch target is measured from the hip-PITCH joint, further
    # down the plane than the hip-roll joint.
    depth = plane_depth + chain.HIP_PITCH_ORIGIN_MM[2] - toe_drop
    hip, knee, ankle = _leg_pitch_ik(v[0] - toe_forward, depth, point_deg)
    roll_deg = math.degrees(roll)
    return {
        "hip_pitch_left": hip,
        "knee_left": knee,
        "ankle_pitch_left": ankle,
        "hip_roll_left": roll_deg,
        # Flat (roll-compensated) foot at rest, rolling onto the outer toe
        # edge with the leg as the kick-out engages.
        "ankle_roll_left": -roll_deg * (1 - edge),
    }


def _dance(phase: float) -> dict[str, tuple]:
    """The King: weight on the right leg, left leg kicked out to the left on
    a shaking pointed toe, right finger pointing up to the right with a beat
    pulse, hip swivel and chin up."""
    angles = dict(ATHLETIC_ANGLES)
    env = _pulse(phase, 0.0, 0.12, 0.88, 1.0)
    beat = phase * ELVIS_BEATS
    dy = ELVIS_WEIGHT_SHIFT_MM * env
    body_z = -ELVIS_DIP_MM * env - ELVIS_BOUNCE_MM * env * abs(math.sin(math.pi * beat))
    # Stance leg: planted under the shifted, bobbing pelvis.
    angles.update(_planted_leg("right", body_z, dy))
    # Kicked-out leg: toe planted out to the left, shaking with the beat. The
    # whole transition is IK-driven: the toe target slides from the athletic
    # toe spot to the kick-out point with a lift bump mid-blend, so the foot
    # never sweeps through the floor (at env 0 the IK lands exactly back on
    # the athletic leg).
    shake = env * math.sin(math.tau * 2 * beat)
    toe_x = _lerp(ATHLETIC_TOE[0], ELVIS_TOE_X_MM, env)
    toe_y = _lerp(ATHLETIC_TOE[1], ELVIS_TOE_Y_MM + ELVIS_TOE_SHAKE_MM * shake, env)
    point = ELVIS_FOOT_POINT_DEG * env + ELVIS_FOOT_POINT_SHAKE_DEG * shake
    lift = ELVIS_TOE_LIFT_MM * math.sin(math.pi * env)
    angles.update(_elvis_kick_out_leg(body_z, dy, toe_x, toe_y, point, lift, env))
    # The point: right arm up and out to the right, pulsing on the beat.
    pulse_deg = ELVIS_POINT_PULSE_DEG * math.sin(math.tau * beat)
    rest_roll = _s("right") * SHOULDER_ROLL_ABDUCT_DEG
    angles["shoulder_roll_right"] = _lerp(rest_roll, ELVIS_POINT_ROLL_DEG + pulse_deg, env)
    angles["shoulder_pitch_right"] = _lerp(SHOULDER_PITCH_DEG, ELVIS_POINT_PITCH_DEG, env)
    angles["elbow_right"] = _lerp(ELBOW_DEG, ELVIS_POINT_ELBOW_DEG, env)
    # Off arm low and bent across the body.
    angles["shoulder_pitch_left"] = _lerp(SHOULDER_PITCH_DEG, ELVIS_OFF_ARM_PITCH_DEG, env)
    angles["elbow_left"] = _lerp(ELBOW_DEG, ELVIS_OFF_ARM_ELBOW_DEG, env)
    # Hip swivel, lean into the point, head to the pointing hand, chin up.
    twist = ELVIS_TWIST_DEG * env * math.sin(math.pi * beat)
    angles["waist_yaw"] += twist
    angles["neck_yaw"] += ELVIS_HEAD_TURN_DEG * env - twist * 0.6
    angles["neck_pitch"] += ELVIS_CHIN_UP_DEG * env
    return _fk_frames(angles, roll_deg=ELVIS_LEAN_RIGHT_DEG * env, root=(0.0, dy, body_z))


# ----------------------------------------------------------------- clips


def _move_links(m, frames: dict[str, tuple]) -> None:
    """Move every link subtree from its baked athletic placement onto its
    placement in frames: the rigid delta T * inverse(T_athletic), applied in
    the fixed model frame. A link still where it was baked is left alone."""
    for link, (rest_r, rest_p) in ATHLETIC_FRAMES.items():
        r, p = frames[link]
        delta = _mat_mul(r, tuple(zip(*rest_r)))
        moved = _mat_vec(delta, rest_p)
        shift = (p[0] - moved[0], p[1] - moved[1], p[2] - moved[2])
        turned = max(abs(delta[i][j] - _IDENTITY3[i][j]) for i in range(3) for j in range(3)) > 1e-12
        if turned or max(abs(c) for c in shift) > 1e-9:
            matrix = [[*delta[0], shift[0]], [*delta[1], shift[1]], [*delta[2], shift[2]], [0.0, 0.0, 0.0, 1.0]]
            m.get(f"#{link}").transform(matrix)


def _looped(gait, duration: float, label: str):
    """A looping clip that plays gait's cycle once every duration seconds."""

    def update(t: float, m) -> None:
        _move_links(m, gait(t / duration % 1.0))

    return cadgen.clip(update, duration=duration, label=label)


# Most exciting first: the order the viewer lists them.
ANIMATION = {
    "danceLoop": _looped(_dance, 3.2, "Elvis dance"),
    "handstandLoop": _looped(_handstand, 4.6, "Handstand"),
    "kickLoop": _looped(_kick, 2.8, "Karate kick"),
    "jumpLoop": _looped(_jump, 1.8, "Jump in place"),
    "runLoop": _looped(_run, 0.8, "Run in place"),
    "strideLoop": _looped(_stride, 1.9, "Stride in place"),
    "walkLoop": _looped(_walk, 1.5, "Walk in place"),
}


@step(out="../STEP/juno.step", kinematics=KINEMATICS, animation=ANIMATION)
def juno():
    return assemble()


if __name__ == "__main__":
    juno()
