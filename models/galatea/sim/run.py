# /// script
# dependencies = ["mujoco", "numpy"]
# ///
"""Galatea's motions in MuJoCo: under gravity, on its own feet, by position servos alone; and their video.

    cad run sim/run.py                    every clip: simulate, report, render, and cut them together
    cad run sim/run.py crouch bow         the named clips
    cad run sim/run.py --dry              simulate and report: no picture
    cad run sim/run.py crouch --stills 74 those frames of the named clips as PNG files, and nothing else
    cad run sim/run.py --cut              cut the clips' videos together again, as they are
    cad run sim/run.py --film crouch      the showcase film's clip alone, from that motion (bow unless one is named);
                       --dry              with it, its report and no picture; --stills 0,60,119: those frames as PNG files
    cad run sim/run.py --friction 1.0     an experiment, reports only: on another floor (the model's own is 0.7),
                       --stiffness 4      with every drive's servo so many times as stiff,
                       --pace 2           with every motion played so many times as slow,
                       --still-legs       or with the legs' controls left at `ready` through every motion

`mjcf.py` writes the model this loads (`sim/galatea.xml`). A clip resets the robot to a keyframe
(`ready`; `rest` for the motion that wakes it), standing on the floor with nothing holding it, lets it
settle, and then feeds the servos a motion of `lib/poses.py`: the motion's waypoints in the model's
controls, between them exactly as the CAD engine plays a configuration sequence (eased from waypoint
to waypoint, or straight from sample to sample of a sampled path). There is no balance controller:
each servo follows its own joint's angle and knows nothing of the floor, of the other joints or of
where the weight is. A robot that falls is shown falling, and the clip stops soon after.

The two motions that stand on one foot fall so. Each is shown three ways: as it falls; standing, on
what `oneleg.py` found it takes (the motion at half its pace, each drive fed the torque the motion
asks of it, the ankles' roll servos four times as stiff: still nothing fed back but each joint's own
angle); and `held`, which says so in its picture: the weld `hold_pelvis` is turned on and the pelvis
hangs from a point over the floor, the feet clear of it. The gait is shown held only: walking needs a
controller this model does not have.

Every clip is drawn to be read as a simulation: a grid on the floor, MuJoCo's own arrows for the
floor's push at every point of contact, a mark on the floor under the centre of mass, the robot in the
middle and 0.8 of the picture high. `galatea-sim.mp4` is the clips of `CUT` in a row, each with its
caption: what the motion is, what it shows, how the robot stood for it and what, if anything, was
changed from the servos as assumed. `--film` makes one more clip, for the showcase film, and nothing
else: the robot let go 30 mm over the floor, its landing, and then one motion, in exactly five seconds
and with nothing written on the picture.

Everything is written into `tmp/sim/`, which Git ignores: `<clip>.mp4`, `<clip>.npz` (the simulated
trajectory and what was measured along it), `report.json` and `report.txt` (every clip's numbers, and
the same as this script says them), `galatea-sim.mp4`, and the film's `film_clip.mp4`, `film_clip.npz`
and `film_clip.json`. The picture is MuJoCo's own renderer, offscreen: `MUJOCO_GL` chooses the context
(`egl` unless set; `osmesa` works too).
"""

import argparse
import copy
import itertools
import json
import math
import os
import struct
import subprocess
import sys
import textwrap
import time
import xml.etree.ElementTree as ET
import zlib
from dataclasses import dataclass, replace
from pathlib import Path

os.environ.setdefault("MUJOCO_GL", "egl")

import mujoco  # noqa: E402
import numpy as np  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))

from lib import dims, kin  # noqa: E402
from lib.poses import MOTIONS, POSES  # noqa: E402

XML = HERE / "galatea.xml"
OUT = HERE.parent / "tmp" / "sim"
WIDTH, HEIGHT, FPS = 1600, 900, 24
FONTS = Path("/usr/share/fonts/opentype/inter")
PELVIS = np.array([0.0, 0.0, dims.HIP[2]]) / 1000.0          # the pelvis's frame at the zero pose, m
SETTLE = 1.5           # s a clip stands before anything is recorded
LEAD, TAIL = 0.6, 1.0  # s recorded before a motion begins and after it ends
AFTER = 1.5            # s recorded after a fall
VIEW = dict(elevation=-5.5, distance=4.1, lookat=(0.0, -0.05, 0.875))             # from chest height: a standing robot fills 0.8 of the picture
# After a fall the camera's aim goes after the robot, so that one that falls to a side ends in the picture: it
# starts `lead` s before the fall touches down and takes `over` s. It ends `aside` m to the picture's left of where
# the pelvis comes to lie, which puts the robot in the right of the picture and clear of a caption, and `lower` m down.
FOLLOW = dict(lead=0.6, over=1.6, aside=0.65, lower=0.2)
STIFF = 8.0            # how many times as stiff every drive's servo is in the run a fed-ahead torque is taken from
LIFT = 0.10            # m: how far over its place at the zero pose a held pelvis hangs
SOLES = ("heel", "ball", "toe", "toe_cap", "upper")           # the shapes of a foot: anything else on the floor is a fall
LEGS = ("hip_yaw", "hip_roll", "hip_pitch", "knee", "ankle_pitch", "ankle_roll", "toe")      # a leg's controls
STATE = mujoco.mjtState.mjSTATE_INTEGRATION                   # what a frame keeps: enough to compute its contact forces again
# The film's clip (`--film`): its length, how long the landing has before the motion begins, how far over the
# floor the robot is let go, and the least a motion's hold is played for when the motion has to be fitted in.
FILM_SECONDS, LAND, DROP, HOLD_LEAST = 5.0, 0.8, 0.03, 0.2
# The floor's grid: a line each 100 mm and a heavier one each 500 mm. The heavy ones are in the floor's texture (their
# width in mm, and how much lighter than the floor they are), so they run to the horizon. Near the robot, out to
# `reach` metres from the origin and fading on the way, both are drawn again as lines of whole pixels, which stay
# sharp where a texture seen from chest height does not: (pixels wide, opacity at the origin) for each, and a colour.
GRID = dict(tile=500, heavy=(10, 0.11), fine=100, reach=2.6, piece=0.2, colour=(0.52, 0.57, 0.64), lines={100: (1.0, 0.2), 500: (2.0, 0.42)})
# A contact's arrow: how long it is drawn for how many newtons (35 N is a sixteenth of the robot's weight, and it
# stands on sixteen corners), its shaft's radius, its colour and its point's.
FORCE = dict(newtons=35.0, metres=0.30, width=0.016, colour=(0.1, 0.85, 1.0, 1.0), point=(1.0, 0.55, 0.1, 1.0))
# Under the centre of mass, on the floor: a ring with a cross through it (radius m, pixels wide) and its colour.
COM_MARK = dict(radius=0.05, pixels=2.0, colour=(1.0, 0.9, 0.45, 1.0))


@dataclass
class Clip:
    name: str
    caption: str
    motion: str | None = None      # a motion of lib/poses.py, or None: stand
    seconds: float = 0.0           # how long a clip with no motion stands
    held: bool = False             # the pelvis welded to a point over the floor
    repeat: int = 1
    drop: float = 0.0              # m: a clip with no motion is let go this far over the floor
    orbit: tuple = (116.0, 134.0)  # the camera's azimuth at the clip's start and end, degrees
    start: str = "ready"           # the keyframe it starts from
    still_legs: bool = False       # an experiment: the legs' controls left at `ready` through the motion
    settle: float = SETTLE         # s it stands, unseen, before a motion's clip begins
    lead: float = LEAD             # s recorded before the motion begins
    tail: float = TAIL             # s recorded after it ends
    fit: float = 0.0               # s the whole clip is to last, or 0: as long as its motion asks
    # What a clip may change from the motion as it is written and the servos as `mjcf.py` assumes them (`oneleg.py`):
    pace: float = 1.0              # the motion played this many times as slow
    ahead: bool = False            # each drive fed ahead the torque the motion asks of it
    ankle: float = 1.0             # the ankles' roll servos this many times as stiff


# Every motion of `lib/poses.py`, free-standing on the servos as assumed. The two that stand on one foot fall so.
# They are shown again as `oneleg.py` found they stand, still with no balance feedback, and again held; the gait
# is shown held alone.
CLIPS = [
    Clip("ready", "let go 30 mm over the floor: it lands, settles and stands", seconds=6.0, drop=0.03),
    Clip("wake", "asleep on its feet, it wakes", motion="wake", start="rest", orbit=(140.0, 118.0)),
    Clip("bow", "a bow from the hips and the waist, the hips eased back over the heels", motion="bow", orbit=(150.0, 126.0)),
    Clip("wave", "a greeting", motion="wave", orbit=(98.0, 118.0)),
    Clip("reach", "the right hand offered forward, the feet where they stand", motion="reach", orbit=(130.0, 106.0)),
    Clip("look", "the head looks round", motion="look", orbit=(102.0, 84.0)),
    Clip("grasp", "both hands close and open", motion="grasp", orbit=(86.0, 106.0)),
    Clip("crouch", "a squat and back up: the hips go back and down over feet that stay", motion="crouch", orbit=(132.0, 146.0)),
    Clip("poise", "onto the left leg: the legs' servos give under the weight, and one ankle cannot make it up", motion="poise",
         orbit=(108.0, 122.0)),
    Clip("settle", "into contrapposto by a step: the legs' servos give under the weight, and one ankle cannot make it up", motion="settle",
         orbit=(104.0, 122.0)),
    Clip("poise_stands", "onto the left leg alone, and back", motion="poise", pace=2.0, ahead=True, ankle=4.0, orbit=(108.0, 122.0)),
    Clip("settle_stands", "into contrapposto: the left foot lifted, carried and set down", motion="settle", pace=2.0, ahead=True, ankle=4.0,
         orbit=(104.0, 122.0)),
    Clip("poise_held", "onto the left leg alone, as it is written", motion="poise", held=True, orbit=(110.0, 130.0)),
    Clip("settle_held", "into contrapposto, as it is written", motion="settle", held=True, orbit=(104.0, 128.0)),
    Clip("walk_held", "the gait: walking needs a controller this model does not have", motion="walk", held=True, repeat=3,
         orbit=(150.0, 120.0)),
]
# galatea-sim.mp4: the clips it shows, in order, and how many times as fast each is played. It ends on what the robot
# can do: the eight motions that complete as assumed, one fall, the two one-leg motions standing, and the gait.
CUT = [("ready", 1), ("wake", 1), ("bow", 1), ("wave", 1), ("reach", 1), ("look", 1), ("grasp", 1), ("crouch", 1), ("poise", 1),
       ("poise_stands", 2), ("settle_stands", 2), ("walk_held", 1)]
CAPTION = dict(shows=38, stood=44)     # the most characters in a line of each text, so that a caption ends left of the robot


# ---------------------------------------------------------------------------------------------
# The motions, as the servos are fed them
# ---------------------------------------------------------------------------------------------
class Servos:
    """The model's servos by the control each stands for: a pose in controls -> their targets, radians."""

    def __init__(self, model):
        couplings = kin.couplings()
        self.names = [model.actuator(i).name for i in range(model.nu)]
        self.joint = [model.joint(model.actuator_trnid[i, 0]).name for i in range(model.nu)]
        # A coupling's servo turns one of its joints: the control's value times that joint's ratio.
        self.ratio = np.array([couplings[name][joint] if name in couplings else 1.0 for name, joint in zip(self.names, self.joint)])
        self.qpos = np.array([model.jnt_qposadr[model.actuator_trnid[i, 0]] for i in range(model.nu)])
        self.limit = model.actuator_forcerange[:, 1].copy()
        # MuJoCo's position servo is stiffness x (control - angle) - damping x the joint's own rate. Fed the angle
        # wanted plus damping / stiffness times the rate wanted, it is a servo on the error and on the error's rate:
        # stiffness x (wanted - angle) + damping x (wanted rate - rate), which does not lag a moving target.
        self.stiffness = model.actuator_gainprm[:, 0].copy()
        self.lead = -model.actuator_biasprm[:, 2] / self.stiffness
        self.range = model.actuator_ctrlrange.copy()

    def targets(self, pose):
        return np.radians(self.ratio * np.array([pose.get(name, 0.0) for name in self.names]))

    def fed(self, wanted, rate):
        return np.clip(wanted + self.lead * rate, self.range[:, 0], self.range[:, 1])


def waypoints(clip):
    """A clip's motion as ([seconds], [pose in controls], ease), from its lead-in to its hold; standing is one pose."""
    if clip.motion is None:
        return [0.0, clip.seconds], [POSES.get(clip.start, {})] * 2, "linear"
    _, keys, ease = next(motion for motion in MOTIONS if motion[0] == clip.motion)
    stops, poses = [], []
    for lap in range(clip.repeat):
        for at, pose in keys[(1 if lap else 0):]:
            stops.append((lap * keys[-1][0] + at) * clip.pace)
            poses.append(POSES[pose] if isinstance(pose, str) else pose)
    tail = clip.tail
    if clip.fit:
        stops = fitted(stops, poses, clip.fit - clip.lead)
        tail = max(0.0, clip.fit - clip.lead - stops[-1])         # a motion shorter than its room holds its last pose
    if clip.still_legs:
        stood = {name: value for name, value in POSES["ready"].items() if name[2:] in LEGS}
        poses = [{**pose, **stood} for pose in poses]
    times = [clip.lead + at for at in stops]
    return [0.0, *times, times[-1] + tail], [poses[0], *poses, poses[-1]], ease


def fitted(stops, poses, room):
    """A motion's waypoint times, its holds played shorter where it is longer than `room`: a hold is a run of
    waypoints of one pose (two of them, or the many of a sampled path), and none is cut below HOLD_LEAST. What is
    still too long ends when the clip does."""
    spans, spare, at = np.diff(stops), np.zeros(len(stops) - 1), 0
    still = [all(abs(a[name] - b[name]) < 1e-6 for name in a.keys() | b.keys()) if a.keys() == b.keys() else False
             for a, b in zip(poses, poses[1:])]
    for held, run in itertools.groupby(still):
        steps = slice(at, at + len(list(run)))
        if held:
            spare[steps] = spans[steps] * max(0.0, 1.0 - HOLD_LEAST / spans[steps].sum())
        at = steps.stop
    over = stops[-1] - stops[0] - room
    if over > 0 and spare.sum() > 0:
        spans = spans - spare * min(1.0, over / spare.sum())
    return [float(at) for at in stops[0] + np.concatenate([[0.0], np.cumsum(spans)])]


def eased(times, values, ease, t):
    """(values, their rates) at `t` between keys, as `cad.engine.mechanism` interpolates a configuration sequence:
    over each step by `3 s^2 - 2 s^3`, at rest at every key, or linearly.

    A linear sequence is a path sampled (`lib/poses.py` samples the paths that keep the feet where they stand),
    and its values are the engine's: straight from sample to sample. The rate given with them is not each step's
    own, which jumps at every sample and would reach a servo as a blow ten times a second: it is the mean of the
    two steps' rates at a sample and goes linearly from one sample's to the next, as the path's own rate does."""
    if t <= times[0]:
        return values[0], 0.0 * values[0]
    if t >= times[-1]:
        return values[-1], 0.0 * values[-1]
    at = min(int(np.searchsorted(times, t, side="right")) - 1, len(times) - 2)
    span = times[at + 1] - times[at]
    s = (t - times[at]) / span
    if ease == "linear":
        before, here, after = (slope(times, values, step) for step in (at - 1, at, at + 1))
        return values[at] + s * (values[at + 1] - values[at]), (1.0 - s) * (before + here) / 2.0 + s * (here + after) / 2.0
    return values[at] + s * s * (3.0 - 2.0 * s) * (values[at + 1] - values[at]), 6.0 * s * (1.0 - s) / span * (values[at + 1] - values[at])


def slope(times, values, step):
    """A sequence's rate over one of its steps: none before its first key, after its last, or over a step of no length."""
    if not 0 <= step < len(times) - 1 or times[step + 1] - times[step] < 1e-9:
        return 0.0 * values[0]
    return (values[step + 1] - values[step]) / (times[step + 1] - times[step])


def standing(pose):
    """Where the pelvis would be with the left sole flat on the floor at a pose: (height m, tilt degrees)."""
    turn, shift = kin.stance(pose, "l_foot")
    height = sum(turn[2][k] * PELVIS[k] * 1000.0 for k in range(3)) + shift[2]
    return height / 1000.0, math.degrees(math.acos(max(-1.0, min(1.0, turn[2][2]))))


# ---------------------------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------------------------
def simulate(model, clip, ahead=None):
    """Run a clip. Returns (frames: the state at FPS, series: what was measured at 100 Hz, report).

    `ahead` is an experiment (`oneleg.py`): ([seconds], [N m for each servo]), a torque fed ahead to every servo
    beside its angle, as these drives take one. A position servo gets it as an offset of the angle it is asked:
    the torque over its stiffness. Nothing is fed back by it: it is a plan's torque, not a measurement."""
    servos, data = Servos(model), mujoco.MjData(model)
    times, poses, ease = waypoints(clip)
    keys, times = np.array([servos.targets(pose) for pose in poses]), np.array(times)
    step = model.opt.timestep
    pelvis, floor = model.body("pelvis").id, model.geom("floor").id
    feet = {side: model.body(f"{side}_foot").id for side in kin.SIDES}
    shapes = [f"{side}_{name}" for side in kin.SIDES for name in SOLES]
    shape_of = {model.geom(name).id: n for n, name in enumerate(shapes)}
    of_foot = {side: [n for n, name in enumerate(shapes) if name[0] == side] for side in kin.SIDES}

    mujoco.mj_resetDataKeyframe(model, data, model.key(clip.start).id)
    data.ctrl[:] = wanted = keys[0]
    if clip.held:
        data.eq_active[model.equality("hold_pelvis").id] = 1
        data.mocap_pos[0] = PELVIS + (0.0, 0.0, LIFT)
        data.qpos[:3], data.qpos[3:7] = data.mocap_pos[0], (1.0, 0.0, 0.0, 0.0)
    data.qpos[2] += clip.drop
    if clip.motion is not None:                      # stand first, unseen, so that a motion starts from rest
        for _ in range(round(clip.settle / step)):
            mujoco.mj_step(model, data)
    data.time = 0.0
    mujoco.mj_forward(model, data)

    frames = {"qpos": [], "hanger": [], "state": []}
    series = {name: [] for name in ("t", "height", "tilt", "com", "soles", "force", "error")}
    peak, at_limit, worst = np.zeros(model.nu), np.zeros(model.nu), np.zeros(model.nu)
    fell, wrench, state = None, np.zeros(6), np.empty(mujoco.mj_stateSize(model, STATE))
    last = min(times[-1], clip.fit) if clip.fit else times[-1]

    def sole(body):
        """The point of a foot's sole under its ankle, in the world: where a foot is on the floor."""
        return data.xpos[body] + data.xmat[body].reshape(3, 3) @ (0.0, 0.0, -dims.ANKLE[2] / 1000.0)

    begun = {side: (sole(body), data.xmat[body].copy()) for side, body in feet.items()}
    trod, scrubbed = {side: sole(body)[:2] for side, body in feet.items()}, {side: 0.0 for side in feet}
    for k in range(round(times[-1] / step) + 1):
        t = k * step
        if t > last:
            break
        wanted, rate = eased(times, keys, ease, t)
        if ahead is None:
            data.ctrl[:] = servos.fed(wanted, rate)
        else:
            at = min(int(np.searchsorted(ahead[0], t, side="right")), len(ahead[0]) - 1)
            share = 0.0 if at == 0 else min(1.0, (t - ahead[0][at - 1]) / (ahead[0][at] - ahead[0][at - 1]))
            torque = ahead[1][at] if at == 0 else ahead[1][at - 1] + share * (ahead[1][at] - ahead[1][at - 1])
            data.ctrl[:] = servos.fed(wanted + torque / servos.stiffness, rate)
        if t + step / 2 >= len(frames["qpos"]) / FPS:
            mujoco.mj_getState(model, data, state, STATE)
            frames["state"].append(state.copy())
            frames["qpos"].append(data.qpos.copy())
            frames["hanger"].append(data.mocap_pos[0].copy())
        if k % round(0.01 / step) == 0:
            bears = np.zeros(len(shapes))                # what the floor pushes on each of the soles' shapes, N
            for i in range(data.ncon):
                contact = data.contact[i]
                other = contact.geom2 if contact.geom1 == floor else contact.geom1
                if other in shape_of:
                    mujoco.mj_contactForce(model, data, i, wrench)
                    bears[shape_of[other]] += wrench[0]
                elif fell is None and not clip.held:
                    fell = (t, f"its {model.geom(other).name} touched the floor")
                    last = last if clip.fit else min(last, t + AFTER)    # a clip of a fixed length is that long, fall or no
            load = {side: float(bears[of_foot[side]].sum()) for side in kin.SIDES}
            for side, body in feet.items():
                here = sole(body)[:2]
                if load[side] > 1.0 and fell is None:    # a foot scrubs only while it bears on the floor
                    scrubbed[side] += float(np.linalg.norm(here - trod[side]))
                trod[side] = here
            series["t"].append(t)
            series["height"].append(data.xpos[pelvis][2])
            series["tilt"].append(math.degrees(math.acos(max(-1.0, min(1.0, data.xmat[pelvis][8])))))
            series["com"].append(data.subtree_com[pelvis].copy())
            series["soles"].append(bears)
            series["force"].append(data.actuator_force.copy())
            series["error"].append(wanted - data.qpos[servos.qpos])
        mujoco.mj_step(model, data)
        if fell is None:                             # what the servos were asked while the robot stood
            force = np.abs(data.actuator_force)
            peak, worst = np.maximum(peak, force), np.maximum(worst, np.abs(wanted - data.qpos[servos.qpos]))
            at_limit += (force >= 0.999 * servos.limit) * step

    series = {name: np.array(rows) for name, rows in series.items()}
    series["sole_names"] = np.array(shapes)
    frames = {name: np.array(rows) for name, rows in frames.items()}
    height, tilt = series["height"], series["tilt"]
    borne = {side: series["soles"][:, of_foot[side]].sum(axis=1) for side in kin.SIDES}
    report = {"clip": clip.name, "motion": clip.motion, "caption": clip.caption, "held": clip.held, "seconds": float(series["t"][-1]),
              "begins_s": clip.lead if clip.motion else 0.0,
              "pelvis": {"height_mm": [round(1000 * float(v), 1) for v in (height[0], height.min(), height.max(), height[-1])],
                         "tilt_deg": [round(float(v), 2) for v in (tilt[0], tilt.max(), tilt[-1])]}}
    if not clip.held:
        # Against the poses' own geometry: where the pelvis is with a sole flat on the floor, at the lowest pose and the last.
        by_pose = [standing(pose) for pose in poses]
        report["pelvis"]["posed_mm"] = [round(1000 * min(h for h, _ in by_pose), 1), round(1000 * by_pose[-1][0], 1)]
        report["pelvis"]["posed_tilt_deg"] = [round(max(a for _, a in by_pose), 2), round(by_pose[-1][1], 2)]
        report["feet"] = {}
        for side, body in feet.items():
            at, turn = begun[side]
            spun = math.degrees(math.atan2(*(data.xmat[body].reshape(3, 3) @ turn.reshape(3, 3).T)[[1, 0], 0]))
            report["feet"][side] = {"moved_mm": [round(float(v), 1) for v in (sole(body) - at) * 1000.0],
                                    "turned_deg": round(spun, 2), "scrubbed_mm": round(1000 * scrubbed[side], 1)}
        report["load_N"] = {side: [round(float(borne[side].min())), round(float(borne[side].max()))] for side in kin.SIDES}
        # From when, until the clip's end or the fall, the balls and toes bear nothing, and each foot bears nothing.
        fore = series["soles"][:, [n for n, name in enumerate(shapes) if name[2:] in ("ball", "toe", "toe_cap")]].sum(axis=1)
        before = series["t"] <= (fell[0] if fell else series["t"][-1])
        report["heels_alone_from_s"] = first(series["t"][before], fore[before] < 1.0)
        report["foot_off_floor_from_s"] = {side: first(series["t"][before], borne[side][before] < 1.0) for side in kin.SIDES}
        if fell is None and (height[-1] < by_pose[-1][0] - 0.15 or tilt[-1] > by_pose[-1][1] + 20.0):
            fell = (float(series["t"][-1]), "it ended off its feet")
    report["fell"] = None if fell is None else {"at_s": round(fell[0], 2), "how": fell[1]}
    share = peak / servos.limit
    order = np.argsort(-share)
    report["servos"] = {
        "hardest": [{"servo": servos.names[i], "peak_Nm": round(float(peak[i]), 2), "limit_Nm": float(servos.limit[i]),
                     "share": round(float(share[i]), 3)} for i in order[:6]],
        "at_limit_s": {servos.names[i]: round(float(at_limit[i]), 3) for i in order if at_limit[i] > 0},
        "worst_error_deg": {servos.names[i]: round(math.degrees(float(worst[i])), 2) for i in np.argsort(-worst)[:5]},
        "last_error_deg": {servos.names[i]: round(math.degrees(float(series["error"][-1][i])), 2)
                           for i in np.argsort(-np.abs(series["error"][-1]))[:5]},
        "last_Nm": {servos.names[i]: round(float(series["force"][-1][i]), 1) for i in np.argsort(-np.abs(series["force"][-1]) / servos.limit)[:5]},
    }
    return frames, series, report


def first(times, holds):
    """The first of `times` from which `holds` stays true to the last of them, or None."""
    fails = np.flatnonzero(~holds)
    after = 0 if len(fails) == 0 else fails[-1] + 1
    return None if after >= len(times) else round(float(times[after]), 2)


def said(report):
    """A clip's report as a few lines."""
    pelvis, servos = report["pelvis"], report["servos"]
    fell = report["fell"]
    lines = [f"{report['clip']}: {report['seconds']:.1f} s, " + (
        "pelvis held" if report["held"] else
        f"FELL {fell['at_s'] - report['begins_s']:.2f} s into the motion ({fell['how']})" if fell else "on its feet throughout")]
    if report.get("changed"):
        lines.append("  changed from what is assumed: " + ", ".join(report["changed"]))
    if not report["held"]:
        start, low, high, end = pelvis["height_mm"]
        lines.append(f"  pelvis height {start:.1f} mm, between {low:.1f} and {high:.1f}, ends {end:.1f} "
                     f"(by the poses, sole flat: lowest {pelvis['posed_mm'][0]:.1f}, last {pelvis['posed_mm'][1]:.1f}); "
                     f"tilt at most {pelvis['tilt_deg'][1]:.2f} deg, ends {pelvis['tilt_deg'][2]:.2f} "
                     f"(by the poses {pelvis['posed_tilt_deg'][0]:.2f}, {pelvis['posed_tilt_deg'][1]:.2f})")
        lines.append("  feet: " + "; ".join(
            f"{side} scrubbed {foot['scrubbed_mm']:.0f} mm, ends ({foot['moved_mm'][0]:+.1f}, {foot['moved_mm'][1]:+.1f}) mm away "
            f"and turned {foot['turned_deg']:+.1f} deg, bore {report['load_N'][side][0]} to {report['load_N'][side][1]} N"
            for side, foot in report["feet"].items()))
    if fell:                                         # a fall's own loads say nothing of the motion: only what gave way before it
        begins = report["begins_s"]
        off = {side: at for side, at in report["foot_off_floor_from_s"].items() if at is not None and at < fell["at_s"] - 0.05}
        went = [f"{'left' if side == 'l' else 'right'} foot off the floor from {at - begins:.2f} s" for side, at in off.items()]
        heels = report["heels_alone_from_s"]
        if heels is not None and heels < min(off.values(), default=fell["at_s"]) - 0.2:
            went.insert(0, f"balls and toes bearing nothing from {heels - begins:.2f} s")
        if went:
            lines.append("  " + ", ".join(went) + " into the motion")
        spent = {name: seconds for name, seconds in servos["at_limit_s"].items() if seconds >= 0.05}
        lines.append("  at their limit before it touched down: " + (", ".join(f"{name} for {seconds:.2f} s" for name, seconds in spent.items())
                                                                   if spent else "no servo for as long as 0.05 s"))
        return "\n".join(lines)
    lines.append("  hardest-worked servos: " + ", ".join(f"{row['servo']} {row['peak_Nm']:.1f} of {row['limit_Nm']:g} N m ({row['share']:.0%})"
                                                         for row in servos["hardest"]))
    if servos["at_limit_s"]:
        lines.append("  at their limit: " + ", ".join(f"{name} for {seconds:.2f} s" for name, seconds in servos["at_limit_s"].items()))
    lines.append("  largest error: " + ", ".join(f"{name} {value:.2f}" for name, value in servos["worst_error_deg"].items()) + " deg; at the end: "
                 + ", ".join(f"{name} {value:+.2f} deg" for name, value in servos["last_error_deg"].items())
                 + "; holding " + ", ".join(f"{name} {value:+.1f} N m" for name, value in servos["last_Nm"].items()))
    return "\n".join(lines)


# ---------------------------------------------------------------------------------------------
# Picture
# ---------------------------------------------------------------------------------------------
class Picture:
    """MuJoCo's offscreen renderer and one free camera, on the model as it is drawn (`drawn`): a frame shows what a
    simulator knows and a picture does not. A grid on the floor, MuJoCo's own arrows for the floor's push at every
    point of contact, and a ring with a cross through it on the floor under the centre of mass."""

    def __init__(self):
        self.model = drawn()
        self.data = mujoco.MjData(self.model)
        self.renderer = mujoco.Renderer(self.model, height=HEIGHT, width=WIDTH)
        self.camera = mujoco.MjvCamera()
        self.camera.type = mujoco.mjtCamera.mjCAMERA_FREE
        self.shown = mujoco.MjvOption()
        self.shown.flags[mujoco.mjtVisFlag.mjVIS_CONTACTFORCE] = self.shown.flags[mujoco.mjtVisFlag.mjVIS_CONTACTPOINT] = True
        self.lines = grid_lines()

    def like(self, model):
        """Take the servos and the floor of the model a clip ran on. A frame's forces are worked out again from its
        state, and they are the simulation's only on the simulation's servos."""
        self.model.actuator_gainprm[:], self.model.actuator_biasprm[:] = model.actuator_gainprm, model.actuator_biasprm
        self.model.geom_friction[:] = model.geom_friction

    def line(self, start, end, pixels, colour):
        """Add a line to the frame being drawn: unlit, `pixels` wide, between two points of the world."""
        scene = self.renderer.scene
        geom = scene.geoms[scene.ngeom]
        mujoco.mjv_initGeom(geom, mujoco.mjtGeom.mjGEOM_LINE, np.zeros(3), np.zeros(3), np.eye(3).ravel(), np.array(colour, dtype=np.float32))
        mujoco.mjv_connector(geom, mujoco.mjtGeom.mjGEOM_LINE, pixels, np.array(start, dtype=float), np.array(end, dtype=float))
        scene.ngeom += 1

    @staticmethod
    def azimuth(turn, orbit):
        """The camera's azimuth `turn` (0 to 1) of the way through a clip, eased from orbit[0] to orbit[1]."""
        return orbit[0] + turn * turn * (3.0 - 2.0 * turn) * (orbit[1] - orbit[0])

    def frame(self, state, turn, orbit, lookat=VIEW["lookat"]):
        """One frame: the simulation's state as `simulate` kept it, the camera `turn` (0 to 1) of the way round its
        orbit. The state is the whole of it, so the contact forces drawn are the simulation's."""
        mujoco.mj_setState(self.model, self.data, state, STATE)
        mujoco.mj_forward(self.model, self.data)
        self.camera.azimuth, self.camera.elevation, self.camera.distance = self.azimuth(turn, orbit), VIEW["elevation"], VIEW["distance"]
        self.camera.lookat[:] = lookat
        self.renderer.update_scene(self.data, camera=self.camera, scene_option=self.shown)
        for start, end, pixels, opacity in self.lines:
            self.line(start, end, pixels, (*GRID["colour"], opacity))
        x, y, _ = self.data.subtree_com[self.model.body("pelvis").id]
        radius, lift = COM_MARK["radius"], 0.003
        ring = [(x + radius * math.cos(a), y + radius * math.sin(a), lift) for a in np.linspace(0.0, 2.0 * math.pi, 25)]
        for start, end in [*zip(ring, ring[1:]), (ring[0], ring[12]), (ring[6], ring[18])]:
            self.line(start, end, COM_MARK["pixels"], COM_MARK["colour"])
        return self.renderer.render()

    def aims(self, frames, orbit, fell):
        """Where the camera looks at each frame: at VIEW's point, and after a fall (`fell`: the second it touched
        down) on its way after the robot (FOLLOW)."""
        count, aim = len(frames["state"]), np.array(VIEW["lookat"])
        aims = np.tile(aim, (count, 1))
        if fell is not None:
            lies = frames["qpos"][-1][:2]                                   # where the pelvis comes to lie
            for k in range(count):
                gone = min(1.0, max(0.0, (k / FPS - fell + FOLLOW["lead"]) / FOLLOW["over"]))
                turned = math.radians(self.azimuth(k / max(count - 1, 1), orbit))
                right = np.array([math.sin(turned), -math.cos(turned)])        # the picture's right, on the floor
                there = np.array([*(lies - FOLLOW["aside"] * right), aim[2] - FOLLOW["lower"]])
                aims[k] = aim + gone * gone * (3.0 - 2.0 * gone) * (there - aim)
        return aims

    def film(self, path, frames, orbit, tag=None, fell=None):
        """Write frames as an mp4 through ffmpeg, the camera going round from orbit[0] to orbit[1]. `tag` is written
        into the picture itself, so that it cannot be lost from it. `fell`: the second at which a fall touched down."""
        look = []
        if tag:
            note = OUT / "captions" / f"{path.stem}.tag.txt"
            note.parent.mkdir(exist_ok=True)
            note.write_text(tag)
            look.append(f"drawtext=fontfile={FONTS / 'Inter-Medium.otf'}:textfile={note}:x=72:y=64:fontsize=26:fontcolor=white@0.8")
        encoder = subprocess.Popen(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{WIDTH}x{HEIGHT}", "-r", str(FPS),
             "-i", "-", "-an", *(["-vf", ",".join(look)] if look else []), "-c:v", "libx264", "-preset", "medium", "-crf", "15",
             "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(path)], stdin=subprocess.PIPE)
        count, aims = len(frames["state"]), self.aims(frames, orbit, fell)
        for k in range(count):
            encoder.stdin.write(self.frame(frames["state"][k], k / max(count - 1, 1), orbit, aims[k]).tobytes())
        encoder.stdin.close()
        if encoder.wait():
            raise RuntimeError(f"ffmpeg failed on {path}")


def changed(clip):
    """What a clip changes from the motion as it is written and the servos as they are assumed, in plain words."""
    said = []
    if clip.pace != 1.0:
        said.append("half the pace" if clip.pace == 2.0 else f"the motion {clip.pace:g} times as slow")
    if clip.ahead:
        said.append("each drive fed the torque the motion asks of it")
    if clip.ankle != 1.0:
        said.append(f"the ankles' roll servos {clip.ankle:g} times as stiff")
    return said


def headline(clip, report, speed=1):
    """A clip's three texts in the cut: the motion's name, what it shows, and how the robot stood for it."""
    fast = f" Shown x{speed:g}." if speed != 1 else ""
    if clip.held:
        return clip.motion, clip.caption, "pelvis held over the floor: the legs work in the air." + fast
    stood = "free-standing on position servos, no balance feedback"
    if report["fell"]:
        stood += f": it falls {report['fell']['at_s'] - report['begins_s']:.1f} s into the motion"
    if report.get("changed"):
        stood += ". Changed from what is assumed: " + ", ".join(report["changed"])
    return clip.motion or clip.name, clip.caption, stood + "." + fast


def caption(clip, report, speed=1):
    """The ffmpeg filters that write a clip's caption into its picture, bottom left and ending left of the robot:
    the motion's name, what the clip shows, and how the robot stood for it, the last line lowest."""
    notes = OUT / "captions"
    notes.mkdir(exist_ok=True)
    title, shows, stood = headline(clip, report, speed)
    shows, stood = textwrap.wrap(shows, CAPTION["shows"]), textwrap.wrap(stood, CAPTION["stood"])
    files = []
    for kind, text in (("title", title), ("line", "\n".join(shows)), ("stood", "\n".join(stood))):
        files.append(notes / f"{clip.name}.{kind}.txt")
        files[-1].write_text(text)
    plate = "box=1:boxcolor=black@0.5:boxborderw=7"   # a line stays legible on the grid
    low = HEIGHT - 36 - 28 * len(stood)               # the texts' tops, from the last up
    mid = low - 14 - 32 * len(shows)
    return (f"drawtext=fontfile={FONTS / 'Inter-SemiBold.otf'}:textfile={files[0]}:x=72:y={mid - 58}:fontsize=40:fontcolor=white@0.95,"
            f"drawtext=fontfile={FONTS / 'Inter-Regular.otf'}:textfile={files[1]}:x=72:y={mid}:fontsize=24:line_spacing=8:"
            f"fontcolor=white@0.82:{plate},"
            f"drawtext=fontfile={FONTS / 'Inter-Regular.otf'}:textfile={files[2]}:x=72:y={low}:fontsize=21:line_spacing=7:"
            f"fontcolor=white@0.62:{plate}")


def cut(reports):
    """The clips of CUT in a row with a caption each, a clip played faster where CUT says so: tmp/sim/galatea-sim.mp4."""
    inputs, chains = [], []
    for k, (name, speed) in enumerate(CUT):
        clip = next(clip for clip in CLIPS if clip.name == name)
        seconds = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                        str(OUT / f"{name}.mp4")], capture_output=True, text=True, check=True).stdout) / speed
        inputs += ["-i", str(OUT / f"{name}.mp4")]
        chains.append(f"[{k}:v]" + (f"setpts=PTS/{speed},fps={FPS}," if speed != 1 else "") + caption(clip, reports[name], speed)
                      + f",fade=t=in:st=0:d=0.3,fade=t=out:st={seconds - 0.3:.3f}:d=0.3[v{k}]")
    graph = ";".join(chains) + ";" + "".join(f"[v{k}]" for k in range(len(CUT))) + f"concat=n={len(CUT)}:v=1:a=0[v]"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", graph, "-map", "[v]", "-an", "-c:v", "libx264",
                    "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p", "-r", str(FPS), "-movflags", "+faststart",
                    str(OUT / "galatea-sim.mp4")], check=True)


def written():
    """The file `mjcf.py` wrote, or the way to it."""
    if not XML.exists():
        raise SystemExit(f"{XML} is not there: `cad run sim/mjcf.py` writes it, and the meshes it draws")
    return XML


def load():
    """The model `mjcf.py` wrote."""
    return mujoco.MjModel.from_xml_path(str(written()))


def tuned(model, drives=1.0, ankle_roll=1.0):
    """The model with every drive's servo `drives` times as stiff and the ankles' roll servos `ankle_roll` times
    more, damping with stiffness: what an experiment changes from the servos as `mjcf.py` assumes them."""
    scale = np.where(model.actuator_forcerange[:, 1] > 1.0, drives, 1.0)                 # the hand's servos are not a drive's
    scale = scale * np.array([ankle_roll if model.actuator(i).name[2:] == "ankle_roll" else 1.0 for i in range(model.nu)])
    model.actuator_gainprm[:, 0] *= scale
    model.actuator_biasprm[:, 1] *= scale
    model.actuator_biasprm[:, 2] *= scale
    return model


def performed(model, clip):
    """Simulate a clip on the servos it asks for: (the model it ran on, frames, series, report). A clip that feeds
    torque ahead is run first on servos STIFF times as stiff, which keep to its path, and what each drive gave there
    is what it is fed: a plan's torque, worked out beforehand."""
    ahead = None
    if clip.ahead:
        _, followed, kept = simulate(tuned(copy.deepcopy(model), drives=STIFF), clip)
        if kept["fell"]:
            raise SystemExit(f"{clip.name}: on servos {STIFF:g} times as stiff it falls too, so there is no torque to feed ahead")
        ahead = (followed["t"], followed["force"])
    own = model if clip.ankle == 1.0 else tuned(copy.deepcopy(model), ankle_roll=clip.ankle)
    frames, series, report = simulate(own, clip, ahead)
    report["changed"] = changed(clip)
    return own, frames, series, report


def pictured():
    """A Picture, or None, said plainly, where MuJoCo's renderer cannot start: no picture is made up."""
    try:
        return Picture()
    except Exception as error:  # noqa: BLE001  (whatever a missing GL context raises)
        print(f"no picture: MuJoCo's renderer could not start with MUJOCO_GL={os.environ['MUJOCO_GL']} "
              f"({type(error).__name__}: {error}). The simulated trajectories are written to {OUT}/<clip>.npz.")


def current(model, start="ready"):
    """Refuse a model written from other poses than `lib/poses.py` holds now: its keyframes are the poses', and a
    clip starts from one of them."""
    asked = Servos(model).targets(POSES[start])
    if float(np.abs(model.key(start).ctrl - asked).max()) > 1e-6:
        raise SystemExit(f"{XML.name} was written before lib/poses.py last changed (its keyframe {start} is not the pose {start}): "
                         "`cad run sim/mjcf.py --poses` writes its keyframes again")


# ---------------------------------------------------------------------------------------------
# The look: the simulation drawn so that it reads as one
# ---------------------------------------------------------------------------------------------
def png(image):
    """An 8-bit RGB image (rows x columns x 3) as a PNG file's bytes."""
    def chunk(tag, body):
        return struct.pack(">I", len(body)) + tag + body + struct.pack(">I", zlib.crc32(tag + body))

    rows = b"".join(b"\x00" + row.tobytes() for row in np.ascontiguousarray(image, dtype=np.uint8))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", image.shape[1], image.shape[0], 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b""))


def grid(ground):
    """The floor's tile, a millimetre a pixel: the floor's own colour with a heavy line round it, so one each
    GRID["tile"]. The world's origin, between the feet, is on a crossing of them."""
    width, by = GRID["heavy"]
    on = (np.arange(GRID["tile"]) + width // 2) % GRID["tile"] < width
    lighter = np.zeros((GRID["tile"], GRID["tile"]))
    lighter[on, :] = lighter[:, on] = by
    return np.round(255.0 * np.clip(np.array(ground) + lighter[..., None], 0.0, 1.0)).astype(np.uint8)


def grid_lines():
    """The grid's lines near the robot: [(start, end, pixels wide, opacity)], in pieces, so that they fade with their
    distance from the origin and end GRID["reach"] from it."""
    reach, piece, tile, lift = GRID["reach"], GRID["piece"], GRID["tile"] / 1000.0, 0.002
    lines = []
    for at in np.round(np.arange(-reach, reach + 1e-9, GRID["fine"] / 1000.0), 6):
        heavy = abs(at / tile - round(at / tile)) < 1e-6
        pixels, most = GRID["lines"][GRID["tile"] if heavy else GRID["fine"]]
        for start in np.arange(-reach, reach - 1e-9, piece):
            opacity = most * (1.0 - (at * at + (start + piece / 2) ** 2) / (reach * reach))
            if opacity > 0.01:
                lines.append(((at, start, lift), (at, start + piece, lift), pixels, opacity))
                lines.append(((start, at, lift), (start + piece, at, lift), pixels, opacity))
    return lines


def drawn():
    """The model as `mjcf.py` wrote it, with what every clip is drawn with: the grid on the floor (and a backdrop
    of the gridded floor's mean colour, so that still no horizon shows), and the contact forces' arrows scaled and
    coloured to be read. Nothing of the mechanics is touched, and `galatea.xml` is not rewritten."""
    root = ET.parse(written()).getroot()
    root.find("compiler").set("meshdir", str(HERE / "meshes"))
    asset = root.find("asset")
    floor = next(material for material in asset.findall("material") if material.get("name") == "floor")
    ground = np.array(floor.get("rgba").split()[:3], dtype=float)
    tile = grid(ground)
    ET.SubElement(asset, "texture", name="grid", type="2d", file="grid.png")
    floor.attrib.update(texture="grid", rgba="1 1 1 1", texuniform="true", texrepeat=" ".join([f"{1000.0 / GRID['tile']:g}"] * 2))
    haze = root.find("visual/rgba")
    far = np.array(haze.get("haze").split()[:3], dtype=float) / ground * tile.mean(axis=(0, 1)) / 255.0       # lit as the floor is
    haze.set("haze", " ".join(f"{c:.4g}" for c in (*far, 1.0)))
    backdrop = next(texture for texture in asset.findall("texture") if texture.get("type") == "skybox")
    backdrop.attrib.update(rgb1=" ".join(f"{c:.4g}" for c in far), rgb2=" ".join(f"{c:.4g}" for c in far))
    model = mujoco.MjModel.from_xml_string(ET.tostring(root, encoding="unicode"), {"grid.png": png(tile)})
    # MuJoCo sizes a contact's arrow at force x vis.map.force / the mean mass, and draws an arrow at half its size
    # (measured: one of size 1 m is drawn 0.49 m long, head and all).
    model.vis.map.force = 2.0 * FORCE["metres"] / FORCE["newtons"] * model.stat.meanmass
    model.vis.scale.forcewidth = FORCE["width"] / model.stat.meansize
    model.vis.scale.contactwidth, model.vis.scale.contactheight = 0.013 / model.stat.meansize, 0.003 / model.stat.meansize
    model.vis.rgba.contactforce[:], model.vis.rgba.contactpoint[:] = FORCE["colour"], FORCE["point"]
    return model


def film(motion, stills=(), dry=False):
    """tmp/sim/film_clip.mp4: the robot let go DROP over the floor, landing, and then `motion`, free-standing, in
    FILM_SECONDS; or, with `stills`, those frames of it as PNG files; or, `dry`, its report alone."""
    keys = next(keys for name, keys, _ in MOTIONS if name == motion)
    asked, begins = keys[-1][0], keys[0][1]
    # It is let go in the pose its motion begins from: `ready` for all but the one that wakes it.
    clip = Clip("film_clip", f"let go {DROP * 1000:g} mm over the floor, then the motion {motion}", motion=motion, drop=DROP,
                settle=0.0, lead=LAND, tail=0.0, fit=FILM_SECONDS, orbit=(128.0, 122.0), start=begins if isinstance(begins, str) else "ready")
    times, _, _ = waypoints(clip)
    OUT.mkdir(parents=True, exist_ok=True)
    model = load()
    current(model, clip.start)
    frames, series, report = simulate(model, clip)
    count = round(FILM_SECONDS * FPS)
    frames = {name: rows[:count] for name, rows in frames.items()}
    assert len(frames["state"]) == count, f"the film's clip is {len(frames['state'])} frames, not {count}"
    played = times[-2] - LAND
    print(f"film_clip: {motion}, {asked:g} s as written, from {LAND:g} s to {min(times[-2], FILM_SECONDS):g} s of {FILM_SECONDS:g}"
          + (f", its holds played {asked - played:.2f} s shorter" if played < asked - 1e-9 else "")
          + (f"; THE CLIP ENDS {times[-2] - FILM_SECONDS:.2f} s BEFORE THE MOTION DOES" if times[-2] > FILM_SECONDS + 1e-9 else ""))
    print(said(report), flush=True)
    if stills:
        picture = pictured()
        return picture and still(picture, clip, frames, report, stills)
    (OUT / "film_clip.json").write_text(json.dumps(report, indent=1) + "\n")
    np.savez_compressed(OUT / "film_clip.npz", fps=FPS, qpos=frames["qpos"], hanger=frames["hanger"],
                        joints=[model.joint(i).name for i in range(model.njnt)], servos=[model.actuator(i).name for i in range(model.nu)],
                        **series)
    picture, started = None if dry else pictured(), time.time()
    if picture is None:
        return
    picture.film(OUT / "film_clip.mp4", frames, clip.orbit, fell=report["fell"]["at_s"] if report["fell"] else None)
    print(f"{OUT / 'film_clip.mp4'}: {count} frames in {time.time() - started:.0f} s")


def still(picture, clip, frames, report, wanted):
    """Frames of a clip as PNG files, drawn as its video draws them: tmp/sim/<clip>.NNN.png."""
    count = len(frames["state"])
    aims = picture.aims(frames, clip.orbit, report["fell"]["at_s"] if report["fell"] else None)
    for k in wanted:
        if not 0 <= k < count:
            print(f"{clip.name} has frames 0 to {count - 1}: none {k}")
            continue
        path = OUT / f"{clip.name}.{k:03d}.png"
        path.write_bytes(png(picture.frame(frames["state"][k], k / max(count - 1, 1), clip.orbit, aims[k])))
        print(path)


def trial_asked(options):
    return options.friction is not None or options.stiffness is not None or options.pace is not None or options.still_legs


def main(arguments):
    parser = argparse.ArgumentParser(prog="cad run sim/run.py", description="Galatea's motions in MuJoCo, and their video.")
    parser.add_argument("clips", nargs="*", metavar="CLIP", help=f"the clips to run (all of them unless named): {', '.join(c.name for c in CLIPS)}")
    parser.add_argument("--dry", action="store_true", help="simulate and report: no picture")
    parser.add_argument("--cut", action="store_true", help="cut the clips' videos together again, as they are, and stop")
    # Any motion but the gait: that one is shown held and labelled, and this clip holds nothing and says nothing.
    parser.add_argument("--film", nargs="?", const="bow", metavar="MOTION", choices=[name for name, _, _ in MOTIONS if name != "walk"],
                        help="make tmp/sim/film_clip.mp4 alone, from this motion (bow unless named), and stop")
    parser.add_argument("--stills", metavar="FRAMES", help="these frames (numbers with commas) of the named clips, or of --film's, as PNG "
                                                         "files: no video, and nothing else written")
    trial = parser.add_argument_group("experiments: another floor, other servos or a changed motion; reports only, nothing is written")
    trial.add_argument("--friction", type=float, help="the floor's friction (the model's own: 0.7)")
    trial.add_argument("--stiffness", type=float, help="every drive's servo this many times as stiff, its damping with it")
    trial.add_argument("--pace", type=float, help="every motion played this many times as slow")
    trial.add_argument("--still-legs", action="store_true", help="the legs' controls left at the pose ready through every motion")
    options = parser.parse_args(arguments)
    unknown = sorted(set(options.clips) - {clip.name for clip in CLIPS})
    if unknown:
        parser.error(f"no clip {', '.join(unknown)}")
    if options.cut:
        cut(json.loads((OUT / "report.json").read_text()))
        return print(OUT / "galatea-sim.mp4")
    stills = [int(k) for k in options.stills.split(",")] if options.stills else []
    trial = trial_asked(options)
    if stills and (options.dry or trial or not (options.film or options.clips)):
        parser.error("--stills draws frames of the clips it is given, or of --film's: name them, and no --dry and no experiment with it")
    if options.film:
        if options.clips or trial:
            parser.error("--film makes its one clip, of the model as it is: name no other clip and no experiment with it")
        return film(options.film, stills, options.dry)
    clips = [replace(clip, still_legs=options.still_legs, pace=options.pace or clip.pace) for clip in CLIPS
             if not options.clips or clip.name in options.clips]
    OUT.mkdir(parents=True, exist_ok=True)
    model = load()
    for start in sorted({clip.start for clip in clips}):
        current(model, start)
    if options.friction is not None:
        model.geom_friction[:, 0] = options.friction
    if options.stiffness is not None:
        tuned(model, drives=options.stiffness)
    print(f"{XML.name}: {float(model.body_mass.sum()):.2f} kg, {model.nu} servos, step {model.opt.timestep * 1000:g} ms, "
          f"floor friction {model.geom_friction[model.geom('floor').id, 0]:g}"
          + (f", the drives' servos {options.stiffness:g} times as stiff" if options.stiffness is not None else "")
          + (f", every motion {options.pace:g} times as slow" if options.pace is not None else "")
          + (", the legs' controls left at ready" if options.still_legs else ""))

    picture = None if options.dry or trial else pictured()
    reports_file = OUT / "report.json"
    reports = json.loads(reports_file.read_text()) if reports_file.exists() else {}
    reports = {clip.name: reports[clip.name] for clip in CLIPS if clip.name in reports}       # none of a clip there no longer is
    for clip in clips:
        started = time.time()
        own, frames, series, report = performed(model, clip)
        print(said(report), flush=True)
        if trial:
            continue
        if stills:
            if picture:
                picture.like(own)
                still(picture, clip, frames, report, stills)
            continue
        reports[clip.name] = report
        reports_file.write_text(json.dumps(reports, indent=1) + "\n")
        reports_file.with_suffix(".txt").write_text("\n".join(said(reports[c.name]) for c in CLIPS if c.name in reports) + "\n")
        np.savez_compressed(OUT / f"{clip.name}.npz", fps=FPS, qpos=frames["qpos"], hanger=frames["hanger"],
                            joints=[model.joint(i).name for i in range(model.njnt)], servos=[model.actuator(i).name for i in range(model.nu)],
                            **series)
        if picture:
            picture.like(own)
            picture.film(OUT / f"{clip.name}.mp4", frames, clip.orbit, tag="pelvis held over the floor" if clip.held else None,
                         fell=report["fell"]["at_s"] if report["fell"] else None)
            print(f"  {clip.name}.mp4: {len(frames['qpos'])} frames in {time.time() - started:.0f} s", flush=True)
    if picture and not stills and all((OUT / f"{name}.mp4").exists() and name in reports for name, _ in CUT):
        cut(reports)
        print(OUT / "galatea-sim.mp4")


if __name__ == "__main__":
    main(sys.argv[1:])
