# /// script
# dependencies = ["mujoco", "numpy"]
# ///
"""What standing on one leg asks of Galatea's drives: an experiment on the two motions that lift a foot.

    cad run sim/oneleg.py            two minutes; prints three tables and writes nothing

`run.py` shows `poise` and `settle` falling, free-standing, on the servos as `mjcf.py` assumes them. This says
what would have to be otherwise for them not to fall, with no balance feedback anywhere: in every row each servo
still knows its own joint's angle and nothing else.

1. Stiffness and pace. Every drive's servo as assumed, 4 and 8 times as stiff; the motion as it is written, and
   2 and 4 times as slow.
2. The ankle alone. Only the ankles' roll servos stiffer, 16 times: is it that one joint?
3. Torque fed ahead. At half the pace, on servos as assumed but for the ankles' roll, each drive is fed the torque
   the motion will ask of it, beside the angle (`run.simulate`'s `ahead`). The torque is what the drive gave in a
   run that followed the plan, the one of table 1 with every servo 8 times as stiff: a plan's torque, known
   beforehand, not a measurement. These drives take such a term; it is the least a controller adds to a position.

A cell says when the robot fell, in seconds from where the motion begins, or that it stood through the motion and
for how long the stance ankle's roll drive was at its limit on the way.
"""

import sys
from dataclasses import replace
from pathlib import Path

import mujoco

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import run  # noqa: E402  (puts src/ on the path)

MOTIONS = {"poise": "l", "settle": "r"}          # each motion, and the foot it stands on
PACES = (1.0, 2.0, 4.0)


def robot(drives=1.0, ankle_roll=1.0):
    """The model with every drive's servo `drives` times as stiff, and the ankles' roll servos `ankle_roll` times more."""
    return run.tuned(run.load(), drives, ankle_roll)


def clip_of(name, pace=1.0):
    """The motion's clip as `run.py` shows it falling, at a pace."""
    return replace(next(clip for clip in run.CLIPS if clip.name == name), pace=pace)


def outcome(report, clip):
    """A cell: when it fell, or that it stood, and how long the ankles' roll drives were at their limit."""
    if report["fell"]:
        return f"falls at {report['fell']['at_s'] - clip.lead:.1f} s"
    limit = sum(seconds for name, seconds in report["servos"]["at_limit_s"].items() if name[2:] == "ankle_roll")
    return f"STANDS ({limit:.1f} s at its limit)"


def main():
    model = robot()
    data = mujoco.MjData(model)
    run.current(model)
    mujoco.mj_resetDataKeyframe(model, data, model.key("poise").id)
    mujoco.mj_forward(model, data)
    foot, total = model.body("l_foot").id, float(model.body_mass.sum())
    above = total - float(model.body_subtreemass[foot])
    com = (total * data.subtree_com[model.body("pelvis").id] - (total - above) * data.subtree_com[foot]) / above
    over = float(com[2] - data.xanchor[model.joint("l_ankle_roll").id][2])
    servo = model.actuator("l_ankle_roll")
    print(f"on one foot, {above:.1f} kg stand on the ankle, their centre of mass {over:.2f} m over its roll axis: they topple at "
          f"{above * 9.81 * over:.0f} N m/rad. The ankle's roll servo as assumed: {float(servo.gainprm[0]):.0f} N m/rad, and at its peak of "
          f"{float(servo.forcerange[1]):g} N m it holds that weight {float(servo.forcerange[1]) / (above * 9.81) * 1000:.0f} mm from its axis.")

    print("\n1. every drive's servo stiffer, the motion slower")
    followed = {}                                       # a run that stood: what each drive gave, to feed ahead in table 3
    for stiffness in (1.0, 4.0, 8.0):
        model = robot(drives=stiffness)
        for name in MOTIONS:
            cells = []
            for pace in PACES:
                clip = clip_of(name, pace)
                _, series, report = run.simulate(model, clip)
                cells.append(f"{'as written' if pace == 1 else f'{pace:g} times as slow'}: {outcome(report, clip)}")
                if stiffness == 8.0 and pace == 2.0 and not report["fell"]:
                    followed[name] = (series["t"], series["force"])
            print(f"   servos x{stiffness:g}, {name:6s}  " + "; ".join(cells), flush=True)

    print("\n2. the ankles' roll servos alone 16 times as stiff")
    model = robot(ankle_roll=16.0)
    for name in MOTIONS:
        cells = []
        for pace in PACES[:2]:
            clip = clip_of(name, pace)
            cells.append(f"{'as written' if pace == 1 else f'{pace:g} times as slow'}: {outcome(run.simulate(model, clip)[2], clip)}")
        print(f"   {name:6s}  " + "; ".join(cells), flush=True)

    print("\n3. at half the pace, each drive fed ahead the torque the motion asks of it; every servo as assumed but the ankles' roll")
    for name in MOTIONS:
        if name not in followed:
            print(f"   {name}: no run of table 1 followed the plan at half the pace, so there is no torque to feed ahead")
            continue
        clip, cells = clip_of(name, 2.0), []
        for ankle_roll in (1.0, 2.0, 4.0, 8.0):
            report = run.simulate(robot(ankle_roll=ankle_roll), clip, ahead=followed[name])[2]
            cells.append(f"ankles' roll x{ankle_roll:g} ({float(servo.gainprm[0]) * ankle_roll:.0f} N m/rad): {outcome(report, clip)}")
        print(f"   {name:6s}  " + "; ".join(cells), flush=True)


if __name__ == "__main__":
    main()
