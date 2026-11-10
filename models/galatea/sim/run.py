# /// script
# dependencies = ["mujoco", "numpy"]
# ///
"""Galatea's motions in MuJoCo: under gravity, on its own feet, by position servos alone; and their video.

    cad run sim/run.py                    every clip: simulate, report, render, and cut them together
    cad run sim/run.py crouch bow         the named clips
    cad run sim/run.py --dry              simulate and report: no picture
    cad run sim/run.py --cut              cut the clips' videos together again, as they are
    cad run sim/run.py --film crouch      the showcase film's clip alone, from that motion (bow unless one is named);
                       --dry              with it, its report and no picture; --stills 0,60,119: those frames as PNG files
    cad run sim/run.py --friction 1.0     an experiment, reports only: on another floor (the model's own is 0.7),
                       --stiffness 4      with every drive's servo so many times as stiff,
                       --still-legs       or with the legs' controls left at `ready` through every motion

`build.py` writes the model this loads (`sim/galatea.xml`). A clip resets the robot to a keyframe
(`ready`; `rest` for the motion that wakes it), standing on the floor with nothing holding it, lets it
settle, and then feeds the servos a motion of `lib/poses.py`: the motion's waypoints in the model's
controls, between them exactly as the CAD engine plays a configuration sequence (eased from waypoint
to waypoint, or straight from sample to sample of a sampled path). There is no balance controller:
each servo follows its own joint's angle and knows nothing of the floor, of the other joints or of
where the weight is. A robot that falls is shown falling, and the clip stops soon after.

A clip marked `held` is the exception, and says so in its picture: the weld `hold_pelvis` is turned
on and the pelvis hangs from a point over the floor, the feet clear of it. The motions the standing
robot cannot do (the two that stand on one foot) are shown a second time so, and the walk only so:
walking needs a controller this model does not have.

`--film` makes one more clip, for the showcase film, and nothing else: the robot let go 30 mm over the
floor, its landing, and then one motion, free-standing, in exactly five seconds and with nothing written
on the picture. It is drawn to be read as a simulation: a grid on the floor, MuJoCo's own arrows for the
floor's push at every point of contact, and a mark on the floor under the centre of mass.

Everything is written into `tmp/sim/`, which Git ignores: `<clip>.mp4`, `<clip>.npz` (the simulated
trajectory and what was measured along it), `report.json` and `report.txt` (every clip's numbers, and
the same as this script says them), `galatea-sim.mp4` (the clips in a row, each with its caption), and
the film's `film_clip.mp4`, `film_clip.npz` and `film_clip.json`. The picture is MuJoCo's own renderer,
offscreen: `MUJOCO_GL` chooses the context (`egl` unless set; `osmesa` works too).
"""

import argparse
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
AFTER = 2.5            # s recorded after a fall
LIFT = 0.10            # m: how far over its place at the zero pose a held pelvis hangs
SOLES = ("heel", "ball", "toe", "toe_cap", "upper")           # the shapes of a foot: anything else on the floor is a fall
LEGS = ("hip_yaw", "hip_roll", "hip_pitch", "knee", "ankle_pitch", "ankle_roll", "toe")      # a leg's controls
STATE = mujoco.mjtState.mjSTATE_INTEGRATION                   # what a frame keeps: enough to compute its contact forces again
# The film's clip (`--film`): its length, how long the landing has before the motion begins, how far over the
# floor the robot is let go, and the least a motion's hold is played for when the motion has to be fitted in.
FILM_SECONDS, LAND, DROP, HOLD_LEAST = 5.0, 0.8, 0.03, 0.2
FILM_VIEW = dict(elevation=-5.5, distance=4.1, lookat=(0.0, -0.05, 0.875))        # from chest height: the robot fills 0.8 of the picture
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


# Every motion of `lib/poses.py`, free-standing. The two that stand on one foot fall so, and are shown again held;
# the gait is shown held alone.
CLIPS = [
    Clip("ready", "let go 30 mm over the floor: it lands, settles and stands", seconds=6.0, drop=0.03),
    Clip("wake", "asleep on its feet, it wakes", motion="wake", start="rest", orbit=(140.0, 118.0)),
    Clip("bow", "a bow from the hips and the waist, the hips eased back over the heels", motion="bow", orbit=(150.0, 126.0)),
    Clip("wave", "a greeting", motion="wave", orbit=(98.0, 118.0)),
    Clip("reach", "the right hand offered forward, the feet where they stand", motion="reach", orbit=(130.0, 106.0)),
    Clip("look", "the head looks round", motion="look", orbit=(102.0, 84.0)),
    Clip("grasp", "both hands close and open", motion="grasp", orbit=(86.0, 106.0)),
    Clip("crouch", "a squat and back up: the hips go back and down over feet that stay", motion="crouch", orbit=(132.0, 146.0)),
    Clip("settle", "into contrapposto: the weight goes over the right foot first, and one ankle's roll drive cannot keep it there",
         motion="settle", orbit=(104.0, 122.0)),
    Clip("settle_held", "into contrapposto as it is written: on a floor the step wants balance feedback", motion="settle", held=True,
         orbit=(104.0, 128.0)),
    Clip("poise", "onto the left leg: the weight goes over it first, and one ankle's roll drive cannot keep it there", motion="poise",
         orbit=(108.0, 122.0)),
    Clip("poise_held", "onto the left leg alone as it is written: on a floor it wants balance feedback", motion="poise", held=True,
         orbit=(110.0, 130.0)),
    Clip("walk_held", "the gait: walking needs a controller this model does not have", motion="walk", held=True, repeat=3,
         orbit=(150.0, 120.0)),
]


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
        self.lead = -model.actuator_biasprm[:, 2] / model.actuator_gainprm[:, 0]
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
            stops.append(lap * keys[-1][0] + at)
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
def simulate(model, clip):
    """Run a clip. Returns (frames: the state at FPS, series: what was measured at 100 Hz, report)."""
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
        data.ctrl[:] = servos.fed(wanted, rate)
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
    """MuJoCo's offscreen renderer on the model, and one free camera. With `forces`, a frame also shows what a
    simulator knows and a picture does not: MuJoCo's own arrows for the floor's push at every point of contact, a
    ring with a cross through it on the floor under the centre of mass, and the grid's lines near the robot."""

    def __init__(self, model, forces=False):
        self.model, self.data, self.forces = model, mujoco.MjData(model), forces
        self.renderer = mujoco.Renderer(model, height=HEIGHT, width=WIDTH)
        self.camera = mujoco.MjvCamera()
        self.camera.type = mujoco.mjtCamera.mjCAMERA_FREE
        self.shown = mujoco.MjvOption()
        self.shown.flags[mujoco.mjtVisFlag.mjVIS_CONTACTFORCE] = self.shown.flags[mujoco.mjtVisFlag.mjVIS_CONTACTPOINT] = forces
        self.lines = grid_lines() if forces else []

    def line(self, start, end, pixels, colour):
        """Add a line to the frame being drawn: unlit, `pixels` wide, between two points of the world."""
        scene = self.renderer.scene
        geom = scene.geoms[scene.ngeom]
        mujoco.mjv_initGeom(geom, mujoco.mjtGeom.mjGEOM_LINE, np.zeros(3), np.zeros(3), np.eye(3).ravel(), np.array(colour, dtype=np.float32))
        mujoco.mjv_connector(geom, mujoco.mjtGeom.mjGEOM_LINE, pixels, np.array(start, dtype=float), np.array(end, dtype=float))
        scene.ngeom += 1

    def frame(self, state, turn, azimuth, elevation=-7.0, distance=4.0, lookat=(0.0, -0.02, 0.87)):
        """One frame: the simulation's state as `simulate` kept it, the camera `turn` (0 to 1) of the way from
        azimuth[0] to azimuth[1]. The state is the whole of it, so the contact forces drawn are the simulation's."""
        mujoco.mj_setState(self.model, self.data, state, STATE)
        mujoco.mj_forward(self.model, self.data)
        turn = turn * turn * (3.0 - 2.0 * turn)
        self.camera.azimuth, self.camera.elevation, self.camera.distance = azimuth[0] + turn * (azimuth[1] - azimuth[0]), elevation, distance
        self.camera.lookat[:] = lookat
        self.renderer.update_scene(self.data, camera=self.camera, scene_option=self.shown)
        for start, end, pixels, opacity in self.lines:
            self.line(start, end, pixels, (*GRID["colour"], opacity))
        if self.forces:
            x, y, _ = self.data.subtree_com[self.model.body("pelvis").id]
            radius, lift = COM_MARK["radius"], 0.003
            ring = [(x + radius * math.cos(a), y + radius * math.sin(a), lift) for a in np.linspace(0.0, 2.0 * math.pi, 25)]
            for start, end in [*zip(ring, ring[1:]), (ring[0], ring[12]), (ring[6], ring[18])]:
                self.line(start, end, COM_MARK["pixels"], COM_MARK["colour"])
        return self.renderer.render()

    def film(self, path, frames, orbit, tag=None, plain=False, **view):
        """Write frames as an mp4 through ffmpeg, the camera going round from orbit[0] to orbit[1]. The corners
        are darkened a little, unless the picture is to be `plain`; `tag` is written into the picture itself, so
        that it cannot be lost from it."""
        look = [] if plain else ["vignette=angle=0.5"]
        if tag:
            note = OUT / "captions" / f"{path.stem}.tag.txt"
            note.parent.mkdir(exist_ok=True)
            note.write_text(tag)
            look.append(f"drawtext=fontfile={FONTS / 'Inter-Medium.otf'}:textfile={note}:x=72:y=64:fontsize=26:fontcolor=white@0.8")
        encoder = subprocess.Popen(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{WIDTH}x{HEIGHT}", "-r", str(FPS),
             "-i", "-", "-an", *(["-vf", ",".join(look)] if look else []), "-c:v", "libx264", "-preset", "medium", "-crf", "15",
             "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(path)], stdin=subprocess.PIPE)
        count = len(frames["state"])
        for k in range(count):
            encoder.stdin.write(self.frame(frames["state"][k], k / max(count - 1, 1), orbit, **view).tobytes())
        encoder.stdin.close()
        if encoder.wait():
            raise RuntimeError(f"ffmpeg failed on {path}")


def headline(clip, report):
    """A clip's three lines in the cut: the motion's name, what it shows, and how the robot stood for it."""
    if clip.held:
        return clip.motion, clip.caption, "pelvis held over the floor: the legs work in the air"
    if report["fell"]:
        return clip.name, clip.caption, f"free-standing: it falls {report['fell']['at_s'] - report['begins_s']:.1f} s into the motion"
    return clip.name, clip.caption, "free-standing: position servos, no balance controller"


def cut(clips, reports):
    """The clips in a row with a caption each: tmp/sim/galatea-sim.mp4."""
    notes = OUT / "captions"
    notes.mkdir(exist_ok=True)
    inputs, chains = [], []
    plate = "box=1:boxcolor=black@0.5:boxborderw=7"   # a line stays legible where a fallen robot lies behind it
    for k, clip in enumerate(clips):
        name, shows, stood = headline(clip, reports[clip.name])
        shows = textwrap.wrap(shows, 46)             # short lines, so that the words stay to the left of the robot's feet
        written = []
        for kind, text in (("title", name), ("line", "\n".join(shows)), ("stood", stood)):
            written.append(notes / f"{clip.name}.{kind}.txt")
            written[-1].write_text(text)
        seconds = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                        str(OUT / f"{clip.name}.mp4")], capture_output=True, text=True, check=True).stdout)
        inputs += ["-i", str(OUT / f"{clip.name}.mp4")]
        top = 76 + 34 * len(shows)                   # the caption's first line, from the picture's foot
        chains.append(
            f"[{k}:v]drawtext=fontfile={FONTS / 'Inter-SemiBold.otf'}:textfile={written[0]}:x=72:y=h-{top + 58}:fontsize=40:fontcolor=white@0.95,"
            f"drawtext=fontfile={FONTS / 'Inter-Regular.otf'}:textfile={written[1]}:x=72:y=h-{top}:fontsize=24:line_spacing=8:"
            f"fontcolor=white@0.82:{plate},"
            f"drawtext=fontfile={FONTS / 'Inter-Regular.otf'}:textfile={written[2]}:x=72:y=h-64:fontsize=21:fontcolor=white@0.58:{plate},"
            f"fade=t=in:st=0:d=0.3,fade=t=out:st={seconds - 0.3:.3f}:d=0.3[v{k}]")
    graph = ";".join(chains) + ";" + "".join(f"[v{k}]" for k in range(len(clips))) + f"concat=n={len(clips)}:v=1:a=0[v]"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", graph, "-map", "[v]", "-an", "-c:v", "libx264",
                    "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p", "-r", str(FPS), "-movflags", "+faststart",
                    str(OUT / "galatea-sim.mp4")], check=True)


def written():
    """The file `build.py` wrote, or the way to it."""
    if not XML.exists():
        raise SystemExit(f"{XML} is not there: `cad run sim/build.py` writes it, and the meshes it draws")
    return XML


def load():
    """The model `build.py` wrote."""
    return mujoco.MjModel.from_xml_path(str(written()))


def pictured(model, forces=False):
    """A Picture of the model, or None, said plainly, where MuJoCo's renderer cannot start: no picture is made up."""
    try:
        return Picture(model, forces)
    except Exception as error:  # noqa: BLE001  (whatever a missing GL context raises)
        print(f"no picture: MuJoCo's renderer could not start with MUJOCO_GL={os.environ['MUJOCO_GL']} "
              f"({type(error).__name__}: {error}). The simulated trajectories are written to {OUT}/<clip>.npz.")


def current(model, start="ready"):
    """Refuse a model written from other poses than `lib/poses.py` holds now: its keyframes are the poses', and a
    clip starts from one of them."""
    asked = Servos(model).targets(POSES[start])
    if float(np.abs(model.key(start).ctrl - asked).max()) > 1e-6:
        raise SystemExit(f"{XML.name} was written before lib/poses.py last changed (its keyframe {start} is not the pose {start}): "
                         "`cad run sim/build.py --poses` writes its keyframes again")


# ---------------------------------------------------------------------------------------------
# The film's clip: the same simulation, drawn so that it reads as one
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


def film_model():
    """The model as `build.py` wrote it, with what the film's clip is drawn with: the grid on the floor (and a
    backdrop of the gridded floor's mean colour, so that still no horizon shows), and the contact forces' arrows
    scaled and coloured to be read. Nothing of the mechanics is touched, and `galatea.xml` is not rewritten."""
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
    model = film_model()
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
    (OUT / "film_clip.json").write_text(json.dumps(report, indent=1) + "\n")
    np.savez_compressed(OUT / "film_clip.npz", fps=FPS, qpos=frames["qpos"], hanger=frames["hanger"],
                        joints=[model.joint(i).name for i in range(model.njnt)], servos=[model.actuator(i).name for i in range(model.nu)],
                        **series)
    picture, started = None if dry else pictured(model, forces=True), time.time()
    if picture is None:
        return
    for k in stills:
        path = OUT / f"film_clip.{k:03d}.png"
        path.write_bytes(png(picture.frame(frames["state"][k], k / (count - 1), clip.orbit, **FILM_VIEW)))
        print(path)
    if not stills:
        picture.film(OUT / "film_clip.mp4", frames, clip.orbit, plain=True, **FILM_VIEW)
        print(f"{OUT / 'film_clip.mp4'}: {count} frames in {time.time() - started:.0f} s")


def trial_asked(options):
    return options.friction is not None or options.stiffness is not None or options.still_legs


def main(arguments):
    parser = argparse.ArgumentParser(prog="cad run sim/run.py", description="Galatea's motions in MuJoCo, and their video.")
    parser.add_argument("clips", nargs="*", metavar="CLIP", help=f"the clips to run (all of them unless named): {', '.join(c.name for c in CLIPS)}")
    parser.add_argument("--dry", action="store_true", help="simulate and report: no picture")
    parser.add_argument("--cut", action="store_true", help="cut the clips' videos together again, as they are, and stop")
    # Any motion but the gait: that one is shown held and labelled, and this clip holds nothing and says nothing.
    parser.add_argument("--film", nargs="?", const="bow", metavar="MOTION", choices=[name for name, _, _ in MOTIONS if name != "walk"],
                        help="make tmp/sim/film_clip.mp4 alone, from this motion (bow unless named), and stop")
    parser.add_argument("--stills", metavar="FRAMES", help=f"with --film: these frames of its clip (0 to {round(FILM_SECONDS * FPS) - 1}, "
                                                         "with commas) as PNG files, and no video")
    trial = parser.add_argument_group("experiments: another floor, other servos or a changed motion; reports only, nothing is written")
    trial.add_argument("--friction", type=float, help="the floor's friction (the model's own: 0.7)")
    trial.add_argument("--stiffness", type=float, help="every drive's servo this many times as stiff, its damping with it")
    trial.add_argument("--still-legs", action="store_true", help="the legs' controls left at the pose ready through every motion")
    options = parser.parse_args(arguments)
    unknown = sorted(set(options.clips) - {clip.name for clip in CLIPS})
    if unknown:
        parser.error(f"no clip {', '.join(unknown)}")
    if options.cut:
        cut(CLIPS, json.loads((OUT / "report.json").read_text()))
        return print(OUT / "galatea-sim.mp4")
    if options.stills and not options.film:
        parser.error("--stills goes with --film")
    if options.film:
        if options.clips or trial_asked(options):
            parser.error("--film makes its one clip, of the model as it is: name no other clip and no experiment with it")
        stills = [int(k) for k in options.stills.split(",")] if options.stills else []
        if any(not 0 <= k < round(FILM_SECONDS * FPS) for k in stills):
            parser.error(f"--stills: the clip's frames are 0 to {round(FILM_SECONDS * FPS) - 1}")
        return film(options.film, stills, options.dry)
    trial = trial_asked(options)
    clips = [replace(clip, still_legs=options.still_legs) for clip in CLIPS if not options.clips or clip.name in options.clips]
    OUT.mkdir(parents=True, exist_ok=True)
    model = load()
    for start in sorted({clip.start for clip in clips}):
        current(model, start)
    if options.friction is not None:
        model.geom_friction[:, 0] = options.friction
    if options.stiffness is not None:
        drives = model.actuator_forcerange[:, 1] > 1.0           # the drives' servos; the hand's are not a drive's
        model.actuator_gainprm[drives, 0] *= options.stiffness
        model.actuator_biasprm[drives, 1:3] *= options.stiffness
    print(f"{XML.name}: {float(model.body_mass.sum()):.2f} kg, {model.nu} servos, step {model.opt.timestep * 1000:g} ms, "
          f"floor friction {model.geom_friction[model.geom('floor').id, 0]:g}"
          + (f", the drives' servos {options.stiffness:g} times as stiff" if options.stiffness is not None else "")
          + (", the legs' controls left at ready" if options.still_legs else ""))

    picture = None if options.dry or trial else pictured(model)
    reports_file = OUT / "report.json"
    reports = json.loads(reports_file.read_text()) if reports_file.exists() else {}
    reports = {clip.name: reports[clip.name] for clip in CLIPS if clip.name in reports}       # none of a clip there no longer is
    for clip in clips:
        started = time.time()
        frames, series, report = simulate(model, clip)
        print(said(report), flush=True)
        if trial:
            continue
        reports[clip.name] = report
        reports_file.write_text(json.dumps(reports, indent=1) + "\n")
        reports_file.with_suffix(".txt").write_text("\n".join(said(reports[c.name]) for c in CLIPS if c.name in reports) + "\n")
        np.savez_compressed(OUT / f"{clip.name}.npz", fps=FPS, qpos=frames["qpos"], hanger=frames["hanger"],
                            joints=[model.joint(i).name for i in range(model.njnt)], servos=[model.actuator(i).name for i in range(model.nu)],
                            **series)
        if picture:
            picture.film(OUT / f"{clip.name}.mp4", frames, clip.orbit, tag="pelvis held over the floor" if clip.held else None)
            print(f"  {clip.name}.mp4: {len(frames['qpos'])} frames in {time.time() - started:.0f} s", flush=True)
    if picture and all((OUT / f"{clip.name}.mp4").exists() and clip.name in reports for clip in CLIPS):
        cut(CLIPS, reports)
        print(OUT / "galatea-sim.mp4")


if __name__ == "__main__":
    main(sys.argv[1:])
