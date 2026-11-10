"""Galatea's skeleton: every joint centre, axis, travel and linkage dimension, as plain numbers.

Frame: millimetres, +Z up, the robot faces -Y (the viewer's `front`), its left is +X. Everything
here is the LEFT side at the zero pose (standing straight, arms hanging, palms toward the thighs);
the right side is the mirror image in the YZ plane. Nothing in this module touches the CAD kernel.
"""

import math

# --------------------------------------------------------------------------------------------
# Leg
# --------------------------------------------------------------------------------------------
HIP_X = 82.0
HIP = (HIP_X, 0.0, 920.0)        # hip yaw (Z), roll (Y) and pitch (X) axes meet here
KNEE = (HIP_X, 0.0, 500.0)       # knee axis (X)
ANKLE = (HIP_X, 0.0, 90.0)       # ankle pitch (X) and roll (Y) axes meet here
TOE = (HIP_X, -118.0, 15.0)      # toe hinge (X), mid-height of the sole plate
THIGH_LEN = HIP[2] - KNEE[2]     # 420
SHIN_LEN = KNEE[2] - ANKLE[2]    # 410

# Knee drive: a rotary actuator high in the thigh turns the shin through a parallelogram
# four-bar (crank = horn, pushrod = pivot spacing), so crank angle == knee angle exactly.
KNEE_ACT = (HIP_X, 0.0, 800.0)   # crank pivot, on the thigh axis
KNEE_ROD = KNEE_ACT[2] - KNEE[2]                  # 300, pushrod length
KNEE_CRANK_R = 55.0
KNEE_CRANK_PSI = -62.5                            # deg from +Y (back) at knee = 0; flexion adds
KNEE_RANGE = (0.0, 125.0)                         # transmission angle 27.5 deg at both ends

# Ankle pitch drive: a double-ended actuator between the shin rails turns the ankle gimbal
# through twin parallel pushrods (again a parallelogram: crank angle == ankle pitch).
ANKLE_ACT = (HIP_X, 0.0, 345.0)
ANKLE_ROD = ANKLE_ACT[2] - ANKLE[2]               # 255
ANKLE_CRANK_R = 45.0                              # crank and gimbal arm point straight back (+Y)
ANKLE_ROD_X = 34.0                                # pushrods sit this far either side of the leg's centre plane

SHIN_RAIL_X = (40.0, 48.0)                        # shin rails: inner and outer face, from the centre plane
FEMUR_PLATE_X = (18.0, 26.0)                      # femur plates: inner and outer face
CRADLE_CHEEK_X = (27.0, 35.0)                     # hip cradle cheeks: inner and outer face

# Pelvis
PELVIS_Z = (1009.0, 1075.0)                       # underside and top of the pelvis casting
WAIST_AXIS_Y = 32.0                               # the spine stands this far behind the hip centres
WAIST = (0.0, WAIST_AXIS_Y, 1150.0)               # waist roll (Y) and pitch (X) axes meet here

# --------------------------------------------------------------------------------------------
# Arm
# --------------------------------------------------------------------------------------------
SHOULDER_X = 205.0
SHOULDER = (SHOULDER_X, 0.0, 1420.0)              # shoulder pitch (X), roll (Y) and yaw (Z) meet here
ELBOW = (SHOULDER_X, 0.0, 1130.0)                 # elbow axis (X)
WRIST_ROLL = (SHOULDER_X, 0.0, 1039.0)            # forearm rotation (Z), just under the elbow
WRIST = (SHOULDER_X, 0.0, 915.0)                  # wrist pitch (Y)
WRIST_YAW = (SHOULDER_X, 0.0, 871.0)              # wrist yaw / deviation (X), 44 below the pitch axis
CHEST_SIDE_X = (132.0, 140.0)                     # chest side plates the shoulder actuators bolt to
UPPER_ARM_LEN = SHOULDER[2] - ELBOW[2]            # 290
FOREARM_LEN = ELBOW[2] - WRIST[2]                 # 215

# Hand: knuckle line and finger geometry. Fingers hang along -Z, the palm faces -X (the
# thigh), the thumb leads (-Y). Per finger: knuckle Y, then the three phalanx lengths.
KNUCKLE_Z = 762.0
FINGERS = {
    "index": (-30.0, (44.0, 26.0, 22.0)),
    "middle": (-10.0, (48.0, 30.0, 24.0)),
    "ring": (10.0, (44.0, 26.0, 22.0)),
    "little": (29.0, (36.0, 22.0, 20.0)),
}
FINGER_CURL = (85.0, 100.0, 70.0)                 # MCP, PIP, DIP at a full curl
THUMB_BASE = (SHOULDER_X, -40.0, 826.0)           # opposition axis (Z) through here
THUMB_LEAN = 40.0                                 # degrees from the fingers' direction, toward the front
THUMB_BONES = (38.0, 32.0, 26.0)                  # metacarpal, proximal, distal
THUMB_CURL = (55.0, 75.0)                         # MCP, IP at a full curl
_lean = math.radians(THUMB_LEAN)
THUMB_DIR = (0.0, -math.sin(_lean), -math.cos(_lean))                       # the thumb's line at the zero pose
THUMB_ROOT = tuple(b + 20.0 * k for b, k in zip(THUMB_BASE, THUMB_DIR))     # where the metacarpal's bone starts
THUMB_MCP = tuple(b + THUMB_BONES[0] * k for b, k in zip(THUMB_ROOT, THUMB_DIR))
THUMB_IP = tuple(b + THUMB_BONES[1] * k for b, k in zip(THUMB_MCP, THUMB_DIR))

# --------------------------------------------------------------------------------------------
# Neck and head
# --------------------------------------------------------------------------------------------
NECK_BASE = (0.0, 14.0, 1497.0)                   # neck yaw (Z): the drive's output face, in the collar
NECK_ROLL = (0.0, 32.0, 1531.0)                   # neck roll (Y): the neck leans from its root
NECK = (0.0, 14.0, 1580.0)                        # neck pitch (X): the head nods at the skull's base
HEAD_TOP_Z = 1752.0

# --------------------------------------------------------------------------------------------
# Actuator family: one design in five frame sizes. R = mounting flange radius, L = body
# length behind the mounting face, r_out = output flange radius, bore = hollow shaft (cables),
# ring = flange ring width, screw = stator screw size, n = screws per bolt circle.
# --------------------------------------------------------------------------------------------
ACTUATORS = {
    "A110": dict(R=55.0, L=44.0, r_out=34.0, bore=10.0, ring=10.0, screw="M5", n=12, nm=160),
    "A86": dict(R=43.0, L=50.0, r_out=26.0, bore=8.0, ring=8.0, screw="M4", n=10, nm=85),
    "A70": dict(R=35.0, L=44.0, r_out=21.0, bore=6.0, ring=7.5, screw="M4", n=8, nm=42),
    "A52": dict(R=26.0, L=36.0, r_out=15.0, bore=4.0, ring=6.5, screw="M3", n=8, nm=16),
    "A52L": dict(R=26.0, L=54.0, r_out=15.0, bore=4.0, ring=6.5, screw="M3", n=8, nm=27),   # long stack: ankle roll
    "A40": dict(R=20.0, L=28.0, r_out=11.5, bore=3.0, ring=6.0, screw="M3", n=6, nm=7),
}
PLATE_T = 8.0          # the parent's mounting plate an actuator's output passes through
ROTOR_PROUD = 9.0      # the output flange stands this far past the mounting face (plate + 1)

# Socket-head cap screws, heads only: head diameter, head height, hex socket across flats.
SCREWS = {
    "M3": (5.5, 3.0, 2.5),
    "M4": (7.0, 4.0, 3.0),
    "M5": (8.5, 5.0, 4.0),
    "M6": (10.0, 6.0, 5.0),
}

# --------------------------------------------------------------------------------------------
# Joints: label -> (parent link, child link, origin, axis direction, (min, max) degrees).
# Left side; `mirror_joint` gives the right. Axis directions are chosen so that a positive
# value is the anatomical motion named in the comment, on both sides.
# --------------------------------------------------------------------------------------------
X, Y, Z = (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)
NX, NY, NZ = (-1.0, 0.0, 0.0), (0.0, -1.0, 0.0), (0.0, 0.0, -1.0)


def _polar(origin, radius, psi_deg):
    """A point in the leg's sagittal plane: psi from +Y (back) toward +Z (up)."""
    psi = math.radians(psi_deg)
    return (origin[0], origin[1] + radius * math.cos(psi), origin[2] + radius * math.sin(psi))


KNEE_CRANK_PIN = _polar(KNEE_ACT, KNEE_CRANK_R, KNEE_CRANK_PSI)     # B: crank to pushrod
KNEE_HORN_PIN = _polar(KNEE, KNEE_CRANK_R, KNEE_CRANK_PSI)          # C: pushrod to shin horn
ANKLE_CRANK_PIN = _polar(ANKLE_ACT, ANKLE_CRANK_R, 0.0)
ANKLE_ARM_PIN = _polar(ANKLE, ANKLE_CRANK_R, 0.0)

SIDE_JOINTS = {
    # leg ------------------------------------------------------------------------------
    "hip_yaw": ("pelvis", "hip_yoke", HIP, Z, (-25.0, 40.0)),             # + turns the toes outward
    "hip_roll": ("hip_yoke", "hip_cradle", HIP, NY, (-20.0, 25.0)),       # + abducts (leg outward)
    "hip_pitch": ("hip_cradle", "thigh", HIP, NX, (-30.0, 100.0)),        # + flexes (thigh forward)
    "knee_pivot": ("thigh", "shin", KNEE, X, KNEE_RANGE),                 # + flexes (heel to the back)
    "knee_crank": ("thigh", "knee_crank", KNEE_ACT, X, KNEE_RANGE),
    "knee_rod": ("knee_crank", "knee_rod", KNEE_CRANK_PIN, X, (-KNEE_RANGE[1], -KNEE_RANGE[0])),
    "ankle_pitch_pivot": ("shin", "ankle_gimbal", ANKLE, NX, (-45.0, 30.0)),   # + dorsiflexes (toes up)
    "ankle_crank": ("shin", "ankle_crank", ANKLE_ACT, NX, (-45.0, 30.0)),
    "ankle_rod": ("ankle_crank", "ankle_rods", ANKLE_CRANK_PIN, NX, (-30.0, 45.0)),
    "ankle_roll": ("ankle_gimbal", "foot", ANKLE, NY, (-20.0, 20.0)),     # + everts (sole outward)
    "toe": ("foot", "toe", TOE, NX, (0.0, 50.0)),                         # + lifts the toes (heel-off)
    # arm ------------------------------------------------------------------------------
    "shoulder_pitch": ("chest", "shoulder_yoke", SHOULDER, NX, (-60.0, 180.0)),   # + raises the arm forward
    "shoulder_roll": ("shoulder_yoke", "shoulder_block", SHOULDER, NY, (-12.0, 120.0)),  # + abducts
    "shoulder_yaw": ("shoulder_block", "upper_arm", SHOULDER, NZ, (-90.0, 90.0)),  # + turns the elbow pit inward
    "elbow": ("upper_arm", "forearm", ELBOW, NX, (0.0, 140.0)),                  # + flexes
    "wrist_roll": ("forearm", "forearm_distal", WRIST_ROLL, NZ, (-90.0, 90.0)),  # + pronates (palm to the back)
    "wrist_pitch": ("forearm_distal", "wrist_link", WRIST, Y, (-70.0, 70.0)),    # + flexes (palm toward forearm)
    "wrist_yaw": ("wrist_link", "palm", WRIST_YAW, X, (-25.0, 35.0)),            # + ulnar deviation (toward little finger)
}

CENTRE_JOINTS = {
    "waist_yaw": ("pelvis", "lumbar_yoke", (0.0, WAIST_AXIS_Y, 1080.0), Z, (-50.0, 50.0)),   # + turns the chest left
    "waist_roll": ("lumbar_yoke", "waist_cross", WAIST, Y, (-20.0, 20.0)),                  # + leans to the left
    "waist_pitch": ("waist_cross", "chest", WAIST, X, (-20.0, 40.0)),                       # + bows forward
    "neck_yaw": ("chest", "neck", NECK_BASE, Z, (-75.0, 75.0)),                             # + looks left
    "neck_roll": ("neck", "neck_stem", NECK_ROLL, Y, (-25.0, 25.0)),                        # + tilts to the left
    "neck_pitch": ("neck_stem", "head", NECK, X, (-25.0, 40.0)),                            # + nods down
}


def hand_joints():
    """The hand's joints, left side, in the form of SIDE_JOINTS."""
    joints = {}
    for finger, (y, lengths) in FINGERS.items():
        z, parent = KNUCKLE_Z, "palm"
        for bone, joint, limit, length in zip(("prox", "mid", "dist"), ("mcp", "pip", "dip"), FINGER_CURL, lengths):
            joints[f"{finger}_{joint}"] = (parent, f"{finger}_{bone}", (SHOULDER_X, y, z), Y, (0.0, limit))   # + curls
            z, parent = z - length, f"{finger}_{bone}"
    joints["thumb_opp"] = ("palm", "thumb_meta", THUMB_BASE, NZ, (0.0, 80.0))          # + swings across the palm
    joints["thumb_mcp"] = ("thumb_meta", "thumb_prox", THUMB_MCP, X, (0.0, THUMB_CURL[0]))   # + curls
    joints["thumb_ip"] = ("thumb_prox", "thumb_dist", THUMB_IP, X, (0.0, THUMB_CURL[1]))
    return joints


CENTRE_LINKS = ("pelvis", "lumbar_yoke", "waist_cross", "chest", "neck", "neck_stem", "head")


def mirror_point(p):
    return (-p[0], p[1], p[2])


def mirror_joint(origin, direction):
    """The right-hand twin of a left joint: the same value is the mirrored motion."""
    return mirror_point(origin), (direction[0], -direction[1], -direction[2])
