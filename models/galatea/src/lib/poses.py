"""Galatea's named poses and motions, as plain numbers (controls, see lib/kin.py).

The pelvis is the mechanism's fixed link, and a robot on a floor is the other way round: its
feet stay where they stand and its pelvis moves over them. So the standing poses are written
that way. `ready` sets the stance (`kin.leg` puts each foot under its hip, the sole level), and
the others say where the pelvis goes from there (`stand`: `kin.standing` solves both legs for
feet that have not moved). The motions that move the pelvis are paths of that kind, sampled, so
no loaded foot slides on the way; where a foot is re-placed (`settle`, `poise`) the weight is
carried over the other first, and the foot is lifted. `checks/balance.py` holds every motion
to that: its feet stay put while they bear, and its centre of mass stays over them.
"""

import math

from .dims import ANKLE, FINGERS, mirror_point
from .kin import (
    SIDES, LEG_CONTROLS, apply, check_limits, compose, foot_at, inverse, leg, pelvis_over, placed, standing,
)


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

LEGS = tuple(f"{s}_{name}" for s in SIDES for name in (*LEG_CONTROLS, "toe"))


def stand(upper=None, feet=None, **pelvis):
    """A pose on the stance of `ready`: the feet where they stand there (or moved over the floor by `feet`), the
    pelvis moved from its place there (`kin.placed`'s words: left, forward, drop, yaw, roll, pitch), and `upper`
    over READY's arms, hands, waist and neck."""
    return {**READY, **standing(READY, placed(**pelvis), feet), **(upper or {})}


def _mix(a, b, share):
    """The controls a `share` of the way from pose a to pose b."""
    return {name: a[name] + (b[name] - a[name]) * share for name in a}


def _upper(pose):
    return {name: value for name, value in pose.items() if name not in LEGS}


# The crouch: the hips go back and down and the pelvis tips forward, the arms out in front as a counterweight.
# The ankles end half a degree from their dorsiflexion limit and the hips two from theirs, which is what sets the
# depth: lower, and the weight would stand behind the middle of the feet.
CROUCH = dict(forward=-205.0, drop=325.0, pitch=25.8)
CROUCH_UPPER = {
    **both(shoulder_pitch=72, shoulder_roll=8, shoulder_yaw=10, elbow=22, wrist_roll=10),
    "waist_pitch": 2, "neck_pitch": -22,
}
# The bow: from the hips and the waist, the hips eased back over the heels as the chest goes forward.
BOW = dict(forward=-87.0, drop=-4.0, pitch=24.0)
BOW_UPPER = {**both(shoulder_pitch=34, shoulder_roll=7, shoulder_yaw=10, elbow=10), "waist_pitch": 34, "neck_pitch": 16}


CROUCH_LEAD = 64.0       # how far further back the hips are half-way down than a straight path has them, mm


def squat(depth):
    """Down toward the crouch by `depth`: 0 is `ready`, 1 the crouch. The pelvis's path is the crouch's place
    over the feet taken in shares, so every pose on the way stands on the same two feet; the hips lead a
    little on their way back, which keeps the rear ankle inside its dorsiflexion limit on the way down."""
    place = {name: value * depth for name, value in CROUCH.items()}
    place["forward"] -= CROUCH_LEAD * depth * (1.0 - depth)
    return {**stand(**place), **_mix(_upper(READY), {**_upper(READY), **CROUCH_UPPER}, depth)}


def bend(depth):
    """Forward toward the bow by `depth`: 0 is `ready`, 1 the bow."""
    return {**stand(**{name: value * depth for name, value in BOW.items()}),
            **_mix(_upper(READY), {**_upper(READY), **BOW_UPPER}, depth)}


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
        **leg("r", forward=-18, drop=8, yaw=3, roll=-5), **leg("l", forward=74, drop=8, yaw=13, roll=5),
        **side("l", shoulder_pitch=0, shoulder_roll=12, shoulder_yaw=8, elbow=24, wrist_roll=12),
        **side("r", shoulder_pitch=-8, shoulder_roll=7, shoulder_yaw=6, elbow=14),
        "waist_yaw": -12, "waist_roll": -5, "waist_pitch": 1, "neck_yaw": 24, "neck_roll": 6, "neck_pitch": 3,
    },
    # The right hand offered forward, open: the feet stay, the pelvis goes a little forward and turns with the chest.
    "reach": stand({
        **side("r", shoulder_pitch=72, shoulder_roll=6, shoulder_yaw=18, elbow=32, wrist_roll=-30, wrist_pitch=-12, wrist_yaw=0),
        **hand("r", curl=0.08, thumb=0.05, opp=38),
        "waist_yaw": 12, "waist_pitch": 6, "neck_yaw": -8, "neck_pitch": 8,
    }, forward=10, drop=3, yaw=4),
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
    # A deep crouch on flat feet where they stood, the ankles at their dorsiflexion limit; the hips fold further
    # than the knees and ankles undo, so the pelvis tips forward and keeps the weight over the middle of the feet.
    "crouch": squat(1.0),
    # A bow from the hips and the waist, the ankles easing the hips back.
    "bow": bend(1.0),
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
    # Asleep on its feet, which are where it will stand when it wakes: the legs almost straight, the arms hanging,
    # the chest eased forward and the head bowed.
    "rest": stand({
        **both(shoulder_pitch=5, shoulder_roll=8, shoulder_yaw=6, elbow=12, wrist_roll=8, wrist_pitch=4, wrist_yaw=2),
        **hands(curl=0.4, thumb=0.3, opp=20), "waist_yaw": 0, "waist_roll": 0, "waist_pitch": 11, "neck_yaw": 0, "neck_roll": 0,
        "neck_pitch": 36,
    }, drop=-9),
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
    return [(duration * k / count, check_limits(fn(duration * k / count), f"{fn.__name__} at {duration * k / count:.2f} s"))
            for k in range(count + 1)]


def _with(base, **changes):
    return check_limits({**POSES[base], **changes}, base)


def _smooth(share):
    """0 to 1 as `share` goes 0 to 1, leaving and arriving with no speed and no acceleration."""
    u = min(1.0, max(0.0, share))
    return u * u * u * (10.0 - 15.0 * u + 6.0 * u * u)


def _span(t, start, end):
    return _smooth((t - start) / (end - start))


def _there_and_back(t, arrive, leave, end):
    """0 at the start, 1 from `arrive` to `leave`, 0 again at `end`."""
    return _span(t, 0.0, arrive) - _span(t, leave, end)


def bow(t):
    return bend(_there_and_back(t, 1.6, 2.6, 4.2))


def crouch(t):
    return squat(_there_and_back(t, 2.0, 3.0, 5.0))


def reach(t):
    """The right hand offered and taken back, the feet where they stand."""
    share = _there_and_back(t, 1.5, 2.4, 3.9)
    return {**stand(forward=10 * share, drop=3 * share, yaw=4 * share), **_mix(_upper(READY), _upper(POSES["reach"]), share)}


# A pose that stands on one foot, or has set one down somewhere else, is written joint by joint above. To get
# there over a floor the robot first carries its weight over the foot that stays, and only then moves the other.
def _placement(pose, kept):
    """Where a pose has the pelvis, in `kin.placed`'s words, from its place in `ready`, the `kept` foot having
    stayed where `ready` stands it."""
    (r, _), centre = (moved := pelvis_over(READY, pose, kept)), (0.0, 0.0, 920.0)
    at = apply(moved, centre)
    return dict(left=at[0] - centre[0], forward=centre[1] - at[1], drop=centre[2] - at[2],
                yaw=math.degrees(math.atan2(r[1][0], r[0][0])), roll=-math.degrees(math.asin(r[2][0])),
                pitch=math.degrees(math.atan2(r[2][1], r[2][2])))


def _ankle(s):
    """Where a foot's ankle stands in `ready`, the pelvis's frame there being the floor's."""
    return apply(foot_at(s, [READY[f"{s}_{name}"] for name in LEG_CONTROLS]), ANKLE if s == "l" else mirror_point(ANKLE))


def _stepped(pose, s, kept):
    """How a pose has re-placed its `s` foot on the floor from where `ready` stands it, the `kept` foot having
    stayed: (to the left, forward, turned to the left), mm and degrees. Both soles are flat in both poses."""
    was = foot_at(s, [READY[f"{s}_{name}"] for name in LEG_CONTROLS])
    now = compose(pelvis_over(READY, pose, kept), foot_at(s, [pose[f"{s}_{name}"] for name in LEG_CONTROLS]))
    ankle = ANKLE if s == "l" else mirror_point(ANKLE)
    a, b, turn = apply(was, ankle), apply(now, ankle), compose(now, inverse(was))[0]
    return b[0] - a[0], a[1] - b[1], math.degrees(math.atan2(turn[1][0], turn[0][0]))


def _leg(pose, s):
    return {f"{s}_{name}": pose[f"{s}_{name}"] for name in (*LEG_CONTROLS, "toe")}


# How long the weight takes to go over one foot, s. It cannot hurry: the pelvis travels 126 mm, and while it
# slows the floor's push stands ahead of the centre of mass by the braking times the height over gravity, 30 mm
# when the shift takes 1.5 s. The foot it arrives over is 60 mm wide and its ankle's roll drive steers the push
# 24 mm either side of its axis, so a quick shift goes on over the outside of the foot. In 3 s it is 8 mm.
SHIFT = 3.0
POISE_AT = _placement(POSES["poise"], "l")          # the pelvis over the left foot
POISE_CLEAR = 40.0                                  # how high the right foot goes straight up as its leg begins to fold, mm


def poise(t):
    """Onto the left leg and back. The pelvis goes over the left foot with both feet down, so the right foot
    has nothing left to carry when its knee lifts; coming back, the foot is set down before the weight returns."""
    over = _span(t, 0.0, SHIFT) - _span(t, SHIFT + 3.6, 2 * SHIFT + 3.6)
    up = _span(t, SHIFT, SHIFT + 1.4) - _span(t, SHIFT + 2.2, SHIFT + 3.6)
    # The foot leaves the floor straight up, its sole level, and the leg folds as it clears.
    raised = placed(drop=-POISE_CLEAR * _smooth(up / 0.35), centre=_ankle("r"))
    pose = stand(_mix(_upper(READY), _upper(POSES["poise"]), over), feet={"r": raised},
                 **{name: value * over for name, value in POISE_AT.items()})
    return {**pose, **_mix(_leg(pose, "r"), _leg(POSES["poise"], "r"), _smooth((up - 0.15) / 0.85))}


SETTLE_AT = _placement(POSES["contrapposto"], "r")  # the pelvis in contrapposto, the right foot where it stood
SETTLE_STEP = _stepped(POSES["contrapposto"], "l", "r")
# Before the left foot is moved the pelvis goes further over the right one than contrapposto has it, and a little
# lower: far enough that the right foot alone carries the robot, with the left leg still long enough to stand.
SETTLE_OVER = dict(left=SETTLE_AT["left"] - 24.0, forward=0.0, drop=10.0, yaw=SETTLE_AT["yaw"] / 2.0, roll=0.0, pitch=0.0)
STEP_LIFT = 16.0


def settle(t):
    """From `ready` into contrapposto: the weight goes over the right foot, the left foot is lifted, carried to
    its new place and set down, and only then does the pelvis ease into the pose and share the weight out."""
    over, step, ease = _span(t, 0.0, SHIFT), _span(t, SHIFT, SHIFT + 1.1), _span(t, SHIFT + 1.1, SHIFT + 2.4)
    place = {name: SETTLE_OVER[name] * over + (SETTLE_AT[name] - SETTLE_OVER[name]) * ease for name in SETTLE_AT}
    left, forward, turn = SETTLE_STEP
    lift = STEP_LIFT * math.sin(math.pi * step) ** 2 if 0.0 < step < 1.0 else 0.0
    carried = _smooth((step - 0.2) / 0.6)                # it is carried only while it is clear of the floor
    foot = placed(left=left * carried, forward=forward * carried, drop=-lift, yaw=turn * carried, centre=_ankle("l"))
    return stand(_mix(_upper(READY), _upper(POSES["contrapposto"]), _span(t, 0.4, SHIFT + 2.4)), feet={"l": foot}, **place)


MOTIONS = [
    ("walk", _sampled(walk, CYCLE, 24), "linear"),
    ("wave", [(0.0, "ready"), (1.1, _with("wave", r_wrist_yaw=-22)), (1.5, _with("wave", r_wrist_yaw=28)),
              (1.9, _with("wave", r_wrist_yaw=-22)), (2.3, _with("wave", r_wrist_yaw=28)),
              (2.7, _with("wave", r_wrist_yaw=-22)), (3.8, "ready")], "cubic"),
    # Where the pelvis moves over the feet the path is sampled, ten times a second: between two poses that keep the
    # feet, joints eased one by one would let them wander, and the weight with them.
    ("bow", _sampled(bow, 4.2, 42), "linear"),
    ("crouch", _sampled(crouch, 5.0, 50), "linear"),
    ("reach", _sampled(reach, 3.9, 39), "linear"),
    ("poise", _sampled(poise, 9.6, 96), "linear"),
    ("look", [(0.0, "ready"), (1.0, _with("ready", neck_yaw=58, neck_pitch=-8)),
              (2.3, _with("ready", neck_yaw=-58, neck_pitch=10, neck_roll=-12)),
              (3.3, _with("ready", neck_yaw=0, neck_pitch=22, neck_roll=18)), (4.3, "ready")], "cubic"),
    ("grasp", [(0.0, "ready"), (1.2, "fists"), (2.0, "fists"), (3.2, "ready")], "cubic"),
    # The film's own two (`film.py`): it wakes, and it settles its weight on one leg.
    ("wake", [(0.0, "rest"), (0.7, "rest"), (3.4, "ready")], "cubic"),
    ("settle", _sampled(settle, 7.0, 70), "linear"),
]
