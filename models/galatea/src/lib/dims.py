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
KNEE_ACT = (HIP_X, 0.0, 780.0)   # crank pivot, on the thigh axis: 140 under the hip's, so that the knee drive's can passes
                                 # under the hip's roll drive when the leg swings back
KNEE_ROD = KNEE_ACT[2] - KNEE[2]                  # 280, pushrod length
KNEE_CRANK_R = 55.0
KNEE_CRANK_PSI = -62.5                            # deg from +Y (back) at knee = 0; flexion adds
KNEE_RANGE = (0.0, 125.0)                         # transmission angle 27.5 deg at both ends
KNEE_ROD_R = 6.0                                  # a solid titanium rod: it pushes when the knee holds the body up

# Ankle pitch drive: an actuator across the calf, between the shin rails, turns the ankle gimbal
# through a crank and a pushrod (again a parallelogram: crank angle == ankle pitch).
ANKLE_ACT = (HIP_X, 12.0, 345.0)
ANKLE_ROD = math.hypot(ANKLE_ACT[1] - ANKLE[1], ANKLE_ACT[2] - ANKLE[2])   # 255.3: the drive stands 12 behind the ankle, as a calf does
ANKLE_CRANK_R = 45.0                              # crank and gimbal arm point straight back (+Y)
ANKLE_ROD_X = 35.5                                # the pushrod sits this far outboard of the leg's centre plane
ANKLE_ROD_R = 4.5                                 # steel, behind the ankle like a tendon: push-off pulls it

SHIN_RAIL_X = (40.0, 48.0)                        # shin rails: inner and outer face, from the centre plane
FEMUR_PLATE_X = (18.0, 26.0)                      # femur plates: inner and outer face
CRADLE_CHEEK_X = (27.0, 35.0)                     # hip cradle cheeks: inner and outer face

# Hip: the yoke's rear plate stands HIP_YOKE_Y behind the hip's centre and carries the roll drive behind it. The drive's
# can swings with the hip's yaw: turned out by a degrees, its inner edge stands R cos a + B sin a inboard of the hip,
# R the can's radius and B how far its end stands behind the hip (`hip_can_reach`). The two legs' cans must not meet
# on the centre plane, which bounds the two yaws together: both feet turn out 10 degrees, or one 20 and the other none.
HIP_YOKE_Y = 70.0
HIP_ROLL_CAN = (60.0, HIP_YOKE_Y + 8.0 + 39.0)       # an RS04's radius, and its main body's end behind the hip (plate 8, body 39)


def hip_can_reach(yaw):
    """How far inboard of its hip a roll drive's can reaches with the hip turned out `yaw` degrees."""
    a = math.radians(max(yaw, 0.0))
    return HIP_ROLL_CAN[0] * math.cos(a) + HIP_ROLL_CAN[1] * math.sin(a)


# Pelvis
PELVIS_Z = (1009.0, 1075.0)                       # underside and top of the pelvis casting
WAIST_AXIS_Y = 32.0                               # the spine stands this far behind the hip centres
WAIST = (0.0, WAIST_AXIS_Y, 1150.0)               # waist roll (Y) and pitch (X) axes meet here

# --------------------------------------------------------------------------------------------
# Arm
# --------------------------------------------------------------------------------------------
SHOULDER_X = 212.0
SHOULDER = (SHOULDER_X, 0.0, 1420.0)              # shoulder pitch (X), roll (Y) and yaw (Z) meet here
ELBOW = (SHOULDER_X, 0.0, 1130.0)                 # elbow axis (X)
WRIST_ROLL = (SHOULDER_X, 0.0, 1022.0)            # forearm rotation (Z), under the elbow drive's can
WRIST = (SHOULDER_X, 0.0, 924.0)                  # wrist pitch (Y)
WRIST_YAW = (SHOULDER_X, 0.0, 873.0)              # wrist yaw / deviation (X), 51 below the pitch axis: two 46 mm cans, crossed
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
NECK_BASE = (0.0, 14.0, 1497.0)                   # neck yaw (Z): the drive's output face, at the chest's top
NECK_ROLL = (0.0, 32.0, 1531.0)                   # neck roll (Y): the neck leans from its root
NECK = (0.0, 14.0, 1586.0)                        # neck pitch (X): the head nods at the skull's base, 55 over the roll's can
HEAD_TOP_Z = 1752.0

# --------------------------------------------------------------------------------------------
# Actuators: RobStride quasi-direct drives (a frameless motor, a 7.75 to 10:1 planetary stage,
# encoder and driver in one housing; 48 V, CAN). Their shapes are the maker's own STEP models,
# fetched into vendor/ by `vendor.py` and read by `lib/hardware.py`. The numbers here are what the
# brackets and the checks need, measured on those models, with torques and masses from the maker's
# Product Specification of 2026-10-09 (both in github.com/RobStride/Product_Information):
#
#   front  (radius, length)  the main body behind the mounting face
#   rear   (radius, length)  the cover behind it, over the driver board
#   ears   radius over the lobes its mounting screws run in, or None for a plain can
#   pilot  (radius, height)  what stands proud of the mounting face round the output: the plate's hole clears it
#   flange height of the output flange's face over the mounting face: the hub seats on it
#   pins   (radius, circle radius, height over the mounting face) of locating pins standing on the flange
#   mount  (screw, count, pitch radius)  tapped holes in the mounting face, the first 180 / count from local X,
#          or at `mount_at`: the RS04 is stood with its cable connector on local +Y, which puts a hole on local X.
#          (A connector on the frame's own mirror plane is on it on both sides of the robot.)
#   out    (screw, count, pitch radius)  tapped holes in the output flange; `out_at` where they are not evenly spaced
#   step   how the maker's file stands in the actuator's frame: (its output points along its own -Z,
#          its z of the mounting face, degrees to turn it so the mounting holes lie as `mount` says)
#   peak, rated  N m at the output. Rated is continuous, at 100 rpm (50 for the RS04), on the maker's
#          aluminium heat sink of `sink` mm; the RS04 gives 40 on a 345 x 345 one and 35 on this
#   kg     the unit's mass
#   hub    radius of the adapter this robot bolts to the output flange: it stands through the
#          parent's mounting plate and the child's lug bolts to it (not a RobStride part)
# --------------------------------------------------------------------------------------------
ACTUATORS = {
    "RS04": dict(front=(60.0, 39.0), rear=(47.0, 13.2), ears=None, pilot=(25.0, 0.5), flange=0.5, pins=(3.0, 17.9, 3.5),
                 mount=("M4", 10, 53.0), mount_at=0.0, out=("M5", 9, 18.0), out_at=(0, 30, 60, 120, 150, 180, 240, 270, 300),
                 step=(False, 25.0, 15.0), peak=120.0, rated=35.0, sink="220 x 200", kg=1.51, hub=25.0),
    "RS03": dict(front=(48.2, 39.5), rear=(39.75, 14.6), ears=53.0, pilot=(35.5, 2.5), flange=2.5, pins=None,
                 mount=("M4", 8, 49.0), out=("M4", 6, 15.18), step=(True, 2.5, 0.0),
                 peak=60.0, rated=21.0, sink="200 x 200", kg=0.928, hub=22.0),
    "RS06": dict(front=(41.6, 33.0), rear=(35.0, 16.0), ears=44.0, pilot=(26.5, 1.5), flange=1.5, pins=None,
                 mount=("M3", 8, 41.0), out=("M4", 6, 12.0), step=(True, 0.0, 0.0),
                 peak=36.0, rated=11.0, sink="200 x 200", kg=0.615, hub=18.0),
    "RS00": dict(front=(28.5, 35.8), rear=(27.5, 15.3), ears=None, pilot=(17.5, 1.0), flange=1.0, pins=None,
                 mount=("M3", 6, 25.0), out=("M3", 6, 13.5), step=(True, -5.0, 30.0),
                 peak=14.0, rated=5.0, sink="150 x 150", kg=0.31, hub=17.0),
    "RS05": dict(front=(23.0, 44.0), rear=(23.0, 0.0), ears=None, pilot=(15.0, 0.0), flange=0.0, pins=(2.0, 9.5, 3.0),
                 mount=("M3", 4, 20.8), out=("M4", 6, 12.0), step=(False, 30.5, 22.5),
                 peak=5.5, rated=1.8, sink="150 x 150", kg=0.243, hub=15.0),
}


def actuator_length(size):
    """How far an actuator stands behind its mounting face."""
    spec = ACTUATORS[size]
    return spec["front"][1] + spec["rear"][1]


# Which drive turns which joint: control -> (model, how many share the joint). The builders place
# them by these names (`Hardware.actuator` checks the model), and `checks/loads.py` reads the
# torques from here.
DRIVES = {
    "hip_yaw": ("RS06", 1), "hip_roll": ("RS04", 1), "hip_pitch": ("RS04", 1), "knee": ("RS04", 1),
    "ankle_pitch": ("RS04", 1), "ankle_roll": ("RS00", 1),
    "waist_yaw": ("RS06", 1), "waist_roll": ("RS06", 1), "waist_pitch": ("RS06", 2),
    "shoulder_pitch": ("RS03", 1), "shoulder_roll": ("RS06", 1), "shoulder_yaw": ("RS00", 1), "elbow": ("RS06", 1),
    "wrist_roll": ("RS05", 1), "wrist_pitch": ("RS05", 1), "wrist_yaw": ("RS05", 1),
    "neck_yaw": ("RS00", 1), "neck_roll": ("RS05", 1), "neck_pitch": ("RS00", 1),
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
    "hip_yaw": ("pelvis", "hip_yoke", HIP, Z, (-25.0, 20.0)),             # + turns the toes outward (see HIP_ROLL_CAN)
    "hip_roll": ("hip_yoke", "hip_cradle", HIP, NY, (-20.0, 16.0)),       # + abducts (leg outward): the pitch drive's can rises under the pelvis
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
    "waist_roll": ("lumbar_yoke", "waist_cross", WAIST, Y, (-15.0, 15.0)),                  # + leans to the left; the abdomen's hem ends it
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
