"""juno's seven clips as poses over a cycle: the old ``ANIMATION_JS`` gaits, in Python.

Stdlib-only, like ``chain.py``. Each gait is a function of its phase (0..1 over the
clip) returning the old module's frame inputs, ``(angles, extras, root_offset,
root_pitch_deg)``:

- ``angles``: the 27 joints' absolute angles (degrees), the IK included;
- ``extras``: ``{joint: {"pitchDeg", "rollDeg"}}``, an extra rotation folded in at a
  joint's centre that no joint has (the torso's lean and roll at ``waist_yaw``);
- ``root_offset``: the pelvis's translation (mm) in the world;
- ``root_pitch_deg``: the whole body's pitch about +Y at the pelvis (the handstand).

``fk_frames`` is the old ``fkFrames``: the chain FK with the three folded in, which the
handstand's contact anchors and the checks use. ``juno.py`` turns each gait into a
motion: the angles, and the root offset's Z on ``pelvis_lift``, the one joint between
the world and the pelvis (src/README.md, "Motions", says what that loses).

Two gaits take ``pelvis_dy``: the lateral pelvis shift of the kick and the dance. The
old clips shifted the pelvis sideways over the stance leg and rolled the planted legs to
keep the feet where they were; ``pelvis_dy=0.0`` solves the same contacts under a pelvis
that does not shift, so a planted foot stays where the old IK planted it.
"""

from __future__ import annotations

import math

from . import chain

X = chain.X_AXIS
Y = chain.Y_AXIS
Z = chain.Z_AXIS
SIDES = chain.SIDES
_s = chain.side_sign

HIP_Y = chain.HIP_Y_MM

# ---------------------------------------------------------------- the old constants
# Gait amplitudes (deg) at parameter scale 1. Sign conventions follow the chain
# ledger: pitch about +Y (negative = forward), roll about +X (positive = toward
# robot-left), yaw about +Z (positive = turn left).
HIP_LIFT_DEG = 24.0        # swing-leg thigh raise (forward = negative pitch)
KNEE_FOLD_DEG = 44.0       # extra swing-leg knee flexion
TOE_POINT_DEG = 8.0        # slight toes-down of the airborne foot
ARM_SWING_DEG = 12.0       # shoulder pitch swing, antiphase to own-side leg
ELBOW_EXTRA_DEG = 10.0     # extra elbow flexion on the forward arm swing
WAIST_SWAY_DEG = 4.0       # torso counter-rotation about the waist yaw axis
TORSO_ROLL_DEG = 1.2       # weight-shift hint, roll about +X at the waist
NECK_COMPENSATION = 0.8    # head stabilization fraction against waist sway

# Swing windows of the normalized cycle (left lifts first), with double-support
# dwell between them.
SWING = {"left": (0.05, 0.45), "right": (0.55, 0.95)}

# Stride gait (treadmill-style walk in place): the stance foot slides backward flat
# on the ground while the swing leg passes through the air, both solved with planar
# two-link leg IK in each leg's (slightly rolled) sagittal plane.
THIGH_LEN = 290.0
SHIN_LEN = 290.0
STANCE_FRACTION = 0.58
STRIDE_LIFT_MM = 60.0
STRIDE_TOE_OFF_DEG = 14.0
STRIDE_HEEL_DEG = 10.0
STRIDE_ARM_FACTOR = 1.5
STRIDE_SWAY_FACTOR = 1.25
MAX_STRIDE_MM = 300.0
DEFAULT_STRIDE_MM = 230.0
STRIDE_PHASE = {"left": 0.0, "right": 0.5}
STRIDE_MID_SWING = {
    side: (STRIDE_PHASE[side] + STANCE_FRACTION + (1 - STANCE_FRACTION) / 2) % 1 for side in SIDES
}

# Run gait: short ground contacts with a flight phase between them, a vertical body
# bounce absorbed by the stance-leg IK, toe-pivot heel-off into push-off, high
# heel-recovery swing, forward torso lean, and pumping bent arms.
RUN_STANCE_FRACTION = 0.35
RUN_PHASE = {"left": 0.0, "right": 0.5}
RUN_MID_STANCE = {"left": RUN_STANCE_FRACTION / 2, "right": (0.5 + RUN_STANCE_FRACTION / 2) % 1}
RUN_MID_SWING = {
    "left": (RUN_STANCE_FRACTION + (1 - RUN_STANCE_FRACTION) / 2) % 1,
    "right": (0.5 + RUN_STANCE_FRACTION + (1 - RUN_STANCE_FRACTION) / 2) % 1,
}
RUN_CONTACT_SHARE = 0.3
RUN_BOUNCE_MM = 22.0
RUN_APEX_MM = 140.0
RUN_HEEL_OFF_DEG = 26.0
RUN_HEEL_OFF_START = 0.62
RUN_HEEL_IN_DEG = 8.0
RUN_TOE_PIVOT_X_MM = 112.0
RUN_ANKLE_HEIGHT_MM = 56.0
RUN_LEAN_DEG = 7.0
RUN_ARM_SWING_DEG = 26.0
RUN_ELBOW_BASE_DEG = -60.0
RUN_ELBOW_PUMP_DEG = 15.0
RUN_SWAY_DEG = 5.0
RUN_ROLL_DEG = 1.6

# Jump gait: countermovement crouch -> push -> ballistic flight with toe point and
# leg tuck -> springy landing -> recover.
JUMP_TIMING = {"crouch": 0.18, "push": 0.3, "land": 0.62, "absorb": 0.74}
JUMP_CROUCH_MM = 120.0
JUMP_TAKEOFF_MM = 20.0
JUMP_APEX_MM = 160.0
JUMP_TUCK_MM = 250.0
JUMP_TOE_POINT_DEG = 25.0
JUMP_LAND_DIP_MM = -80.0
JUMP_SPRING_DECAY = 3.5
JUMP_SPRING_CYCLES = 1.25
JUMP_ARM_BACK_DEG = 30.0
JUMP_ARM_UP_DEG = -155.0
JUMP_ARM_V_DEG = 20.0
JUMP_ARM_SPRING_DEG_PER_MM = 0.3
JUMP_LEAN_DEG = 8.0
JUMP_HEAD_UP_DEG = -8.0

# Showpieces: the lateral pendulum for weight shifts (the hip-roll joint sits at
# z=-184 in the pelvis frame).
HIP_ROLL_Z_MM = -184.0
KICK_WEIGHT_SHIFT_MM = 42.0
KICK_DIP_MM = 18.0
KICK_CHAMBER_HIP_DEG = -70.0
KICK_CHAMBER_KNEE_DEG = 115.0
KICK_CHAMBER_ANKLE_DEG = 10.0
KICK_EXTEND_HIP_DEG = -20.0
KICK_EXTEND_KNEE_DEG = -105.0
KICK_EXTEND_ANKLE_DEG = -25.0
KICK_GUARD_SHOULDER_DEG = -45.0
KICK_GUARD_ELBOW_DEG = -105.0
KICK_GUARD_ROLL_OUT_DEG = 18.0
KICK_HIP_TURN_DEG = -14.0
KICK_LEAN_BACK_DEG = -7.0
# Handstand: keyframed root rotation about +Y with contact anchoring.
HS_PLANT_X_MM = 430.0
HS_PALM_LOCAL_MM = (-35.0, 0.0, -70.0)
HS_TOE_LOCAL_MM = (112.0, 0.0, -26.0)
HS_WOBBLE_DEG = 1.6
# Elvis dance (4 beats).
ELVIS_BEATS = 4
ELVIS_WEIGHT_SHIFT_MM = -55.0
ELVIS_DIP_MM = 20.0
ELVIS_BOUNCE_MM = 8.0
ELVIS_TOE_X_MM = 80.0
ELVIS_TOE_Y_MM = 330.0
ELVIS_TOE_SHAKE_MM = 28.0
ELVIS_FOOT_POINT_DEG = 55.0
ELVIS_FOOT_POINT_SHAKE_DEG = 7.0
ELVIS_TOE_TIP_X = 112.0
ELVIS_TOE_TIP_DROP = 56.0
ELVIS_POINT_ROLL_DEG = -115.0
ELVIS_POINT_PITCH_DEG = -25.0
ELVIS_POINT_ELBOW_DEG = -12.0
ELVIS_POINT_PULSE_DEG = 8.0
ELVIS_OFF_ARM_PITCH_DEG = -30.0
ELVIS_OFF_ARM_ELBOW_DEG = -70.0
ELVIS_TWIST_DEG = 10.0
ELVIS_LEAN_RIGHT_DEG = -3.0
ELVIS_HEAD_TURN_DEG = -20.0
ELVIS_CHIN_UP_DEG = -5.0

# The published defaults the old clips baked in (the retired sidecar's live
# parameters).
LEG_LIFT = 1.0
ARM_SWING = 1.0
TORSO_SWAY = 1.0
STRIDE_LENGTH = DEFAULT_STRIDE_MM

ATHLETIC = chain.athletic_ready_deg()
JOINTS = chain.all_joints()


# ---------------------------------------------------------------- math and FK
def clamp(value: float, low: float, high: float) -> float:
    return min(max(value, low), high)


def smooth01(value: float) -> float:
    t = clamp(value, 0.0, 1.0)
    return t * t * (3 - 2 * t)


def pulse(t: float, in_start: float, in_end: float, out_start: float, out_end: float) -> float:
    """Smooth on/off window: up over [in_start, in_end], down over [out_start, out_end]."""
    return smooth01((t - in_start) / max(1e-9, in_end - in_start)) * (
        1 - smooth01((t - out_start) / max(1e-9, out_end - out_start)))


def _rot(axis, deg: float) -> list[list[float]]:
    rad = math.radians(deg)
    c, s = math.cos(rad), math.sin(rad)
    if axis == X:
        return [[1.0, 0.0, 0.0], [0.0, c, -s], [0.0, s, c]]
    if axis == Y:
        return [[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]]
    return [[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]]


def _mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def _apply(a, v):
    return [sum(a[i][k] * v[k] for k in range(3)) for i in range(3)]


_IDENTITY = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]


def fk_frames(angles: dict[str, float], extras: dict | None = None, root_offset=(0.0, 0.0, 0.0),
              root_pitch_deg: float = 0.0) -> dict[str, dict]:
    """Every link's world frame ``{"R", "p"}``: the old ``fkFrames``. ``extras[joint]``
    folds ``pitchDeg`` (+Y) then ``rollDeg`` (+X) in after the joint's own turn;
    ``root_offset`` translates and ``root_pitch_deg`` pitches the pelvis."""
    extras = extras or {}
    frames = {"pelvis": {"R": _rot(Y, root_pitch_deg) if root_pitch_deg else _IDENTITY, "p": list(root_offset)}}
    for joint in JOINTS:
        parent = frames[joint["parent"]]
        offset = _apply(parent["R"], joint["origin_mm"])
        p = [parent["p"][k] + offset[k] for k in range(3)]
        R = _mul(parent["R"], _rot(joint["axis"], angles.get(joint["name"], 0.0)))
        extra = extras.get(joint["name"]) or {}
        if extra.get("pitchDeg"):
            R = _mul(R, _rot(Y, extra["pitchDeg"]))
        if extra.get("rollDeg"):
            R = _mul(R, _rot(X, extra["rollDeg"]))
        frames[joint["child"]] = {"R": R, "p": p}
    return frames


def point(frame: dict, local) -> list[float]:
    """A link-local point (mm) in the world."""
    moved = _apply(frame["R"], local)
    return [moved[k] + frame["p"][k] for k in range(3)]


ATHLETIC_FRAMES = fk_frames(ATHLETIC)


def _stride_rig() -> dict[str, dict[str, float]]:
    """Per-side IK constants from the athletic FK: the hip-pitch centre's height, the
    hip roll's cosine, the sole plane and the flat foot's ankle-to-sole height."""
    rig = {}
    for side in SIDES:
        hip = ATHLETIC_FRAMES[f"thigh_{side}"]["p"]
        foot = ATHLETIC_FRAMES[f"foot_{side}"]
        roll = math.radians(_s(side) * chain.HIP_ROLL_ABDUCT_DEG)
        sole_z = foot["p"][2] + _apply(foot["R"], (0.0, 0.0, -26.0))[2]
        rig[side] = {"hipZ": hip[2], "cosRoll": math.cos(roll), "soleZ": sole_z,
                     "ankleToSole": 30 * math.cos(roll) + 26}
    return rig


STRIDE_RIG = _stride_rig()
# The athletic left toe tip (x, y): where the dance's kick-out starts and ends.
ELVIS_ATHLETIC_TOE = point(ATHLETIC_FRAMES["foot_left"], (112.0, 0.0, -26.0))[:2]


def swing_envelope(phase: float, window: tuple[float, float]) -> float:
    """Raised cosine: 0 at lift-off and touch-down, 1 mid-swing, 0 outside the window."""
    p = phase % 1
    start, end = window
    if p <= start or p >= end:
        return 0.0
    lobe = math.sin(math.pi * (p - start) / (end - start))
    return lobe * lobe


def forwardness(phase: float, peak_at: float) -> float:
    return math.cos(2 * math.pi * (phase - peak_at))


def leg_pitch_ik(dx: float, d: float, foot_pitch_deg: float) -> tuple[float, float, float]:
    """Two-link planar leg IK in the rolled sagittal plane: the ankle-pitch joint at
    forward offset ``dx`` and plane depth ``d`` from the hip-pitch joint, the foot at
    world pitch ``foot_pitch_deg``. Returns (hip pitch, knee, ankle pitch)."""
    dist = clamp(math.hypot(dx, d), abs(THIGH_LEN - SHIN_LEN) + 1, THIGH_LEN + SHIN_LEN - 1)
    phi = math.atan2(dx, d)
    cos_interior = clamp((THIGH_LEN ** 2 + SHIN_LEN ** 2 - dist ** 2) / (2 * THIGH_LEN * SHIN_LEN), -1, 1)
    knee = math.pi - math.acos(cos_interior)
    cos_beta = clamp((THIGH_LEN ** 2 + dist ** 2 - SHIN_LEN ** 2) / (2 * THIGH_LEN * dist), -1, 1)
    thigh = phi + math.acos(cos_beta)
    hip_deg = -math.degrees(thigh)
    knee_deg = math.degrees(knee)
    return hip_deg, knee_deg, foot_pitch_deg - (hip_deg + knee_deg)


def _set_leg(angles: dict[str, float], side: str, ik: tuple[float, float, float]) -> None:
    angles[f"hip_pitch_{side}"], angles[f"knee_{side}"], angles[f"ankle_pitch_{side}"] = ik


# ---------------------------------------------------------------- walk (the march)
def walk(phase: float):
    """In-place march: each leg swings in its own window, exactly athletic outside it,
    so the stance foot stays planted; arms antiphase, torso counter-sway, head steady."""
    angles = dict(ATHLETIC)
    for side in SIDES:
        env = swing_envelope(phase, SWING[side]) * LEG_LIFT
        hip = -HIP_LIFT_DEG * env
        knee = KNEE_FOLD_DEG * env
        angles[f"hip_pitch_{side}"] += hip
        angles[f"knee_{side}"] += knee
        angles[f"ankle_pitch_{side}"] += -(hip + knee) + TOE_POINT_DEG * env
        own_leg_peak = 0.25 if side == "left" else 0.75
        arm_forward = forwardness(phase, own_leg_peak + 0.5) * ARM_SWING
        angles[f"shoulder_pitch_{side}"] += -ARM_SWING_DEG * arm_forward
        angles[f"elbow_{side}"] += -ELBOW_EXTRA_DEG * max(0.0, arm_forward)
    sway = WAIST_SWAY_DEG * TORSO_SWAY * math.sin(2 * math.pi * phase)
    angles["waist_yaw"] += sway
    angles["neck_yaw"] += -sway * NECK_COMPENSATION
    extras = {"waist_yaw": {"rollDeg": -TORSO_ROLL_DEG * TORSO_SWAY * math.sin(2 * math.pi * phase)}}
    return angles, extras, (0.0, 0.0, 0.0), 0.0


# ---------------------------------------------------------------- stride
def stride(phase: float):
    """Treadmill stride: the stance foot slides back flat on the ground, the swing leg
    returns through the air with toe-off and heel-strike accents (both by leg IK)."""
    angles = dict(ATHLETIC)
    length = clamp(STRIDE_LENGTH, 0, MAX_STRIDE_MM)
    for side in SIDES:
        rig = STRIDE_RIG[side]
        q = (phase + STRIDE_PHASE[side]) % 1
        if q < STANCE_FRACTION:
            s = q / STANCE_FRACTION
            ankle_x = length / 2 - length * s
            sole_z = rig["soleZ"]
            foot_pitch = 0.0
        else:
            u = (q - STANCE_FRACTION) / (1 - STANCE_FRACTION)
            ankle_x = -length / 2 + length * smooth01(u)
            lobe = math.sin(math.pi * u)
            reach = length / DEFAULT_STRIDE_MM
            sole_z = rig["soleZ"] + STRIDE_LIFT_MM * clamp(LEG_LIFT, 0, 1.4) * lobe * reach
            foot_pitch = (STRIDE_TOE_OFF_DEG * lobe * (1 - u) - STRIDE_HEEL_DEG * lobe * u) * reach
        depth = (rig["hipZ"] - (sole_z + rig["ankleToSole"])) / rig["cosRoll"]
        _set_leg(angles, side, leg_pitch_ik(ankle_x, depth, foot_pitch))
        other = "right" if side == "left" else "left"
        arm_forward = forwardness(phase, STRIDE_MID_SWING[other]) * ARM_SWING * STRIDE_ARM_FACTOR
        angles[f"shoulder_pitch_{side}"] += -ARM_SWING_DEG * arm_forward
        angles[f"elbow_{side}"] += -ELBOW_EXTRA_DEG * max(0.0, arm_forward)
    sway = WAIST_SWAY_DEG * STRIDE_SWAY_FACTOR * TORSO_SWAY * forwardness(phase, STRIDE_MID_SWING["left"])
    angles["waist_yaw"] += sway
    angles["neck_yaw"] += -sway * NECK_COMPENSATION
    roll = -TORSO_ROLL_DEG * STRIDE_SWAY_FACTOR * TORSO_SWAY * forwardness(phase, STRIDE_MID_SWING["left"])
    return angles, {"waist_yaw": {"rollDeg": roll}}, (0.0, 0.0, 0.0), 0.0


# ---------------------------------------------------------------- run
def run_bounce_mm(phase: float) -> float:
    """Twice a cycle: lowest at each mid-stance, highest at mid-flight."""
    return -RUN_BOUNCE_MM * clamp(LEG_LIFT, 0, 1.4) * math.cos(4 * math.pi * (phase - RUN_MID_STANCE["left"]))


def _run_stance_target(s: float, length: float, reach: float, rig: dict) -> tuple[float, float, float]:
    """The stance ankle with a toe-pivot heel-off: the foot pivots about the sole's
    front edge so the heel rises into push-off without the toe digging in."""
    flat_x = length * RUN_CONTACT_SHARE - length * s
    pitch = 0.0
    if s > RUN_HEEL_OFF_START:
        pitch = RUN_HEEL_OFF_DEG * reach * smooth01((s - RUN_HEEL_OFF_START) / (1 - RUN_HEEL_OFF_START))
    c, sn = math.cos(math.radians(pitch)), math.sin(math.radians(pitch))
    ankle_x = flat_x + RUN_TOE_PIVOT_X_MM * (1 - c) + RUN_ANKLE_HEIGHT_MM * sn
    ankle_z = rig["soleZ"] + RUN_TOE_PIVOT_X_MM * sn + rig["ankleToSole"] * c
    return ankle_x, ankle_z, pitch


def run(phase: float):
    angles = dict(ATHLETIC)
    length = clamp(STRIDE_LENGTH, 0, MAX_STRIDE_MM)
    reach = length / DEFAULT_STRIDE_MM
    lift = clamp(LEG_LIFT, 0, 1.4)
    bounce = run_bounce_mm(phase)
    for side in SIDES:
        rig = STRIDE_RIG[side]
        q = (phase + RUN_PHASE[side]) % 1
        if q < RUN_STANCE_FRACTION:
            ankle_x, ankle_z, pitch = _run_stance_target(q / RUN_STANCE_FRACTION, length, reach, rig)
        else:
            u = (q - RUN_STANCE_FRACTION) / (1 - RUN_STANCE_FRACTION)
            t = smooth01(u)
            end_x, end_z, end_pitch = _run_stance_target(1, length, reach, rig)
            contact_x = length * RUN_CONTACT_SHARE
            contact_z = rig["soleZ"] + rig["ankleToSole"]
            ankle_x = end_x + (contact_x - end_x) * t
            ankle_z = end_z + (contact_z - end_z) * t + RUN_APEX_MM * lift * reach * math.sin(math.pi * u)
            pitch = end_pitch * (1 - t) * (1 - t) - RUN_HEEL_IN_DEG * reach * math.sin(math.pi * u) * u
        depth = (rig["hipZ"] + bounce - ankle_z) / rig["cosRoll"]
        _set_leg(angles, side, leg_pitch_ik(ankle_x, depth, pitch))
        other = "right" if side == "left" else "left"
        arm_forward = forwardness(phase, RUN_MID_SWING[other]) * ARM_SWING
        angles[f"shoulder_pitch_{side}"] += -RUN_ARM_SWING_DEG * arm_forward
        angles[f"elbow_{side}"] += (RUN_ELBOW_BASE_DEG * clamp(ARM_SWING, 0, 1.5)
                                    - RUN_ELBOW_PUMP_DEG * max(0.0, arm_forward))
    sway = RUN_SWAY_DEG * TORSO_SWAY * forwardness(phase, RUN_MID_SWING["left"])
    angles["waist_yaw"] += sway
    angles["neck_yaw"] += -sway * NECK_COMPENSATION
    angles["neck_pitch"] += -RUN_LEAN_DEG * NECK_COMPENSATION
    roll = RUN_ROLL_DEG * TORSO_SWAY * forwardness(phase, RUN_MID_STANCE["left"])
    return angles, {"waist_yaw": {"pitchDeg": RUN_LEAN_DEG, "rollDeg": roll}}, (0.0, 0.0, bounce), 0.0


# ---------------------------------------------------------------- jump
def jump_body_z_mm(phase: float, lift: float) -> float:
    p = phase % 1
    crouch, push, land, absorb = (JUMP_TIMING[k] for k in ("crouch", "push", "land", "absorb"))
    if p < crouch:
        return -JUMP_CROUCH_MM * lift * smooth01(p / crouch)
    if p < push:
        t = smooth01((p - crouch) / (push - crouch))
        return -JUMP_CROUCH_MM * lift + (JUMP_TAKEOFF_MM + JUMP_CROUCH_MM * lift) * t
    if p < land:
        t = (p - push) / (land - push)
        apex = JUMP_APEX_MM * lift
        return JUMP_TAKEOFF_MM + (apex - JUMP_TAKEOFF_MM) * (1 - (2 * t - 1) * (2 * t - 1))
    if p < absorb:
        t = smooth01((p - land) / (absorb - land))
        return JUMP_TAKEOFF_MM + (JUMP_LAND_DIP_MM * lift - JUMP_TAKEOFF_MM) * t
    t = (p - absorb) / (1 - absorb)
    return JUMP_LAND_DIP_MM * lift * math.exp(-JUMP_SPRING_DECAY * t) * math.cos(2 * math.pi * JUMP_SPRING_CYCLES * t)


def _jump_flight(phase: float) -> float:
    p = phase % 1
    push, land = JUMP_TIMING["push"], JUMP_TIMING["land"]
    return 0.0 if p <= push or p >= land else (p - push) / (land - push)


def _jump_shoulder_pitch(phase: float, body_z: float) -> float:
    p = phase % 1
    crouch, push, land, absorb = (JUMP_TIMING[k] for k in ("crouch", "push", "land", "absorb"))
    athletic = chain.SHOULDER_PITCH_DEG
    if p < crouch:
        return athletic + (JUMP_ARM_BACK_DEG - athletic) * smooth01(p / crouch)
    if p < push:
        return JUMP_ARM_BACK_DEG + (JUMP_ARM_UP_DEG - JUMP_ARM_BACK_DEG) * smooth01((p - crouch) / (push - crouch))
    if p < land:
        return JUMP_ARM_UP_DEG
    dipped = JUMP_ARM_UP_DEG + abs(min(0.0, body_z)) * JUMP_ARM_SPRING_DEG_PER_MM
    if p < absorb:
        return dipped
    return dipped + (athletic - dipped) * smooth01((p - absorb) / (1 - absorb))


def jump(phase: float):
    """Crouch, leap with hands overhead, springy knee-absorbed landing, settle."""
    angles = dict(ATHLETIC)
    lift = clamp(LEG_LIFT, 0, 1.4)
    body_z = jump_body_z_mm(phase, lift)
    flight = _jump_flight(phase)
    tuck = math.sin(math.pi * flight)
    for side in SIDES:
        rig = STRIDE_RIG[side]
        ankle_z = rig["soleZ"] + rig["ankleToSole"] + (JUMP_TUCK_MM * lift * tuck if flight > 0 else 0.0)
        pitch = JUMP_TOE_POINT_DEG * tuck if flight > 0 else 0.0
        depth = (rig["hipZ"] + body_z - ankle_z) / rig["cosRoll"]
        _set_leg(angles, side, leg_pitch_ik(0.0, depth, pitch))
        shoulder = _jump_shoulder_pitch(phase, body_z)
        raised = clamp((shoulder - chain.SHOULDER_PITCH_DEG) / (JUMP_ARM_UP_DEG - chain.SHOULDER_PITCH_DEG), 0, 1)
        arm_scale = clamp(ARM_SWING, 0, 1.5)
        angles[f"shoulder_pitch_{side}"] = chain.SHOULDER_PITCH_DEG + (shoulder - chain.SHOULDER_PITCH_DEG) * arm_scale
        angles[f"shoulder_roll_{side}"] += _s(side) * JUMP_ARM_V_DEG * raised * arm_scale
        angles[f"elbow_{side}"] = chain.ELBOW_DEG + 5 * raised * arm_scale
    angles["neck_pitch"] += JUMP_HEAD_UP_DEG * tuck
    compression = clamp(-min(0.0, body_z) / JUMP_CROUCH_MM, 0, 1.2)
    lean = JUMP_LEAN_DEG * compression * (1 - flight) * clamp(TORSO_SWAY, 0, 1.5)
    return angles, {"waist_yaw": {"pitchDeg": lean}}, (0.0, 0.0, body_z), 0.0


# ---------------------------------------------------------------- the showpieces
def planted_leg(side: str, body_z: float, pelvis_dy: float) -> dict[str, float]:
    """A planted leg under a bobbing, shifted pelvis: the pitch IK keeps the sole at
    ground height, a hip/ankle roll pair absorbs the lateral shift."""
    rig = STRIDE_RIG[side]
    s = _s(side)
    depth = (rig["hipZ"] + body_z - (rig["soleZ"] + rig["ankleToSole"])) / rig["cosRoll"]
    hip, knee, ankle = leg_pitch_ik(0.0, depth, 0.0)
    roll_delta = math.degrees(math.asin(clamp(pelvis_dy / (HIP_ROLL_Z_MM - rig["soleZ"]), -0.5, 0.5)))
    roll = s * chain.HIP_ROLL_ABDUCT_DEG - roll_delta
    return {f"hip_pitch_{side}": hip, f"knee_{side}": knee, f"ankle_pitch_{side}": ankle,
            f"hip_roll_{side}": roll, f"ankle_roll_{side}": -roll}


def kick(phase: float, pelvis_dy: float | None = None):
    """Karate front kick: weight onto the left leg, the right leg chambers and snaps a
    ball-of-foot kick at hip height behind a fists-up guard, re-chambers and plants.
    ``pelvis_dy`` overrides the old lateral weight shift (42 mm at full weight)."""
    t = phase
    angles = dict(ATHLETIC)
    weight = pulse(t, 0.0, 0.12, 0.86, 0.98)
    chamber = pulse(t, 0.14, 0.3, 0.72, 0.88)
    extend = pulse(t, 0.36, 0.48, 0.58, 0.7)
    guard = pulse(t, 0.04, 0.16, 0.8, 0.94)
    dy = KICK_WEIGHT_SHIFT_MM * weight if pelvis_dy is None else pelvis_dy
    body_z = -KICK_DIP_MM * chamber
    angles.update(planted_leg("left", body_z, dy))
    angles["hip_pitch_right"] = (chain.HIP_PITCH_DEG + (KICK_CHAMBER_HIP_DEG - chain.HIP_PITCH_DEG) * chamber
                                 + KICK_EXTEND_HIP_DEG * extend)
    angles["knee_right"] = chain.KNEE_DEG + (KICK_CHAMBER_KNEE_DEG - chain.KNEE_DEG) * chamber + KICK_EXTEND_KNEE_DEG * extend
    angles["ankle_pitch_right"] = (chain.ANKLE_PITCH_DEG + (KICK_CHAMBER_ANKLE_DEG - chain.ANKLE_PITCH_DEG) * chamber
                                   + KICK_EXTEND_ANKLE_DEG * extend)
    angles["ankle_roll_right"] = -_s("right") * chain.HIP_ROLL_ABDUCT_DEG
    for side in SIDES:
        s = _s(side)
        angles[f"shoulder_pitch_{side}"] = (chain.SHOULDER_PITCH_DEG
                                            + (KICK_GUARD_SHOULDER_DEG - chain.SHOULDER_PITCH_DEG) * guard)
        angles[f"shoulder_roll_{side}"] = s * chain.SHOULDER_ROLL_ABDUCT_DEG + s * KICK_GUARD_ROLL_OUT_DEG * guard
        angles[f"elbow_{side}"] = chain.ELBOW_DEG + (KICK_GUARD_ELBOW_DEG - chain.ELBOW_DEG) * guard
    turn = KICK_HIP_TURN_DEG * (0.5 * chamber + 0.5 * extend)
    angles["waist_yaw"] += turn
    angles["neck_yaw"] += -turn * NECK_COMPENSATION
    return angles, {"waist_yaw": {"pitchDeg": KICK_LEAN_BACK_DEG * extend}}, (0.0, dy, body_z), 0.0


def _anchored_root_offset(angles, root_pitch_deg, link, local, target):
    """The root translation putting ``link``'s ``local`` point on ``target`` (a None
    component left where the pose puts it)."""
    world = point(fk_frames(angles, {}, (0.0, 0.0, 0.0), root_pitch_deg)[link], local)
    return tuple(0.0 if aim is None else aim - world[k] for k, aim in enumerate(target))


def _handstand_key_angles(legs: dict | None, arms: dict | None, neck_pitch: float | None = None) -> dict[str, float]:
    angles = dict(ATHLETIC)
    for side in SIDES:
        # Square the limbs for the gymnastic line: no abduction or twist.
        for name in ("hip_roll", "ankle_roll", "shoulder_yaw", "wrist_pitch"):
            angles[f"{name}_{side}"] = 0.0
        for name, value in (legs or {}).items():
            angles[f"{name}_{side}"] = value
        for name, value in (arms or {}).items():
            angles[f"{name}_{side}"] = value
    if neck_pitch is not None:
        angles["neck_pitch"] = neck_pitch
    return angles


def _handstand_keys():
    toe_world = point(ATHLETIC_FRAMES["foot_left"], HS_TOE_LOCAL_MM)
    toe_target = (toe_world[0], None, toe_world[2])
    ground = STRIDE_RIG["left"]["soleZ"]
    palm_target = (HS_PLANT_X_MM, None, ground)
    hold_arms = {"shoulder_pitch": -180.0, "shoulder_roll": 0.0, "elbow": -18.0, "wrist_roll": 0.0, "wrist_pitch": -70.0}
    # (t, root pitch, anchor, solve the press hip, legs, arms)
    spec = [
        (0.0, 0.0, None, False, None, None),
        (0.09, 12.0, "toe", False, {"hip_pitch": -30.0, "knee": 20.0, "ankle_pitch": 3.0},
         {"shoulder_pitch": -52.0, "shoulder_roll": 0.0, "elbow": -10.0, "wrist_roll": 0.0, "wrist_pitch": -20.0}),
        (0.2, 55.0, "toe", False, {"hip_pitch": -100.0, "knee": 30.0, "ankle_pitch": 27.0},
         {"shoulder_pitch": -70.0, "shoulder_roll": 0.0, "elbow": -8.0, "wrist_roll": 0.0, "wrist_pitch": -45.0}),
        (0.3, 95.0, "palm", True, {"hip_pitch": -80.0, "knee": 8.0, "ankle_pitch": 30.0},
         {"shoulder_pitch": -95.0, "shoulder_roll": 0.0, "elbow": -20.0, "wrist_roll": 0.0, "wrist_pitch": -70.0}),
        (0.4, 140.0, "palm", False, {"hip_pitch": -45.0, "knee": 25.0, "ankle_pitch": 10.0},
         {"shoulder_pitch": -145.0, "shoulder_roll": 0.0, "elbow": -18.0, "wrist_roll": 0.0, "wrist_pitch": -67.0}),
        (0.48, 178.0, "palm", False, {"hip_pitch": -6.0, "knee": 4.0, "ankle_pitch": 25.0}, hold_arms),
        (0.58, 178.0, "palm", False, {"hip_pitch": -6.0, "knee": 4.0, "ankle_pitch": 25.0}, hold_arms),
    ]
    # Mirror the way back down through the same shapes.
    back = [(t, *spec[i][1:]) for t, i in ((0.66, 4), (0.76, 3), (0.86, 2), (0.94, 1), (1.0, 0))]
    keys = []
    for t, pitch, anchor, press, legs, arms in spec + back:
        angles = _handstand_key_angles(legs, arms) if legs is not None else dict(ATHLETIC)
        kind = "palm" if anchor == "palm" else "toe"
        if press:
            # Bisect the pike fold so the toes rest on the ground behind the planted hands.
            offset = _anchored_root_offset(angles, pitch, "hand_left", HS_PALM_LOCAL_MM, palm_target)
            lo, hi = -95.0, -40.0
            for _ in range(48):
                mid = (lo + hi) / 2
                for side in SIDES:
                    angles[f"hip_pitch_{side}"] = mid
                toe_z = point(fk_frames(angles, {}, offset, pitch)["foot_left"], HS_TOE_LOCAL_MM)[2]
                if toe_z < ground:
                    lo = mid
                else:
                    hi = mid
        if kind == "palm":
            offset = _anchored_root_offset(angles, pitch, "hand_left", HS_PALM_LOCAL_MM, palm_target)
        else:
            offset = _anchored_root_offset(angles, pitch, "foot_left", HS_TOE_LOCAL_MM, toe_target)
        toe_x = point(fk_frames(angles, {}, offset, pitch)["foot_left"], HS_TOE_LOCAL_MM)[0]
        keys.append({"t": t, "pitch": pitch, "type": kind, "toeX": toe_x, "angles": angles})
    keys.sort(key=lambda key: key["t"])
    return keys, toe_world[2], palm_target


HANDSTAND_KEYS, _HS_TOE_Z, _HS_PALM_TARGET = _handstand_keys()


def handstand(phase: float):
    """Toe-pivot fold, press to a palms-flat inverted hold with a breathing wobble, and
    back up: keyed joint angles, smoothstepped, with the root pitched and anchored at the
    toe (folding) or the palm (planted) every frame."""
    t = phase
    keys = HANDSTAND_KEYS
    a, b = keys[0], keys[-1]
    for i in range(len(keys) - 1):
        if keys[i]["t"] <= t <= keys[i + 1]["t"]:
            a, b = keys[i], keys[i + 1]
            break
    s = smooth01((t - a["t"]) / max(1e-9, b["t"] - a["t"]))
    angles = {name: a["angles"][name] + (b["angles"][name] - a["angles"][name]) * s for name in ATHLETIC}
    hold = pulse(t, 0.46, 0.5, 0.56, 0.6)
    wobble = HS_WOBBLE_DEG * hold * math.sin(2 * math.pi * ((t - 0.46) / 0.14) * 2)
    for side in SIDES:
        angles[f"hip_pitch_{side}"] += wobble
        angles[f"knee_{side}"] += -wobble * 0.6
    pitch = a["pitch"] + (b["pitch"] - a["pitch"]) * s
    if a["type"] == "palm" and b["type"] == "palm":
        offset = _anchored_root_offset(angles, pitch, "hand_left", HS_PALM_LOCAL_MM, _HS_PALM_TARGET)
    else:
        toe_x = a["toeX"] + (b["toeX"] - a["toeX"]) * s
        offset = _anchored_root_offset(angles, pitch, "foot_left", HS_TOE_LOCAL_MM, (toe_x, None, _HS_TOE_Z))
    return angles, {}, offset, pitch


def _elvis_kick_out_leg(body_z, pelvis_dy, toe_x, toe_y, foot_point_deg, lift, edge_scale) -> dict[str, float]:
    """The left leg kicked out onto a pointed toe at a world target: the hip roll puts
    the target in the leg's pitch plane, the in-plane IK lands the toe tip on it."""
    rig = STRIDE_RIG["left"]
    hip_roll = (0.0, HIP_Y + pelvis_dy, HIP_ROLL_Z_MM + body_z)
    target = (toe_x, toe_y, rig["soleZ"] + lift)
    v = [target[k] - hip_roll[k] for k in range(3)]
    edge_lift = (35 * abs(math.sin(math.atan2(v[1], -v[2]))) + 1) * edge_scale
    target = (toe_x, toe_y, rig["soleZ"] + lift + edge_lift)
    v = [target[k] - hip_roll[k] for k in range(3)]
    roll = math.atan2(v[1], -v[2])
    plane_depth = math.hypot(v[1], v[2])
    point_rad = math.radians(foot_point_deg)
    toe_forward = ELVIS_TOE_TIP_X * math.cos(point_rad) - ELVIS_TOE_TIP_DROP * math.sin(point_rad)
    toe_drop = ELVIS_TOE_TIP_X * math.sin(point_rad) + ELVIS_TOE_TIP_DROP * math.cos(point_rad)
    hip, knee, ankle = leg_pitch_ik(v[0] - toe_forward, plane_depth - 78 - toe_drop, foot_point_deg)
    roll_deg = math.degrees(roll)
    return {"hip_pitch_left": hip, "knee_left": knee, "ankle_pitch_left": ankle, "hip_roll_left": roll_deg,
            "ankle_roll_left": -roll_deg * (1 - edge_scale)}


def dance(phase: float, pelvis_dy: float | None = None):
    """The Elvis dance (4 beats): weight over the right leg, the left leg kicked out on a
    shaking pointed toe, the right finger pointing up and out with a beat pulse, hip
    swivel, chin up. ``pelvis_dy`` overrides the old lateral shift (-55 mm at full)."""
    t = phase
    angles = dict(ATHLETIC)
    env = pulse(t, 0.0, 0.12, 0.88, 1.0)
    beat = t * ELVIS_BEATS
    dy = ELVIS_WEIGHT_SHIFT_MM * env if pelvis_dy is None else pelvis_dy
    body_z = -ELVIS_DIP_MM * env - ELVIS_BOUNCE_MM * env * abs(math.sin(math.pi * beat))
    angles.update(planted_leg("right", body_z, dy))
    shake = env * math.sin(2 * math.pi * 2 * beat)
    toe_x = ELVIS_ATHLETIC_TOE[0] + (ELVIS_TOE_X_MM - ELVIS_ATHLETIC_TOE[0]) * env
    toe_y = ELVIS_ATHLETIC_TOE[1] + (ELVIS_TOE_Y_MM + ELVIS_TOE_SHAKE_MM * shake - ELVIS_ATHLETIC_TOE[1]) * env
    point_deg = ELVIS_FOOT_POINT_DEG * env + ELVIS_FOOT_POINT_SHAKE_DEG * shake
    lift = 45 * math.sin(math.pi * env)
    angles.update(_elvis_kick_out_leg(body_z, dy, toe_x, toe_y, point_deg, lift, env))
    beat_pulse = ELVIS_POINT_PULSE_DEG * math.sin(2 * math.pi * beat)
    rest_roll = _s("right") * chain.SHOULDER_ROLL_ABDUCT_DEG
    angles["shoulder_roll_right"] = rest_roll + (ELVIS_POINT_ROLL_DEG + beat_pulse - rest_roll) * env
    angles["shoulder_pitch_right"] = chain.SHOULDER_PITCH_DEG + (ELVIS_POINT_PITCH_DEG - chain.SHOULDER_PITCH_DEG) * env
    angles["elbow_right"] = chain.ELBOW_DEG + (ELVIS_POINT_ELBOW_DEG - chain.ELBOW_DEG) * env
    angles["shoulder_pitch_left"] = chain.SHOULDER_PITCH_DEG + (ELVIS_OFF_ARM_PITCH_DEG - chain.SHOULDER_PITCH_DEG) * env
    angles["elbow_left"] = chain.ELBOW_DEG + (ELVIS_OFF_ARM_ELBOW_DEG - chain.ELBOW_DEG) * env
    twist = ELVIS_TWIST_DEG * env * math.sin(math.pi * beat)
    angles["waist_yaw"] += twist
    angles["neck_yaw"] += ELVIS_HEAD_TURN_DEG * env - twist * 0.6
    angles["neck_pitch"] += ELVIS_CHIN_UP_DEG * env
    return angles, {"waist_yaw": {"rollDeg": ELVIS_LEAN_RIGHT_DEG * env}}, (0.0, dy, body_z), 0.0


# name: (the gait, the clip's duration in seconds), in the old clips' order (most
# exciting first: the order the viewer listed them).
CLIPS = {
    "danceLoop": (dance, 3.2),
    "handstandLoop": (handstand, 4.6),
    "kickLoop": (kick, 2.8),
    "jumpLoop": (jump, 1.8),
    "runLoop": (run, 0.8),
    "strideLoop": (stride, 1.9),
    "walkLoop": (walk, 1.5),
}
