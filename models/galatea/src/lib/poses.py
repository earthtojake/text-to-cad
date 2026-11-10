"""Galatea's named poses and motions, as plain numbers (controls, see lib/kin.py).

A leg is posed by where its foot goes (`kin.leg` solves hip, knee and ankle so the sole
stays level), so a pose with both feet at one `drop` stands on flat ground. The pelvis is
the mechanism's fixed link; a posed model plants the stance foot instead (`kin.stance`).
"""

import math

from .dims import FINGERS
from .kin import SIDES, check_limits, leg


def both(**values):
    return {f"{s}_{name}": value for s in SIDES for name, value in values.items()}


def side(s, **values):
    return {f"{s}_{name}": value for name, value in values.items()}


def hand(s, curl=0.0, thumb=0.0, opp=0.0, **fingers):
    """One hand: every finger at `curl` (0 open, 1 closed) unless named, the thumb's curl and opposition."""
    pose = {f"{s}_{finger}_curl": fingers.get(finger, curl) for finger in FINGERS}
    pose[f"{s}_thumb_curl"] = thumb
    pose[f"{s}_thumb_opp"] = opp
    return pose


def hands(**kw):
    return {**hand("l", **kw), **hand("r", **kw)}


RELAXED = dict(curl=0.28, thumb=0.25, opp=24.0, index=0.2, little=0.36)

READY = {
    **leg("l", forward=8, drop=12, yaw=7, roll=2), **leg("r", forward=-8, drop=12, yaw=7, roll=2),
    **both(shoulder_pitch=8, shoulder_roll=9, shoulder_yaw=10, elbow=24, wrist_roll=12, wrist_pitch=6, wrist_yaw=4),
    **hands(**RELAXED), "waist_yaw": 0, "waist_roll": 0, "waist_pitch": 2, "neck_yaw": 0, "neck_roll": 0, "neck_pitch": 4,
}

POSES = {
    # An easy athletic stance: knees unlocked, arms a little out, hands relaxed.
    "ready": READY,
    # Mid-stride: the left heel has just landed, the right foot is rolling off its toes.
    "stride": {
        **READY,
        **leg("l", forward=205, drop=30, yaw=3, foot_pitch=6), **leg("r", forward=-170, drop=59, yaw=3, foot_pitch=-20, toe=20),
        **side("l", shoulder_pitch=-24, shoulder_roll=8, elbow=18), **side("r", shoulder_pitch=32, shoulder_roll=8, elbow=46),
        "waist_yaw": 8, "waist_pitch": 4, "neck_yaw": -5, "neck_pitch": 2,
    },
    # Weight on the right leg, the left knee eased, the chest and head turned.
    "contrapposto": {
        **READY,
        **leg("r", forward=-18, drop=8, yaw=10, roll=-5), **leg("l", forward=74, drop=8, yaw=22, roll=5),
        **side("l", shoulder_pitch=0, shoulder_roll=12, shoulder_yaw=8, elbow=24, wrist_roll=12),
        **side("r", shoulder_pitch=-8, shoulder_roll=7, shoulder_yaw=6, elbow=14),
        "waist_yaw": -12, "waist_roll": -5, "waist_pitch": 1, "neck_yaw": 24, "neck_roll": 6, "neck_pitch": 3,
    },
    # The right hand offered forward, open.
    "reach": {
        **READY,
        **leg("l", forward=70, drop=16, yaw=5), **leg("r", forward=-70, drop=16, yaw=9),
        **side("r", shoulder_pitch=72, shoulder_roll=6, shoulder_yaw=18, elbow=32, wrist_roll=-30, wrist_pitch=-12, wrist_yaw=0),
        **hand("r", curl=0.08, thumb=0.05, opp=38),
        "waist_yaw": 12, "waist_pitch": 6, "neck_yaw": -8, "neck_pitch": 8,
    },
    # A greeting: the right forearm raised, the palm turned out.
    "wave": {
        **READY,
        **side("r", shoulder_pitch=20, shoulder_roll=72, shoulder_yaw=-78, elbow=96, wrist_roll=-5, wrist_pitch=-8, wrist_yaw=0),
        **hand("r", curl=0.04, thumb=0.0, opp=10),
        "waist_yaw": -4, "neck_yaw": -14, "neck_roll": -7, "neck_pitch": -2,
    },
    # Both palms turned up, forearms level.
    "present": {
        **READY,
        **both(shoulder_pitch=26, shoulder_roll=8, shoulder_yaw=-14, elbow=82, wrist_roll=-86, wrist_pitch=-6, wrist_yaw=0),
        **hands(curl=0.1, thumb=0.05, opp=18), "neck_pitch": 12,
    },
    # A deep crouch on flat feet, the ankles at their dorsiflexion limit; the hips fold further
    # than the knees and ankles undo, so the pelvis tips forward and keeps the weight over the feet.
    "crouch": {
        **READY,
        **both(hip_yaw=0, hip_roll=0, hip_pitch=98, knee=112, ankle_pitch=30, ankle_roll=0, toe=0),
        **both(shoulder_pitch=58, shoulder_roll=10, shoulder_yaw=12, elbow=50, wrist_roll=10),
        "waist_pitch": 10, "neck_pitch": -22,
    },
    # A bow from the hips and the waist, the ankles easing the hips back.
    "bow": {
        **READY,
        **both(hip_yaw=0, hip_roll=0, hip_pitch=32, knee=3, ankle_pitch=-5, ankle_roll=0, toe=0),
        **both(shoulder_pitch=34, shoulder_roll=7, shoulder_yaw=10, elbow=10),
        "waist_pitch": 34, "neck_pitch": 16,
    },
    # Balanced on the left leg: its hip adducts until the weight stands over the foot, the right knee lifted.
    "poise": {
        **READY,
        **leg("l", forward=20, drop=14, yaw=4, roll=-7),
        **side("r", hip_yaw=4, hip_roll=4, hip_pitch=60, knee=100, ankle_pitch=-22, ankle_roll=0, toe=0),
        **side("l", shoulder_pitch=6, shoulder_roll=24, shoulder_yaw=6, elbow=24, wrist_roll=10),
        **side("r", shoulder_pitch=-4, shoulder_roll=20, shoulder_yaw=6, elbow=30, wrist_roll=10),
    },
    # Both hands closed.
    "fists": {**READY, **hands(curl=1.0, thumb=0.85, opp=62)},
}

for _name, _pose in POSES.items():
    check_limits(_pose, _name)


# ---------------------------------------------------------------------------------------------
# Motions: (name, [(seconds, pose), ...], ease)
# ---------------------------------------------------------------------------------------------
STEP = 300.0          # how far a foot travels under the hip in one stance
CYCLE = 2.0           # seconds for a left and a right step


def _foot(phase):
    """Where a foot is in its cycle: (forward, drop, sole pitch, toe)."""
    stance = 0.6
    if phase < stance:
        u = phase / stance
        heel_off = max(0.0, (u - 0.72) / 0.28)
        pitch = -18.0 * heel_off ** 2
        return STEP / 2 - STEP * u, 24.0 + 118.0 * math.sin(math.radians(-pitch)), pitch, -pitch
    s = (phase - stance) / (1.0 - stance)
    glide = s - math.sin(2 * math.pi * s) / (2 * math.pi)
    pitch = -18.0 * (1.0 - s) ** 2 + 12.0 * math.sin(math.pi * s) * s
    lift = 36.0 * (1.0 - s) + 40.0 * math.sin(math.pi * s)
    return -STEP / 2 + STEP * glide, 24.0 + lift, pitch, max(0.0, 18.0 * (1.0 - 3.0 * s))


def walk(t):
    """One gait cycle on the spot: the feet tread under a fixed pelvis, the arms and chest counter-swing."""
    phase = (t / CYCLE) % 1.0
    swing = math.cos(2 * math.pi * phase)
    pose = dict(READY)
    for s, offset in (("l", 0.0), ("r", 0.5)):
        forward, drop, pitch, toe = _foot((phase + offset) % 1.0)
        sway = 2.0 * math.sin(2 * math.pi * phase) * (1 if s == "l" else -1)
        pose.update(leg(s, forward=forward, drop=drop, foot_pitch=pitch, yaw=3, roll=sway, toe=toe))
        arm = -swing if s == "l" else swing
        pose.update(side(s, shoulder_pitch=4 + 22 * arm, elbow=26 + 12 * arm, shoulder_roll=8))
    pose.update({"waist_yaw": 6 * swing, "waist_roll": -2 * math.sin(2 * math.pi * phase), "waist_pitch": 4,
                 "neck_yaw": -3 * swing})
    return check_limits(pose, f"walk at {t:.2f}")


def _sampled(fn, duration, count):
    return [(duration * k / count, fn(duration * k / count)) for k in range(count + 1)]


def _with(base, **changes):
    return check_limits({**POSES[base], **changes}, base)


MOTIONS = [
    ("walk", _sampled(walk, CYCLE, 24), "linear"),
    ("wave", [(0.0, "ready"), (1.1, _with("wave", r_wrist_yaw=-22)), (1.5, _with("wave", r_wrist_yaw=28)),
              (1.9, _with("wave", r_wrist_yaw=-22)), (2.3, _with("wave", r_wrist_yaw=28)),
              (2.7, _with("wave", r_wrist_yaw=-22)), (3.8, "ready")], "cubic"),
    ("bow", [(0.0, "ready"), (1.6, "bow"), (2.6, "bow"), (4.2, "ready")], "cubic"),
    ("crouch", [(0.0, "ready"), (2.0, "crouch"), (3.0, "crouch"), (5.0, "ready")], "cubic"),
    ("reach", [(0.0, "ready"), (1.5, "reach"), (2.4, "reach"), (3.9, "ready")], "cubic"),
    ("poise", [(0.0, "ready"), (2.2, "poise"), (3.4, "poise"), (5.6, "ready")], "cubic"),
    ("look", [(0.0, "ready"), (1.0, _with("ready", neck_yaw=58, neck_pitch=-8)),
              (2.3, _with("ready", neck_yaw=-58, neck_pitch=10, neck_roll=-12)),
              (3.3, _with("ready", neck_yaw=0, neck_pitch=22, neck_roll=18)), (4.3, "ready")], "cubic"),
    ("grasp", [(0.0, "ready"), (1.2, "fists"), (2.0, "fists"), (3.2, "ready")], "cubic"),
]
