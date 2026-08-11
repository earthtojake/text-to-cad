"""lyra kinematic chain spec shared by the CAD assembly and URDF/SRDF.

Stdlib-only (no build123d) so robot-description generators can import it
cheaply. `lyra.py` consumes the same offsets and CAD pose angles, keeping
the STEP assembly, the URDF tree, and the viewer animation sidecar in
lockstep.

Design ledger:
- Units: chain offsets are millimeters in each parent part's local frame;
  URDF emission converts to meters/radians. RIGHT hand frame: origin at the
  wrist-flange mount face center, +Z distal (fingers up), +Y palmar (the
  palm faces +Y), +X radial (thumb side). The palm link is the root; every
  child link frame sits at its joint center with axes parallel to the
  parent at zero joint angle (joints are pure translations).
- Fingers (index/middle/ring/pinky): 3 flexion joints each (MCP, PIP, DIP)
  about -X, so positive angles curl toward the palm (+Y). Phalanges extend
  +Z local. MCP abduction/spread is intentionally omitted: the tendon
  routing budget of the compact palm is spent on flexion; documented
  design trade, not an oversight.
- Thumb: 4 joints. `thumb_cmc_yaw` about +Z swings the column from radial
  (+X, the zero pose) across the palm front toward opposition;
  `thumb_cmc_flex`, `thumb_mp`, `thumb_ip` about -Y curl the column toward
  distal (+Z). Thumb segments extend +X local with the pad facing +Z, so a
  yawed-and-curled thumb meets the curled fingertips pad-to-pad.
- Joint limits, efforts, and velocities are ASSUMED plausible values for a
  tendon-driven research-hand concept (documented here, not measured); the
  CAD does not model hard stops.
"""

from __future__ import annotations

import math

X_AXIS = (1.0, 0.0, 0.0)
Y_AXIS = (0.0, 1.0, 0.0)
Z_AXIS = (0.0, 0.0, 1.0)
NEG_X_AXIS = (-1.0, 0.0, 0.0)
NEG_Y_AXIS = (0.0, -1.0, 0.0)

ROBOT_NAME = "lyra"

FINGERS = ("index", "middle", "ring", "pinky")

# MCP joint centers in the palm frame (mm): a gentle knuckle arch, the
# middle finger proudest, the pinky lower and slightly palmar.
MCP_ORIGIN_MM = {
    "index": (28.5, 0.0, 99.0),
    "middle": (9.5, 0.0, 103.0),
    "ring": (-9.5, 0.0, 99.0),
    "pinky": (-28.5, 0.0, 90.0),
}

# Segment lengths (mm): proximal (MCP->PIP), middle (PIP->DIP), and the
# distal tip length (DIP->fingertip surface) used for pose design.
SEGMENT_MM = {
    "index": (44.0, 26.0, 23.0),
    "middle": (48.0, 29.0, 24.5),
    "ring": (44.0, 27.0, 23.5),
    "pinky": (35.0, 21.0, 20.5),
}

# Thumb column offsets (mm).
THUMB_CMC_ORIGIN_MM = (31.0, 4.0, 44.0)   # turret center on the radial palm corner
THUMB_BASE_LEN_MM = 13.0                  # cmc_yaw -> cmc_flex along the column
THUMB_METACARPAL_LEN_MM = 46.0            # cmc_flex -> MP
THUMB_PROXIMAL_LEN_MM = 30.0              # MP -> IP
THUMB_TIP_LEN_MM = 24.0                   # IP -> thumb-pad surface (pose design)

# ---------------------------------------------------------------- limits
# ASSUMED tendon-driven actuator budget for a research-hand concept.
FINGER_MCP_EFFORT_NM = 3.0
FINGER_PIP_EFFORT_NM = 2.0
FINGER_DIP_EFFORT_NM = 1.5
THUMB_CMC_EFFORT_NM = 4.0
THUMB_MP_EFFORT_NM = 2.5
THUMB_IP_EFFORT_NM = 2.0
FINGER_VELOCITY_RAD_S = 8.0
THUMB_VELOCITY_RAD_S = 6.0

# ASSUMED joint travel (degrees); positive = flexion (curl toward palm).
MCP_RANGE_DEG = (-15.0, 95.0)
PIP_RANGE_DEG = (-5.0, 105.0)
DIP_RANGE_DEG = (-5.0, 95.0)
THUMB_CMC_YAW_RANGE_DEG = (-10.0, 100.0)  # positive sweeps toward opposition
THUMB_CMC_FLEX_RANGE_DEG = (-10.0, 55.0)  # positive lifts the column distal
THUMB_MP_RANGE_DEG = (-10.0, 75.0)
THUMB_IP_RANGE_DEG = (-15.0, 85.0)


def finger_joints(finger: str) -> list[dict]:
    prox, mid, _tip = SEGMENT_MM[finger]
    return [
        {
            "name": f"{finger}_mcp",
            "parent": "palm",
            "child": f"{finger}_proximal",
            "origin_mm": MCP_ORIGIN_MM[finger],
            "axis": NEG_X_AXIS,
            "range_deg": MCP_RANGE_DEG,
            "effort_nm": FINGER_MCP_EFFORT_NM,
            "velocity_rad_s": FINGER_VELOCITY_RAD_S,
        },
        {
            "name": f"{finger}_pip",
            "parent": f"{finger}_proximal",
            "child": f"{finger}_middle",
            "origin_mm": (0.0, 0.0, prox),
            "axis": NEG_X_AXIS,
            "range_deg": PIP_RANGE_DEG,
            "effort_nm": FINGER_PIP_EFFORT_NM,
            "velocity_rad_s": FINGER_VELOCITY_RAD_S,
        },
        {
            "name": f"{finger}_dip",
            "parent": f"{finger}_middle",
            "child": f"{finger}_distal",
            "origin_mm": (0.0, 0.0, mid),
            "axis": NEG_X_AXIS,
            "range_deg": DIP_RANGE_DEG,
            "effort_nm": FINGER_DIP_EFFORT_NM,
            "velocity_rad_s": FINGER_VELOCITY_RAD_S,
        },
    ]


def thumb_joints() -> list[dict]:
    return [
        {
            "name": "thumb_cmc_yaw",
            "parent": "palm",
            "child": "thumb_base",
            "origin_mm": THUMB_CMC_ORIGIN_MM,
            "axis": Z_AXIS,
            "range_deg": THUMB_CMC_YAW_RANGE_DEG,
            "effort_nm": THUMB_CMC_EFFORT_NM,
            "velocity_rad_s": THUMB_VELOCITY_RAD_S,
        },
        {
            "name": "thumb_cmc_flex",
            "parent": "thumb_base",
            "child": "thumb_metacarpal",
            "origin_mm": (THUMB_BASE_LEN_MM, 0.0, 0.0),
            "axis": NEG_Y_AXIS,
            "range_deg": THUMB_CMC_FLEX_RANGE_DEG,
            "effort_nm": THUMB_CMC_EFFORT_NM,
            "velocity_rad_s": THUMB_VELOCITY_RAD_S,
        },
        {
            "name": "thumb_mp",
            "parent": "thumb_metacarpal",
            "child": "thumb_proximal",
            "origin_mm": (THUMB_METACARPAL_LEN_MM, 0.0, 0.0),
            "axis": NEG_Y_AXIS,
            "range_deg": THUMB_MP_RANGE_DEG,
            "effort_nm": THUMB_MP_EFFORT_NM,
            "velocity_rad_s": THUMB_VELOCITY_RAD_S,
        },
        {
            "name": "thumb_ip",
            "parent": "thumb_proximal",
            "child": "thumb_distal",
            "origin_mm": (THUMB_PROXIMAL_LEN_MM, 0.0, 0.0),
            "axis": NEG_Y_AXIS,
            "range_deg": THUMB_IP_RANGE_DEG,
            "effort_nm": THUMB_IP_EFFORT_NM,
            "velocity_rad_s": THUMB_VELOCITY_RAD_S,
        },
    ]


def all_joints() -> list[dict]:
    """All 16 movable joints in root-to-leaf order (fingers, then thumb)."""
    joints: list[dict] = []
    for finger in FINGERS:
        joints.extend(finger_joints(finger))
    joints.extend(thumb_joints())
    return joints


def all_links() -> list[str]:
    """All 17 link names, root first, in joint emission order."""
    links = ["palm"]
    for joint in all_joints():
        links.append(joint["child"])
    return links


# -------------------------------------------------------------------- FK
def _rot_axis(axis, deg: float):
    """3x3 rotation about a principal-ish axis (unit vector), row-major."""
    ax, ay, az = axis
    rad = math.radians(deg)
    c, s = math.cos(rad), math.sin(rad)
    t = 1.0 - c
    return [
        [c + ax * ax * t, ax * ay * t - az * s, ax * az * t + ay * s],
        [ay * ax * t + az * s, c + ay * ay * t, ay * az * t - ax * s],
        [az * ax * t - ay * s, az * ay * t + ax * s, c + az * az * t],
    ]


def _mat_mul(a, b):
    return [
        [sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)]
        for i in range(3)
    ]


def _mat_vec(a, v):
    return tuple(sum(a[i][k] * v[k] for k in range(3)) for i in range(3))


def fk_frames(pose_deg: dict[str, float]) -> dict[str, tuple]:
    """Link frames {link: (R 3x3, p mm)} in the palm frame for a pose."""
    identity = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    frames = {"palm": (identity, (0.0, 0.0, 0.0))}
    for joint in all_joints():
        rot_parent, pos_parent = frames[joint["parent"]]
        offset = _mat_vec(rot_parent, joint["origin_mm"])
        pos = tuple(pos_parent[i] + offset[i] for i in range(3))
        rot = _mat_mul(
            rot_parent, _rot_axis(joint["axis"], pose_deg.get(joint["name"], 0.0))
        )
        frames[joint["child"]] = (rot, pos)
    return frames


def tip_world_mm(pose_deg: dict[str, float], digit: str) -> tuple:
    """Pad-surface point of a digit tip in the palm frame (pose design aid)."""
    frames = fk_frames(pose_deg)
    if digit == "thumb":
        rot, pos = frames["thumb_distal"]
        local = (THUMB_TIP_LEN_MM, 0.0, 0.0)
    else:
        rot, pos = frames[f"{digit}_distal"]
        local = (0.0, 0.0, SEGMENT_MM[digit][2])
    offset = _mat_vec(rot, local)
    return tuple(pos[i] + offset[i] for i in range(3))


# ----------------------------------------------------------------- poses
def _zero_deg() -> dict[str, float]:
    return {joint["name"]: 0.0 for joint in all_joints()}


def _relaxed_deg() -> dict[str, float]:
    """Gentle natural curl; this is the pose baked into lyra.step."""
    pose = _zero_deg()
    curl = {
        "index": (10.0, 14.0, 8.0),
        "middle": (12.0, 16.0, 9.0),
        "ring": (14.0, 18.0, 10.0),
        "pinky": (16.0, 20.0, 12.0),
    }
    for finger, (mcp, pip_deg, dip) in curl.items():
        pose[f"{finger}_mcp"] = mcp
        pose[f"{finger}_pip"] = pip_deg
        pose[f"{finger}_dip"] = dip
    pose.update(
        {
            "thumb_cmc_yaw": 34.0,
            "thumb_cmc_flex": 26.0,
            "thumb_mp": 14.0,
            "thumb_ip": 12.0,
        }
    )
    return pose


def _fist_deg() -> dict[str, float]:
    pose = _zero_deg()
    for finger in FINGERS:
        pose[f"{finger}_mcp"] = 78.0
        pose[f"{finger}_pip"] = 100.0
        pose[f"{finger}_dip"] = 60.0
    # Capsule-tuned wrap: the thumb pad rests on the index middle phalanx
    # with ~0.8 mm surface clearance (no interpenetration at any digit).
    pose.update(
        {
            "thumb_cmc_yaw": 92.0,
            "thumb_cmc_flex": 13.0,
            "thumb_mp": 58.0,
            "thumb_ip": 74.0,
        }
    )
    return pose


def _precision_pinch_deg() -> dict[str, float]:
    """Thumb-index pad opposition, capsule-tuned so the tip pads kiss with
    ~0.8 mm surface clearance (no tip-sphere interpenetration)."""
    pose = _zero_deg()
    pose.update({"index_mcp": 40.0, "index_pip": 48.0, "index_dip": 30.0})
    for finger in ("middle", "ring", "pinky"):
        pose[f"{finger}_mcp"] = 66.0
        pose[f"{finger}_pip"] = 92.0
        pose[f"{finger}_dip"] = 55.0
    pose.update(
        {
            "thumb_cmc_yaw": 91.0,
            "thumb_cmc_flex": 34.0,
            "thumb_mp": 29.0,
            "thumb_ip": 8.0,
        }
    )
    return pose


def _tripod_pinch_deg() -> dict[str, float]:
    """Thumb opposed between index and middle pads, chuck-gripping a
    virtual object (capsule-tuned: ~12 mm pad-surface gap to both)."""
    pose = _precision_pinch_deg()
    pose.update({"index_mcp": 44.0, "index_pip": 52.0, "index_dip": 32.0})
    pose.update({"middle_mcp": 42.0, "middle_pip": 50.0, "middle_dip": 30.0})
    pose.update(
        {
            "thumb_cmc_yaw": 100.0,
            "thumb_cmc_flex": 39.0,
            "thumb_mp": 0.0,
            "thumb_ip": 14.0,
        }
    )
    return pose


def _point_deg() -> dict[str, float]:
    pose = _zero_deg()
    pose.update({"index_mcp": -6.0, "index_pip": 0.0, "index_dip": 0.0})
    for finger in ("middle", "ring", "pinky"):
        pose[f"{finger}_mcp"] = 80.0
        pose[f"{finger}_pip"] = 102.0
        pose[f"{finger}_dip"] = 62.0
    pose.update(
        {
            "thumb_cmc_yaw": 62.0,
            "thumb_cmc_flex": 30.0,
            "thumb_mp": 42.0,
            "thumb_ip": 45.0,
        }
    )
    return pose


def _ok_sign_deg() -> dict[str, float]:
    """Index-thumb ring closed, remaining fingers extended with a stagger."""
    pose = _zero_deg()
    pose.update({"index_mcp": 42.0, "index_pip": 52.0, "index_dip": 32.0})
    pose.update({"middle_mcp": 6.0, "middle_pip": 8.0, "middle_dip": 4.0})
    pose.update({"ring_mcp": 10.0, "ring_pip": 12.0, "ring_dip": 6.0})
    pose.update({"pinky_mcp": 14.0, "pinky_pip": 16.0, "pinky_dip": 8.0})
    pose.update(
        {
            "thumb_cmc_yaw": 91.0,
            "thumb_cmc_flex": 26.0,
            "thumb_mp": 35.0,
            "thumb_ip": 20.0,
        }
    )
    return pose


BAKED_POSE_NAME = "relaxed"


def named_poses_deg() -> dict[str, dict[str, float]]:
    """SRDF group-state poses (degrees) for the full hand."""
    return {
        "zero": _zero_deg(),
        "relaxed": _relaxed_deg(),
        "fist": _fist_deg(),
        "precision_pinch": _precision_pinch_deg(),
        "tripod_pinch": _tripod_pinch_deg(),
        "point": _point_deg(),
        "ok_sign": _ok_sign_deg(),
    }
