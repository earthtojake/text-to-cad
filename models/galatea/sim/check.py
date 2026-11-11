# /// script
# dependencies = ["mujoco", "numpy", "scipy"]
# ///
"""Is `sim/galatea.xml` the robot of the CAD model? What MuJoCo compiled, against `lib/dims.py` and `lib/kin.py`.

    cad run sim/check.py

Prints what it measured and exits non-zero when a check fails. It needs no CAD kernel and takes seconds.

1. The model compiles, with the model's 73 links, 72 joints, 26 coupled joints and 44 servos, and its keyframes are
   the poses of `lib/poses.py` as they are now.
2. It weighs what `checks/balance.py` weighs the robot at, within a per cent, and its centre of mass at each
   named pose is printed as that check prints it, to be set beside it.
3. Every joint stands where `dims.py` puts it, turns about its axis, and has its travel.
4. Every coupling has `kin.couplings()`'s ratio, and every servo its drive's peak torque.
5. At the zero pose the soles' boxes lie on the floor.
6. Forward kinematics: at each named pose every link stands where `kin.link_transforms` puts it.
7. Along each motion, by geometry alone: how far inside the support of its heels and the balls of its feet the
   centre of mass stays when the pose the servos are fed at each instant is set flat on the foot it stands on.
   A report, not a verdict: `checks/balance.py` holds the motions to it, and `run.py` has the dynamics' word.
8. Released at the zero pose, in the crouch and in `ready`, it stands where it stood (in `ready` for 30 s), and
   what the servos hold is printed, to set beside `checks/loads.py`'s statics.
"""

import math
import sys
from pathlib import Path

import mujoco
import numpy as np
from scipy.spatial import ConvexHull

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import run  # noqa: E402  (puts src/ on the path)
from lib import dims, kin  # noqa: E402
from lib.poses import MOTIONS, POSES  # noqa: E402

TOTAL_KG = 57.4                                      # `checks/balance.py`
PELVIS = np.array([0.0, 0.0, dims.HIP[2]])           # mm
PLANTED = {"bow": "l_foot", "crouch": "l_foot"}      # as `checks/balance.py` and `stances.py` set a pose down
SOLES = ("heel", "ball", "toe")
# What a foot stands on, as `checks/balance.py` counts it: the heel and the ball. The toe is a sprung hinge and
# carries what its spring gives it, which is nothing while the foot is flat. A frame of the gait stands on its toe.
BEARING = ("heel", "ball")
GAIT_FRAMES = {"stride"}


def matrix(transform):
    r, p = transform
    m = np.eye(4)
    m[:3, :3], m[:3, 3] = np.array(r), np.array(p)
    return m


def place(model, data, pose, ground=None):
    """Set the model at a pose in controls; `ground` moves the whole robot (a `kin` transform), else the pelvis stays."""
    data.qpos[:] = model.qpos0
    if ground is not None:
        g = matrix(ground)
        data.qpos[:3] = (g @ np.append(PELVIS, 1.0))[:3] / 1000.0
        quaternion = np.zeros(4)
        mujoco.mju_mat2Quat(quaternion, g[:3, :3].ravel())
        data.qpos[3:7] = quaternion
    for joint, degrees in kin.expand(pose).items():
        data.qpos[model.joint(joint).qposadr[0]] = math.radians(degrees)
    mujoco.mj_forward(model, data)


def corners(model, data, geom):
    """The four lower corners of a sole's box, in the world."""
    g = model.geom(geom).id
    centre, turn, half = data.geom_xpos[g], data.geom_xmat[g].reshape(3, 3), model.geom_size[g]
    return np.array([centre + turn @ (np.array([i, j, -1.0]) * half) for i in (-1, 1) for j in (-1, 1)])


def margin(model, data, floor=None, shapes=BEARING):
    """How far inside the support the centre of mass stands, mm (negative: outside), and which feet are down.
    The support is the hull of the corners of the soles' `shapes` within 2 mm of the floor: of the lowest of them, or
    of the height `floor` where a foot has been set flat. Nothing is said (nan) of a robot set with a corner more than
    that under the floor: it is standing on its other foot."""
    points = {f"{s}_{name}": corners(model, data, f"{s}_{name}") for s in kin.SIDES for name in shapes}
    lowest = min(float(p[:, 2].min()) for p in points.values())
    level = lowest if floor is None else floor
    down = np.vstack([p[p[:, 2] < level + 0.002] for p in points.values()])
    feet = "".join(sorted({name[0] for name, p in points.items() if p[:, 2].min() < level + 0.002}))
    if len(down) < 3 or lowest < level - 0.002:
        return float("nan"), feet
    hull = ConvexHull(down[:, :2])
    com = data.subtree_com[model.body("pelvis").id][:2]
    return float(-np.max(hull.equations[:, :2] @ com + hull.equations[:, 2])) * 1000.0, feet


def pose_at(keys, ease, t):
    """A motion's pose at `t`, in controls: its waypoints eased as `run.eased` eases the servos' targets."""
    times = [at for at, _ in keys]
    poses = [POSES[pose] if isinstance(pose, str) else pose for _, pose in keys]
    names = sorted(set().union(*poses))
    values, _ = run.eased(np.array(times), np.array([[pose.get(name, 0.0) for name in names] for pose in poses]), ease, t)
    return dict(zip(names, values))


def main():
    failed = []

    def check(ok, text):
        print(("  ok    " if ok else "  FAIL  ") + text)
        if not ok:
            failed.append(text)

    model = run.load()
    data = mujoco.MjData(model)
    joints, couplings = kin.all_joints(), kin.couplings()

    print("1. the model")
    links = {child for _, child, *_ in joints.values()} | {"pelvis"}
    bodies = {model.body(i).name for i in range(1, model.nbody)} - {"hanger"}
    check(bodies == links, f"{len(bodies)} links, the joint tree's {len(links)}")
    hinges = {model.joint(i).name for i in range(model.njnt)} - {"root"}
    check(hinges == set(joints), f"{len(hinges)} revolute joints, the joint tree's {len(joints)}, and one free joint at the pelvis")
    coupled = sum(len(ratios) - 1 for ratios in couplings.values())
    check(model.neq - 1 == coupled, f"{model.neq - 1} joint equalities for {len(couplings)} couplings ({coupled} followers), "
                                    "and the weld hold_pelvis, which is off")
    check(model.eq_active0[model.equality("hold_pelvis").id] == 0, "nothing holds the pelvis: the weld is inactive as compiled")
    driven = len(kin.controls()) - 2                                           # every control but the two toes
    check(model.nu == driven, f"{model.nu} servos for the {driven} driven controls; the toes are sprung")
    # A file written before the poses last changed has the old ones for keyframes: `mjcf.py --poses` writes them again.
    servos = run.Servos(model)
    stale = [name for name, pose in {"zero": {}, **POSES}.items()
             if name not in {model.key(i).name for i in range(model.nkey)} or float(np.abs(model.key(name).ctrl - servos.targets(pose)).max()) > 1e-6]
    check(not stale, f"its {model.nkey} keyframes are the zero pose and lib/poses.py's {len(POSES)} poses as they are now"
          + (f": not {', '.join(stale)} (`cad run sim/mjcf.py --poses` writes them again)" if stale else ""))

    print("2. mass")
    total = float(model.body_mass.sum())
    check(abs(total - TOTAL_KG) <= 0.01 * TOTAL_KG, f"{total:.2f} kg, within a per cent of checks/balance.py's {TOTAL_KG} kg")
    heavy = sorted(((float(model.body_mass[i]), model.body(i).name) for i in range(1, model.nbody)), reverse=True)[:6]
    print("        the heaviest links: " + ", ".join(f"{name} {kg:.2f} kg" for kg, name in heavy))
    print("        centre of mass at each pose, set on the floor as checks/balance.py sets it (mm), and its margin on the heels' and balls' boxes:")
    for name, pose in {"zero": {}, **POSES}.items():
        place(model, data, pose, kin.stance(pose, PLANTED[name]) if name in PLANTED else kin.settle(pose))
        com = data.subtree_com[model.body("pelvis").id] * 1000.0
        inside, feet = margin(model, data, shapes=SOLES if name in GAIT_FRAMES else BEARING)
        print(f"          {name:13s} ({com[0]:6.1f}, {com[1]:6.1f}, {com[2]:6.1f})   margin {inside:6.1f} mm on {feet}")

    print("3. joints: centre, axis, travel against lib/dims.py")
    place(model, data, {})
    worst = {"centre": 0.0, "axis": 0.0, "travel": 0.0}
    rows = []
    for label, (_, _, origin, direction, (low, high)) in joints.items():
        j = model.joint(label)
        axis = np.array(direction) / np.linalg.norm(direction)
        travel = np.degrees(j.range)
        worst["centre"] = max(worst["centre"], float(np.linalg.norm(data.xanchor[j.id] * 1000.0 - origin)))
        worst["axis"] = max(worst["axis"], float(np.linalg.norm(data.xaxis[j.id] - axis)))
        worst["travel"] = max(worst["travel"], abs(travel[0] - low), abs(travel[1] - high))
        rows.append((label, data.xanchor[j.id] * 1000.0, data.xaxis[j.id], travel, origin, direction, (low, high)))
    print("        joint                 centre mm                 axis          travel deg      | dims.py: centre, axis, travel")
    for label in ("l_hip_pitch", "r_hip_roll", "l_knee_pivot", "l_knee_rod", "r_ankle_pitch_pivot", "l_toe", "waist_pitch", "r_shoulder_roll",
                  "l_wrist_yaw", "r_thumb_opp", "l_index_pip", "neck_pitch"):
        _, at, axis, travel, origin, direction, limits = next(row for row in rows if row[0] == label)
        way = lambda v: "(" + ",".join(f"{round(float(c)):+d}" for c in v) + ")"  # noqa: E731
        print(f"          {label:20s} ({at[0]:7.1f},{at[1]:7.1f},{at[2]:7.1f})  {way(axis)}  {travel[0]:7.1f} to {travel[1]:6.1f}  "
              f"| ({origin[0]:7.1f},{origin[1]:7.1f},{origin[2]:7.1f})  {way(direction)}  {limits[0]:7.1f} to {limits[1]:6.1f}")
    check(worst["centre"] < 1e-3 and worst["axis"] < 1e-9 and worst["travel"] < 1e-6,
          f"all {len(joints)}: centres within {worst['centre']:.1e} mm, axes within {worst['axis']:.1e}, travel within {worst['travel']:.1e} deg")

    print("4. couplings and servos")
    off = 0.0
    for name, ratios in couplings.items():
        (first, ratio), *rest = ratios.items()
        for joint, other in rest:
            e = model.equality(f"{name}.{joint.split('_', 1)[1]}")
            pair = {model.joint(e.obj1id[0]).name, model.joint(e.obj2id[0]).name}
            off = max(off, abs(float(e.data[1]) - other / ratio) if pair == {joint, first} else 1.0, abs(float(e.data[0])))
    check(off < 1e-9, f"every coupled joint follows its coupling's first joint at kin.couplings()'s ratio (within {off:.1e})")
    wrong, by_drive = [], {}
    for i in range(model.nu):
        name = model.actuator(i).name
        bare = name[2:] if name[:2] in ("l_", "r_") else name
        if bare in dims.DRIVES:
            drive, count = dims.DRIVES[bare]
            peak = count * dims.ACTUATORS[drive]["peak"]
            by_drive.setdefault(f"{count} x {drive}" if count > 1 else drive, (peak, float(model.actuator_gainprm[i, 0]), []))[2].append(name)
            if abs(model.actuator_forcerange[i, 1] - peak) > 1e-9 or abs(model.actuator_forcerange[i, 0] + peak) > 1e-9:
                wrong.append(name)
    check(not wrong, "every drive's servo is limited to its drive's peak torque" + (f": not {wrong}" if wrong else ""))
    for drive, (peak, stiffness, names) in by_drive.items():
        print(f"          {drive:9s} peak {peak:5.1f} N m, servo stiffness {stiffness:6.0f} N m/rad: {len(names)} servos")

    print("5. the soles at the zero pose")
    place(model, data, {})
    heights = {f"{s}_{name}": float(corners(model, data, f"{s}_{name}")[:, 2].max()) * 1000.0 for s in kin.SIDES for name in SOLES}
    check(max(abs(z) for z in heights.values()) < 1e-3, "the six boxes' undersides are on the floor: "
          + ", ".join(f"{name} {z:+.4f} mm" for name, z in heights.items()))
    for name in SOLES:
        p = corners(model, data, f"l_{name}") * 1000.0
        print(f"          l_{name:5s} x {p[:, 0].min():6.1f} to {p[:, 0].max():6.1f}, y {p[:, 1].min():7.1f} to {p[:, 1].max():7.1f} mm")
    points = [point for _, _, point in kin.sole_points({}) if point[0] > 0]
    print(f"          kin's sole points, left: x {min(p[0] for p in points):.1f} to {max(p[0] for p in points):.1f}, "
          f"y {min(p[1] for p in points):.1f} to {max(p[1] for p in points):.1f} mm")

    print("6. forward kinematics against lib/kin.py, the pelvis where it is at the zero pose")
    origins = {"pelvis": PELVIS, **{child: np.array(origin) for _, child, origin, _, _ in joints.values()}}
    worst_at, worst_turn = 0.0, 0.0
    for name, pose in {"zero": {}, **POSES}.items():
        place(model, data, pose)
        there = kin.link_transforms(pose)
        for link, origin in origins.items():
            t = matrix(there[link])
            b = model.body(link).id
            worst_at = max(worst_at, float(np.linalg.norm(data.xpos[b] * 1000.0 - (t @ np.append(origin, 1.0))[:3])))
            worst_turn = max(worst_turn, float(np.abs(data.xmat[b].reshape(3, 3) - t[:3, :3]).max()))
        if name in ("ready", "crouch", "wave"):
            for link in ("r_palm", "l_middle_dist", "l_foot", "r_toe"):
                mine = data.xpos[model.body(link).id] * 1000.0
                theirs = (matrix(there[link]) @ np.append(origins[link], 1.0))[:3]
                print(f"          {name:7s} {link:14s} MuJoCo ({mine[0]:8.3f}, {mine[1]:8.3f}, {mine[2]:8.3f})   "
                      f"kin ({theirs[0]:8.3f}, {theirs[1]:8.3f}, {theirs[2]:8.3f}) mm")
    check(worst_at < 1e-3 and worst_turn < 1e-9, f"all {len(origins)} links at the zero pose and the {len(POSES)} named poses: "
                                                 f"within {worst_at:.1e} mm and {worst_turn:.1e} of a rotation matrix's entry")

    print("7. each motion's margin by geometry: the pose fed at each instant, flat on the foot it stands on (the one that leaves it most, of two)")
    for name, keys, ease in MOTIONS:
        least = (math.inf, 0.0, "")
        for t in np.linspace(0.0, keys[-1][0], 81):
            pose = pose_at(keys, ease, float(t))
            best = (-math.inf, "")
            for foot in ("l_foot", "r_foot"):
                place(model, data, pose, kin.stance(pose, foot))
                inside, feet = margin(model, data, floor=0.0)
                if not math.isnan(inside) and inside > best[0]:
                    best = (inside, feet)
            if best[0] < least[0]:
                least = (best[0], float(t), best[1])
        print(f"          {name:8s} least {least[0]:6.1f} mm, at {least[1]:.2f} s of {keys[-1][0]:g}, on {least[2] or 'no flat foot'}")

    print("8. released at a pose and left standing: what the servos hold (N m; checks/loads.py has the statics), and whether it stays")
    feet = [model.body(f"{s}_foot").id for s in kin.SIDES]
    for key, seconds, names in (("zero", 3.0, ("l_ankle_pitch", "l_knee", "l_hip_pitch")),
                                ("crouch", 3.0, ("l_knee", "waist_pitch", "l_hip_pitch", "l_ankle_pitch")),
                                ("ready", 30.0, ("l_knee", "waist_pitch", "l_ankle_pitch"))):
        pelvis = model.body("pelvis").id
        mujoco.mj_resetDataKeyframe(model, data, model.key(key).id)
        mujoco.mj_forward(model, data)
        posed = math.degrees(math.acos(min(1.0, data.xmat[pelvis][8])))          # a pose may tip the pelvis itself: the crouch does
        for k in range(round(seconds / model.opt.timestep)):
            if k == round(1.0 / model.opt.timestep):                           # settled: where the feet and the pelvis are
                stood = data.xpos[feet].copy(), data.xpos[pelvis].copy()
            mujoco.mj_step(model, data)
        tilt = math.degrees(math.acos(min(1.0, data.xmat[pelvis][8])))
        crept = float(np.linalg.norm(data.xpos[feet] - stood[0], axis=1).max()) * 1000.0
        sank = float(np.linalg.norm(data.xpos[pelvis] - stood[1])) * 1000.0
        print(f"          {key:7s} {seconds:g} s: " + ", ".join(f"{name} {abs(float(data.actuator_force[model.actuator(name).id])):.1f}" for name in names)
              + f"; pelvis {data.xpos[pelvis][2] * 1000:.1f} mm high, tilted {tilt:.2f} deg (the pose: {posed:.2f}); "
              + f"since 1 s the feet moved {crept:.2f} mm, the pelvis {sank:.2f}")
        check(crept < 1.0 and sank < 5.0 and abs(tilt - posed) < 5.0, f"{key}: it stands where it stood")

    print("OK" if not failed else f"{len(failed)} check(s) failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
