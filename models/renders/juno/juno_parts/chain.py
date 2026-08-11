"""juno kinematic chain spec shared by the CAD assembly and URDF/SRDF.

Stdlib-only (no build123d) so robot-description generators can import it
cheaply. `juno.py` consumes the same offsets and CAD pose angles, keeping
the STEP assembly and the URDF tree in lockstep.

Design ledger (URDF):
- Units: chain offsets are millimeters in each parent part's local frame;
  URDF emission converts to meters/radians. Frames follow REP-103: +X
  forward, +Y robot-left, +Z up. The pelvis waist-yaw joint center is the
  robot origin; every child link frame sits at its joint center with axes
  parallel to the parent at zero joint angle (pure translations).
- Source: offsets and axes mirror the `revolute_attach()` calls in
  `juno.py` (the build123d assembly), which is the CAD source of truth.
- Positive-motion conventions (verified against the CAD athletic stance):
  pitch joints rotate about +Y (positive swings the distal segment
  backward: knee flexion positive, hip/shoulder flexion forward negative);
  roll joints rotate about +X (positive moves the distal segment toward
  +Y, robot-left); yaw joints rotate about +Z (positive turns toward
  robot-left). Side-dependent signs (abduction, internal rotation) are
  encoded per side in limits and poses.
- Joint limits, efforts, and velocities are ASSUMED plausible values for a
  1.4 m research-humanoid concept (G1-class actuators); the CAD does not
  model hard stops. Documented here, not measured.
"""

from __future__ import annotations

# Lateral offsets (mm) from juno.py.
HIP_Y_MM = 90.0
SHOULDER_Y_MM = 148.0

# Parent-local joint origin offsets (mm); see juno.py chain-offset docstring.
WAIST_YAW_ORIGIN_MM = (0.0, 0.0, 0.0)
NECK_YAW_ORIGIN_MM = (0.0, 0.0, 324.0)
NECK_PITCH_ORIGIN_MM = (0.0, 0.0, 46.0)
HIP_YAW_DROP_Z_MM = -120.0
HIP_ROLL_ORIGIN_MM = (0.0, 0.0, -64.0)
HIP_PITCH_ORIGIN_MM = (0.0, 0.0, -78.0)
KNEE_ORIGIN_MM = (0.0, 0.0, -290.0)
ANKLE_PITCH_ORIGIN_MM = (0.0, 0.0, -290.0)
ANKLE_ROLL_ORIGIN_MM = (0.0, 0.0, -30.0)
SHOULDER_PITCH_RAISE_Z_MM = 290.0
SHOULDER_ROLL_Y_MM = 34.0
SHOULDER_ROLL_Z_MM = -72.0
SHOULDER_YAW_ORIGIN_MM = (0.0, 0.0, -24.0)
ELBOW_ORIGIN_MM = (0.0, 0.0, -156.0)
WRIST_ROLL_ORIGIN_MM = (0.0, 0.0, -150.0)
WRIST_PITCH_ORIGIN_MM = (0.0, 0.0, -28.0)

X_AXIS = (1.0, 0.0, 0.0)
Y_AXIS = (0.0, 1.0, 0.0)
Z_AXIS = (0.0, 0.0, 1.0)

# Sole plane below the foot link origin (foot part bbox bottom; the rubber
# sole pads are modeled 26 mm under the ankle-roll center).
SOLE_BELOW_FOOT_MM = 26.0

# Standing pelvis height at the all-zero pose: the URDF roots a frame-only
# `base_footprint` link at ground level and lifts the pelvis by this fixed
# offset so the zero pose stands exactly on z = 0. Posed states with bent
# knees (athletic_ready, squat) keep the pelvis fixed and hover slightly.
BASE_FOOTPRINT_TO_PELVIS_Z_MM = -(
    HIP_YAW_DROP_Z_MM
    + HIP_ROLL_ORIGIN_MM[2]
    + HIP_PITCH_ORIGIN_MM[2]
    + KNEE_ORIGIN_MM[2]
    + ANKLE_PITCH_ORIGIN_MM[2]
    + ANKLE_ROLL_ORIGIN_MM[2]
    - SOLE_BELOW_FOOT_MM
)

SIDES = ("left", "right")


def side_sign(side: str) -> float:
    """+1 for the robot-left side, -1 for the robot-right side."""
    return 1.0 if side == "left" else -1.0


# CAD athletic ready stance (degrees), shared with juno.py and the SRDF
# `athletic_ready` group state.
HIP_PITCH_DEG = -16.0
KNEE_DEG = 32.0
ANKLE_PITCH_DEG = -16.0
HIP_ROLL_ABDUCT_DEG = 3.0       # left +, right -; ankle roll compensates
HIP_YAW_DEG = 0.0
WAIST_YAW_DEG = 0.0
SHOULDER_PITCH_DEG = -8.0       # negative swings the arm forward
SHOULDER_ROLL_ABDUCT_DEG = 8.0  # elbows out
SHOULDER_YAW_INTERNAL_DEG = 8.0
ELBOW_DEG = -20.0               # negative flexes the forearm forward
WRIST_ROLL_DEG = 0.0
WRIST_PITCH_DEG = -2.0
NECK_YAW_DEG = 0.0
NECK_PITCH_DEG = -2.0


# ---------------------------------------------------------------- limits
# ASSUMED actuator classes (Nm rated torque / rad/s no-load class speed)
# for a G1-class concept humanoid; the CAD does not model actuators' data.
LEG_PRIMARY_EFFORT_NM = 120.0   # hip yaw/roll/pitch, knee
LEG_PRIMARY_VELOCITY_RAD_S = 15.0
ANKLE_EFFORT_NM = 50.0
ANKLE_VELOCITY_RAD_S = 12.0
WAIST_EFFORT_NM = 60.0
WAIST_VELOCITY_RAD_S = 8.0
SHOULDER_EFFORT_NM = 40.0
SHOULDER_VELOCITY_RAD_S = 12.0
ELBOW_EFFORT_NM = 35.0
ELBOW_VELOCITY_RAD_S = 12.0
WRIST_EFFORT_NM = 15.0
WRIST_VELOCITY_RAD_S = 15.0
NECK_EFFORT_NM = 8.0
NECK_VELOCITY_RAD_S = 8.0

# ASSUMED joint travel (degrees), humanoid-plausible and containing the CAD
# athletic stance. Asymmetric ranges are authored for the LEFT side with
# the convention noted; the right side mirrors lower/upper.
WAIST_YAW_RANGE_DEG = (-150.0, 150.0)
NECK_YAW_RANGE_DEG = (-90.0, 90.0)
NECK_PITCH_RANGE_DEG = (-35.0, 45.0)        # negative looks up, positive down
HIP_YAW_RANGE_DEG = (-60.0, 60.0)
HIP_ROLL_LEFT_RANGE_DEG = (-20.0, 45.0)     # +abduction for the left leg
HIP_PITCH_RANGE_DEG = (-120.0, 30.0)        # negative flexes forward
KNEE_RANGE_DEG = (-5.0, 140.0)              # positive flexes backward
ANKLE_PITCH_RANGE_DEG = (-30.0, 50.0)       # negative toes-up
ANKLE_ROLL_LEFT_RANGE_DEG = (-25.0, 25.0)
SHOULDER_PITCH_RANGE_DEG = (-180.0, 60.0)   # negative swings forward
SHOULDER_ROLL_LEFT_RANGE_DEG = (-25.0, 160.0)  # +abduction for the left arm
SHOULDER_YAW_RANGE_DEG = (-120.0, 120.0)
ELBOW_RANGE_DEG = (-145.0, 5.0)             # negative flexes forward
WRIST_ROLL_RANGE_DEG = (-170.0, 170.0)
WRIST_PITCH_RANGE_DEG = (-70.0, 70.0)


def _mirror_range(range_deg: tuple[float, float], side: str) -> tuple[float, float]:
    if side == "left":
        return range_deg
    lower, upper = range_deg
    return (-upper, -lower)


def central_joints() -> list[dict]:
    """The three non-sided joints in root-to-leaf order."""
    return [
        {
            "name": "waist_yaw",
            "parent": "pelvis",
            "child": "torso",
            "origin_mm": WAIST_YAW_ORIGIN_MM,
            "axis": Z_AXIS,
            "range_deg": WAIST_YAW_RANGE_DEG,
            "effort_nm": WAIST_EFFORT_NM,
            "velocity_rad_s": WAIST_VELOCITY_RAD_S,
        },
        {
            "name": "neck_yaw",
            "parent": "torso",
            "child": "neck_collar",
            "origin_mm": NECK_YAW_ORIGIN_MM,
            "axis": Z_AXIS,
            "range_deg": NECK_YAW_RANGE_DEG,
            "effort_nm": NECK_EFFORT_NM,
            "velocity_rad_s": NECK_VELOCITY_RAD_S,
        },
        {
            "name": "neck_pitch",
            "parent": "neck_collar",
            "child": "head",
            "origin_mm": NECK_PITCH_ORIGIN_MM,
            "axis": Y_AXIS,
            "range_deg": NECK_PITCH_RANGE_DEG,
            "effort_nm": NECK_EFFORT_NM,
            "velocity_rad_s": NECK_VELOCITY_RAD_S,
        },
    ]


def leg_joints(side: str) -> list[dict]:
    s = side_sign(side)
    return [
        {
            "name": f"hip_yaw_{side}",
            "parent": "pelvis",
            "child": f"hip_bracket_{side}",
            "origin_mm": (0.0, s * HIP_Y_MM, HIP_YAW_DROP_Z_MM),
            "axis": Z_AXIS,
            "range_deg": HIP_YAW_RANGE_DEG,
            "effort_nm": LEG_PRIMARY_EFFORT_NM,
            "velocity_rad_s": LEG_PRIMARY_VELOCITY_RAD_S,
        },
        {
            "name": f"hip_roll_{side}",
            "parent": f"hip_bracket_{side}",
            "child": f"hip_carrier_{side}",
            "origin_mm": HIP_ROLL_ORIGIN_MM,
            "axis": X_AXIS,
            "range_deg": _mirror_range(HIP_ROLL_LEFT_RANGE_DEG, side),
            "effort_nm": LEG_PRIMARY_EFFORT_NM,
            "velocity_rad_s": LEG_PRIMARY_VELOCITY_RAD_S,
        },
        {
            "name": f"hip_pitch_{side}",
            "parent": f"hip_carrier_{side}",
            "child": f"thigh_{side}",
            "origin_mm": HIP_PITCH_ORIGIN_MM,
            "axis": Y_AXIS,
            "range_deg": HIP_PITCH_RANGE_DEG,
            "effort_nm": LEG_PRIMARY_EFFORT_NM,
            "velocity_rad_s": LEG_PRIMARY_VELOCITY_RAD_S,
        },
        {
            "name": f"knee_{side}",
            "parent": f"thigh_{side}",
            "child": f"shin_{side}",
            "origin_mm": KNEE_ORIGIN_MM,
            "axis": Y_AXIS,
            "range_deg": KNEE_RANGE_DEG,
            "effort_nm": LEG_PRIMARY_EFFORT_NM,
            "velocity_rad_s": LEG_PRIMARY_VELOCITY_RAD_S,
        },
        {
            "name": f"ankle_pitch_{side}",
            "parent": f"shin_{side}",
            "child": f"ankle_link_{side}",
            "origin_mm": ANKLE_PITCH_ORIGIN_MM,
            "axis": Y_AXIS,
            "range_deg": ANKLE_PITCH_RANGE_DEG,
            "effort_nm": ANKLE_EFFORT_NM,
            "velocity_rad_s": ANKLE_VELOCITY_RAD_S,
        },
        {
            "name": f"ankle_roll_{side}",
            "parent": f"ankle_link_{side}",
            "child": f"foot_{side}",
            "origin_mm": ANKLE_ROLL_ORIGIN_MM,
            "axis": X_AXIS,
            "range_deg": _mirror_range(ANKLE_ROLL_LEFT_RANGE_DEG, side),
            "effort_nm": ANKLE_EFFORT_NM,
            "velocity_rad_s": ANKLE_VELOCITY_RAD_S,
        },
    ]


def arm_joints(side: str) -> list[dict]:
    s = side_sign(side)
    return [
        {
            "name": f"shoulder_pitch_{side}",
            "parent": "torso",
            "child": f"shoulder_pod_{side}",
            "origin_mm": (0.0, s * SHOULDER_Y_MM, SHOULDER_PITCH_RAISE_Z_MM),
            "axis": Y_AXIS,
            "range_deg": SHOULDER_PITCH_RANGE_DEG,
            "effort_nm": SHOULDER_EFFORT_NM,
            "velocity_rad_s": SHOULDER_VELOCITY_RAD_S,
        },
        {
            "name": f"shoulder_roll_{side}",
            "parent": f"shoulder_pod_{side}",
            "child": f"yaw_housing_{side}",
            "origin_mm": (0.0, s * SHOULDER_ROLL_Y_MM, SHOULDER_ROLL_Z_MM),
            "axis": X_AXIS,
            "range_deg": _mirror_range(SHOULDER_ROLL_LEFT_RANGE_DEG, side),
            "effort_nm": SHOULDER_EFFORT_NM,
            "velocity_rad_s": SHOULDER_VELOCITY_RAD_S,
        },
        {
            "name": f"shoulder_yaw_{side}",
            "parent": f"yaw_housing_{side}",
            "child": f"bicep_{side}",
            "origin_mm": SHOULDER_YAW_ORIGIN_MM,
            "axis": Z_AXIS,
            "range_deg": SHOULDER_YAW_RANGE_DEG,
            "effort_nm": SHOULDER_EFFORT_NM,
            "velocity_rad_s": SHOULDER_VELOCITY_RAD_S,
        },
        {
            "name": f"elbow_{side}",
            "parent": f"bicep_{side}",
            "child": f"forearm_{side}",
            "origin_mm": ELBOW_ORIGIN_MM,
            "axis": Y_AXIS,
            "range_deg": ELBOW_RANGE_DEG,
            "effort_nm": ELBOW_EFFORT_NM,
            "velocity_rad_s": ELBOW_VELOCITY_RAD_S,
        },
        {
            "name": f"wrist_roll_{side}",
            "parent": f"forearm_{side}",
            "child": f"wrist_carrier_{side}",
            "origin_mm": WRIST_ROLL_ORIGIN_MM,
            "axis": Z_AXIS,
            "range_deg": WRIST_ROLL_RANGE_DEG,
            "effort_nm": WRIST_EFFORT_NM,
            "velocity_rad_s": WRIST_VELOCITY_RAD_S,
        },
        {
            "name": f"wrist_pitch_{side}",
            "parent": f"wrist_carrier_{side}",
            "child": f"hand_{side}",
            "origin_mm": WRIST_PITCH_ORIGIN_MM,
            "axis": Y_AXIS,
            "range_deg": WRIST_PITCH_RANGE_DEG,
            "effort_nm": WRIST_EFFORT_NM,
            "velocity_rad_s": WRIST_VELOCITY_RAD_S,
        },
    ]


def all_joints() -> list[dict]:
    """All 27 movable joints in root-to-leaf order (legs then arms per side)."""
    joints = central_joints()
    for side in SIDES:
        joints.extend(leg_joints(side))
    for side in SIDES:
        joints.extend(arm_joints(side))
    return joints


def all_links() -> list[str]:
    """All 28 link names, root first, in joint emission order."""
    links = ["pelvis"]
    for joint in all_joints():
        links.append(joint["child"])
    return links


# ----------------------------------------------------------------- poses
def _athletic_ready_deg() -> dict[str, float]:
    pose = {
        "waist_yaw": WAIST_YAW_DEG,
        "neck_yaw": NECK_YAW_DEG,
        "neck_pitch": NECK_PITCH_DEG,
    }
    for side in SIDES:
        s = side_sign(side)
        pose.update(
            {
                f"hip_yaw_{side}": HIP_YAW_DEG,
                f"hip_roll_{side}": s * HIP_ROLL_ABDUCT_DEG,
                f"hip_pitch_{side}": HIP_PITCH_DEG,
                f"knee_{side}": KNEE_DEG,
                f"ankle_pitch_{side}": ANKLE_PITCH_DEG,
                f"ankle_roll_{side}": -s * HIP_ROLL_ABDUCT_DEG,
                f"shoulder_pitch_{side}": SHOULDER_PITCH_DEG,
                f"shoulder_roll_{side}": s * SHOULDER_ROLL_ABDUCT_DEG,
                f"shoulder_yaw_{side}": -s * SHOULDER_YAW_INTERNAL_DEG,
                f"elbow_{side}": ELBOW_DEG,
                f"wrist_roll_{side}": WRIST_ROLL_DEG,
                f"wrist_pitch_{side}": WRIST_PITCH_DEG,
            }
        )
    return pose


def _wave_right_deg() -> dict[str, float]:
    """Friendly right-hand wave on top of the athletic lower body.

    Right upper arm raised out to the side just above horizontal
    (shoulder roll), full external shoulder yaw so the 90 deg elbow
    carries the forearm vertically up, slight wrist-pitch flick, head
    turned toward the waving hand.
    """
    pose = _athletic_ready_deg()
    pose.update(
        {
            "shoulder_pitch_right": 0.0,
            "shoulder_roll_right": -115.0,
            "shoulder_yaw_right": -90.0,
            "elbow_right": -90.0,
            "wrist_roll_right": 0.0,
            "wrist_pitch_right": -15.0,
            "neck_yaw": -20.0,
            "neck_pitch": -5.0,
        }
    )
    return pose


def _squat_deg() -> dict[str, float]:
    """Deep flat-footed squat: pitch sum stays zero so the soles stay level."""
    pose = _athletic_ready_deg()
    for side in SIDES:
        pose.update(
            {
                f"hip_pitch_{side}": -55.0,
                f"knee_{side}": 85.0,
                f"ankle_pitch_{side}": -30.0,
            }
        )
    return pose


def _t_pose_deg() -> dict[str, float]:
    pose = {name: 0.0 for name in (joint["name"] for joint in all_joints())}
    pose["shoulder_roll_left"] = 90.0
    pose["shoulder_roll_right"] = -90.0
    return pose


def named_poses_deg() -> dict[str, dict[str, float]]:
    """SRDF group-state poses (degrees) for the whole_body group."""
    zero = {name: 0.0 for name in (joint["name"] for joint in all_joints())}
    return {
        "zero": zero,
        "athletic_ready": _athletic_ready_deg(),
        "t_pose": _t_pose_deg(),
        "wave_right": _wave_right_deg(),
        "squat": _squat_deg(),
    }
