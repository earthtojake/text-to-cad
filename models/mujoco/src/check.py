"""Does a benchmark robot work? The proof, with numbers, for each robot's saved MuJoCo-function file.

    python src/check.py                    # every robot that has a MuJoCo function
    python src/check.py so101 --before /path/to/old/out/so101/so101.xml

For ``out/<robot>/<robot>.xml`` (written by ``src/<robot>_mujoco.py``) it prints:

- that MuJoCo compiles it, and what it holds (bodies, joints, actuators, keys, total mass);
- the health checks ``cad mjcf validate --compile required`` runs: every error and warning;
- that the folder loads after it is copied elsewhere (the robot's file and its ``scene.xml``);
- its collision geoms by kind, and, with ``--before FILE``, each one's kind and size against the
  geom of the same name in that file (an older build of the same robot);
- that the position servos hold the commanded key under gravity: started at the key, stepped
  ``--seconds`` of simulated time, the largest distance of any joint from its command against
  ``--threshold`` (radians or metres), with the timestep, the step count and the gains;
- that the plain exports beside it (``out/<robot>/export/<robot>.xml`` and ``.urdf``) validate.

Exit status 1 when any robot fails a check. Needs mujoco and numpy (the repository's .venv).
"""

from __future__ import annotations

import argparse
import collections
import shutil
import sys
import tempfile
from pathlib import Path

import mujoco
import numpy as np

from sources import OUT

ROBOTS = ("so101", "wxai")
KINDS = {int(value): name[len("mjGEOM_"):].lower() for name, value in mujoco.mjtGeom.__members__.items()
         if name.startswith("mjGEOM_")}


def colliding(model: mujoco.MjModel) -> dict[str, tuple[str, tuple[float, ...]]]:
    """Each colliding geom by name: its kind and its size (a mesh's: its fitted box, which changes with the mesh)."""
    return {model.geom(g).name: (KINDS[int(model.geom_type[g])], tuple(round(float(x), 6) for x in model.geom_size[g]))
            for g in range(model.ngeom) if model.geom_contype[g] or model.geom_conaffinity[g]}


def findings(path: Path) -> tuple[list[str], list[str]]:
    """The errors and warnings of ``cad mjcf validate --compile required`` (an ``.xml``) or ``cad urdf validate``."""
    from cad import mjcf, urdf

    result = mjcf.validate(path, compile="required") if path.suffix == ".xml" else urdf.validate(path)
    said = {"error": [], "warning": []}
    for finding in result.findings:
        if finding.severity in said:
            said[finding.severity].append(f"{finding.code}: {finding.message}")
    return said["error"], said["warning"]


def hold(model: mujoco.MjModel, key: str, seconds: float) -> tuple[int, float, str, int]:
    """Started at ``key`` with its controls, stepped ``seconds``: the steps taken, the largest distance of a joint
    from its command at the end, that joint's name, and the contacts at the end (a pose that holds by resting a
    link on another is no proof of the servos)."""
    data = mujoco.MjData(model)
    mujoco.mj_resetDataKeyframe(model, data, model.key(key).id)
    wanted = data.qpos.copy()
    steps = round(seconds / model.opt.timestep)
    for _step in range(steps):
        mujoco.mj_step(model, data)
    off = np.abs(data.qpos - wanted)
    worst = int(np.argmax(off))
    joint = next(model.joint(j).name for j in range(model.njnt) if model.jnt_qposadr[j] == worst)
    return steps, float(off[worst]), joint, int(data.ncon)


def check(robot: str, before: Path | None, seconds: float, threshold: float) -> bool:
    folder = OUT / robot
    path = folder / f"{robot}.xml"
    if not path.is_file():
        print(f"{robot}: {path} not found; make it with `python src/{robot}_mujoco.py`")
        return False
    ok = True
    model = mujoco.MjModel.from_xml_path(str(path))
    mass = float(model.body_subtreemass[0])
    print(f"{robot}: compiles: {model.nbody - 1} bodies, {model.njnt} joints, {model.nu} actuators, "
          f"{model.nkey} keys ({', '.join(model.key(k).name for k in range(model.nkey))}), {model.nmesh} meshes, "
          f"mass {mass:.4f} kg")
    errors, warnings = findings(path)
    print(f"  health: {len(errors)} errors, {len(warnings)} warnings")
    for line in errors + warnings:
        print(f"    {line}")
    ok &= not errors
    with tempfile.TemporaryDirectory() as moved:
        copied = Path(moved) / "elsewhere" / robot
        shutil.copytree(folder, copied, ignore=shutil.ignore_patterns("export"))
        again = mujoco.MjModel.from_xml_path(str(copied / path.name))
        scene = mujoco.MjModel.from_xml_path(str(copied / "scene.xml"))
        same = again.nmesh == model.nmesh and scene.nmesh == model.nmesh
        print(f"  moved: the copied folder loads ({again.nmesh} meshes; scene.xml {scene.nmesh} meshes, "
              f"{scene.ngeom - again.ngeom} geoms of its own)")
        ok &= same
    geoms = colliding(model)
    kinds = collections.Counter(kind for kind, _size in geoms.values())
    print(f"  collision: {len(geoms)} geoms (" + ", ".join(f"{kind} {count}" for kind, count in kinds.most_common()) + ")")
    if before is not None:
        old_model = mujoco.MjModel.from_xml_path(str(before))
        old = colliding(old_model)
        differ = [name for name in sorted(set(old) | set(geoms)) if old.get(name) != geoms.get(name)
                  and (name not in old or name not in geoms or old[name][0] != geoms[name][0]
                       or not np.allclose(old[name][1], geoms[name][1], atol=2e-6))]
        print(f"  before ({before}): {len(old)} geoms, mass {float(old_model.body_subtreemass[0]):.4f} kg; "
              f"{len(differ)} geoms differ in kind or size (to 2e-6 m)")
        for name in differ:
            print(f"    {name}: {old.get(name)} -> {geoms.get(name)}")
        excludes = [sorted({(model_.body(int(s >> 16)).name, model_.body(int(s & 0xFFFF)).name)
                            for s in model_.exclude_signature}) for model_ in (old_model, model)]
        print(f"    contact excludes: {len(excludes[0])} before, {len(excludes[1])} now"
              + ("" if excludes[0] == excludes[1] else f"; added {sorted(set(excludes[1]) - set(excludes[0]))}, "
                                                        f"gone {sorted(set(excludes[0]) - set(excludes[1]))}"))
        ok &= not differ and abs(float(old_model.body_subtreemass[0]) - mass) < 1e-6
    held = True
    for k in range(model.nkey):
        key = model.key(k).name
        if not np.any(model.key_ctrl[k]):
            continue  # a mechanism state of the model: a pose, with no command
        steps, off, joint, contacts = hold(model, key, seconds)
        gains = sorted({round(float(model.actuator_gainprm[a, 0]), 6) for a in range(model.nu)})
        held &= off < threshold and not contacts
        print(f"  hold: key {key}, timestep {model.opt.timestep} s, {steps} steps ({seconds} s), kp {gains}: "
              f"worst joint {joint} is {off:.5f} from its command (threshold {threshold}): "
              f"{'held' if off < threshold else 'NOT held'}, {contacts} contacts")
    ok &= held and model.nu > 0
    for plain in (folder / "export" / f"{robot}.xml", folder / "export" / f"{robot}.urdf"):
        if not plain.is_file():
            print(f"  plain: {plain} not found; make it with `python src/{robot}.py`")
            ok = False
            continue
        bad, warned = findings(plain)
        print(f"  plain {plain.name}: {len(bad)} errors, {len(warned)} warnings")
        for line in bad + warned:
            print(f"    {line}")
        ok &= not bad
    print(f"  {'OK' if ok else 'FAILED'}")
    return ok


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("robots", nargs="*", metavar="robot", help=f"one or more of {', '.join(ROBOTS)} (default: all)")
    parser.add_argument("--before", type=Path, help="an older build of the one robot named, to compare collisions with")
    parser.add_argument("--seconds", type=float, default=5.0, help="simulated time the pose is held for")
    parser.add_argument("--threshold", type=float, default=0.02, help="how far a joint may end from its command")
    args = parser.parse_args(argv)
    unknown = [robot for robot in args.robots if robot not in ROBOTS]
    if unknown:
        parser.error(f"unknown robot {', '.join(unknown)}: one of {', '.join(ROBOTS)}")
    if args.before is not None and len(args.robots) != 1:
        parser.error("--before compares one robot: name it")
    done = [check(robot, args.before, args.seconds, args.threshold) for robot in (args.robots or ROBOTS)]
    return 0 if all(done) else 1


if __name__ == "__main__":
    sys.exit(main())
